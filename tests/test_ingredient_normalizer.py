"""
Unit tests for app/services/ingredient_normalizer.py
=====================================================

All tests run without a live database — the ``normalizer`` and ``mock_cache``
fixtures from conftest.py inject an in-memory _IngredientCache.

Test coverage:
  IngredientParser
    ✓ tokenize — simple comma list
    ✓ tokenize — slash-separated synonyms produce multiple candidates
    ✓ tokenize — parenthetical aliases are extracted as candidates
    ✓ tokenize — inline percentages are stripped
    ✓ tokenize — square bracket annotations stripped
    ✓ tokenize — empty / whitespace-only input → empty list
    ✓ tokenize — position (list index) is preserved in order
    ✓ clean_token — parentheticals removed
    ✓ clean_token — percentage stripped
    ✓ clean_token — slash → first part only
    ✓ clean_token — combined: parens + percent + slash

  _IngredientCache
    ✓ exact INCI match (case-insensitive)
    ✓ synonym match — "Aqua" resolves to "Water"
    ✓ synonym match — "Vitamin B3" resolves to "Niacinamide"
    ✓ fuzzy match — deliberate single-char typo still matches
    ✓ unmatched — completely unknown ingredient

  IngredientNormalizer (async, DB-free via injected cache)
    ✓ normalize — position index starts at 1 and is sequential
    ✓ normalize — order is preserved from input string
    ✓ normalize — synonym resolution sets correct inci_name
    ✓ normalize — unmatched ingredient is flagged for review
    ✓ normalize — mixed resolved + unmatched in same string
    ✓ normalize — complex label: slashes + parens + percentage
    ✓ normalize_to_positions — only returns resolved (non-None) pairs
    ✓ normalize — all resolved items have is_resolved() == True
"""
from __future__ import annotations

import uuid

import pytest

from app.services.ingredient_normalizer import (
    FUZZY_THRESHOLD,
    IngredientNormalizer,
    IngredientParser,
    NormalizedIngredient,
    ParsedToken,
    _IngredientCache,
)


# ===========================================================================
# IngredientParser — pure / synchronous tests
# ===========================================================================


class TestIngredientParserTokenize:
    """Tests for IngredientParser.tokenize()"""

    def test_simple_comma_list(self) -> None:
        tokens = IngredientParser.tokenize("Water, Glycerin, Niacinamide")
        assert len(tokens) == 3
        assert tokens[0].primary == "Water"
        assert tokens[1].primary == "Glycerin"
        assert tokens[2].primary == "Niacinamide"

    def test_slash_separated_synonyms_produce_multiple_candidates(self) -> None:
        tokens = IngredientParser.tokenize("Aqua / Water / Eau")
        assert len(tokens) == 1
        tok = tokens[0]
        assert "Aqua" in tok.candidates
        assert "Water" in tok.candidates
        assert "Eau" in tok.candidates

    def test_slash_primary_is_first_part(self) -> None:
        tokens = IngredientParser.tokenize("Aqua / Water / Eau")
        assert tokens[0].primary == "Aqua"

    def test_parenthetical_content_extracted_as_alias(self) -> None:
        tokens = IngredientParser.tokenize("Niacinamide (Vitamin B3)")
        assert len(tokens) == 1
        tok = tokens[0]
        assert "Niacinamide" in tok.candidates
        assert "Vitamin B3" in tok.candidates

    def test_inline_percentage_stripped(self) -> None:
        tokens = IngredientParser.tokenize("Glycerin 10%")
        assert len(tokens) == 1
        assert "Glycerin" in tokens[0].candidates
        # The "10%" should NOT appear as a standalone candidate
        assert not any("%" in c for c in tokens[0].candidates)

    def test_parenthetical_percentage_stripped(self) -> None:
        tokens = IngredientParser.tokenize("Salicylic Acid (2%)")
        tok = tokens[0]
        assert "Salicylic Acid" in tok.candidates
        assert not any("%" in c for c in tok.candidates)

    def test_square_bracket_stripped_from_primary_but_kept_as_alias(self) -> None:
        tokens = IngredientParser.tokenize("Salicylic Acid [BHA]")
        tok = tokens[0]
        assert "Salicylic Acid" in tok.candidates
        assert "BHA" in tok.candidates

    def test_empty_string_returns_empty_list(self) -> None:
        assert IngredientParser.tokenize("") == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        assert IngredientParser.tokenize("   ") == []

    def test_position_order_preserved(self) -> None:
        """
        The order of tokens in the returned list MUST match the order of
        ingredients in the raw label string (INCI descending concentration).
        """
        raw = "Water, Glycerin, Niacinamide, Salicylic Acid"
        tokens = IngredientParser.tokenize(raw)
        primaries = [t.primary for t in tokens]
        assert primaries == ["Water", "Glycerin", "Niacinamide", "Salicylic Acid"]

    def test_trailing_leading_whitespace_normalised(self) -> None:
        tokens = IngredientParser.tokenize("  Water  ,  Glycerin  ")
        assert tokens[0].primary == "Water"
        assert tokens[1].primary == "Glycerin"

    def test_complex_eu_label(self) -> None:
        """Real-world label with slashes, parens, and percentages."""
        raw = "Aqua / Water / Eau, Niacinamide (Vitamin B3) 10%, Glycerin (vegetable)"
        tokens = IngredientParser.tokenize(raw)
        assert len(tokens) == 3
        # First token: slash synonyms
        assert "Aqua" in tokens[0].candidates
        assert "Water" in tokens[0].candidates
        # Second token: niacinamide primary, vitamin B3 as alias, no %
        assert "Niacinamide" in tokens[1].candidates
        assert "Vitamin B3" in tokens[1].candidates
        assert not any("%" in c for c in tokens[1].candidates)
        # Third token: glycerin primary, "vegetable" as alias (parenthetical)
        assert "Glycerin" in tokens[2].candidates


class TestIngredientParserCleanToken:
    """Tests for IngredientParser.clean_token()"""

    def test_removes_parenthetical(self) -> None:
        assert IngredientParser.clean_token("Niacinamide (Vitamin B3)") == "Niacinamide"

    def test_removes_trailing_percentage(self) -> None:
        assert IngredientParser.clean_token("Glycerin 10%") == "Glycerin"

    def test_removes_inline_percentage(self) -> None:
        assert IngredientParser.clean_token("Retinol 0.5%") == "Retinol"

    def test_slash_returns_first_part(self) -> None:
        assert IngredientParser.clean_token("Aqua / Water / Eau") == "Aqua"

    def test_combined_parens_percent_slash(self) -> None:
        result = IngredientParser.clean_token("Salicylic Acid (BHA) / Beta Hydroxy Acid 2%")
        assert result == "Salicylic Acid"

    def test_plain_token_unchanged(self) -> None:
        assert IngredientParser.clean_token("Glycerin") == "Glycerin"

    def test_bracket_annotation_removed(self) -> None:
        assert IngredientParser.clean_token("Salicylic Acid [BHA]") == "Salicylic Acid"


# ===========================================================================
# _IngredientCache — matching logic tests
# ===========================================================================


class TestIngredientCache:
    """Unit tests for the in-memory matching cache."""

    def test_exact_inci_match(self, mock_cache: _IngredientCache) -> None:
        inci, canonical, ing_id, method, confidence = mock_cache.match(["Water"])
        assert inci == "Water"
        assert method == "exact_inci"
        assert confidence == 1.0
        assert ing_id == uuid.UUID("00000000-0000-0000-0000-000000000001")

    def test_exact_inci_match_case_insensitive(self, mock_cache: _IngredientCache) -> None:
        inci, _, _, method, confidence = mock_cache.match(["water"])
        assert inci == "Water"
        assert method == "exact_inci"
        assert confidence == 1.0

    def test_synonym_aqua_resolves_to_water(self, mock_cache: _IngredientCache) -> None:
        """
        'Aqua' is a synonym of 'Water' — the canonical INCI name must be returned.
        This is the EU multilingual label synonym case.
        """
        inci, canonical, ing_id, method, confidence = mock_cache.match(["Aqua"])
        assert inci == "Water"
        assert canonical == "Water"
        assert method == "synonym"
        assert confidence == 1.0
        assert ing_id == uuid.UUID("00000000-0000-0000-0000-000000000001")

    def test_synonym_eau_resolves_to_water(self, mock_cache: _IngredientCache) -> None:
        inci, _, _, method, _ = mock_cache.match(["Eau"])
        assert inci == "Water"
        assert method == "synonym"

    def test_synonym_vitamin_b3_resolves_to_niacinamide(
        self, mock_cache: _IngredientCache
    ) -> None:
        inci, _, ing_id, method, _ = mock_cache.match(["Vitamin B3"])
        assert inci == "Niacinamide"
        assert method == "synonym"
        assert ing_id == uuid.UUID("00000000-0000-0000-0000-000000000002")

    def test_synonym_bha_resolves_to_salicylic_acid(self, mock_cache: _IngredientCache) -> None:
        inci, _, _, method, _ = mock_cache.match(["BHA"])
        assert inci == "Salicylic Acid"
        assert method == "synonym"

    def test_fuzzy_match_single_typo(self, mock_cache: _IngredientCache) -> None:
        """
        'Niacinamiide' (double 'i') should fuzzy-match 'Niacinamide' above threshold.
        """
        inci, _, _, method, confidence = mock_cache.match(["Niacinamiide"])
        assert inci == "Niacinamide"
        assert method == "fuzzy"
        assert confidence >= FUZZY_THRESHOLD

    def test_fuzzy_match_glycerol_to_glycerin(self, mock_cache: _IngredientCache) -> None:
        """
        'Glycerol' is a synonym, not a fuzzy hit — but tests that synonym lookup
        wins over fuzzy when available.
        """
        inci, _, _, method, _ = mock_cache.match(["Glycerol"])
        assert inci == "Glycerin"
        # Should be synonym, not fuzzy
        assert method == "synonym"

    def test_unmatched_unknown_ingredient(self, mock_cache: _IngredientCache) -> None:
        inci, canonical, ing_id, method, confidence = mock_cache.match(
            ["Completely Unknown Compound XYZ-999"]
        )
        assert inci is None
        assert canonical is None
        assert ing_id is None
        assert method == "unmatched"
        assert confidence == 0.0

    def test_slash_candidates_fallback(self, mock_cache: _IngredientCache) -> None:
        """
        When the primary slash-part is unknown, the second part should still match.
        e.g. "Wasser / Water" — "Wasser" is not in DB but "Water" is.
        """
        inci, _, _, method, _ = mock_cache.match(["Wasser", "Water"])
        assert inci == "Water"
        assert method == "exact_inci"

    def test_empty_candidates_returns_unmatched(self, mock_cache: _IngredientCache) -> None:
        inci, _, _, method, confidence = mock_cache.match([])
        assert method == "unmatched"
        assert confidence == 0.0


# ===========================================================================
# IngredientNormalizer — async pipeline tests
# ===========================================================================


class TestIngredientNormalizer:
    """End-to-end async tests for IngredientNormalizer (no DB)."""

    async def test_positions_start_at_one_and_are_sequential(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        INCI position encoding is mandatory (gemini.md §2).
        Positions must be 1-based and contiguous.
        """
        raw = "Water, Glycerin, Niacinamide"
        results = await normalizer.normalize(raw)
        assert [r.position for r in results] == [1, 2, 3]

    async def test_order_preserved_from_input_string(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        Output order MUST match label order — this directly feeds the dupe
        vector calculation weights.
        """
        raw = "Niacinamide, Water, Glycerin"
        results = await normalizer.normalize(raw)
        assert results[0].inci_name == "Niacinamide"
        assert results[1].inci_name == "Water"
        assert results[2].inci_name == "Glycerin"

    async def test_synonym_aqua_sets_inci_name_water(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        Core synonym resolution: 'Aqua' on label → inci_name 'Water' in DB.
        The returned NormalizedIngredient must carry the canonical INCI name.
        """
        results = await normalizer.normalize("Aqua / Water / Eau")
        assert len(results) == 1
        result = results[0]
        assert result.inci_name == "Water"
        assert result.match_method == "synonym"  # first match is "Aqua" via synonym
        assert result.flagged_for_review is False
        assert result.ingredient_id == uuid.UUID("00000000-0000-0000-0000-000000000001")

    async def test_vitamin_b3_in_parens_resolves_niacinamide(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        When the primary token 'Niacinamide' is exact-matched, the parenthetical
        alias is never needed.  When primary is unknown, the alias 'Vitamin B3'
        should still resolve via synonym.
        """
        results = await normalizer.normalize("Niacinamide (Vitamin B3)")
        assert results[0].inci_name == "Niacinamide"
        assert results[0].match_method == "exact_inci"

    async def test_unknown_ingredient_flagged_for_review(
        self, normalizer: IngredientNormalizer
    ) -> None:
        results = await normalizer.normalize("Unicorn Extract ZZZ-001")
        assert len(results) == 1
        result = results[0]
        assert result.inci_name is None
        assert result.ingredient_id is None
        assert result.match_method == "unmatched"
        assert result.flagged_for_review is True
        assert result.is_resolved() is False

    async def test_mixed_resolved_and_unmatched(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        Unmatched items must NOT shift the positions of resolved items.
        Positions are always based on the original label order.
        """
        raw = "Water, Unknown Ingredient XYZ, Glycerin"
        results = await normalizer.normalize(raw)
        assert len(results) == 3
        assert results[0].position == 1
        assert results[0].inci_name == "Water"
        assert results[1].position == 2
        assert results[1].inci_name is None
        assert results[1].flagged_for_review is True
        assert results[2].position == 3
        assert results[2].inci_name == "Glycerin"

    async def test_complex_label_with_slashes_parens_percentage(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        Full integration: real-world EU label format.
        """
        raw = (
            "Aqua / Water / Eau, "
            "Niacinamide (Vitamin B3) 10%, "
            "Glycerin, "
            "Salicylic Acid [BHA] 2%, "
            "Phenoxyethanol"
        )
        results = await normalizer.normalize(raw)
        assert len(results) == 5

        # Position 1: Aqua → Water
        assert results[0].position == 1
        assert results[0].inci_name == "Water"

        # Position 2: Niacinamide (Vitamin B3) 10%
        assert results[1].position == 2
        assert results[1].inci_name == "Niacinamide"
        assert results[1].flagged_for_review is False

        # Position 3: Glycerin
        assert results[2].position == 3
        assert results[2].inci_name == "Glycerin"

        # Position 4: Salicylic Acid [BHA] 2%
        assert results[3].position == 4
        assert results[3].inci_name == "Salicylic Acid"

        # Position 5: Phenoxyethanol
        assert results[4].position == 5
        assert results[4].inci_name == "Phenoxyethanol"

    async def test_normalize_to_positions_excludes_unmatched(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        normalize_to_positions() must only yield (position, uuid) pairs
        for successfully resolved ingredients.
        """
        raw = "Water, Unknown XYZ, Glycerin"
        pairs = await normalizer.normalize_to_positions(raw)
        positions = [p for p, _ in pairs]
        assert positions == [1, 3]
        # All returned IDs must be valid UUIDs (not None)
        assert all(isinstance(ing_id, uuid.UUID) for _, ing_id in pairs)

    async def test_all_resolved_items_have_is_resolved_true(
        self, normalizer: IngredientNormalizer
    ) -> None:
        raw = "Water, Glycerin, Niacinamide"
        results = await normalizer.normalize(raw)
        assert all(r.is_resolved() for r in results)

    async def test_single_ingredient(self, normalizer: IngredientNormalizer) -> None:
        results = await normalizer.normalize("Retinol")
        assert len(results) == 1
        assert results[0].position == 1
        assert results[0].inci_name == "Retinol"

    async def test_fuzzy_match_typo_in_normalize(
        self, normalizer: IngredientNormalizer
    ) -> None:
        """
        A deliberate single-character typo should still resolve via fuzzy match.
        The match_method must be 'fuzzy' and confidence should be high.
        """
        results = await normalizer.normalize("Niacinamiide")  # double 'i'
        assert len(results) == 1
        result = results[0]
        assert result.inci_name == "Niacinamide"
        assert result.match_method == "fuzzy"
        assert result.confidence >= FUZZY_THRESHOLD

    async def test_provitamin_b5_synonym_resolves_panthenol(
        self, normalizer: IngredientNormalizer
    ) -> None:
        results = await normalizer.normalize("Provitamin B5")
        assert results[0].inci_name == "Panthenol"
        assert results[0].match_method == "synonym"

    async def test_with_cache_factory_no_session_required(
        self, mock_cache: _IngredientCache
    ) -> None:
        """
        IngredientNormalizer.with_cache() must work without any DB session.
        Calling normalize() should not raise RuntimeError.
        """
        norm = IngredientNormalizer.with_cache(mock_cache)
        results = await norm.normalize("Water")
        assert results[0].inci_name == "Water"

    async def test_no_session_no_cache_raises(self) -> None:
        """
        Calling normalize() without a session AND without an injected cache
        must raise RuntimeError immediately.
        """
        norm = IngredientNormalizer(session=None)
        with pytest.raises(RuntimeError, match="AsyncSession"):
            await norm.normalize("Water")
