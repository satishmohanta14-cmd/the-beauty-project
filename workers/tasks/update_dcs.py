"""
Periodic & Event-Driven DCS Update Tasks
========================================
Tasks:
  ``update_dcs.re_score_page``:
      Re-score a programmatic page and its underlying product after new data ingestion.

  ``update_dcs.re_score_product``:
      Re-score a product directly and update its DCS score and index_tier.

  ``update_dcs.periodic_rescore_all_pages``:
      Periodic Celery Beat task that evaluates all programmatic pages to promote/demote
      pages as new price records (>= 30d history), reviews (>= 15), or offers are detected.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from celery.schedules import crontab

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Register 4-hourly periodic DCS audit in Celery Beat
celery_app.conf.beat_schedule.update(
    {
        "dcs-periodic-rescore-every-4h": {
            "task": "update_dcs.periodic_rescore_all_pages",
            "schedule": crontab(minute="15", hour="*/4"),  # 00:15, 04:15, 08:15, etc.
        },
    }
)


@celery_app.task(
    name="update_dcs.re_score_page",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def re_score_page(self, page_id: str) -> dict:
    """Re-score a page and its associated product using DCSEvaluator."""
    async def _run() -> dict:
        from app.db.session import async_session
        from app.services.dcs_evaluator import DCSEvaluator

        pid = uuid.UUID(page_id)
        async with async_session() as session:
            evaluator = DCSEvaluator(session)
            page, result = await evaluator.evaluate_page(pid)
            await session.commit()

            return {
                "page_id": str(page.id),
                "url": page.url,
                "archetype": page.archetype,
                "dcs_score": page.dcs_score,
                "indexable": page.indexable,
                "index_tier": result.index_tier,
                "robots_meta": result.robots_meta,
                "reasons": result.reasons,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("re_score_page failed for %s: %s", page_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="update_dcs.re_score_product",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def re_score_product(self, product_id: str) -> dict:
    """Re-score a product directly and update product.dcs_score and product.index_tier."""
    async def _run() -> dict:
        from app.db.session import async_session
        from app.services.dcs_evaluator import DCSEvaluator

        prod_uuid = uuid.UUID(product_id)
        async with async_session() as session:
            evaluator = DCSEvaluator(session)
            result = await evaluator.evaluate_product(prod_uuid)
            await session.commit()

            return {
                "product_id": str(product_id),
                "dcs_score": result.score,
                "index_tier": result.index_tier,
                "indexable": result.indexable,
                "reasons": result.reasons,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("re_score_product failed for %s: %s", product_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="update_dcs.periodic_rescore_all_pages",
    bind=True,
    max_retries=1,
)
def periodic_rescore_all_pages(self) -> dict:
    """
    Fan-out task dispatched on schedule by Celery Beat.
    Queries all pages in the system and triggers re-scoring for each.
    """
    async def _get_all_page_ids() -> list[str]:
        from sqlalchemy import select

        from app.db.session import async_session
        from app.models.page import Page

        async with async_session() as session:
            rows = (await session.execute(select(Page.id))).scalars().all()
            return [str(pid) for pid in rows]

    try:
        page_ids = asyncio.run(_get_all_page_ids())
    except Exception as exc:
        logger.exception("periodic_rescore_all_pages: failed to fetch page IDs: %s", exc)
        raise self.retry(exc=exc)

    for pid in page_ids:
        re_score_page.delay(pid)

    logger.info("periodic_rescore_all_pages: queued %d pages for re-scoring", len(page_ids))
    return {"pages_queued": len(page_ids)}
