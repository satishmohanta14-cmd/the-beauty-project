"""Page ORM model — programmatic page state and DCS gate."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Page(Base):
    __tablename__ = "page"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Archetype: product | ingredient | dupe | conflict | vs | under
    archetype: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    # UUIDs of the primary entities this page surfaces (product, ingredient, etc.)
    entity_refs: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    # Data Completeness Score — computed, never manually set
    dcs_score: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    # True only when dcs_score >= 70 (enforced by DCS worker)
    indexable: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    first_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return (
            f"<Page archetype={self.archetype!r} url={self.url!r} "
            f"dcs={self.dcs_score} indexable={self.indexable}>"
        )
