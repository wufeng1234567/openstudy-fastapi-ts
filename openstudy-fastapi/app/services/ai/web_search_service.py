"""DeepSeek 官方 Search / Fetch 服务。

为什么单独成层
==============
`deepseek-flash` 的 `/chat/completions` **没有** web_search 参数；联网搜索是官方
独立的 Search / Fetch API（与聊天接口共用同一个 `DEEPSEEK_API_KEY`）：

    POST https://api.deepseek.com/v1/tools/search
    POST https://api.deepseek.com/v1/tools/fetch

本层只负责「调用真实搜索/抓取接口并把结果归一化」：
  · 返回的每一条结果都必须带真实 `url`，前端据此渲染可点击索引；
  · 失败如实抛 `WebSearchError`，绝不编造链接或假装联网成功；
  · 不落库、不调 LLM，知识库导入和 Agent 工具都复用这一层。

⚠️ 这不是已经被废弃的 DeepSeek 网页版免费反代（chat.deepseek.com 登录 +
PoW/WASM + 浏览器扩展）。本服务只走官方公开 API，不依赖任何浏览器登录态。
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.ai import db_config

SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"

DEFAULT_SEARCH_COUNT = 6
MAX_SEARCH_COUNT = 10
MAX_FETCH_CHARS = 120_000
DEFAULT_FETCH_CHARS = 24_000
REQUEST_TIMEOUT = 45.0


class WebSearchError(RuntimeError):
    """搜索/抓取失败（消息是直接给用户和模型看的人话）。"""


def _valid_key(value: Optional[str]) -> bool:
    text = (value or "").strip()
    return len(text) >= 20 and text.lower().startswith("sk-")


async def resolve_api_key(db: AsyncSession, user_id: Optional[int] = None) -> str:
    """解析官方 DeepSeek Key：优先系统 deepseek-flash 配置，fallback .env。

    ⚠️ Search/Fetch 只部署在官方 `api.deepseek.com`。若用户选中的是自建网关
    （base_url 不是 deepseek.com），不能把网关 key 发到官方端点，继续回退系统配置。
    """
    candidates = []
    try:
        candidates.append(
            await db_config.resolve_config(
                db, provider="deepseek", model="deepseek-flash", user_id=user_id
            )
        )
    except Exception:  # noqa: BLE001 - 配置缺失时继续尝试默认/环境变量
        pass
    try:
        candidates.append(await db_config.get_default_config(db, user_id))
    except Exception:  # noqa: BLE001
        pass

    for cfg in candidates:
        if cfg is None:
            continue
        base = (getattr(cfg, "base_url", "") or "").lower()
        if base and "deepseek.com" not in base:
            continue
        key = (getattr(cfg, "api_key", "") or "").strip()
        if _valid_key(key):
            return key

    env_key = (getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
    if _valid_key(env_key):
        return env_key
    raise WebSearchError(
        "还没有可用的 DeepSeek 官方 API Key，网页搜索暂时不可用。"
        "请在模型配置里填写 deepseek-flash 的官方 Key。"
    )


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _validate_public_url(url: str) -> str:
    """只允许公网 http(s) 地址；拒绝 localhost / 内网 / 元数据地址。

    官方 Fetch 是在 DeepSeek 服务器侧抓取，本来也访问不到本机；但用户把
    `http://127.0.0.1:...` 粘进来时应在入口就给出明确错误，而不是把内网地址
    发给第三方。
    """
    value = (url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise WebSearchError("网址格式不对，请提供 http:// 或 https:// 开头的公开网页链接。")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise WebSearchError("网址里没有识别到域名。")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise WebSearchError("不能抓取本机或内网地址，请换一个公开网页。")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise WebSearchError("不能抓取内网或保留地址，请换一个公开网页。")
    except ValueError:
        pass
    if host == "169.254.169.254" or host.endswith(".internal"):
        raise WebSearchError("不能抓取云元数据或内网地址，请换一个公开网页。")
    return value


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # 官方返回 ISO 时间：前端只显示日期，避免长串时区把卡片撑开。
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else text[:19]


def _site_of(item: Dict[str, Any], url: str) -> str:
    return str(item.get("site_name") or "").strip() or _host_of(url) or "网页"


def _map_result(item: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    url = str(item.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    title = str(item.get("title") or "").strip() or _site_of(item, url)
    snippet = str(item.get("snippet") or item.get("summary") or "").strip()
    summary = str(item.get("summary") or "").strip()
    return {
        "index": index,
        "id": f"W{index}",
        "title": title,
        "url": url,
        "snippet": snippet,
        "summary": summary,
        "siteName": _site_of(item, url),
        "siteIcon": str(item.get("site_icon") or "").strip(),
        "date": _normalize_date(item.get("date")),
        "authority": item.get("authority"),
    }


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.status_code == 200:
        return
    mapping = {
        400: f"{action}请求参数不被官方接口接受",
        401: "DeepSeek 官方 API Key 无效或已过期",
        402: "DeepSeek 账户余额不足，网页搜索暂时不可用",
        403: "DeepSeek 官方接口拒绝访问（请检查 Key 权限）",
        404: "要抓取的网页不存在或无法访问",
        429: "网页搜索请求太频繁，请稍后再试",
    }
    reason = mapping.get(response.status_code, f"官方{action}接口返回 HTTP {response.status_code}")
    raise WebSearchError(reason)


async def search_web(
    db: AsyncSession,
    query: str,
    *,
    count: int = DEFAULT_SEARCH_COUNT,
    original_question: str = "",
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """调用官方 Search 接口，返回真实、可直接引用的网页结果。"""
    text = (query or "").strip()
    if not text:
        raise WebSearchError("搜索关键词不能为空。")
    limit = max(1, min(int(count or DEFAULT_SEARCH_COUNT), MAX_SEARCH_COUNT))
    key = await resolve_api_key(db, user_id)
    payload = {
        "query": text[:500],
        "count": limit,
        "ori_question": (original_question or text)[:1000],
        "need_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(
                SEARCH_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise WebSearchError("网页搜索超时，请稍后再试。") from exc
    except httpx.HTTPError as exc:
        raise WebSearchError(f"网页搜索网络异常：{exc}") from exc

    _raise_for_status(response, "搜索")
    try:
        body = response.json()
    except ValueError as exc:
        raise WebSearchError("官方搜索接口返回了无法解析的内容。") from exc

    results: List[Dict[str, Any]] = []
    for item in body.get("results") or []:
        if not isinstance(item, dict):
            continue
        mapped = _map_result(item, len(results) + 1)
        if mapped:
            results.append(mapped)
    return {
        "query": text,
        "results": results,
        "count": len(results),
        "provider": "deepseek-search",
        "searchedAt": datetime.now().isoformat(timespec="seconds"),
    }


async def fetch_web_page(
    db: AsyncSession,
    url: str,
    *,
    max_chars: int = DEFAULT_FETCH_CHARS,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """调用官方 Fetch 接口，把单个网页转成 Markdown 文本。"""
    target = _validate_public_url(url)
    key = await resolve_api_key(db, user_id)
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(
                FETCH_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"url": target},
            )
    except httpx.TimeoutException as exc:
        raise WebSearchError("网页抓取超时，请稍后再试。") from exc
    except httpx.HTTPError as exc:
        raise WebSearchError(f"网页抓取网络异常：{exc}") from exc

    _raise_for_status(response, "抓取")
    try:
        body = response.json()
    except ValueError as exc:
        raise WebSearchError("官方抓取接口返回了无法解析的内容。") from exc

    content = str(body.get("content") or "").strip()
    if not content:
        raise WebSearchError("这个网页没有抓取到可读正文，可能被站点限制或需要登录。")
    limit = max(1000, min(int(max_chars or DEFAULT_FETCH_CHARS), MAX_FETCH_CHARS))
    clipped = content[:limit]
    title = str(body.get("title") or "").strip() or _host_of(target) or "网页资料"
    return {
        "url": str(body.get("url") or target).strip() or target,
        "requestedUrl": target,
        "title": title,
        "content": clipped,
        "contentLength": len(clipped),
        "truncated": len(content) > limit,
        "siteName": _site_of(body, target),
        "fetchedAt": datetime.now().isoformat(timespec="seconds"),
    }


__all__ = [
    "WebSearchError",
    "resolve_api_key",
    "search_web",
    "fetch_web_page",
]
