"""
Unit tests for Data Completeness Score (DCS), Promotion Logic & Indexability Gate.
===================================================================================
Verifies:
  - 6-part scoring rubric adherence (ingredients, offers, reviews, price history, media, expert annotation)
  - Promotion logic:
      DCS >= 70 -> page.indexable = True, product.index_tier = 'indexed', robots_meta = 'index, follow'
      DCS < 70  -> page.indexable = False, product.index_tier = 'provisional', robots_meta = 'noindex, follow'
  - Mandatory criteria (/p/ offers, /ingredient/ expert review)
  - first_indexed_at lifecycle preservation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.page import Page
from app.models.product import Product
from app.services.dcs_evaluator import (
    ARCHETYPE_BEST,
    ARCHETYPE_DUPE,
    ARCHETYPE_INGREDIENT,
    ARCHETYPE_PRODUCT,
    DCS_INDEX_THRESHOLD,
    DCSEvaluator,
    DCSRubricMetrics,
    TIER_INDEXED,
    TIER_PROVISIONAL,
)


class TestDCSEvaluatorRubric:
    def test_full_marks_yields_100_and_promotes_to_indexed(self) -> None:
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,              # +30
            live_offer_count=3,                         # +20
            parsed_review_count=20,                     # +20
            price_history_days=45,                      # +10
            has_image_and_variant_coverage=True,        # +10
            has_expert_annotation=True,                 # +10
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_PRODUCT, metrics)
        assert res.score == 100
        assert res.mandatory_passed is True
        assert res.indexable is True
        assert res.index_tier == TIER_INDEXED
        assert res.robots_meta == "index, follow"
        assert len(res.reasons) == 0

    def test_exactly_70_points_promotes_product_and_page(self) -> None:
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,              # +30 (Mandatory)
            live_offer_count=2,                         # +20 (Mandatory for /p/)
            parsed_review_count=15,                     # +20
            price_history_days=0,                       # 0
            has_image_and_variant_coverage=False,       # 0
            has_expert_annotation=False,                # 0
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_PRODUCT, metrics)
        assert res.score == 70
        assert res.mandatory_passed is True
        assert res.indexable is True
        assert res.index_tier == TIER_INDEXED
        assert res.robots_meta == "index, follow"

    def test_score_below_70_retains_provisional_and_noindex(self) -> None:
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,              # +30
            live_offer_count=2,                         # +20
            parsed_review_count=5,                      # 0 (< 15)
            price_history_days=35,                      # +10
            has_image_and_variant_coverage=False,       # 0
            has_expert_annotation=False,                # 0
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_PRODUCT, metrics)
        assert res.score == 60  # < 70
        assert res.mandatory_passed is True
        assert res.indexable is False
        assert res.index_tier == TIER_PROVISIONAL
        assert res.robots_meta == "noindex, follow"
        assert any("below indexability threshold" in r for r in res.reasons)

    def test_missing_mandatory_ingredients_blocks_promotion_even_above_70(self) -> None:
        # Score = 0 + 20 + 20 + 10 + 10 + 10 = 70 points, but ingredients missing!
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=False,             # 0 (Mandatory violated)
            live_offer_count=2,                         # +20
            parsed_review_count=25,                     # +20
            price_history_days=30,                      # +10
            has_image_and_variant_coverage=True,        # +10
            has_expert_annotation=True,                 # +10
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_PRODUCT, metrics)
        assert res.score == 70
        assert res.mandatory_passed is False
        assert res.indexable is False
        assert res.index_tier == TIER_PROVISIONAL
        assert res.robots_meta == "noindex, follow"
        assert any("Missing full parsed ingredient list" in r for r in res.reasons)

    def test_product_archetype_requires_two_live_offers(self) -> None:
        # Score = 30 + 0 + 20 + 10 + 10 + 10 = 80, but only 1 live offer for /p/
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,              # +30
            live_offer_count=1,                         # 0 (< 2, mandatory for /p/)
            parsed_review_count=20,                     # +20
            price_history_days=35,                      # +10
            has_image_and_variant_coverage=True,        # +10
            has_expert_annotation=True,                 # +10
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_PRODUCT, metrics)
        assert res.score == 80
        assert res.mandatory_passed is False
        assert res.indexable is False
        assert res.index_tier == TIER_PROVISIONAL
        assert res.robots_meta == "noindex, follow"
        assert any("Fewer than 2 live offers" in r for r in res.reasons)

    def test_ingredient_archetype_requires_expert_annotation(self) -> None:
        # Score = 30 + 20 + 20 + 10 + 0 = 80, but missing expert review
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,              # +30
            live_offer_count=2,                         # +20
            parsed_review_count=20,                     # +20
            price_history_days=30,                      # +10
            has_image_and_variant_coverage=False,
            has_expert_annotation=False,                # 0 (mandatory for /ingredient/ and /best/)
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_INGREDIENT, metrics)
        assert res.score == 80
        assert res.mandatory_passed is False
        assert res.indexable is False
        assert res.index_tier == TIER_PROVISIONAL
        assert res.robots_meta == "noindex, follow"
        assert any("Missing named expert/editorial annotation" in r for r in res.reasons)

    def test_best_archetype_requires_expert_annotation(self) -> None:
        metrics = DCSRubricMetrics(
            has_full_ingredient_list=True,
            live_offer_count=2,
            parsed_review_count=20,
            price_history_days=30,
            has_image_and_variant_coverage=False,
            has_expert_annotation=False,
        )
        res = DCSEvaluator.calculate_score(ARCHETYPE_BEST, metrics)
        assert res.indexable is False
        assert res.robots_meta == "noindex, follow"


class TestDCSEvaluatorAsyncLifecycle:
    async def test_evaluate_product_promotes_index_tier(self) -> None:
        prod_id = uuid.uuid4()
        prod = Product(
            id=prod_id,
            brand_id=uuid.uuid4(),
            name="10% Niacinamide Serum",
            slug="10-niacinamide-serum",
            category_id="serum",
            dcs_score=0,
            index_tier="provisional",
        )

        session = AsyncMock()
        session.get.return_value = prod

        evaluator = DCSEvaluator(session)
        evaluator.gather_product_metrics = AsyncMock(return_value=DCSRubricMetrics(
            has_full_ingredient_list=True,
            live_offer_count=3,
            parsed_review_count=20,
            price_history_days=35,
            has_image_and_variant_coverage=True,
            has_expert_annotation=False,
        ))

        res = await evaluator.evaluate_product(prod_id)

        assert res.score == 90
        assert prod.dcs_score == 90
        assert prod.index_tier == TIER_INDEXED
        session.flush.assert_called_once()

    async def test_evaluate_page_sets_page_and_product_promotion(self) -> None:
        prod_id = uuid.uuid4()
        prod = Product(
            id=prod_id,
            brand_id=uuid.uuid4(),
            name="10% Niacinamide Serum",
            slug="10-niacinamide-serum",
            category_id="serum",
            dcs_score=0,
            index_tier="provisional",
        )

        page_id = uuid.uuid4()
        page = Page(
            id=page_id,
            archetype=ARCHETYPE_PRODUCT,
            url="/p/minimalist/niacinamide-10",
            locale="en-in",
            entity_refs=[prod_id],
            dcs_score=0,
            indexable=False,
            first_indexed_at=None,
        )

        session = AsyncMock()
        # Mock session.get to return page on first call, product on second call
        session.get.side_effect = [page, prod]

        evaluator = DCSEvaluator(session)
        evaluator.gather_product_metrics = AsyncMock(return_value=DCSRubricMetrics(
            has_full_ingredient_list=True,
            live_offer_count=2,
            parsed_review_count=20,
            price_history_days=30,
            has_image_and_variant_coverage=True,
            has_expert_annotation=True,
        ))

        evaluated_page, res = await evaluator.evaluate_page(page_id)

        assert evaluated_page.dcs_score == 100
        assert evaluated_page.indexable is True
        assert evaluated_page.first_indexed_at is not None
        assert prod.dcs_score == 100
        assert prod.index_tier == TIER_INDEXED

    async def test_first_indexed_at_preserved_on_subsequent_evaluations(self) -> None:
        page_id = uuid.uuid4()
        initial_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        page = Page(
            id=page_id,
            archetype=ARCHETYPE_PRODUCT,
            url="/p/minimalist/niacinamide-10",
            locale="en-in",
            entity_refs=[uuid.uuid4()],
            dcs_score=80,
            indexable=True,
            first_indexed_at=initial_time,
        )

        session = AsyncMock()
        session.get.side_effect = [page, MagicMock()]

        evaluator = DCSEvaluator(session)
        evaluator.gather_product_metrics = AsyncMock(return_value=DCSRubricMetrics(
            has_full_ingredient_list=True,
            live_offer_count=3,
            parsed_review_count=20,
            price_history_days=40,
            has_image_and_variant_coverage=True,
            has_expert_annotation=True,
        ))

        evaluated_page, _ = await evaluator.evaluate_page(page_id)

        assert evaluated_page.first_indexed_at == initial_time
