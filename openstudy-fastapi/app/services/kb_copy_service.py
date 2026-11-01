"""知识库分享领取服务。

用户明确的分享语义（2026-11-01 修正）：
  · 分享是“把物理文件本体复制给领取者”，领取者拿到后可以二次修改；
  · 因此每个复制出的文档都必须**重新解析、分块、向量化**，不能复用原库
    的索引（否则正文修改后旧向量会指向旧内容）；
  · 原分享者的文件和索引完全不受影响。

为了在产品上区分来源，复制出的知识库和文档都会带 `source_type='share'`、
`source_kb_id` / `source_doc_id` / `share_id` 标记。
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
    share_id: Optional[int] = None,
) -> tuple[RagKnowledgeBase, list[int]]:
    """复制知识库 + 物理文档，返回新库和待重新解析/向量化的文档 ID。"""
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
        source_type="share",
        source_kb_id=int(source_kb.id),
        share_id=share_id,
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
            source_type="share",
            source_doc_id=int(doc.id),
            share_id=share_id,
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
    share_id: Optional[int] = None,
) -> RagDocument:
    """把单份物理文档复制到目标知识库，并交给后台重新解析/向量化。"""
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
        source_type="share",
        source_doc_id=int(source_doc.id),
        share_id=share_id,
        create_time=datetime.now(),
    )
    db.add(copied)
    await db.flush()
    target_kb.doc_count = int(target_kb.doc_count or 0) + 1
    await db.flush()
    return copied
