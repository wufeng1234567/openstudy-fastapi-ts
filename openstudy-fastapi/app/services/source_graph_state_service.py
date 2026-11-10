"""资料夹来源实体集：指纹、状态与增量扫描。

每个来源（文档/网页/图片/题库/笔记）是一个独立实体集。增量更新只处理
尚未处理或内容 hash 变化的来源，不重新挖掘已完成的实体集。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentReference, RagImageAsset
from app.models.note import Note
from app.models.question import QuestionBank, QuestionMain
from app.models.rag import RagDocument
from app.models.source_graph_state import SourceGraphState
from app.models.wiki import RagWikiPage
from app.services import note_kb_link_service, question_bank_link_service


def _hash(value: str) -> str:
    return hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()


def _page_has_source(page: RagWikiPage, source_type: str, source_id: int) -> bool:
    meta = page.generation_meta or {}
    if str(meta.get("sourceType") or "") == source_type and int(meta.get("sourceId") or 0) == int(source_id):
        return True
    if source_type in {"document", "web"}:
        return int(source_id) in [int(x) for x in (page.source_doc_ids or []) if str(x).isdigit()]
    return False


async def _has_pages(db: AsyncSession, *, user_id: int, kb_id: int, source_type: str, source_id: int) -> bool:
    pages = (
        await db.execute(
            select(RagWikiPage).where(
                RagWikiPage.user_id == int(user_id),
                RagWikiPage.kb_id == int(kb_id),
                RagWikiPage.status.in_(["ready", "stale"]),
            )
        )
    ).scalars().all()
    return any(_page_has_source(page, source_type, source_id) for page in pages)


async def _source_descriptors(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    uid = int(user_id)
    kid = int(kb_id)
    result: List[Dict[str, Any]] = []

    docs = (
        await db.execute(
            select(RagDocument).where(
                RagDocument.user_id == uid,
                RagDocument.kb_id == kid,
                RagDocument.disabled == 0,
            )
        )
    ).scalars().all()
    for doc in docs:
        source_type = "web" if str(doc.source_url or "").strip() else "document"
        raw = str(doc.raw_content or "")
        result.append(
            {
                "sourceType": source_type,
                "sourceId": int(doc.id),
                "sourceName": str(doc.file_name or "未命名资料"),
                "contentHash": _hash(f"{doc.file_name}|{doc.version}|{doc.index_version}|{doc.status}|{raw[:12000]}"),
            }
        )

    images = (
        await db.execute(
            select(RagImageAsset).where(
                RagImageAsset.user_id == uid,
                RagImageAsset.kb_id == kid,
            )
        )
    ).scalars().all()
    for image in images:
        # 文档图片也可以成为一个独立图片实体集；只有真正有描述/OCR 文本的图片才处理。
        text = " ".join(
            str(item or "")
            for item in (image.caption, image.ocr_text, " ".join(image.keywords or []))
        ).strip()
        if not text:
            continue
        result.append(
            {
                "sourceType": "image",
                "sourceId": int(image.id),
                "sourceName": str(image.file_name or "图片"),
                "contentHash": _hash(f"{image.asset_key}|{text}"),
            }
        )

    linked_bank_ids = await question_bank_link_service.linked_bank_ids(db, user_id=uid, kb_id=kid)
    if linked_bank_ids:
        banks = (
            await db.execute(
                select(QuestionBank).where(
                    QuestionBank.id.in_(linked_bank_ids),
                    QuestionBank.user_id == uid,
                    QuestionBank.status == "0",
                )
            )
        ).scalars().all()
        for bank in banks:
            max_qid = await db.scalar(
                select(func.max(QuestionMain.id)).where(
                    QuestionMain.bank_id == int(bank.id),
                    QuestionMain.status == "0",
                )
            )
            result.append(
                {
                    "sourceType": "bank",
                    "sourceId": int(bank.id),
                    "sourceName": str(bank.bank_name or "题库"),
                    "contentHash": _hash(f"{bank.bank_name}|{bank.total_questions}|{int(max_qid or 0)}"),
                }
            )

    # 笔记只有被显式引用到某个知识百科页面时，才属于该资料夹。
    note_refs = (
        await db.execute(
            select(ContentReference.source_id, RagWikiPage.kb_id)
            .select_from(
                ContentReference.__table__.join(
                    RagWikiPage.__table__,
                    (ContentReference.target_type == "wiki_page")
                    & (ContentReference.target_id == RagWikiPage.id),
                )
            )
            .where(
                ContentReference.user_id == uid,
                ContentReference.source_type == "note",
                ContentReference.deleted == 0,
                RagWikiPage.user_id == uid,
                RagWikiPage.kb_id == kid,
            )
        )
    ).all()
    # 兼容旧 ContentReference 旁路 + P2 新增的 note_kb_link 显式导入。
    note_ids = {int(note_id) for note_id, _ in note_refs if int(note_id or 0) > 0}
    note_ids.update(
        await note_kb_link_service.linked_note_ids(db, user_id=uid, kb_id=kid)
    )
    for note_id in sorted(note_ids):
        note = await db.get(Note, int(note_id))
        if not note:
            continue
        text = "\n".join(str(item or "") for item in (note.title, note.markdown_content, note.content, note.tags))
        result.append(
            {
                "sourceType": "note",
                "sourceId": int(note.note_id),
                "sourceName": str(note.title or "笔记"),
                "contentHash": _hash(text),
            }
        )
    return result


async def sync_states(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    """补齐/刷新所有来源状态，返回当前待处理来源。"""
    descriptors = await _source_descriptors(db, user_id=user_id, kb_id=kb_id)
    pending: List[Dict[str, Any]] = []
    for item in descriptors:
        state = (
            await db.execute(
                select(SourceGraphState).where(
                    SourceGraphState.user_id == int(user_id),
                    SourceGraphState.kb_id == int(kb_id),
                    SourceGraphState.source_type == item["sourceType"],
                    SourceGraphState.source_id == int(item["sourceId"]),
                )
            )
        ).scalar_one_or_none()
        if state is None:
            has_pages = await _has_pages(
                db,
                user_id=user_id,
                kb_id=kb_id,
                source_type=item["sourceType"],
                source_id=int(item["sourceId"]),
            )
            state = SourceGraphState(
                user_id=int(user_id),
                kb_id=int(kb_id),
                source_type=item["sourceType"],
                source_id=int(item["sourceId"]),
                content_hash=item["contentHash"],
                status="done" if has_pages else "pending",
                entity_set_version=1,
                last_processed_at=datetime.now() if has_pages else None,
            )
            db.add(state)
            await db.flush()
        elif state.content_hash != item["contentHash"]:
            state.content_hash = item["contentHash"]
            state.status = "pending"
            state.entity_set_version = int(state.entity_set_version or 1) + 1
            state.error = ""
            state.update_time = datetime.now()
        if state.status in {"pending", "failed"}:
            pending.append(
                {
                    **item,
                    "stateId": int(state.id),
                    "status": state.status,
                    "entitySetVersion": int(state.entity_set_version or 1),
                }
            )
    await db.flush()
    return pending


async def mark_state(
    db: AsyncSession,
    *,
    state_id: int,
    status: str,
    error: str = "",
) -> None:
    state = await db.get(SourceGraphState, int(state_id))
    if not state:
        return
    state.status = status
    state.error = str(error or "")[:480]
    state.update_time = datetime.now()
    if status == "done":
        state.last_processed_at = datetime.now()
    await db.flush()


async def source_text(db: AsyncSession, *, source_type: str, source_id: int) -> str:
    if source_type in {"document", "web"}:
        doc = await db.get(RagDocument, int(source_id))
        return str((doc.raw_content if doc else "") or "")
    if source_type == "image":
        image = await db.get(RagImageAsset, int(source_id))
        if not image:
            return ""
        return "\n".join(
            str(item or "")
            for item in (image.caption, image.ocr_text, " ".join(image.keywords or []))
        )
    if source_type == "bank":
        rows = (
            await db.execute(
                select(QuestionMain.question_text, QuestionMain.analysis)
                .where(QuestionMain.bank_id == int(source_id), QuestionMain.status == "0")
                .order_by(QuestionMain.id.asc())
                .limit(200)
            )
        ).all()
        return "\n\n".join(
            f"题目：{str(row.question_text or '')}\n解析：{str(row.analysis or '')}"
            for row in rows
        )
    if source_type == "note":
        note = await db.get(Note, int(source_id))
        if not note:
            return ""
        return "\n".join(str(item or "") for item in (note.title, note.markdown_content, note.content, note.tags))
    return ""


__all__ = ["sync_states", "mark_state", "source_text"]
