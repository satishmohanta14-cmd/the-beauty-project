"""Product ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Product(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    brand_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category_id: Mapped[str] = mapped_column(String(100), nullable=False)
    format: Mapped[str | None] = mapped_column(String(100))  # serum, cream, gel, etc.
    claims: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    markets: Mapped[list[str]] = mapped_column(
        ARRAY(String(10)), server_default="{IN}", nullable=False
    )
    dcs_score: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    index_tier: Mapped[str] = mapped_column(
        String(50), server_default="provisional", nullable=False
    )
    # Populated asynchronously by the embedding worker (sentence-transformers all-MiniLM-L6-v2).
    # Queried by pgvector <=> cosine operator in Tier-3 entity resolution.
    # NULL until the embedding worker has processed this product.
    name_vector: Mapped[list[float] | None] = mapped_column(
        Vector(384), nullable=True
    )
    # Weighted INCI composition vector (3000 dims = full ingredient vocab).
    # Built by DupeEngineService using position-decay × active-boost weights.
    # Used for pgvector cosine ANN to find formulation dupes.
    formula_vector: Mapped[list[float] | None] = mapped_column(
        Vector(3000), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="products")  # noqa: F821
    variants: Mapped[list["Variant"]] = relationship(  # noqa: F821
        "Variant", back_populates="product", cascade="all, delete-orphan"
    )
    product_ingredients: Mapped[list["ProductIngredient"]] = relationship(  # noqa: F821
        "ProductIngredient",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductIngredient.position",
    )
    dupe_edges_a: Mapped[list["DupeEdge"]] = relationship(  # noqa: F821
        "DupeEdge",
        foreign_keys="DupeEdge.product_a",
        back_populates="product_a_rel",
        cascade="all, delete-orphan",
    )
    dupe_edges_b: Mapped[list["DupeEdge"]] = relationship(  # noqa: F821
        "DupeEdge",
        foreign_keys="DupeEdge.product_b",
        back_populates="product_b_rel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} slug={self.slug!r}>"
