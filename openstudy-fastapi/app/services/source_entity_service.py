"""从题库/图片/网页等来源抽取知识点、实体与关系。

题库不把题干本身当图节点；这里让 LLM 读题目正文与解析，抽成
`知识点/实体 + 关系`，供学习建议引用。结果按内容哈希做内存缓存。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionMain

_CACHE: Dict[str, tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL = 600


def _strip_json(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    return value[start : end + 1] if start >= 0 and end > start else value


def _key(source_type: str, source_id: int, text: str) -> str:
    raw = f"{source_type}:{source_id}:{text[:4000]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
    entities = []
    for item in payload.get("entities") or payload.get("nodes") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        entities.append(
            {
                "name": name[:80],
                "type": str(item.get("type") or "概念")[:32],
                "description": str(item.get("description") or "")[:240],
            }
        )
    relations = []
    for item in payload.get("relations") or payload.get("edges") or []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target:
            continue
        relations.append(
            {
                "source": source[:80],
                "target": target[:80],
                "type": str(item.get("type") or "相关")[:32],
                "description": str(item.get("description") or "")[:240],
            }
        )
    return {"entities": entities[:30], "relations": relations[:40]}


async def extract_entities_from_text(
    db: AsyncSession,
    *,
    user_id: int,
    source_type: str,
    source_id: int,
    source_name: str,
    text: str,
    use_llm: bool = True,
) -> Dict[str, Any]:
    clean = str(text or "").strip()
    if not clean:
        return {"entities": [], "relations": [], "degraded": {"empty": True}}
    key = _key(source_type, source_id, clean)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    if not use_llm:
        return {"entities": [], "relations": [], "degraded": {"llmDisabled": True}}
    try:
        from app.services.ai.base_client import ChatMessage
        from app.services.ai.db_config import chat_with_config

        prompt = f"""你是一个知识图谱抽取器。请从下面的「{source_name}」内容中抽取知识点、实体和它们的关系。
不要把题目原文、选项或整段话当成实体；实体应是可学习的概念/定理/方法/术语。
这是题库来源：请做“知识点总结”，只保留能覆盖这组题目的核心知识点，最多 12 个，不要逐题罗列实体。
只依据给定内容，不要靠常识补关系。
输出严格 JSON：
{{"entities":[{{"name":"实体名","type":"概念","description":"一句话解释"}}],"relations":[{{"source":"实体1","target":"实体2","type":"前置/包含/应用/相关","description":"依据"}}]}}
来源类型：{source_type}
内容：
{clean[:12000]}
"""
        response = await chat_with_config(
            db,
            [ChatMessage(role="user", content=prompt)],
            temperature=0.2,
            max_tokens=2600,
            thinking=False,
            user_id=int(user_id),
        )
        payload = json.loads(_strip_json(response.content or ""))
        result = {**_normalize(payload if isinstance(payload, dict) else {}), "degraded": {}}
        _CACHE[key] = (now, result)
        return result
    except Exception as exc:  # noqa: BLE001
        return {"entities": [], "relations": [], "degraded": {"error": str(exc)[:160]}}


async def extract_bank_entities(
    db: AsyncSession,
    *,
    user_id: int,
    bank_id: int,
    limit: int = 200,
    chunk_size: int = 20,
    use_llm: bool = True,
) -> Dict[str, Any]:
    """按题目块抽取后合并，避免大题库一次塞进模型上下文。"""
    rows = (
        await db.execute(
            select(QuestionMain.question_text, QuestionMain.analysis)
            .where(QuestionMain.bank_id == int(bank_id), QuestionMain.status == "0")
            .order_by(QuestionMain.id.asc())
            .limit(max(1, min(int(limit or 200), 300)))
        )
    ).all()
    chunk_size = max(1, min(int(chunk_size or 20), 40))
    chunks = [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]
    texts = [
        "\n\n".join(
            f"题目：{str(row.question_text or '')}\n解析：{str(row.analysis or '')}"
            for row in chunk
            if str(row.question_text or "").strip()
        )
        for chunk in chunks
    ]
    texts = [text for text in texts if text]
    all_entities: Dict[str, Dict[str, Any]] = {}
    all_relations: Dict[tuple, Dict[str, Any]] = {}
    entity_hits: Dict[str, int] = {}
    relation_hits: Dict[tuple, int] = {}
    errors: List[str] = []

    async def _extract_chunk(text: str) -> Dict[str, Any]:
        # 每块独立 session，避免多个并发 LLM 调用共享同一个 AsyncSession。
        from app.database import async_session_factory

        async with async_session_factory() as chunk_db:
            return await extract_entities_from_text(
                chunk_db,
                user_id=user_id,
                source_type="bank",
                source_id=int(bank_id),
                source_name=f"题库 #{bank_id}",
                text=text,
                use_llm=use_llm,
            )

    if use_llm and len(texts) > 1:
        semaphore = asyncio.Semaphore(3)

        async def _limited(text: str) -> Dict[str, Any]:
            async with semaphore:
                return await _extract_chunk(text)

        results = await asyncio.gather(*(_limited(text) for text in texts))
    else:
        results = []
        for text in texts:
            async with db.begin_nested():
                results.append(
                    await extract_entities_from_text(
                        db,
                        user_id=user_id,
                        source_type="bank",
                        source_id=int(bank_id),
                        source_name=f"题库 #{bank_id}",
                        text=text,
                        use_llm=use_llm,
                    )
                )

    for result in results:
        if result.get("degraded", {}).get("error"):
            errors.append(str(result["degraded"]["error"]))
        for item in result.get("entities") or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            entry = all_entities.setdefault(name, {**item, "mentionCount": 0})
            entry["mentionCount"] = int(entry.get("mentionCount") or 0) + 1
            if len(str(item.get("description") or "")) > len(str(entry.get("description") or "")):
                entry["description"] = item.get("description") or ""
            entity_hits[name] = entity_hits.get(name, 0) + 1
        for item in result.get("relations") or []:
            key = (str(item.get("source") or ""), str(item.get("target") or ""), str(item.get("type") or ""))
            all_relations[key] = item
            relation_hits[key] = relation_hits.get(key, 0) + 1

    # 题库是“总结型”来源：按跨题块命中次数和关系度排序，只保留核心知识点，
    # 不把每道题抽出的实体全部堆进图谱。
    relation_degree: Dict[str, int] = {}
    for source, target, _ in all_relations:
        relation_degree[source] = relation_degree.get(source, 0) + 1
        relation_degree[target] = relation_degree.get(target, 0) + 1
    ranked_entities = sorted(
        all_entities.values(),
        key=lambda item: (
            int(item.get("mentionCount") or 0) * 2 + relation_degree.get(str(item.get("name") or ""), 0),
            len(str(item.get("description") or "")),
        ),
        reverse=True,
    )
    top_entities = ranked_entities[:24]
    kept_names = {str(item.get("name") or "") for item in top_entities}
    top_relations = [
        item
        for key, item in sorted(all_relations.items(), key=lambda pair: relation_hits.get(pair[0], 0), reverse=True)
        if str(item.get("source") or "") in kept_names and str(item.get("target") or "") in kept_names
    ][:60]
    top_names = [str(item.get("name") or "") for item in top_entities[:8] if str(item.get("name") or "")]
    summary = f"题库主要聚焦：{'、'.join(top_names)}。" if top_names else ""
    return {
        "summary": summary,
        "questionCount": len(rows),
        "entities": top_entities,
        "relations": top_relations,
        "degraded": {
            "error": errors[0] if errors else "",
            "chunks": len(texts),
            "parallel": bool(use_llm and len(texts) > 1),
            "rawEntityCount": len(all_entities),
            "keptEntityCount": len(top_entities),
        },
    }


__all__ = ["extract_entities_from_text", "extract_bank_entities"]
