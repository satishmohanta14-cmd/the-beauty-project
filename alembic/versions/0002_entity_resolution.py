"""
Migration 0002 — Entity Resolution Infrastructure
====================================================
Changes:
  1. ``product.name_vector VECTOR(384)``
       Nullable column for pgvector ANN queries in Tier-3 entity resolution.
       Populated asynchronously by the embedding worker.
       HNSW index created for cosine similarity (ef_construction=64, m=16).

  2. ``unresolved_entity_queue`` table
       Holds feed items that could not be auto-linked (confidence < 0.85).
       Status workflow: pending → approved | rejected | auto_linked.

  NOTE: The HNSW index is created WITHOUT CONCURRENTLY so it can run inside
  the migration transaction.  For large datasets, prefer:
      CREATE INDEX CONCURRENTLY product_name_vector_hnsw ON product
      USING hnsw (name_vector vector_cosine_ops) WITH (m=16, ef_construction=64);
  executed manually during a maintenance window.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_entity_resolution"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | None = None
depends_on: str | None = None

EMBEDDING_DIMS = 384


def upgrade() -> None:
    # ── 1. Add name_vector column to product ──────────────────────────────
    op.add_column(
        "product",
        sa.Column(
            "name_vector",
            sa.Text(),
            nullable=True,
            comment=(
                "384-dim sentence embedding (all-MiniLM-L6-v2). "
                "Populated by embedding worker. Used by pgvector ANN in Tier-3 entity resolution."
            ),
        ),
    )

    # Retype from TEXT to VECTOR so pgvector operators work
    op.execute(
        f"ALTER TABLE product ALTER COLUMN name_vector TYPE vector({EMBEDDING_DIMS}) "
        f"USING name_vector::vector({EMBEDDING_DIMS})"
    )

    # HNSW index — cosine distance (best for normalised sentence embeddings)
    op.execute(
        "CREATE INDEX product_name_vector_hnsw "
        "ON product USING hnsw (name_vector vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # ── 2. Create unresolved_entity_queue ────────────────────────────────
    op.create_table(
        "unresolved_entity_queue",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Raw feed snapshot
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_sku", sa.String(255), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=False),
        sa.Column("raw_size", sa.String(100), nullable=False),
        sa.Column("size_ml", sa.Numeric(8, 2)),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("in_stock", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column("gtin", sa.String(50)),
        # Best resolution candidate
        sa.Column("candidate_variant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("candidate_product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("candidate_confidence", sa.Numeric(5, 4)),
        sa.Column("resolution_tier", sa.String(20)),
        sa.Column("resolution_method", sa.String(100)),
        # Admin workflow
        sa.Column("status", sa.String(50), server_default="pending", nullable=False),
        sa.Column("resolved_variant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # FK constraints
        sa.ForeignKeyConstraint(["retailer_id"], ["retailer.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["candidate_variant_id"], ["variant.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_product_id"], ["product.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resolved_variant_id"], ["variant.id"], ondelete="SET NULL"
        ),
        # Check constraints
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'auto_linked')",
            name="ck_ueq_status",
        ),
        sa.CheckConstraint(
            "resolution_tier IN ('tier1', 'tier2', 'tier3', 'no_match')",
            name="ck_ueq_resolution_tier",
        ),
    )

    # Indexes for queue management
    op.create_index("ix_ueq_status", "unresolved_entity_queue", ["status"])
    op.create_index(
        "ix_ueq_retailer_status",
        "unresolved_entity_queue",
        ["retailer_id", "status"],
    )
    op.create_index(
        "ix_ueq_created_at", "unresolved_entity_queue", ["created_at"]
    )
    op.create_index(
        "ix_ueq_candidate_variant",
        "unresolved_entity_queue",
        ["candidate_variant_id"],
    )


def downgrade() -> None:
    op.drop_table("unresolved_entity_queue")
    op.execute("DROP INDEX IF EXISTS product_name_vector_hnsw")
    op.drop_column("product", "name_vector")
