"""Ingredient ORM model — normalized INCI graph node."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Ingredient(Base):
    __tablename__ = "ingredient"
    __table_args__ = (
        CheckConstraint("comedogenic BETWEEN 0 AND 5", name="ck_ingredient_comedogenic"),
        CheckConstraint("irritancy BETWEEN 0 AND 5", name="ck_ingredient_irritancy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inci_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    synonyms: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    cas_no: Mapped[str | None] = mapped_column(String(100))
    # function is a reserved word in Python — use function_ with column name override
    function_: Mapped[list[str] | None] = mapped_column(
        "function", ARRAY(String)
    )
    evidence_grade: Mapped[str | None] = mapped_column(String(10))  # A, B, C, D
    comedogenic: Mapped[int | None] = mapped_column(Integer)
    irritancy: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product_ingredients: Mapped[list["ProductIngredient"]] = relationship(  # noqa: F821
        "ProductIngredient", back_populates="ingredient"
    )

    def __repr__(self) -> str:
        return f"<Ingredient inci={self.inci_name!r}>"
