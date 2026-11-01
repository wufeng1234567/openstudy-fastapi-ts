"""知识库分享领取服务。

分享的语义是「把源知识库的已有索引映射一份给领取者」：
  · 文档正文、分块、向量、图片映射全部原样复制；
  · **不重新解析、不重新向量化** —— 源库主已经处理过；
  · 复制后的副本仍然属于领取者，可以继续编辑和检索。
"""

from __future__ import annotations

import copy as _copy
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagDocument, RagKnowledgeBase


async def _copy_chunks(
    db: AsyncSession,
    source_doc_id: int,
    target_doc_id: int,
    target_kb_id: int,
) -> None:
    """直接复制已有分块和向量，避免领取后重跑 embedding。"""
    await db.execute(
        text(
            """
            INSERT INTO rag_document_chunk
              (kb_id, doc_id, chunk_index, index_version, content, content_length,
               token_count, content_tokens, embedding, meta_data, create_time)
            SELECT :target_kb_id, :target_doc_id, chunk_index, index_version, content,
                   content_length, token_count, content_tokens, embedding, meta_data, now()
            FROM rag_document_chunk
            WHERE doc_id = :source_doc_id
            """
        ),
        {
            "target_kb_id": int(target_kb_id),
            "target_doc_id": int(target_doc_id),
            "source_doc_id": int(source_doc_id),
        },
    )


def copy_kb_name(source_name: str) -> str:
    return f"{source_name}（来自分享）"[:255]


async def copy_knowledge_base(
    db: AsyncSession,
    source_kb: RagKnowledgeBase,
    target_user_id: int,
    new_name: Optional[str] = None,
) -> tuple[RagKnowledgeBase, list[int]]:
    """复制知识库 + 文档 + 已有分块/向量，返回新库（无需再处理的文档列表为空）。"""
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
            chunk_count=int(doc.chunk_count or 0),
            index_version=doc.index_version,
            status=doc.status,
            disabled=0,
            error_msg=None,
            create_time=datetime.now(),
        )
        db.add(copied)
        await db.flush()
        await _copy_chunks(db, int(doc.id), int(copied.id), int(new_kb.id))
        pending_ids.append(int(copied.id))

    new_kb.doc_count = len(pending_ids)
    new_kb.chunk_count = sum(int(doc.chunk_count or 0) for doc in docs)
    await db.flush()
    return new_kb, []


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
        chunk_count=int(source_doc.chunk_count or 0),
        index_version=source_doc.index_version,
        status=source_doc.status,
        disabled=0,
        error_msg=None,
        create_time=datetime.now(),
    )
    db.add(copied)
    await db.flush()
    await _copy_chunks(db, int(source_doc.id), int(copied.id), int(target_kb.id))
    target_kb.doc_count = int(target_kb.doc_count or 0) + 1
    target_kb.chunk_count = int(target_kb.chunk_count or 0) + int(source_doc.chunk_count or 0)
    await db.flush()
    return copied
