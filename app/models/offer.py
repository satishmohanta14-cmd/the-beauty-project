"""
Offer ORM model — APPEND-ONLY price observation ledger.

ARCHITECTURE INVARIANT: Never call session.execute(update(Offer)...) or any
ORM update on this model. Every price snapshot from a retailer scrape or
affiliate feed import MUST be a fresh INSERT with the current `seen_at`
timestamp. This table is the authoritative source for price history analytics.

The model deliberately omits any SQLAlchemy `onupdate` hook to signal intent.
A database-level trigger (defined in the Alembic migration) will RAISE an
exception if any UPDATE is attempted against this table.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Offer(Base):
    __tablename__ = "offer"
    __table_args__ = (
        # Fast historical price lookups: latest offer per variant
        Index("ix_offer_variant_seen_at", "variant_id", "seen_at"),
        # Secondary index for retailer-scoped queries
        Index("ix_offer_retailer_seen_at", "retailer_id", "seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("variant.id", ondelete="CASCADE"),
        nullable=False,
    )
    retailer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("retailer.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    affiliate_url: Mapped[str] = mapped_column(Text, nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    variant: Mapped["Variant"] = relationship("Variant", back_populates="offers")  # noqa: F821
    retailer: Mapped["Retailer"] = relationship("Retailer", back_populates="offers")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<Offer id={self.id} variant={self.variant_id} "
            f"price={self.price} {self.currency} seen_at={self.seen_at}>"
        )
