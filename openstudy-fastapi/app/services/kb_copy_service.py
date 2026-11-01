"""知识库深拷贝服务。

知识库分享领取时使用：把源知识库及其文档复制到领取者名下，生成一个
真正属于对方、可以继续编辑 / 检索的副本。

不复制：
  · 向量分块（目标库的文档会重新走解析/向量化，避免跨 embedding 配置漂移）；
  · 任何个人状态（笔记、错题、收藏等，知识库没有这些概念）。

调用方负责 commit；复制出的文档会由接口放进 BackgroundTasks 重新处理。
"""

from __future__ import annotations

import copy as _copy
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import DOC_PENDING, RagDocument, RagKnowledgeBase


def copy_kb_name(source_name: str) -> str:
    return f"{source_name}（来自分享）"[:255]


async def copy_knowledge_base(
    db: AsyncSession,
    source_kb: RagKnowledgeBase,
    target_user_id: int,
    new_name: Optional[str] = None,
) -> tuple[RagKnowledgeBase, list[int]]:
    """复制知识库 + 文档，返回新库和待重新处理的文档 ID。"""
    if not source_kb:
        raise ValueError("源知识库不存在")

    new_kb = RagKnowledgeBase(
        user_id=target_user_id,
        name=(new_name or copy_kb_name(source_kb.name))[:255],
        description=source_kb.description,
        embedding_model=source_kb.embedding_model,
        embedding_dim=source_kb.embedding_dim,
        chunk_size=source_kb.chunk_size,
        chunk_overlap=source_kb.chunk_overlap,
        doc_count=0,
        chunk_count=0,
        status="0",
        del_flag="0",
        disabled=0,
        is_workspace=0,
        create_time=datetime.now(),
    )
    db.add(new_kb)
    await db.flush()

    docs = (
        await db.execute(
            select(RagDocument)
            .where(RagDocument.kb_id == source_kb.id)
            .order_by(RagDocument.id)
        )
    ).scalars().all()

    pending_ids: list[int] = []
    for doc in docs:
        copied = RagDocument(
            kb_id=new_kb.id,
            user_id=target_user_id,
            file_name=doc.file_name,
            original_file_name=doc.original_file_name,
            subject=doc.subject,
            material_type=doc.material_type,
            facets=_copy.deepcopy(doc.facets),
            excluded_ranges=_copy.deepcopy(doc.excluded_ranges),
            file_type=doc.file_type,
            file_size=doc.file_size,
            file_path=doc.file_path,
            raw_content=doc.raw_content,
            image_map=_copy.deepcopy(doc.image_map),
            content_structure=_copy.deepcopy(doc.content_structure),
            user_note=doc.user_note,
            chunk_count=0,
            index_version=1,
            status=DOC_PENDING,
            disabled=0,
            error_msg=None,
            create_time=datetime.now(),
        )
        db.add(copied)
        await db.flush()
        pending_ids.append(int(copied.id))

    new_kb.doc_count = len(pending_ids)
    new_kb.chunk_count = 0
    await db.flush()
    return new_kb, pending_ids


async def copy_document_to_kb(
    db: AsyncSession,
    source_doc: RagDocument,
    target_kb: RagKnowledgeBase,
    target_user_id: int,
) -> RagDocument:
    """把单份文档复制到目标知识库（文档分享领取使用）。"""
    copied = RagDocument(
        kb_id=target_kb.id,
        user_id=target_user_id,
        file_name=source_doc.file_name,
        original_file_name=source_doc.original_file_name,
        subject=source_doc.subject,
        material_type=source_doc.material_type,
        facets=_copy.deepcopy(source_doc.facets),
        excluded_ranges=_copy.deepcopy(source_doc.excluded_ranges),
        file_type=source_doc.file_type,
        file_size=source_doc.file_size,
        file_path=source_doc.file_path,
        raw_content=source_doc.raw_content,
        image_map=_copy.deepcopy(source_doc.image_map),
        content_structure=_copy.deepcopy(source_doc.content_structure),
        user_note=source_doc.user_note,
        chunk_count=0,
        index_version=1,
        status=DOC_PENDING,
        disabled=0,
        error_msg=None,
        create_time=datetime.now(),
    )
    db.add(copied)
    await db.flush()
    target_kb.doc_count = int(target_kb.doc_count or 0) + 1
    await db.flush()
    return copied
