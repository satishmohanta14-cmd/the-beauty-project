"""
Unit & Integration Tests for Next.js ISR Public Endpoints & Affiliate Redirection.
==================================================================================
Tests:
  - GET /api/v1/products/{slug} (INCI breakdown, price comparison, 30-day trend, robots meta)
  - GET /api/v1/dupes/{slug} (dupe alternatives with similarity & price delta)
  - GET /api/v1/ingredients/{slug} (canonical details & top products ordered by concentration)
  - GET /api/v1/sitemap/{archetype} (paginated list of indexable pages)
  - GET /go/{offer_id} (telemetry recording & 307 temporary redirect)
  - Response caching & header verification
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.models.brand import Brand
from app.models.dupe_edge import DupeEdge
from app.models.ingredient import Ingredient
from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.retailer import Retailer
from app.models.variant import Variant


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    return session


@pytest.fixture
def client(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestPublicProductsAPI:
    def test_product_not_found_returns_404(self, client, mock_db_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        resp = client.get("/api/v1/products/non-existent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_product_found_returns_complete_payload_and_headers(self, client, mock_db_session):
        prod_id = uuid.uuid4()
        brand = Brand(id=uuid.uuid4(), name="Minimalist", slug="minimalist")
        product = Product(
            id=prod_id,
            name="10% Niacinamide Serum",
            slug="10-niacinamide-serum",
            brand_id=brand.id,
            brand=brand,
            category_id="serum",
            format="serum",
            claims=["oil control", "barrier repair"],
            markets=["IN", "US"],
            dcs_score=85,
            index_tier="indexed",
        )

        mock_prod_res = MagicMock()
        mock_prod_res.scalar_one_or_none.return_value = product

        mock_ing_res = MagicMock()
        mock_ing_res.all.return_value = [
            MagicMock(
                position=1,
                is_active=False,
                inci_name="Water",
                canonical_name="Water",
                function_=["solvent"],
                comedogenic=0,
                irritancy=0,
            ),
            MagicMock(
                position=2,
                is_active=True,
                inci_name="Niacinamide",
                canonical_name="Niacinamide",
                function_=["barrier repair"],
                comedogenic=0,
                irritancy=1,
            ),
        ]

        mock_comp_res = MagicMock()
        mock_comp_res.all.return_value = [
            MagicMock(
                retailer_name="Nykaa",
                size_ml=Decimal("30.00"),
                price=Decimal("599.00"),
                currency="INR",
                in_stock=True,
                offer_id=uuid.uuid4(),
            )
        ]

        mock_hist_res = MagicMock()
        mock_hist_res.all.return_value = []

        # Sequence of execute queries: Product, Ingredients, Price Comparison, History
        mock_db_session.execute.side_effect = [
            mock_prod_res,
            mock_ing_res,
            mock_comp_res,
            mock_hist_res,
        ]

        resp = client.get("/api/v1/products/10-niacinamide-serum")
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "10-niacinamide-serum"
        assert data["brand"]["name"] == "Minimalist"
        assert data["dcs_score"] == 85
        assert data["robots_meta"] == "index, follow"
        assert len(data["ingredients"]) == 2
        assert data["ingredients"][0]["position"] == 1
        assert len(data["price_comparison"]) == 1
        assert "Cache-Control" in resp.headers


class TestPublicDupesAPI:
    def test_dupes_not_found_returns_404(self, client, mock_db_session):
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_res

        resp = client.get("/api/v1/dupes/unknown-product")
        assert resp.status_code == 404

    def test_dupes_found_returns_ranked_alternatives(self, client, mock_db_session):
        prod_id = uuid.uuid4()
        dupe_id = uuid.uuid4()

        brand1 = Brand(id=uuid.uuid4(), name="Brand 1", slug="brand-1")
        prod = Product(
            id=prod_id,
            name="Expensive Serum",
            slug="expensive-serum",
            brand_id=brand1.id,
            brand=brand1,
            category_id="serum",
        )

        brand2 = Brand(id=uuid.uuid4(), name="Brand 2", slug="brand-2")
        dupe_prod = Product(
            id=dupe_id,
            name="Affordable Dupe",
            slug="affordable-dupe",
            brand_id=brand2.id,
            brand=brand2,
            category_id="serum",
            format="serum",
        )

        edge = DupeEdge(
            id=uuid.uuid4(),
            product_a=prod_id,
            product_b=dupe_id,
            similarity=Decimal("0.94"),
            price_delta_pct=Decimal("-45.50"),
            method_version="v1_inci_weighted",
        )

        prod_res = MagicMock()
        prod_res.scalar_one_or_none.return_value = prod

        edge_res = MagicMock()
        edge_res.scalars.return_value.all.return_value = [edge]

        target_res = MagicMock()
        target_res.scalar_one_or_none.return_value = dupe_prod

        offer_res = MagicMock()
        offer_res.one_or_none.return_value = MagicMock(
            id=uuid.uuid4(),
            price=Decimal("299.00"),
            currency="INR",
            size_ml=Decimal("30.00"),
        )

        mock_db_session.execute.side_effect = [
            prod_res,
            edge_res,
            target_res,
            offer_res,
        ]

        resp = client.get("/api/v1/dupes/expensive-serum")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product_slug"] == "expensive-serum"
        assert len(data["dupes"]) == 1
        assert data["dupes"][0]["similarity"] == pytest.approx(0.94)
        assert data["dupes"][0]["price_delta_pct"] == pytest.approx(-45.50)


class TestPublicIngredientsAPI:
    def test_ingredient_not_found_returns_404(self, client, mock_db_session):
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_res

        resp = client.get("/api/v1/ingredients/unknown-chemical")
        assert resp.status_code == 404

    def test_ingredient_found_returns_canonical_info_and_top_products(self, client, mock_db_session):
        ing = Ingredient(
            id=uuid.uuid4(),
            inci_name="Salicylic Acid",
            canonical_name="Salicylic Acid",
            function_=["exfoliant"],
            evidence_grade="A",
            comedogenic=0,
            irritancy=2,
        )

        mock_ing_res = MagicMock()
        mock_ing_res.scalars.return_value.all.return_value = [ing]

        mock_prod_res = MagicMock()
        mock_prod_res.all.return_value = [
            MagicMock(
                product_id=uuid.uuid4(),
                name="2% BHA Toner",
                slug="2-bha-toner",
                brand_name="Paula's Choice",
                position=3,
                is_active=True,
                dcs_score=95,
            )
        ]

        mock_db_session.execute.side_effect = [mock_ing_res, mock_prod_res]

        resp = client.get("/api/v1/ingredients/salicylic-acid")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inci_name"] == "Salicylic Acid"
        assert len(data["top_products"]) == 1
        assert data["top_products"][0]["position"] == 3


class TestPublicSitemapAPI:
    def test_sitemap_returns_paginated_indexable_pages(self, client, mock_db_session):
        count_res = MagicMock()
        count_res.scalar.return_value = 1

        rows_res = MagicMock()
        rows_res.all.return_value = [
            MagicMock(
                url="/p/minimalist/niacinamide-10",
                locale="en-in",
                first_indexed_at=None,
                dcs_score=85,
            )
        ]

        mock_db_session.execute.side_effect = [count_res, rows_res]

        resp = client.get("/api/v1/sitemap/product?page=1&size=50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["archetype"] == "product"
        assert data["total"] == 1
        assert len(data["urls"]) == 1
        assert data["urls"][0]["dcs_score"] == 85


class TestAffiliateRedirectionAPI:
    def test_unknown_offer_returns_404(self, client, mock_db_session):
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_res

        offer_id = uuid.uuid4()
        resp = client.get(f"/go/{offer_id}")
        assert resp.status_code == 404

    def test_known_offer_records_telemetry_and_redirects_307(self, client, mock_db_session):
        offer_id = uuid.uuid4()
        offer = Offer(
            id=offer_id,
            variant_id=uuid.uuid4(),
            retailer_id=uuid.uuid4(),
            price=Decimal("499.00"),
            currency="INR",
            affiliate_url="https://affiliate.retailer.com/deep-link-track?subid=123",
        )

        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = offer
        mock_db_session.execute.return_value = mock_res

        resp = client.get(
            f"/go/{offer_id}",
            headers={"User-Agent": "Mozilla/5.0 Test", "Referer": "https://thebeautyproject.com/p/serum"},
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert resp.headers["Location"] == "https://affiliate.retailer.com/deep-link-track?subid=123"
        assert resp.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
