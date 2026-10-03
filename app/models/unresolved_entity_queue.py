"""
UnresolvedEntityQueue ORM model.

Holds retailer feed items that could not be automatically matched to a
canonical Variant (confidence < AUTO_LINK_THRESHOLD = 0.85).

Workflow
--------
1. EntityResolutionService fails to auto-link a feed item.
2. A row is inserted here with the best resolution candidate and its
   confidence score.
3. An admin reviews the queue, approves or rejects the match, and sets
   ``resolved_variant_id``.
4. A downstream worker picks up approved rows and creates the Offer.

Status values
-------------
``pending``   — awaiting admin review (default)
``approved``  — admin has confirmed the variant match
``rejected``  — admin has rejected the candidate; item discarded
``auto_linked`` — confidence was raised above threshold on re-evaluation
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_VALID_STATUSES = ("pending", "approved", "rejected", "auto_linked")
_VALID_TIERS = ("tier1", "tier2", "tier3", "no_match")


class UnresolvedEntityQueue(Base):
    __tablename__ = "unresolved_entity_queue"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_VALID_STATUSES!r}",
            name="ck_ueq_status",
        ),
        CheckConstraint(
            f"resolution_tier IN {_VALID_TIERS!r}",
            name="ck_ueq_resolution_tier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ── Raw feed item snapshot (preserved for manual review) ────────────────
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retailer.id", ondelete="CASCADE"),
        nullable=False,
    )
    retailer_sku: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_size: Mapped[str] = mapped_column(String(100), nullable=False)
    size_ml: Mapped[float | None] = mapped_column(
        Numeric(8, 2), comment="Parsed volume in ml; NULL if parsing failed."
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    gtin: Mapped[str | None] = mapped_column(String(50))

    # ── Best resolution candidate ─────────────────────────────────────────
    candidate_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variant.id", ondelete="SET NULL"),
    )
    candidate_product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="SET NULL"),
    )
    candidate_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    resolution_tier: Mapped[str | None] = mapped_column(String(20))
    resolution_method: Mapped[str | None] = mapped_column(String(100))

    # ── Admin review workflow ─────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(50), server_default="pending", nullable=False
    )
    resolved_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variant.id", ondelete="SET NULL"),
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(255))

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────
    retailer: Mapped["Retailer"] = relationship("Retailer")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<UnresolvedEntityQueue id={self.id} "
            f"sku={self.retailer_sku!r} status={self.status!r} "
            f"confidence={self.candidate_confidence}>"
        )
