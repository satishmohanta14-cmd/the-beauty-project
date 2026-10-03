"""
Public Dupes Endpoint for Next.js ISR.
GET /api/v1/dupes/{slug}
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.db.session import get_db
from app.models.brand import Brand
from app.models.dupe_edge import DupeEdge
from app.models.offer import Offer
from app.models.product import Product
from app.models.variant import Variant
from app.schemas.public_api import DupeAlternative, ProductDupesResponse

router = APIRouter(prefix="/api/v1/dupes", tags=["Public Dupes (ISR)"])


@router.get("/{slug}", response_model=ProductDupesResponse)
async def get_dupes_by_slug(
    slug: str,
    response: Response,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> ProductDupesResponse:
    """
    Returns ranked dupe alternatives from `dupe_edge` with similarity scores,
    price differences, format info, and live offer details.
    Cached for Next.js static generation (ISR).
    """
    cache_key = f"api:v1:dupes:{slug}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
        return ProductDupesResponse.model_validate(cached)

    # 1. Look up primary product
    prod_stmt = (
        select(Product)
        .options(selectinload(Product.brand))
        .where(Product.slug == slug)
        .limit(1)
    )
    product = (await db.execute(prod_stmt)).scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with slug '{slug}' not found",
        )

    # 2. Query DupeEdge rows connected to product
    edge_stmt = (
        select(DupeEdge)
        .where(
            or_(
                DupeEdge.product_a == product.id,
                DupeEdge.product_b == product.id,
            )
        )
        .order_by(DupeEdge.similarity.desc())
        .limit(limit)
    )
    edges = (await db.execute(edge_stmt)).scalars().all()

    dupe_items: list[DupeAlternative] = []
    for edge in edges:
        # Determine dupe product ID
        is_a = edge.product_a == product.id
        target_id = edge.product_b if is_a else edge.product_a
        # Adjusted price delta: positive if target is more expensive than primary
        delta = float(edge.price_delta_pct) if is_a else -float(edge.price_delta_pct)

        target_prod = (
            await db.execute(
                select(Product)
                .options(selectinload(Product.brand))
                .where(Product.id == target_id)
            )
        ).scalar_one_or_none()
        if not target_prod:
            continue

        # Latest offer for target product
        offer_stmt = (
            select(Offer.id, Offer.price, Offer.currency, Variant.size_ml)
            .join(Variant, Offer.variant_id == Variant.id)
            .where(Variant.product_id == target_id, Offer.in_stock.is_(True))
            .order_by(desc(Offer.seen_at))
            .limit(1)
        )
        offer_row = (await db.execute(offer_stmt)).one_or_none()

        dupe_items.append(
            DupeAlternative(
                id=target_prod.id,
                name=target_prod.name,
                slug=target_prod.slug,
                brand_name=target_prod.brand.name,
                similarity=float(edge.similarity),
                price_delta_pct=round(delta, 2),
                format=target_prod.format,
                price=Decimal(str(offer_row.price)) if offer_row else None,
                size_ml=Decimal(str(offer_row.size_ml)) if offer_row else None,
                currency=offer_row.currency if offer_row else None,
                affiliate_redirect_url=f"/go/{offer_row.id}" if offer_row else None,
            )
        )

    result = ProductDupesResponse(
        product_id=product.id,
        product_name=product.name,
        product_slug=product.slug,
        brand_name=product.brand.name,
        dupes=dupe_items,
    )

    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
    response.headers["X-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
    return result
