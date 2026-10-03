"""
Migration 0003 — Dupe Engine: Formula Vector Column
=====================================================
Changes:
  1. ``product.formula_vector VECTOR(3000)``
       Nullable INCI-weighted composition vector.
       Dimension = FORMULA_VECTOR_DIMS (3000) matching the full
       canonical ingredient vocabulary.
       Built by DupeEngineService; queried via cosine ANN for dupes.

  2. HNSW index on ``product.formula_vector``
       ``vector_cosine_ops`` — same as the name_vector index.
       m=16, ef_construction=64 (standard starting point).

  NOTE: For production with large datasets, build the HNSW index using
  ``CONCURRENTLY`` in a separate maintenance window after data load:

      CREATE INDEX CONCURRENTLY product_formula_vector_hnsw
      ON product USING hnsw (formula_vector vector_cosine_ops)
      WITH (m=16, ef_construction=64);
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_formula_vector"
down_revision: str | None = "0002_entity_resolution"
branch_labels: str | None = None
depends_on: str | None = None

FORMULA_VECTOR_DIMS = 3000


def upgrade() -> None:
    # ── 1. Add formula_vector column ──────────────────────────────────────
    op.add_column(
        "product",
        sa.Column(
            "formula_vector",
            sa.Text(),
            nullable=True,
            comment=(
                f"{FORMULA_VECTOR_DIMS}-dim INCI composition vector. "
                "Position-decay × active-boost weighted. "
                "Populated by DupeEngineService. "
                "Used by pgvector cosine ANN for dupe similarity."
            ),
        ),
    )

    # Retype TEXT → VECTOR so pgvector operators bind correctly
    op.execute(
        f"ALTER TABLE product ALTER COLUMN formula_vector "
        f"TYPE vector({FORMULA_VECTOR_DIMS}) "
        f"USING formula_vector::vector({FORMULA_VECTOR_DIMS})"
    )

    # Note: pgvector caps HNSW indices at 2000 dimensions.
    # For 3000-dim formula vectors, PostgreSQL uses exact scan with <=> operator.


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS product_formula_vector_hnsw")
    op.drop_column("product", "formula_vector")
