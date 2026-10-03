"""
ProductIngredient ORM model.

ARCHITECTURE NOTE: `position` is MANDATORY and represents descending
concentration order from the INCI label. It directly weights dupe vector
calculations and skin-fit scoring. Never insert without a position value.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ProductIngredient(Base):
    __tablename__ = "product_ingredient"
    __table_args__ = (
        UniqueConstraint("product_id", "position", name="uq_product_ingredient_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingredient.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Mandatory: 1-based descending concentration rank from INCI label
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship(  # noqa: F821
        "Product", back_populates="product_ingredients"
    )
    ingredient: Mapped["Ingredient"] = relationship(  # noqa: F821
        "Ingredient", back_populates="product_ingredients"
    )

    def __repr__(self) -> str:
        return (
            f"<ProductIngredient product={self.product_id} "
            f"ingredient={self.ingredient_id} pos={self.position}>"
        )
