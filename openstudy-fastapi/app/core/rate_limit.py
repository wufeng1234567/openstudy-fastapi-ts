"""
AI 接口限流中间件（纯 ASGI，不破坏流式响应）

策略：
  1. 每用户每日 AI 请求上限 50 次（按 user_id 计数，需登录）
  2. 每用户每分钟请求上限 5 次（防止快速刷，不依赖 IP）
  3. 每 IP 每分钟请求上限 10 次（防匿名刷）
  4. 超限返回 429 + 友好提示，不报错

只对 /ai/ 路径生效，其他接口不限流。

⚠️ 为什么不解析 JWT 拿 user_id：
  本系统的 token 是 UUID（不是 JWT），存在 Redis 里：
    openstudy-py:login_tokens:{token} = {"user_id": 2, "user_name": "demo", ...}
  所以要从 Redis 查 token → user_id。
"""

import time
import json
import redis.asyncio as redis
from loguru import logger
from app.redis import redis_client


# ── 限流参数 ──
AI_DAILY_LIMIT = 50        # 每用户每天
AI_USER_PER_MINUTE = 5     # 每用户每分钟（不依赖 IP，隧道多 IP 也能挡）
AI_IP_PER_MINUTE = 10      # 每 IP 每分钟（防匿名刷）
AI_PATH_PREFIX = "/ai/"    # 只限 AI 接口
LOGIN_TOKEN_PREFIX = "openstudy-py:login_tokens:"


def _get_client_ip(scope) -> str:
    """从 ASGI scope 提取客户端 IP（优先 X-Forwarded-For）"""
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def _extract_token(scope) -> str | None:
    """从 Authorization header 提取 Bearer token"""
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            token = value.decode("latin-1").removeprefix("Bearer ").strip()
            return token if token else None
    return None


async def _get_user_id_from_token(token: str) -> str | None:
    """从 Redis 查 token → user_id

    Redis key: openstudy-py:login_tokens:{token}
    Value: {"user_id": 2, "user_name": "demo", ...}
    """
    pool: redis.Redis = redis_client._pool
    if pool is None or not token:
        return None
    try:
        data = await pool.get(f"{LOGIN_TOKEN_PREFIX}{token}")
        if data:
            user_data = json.loads(data)
            uid = user_data.get("user_id")
            return str(uid) if uid else None
    except Exception as e:
        logger.debug(f"rate_limit: token lookup failed: {e}")
    return None


async def _check_rate_limit(ip: str, user_id: str | None) -> tuple[bool, str]:
    """检查是否超限，返回 (allowed, reason)"""
    pool: redis.Redis = redis_client._pool
    if pool is None:
        return True, ""

    now = int(time.time())
    minute_bucket = now // 60

    # ── 每 IP 每分钟 ──
    ip_key = f"rl:ai:ip:{ip}:{minute_bucket}"
    ip_count = await pool.incr(ip_key)
    if ip_count == 1:
        await pool.expire(ip_key, 70)
    if ip_count > AI_IP_PER_MINUTE:
        logger.warning(f"AI rate limit (IP): {ip} {ip_count}/{AI_IP_PER_MINUTE} per min")
        return False, f"请求过于频繁，请稍后再试（每分钟限 {AI_IP_PER_MINUTE} 次）"

    if user_id:
        # ── 每用户每分钟（不依赖 IP，隧道多 IP 也能挡）──
        user_min_key = f"rl:ai:umin:{user_id}:{minute_bucket}"
        user_min_count = await pool.incr(user_min_key)
        if user_min_count == 1:
            await pool.expire(user_min_key, 70)
        if user_min_count > AI_USER_PER_MINUTE:
            logger.warning(f"AI rate limit (User/min): {user_id} {user_min_count}/{AI_USER_PER_MINUTE} per min")
            return False, f"请求过于频繁，请稍后再试（每分钟限 {AI_USER_PER_MINUTE} 次）"

        # ── 每用户每日 ──
        day = time.strftime("%Y%m%d")
        user_day_key = f"rl:ai:uday:{user_id}:{day}"
        user_day_count = await pool.incr(user_day_key)
        if user_day_count == 1:
            await pool.expire(user_day_key, 90000)
        if user_day_count > AI_DAILY_LIMIT:
            logger.warning(f"AI rate limit (User/day): {user_id} {user_day_count}/{AI_DAILY_LIMIT} today")
            return False, f"今日 AI 体验额度已用完（{AI_DAILY_LIMIT}/{AI_DAILY_LIMIT}），明天重置"

    return True, ""


class AiRateLimitMiddleware:
    """AI 接口限流中间件（纯 ASGI）

    只拦截 /ai/ 前缀的请求；其他请求直接放行。
    超限时返回 429 JSON，不调用下游 app。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        if not path.startswith(AI_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        ip = _get_client_ip(scope)
        token = _extract_token(scope)
        user_id = await _get_user_id_from_token(token) if token else None

        allowed, reason = await _check_rate_limit(ip, user_id)
        if not allowed:
            body = json.dumps(
                {"code": 429, "msg": reason, "data": None},
                ensure_ascii=False,
            ).encode("utf-8")

            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("latin-1")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)
