"""
Migration 0004 — Click Telemetry
================================
Creates click_telemetry table for affiliate redirection tracking and analytics.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_click_telemetry"
down_revision: str | None = "0003_formula_vector"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "click_telemetry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("offer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "clicked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(["offer_id"], ["offer.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_click_telemetry_offer_id", "click_telemetry", ["offer_id"])
    op.create_index("ix_click_telemetry_clicked_at", "click_telemetry", ["clicked_at"])


def downgrade() -> None:
    op.drop_table("click_telemetry")
