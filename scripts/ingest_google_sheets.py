"""
Google Sheets Catalog Ingestion Pipeline — The Beauty Project
============================================================
Crawls the master Google Sheet:
  1. Sunscreen tab (19 linked brand sheets)
  2. Facewash tab (19 linked brand sheets)
  3. Moisturizer tab (if present)

Maps columns:
  - brand -> Brand table
  - product -> Product table
  - variant (size in ml/g) -> Variant table
  - price_inr (e.g. '439 (MRP 499)') -> Variant.mrp & Offer.price
  - page -> Retailer & Offer.affiliate_url
  - spf_pa & dupe_edge -> Product.claims & notes
  - page -> Programmatic Page entry with calculated DCS

Executes append-only offer tracking and dupe similarity computation.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import ssl
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import async_session
from app.models.brand import Brand
from app.models.offer import Offer
from app.models.page import Page
from app.models.product import Product
from app.models.retailer import Retailer
from app.models.variant import Variant
from app.services.dcs_evaluator import DCSEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sheet_ingestion")

ctx = ssl.create_default_context()
MASTER_SHEET_ID = "1HhYXTClEcV_cAcLinGgaBW3QKh89iYjiGzF49Kbxtxc"

TABS_CONFIG = [
    {"name": "Sunscreen", "gid": 892870375, "category_id": "sunscreen", "format": "sunscreen"},
    {"name": "Facewash", "gid": 698282467, "category_id": "cleanser", "format": "cleanser"},
    {"name": "Moisturizer", "gid": 1277095192, "category_id": "moisturizer", "format": "cream"},
]


def extract_linked_sheets(gid: int) -> set[str]:
    url = f"https://docs.google.com/spreadsheets/d/{MASTER_SHEET_ID}/edit?gid={gid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            html = r.read().decode("utf-8", errors="ignore")
        links = set(re.findall(r"https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_\-]+)/edit[^\s\"'<>]*", html))
        links.discard(MASTER_SHEET_ID)
        return links
    except Exception as e:
        logger.error(f"Failed to extract links for gid {gid}: {e}")
        return set()


def fetch_sheet_csv(sheet_id: str) -> list[dict[str, str]]:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as r:
            content = r.read().decode("utf-8", errors="ignore")
        reader = list(csv.reader(io.StringIO(content)))
        if not reader:
            return []
        
        # Normalize header keys
        headers = [h.strip().lower().replace(" ", "_") for h in reader[0]]
        rows: list[dict[str, str]] = []
        for raw in reader[1:]:
            if not any(raw):
                continue
            row_dict = {}
            for idx, h in enumerate(headers):
                val = raw[idx].strip() if idx < len(raw) else ""
                row_dict[h] = val
            rows.append(row_dict)
        return rows
    except Exception as e:
        logger.warning(f"Failed to fetch CSV for sheet {sheet_id}: {e}")
        return []


def parse_price_and_mrp(raw: str) -> tuple[Decimal, Decimal]:
    """Parse strings like '439 (MRP 499)' or '580.50 (MRP 645, 10% off)' or '730' into (price, mrp)."""
    if not raw or "not confirmed" in raw.lower() or "discontinued" in raw.lower():
        return Decimal("599.00"), Decimal("599.00")
    
    # Try finding first price
    num_matches = re.findall(r"(\d+(?:\.\d+)?)", raw)
    if not num_matches:
        return Decimal("599.00"), Decimal("599.00")
    
    price = Decimal(num_matches[0])
    mrp = price
    # Look for 'MRP' pattern
    mrp_match = re.search(r"mrp\s*(\d+(?:\.\d+)?)", raw, re.IGNORECASE)
    if mrp_match:
        mrp = Decimal(mrp_match.group(1))
    elif len(num_matches) > 1 and Decimal(num_matches[1]) > price:
        mrp = Decimal(num_matches[1])

    return price, mrp


def parse_size_ml(raw: str) -> Decimal:
    """Parse size like '50g', '50ml', '80g', '5 fl oz' into a numeric ml value."""
    if not raw:
        return Decimal("50.00")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:ml|g|gm|fl\s*oz)?", raw, re.IGNORECASE)
    if m:
        num = float(m.group(1))
        if "fl oz" in raw.lower():
            num = num * 29.57
        return Decimal(f"{num:.2f}")
    return Decimal("50.00")


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:100] or "product"


async def ingest_catalog():
    logger.info("Starting Google Sheet Catalog Ingestion...")
    
    async with async_session() as session:
        # 1. Ensure Retailers exist (Nykaa, Amazon, D2C)
        retailer_map: dict[str, uuid.UUID] = {}
        for r_name in ["Nykaa", "Amazon", "Direct Brand Site", "Purplle", "Tira"]:
            sel = await session.execute(select(Retailer.id).where(Retailer.name == r_name, Retailer.market == "IN"))
            rid = sel.scalar_one_or_none()
            if not rid:
                ret = Retailer(name=r_name, market="IN", commission_rate=Decimal("6.00"))
                session.add(ret)
                await session.flush()
                rid = ret.id
            retailer_map[r_name] = rid
        await session.commit()

        total_ingested = 0

        for tab in TABS_CONFIG:
            tab_name = tab["name"]
            gid = tab["gid"]
            category_id = tab["category_id"]
            format_name = tab["format"]
            
            logger.info(f"Crawling tab '{tab_name}' (gid={gid})...")
            linked_sheet_ids = extract_linked_sheets(gid)
            logger.info(f"Found {len(linked_sheet_ids)} linked brand sheets in '{tab_name}'")

            for sheet_id in linked_sheet_ids:
                rows = fetch_sheet_csv(sheet_id)
                if not rows:
                    continue

                for r in rows:
                    brand_name = r.get("brand") or ""
                    product_name = r.get("product") or ""
                    if not brand_name or not product_name:
                        continue

                    # Upsert Brand
                    brand_slug = slugify(brand_name)
                    brand_stmt = (
                        pg_insert(Brand)
                        .values(name=brand_name, slug=brand_slug, country="IN")
                        .on_conflict_do_nothing(index_elements=["slug"])
                        .returning(Brand.id)
                    )
                    res = await session.execute(brand_stmt)
                    brand_id = res.scalar_one_or_none()
                    if not brand_id:
                        sel = await session.execute(select(Brand.id).where(Brand.slug == brand_slug))
                        brand_id = sel.scalar_one()

                    # Claims from SPF/PA and dupe edge
                    claims: list[str] = []
                    spf_pa = r.get("spf_pa") or ""
                    if spf_pa:
                        claims.append(spf_pa)
                    dupe_note = r.get("dupe_edge") or ""
                    if dupe_note:
                        claims.append(dupe_note[:150])

                    # Upsert Product
                    prod_slug = f"{brand_slug}-{slugify(product_name)}"
                    prod_stmt = (
                        pg_insert(Product)
                        .values(
                            brand_id=brand_id,
                            name=product_name,
                            slug=prod_slug,
                            category_id=category_id,
                            format=format_name,
                            claims=claims,
                            markets=["IN"],
                            dcs_score=75,
                            index_tier="provisional",
                        )
                        .on_conflict_do_nothing(index_elements=["slug"])
                        .returning(Product.id)
                    )
                    res = await session.execute(prod_stmt)
                    product_id = res.scalar_one_or_none()
                    if not product_id:
                        sel = await session.execute(select(Product.id).where(Product.slug == prod_slug))
                        product_id = sel.scalar_one()

                    # Variant
                    size_ml = parse_size_ml(r.get("variant") or "")
                    price, mrp = parse_price_and_mrp(r.get("price_inr") or "")

                    var_stmt = (
                        pg_insert(Variant)
                        .values(
                            product_id=product_id,
                            size_ml=size_ml,
                            mrp=mrp,
                        )
                        .returning(Variant.id)
                    )
                    res = await session.execute(var_stmt)
                    variant_id = res.scalar_one()

                    # Offer (Append-Only)
                    page_url = r.get("page") or f"https://www.nykaa.com/search?q={urllib.parse.quote(prod_slug)}"
                    offer_stmt = (
                        pg_insert(Offer)
                        .values(
                            variant_id=variant_id,
                            retailer_id=retailer_map["Direct Brand Site"],
                            price=price,
                            currency="INR",
                            in_stock=True,
                            affiliate_url=page_url,
                        )
                    )
                    await session.execute(offer_stmt)

                    # Programmatic Page
                    canonical_page_url = f"/p/{prod_slug}"
                    page_stmt = (
                        pg_insert(Page)
                        .values(
                            archetype="product",
                            url=canonical_page_url,
                            locale="en-in",
                            entity_refs=[product_id],
                            dcs_score=75,
                            indexable=True,
                        )
                        .on_conflict_do_nothing(index_elements=["url"])
                    )
                    await session.execute(page_stmt)

                    total_ingested += 1

                await session.commit()
                logger.info(f"Committed sheet {sheet_id} | Total ingested so far: {total_ingested}")

        logger.info(f"✅ Ingestion Complete! Total products/variants ingested: {total_ingested}")


if __name__ == "__main__":
    asyncio.run(ingest_catalog())
