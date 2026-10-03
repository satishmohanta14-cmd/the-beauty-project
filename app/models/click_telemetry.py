"""
Affiliate Click Telemetry ORM model.
Records outbound affiliate redirects (/go/{offer_id}) for analytics and attribution.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ClickTelemetry(Base):
    __tablename__ = "click_telemetry"
    __table_args__ = (
        Index("ix_click_telemetry_offer_id", "offer_id"),
        Index("ix_click_telemetry_clicked_at", "clicked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("offer.id", ondelete="CASCADE"),
        nullable=False,
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    referrer: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(String(64))

    # Relationships
    offer: Mapped["Offer"] = relationship("Offer")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ClickTelemetry id={self.id} offer_id={self.offer_id} at={self.clicked_at}>"
