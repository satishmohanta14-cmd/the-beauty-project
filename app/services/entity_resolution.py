"""
Entity Resolution Engine
========================
Matches messy retailer feed items against canonical ``Variant`` / ``Product``
records using a 3-tier confidence cascade.

Tier 1 — Deterministic  (confidence = 1.00)
    1a. GTIN / barcode exact match on ``variant.gtin``.
    1b. Composite key: ``brand.slug`` + slugified product name + exact ``size_ml``.

Tier 2 — Fuzzy String + Volume  (confidence 0.60–1.00)
    Load up to MAX_CANDIDATES variants within ±SIZE_TOLERANCE_PCT of ``size_ml``.
    Score each: 0.70 × rapidfuzz.WRatio(title, product.name) + 0.30 × size_score.
    Best candidate wins.

Tier 3 — Embedding Fallback  (confidence 0.70–0.85)
    Invoked when Tier 2 produces 0.70 ≤ score < AUTO_LINK_THRESHOLD.
    Encodes the input title via the injected ``Embedder`` protocol, queries
    ``product.name_vector`` using pgvector cosine ANN (``<=>``), and
    re-scores the top-5 candidates combining embedding similarity + size score.

Routing
-------
score >= AUTO_LINK_THRESHOLD (0.85):  auto-link → return ``variant_id`` immediately.
score <  AUTO_LINK_THRESHOLD:         enqueue in ``unresolved_entity_queue`` for
                                       admin review; return ``variant_id=None``.

Usage
-----
::

    svc = EntityResolutionService(session, embedder=SentenceTransformerEmbedder())
    result = await svc.resolve_and_route(item, size_ml=Decimal("30"), retailer_id=...)

    if result.auto_linked:
        # create offer with result.variant_id
    else:
        # item is now in unresolved_entity_queue — skip offer creation
"""
from __future__ import annotations

import difflib
import logging
import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.feed import RawFeedItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
AUTO_LINK_THRESHOLD: float = 0.85     # confidence required to skip the review queue
TIER3_LOWER_BOUND: float = 0.70       # invoke Tier 3 when Tier 2 score is in [0.70, 0.85)
SIZE_TOLERANCE_PCT: float = 0.05      # ±5 % size_ml tolerance for Tier-2 candidate fetch
SIZE_HARD_LIMIT_PCT: float = 0.15     # beyond ±15 % → size score = 0
NAME_WEIGHT: float = 0.70             # weight of name score in combined Tier-2 score
SIZE_WEIGHT: float = 0.30             # weight of size score in combined Tier-2 score
MAX_FUZZY_CANDIDATES: int = 50        # maximum Tier-2 DB candidates per query
MAX_EMBEDDING_CANDIDATES: int = 5     # pgvector ANN result limit for Tier 3
EMBEDDING_DIMS: int = 384             # vector dimension (all-MiniLM-L6-v2)


# ===========================================================================
# Data classes
# ===========================================================================


@dataclass
class ResolutionCandidate:
    """One potential match from any tier, before confidence thresholding."""

    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    size_ml: Decimal
    confidence: float
    tier: Literal["tier1", "tier2", "tier3"]
    method: str  # e.g. "gtin", "composite_slug", "fuzzy_name", "embedding"


@dataclass
class ResolutionResult:
    """
    Final output of the resolution cascade.

    ``auto_linked``         True when ``confidence >= AUTO_LINK_THRESHOLD``.
    ``variant_id``          Non-None only when ``auto_linked=True``.
    ``candidate_variant_id``  Best guess even if not auto-linked (for queue row).
    """

    tier: Literal["tier1", "tier2", "tier3", "no_match"]
    method: str
    confidence: float
    auto_linked: bool

    # Populated only when auto_linked=True
    variant_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None

    # Best candidate regardless of auto-link decision (stored in queue)
    candidate_variant_id: uuid.UUID | None = None
    candidate_product_id: uuid.UUID | None = None

    @classmethod
    def from_candidate(
        cls,
        candidate: ResolutionCandidate,
        *,
        threshold: float = AUTO_LINK_THRESHOLD,
    ) -> "ResolutionResult":
        auto = candidate.confidence >= threshold
        return cls(
            tier=candidate.tier,
            method=candidate.method,
            confidence=candidate.confidence,
            auto_linked=auto,
            variant_id=candidate.variant_id if auto else None,
            product_id=candidate.product_id if auto else None,
            candidate_variant_id=candidate.variant_id,
            candidate_product_id=candidate.product_id,
        )

    @classmethod
    def no_match(cls) -> "ResolutionResult":
        return cls(tier="no_match", method="exhausted", confidence=0.0, auto_linked=False)


# ===========================================================================
# Embedder protocol (dependency-injected for testability)
# ===========================================================================


@runtime_checkable
class Embedder(Protocol):
    """Minimal interface for a text embedding model."""

    def encode(self, text: str) -> list[float]:
        """Return a unit-normalised float vector of length ``EMBEDDING_DIMS``."""
        ...


class SentenceTransformerEmbedder:
    """
    Production embedder backed by ``sentence-transformers``.

    Requires ``pip install sentence-transformers`` (optional dep).
    Model: ``all-MiniLM-L6-v2`` (384 dims, fast, good zero-shot quality).
    """

    _instance: "SentenceTransformerEmbedder | None" = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(model_name)
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for Tier-3 entity resolution. "
                "Install with: pip install sentence-transformers"
            ) from exc

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()

    @classmethod
    def default(cls) -> "SentenceTransformerEmbedder":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class HashEmbedder:
    """
    Deterministic, dependency-free embedder for unit tests and CI.

    Produces a normalised pseudo-random vector seeded from the input text.
    Different texts → different (but stable) vectors.
    NOT suitable for production similarity — only for testing the Tier-3
    plumbing without a real ML model.
    """

    def encode(self, text: str) -> list[float]:
        import hashlib
        import math
        import struct

        digest = hashlib.sha256(text.encode()).digest()
        # Repeat digest bytes to fill EMBEDDING_DIMS * 4 bytes (f32)
        needed = EMBEDDING_DIMS * 4
        repeated = (digest * (needed // len(digest) + 1))[:needed]
        raw = list(struct.unpack(f"{EMBEDDING_DIMS}f", repeated))
        # Normalise to unit sphere
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]


# ===========================================================================
# Pure helpers (all static — testable without any DB)
# ===========================================================================

_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
_SLUG_WS_RE = re.compile(r"[\s_]+")
_SIZE_STRIP_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*"
    r"(?:fl\.?\s*oz\.?|millilitre?s?|milliliter?s?|kilograms?|litres?|liters?|grams?|kg|ml|[lgLG])",
    re.IGNORECASE,
)
_PCT_STRIP_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%")


def _slugify(text: str) -> str:
    """Convert raw text to a URL-style slug for composite key comparison."""
    t = _SLUG_STRIP_RE.sub("", text.lower().strip())
    t = _SLUG_WS_RE.sub("-", t)
    return re.sub(r"-+", "-", t).strip("-")


def _clean_product_title(title: str, brand_name: str | None, raw_size: str) -> str:
    """
    Produce a cleaned product title by stripping brand prefix, size text,
    and percentage values — used to derive a comparable slug for Tier-1 composite.
    """
    t = title
    if brand_name and t.lower().startswith(brand_name.lower()):
        t = t[len(brand_name) :].strip()
    t = _SIZE_STRIP_RE.sub("", t)
    t = _PCT_STRIP_RE.sub("", t)
    return t.strip(" ,;-+")


def _name_score(title_a: str, title_b: str) -> float:
    """
    Compute token-sort ratio between two product title strings (0–1).
    Uses rapidfuzz if available, falls back to difflib.
    """
    a = title_a.upper().strip()
    b = title_b.upper().strip()
    try:
        from rapidfuzz import fuzz

        return fuzz.WRatio(a, b) / 100.0
    except ImportError:
        return difflib.SequenceMatcher(None, a, b).ratio()


def _size_score(input_ml: Decimal, candidate_ml: Decimal) -> float:
    """
    Continuous size similarity:

    * Exact match → 1.00
    * Within SIZE_TOLERANCE_PCT (5 %) → 0.80–1.00 linearly
    * Between 5 % and SIZE_HARD_LIMIT_PCT (15 %) → 0.50 (partial credit)
    * Beyond 15 % → 0.00
    """
    if candidate_ml == 0:
        return 0.0
    deviation = abs(input_ml - candidate_ml) / candidate_ml
    if deviation == 0:
        return 1.0
    if deviation <= SIZE_TOLERANCE_PCT:
        # Linearly interpolate from 1.0 (exact) down to 0.80 at tolerance boundary
        return 1.0 - (deviation / SIZE_TOLERANCE_PCT) * 0.20
    if deviation <= SIZE_HARD_LIMIT_PCT:
        return 0.50
    return 0.0


def _combined_score(ns: float, ss: float) -> float:
    return NAME_WEIGHT * ns + SIZE_WEIGHT * ss


def _vec_to_pg_literal(vec: list[float]) -> str:
    """Format a Python float list as a pgvector literal: ``'[1.0,2.0,...]'``."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


# ===========================================================================
# EntityResolutionService
# ===========================================================================


class EntityResolutionService:
    """
    3-tier entity resolution cascade for retailer feed items.

    Parameters
    ----------
    session:
        Async SQLAlchemy session.
    embedder:
        Optional :class:`Embedder` implementation.  Required only when
        ``resolve()`` reaches Tier 3.  Inject :class:`HashEmbedder` in tests.
    auto_link_threshold:
        Minimum confidence to auto-link without human review (default 0.85).
    """

    def __init__(
        self,
        session: "AsyncSession",
        embedder: Embedder | None = None,
        *,
        auto_link_threshold: float = AUTO_LINK_THRESHOLD,
    ) -> None:
        self._session = session
        self._embedder = embedder
        self._threshold = auto_link_threshold

    # ── Public API ─────────────────────────────────────────────────────────

    async def resolve(
        self,
        item: RawFeedItem,
        size_ml: Decimal,
    ) -> ResolutionResult:
        """
        Run the 3-tier cascade and return a :class:`ResolutionResult`.

        Does NOT write to the DB — call :meth:`resolve_and_route` for that.
        """
        # ── Tier 1: Deterministic ──────────────────────────────────────────
        candidate = await self._tier1_gtin(item.gtin)
        if candidate is None:
            candidate = await self._tier1_composite(item, size_ml)
        if candidate is not None:
            logger.debug(
                "Tier-1 hit: method=%s variant=%s confidence=%.2f",
                candidate.method, candidate.variant_id, candidate.confidence,
            )
            return ResolutionResult.from_candidate(candidate, threshold=self._threshold)

        # ── Tier 2: Fuzzy string + volume ──────────────────────────────────
        candidate = await self._tier2_fuzzy(item, size_ml)
        if candidate is not None and candidate.confidence >= self._threshold:
            logger.debug(
                "Tier-2 auto-link: confidence=%.3f variant=%s",
                candidate.confidence, candidate.variant_id,
            )
            return ResolutionResult.from_candidate(candidate, threshold=self._threshold)

        # ── Tier 3: Embedding ANN fallback ─────────────────────────────────
        # Invoked when Tier 2 gave a partial signal (TIER3_LOWER_BOUND ≤ score < threshold)
        # or when Tier 2 produced no candidate at all.
        t2_confidence = candidate.confidence if candidate else 0.0
        if t2_confidence >= TIER3_LOWER_BOUND or candidate is None:
            t3_candidate = await self._tier3_embedding(item, size_ml)
            if t3_candidate is not None:
                # Use whichever tier produced the higher confidence
                if t3_candidate.confidence >= t2_confidence:
                    candidate = t3_candidate
                logger.debug(
                    "Tier-3 result: confidence=%.3f method=%s",
                    candidate.confidence, candidate.method,
                )

        if candidate is not None:
            return ResolutionResult.from_candidate(candidate, threshold=self._threshold)

        return ResolutionResult.no_match()

    async def resolve_and_route(
        self,
        item: RawFeedItem,
        size_ml: Decimal,
        retailer_id: uuid.UUID,
    ) -> ResolutionResult:
        """
        Run :meth:`resolve` and route the outcome:

        * ``auto_linked=True``  → return result (caller creates Offer).
        * ``auto_linked=False`` → insert into ``unresolved_entity_queue`` and return result.
        """
        result = await self.resolve(item, size_ml)
        if not result.auto_linked:
            await self._enqueue(item, size_ml, retailer_id, result)
        return result

    # ── Tier 1: Deterministic ───────────────────────────────────────────────

    async def _tier1_gtin(self, gtin: str | None) -> ResolutionCandidate | None:
        """Exact GTIN match on variant.gtin → confidence 1.0."""
        if not gtin:
            return None

        from sqlalchemy import select

        from app.models.product import Product
        from app.models.variant import Variant

        row = (
            await self._session.execute(
                select(Variant.id, Variant.size_ml, Product.id.label("product_id"), Product.name)
                .join(Product, Variant.product_id == Product.id)
                .where(Variant.gtin == gtin)
                .limit(1)
            )
        ).one_or_none()

        if row is None:
            return None

        return ResolutionCandidate(
            variant_id=row.id,
            product_id=row.product_id,
            product_name=row.name,
            size_ml=Decimal(str(row.size_ml)),
            confidence=1.0,
            tier="tier1",
            method="gtin",
        )

    async def _tier1_composite(
        self, item: RawFeedItem, size_ml: Decimal
    ) -> ResolutionCandidate | None:
        """
        Composite key: brand.slug == slugify(brand_name)
                       AND product.slug == slugify(cleaned_title)
                       AND variant.size_ml == size_ml (exact).
        """
        if not item.brand_name:
            return None

        from sqlalchemy import select, func as sa_func

        from app.models.brand import Brand
        from app.models.product import Product
        from app.models.variant import Variant

        brand_slug = _slugify(item.brand_name)
        cleaned = _clean_product_title(item.title, item.brand_name, item.raw_size)
        product_slug = _slugify(cleaned)

        if not brand_slug or not product_slug:
            return None

        row = (
            await self._session.execute(
                select(Variant.id, Variant.size_ml, Product.id.label("product_id"), Product.name)
                .join(Product, Variant.product_id == Product.id)
                .join(Brand, Product.brand_id == Brand.id)
                .where(
                    Brand.slug == brand_slug,
                    Product.slug == product_slug,
                    Variant.size_ml == float(size_ml),
                )
                .limit(1)
            )
        ).one_or_none()

        if row is None:
            return None

        return ResolutionCandidate(
            variant_id=row.id,
            product_id=row.product_id,
            product_name=row.name,
            size_ml=Decimal(str(row.size_ml)),
            confidence=1.0,
            tier="tier1",
            method="composite_slug",
        )

    # ── Tier 2: Fuzzy string + volume ────────────────────────────────────────

    async def _tier2_fuzzy(
        self, item: RawFeedItem, size_ml: Decimal
    ) -> ResolutionCandidate | None:
        """
        1. Fetch variants within ±SIZE_TOLERANCE_PCT of size_ml.
        2. Score each candidate: 0.70 × name_score + 0.30 × size_score.
        3. Return the highest-scoring candidate (or None if none exceed 0.0).
        """
        from sqlalchemy import and_, select

        from app.models.brand import Brand
        from app.models.product import Product
        from app.models.variant import Variant

        slack = float(size_ml) * SIZE_HARD_LIMIT_PCT
        min_size = float(size_ml) - slack
        max_size = float(size_ml) + slack

        rows = (
            await self._session.execute(
                select(
                    Variant.id,
                    Variant.size_ml,
                    Product.id.label("product_id"),
                    Product.name,
                )
                .join(Product, Variant.product_id == Product.id)
                .where(Variant.size_ml.between(min_size, max_size))
                .limit(MAX_FUZZY_CANDIDATES)
            )
        ).all()

        if not rows:
            return None

        best: ResolutionCandidate | None = None

        for row in rows:
            ns = _name_score(item.title, row.name)
            ss = _size_score(size_ml, Decimal(str(row.size_ml)))
            score = _combined_score(ns, ss)

            if best is None or score > best.confidence:
                best = ResolutionCandidate(
                    variant_id=row.id,
                    product_id=row.product_id,
                    product_name=row.name,
                    size_ml=Decimal(str(row.size_ml)),
                    confidence=round(score, 4),
                    tier="tier2",
                    method="fuzzy_name+size",
                )

        return best

    # ── Tier 3: Embedding ANN ────────────────────────────────────────────────

    async def _tier3_embedding(
        self, item: RawFeedItem, size_ml: Decimal
    ) -> ResolutionCandidate | None:
        """
        1. Encode item.title via self._embedder.
        2. Query pgvector for top-5 nearest products by cosine distance.
        3. Re-score candidates: 0.70 × embedding_sim + 0.30 × size_score.
        4. Return the best candidate, or None if embedder is unavailable.
        """
        if self._embedder is None:
            logger.debug("Tier-3 skipped: no embedder configured")
            return None

        try:
            vec = self._embedder.encode(item.title)
        except Exception as exc:
            logger.warning("Tier-3 embedder encode() failed: %s", exc)
            return None

        pg_literal = _vec_to_pg_literal(vec)
        slack = float(size_ml) * SIZE_HARD_LIMIT_PCT
        min_size = float(size_ml) - slack
        max_size = float(size_ml) + slack

        from sqlalchemy import text

        # cosine distance in pgvector: 0 = identical, 2 = opposite
        # cosine_similarity = 1 - cosine_distance
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        v.id              AS variant_id,
                        p.id              AS product_id,
                        p.name            AS product_name,
                        v.size_ml,
                        1 - (p.name_vector <=> :qv ::vector) AS cosine_sim
                    FROM variant v
                    JOIN product p ON p.id = v.product_id
                    WHERE p.name_vector IS NOT NULL
                      AND v.size_ml BETWEEN :min_size AND :max_size
                    ORDER BY p.name_vector <=> :qv ::vector
                    LIMIT :lim
                    """
                ).bindparams(
                    qv=pg_literal,
                    min_size=min_size,
                    max_size=max_size,
                    lim=MAX_EMBEDDING_CANDIDATES,
                )
            )
        ).all()

        if not rows:
            return None

        best: ResolutionCandidate | None = None

        for row in rows:
            emb_sim = float(row.cosine_sim)
            ss = _size_score(size_ml, Decimal(str(row.size_ml)))
            # Weighted: embedding contributes same NAME_WEIGHT as name did in Tier 2
            score = round(NAME_WEIGHT * emb_sim + SIZE_WEIGHT * ss, 4)

            if best is None or score > best.confidence:
                best = ResolutionCandidate(
                    variant_id=row.variant_id,
                    product_id=row.product_id,
                    product_name=row.product_name,
                    size_ml=Decimal(str(row.size_ml)),
                    confidence=score,
                    tier="tier3",
                    method="embedding_cosine",
                )

        return best

    # ── Queue insertion ──────────────────────────────────────────────────────

    async def _enqueue(
        self,
        item: RawFeedItem,
        size_ml: Decimal | None,
        retailer_id: uuid.UUID,
        result: ResolutionResult,
    ) -> None:
        """Insert a row into ``unresolved_entity_queue`` for admin review."""
        from app.models.unresolved_entity_queue import UnresolvedEntityQueue

        queue_row = UnresolvedEntityQueue(
            retailer_id=retailer_id,
            retailer_sku=item.retailer_sku,
            raw_title=item.title,
            raw_size=item.raw_size,
            size_ml=float(size_ml) if size_ml is not None else None,
            price=item.price,
            currency=item.currency,
            in_stock=item.in_stock,
            affiliate_url=item.affiliate_url,
            gtin=item.gtin,
            candidate_variant_id=result.candidate_variant_id,
            candidate_product_id=result.candidate_product_id,
            candidate_confidence=result.confidence if result.confidence > 0 else None,
            resolution_tier=result.tier,
            resolution_method=result.method,
            status="pending",
        )
        self._session.add(queue_row)
        await self._session.flush()
        logger.info(
            "Enqueued for review: sku=%r confidence=%.3f tier=%s",
            item.retailer_sku,
            result.confidence,
            result.tier,
        )
