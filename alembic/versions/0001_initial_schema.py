"""
Initial Alembic migration — create all core tables.

Revision: 0001
Tables created:
  brand, ingredient, product, variant, product_ingredient,
  retailer, offer, dupe_edge, page

Special DDL:
  - pgvector extension CREATE (idempotent)
  - Composite descending index on offer(variant_id, seen_at DESC)
  - Append-only trigger on offer table (blocks UPDATE at DB level)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ── brand ────────────────────────────────────────────────────────────────
    op.create_table(
        "brand",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100)),
        sa.Column("parent_company", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_brand_slug", "brand", ["slug"])

    # ── ingredient ───────────────────────────────────────────────────────────
    op.create_table(
        "ingredient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("inci_name", sa.String(255), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("synonyms", postgresql.ARRAY(sa.String())),
        sa.Column("cas_no", sa.String(100)),
        sa.Column("function", postgresql.ARRAY(sa.String())),
        sa.Column("evidence_grade", sa.String(10)),
        sa.Column("comedogenic", sa.Integer(),
                  sa.CheckConstraint("comedogenic BETWEEN 0 AND 5",
                                     name="ck_ingredient_comedogenic")),
        sa.Column("irritancy", sa.Integer(),
                  sa.CheckConstraint("irritancy BETWEEN 0 AND 5",
                                     name="ck_ingredient_irritancy")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_unique_constraint("uq_ingredient_inci_name", "ingredient", ["inci_name"])

    # ── product ──────────────────────────────────────────────────────────────
    op.create_table(
        "product",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("category_id", sa.String(100), nullable=False),
        sa.Column("format", sa.String(100)),
        sa.Column("claims", postgresql.ARRAY(sa.String())),
        sa.Column("markets", postgresql.ARRAY(sa.String(10)),
                  server_default=sa.text("'{IN}'"), nullable=False),
        sa.Column("dcs_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_tier", sa.String(50), server_default="provisional", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"], ondelete="CASCADE"),
    )
    op.create_unique_constraint("uq_product_slug", "product", ["slug"])
    op.create_index("ix_product_brand_id", "product", ["brand_id"])
    op.create_index("ix_product_markets", "product", ["markets"],
                    postgresql_using="gin")

    # ── variant ──────────────────────────────────────────────────────────────
    op.create_table(
        "variant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("size_ml", sa.Numeric(8, 2), nullable=False),
        sa.Column("shade_name", sa.String(100)),
        sa.Column("gtin", sa.String(50)),
        sa.Column("mrp", sa.Numeric(10, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_variant_product_id", "variant", ["product_id"])
    op.create_index("ix_variant_gtin", "variant", ["gtin"])

    # ── product_ingredient ───────────────────────────────────────────────────
    op.create_table(
        "product_ingredient",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingredient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredient.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "position", name="uq_product_ingredient_position"),
    )
    op.create_index("ix_product_ingredient_product_id", "product_ingredient", ["product_id"])
    op.create_index("ix_product_ingredient_ingredient_id", "product_ingredient", ["ingredient_id"])

    # ── retailer ─────────────────────────────────────────────────────────────
    op.create_table(
        "retailer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("affiliate_network", sa.String(100)),
        sa.Column("commission_rate", sa.Numeric(5, 2)),
        sa.Column("feed_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # ── offer (append-only) ──────────────────────────────────────────────────
    op.create_table(
        "offer",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("retailer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("in_stock", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("affiliate_url", sa.Text(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["variant_id"], ["variant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["retailer_id"], ["retailer.id"], ondelete="CASCADE"),
    )
    # PRIMARY index: latest price per variant (DESC keeps newest rows hot)
    op.execute(
        "CREATE INDEX ix_offer_variant_seen_at "
        "ON offer (variant_id, seen_at DESC)"
    )
    op.create_index("ix_offer_retailer_seen_at", "offer", ["retailer_id", "seen_at"])

    # ── Append-only guard trigger on `offer` ─────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_offer_no_update()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION
                'offer table is append-only. Updates are forbidden. '
                'Insert a new row with current seen_at instead.';
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER trg_offer_no_update
        BEFORE UPDATE ON offer
        FOR EACH ROW EXECUTE FUNCTION fn_offer_no_update();
    """)

    # ── dupe_edge ─────────────────────────────────────────────────────────────
    op.create_table(
        "dupe_edge",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("product_a", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_b", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("price_delta_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("method_version", sa.String(50), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_a"], ["product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_b"], ["product.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("product_a", "product_b", "method_version",
                            name="uq_dupe_edge_ab_method"),
    )
    op.create_index("ix_dupe_edge_product_a", "dupe_edge", ["product_a"])
    op.create_index("ix_dupe_edge_product_b", "dupe_edge", ["product_b"])
    op.create_index("ix_dupe_edge_similarity", "dupe_edge", ["similarity"])

    # ── page ──────────────────────────────────────────────────────────────────
    op.create_table(
        "page",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("archetype", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column("entity_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("dcs_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("indexable", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("first_indexed_at", sa.DateTime(timezone=True)),
    )
    op.create_unique_constraint("uq_page_url", "page", ["url"])
    op.create_index("ix_page_archetype", "page", ["archetype"])
    op.create_index("ix_page_locale", "page", ["locale"])
    op.create_index("ix_page_indexable", "page", ["indexable"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("page")
    op.drop_table("dupe_edge")

    op.execute("DROP TRIGGER IF EXISTS trg_offer_no_update ON offer")
    op.execute("DROP FUNCTION IF EXISTS fn_offer_no_update()")
    op.drop_table("offer")

    op.drop_table("retailer")
    op.drop_table("product_ingredient")
    op.drop_table("variant")
    op.drop_table("product")
    op.drop_table("ingredient")
    op.drop_table("brand")
