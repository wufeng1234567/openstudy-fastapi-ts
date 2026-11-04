"""操作日志 / 登录日志的写入辅助。

原则：**日志永远不能反向影响业务**。所有写入都吞异常，最多打印一条 warning；
数据库不可用时业务请求仍应成功。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import SysLogininfor


def client_ip(request: Optional[Request]) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()[:128]
    return (request.client.host if request.client else "")[:128]


def parse_user_agent(ua: str) -> tuple[str, str]:
    """极简 UA 解析（不引入 user-agents 依赖）：浏览器 / 操作系统。"""
    text = (ua or "").lower()
    if "edg/" in text:
        browser = "Edge"
    elif "chrome/" in text:
        browser = "Chrome"
    elif "firefox/" in text:
        browser = "Firefox"
    elif "safari/" in text:
        browser = "Safari"
    elif "postman" in text:
        browser = "Postman"
    else:
        browser = "未知"
    if "windows" in text:
        os_name = "Windows"
    elif "android" in text:
        os_name = "Android"
    elif "iphone" in text or "ipad" in text:
        os_name = "iOS"
    elif "mac os" in text or "macintosh" in text:
        os_name = "macOS"
    elif "linux" in text:
        os_name = "Linux"
    else:
        os_name = "未知"
    return browser, os_name


async def record_login(
    db: AsyncSession,
    *,
    user_name: str,
    status: int,
    msg: str,
    request: Optional[Request] = None,
) -> None:
    """记录一条登录日志；失败只告警，不影响登录响应。"""
    try:
        ua = request.headers.get("user-agent", "") if request else ""
        browser, os_name = parse_user_agent(ua)
        db.add(
            SysLogininfor(
                user_name=(user_name or "")[:50],
                ipaddr=client_ip(request),
                login_location="内网" if client_ip(request).startswith(("127.", "192.168.", "10.")) else "外网",
                browser=browser,
                os=os_name,
                status=int(status),
                msg=(msg or "")[:255],
                login_time=datetime.now(),
            )
        )
        await db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[audit] 写登录日志失败: {}", exc)
