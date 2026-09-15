"""
Redis 工具函数
"""

import json
from typing import Any, Optional
from app.redis import redis_client


async def set_cache(key: str, value: Any, expire: int = None) -> None:
    """设置缓存"""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str):
        value = str(value)

    if expire:
        await redis_client.client.setex(key, expire, value)
    else:
        await redis_client.client.set(key, value)


async def get_cache(key: str) -> Optional[str]:
    """获取缓存"""
    return await redis_client.client.get(key)


async def get_cache_json(key: str) -> Optional[Any]:
    """获取 JSON 缓存"""
    data = await redis_client.client.get(key)
    if data:
        return json.loads(data)
    return None


async def delete_cache(key: str) -> bool:
    """删除缓存"""
    return await redis_client.client.delete(key) > 0


async def delete_pattern(pattern: str) -> int:
    """按模式删除缓存"""
    keys = []
    async for key in redis_client.client.scan_iter(match=pattern):
        keys.append(key)
    if keys:
        return await redis_client.client.delete(*keys)
    return 0


async def exists(key: str) -> bool:
    """检查 key 是否存在"""
    return await redis_client.client.exists(key) > 0


async def expire_key(key: str, seconds: int) -> bool:
    """设置过期时间"""
    return await redis_client.client.expire(key, seconds)


async def increment(key: str, amount: int = 1) -> int:
    """自增"""
    return await redis_client.client.incrby(key, amount)


async def get_keys(pattern: str) -> list:
    """获取匹配的 keys"""
    keys = []
    async for key in redis_client.client.scan_iter(match=pattern):
        keys.append(key)
    return keys
