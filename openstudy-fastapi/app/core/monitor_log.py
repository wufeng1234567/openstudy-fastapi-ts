"""后台写操作自动记入 `sys_oper_log`（2026-11-04）。

用纯 ASGI 中间件而不是 `BaseHTTPMiddleware`：
- 需要在不破坏下游 `request.body()` 的前提下旁路读取请求体；
- 纯 ASGI 里包一层 `receive` 就能做到，且不会改变响应类型。

只记录后台管理域（`/system/**`、`/monitor/**`）的 POST/PUT/DELETE/PATCH；
登录日志单独由 `auth.py` 写 `sys_logininfor`。
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from loguru import logger

from app.core.security import get_login_user
from app.database import async_session_factory
from app.models.monitor import SysOperLog

_MAX_CAPTURE = 4000
_SKIP_PREFIXES = ("/monitor/operlog", "/monitor/logininfor")

_TITLES = (
    ("/system/user", "用户管理"),
    ("/system/role", "角色管理"),
    ("/system/menu", "菜单管理"),
    ("/system/dept", "部门管理"),
    ("/system/dict", "字典管理"),
    ("/system/config", "参数管理"),
    ("/system/notice", "通知公告"),
    ("/monitor/jobLog", "调度日志"),
    ("/monitor/job", "定时任务"),
    ("/monitor/server", "服务监控"),
    ("/monitor/cache", "缓存监控"),
    ("/monitor/online", "在线用户"),
    ("/system", "系统管理"),
    ("/monitor", "系统监控"),
)


def _title_for(path: str) -> str:
    for prefix, title in _TITLES:
        if path.startswith(prefix):
            return title
    return "后台操作"


def _business_type(method: str) -> int:
    return {"POST": 1, "PUT": 2, "DELETE": 3}.get(method.upper(), 0)


def _client_ip(scope: dict[str, Any]) -> str:
    headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
    forwarded = headers.get(b"x-forwarded-for", b"").decode("latin-1")
    if forwarded:
        return forwarded.split(",")[0].strip()[:128]
    client = scope.get("client") or ("", 0)
    return str(client[0] or "")[:128]


#: 这些键的内容绝不能进操作日志（改密 / AI Key / 分享 token 等）。
_SENSITIVE_KEYWORDS = (
    "password", "passwd", "newpassword", "oldpassword", "confirmpassword",
    "token", "apikey", "api_key", "secret", "privatekey", "private_key",
)


def _scrub(value):
    """递归脱敏请求/响应 JSON 里的密码、Token、API Key。"""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = str(key).lower().replace("-", "").replace("_", "")
            if any(word in lowered for word in _SENSITIVE_KEYWORDS):
                out[key] = "***"
            else:
                out[key] = _scrub(item)
        return out
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _read_json_message(raw: bytes) -> tuple[str, str]:
    """返回 (脱敏后的文本截断, 错误消息)。"""
    if not raw:
        return "", ""
    text = raw.decode("utf-8", errors="replace")
    msg = ""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            msg = str(obj.get("msg") or obj.get("detail") or "")
        text = json.dumps(_scrub(obj), ensure_ascii=False)
    except Exception:
        pass
    return text[:_MAX_CAPTURE], msg[:500]


async def _write_log(
    *,
    scope: dict[str, Any],
    body: bytes,
    response_body: bytes,
    status_code: int,
    cost_ms: int,
    auth_token: str,
) -> None:
    try:
        user = await get_login_user(auth_token) if auth_token else None
        if not user:
            return
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "")
        query = (scope.get("query_string") or b"").decode("latin-1")
        param_text, _ = _read_json_message(body)
        result_text, err_msg = _read_json_message(response_body)
        if status_code >= 400 and not err_msg:
            err_msg = f"HTTP {status_code}"
        async with async_session_factory() as db:
            db.add(
                SysOperLog(
                    title=_title_for(path)[:50],
                    business_type=_business_type(method),
                    method=f"{method} {path}",
                    request_method=method,
                    operator_type=1 if "admin" in (user.get("roles") or []) else 2,
                    oper_name=str(user.get("user_name") or "")[:50],
                    dept_name="",
                    oper_url=(path + ("?" + query if query else ""))[:255],
                    oper_ip=_client_ip(scope),
                    oper_location="内网",
                    oper_param=param_text,
                    json_result=result_text,
                    status=0 if status_code < 400 else 1,
                    error_msg=err_msg,
                    cost_time=int(cost_ms),
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - 日志失败不能影响已经返回的响应
        logger.warning("[audit] 写操作日志失败: {}", exc)


class OperLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "").upper()
        should_log = (
            method in {"POST", "PUT", "DELETE", "PATCH"}
            and (path.startswith("/system") or path.startswith("/monitor"))
            and not path.startswith(_SKIP_PREFIXES)
        )
        if not should_log:
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        body_chunks: list[bytes] = []
        captured = 0

        async def receive_wrapper():
            nonlocal captured
            message = await receive()
            if message.get("type") == "http.request":
                chunk = message.get("body", b"") or b""
                if captured < _MAX_CAPTURE and chunk:
                    body_chunks.append(chunk[: _MAX_CAPTURE - captured])
                    captured += len(body_chunks[-1])
            return message

        status_code = 500
        response_chunks: list[bytes] = []
        response_captured = 0

        async def send_wrapper(message):
            nonlocal status_code, response_captured
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
            elif message.get("type") == "http.response.body":
                chunk = message.get("body", b"") or b""
                if response_captured < _MAX_CAPTURE and chunk:
                    response_chunks.append(chunk[: _MAX_CAPTURE - response_captured])
                    response_captured += len(response_chunks[-1])
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
            auth = headers.get(b"authorization", b"").decode("latin-1")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            cost_ms = int((time.perf_counter() - started) * 1000)
            asyncio.create_task(
                _write_log(
                    scope=scope,
                    body=b"".join(body_chunks),
                    response_body=b"".join(response_chunks),
                    status_code=status_code,
                    cost_ms=cost_ms,
                    auth_token=token,
                )
            )
