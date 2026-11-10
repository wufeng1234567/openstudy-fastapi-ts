"""统一学习图谱：把知识页、题库、文档、网页、笔记、图片合成一张只读图。

设计边界
========
· 节点只有六类：topic / bank / document / web / note / image。
· 所有节点都来自真实表；没有真实关系的节点允许独立存在，但不画假边。
· 本服务不建图库、不写库、不调 LLM；请求期聚合，输出稳定 ID。
· 旧的 `study_graph_service.build_study_graph` 继续保留给旧接口/旧工具；
  这里做的是“学习计划工作台”使用的统一视图。

ID 规约
=======
topic:{pageId} bank:{bankId} doc:{docId} web:{docId}
note:{noteId} image:{imageAssetId}
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentReference, RagImageAsset
from app.models.note import Note
from app.models.rag import DOC_PARSED, DOC_VECTORIZED, RagDocument
from app.models.wiki import RagWikiPage
from app.services.rag.graph_contract import stable_edge_id
from app.services import note_kb_link_service, question_bank_link_service
from app.services.rag import study_graph_service

SOURCE_TYPES = ("wiki", "bank", "document", "web", "note", "image")
DEFAULT_SOURCE_TYPES = ("wiki", "bank")
MAX_DOCUMENTS = 80
MAX_NOTES = 80
MAX_IMAGES = 120
MAX_REFERENCES = 500
MAX_NODES = 80

_KIND_PRIORITY = {
    "topic": 0,
    "bank": 1,
    "document": 2,
    "web": 3,
    "note": 4,
    "image": 5,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _image_seq(asset: RagImageAsset) -> int:
    try:
        return int(str(asset.asset_key or "").rsplit(":", 1)[-1]) + 1
    except (TypeError, ValueError):
        return 1


def _image_asset_title(asset: RagImageAsset, doc: Optional[RagDocument]) -> tuple[str, str]:
    """单张图片节点用图片内容命名；LLM 缺名时按文档名-图N/文件名兜底。"""
    doc_name = _safe_text(getattr(doc, "file_name", "") or "", 80)
    caption = _safe_text(
        getattr(asset, "caption", "")
        or getattr(asset, "ocr_text", "")
        or " ".join(getattr(asset, "keywords", []) or []),
        56,
    )
    seq = _image_seq(asset)
    if caption and caption not in {"图片", "截图", "image", "图片描述"}:
        subtitle = f"{doc_name} · 图{seq}" if doc_name else f"独立图片 · 第{seq}张"
        return caption, subtitle
    if doc_name:
        return f"{doc_name}-图{seq}", f"{doc_name} · 图{seq}"
    file_name = _safe_text(getattr(asset, "file_name", "") or "", 80)
    return file_name or f"图片 {int(asset.id or 0)}", "独立图片"


def _parse_source_types(value: Optional[Iterable[str] | str]) -> Set[str]:
    if value is None:
        return set(DEFAULT_SOURCE_TYPES)
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    picked = {str(item or "").strip().lower() for item in raw}
    return {item for item in picked if item in SOURCE_TYPES}


def _topic_id(page_id: Any) -> str:
    return f"topic:{_safe_int(page_id)}"


def _bank_id(bank_id: Any) -> str:
    return f"bank:{_safe_int(bank_id)}"


def _doc_id(doc_id: Any) -> str:
    return f"doc:{_safe_int(doc_id)}"


def _web_id(doc_id: Any) -> str:
    return f"web:{_safe_int(doc_id)}"


def _note_id(note_id: Any) -> str:
    return f"note:{_safe_int(note_id)}"


def _image_id(doc_id: Any) -> str:
    return f"image:{_safe_int(doc_id)}"


def _build_groups(nodes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    specs = [
        ("group:wiki", "topic", "知识主题"),
        ("group:bank", "bank", "题库"),
        ("group:document", "document", "资料"),
        ("group:web", "web", "网站"),
        ("group:note", "note", "笔记"),
        ("group:image", "image", "图片"),
    ]
    groups: List[Dict[str, Any]] = []
    for group_id, kind, title in specs:
        if kind == "bank":
            ids = [str(n["id"]) for n in nodes if n.get("kind") in {"bank", "question"}]
        elif kind == "topic":
            ids = [str(n["id"]) for n in nodes if n.get("kind") == "topic"]
        else:
            ids = [str(n["id"]) for n in nodes if n.get("kind") == kind]
        if ids:
            groups.append(
                {
                    "id": group_id,
                    "kind": kind,
                    "title": title,
                    "nodeIds": ids,
                }
            )
    return groups


def _node_sort_key(node: Dict[str, Any]) -> tuple:
    return (
        _KIND_PRIORITY.get(str(node.get("kind") or ""), 9),
        -_safe_int((node.get("metrics") or {}).get("degree")),
        _safe_int((node.get("ref") or {}).get("pageId")),
        str(node.get("title") or ""),
    )


def _trim_to_limit(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    *,
    seed_node_id: str = "",
    limit: int = MAX_NODES,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if len(nodes) <= limit:
        return nodes, edges
    by_id = {str(node["id"]): node for node in nodes}
    ordered: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    if seed_node_id and seed_node_id in by_id:
        # 先保留 seed + 1 跳邻居，保证用户选中的东西不会被截掉。
        ordered.append(by_id[seed_node_id])
        seen.add(seed_node_id)
        for edge in edges:
            source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
            neighbor = target if source == seed_node_id else source if target == seed_node_id else ""
            if neighbor and neighbor in by_id and neighbor not in seen:
                ordered.append(by_id[neighbor])
                seen.add(neighbor)
    for node in sorted(nodes, key=_node_sort_key):
        if len(ordered) >= limit:
            break
        if str(node["id"]) not in seen:
            ordered.append(node)
            seen.add(str(node["id"]))
    keep = {str(node["id"]) for node in ordered}
    kept_edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in keep and str(edge.get("target") or "") in keep
    ]
    return ordered, kept_edges


async def _load_page_docs(
    db: AsyncSession, user_id: int, kb_id: int, page_ids: Sequence[int]
) -> Dict[int, Set[int]]:
    """主题页 → 真实来源文档 ID（source_doc_ids + source_refs）。"""
    if not page_ids:
        return {}
    rows = (
        await db.execute(
            select(RagWikiPage.id, RagWikiPage.source_doc_ids, RagWikiPage.source_refs).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.id.in_([int(x) for x in page_ids]),
            )
        )
    ).all()
    result: Dict[int, Set[int]] = {}
    for page_id, doc_ids, refs in rows:
        found: Set[int] = set()
        for value in doc_ids or []:
            doc_id = _safe_int(value)
            if doc_id > 0:
                found.add(doc_id)
        for ref in refs or []:
            if isinstance(ref, dict):
                doc_id = _safe_int(ref.get("docId") or ref.get("doc_id"))
                if doc_id > 0:
                    found.add(doc_id)
        if found:
            result[int(page_id)] = found
    return result


async def _load_documents(
    db: AsyncSession, user_id: int, kb_id: int
) -> List[RagDocument]:
    query = select(RagDocument).where(
        RagDocument.user_id == int(user_id),
        RagDocument.status.in_([DOC_PARSED, DOC_VECTORIZED]),
        RagDocument.disabled == 0,
    )
    if int(kb_id or 0) > 0:
        query = query.where(RagDocument.kb_id == int(kb_id))
    return list(
        (
            await db.execute(
                query.order_by(RagDocument.create_time.desc(), RagDocument.id.desc()).limit(
                    MAX_DOCUMENTS
                )
            )
        )
        .scalars()
        .all()
    )


async def _load_notes(
    db: AsyncSession, user_id: int
) -> List[Note]:
    return list(
        (
            await db.execute(
                select(Note)
                .where(Note.user_id == int(user_id), Note.del_flag == "0")
                .order_by(Note.update_time.desc(), Note.note_id.desc())
                .limit(MAX_NOTES)
            )
        )
        .scalars()
        .all()
    )


async def _load_images(
    db: AsyncSession, user_id: int, kb_id: int, doc_ids: Sequence[int]
) -> List[RagImageAsset]:
    conditions = [RagImageAsset.user_id == int(user_id)]
    doc_filters = []
    if doc_ids:
        doc_filters.append(RagImageAsset.doc_id.in_([int(x) for x in doc_ids]))
    if int(kb_id or 0) > 0:
        doc_filters.append(
            and_(
                RagImageAsset.doc_id.is_(None),
                RagImageAsset.kb_id == int(kb_id),
            )
        )
    if doc_filters:
        conditions.append(or_(*doc_filters))
    return list(
        (
            await db.execute(
                select(RagImageAsset)
                .where(*conditions)
                .order_by(RagImageAsset.id.asc())
                .limit(MAX_IMAGES)
            )
        )
        .scalars()
        .all()
    )


def _reference_links(ref: ContentReference) -> tuple[int, int, int]:
    """把 ContentReference 归一成 (doc_id, note_id, page_id)。"""
    doc_id = 0
    note_id = 0
    page_id = 0
    source_type = str(ref.source_type or "")
    target_type = str(ref.target_type or "")
    if source_type in {"document", "document_image"}:
        doc_id = _safe_int(ref.source_id)
    elif source_type == "note":
        note_id = _safe_int(ref.source_id)
    elif source_type == "wiki_page":
        page_id = _safe_int(ref.source_id)
    if target_type == "document":
        doc_id = _safe_int(ref.target_id)
    elif target_type == "note":
        note_id = _safe_int(ref.target_id)
    elif target_type == "wiki_page":
        page_id = _safe_int(ref.target_id)
    return doc_id, note_id, page_id


async def _load_references(db: AsyncSession, user_id: int) -> List[ContentReference]:
    return list(
        (
            await db.execute(
                select(ContentReference)
                .where(
                    ContentReference.user_id == int(user_id),
                    ContentReference.deleted == 0,
                )
                .order_by(ContentReference.id.desc())
                .limit(MAX_REFERENCES)
            )
        )
        .scalars()
        .all()
    )


def _add_edge(
    edges: List[Dict[str, Any]],
    seen: Set[tuple],
    *,
    source: str,
    target: str,
    kind: str,
    label: str,
    weight: int = 5,
    evidence: Optional[Dict[str, Any]] = None,
) -> None:
    if not source or not target or source == target:
        return
    key = (source, target, kind)
    if key in seen:
        return
    seen.add(key)
    edge_id = stable_edge_id(kind, source, target)
    edges.append(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "kind": kind,
            "label": label,
            "weight": int(weight or 5),
            "evidence": evidence or {},
        }
    )


async def build_study_map(
    db: AsyncSession,
    user_id: int,
    *,
    kb_id: int = 0,
    bank_ids: Optional[Sequence[int]] = None,
    source_types: Optional[Iterable[str] | str] = None,
    seed_node_id: str = "",
    depth: int = 1,
    limit: int = MAX_NODES,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """构建六类节点的统一学习图谱（只读）。"""
    moment = now or datetime.now()
    wanted = _parse_source_types(source_types)
    if not wanted:
        wanted = set(DEFAULT_SOURCE_TYPES)
    if "image" in wanted:
        # 图片资产索引是图谱图片节点的真实来源；这里做一次幂等同步，
        # 避免用户没有先打开画廊时看不到文档图片。
        from app.services.rag import gallery_service

        await gallery_service.sync_image_assets(db, int(user_id))
    include_doc = bool({"document", "web", "note", "image"} & wanted)
    include_wiki = "wiki" in wanted
    include_bank = "bank" in wanted

    # 资料夹里逻辑关联的题库默认参与本次图谱；显式传入 bank_ids 时以传入为准。
    if int(kb_id or 0) > 0 and not bank_ids and include_bank:
        linked_ids = await question_bank_link_service.linked_bank_ids(
            db, user_id=int(user_id), kb_id=int(kb_id)
        )
        if linked_ids:
            bank_ids = linked_ids

    core = await study_graph_service.build_study_graph(
        db,
        int(user_id),
        int(kb_id or 0),
        bank_ids=bank_ids,
        include_legacy=False,
        bank_limit=8,
        now=moment,
    )

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_edges: Set[tuple] = set()
    core_page_ids: List[int] = []

    for raw in core.get("nodes") or []:
        if str(raw.get("kind") or "") != "page":
            continue
        page_id = _safe_int(raw.get("pageId"))
        if page_id <= 0:
            continue
        core_page_ids.append(page_id)
        if not include_wiki:
            continue
        nodes.append(
            {
                "id": _topic_id(page_id),
                "kind": "topic",
                "title": str(raw.get("title") or "未命名主题"),
                "subtitle": str(raw.get("pageType") or "知识百科"),
                "groupId": f"kb:{int(kb_id or 0)}",
                "source": "wiki",
                "ref": {"pageId": page_id, "bankId": 0, "docId": 0, "noteId": 0, "assetKey": ""},
                "metrics": {
                    "degree": _safe_int(raw.get("degree")),
                    "weakCount": _safe_int(raw.get("weakCount")),
                    "viewCount": _safe_int((raw.get("learning") or {}).get("viewCount")),
                    "practiceCount": _safe_int((raw.get("learning") or {}).get("practiceCount")),
                },
                "detail": {
                    "summary": str(raw.get("summary") or ""),
                    "pageType": str(raw.get("pageType") or ""),
                    "aliases": list(raw.get("aliases") or []),
                    "docIds": list(raw.get("docIds") or []),
                    "learning": raw.get("learning") or {},
                },
            }
        )

    for raw in core.get("nodes") or []:
        if str(raw.get("kind") or "") != "bank":
            continue
        bank_id = _safe_int(raw.get("bankId"))
        if bank_id <= 0 or not include_bank:
            continue
        nodes.append(
            {
                "id": _bank_id(bank_id),
                "kind": "bank",
                "title": str(raw.get("title") or "未命名题库"),
                "subtitle": str(raw.get("subject") or "题库"),
                "groupId": "bank",
                "source": "bank",
                "ref": {"pageId": 0, "bankId": bank_id, "docId": 0, "noteId": 0, "assetKey": ""},
                "metrics": {
                    "degree": len(raw.get("pageIds") or []),
                    "questionCount": _safe_int(raw.get("questionCount")),
                    "weakCount": _safe_int(raw.get("weakCount")),
                    "mappedQuestionCount": _safe_int(raw.get("mappedQuestionCount")),
                },
                "detail": {
                    "accuracy": raw.get("accuracy") or 0,
                    "practicedQuestionCount": _safe_int(raw.get("practicedQuestionCount")),
                    "pageIds": list(raw.get("pageIds") or []),
                },
            }
        )

    for edge in core.get("edges") or []:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source.startswith("bank:"):
            source_id = source
        elif source.startswith("page:"):
            source_id = _topic_id(source.split(":", 1)[1])
        else:
            source_id = _topic_id(source)
        if target.startswith("bank:"):
            target_id = target
        elif target.startswith("page:"):
            target_id = _topic_id(target.split(":", 1)[1])
        else:
            target_id = _topic_id(target)
        _add_edge(
            edges,
            seen_edges,
            source=source_id,
            target=target_id,
            kind=str(edge.get("type") or edge.get("kind") or "related"),
            label="题源关系" if edge.get("type") == "question_source" else "主题关系",
            weight=_safe_int(edge.get("weight")),
            evidence={"table": "rag_wiki_page_link / question_source", "id": edge.get("id")},
        )

    doc_by_id: Dict[int, RagDocument] = {}
    if include_doc:
        docs = await _load_documents(db, int(user_id), int(kb_id or 0))
        doc_by_id = {int(doc.id): doc for doc in docs}
        for doc in docs:
            is_web = bool(str(doc.source_url or "").strip())
            kind = "web" if is_web else "document"
            if kind not in wanted:
                continue
            node_id = _web_id(doc.id) if is_web else _doc_id(doc.id)
            nodes.append(
                {
                    "id": node_id,
                    "kind": kind,
                    "title": str(doc.file_name or "未命名资料"),
                    "subtitle": "网页导入" if is_web else str(doc.file_type or "资料"),
                    "groupId": f"kb:{_safe_int(doc.kb_id)}",
                    "source": kind,
                    "ref": {"pageId": 0, "bankId": 0, "docId": int(doc.id), "noteId": 0, "assetKey": ""},
                    "metrics": {
                        "degree": 0,
                        "chunkCount": _safe_int(doc.chunk_count),
                        "imageCount": len(doc.image_map or {}),
                    },
                    "detail": {
                        "summary": str(doc.user_note or ""),
                        "sourceUrl": str(doc.source_url or ""),
                        "status": _safe_int(doc.status),
                        "version": _safe_int(doc.version),
                    },
                }
            )

        # 主题页 → 文档：只画真实 source_doc_ids/source_refs
        page_docs = await _load_page_docs(db, int(user_id), int(kb_id or 0), core_page_ids)
        for page_id, doc_ids in page_docs.items():
            for doc_id in doc_ids:
                doc = doc_by_id.get(doc_id)
                if not doc:
                    continue
                doc_node = _web_id(doc_id) if str(doc.source_url or "").strip() else _doc_id(doc_id)
                if doc_node not in {str(n["id"]) for n in nodes}:
                    continue
                _add_edge(
                    edges,
                    seen_edges,
                    source=_topic_id(page_id),
                    target=doc_node,
                    kind="source_doc",
                    label="文档知识点",
                    evidence={"table": "rag_wiki_page.source_doc_ids", "docId": doc_id},
                )

        # 图片：每张 RagImageAsset 一个独立节点；图片可以属于文档，也可以是独立图片。
        if "image" in wanted:
            images = await _load_images(
                db, int(user_id), int(kb_id or 0), list(doc_by_id.keys())
            )
            image_node_ids: Dict[int, str] = {}
            image_by_asset_key: Dict[str, str] = {}
            image_id_by_asset_key: Dict[str, int] = {}
            for asset in images:
                doc_id = _safe_int(asset.doc_id)
                doc = doc_by_id.get(doc_id)
                if doc_id > 0 and doc is None:
                    continue
                node_id = f"image:{int(asset.id)}"
                image_node_ids[int(asset.id)] = node_id
                image_by_asset_key[str(asset.asset_key or "")] = node_id
                image_id_by_asset_key[str(asset.asset_key or "")] = int(asset.id)
                image_title, image_subtitle = _image_asset_title(asset, doc)
                image_summary = _safe_text(asset.caption or asset.ocr_text, 120) or image_subtitle
                nodes.append(
                    {
                        "id": node_id,
                        "kind": "image",
                        "title": image_title,
                        "subtitle": image_subtitle,
                        "groupId": "image",
                        "source": "image",
                        "ref": {
                            "pageId": 0,
                            "bankId": 0,
                            "docId": doc_id,
                            "noteId": 0,
                            "assetKey": str(asset.asset_key or ""),
                        },
                        "metrics": {
                            "degree": 0,
                            "imageCount": 1,
                            "descriptionStatus": str(asset.description_status or "pending"),
                        },
                        "detail": {
                            "summary": image_summary,
                            "caption": str(asset.caption or ""),
                            "ocrText": str(asset.ocr_text or ""),
                            "keywords": list(asset.keywords or []),
                            "imageKinds": [str(asset.kind or "image")],
                            "descriptionStatus": str(asset.description_status or "pending"),
                        },
                    }
                )
                if doc_id > 0 and doc is not None:
                    doc_node = (
                        _web_id(doc_id)
                        if str(doc.source_url or "").strip()
                        else _doc_id(doc_id)
                    )
                    _add_edge(
                        edges,
                        seen_edges,
                        source=doc_node,
                        target=node_id,
                        kind="document_image",
                        label="包含图片",
                        evidence={"table": "rag_image_asset", "assetId": int(asset.id), "docId": doc_id},
                    )

            # 图片 -> 知识点：① generation_meta.sourceType=image；② 页面显式引用了图片。
            if core_page_ids:
                page_rows = (
                    await db.execute(
                        select(RagWikiPage).where(
                            RagWikiPage.user_id == int(user_id),
                            RagWikiPage.id.in_([int(x) for x in core_page_ids]),
                        )
                    )
                ).scalars().all()
                image_page_ids: Dict[int, Set[int]] = defaultdict(set)
                for page in page_rows:
                    meta = page.generation_meta or {}
                    image_sources = []
                    if str(meta.get("sourceType") or "") == "image":
                        image_sources.append(meta)
                    image_sources.extend(
                        item
                        for item in (meta.get("sources") or [])
                        if isinstance(item, dict) and str(item.get("sourceType") or "") == "image"
                    )
                    for source in image_sources:
                        source_id = _safe_int(source.get("sourceId"))
                        if source_id in image_node_ids:
                            image_page_ids[source_id].add(int(page.id))
                refs = (
                    await db.execute(
                        select(ContentReference).where(
                            ContentReference.user_id == int(user_id),
                            ContentReference.deleted == 0,
                            ContentReference.target_type == "wiki_page",
                            ContentReference.target_id.in_([int(x) for x in core_page_ids]),
                        )
                    )
                ).scalars().all()
                for ref in refs:
                    asset_key = ""
                    if ref.source_type == "document_image":
                        asset_key = f"doc:{int(ref.source_id)}:{ref.source_sub_id or ''}"
                    elif ref.source_type == "chat_image":
                        asset_key = f"chat:{int(ref.source_id)}"
                    if asset_key in image_id_by_asset_key:
                        image_page_ids[image_id_by_asset_key[asset_key]].add(int(ref.target_id))
                for image_id, page_ids in image_page_ids.items():
                    image_node = image_node_ids.get(int(image_id))
                    if not image_node:
                        continue
                    for page_id in page_ids:
                        _add_edge(
                            edges,
                            seen_edges,
                            source=image_node,
                            target=_topic_id(page_id),
                            kind="image_knowledge",
                            label="图片知识点",
                            evidence={"table": "rag_wiki_page / content_reference", "assetId": int(image_id), "pageId": int(page_id)},
                        )

        # 笔记：ContentReference 和 note_kb_link 都是真实来源；
        # 被用户显式关联到资料夹的笔记即使还没有主题页，也要作为来源节点出现。
        if "note" in wanted:
            notes = await _load_notes(db, int(user_id))
            note_by_id = {int(note.note_id): note for note in notes}
            refs = await _load_references(db, int(user_id))
            note_links: Dict[int, Set[tuple[str, int]]] = defaultdict(set)
            for ref in refs:
                doc_id, note_id, page_id = _reference_links(ref)
                if note_id and note_id in note_by_id:
                    if doc_id and doc_id in doc_by_id:
                        note_links[note_id].add(("doc", doc_id))
                    if page_id:
                        note_links[note_id].add(("topic", page_id))
            linked_note_ids = set(
                await note_kb_link_service.linked_note_ids(
                    db, user_id=int(user_id), kb_id=int(kb_id)
                )
            )
            all_note_ids = sorted(set(note_links) | linked_note_ids)
            for note_id in all_note_ids:
                note = note_by_id.get(note_id)
                if not note:
                    continue
                links = note_links.get(note_id, set())
                node_id = _note_id(note_id)
                nodes.append(
                    {
                        "id": node_id,
                        "kind": "note",
                        "title": str(note.title or "未命名笔记"),
                        "subtitle": "笔记",
                        "groupId": "note",
                        "source": "note",
                        "ref": {"pageId": 0, "bankId": 0, "docId": 0, "noteId": note_id, "assetKey": ""},
                        "metrics": {"degree": len(links)},
                        "detail": {"summary": _safe_text(note.markdown_content or note.content or "", 160)},
                    }
                )
                for kind, target_id in links:
                    target_node = _doc_id(target_id) if kind == "doc" else _topic_id(target_id)
                    _add_edge(
                        edges,
                        seen_edges,
                        source=node_id,
                        target=target_node,
                        kind="reference",
                        label="引用",
                        evidence={"table": "content_reference", "noteId": note_id},
                    )

    # 只保留两端都存在的边
    node_ids = {str(node["id"]) for node in nodes}
    edges = [
        edge
        for edge in edges
        if str(edge.get("source") or "") in node_ids and str(edge.get("target") or "") in node_ids
    ]
    nodes, edges = _trim_to_limit(nodes, edges, seed_node_id=seed_node_id, limit=max(8, int(limit or MAX_NODES)))
    degree_by_id: Dict[str, int] = defaultdict(int)
    for edge in edges:
        degree_by_id[str(edge.get("source") or "")] += 1
        degree_by_id[str(edge.get("target") or "")] += 1
    for node in nodes:
        metrics = node.setdefault("metrics", {})
        metrics["degree"] = max(int(metrics.get("degree") or 0), degree_by_id.get(str(node["id"]), 0))

    stats = {
        "topicCount": sum(1 for n in nodes if n["kind"] == "topic"),
        "bankCount": sum(1 for n in nodes if n["kind"] == "bank"),
        "documentCount": sum(1 for n in nodes if n["kind"] == "document"),
        "webCount": sum(1 for n in nodes if n["kind"] == "web"),
        "noteCount": sum(1 for n in nodes if n["kind"] == "note"),
        "imageCount": sum(1 for n in nodes if n["kind"] == "image"),
        "questionNodeCount": sum(1 for n in nodes if n["kind"] == "question"),
        "edgeCount": len(edges),
    }
    stats["weakQuestionCount"] = sum(
        _safe_int((n.get("metrics") or {}).get("weakCount"))
        for n in nodes
        if n["kind"] == "bank"
    )
    groups = _build_groups(nodes)
    source_stats = [
        {"type": "wiki", "label": "知识主题", "count": stats["topicCount"]},
        {"type": "bank", "label": "题库", "count": stats["bankCount"]},
        {"type": "document", "label": "资料", "count": stats["documentCount"]},
        {"type": "web", "label": "网页", "count": stats["webCount"]},
        {"type": "note", "label": "笔记", "count": stats["noteCount"]},
        {"type": "image", "label": "图片", "count": stats["imageCount"]},
    ]
    return {
        "kbId": int(kb_id or 0),
        "generatedAt": moment.isoformat(sep=" ", timespec="seconds"),
        "nodes": nodes,
        "edges": edges,
        "groups": groups,
        "stats": stats,
        "sourceStats": source_stats,
        "degraded": {
            "pagesEmpty": stats["topicCount"] == 0,
            "banksEmpty": stats["bankCount"] == 0,
            "noQuestionSource": stats["bankCount"] > 0
            and not any(_safe_int((n.get("metrics") or {}).get("mappedQuestionCount")) for n in nodes if n["kind"] == "bank"),
            "noSources": (stats["documentCount"] + stats["webCount"] + stats["noteCount"] + stats["imageCount"]) == 0,
            "noEdges": len(edges) == 0,
        },
        "sources": {
            "topics": "rag_wiki_page / rag_wiki_page_link",
            "banks": "question_bank / question_main / question_source",
            "documents": "rag_document / rag_wiki_page.source_doc_ids",
            "web": "rag_document.source_url",
            "notes": "note / content_reference",
            "images": "rag_image_asset",
            "generated": "request-time; no graph table",
        },
    }


__all__ = ["build_study_map", "SOURCE_TYPES", "DEFAULT_SOURCE_TYPES"]
