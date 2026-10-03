"""
Models package — import all ORM models here so Alembic can discover them
via `app.models` when building autogenerate migrations.

Import order matters: Brand before Product (FK dependency).
"""
from app.models.brand import Brand
from app.models.ingredient import Ingredient
from app.models.product import Product
from app.models.variant import Variant
from app.models.product_ingredient import ProductIngredient
from app.models.retailer import Retailer
from app.models.offer import Offer
from app.models.dupe_edge import DupeEdge
from app.models.page import Page
from app.models.unresolved_entity_queue import UnresolvedEntityQueue
from app.models.click_telemetry import ClickTelemetry
from app.models.search_performance import SearchPerformance

__all__ = [
    "Brand",
    "Ingredient",
    "Product",
    "Variant",
    "ProductIngredient",
    "Retailer",
    "Offer",
    "DupeEdge",
    "Page",
    "UnresolvedEntityQueue",
    "ClickTelemetry",
    "SearchPerformance",
]
