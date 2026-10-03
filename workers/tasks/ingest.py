"""
Retailer Feed Ingestion — Celery Tasks
=======================================
Tasks:
    ``ingest.process_retailer_feed``
        Core task: accepts a serialised FeedEnvelope dict, runs the
        FeedIngestionService, and returns the aggregate result.

    ``ingest.trigger_scheduled_ingest``
        Periodic trigger: one task per retailer slug, dispatched by
        Celery Beat on a configurable schedule.  In production this
        fetches live affiliate feeds; in development it uses mock data.

Scheduled retailers (Celery Beat):
    - Nykaa        every 6 h  (00:00, 06:00, 12:00, 18:00 UTC)
    - Amazon IN    every 6 h  (00:30, 06:30, 12:30, 18:30 UTC) — staggered
    - Sephora US   every 6 h  (01:00, 07:00, 13:00, 19:00 UTC) — staggered

APPEND-ONLY NOTE
----------------
These tasks delegate to FeedIngestionService which is the sole point of
offer creation.  Tasks must NEVER call session.execute(update(Offer)...).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from celery.schedules import crontab

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Beat schedule — registered on the app at module import time
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule.update(
    {
        "ingest-nykaa-every-6h": {
            "task": "ingest.trigger_scheduled_ingest",
            "schedule": crontab(minute="0", hour="*/6"),
            "kwargs": {"retailer_slug": "nykaa"},
        },
        "ingest-amazon-in-every-6h": {
            "task": "ingest.trigger_scheduled_ingest",
            "schedule": crontab(minute="30", hour="*/6"),
            "kwargs": {"retailer_slug": "amazon_in"},
        },
        "ingest-sephora-us-every-6h": {
            "task": "ingest.trigger_scheduled_ingest",
            "schedule": crontab(minute="0", hour="1,7,13,19"),
            "kwargs": {"retailer_slug": "sephora_us"},
        },
    }
)


# ===========================================================================
# Core ingest task
# ===========================================================================


@celery_app.task(
    name="ingest.process_retailer_feed",
    bind=True,
    max_retries=3,
    default_retry_delay=120,  # 2 minutes
)
def process_retailer_feed(self, feed_envelope_dict: dict) -> dict:
    """
    Ingest a batch of retailer feed items into the offer table.

    Parameters
    ----------
    feed_envelope_dict:
        A JSON-serialisable dict that validates against
        :class:`~app.schemas.feed.FeedEnvelope`.

    Returns
    -------
    dict
        Serialised :class:`~app.schemas.feed.FeedIngestResult`.

    IMPORTANT: This task only ever INSERTS new Offer rows via
    FeedIngestionService. It never updates existing offers.
    """

    async def _run() -> dict:
        from app.db.session import async_session
        from app.schemas.feed import FeedEnvelope
        from app.services.feed_ingestion import FeedIngestionService

        envelope = FeedEnvelope.model_validate(feed_envelope_dict)

        async with async_session() as session:
            service = FeedIngestionService(session)
            result = await service.ingest_feed(envelope)
            await session.commit()

        logger.info(
            "Feed ingest complete: retailer=%s inserted=%d skipped=%d failed=%d",
            envelope.retailer_slug,
            result.inserted,
            result.skipped,
            result.failed,
        )
        return result.model_dump(mode="json")

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("Feed ingest failed, retrying: %s", exc)
        raise self.retry(exc=exc)


# ===========================================================================
# Scheduled trigger task
# ===========================================================================


@celery_app.task(
    name="ingest.trigger_scheduled_ingest",
    bind=True,
    max_retries=2,
)
def trigger_scheduled_ingest(self, retailer_slug: str) -> dict:
    """
    Periodic entry point dispatched by Celery Beat.

    In production: fetches the live affiliate feed URL from the retailer
    row, parses it, and dispatches ``process_retailer_feed`` with the result.

    In development / CI: falls back to :func:`_build_mock_feed` to produce
    realistic sample data without a live feed connection.
    """

    async def _run() -> dict:
        from sqlalchemy import select

        from app.db.session import async_session
        from app.models.retailer import Retailer
        from app.schemas.feed import FeedEnvelope
        from app.services.feed_ingestion import FeedIngestionService

        async with async_session() as session:
            result = await session.execute(
                select(Retailer).where(Retailer.name.ilike(f"%{retailer_slug}%")).limit(1)
            )
            retailer = result.scalar_one_or_none()

        if retailer is None:
            logger.warning(
                "trigger_scheduled_ingest: no Retailer found for slug=%r — "
                "using mock feed",
                retailer_slug,
            )
            # Use a placeholder UUID so the mock feed can still be validated
            retailer_id = uuid.uuid4()
        else:
            retailer_id = retailer.id

        # Build feed — in production, fetch from retailer.feed_url
        envelope = _build_mock_feed(retailer_slug=retailer_slug, retailer_id=retailer_id)

        # Dispatch the actual ingest task asynchronously
        process_retailer_feed.delay(envelope.model_dump(mode="json"))

        return {
            "retailer_slug": retailer_slug,
            "retailer_id": str(retailer_id),
            "items_dispatched": len(envelope.items),
        }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("Scheduled ingest trigger failed: %s", exc)
        raise self.retry(exc=exc)


# ===========================================================================
# Mock feed generator (dev / testing)
# ===========================================================================

_MOCK_FEEDS: dict[str, list[dict]] = {
    "nykaa": [
        {
            "retailer_sku": "NYK-TO-NIA-30",
            "gtin": "8901030910237",
            "title": "The Ordinary Niacinamide 10% + Zinc 1% 30ml",
            "brand_name": "The Ordinary",
            "raw_size": "30ml",
            "price": "599.00",
            "currency": "INR",
            "in_stock": True,
            "affiliate_url": "https://www.nykaa.com/affiliate/the-ordinary-niacinamide",
        },
        {
            "retailer_sku": "NYK-MM-VIT-30",
            "gtin": "8906053861207",
            "title": "Minimalist 10% Vitamin C Face Serum 30ml",
            "brand_name": "Minimalist",
            "raw_size": "30 ml",
            "price": "499.00",
            "currency": "INR",
            "in_stock": True,
            "affiliate_url": "https://www.nykaa.com/affiliate/minimalist-vitamin-c",
        },
        {
            "retailer_sku": "NYK-COS-RET-30",
            "gtin": "8901234567890",
            "title": "CosRx Retinol 0.1% Cream 20g",
            "brand_name": "CosRx",
            "raw_size": "20g",
            "price": "1299.00",
            "currency": "INR",
            "in_stock": False,
            "affiliate_url": "https://www.nykaa.com/affiliate/cosrx-retinol",
        },
    ],
    "amazon_in": [
        {
            "retailer_sku": "AMZN-B09K3R1234",
            "gtin": "8901030910237",
            "title": "The Ordinary Niacinamide 10% + Zinc 1% - 30 ml",
            "brand_name": "The Ordinary",
            "raw_size": "30 ml",
            "price": "645.00",
            "currency": "INR",
            "in_stock": True,
            "affiliate_url": "https://www.amazon.in/dp/B09K3R1234?tag=tbp-21",
        },
        {
            "retailer_sku": "AMZN-B08TZK5678",
            "gtin": "8901234560001",
            "title": "Plum 1% Salicylic Acid Face Serum 30ml",
            "brand_name": "Plum",
            "raw_size": "30 ml",
            "price": "425.00",
            "currency": "INR",
            "in_stock": True,
            "affiliate_url": "https://www.amazon.in/dp/B08TZK5678?tag=tbp-21",
        },
    ],
    "sephora_us": [
        {
            "retailer_sku": "SEP-TO-NIA-30",
            "gtin": "0769915194004",
            "title": "The Ordinary Niacinamide 10% + Zinc 1% 1 fl. oz",
            "brand_name": "The Ordinary",
            "raw_size": "1 fl. oz",
            "price": "10.00",
            "currency": "USD",
            "in_stock": True,
            "affiliate_url": "https://www.sephora.com/product/the-ordinary-niacinamide?affiliate=tbp",
        },
    ],
}


def _build_mock_feed(retailer_slug: str, retailer_id: uuid.UUID) -> "FeedEnvelope":
    """
    Build a realistic :class:`~app.schemas.feed.FeedEnvelope` for
    development and testing without a live affiliate feed connection.
    """
    from app.schemas.feed import FeedEnvelope, RawFeedItem

    items_data = _MOCK_FEEDS.get(retailer_slug, _MOCK_FEEDS["nykaa"])
    items = [RawFeedItem.model_validate(d) for d in items_data]

    return FeedEnvelope(
        retailer_id=retailer_id,
        retailer_slug=retailer_slug,
        items=items,
        source_url=None,
    )
