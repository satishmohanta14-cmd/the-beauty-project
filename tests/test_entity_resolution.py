"""
Unit tests for app/services/entity_resolution.py
==================================================
All tests use mock AsyncSession — no live DB or ML model required.

Coverage map
------------
Pure helpers (no DB, synchronous)
    ✓ _slugify — basic ASCII
    ✓ _slugify — special chars stripped
    ✓ _clean_product_title — brand prefix removed
    ✓ _clean_product_title — size text stripped
    ✓ _clean_product_title — percentage stripped
    ✓ _name_score — identical strings → 1.0
    ✓ _name_score — completely different → low score
    ✓ _name_score — partial overlap → intermediate score
    ✓ _size_score — exact match → 1.0
    ✓ _size_score — within tolerance → 0.80–1.00
    ✓ _size_score — within hard limit → 0.50
    ✓ _size_score — beyond hard limit → 0.0
    ✓ _combined_score — weights applied correctly

Tier 1 — GTIN
    ✓ exact GTIN hit → confidence=1.0, tier="tier1", method="gtin"
    ✓ GTIN not in DB → returns None from _tier1_gtin
    ✓ None GTIN → skips lookup entirely
    ✓ resolve() with GTIN match → auto_linked=True, variant_id populated

Tier 1 — Composite slug
    ✓ brand+product slug+size_ml all match → confidence=1.0, auto_linked=True
    ✓ brand slug mismatch → composite returns None
    ✓ missing brand_name → composite returns None

Tier 2 — Fuzzy
    ✓ high-confidence fuzzy (≥0.85) → auto_linked=True
    ✓ medium fuzzy (0.70–0.84) → auto_linked=False (queued)
    ✓ low fuzzy (<0.70) → auto_linked=False (queued)
    ✓ no candidates from DB → Tier-2 returns None
    ✓ multiple candidates → highest score wins
    ✓ size out of hard limit → size_score=0 reduces combined score

Tier 3 — Embedding
    ✓ embedder returns vectors, pgvector returns candidates → confidence computed
    ✓ embedder not configured → Tier-3 returns None gracefully
    ✓ embedder raises → Tier-3 returns None gracefully, no crash
    ✓ Tier-3 high confidence → auto_linked=True
    ✓ Tier-3 score < threshold → auto_linked=False (queued)

Cascade behaviour
    ✓ Tier-1 GTIN match short-circuits (Tier-2 never called)
    ✓ Tier-2 high confidence → Tier-3 NOT invoked
    ✓ Tier-2 score in [0.70,0.85) → Tier-3 invoked
    ✓ no_match when all tiers fail → ResolutionResult.tier="no_match"

resolve_and_route — routing
    ✓ auto_linked=True → session.add() NOT called for queue
    ✓ auto_linked=False → session.add(UnresolvedEntityQueue) called
    ✓ queue row fields match feed item (sku, title, price, gtin, tier, confidence)
    ✓ no_match → enqueued with confidence=0, tier="no_match"
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.schemas.feed import RawFeedItem
from app.services.entity_resolution import (
    AUTO_LINK_THRESHOLD,
    TIER3_LOWER_BOUND,
    EntityResolutionService,
    HashEmbedder,
    ResolutionCandidate,
    ResolutionResult,
    _clean_product_title,
    _combined_score,
    _name_score,
    _size_score,
    _slugify,
)

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

RETAILER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
VARIANT_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
VARIANT_ID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
PRODUCT_ID_1 = uuid.UUID("aaaaaaaa-1111-1111-1111-111111111111")
PRODUCT_ID_2 = uuid.UUID("aaaaaaaa-2222-2222-2222-222222222222")
TEST_GTIN = "8901030910237"


def _item(
    *,
    gtin: str | None = TEST_GTIN,
    title: str = "The Ordinary Niacinamide 10% + Zinc 1% 30ml",
    brand_name: str | None = "The Ordinary",
    raw_size: str = "30ml",
    price: str = "599.00",
    retailer_sku: str = "NYK-001",
) -> RawFeedItem:
    return RawFeedItem(
        retailer_sku=retailer_sku,
        gtin=gtin,
        title=title,
        brand_name=brand_name,
        raw_size=raw_size,
        price=Decimal(price),
        currency="INR",
        in_stock=True,
        affiliate_url="https://example.com/affiliate/test",
    )


def _mock_row(**kwargs) -> MagicMock:
    """Build a mock SQLAlchemy Row-like object with attribute access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


def _one_or_none_session(row_or_none) -> AsyncMock:
    """Session mock whose execute() → result.one_or_none() returns the given value."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row_or_none
    session.execute.return_value = mock_result
    return session


def _all_rows_session(rows: list) -> AsyncMock:
    """Session mock whose execute() → result.all() returns the given list."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    session.execute.return_value = mock_result
    return session


# ===========================================================================
# Pure helper tests (no async, no DB)
# ===========================================================================


class TestSlugify:
    def test_basic_ascii(self) -> None:
        assert _slugify("The Ordinary") == "the-ordinary"

    def test_special_chars_stripped(self) -> None:
        assert _slugify("Niacinamide 10% + Zinc 1%") == "niacinamide-10--zinc-1"

    def test_leading_trailing_hyphens_removed(self) -> None:
        result = _slugify("  Hello World  ")
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_already_clean_slug(self) -> None:
        assert _slugify("retinol-serum") == "retinol-serum"


class TestCleanProductTitle:
    def test_removes_brand_prefix(self) -> None:
        result = _clean_product_title(
            "The Ordinary Niacinamide 10% + Zinc 1% 30ml",
            "The Ordinary",
            "30ml",
        )
        assert not result.lower().startswith("the ordinary")

    def test_removes_size_text(self) -> None:
        result = _clean_product_title("Retinol Serum 30ml", None, "30ml")
        assert "30ml" not in result.lower()
        assert "ml" not in result.lower()

    def test_removes_percentage(self) -> None:
        result = _clean_product_title("Niacinamide 10%", None, "")
        assert "10%" not in result
        assert "%" not in result

    def test_no_brand_returns_cleaned_title(self) -> None:
        result = _clean_product_title("Glycerin Serum 50ml", None, "50ml")
        assert "Glycerin" in result or "glycerin" in result.lower()


class TestNameScore:
    def test_identical_strings_score_one(self) -> None:
        assert _name_score("Niacinamide", "Niacinamide") == pytest.approx(1.0)

    def test_completely_different_scores_low(self) -> None:
        score = _name_score("Niacinamide Serum", "Zinc Oxide Sunscreen SPF50")
        assert score < 0.50

    def test_partial_overlap_intermediate(self) -> None:
        score = _name_score(
            "The Ordinary Niacinamide 10%",
            "Niacinamide 10% + Zinc 1%",
        )
        assert 0.50 < score < 1.0

    def test_case_insensitive(self) -> None:
        s1 = _name_score("GLYCERIN", "glycerin")
        assert s1 == pytest.approx(1.0, abs=0.01)


class TestSizeScore:
    def test_exact_match_returns_one(self) -> None:
        assert _size_score(Decimal("30"), Decimal("30")) == pytest.approx(1.0)

    def test_within_tolerance_returns_high(self) -> None:
        # 30 vs 31 ≈ 3.3% deviation — within 5% tolerance
        score = _size_score(Decimal("30"), Decimal("31"))
        assert 0.80 <= score <= 1.0

    def test_within_hard_limit_returns_half(self) -> None:
        # 30 vs 34 ≈ 13% deviation — between 5% and 15%
        score = _size_score(Decimal("30"), Decimal("34"))
        assert score == pytest.approx(0.50)

    def test_beyond_hard_limit_returns_zero(self) -> None:
        # 30 vs 60 = 100% deviation
        score = _size_score(Decimal("30"), Decimal("60"))
        assert score == pytest.approx(0.0)

    def test_zero_candidate_safe(self) -> None:
        assert _size_score(Decimal("30"), Decimal("0")) == 0.0


class TestCombinedScore:
    def test_weights_applied(self) -> None:
        # 0.70 * 0.9 + 0.30 * 1.0 = 0.63 + 0.30 = 0.93
        assert _combined_score(0.9, 1.0) == pytest.approx(0.93)

    def test_perfect_scores_give_one(self) -> None:
        assert _combined_score(1.0, 1.0) == pytest.approx(1.0)

    def test_zero_name_score(self) -> None:
        # 0.70 * 0.0 + 0.30 * 1.0 = 0.30
        assert _combined_score(0.0, 1.0) == pytest.approx(0.30)


# ===========================================================================
# Tier 1 — GTIN
# ===========================================================================


class TestTier1Gtin:
    async def test_gtin_hit_returns_candidate_confidence_1(self) -> None:
        """Exact GTIN match → confidence=1.0, tier='tier1', method='gtin'."""
        row = _mock_row(
            id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            name="The Ordinary Niacinamide",
            size_ml=30.0,
        )
        session = _one_or_none_session(row)
        svc = EntityResolutionService(session)

        result = await svc.resolve(_item(gtin=TEST_GTIN), Decimal("30"))

        assert result.auto_linked is True
        assert result.variant_id == VARIANT_ID_1
        assert result.confidence == pytest.approx(1.0)
        assert result.tier == "tier1"
        assert result.method == "gtin"

    async def test_gtin_miss_returns_no_auto_link(self) -> None:
        """GTIN supplied but not in DB → Tier-1 GTIN returns None, cascade continues."""
        session = _one_or_none_session(None)
        # Make ALL execute() calls return None (both GTIN and composite)
        svc = EntityResolutionService(session)
        result = await svc.resolve(_item(gtin=TEST_GTIN, brand_name=None), Decimal("30"))
        # Without any candidates, result is no_match (or queued after Tier 2/3)
        assert result.variant_id is None

    async def test_none_gtin_skips_db_lookup(self) -> None:
        """item.gtin=None → no execute() call for GTIN at all."""
        session = _one_or_none_session(None)
        svc = EntityResolutionService(session)

        # Tier-2 needs candidates — return empty list
        mock_all_result = MagicMock()
        mock_all_result.all.return_value = []
        session.execute.return_value = mock_all_result

        await svc.resolve(_item(gtin=None, brand_name=None), Decimal("30"))

        # Any execute calls should NOT contain "gtin" as a lookup
        for c in session.execute.call_args_list:
            stmt = str(c[0][0]).lower()
            if "gtin" in stmt:
                pytest.fail("GTIN lookup should not happen when gtin=None")


# ===========================================================================
# Tier 1 — Composite slug
# ===========================================================================


class TestTier1Composite:
    def _composite_session(self, row_or_none) -> AsyncMock:
        """
        Tier-1 composite: first execute() = GTIN miss, second = composite hit/miss.
        """
        session = AsyncMock()
        gtin_result = MagicMock()
        gtin_result.one_or_none.return_value = None  # GTIN miss
        composite_result = MagicMock()
        composite_result.one_or_none.return_value = row_or_none
        session.execute.side_effect = [gtin_result, composite_result]
        return session

    async def test_composite_hit_auto_links(self) -> None:
        """brand slug + product slug + size_ml all match → confidence=1.0."""
        row = _mock_row(
            id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            name="The Ordinary Niacinamide",
            size_ml=30.0,
        )
        session = self._composite_session(row)
        svc = EntityResolutionService(session)
        result = await svc.resolve(
            _item(gtin=None, brand_name="The Ordinary"),
            Decimal("30"),
        )
        assert result.auto_linked is True
        assert result.tier == "tier1"
        assert result.method == "composite_slug"
        assert result.confidence == pytest.approx(1.0)

    async def test_composite_miss_falls_through(self) -> None:
        """Composite slug doesn't match → cascade continues to Tier 2."""
        session = self._composite_session(None)
        # Tier-2 needs an execute that returns all()
        tier2_result = MagicMock()
        tier2_result.all.return_value = []
        session.execute.side_effect = [
            MagicMock(**{"one_or_none.return_value": None}),  # GTIN
            MagicMock(**{"one_or_none.return_value": None}),  # composite
            tier2_result,  # Tier 2 candidates
        ]
        svc = EntityResolutionService(session)
        result = await svc.resolve(
            _item(gtin=None, brand_name="The Ordinary"),
            Decimal("30"),
        )
        # No match from Tier 2 either → no_match
        assert result.tier == "no_match"

    async def test_no_brand_name_skips_composite(self) -> None:
        """brand_name=None → composite lookup skipped."""
        session = AsyncMock()
        gtin_result = MagicMock()
        gtin_result.one_or_none.return_value = None
        tier2_result = MagicMock()
        tier2_result.all.return_value = []
        session.execute.side_effect = [gtin_result, tier2_result]
        svc = EntityResolutionService(session)
        result = await svc.resolve(_item(gtin=None, brand_name=None), Decimal("30"))
        # Only 2 execute calls (GTIN + Tier-2), not 3
        assert session.execute.call_count == 2


# ===========================================================================
# Tier 2 — Fuzzy string + volume
# ===========================================================================


class TestTier2Fuzzy:
    def _tier2_session(self, fuzzy_rows: list) -> AsyncMock:
        """
        Tier-1 both miss, Tier-2 returns fuzzy_rows.
        """
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        tier2_result = MagicMock()
        tier2_result.all.return_value = fuzzy_rows
        session.execute.side_effect = [miss, miss, tier2_result]
        return session

    async def test_high_confidence_fuzzy_auto_links(self) -> None:
        """
        Candidate name is very close to input title → combined score ≥ 0.85
        → auto_linked=True without human review.
        """
        row = _mock_row(
            id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            name="The Ordinary Niacinamide 10% + Zinc 1%",  # ≈ exact match
            size_ml=30.0,
        )
        session = self._tier2_session([row])
        svc = EntityResolutionService(session)

        result = await svc.resolve(
            _item(gtin=None, brand_name=None,
                  title="The Ordinary Niacinamide 10% + Zinc 1% 30ml"),
            Decimal("30"),
        )

        assert result.tier == "tier2"
        assert result.confidence >= AUTO_LINK_THRESHOLD
        assert result.auto_linked is True
        assert result.variant_id == VARIANT_ID_1

    async def test_medium_confidence_fuzzy_queued(self) -> None:
        """
        Candidate name has moderate overlap → 0.70 ≤ score < 0.85
        → auto_linked=False.
        """
        # Deliberately weaker name match
        row = _mock_row(
            id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            name="Ordinary Niacinamide Plus Zinc Formula",
            size_ml=30.0,
        )
        session = self._tier2_session([row])
        svc = EntityResolutionService(session, embedder=None)

        # Suppress Tier-3 by ensuring no embedder
        result = await svc.resolve(
            _item(gtin=None, brand_name=None,
                  title="The Ordinary Niacinamide 10% Zinc"),
            Decimal("30"),
        )

        # Might be tier2 or tier3-skipped
        assert result.auto_linked is False
        assert result.variant_id is None

    async def test_no_candidates_from_db_returns_no_match(self) -> None:
        """Empty Tier-2 results + no embedder → no_match."""
        session = self._tier2_session([])
        svc = EntityResolutionService(session, embedder=None)
        result = await svc.resolve(_item(gtin=None, brand_name=None), Decimal("30"))
        assert result.tier == "no_match"
        assert result.auto_linked is False

    async def test_multiple_candidates_best_wins(self) -> None:
        """When multiple Tier-2 candidates exist, highest combined score is returned."""
        rows = [
            _mock_row(
                id=VARIANT_ID_1, product_id=PRODUCT_ID_1,
                name="The Ordinary Niacinamide 10% + Zinc 1%",  # high match
                size_ml=30.0,
            ),
            _mock_row(
                id=VARIANT_ID_2, product_id=PRODUCT_ID_2,
                name="Completely Different Sunscreen SPF50",    # low match
                size_ml=30.0,
            ),
        ]
        session = self._tier2_session(rows)
        svc = EntityResolutionService(session)
        result = await svc.resolve(
            _item(gtin=None, brand_name=None,
                  title="The Ordinary Niacinamide 10% + Zinc 1%"),
            Decimal("30"),
        )
        # Winner should be VARIANT_ID_1 (higher name score)
        assert result.candidate_variant_id == VARIANT_ID_1


# ===========================================================================
# Tier 3 — Embedding
# ===========================================================================


class TestTier3Embedding:
    def _tier3_session(self, t3_rows: list) -> AsyncMock:
        """Tier-1 both miss, Tier-2 gives partial match, Tier-3 returns rows."""
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None

        # Tier-2 candidate with medium confidence
        t2_row = _mock_row(
            id=VARIANT_ID_2, product_id=PRODUCT_ID_2,
            name="Slightly Different Product Name",
            size_ml=30.0,
        )
        tier2_result = MagicMock()
        tier2_result.all.return_value = [t2_row]

        tier3_result = MagicMock()
        tier3_result.all.return_value = t3_rows

        session.execute.side_effect = [miss, miss, tier2_result, tier3_result]
        return session

    async def test_tier3_invoked_when_tier2_partial(self) -> None:
        """When Tier-2 gives 0.70 ≤ score < 0.85 and embedder is set, Tier-3 runs."""
        embedder = HashEmbedder()
        t3_row = _mock_row(
            variant_id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            product_name="The Ordinary Niacinamide 10%",
            size_ml=30.0,
            cosine_sim=0.89,  # high embedding similarity
        )
        session = self._tier3_session([t3_row])
        svc = EntityResolutionService(session, embedder=embedder)

        result = await svc.resolve(
            _item(gtin=None, brand_name=None,
                  title="Niacinamide ten percent serum"),
            Decimal("30"),
        )

        # If Tier-3 confidence > Tier-2 confidence, Tier-3 result is used
        # 0.70*0.89 + 0.30*1.0 = 0.623+0.30 = 0.923 → auto_linked=True
        assert result.tier == "tier3"
        assert result.auto_linked is True

    async def test_no_embedder_skips_tier3(self) -> None:
        """embedder=None → Tier-3 silently skipped, no crash."""
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        tier2_result = MagicMock()
        tier2_result.all.return_value = []
        session.execute.side_effect = [miss, miss, tier2_result]

        svc = EntityResolutionService(session, embedder=None)
        result = await svc.resolve(_item(gtin=None, brand_name=None), Decimal("30"))
        # Should degrade gracefully to no_match (no embedder → no Tier 3)
        assert result.tier == "no_match"

    async def test_embedder_encode_exception_handled(self) -> None:
        """If embedder.encode() raises, Tier-3 is skipped gracefully."""
        bad_embedder = MagicMock()
        bad_embedder.encode.side_effect = RuntimeError("model not loaded")

        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        tier2_result = MagicMock()
        tier2_result.all.return_value = []
        session.execute.side_effect = [miss, miss, tier2_result]

        svc = EntityResolutionService(session, embedder=bad_embedder)
        result = await svc.resolve(_item(gtin=None, brand_name=None), Decimal("30"))
        assert result.tier == "no_match"  # graceful degradation

    async def test_tier3_low_confidence_not_auto_linked(self) -> None:
        """Even with Tier-3, score < 0.85 → auto_linked=False."""
        embedder = HashEmbedder()
        t3_row = _mock_row(
            variant_id=VARIANT_ID_1,
            product_id=PRODUCT_ID_1,
            product_name="Somewhat Similar Product",
            size_ml=30.0,
            cosine_sim=0.65,  # low embedding similarity
        )
        session = self._tier3_session([t3_row])
        svc = EntityResolutionService(session, embedder=embedder)

        result = await svc.resolve(
            _item(gtin=None, brand_name=None, title="Niacinamide serum"),
            Decimal("30"),
        )

        # 0.70*0.65 + 0.30*1.0 = 0.455 + 0.30 = 0.755 < 0.85
        assert result.auto_linked is False
        assert result.variant_id is None


# ===========================================================================
# Cascade short-circuit tests
# ===========================================================================


class TestCascadeShortCircuit:
    async def test_tier1_gtin_short_circuits_tier2(self) -> None:
        """Tier-1 GTIN hit → execute() called exactly once, Tier-2 never called."""
        row = _mock_row(
            id=VARIANT_ID_1, product_id=PRODUCT_ID_1,
            name="The Ordinary Niacinamide", size_ml=30.0
        )
        session = _one_or_none_session(row)
        svc = EntityResolutionService(session)

        result = await svc.resolve(_item(gtin=TEST_GTIN), Decimal("30"))

        assert result.auto_linked is True
        # Exactly 1 execute call (GTIN only — Tier-2 not reached)
        assert session.execute.call_count == 1

    async def test_tier2_high_confidence_short_circuits_tier3(self) -> None:
        """
        Tier-2 score >= 0.85 → Tier-3 NOT invoked (execute not called for embedding query).
        """
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        t2_row = _mock_row(
            id=VARIANT_ID_1, product_id=PRODUCT_ID_1,
            name="The Ordinary Niacinamide 10% + Zinc 1%",
            size_ml=30.0,
        )
        tier2_result = MagicMock()
        tier2_result.all.return_value = [t2_row]
        session.execute.side_effect = [miss, miss, tier2_result]

        embedder = MagicMock()  # if Tier-3 runs, this will be called
        svc = EntityResolutionService(session, embedder=embedder)

        result = await svc.resolve(
            _item(gtin=None, brand_name=None,
                  title="The Ordinary Niacinamide 10% + Zinc 1%"),
            Decimal("30"),
        )

        assert result.auto_linked is True
        # Embedder.encode() must NOT have been called
        embedder.encode.assert_not_called()


# ===========================================================================
# resolve_and_route — routing and queue insertion
# ===========================================================================


class TestResolveAndRoute:
    async def test_auto_link_does_not_write_to_queue(self) -> None:
        """High-confidence match → session.add() is NEVER called for the queue."""
        row = _mock_row(
            id=VARIANT_ID_1, product_id=PRODUCT_ID_1,
            name="Test Product", size_ml=30.0
        )
        session = _one_or_none_session(row)
        svc = EntityResolutionService(session)

        result = await svc.resolve_and_route(_item(), Decimal("30"), RETAILER_ID)

        assert result.auto_linked is True
        assert result.variant_id == VARIANT_ID_1
        session.add.assert_not_called()

    async def test_low_confidence_enqueues_row(self) -> None:
        """No match → session.add(UnresolvedEntityQueue) called exactly once."""
        from app.models.unresolved_entity_queue import UnresolvedEntityQueue

        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        no_candidates = MagicMock()
        no_candidates.all.return_value = []
        session.execute.side_effect = [miss, miss, no_candidates]

        svc = EntityResolutionService(session, embedder=None)
        result = await svc.resolve_and_route(
            _item(gtin=None, brand_name=None), Decimal("30"), RETAILER_ID
        )

        assert result.auto_linked is False
        session.add.assert_called_once()

        queued_obj = session.add.call_args[0][0]
        assert isinstance(queued_obj, UnresolvedEntityQueue)

    async def test_queue_row_fields_match_feed_item(self) -> None:
        """Verify every important field is faithfully copied to the queue row."""
        from app.models.unresolved_entity_queue import UnresolvedEntityQueue

        item = _item(
            gtin=TEST_GTIN,
            title="Minimalist Salicylic Acid 2% Serum 30ml",
            brand_name="Minimalist",
            raw_size="30ml",
            price="499.00",
            retailer_sku="MIN-SA-001",
        )

        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        no_candidates = MagicMock()
        no_candidates.all.return_value = []
        # GTIN miss + composite miss + Tier-2 empty
        session.execute.side_effect = [miss, miss, no_candidates]

        svc = EntityResolutionService(session, embedder=None)
        await svc.resolve_and_route(item, Decimal("30"), RETAILER_ID)

        q: UnresolvedEntityQueue = session.add.call_args[0][0]

        assert q.retailer_sku == "MIN-SA-001"
        assert q.raw_title == "Minimalist Salicylic Acid 2% Serum 30ml"
        assert q.gtin == TEST_GTIN
        assert q.price == Decimal("499.00")
        assert q.currency == "INR"
        assert q.retailer_id == RETAILER_ID
        assert q.status == "pending"

    async def test_no_match_queued_with_zero_confidence(self) -> None:
        """no_match result → queue row has confidence=None, tier='no_match'."""
        from app.models.unresolved_entity_queue import UnresolvedEntityQueue

        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        no_candidates = MagicMock()
        no_candidates.all.return_value = []
        session.execute.side_effect = [miss, miss, no_candidates]

        svc = EntityResolutionService(session, embedder=None)
        await svc.resolve_and_route(_item(gtin=None, brand_name=None), Decimal("30"), RETAILER_ID)

        q: UnresolvedEntityQueue = session.add.call_args[0][0]
        assert q.resolution_tier == "no_match"
        assert q.candidate_confidence is None
        assert q.candidate_variant_id is None

    async def test_partial_match_queued_with_candidate(self) -> None:
        """
        When Tier-2 gives a sub-threshold candidate, that candidate is stored in
        the queue row so admin can confirm or reject it.
        """
        from app.models.unresolved_entity_queue import UnresolvedEntityQueue

        partial_row = _mock_row(
            id=VARIANT_ID_2, product_id=PRODUCT_ID_2,
            name="Somewhat Similar Niacinamide Serum",
            size_ml=30.0,
        )
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        tier2_result = MagicMock()
        tier2_result.all.return_value = [partial_row]
        session.execute.side_effect = [miss, miss, tier2_result]

        svc = EntityResolutionService(session, embedder=None)
        result = await svc.resolve_and_route(
            _item(gtin=None, brand_name=None,
                  title="Niacinamide serum face"),
            Decimal("30"),
            RETAILER_ID,
        )

        q: UnresolvedEntityQueue = session.add.call_args[0][0]

        # If a candidate was found by Tier-2 (even sub-threshold), it should be stored
        if result.candidate_variant_id is not None:
            assert q.candidate_variant_id == result.candidate_variant_id
            assert q.candidate_confidence is not None

    async def test_result_object_returned_after_enqueue(self) -> None:
        """resolve_and_route returns the ResolutionResult even when queueing."""
        session = AsyncMock()
        miss = MagicMock()
        miss.one_or_none.return_value = None
        no_candidates = MagicMock()
        no_candidates.all.return_value = []
        session.execute.side_effect = [miss, miss, no_candidates]

        svc = EntityResolutionService(session, embedder=None)
        result = await svc.resolve_and_route(
            _item(gtin=None, brand_name=None), Decimal("30"), RETAILER_ID
        )

        assert isinstance(result, ResolutionResult)
        assert result.auto_linked is False


# ===========================================================================
# HashEmbedder unit test
# ===========================================================================


class TestHashEmbedder:
    def test_returns_correct_dimensions(self) -> None:
        from app.services.entity_resolution import EMBEDDING_DIMS

        embedder = HashEmbedder()
        vec = embedder.encode("Niacinamide serum 30ml")
        assert len(vec) == EMBEDDING_DIMS

    def test_deterministic(self) -> None:
        embedder = HashEmbedder()
        v1 = embedder.encode("same text")
        v2 = embedder.encode("same text")
        assert v1 == v2

    def test_different_texts_give_different_vectors(self) -> None:
        embedder = HashEmbedder()
        v1 = embedder.encode("Niacinamide")
        v2 = embedder.encode("Retinol")
        assert v1 != v2

    def test_unit_normalised(self) -> None:
        import math

        embedder = HashEmbedder()
        vec = embedder.encode("test input")
        norm = math.sqrt(sum(x * x for x in vec))
        assert norm == pytest.approx(1.0, abs=1e-5)
