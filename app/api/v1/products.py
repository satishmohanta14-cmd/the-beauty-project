"""
Public Products Endpoint for Next.js ISR.
GET /api/v1/products/{slug}
"""
from __future__ import annotations

import datetime
from datetime import timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.db.session import get_db
from app.models.brand import Brand
from app.models.ingredient import Ingredient
from app.models.offer import Offer
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.retailer import Retailer
from app.models.variant import Variant
from app.schemas.public_api import (
    BrandBrief,
    PriceHistoryPoint,
    ProductDetailResponse,
    ProductIngredientItem,
    RetailerPriceComparison,
)

router = APIRouter(prefix="/api/v1/products", tags=["Public Products (ISR)"])


@router.get("/{slug}", response_model=ProductDetailResponse)
async def get_product_by_slug(
    slug: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ProductDetailResponse:
    """
    Returns full product details, parsed INCI breakdown, retailer price comparisons,
    latest 30-day price trend, and DCS indexability meta tag.
    Cached for ultra-low latency (<80ms) and ISR generation.
    """
    cache_key = f"api:v1:product:{slug}"
    cached = await cache_get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
        return ProductDetailResponse.model_validate(cached)

    # 1. Fetch Product with Brand
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

    # Meta robots directive: index, follow if dcs_score >= 70 and indexed
    robots_meta = "index, follow" if (product.dcs_score >= 70 and product.index_tier == "indexed") else "noindex, follow"

    # 2. Fetch Ordered INCI Ingredients
    ing_stmt = (
        select(
            ProductIngredient.position,
            ProductIngredient.is_active,
            Ingredient.inci_name,
            Ingredient.canonical_name,
            Ingredient.function_,
            Ingredient.comedogenic,
            Ingredient.irritancy,
        )
        .join(Ingredient, ProductIngredient.ingredient_id == Ingredient.id)
        .where(ProductIngredient.product_id == product.id)
        .order_by(ProductIngredient.position.asc())
    )
    ing_rows = (await db.execute(ing_stmt)).all()
    ingredients = [
        ProductIngredientItem(
            position=r.position,
            inci_name=r.inci_name,
            canonical_name=r.canonical_name,
            is_active=r.is_active,
            function=r.function_ or [],
            comedogenic=r.comedogenic,
            irritancy=r.irritancy,
        )
        for r in ing_rows
    ]

    # 3. Fetch latest live offer per retailer across product variants
    price_comp_stmt = (
        select(
            Retailer.name.label("retailer_name"),
            Variant.size_ml,
            Offer.price,
            Offer.currency,
            Offer.in_stock,
            Offer.id.label("offer_id"),
        )
        .join(Variant, Offer.variant_id == Variant.id)
        .join(Retailer, Offer.retailer_id == Retailer.id)
        .where(
            Variant.product_id == product.id,
            Offer.in_stock.is_(True),
        )
        .order_by(Offer.price.asc(), desc(Offer.seen_at))
    )
    comp_rows = (await db.execute(price_comp_stmt)).all()

    # Deduplicate: pick best offer per retailer
    seen_retailers: set[str] = set()
    price_comparison: list[RetailerPriceComparison] = []
    for r in comp_rows:
        if r.retailer_name not in seen_retailers:
            seen_retailers.add(r.retailer_name)
            price_comparison.append(
                RetailerPriceComparison(
                    retailer_name=r.retailer_name,
                    variant_size_ml=Decimal(str(r.size_ml)),
                    price=Decimal(str(r.price)),
                    currency=r.currency,
                    in_stock=r.in_stock,
                    affiliate_redirect_url=f"/go/{r.offer_id}",
                )
            )

    # 4. Fetch 30-day price history trend
    thirty_days_ago = datetime.datetime.now(timezone.utc) - timedelta(days=30)
    history_stmt = (
        select(
            Offer.seen_at,
            Offer.price,
            Offer.currency,
            Retailer.name.label("retailer_name"),
        )
        .join(Variant, Offer.variant_id == Variant.id)
        .join(Retailer, Offer.retailer_id == Retailer.id)
        .where(
            Variant.product_id == product.id,
            Offer.seen_at >= thirty_days_ago,
        )
        .order_by(Offer.seen_at.asc())
        .limit(200)
    )
    hist_rows = (await db.execute(history_stmt)).all()
    price_trend_30d = [
        PriceHistoryPoint(
            seen_at=r.seen_at,
            price=Decimal(str(r.price)),
            currency=r.currency,
            retailer_name=r.retailer_name,
        )
        for r in hist_rows
    ]

    result = ProductDetailResponse(
        id=product.id,
        name=product.name,
        slug=product.slug,
        brand=BrandBrief(name=product.brand.name, slug=product.brand.slug),
        category_id=product.category_id,
        format=product.format,
        claims=product.claims or [],
        markets=product.markets or [],
        dcs_score=product.dcs_score,
        index_tier=product.index_tier,
        robots_meta=robots_meta,
        ingredients=ingredients,
        price_comparison=price_comparison,
        price_trend_30d=price_trend_30d,
    )

    # Cache for 5 minutes
    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=300)
    response.headers["X-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, s-maxage=300, stale-while-revalidate=600"
    return result
