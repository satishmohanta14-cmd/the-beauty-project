"""
Public API Schemas for Next.js ISR consumption.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# ── Product Details Schemas ──────────────────────────────────────────────────

class BrandBrief(BaseModel):
    name: str
    slug: str


class ProductIngredientItem(BaseModel):
    position: int
    inci_name: str
    canonical_name: str
    is_active: bool
    function: list[str] = Field(default_factory=list)
    comedogenic: int | None = None
    irritancy: int | None = None


class RetailerPriceComparison(BaseModel):
    retailer_name: str
    variant_size_ml: Decimal
    price: Decimal
    currency: str
    in_stock: bool
    affiliate_redirect_url: str


class PriceHistoryPoint(BaseModel):
    seen_at: datetime
    price: Decimal
    currency: str
    retailer_name: str


class ProductDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    brand: BrandBrief
    category_id: str
    format: str | None = None
    claims: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=list)
    dcs_score: int
    index_tier: str
    robots_meta: str = Field(description="'index, follow' or 'noindex, follow'")
    ingredients: list[ProductIngredientItem] = Field(default_factory=list)
    price_comparison: list[RetailerPriceComparison] = Field(default_factory=list)
    price_trend_30d: list[PriceHistoryPoint] = Field(default_factory=list)


# ── Dupes Schemas ────────────────────────────────────────────────────────────

class DupeAlternative(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    brand_name: str
    similarity: float
    price_delta_pct: float
    format: str | None = None
    price: Decimal | None = None
    size_ml: Decimal | None = None
    currency: str | None = None
    affiliate_redirect_url: str | None = None


class ProductDupesResponse(BaseModel):
    product_id: uuid.UUID
    product_name: str
    product_slug: str
    brand_name: str
    dupes: list[DupeAlternative] = Field(default_factory=list)


# ── Ingredient Schemas ───────────────────────────────────────────────────────

class ProductContainingIngredient(BaseModel):
    product_id: uuid.UUID
    name: str
    slug: str
    brand_name: str
    position: int
    is_active: bool
    dcs_score: int


class IngredientDetailResponse(BaseModel):
    id: uuid.UUID
    inci_name: str
    canonical_name: str
    synonyms: list[str] = Field(default_factory=list)
    cas_no: str | None = None
    function: list[str] = Field(default_factory=list)
    evidence_grade: str | None = None
    comedogenic: int | None = None
    irritancy: int | None = None
    top_products: list[ProductContainingIngredient] = Field(default_factory=list)


# ── Sitemap Archetype Schemas ────────────────────────────────────────────────

class SitemapUrlItem(BaseModel):
    url: str
    locale: str
    lastmod: datetime | None = None
    dcs_score: int


class SitemapArchetypeResponse(BaseModel):
    archetype: str
    page: int
    size: int
    total: int
    total_pages: int
    urls: list[SitemapUrlItem] = Field(default_factory=list)
