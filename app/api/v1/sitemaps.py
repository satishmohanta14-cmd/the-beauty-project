"""
Public Sitemap Endpoint by Archetype for Next.js ISR & Search Engines.
GET /api/v1/sitemap/{archetype}
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get, cache_set
from app.db.session import get_db
from app.models.page import Page
from app.schemas.public_api import SitemapArchetypeResponse, SitemapUrlItem

router = APIRouter(prefix="/api/v1/sitemap", tags=["Public Sitemap (ISR)"])


@router.get("/{archetype}", response_model=SitemapArchetypeResponse)
async def get_sitemap_by_archetype(
    archetype: str,
    response: Response,
    page: int = Query(1, ge=1),
    size: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
) -> SitemapArchetypeResponse:
    """
    Paginated list of URLs eligible for indexing (strictly `indexable == True` and `dcs_score >= 70`).
    Consumed by Next.js sitemap generator and search engines.
    """
    cache_key = f"api:v1:sitemap:{archetype}:p{page}:s{size}"
    cached = await cache_get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, s-maxage=900, stale-while-revalidate=1800"
        return SitemapArchetypeResponse.model_validate(cached)

    # Base query for indexable pages
    base_filter = [
        Page.archetype == archetype,
        Page.indexable.is_(True),
        Page.dcs_score >= 70,
    ]

    count_stmt = select(func.count(Page.id)).where(*base_filter)
    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = math.ceil(total / size) if total > 0 else 1

    offset = (page - 1) * size
    query = (
        select(Page.url, Page.locale, Page.first_indexed_at, Page.dcs_score)
        .where(*base_filter)
        .order_by(Page.first_indexed_at.desc().nullslast())
        .offset(offset)
        .limit(size)
    )
    rows = (await db.execute(query)).all()

    urls = [
        SitemapUrlItem(
            url=r.url,
            locale=r.locale,
            lastmod=r.first_indexed_at,
            dcs_score=r.dcs_score,
        )
        for r in rows
    ]

    result = SitemapArchetypeResponse(
        archetype=archetype,
        page=page,
        size=size,
        total=total,
        total_pages=total_pages,
        urls=urls,
    )

    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=900)
    response.headers["X-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, s-maxage=900, stale-while-revalidate=1800"
    return result
