"""
Pydantic v2 schemas for the retailer feed ingestion pipeline.

Schema hierarchy
----------------
::

    RawFeedItem          — one item as it arrives from any retailer feed
         ↓  (validated & volume-parsed by FeedIngestionService)
    ParsedOfferCreate    — clean, typed record ready to write to offer table
         ↓
    IngestItemResult     — per-item outcome (success / skipped / failed)
         ↓ aggregated
    FeedIngestResult     — summary for the entire batch run

    FeedEnvelope         — top-level wrapper sent to the Celery task
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# ===========================================================================
# Input schemas
# ===========================================================================


class RawFeedItem(BaseModel):
    """
    One raw item from a retailer affiliate feed.

    Accepts messy real-world data — raw size strings, mixed-case currency
    codes, empty GTINs — and applies minimal normalisation via validators.
    Volume parsing to ``size_ml`` is handled later by
    :class:`~app.services.feed_ingestion.VolumeParser`.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    # ── Identification ────────────────────────────────────────────────────
    retailer_sku: str = Field(
        ...,
        min_length=1,
        description="Retailer's own product/SKU identifier.",
    )
    gtin: str | None = Field(
        None,
        description="EAN-13 / UPC-12 / EAN-8 barcode for deterministic variant matching.",
    )

    # ── Product meta ──────────────────────────────────────────────────────
    title: str = Field(
        ...,
        min_length=1,
        description="Full product title as listed by the retailer.",
    )
    brand_name: str | None = Field(None, description="Brand name if available in feed.")
    raw_size: str = Field(
        ...,
        min_length=1,
        description="Raw size/volume string from feed, e.g. '50ml', '1.7 oz', '100 g'.",
    )

    # ── Pricing ───────────────────────────────────────────────────────────
    price: Decimal = Field(
        ...,
        gt=Decimal("0"),
        decimal_places=2,
        description="Selling price in the retailer's local currency.",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code, e.g. INR, USD, GBP.",
    )

    # ── Availability ──────────────────────────────────────────────────────
    in_stock: bool = Field(True, description="Whether the item is currently available.")

    # ── Affiliate ─────────────────────────────────────────────────────────
    affiliate_url: str = Field(
        ...,
        min_length=10,
        description="Trackable affiliate deep-link URL.",
    )

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("currency")
    @classmethod
    def _currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @field_validator("gtin", mode="before")
    @classmethod
    def _normalise_gtin(cls, v: object) -> str | None:
        """Coerce empty strings / whitespace-only GTINs to None."""
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    @field_validator("price", mode="before")
    @classmethod
    def _coerce_price(cls, v: object) -> Decimal:
        """Accept int / float / str, convert to Decimal."""
        return Decimal(str(v))


class FeedEnvelope(BaseModel):
    """
    Top-level envelope sent to the Celery ingest task.

    Wraps a batch of :class:`RawFeedItem` objects from one retailer, along
    with the retailer's DB UUID (required to create Offer rows).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    retailer_id: UUID = Field(..., description="UUID of the Retailer row in the DB.")
    retailer_slug: str = Field(
        ...,
        min_length=1,
        description="Human-readable slug, e.g. 'nykaa', 'amazon_in', 'sephora_us'.",
    )
    items: list[RawFeedItem] = Field(..., min_length=1, description="Feed items to ingest.")
    source_url: str | None = Field(None, description="Original feed URL if available.")


# ===========================================================================
# Internal / service-layer schemas
# ===========================================================================


class ParsedOfferCreate(BaseModel):
    """
    A fully validated, type-clean Offer record ready for DB insertion.

    Produced by :class:`~app.services.feed_ingestion.FeedIngestionService`
    after variant resolution and volume parsing.

    NOTE: This schema represents an INSERT payload only.
          Never use it as the source for an UPDATE.
    """

    variant_id: UUID
    retailer_id: UUID
    price: Decimal
    currency: str
    in_stock: bool
    affiliate_url: str
    size_ml: Decimal = Field(..., gt=Decimal("0"), description="Parsed volume in millilitres.")


# ===========================================================================
# Result schemas
# ===========================================================================


class IngestItemResult(BaseModel):
    """Per-item outcome from a single feed ingest attempt."""

    retailer_sku: str
    success: bool
    offer_id: UUID | None = None
    variant_id: UUID | None = None
    size_ml: Decimal | None = None
    error: str | None = None
    skipped: bool = False

    @model_validator(mode="after")
    def _validate_consistency(self) -> "IngestItemResult":
        if self.success and self.offer_id is None:
            raise ValueError("A successful IngestItemResult must have an offer_id.")
        return self


class FeedIngestResult(BaseModel):
    """Aggregate outcome for an entire :class:`FeedEnvelope` batch."""

    retailer_id: UUID
    retailer_slug: str
    total: int
    inserted: int
    skipped: int
    failed: int
    errors: list[str] = Field(default_factory=list)
    item_results: list[IngestItemResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_totals(self) -> "FeedIngestResult":
        if self.inserted + self.skipped + self.failed != self.total:
            raise ValueError(
                f"inserted({self.inserted}) + skipped({self.skipped}) + "
                f"failed({self.failed}) must equal total({self.total})."
            )
        return self
