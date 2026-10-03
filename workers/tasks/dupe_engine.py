"""Dupe engine Celery tasks — vector similarity computation."""
from __future__ import annotations

from workers.celery_app import celery_app


@celery_app.task(name="dupe_engine.compute_dupes_for_product", bind=True, max_retries=2)
def compute_dupes_for_product(self, product_id: str, method_version: str = "v1") -> dict:
    """
    Compute cosine similarity between product_id and all products in the same
    category, then upsert DupeEdge rows (INSERT ... ON CONFLICT DO UPDATE is
    fine here — dupe_edge is NOT append-only).
    """
    # TODO: load ingredient vector, run pgvector ANN, write dupe_edge rows
    raise NotImplementedError
