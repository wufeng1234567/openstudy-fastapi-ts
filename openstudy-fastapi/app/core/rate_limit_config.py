"""
AI 限流参数的运行时配置层（Redis 支持，改完即时生效，无需重启）

存储：Redis hash `rl:ai:config`，字段 enabled / userPerMinute / dailyLimit / ipPerMinute。
缺 key 或缺字段时回落到环境变量默认值（AI_DAILY_LIMIT / AI_USER_PER_MINUTE / AI_IP_PER_MINUTE），
与 rate_limit.py 原来的 import 时读 env 的行为保持兼容。

为什么放 Redis 而不是表：限流中间件每个请求都要读一次配置，
Redis 单次 HGETALL（亚毫秒）远比一次 PG 查询便宜，且天然多进程共享。
"""

import os
from loguru import logger
from app.redis import redis_client

RATE_LIMIT_CONFIG_KEY = "rl:ai:config"

# ── 环境变量默认值（key 缺失时回落）──
DEFAULT_ENABLED = True
DEFAULT_DAILY_LIMIT = int(os.environ.get("AI_DAILY_LIMIT", 50))
DEFAULT_USER_PER_MINUTE = int(os.environ.get("AI_USER_PER_MINUTE", 10))
DEFAULT_IP_PER_MINUTE = int(os.environ.get("AI_IP_PER_MINUTE", 100))


def env_defaults() -> dict:
    """环境变量给出的默认配置（每次调用取，方便测试改 env）"""
    return {
        "enabled": DEFAULT_ENABLED,
        "userPerMinute": DEFAULT_USER_PER_MINUTE,
        "dailyLimit": DEFAULT_DAILY_LIMIT,
        "ipPerMinute": DEFAULT_IP_PER_MINUTE,
    }


def _to_int(value, fallback: int) -> int:
    """Redis 里的值都是字符串，容错转 int（脏数据回落默认值）"""
    try:
        n = int(value)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _to_bool(value, fallback: bool) -> bool:
    if value is None:
        return fallback
    return str(value).strip().lower() in ("1", "true", "yes", "on")


async def get_config() -> dict:
    """读取生效配置：Redis hash 优先，缺字段回落环境变量默认值"""
    defaults = env_defaults()
    pool = redis_client._pool
    if pool is None:
        return {**defaults, "sources": {k: "default" for k in defaults}}
    try:
        raw = await pool.hgetall(RATE_LIMIT_CONFIG_KEY)
    except Exception as e:
        logger.warning(f"rate_limit_config: 读取失败，回落默认值: {e}")
        raw = {}
    cfg = {**defaults}
    sources = {k: "default" for k in defaults}
    for key in ("userPerMinute", "dailyLimit", "ipPerMinute"):
        if key in raw:
            cfg[key] = _to_int(raw[key], defaults[key])
            sources[key] = "redis"
    if "enabled" in raw:
        cfg["enabled"] = _to_bool(raw["enabled"], defaults["enabled"])
        sources["enabled"] = "redis"
    return {**cfg, "sources": sources}


async def save_config(enabled: bool, user_per_minute: int, daily_limit: int, ip_per_minute: int) -> dict:
    """持久化配置到 Redis hash（整体覆盖，只存显式给的四项）"""
    pool = redis_client._pool
    if pool is None:
        raise RuntimeError("Redis not connected")
    await pool.hset(
        RATE_LIMIT_CONFIG_KEY,
        mapping={
            "enabled": "1" if enabled else "0",
            "userPerMinute": str(int(user_per_minute)),
            "dailyLimit": str(int(daily_limit)),
            "ipPerMinute": str(int(ip_per_minute)),
        },
    )
    return await get_config()
