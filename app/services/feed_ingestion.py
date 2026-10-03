"""
Feed Ingestion Service
======================
Validates, transforms, and persists retailer feed items as append-only
``Offer`` rows.

Components
----------
``VolumeParser``
    Pure, stateless parser that converts raw cosmetic size strings into
    numeric millilitre values.  No DB access.

``FeedIngestionService``
    Async service that orchestrates variant resolution and offer insertion
    for a full :class:`~app.schemas.feed.FeedEnvelope` batch.

Append-Only Guarantee
---------------------
This module NEVER issues UPDATE statements against the ``offer`` table.
Every price observation creates a fresh row with the current timestamp.
The DB-level trigger ``trg_offer_no_update`` (defined in migration
``0001_initial_schema``) enforces this at the Postgres layer as well.

Volume Parsing
--------------
Supported units (case-insensitive):

    ml  mL  l  L  litre  liter  litres  liters
    oz  fl oz  fl.oz  fluid oz  fluid ounce(s)
    g   gm  gram  grams  kg  kilogram(s)

Multi-pack patterns: ``"2 x 50ml"`` → 100 ml
Slash-separated:     ``"30ml / 1.7 oz"`` → 30 ml (first match wins)
"""
from __future__ import annotations

import logging
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.feed import (
    FeedEnvelope,
    FeedIngestResult,
    IngestItemResult,
    ParsedOfferCreate,
    RawFeedItem,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unit conversion table  (all values → ml as Decimal)
# ---------------------------------------------------------------------------
_UNIT_TO_ML: dict[str, Decimal] = {
    # Millilitre variants
    "ml": Decimal("1"),
    "milliliter": Decimal("1"),
    "milliliters": Decimal("1"),
    "millilitre": Decimal("1"),
    "millilitres": Decimal("1"),
    # Litre variants
    "l": Decimal("1000"),
    "litre": Decimal("1000"),
    "liter": Decimal("1000"),
    "litres": Decimal("1000"),
    "liters": Decimal("1000"),
    # Fluid ounce variants  (1 fl oz = 29.5735 ml exactly)
    "oz": Decimal("29.5735"),
    "fl oz": Decimal("29.5735"),
    "fl.oz": Decimal("29.5735"),
    "fl. oz": Decimal("29.5735"),
    "fl.oz.": Decimal("29.5735"),
    "fluid oz": Decimal("29.5735"),
    "fluid ounce": Decimal("29.5735"),
    "fluid ounces": Decimal("29.5735"),
    # Gram variants  (cosmetic density ~1 g/ml — standard industry approximation)
    "g": Decimal("1"),
    "gm": Decimal("1"),
    "gr": Decimal("1"),
    "gram": Decimal("1"),
    "grams": Decimal("1"),
    # Kilogram
    "kg": Decimal("1000"),
    "kilogram": Decimal("1000"),
    "kilograms": Decimal("1000"),
}

# ---------------------------------------------------------------------------
# Compiled regex patterns for VolumeParser
# ---------------------------------------------------------------------------

# Unit alternatives, ordered longest-first to prevent prefix collisions.
_UNIT_ALT = (
    r"fl\.?\s*oz\.?"          # fl oz, fl.oz, fl. oz, fl.oz.
    r"|millilitres?"           # millilitre(s)
    r"|milliliters?"           # milliliter(s)
    r"|kilograms?"             # kilogram(s)
    r"|litres?"                # litre(s)
    r"|liters?"                # liter(s)
    r"|fluid\s+ounces?"        # fluid ounce(s)
    r"|fluid\s+oz\.?"          # fluid oz
    r"|grams?"                 # gram(s)
    r"|kg"                     # kg
    r"|ml"                     # ml
    r"|[gGlL]"                 # g, G, l, L — single-letter; matched LAST
)

# Multipack: "2 x 50ml", "2X50ml", "2 × 50 ml"
_MULTIPACK_RE = re.compile(
    rf"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*({_UNIT_ALT})",
    re.IGNORECASE,
)

# Single volume: number + optional space + unit
_VOLUME_RE = re.compile(
    rf"(\d+(?:[.,]\d+)?)\s*({_UNIT_ALT})",
    re.IGNORECASE,
)

# Decimal separator normalisation ("1,7" → "1.7" for European locales)
_COMMA_DECIMAL_RE = re.compile(r"(\d),(\d)")


# ===========================================================================
# VolumeParser
# ===========================================================================


class VolumeParser:
    """
    Pure, stateless converter for raw cosmetic size/volume strings.

    All methods are class-level; no instantiation needed.

    Examples
    --------
    >>> VolumeParser.parse("50ml")
    Decimal('50')
    >>> VolumeParser.parse("1.7 oz")
    Decimal('50.27')
    >>> VolumeParser.parse("2 x 50ml")
    Decimal('100')
    >>> VolumeParser.parse("30ml / 1.7 oz")
    Decimal('30')
    >>> VolumeParser.parse("invalid")
    # None
    """

    @classmethod
    def parse(cls, raw: str) -> Decimal | None:
        """
        Parse *raw* into a ``Decimal`` millilitre value.

        Returns ``None`` if no recognisable unit/number pair is found.
        The result is rounded to 2 decimal places.
        """
        if not raw or not raw.strip():
            return None

        normalised = cls._normalise(raw)

        # 1. Try multipack first ("2 x 50ml")
        mp = _MULTIPACK_RE.search(normalised)
        if mp:
            qty = Decimal(_COMMA_DECIMAL_RE.sub(r"\1.\2", mp.group(1)))
            vol = Decimal(_COMMA_DECIMAL_RE.sub(r"\1.\2", mp.group(2)))
            unit_key = cls._normalise_unit(mp.group(3))
            factor = _UNIT_TO_ML.get(unit_key)
            if factor is not None:
                return cls._round(qty * vol * factor)

        # 2. Single volume — return FIRST match (handles "30ml / 1.7 oz")
        m = _VOLUME_RE.search(normalised)
        if m:
            number = Decimal(_COMMA_DECIMAL_RE.sub(r"\1.\2", m.group(1)))
            unit_key = cls._normalise_unit(m.group(2))
            factor = _UNIT_TO_ML.get(unit_key)
            if factor is not None:
                return cls._round(number * factor)

        logger.debug("VolumeParser: no match in %r", raw)
        return None

    # ── Private helpers ────────────────────────────────────────────────────

    @staticmethod
    def _normalise(raw: str) -> str:
        """Collapse whitespace; keep original case for unit matching."""
        return re.sub(r"[ \t\r\n]+", " ", raw.strip())

    @staticmethod
    def _normalise_unit(unit: str) -> str:
        """Lower-case and collapse inner whitespace for dict lookup."""
        return re.sub(r"\s+", " ", unit.strip().lower())

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ===========================================================================
# FeedIngestionService
# ===========================================================================


class FeedIngestionService:
    """
    Async service that ingests a :class:`~app.schemas.feed.FeedEnvelope` into
    the database, producing one new ``Offer`` row per successfully resolved
    feed item.

    APPEND-ONLY CONTRACT
    --------------------
    ``_ingest_item()`` ONLY calls ``session.add(Offer(...))``.
    It never loads an existing ``Offer`` and never calls any update path.
    This is reinforced by the DB trigger ``trg_offer_no_update``.

    Usage
    -----
    ::

        async with async_session() as session:
            svc = FeedIngestionService(session)
            result = await svc.ingest_feed(envelope)
            await session.commit()   # caller controls the transaction
    """

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session

    # ── Public API ─────────────────────────────────────────────────────────

    async def ingest_feed(self, envelope: FeedEnvelope) -> FeedIngestResult:
        """
        Process every item in *envelope* and return an aggregate result.

        Items that cannot be resolved to an existing Variant are skipped
        (not failed) — variant creation is a separate workflow.
        """
        item_results: list[IngestItemResult] = []

        for item in envelope.items:
            result = await self._ingest_item(envelope.retailer_id, item)
            item_results.append(result)

        inserted = sum(1 for r in item_results if r.success)
        skipped = sum(1 for r in item_results if r.skipped)
        failed = sum(1 for r in item_results if not r.success and not r.skipped)

        return FeedIngestResult(
            retailer_id=envelope.retailer_id,
            retailer_slug=envelope.retailer_slug,
            total=len(item_results),
            inserted=inserted,
            skipped=skipped,
            failed=failed,
            errors=[r.error for r in item_results if r.error],
            item_results=item_results,
        )

    # ── Private pipeline steps ─────────────────────────────────────────────

    async def _ingest_item(
        self,
        retailer_id: uuid.UUID,
        item: RawFeedItem,
    ) -> IngestItemResult:
        """
        Full pipeline for a single feed item:
        1. Parse size_ml from raw_size.
        2. Resolve Variant (GTIN → size+title fallback).
        3. INSERT a new Offer row (append-only).
        """
        # ── 1. Volume parsing ──────────────────────────────────────────────
        size_ml = VolumeParser.parse(item.raw_size)
        if size_ml is None:
            msg = (
                f"[{item.retailer_sku}] Could not parse volume from "
                f"raw_size={item.raw_size!r}"
            )
            logger.warning(msg)
            return IngestItemResult(
                retailer_sku=item.retailer_sku,
                success=False,
                error=msg,
            )

        # ── 2. Variant resolution ──────────────────────────────────────────
        variant = await self._resolve_variant(item)
        if variant is None:
            msg = (
                f"[{item.retailer_sku}] No matching Variant found "
                f"(gtin={item.gtin!r}, size_ml={size_ml}, title={item.title!r})"
            )
            logger.info(msg)
            return IngestItemResult(
                retailer_sku=item.retailer_sku,
                success=False,
                skipped=True,
                size_ml=size_ml,
                error=msg,
            )

        # ── 3. APPEND-ONLY offer insert ────────────────────────────────────
        # Build the schema to validate before touching the DB.
        offer_data = ParsedOfferCreate(
            variant_id=variant.id,
            retailer_id=retailer_id,
            price=item.price,
            currency=item.currency,
            in_stock=item.in_stock,
            affiliate_url=item.affiliate_url,
            size_ml=size_ml,
        )

        offer = await self._insert_offer(offer_data)

        logger.debug(
            "Offer inserted: id=%s variant=%s price=%s %s",
            offer.id,
            variant.id,
            offer_data.price,
            offer_data.currency,
        )

        return IngestItemResult(
            retailer_sku=item.retailer_sku,
            success=True,
            offer_id=offer.id,
            variant_id=variant.id,
            size_ml=size_ml,
        )

    async def _resolve_variant(self, item: RawFeedItem):  # type: ignore[return]
        """
        Attempt to find an existing Variant for the feed item.

        Resolution strategy (in priority order):
        1. **GTIN** — most reliable; exact barcode match.
        2. Returns ``None`` if no match.
           Variant creation from feed data is handled by a separate workflow.
        """
        from sqlalchemy import select

        from app.models.variant import Variant

        # ── GTIN match ─────────────────────────────────────────────────────
        if item.gtin:
            result = await self._session.execute(
                select(Variant).where(Variant.gtin == item.gtin).limit(1)
            )
            variant = result.scalar_one_or_none()
            if variant:
                return variant

        return None

    async def _insert_offer(self, data: ParsedOfferCreate):  # type: ignore[return]
        """
        Create and persist a new Offer row.

        ────────────────────────────────────────────────────
        APPEND-ONLY RULE — Do NOT modify this method to load
        an existing Offer and change its fields.  Always
        construct a fresh Offer instance and call session.add().
        ────────────────────────────────────────────────────
        """
        from app.models.offer import Offer

        offer = Offer(
            variant_id=data.variant_id,
            retailer_id=data.retailer_id,
            price=data.price,
            currency=data.currency,
            in_stock=data.in_stock,
            affiliate_url=data.affiliate_url,
            # seen_at is set by server_default=func.now() in the DB
        )
        self._session.add(offer)
        # flush() resolves the Python-side default uuid so offer.id is populated
        await self._session.flush()
        return offer
