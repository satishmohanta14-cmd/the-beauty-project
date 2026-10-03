"""
Page Metadata, Programmatic SEO & Sitemap API Router.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.page import Page
from app.schemas.page import (
    HrefLangTag,
    PageMetadataResponse,
    SitemapEntry,
    SitemapResponse,
)
from app.services.dcs_evaluator import DCSEvaluator
from workers.tasks.update_dcs import re_score_page

router = APIRouter(prefix="/api/v1/pages", tags=["Programmatic Pages & SEO"])


@router.get("/by-url", response_model=PageMetadataResponse)
async def get_page_by_url(
    url: str = Query(..., description="Exact page URL / path"),
    db: AsyncSession = Depends(get_db),
) -> PageMetadataResponse:
    """
    Retrieve page metadata, DCS score, indexability status, and SEO robots meta.
    Hybrid routing: Returns correct hreflang tags for alternate market locales.
    """
    stmt = select(Page).where(Page.url == url).limit(1)
    res = await db.execute(stmt)
    page = res.scalar_one_or_none()
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page with URL '{url}' not found",
        )

    # Invariant: Pages with dcs_score < 70 or indexable=False get 'noindex, follow'
    robots_meta = "index, follow" if (page.indexable and page.dcs_score >= 70) else "noindex, follow"

    # Query sibling locale pages for hreflang
    hreflangs: list[HrefLangTag] = []
    if page.entity_refs:
        sibling_stmt = (
            select(Page.locale, Page.url)
            .where(
                Page.archetype == page.archetype,
                Page.entity_refs == page.entity_refs,
                Page.indexable.is_(True),
            )
        )
        siblings = (await db.execute(sibling_stmt)).all()
        hreflangs = [HrefLangTag(locale=s.locale, url=s.url) for s in siblings]

    return PageMetadataResponse(
        id=page.id,
        url=page.url,
        archetype=page.archetype,
        locale=page.locale,
        dcs_score=page.dcs_score,
        indexable=page.indexable,
        robots_meta=robots_meta,
        first_indexed_at=page.first_indexed_at,
        hreflang=hreflangs,
    )


@router.post("/{page_id}/evaluate", response_model=PageMetadataResponse)
async def evaluate_page_dcs(
    page_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PageMetadataResponse:
    """
    Synchronously evaluate and update a page's Data Completeness Score and indexability gate.
    """
    service = DCSEvaluator(db)
    try:
        page, result = await service.evaluate_page(page_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return PageMetadataResponse(
        id=page.id,
        url=page.url,
        archetype=page.archetype,
        locale=page.locale,
        dcs_score=page.dcs_score,
        indexable=page.indexable,
        robots_meta=result.robots_meta,
        first_indexed_at=page.first_indexed_at,
        reasons=result.reasons,
    )


@router.post("/{page_id}/queue-evaluate", status_code=status.HTTP_202_ACCEPTED)
async def queue_page_dcs_evaluation(page_id: uuid.UUID) -> dict[str, str]:
    """
    Enqueue an asynchronous DCS evaluation task via Celery.
    """
    re_score_page.delay(str(page_id))
    return {"status": "queued", "page_id": str(page_id)}


@router.get("/sitemap", response_model=SitemapResponse)
async def get_indexable_sitemap(
    locale: str | None = Query(None, description="Filter sitemap by locale e.g. 'en-in', 'en-us'"),
    limit: int = Query(5000, le=50000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SitemapResponse:
    """
    Sitemap generator indexability gate:
    Strictly includes only pages where indexable == True and dcs_score >= 70.
    """
    query = select(Page).where(Page.indexable.is_(True), Page.dcs_score >= 70)
    if locale:
        query = query.where(Page.locale == locale)

    query = query.order_by(Page.first_indexed_at.desc().nullslast()).offset(offset).limit(limit)
    res = await db.execute(query)
    pages = res.scalars().all()

    entries = [
        SitemapEntry(
            loc=p.url,
            lastmod=p.first_indexed_at,
            changefreq="daily",
            priority=0.8 if p.archetype == "product" else 0.6,
        )
        for p in pages
    ]

    return SitemapResponse(total=len(entries), pages=entries)
