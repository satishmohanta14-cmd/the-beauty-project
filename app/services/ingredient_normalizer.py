"""
INCI Ingredient Graph Normalizer
==================================
Parses raw cosmetic ingredient label strings into ordered, DB-matched
``NormalizedIngredient`` records that can be directly written to
``product_ingredient`` rows with the mandatory ``position`` field.

Pipeline
--------
::

    raw string
      ↓ tokenize()        split by comma, extract slash synonyms & parentheticals
      ↓ clean_token()     strip parens, brackets, percentages, normalise whitespace
      ↓ _IngredientCache  in-memory lookup built once per request from the DB
        ├─ exact_inci     O(1) dict lookup on inci_name (upper-cased)
        ├─ synonym        O(1) dict lookup on every synonym in synonyms[]
        ├─ fuzzy          rapidfuzz WRatio (≥ 85 % similarity) with difflib fallback
        └─ unmatched      flagged_for_review = True, ingredient_id = None
      ↓ NormalizedIngredient list (1-indexed positions, preserving INCI order)

Usage
-----
::

    normalizer = IngredientNormalizer(db_session)
    results = await normalizer.normalize(
        "Aqua / Water / Eau, Niacinamide (Vitamin B3), Glycerin 10%"
    )
    for item in results:
        print(item.position, item.inci_name, item.match_method)

Pure-parsing usage (no DB, for testing / CLI):
::

    tokens = IngredientParser.tokenize("Aqua / Water, Glycerin (10%)")

"""
from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Optional high-quality fuzzy backend
# ---------------------------------------------------------------------------
try:
    from rapidfuzz import fuzz as _rf_fuzz
    from rapidfuzz import process as _rf_process

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover
    _HAS_RAPIDFUZZ = False

# ---------------------------------------------------------------------------
# Default configuration constants
# ---------------------------------------------------------------------------
FUZZY_THRESHOLD: float = 0.85  # minimum similarity score for a fuzzy match (0–1)
FUZZY_REVIEW_THRESHOLD: float = 0.70  # below this → always flag for review


# ===========================================================================
# Data classes
# ===========================================================================


@dataclass
class ParsedToken:
    """
    One slot from the raw INCI label string.

    ``raw``        — original substring as extracted (before cleaning).
    ``candidates`` — ordered list of strings to attempt matching against the DB:
                     slash-separated parts come first, then any parenthetical
                     aliases.  The first candidate is the "primary" token.
    """

    raw: str
    candidates: list[str] = field(default_factory=list)

    @property
    def primary(self) -> str:
        """Return the primary (first) candidate, or empty string."""
        return self.candidates[0] if self.candidates else ""


@dataclass
class NormalizedIngredient:
    """
    The resolved record for one INCI position.

    ``position``   — 1-based index from the parsed label (mandatory per gemini.md).
    ``match_method`` — ``"exact_inci"`` | ``"synonym"`` | ``"fuzzy"`` | ``"unmatched"``
    ``confidence`` — 1.0 for exact / synonym hits; 0–1 for fuzzy; 0.0 for unmatched.
    ``flagged_for_review`` — True when unmatched *or* fuzzy confidence < FUZZY_THRESHOLD.
    """

    position: int
    raw_token: str
    inci_name: str | None
    canonical_name: str | None
    ingredient_id: uuid.UUID | None
    match_method: Literal["exact_inci", "synonym", "fuzzy", "unmatched"]
    confidence: float
    flagged_for_review: bool

    def is_resolved(self) -> bool:
        return self.ingredient_id is not None


# ===========================================================================
# Ingredient Parser  (pure — no DB, fully synchronous, trivially testable)
# ===========================================================================


class IngredientParser:
    """
    Stateless tokenizer / cleaner for raw cosmetic INCI label strings.

    All methods are class-level so there is no instantiation overhead.
    """

    # ── Compiled regex patterns ────────────────────────────────────────────
    # Capture group so we can inspect parenthetical content
    _PAREN_RE = re.compile(r"\(([^)]*)\)")
    _BRACKET_RE = re.compile(r"\[([^\]]*)\]")

    # Percentage values — "10%", "0.5 %", "2,5%"
    _PCT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*%")

    # "(and)" connector used in some EU label formats
    _AND_CONNECTOR_RE = re.compile(r"\band\b", re.IGNORECASE)

    # Collapse multiple spaces / tabs / newlines
    _WS_RE = re.compile(r"[ \t\r\n]+")

    # Tokens that are purely noise and should not become candidates
    _NOISE_TOKENS: frozenset[str] = frozenset(
        {
            "may contain",
            "peut contenir",
            "+/-",
            "and",
            "oder",
            "et",
            "",
        }
    )

    # ── Public API ─────────────────────────────────────────────────────────

    @classmethod
    def tokenize(cls, raw: str) -> list[ParsedToken]:
        """
        Split *raw* INCI string into an ordered list of :class:`ParsedToken`.

        Handles:

        * Comma-separated ingredient slots.
        * Slash-separated multi-lingual synonyms — ``"Aqua / Water / Eau"``.
        * Parenthetical common/trade names — ``"Niacinamide (Vitamin B3)"``.
        * Square-bracket annotations — ``"Salicylic Acid [BHA]"``.
        * Inline percentages — ``"Glycerin 10%"`` → primary token ``"Glycerin"``.
        * "(and)" EU connectors stripped from candidate strings.
        """
        if not raw or not raw.strip():
            return []

        tokens: list[ParsedToken] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            parsed = cls._parse_part(part)
            # Only keep tokens that produced at least one non-noise candidate
            if parsed.candidates:
                tokens.append(parsed)
        return tokens

    @classmethod
    def clean_token(cls, token: str) -> str:
        """
        Clean a *single* raw token string and return the primary candidate.

        Useful for ad-hoc cleaning without building a full ParsedToken.

        Examples::

            clean_token("Niacinamide (Vitamin B3)") == "Niacinamide"
            clean_token("Aqua / Water / Eau")        == "Aqua"
            clean_token("Glycerin 10%")              == "Glycerin"
        """
        result, _ = cls._strip_parentheticals(token)
        result, _ = cls._strip_brackets(result)
        result = cls._PCT_RE.sub("", result)
        result = cls._WS_RE.sub(" ", result).strip()
        parts = [p.strip() for p in result.split("/") if p.strip()]
        return parts[0] if parts else result.strip()

    # ── Private helpers ────────────────────────────────────────────────────

    @classmethod
    def _parse_part(cls, part: str) -> ParsedToken:
        raw = part

        # 1. Extract parenthetical and bracket aliases before stripping them
        cleaned, paren_aliases = cls._strip_parentheticals(part)
        cleaned, bracket_aliases = cls._strip_brackets(cleaned)

        # 2. Remove percentage text from the main string
        cleaned = cls._PCT_RE.sub("", cleaned)

        # 3. Normalise whitespace
        cleaned = cls._WS_RE.sub(" ", cleaned).strip()

        # 4. Split by "/" → each part is an alternative name for the same ingredient
        slash_parts = [p.strip() for p in cleaned.split("/") if p.strip()]

        # 5. Assemble candidates: slash parts first (most INCI-like), then aliases
        raw_candidates = slash_parts + paren_aliases + bracket_aliases

        # 6. Strip "(and)" connector words and percentage remnants from each candidate
        cleaned_candidates: list[str] = []
        for cand in raw_candidates:
            cand = cls._AND_CONNECTOR_RE.sub("", cand).strip()
            cand = cls._PCT_RE.sub("", cand).strip()
            cand = cls._WS_RE.sub(" ", cand).strip()
            if cand and cand.lower() not in cls._NOISE_TOKENS:
                cleaned_candidates.append(cand)

        return ParsedToken(raw=raw, candidates=cleaned_candidates)

    @classmethod
    def _strip_parentheticals(cls, text: str) -> tuple[str, list[str]]:
        """Remove ``(content)`` groups; return (stripped_text, list_of_content)."""
        aliases = [m.strip() for m in cls._PAREN_RE.findall(text) if m.strip()]
        stripped = cls._PAREN_RE.sub("", text)
        return stripped, aliases

    @classmethod
    def _strip_brackets(cls, text: str) -> tuple[str, list[str]]:
        """Remove ``[content]`` groups; return (stripped_text, list_of_content)."""
        aliases = [m.strip() for m in cls._BRACKET_RE.findall(text) if m.strip()]
        stripped = cls._BRACKET_RE.sub("", text)
        return stripped, aliases


# ===========================================================================
# Ingredient Cache  (in-memory lookup, built once per request or injected for tests)
# ===========================================================================


@dataclass
class _CacheEntry:
    ingredient_id: uuid.UUID
    inci_name: str
    canonical_name: str
    synonyms: list[str]


class _IngredientCache:
    """
    Flat in-memory lookup for O(1) exact and O(n) fuzzy ingredient matching.

    Build from the live DB via :meth:`from_db`, or from plain dicts for
    testing via :meth:`from_dicts`.
    """

    def __init__(self, entries: list[_CacheEntry]) -> None:
        self._entries = entries

        # Upper-cased key → entry (for exact lookup)
        self._by_inci: dict[str, _CacheEntry] = {}
        self._by_synonym: dict[str, _CacheEntry] = {}

        # All keys in one flat list (for fuzzy search)
        self._all_keys: list[str] = []

        for entry in entries:
            inci_key = entry.inci_name.upper().strip()
            self._by_inci[inci_key] = entry
            self._all_keys.append(inci_key)

            for syn in entry.synonyms or []:
                syn_key = syn.upper().strip()
                if syn_key:
                    self._by_synonym[syn_key] = entry
                    self._all_keys.append(syn_key)

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    async def from_db(cls, session: "AsyncSession") -> "_IngredientCache":
        """Load every ``Ingredient`` row into the cache (one query)."""
        from sqlalchemy import select

        from app.models.ingredient import Ingredient

        result = await session.execute(select(Ingredient))
        entries = [
            _CacheEntry(
                ingredient_id=ing.id,
                inci_name=ing.inci_name,
                canonical_name=ing.canonical_name,
                synonyms=list(ing.synonyms or []),
            )
            for ing in result.scalars().all()
        ]
        return cls(entries)

    @classmethod
    def from_dicts(cls, data: list[dict]) -> "_IngredientCache":
        """
        Build a cache from plain Python dicts — **no DB required**.

        Designed for unit tests and seed-time validation.

        Expected dict keys: ``inci_name``, ``canonical_name``,
        ``synonyms`` (optional), ``id`` (optional UUID).
        """
        entries = [
            _CacheEntry(
                ingredient_id=d.get("id") or uuid.uuid4(),
                inci_name=d["inci_name"],
                canonical_name=d["canonical_name"],
                synonyms=list(d.get("synonyms") or []),
            )
            for d in data
        ]
        return cls(entries)

    # ── Matching ───────────────────────────────────────────────────────────

    def match(
        self,
        candidates: list[str],
        fuzzy_threshold: float = FUZZY_THRESHOLD,
    ) -> tuple[str | None, str | None, uuid.UUID | None, str, float]:
        """
        Try to resolve *candidates* against the cache.

        Returns ``(inci_name, canonical_name, ingredient_id, method, confidence)``.

        Match priority:

        1. **exact_inci**  — upper-cased candidate == upper-cased inci_name.
        2. **synonym**     — upper-cased candidate == upper-cased synonym.
        3. **fuzzy**       — best rapidfuzz WRatio score ≥ fuzzy_threshold.
        4. **unmatched**   — nothing found; all return values are ``None`` / 0.0.
        """
        # ── 1. Exact INCI match ────────────────────────────────────────────
        for cand in candidates:
            key = cand.upper().strip()
            if key in self._by_inci:
                e = self._by_inci[key]
                return e.inci_name, e.canonical_name, e.ingredient_id, "exact_inci", 1.0

        # ── 2. Synonym match ───────────────────────────────────────────────
        for cand in candidates:
            key = cand.upper().strip()
            if key in self._by_synonym:
                e = self._by_synonym[key]
                return e.inci_name, e.canonical_name, e.ingredient_id, "synonym", 1.0

        # ── 3. Fuzzy match ─────────────────────────────────────────────────
        if not self._all_keys:
            return None, None, None, "unmatched", 0.0

        best_score = 0.0
        best_entry: _CacheEntry | None = None

        for cand in candidates:
            key = cand.upper().strip()
            if not key:
                continue

            if _HAS_RAPIDFUZZ:
                hit = _rf_process.extractOne(
                    key,
                    self._all_keys,
                    scorer=_rf_fuzz.WRatio,
                    score_cutoff=fuzzy_threshold * 100,
                )
                if hit:
                    score = hit[1] / 100.0
                    if score > best_score:
                        best_score = score
                        matched_key = hit[0]
                        best_entry = self._by_inci.get(matched_key) or self._by_synonym.get(
                            matched_key
                        )
            else:
                close = difflib.get_close_matches(
                    key, self._all_keys, n=1, cutoff=fuzzy_threshold
                )
                if close:
                    matched_key = close[0]
                    score = difflib.SequenceMatcher(None, key, matched_key).ratio()
                    if score > best_score:
                        best_score = score
                        best_entry = self._by_inci.get(matched_key) or self._by_synonym.get(
                            matched_key
                        )

        if best_entry and best_score >= fuzzy_threshold:
            return (
                best_entry.inci_name,
                best_entry.canonical_name,
                best_entry.ingredient_id,
                "fuzzy",
                round(best_score, 4),
            )

        # ── 4. Unmatched ───────────────────────────────────────────────────
        return None, None, None, "unmatched", 0.0


# ===========================================================================
# IngredientNormalizer  (async, DB-backed)
# ===========================================================================


class IngredientNormalizer:
    """
    Full pipeline: parse → clean → match against DB ingredient graph.

    Instantiate with a live :class:`~sqlalchemy.ext.asyncio.AsyncSession`
    for production use, or inject a pre-built :class:`_IngredientCache`
    via :meth:`with_cache` for testing.

    ::

        # Production
        normalizer = IngredientNormalizer(db_session)

        # Testing (no DB)
        cache = _IngredientCache.from_dicts([...])
        normalizer = IngredientNormalizer.with_cache(cache)

        results = await normalizer.normalize(raw_string)
    """

    def __init__(
        self,
        session: "AsyncSession | None" = None,
        *,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
    ) -> None:
        self._session = session
        self._cache: _IngredientCache | None = None
        self._fuzzy_threshold = fuzzy_threshold

    @classmethod
    def with_cache(
        cls,
        cache: _IngredientCache,
        fuzzy_threshold: float = FUZZY_THRESHOLD,
    ) -> "IngredientNormalizer":
        """Factory for test or offline usage — bypasses DB entirely."""
        inst = cls(session=None, fuzzy_threshold=fuzzy_threshold)
        inst._cache = cache
        return inst

    # ── Public API ─────────────────────────────────────────────────────────

    async def normalize(
        self,
        raw: str,
        *,
        fuzzy_threshold: float | None = None,
    ) -> list[NormalizedIngredient]:
        """
        Parse *raw* INCI label string and resolve each ingredient.

        Returns a list of :class:`NormalizedIngredient` in label order,
        with 1-based ``position`` values (ready for ``product_ingredient``
        insertion).

        Parameters
        ----------
        raw:
            Raw cosmetic ingredient label string, e.g.
            ``"Aqua / Water / Eau, Niacinamide (Vitamin B3), Glycerin"``.
        fuzzy_threshold:
            Override the instance-level fuzzy threshold for this call.
        """
        threshold = fuzzy_threshold if fuzzy_threshold is not None else self._fuzzy_threshold
        cache = await self._ensure_cache()
        parsed_tokens = IngredientParser.tokenize(raw)

        results: list[NormalizedIngredient] = []
        for position, token in enumerate(parsed_tokens, start=1):
            inci, canonical, ing_id, method, confidence = cache.match(
                token.candidates, fuzzy_threshold=threshold
            )
            flagged = method == "unmatched" or confidence < FUZZY_REVIEW_THRESHOLD
            results.append(
                NormalizedIngredient(
                    position=position,
                    raw_token=token.raw,
                    inci_name=inci,
                    canonical_name=canonical,
                    ingredient_id=ing_id,
                    match_method=method,  # type: ignore[arg-type]
                    confidence=confidence,
                    flagged_for_review=flagged,
                )
            )
        return results

    async def normalize_to_positions(
        self, raw: str
    ) -> list[tuple[int, uuid.UUID]]:
        """
        Convenience method — returns only ``(position, ingredient_id)``
        pairs for resolved ingredients (unmatched items are omitted).

        Suitable for bulk-inserting into ``product_ingredient``.
        """
        results = await self.normalize(raw)
        return [
            (r.position, r.ingredient_id)  # type: ignore[misc]
            for r in results
            if r.ingredient_id is not None
        ]

    # ── Private ────────────────────────────────────────────────────────────

    async def _ensure_cache(self) -> _IngredientCache:
        if self._cache is not None:
            return self._cache
        if self._session is None:
            raise RuntimeError(
                "IngredientNormalizer requires either a SQLAlchemy AsyncSession "
                "or a pre-built cache via IngredientNormalizer.with_cache(...)."
            )
        self._cache = await _IngredientCache.from_db(self._session)
        return self._cache
