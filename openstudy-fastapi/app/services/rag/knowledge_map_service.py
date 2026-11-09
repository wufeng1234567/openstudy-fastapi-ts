"""资料知识地图：把文档、章节、笔记、题目、图片组织成可解释的页面关系图。

为什么不是实体图谱
------------------
本服务不抽取「概念/实体」，也不引入图数据库。节点全部来自真实存在的对象：
  文档 → 章节（原文标题切片）→ 题组 / 图组；笔记通过 `ContentReference` 连到文档。
边的类型只有四种，全部可解释：
  hierarchy（文档包含章节）、question_source（题目引用原文）、
  image_source（文档包含图片）、reference（笔记/图片与文档的显式引用）。

前端负责布局和交互，后端只提供稳定节点/边和详情，不把画图逻辑塞进服务端。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentReference, RagImageAsset
from app.models.note import Note
from app.models.question import QuestionSource
from app.models.rag import RagDocument, RagKnowledgeBase
from app.services.rag.graph_contract import stable_edge_id
from app.services.rag.section_outline import content_sections

GROUP_COLORS = [
    "#4F6BED",  # 雾蓝
    "#2F9E8F",  # 青绿
    "#C47A55",  # 陶土
    "#8B6BB1",  # 淡紫
    "#B78B2A",  # 沙金
    "#5C8FA8",  # 灰蓝
]
MAX_DOCUMENTS = 80
MAX_SECTIONS_PER_DOC = 8
MAX_NOTES = 120


def _clean(text: str, limit: int = 90) -> str:
    value = re.sub(r"【图\d+】", " ", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _section_nodes(doc: RagDocument) -> tuple[List[Dict[str, Any]], int]:
    sections = [s for s in content_sections(doc.raw_content or "") if s.get("title") != "开篇"]
    if len(sections) <= 1:
        return [], len(sections)
    chosen = sections[:MAX_SECTIONS_PER_DOC]
    nodes = []
    for section in chosen:
        text = str(section.get("text") or "")
        chars = len(re.sub(r"\s+", "", text))
        nodes.append(
            {
                "id": f"section:{doc.id}:{section.get('index')}",
                "type": "section",
                "label": str(section.get("title") or "未命名章节")[:42],
                "groupId": f"kb:{doc.kb_id}",
                "docId": int(doc.id),
                "kbId": int(doc.kb_id),
                "value": max(1, chars),
                "meta": {
                    "title": str(section.get("title") or "未命名章节"),
                    "excerpt": _clean(text, 120),
                    "chars": chars,
                    "start": int(section.get("start") or 0),
                    "end": int(section.get("end") or 0),
                    "hasPractice": bool(re.search(r"(练习|习题|例题|题目|解答)", text)),
                },
                "searchText": f"{doc.file_name} {section.get('title') or ''} {_clean(text, 200)}",
            }
        )
    return nodes, len(sections)


def _doc_summary(doc: RagDocument) -> str:
    if doc.user_note:
        return str(doc.user_note)[:120]
    sections = [s for s in content_sections(doc.raw_content or "") if s.get("title") != "开篇"]
    if sections:
        return f"{len(sections)} 个章节 · 从「{sections[0].get('title')}」开始"
    return "尚未识别出章节结构"


async def build_knowledge_map(
    db: AsyncSession,
    user_id: int,
    *,
    kb_id: Optional[int] = None,
) -> Dict[str, Any]:
    uid = int(user_id)
    # 地图可能比画廊先被打开：这里幂等补齐图片索引，图组数量才是真实的。
    from app.services.rag.gallery_service import sync_image_assets

    await sync_image_assets(db, uid)
    kb_query = select(RagKnowledgeBase).where(
        RagKnowledgeBase.user_id == uid,
        RagKnowledgeBase.del_flag == "0",
    )
    if kb_id is not None:
        kb_query = kb_query.where(RagKnowledgeBase.id == int(kb_id))
    kbs = (await db.execute(kb_query.order_by(RagKnowledgeBase.id.asc()))).scalars().all()
    kb_by_id = {int(kb.id): kb for kb in kbs}

    doc_query = select(RagDocument).where(RagDocument.user_id == uid)
    if kb_id is not None:
        doc_query = doc_query.where(RagDocument.kb_id == int(kb_id))
    docs = (
        await db.execute(
            doc_query.order_by(RagDocument.create_time.desc(), RagDocument.id.desc()).limit(MAX_DOCUMENTS)
        )
    ).scalars().all()

    # 没有知识库归属的文档（历史数据）也放进一个「未归类」组。
    # 分组颜色按资料量排序：资料最多的组用主色蓝，避免默认资料夹拿到沙金等弱色。
    candidates: List[Dict[str, Any]] = []
    for kb in kbs:
        count = sum(1 for d in docs if int(d.kb_id) == int(kb.id))
        if not count:
            continue
        candidates.append(
            {
                "id": f"kb:{int(kb.id)}",
                "name": kb.name or "未命名资料夹",
                "description": kb.description or "这一组里的资料来自同一个资料夹",
                "docCount": count,
            }
        )
    unclassified = sum(1 for d in docs if int(d.kb_id) not in kb_by_id)
    if unclassified:
        candidates.append(
            {
                "id": "kb:0",
                "name": "未归类资料",
                "description": "历史资料，尚未归入资料夹",
                "docCount": unclassified,
            }
        )
    candidates.sort(key=lambda item: (-int(item["docCount"]), str(item["name"])))
    group_order: List[Dict[str, Any]] = []
    seen_groups: set[str] = set()
    for index, group in enumerate(candidates):
        group["color"] = GROUP_COLORS[index % len(GROUP_COLORS)]
        seen_groups.add(str(group["id"]))
        group_order.append(group)

    question_counts = dict(
        (
            await db.execute(
                select(QuestionSource.doc_id, func.count(QuestionSource.id))
                .where(QuestionSource.user_id == uid, QuestionSource.doc_id.in_([int(d.id) for d in docs] or [0]))
                .group_by(QuestionSource.doc_id)
            )
        ).all()
    )
    image_counts = dict(
        (
            await db.execute(
                select(RagImageAsset.doc_id, func.count(RagImageAsset.id))
                .where(
                    RagImageAsset.user_id == uid,
                    RagImageAsset.doc_id.in_([int(d.id) for d in docs] or [0]),
                )
                .group_by(RagImageAsset.doc_id)
            )
        ).all()
    )

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    doc_node_ids: Dict[int, str] = {}
    section_count_total = 0
    for doc in docs:
        group_id = f"kb:{int(doc.kb_id)}" if int(doc.kb_id) in kb_by_id else "kb:0"
        node_id = f"doc:{int(doc.id)}"
        doc_node_ids[int(doc.id)] = node_id
        section_nodes, section_count = _section_nodes(doc)
        section_count_total += section_count
        q_count = int(question_counts.get(int(doc.id), 0) or 0)
        i_count = int(image_counts.get(int(doc.id), 0) or 0)
        nodes.append(
            {
                "id": node_id,
                "type": "document",
                "label": (doc.file_name or "未命名资料")[:46],
                "groupId": group_id,
                "docId": int(doc.id),
                "kbId": int(doc.kb_id),
                "value": max(1, len(doc.raw_content or "")),
                "meta": {
                    "title": doc.file_name or "未命名资料",
                    "summary": _doc_summary(doc),
                    "sectionCount": section_count,
                    "questionCount": q_count,
                    "imageCount": i_count,
                    "version": int(doc.version or 1),
                    "status": int(doc.status or 0),
                    "fileType": doc.file_type or "",
                },
                "searchText": f"{doc.file_name} {doc.user_note or ''} {doc.raw_content or ''}"[:400],
            }
        )
        for section in section_nodes:
            nodes.append(section)
            edges.append(
                {
                    "id": stable_edge_id("hierarchy", node_id, str(section["id"])),
                    "source": node_id,
                    "target": section["id"],
                    "type": "hierarchy",
                    "label": "章节",
                }
            )
        if q_count:
            qid = f"questions:{int(doc.id)}"
            nodes.append(
                {
                    "id": qid,
                    "type": "question",
                    "label": f"{q_count} 道题",
                    "groupId": group_id,
                    "docId": int(doc.id),
                    "kbId": int(doc.kb_id),
                    "value": q_count,
                    "meta": {"title": "题目锚点", "count": q_count, "docId": int(doc.id)},
                    "searchText": f"{doc.file_name} 题目 题库 {q_count}",
                }
            )
            edges.append(
                {
                    "id": stable_edge_id("question_source", node_id, qid),
                    "source": node_id,
                    "target": qid,
                    "type": "question_source",
                    "label": "出题",
                }
            )
        if i_count:
            iid = f"images:{int(doc.id)}"
            nodes.append(
                {
                    "id": iid,
                    "type": "image",
                    "label": f"{i_count} 张图",
                    "groupId": group_id,
                    "docId": int(doc.id),
                    "kbId": int(doc.kb_id),
                    "value": i_count,
                    "meta": {"title": "图片资产", "count": i_count, "docId": int(doc.id)},
                    "searchText": f"{doc.file_name} 图片 图库 {i_count}",
                }
            )
            edges.append(
                {
                    "id": stable_edge_id("image_source", node_id, iid),
                    "source": node_id,
                    "target": iid,
                    "type": "image_source",
                    "label": "配图",
                }
            )

    # 笔记：只把有真实引用的笔记放进图里，避免“所有笔记都挂上去”变成噪声。
    notes = (
        await db.execute(
            select(Note)
            .where(Note.user_id == uid, Note.del_flag == "0")
            .order_by(Note.update_time.desc(), Note.note_id.desc())
            .limit(MAX_NOTES)
        )
    ).scalars().all()
    note_by_id = {int(n.note_id): n for n in notes}
    refs = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.user_id == uid, ContentReference.deleted == 0
            )
        )
    ).scalars().all()

    note_links: Dict[int, set[int]] = {}
    for ref in refs:
        doc_id: Optional[int] = None
        note_id: Optional[int] = None
        if ref.source_type in {"document", "document_image"}:
            doc_id = int(ref.source_id)
        elif ref.source_type == "note":
            note_id = int(ref.source_id)
        elif ref.source_type == "chat_image":
            doc_id = None
        if ref.target_type == "document":
            doc_id = int(ref.target_id)
        elif ref.target_type == "note":
            note_id = int(ref.target_id)
        if doc_id and note_id:
            note_links.setdefault(note_id, set()).add(doc_id)

    for note_id, doc_ids in note_links.items():
        note = note_by_id.get(note_id)
        if not note:
            continue
        nid = f"note:{note_id}"
        linked_doc = next(iter(doc_ids), None)
        group_id = f"kb:{int(next((d.kb_id for d in docs if int(d.id) == linked_doc), 0))}" if linked_doc else "kb:0"
        if group_id not in seen_groups:
            group_id = group_order[0]["id"] if group_order else "kb:0"
        nodes.append(
            {
                "id": nid,
                "type": "note",
                "label": (note.title or "未命名笔记")[:40],
                "groupId": group_id,
                "noteId": int(note_id),
                "docId": int(linked_doc) if linked_doc else None,
                "value": max(1, len(note.markdown_content or note.content or "")),
                "meta": {
                    "title": note.title or "未命名笔记",
                    "summary": _clean(note.markdown_content or note.content or "", 120),
                    "docId": int(linked_doc) if linked_doc else None,
                },
                "searchText": f"{note.title or ''} {note.markdown_content or note.content or ''}"[:300],
            }
        )
        for did in doc_ids:
            if did in doc_node_ids:
                edges.append(
                    {
                        "id": stable_edge_id("reference", doc_node_ids[did], nid),
                        "source": doc_node_ids[did],
                        "target": nid,
                        "type": "reference",
                        "label": "被引用",
                    }
                )

    # 过滤掉没有入边的笔记节点（可能 note_links 的 doc 不在当前筛选范围）。
    linked_ids = {edge["target"] for edge in edges}
    nodes = [n for n in nodes if n["type"] != "note" or n["id"] in linked_ids]

    groups = [g for g in group_order if any(n["groupId"] == g["id"] for n in nodes)]
    # 统计用真实值；没有节点的组不展示。
    return {
        "groups": groups,
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "documentCount": len([n for n in nodes if n["type"] == "document"]),
            "sectionCount": section_count_total,
            "noteCount": len([n for n in nodes if n["type"] == "note"]),
            "questionCount": sum(int(n["meta"].get("count") or 0) for n in nodes if n["type"] == "question"),
            "imageCount": sum(int(n["meta"].get("count") or 0) for n in nodes if n["type"] == "image"),
            "referenceCount": len([e for e in edges if e["type"] == "reference"]),
        },
        "legend": [
            {"type": "document", "label": "资料页", "hint": "一份资料的中心页"},
            {"type": "section", "label": "章节页", "hint": "从原文标题切出的章节"},
            {"type": "note", "label": "笔记", "hint": "通过真实引用连到资料"},
            {"type": "question", "label": "题组", "hint": "题目锚定的题量"},
            {"type": "image", "label": "图组", "hint": "已生成描述的图片数量"},
        ],
    }


__all__ = ["build_knowledge_map"]
