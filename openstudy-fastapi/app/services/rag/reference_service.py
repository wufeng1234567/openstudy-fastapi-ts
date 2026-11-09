"""统一引用服务（0.4.x）。

与 `QuestionSource` 的关系
--------------------------
题目 → 原文的旧链路继续走 `question_source`，本服务补的是「图片/笔记/文档/题目」
之间的多向引用。两边都保留 quote + offset，属于兼容而非重复：
  · `QuestionSource` 是题目链路的历史表，已有数据不能重写；
  · `ContentReference` 是面向资料知识网络的通用层，地图只会读它和 QuestionSource 的并集。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_upload import ChatUploadImage
from app.models.content import ContentReference, RagImageAsset
from app.models.note import Note
from app.models.question import QuestionMain
from app.models.rag import RagDocument
from app.models.wiki import RagWikiPage

SOURCE_TYPES = {"document", "document_image", "chat_image", "note", "question"}
TARGET_TYPES = {"document", "note", "question", "image", "wiki_page"}


def _trim(value: Any, limit: int = 800) -> str:
    text = str(value or "").strip()
    return text[:limit]


async def _get_doc(db: AsyncSession, user_id: int, doc_id: int) -> RagDocument:
    doc = (
        await db.execute(
            select(RagDocument).where(
                RagDocument.user_id == int(user_id),
                RagDocument.id == int(doc_id),
            )
        )
    ).scalar_one_or_none()
    if not doc:
        raise ValueError("来源文档不存在或无权访问")
    return doc


async def _get_note(db: AsyncSession, user_id: int, note_id: int) -> Note:
    note = (
        await db.execute(
            select(Note).where(Note.note_id == int(note_id), Note.user_id == int(user_id))
        )
    ).scalar_one_or_none()
    if not note:
        raise ValueError("笔记不存在或无权访问")
    return note


async def _validate_source(
    db: AsyncSession, user_id: int, source_type: str, source_id: int, source_sub_id: Optional[str]
) -> None:
    if source_type not in SOURCE_TYPES:
        raise ValueError("不支持的引用来源类型")
    if source_type in {"document", "document_image"}:
        doc = await _get_doc(db, user_id, source_id)
        if source_type == "document_image":
            if source_sub_id is None or str(source_sub_id) not in {str(k) for k in (doc.image_map or {}).keys()}:
                raise ValueError("来源图片不存在于该文档")
    elif source_type == "chat_image":
        image = (
            await db.execute(
                select(ChatUploadImage).where(
                    ChatUploadImage.id == int(source_id),
                    ChatUploadImage.user_id == int(user_id),
                    ChatUploadImage.deleted == 0,
                )
            )
        ).scalar_one_or_none()
        if not image:
            raise ValueError("聊天图片不存在或无权访问")
    elif source_type == "note":
        await _get_note(db, user_id, source_id)
    elif source_type == "question":
        row = (
            await db.execute(select(QuestionMain).where(QuestionMain.id == int(source_id)))
        ).scalar_one_or_none()
        if not row:
            raise ValueError("来源题目不存在")


async def _validate_target(
    db: AsyncSession, user_id: int, target_type: str, target_id: int
) -> None:
    if target_type not in TARGET_TYPES:
        raise ValueError("不支持的引用目标类型")
    if target_type == "document":
        await _get_doc(db, user_id, target_id)
    elif target_type == "note":
        await _get_note(db, user_id, target_id)
    elif target_type == "question":
        row = (
            await db.execute(select(QuestionMain).where(QuestionMain.id == int(target_id)))
        ).scalar_one_or_none()
        if not row:
            raise ValueError("目标题目不存在")
    elif target_type == "image":
        row = (
            await db.execute(
                select(RagImageAsset).where(
                    RagImageAsset.user_id == int(user_id),
                    RagImageAsset.id == int(target_id),
                )
            )
        ).scalar_one_or_none()
        if not row:
            raise ValueError("目标图片不存在或无权访问")
    elif target_type == "wiki_page":
        row = (
            await db.execute(
                select(RagWikiPage).where(
                    RagWikiPage.user_id == int(user_id),
                    RagWikiPage.id == int(target_id),
                )
            )
        ).scalar_one_or_none()
        if not row:
            raise ValueError("目标知识百科主题页不存在或无权访问")


async def create_reference(
    db: AsyncSession,
    user_id: int,
    *,
    source_type: str,
    source_id: int,
    source_sub_id: Optional[str] = None,
    target_type: str,
    target_id: int,
    quote: str = "",
    start_offset: Optional[int] = None,
    end_offset: Optional[int] = None,
    created_by: str = "user",
) -> Dict[str, Any]:
    uid = int(user_id)
    st = str(source_type or "").strip()
    tt = str(target_type or "").strip()
    await _validate_source(db, uid, st, int(source_id), source_sub_id)
    await _validate_target(db, uid, tt, int(target_id))

    # 同一图片 → 同一目标只保留一条，重复插入是更新 quote，不制造脏计数。
    existing = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.user_id == uid,
                ContentReference.source_type == st,
                ContentReference.source_id == int(source_id),
                ContentReference.source_sub_id == (str(source_sub_id) if source_sub_id is not None else None),
                ContentReference.target_type == tt,
                ContentReference.target_id == int(target_id),
                ContentReference.deleted == 0,
            )
        )
    ).scalars().first()
    if existing:
        existing.quote = _trim(quote) or existing.quote
        existing.start_offset = start_offset if start_offset is not None else existing.start_offset
        existing.end_offset = end_offset if end_offset is not None else existing.end_offset
        await db.commit()
        return await get_reference(db, uid, existing.id)

    row = ContentReference(
        user_id=uid,
        source_type=st,
        source_id=int(source_id),
        source_sub_id=str(source_sub_id) if source_sub_id is not None else None,
        target_type=tt,
        target_id=int(target_id),
        quote=_trim(quote),
        start_offset=start_offset,
        end_offset=end_offset,
        created_by=created_by or "user",
    )
    db.add(row)
    await db.commit()

    # 笔记被引用进知识百科页面时，把笔记正文也同步进实体图；失败不影响引用本身。
    if st == "note" and tt == "wiki_page":
        try:
            from app.models.note import Note
            from app.models.wiki import RagWikiPage
            from app.services.rag.source_graph_service import sync_text_source

            note = (
                await db.execute(select(Note).where(Note.note_id == int(source_id), Note.user_id == uid))
            ).scalar_one_or_none()
            page = (
                await db.execute(
                    select(RagWikiPage).where(
                        RagWikiPage.id == int(target_id),
                        RagWikiPage.user_id == uid,
                    )
                )
            ).scalar_one_or_none()
            if note and page:
                text = "\n".join(
                    item
                    for item in (note.title, note.markdown_content, note.content, note.tags)
                    if str(item or "").strip()
                )
                await sync_text_source(
                    db,
                    user_id=uid,
                    kb_id=int(page.kb_id),
                    source_type="note",
                    source_id=int(note.note_id),
                    source_name=str(note.title or "笔记"),
                    text=text,
                )
        except Exception as graph_error:  # noqa: BLE001
            from loguru import logger

            logger.warning("[reference] note graph sync failed: {}", graph_error)

    return await get_reference(db, uid, row.id)


async def _describe_target(db: AsyncSession, user_id: int, target_type: str, target_id: int) -> Dict[str, Any]:
    if target_type == "note":
        note = await _get_note(db, user_id, target_id)
        return {"type": "note", "id": note.note_id, "title": note.title or "未命名笔记"}
    if target_type == "document":
        doc = await _get_doc(db, user_id, target_id)
        return {"type": "document", "id": doc.id, "title": doc.file_name or "未命名资料"}
    if target_type == "question":
        row = (
            await db.execute(select(QuestionMain).where(QuestionMain.id == int(target_id)))
        ).scalar_one_or_none()
        return {
            "type": "question",
            "id": int(target_id),
            "title": ((row.question_text or row.content or "题目")[:72] if row else "题目"),
        }
    if target_type == "image":
        row = (
            await db.execute(
                select(RagImageAsset).where(
                    RagImageAsset.user_id == int(user_id), RagImageAsset.id == int(target_id)
                )
            )
        ).scalar_one_or_none()
        return {"type": "image", "id": int(target_id), "title": row.file_name if row else "图片"}
    if target_type == "wiki_page":
        row = (
            await db.execute(
                select(RagWikiPage).where(
                    RagWikiPage.user_id == int(user_id), RagWikiPage.id == int(target_id)
                )
            )
        ).scalar_one_or_none()
        return {"type": "wiki_page", "id": int(target_id), "title": row.title if row else "知识百科主题页"}
    return {"type": target_type, "id": target_id, "title": target_type}


async def get_reference(db: AsyncSession, user_id: int, reference_id: int) -> Dict[str, Any]:
    row = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.id == int(reference_id),
                ContentReference.user_id == int(user_id),
                ContentReference.deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise ValueError("引用不存在或无权访问")

    source: Dict[str, Any] = {"type": row.source_type, "id": row.source_id, "subId": row.source_sub_id}
    if row.source_type in {"document", "document_image"}:
        doc = await _get_doc(db, user_id, row.source_id)
        source.update(
            {
                "docId": doc.id,
                "title": doc.file_name or "未命名资料",
                "sectionTitle": "",
                "url": (doc.image_map or {}).get(str(row.source_sub_id)) if row.source_type == "document_image" else "",
            }
        )
    elif row.source_type == "chat_image":
        image = (
            await db.execute(
                select(ChatUploadImage).where(
                    ChatUploadImage.id == int(row.source_id),
                    ChatUploadImage.user_id == int(user_id),
                )
            )
        ).scalar_one_or_none()
        source.update({"title": image.image_name if image else "聊天图片", "url": image.url if image else ""})
    elif row.source_type == "note":
        note = await _get_note(db, user_id, row.source_id)
        source.update({"title": note.title or "未命名笔记", "url": ""})
    elif row.source_type == "question":
        source.update({"title": "题目", "url": ""})

    target = await _describe_target(db, user_id, row.target_type, row.target_id)
    return {
        "id": row.id,
        "sourceType": row.source_type,
        "sourceId": row.source_id,
        "sourceSubId": row.source_sub_id,
        "targetType": row.target_type,
        "targetId": row.target_id,
        "quote": row.quote or "",
        "startOffset": row.start_offset,
        "endOffset": row.end_offset,
        "createdBy": row.created_by,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M") if row.create_time else "",
        "source": source,
        "target": target,
    }


async def list_references(
    db: AsyncSession,
    user_id: int,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    query = select(ContentReference).where(
        ContentReference.user_id == int(user_id), ContentReference.deleted == 0
    )
    if target_type:
        query = query.where(ContentReference.target_type == target_type)
    if target_id is not None:
        query = query.where(ContentReference.target_id == int(target_id))
    if source_type:
        query = query.where(ContentReference.source_type == source_type)
    if source_id is not None:
        query = query.where(ContentReference.source_id == int(source_id))
    rows = (
        await db.execute(
            query.order_by(ContentReference.create_time.desc(), ContentReference.id.desc()).limit(
                max(1, min(int(limit or 100), 300))
            )
        )
    ).scalars().all()
    return [await get_reference(db, user_id, row.id) for row in rows]


async def delete_reference(db: AsyncSession, user_id: int, reference_id: int) -> Dict[str, Any]:
    row = (
        await db.execute(
            select(ContentReference).where(
                ContentReference.id == int(reference_id),
                ContentReference.user_id == int(user_id),
                ContentReference.deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise ValueError("引用不存在或无权访问")
    row.deleted = 1
    await db.commit()
    return {"id": int(reference_id), "deleted": True}


__all__ = [
    "create_reference",
    "get_reference",
    "list_references",
    "delete_reference",
]
