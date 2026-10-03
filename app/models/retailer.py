"""Retailer ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Retailer(Base):
    __tablename__ = "retailer"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # market: ISO country code — IN, US, UK, etc.
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    affiliate_network: Mapped[str | None] = mapped_column(String(100))
    commission_rate: Mapped[float | None] = mapped_column(Numeric(5, 2))
    feed_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    offers: Mapped[list["Offer"]] = relationship(  # noqa: F821
        "Offer", back_populates="retailer"
    )

    def __repr__(self) -> str:
        return f"<Retailer id={self.id} name={self.name!r} market={self.market!r}>"
