"""
Catalog Seed Script — The Beauty Project
=========================================
Synchronizes the 10 flagship products from frontend/src/lib/catalog.ts into PostgreSQL:
  1. Brands (Minimalist, The Ordinary, Dot & Key, SkinCeuticals, Re'equil, La Roche-Posay, CeraVe, Drunk Elephant, Deconstruct)
  2. Products with category, format, claims, and DCS score
  3. ProductIngredient rows preserving strict INCI position order (mandatory)
  4. Variants (size_ml, mrp)
  5. Append-only Offers across Nykaa, Amazon, Tira, Sephora
  6. Dupe edges and Programmatic pages

Run:
  python scripts/seed_catalog.py
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session
from app.models.brand import Brand
from app.models.dupe_edge import DupeEdge
from app.models.ingredient import Ingredient
from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.product_ingredient import ProductIngredient
from app.models.retailer import Retailer
from app.models.variant import Variant
from app.services.dcs_evaluator import DCSEvaluator
from app.services.dupe_engine import DupeEngineService
from scripts.seed_ingredients import SEED_INGREDIENTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retailers data
RETAILERS = [
    {"name": "Nykaa", "market": "IN", "affiliate_network": "Cuelinks", "commission_rate": Decimal("7.50")},
    {"name": "Amazon", "market": "IN", "affiliate_network": "Amazon PA-API", "commission_rate": Decimal("5.00")},
    {"name": "Tira", "market": "IN", "affiliate_network": "Cuelinks", "commission_rate": Decimal("6.00")},
    {"name": "Sephora", "market": "IN", "affiliate_network": "Rakuten", "commission_rate": Decimal("8.00")},
]

# 10 Curated Products
RAW_PRODUCTS = [
    {
        "brand": "Minimalist",
        "brand_slug": "minimalist",
        "name": "Niacinamide 10% + Zinc 1% Serum",
        "slug": "minimalist-niacinamide-10",
        "category_id": "serum",
        "format": "serum",
        "claims": ["Fragrance-free", "Non-comedogenic", "Dermat tested"],
        "size_ml": Decimal("30.00"),
        "ingredients": [
            ("Water", False),
            ("Niacinamide", True),
            ("Propanediol", False),
            ("Zinc PCA", True),
            ("Glycerin", False),
            ("Xanthan Gum", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "599.00"), ("Amazon", "549.00"), ("Tira", "579.00")],
    },
    {
        "brand": "The Ordinary",
        "brand_slug": "the-ordinary",
        "name": "Niacinamide 10% + Zinc 1%",
        "slug": "the-ordinary-niacinamide-10",
        "category_id": "serum",
        "format": "serum",
        "claims": ["Vegan", "Cruelty-free"],
        "size_ml": Decimal("30.00"),
        "ingredients": [
            ("Water", False),
            ("Niacinamide", True),
            ("Propanediol", False),
            ("Zinc PCA", True),
            ("Xanthan Gum", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "1150.00"), ("Amazon", "1090.00"), ("Sephora", "1200.00"), ("Tira", "1125.00")],
    },
    {
        "brand": "Dot & Key",
        "brand_slug": "dot-and-key",
        "name": "Vitamin C + E Super Bright Serum",
        "slug": "dot-key-vitamin-c-e",
        "category_id": "serum",
        "format": "serum",
        "claims": ["Brightening", "Paraben-free"],
        "size_ml": Decimal("20.00"),
        "ingredients": [
            ("Water", False),
            ("3-O-Ethyl Ascorbic Acid", True),
            ("Propanediol", False),
            ("Glycerin", False),
            ("Tocopherol", True),
            ("Ferulic Acid", True),
            ("Sodium Hyaluronate", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "645.00"), ("Amazon", "599.00"), ("Tira", "629.00")],
    },
    {
        "brand": "SkinCeuticals",
        "brand_slug": "skinceuticals",
        "name": "C E Ferulic",
        "slug": "skinceuticals-ce-ferulic",
        "category_id": "serum",
        "format": "serum",
        "claims": ["Patented antioxidant", "Clinically tested"],
        "size_ml": Decimal("30.00"),
        "ingredients": [
            ("Water", False),
            ("Ascorbic Acid", True),
            ("Glycerin", False),
            ("Tocopherol", True),
            ("Ferulic Acid", True),
            ("Sodium Hyaluronate", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Sephora", "13900.00"), ("Nykaa", "13500.00"), ("Amazon", "12990.00")],
    },
    {
        "brand": "Re'equil",
        "brand_slug": "reequil",
        "name": "Oxybenzone & OMC Free Sunscreen SPF 50",
        "slug": "re-equil-oxybenzone-free-spf50",
        "category_id": "sunscreen",
        "format": "cream",
        "claims": ["PA+++", "No white cast", "Reef safe"],
        "size_ml": Decimal("50.00"),
        "ingredients": [
            ("Water", False),
            ("Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine", True),
            ("Diethylamino Hydroxybenzoyl Hexyl Benzoate", True),
            ("Zinc Oxide", True),
            ("Glycerin", False),
            ("Dimethicone", False),
            ("Niacinamide", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "795.00"), ("Amazon", "745.00"), ("Tira", "780.00")],
    },
    {
        "brand": "La Roche-Posay",
        "brand_slug": "la-roche-posay",
        "name": "Anthelios UVMune 400 Fluid SPF 50+",
        "slug": "la-roche-posay-anthelios-uvmune",
        "category_id": "sunscreen",
        "format": "fluid",
        "claims": ["PA++++", "Water resistant", "Fragrance-free"],
        "size_ml": Decimal("50.00"),
        "ingredients": [
            ("Water", False),
            ("Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine", True),
            ("Diethylamino Hydroxybenzoyl Hexyl Benzoate", True),
            ("Glycerin", False),
            ("Dimethicone", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "1950.00"), ("Sephora", "2100.00"), ("Amazon", "1879.00"), ("Tira", "1990.00")],
    },
    {
        "brand": "CeraVe",
        "brand_slug": "cerave",
        "name": "Moisturising Cream",
        "slug": "cerave-moisturising-cream",
        "category_id": "moisturizer",
        "format": "cream",
        "claims": ["MVE technology", "Accepted by NEA"],
        "size_ml": Decimal("50.00"),
        "ingredients": [
            ("Water", False),
            ("Glycerin", False),
            ("Cetearyl Alcohol", False),
            ("Ceramide NP", True),
            ("Cholesterol", True),
            ("Sodium Hyaluronate", False),
            ("Dimethicone", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "425.00"), ("Amazon", "399.00"), ("Tira", "415.00"), ("Sephora", "450.00")],
    },
    {
        "brand": "Minimalist",
        "brand_slug": "minimalist",
        "name": "Sepicalm 3% + Oats Moisturizer",
        "slug": "minimalist-ceramides-moisturizer",
        "category_id": "moisturizer",
        "format": "cream",
        "claims": ["Fragrance-free", "Barrier repair"],
        "size_ml": Decimal("50.00"),
        "ingredients": [
            ("Water", False),
            ("Glycerin", False),
            ("Cetearyl Alcohol", False),
            ("Ceramide NP", True),
            ("Squalane", True),
            ("Panthenol", True),
            ("Sodium Hyaluronate", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "349.00"), ("Amazon", "329.00"), ("Tira", "345.00")],
    },
    {
        "brand": "Drunk Elephant",
        "brand_slug": "drunk-elephant",
        "name": "Protini Polypeptide Cream",
        "slug": "drunk-elephant-protini",
        "category_id": "moisturizer",
        "format": "cream",
        "claims": ["Clean-compatible", "Fragrance-free"],
        "size_ml": Decimal("50.00"),
        "ingredients": [
            ("Water", False),
            ("Glycerin", False),
            ("Cetearyl Alcohol", False),
            ("Squalane", True),
            ("Panthenol", True),
            ("Dimethicone", False),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Sephora", "6100.00"), ("Nykaa", "5950.00"), ("Tira", "5990.00")],
    },
    {
        "brand": "Deconstruct",
        "brand_slug": "deconstruct",
        "name": "Bakuchiol + Peptide Night Serum",
        "slug": "deconstruct-bakuchiol-serum",
        "category_id": "serum",
        "format": "serum",
        "claims": ["Pregnancy safe", "Non-irritating"],
        "size_ml": Decimal("30.00"),
        "ingredients": [
            ("Water", False),
            ("Squalane", True),
            ("Bakuchiol", True),
            ("Glycerin", False),
            ("Tocopherol", True),
            ("Phenoxyethanol", False),
        ],
        "offers": [("Nykaa", "599.00"), ("Amazon", "569.00")],
    },
]


async def seed_catalog():
    logger.info("Starting catalog seeding...")
    async with async_session() as session:
        # 1. Seed Ingredients first if missing
        ing_name_to_id: dict[str, uuid.UUID] = {}
        for item in SEED_INGREDIENTS:
            stmt = (
                pg_insert(Ingredient)
                .values(
                    inci_name=item["inci_name"],
                    canonical_name=item["canonical_name"],
                    synonyms=item.get("synonyms", []),
                    cas_no=item.get("cas_no"),
                    function_=item.get("function", []),
                    evidence_grade=item.get("evidence_grade", "B"),
                    comedogenic=item.get("comedogenic", 0),
                    irritancy=item.get("irritancy", 0),
                )
                .on_conflict_do_nothing(index_elements=["inci_name"])
            )
            await session.execute(stmt)

        all_ings = (await session.execute(select(Ingredient.id, Ingredient.canonical_name, Ingredient.inci_name))).all()
        for r in all_ings:
            ing_name_to_id[r.canonical_name.lower()] = r.id
            ing_name_to_id[r.inci_name.lower()] = r.id

        # 2. Seed Retailers
        retailer_name_to_id: dict[str, uuid.UUID] = {}
        for ret in RETAILERS:
            existing = (await session.execute(select(Retailer).where(Retailer.name == ret["name"]))).scalar_one_or_none()
            if not existing:
                r_obj = Retailer(
                    name=ret["name"],
                    market=ret["market"],
                    affiliate_network=ret["affiliate_network"],
                    commission_rate=ret["commission_rate"],
                )
                session.add(r_obj)
                await session.flush()
                retailer_name_to_id[ret["name"]] = r_obj.id
            else:
                retailer_name_to_id[ret["name"]] = existing.id

        # 3. Seed Brands & Products
        created_products = []
        for raw in RAW_PRODUCTS:
            brand = (await session.execute(select(Brand).where(Brand.slug == raw["brand_slug"]))).scalar_one_or_none()
            if not brand:
                brand = Brand(name=raw["brand"], slug=raw["brand_slug"])
                session.add(brand)
                await session.flush()

            prod = (await session.execute(select(Product).where(Product.slug == raw["slug"]))).scalar_one_or_none()
            if not prod:
                prod = Product(
                    brand_id=brand.id,
                    name=raw["name"],
                    slug=raw["slug"],
                    category_id=raw["category_id"],
                    format=raw["format"],
                    claims=raw["claims"],
                    markets=["IN"],
                    dcs_score=85,
                    index_tier="indexed",
                )
                session.add(prod)
                await session.flush()
            created_products.append(prod)

            # 4. Seed Product Ingredients with mandatory position
            for pos, (ing_name, is_active) in enumerate(raw["ingredients"], start=1):
                ing_id = ing_name_to_id.get(ing_name.lower())
                if not ing_id:
                    # Create ingredient on the fly
                    new_ing = Ingredient(
                        inci_name=ing_name,
                        canonical_name=ing_name,
                        evidence_grade="A" if is_active else "B",
                    )
                    session.add(new_ing)
                    await session.flush()
                    ing_id = new_ing.id
                    ing_name_to_id[ing_name.lower()] = ing_id

                pi_stmt = (
                    pg_insert(ProductIngredient)
                    .values(
                        product_id=prod.id,
                        ingredient_id=ing_id,
                        position=pos,
                        is_active=is_active,
                    )
                    .on_conflict_do_nothing(index_elements=["product_id", "position"])
                )
                await session.execute(pi_stmt)

            # 5. Variant & Offers
            variant = (await session.execute(select(Variant).where(Variant.product_id == prod.id))).scalar_one_or_none()
            if not variant:
                variant = Variant(
                    product_id=prod.id,
                    size_ml=raw["size_ml"],
                    mrp=Decimal(raw["offers"][0][1]),
                )
                session.add(variant)
                await session.flush()

            for ret_name, price_str in raw["offers"]:
                ret_id = retailer_name_to_id.get(ret_name)
                if ret_id:
                    session.add(
                        Offer(
                            variant_id=variant.id,
                            retailer_id=ret_id,
                            price=Decimal(price_str),
                            currency="INR",
                            in_stock=True,
                            affiliate_url=f"https://www.{ret_name.lower()}.com/search?q={raw['slug']}",
                        )
                    )

            # 6. Page registration
            page_url = f"/p/{raw['brand_slug']}/{raw['slug']}"
            page_stmt = (
                pg_insert(Page)
                .values(
                    archetype="product",
                    url=page_url,
                    locale="en-in",
                    entity_refs=[prod.id],
                    dcs_score=85,
                    indexable=True,
                )
                .on_conflict_do_nothing(index_elements=["url"])
            )
            await session.execute(page_stmt)

        await session.commit()

        # 7. Compute Dupe vectors and Dupe edges
        logger.info("Computing formula vectors and dupe graph...")
        dupe_svc = DupeEngineService(session)
        for p in created_products:
            await dupe_svc.compute_and_store_formula_vector(p.id)
        await session.commit()

        for p in created_products:
            await dupe_svc.compute_dupes(p.id, rebuild_vector=False)
        await session.commit()

        logger.info("Successfully seeded all 10 products, variants, offers, pages, and dupe edges!")


if __name__ == "__main__":
    asyncio.run(seed_catalog())
