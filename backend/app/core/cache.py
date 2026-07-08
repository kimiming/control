import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings


settings = get_settings()
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def cache_get_json(key: str) -> Any | None:
    value = await redis_client.get(key)
    return json.loads(value) if value else None


async def cache_set_json(key: str, value: Any, ttl: int = 30) -> None:
    await redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)


async def cache_delete(key: str) -> None:
    await redis_client.delete(key)
