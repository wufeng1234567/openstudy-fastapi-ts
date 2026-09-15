"""
Redis 连接配置
仅用于 Token 缓存、验证码、字典缓存、限流等
"""

import redis.asyncio as redis
from app.config import settings
from loguru import logger


class RedisClient:
    """Redis 客户端封装"""

    def __init__(self):
        self._pool = None

    async def connect(self):
        """创建连接池"""
        self._pool = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        # 测试连接
        await self._pool.ping()
        logger.info(f"Redis connected: {settings.REDIS_HOST}:{settings.REDIS_PORT}")

    async def disconnect(self):
        """关闭连接池"""
        if self._pool:
            await self._pool.close()
            logger.info("Redis connections closed")

    @property
    def client(self) -> redis.Redis:
        """获取 Redis 客户端"""
        if not self._pool:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._pool


# 全局单例
redis_client = RedisClient()
