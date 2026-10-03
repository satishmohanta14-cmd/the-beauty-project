"""
Google Search Console (GSC) API Client.
Connects to Search Console API and queries daily search performance grouped by page URL.
"""
from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class GSCPageMetric:
    url: str
    date: datetime.date
    clicks: int
    impressions: int
    ctr: float
    position: float


class GSCClient:
    """
    Client for Google Search Console API (searchanalytics.query).
    """

    def __init__(
        self,
        site_url: str | None = None,
        service_account_info: dict[str, Any] | None = None,
        credentials_file: str | None = None,
    ) -> None:
        self.site_url = site_url or settings.gsc_site_url
        self.service_account_info = service_account_info
        self.credentials_file = credentials_file or settings.gsc_credentials_file
        self._service = None

    def _get_service(self):
        """Initializes the googleapiclient searchconsole v1 service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            scopes = ["https://www.googleapis.com/auth/webmasters.readonly"]

            if self.service_account_info:
                creds = service_account.Credentials.from_service_account_info(
                    self.service_account_info, scopes=scopes
                )
            elif settings.gsc_service_account_json:
                info = json.loads(settings.gsc_service_account_json)
                creds = service_account.Credentials.from_service_account_info(
                    info, scopes=scopes
                )
            elif self.credentials_file:
                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_file, scopes=scopes
                )
            else:
                logger.warning("No GSC credentials configured — running in stub mode")
                return None

            self._service = build("searchconsole", "v1", credentials=creds)
            return self._service
        except ImportError:
            logger.warning("google-api-python-client not installed — running in stub mode")
            return None
        except Exception as exc:
            logger.exception("Failed to initialize Google Search Console client: %s", exc)
            return None

    def query_daily_page_metrics(
        self,
        target_date: datetime.date | str,
        site_url: str | None = None,
        row_limit: int = 25000,
    ) -> list[GSCPageMetric]:
        """
        Query GSC search performance for target_date grouped by page URL.
        """
        if isinstance(target_date, str):
            target_date = datetime.date.fromisoformat(target_date)

        date_str = target_date.isoformat()
        site = site_url or self.site_url
        service = self._get_service()

        if not service:
            logger.info("GSC service not initialized. Returning empty metrics.")
            return []

        request_body = {
            "startDate": date_str,
            "endDate": date_str,
            "dimensions": ["page"],
            "rowLimit": row_limit,
            "dataState": "final",
        }

        try:
            response = (
                service.searchanalytics()
                .query(siteUrl=site, body=request_body)
                .execute()
            )
            rows = response.get("rows", [])
            return self._parse_rows(rows, target_date)
        except Exception as exc:
            logger.exception("Error querying GSC API for %s on %s: %s", site, date_str, exc)
            raise

    @staticmethod
    def _parse_rows(rows: list[dict[str, Any]], target_date: datetime.date) -> list[GSCPageMetric]:
        """Parses API response rows into typed GSCPageMetric objects."""
        results: list[GSCPageMetric] = []
        for r in rows:
            keys = r.get("keys", [])
            if not keys:
                continue
            url = keys[0]
            clicks = int(r.get("clicks", 0))
            impressions = int(r.get("impressions", 0))
            ctr = float(r.get("ctr", 0.0))
            position = float(r.get("position", 0.0))

            results.append(
                GSCPageMetric(
                    url=url,
                    date=target_date,
                    clicks=clicks,
                    impressions=impressions,
                    ctr=round(ctr, 4),
                    position=round(position, 2),
                )
            )
        return results
