"""知识百科（Wiki）**内容与来源**的纯辅助（从 `wiki_service.py` 抽出）。

这些函数**只依赖入参**（外加同目录的既有常量 / 辅助），不碰数据库、不调用模型：

  · **`_source_refs`** —— chunk 列表 → 页面来源引用（docId / chunkId / quote…）
  · **`_cited_source_refs`** —— 只保留正文小节**真正引用过**的 chunk
  · **`_asset_key_from_reference`** —— 图片引用 → `asset_key`
  · **`_wiki_hit`** —— 主题页 chunk → 检索命中（`ChunkHit`）
  · **`_page_revision_snapshot`** —— 页面 → 修订快照（落库前的版本留痕）
  · **`_manual_sections`** —— 清洗用户编辑 / Agent 提交的小节
  · **`_find_anchor_position`** —— 正文里找第一个**不在已有 wiki 标记内**的锚文本

⚠ 依赖方向单向：`wiki_service.py` → 本模块；本模块**不反向依赖** `wiki_service.py`
   （`wiki_helpers` / `wiki_payload_helpers` / `wiki_link_service` / `hybrid_search`
   均无对 `wiki_service` 的模块级回引），因此不会形成循环依赖。

⚠ 页面 / 来源的**响应形状一个字段都没改** —— 这里只是把「形状怎么算」挪到了
   可以单独读、单独测的地方；async 的落库 / 检索 / LLM 流程一行未动。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from app.models.content import ContentReference
from app.models.rag import RagDocumentChunk
from app.models.wiki import RagWikiChunk, RagWikiPage, RagWikiPageRevision
from app.services.rag.hybrid_search import ChunkHit
from app.services.rag.wiki_helpers import _clean
from app.services.rag.wiki_link_service import WIKI_TOKEN_RE
from app.services.rag.wiki_payload_helpers import (
    MAX_SECTIONS,
    MAX_SECTION_CHARS,
    WIKI_READY,
    WIKI_STALE,
)


def _source_refs(chunks: Sequence[RagDocumentChunk], doc_names: Dict[int, str]) -> list[dict]:
    refs = []
    for chunk in chunks:
        refs.append(
            {
                "docId": int(chunk.doc_id),
                "chunkId": int(chunk.id),
                "docName": doc_names.get(int(chunk.doc_id), "资料"),
                "chunkIndex": int(chunk.chunk_index),
                "quote": _clean(chunk.content, 220),
            }
        )
    return refs


def _cited_source_refs(page: RagWikiPage) -> list[dict]:
    """只展示正文小节真正引用的 chunk；生成上下文里未被引用的大段内容不算来源。"""
    refs = list(page.source_refs or [])
    cited = {int(x) for x in (page.source_chunk_ids or []) if str(x).isdigit()}
    if not cited:
        return refs
    filtered = []
    for item in refs:
        if not isinstance(item, dict):
            continue
        try:
            chunk_id = int(item.get("chunkId") or 0)
        except (TypeError, ValueError):
            continue
        if chunk_id in cited:
            filtered.append(item)
    return filtered


def _asset_key_from_reference(ref: ContentReference) -> str:
    if ref.source_type == "document_image":
        return f"doc:{int(ref.source_id)}:{ref.source_sub_id or ''}"
    if ref.source_type == "chat_image":
        return f"chat:{int(ref.source_id)}"
    return ""


def _page_revision_snapshot(page: RagWikiPage, change_type: str, created_by: str) -> RagWikiPageRevision:
    return RagWikiPageRevision(
        user_id=int(page.user_id),
        kb_id=int(page.kb_id),
        page_id=int(page.id),
        version=int(page.version or 1),
        title=page.title or "",
        summary=page.summary or "",
        content_md=page.content_md or "",
        sections=page.sections or [],
        source_refs=page.source_refs or [],
        status=page.status or WIKI_READY,
        change_type=change_type,
        created_by=created_by,
    )


def _manual_sections(value: Any, allowed_chunk_ids: Optional[Sequence[int]] = None) -> list[dict]:
    """清洗用户编辑/Agent 提交的小节。

    手动编辑允许没有 chunk 来源（用户自己写的内容）；但模型传来的来源 id
    只能落在页面已知来源 chunk 里，不能让模型把任意 id 写进页面。
    """
    allowed = {int(x) for x in (allowed_chunk_ids or []) if str(x).isdigit()}
    out: list[dict] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        heading = _clean(item.get("heading") or item.get("title"), 60)
        body = _clean(item.get("body") or item.get("content") or item.get("text"), MAX_SECTION_CHARS)
        if not heading or not body:
            continue
        raw_ids = item.get("sourceChunkIds") or item.get("chunkIds") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        source_ids = []
        for chunk_id in raw_ids:
            try:
                chunk_id = int(chunk_id)
            except (TypeError, ValueError):
                continue
            if allowed and chunk_id in allowed and chunk_id not in source_ids:
                source_ids.append(chunk_id)
        out.append({"heading": heading, "body": body, "sourceChunkIds": source_ids})
        if len(out) >= MAX_SECTIONS:
            break
    return out


def _find_anchor_position(text: str, anchor: str) -> int:
    """在正文里找第一个不在已有 wiki 标记内的锚文本位置。"""
    if not text or not anchor:
        return -1
    occupied = [(match.start(), match.end()) for match in WIKI_TOKEN_RE.finditer(text)]
    start = 0
    while start <= len(text) - len(anchor):
        pos = text.find(anchor, start)
        if pos < 0:
            return -1
        end = pos + len(anchor)
        if not any(pos < span_end and end > span_start for span_start, span_end in occupied):
            return pos
        start = pos + 1
    return -1


def _wiki_hit(
    chunk: RagWikiChunk,
    page_title: str,
    page_id: int,
    page_status: str,
    *,
    vector_score: Optional[float] = None,
    keyword_score: Optional[float] = None,
) -> ChunkHit:
    return ChunkHit(
        chunk_id=int(chunk.id),
        doc_id=0,
        kb_id=int(chunk.kb_id),
        chunk_index=int(chunk.section_index or 0),
        content=chunk.content,
        doc_name=f"知识百科《{page_title}》",
        vector_score=vector_score,
        keyword_score=keyword_score,
        wiki_hit=True,
        wiki_page_id=int(page_id),
        wiki_page_title=page_title,
        wiki_section=chunk.section_title,
        wiki_stale=(page_status == WIKI_STALE),
    )
