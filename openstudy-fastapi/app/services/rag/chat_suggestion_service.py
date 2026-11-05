"""新会话首页的提问推测：优先读用户资料，没有资料时给可体验的起步问题。

这个接口只负责“问什么”，不生成答案：
  · 有资料：把最近几份资料的文件名、主题、章节/正文摘要交给 LLM，让它生成
    用户真的可能问出口的问题；
  · 没有资料：返回一组“从零开始”的体验问题，不伪造用户有资料；
  · 刚上传资料：前端把 docId 传回来，重新生成只围绕这份资料的提问。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagDocument
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config

STARTER_SUGGESTIONS: List[Dict[str, Any]] = [
    {
        "label": "从零开始体验",
        "text": "我还没有资料，先用一个简单的概率论例子带我体验一下你能怎么教",
        "desc": "没有资料也可以直接开始",
        "action": "chat",
    },
    {
        "label": "上传第一份资料",
        "text": "上传一份课件或笔记，帮我找出重点并整理成可以练的题",
        "desc": "支持 Word / PDF / Markdown / TXT",
        "action": "upload",
    },
    {
        "label": "看看我能学什么",
        "text": "你能根据我的学习资料帮我做什么？先给我看一个完整的使用示例",
        "desc": "先了解能力，再决定从哪开始",
        "action": "chat",
    },
    {
        "label": "排一个学习计划",
        "text": "如果你来安排，你会怎么根据我的资料帮我制定一周学习计划？",
        "desc": "先聊目标，再建计划",
        "action": "chat",
    },
]

_CACHE: Dict[tuple[int, Optional[int]], tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL = 600


def _clean(value: Any, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _extract_json_array(text: str) -> list:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        left, right = raw.find("["), raw.rfind("]")
        if left < 0 or right <= left:
            raise ValueError("模型没有返回可解析的提问列表")
        payload = json.loads(raw[left : right + 1])
    if not isinstance(payload, list):
        raise ValueError("提问列表不是 JSON 数组")
    return payload


def _normalize_suggestions(raw: list, docs: List[RagDocument]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            text = _clean(item, 300)
        elif isinstance(item, dict):
            text = _clean(item.get("text") or item.get("question") or item.get("label"), 300)
        else:
            continue
        if not text:
            continue
        result.append(
            {
                "label": _clean(item.get("label") if isinstance(item, dict) else "", 40) or text[:40],
                "text": text,
                "desc": _clean(item.get("desc") if isinstance(item, dict) else "", 90)
                or (f"基于《{docs[0].file_name}》" if docs else ""),
                "action": "chat",
            }
        )
    # LLM 偶尔只给 2~3 条；用资料名兜底到 4 条，不编造具体知识点。
    fallback = _fallback_from_docs(docs)
    for item in fallback:
        if len(result) >= 4:
            break
        if all(item["text"] != existing["text"] for existing in result):
            result.append(item)
    return result[:4]


def _fallback_from_docs(docs: List[RagDocument]) -> List[Dict[str, Any]]:
    if not docs:
        return STARTER_SUGGESTIONS
    first = docs[0].file_name or "这份资料"
    return [
        {
            "label": "先读重点",
            "text": f"《{first}》里最值得先学的重点是什么？帮我按顺序理一下",
            "desc": f"基于《{first}》",
            "action": "chat",
        },
        {
            "label": "帮我出题",
            "text": f"根据《{first}》的内容，帮我出 3 道由浅入深的练习题",
            "desc": f"基于《{first}》",
            "action": "chat",
        },
        {
            "label": "查漏补缺",
            "text": f"如果我要掌握《{first}》，最容易卡住的地方在哪里？",
            "desc": f"基于《{first}》",
            "action": "chat",
        },
        {
            "label": "做学习计划",
            "text": "根据我最近的资料，帮我安排一个每天 30 分钟的 7 天学习计划",
            "desc": "根据你的资料生成",
            "action": "chat",
        },
    ]


async def get_chat_suggestions(
    db: AsyncSession,
    user_id: int,
    *,
    doc_id: Optional[int] = None,
) -> Dict[str, Any]:
    cache_key = (int(user_id), int(doc_id) if doc_id else None)
    # 新资料上传后，旧的“全量资料”提问缓存立即失效，下一次新会话会读到它。
    if doc_id:
        _CACHE.pop((int(user_id), None), None)
    cached = _CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    query = select(RagDocument).where(RagDocument.user_id == int(user_id))
    if doc_id:
        query = query.where(RagDocument.id == int(doc_id))
    else:
        query = query.order_by(RagDocument.create_time.desc(), RagDocument.id.desc()).limit(8)
    docs = (await db.execute(query)).scalars().all()
    if not docs:
        result = {"mode": "empty", "docCount": 0, "suggestions": STARTER_SUGGESTIONS}
        _CACHE[cache_key] = (time.time(), result)
        return result

    snippets: List[str] = []
    for doc in docs[:4]:
        raw = _clean(doc.raw_content, 1800)
        note = _clean(doc.user_note, 80)
        header = f"资料：{doc.file_name}" + (f"（{note}）" if note else "")
        snippets.append(f"{header}\n{raw}")
    prompt = (
        "你是 OpenStudy 的学习助手。请根据下面的用户资料，生成 4 个用户进入新会话时最可能问的问题。\n"
        "要求：\n"
        "1. 必须是自然口语，像学生真的会问出口的一句话；不要写功能菜单名；\n"
        "2. 至少 2 个问题要结合资料中的具体主题、概念或内容；\n"
        "3. 不要编造资料里不存在的事实；\n"
        "4. 输出严格 JSON 数组，每个元素包含 label、text、desc；\n"
        "5. text 是直接发送给助手的问题，desc 是 15 字以内的来源提示。\n\n"
        + "\n\n".join(snippets)
    )
    try:
        messages = [
            ChatMessage(role="system", content="你只输出 JSON 数组，不要 Markdown 代码围栏和解释。"),
            ChatMessage(role="user", content=[TextBlock(type="text", text=prompt)]),
        ]
        response = await chat_with_config(
            db,
            messages,
            temperature=0.65,
            max_tokens=1400,
            user_id=int(user_id),
        )
        suggestions = _normalize_suggestions(_extract_json_array(response.content or ""), list(docs))
        result = {"mode": "documents", "docCount": len(docs), "suggestions": suggestions}
    except Exception:
        result = {
            "mode": "documents",
            "docCount": len(docs),
            "suggestions": _fallback_from_docs(list(docs)),
        }
    _CACHE[cache_key] = (time.time(), result)
    return result


__all__ = ["STARTER_SUGGESTIONS", "get_chat_suggestions"]
