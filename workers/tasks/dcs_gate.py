"""DCS gate Celery task — recalculates Data Completeness Score for a page."""
from __future__ import annotations

import asyncio
import logging
import uuid

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="dcs_gate.recalculate_dcs", bind=True, max_retries=3)
def recalculate_dcs(self, page_id: str) -> dict:
    """
    Recalculate the DCS score for a given page and set `indexable` accordingly.

    Pages with dcs_score < 70 (or failing mandatory criteria) are tagged noindex, follow.
    """
    async def _run() -> dict:
        from app.db.session import async_session
        from app.services.dcs_service import DCSService

        p_uuid = uuid.UUID(page_id)
        async with async_session() as session:
            service = DCSService(session)
            page, breakdown = await service.evaluate_page(p_uuid)
            await session.commit()

            return {
                "page_id": str(page.id),
                "url": page.url,
                "archetype": page.archetype,
                "dcs_score": page.dcs_score,
                "indexable": page.indexable,
                "robots_meta": breakdown.robots_meta,
                "reasons": breakdown.reasons,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("recalculate_dcs failed for page %s: %s", page_id, exc)
        raise self.retry(exc=exc, countdown=60)
