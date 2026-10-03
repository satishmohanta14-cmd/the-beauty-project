"""
Seed script — pre-populate the `ingredient` table with ~30 canonical INCI entries.

Run with:
    python scripts/seed_ingredients.py

The script is idempotent: it uses INSERT ... ON CONFLICT (inci_name) DO NOTHING,
so running it multiple times is safe.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `app/` importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Seed data — 30 canonical INCI entries
# Keys: inci_name, canonical_name, synonyms, cas_no, function,
#       evidence_grade, comedogenic (0-5), irritancy (0-5)
# ---------------------------------------------------------------------------
SEED_INGREDIENTS: list[dict] = [
    {
        "inci_name": "Water",
        "canonical_name": "Water",
        "synonyms": ["Aqua", "Eau", "H2O"],
        "cas_no": "7732-18-5",
        "function": ["solvent", "humectant"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Niacinamide",
        "canonical_name": "Niacinamide",
        "synonyms": ["Vitamin B3", "Nicotinamide", "Nicotinic Acid Amide"],
        "cas_no": "98-92-0",
        "function": ["skin-brightening", "sebum-regulation", "barrier-repair"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Glycerin",
        "canonical_name": "Glycerin",
        "synonyms": ["Glycerol", "Glycerine", "1,2,3-Propanetriol"],
        "cas_no": "56-81-5",
        "function": ["humectant", "solvent", "skin-conditioning"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Retinol",
        "canonical_name": "Retinol",
        "synonyms": ["Vitamin A", "All-trans-retinol", "Vitamin A1"],
        "cas_no": "68-26-8",
        "function": ["anti-aging", "cell-turnover", "skin-conditioning"],
        "evidence_grade": "A",
        "comedogenic": 2,
        "irritancy": 3,
    },
    {
        "inci_name": "Salicylic Acid",
        "canonical_name": "Salicylic Acid",
        "synonyms": ["BHA", "Beta Hydroxy Acid", "2-Hydroxybenzoic Acid"],
        "cas_no": "69-72-7",
        "function": ["exfoliant", "anti-acne", "keratolytic", "preservative"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 2,
    },
    {
        "inci_name": "Ascorbic Acid",
        "canonical_name": "Ascorbic Acid",
        "synonyms": ["Vitamin C", "L-Ascorbic Acid", "Ascorbate"],
        "cas_no": "50-81-7",
        "function": ["antioxidant", "skin-brightening", "collagen-synthesis"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 2,
    },
    {
        "inci_name": "Sodium Hyaluronate",
        "canonical_name": "Sodium Hyaluronate",
        "synonyms": ["Hyaluronic Acid Sodium Salt", "Hyaluronan", "HA"],
        "cas_no": "9067-32-7",
        "function": ["humectant", "film-forming", "skin-conditioning"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Dimethicone",
        "canonical_name": "Dimethicone",
        "synonyms": ["Polydimethylsiloxane", "PDMS", "Dimethyl Silicone"],
        "cas_no": "9006-65-9",
        "function": ["emollient", "skin-conditioning", "occlusive"],
        "evidence_grade": "B",
        "comedogenic": 1,
        "irritancy": 0,
    },
    {
        "inci_name": "Cetyl Alcohol",
        "canonical_name": "Cetyl Alcohol",
        "synonyms": ["1-Hexadecanol", "Palmityl Alcohol", "n-Hexadecyl Alcohol"],
        "cas_no": "36653-82-4",
        "function": ["emollient", "emulsifier", "viscosity-controlling"],
        "evidence_grade": "B",
        "comedogenic": 2,
        "irritancy": 0,
    },
    {
        "inci_name": "Phenoxyethanol",
        "canonical_name": "Phenoxyethanol",
        "synonyms": ["2-Phenoxyethanol", "Rose Ether", "Ethylene Glycol Monophenyl Ether"],
        "cas_no": "122-99-6",
        "function": ["preservative", "antimicrobial"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Tocopherol",
        "canonical_name": "Tocopherol",
        "synonyms": ["Vitamin E", "Alpha Tocopherol", "d-Alpha Tocopherol"],
        "cas_no": "59-02-9",
        "function": ["antioxidant", "skin-conditioning"],
        "evidence_grade": "B",
        "comedogenic": 2,
        "irritancy": 0,
    },
    {
        "inci_name": "Allantoin",
        "canonical_name": "Allantoin",
        "synonyms": ["5-Ureidohydantoin", "Glyoxyldiureide"],
        "cas_no": "97-59-6",
        "function": ["soothing", "skin-healing", "keratolytic"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Panthenol",
        "canonical_name": "Panthenol",
        "synonyms": ["Provitamin B5", "D-Panthenol", "DL-Panthenol"],
        "cas_no": "16485-10-2",
        "function": ["humectant", "moisturizing", "anti-inflammatory"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Titanium Dioxide",
        "canonical_name": "Titanium Dioxide",
        "synonyms": ["CI 77891", "TiO2"],
        "cas_no": "13463-67-7",
        "function": ["UV-filter", "colorant", "opacifying"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Zinc Oxide",
        "canonical_name": "Zinc Oxide",
        "synonyms": ["CI 77947", "Zinc White"],
        "cas_no": "1314-13-2",
        "function": ["UV-filter", "anti-acne", "skin-protectant"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Azelaic Acid",
        "canonical_name": "Azelaic Acid",
        "synonyms": ["Nonanedioic Acid", "1,7-Heptanedicarboxylic Acid"],
        "cas_no": "123-99-9",
        "function": ["anti-acne", "skin-brightening", "anti-rosacea"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Squalane",
        "canonical_name": "Squalane",
        "synonyms": ["Perhydrosqualene", "Shark Squalane", "Olive Squalane"],
        "cas_no": "111-01-3",
        "function": ["emollient", "occlusive", "skin-conditioning"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Kojic Acid",
        "canonical_name": "Kojic Acid",
        "synonyms": ["5-Hydroxy-2-hydroxymethyl-4-pyranone"],
        "cas_no": "501-30-4",
        "function": ["skin-brightening", "antioxidant", "tyrosinase-inhibitor"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Alpha-Arbutin",
        "canonical_name": "Alpha-Arbutin",
        "synonyms": ["4-Hydroxyphenyl alpha-D-Glucopyranoside", "Alpha Arbutin"],
        "cas_no": "84380-01-8",
        "function": ["skin-brightening", "tyrosinase-inhibitor"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Caffeine",
        "canonical_name": "Caffeine",
        "synonyms": ["1,3,7-Trimethylxanthine", "Methyltheobromine"],
        "cas_no": "58-08-2",
        "function": ["antioxidant", "anti-puffiness", "skin-conditioning"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Lactic Acid",
        "canonical_name": "Lactic Acid",
        "synonyms": ["AHA", "Alpha Hydroxy Acid", "2-Hydroxypropanoic Acid"],
        "cas_no": "50-21-5",
        "function": ["exfoliant", "humectant", "pH-adjuster"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 2,
    },
    {
        "inci_name": "Ferulic Acid",
        "canonical_name": "Ferulic Acid",
        "synonyms": ["4-Hydroxy-3-methoxycinnamic Acid", "Hydroxymethoxycinnamic Acid"],
        "cas_no": "1135-24-6",
        "function": ["antioxidant", "UV-protection", "skin-conditioning"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Centella Asiatica Extract",
        "canonical_name": "Centella Asiatica Extract",
        "synonyms": ["Gotu Kola Extract", "Cica Extract", "TECA"],
        "cas_no": "84696-21-9",
        "function": ["soothing", "wound-healing", "anti-inflammatory"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Ceramide NP",
        "canonical_name": "Ceramide NP",
        "synonyms": ["Ceramide 3", "N-Stearoyl Phytosphingosine"],
        "cas_no": "100403-19-8",
        "function": ["barrier-repair", "skin-conditioning", "moisturizing"],
        "evidence_grade": "A",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Tranexamic Acid",
        "canonical_name": "Tranexamic Acid",
        "synonyms": ["TXA", "4-(Aminomethyl)cyclohexanecarboxylic Acid"],
        "cas_no": "1197-18-8",
        "function": ["skin-brightening", "anti-melasma"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
    {
        "inci_name": "Sodium Laureth Sulfate",
        "canonical_name": "Sodium Laureth Sulfate",
        "synonyms": ["SLES", "Sodium Lauryl Ether Sulfate"],
        "cas_no": "9004-82-4",
        "function": ["surfactant", "cleansing", "foaming"],
        "evidence_grade": "C",
        "comedogenic": 0,
        "irritancy": 3,
    },
    {
        "inci_name": "Cocamidopropyl Betaine",
        "canonical_name": "Cocamidopropyl Betaine",
        "synonyms": ["CAPB", "Cocoamidopropyl Betaine"],
        "cas_no": "61789-40-0",
        "function": ["surfactant", "cleansing", "antistatic"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Benzyl Alcohol",
        "canonical_name": "Benzyl Alcohol",
        "synonyms": ["Phenylcarbinol", "Benzenemethanol"],
        "cas_no": "100-51-6",
        "function": ["preservative", "solvent", "fragrance"],
        "evidence_grade": "C",
        "comedogenic": 0,
        "irritancy": 2,
    },
    {
        "inci_name": "Ethylhexylglycerin",
        "canonical_name": "Ethylhexylglycerin",
        "synonyms": ["3-((2-Ethylhexyl)oxy)-1,2-propanediol"],
        "cas_no": "70445-33-9",
        "function": ["preservative", "skin-conditioning", "deodorant"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 1,
    },
    {
        "inci_name": "Xanthan Gum",
        "canonical_name": "Xanthan Gum",
        "synonyms": ["Corn Sugar Gum", "Xanthan"],
        "cas_no": "11138-66-2",
        "function": ["viscosity-controlling", "stabilizer", "emulsifier"],
        "evidence_grade": "B",
        "comedogenic": 0,
        "irritancy": 0,
    },
]


# ---------------------------------------------------------------------------
# Insertion logic
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO ingredient (
    inci_name, canonical_name, synonyms, cas_no,
    function, evidence_grade, comedogenic, irritancy
)
VALUES (
    :inci_name, :canonical_name, :synonyms, :cas_no,
    :function, :evidence_grade, :comedogenic, :irritancy
)
ON CONFLICT (inci_name) DO NOTHING
"""


async def seed(session: AsyncSession) -> int:
    """
    Insert all seed ingredients and return the count of new rows created.
    Existing rows (matched on ``inci_name``) are silently skipped.
    """
    inserted = 0
    for row in SEED_INGREDIENTS:
        result = await session.execute(
            text(INSERT_SQL),
            {
                "inci_name": row["inci_name"],
                "canonical_name": row["canonical_name"],
                # asyncpg expects Python lists for ARRAY columns
                "synonyms": row.get("synonyms") or [],
                "cas_no": row.get("cas_no"),
                "function": row.get("function") or [],
                "evidence_grade": row.get("evidence_grade"),
                "comedogenic": row.get("comedogenic"),
                "irritancy": row.get("irritancy"),
            },
        )
        if result.rowcount:
            inserted += result.rowcount
    await session.commit()
    return inserted


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.async_database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        count = await seed(session)

    await engine.dispose()
    total = len(SEED_INGREDIENTS)
    print(f"Seed complete: {count} new / {total - count} already existed ({total} total).")


if __name__ == "__main__":
    asyncio.run(main())
