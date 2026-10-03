"""
Shared pytest fixtures for The Beauty Project test suite.

Fixtures defined here are auto-discovered by pytest (conftest.py semantics).
No real database is required for unit tests — use the mock_cache fixture
to drive IngredientNormalizer without a live PostgreSQL connection.
"""
from __future__ import annotations

import uuid

import pytest

from app.services.ingredient_normalizer import (
    IngredientNormalizer,
    IngredientParser,
    _IngredientCache,
)

# ---------------------------------------------------------------------------
# Minimal in-memory ingredient dataset for unit tests
# ---------------------------------------------------------------------------
MOCK_INGREDIENTS: list[dict] = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "inci_name": "Water",
        "canonical_name": "Water",
        "synonyms": ["Aqua", "Eau", "H2O"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "inci_name": "Niacinamide",
        "canonical_name": "Niacinamide",
        "synonyms": ["Vitamin B3", "Nicotinamide"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "inci_name": "Glycerin",
        "canonical_name": "Glycerin",
        "synonyms": ["Glycerol", "Glycerine"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
        "inci_name": "Salicylic Acid",
        "canonical_name": "Salicylic Acid",
        "synonyms": ["BHA", "Beta Hydroxy Acid"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000005"),
        "inci_name": "Ascorbic Acid",
        "canonical_name": "Ascorbic Acid",
        "synonyms": ["Vitamin C", "L-Ascorbic Acid"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000006"),
        "inci_name": "Phenoxyethanol",
        "canonical_name": "Phenoxyethanol",
        "synonyms": ["2-Phenoxyethanol"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000007"),
        "inci_name": "Retinol",
        "canonical_name": "Retinol",
        "synonyms": ["Vitamin A", "All-trans-retinol"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000008"),
        "inci_name": "Panthenol",
        "canonical_name": "Panthenol",
        "synonyms": ["Provitamin B5", "D-Panthenol"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000009"),
        "inci_name": "Sodium Hyaluronate",
        "canonical_name": "Sodium Hyaluronate",
        "synonyms": ["Hyaluronic Acid Sodium Salt", "HA"],
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000010"),
        "inci_name": "Allantoin",
        "canonical_name": "Allantoin",
        "synonyms": ["5-Ureidohydantoin"],
    },
]


@pytest.fixture(scope="session")
def mock_cache() -> _IngredientCache:
    """Pre-built in-memory cache — no DB required."""
    return _IngredientCache.from_dicts(MOCK_INGREDIENTS)


@pytest.fixture(scope="session")
def normalizer(mock_cache: _IngredientCache) -> IngredientNormalizer:
    """IngredientNormalizer wired to the in-memory mock cache."""
    return IngredientNormalizer.with_cache(mock_cache)


@pytest.fixture(scope="session")
def parser() -> type[IngredientParser]:
    """Return the IngredientParser class (stateless, no instance needed)."""
    return IngredientParser
