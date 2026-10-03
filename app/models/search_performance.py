"""
SearchPerformance ORM model.
Stores daily Google Search Console performance data mapped to programmatic pages.
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SearchPerformance(Base):
    __tablename__ = "search_performance"
    __table_args__ = (
        UniqueConstraint("url", "date", name="uq_search_performance_url_date"),
        Index("ix_search_performance_date", "date"),
        Index("ix_search_performance_archetype_date", "archetype", "date"),
        Index("ix_search_performance_page_id", "page_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("page.id", ondelete="SET NULL"),
        nullable=True,
    )
    archetype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    ctr: Mapped[float] = mapped_column(Numeric(6, 4), server_default="0.0", nullable=False)
    position: Mapped[float] = mapped_column(Numeric(6, 2), server_default="0.0", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    page: Mapped["Page"] = relationship("Page")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<SearchPerformance url={self.url!r} date={self.date} "
            f"clicks={self.clicks} imps={self.impressions}>"
        )
