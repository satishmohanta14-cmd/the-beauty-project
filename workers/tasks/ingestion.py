"""Ingestion Celery tasks — feed import and retailer scrape workers."""
from __future__ import annotations

from workers.celery_app import celery_app


@celery_app.task(name="ingestion.import_affiliate_feed", bind=True, max_retries=3)
def import_affiliate_feed(self, retailer_id: str, feed_url: str) -> dict:
    """
    Download and parse an affiliate product feed, creating new Offer rows.

    ARCHITECTURE NOTE: This task MUST only INSERT into the offer table.
    Never update existing rows — see the append-only invariant in gemini.md.
    """
    # TODO: implement feed parsing and bulk INSERT
    raise NotImplementedError


@celery_app.task(name="ingestion.scrape_retailer_prices", bind=True, max_retries=3)
def scrape_retailer_prices(self, retailer_id: str) -> dict:
    """Scrape current prices for all variants associated with a retailer."""
    # TODO: implement scraper, create new Offer rows
    raise NotImplementedError
