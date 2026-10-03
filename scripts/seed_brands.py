"""
Brand Seed Script — The Beauty Project
======================================
Pre-populates Indian homegrown and international beauty brands sold in India.
Includes country of origin and parent company metadata.

Run:
  python scripts/seed_brands.py
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session
from app.models.brand import Brand

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALL_BRANDS = [
    # ── Indian / Homegrown Brands ──────────────────────────────────────────
    {
        "name": "Minimalist",
        "slug": "minimalist",
        "country": "IN",
        "parent_company": "Uprising Science Pvt Ltd",
    },
    {
        "name": "Dot & Key",
        "slug": "dot-and-key",
        "country": "IN",
        "parent_company": "Dot & Key Wellness (Nykaa)",
    },
    {
        "name": "The Derma Co",
        "slug": "the-derma-co",
        "country": "IN",
        "parent_company": "Honasa Consumer Ltd",
    },
    {
        "name": "Aqualogica",
        "slug": "aqualogica",
        "country": "IN",
        "parent_company": "Honasa Consumer Ltd",
    },
    {
        "name": "Re'equil",
        "slug": "reequil",
        "country": "IN",
        "parent_company": "Re'equil India Pvt Ltd",
    },
    {
        "name": "Mamaearth",
        "slug": "mamaearth",
        "country": "IN",
        "parent_company": "Honasa Consumer Ltd",
    },
    {
        "name": "Dr. Sheth's",
        "slug": "dr-sheths",
        "country": "IN",
        "parent_company": "Honasa Consumer Ltd",
    },
    {
        "name": "Lotus Herbals",
        "slug": "lotus-herbals",
        "country": "IN",
        "parent_company": "Lotus Herbals Color Cosmetics",
    },
    {
        "name": "Biotique",
        "slug": "biotique",
        "country": "IN",
        "parent_company": "Bio Veda Action Research Co.",
    },
    {
        "name": "Bombay Shaving Company",
        "slug": "bombay-shaving-company",
        "country": "IN",
        "parent_company": "Visage Lines Personal Care",
    },
    {
        "name": "Earth Rhythm",
        "slug": "earth-rhythm",
        "country": "IN",
        "parent_company": "Earth Rhythm Pvt Ltd",
    },
    {
        "name": "La Shield",
        "slug": "la-shield",
        "country": "IN",
        "parent_company": "Glenmark Pharmaceuticals",
    },
    {
        "name": "Suncros",
        "slug": "suncros",
        "country": "IN",
        "parent_company": "Sun Pharma Laboratories",
    },
    {
        "name": "Himalaya",
        "slug": "himalaya",
        "country": "IN",
        "parent_company": "Himalaya Global Holdings",
    },

    # ── International Brands Sold in India ─────────────────────────────────
    {
        "name": "Neutrogena",
        "slug": "neutrogena",
        "country": "US",
        "parent_company": "Kenvue (Johnson & Johnson)",
    },
    {
        "name": "La Roche-Posay",
        "slug": "la-roche-posay",
        "country": "FR",
        "parent_company": "L'Oréal",
    },
    {
        "name": "Cetaphil",
        "slug": "cetaphil",
        "country": "CH",
        "parent_company": "Galderma",
    },
    {
        "name": "Vichy",
        "slug": "vichy",
        "country": "FR",
        "parent_company": "L'Oréal",
    },
    {
        "name": "Eucerin",
        "slug": "eucerin",
        "country": "DE",
        "parent_company": "Beiersdorf",
    },
]


async def seed_brands():
    logger.info("Seeding %d Indian and International brands...", len(ALL_BRANDS))
    async with async_session() as session:
        for b in ALL_BRANDS:
            stmt = (
                pg_insert(Brand)
                .values(
                    name=b["name"],
                    slug=b["slug"],
                    country=b["country"],
                    parent_company=b["parent_company"],
                )
                .on_conflict_do_update(
                    index_elements=["slug"],
                    set_={
                        "name": b["name"],
                        "country": b["country"],
                        "parent_company": b["parent_company"],
                    },
                )
            )
            await session.execute(stmt)

        await session.commit()
        logger.info("Successfully seeded %d brands into PostgreSQL!", len(ALL_BRANDS))


if __name__ == "__main__":
    asyncio.run(seed_brands())
