"""RAG 上传与文档辅助：大小限制、文件读取、格式化与错误转换。"""

import asyncio
import re
from pathlib import Path
from typing import List

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import error
from app.services.rag import rag_write_service
from app.services.rag.rag_write_service import RagConflict, RagNotFound


#: 单次上传总大小上限：多文件合计也不能超过 5MB。
MAX_BATCH_UPLOAD_BYTES = 5 * 1024 * 1024
#: 单个文件上限同样收敛到 5MB（避免一个 8MB 文件绕过“总大小 5MB”的口径）。
MAX_UPLOAD_BYTES = min(settings.MAX_FILE_SIZE, MAX_BATCH_UPLOAD_BYTES)
#: 一次最多选择的文件数，避免一次请求创建过多流水线。
MAX_UPLOAD_FILES = 20
_IMAGE_FILE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "gif"}


def _uid(current_user: dict) -> int:
    """当前登录用户 id。**唯一可信来源**。"""
    return int((current_user or {}).get("user_id") or 0)


async def _read_upload_files(files: List[UploadFile]) -> tuple[list[tuple[str, bytes]], str]:
    """读取多文件并校验单文件/总大小；返回 (payloads, error)。"""
    payloads: list[tuple[str, bytes]] = []
    total = 0
    if len(files or []) > MAX_UPLOAD_FILES:
        return [], f"一次最多上传 {MAX_UPLOAD_FILES} 个文件"
    for upload in files or []:
        raw = await upload.read()
        if not raw:
            return [], f"文件为空：{upload.filename or '未命名文件'}"
        if len(raw) > MAX_UPLOAD_BYTES:
            return [], (
                f"文件「{upload.filename or '未命名文件'}」过大"
                f"（{len(raw) / 1024 / 1024:.1f}MB），单文件上限 5MB"
            )
        total += len(raw)
        if total > MAX_BATCH_UPLOAD_BYTES:
            return [], "本次上传总大小超过 5MB，请减少文件数量或压缩后再上传"
        payloads.append((upload.filename or "未命名文档", raw))
    return payloads, ""


def _batch_image_assets(payloads: list[tuple[str, bytes]]) -> dict[str, bytes]:
    """同一批上传的图片按文件名建索引，供 Markdown 相对图片引用使用。"""
    assets: dict[str, bytes] = {}
    for filename, raw in payloads:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _IMAGE_FILE_EXTS:
            assets[Path(filename).name] = raw
    return assets


def _referenced_markdown_image_names(payloads: list[tuple[str, bytes]]) -> set[str]:
    """本批 Markdown 实际引用到的图片文件名，用于避免把随文档上传的插图再建一份图片文档。"""
    names: set[str] = set()
    pattern = re.compile(r"!\[[^\]]*\]\(([^)\s]+)\)")
    for filename, raw in payloads:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in {"md", "markdown", "txt", "doc"}:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for match in pattern.finditer(text):
            names.add(Path(match.group(1)).name)
    return names


def _upload_doc_payload(
    doc,
    kb_id: int,
    *,
    image_count: int,
    content_length: int,
    note: str = "",
    ocr_applied: bool = False,
) -> dict:
    return {
        "docId": doc.id,
        "kbId": kb_id,
        "fileName": doc.file_name,
        "note": note,
        "contentLength": content_length,
        "imageCount": image_count,
        "ocrApplied": ocr_applied,
        "status": doc.status,
        "statusText": "待解析",
        # 同名上传的版本信息：前端可据此提示「已更新为第 N 版」或「内容相同，未重复创建」。
        "version": int(getattr(doc, "version", 1) or 1),
        "versioned": bool(getattr(doc, "_was_versioned", False)),
        "unchanged": bool(getattr(doc, "_upload_unchanged", False)),
    }


async def _create_uploaded_document(
    db: AsyncSession,
    user_id: int,
    kb_id: int,
    filename: str,
    raw: bytes,
    note: str = "",
    assets: dict[str, bytes] | None = None,
    on_duplicate: str = "newVersion",
):
    """解析单个上传文件并落库；图片文件额外走手写 OCR 校对。"""
    from app.services.file_parser import build_marked_document, parse_file
    from app.services.handwriting_ocr import recognize_handwriting
    from app.services.material_organizer import analyze as analyze_material

    try:
        parsed = await asyncio.to_thread(parse_file, filename, raw, assets)
    except Exception as e:
        raise ValueError(f"文档解析失败：{e}") from e

    text = (parsed.get("textContent") or "").strip()
    marked_text, image_data_urls = build_marked_document(parsed)
    image_map = rag_write_service.persist_document_images(image_data_urls)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # 只有用户直接上传的图片才做手写 OCR；文档里的插图走智能整理的多模态分析。
    ocr_text = ""
    if not text and image_data_urls and ext in _IMAGE_FILE_EXTS:
        ocr_text = await recognize_handwriting(db, user_id, filename, raw)

    if not text and not image_data_urls:
        raise ValueError(
            f"没能从「{filename}」中提取出文本：{parsed.get('error') or '内容为空'}"
        )

    if ocr_text:
        body_text = (ocr_text + "\n\n" + marked_text).strip()
        text_for_facets = ocr_text
    else:
        body_text = (marked_text or "").strip() or text
        text_for_facets = text

    organized = analyze_material(filename, text_for_facets, parsed, image_count=len(image_map))
    doc = await rag_write_service.create_document(
        db,
        user_id,
        kb_id,
        file_name=organized["display_name"],
        raw_content=body_text,
        file_type=ext or None,
        file_size=len(raw),
        image_map=image_map,
        content_structure=parsed.get("contentStructure") or [],
        original_file_name=organized["original_file_name"],
        subject=organized["subject"],
        material_type=organized["material_type"],
        facets=organized["facets"],
        on_duplicate=on_duplicate,
    )
    if note and note.strip():
        doc.user_note = note.strip()[:200]
        await db.flush()
    return doc, image_map, len(body_text), (doc.user_note or ""), bool(ocr_text)


def _fail(e: Exception) -> dict:
    """把服务层异常翻译成响应。区分「找不到/无权限」「业务冲突」「其它」。"""
    if isinstance(e, RagNotFound):
        return error(str(e), code=404)
    if isinstance(e, RagConflict):
        return error(str(e), code=400)
    if isinstance(e, ValueError):
        return error(str(e), code=400)
    return error(f"操作失败：{e}")


