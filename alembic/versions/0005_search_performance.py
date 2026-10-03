"""
Migration 0005 — Search Performance
===================================
Creates search_performance table to store daily Google Search Console performance data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_search_performance"
down_revision: str | None = "0004_click_telemetry"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "search_performance",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("archetype", sa.String(50), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("impressions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ctr", sa.Numeric(6, 4), server_default="0.0", nullable=False),
        sa.Column("position", sa.Numeric(6, 2), server_default="0.0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["page_id"], ["page.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("url", "date", name="uq_search_performance_url_date"),
    )
    op.create_index("ix_search_performance_date", "search_performance", ["date"])
    op.create_index(
        "ix_search_performance_archetype_date",
        "search_performance",
        ["archetype", "date"],
    )
    op.create_index("ix_search_performance_page_id", "search_performance", ["page_id"])


def downgrade() -> None:
    op.drop_table("search_performance")
