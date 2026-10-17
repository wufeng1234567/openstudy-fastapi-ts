"""
AI 接口限流中间件（纯 ASGI，不破坏流式响应）

策略（均可通过环境变量覆盖）：
  1. 每用户每日 AI 请求上限 50 次（AI_DAILY_LIMIT）
  2. 每用户每分钟请求上限 10 次（AI_USER_PER_MINUTE，不依赖 IP）
  3. 每 IP 每分钟请求上限 100 次（AI_IP_PER_MINUTE，防脚本刷，NAT 不误伤）
  4. 超限返回 429 + 友好提示，不报错

⚠️ 只限流「真正调 LLM」的接口，不拦查库/配置/会话管理接口。
   白名单匹配 AI_LLM_PATHS，不在白名单里的 /ai/ 请求直接放行。

⚠️ **本地开发版不限流**：
   环境变量 `AI_RATE_LIMIT_ENABLED=false`（`app/config.py` 的
   `Settings.AI_RATE_LIMIT_ENABLED`）是最高优先级的硬开关，压过 Redis 配置 ——
   置 false 时本中间件直接放行（连计数器都不写）。
   本地 `startup-scripts/start-fastapi.bat` 已显式设为 false；
   线上 `daily-start.sh` 保持 true（体验版防刷）。

⚠️ 评测期间如需调整：
  export AI_USER_PER_MINUTE=30   # 放宽每用户每分钟
  export AI_DAILY_LIMIT=200      # 放宽每日额度
  export AI_IP_PER_MINUTE=1000   # 基本关掉 IP 限流

⚠️ 为什么不解析 JWT 拿 user_id：
  本系统的 token 是 UUID（不是 JWT），存在 Redis 里：
    openstudy-py:login_tokens:{token} = {"user_id": 2, "user_name": "demo", ...}
  所以要从 Redis 查 token → user_id。
"""

import os
import time
import json
import fnmatch
import redis.asyncio as redis
from loguru import logger
from app.config import settings
from app.redis import redis_client
from app.core.rate_limit_config import get_config


# ── 限流参数默认值（兼容旧的 import 时读 env；运行时以 Redis 配置为准）──
AI_DAILY_LIMIT = int(os.environ.get("AI_DAILY_LIMIT", 50))       # 每用户每天
AI_USER_PER_MINUTE = int(os.environ.get("AI_USER_PER_MINUTE", 10))  # 每用户每分钟
AI_IP_PER_MINUTE = int(os.environ.get("AI_IP_PER_MINUTE", 100))    # 每 IP 每分钟
LOGIN_TOKEN_PREFIX = "openstudy-py:login_tokens:"

# ── 需要限流的路径白名单（**只列真正调 LLM 的接口**）──
# 用 fnmatch 做 glob 匹配，支持通配符
#
# ⚠️ 这里曾经混进了 3 个**根本不调 LLM** 的路径，造成两个真实的线上故障
#    （用户 2026-10-17 报「点取消，LLM 那边没有反应」，并很快烧完 50 次额度）：
#
#    · `/ai/agent/confirm` —— 只做 `resolve_confirmation()` 唤醒挂起的循环，
#      **一次 LLM 都不调**。被限流后前端 POST 收到 429 → 后端永远收不到「取消」决定 →
#      循环挂到 180s 超时；用户看到卡片显示「已取消」，但模型那边毫无反应。
#    · `/ai/agent/preview` / `/ai/agent/execute` —— ds-free 链路里每调一个工具都要
#      走一遍（预览 + 执行），**后端一次 LLM 都不调**（LLM 在浏览器扩展侧）。
#      计入额度后，一个多工具回合就能干掉好几次「日额度」。
#
#    结论：额度只该按「真正的模型轮次」计。上面三个一律移出白名单。
AI_LLM_PATHS = [
    "/ai/chat",                        # POST 对话
    "/ai/assistant/stream",            # GET/POST 流式对话
    "/ai/assistant/generate-with-images",  # POST 图片生成
    "/ai/generate/questions",          # POST 出题
    "/ai/generate/questions/stream",   # GET 流式出题
    "/ai/generate/questions/sync",     # POST 同步出题
    "/ai/generate/reading/stream",     # GET 流式阅读
    "/ai/generate/composite/stream",   # GET 流式组合
    "/ai/generate/composite/sync",     # POST 同步组合
    "/ai/agent/stream",                # POST 智能体流式（后端 LLM 循环）
    "/ai/analyze/question/stream",     # GET 题目分析
]

#: 硬开关：False = 整个限流关闭（本地开发版）。
#: 每次请求实时读 `settings`，改环境变量后重启即生效（不缓存，避免与热重载打架）。
def _globally_enabled() -> bool:
    return bool(getattr(settings, "AI_RATE_LIMIT_ENABLED", True))


def _is_llm_path(path: str) -> bool:
    """判断路径是否在 LLM 白名单中"""
    for pattern in AI_LLM_PATHS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


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
    """从 Redis 查 token → user_id"""
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


async def _log_violation(
    limit_type: str,
    current_count: int,
    limit_value: int,
    ip: str,
    user_id: str | None,
    path: str,
) -> None:
    """违规落库（尽力而为，绝不影响 429 响应本身）

    ⚠️ 中间件热路径上的旁路写：任何异常都吞掉只打 debug 日志。
    用独立短会话（不复用请求级 db 依赖），因为 ASGI 中间件拿不到 get_db。
    """
    try:
        from sqlalchemy import delete
        from app.database import async_session_factory
        from app.models.ai_rate_limit_log import SysAiRateLimitLog

        user_name = None
        if user_id:
            # user_id 是 token 里带出来的，登录时 user_name 也存了；查一遍补全（失败不影响主流程）
            try:
                from app.models.user import SysUser
                async with async_session_factory() as db:
                    row = await db.get(SysUser, int(user_id))
                    user_name = row.user_name if row else None
            except Exception:
                user_name = None

        async with async_session_factory() as db:
            db.add(
                SysAiRateLimitLog(
                    user_id=int(user_id) if user_id else None,
                    user_name=user_name,
                    ip=ip,
                    path=path,
                    limit_type=limit_type,
                    current_count=current_count,
                    limit_value=limit_value,
                )
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"rate_limit: violation log write failed: {e}")


async def _check_rate_limit(ip: str, user_id: str | None, path: str = "") -> tuple[bool, str]:
    """检查是否超限，返回 (allowed, reason)

    ⚠️ 配置每个请求实时读 Redis（rate_limit_config.get_config），
    后台改完即时生效，不用重启。Redis 不通时回落环境变量默认值。
    """
    pool: redis.Redis = redis_client._pool
    if pool is None:
        return True, ""

    # 本地开发版：硬开关优先于 Redis 配置（连计数器都不写，别在本地把自己卡住）
    if not _globally_enabled():
        return True, ""

    cfg = await get_config()
    if not cfg["enabled"]:
        return True, ""

    now = int(time.time())
    minute_bucket = now // 60

    # ── 每 IP 每分钟 ──
    ip_key = f"rl:ai:ip:{ip}:{minute_bucket}"
    ip_count = await pool.incr(ip_key)
    if ip_count == 1:
        await pool.expire(ip_key, 70)
    if ip_count > cfg["ipPerMinute"]:
        logger.warning(f"AI rate limit (IP): {ip} {ip_count}/{cfg['ipPerMinute']} per min")
        await _log_violation("ip", ip_count, cfg["ipPerMinute"], ip, user_id, path)
        return False, f"请求过于频繁，请稍后再试（每分钟限 {cfg['ipPerMinute']} 次）"

    if user_id:
        # ── 每用户每分钟 ──
        user_min_key = f"rl:ai:umin:{user_id}:{minute_bucket}"
        user_min_count = await pool.incr(user_min_key)
        if user_min_count == 1:
            await pool.expire(user_min_key, 70)
        if user_min_count > cfg["userPerMinute"]:
            logger.warning(f"AI rate limit (User/min): {user_id} {user_min_count}/{cfg['userPerMinute']} per min")
            await _log_violation("user_min", user_min_count, cfg["userPerMinute"], ip, user_id, path)
            return False, f"请求过于频繁，请稍后再试（每分钟限 {cfg['userPerMinute']} 次）"

        # ── 每用户每日 ──
        day = time.strftime("%Y%m%d")
        user_day_key = f"rl:ai:uday:{user_id}:{day}"
        user_day_count = await pool.incr(user_day_key)
        if user_day_count == 1:
            await pool.expire(user_day_key, 90000)
        if user_day_count > cfg["dailyLimit"]:
            logger.warning(f"AI rate limit (User/day): {user_id} {user_day_count}/{cfg['dailyLimit']} today")
            await _log_violation("user_day", user_day_count, cfg["dailyLimit"], ip, user_id, path)
            return False, f"今日 AI 体验额度已用完（{cfg['dailyLimit']}/{cfg['dailyLimit']}），明天重置"

    return True, ""


class AiRateLimitMiddleware:
    """AI 接口限流中间件（纯 ASGI）

    只拦截白名单中「真正调 LLM」的接口；
    /ai/sessions、/ai/models、/ai/agent/tools 等查库接口不受限流。
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        # 只限白名单中的 LLM 接口
        if not _is_llm_path(path):
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        ip = _get_client_ip(scope)
        token = _extract_token(scope)
        user_id = await _get_user_id_from_token(token) if token else None

        allowed, reason = await _check_rate_limit(ip, user_id, path)
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
