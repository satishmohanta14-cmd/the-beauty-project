"""DupeEdge ORM model — vector similarity graph edge between two products."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DupeEdge(Base):
    __tablename__ = "dupe_edge"
    __table_args__ = (
        UniqueConstraint(
            "product_a", "product_b", "method_version",
            name="uq_dupe_edge_ab_method",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_a: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_b: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Cosine similarity in [0, 1] range
    similarity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    # Percentage price difference between the two products
    price_delta_pct: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    method_version: Mapped[str] = mapped_column(String(50), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product_a_rel: Mapped["Product"] = relationship(  # noqa: F821
        "Product",
        foreign_keys=[product_a],
        back_populates="dupe_edges_a",
    )
    product_b_rel: Mapped["Product"] = relationship(  # noqa: F821
        "Product",
        foreign_keys=[product_b],
        back_populates="dupe_edges_b",
    )

    def __repr__(self) -> str:
        return (
            f"<DupeEdge a={self.product_a} b={self.product_b} "
            f"sim={self.similarity} v={self.method_version!r}>"
        )
