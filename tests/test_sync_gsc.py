"""
Unit Tests for GSC Client, Search Performance Sync & Admin Analytics.
======================================================================
Tests:
  - GSCClient row parsing into GSCPageMetric
  - Archetype derivation logic
  - Celery task sync_daily_performance mapping URLs to page.id
  - Admin endpoint GET /api/v1/admin/analytics/archetypes
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.page import Page
from app.models.search_performance import SearchPerformance
from app.services.gsc_client import GSCClient, GSCPageMetric
from workers.tasks.sync_gsc import _derive_archetype_from_path


class TestGSCClient:
    def test_parse_rows_converts_raw_dict_to_dataclass(self) -> None:
        raw_rows = [
            {
                "keys": ["https://thebeautyproject.com/p/minimalist/niacinamide-10"],
                "clicks": 150,
                "impressions": 3000,
                "ctr": 0.05,
                "position": 4.2,
            },
            {
                "keys": ["https://thebeautyproject.com/ingredient/salicylic-acid"],
                "clicks": 80,
                "impressions": 1200,
                "ctr": 0.0667,
                "position": 2.1,
            },
        ]
        test_date = datetime.date(2025, 1, 15)
        parsed = GSCClient._parse_rows(raw_rows, test_date)

        assert len(parsed) == 2
        assert parsed[0].url == "https://thebeautyproject.com/p/minimalist/niacinamide-10"
        assert parsed[0].clicks == 150
        assert parsed[0].impressions == 3000
        assert parsed[0].ctr == 0.05
        assert parsed[0].position == 4.2
        assert parsed[0].date == test_date

    def test_derive_archetype_from_path(self) -> None:
        assert _derive_archetype_from_path("/p/brand/product") == "product"
        assert _derive_archetype_from_path("/ingredient/water") == "ingredient"
        assert _derive_archetype_from_path("/dupe/product-slug") == "dupe"
        assert _derive_archetype_from_path("/dupes/product-slug") == "dupe"
        assert _derive_archetype_from_path("/best/vitamin-c") == "best"
        assert _derive_archetype_from_path("/vs/prod-a-vs-prod-b") == "vs"
        assert _derive_archetype_from_path("/conflict/retinol-and-aha") == "conflict"
        assert _derive_archetype_from_path("/under/500-rs") == "under"
        assert _derive_archetype_from_path("/about-us") == "other"


class TestSyncGSCTask:
    @pytest.mark.asyncio
    async def test_sync_maps_url_to_page_and_upserts(self) -> None:
        from workers.tasks.sync_gsc import sync_daily_performance

        page_id = uuid.uuid4()
        test_date = datetime.date(2025, 1, 15)

        mock_page_row = MagicMock(
            id=page_id,
            url="/p/minimalist/niacinamide-10",
            archetype="product",
        )

        fake_metric = GSCPageMetric(
            url="https://thebeautyproject.com/p/minimalist/niacinamide-10",
            date=test_date,
            clicks=25,
            impressions=500,
            ctr=0.05,
            position=3.5,
        )

        with patch("app.services.gsc_client.GSCClient.query_daily_page_metrics", return_value=[fake_metric]):
            mock_session = AsyncMock()
            # First query: select(Page.id, Page.url, Page.archetype)
            page_query_res = MagicMock()
            page_query_res.all.return_value = [mock_page_row]

            mock_session.execute.side_effect = [
                page_query_res,     # pages select
                MagicMock(),        # insert...on_conflict upsert
            ]

            with patch("app.db.session.async_session", return_value=mock_session):
                # Run the inner async logic directly
                res = sync_daily_performance.apply(kwargs={"date_str": "2025-01-15"}).get()
                assert res["synced"] == 1
                assert res["date"] == "2025-01-15"


class TestAdminArchetypeAnalyticsAPI:
    def test_analytics_archetypes_endpoint(self) -> None:
        mock_db_session = AsyncMock()

        # 1. Page stats: product (10 total, 8 indexable), ingredient (5 total, 5 indexable)
        page_res = MagicMock()
        page_res.all.return_value = [
            MagicMock(archetype="product", total_pages=10, indexable_pages=8),
            MagicMock(archetype="ingredient", total_pages=5, indexable_pages=5),
        ]

        # 2. SearchPerformance stats
        perf_res = MagicMock()
        perf_res.all.return_value = [
            MagicMock(
                archetype="product",
                total_impressions=10000,
                total_clicks=500,
                avg_ctr=0.05,
                avg_position=4.5,
            ),
            MagicMock(
                archetype="ingredient",
                total_impressions=4000,
                total_clicks=240,
                avg_ctr=0.06,
                avg_position=2.8,
            ),
        ]

        mock_db_session.execute.side_effect = [page_res, perf_res]
        app.dependency_overrides[get_db] = lambda: mock_db_session

        with TestClient(app) as client:
            resp = client.get("/api/v1/admin/analytics/archetypes?days=30")
            assert resp.status_code == 200
            data = resp.json()
            assert data["days_evaluated"] == 30
            assert len(data["archetypes"]) == 2

            prod_stats = next(a for a in data["archetypes"] if a["archetype"] == "product")
            assert prod_stats["total_pages"] == 10
            assert prod_stats["indexable_pages"] == 8
            assert prod_stats["index_rate_pct"] == 80.0
            assert prod_stats["total_impressions"] == 10000
            assert prod_stats["total_clicks"] == 500
            assert prod_stats["average_ctr_pct"] == 5.0
            assert prod_stats["average_position"] == 4.5

        app.dependency_overrides.clear()
