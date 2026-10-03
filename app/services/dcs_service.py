"""
Data Completeness Score (DCS) & Indexability Gate Service
=========================================================

Architecture Principle (gemini.md §3)
--------------------------------------
Every programmatic page has a calculated Data Completeness Score (DCS).
Pages with DCS < 70 (or failing mandatory criteria) MUST be tagged
`noindex, follow` in sitemaps and API metadata responses.

Scoring Rubric
--------------
- Full parsed ingredient list:               +30 pts (Mandatory for all archetypes)
- >= 2 live retailer offers:                  +20 pts (Mandatory for `/p/` archetype)
- >= 15 structured skin-profile reviews:      +20 pts
- >= 30 days of recorded price history:       +10 pts
- Media & variant coverage:                   +10 pts
- Expert / Chemist review annotation:         +10 pts (Mandatory for `/ingredient/` and `/best/`)

Total Possible: 100 points
Indexability Threshold: >= 70 points AND all archetype-specific mandatory criteria satisfied.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.variant import Variant

logger = logging.getLogger(__name__)

DCS_INDEX_THRESHOLD = 70

# Archetype constants
ARCHETYPE_PRODUCT = "product"         # e.g., /p/[brand]/[slug]
ARCHETYPE_INGREDIENT = "ingredient"   # e.g., /ingredient/[inci]
ARCHETYPE_BEST = "best"               # e.g., /best/niacinamide-serums
ARCHETYPE_DUPE = "dupe"               # e.g., /dupe/[slug]
ARCHETYPE_VS = "vs"                   # e.g., /vs/[slug-a]-vs-[slug-b]
ARCHETYPE_CONFLICT = "conflict"       # e.g., /conflict/[inci-a]-and-[inci-b]
ARCHETYPE_UNDER = "under"             # e.g., /under/500-rs


@dataclass
class DCSBreakdown:
    has_full_ingredient_list: bool = False
    live_offer_count: int = 0
    review_count: int = 0
    price_history_days: int = 0
    has_media_and_variants: bool = False
    has_expert_review: bool = False

    score: int = 0
    mandatory_passed: bool = False
    indexable: bool = False
    robots_meta: str = "noindex, follow"
    reasons: list[str] = field(default_factory=list)


class DCSService:
    """Service to evaluate page readiness, calculate DCS scores, and determine indexability."""

    def __init__(self, session: "AsyncSession") -> None:
        self.session = session

    @staticmethod
    def calculate_score(
        archetype: str,
        breakdown: DCSBreakdown,
    ) -> DCSBreakdown:
        """
        Pure calculation of DCS score and gate validation based on rubric.
        Archetype-specific mandatory requirements:
          - Mandatory for all: Full parsed ingredient list (+30).
          - Mandatory for `/p/` (product): >= 2 live retailer offers (+20).
          - Mandatory for `/ingredient/` and `/best/`: Expert / Chemist review (+10).
        """
        score = 0
        reasons: list[str] = []
        mandatory_passed = True

        # 1. Full parsed ingredient list: +30 pts (Mandatory)
        if breakdown.has_full_ingredient_list:
            score += 30
        else:
            mandatory_passed = False
            reasons.append("Missing full parsed ingredient list (Mandatory: 30 pts)")

        # 2. >= 2 live retailer offers: +20 pts (Mandatory for product /p/ pages)
        if breakdown.live_offer_count >= 2:
            score += 20
        else:
            if archetype in (ARCHETYPE_PRODUCT, "p"):
                mandatory_passed = False
                reasons.append(
                    f"Fewer than 2 live offers (found {breakdown.live_offer_count}, Mandatory for product: 20 pts)"
                )

        # 3. >= 15 structured skin-profile reviews: +20 pts
        if breakdown.review_count >= 15:
            score += 20

        # 4. >= 30 days of recorded price history: +10 pts
        if breakdown.price_history_days >= 30:
            score += 10

        # 5. Media & variant coverage: +10 pts
        if breakdown.has_media_and_variants:
            score += 10

        # 6. Expert / Chemist review annotation: +10 pts (Mandatory for /ingredient/ & /best/)
        if breakdown.has_expert_review:
            score += 10
        else:
            if archetype in (ARCHETYPE_INGREDIENT, ARCHETYPE_BEST):
                mandatory_passed = False
                reasons.append("Missing expert/chemist annotation (Mandatory for archetype: 10 pts)")

        breakdown.score = score
        breakdown.mandatory_passed = mandatory_passed

        # Indexability Gate: Threshold >= 70 AND mandatory criteria met
        if score >= DCS_INDEX_THRESHOLD and mandatory_passed:
            breakdown.indexable = True
            breakdown.robots_meta = "index, follow"
        else:
            breakdown.indexable = False
            breakdown.robots_meta = "noindex, follow"
            if score < DCS_INDEX_THRESHOLD:
                reasons.append(f"Score {score} is below indexability threshold {DCS_INDEX_THRESHOLD}")

        breakdown.reasons = reasons
        return breakdown

    async def evaluate_page(self, page_id: uuid.UUID) -> tuple[Page, DCSBreakdown]:
        """Fetch page by ID, query associated entity metrics, evaluate DCS, and persist state."""
        page = await self.session.get(Page, page_id)
        if not page:
            raise ValueError(f"Page {page_id} not found")

        breakdown = await self._gather_metrics(page)
        self.calculate_score(page.archetype, breakdown)

        # Update page state
        page.dcs_score = breakdown.score
        previously_indexable = page.indexable
        page.indexable = breakdown.indexable

        # Set first_indexed_at when page first transitions to indexable
        if breakdown.indexable and not page.first_indexed_at:
            page.first_indexed_at = datetime.now(timezone.utc)

        await self.session.flush()

        logger.info(
            "Evaluated page %s (%s): DCS=%d indexable=%s (%s)",
            page.url, page.archetype, breakdown.score, breakdown.indexable, breakdown.robots_meta
        )
        return page, breakdown

    async def _gather_metrics(self, page: Page) -> DCSBreakdown:
        """Inspect entities linked to the page to compute empirical completeness metrics."""
        breakdown = DCSBreakdown()
        if not page.entity_refs:
            return breakdown

        # Primary entity (first ref)
        primary_id = page.entity_refs[0]

        if page.archetype in (ARCHETYPE_PRODUCT, "p", ARCHETYPE_DUPE):
            # Check ingredients
            ing_stmt = (
                select(func.count(ProductIngredient.id))
                .where(ProductIngredient.product_id == primary_id)
            )
            ing_count = (await self.session.execute(ing_stmt)).scalar() or 0
            breakdown.has_full_ingredient_list = ing_count > 0

            # Check live offers & price history
            now = datetime.now(timezone.utc)
            offer_stmt = (
                select(
                    func.count(Offer.id.distinct()).label("offer_count"),
                    func.min(Offer.seen_at).label("first_seen"),
                    func.max(Offer.seen_at).label("latest_seen"),
                )
                .join(Variant, Offer.variant_id == Variant.id)
                .where(Variant.product_id == primary_id, Offer.in_stock.is_(True))
            )
            offer_res = (await self.session.execute(offer_stmt)).one()
            breakdown.live_offer_count = offer_res.offer_count or 0

            if offer_res.first_seen and offer_res.latest_seen:
                days = (offer_res.latest_seen - offer_res.first_seen).days
                breakdown.price_history_days = max(0, days)

            # Check variant coverage
            var_stmt = select(func.count(Variant.id)).where(Variant.product_id == primary_id)
            var_count = (await self.session.execute(var_stmt)).scalar() or 0
            breakdown.has_media_and_variants = var_count >= 1

        elif page.archetype in (ARCHETYPE_INGREDIENT, ARCHETYPE_BEST):
            # For ingredients, ingredient definition itself is mandatory
            breakdown.has_full_ingredient_list = True

        return breakdown
