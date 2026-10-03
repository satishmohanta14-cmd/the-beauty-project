"""
Data Completeness Score (DCS) Evaluator & Promotion Engine
==========================================================

Architecture Invariant (gemini.md §3)
-------------------------------------
Every programmatic page has a calculated Data Completeness Score (DCS).
- Score Threshold: DCS >= 70 AND all archetype-specific mandatory criteria satisfied.
- Promotion:
    * When DCS >= 70:
        `page.indexable = true`
        `product.index_tier = 'indexed'`
        `robots_meta = 'index, follow'`
    * When DCS < 70 (or mandatory criteria failed):
        `page.indexable = false`
        `product.index_tier = 'provisional'`
        `robots_meta = 'noindex, follow'`

Scoring Rubric (gemini.md §3):
------------------------------
1. Full parsed ingredient list:           +30 pts (Mandatory for all)
2. >= 2 live retailer offers:              +20 pts (Mandatory for product pages `/p/`)
3. >= 15 parsed reviews:                   +20 pts
4. >= 30 days of price history records:   +10 pts
5. Image and variant coverage:             +10 pts
6. Named expert/editorial annotation:      +10 pts (Mandatory for `/ingredient/` and `/best/`)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select, update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.variant import Variant

logger = logging.getLogger(__name__)

DCS_INDEX_THRESHOLD: int = 70

# Archetype constants
ARCHETYPE_PRODUCT = "product"         # /p/
ARCHETYPE_INGREDIENT = "ingredient"   # /ingredient/
ARCHETYPE_BEST = "best"               # /best/
ARCHETYPE_DUPE = "dupe"               # /dupe/
ARCHETYPE_VS = "vs"                   # /vs/
ARCHETYPE_CONFLICT = "conflict"       # /conflict/
ARCHETYPE_UNDER = "under"             # /under/

TIER_INDEXED = "indexed"
TIER_PROVISIONAL = "provisional"


@dataclass
class DCSRubricMetrics:
    """Raw empirical metrics gathered for a product or page."""
    has_full_ingredient_list: bool = False
    live_offer_count: int = 0
    parsed_review_count: int = 0
    price_history_days: int = 0
    has_image_and_variant_coverage: bool = False
    has_expert_annotation: bool = False


@dataclass
class DCSScoreResult:
    """Calculated score, mandatory validation, and promotion outcome."""
    score: int = 0
    mandatory_passed: bool = False
    indexable: bool = False
    index_tier: str = TIER_PROVISIONAL
    robots_meta: str = "noindex, follow"
    reasons: list[str] = field(default_factory=list)
    metrics: DCSRubricMetrics = field(default_factory=DCSRubricMetrics)


class DCSEvaluator:
    """Evaluates DCS scores and applies promotion logic to pages and products."""

    def __init__(self, session: "AsyncSession") -> None:
        self.session = session

    @staticmethod
    def calculate_score(
        archetype: str,
        metrics: DCSRubricMetrics,
    ) -> DCSScoreResult:
        """
        Pure calculation of DCS score and mandatory requirements.

        Rubric:
        - Full parsed ingredient list (+30, mandatory)
        - >= 2 live retailer offers (+20, mandatory for product /p/ pages)
        - >= 15 parsed reviews (+20)
        - >= 30 days of price history records (+10)
        - Image and variant coverage (+10)
        - Named expert/editorial annotation (+10, mandatory for ingredient/best pages)
        """
        score = 0
        reasons: list[str] = []
        mandatory_passed = True

        # 1. Full parsed ingredient list (+30, Mandatory)
        if metrics.has_full_ingredient_list:
            score += 30
        else:
            mandatory_passed = False
            reasons.append("Missing full parsed ingredient list (+30 mandatory)")

        # 2. >= 2 live retailer offers (+20, Mandatory for product pages)
        if metrics.live_offer_count >= 2:
            score += 20
        else:
            if archetype in (ARCHETYPE_PRODUCT, "p"):
                mandatory_passed = False
                reasons.append(
                    f"Fewer than 2 live offers (found {metrics.live_offer_count}, +20 mandatory for product)"
                )

        # 3. >= 15 parsed reviews (+20)
        if metrics.parsed_review_count >= 15:
            score += 20

        # 4. >= 30 days of price history records (+10)
        if metrics.price_history_days >= 30:
            score += 10

        # 5. Image and variant coverage (+10)
        if metrics.has_image_and_variant_coverage:
            score += 10

        # 6. Named expert/editorial annotation (+10, Mandatory for /ingredient/ and /best/)
        if metrics.has_expert_annotation:
            score += 10
        else:
            if archetype in (ARCHETYPE_INGREDIENT, ARCHETYPE_BEST):
                mandatory_passed = False
                reasons.append("Missing named expert/editorial annotation (+10 mandatory for archetype)")

        # Promotion logic
        is_promoted = (score >= DCS_INDEX_THRESHOLD) and mandatory_passed
        index_tier = TIER_INDEXED if is_promoted else TIER_PROVISIONAL
        robots_meta = "index, follow" if is_promoted else "noindex, follow"

        if score < DCS_INDEX_THRESHOLD:
            reasons.append(f"DCS score ({score}) below indexability threshold ({DCS_INDEX_THRESHOLD})")

        return DCSScoreResult(
            score=score,
            mandatory_passed=mandatory_passed,
            indexable=is_promoted,
            index_tier=index_tier,
            robots_meta=robots_meta,
            reasons=reasons,
            metrics=metrics,
        )

    async def gather_product_metrics(
        self,
        product_id: uuid.UUID,
        parsed_reviews: int = 0,
        has_expert_annotation: bool = False,
    ) -> DCSRubricMetrics:
        """Gathers database metrics for a given product."""
        metrics = DCSRubricMetrics(
            parsed_review_count=parsed_reviews,
            has_expert_annotation=has_expert_annotation,
        )

        # 1. Full parsed ingredient list
        ing_stmt = select(func.count(ProductIngredient.id)).where(
            ProductIngredient.product_id == product_id
        )
        ing_count = (await self.session.execute(ing_stmt)).scalar() or 0
        metrics.has_full_ingredient_list = ing_count > 0

        # 2. Live offers & price history days
        offer_stmt = (
            select(
                func.count(Offer.id.distinct()).label("offer_count"),
                func.min(Offer.seen_at).label("first_seen"),
                func.max(Offer.seen_at).label("latest_seen"),
            )
            .join(Variant, Offer.variant_id == Variant.id)
            .where(Variant.product_id == product_id, Offer.in_stock.is_(True))
        )
        offer_res = (await self.session.execute(offer_stmt)).one()
        metrics.live_offer_count = offer_res.offer_count or 0

        if offer_res.first_seen and offer_res.latest_seen:
            days = (offer_res.latest_seen - offer_res.first_seen).days
            metrics.price_history_days = max(0, days)

        # 3. Variant and media coverage
        var_stmt = select(func.count(Variant.id)).where(Variant.product_id == product_id)
        var_count = (await self.session.execute(var_stmt)).scalar() or 0
        metrics.has_image_and_variant_coverage = var_count >= 1

        return metrics

    async def evaluate_product(
        self,
        product_id: uuid.UUID,
        parsed_reviews: int = 0,
        has_expert_annotation: bool = False,
    ) -> DCSScoreResult:
        """
        Evaluate and promote a Product directly:
        - Sets product.dcs_score
        - Sets product.index_tier = 'indexed' if DCS >= 70 and mandatory passed, else 'provisional'
        """
        product = await self.session.get(Product, product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        metrics = await self.gather_product_metrics(
            product_id,
            parsed_reviews=parsed_reviews,
            has_expert_annotation=has_expert_annotation,
        )
        result = self.calculate_score(ARCHETYPE_PRODUCT, metrics)

        product.dcs_score = result.score
        product.index_tier = result.index_tier
        await self.session.flush()

        logger.info(
            "Evaluated product %s: DCS=%d, tier=%s, reasons=%s",
            product.slug, result.score, result.index_tier, result.reasons,
        )
        return result

    async def evaluate_page(
        self,
        page_id: uuid.UUID,
        parsed_reviews: int = 0,
        has_expert_annotation: bool = False,
    ) -> tuple[Page, DCSScoreResult]:
        """
        Evaluate and promote a programmatic Page and any linked Product:
        - Sets page.dcs_score and page.indexable
        - If promoted: sets page.first_indexed_at (if unset)
        - Updates linked Product entity's index_tier and dcs_score
        """
        page = await self.session.get(Page, page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        # Collect metrics depending on archetype and entity_refs
        metrics = DCSRubricMetrics(
            parsed_review_count=parsed_reviews,
            has_expert_annotation=has_expert_annotation,
        )

        primary_product_id: uuid.UUID | None = None
        if page.entity_refs:
            primary_product_id = page.entity_refs[0]

        if page.archetype in (ARCHETYPE_PRODUCT, "p", ARCHETYPE_DUPE, ARCHETYPE_VS, ARCHETYPE_UNDER):
            if primary_product_id:
                metrics = await self.gather_product_metrics(
                    primary_product_id,
                    parsed_reviews=parsed_reviews,
                    has_expert_annotation=has_expert_annotation,
                )
        elif page.archetype in (ARCHETYPE_INGREDIENT, ARCHETYPE_BEST):
            # Ingredient pages have canonical INCI definitions
            metrics.has_full_ingredient_list = True

        result = self.calculate_score(page.archetype, metrics)

        page.dcs_score = result.score
        page.indexable = result.indexable

        # Lifecycle tracking
        if result.indexable and not page.first_indexed_at:
            page.first_indexed_at = datetime.now(timezone.utc)

        # Synchronize linked Product if applicable
        if primary_product_id and page.archetype in (ARCHETYPE_PRODUCT, "p"):
            prod = await self.session.get(Product, primary_product_id)
            if prod:
                prod.dcs_score = result.score
                prod.index_tier = result.index_tier

        await self.session.flush()

        logger.info(
            "Evaluated page %s (%s): DCS=%d indexable=%s robots=%s",
            page.url, page.archetype, result.score, result.indexable, result.robots_meta,
        )
        return page, result
