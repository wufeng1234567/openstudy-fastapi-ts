"""资料阅读器的智能分段服务。

目标
----
Word / PDF / Markdown 的标题格式并不统一：有人用 Markdown `#`，有人用
「一、」，有人用「1.2」，还有大量纯文本资料完全没有标题。只靠正则会出现
两种极端：要么整篇只有「全文」一个节点，要么把题号/代码行误判成章节。

本模块采用**规则优先 + LLM 清洗**：

1. 先用 `content_sections` 识别明确标题，能识别就立即返回；
2. 没有可靠标题时，用户可触发 `rebuild_sections(use_llm=True)`：
   LLM 只判断「哪些行是结构标题」和「标题层级」，**不负责生成字符偏移**；
3. 后端拿 LLM 返回的行号，用原文 `_line_offsets` 计算 start/end，避免
   模型编造位置；
4. 仍然没有结果时，按已有 `RagDocumentChunk` 生成「第 N 段」目录，保证
   阅读器永远有可点击的目录。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagDocument, RagDocumentChunk, RagDocumentSection
from app.services.ai.base_client import ChatMessage, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.document_health_service import _line_offsets
from app.services.rag.section_outline import content_sections

MAX_LLM_CHARS = 30000
MAX_SECTIONS = 80


def _clean_title(value: Any, fallback: str = "未命名章节") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.strip("《》\"'“”‘’（）()[]【】")
    return (text or fallback)[:255]


def _rule_sections(raw: str) -> List[Dict[str, Any]]:
    sections = content_sections(raw)
    # `content_sections` 在无标题时会返回一个「全文」兜底；交给 chunk 兜底更可导航。
    if len(sections) <= 1 and str(sections[0].get("title") or "") == "全文":
        return []
    return [
        {
            "index": idx,
            "title": _clean_title(item.get("title")),
            "level": max(1, min(4, int(item.get("level") or 1))),
            "start": max(0, int(item.get("start") or 0)),
            "end": max(0, int(item.get("end") or 0)),
            "source": "rule",
        }
        for idx, item in enumerate(sections)
    ]


def _normalize_sections(
    raw: str,
    items: Sequence[Dict[str, Any]],
    *,
    source: str,
) -> List[Dict[str, Any]]:
    """把 LLM / 规则返回的起点行整理成连续、无重叠的章节。"""
    if not raw:
        return []
    offsets = _line_offsets(raw)
    starts: List[tuple[int, str, int]] = []
    seen_starts: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            line = int(item.get("start_line") or item.get("line") or 1)
        except (TypeError, ValueError):
            continue
        line = max(1, min(len(offsets), line))
        start = offsets[line - 1]
        if start in seen_starts:
            continue
        seen_starts.add(start)
        title = _clean_title(item.get("title"), f"第 {len(starts) + 1} 节")
        try:
            level = int(item.get("level") or 1)
        except (TypeError, ValueError):
            level = 1
        starts.append((start, title, max(1, min(4, level))))
    if not starts:
        return []
    starts.sort(key=lambda item: item[0])
    # 原文最前面如果有封面 / 前言，补一个「开篇」，避免目录点不到开头。
    if starts[0][0] > 0:
        starts.insert(0, (0, "开篇", 1))
    sections: List[Dict[str, Any]] = []
    for index, (start, title, level) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(raw)
        if end <= start:
            continue
        sections.append(
            {
                "index": len(sections),
                "title": title,
                "level": level,
                "start": start,
                "end": end,
                "source": source,
            }
        )
    return sections[:MAX_SECTIONS]


def _parse_llm_sections(raw: str) -> List[Dict[str, Any]]:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    items = payload.get("sections") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _numbered_lines(raw: str) -> tuple[str, int]:
    """给 LLM 的带行号正文；超长时只送前 MAX_LLM_CHARS，避免上下文爆掉。"""
    lines = raw.split("\n")
    counted: list[str] = []
    used = 0
    for index, line in enumerate(lines, start=1):
        piece = f"{index}. {line}"
        if used + len(piece) + 1 > MAX_LLM_CHARS:
            break
        counted.append(piece)
        used += len(piece) + 1
    return "\n".join(counted), len(counted)


async def _llm_sections(db: AsyncSession, user_id: int, raw: str) -> List[Dict[str, Any]]:
    # 超长资料只走规则/chunk 兜底，不把整篇塞给模型；否则既慢又容易截断。
    if len(raw) > MAX_LLM_CHARS:
        return []
    numbered, line_count = _numbered_lines(raw)
    if not numbered:
        return []
    prompt = (
        "你是学习资料的结构整理器。下面是一份带原始行号的学习资料。\n"
        "请判断资料的章节/小节结构，输出严格 JSON，不要 Markdown 代码围栏。\n"
        "要求：\n"
        "1. 只识别真正的结构标题；不要把题号、页码、代码行、表头当标题；\n"
        "2. 如果没有明确标题，按语义把全文分成 4-10 个主题段，标题用简短概括；\n"
        "3. start_line 必须是原文行号（从 1 开始），每个章节的第一行要指向标题行或段落起点；\n"
        "4. 不要改写正文，不要编造原文没有的内容；\n"
        "5. 章节必须覆盖全文，不要重叠。\n\n"
        '输出格式：{"sections":[{"title":"章节标题","level":1,"start_line":1}]}\n\n'
        f"资料共 {line_count} 行（只展示前 {MAX_LLM_CHARS} 字符）：\n{numbered}"
    )
    try:
        response = await chat_with_config(
            db,
            [
                ChatMessage(
                    role="system",
                    content="你只输出严格 JSON，不输出解释或 Markdown 围栏。",
                ),
                ChatMessage(role="user", content=[TextBlock(type="text", text=prompt)]),
            ],
            temperature=0.1,
            max_tokens=2600,
            user_id=int(user_id),
        )
    except Exception as exc:  # noqa: BLE001 - 目录整理失败不阻断原文阅读
        logger.warning(f"[document.section] LLM 目录整理失败: {exc}")
        return []
    return _normalize_sections(
        raw,
        _parse_llm_sections(response.content or ""),
        source="llm",
    )


async def _chunk_sections(db: AsyncSession, doc: RagDocument) -> List[Dict[str, Any]]:
    chunks = (
        await db.execute(
            select(RagDocumentChunk)
            .where(
                RagDocumentChunk.doc_id == int(doc.id),
                RagDocumentChunk.index_version == int(doc.index_version or 1),
            )
            .order_by(RagDocumentChunk.chunk_index.asc())
        )
    ).scalars().all()
    raw = doc.raw_content or ""
    if not chunks or not raw:
        return []
    starts: list[tuple[int, str, int]] = []
    cursor = 0
    for index, chunk in enumerate(chunks):
        content = str(chunk.content or "")
        start = raw.find(content, cursor)
        if start < 0:
            start = min(cursor, len(raw))
        cursor = max(cursor, start + max(1, len(content)))
        title = re.sub(r"【图\d+】", "", content)
        title = re.sub(r"\s+", " ", title).strip()
        title = _clean_title(title[:32], f"第 {index + 1} 段")
        starts.append((start, title or f"第 {index + 1} 段", 1))
    if not starts:
        return []
    if starts[0][0] > 0:
        starts.insert(0, (0, "开篇", 1))
    result: List[Dict[str, Any]] = []
    for index, (start, title, level) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(raw)
        if end <= start:
            continue
        result.append(
            {
                "index": len(result),
                "title": title,
                "level": level,
                "start": start,
                "end": end,
                "source": "chunk",
            }
        )
    return result[:MAX_SECTIONS]


def _serialize(section: RagDocumentSection) -> Dict[str, Any]:
    return {
        "index": int(section.section_index),
        "title": section.title,
        "level": int(section.level or 1),
        "start": int(section.start_offset or 0),
        "end": int(section.end_offset or 0),
        "source": section.source or "rule",
    }


async def ensure_sections(
    db: AsyncSession,
    user_id: int,
    doc: RagDocument,
    *,
    force: bool = False,
    use_llm: bool = False,
) -> tuple[List[Dict[str, Any]], bool]:
    """读取或生成章节结构，返回 `(sections, needs_ai_outline)`。"""
    existing = (
        await db.execute(
            select(RagDocumentSection)
            .where(
                RagDocumentSection.doc_id == int(doc.id),
                RagDocumentSection.index_version == int(doc.index_version or 1),
            )
            .order_by(RagDocumentSection.section_index.asc())
        )
    ).scalars().all()
    if existing and not force:
        return [_serialize(item) for item in existing], False

    raw = str(doc.raw_content or "")
    sections = _rule_sections(raw)
    if use_llm and (force or len(sections) < 2):
        llm = await _llm_sections(db, int(user_id), raw)
        if len(llm) >= 2:
            sections = llm
    if not sections:
        sections = await _chunk_sections(db, doc)
    if not sections:
        sections = [
            {
                "index": 0,
                "title": "全文",
                "level": 1,
                "start": 0,
                "end": len(raw),
                "source": "chunk",
            }
        ]
    # 保证连续覆盖（规则分段可能因为标题行首尾出现缺口）。
    sections = sorted(sections, key=lambda item: int(item["start"]))
    for index, item in enumerate(sections):
        item["index"] = index
        if index + 1 < len(sections):
            item["end"] = max(int(item["start"]), int(sections[index + 1]["start"]))
        else:
            item["end"] = max(int(item["start"]), len(raw))

    await db.execute(
        delete(RagDocumentSection).where(
            RagDocumentSection.doc_id == int(doc.id),
            RagDocumentSection.index_version == int(doc.index_version or 1),
        )
    )
    now = datetime.now()
    for item in sections:
        db.add(
            RagDocumentSection(
                user_id=int(user_id),
                kb_id=int(doc.kb_id),
                doc_id=int(doc.id),
                index_version=int(doc.index_version or 1),
                section_index=int(item["index"]),
                level=int(item["level"]),
                title=str(item["title"])[:255],
                start_offset=int(item["start"]),
                end_offset=int(item["end"]),
                source=str(item.get("source") or "rule"),
                update_time=now,
            )
        )
    await db.commit()
    # 规则分段可以作为兜底，但按钮仍保留：用户可以随时让 LLM 按内容重新清洗标题。
    needs_ai = len(sections) <= 1 or not all(
        str(item.get("source") or "") == "llm" for item in sections
    )
    return sections, needs_ai


async def rebuild_sections(db: AsyncSession, user_id: int, doc: RagDocument) -> List[Dict[str, Any]]:
    sections, _ = await ensure_sections(db, user_id, doc, force=True, use_llm=True)
    return sections


__all__ = [
    "MAX_LLM_CHARS",
    "ensure_sections",
    "rebuild_sections",
]
