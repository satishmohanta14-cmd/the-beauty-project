"""
Dupe Computation Celery Tasks
==============================
Tasks:
    ``dupes.compute_dupes_for_product``
        Compute and upsert dupe_edge rows for a single product.
        Triggered by new product creation or ingredient list updates.

    ``dupes.build_formula_vector``
        (Re)build the formula_vector for a single product without
        running the full ANN search.  Useful for bulk backfills.

    ``dupes.recompute_all_dupes``
        Fan-out task: dispatches ``compute_dupes_for_product`` for
        every product that has at least one ingredient linked.

Beat schedule:
    ``dupes-nightly-recompute``:  runs at 02:00 UTC daily.
    New products are auto-triggered via ``compute_dupes_for_product``
    dispatched from the ingestion / entity-resolution pipeline.
"""
from __future__ import annotations

import asyncio
import logging

from celery.schedules import crontab

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Register nightly full-recompute in the Beat schedule
celery_app.conf.beat_schedule.update(
    {
        "dupes-nightly-recompute": {
            "task": "dupes.recompute_all_dupes",
            "schedule": crontab(minute="0", hour="2"),  # 02:00 UTC daily
        },
    }
)


# ===========================================================================
# Per-product task
# ===========================================================================


@celery_app.task(
    name="dupes.compute_dupes_for_product",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def compute_dupes_for_product(
    self,
    product_id: str,
    *,
    rebuild_vector: bool = True,
) -> dict:
    """
    Compute and upsert dupe_edge rows for *product_id*.

    Parameters
    ----------
    product_id:
        UUID string of the product to process.
    rebuild_vector:
        When True (default), rebuilds ``formula_vector`` from the current
        ingredient list before searching for dupes.
        Pass False to skip the rebuild and use the existing stored vector.

    Returns
    -------
    dict with keys: ``product_id``, ``edges_upserted``, ``new_edges``.
    """

    async def _run() -> dict:
        from uuid import UUID

        from app.db.session import async_session
        from app.services.dupe_engine import DupeEngineService

        pid = UUID(product_id)

        async with async_session() as session:
            svc = DupeEngineService(session)
            results = await svc.compute_dupes(pid, rebuild_vector=rebuild_vector)
            await session.commit()

        new_count = sum(1 for r in results if r.is_new_edge)
        logger.info(
            "compute_dupes_for_product done: product=%s total=%d new=%d",
            product_id, len(results), new_count,
        )
        return {
            "product_id": product_id,
            "edges_upserted": len(results),
            "new_edges": new_count,
        }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("compute_dupes_for_product failed for %s: %s", product_id, exc)
        raise self.retry(exc=exc)


# ===========================================================================
# Formula vector backfill task
# ===========================================================================


@celery_app.task(
    name="dupes.build_formula_vector",
    bind=True,
    max_retries=2,
)
def build_formula_vector(self, product_id: str) -> dict:
    """
    (Re)build and store ``formula_vector`` for *product_id* without
    running the ANN search.

    Use this for initial backfills or when ingredient data changes
    without requiring an immediate dupe recomputation.
    """

    async def _run() -> dict:
        from uuid import UUID

        from app.db.session import async_session
        from app.services.dupe_engine import DupeEngineService

        pid = UUID(product_id)

        async with async_session() as session:
            svc = DupeEngineService(session)
            vec = await svc.compute_and_store_formula_vector(pid)
            await session.commit()

        return {
            "product_id": product_id,
            "vector_built": vec is not None,
            "dims": len(vec) if vec is not None else 0,
        }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("build_formula_vector failed for %s: %s", product_id, exc)
        raise self.retry(exc=exc)


# ===========================================================================
# Recompute-all fan-out task
# ===========================================================================


@celery_app.task(
    name="dupes.recompute_all_dupes",
    bind=True,
    max_retries=1,
)
def recompute_all_dupes(self) -> dict:
    """
    Fan-out task dispatched by Celery Beat nightly.

    Queries all products that have at least one product_ingredient row
    (i.e., have an ingredient list) and queues a ``compute_dupes_for_product``
    task for each.

    Uses ``rebuild_vector=True`` so vectors are refreshed from the latest
    ingredient data before similarity is recomputed.
    """

    async def _get_product_ids() -> list[str]:
        from sqlalchemy import select

        from app.db.session import async_session
        from app.models.product_ingredient import ProductIngredient

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(ProductIngredient.product_id)
                    .distinct()
                    .order_by(ProductIngredient.product_id)
                )
            ).all()

        return [str(row[0]) for row in rows]

    try:
        product_ids = asyncio.run(_get_product_ids())
    except Exception as exc:
        logger.exception("recompute_all_dupes: failed to fetch product IDs: %s", exc)
        raise self.retry(exc=exc)

    for pid in product_ids:
        compute_dupes_for_product.delay(pid, rebuild_vector=True)

    logger.info("recompute_all_dupes: dispatched %d tasks", len(product_ids))
    return {"products_queued": len(product_ids)}
