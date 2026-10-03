"""Celery application factory for The Beauty Project workers."""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tbp_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "workers.tasks.ingestion",      # legacy stubs (kept for backward compat)
        "workers.tasks.ingest",         # active ingestion tasks (Step 3)
        "workers.tasks.compute_dupes",  # dupe similarity engine (Step 5)
        "workers.tasks.dupe_engine",    # legacy stub
        "workers.tasks.dcs_gate",
        "workers.tasks.update_dcs",     # periodic & event-driven DCS updates (Step 6)
        "workers.tasks.sync_gsc",       # GSC performance sync (Step 8)
    ],
)

# Initialise beat_schedule so task modules can safely .update() it
celery_app.conf.beat_schedule = {}

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,            # Only ack after task completes (safer)
    worker_prefetch_multiplier=1,   # Fair dispatch for long-running tasks
    result_expires=3600,
)

if __name__ == "__main__":
    celery_app.start()
