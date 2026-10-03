"""FastAPI application entry point for The Beauty Project backend."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="The Beauty Project API",
    description=(
        "High-performance programmatic beauty & skincare publisher backend. "
        "Ingredient graph, dupe engine, affiliate offer index, and DCS gate."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

dev_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.pages import router as pages_router
from app.api.v1.admin import router as admin_router
from app.api.v1.affiliate import router as affiliate_router
from app.api.v1.dupes import router as dupes_router
from app.api.v1.ingredients import router as ingredients_router
from app.api.v1.products import router as products_router
from app.api.v1.sitemaps import router as sitemaps_router

# Core API & ISR generation endpoints
app.include_router(products_router)
app.include_router(dupes_router)
app.include_router(ingredients_router)
app.include_router(sitemaps_router)
app.include_router(pages_router)
app.include_router(affiliate_router)
app.include_router(admin_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "status": "online",
        "message": "The Beauty Project API is running",
        "docs": "/docs",
        "health": "/health",
        "version": "0.1.0",
    }


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, Any]:
    db_status = "unknown"
    db_error = None
    try:
        from sqlalchemy import text
        from app.db.session import async_session
        async with async_session() as session:
            res = await session.execute(text("SELECT count(*) FROM brand;"))
            brand_count = res.scalar()
            db_status = f"connected ({brand_count} brands in database)"
    except Exception as e:
        db_status = "connection_failed"
        db_error = str(e)

    return {
        "status": "ok",
        "env": settings.app_env,
        "database": db_status,
        "database_error": db_error,
        "database_url_provided": bool(settings.database_url),
    }
