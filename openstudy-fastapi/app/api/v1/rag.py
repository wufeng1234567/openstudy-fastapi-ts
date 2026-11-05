"""
RAG 知识库 API

路径风格对齐仓库既有写法（camelCase 段，如 `/courses/courses`、`/wordBooks/...`）。

权限
----
**所有端点都从 JWT 取 user_id**，不从请求体读 `userId`。
SpringBoot 版 `/rag/**` 是 permit-all + `userId` 参数默认 1 + 无归属校验 —— 任意人
猜到 id 就能读删他人知识库。这里每个操作都经 `rag_write_service` 校验归属。

响应形状
--------
沿用仓库主流形状：HTTP 200 + `body.code`（前端判 `code !== 200`）。
与 `/ai/agent/execute`（403 + fail 信封）、SSE（403）那几个族**刻意不同** —— 不要统一。
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import error, success
from app.core.security import get_current_user, require_admin
from app.database import async_session_factory, get_db
from app.services.rag import (
    document_pipeline,
    gallery_service,
    knowledge_map_service,
    rag_config_service,
    rag_query_service,
    rag_write_service,
    reference_service,
    workspace_service,
)
from app.services.rag.rag_write_service import RagConflict, RagNotFound

router = APIRouter(prefix="/rag")

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


# ============================================================ 知识库

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class KnowledgeBaseUpdate(BaseModel):
    # ⚠️⚠️ `extra='forbid'` 是**必选项**，不是洁癖。
    #    pydantic v2 默认 `extra='ignore'`（实测 `pydantic==2.10.4`）：
    #    前端把字段名写成 `blocked` / `isDisabled` / `enabled`（或后端改了名没同步）
    #    → 未知字段被**静默丢弃** → PUT 照回 200、前端 `loadKbs()` 也照成功，
    #    而库里一个字节没变。表现就是「开关翻过去了、模型照样读到这个库」——
    #    这条链路上任何静态检查都查不出来（前端静态检查不查类型）。
    #    改成 forbid 之后，字段名对不上会立刻变 **422**，当场暴露。
    #    既有前端只发 name / description（都是声明过的字段），不受影响。
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    #: 屏蔽开关：0 = 启用，1 = 已屏蔽（其余非零值在服务层归一成 1）。
    #: 字段名端到端冻结为 `disabled`（DB 列 / ORM 属性 / 请求体键 / `_kb_brief` /
    #: GET 详情 / 前端类型，六处同名），配合上面的 extra='forbid' 才拦得住写错。
    #: 走既有的 PUT 而不是新开 `/knowledgeBase/{id}/block`：`catch_all` 是按
    #: **路径关键字**分发的，没有关键字的路由会兜底成 `success(None)` ——
    #: 即「路径写错 = 看起来成功的 200 + data:null」，这种坑不值得为对称性踩一次。
    disabled: Optional[int] = None


@router.get("/knowledgeBase/list")
async def list_knowledge_bases(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户的知识库列表。只能看到自己的。"""
    try:
        return success(await rag_write_service.list_knowledge_bases(db, _uid(current_user)))
    except Exception as e:
        return _fail(e)


@router.post("/knowledgeBase")
async def create_knowledge_base(
    data: KnowledgeBaseCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        kb = await rag_write_service.create_knowledge_base(
            db, _uid(current_user), data.name, data.description
        )
        return success(
            {
                "kbId": kb.id,
                "name": kb.name,
                "description": kb.description,
                "docCount": kb.doc_count,
                "chunkCount": kb.chunk_count,
                # 新库恒为启用；照样下发（同一份 `kb_disabled_flag`）是为了让
                # 「凡是返回知识库对象的响应都带 disabled」这条口径没有例外 ——
                # 少一处，前端那一行就可能绑到 undefined（见 kb_disabled_flag 的说明）。
                "disabled": rag_write_service.kb_disabled_flag(kb),
            },
            "资料夹创建成功",
        )
    except Exception as e:
        return _fail(e)


@router.get("/knowledgeBase/{kb_id}")
async def get_knowledge_base(
    kb_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        kb = await rag_write_service.get_knowledge_base(db, _uid(current_user), kb_id)
        return success(
            {
                "kbId": kb.id,
                "name": kb.name,
                "description": kb.description,
                "docCount": kb.doc_count,
                "chunkCount": kb.chunk_count,
                # ⚠️ 与 `_kb_brief`（列表）**必须同时有**：详情是手写出来的另一份，
                #    只改一处就会出现「列表知道它被屏蔽了、详情不知道」。
                #    归一走同一个函数（整数 0/1，永不 null / 字符串）—— 见
                #    `rag_write_service.kb_disabled_flag` 的 el-switch 说明。
                "disabled": rag_write_service.kb_disabled_flag(kb),
                "embeddingModel": kb.embedding_model,
                "chunkSize": kb.chunk_size,
                "chunkOverlap": kb.chunk_overlap,
                "createTime": kb.create_time.isoformat(sep=" ") if kb.create_time else None,
            }
        )
    except Exception as e:
        return _fail(e)


@router.put("/knowledgeBase/{kb_id}")
async def update_knowledge_base(
    kb_id: int,
    data: KnowledgeBaseUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        kb = await rag_write_service.update_knowledge_base(
            db,
            _uid(current_user),
            kb_id,
            name=data.name,
            description=data.description,
            disabled=data.disabled,
        )
        # 回显 disabled：前端关掉开关后要立刻能从响应里确认状态，
        # 而不是再发一次 GET 去猜（不 echo 的话「点了没反应」看不出是写失败还是没写）。
        return success(
            {
                "kbId": kb.id,
                "name": kb.name,
                "disabled": rag_write_service.kb_disabled_flag(kb),
            },
            "更新成功",
        )
    except Exception as e:
        return _fail(e)


@router.delete("/knowledgeBase/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删知识库（逻辑删）+ 物理清掉它的文档与分块，避免残留向量被检索到。"""
    try:
        info = await rag_write_service.delete_knowledge_base(db, _uid(current_user), kb_id)
        return success(info, "资料夹已删除")
    except Exception as e:
        return _fail(e)


# ============================================================ 文档

class TextImport(BaseModel):
    kbId: int
    content: str
    fileName: Optional[str] = "未命名文档.txt"


@router.post("/document/upload")
async def upload_document(
    background: BackgroundTasks,
    kb_id: int = Query(..., alias="kbId"),
    file: List[UploadFile] = File(...),
    onDuplicate: str = Query(
        "newVersion",
        description="同名资料策略：newVersion=生成新版本（默认）/ reject=拒绝",
    ),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传一个或多个文档：同步解析落库 + 每个文档独立异步向量化。

    多文件一次请求合计不超过 5MB（单文件也不超过 5MB），避免一个大文件或
    批量上传把解析/向量化队列打满。

    同名策略：默认生成新版本（旧正文进历史版本，最多保留 20 个快照）；
    传 `onDuplicate=reject` 可恢复旧的「同名即拒绝」行为。
    """
    uid = _uid(current_user)
    try:
        # 先确认知识库归属，避免替别人的库上传
        await rag_write_service.get_knowledge_base(db, uid, kb_id)
    except Exception as e:
        return _fail(e)

    payloads, size_error = await _read_upload_files(file)
    if size_error:
        return error(size_error, code=400)

    assets = _batch_image_assets(payloads)
    referenced_images = _referenced_markdown_image_names(payloads)
    documents: list[dict] = []
    failed: list[dict] = []
    for filename, raw in payloads:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _IMAGE_FILE_EXTS and Path(filename).name in referenced_images:
            # 这张图是 Markdown 的随文插图，已进入 markdown 文档的 imageMap，
            # 不再单独建一份“图片文档”。
            continue
        try:
            doc, image_map, content_length, _, ocr_applied = await _create_uploaded_document(
                db, uid, kb_id, filename, raw, assets=assets, on_duplicate=onDuplicate
            )
        except Exception as e:  # noqa: BLE001 - 多文件允许部分成功
            failed.append({"fileName": filename, "error": str(e)[:300]})
            continue
        background.add_task(document_pipeline.process_document, doc.id)
        documents.append(
            _upload_doc_payload(
                doc,
                kb_id,
                image_count=len(image_map),
                content_length=content_length,
                ocr_applied=ocr_applied,
            )
        )

    if not documents:
        reason = failed[0]["error"] if failed else "没有可上传的文件"
        return error(f"上传失败：{reason}", code=400)
    if len(payloads) == 1 and not failed:
        return success(documents[0], "上传成功，正在后台处理")
    return success(
        {
            "documents": documents,
            "failed": failed,
            "count": len(documents),
            "totalSize": sum(len(raw) for _, raw in payloads),
        },
        f"已上传 {len(documents)} 份" + (f"，{len(failed)} 份失败" if failed else ""),
    )


@router.post("/document/uploadText")
async def import_text(
    data: TextImport,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """纯文本导入：走同一条解析链，代码/公式/表格结构一样落库。"""
    if not (data.content or "").strip():
        return error("内容不能为空", code=400)
    if len(data.content.encode("utf-8")) > MAX_BATCH_UPLOAD_BYTES:
        return error("粘贴内容超过 5MB，请拆分后再导入", code=400)
    from app.services.file_parser import build_marked_document, parse_file
    from app.services.material_organizer import analyze as analyze_material

    txt_name = data.fileName or "未命名文档.txt"
    parsed = await asyncio.to_thread(parse_file, txt_name, data.content.encode("utf-8"))
    body_text, image_urls = build_marked_document(parsed)
    body_text = (body_text or "").strip() or data.content
    image_map = rag_write_service.persist_document_images(image_urls)
    organized = analyze_material(txt_name, body_text, parsed, image_count=len(image_map))
    try:
        doc = await rag_write_service.create_document(
            db,
            _uid(current_user),
            data.kbId,
            file_name=organized["display_name"],
            raw_content=body_text,
            file_type="txt",
            file_size=len(data.content.encode("utf-8")),
            image_map=image_map,
            content_structure=parsed.get("contentStructure") or [],
            original_file_name=organized["original_file_name"],
            subject=organized["subject"],
            material_type=organized["material_type"],
            facets=organized["facets"],
        )
    except Exception as e:
        return _fail(e)

    background.add_task(document_pipeline.process_document, doc.id)
    return success({"docId": doc.id, "fileName": doc.file_name, "status": doc.status}, "导入成功，正在后台处理")


@router.get("/document/list/{kb_id}")
async def list_documents(
    kb_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(await rag_write_service.list_documents(db, _uid(current_user), kb_id))
    except Exception as e:
        return _fail(e)


class DocumentContentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(..., min_length=1)


class DocumentExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = Field(default="markdown", pattern="^(markdown|docx)$")
    content: Optional[str] = None


@router.put("/document/content/{doc_id}")
async def update_document_content(
    doc_id: int,
    data: DocumentContentUpdate,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存二次编辑后的正文，并重新解析/向量化。"""
    try:
        result = await rag_write_service.update_document_content(
            db, _uid(current_user), doc_id, data.content
        )
        background.add_task(document_pipeline.process_document, doc_id)
        return success(result, "正文已保存，正在重新解析")
    except Exception as e:
        return _fail(e)


@router.get("/document/versions/{doc_id}")
async def list_document_versions(
    doc_id: int,
    limit: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """历史版本列表（只读；版本快照复用整理日志表，不新增独立记录入口）。"""
    try:
        return success(
            await rag_write_service.list_document_versions(
                db, _uid(current_user), doc_id, limit
            )
        )
    except Exception as e:
        return _fail(e)


@router.get("/document/versions/{doc_id}/diff")
async def diff_document_versions(
    doc_id: int,
    fromId: int = Query(..., ge=1, description="历史版本 ID"),
    toId: int = Query(0, ge=0, description="对比目标版本；0=当前正文"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """版本对照：左右 diff + 体检分数/问题数变化。

    只展示真实正文和规则体检结果，不生成“AI 评价”。
    """
    try:
        return success(
            await rag_write_service.diff_document_versions(
                db, _uid(current_user), doc_id, fromId, toId
            )
        )
    except Exception as e:
        return _fail(e)


@router.get("/document/versions/{doc_id}/{version_id}")
async def get_document_version(
    doc_id: int,
    version_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(
            await rag_write_service.get_document_version(
                db, _uid(current_user), doc_id, version_id
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/document/versions/{doc_id}/{version_id}/restore")
async def restore_document_version(
    doc_id: int,
    version_id: int,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """恢复历史版本；恢复前会自动保存当前内容，之后仍可再次恢复。"""
    try:
        result = await rag_write_service.restore_document_version(
            db, _uid(current_user), doc_id, version_id
        )
        if result.get("needsReindex"):
            background.add_task(document_pipeline.process_document, doc_id)
        return success(result, "历史版本已恢复，正在重新解析")
    except Exception as e:
        return _fail(e)


@router.get("/document/export/{doc_id}")
async def export_document(
    doc_id: int,
    format: str = Query("markdown", pattern="^(markdown|docx)$"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出当前正文为 Markdown 或 Word。"""
    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        from app.services.document_export_service import content_disposition, export_document

        body, filename, media_type = export_document(
            doc.file_name or "资料",
            doc.raw_content or "",
            doc.image_map or {},
            format,
        )
        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": content_disposition(filename)},
        )
    except Exception as e:
        return _fail(e)


@router.post("/document/export/{doc_id}")
async def export_document_with_content(
    doc_id: int,
    data: DocumentExportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出编辑器里的当前内容（未保存也可以直接导出 Word/Markdown）。"""
    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        from app.services.document_export_service import content_disposition, export_document

        body, filename, media_type = export_document(
            doc.file_name or "资料",
            data.content if data.content is not None else (doc.raw_content or ""),
            doc.image_map or {},
            data.format,
        )
        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": content_disposition(filename)},
        )
    except Exception as e:
        return _fail(e)


@router.get("/document/content/{doc_id}")
async def get_document_content(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取文档全文（给「查看原文」用）。"""
    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        return success(
            {
                "docId": doc.id,
                "fileName": doc.file_name,
                "content": doc.raw_content or "",
                "contentLength": len(doc.raw_content or ""),
                # 软剔除范围：展示时隐藏，不改 raw_content。
                "excludedRanges": doc.excluded_ranges or [],
                # 图片清单：{"0": "/profile/upload/...", ...}，键即正文里 `【图N】` 的 N。
                # 前端据此把正文中的标记渲染成真实图片（否则只会看到「【图0】」文字）。
                "imageMap": workspace_service.visible_image_map(doc),
            }
        )
    except Exception as e:
        return _fail(e)


class StudyPackStreamRequest(BaseModel):
    """资料装配：把选中章节交给 LLM 重组为学习资产。"""

    model_config = ConfigDict(extra="forbid")

    mode: str = Field(default="review", pattern="^(review|lecture|outline)$")
    sectionIndexes: List[int] = Field(default_factory=list)
    instruction: str = Field(default="", max_length=800)


class KnowledgeGraphBuildRequest(BaseModel):
    """知识图谱抽取：对一个资料夹内的文档做实体/关系抽取。"""

    model_config = ConfigDict(extra="forbid")

    kbId: int = Field(..., gt=0)
    docIds: Optional[List[int]] = None
    force: bool = False


class StudyPrescriptionRequest(BaseModel):
    """学习处方：按资料体检和章节生成按天执行的学习计划。"""

    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=7, ge=3, le=30)
    dailyMinutes: int = Field(default=30, ge=10, le=180)
    goal: str = Field(default="exam", pattern="^(foundation|exam|weakness)$")
    sectionIndexes: List[int] = Field(default_factory=list)
    instruction: str = Field(default="", max_length=800)


@router.post("/workspace/documents/{doc_id}/study-pack/stream")
async def stream_workspace_study_pack(
    doc_id: int,
    data: StudyPackStreamRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """资料装配（LLM 流式）：读取选中章节全文后重新组织，不是本地截断拼接。

    返回纯文本分片（与 /ai/assistant/stream 同一事件契约）：
      · 正文增量 → 直接追加
      · 失败 → `Error: <原因>`
      · 结束 → `[DONE]`
    """
    try:
        from app.services.ai import chat_engine, prompts
        from app.services.document_health_service import build_document_health
        from app.services.study_pack_service import build_study_pack_prompt

        uid = _uid(current_user)
        doc = await rag_write_service.get_document(db, uid, doc_id)
        report = await asyncio.to_thread(build_document_health, doc)
        prompt, _selected = build_study_pack_prompt(
            doc_name=str(getattr(doc, "file_name", "") or "未命名资料"),
            raw=str(getattr(doc, "raw_content", "") or ""),
            report=report,
            mode=data.mode,
            section_indexes=data.sectionIndexes,
            instruction=data.instruction,
        )
        turn = chat_engine.ChatTurn(
            scene=prompts.SCENE_STUDY_PACK,
            prompt=prompt,
            user_id=uid,
            temperature=0.35,
            thinking=False,
        )

        async def event_stream():
            async for chunk in chat_engine.stream_turn(db, turn):
                yield chunk

        return StreamingResponse(
            event_stream(),
            media_type="text/plain; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    except Exception as e:
        return _fail(e)


@router.post("/workspace/documents/{doc_id}/prescription/generate")
async def generate_workspace_study_prescription(
    doc_id: int,
    data: StudyPrescriptionRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """学习处方：让 LLM 根据资料体检与章节排一份可执行的按天计划。

    返回结构化 JSON（不是 Markdown 文件），前端按天展示任务、勾选完成和复诊。
    """
    try:
        from app.services.ai import chat_engine, prompts
        from app.services.document_health_service import build_document_health
        from app.services.study_prescription_service import (
            baseline_from_report,
            build_prescription_prompt,
            parse_prescription,
        )

        uid = _uid(current_user)
        doc = await rag_write_service.get_document(db, uid, doc_id)
        report = await asyncio.to_thread(build_document_health, doc)
        prompt, selected = build_prescription_prompt(
            doc_name=str(getattr(doc, "file_name", "") or "未命名资料"),
            report=report,
            days=data.days,
            daily_minutes=data.dailyMinutes,
            goal=data.goal,
            section_indexes=data.sectionIndexes,
            instruction=data.instruction,
        )
        turn = chat_engine.ChatTurn(
            scene=prompts.SCENE_STUDY_PRESCRIPTION,
            prompt=prompt,
            user_id=uid,
            temperature=0.35,
            thinking=False,
        )
        chunks: List[str] = []
        async for chunk in chat_engine.stream_turn(db, turn):
            if chunk == "[DONE]":
                break
            if chunk.startswith("Error: "):
                raise RuntimeError(chunk[7:].strip() or "AI 生成失败")
            chunks.append(chunk)
        plan = parse_prescription(
            "".join(chunks),
            selected_sections=selected,
            days=data.days,
        )
        return success(
            {
                "plan": plan,
                "baseline": baseline_from_report(report),
            }
        )
    except Exception as e:
        return _fail(e)


class StudyPrescriptionExportRequest(BaseModel):
    """学习处方导出：plan 是当前前端正在展示的结构化处方。"""

    model_config = ConfigDict(extra="forbid")

    format: str = Field(..., pattern="^(pdf|word|docx|md|markdown|txt|text)$")
    plan: dict
    meta: dict = Field(default_factory=dict)


@router.get("/chat/suggestions")
async def get_chat_suggestions(
    docId: Optional[int] = Query(None, gt=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新会话首页的提问推测；没有资料时返回起步体验问题。"""
    try:
        from app.services.rag.chat_suggestion_service import get_chat_suggestions as load_suggestions

        return success(await load_suggestions(db, _uid(current_user), doc_id=docId))
    except Exception as e:
        return _fail(e)


@router.get("/knowledge-graph")
async def get_knowledge_graph(
    kbId: Optional[int] = Query(None, gt=0),
    q: str = Query("", max_length=120),
    types: Optional[str] = Query(None, description="逗号分隔的实体类型"),
    minStrength: int = Query(0, ge=0, le=10),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """实体-关系知识图谱。节点和边来自真实抽取，不是页面层级。"""
    try:
        from app.services.rag.knowledge_graph_service import list_graph

        entity_types = [x.strip() for x in (types or "").split(",") if x.strip()]
        return success(
            await list_graph(
                db,
                _uid(current_user),
                kb_id=kbId,
                q=q,
                entity_types=entity_types or None,
                min_strength=minStrength,
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/knowledge-graph/build")
async def build_knowledge_graph(
    data: KnowledgeGraphBuildRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从资料正文抽取实体和关系（同步返回本批统计）。"""
    try:
        from app.services.rag.knowledge_graph_service import build_graph

        return success(
            await build_graph(
                db,
                _uid(current_user),
                data.kbId,
                doc_ids=data.docIds,
                force=data.force,
            ),
            "知识图谱抽取完成",
        )
    except Exception as e:
        return _fail(e)


@router.get("/knowledge-graph/entity/{entity_id}")
async def get_knowledge_graph_entity(
    entity_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from app.services.rag.knowledge_graph_service import get_entity_detail

        return success(await get_entity_detail(db, _uid(current_user), entity_id))
    except Exception as e:
        return _fail(e)


@router.post("/workspace/documents/{doc_id}/prescription/export")
async def export_workspace_study_prescription(
    doc_id: int,
    data: StudyPrescriptionExportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出学习处方：PDF / Word / Markdown / TXT。"""
    try:
        from app.services.study_prescription_export_service import export_prescription

        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        body, filename, media_type = export_prescription(
            doc_name=str(getattr(doc, "file_name", "") or data.meta.get("docName") or "资料"),
            plan=data.plan,
            fmt=data.format,
            meta=data.meta,
        )
        from app.services.document_export_service import content_disposition

        return Response(
            content=body,
            media_type=media_type,
            headers={"Content-Disposition": content_disposition(filename)},
        )
    except Exception as e:
        return _fail(e)


@router.get("/workspace/documents/{doc_id}/health")
async def get_workspace_document_health(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """资料体检：结构 / 图文 / 知识覆盖 / 可学习化四维报告。

    纯规则计算，不调用模型；同一份资料两次体检结果一致。
    前端资料诊疗室的「资料体检」页签和整理手术台都消费这份数据。
    """
    try:
        from app.services.document_health_service import build_document_health

        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        # 体检是同步 CPU 计算（可能几十万字符），放到线程池，避免阻塞事件循环。
        report = await asyncio.to_thread(build_document_health, doc)
        return success(report)
    except Exception as e:
        return _fail(e)


@router.get("/document/outline/{doc_id}")
async def get_document_outline(
    doc_id: int,
    max_nodes: int = Query(120, ge=10, le=400, description="树上最多多少节点"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    资料结构树（2026-10-26 v3 新增）

    ── 为什么需要这个接口 ───────────────────────────────────────
    知识库把文档读进来之后（`raw_content` + 分块 + 向量），
    用户能看到的只有「一串分块」或「AI 零散聊几句」。

    一份 30 页的资料被切成 13 个 chunk 后，
    **它讲了哪几个主题、层级怎么分**这个信息就丢了 ——
    而这恰好是复习时最需要先看到的骨架。

    这个接口把原文标题还原成树，前端用 echarts `tree` 画出来。

    ── 返回 ─────────────────────────────────────────────────────
        {
          "name": "文档名",
          "children": [...],          # 树结构，直接喂 echarts
          "count": 15,                # 上树的节点数
          "totalHeadings": 15,        # 原文里识别到的标题总数
          "truncated": false          # 是否因为 max_nodes 截断
        }

    解析不出章节时返回 `hasOutline=false` + `reason`，
    让前端能如实提示"这份资料没有可提取的章节结构"，
    而不是画一张只有根节点的空图。
    """
    from app.services.outline_tree_service import build_outline_tree

    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
    except Exception as e:
        return _fail(e)

    tree = build_outline_tree(
        doc.raw_content or "",
        root_name=doc.file_name or "资料结构",
        max_nodes=max_nodes,
    )

    if not tree:
        # 题库型文档（纯题目列表）和未排版的纯文本都会走到这里。
        # 这不是错误，是"这份资料本身没有章节结构"。
        return success(
            {
                "docId": doc.id,
                "fileName": doc.file_name,
                "hasOutline": False,
                "reason": (
                    "这份资料里没有可识别的章节标题（Markdown 标题、"
                    "「一、」或「1.」序号），因此画不出结构树。"
                    "题库类文档（纯题目列表）通常就是这种情况。"
                ),
                "chunkCount": getattr(doc, "chunk_count", 0) or 0,
            }
        )

    return success(
        {
            "docId": doc.id,
            "fileName": doc.file_name,
            "hasOutline": True,
            "tree": tree,
            "chunkCount": getattr(doc, "chunk_count", 0) or 0,
        }
    )


@router.get("/document/micro-course/{doc_id}")
async def get_document_micro_course(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """资料变微课（2026-10-31 新增）。

    把文档章节变成一串「站点」：每站有原文导读、要点清单、检查点。
    全部由原文结构生成，不调用大模型，不编造资料里没有的内容。
    """
    from app.services.micro_course_service import build_micro_course

    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        return success(await build_micro_course(db, _uid(current_user), doc))
    except Exception as e:
        return _fail(e)


@router.get("/document/micro-course/{doc_id}/html")
async def get_document_micro_course_html(
    doc_id: int,
    background: BackgroundTasks,
    refresh: bool = Query(False, description="true 表示重新生成一个新版本"),
    prompt: str = Query("", description="用户对本次生成/修改的自然语言要求"),
    recordId: Optional[int] = Query(None, description="基于当前选中的历史版本生成；不传则用最新版本"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取教学 HTML 课件；生成时立即返回初始页，后台继续逐页更新。"""
    from app.services.micro_course_export_service import (
        get_latest_micro_course_record,
        get_micro_course_generation_status,
        get_micro_course_record,
        run_micro_course_generation,
        start_micro_course_generation,
    )

    try:
        user_id = _uid(current_user)
        doc = await rag_write_service.get_document(db, user_id, doc_id)
        latest = await get_latest_micro_course_record(db, user_id, doc_id)
        selected_payload = None
        if recordId:
            selected_payload = await get_micro_course_record(db, user_id, int(recordId))
        if latest and (latest.generation_status or "ready") == "generating" and not refresh and not prompt.strip() and not recordId:
            return success(await get_micro_course_generation_status(db, user_id, doc_id))
        if selected_payload:
            base_deck = selected_payload.get("deck") or {}
            base_html = selected_payload.get("html") or ""
        else:
            base_deck = (latest.deck_json or {}) if latest and (prompt.strip() or recordId) else None
            base_html = (latest.html or "") if latest and (prompt.strip() or recordId) else ""
        payload = await start_micro_course_generation(
            db, user_id, doc, prompt=prompt, refresh=bool(refresh), record_id=recordId
        )
        if payload.get("status") == "generating":
            background.add_task(
                run_micro_course_generation,
                int(payload["recordId"]),
                user_id,
                int(doc.id),
                prompt,
                base_deck,
                base_html,
            )
        return success(payload)
    except Exception as e:
        return _fail(e)


@router.get("/document/micro-course/{doc_id}/status")
async def get_micro_course_status(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.micro_course_export_service import get_micro_course_generation_status

    try:
        user_id = _uid(current_user)
        await rag_write_service.get_document(db, user_id, doc_id)
        data = await get_micro_course_generation_status(db, user_id, doc_id)
        return success(data)
    except Exception as e:
        return _fail(e)


@router.get("/document/micro-course/{doc_id}/history")
async def list_micro_course_history(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出某份资料的历史微课版本（只返回摘要，不返回 HTML）。"""
    from app.services.micro_course_export_service import list_micro_course_history

    try:
        # 先校验文档归属，避免通过 doc_id 探测别人的历史
        await rag_write_service.get_document(db, _uid(current_user), doc_id)
        return success(await list_micro_course_history(db, _uid(current_user), doc_id))
    except Exception as e:
        return _fail(e)


@router.get("/document/micro-course/record/{record_id}")
async def get_micro_course_record(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取某一个历史微课版本的完整 HTML。"""
    from app.services.micro_course_export_service import get_micro_course_record

    try:
        return success(await get_micro_course_record(db, _uid(current_user), record_id))
    except Exception as e:
        return _fail(e)


class MicroCourseSlidePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layout: Optional[str] = None
    eyebrow: Optional[str] = None
    title: Optional[str] = None
    bullets: Optional[List[str]] = None
    note: Optional[str] = None
    image: Optional[dict] = None
    chart: Optional[dict] = None
    table: Optional[dict] = None
    quote: Optional[str] = None


class MicroCourseReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fromIndex: int = Field(..., ge=0)
    toIndex: int = Field(..., ge=0)


class MicroCourseSlideRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field("", max_length=1000)


class MicroCourseSlideInsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(0, ge=0)
    slide: dict


@router.post("/document/micro-course/record/{record_id}/slide/{slide_index}")
async def edit_micro_course_slide(
    record_id: int,
    slide_index: int,
    data: MicroCourseSlidePatch,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.micro_course_export_service import edit_micro_course_slide

    try:
        patch = data.model_dump(exclude_none=True)
        return success(await edit_micro_course_slide(db, _uid(current_user), record_id, slide_index, patch))
    except ValueError as e:
        return error(str(e), code=400)
    except Exception as e:
        return _fail(e)


@router.post("/document/micro-course/record/{record_id}/reorder")
async def reorder_micro_course_slides(
    record_id: int,
    data: MicroCourseReorderRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.micro_course_export_service import reorder_micro_course_slides

    try:
        return success(
            await reorder_micro_course_slides(
                db, _uid(current_user), record_id, data.fromIndex, data.toIndex
            )
        )
    except ValueError as e:
        return error(str(e), code=400)
    except Exception as e:
        return _fail(e)


@router.post("/document/micro-course/record/{record_id}/slides/{slide_index}/regenerate")
async def regenerate_micro_course_slide(
    record_id: int,
    slide_index: int,
    data: MicroCourseSlideRegenerateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.micro_course_export_service import regenerate_micro_course_slide

    try:
        return success(
            await regenerate_micro_course_slide(
                db, _uid(current_user), record_id, slide_index, data.prompt
            )
        )
    except ValueError as e:
        return error(str(e), code=400)
    except Exception as e:
        return _fail(e)


@router.post("/document/micro-course/record/{record_id}/insert")
async def insert_micro_course_slide(
    record_id: int,
    data: MicroCourseSlideInsertRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.micro_course_export_service import insert_micro_course_slide

    try:
        return success(
            await insert_micro_course_slide(
                db, _uid(current_user), record_id, data.index, data.slide
            )
        )
    except ValueError as e:
        return error(str(e), code=400)
    except Exception as e:
        return _fail(e)


class MicroCoursePptxRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: Optional[str] = None
    recordId: Optional[int] = None


class MicroCourseImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str = Field(..., min_length=1, max_length=2_000_000)
    title: Optional[str] = Field(None, max_length=200)


@router.post("/document/micro-course/{doc_id}/import")
async def import_micro_course_html(
    doc_id: int,
    data: MicroCourseImportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入用户自己的 HTML 文件/代码作为微课新版本。"""
    from app.services.micro_course_export_service import import_micro_course_html

    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        return success(
            await import_micro_course_html(
                db, _uid(current_user), doc, data.html, title=data.title or ""
            )
        )
    except ValueError as e:
        return error(str(e), code=400)
    except Exception as e:
        return _fail(e)


@router.post("/document/micro-course/{doc_id}/pptx")
async def download_micro_course_pptx(
    doc_id: int,
    data: MicroCoursePptxRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """把教学 HTML（或服务器生成的结构）转成 .pptx 下载。"""
    from app.services.micro_course_export_service import (
        build_micro_course_export,
        build_pptx_bytes,
        get_latest_micro_course_record,
        get_micro_course_record,
    )

    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        record = None
        record_payload = None
        if data.recordId:
            record_payload = await get_micro_course_record(db, _uid(current_user), data.recordId)
        if not record_payload:
            record = await get_latest_micro_course_record(db, _uid(current_user), doc_id)
        if record_payload:
            deck = record_payload.get("deck") or {}
            html = data.html or record_payload.get("html") or ""
        elif record:
            deck = record.deck_json or {}
            html = data.html or record.html
        else:
            export = await build_micro_course_export(db, _uid(current_user), doc)
            deck = export["deck"]
            html = data.html or export["html"]
        content = build_pptx_bytes(deck, html)
        version = 1
        display_title = doc.file_name or "教学课件"
        if record_payload:
            version = int(record_payload.get("version") or 1)
            display_title = str(record_payload.get("title") or display_title)
        elif record:
            version = int(record.version or 1)
            display_title = str(record.title or display_title)
        stem = re.sub(r"[\\/:*?\"<>|]", "_", display_title or "教学课件")
        stem = re.sub(r"\.[A-Za-z0-9]{1,6}$", "", stem)
        name = f"{stem}_第{version}版.pptx"
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        )
    except Exception as e:
        return _fail(e)


@router.get("/document/chunks/{doc_id}")
async def get_document_chunks(
    doc_id: int,
    limit: int = Query(200, ge=1, le=1000),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(await rag_write_service.list_chunks(db, _uid(current_user), doc_id, limit))
    except Exception as e:
        return _fail(e)


class DocumentStatusBatchRequest(BaseModel):
    docIds: list[int] = Field(default_factory=list, max_length=50)


@router.post("/document/status/batch")
async def get_document_status_batch(
    data: DocumentStatusBatchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量查询文档处理状态：上传后轮询一次请求查完全部文档。

    原来前端对每个文档各发一条 `/document/status/{id}`，一次上传 9 份就是
    9 个请求/轮；统一成一个接口减少请求风暴，也便于页面只刷新一次。
    """
    from app.models.rag import DOC_STATUS_TEXT

    result = []
    for doc_id in list(dict.fromkeys(int(x) for x in data.docIds))[:50]:
        try:
            doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        except Exception:
            continue
        result.append(
            {
                "docId": doc.id,
                "status": doc.status,
                "statusText": DOC_STATUS_TEXT.get(doc.status, "未知"),
                "chunkCount": doc.chunk_count,
                "errorMsg": doc.error_msg,
                "done": doc.status in (4, 5),
                "ok": doc.status == 5,
            }
        )
    return success(result)


@router.get("/document/status/{doc_id}")
async def get_document_status(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """轮询处理进度用。前端上传后按这个查。"""
    from app.models.rag import DOC_STATUS_TEXT

    try:
        doc = await rag_write_service.get_document(db, _uid(current_user), doc_id)
        return success(
            {
                "docId": doc.id,
                "status": doc.status,
                "statusText": DOC_STATUS_TEXT.get(doc.status, "未知"),
                "chunkCount": doc.chunk_count,
                "errorMsg": doc.error_msg,
                "done": doc.status in (4, 5),
                "ok": doc.status == 5,
            }
        )
    except Exception as e:
        return _fail(e)


class DocumentSearchableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


@router.put("/document/{doc_id}/searchable")
async def update_document_searchable(
    doc_id: int,
    data: DocumentSearchableUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单文档检索开关：屏蔽后不参与搜索/问答，但仍保留在资料夹里。"""
    try:
        return success(
            await rag_write_service.set_document_disabled(
                db, _uid(current_user), doc_id, data.disabled
            )
        )
    except Exception as e:
        return _fail(e)


@router.delete("/document/{doc_id}")
async def delete_document(
    doc_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(await rag_write_service.delete_document(db, _uid(current_user), doc_id), "文档已删除")
    except Exception as e:
        return _fail(e)


@router.post("/document/reprocess/{doc_id}")
async def reprocess_document(
    doc_id: int,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重新解析并向量化：立即返回 queued，解析/向量化在后台跑。

    旧实现同步 await 整条 embedding 管线，用户点完按钮要等 30~60 秒，
    没有阶段提示；现在返回 1（待解析），前端按 status 接口轮询。
    """
    try:
        result = await document_pipeline.queue_reprocess_document(
            db, _uid(current_user), doc_id
        )
        background.add_task(document_pipeline.process_document, doc_id)
        return success(result, "已开始重新解析，完成后状态会更新")
    except Exception as e:
        return _fail(e)


@router.post("/document/pending")
async def process_pending(
    kb_id: Optional[int] = Query(None, alias="kbId"),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """补跑「待解析 / 已解析未向量化」的文档。

    用来收拾两类历史遗留：status=1 的，以及 SpringBoot 的 `/parse/pending`
    只做 parse+chunk 就停下、永远停在 status=3 的文档。

    ⚠️ 补跑范围**只限当前用户**（`user_id` 由 JWT 取，不是请求体）——
    省略 kbId 时也只补跑自己的文档，不会替别人烧 embedding 额度、也不会回别人的 docId。
    """
    try:
        uid = _uid(current_user)
        if kb_id:
            await rag_write_service.get_knowledge_base(db, uid, kb_id)
        return success(
            await document_pipeline.process_pending_documents(uid, kb_id, limit), "补跑完成"
        )
    except Exception as e:
        return _fail(e)


# ============================================================ 检索与问答

class SearchRequest(BaseModel):
    query: str
    kbIds: Optional[List[int]] = None
    topK: int = Field(5, ge=1, le=20)


class AskRequest(BaseModel):
    query: str
    kbIds: Optional[List[int]] = None
    topK: int = Field(5, ge=1, le=20)
    sessionId: Optional[str] = None


@router.post("/search")
async def search(
    data: SearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只检索、不调模型。给前端预览「命中了哪些片段」。"""
    try:
        return success(
            await rag_query_service.search(
                db, _uid(current_user), data.query, data.kbIds, data.topK
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/ask")
async def ask(
    data: AskRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RAG 问答。返回答案 + 出处（citations）。

    非流式：先保证「检索 → 出处 → 权限」这条链路是对的，流式后面再接。
    """
    try:
        return success(
            await rag_query_service.answer(
                db,
                _uid(current_user),
                data.query,
                data.kbIds,
                data.topK,
                session_id=data.sessionId,
            )
        )
    except Exception as e:
        return _fail(e)


# ============================================================ 向量化后端配置
#
# 后台「AI 配置 → 知识库向量化」页用。
# 为什么单独一组接口：`.env` 只能重启生效，而用户切换本地/云端是**产品行为**，
# 必须能即时生效并看到检测结果。

class RagConfigUpdate(BaseModel):
    """可更新项全部可选 —— 前端只传改过的字段。"""

    backend: Optional[str] = Field(None, description="local | siliconflow | auto")
    model: Optional[str] = None
    chunkSize: Optional[int] = Field(None, ge=100, le=4000)
    chunkOverlap: Optional[int] = Field(None, ge=0, le=1000)
    topK: Optional[int] = Field(None, ge=1, le=50)
    rrfK: Optional[int] = Field(None, ge=1, le=200)
    cloudModel: Optional[str] = None
    autoFallback: Optional[bool] = None
    #: 硅基流动 API Key。传空串或不传 = 不改；传 "__CLEAR__" = 清空
    cloudApiKey: Optional[str] = None


@router.get("/config")
async def get_rag_config(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """读当前配置 + 本地/云端两条链路的可用性检测。

    前端进页面就调它，据此渲染：
      · 三个后端选项哪个可选、哪个禁用；
      · 本地不可用时提示「没装模型」，并引导去用云端；
      · 云端不可用时提示「没配 Key」。
    """
    try:
        return success(await rag_config_service.get_status(db))
    except Exception as e:
        return _fail(e)


@router.put("/config")
async def update_rag_config(
    data: RagConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """更新向量化配置（即时生效，无需重启）。

    注意：切换后端**不会**自动重算已有向量。历史文档的向量是旧模型算的，
    换模型后新旧向量不在同一空间，检索会失真。所以响应里会带一个
    `needReindex` 标志，由前端提示用户「要不要重建索引」。
    """
    try:
        if data.backend and data.backend not in rag_config_service.BACKENDS:
            return error(f"不支持的后端：{data.backend}，可选 {rag_config_service.BACKENDS}", code=400)

        old = await rag_config_service.get_config_map(db)
        payload = {
            rag_config_service.KEY_BACKEND: data.backend,
            rag_config_service.KEY_MODEL: data.model,
            rag_config_service.KEY_CHUNK_SIZE: data.chunkSize,
            rag_config_service.KEY_CHUNK_OVERLAP: data.chunkOverlap,
            rag_config_service.KEY_TOP_K: data.topK,
            rag_config_service.KEY_RRF_K: data.rrfK,
            rag_config_service.KEY_CLOUD_MODEL: data.cloudModel,
            rag_config_service.KEY_AUTO_FALLBACK: data.autoFallback,
        }

        # ── 云端 API Key（2026-10-22 新增）───────────────────────────
        # 语义：不传 / 传空串 = 保持原值；传 "__CLEAR__" = 清空。
        # 为什么不接受「空串即清空」：前端回填的是掩码，用户没动就原样提交，
        # 若把空串当清空，用户只是改个分块大小就会把 Key 清掉。
        if data.cloudApiKey is not None:
            v = data.cloudApiKey.strip()
            if v == "__CLEAR__":
                payload[rag_config_service.KEY_CLOUD_API_KEY] = ""
            elif v and "••••" not in v:
                # 前端把掩码回传时（含 ••••）视为未修改
                payload[rag_config_service.KEY_CLOUD_API_KEY] = v

        await rag_config_service.set_configs(db, payload)
        await db.commit()

        new = await rag_config_service.get_config_map(db)

        # 让本进程立刻用新配置（否则要重启才生效）
        from app.services.rag import embedding as embedding_service

        embedding_service.refresh_runtime_config(
            backend=new.get(rag_config_service.KEY_BACKEND),
            model=new.get(rag_config_service.KEY_MODEL),
        )

        # 把最新 Key 刷进进程内缓存（siliconflow_client 会读它）。
        # siliconflow_client 本身不再缓存旧的 api_key（改成每次动态读），
        # 所以这里不需要重建客户端实例。
        rag_config_service.refresh_runtime_cloud_api_key(
            new.get(rag_config_service.KEY_CLOUD_API_KEY) or ""
        )

        need_reindex = (
            old.get(rag_config_service.KEY_MODEL) != new.get(rag_config_service.KEY_MODEL)
            or old.get(rag_config_service.KEY_CLOUD_MODEL) != new.get(rag_config_service.KEY_CLOUD_MODEL)
        )

        status = await rag_config_service.get_status(db)
        status["needReindex"] = need_reindex
        status["reindexHint"] = (
            "向量化模型已变更。已有文档的向量是用旧模型算的，与新向量不在同一空间，"
            "检索结果会不准。请到「我的资料」页面点「重建索引」，或重新上传文档。"
            if need_reindex
            else ""
        )
        return success(status)
    except Exception as e:
        return _fail(e)


# ============================================================ 工作空间
#
# 产品定位：用户的「资料抽屉」。
# 在对话里说「用我空间里那份概率论的资料出题」，AI 自己去空间里找 —— 不需要用户选文件。
#
# 实现：复用 `rag_knowledge_base`（`is_workspace=1`），文件仍是普通 `rag_document`，
# 分块/向量化/检索全部走既有链路。详见 `services/rag/workspace_service.py` 顶部说明。

@router.get("/workspace")
async def get_workspace(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """默认知识库概况 + 文件列表（旧版页面/工具仍在用，保留兼容）"""
    try:
        uid = _uid(current_user)
        stats = await workspace_service.space_stats(db, uid)
        files = await workspace_service.list_space_files(db, uid)
        return success({"stats": stats, "files": files})
    except Exception as e:
        return _fail(e)


@router.get("/workspace/overview")
async def get_workspace_overview(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """**知识库总览** —— 全部知识库 + 每个库的文档，一次返回。

    新版「知识库」整页（侧栏入口 `/front/workspace`）用它渲染：
    左侧是库列表，右侧是当前库的文档，头部是全站统计。

    ⚠️ 与上面的 `/workspace` 的区别：那个只返回**默认库**的文件（给旧页面和
       `workspace_search` 工具用），这个返回**所有库**。不要互相替代。
    """
    try:
        return success(await workspace_service.overview(db, _uid(current_user)))
    except Exception as e:
        return _fail(e)


@router.post("/workspace/upload")
async def upload_to_workspace(
    background: BackgroundTasks,
    file: List[UploadFile] = File(...),
    note: Optional[str] = Query(None, description="用户给这份资料写的一句话说明"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上传一个或多个文件到工作空间。

    与 `/rag/document/upload` 的差别只有两处：
      · 目标库自动取「该用户的工作空间」（没有就建），不需要传 kbId；
      · 可以顺手写一句 `note`（如「高二期末卷」），帮 AI 以后认出这份资料。
    多文件一次请求合计不超过 5MB；每个文档独立进入同一条解析/向量化流水线。
    """
    uid = _uid(current_user)
    try:
        kb = await workspace_service.get_or_create_workspace(db, uid)
    except Exception as e:
        return _fail(e)

    payloads, size_error = await _read_upload_files(file)
    if size_error:
        return error(size_error, code=400)

    assets = _batch_image_assets(payloads)
    referenced_images = _referenced_markdown_image_names(payloads)
    documents: list[dict] = []
    failed: list[dict] = []
    for filename, raw in payloads:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _IMAGE_FILE_EXTS and Path(filename).name in referenced_images:
            continue
        try:
            doc, image_map, content_length, note_text, ocr_applied = await _create_uploaded_document(
                db, uid, kb.id, filename, raw, note or "", assets=assets
            )
        except Exception as e:  # noqa: BLE001 - 多文件允许部分成功
            failed.append({"fileName": filename, "error": str(e)[:300]})
            continue
        background.add_task(document_pipeline.process_document, doc.id)
        documents.append(
            _upload_doc_payload(
                doc,
                kb.id,
                image_count=len(image_map),
                content_length=content_length,
                note=note_text,
                ocr_applied=ocr_applied,
            )
        )

    if not documents:
        reason = failed[0]["error"] if failed else "没有可上传的文件"
        return error(f"上传失败：{reason}", code=400)
    if len(payloads) == 1 and not failed:
        return success(documents[0], "已放进工作空间，正在后台解析")
    return success(
        {
            "documents": documents,
            "failed": failed,
            "count": len(documents),
            "totalSize": sum(len(raw) for _, raw in payloads),
        },
        f"已上传 {len(documents)} 份" + (f"，{len(failed)} 份失败" if failed else ""),
    )


@router.get("/workspace/standalone-images")
async def list_workspace_standalone_images(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """聊天里直接粘贴/上传的独立图片（fileId=0）。

    这些图片已经在 `chat_upload_image` 落盘，不需要再复制一份；
    「我的资料」的图片墙把它们作为“聊天图片”展示。
    """
    try:
        from app.services import chat_upload_service

        rows = await chat_upload_service.list_images(
            db,
            user_id=_uid(current_user),
            limit=max(1, min(limit, 200)),
        )
        return success([r for r in rows if int(r.get("fileId") or 0) == 0])
    except Exception as e:
        return _fail(e)


class AssetUsageRequest(BaseModel):
    """记录一张图片资产被哪个题目/笔记使用。"""

    model_config = ConfigDict(extra="forbid")

    assetKey: str = Field(..., min_length=1, max_length=120)
    assetUrl: Optional[str] = Field(None, max_length=500)
    targetType: str = Field(..., pattern="^(question|note|document)$")
    targetId: int


class GalleryDescribeRequest(BaseModel):
    """批量补图片描述：传 docId 或 assetKeys，二选一。

    不提供“全库自动跑”的隐藏行为——用户点哪次就描述哪批，成本可控。
    """

    model_config = ConfigDict(extra="forbid")

    docId: Optional[int] = Field(None, gt=0)
    assetKeys: Optional[List[str]] = None
    limit: int = Field(20, ge=1, le=40)


class ContentReferenceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sourceType: str = Field(..., pattern="^(document|document_image|chat_image|note|question)$")
    sourceId: int = Field(..., gt=0)
    sourceSubId: Optional[str] = Field(None, max_length=64)
    targetType: str = Field(..., pattern="^(document|note|question|image)$")
    targetId: int = Field(..., gt=0)
    quote: str = Field("", max_length=4000)
    startOffset: Optional[int] = None
    endOffset: Optional[int] = None


class OrganizeRequest(BaseModel):
    """智能整理：传 docIds（单个/多个）或 kbId（整资料夹）。"""

    model_config = ConfigDict(extra="forbid")

    docIds: Optional[List[int]] = None
    kbId: Optional[int] = None


class OrganizePreviewRequest(BaseModel):
    """单文档智能整理预览（仅深度/智能整理）。"""

    model_config = ConfigDict(extra="forbid")

    docId: int = Field(..., gt=0)
    mode: str = Field(default="deep", pattern="^deep$")
    options: dict = Field(default_factory=dict)


class OrganizeApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planId: int = Field(..., gt=0)
    changeIds: Optional[List[str]] = None
    exclusionIds: Optional[List[str]] = None


class OrganizeRollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batchId: str = Field(..., min_length=1, max_length=64)


@router.post("/workspace/organize/preview")
async def preview_workspace_organize(
    data: OrganizePreviewRequest,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单文档智能整理预览：后台执行并实时上报阶段。"""
    try:
        uid = _uid(current_user)
        result = await workspace_service.create_deep_plan(
            db, uid, data.docId, data.options or {}
        )
        background.add_task(workspace_service.process_deep_plan, result["planId"])
        return success(result, "智能整理已开始")
    except Exception as e:
        return _fail(e)


@router.get("/workspace/organize/plans")
async def list_workspace_organize_plans(
    limit: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(await workspace_service.list_plans(db, _uid(current_user), limit))
    except Exception as e:
        return _fail(e)


@router.get("/workspace/organize/plans/{plan_id}")
async def get_workspace_organize_plan(
    plan_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await workspace_service.get_plan(db, _uid(current_user), plan_id)
        return success(workspace_service._plan_payload(plan))
    except Exception as e:
        return _fail(e)


@router.get("/workspace/organize/plans/{plan_id}/events")
async def stream_workspace_organize_plan(
    plan_id: int,
    current_user: dict = Depends(get_current_user),
):
    """SSE 实时整理事件：阶段变化和逐步出现的 diff。"""
    uid = _uid(current_user)

    async def event_stream():
        last_stage = None
        last_change_count = 0
        while True:
            async with async_session_factory() as session:
                plan = await workspace_service.get_plan(session, uid, plan_id)
                payload = workspace_service._plan_payload(plan)
            stage_key = f"{payload['status']}:{payload['stage']}"
            if stage_key != last_stage:
                last_stage = stage_key
                yield "event: stage\n"
                yield "data: " + json.dumps(
                    {
                        "status": payload["status"],
                        "stage": payload["stage"],
                        "progress": payload["progress"],
                        "summary": payload["summary"],
                    },
                    ensure_ascii=False,
                ) + "\n\n"
            changes = payload.get("changes") or []
            if len(changes) > last_change_count:
                for change in changes[last_change_count:]:
                    yield "event: change\n"
                    yield "data: " + json.dumps(change, ensure_ascii=False) + "\n\n"
                last_change_count = len(changes)
            if payload["status"] in {"ready", "applied", "rejected", "failed", "rolled_back"}:
                yield "event: done\n"
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                return
            await asyncio.sleep(0.35)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/workspace/organize/apply")
async def apply_workspace_organize(
    data: OrganizeApplyRequest,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await workspace_service.apply_plan(
            db,
            _uid(current_user),
            data.planId,
            data.changeIds,
            data.exclusionIds,
        )
        if result.get("needsReindex"):
            background.add_task(document_pipeline.process_document, result.get("docId") or 0)
        return success(result, "整理已应用")
    except Exception as e:
        return _fail(e)


@router.get("/workspace/organize/records/{record_id}")
async def get_workspace_organize_record(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取一条整理记录；负数表示旧版日志。"""
    try:
        if record_id < 0:
            return success(await workspace_service.get_legacy_record(db, _uid(current_user), record_id))
        plan = await workspace_service.get_plan(db, _uid(current_user), record_id)
        return success(workspace_service._plan_payload(plan))
    except Exception as e:
        return _fail(e)


@router.delete("/workspace/organize/records/{record_id}")
async def delete_workspace_organize_record(
    record_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除一条整理记录；只删记录，不回退已应用的文档变更。"""
    try:
        result = await workspace_service.delete_plan_record(db, _uid(current_user), record_id)
        return success(result, "整理记录已删除")
    except Exception as e:
        return _fail(e)


@router.post("/workspace/organize/plans/{plan_id}/rollback")
async def rollback_workspace_plan(
    plan_id: int,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await workspace_service.rollback_plan(db, _uid(current_user), plan_id)
        if result.get("needsReindex"):
            background.add_task(document_pipeline.process_document, result.get("docId") or 0)
        return success(result, "已回退整理")
    except Exception as e:
        return _fail(e)


@router.post("/workspace/organize")
async def organize_workspace(
    data: OrganizeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """兼容旧调用：只允许单文档；新前端使用 /organize/preview。"""
    if data.kbId is not None or not data.docIds or len(data.docIds) != 1:
        return error("智能整理只支持单个文档，资料夹整理入口已移除", code=400)
    try:
        result = await workspace_service.organize_documents(
            db,
            _uid(current_user),
            doc_ids=data.docIds,
            kb_id=None,
        )
        return success(result)
    except Exception as e:
        return _fail(e)


@router.post("/workspace/organize/rollback")
async def rollback_workspace_organize(
    data: OrganizeRollbackRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按 batchId 整批回退智能整理。"""
    try:
        result = await workspace_service.rollback_organize(
            db, _uid(current_user), data.batchId
        )
        return success(result)
    except Exception as e:
        return _fail(e)


@router.post("/assets/usage")
async def record_asset_usage(
    data: AssetUsageRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入资料资产用途账本（幂等）。

    用户把图片插入题目/笔记时调用；同一 asset + target 只记一次，
    重复插入只恢复 `deleted=0`，不制造重复计数。
    """
    from sqlalchemy import select

    from app.models.rag import MaterialAssetUsage

    uid = _uid(current_user)
    try:
        row = (
            await db.execute(
                select(MaterialAssetUsage).where(
                    MaterialAssetUsage.user_id == uid,
                    MaterialAssetUsage.asset_key == data.assetKey,
                    MaterialAssetUsage.target_type == data.targetType,
                    MaterialAssetUsage.target_id == data.targetId,
                )
            )
        ).scalars().first()
        if row:
            row.deleted = 0
            if data.assetUrl:
                row.asset_url = data.assetUrl
        else:
            db.add(
                MaterialAssetUsage(
                    user_id=uid,
                    asset_key=data.assetKey,
                    asset_url=data.assetUrl,
                    target_type=data.targetType,
                    target_id=data.targetId,
                )
            )
        await db.commit()
        return success({"assetKey": data.assetKey, "targetType": data.targetType, "targetId": data.targetId})
    except Exception as e:
        return _fail(e)


@router.get("/assets/usage-summary")
async def asset_usage_summary(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前用户所有图片资产的用途计数：`{assetKey: count}`。"""
    from sqlalchemy import func, select

    from app.models.rag import MaterialAssetUsage

    try:
        rows = (
            await db.execute(
                select(
                    MaterialAssetUsage.asset_key,
                    func.count(MaterialAssetUsage.id).label("cnt"),
                )
                .where(
                    MaterialAssetUsage.user_id == _uid(current_user),
                    MaterialAssetUsage.deleted == 0,
                )
                .group_by(MaterialAssetUsage.asset_key)
            )
        ).all()
        return success({str(r[0]): int(r[1]) for r in rows})
    except Exception as e:
        return _fail(e)


@router.get("/gallery")
async def list_gallery_assets(
    scope: str = Query("all", pattern="^(all|current)$"),
    kbId: Optional[int] = Query(None, gt=0),
    source: str = Query("all", pattern="^(all|document|chat)$"),
    status: str = Query("all", pattern="^(all|pending|processing|done|failed)$"),
    q: str = Query("", max_length=120),
    limit: int = Query(200, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """画廊：当前用户全部/指定资料夹的图片资产。

    每次读取前会幂等同步 `rag_document.image_map` 与 `chat_upload_image`，
    不依赖上传时是否跑过描述任务。
    """
    try:
        return success(
            await gallery_service.list_gallery(
                db,
                _uid(current_user),
                scope=scope,
                kb_id=kbId,
                source=source,
                status=status,
                q=q,
                limit=limit,
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/gallery/describe")
async def describe_gallery_assets(
    data: GalleryDescribeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为一批未描述图片生成描述/OCR。

    同步返回完成数量，前端用 loading 进度展示；不阻塞上传链路。
    """
    try:
        result = await gallery_service.describe_assets(
            db,
            _uid(current_user),
            asset_keys=data.assetKeys,
            doc_id=data.docId,
            limit=data.limit,
        )
        msg = f"已处理 {result['done']} 张" + (f"，{result['failed']} 张失败" if result["failed"] else "")
        return success(result, msg)
    except Exception as e:
        return _fail(e)


@router.get("/gallery/{asset_key}")
async def gallery_asset_detail(
    asset_key: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单张图片资产详情：描述、OCR、来源章节、用途与引用。"""
    try:
        return success(await gallery_service.get_asset_detail(db, _uid(current_user), asset_key))
    except Exception as e:
        return _fail(e)


@router.get("/knowledge-map")
async def get_knowledge_map(
    kbId: Optional[int] = Query(None, gt=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """资料知识地图：真实文档/章节/笔记/题组/图组节点与可解释边。"""
    try:
        return success(await knowledge_map_service.build_knowledge_map(db, _uid(current_user), kb_id=kbId))
    except Exception as e:
        return _fail(e)


@router.get("/references")
async def list_content_references(
    targetType: Optional[str] = Query(None, pattern="^(document|note|question|image)$"),
    targetId: Optional[int] = Query(None, gt=0),
    sourceType: Optional[str] = Query(None, pattern="^(document|document_image|chat_image|note|question)$"),
    sourceId: Optional[int] = Query(None, gt=0),
    limit: int = Query(100, ge=1, le=300),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(
            await reference_service.list_references(
                db,
                _uid(current_user),
                target_type=targetType,
                target_id=targetId,
                source_type=sourceType,
                source_id=sourceId,
                limit=limit,
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/references")
async def create_content_reference(
    data: ContentReferenceCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """建立统一引用；同一来源→同一目标幂等更新。"""
    try:
        return success(
            await reference_service.create_reference(
                db,
                _uid(current_user),
                source_type=data.sourceType,
                source_id=data.sourceId,
                source_sub_id=data.sourceSubId,
                target_type=data.targetType,
                target_id=data.targetId,
                quote=data.quote,
                start_offset=data.startOffset,
                end_offset=data.endOffset,
            )
        )
    except Exception as e:
        return _fail(e)


@router.delete("/references/{reference_id}")
async def delete_content_reference(
    reference_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return success(await reference_service.delete_reference(db, _uid(current_user), reference_id))
    except Exception as e:
        return _fail(e)


@router.delete("/workspace/file/{doc_id}")
async def delete_workspace_file(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """从工作空间移除文件（软删除 + 删分块）"""
    try:
        return success(await rag_write_service.delete_document(db, _uid(current_user), doc_id))
    except Exception as e:
        return _fail(e)


@router.get("/workspace/cascade-search")
async def cascade_search_workspace(
    q: str = Query("", max_length=120),
    folderLimit: int = Query(50, ge=1, le=100),
    documentLimit: int = Query(20, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跨资料夹级联搜索：资料夹名命中 / 内部文档名、备注、正文命中同时返回。"""
    try:
        return success(
            await workspace_service.cascade_search(
                db,
                _uid(current_user),
                q,
                max_folders=folderLimit,
                max_documents_per_folder=documentLimit,
            )
        )
    except Exception as e:
        return _fail(e)


@router.post("/workspace/search")
async def search_workspace(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按自然语言找文件（页面「试试 AI 会怎么找」）。

    ⚠️ 2026-10-22 重写：原来这里调 `workspace_service.search_files()` ——
    那是一个**纯字符串匹配**（`if token in content`），而且写死只搜**默认知识库**。
    结果：
      · 在「数据结构」库里搜「随机事件」，实际查的是默认库 → 一条都搜不到；
      · `score=1` 的分全是假阳性（单个二元组在正文里撞上一个字就算命中）。

    现在改走**真正的 RAG 链路**（`rag_query_service.search`：bge-m3 向量 +
    jieba 全文 + RRF 融合），并且支持传 `kbIds` 收窄到指定库；
    不传就是该用户的全部知识库。返回结构同时保留 `files`（按文件去重，
    给页面列表用）和 `hits`（原始分块命中，给"看详情/看分块"用）。
    """
    try:
        body = data or {}
        q = str(body.get("query") or "").strip()
        limit = int(body.get("limit") or 5)
        # 不传 kbIds = 搜全部知识库；传了就只搜这些（下面的 resolve 会校验归属）
        raw_ids = body.get("kbIds")
        kb_ids = [int(x) for x in raw_ids] if isinstance(raw_ids, list) and raw_ids else None

        result = await rag_query_service.search(
            db, _uid(current_user), q, kb_ids, top_k=max(limit, 1)
        )
        hits = result.get("hits") or []
        # `ChunkHit.to_dict()` 只有 kbId，没有库名；从本次检索范围里补一张 id→name 表
        kb_names = {
            int(k.get("kbId")): str(k.get("name") or "")
            for k in (result.get("knowledgeBases") or [])
            if k.get("kbId") is not None
        }
        for h in hits:
            try:
                h["kbName"] = kb_names.get(int(h.get("kbId")), "")
            except (TypeError, ValueError):
                h["kbName"] = ""

        return success(
            {
                "query": q,
                "hits": hits,
                "knowledgeBases": result.get("knowledgeBases") or [],
                "files": _group_hits_by_file(hits, limit),
                "reason": result.get("reason") or "",
                # 两路都没关键词命中 = 结果可能不相关（见 rag_query_service.search 的说明）
                "lowConfidence": bool(result.get("lowConfidence")),
            }
        )
    except Exception as e:
        return _fail(e)


def _group_hits_by_file(hits: list, limit: int) -> list:
    """把分块命中按**文件**聚合，供页面列表展示。

    为什么不直接返回分块：用户问「找下概率论那份资料」时想看的是**哪份文件**，
    而不是十几条零散片段。文件级列表 + 命中段数，才是这个页面该给的东西。
    组内保留第一段正文摘要，方便用户确认「就是这份」。
    """
    groups: dict[int, dict] = {}
    order: list[int] = []

    for h in hits:
        doc_id = h.get("docId")
        if doc_id is None:
            continue
        if doc_id not in groups:
            content = str(h.get("content") or "")
            groups[doc_id] = {
                "docId": doc_id,
                "kbId": h.get("kbId"),
                "kbName": h.get("kbName") or "",
                "fileName": h.get("docName") or h.get("fileName") or "未命名文档",
                "score": float(h.get("score") or 0),
                "hitCount": 0,
                "snippet": content[:120] + ("…" if len(content) > 120 else ""),
                "images": list(h.get("images") or [])[:3],
            }
            order.append(doc_id)
        groups[doc_id]["hitCount"] += 1

    return [groups[d] for d in order][:limit]
