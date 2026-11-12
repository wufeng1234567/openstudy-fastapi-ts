"""知识百科页面生成辅助：标题/正文清洗、页面 payload 校验与 prompt 构建。"""

import json
import re
from typing import Any, Dict, Sequence

from loguru import logger

from app.models.knowledge_graph import RagGraphEntity
from app.models.rag import RagDocument, RagDocumentChunk
from app.services.rag.rag_write_service import sanitize_text

MAX_SECTIONS = 6
MAX_SECTION_CHARS = 1600
_ENTITY_PAGE_TYPES = {
    "人物": "entity",
    "机构": "entity",
    "事件": "entity",
    "作品": "entity",
    "其他": "entity",
    "概念": "concept",
    "定理/公式": "concept",
    "方法": "concept",
    "术语": "concept",
    "变量/符号": "concept",
}


def _page_type_for_entity(entity: RagGraphEntity, degree: int, relations: Sequence[dict]) -> str:
    """按实体类型 + 图上位置生成 Wiki 页面类型，供图谱颜色区分。"""
    base = _ENTITY_PAGE_TYPES.get(str(entity.type or ""), "concept")
    contrast_count = sum(1 for item in relations if item.get("relationType") == "对比")
    if contrast_count >= 2:
        return "comparison"
    # 枢纽页不是“更好的概念页”，而是把多个主题串起来的综合页。
    if int(degree or 0) >= 8:
        return "synthesis"
    return base


def _clean_aliases(value: Any, limit: int = 8) -> list[str]:
    """清洗模型给出的同义名：去重、去空白、限制长度，不把整段解释当别名。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean(item, 80)
        if not text or len(text) < 2 or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean(value: Any, limit: int = 4000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return sanitize_text(text)[:limit]


def _normalize_title(value: Any) -> str:
    """页面标题归一化：只做名称级合并，不做模糊同义词合并。"""
    title = re.sub(r"[\s\u3000]+", "", str(value or "").strip())
    title = title.strip("《》\"'“”‘’（）()[]【】")
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(title) > len(suffix) + 1 and title.endswith(suffix):
            title = title[: -len(suffix)]
            break
    return title.lower()


def _display_title(value: Any) -> str:
    """展示标题去掉“定义/概念/概述”等解释性后缀，保留大小写与正文。"""
    title = re.sub(r"[\s\u3000]+", " ", str(value or "").strip())
    title = title.strip("《》\"'“”‘’（）()[]【】")
    for suffix in ("定义", "概念", "概述", "简介", "介绍", "说明"):
        if len(title) > len(suffix) + 1 and title.endswith(suffix):
            return title[: -len(suffix)].strip()
    return title


def _parse_page_payload(raw: str) -> Dict[str, Any]:
    """解析模型返回的主题页 JSON；兼容代码围栏与裸数组。"""
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回可解析的主题页 JSON")
        payload = json.loads(text[start : end + 1])
    if isinstance(payload, list):
        return {"summary": "", "sections": payload, "relatedTitles": []}
    if not isinstance(payload, dict):
        raise ValueError("主题页 JSON 不是对象")
    return payload


def _section_source_ids(section: Dict[str, Any]) -> list[int]:
    raw = (
        section.get("sourceChunkIds")
        or section.get("chunkIds")
        or section.get("source_chunk_ids")
        or section.get("sources")
        or []
    )
    if not isinstance(raw, list):
        raw = [raw]
    result: list[int] = []
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result


def _validate_page_payload(
    payload: Dict[str, Any],
    allowed_chunk_ids: Sequence[int],
    allowed_related_titles: Sequence[str],
    fallback_summary: str,
) -> Dict[str, Any]:
    """过滤模型输出里的无效来源，保证页面只引用真实 chunk。

    原则：没有真实来源的小节宁可不要，也不把模型自造的 chunk id 写进页面。
    """
    allowed = {int(x) for x in allowed_chunk_ids if int(x) > 0}
    summary = _clean(payload.get("summary") or payload.get("description") or fallback_summary, 500)
    if not summary:
        summary = _clean(fallback_summary, 500)

    sections: list[dict] = []
    raw_sections = payload.get("sections") or payload.get("chapters") or []
    if isinstance(raw_sections, dict):
        raw_sections = [raw_sections]
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        heading = _clean(item.get("heading") or item.get("title"), 60)
        body = _clean(item.get("body") or item.get("content") or item.get("text"), MAX_SECTION_CHARS)
        if not heading or not body:
            continue
        source_ids = [cid for cid in _section_source_ids(item) if cid in allowed]
        if not source_ids:
            # 没有可核对的来源，整节不要；不能让用户以为这是资料原文。
            continue
        sections.append({"heading": heading, "body": body, "sourceChunkIds": source_ids})
        if len(sections) >= MAX_SECTIONS:
            break

    related: list[str] = []
    raw_related = payload.get("relatedTitles") or payload.get("related") or []
    allowed_names = {_normalize_title(x): _clean(x, 120) for x in allowed_related_titles if _clean(x, 120)}
    for item in raw_related if isinstance(raw_related, list) else []:
        key = _normalize_title(item)
        if key in allowed_names and allowed_names[key] not in related:
            related.append(allowed_names[key])

    return {
        "summary": summary,
        "sections": sections,
        "relatedTitles": related,
        "aliases": _clean_aliases(payload.get("aliases") or payload.get("alias") or []),
    }


def _render_markdown(summary: str, sections: Sequence[Dict[str, Any]]) -> str:
    lines = [f"> {summary}", ""]
    for section in sections:
        lines.append(f"## {section['heading']}")
        lines.append("")
        lines.append(str(section.get("body") or ""))
        lines.append("")
    return "\n".join(lines).strip()


def _build_prompt(
    *,
    kb_name: str,
    entity: RagGraphEntity,
    relations: Sequence[Dict[str, Any]],
    chunks: Sequence[RagDocumentChunk],
    doc_names: Dict[int, str],
    linkable_titles: Sequence[str] = (),
) -> str:
    context_parts = []
    for chunk in chunks:
        doc_name = doc_names.get(int(chunk.doc_id), "资料")
        context_parts.append(
            f"[chunk:{int(chunk.id)}] 资料《{doc_name}》第 {int(chunk.chunk_index) + 1} 段\n"
            f"{_clean(chunk.content, 1200)}"
        )
    context = "\n\n".join(context_parts)
    relation_lines = []
    for item in relations[:20]:
        direction = "→" if item.get("direction") == "out" else "←"
        relation_lines.append(
            f"{entity.name} {direction} {item.get('relationType', '相关')} {item.get('name', '')}"
        )
    relation_text = "\n".join(relation_lines) or "（暂时没有抽到实体关系）"
    linkable = [
        _display_title(item)
        for item in linkable_titles
        if _display_title(item) and _normalize_title(item) != _normalize_title(entity.name)
    ][:80]
    linkable_text = "、".join(dict.fromkeys(linkable)) or "（暂无其他主题页）"

    return (
        "你是 OpenStudy 的课程知识编辑。请把给定资料整理成一篇可读的知识主题页。\n"
        "硬性要求：\n"
        "1. 只能使用下面提供的资料片段，不准使用资料之外的常识，不准编造事实、数字、引用或 chunk id。\n"
        "2. 每个 section 必须给出至少一个 sourceChunkIds，且只能从提供的 [chunk:数字] 里选。\n"
        "3. 资料不足以支撑的章节直接不写，不要写“补充证据”“据推测”等话。\n"
        "4. 不要把所有关系都罗列出来；只写对学习这个主题有帮助的内容。\n"
        "5. 正文里凡是提到「可链接主题页」里的名称或同义名，必须写成 [[主题页标题|正文原词]]，例如 [[记忆机制|记忆机制]]；只能使用候选列表里的标题，不能链接本页自己，同一目标只链接第一次出现。\n"
        "6. aliases 只写资料里明确出现过的同义名/缩写，没有就返回空数组。\n"
        "7. 输出严格 JSON，不要 Markdown 代码围栏。\n\n"
        "输出格式：\n"
        '{"summary":"一句话解释这个主题",'
        '"aliases":["同义名或缩写"],'
        '"sections":[{"heading":"核心要点","body":"用短段落或列表写清楚，必要时带 [[主题页标题|原词]]",'
        '"sourceChunkIds":[123]}],'
        '"relatedTitles":["只能是相邻实体名"]}\n\n'
        f"资料夹：{kb_name}\n"
        f"主题：{entity.name}（类型：{entity.type}）\n"
        f"已有描述：{_clean(entity.description, 500) or '（无）'}\n"
        f"可链接主题页：{linkable_text}\n"
        f"相邻实体：\n{relation_text}\n\n"
        f"资料片段：\n{context}"
    )


