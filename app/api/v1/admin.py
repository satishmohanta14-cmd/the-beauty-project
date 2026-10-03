"""
Internal Admin Diagnostics, Feed Management & Product Catalog API.
Prefix: /api/v1/admin
"""
from __future__ import annotations

import datetime
import re
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.brand import Brand
from app.models.ingredient import Ingredient
from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.retailer import Retailer
from app.models.search_performance import SearchPerformance
from app.models.unresolved_entity_queue import UnresolvedEntityQueue
from app.models.variant import Variant
from app.services.dcs_evaluator import DCSEvaluator
from app.services.dupe_engine import DupeEngineService
from app.services.ingredient_normalizer import IngredientNormalizer
from workers.tasks.ingest import process_retailer_feed
from workers.tasks.sync_gsc import sync_daily_performance

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Portal & Pipeline Controls"])


def _slugify(text: str) -> str:
    t = re.sub(r"[^\w\s-]", "", text.lower().strip())
    return re.sub(r"[\s_]+", "-", t).strip("-")


# ── Schemas ──────────────────────────────────────────────────────────────────

class AdminProductItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    brand_name: str
    category_id: str
    format: str | None = None
    dcs_score: int
    index_tier: str
    offer_count: int
    ingredient_count: int


class AdminCreateProductRequest(BaseModel):
    name: str
    brand_name: str
    category_id: str = "serum"
    format: str | None = "serum"
    claims: list[str] = Field(default_factory=list)
    raw_ingredients: str = Field(description="Comma-separated or newline-separated INCI string")
    size_ml: Decimal = Decimal("30.00")
    price: Decimal = Decimal("599.00")
    currency: str = "INR"
    retailer_name: str = "Nykaa"


class AdminQueueItem(BaseModel):
    id: uuid.UUID
    retailer_name: str
    raw_title: str
    raw_brand: str | None
    raw_size_ml: Decimal | None
    raw_price: Decimal | None
    candidate_product_name: str | None
    candidate_confidence: float | None
    match_tier: str | None
    status: str
    created_at: datetime.datetime


class ArchetypeAnalyticsItem(BaseModel):
    archetype: str
    total_pages: int
    indexable_pages: int
    index_rate_pct: float
    total_impressions: int
    total_clicks: int
    average_ctr_pct: float
    average_position: float


class ArchetypeAnalyticsResponse(BaseModel):
    days_evaluated: int
    archetypes: list[ArchetypeAnalyticsItem] = Field(default_factory=list)


class AdminBrandItem(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    country: str | None = None
    parent_company: str | None = None
    product_count: int = 0


@router.get("/brands", response_model=list[AdminBrandItem])
async def list_admin_brands(
    db: AsyncSession = Depends(get_db),
) -> list[AdminBrandItem]:
    """List all configured brands with country, parent company, and product counts."""
    stmt = (
        select(
            Brand.id,
            Brand.name,
            Brand.slug,
            Brand.country,
            Brand.parent_company,
            func.count(Product.id).label("product_count"),
        )
        .outerjoin(Product, Product.brand_id == Brand.id)
        .group_by(Brand.id)
        .order_by(Brand.name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminBrandItem(
            id=r.id,
            name=r.name,
            slug=r.slug,
            country=r.country,
            parent_company=r.parent_company,
            product_count=r.product_count or 0,
        )
        for r in rows
    ]


# ── Product Management ───────────────────────────────────────────────────────

@router.get("/products", response_model=list[AdminProductItem])
async def list_admin_products(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[AdminProductItem]:
    """List products with brand info, DCS score, index tier, and offer counts."""
    stmt = (
        select(
            Product.id,
            Product.name,
            Product.slug,
            Brand.name.label("brand_name"),
            Product.category_id,
            Product.format,
            Product.dcs_score,
            Product.index_tier,
            func.count(Offer.id.distinct()).label("offer_count"),
            func.count(ProductIngredient.id.distinct()).label("ingredient_count"),
        )
        .join(Brand, Product.brand_id == Brand.id)
        .outerjoin(Variant, Variant.product_id == Product.id)
        .outerjoin(Offer, Offer.variant_id == Variant.id)
        .outerjoin(ProductIngredient, ProductIngredient.product_id == Product.id)
        .group_by(Product.id, Brand.name)
        .order_by(Product.dcs_score.desc(), Product.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    return [
        AdminProductItem(
            id=r.id,
            name=r.name,
            slug=r.slug,
            brand_name=r.brand_name,
            category_id=r.category_id,
            format=r.format,
            dcs_score=r.dcs_score,
            index_tier=r.index_tier,
            offer_count=r.offer_count or 0,
            ingredient_count=r.ingredient_count or 0,
        )
        for r in rows
    ]


@router.post("/products", response_model=AdminProductItem, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: AdminCreateProductRequest,
    db: AsyncSession = Depends(get_db),
) -> AdminProductItem:
    """
    Create a new product manually:
    - Finds or creates Brand
    - Parses raw INCI string via IngredientNormalizer preserving position
    - Creates Variant & initial append-only Offer
    - Evaluates DCS and builds formula vector
    """
    brand_slug = _slugify(payload.brand_name)
    brand = (await db.execute(select(Brand).where(Brand.slug == brand_slug))).scalar_one_or_none()
    if not brand:
        brand = Brand(name=payload.brand_name, slug=brand_slug)
        db.add(brand)
        await db.flush()

    prod_slug = f"{brand_slug}-{_slugify(payload.name)}"
    existing = (await db.execute(select(Product).where(Product.slug == prod_slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail=f"Product with slug '{prod_slug}' already exists")

    product = Product(
        brand_id=brand.id,
        name=payload.name,
        slug=prod_slug,
        category_id=payload.category_id,
        format=payload.format,
        claims=payload.claims,
        markets=["IN"],
        dcs_score=0,
        index_tier="provisional",
    )
    db.add(product)
    await db.flush()

    # Normalize ingredients
    normalizer = await IngredientNormalizer.from_db(db)
    normalized_list = await normalizer.normalize(payload.raw_ingredients)

    for item in normalized_list:
        pi = ProductIngredient(
            product_id=product.id,
            ingredient_id=item.ingredient_id,
            position=item.position,
            is_active=item.position <= 4,
        )
        db.add(pi)
    await db.flush()

    # Variant & Offer
    variant = Variant(
        product_id=product.id,
        size_ml=payload.size_ml,
        mrp=payload.price,
    )
    db.add(variant)
    await db.flush()

    retailer = (await db.execute(select(Retailer).where(Retailer.name == payload.retailer_name))).scalar_one_or_none()
    if not retailer:
        retailer = Retailer(name=payload.retailer_name, market="IN")
        db.add(retailer)
        await db.flush()

    offer = Offer(
        variant_id=variant.id,
        retailer_id=retailer.id,
        price=payload.price,
        currency=payload.currency,
        in_stock=True,
        affiliate_url=f"https://www.{payload.retailer_name.lower()}.com/p/{prod_slug}",
    )
    db.add(offer)

    # Page entry
    page = Page(
        archetype="product",
        url=f"/p/{brand_slug}/{prod_slug}",
        locale="en-in",
        entity_refs=[product.id],
        dcs_score=0,
        indexable=False,
    )
    db.add(page)
    await db.flush()

    # Evaluate DCS
    dcs_evaluator = DCSEvaluator(db)
    await dcs_evaluator.evaluate_product(product.id)
    await dcs_evaluator.evaluate_page(page.id)

    # Build formula vector & dupes
    dupe_svc = DupeEngineService(db)
    await dupe_svc.compute_and_store_formula_vector(product.id)
    await db.commit()

    return AdminProductItem(
        id=product.id,
        name=product.name,
        slug=product.slug,
        brand_name=brand.name,
        category_id=product.category_id,
        format=product.format,
        dcs_score=product.dcs_score,
        index_tier=product.index_tier,
        offer_count=1,
        ingredient_count=len(normalized_list),
    )


# ── Automated Feeds Ingestion ────────────────────────────────────────────────

@router.post("/feeds/ingest-sample", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sample_feed_ingest(
    retailer: str = Query("nykaa", description="Retailer feed name e.g. 'nykaa', 'amazon_in', 'sephora_us'")
) -> dict[str, str]:
    """
    Trigger Method 1 automated feed ingestion:
    Processes retailer items, runs Entity Resolution, and appends timestamped offers.
    """
    process_retailer_feed.delay(retailer)
    return {"status": "queued", "retailer": retailer}


# ── Unresolved Review Queue (Human-in-the-Loop) ───────────────────────────────

@router.get("/queue", response_model=list[AdminQueueItem])
async def list_review_queue(
    status_filter: str = Query("pending"),
    db: AsyncSession = Depends(get_db),
) -> list[AdminQueueItem]:
    """Fetch items from unresolved_entity_queue where match confidence was < 0.85."""
    stmt = (
        select(UnresolvedEntityQueue)
        .where(UnresolvedEntityQueue.status == status_filter)
        .order_by(UnresolvedEntityQueue.created_at.desc())
        .limit(100)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return [
        AdminQueueItem(
            id=r.id,
            retailer_name=r.retailer_name,
            raw_title=r.raw_title,
            raw_brand=r.raw_brand,
            raw_size_ml=r.raw_size_ml,
            raw_price=r.raw_price,
            candidate_product_name=r.candidate_product_name,
            candidate_confidence=float(r.candidate_confidence) if r.candidate_confidence else None,
            match_tier=r.match_tier,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/queue/{queue_id}/resolve")
async def resolve_queue_item(
    queue_id: uuid.UUID,
    action: str = Query(..., pattern="^(approved|rejected)$"),
    variant_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Approve or reject a review queue candidate."""
    item = await db.get(UnresolvedEntityQueue, queue_id)
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item.status = action
    item.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    item.reviewed_by = "admin"

    if action == "approved" and variant_id:
        item.resolved_variant_id = variant_id
        # Append offer
        retailer = (await db.execute(select(Retailer).where(Retailer.name == item.retailer_name))).scalar_one_or_none()
        if retailer and item.raw_price:
            offer = Offer(
                variant_id=variant_id,
                retailer_id=retailer.id,
                price=item.raw_price,
                currency=item.raw_currency or "INR",
                in_stock=True,
                affiliate_url=item.raw_url or "#",
            )
            db.add(offer)

    await db.commit()
    return {"status": "success", "id": str(queue_id), "action": action}


# ── Analytics & Diagnostics ──────────────────────────────────────────────────

@router.get("/analytics/archetypes", response_model=ArchetypeAnalyticsResponse)
async def get_archetype_analytics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> ArchetypeAnalyticsResponse:
    page_stmt = (
        select(
            Page.archetype,
            func.count(Page.id).label("total_pages"),
            func.count(case((Page.indexable.is_(True), 1))).label("indexable_pages"),
        )
        .group_by(Page.archetype)
    )
    page_rows = (await db.execute(page_stmt)).all()
    page_stats: dict[str, dict[str, int]] = {
        row.archetype: {
            "total_pages": row.total_pages or 0,
            "indexable_pages": row.indexable_pages or 0,
        }
        for row in page_rows
    }

    cutoff = datetime.date.today() - datetime.timedelta(days=days)
    perf_stmt = (
        select(
            SearchPerformance.archetype,
            func.sum(SearchPerformance.impressions).label("total_impressions"),
            func.sum(SearchPerformance.clicks).label("total_clicks"),
            func.avg(SearchPerformance.ctr).label("avg_ctr"),
            func.avg(SearchPerformance.position).label("avg_position"),
        )
        .where(SearchPerformance.date >= cutoff, SearchPerformance.archetype.isnot(None))
        .group_by(SearchPerformance.archetype)
    )
    perf_rows = (await db.execute(perf_stmt)).all()
    perf_stats: dict[str, dict[str, Any]] = {
        row.archetype: {
            "total_impressions": int(row.total_impressions or 0),
            "total_clicks": int(row.total_clicks or 0),
            "avg_ctr": float(row.avg_ctr or 0.0),
            "avg_position": float(row.avg_position or 0.0),
        }
        for row in perf_rows
    }

    all_archetypes = sorted(set(list(page_stats.keys()) + list(perf_stats.keys())))
    items: list[ArchetypeAnalyticsItem] = []

    for arch in all_archetypes:
        p_info = page_stats.get(arch, {"total_pages": 0, "indexable_pages": 0})
        s_info = perf_stats.get(arch, {"total_impressions": 0, "total_clicks": 0, "avg_ctr": 0.0, "avg_position": 0.0})

        tot_pages = p_info["total_pages"]
        idx_pages = p_info["indexable_pages"]
        idx_rate = round((idx_pages / tot_pages * 100), 2) if tot_pages > 0 else 0.0
        tot_imps = s_info["total_impressions"]
        tot_clicks = s_info["total_clicks"]
        ctr_pct = round((tot_clicks / tot_imps * 100), 4) if tot_imps > 0 else (s_info["avg_ctr"] * 100)

        items.append(
            ArchetypeAnalyticsItem(
                archetype=arch,
                total_pages=tot_pages,
                indexable_pages=idx_pages,
                index_rate_pct=idx_rate,
                total_impressions=tot_imps,
                total_clicks=tot_clicks,
                average_ctr_pct=round(ctr_pct, 4),
                average_position=round(s_info["avg_position"], 2),
            )
        )

    return ArchetypeAnalyticsResponse(days_evaluated=days, archetypes=items)


@router.post("/analytics/sync-gsc", status_code=202)
async def trigger_gsc_sync(date: str | None = None) -> dict[str, str]:
    sync_daily_performance.delay(date_str=date)
    return {"status": "queued", "date": date or "default (2 days ago)"}
