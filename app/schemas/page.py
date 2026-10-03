"""
Page schemas for Programmatic SEO, Hybrid Routing & Metadata APIs.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HrefLangTag(BaseModel):
    locale: str
    url: str


class PageMetadataResponse(BaseModel):
    id: uuid.UUID
    url: str
    archetype: str
    locale: str
    dcs_score: int
    indexable: bool
    robots_meta: str = Field(description="'index, follow' or 'noindex, follow'")
    first_indexed_at: datetime | None = None
    hreflang: list[HrefLangTag] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class SitemapEntry(BaseModel):
    loc: str
    lastmod: datetime | None = None
    changefreq: str = "daily"
    priority: float = 0.8


class SitemapResponse(BaseModel):
    total: int
    pages: list[SitemapEntry]
