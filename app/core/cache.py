"""
High-Speed Cache Layer (Redis with In-Memory Fallback).
Ensures Next.js ISR endpoints respond well under 80ms.
"""
from __future__ import annotations

import functools
import json
import logging
import time
from typing import Any, Callable

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_redis_client = None
_in_memory_cache: dict[str, tuple[float, str]] = {}  # key -> (expires_at, json_data)


async def get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            # Ping to verify
            await _redis_client.ping()
        except Exception as exc:
            logger.debug("Redis unavailable for caching, using in-memory store: %s", exc)
            _redis_client = False
    return _redis_client if _redis_client else None


async def cache_get(key: str) -> dict[str, Any] | list[Any] | None:
    """Retrieve item from Redis or in-memory cache."""
    # 1. Try Redis
    client = await get_redis_client()
    if client:
        try:
            raw = await client.get(key)
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Redis get error for %s: %s", key, exc)

    # 2. In-memory fallback
    now = time.time()
    if key in _in_memory_cache:
        expires_at, val = _in_memory_cache[key]
        if now < expires_at:
            return json.loads(val)
        else:
            del _in_memory_cache[key]

    return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> None:
    """Store item in Redis and in-memory cache with TTL."""
    raw = json.dumps(value, default=str)
    client = await get_redis_client()
    if client:
        try:
            await client.set(key, raw, ex=ttl_seconds)
        except Exception as exc:
            logger.debug("Redis set error for %s: %s", key, exc)

    # In-memory storage
    _in_memory_cache[key] = (time.time() + ttl_seconds, raw)
