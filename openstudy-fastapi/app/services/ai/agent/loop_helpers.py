"""Agent loop 的小型纯函数与事件文案工具。

从 `loop.py` 拆出，降低单文件体积；不依赖数据库/LLM，可独立测试。
"""

from __future__ import annotations

import json
from typing import Any, Dict

REASONING_DELTA_KEYS = ("reasoning_content", "reasoning")


def detect_user_language(text: str) -> str:
    """粗略判断用户消息语言（只为把「结论语言」透传给子代理）。"""
    s = text or ""
    if not s:
        return "中文"
    han = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    return "中文" if (han / max(1, len(s))) >= 0.15 else "English"


def text_of(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def reasoning_of(chunk: Any) -> str:
    """从流式分片里取「深度思考正文」，取不到返回空串。"""
    kwargs = getattr(chunk, "additional_kwargs", None)
    if not isinstance(kwargs, dict):
        return ""
    for key in REASONING_DELTA_KEYS:
        value = kwargs.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(payload)


def safe_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """给前端看的参数：长字段截断（`questions` 可能上万字）。"""
    safe: Dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key.startswith("_"):
            continue
        if isinstance(value, str) and len(value) > 200:
            safe[key] = value[:200] + f"…（共 {len(value)} 字）"
        else:
            safe[key] = value
    return safe


def tool_start_message(tool_name: str, params: Dict[str, Any]) -> str:
    """把工具调用翻译成用户看得懂的一句话。"""
    action = str(params.get("action") or "")
    bank = params.get("bank_name") or (f"ID={params.get('bank_id')}" if params.get("bank_id") else "")
    if tool_name == "bank_manage":
        return {
            "list": "正在查询你的题库…",
            "detail": f"正在查看题库{bank}的详情…",
            "create": f"正在创建题库「{params.get('bank_name') or ''}」…",
            "update": f"正在修改题库{bank}…",
            "delete": f"正在删除题库{bank}…",
            "delete_by_name": f"正在删除题库「{params.get('bank_name') or ''}」…",
        }.get(action, "正在处理题库…")
    if tool_name == "question_manage":
        if action == "batch_import":
            qs = params.get("questions")
            n = len(qs) if isinstance(qs, list) else None
            cnt = f"{n} 道" if n else ""
            target = f"到「{bank}」" if bank else ""
            return f"正在批量导入{cnt}题目{target}…"
        return {
            "list": f"正在查询「{bank}」的题目…",
            "detail": "正在查看题目详情…",
            "search": "正在搜索题目…",
            "create": "正在创建题目…",
            "update": "正在修改题目…",
            "delete": "正在删除题目…",
            "delete_many": "正在批量删除题目…",
            "clear_questions": f"正在清空「{bank}」的题目…",
        }.get(action, "正在处理题目…")
    return f"正在执行 {tool_name}…"


def friendly_llm_error(error: Exception) -> str:
    """把上游异常翻译成用户能看懂、且可行动的一句话。"""
    text = str(error)
    lowered = text.lower()
    if "管理员" in text or "我的模型" in text or "系统管理" in text:
        return text
    if "tools" in lowered and ("not support" in lowered or "unsupported" in lowered):
        return (
            "当前模型不支持工具调用（Function Calling），Agent 无法工作。"
            "请在模型下拉框里切换到 deepseek-flash / deepseek-v4-pro 等官方模型。"
        )
    if "api_key" in lowered or "401" in lowered or "unauthorized" in lowered or "authentication" in lowered:
        return (
            "模型凭据无效或未配置。\n"
            "• 用的是系统官方模型：请联系【管理员】进入后台「系统管理 → AI 模型配置」填写该模型的 API Key；\n"
            "• 用的是你自己添加的模型：请到「个人中心 → 我的模型」补全有效的 API Key。"
        )
    if "rate limit" in lowered or "429" in lowered:
        return "模型请求过于频繁（限流），请稍后再试。"
    if "timeout" in lowered or "timed out" in lowered:
        return "模型响应超时，请重试；文档较大时可以只上传其中一部分。"
    return f"模型调用失败：{text}"


__all__ = [
    "REASONING_DELTA_KEYS",
    "detect_user_language",
    "text_of",
    "reasoning_of",
    "dumps",
    "safe_params",
    "tool_start_message",
    "friendly_llm_error",
]
