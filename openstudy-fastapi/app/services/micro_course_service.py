"""资料变微课：把一份文档的章节结构，变成一条可以「一站一站学」的路径。

不是让模型凭空写课程 —— 站点全部来自原文标题与正文：
· 每一站 = 原始资料里的一个一级章节（没有标题时按段落切）；
· 每站的「导读」是原文摘录，不是模型总结；
· 每站的检查点是「合上资料复述」，前端记录完成状态；
· 相关题库按资料科目 / 文件名匹配，只作为「去练习」入口，不伪造题目。

这样用户看到的是：这份资料本来讲了什么 + 我学到哪了，而不是一份看了就忘的
AI 总结。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionBank
from app.models.rag import RagDocument
from app.services.outline_tree_service import _extract_headings

MAX_STATIONS = 8
EXCERPT_LIMIT = 520


def _strip_markdown(text: str) -> str:
    s = text or ""
    s = re.sub(r"```.*?```", "", s, flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]*)\*", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _excerpt(lines: List[str], start: int, end: int) -> str:
    body = "\n".join(lines[start:end]).strip()
    body = _strip_markdown(body)
    body = re.sub(r"\s+", " ", body)
    if len(body) > EXCERPT_LIMIT:
        body = body[: EXCERPT_LIMIT - 1] + "…"
    return body


def _fallback_stations(raw: str) -> List[Dict[str, Any]]:
    """没有标题时的兜底：按段落切，每段 800~1200 字，最多 6 站。"""
    text = _strip_markdown(raw)
    chunks: List[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > 1000 and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    stations = []
    for idx, chunk in enumerate(chunks[:6]):
        stations.append(
            {
                "id": f"station-{idx + 1}",
                "index": idx + 1,
                "title": f"第 {idx + 1} 段",
                "summary": chunk[: EXCERPT_LIMIT - 1] + ("…" if len(chunk) > EXCERPT_LIMIT else ""),
                "points": [],
                "minutes": max(3, min(12, len(chunk) // 180 + 3)),
                "checkpoint": "合上资料，用 3 句话复述这一段在讲什么。",
            }
        )
    return stations


def build_stations(raw: str) -> tuple[List[Dict[str, Any]], bool]:
    heads = _extract_headings(raw or "")
    if not heads:
        return _fallback_stations(raw or ""), False

    levels = [h["level"] for h in heads]
    # 数字编号（`1. 智能体定义`）在技术文档里常是正文要点，不是章节。
    # 只要文档里存在 Markdown / 中文序号标题，就只在它们里面选「站」；
    # 整份文档只有数字标题时，才退回用数字标题（避免把纯编号笔记切碎）。
    prose_heads = [h for h in heads if h.get("kind") in ("md", "cn")]
    if len(prose_heads) >= 2:
        heads = prose_heads
        levels = [h["level"] for h in heads]

    top_level = min(levels)
    tops = [h for h in heads if h["level"] == top_level]

    # 很多文档第一行是文档自己的标题（`# 智能体基础概念`），真正的章节是
    # 下一层的 `## 一、...`。只有一个顶层标题时，自动下钻一层，否则整份资料
    # 会被压成「1 站」，微课就失去意义了。
    station_level = top_level
    if len(tops) == 1:
        deeper = [h for h in heads if h["level"] > top_level]
        if deeper:
            station_level = min(h["level"] for h in deeper)
            tops = [h for h in heads if h["level"] == station_level]
            if len(tops) <= 1:
                # 再下钻一层仍只有一节，接受单站，不强行拆
                pass

    if not tops:
        return _fallback_stations(raw or ""), False

    lines = (raw or "").split("\n")
    stations: List[Dict[str, Any]] = []
    for idx, head in enumerate(tops[:MAX_STATIONS]):
        start_line = max(0, int(head["line"]) - 1)
        # 到「下一个同级或更高级标题」为止
        next_lines = [
            int(h["line"])
            for h in heads
            if int(h["line"]) > int(head["line"]) and int(h["level"]) <= station_level
        ]
        end_line = (min(next_lines) - 1) if next_lines else len(lines)
        title = str(head["title"] or f"第 {idx + 1} 节")
        # 子标题作为「这一节的要点」列出来
        points = [
            str(h["title"])
            for h in heads
            if int(h["line"]) > int(head["line"]) and int(h["line"]) <= end_line
        ][:6]
        summary = _excerpt(lines, start_line + 1, end_line)
        stations.append(
            {
                "id": f"station-{idx + 1}",
                "index": idx + 1,
                "title": title,
                "summary": summary or "（这一节正文较短，建议直接打开原文阅读）",
                "points": points,
                "minutes": max(3, min(15, len(summary) // 120 + 3)),
                "checkpoint": f"合上资料，用 3 句话说明「{title}」讲了什么；再回答：它和上一节是什么关系？",
            }
        )
    return stations, len(tops) > MAX_STATIONS


def _doc_keywords(file_name: str) -> List[str]:
    stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", file_name or "")
    parts = re.split(r"[\s_\-—（）()【】\[\]、,，.。]+", stem)
    return [p for p in parts if len(p) >= 2][:4]


async def _related_banks(db: AsyncSession, user_id: int, doc: RagDocument) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(QuestionBank.id, QuestionBank.bank_name, QuestionBank.subject).where(
                QuestionBank.user_id == int(user_id),
                QuestionBank.status == "0",
            )
        )
    ).all()
    keywords = _doc_keywords(doc.file_name or "")
    matched: List[Dict[str, Any]] = []
    for bank_id, bank_name, subject in rows:
        name = bank_name or ""
        score = 0
        if doc.subject and subject and subject == doc.subject:
            score += 2
        for kw in keywords:
            if kw and kw in name:
                score += 3
        if score:
            matched.append(
                {
                    "id": int(bank_id),
                    "name": name,
                    "subject": subject or "",
                    "score": score,
                }
            )
    matched.sort(key=lambda b: (-b["score"], b["id"]))
    return matched[:3]


async def build_micro_course(
    db: AsyncSession, user_id: int, doc: RagDocument
) -> Dict[str, Any]:
    raw = doc.raw_content or ""
    stations, truncated = build_stations(raw)
    banks = await _related_banks(db, user_id, doc)
    total_minutes = sum(int(s["minutes"]) for s in stations)
    return {
        "document": {
            "id": int(doc.id),
            "fileName": doc.file_name or "",
            "subject": doc.subject or "",
            "materialType": doc.material_type or "",
            "wordCount": len(re.sub(r"\s+", "", raw)),
            "chunkCount": int(getattr(doc, "chunk_count", 0) or 0),
            "hasOutline": bool(stations) and stations[0]["title"] != "第 1 段",
            "truncated": truncated,
        },
        "overview": {
            "stationCount": len(stations),
            "totalMinutes": total_minutes,
            "estimatedSessions": max(1, round(total_minutes / 25)),
        },
        "stations": stations,
        "relatedBanks": banks,
    }


__all__ = ["build_micro_course"]
