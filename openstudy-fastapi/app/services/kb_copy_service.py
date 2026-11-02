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
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.rag import DOC_PENDING, RagDocument, RagKnowledgeBase
from app.utils.file_util import get_upload_path


def _copy_physical_file(source_path: Optional[str]) -> tuple[Optional[str], int]:
    """复制真实文件到新的上传目录，返回相对路径和字节数。"""
    if not source_path:
        return source_path, 0
    raw = str(source_path).replace("\\", "/")
    if raw.startswith("/profile/"):
        raw = raw[len("/profile/"):]
    if raw.startswith("uploadPath/"):
        raw = raw[len("uploadPath/"):]
    src = raw if os.path.isabs(raw) else os.path.join(settings.UPLOAD_DIR, raw)
    if not os.path.isfile(src):
        return source_path, 0
    target_dir = get_upload_path("upload")
    target = os.path.join(
        target_dir, f"{uuid.uuid4().hex}{Path(source_path).suffix.lower()}"
    )
    shutil.copy2(src, target)
    rel = os.path.relpath(target, settings.UPLOAD_DIR).replace("\\", "/")
    return rel, os.path.getsize(target)


def _copy_image_map(image_map: Optional[dict]) -> tuple[Optional[dict], dict]:
    """图片也复制物理文件，并返回旧 URL -> 新 URL 的映射。"""
    if not image_map:
        return image_map, {}
    copied: dict = {}
    url_map: dict = {}
    for key, url in (image_map or {}).items():
        if not isinstance(url, str) or url.startswith(("http://", "https://")):
            copied[key] = url
            continue
        rel, _ = _copy_physical_file(url)
        if rel:
            new_url = f"/profile/{rel}"
            copied[key] = new_url
            url_map[url] = new_url
        else:
            copied[key] = url
    return copied, url_map


def _copy_doc_files(doc: RagDocument) -> tuple[Optional[str], int, Optional[dict], Optional[str]]:
    file_path, file_size = _copy_physical_file(doc.file_path)
    raw_content = doc.raw_content
    # 老资料/演示资料可能只有 raw_content，没有原始物理文件；落一份正文文件，
    # 保证领取者拿到的是可独立存在、可再次编辑的副本。
    if not file_path and raw_content:
        target_dir = get_upload_path("upload")
        ext = Path(doc.file_name or "document.md").suffix.lower() or ".md"
        target = os.path.join(target_dir, f"{uuid.uuid4().hex}{ext}")
        data = raw_content.encode("utf-8")
        with open(target, "wb") as f:
            f.write(data)
        file_path = os.path.relpath(target, settings.UPLOAD_DIR).replace("\\", "/")
        file_size = len(data)
    image_map, url_map = _copy_image_map(doc.image_map)
    for old_url, new_url in url_map.items():
        if raw_content:
            raw_content = raw_content.replace(old_url, new_url)
    return file_path, (file_size or int(doc.file_size or 0)), image_map, raw_content


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
        copied_path, copied_size, copied_image_map, copied_raw = _copy_doc_files(doc)
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
            file_size=copied_size,
            file_path=copied_path,
            raw_content=copied_raw,
            image_map=copied_image_map,
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
    copied_path, copied_size, copied_image_map, copied_raw = _copy_doc_files(source_doc)
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
        file_size=copied_size,
        file_path=copied_path,
        raw_content=copied_raw,
        image_map=copied_image_map,
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
