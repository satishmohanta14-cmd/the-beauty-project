"""Variant ORM model — SKU-level entity."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Variant(Base):
    __tablename__ = "variant"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )
    size_ml: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    shade_name: Mapped[str | None] = mapped_column(String(100))
    gtin: Mapped[str | None] = mapped_column(String(50))  # barcode/EAN/UPC
    mrp: Mapped[float | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants")  # noqa: F821
    offers: Mapped[list["Offer"]] = relationship(  # noqa: F821
        "Offer", back_populates="variant"
    )

    def __repr__(self) -> str:
        return f"<Variant id={self.id} product_id={self.product_id} size_ml={self.size_ml}>"
