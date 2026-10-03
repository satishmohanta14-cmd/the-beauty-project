"""
Google Search Console Sync Celery Tasks
=======================================
Tasks:
  ``sync_gsc.sync_daily_performance``:
      Fetches daily search metrics from GSC, maps URLs to page.id and archetype,
      and upserts records into `search_performance`.

Beat schedule:
  Runs daily at 06:00 UTC for previous day's performance.
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from urllib.parse import urlparse

from celery.schedules import crontab

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Register 06:00 UTC daily GSC sync in Celery Beat
celery_app.conf.beat_schedule.update(
    {
        "gsc-daily-sync-0600": {
            "task": "sync_gsc.sync_daily_performance",
            "schedule": crontab(minute="0", hour="6"),  # 06:00 UTC daily
        },
    }
)


def _derive_archetype_from_path(path: str) -> str:
    """Fallback archetype derivation from URL path structure."""
    p = path.lower()
    if p.startswith("/p/"):
        return "product"
    elif p.startswith("/ingredient/"):
        return "ingredient"
    elif p.startswith("/dupe/") or p.startswith("/dupes/"):
        return "dupe"
    elif p.startswith("/best/"):
        return "best"
    elif p.startswith("/vs/"):
        return "vs"
    elif p.startswith("/conflict/"):
        return "conflict"
    elif p.startswith("/under/"):
        return "under"
    return "other"


@celery_app.task(
    name="sync_gsc.sync_daily_performance",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_daily_performance(
    self,
    date_str: str | None = None,
    site_url: str | None = None,
) -> dict:
    """
    Sync daily performance data from GSC for target date (default: yesterday).
    Maps URLs back to canonical page.id and archetype, and upserts into search_performance.
    """
    if date_str:
        target_date = datetime.date.fromisoformat(date_str)
    else:
        # GSC data typically finalizes with ~2-day lag, query 2 days ago by default
        target_date = datetime.date.today() - datetime.timedelta(days=2)

    async def _run() -> dict:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.db.session import async_session
        from app.models.page import Page
        from app.models.search_performance import SearchPerformance
        from app.services.gsc_client import GSCClient

        client = GSCClient(site_url=site_url)
        metrics = client.query_daily_page_metrics(target_date)

        if not metrics:
            logger.info("No GSC metrics found for date %s", target_date)
            return {"date": str(target_date), "synced": 0}

        async with async_session() as session:
            # Pre-load known pages into memory for fast URL matching
            page_rows = (await session.execute(select(Page.id, Page.url, Page.archetype))).all()
            # Map by both relative path and absolute URL
            url_to_page: dict[str, tuple] = {}
            for row in page_rows:
                url_to_page[row.url] = (row.id, row.archetype)

            upserted = 0
            for item in metrics:
                # Extract relative path from GSC absolute URL
                parsed = urlparse(item.url)
                rel_path = parsed.path
                if parsed.query:
                    rel_path += f"?{parsed.query}"

                page_match = url_to_page.get(rel_path) or url_to_page.get(item.url)
                if page_match:
                    page_id, archetype = page_match
                else:
                    page_id = None
                    archetype = _derive_archetype_from_path(rel_path)

                stmt = (
                    pg_insert(SearchPerformance)
                    .values(
                        url=item.url,
                        page_id=page_id,
                        archetype=archetype,
                        date=item.date,
                        clicks=item.clicks,
                        impressions=item.impressions,
                        ctr=item.ctr,
                        position=item.position,
                    )
                    .on_conflict_do_update(
                        index_elements=["url", "date"],
                        set_={
                            "page_id": page_id,
                            "archetype": archetype,
                            "clicks": item.clicks,
                            "impressions": item.impressions,
                            "ctr": item.ctr,
                            "position": item.position,
                        },
                    )
                )
                await session.execute(stmt)
                upserted += 1

            await session.commit()

        logger.info("GSC sync complete for %s: upserted %d records", target_date, upserted)
        return {"date": str(target_date), "synced": upserted}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.exception("GSC sync failed for date %s: %s", target_date, exc)
        raise self.retry(exc=exc)
