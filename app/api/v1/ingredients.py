"""
Public Ingredients Endpoint for Next.js ISR.
GET /api/v1/ingredients/{slug}
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache_get, cache_set
from app.db.session import get_db
from app.models.brand import Brand
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.schemas.public_api import (
    IngredientDetailResponse,
    ProductContainingIngredient,
)

router = APIRouter(prefix="/api/v1/ingredients", tags=["Public Ingredients (ISR)"])


def _slugify(text: str) -> str:
    t = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[\s_]+", "-", t).strip("-")


@router.get("/{slug}", response_model=IngredientDetailResponse)
async def get_ingredient_by_slug(
    slug: str,
    response: Response,
    limit_products: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> IngredientDetailResponse:
    """
    Returns canonical ingredient details, function, safety grades, and top products
    containing it ordered strictly by concentration (position 1 = highest).
    """
    cache_key = f"api:v1:ingredient:{slug}:{limit_products}"
    cached = await cache_get(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        response.headers["Cache-Control"] = "public, s-maxage=600, stale-while-revalidate=1200"
        return IngredientDetailResponse.model_validate(cached)

    # 1. Match ingredient by slug (slugified canonical_name or inci_name)
    ing_stmt = select(Ingredient)
    ing_rows = (await db.execute(ing_stmt)).scalars().all()

    target_ing: Ingredient | None = None
    for ing in ing_rows:
        if _slugify(ing.canonical_name) == slug or _slugify(ing.inci_name) == slug:
            target_ing = ing
            break

    if not target_ing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingredient with slug '{slug}' not found",
        )

    # 2. Query top products containing this ingredient ordered by position ASC (highest concentration first)
    prod_stmt = (
        select(
            Product.id.label("product_id"),
            Product.name,
            Product.slug,
            Brand.name.label("brand_name"),
            ProductIngredient.position,
            ProductIngredient.is_active,
            Product.dcs_score,
        )
        .join(Product, ProductIngredient.product_id == Product.id)
        .join(Brand, Product.brand_id == Brand.id)
        .where(ProductIngredient.ingredient_id == target_ing.id)
        .order_by(
            ProductIngredient.position.asc(),
            Product.dcs_score.desc(),
        )
        .limit(limit_products)
    )
    prod_rows = (await db.execute(prod_stmt)).all()

    top_products = [
        ProductContainingIngredient(
            product_id=r.product_id,
            name=r.name,
            slug=r.slug,
            brand_name=r.brand_name,
            position=r.position,
            is_active=r.is_active,
            dcs_score=r.dcs_score,
        )
        for r in prod_rows
    ]

    result = IngredientDetailResponse(
        id=target_ing.id,
        inci_name=target_ing.inci_name,
        canonical_name=target_ing.canonical_name,
        synonyms=target_ing.synonyms or [],
        cas_no=target_ing.cas_no,
        function=target_ing.function_ or [],
        evidence_grade=target_ing.evidence_grade,
        comedogenic=target_ing.comedogenic,
        irritancy=target_ing.irritancy,
        top_products=top_products,
    )

    await cache_set(cache_key, result.model_dump(mode="json"), ttl_seconds=600)
    response.headers["X-Cache"] = "MISS"
    response.headers["Cache-Control"] = "public, s-maxage=600, stale-while-revalidate=1200"
    return result
