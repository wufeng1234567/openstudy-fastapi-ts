"""
AI 接口限流中间件（纯 ASGI，不破坏流式响应）

策略：
  1. 每用户每日 AI 请求上限 50 次（按 user_id 计数，需登录）
  2. 每 IP 每分钟请求上限 10 次（防匿名刷）
  3. 超限返回 429 + 友好提示，不报错

只对 /ai/ 路径生效，其他接口不限流。
"""

import time
import json
import redis.asyncio as redis
from loguru import logger
from app.redis import redis_client


# ── 限流参数 ──
AI_DAILY_LIMIT = 50        # 每用户每天
AI_IP_PER_MINUTE = 10      # 每 IP 每分钟
AI_PATH_PREFIX = "/ai/"    # 只限 AI 接口


def _get_client_ip(scope) -> str:
    """从 ASGI scope 提取客户端 IP（优先 X-Forwarded-For）"""
    # 先查 X-Forwarded-For（隧道/代理场景）
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    # 直连
    client = scope.get("client")
    return client[0] if client else "unknown"


def _get_user_id_from_auth(scope) -> str | None:
    """从 Authorization header 提取 user_id（简化版：JWT payload 解析）

    这里不验签，只取 user_id 用于限流分桶 —— 即使被伪造也只是限流桶偏移，
    后端路由层的 get_current_user 会做真正的验签。
    """
    import base64
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            token = value.decode("latin-1").removeprefix("Bearer ").strip()
            if not token or token.count(".") < 2:
                return None
            try:
                # JWT = header.payload.signature，取 payload
                payload_b64 = token.split(".")[1]
                # 补齐 base64 padding
                padding = 4 - len(payload_b64) % 4
                if padding != 4:
                    payload_b64 += "=" * padding
                payload = json.loads(base64.urlsafe_b64decode(payload_b64))
                # 兼容不同 JWT claim 名
                return str(payload.get("sub") or payload.get("user_id") or payload.get("uid") or "")
            except Exception:
                return None
    return None


async def _check_rate_limit(ip: str, user_id: str | None) -> tuple[bool, str]:
    """检查是否超限，返回 (allowed, reason)"""
    pool: redis.Redis = redis_client._pool
    if pool is None:
        # Redis 未连接，放行（不因基础设施故障阻断业务）
        return True, ""

    now = int(time.time())

    # ── 每 IP 每分钟 ──
    ip_key = f"rl:ai:ip:{ip}:{now // 60}"
    ip_count = await pool.incr(ip_key)
    if ip_count == 1:
        await pool.expire(ip_key, 70)  # 60s + 10s 缓冲
    if ip_count > AI_IP_PER_MINUTE:
        logger.warning(f"AI rate limit (IP): {ip} {ip_count}/{AI_IP_PER_MINUTE} per min")
        return False, f"请求过于频繁，请稍后再试（每分钟限 {AI_IP_PER_MINUTE} 次）"

    # ── 每用户每日 ──
    if user_id:
        day = time.strftime("%Y%m%d")
        user_key = f"rl:ai:user:{user_id}:{day}"
        user_count = await pool.incr(user_key)
        if user_count == 1:
            await pool.expire(user_key, 90000)  # 25h
        if user_count > AI_DAILY_LIMIT:
            logger.warning(f"AI rate limit (User): {user_id} {user_count}/{AI_DAILY_LIMIT} today")
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

        # 只限 AI 接口的写操作（POST/GET 带 stream）
        if not path.startswith(AI_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # OPTIONS 预检直接放行
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # 提取 IP 和 user_id
        ip = _get_client_ip(scope)
        user_id = _get_user_id_from_auth(scope)

        # 检查限流
        allowed, reason = await _check_rate_limit(ip, user_id)
        if not allowed:
            # 返回 429 JSON
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

        # 放行
        await self.app(scope, receive, send)
