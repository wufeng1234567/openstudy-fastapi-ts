"""主题页来源合并工具。

历史实现里，一篇文档第二次生成本应是同一个概念的主题页时，会直接覆盖
`source_refs` / `source_doc_ids` / `sections`。这会让“智能体理论文档”和
“智能体实操文档”的共享概念只剩下最后一份来源。

本模块只做一件事：**把新来源并入已有主题页，保留原有来源、正文小节和实体**。
不调用模型、不写库；调用方负责提交事务和更新向量块。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from app.models.wiki import RagWikiPage


def _as_int_list(values: Any) -> List[int]:
    result: List[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def merge_int_list(existing: Any, incoming: Any) -> List[int]:
    return _as_int_list(list(existing or []) + list(incoming or []))


def _ref_key(item: Dict[str, Any]) -> Tuple[int, int]:
    return (int(item.get("docId") or 0), int(item.get("chunkId") or 0))


def merge_source_refs(existing: Any, incoming: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen: Set[Tuple[int, int]] = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        key = _ref_key(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _section_key(section: Dict[str, Any]) -> Tuple[str, int, str, str]:
    return (
        str(section.get("sourceType") or ""),
        int(section.get("sourceId") or 0),
        str(section.get("heading") or "").strip(),
        str(section.get("body") or "").strip()[:160],
    )


def merge_sections(
    existing: Any,
    incoming: Any,
    *,
    source_type: str = "",
    source_id: int = 0,
    source_name: str = "",
) -> List[Dict[str, Any]]:
    """追加来源小节，不覆盖旧来源；相同来源+标题+正文视为重复。"""
    result: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, int, str, str]] = set()
    for raw in list(existing or []):
        if not isinstance(raw, dict):
            continue
        block = dict(raw)
        key = _section_key(block)
        if key in seen:
            continue
        seen.add(key)
        result.append(block)
    for raw in list(incoming or []):
        if not isinstance(raw, dict):
            continue
        block = dict(raw)
        if source_type and not block.get("sourceType"):
            block["sourceType"] = source_type
        if source_id and not block.get("sourceId"):
            block["sourceId"] = int(source_id)
        if source_name and not block.get("sourceName"):
            block["sourceName"] = source_name
        key = _section_key(block)
        if key in seen:
            continue
        seen.add(key)
        result.append(block)
    return result


def merge_generation_sources(
    meta: Optional[Dict[str, Any]],
    *,
    source_type: str,
    source_id: int,
    source_name: str,
) -> Dict[str, Any]:
    """维护 generation_meta.sources 数组，兼容旧的单来源字段。"""
    result = dict(meta or {})
    sources: List[Dict[str, Any]] = []
    raw_sources = result.get("sources")
    if isinstance(raw_sources, list):
        sources = [dict(item) for item in raw_sources if isinstance(item, dict)]
    if not sources:
        old_type = str(result.get("sourceType") or "").strip()
        old_id = int(result.get("sourceId") or 0)
        old_name = str(result.get("sourceName") or "").strip()
        if old_type and old_id:
            sources.append(
                {"sourceType": old_type, "sourceId": old_id, "sourceName": old_name}
            )
    key = (source_type, int(source_id))
    for item in sources:
        if (
            str(item.get("sourceType") or "") == key[0]
            and int(item.get("sourceId") or 0) == key[1]
        ):
            if source_name:
                item["sourceName"] = source_name
            break
    else:
        if source_type and int(source_id or 0) > 0:
            sources.append(
                {
                    "sourceType": source_type,
                    "sourceId": int(source_id),
                    "sourceName": source_name,
                }
            )
    result["sources"] = sources
    if source_type and int(source_id or 0) > 0:
        # 保留一个“主来源”字段供老代码读取；多来源的真实集合在 sources。
        result.setdefault("sourceType", source_type)
        result.setdefault("sourceId", int(source_id))
        result.setdefault("sourceName", source_name)
    return result


def _render_markdown(summary: str, sections: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    if summary:
        parts.append(summary)
    for section in sections or []:
        heading = str(section.get("heading") or "").strip()
        body = str(section.get("body") or "").strip()
        if heading:
            parts.append(f"## {heading}\n\n{body}")
        elif body:
            parts.append(body)
    return "\n\n".join(parts)


def apply_source_to_page(
    page: RagWikiPage,
    *,
    title: str,
    page_type: str,
    summary: str,
    sections: Sequence[Dict[str, Any]],
    source_refs: Sequence[Dict[str, Any]],
    source_chunk_ids: Sequence[int],
    entity_ids: Sequence[int],
    source_type: str,
    source_id: int,
    source_name: str,
    aliases: Optional[Sequence[str]] = None,
) -> RagWikiPage:
    """把一份来源并入主题页；保留旧来源，不覆盖。

    调用方需要保证：
    * 页面已经加入 session 或已存在；
    * 若页面正文变化，调用方重新生成 wiki chunk；
    * 若 page.status 是 manual/agent，调用方不要调用本函数。
    """
    if not str(page.title or "").strip():
        page.title = title[:255]
    if not str(page.normalized_title or "").strip():
        page.normalized_title = title[:255]
    if not str(page.page_type or "").strip():
        page.page_type = page_type

    existing_summary = str(page.summary or "").strip()
    incoming_summary = str(summary or "").strip()
    existing_sections = list(page.sections or [])

    # 旧页面只有一条摘要；新来源的摘要不同时作为“来源摘要”小节保留，
    # 避免为了合并把旧摘要覆盖掉。
    extra_sections: List[Dict[str, Any]] = []
    if existing_summary and incoming_summary and incoming_summary != existing_summary:
        extra_sections.append(
            {
                "heading": f"来源摘要 · {source_name or '来源'}",
                "body": incoming_summary,
                "sourceChunkIds": [],
                "sourceType": source_type,
                "sourceId": int(source_id or 0),
                "sourceName": source_name,
            }
        )
    if not existing_summary and incoming_summary:
        page.summary = incoming_summary

    page.sections = merge_sections(
        existing_sections + extra_sections,
        sections,
        source_type=source_type,
        source_id=source_id,
        source_name=source_name,
    )
    page.source_refs = merge_source_refs(page.source_refs, source_refs)
    page.source_doc_ids = sorted(
        {
            int(item.get("docId") or 0)
            for item in page.source_refs
            if int(item.get("docId") or 0) > 0
        }
    )
    page.source_chunk_ids = merge_int_list(page.source_chunk_ids, source_chunk_ids)
    page.entity_ids = merge_int_list(page.entity_ids, entity_ids)
    page.aliases = list(
        dict.fromkeys(
            [
                *[str(item).strip() for item in (page.aliases or []) if str(item).strip()],
                *[str(item).strip() for item in (aliases or []) if str(item).strip()],
            ]
        )
    )[:12]
    page.generation_meta = merge_generation_sources(
        page.generation_meta,
        source_type=source_type,
        source_id=source_id,
        source_name=source_name,
    )
    page.generation_meta["pageType"] = page.page_type
    page.generation_meta["aliases"] = page.aliases
    page.generation_meta["generatedAt"] = datetime.now().isoformat(timespec="seconds")
    page.content_md = _render_markdown(str(page.summary or ""), page.sections)
    page.status = "ready"
    page.update_time = datetime.now()
    return page


__all__ = [
    "apply_source_to_page",
    "merge_generation_sources",
    "merge_int_list",
    "merge_sections",
    "merge_source_refs",
]
