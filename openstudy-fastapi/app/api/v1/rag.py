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
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services.rag import document_pipeline, rag_query_service, rag_write_service
from app.services.rag.rag_write_service import RagConflict, RagNotFound

router = APIRouter(prefix="/rag")

#: 单个上传文件上限（沿用全局配置）
MAX_UPLOAD_BYTES = settings.MAX_FILE_SIZE


def _uid(current_user: dict) -> int:
    """当前登录用户 id。**唯一可信来源**。"""
    return int((current_user or {}).get("user_id") or 0)


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
            "知识库创建成功",
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
        return success(info, "知识库已删除")
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
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传文档：同步解析（拿到全文落库）+ 异步向量化。

    解析放线程池 —— 它是同步的，老版 `.doc` 还会借 Word COM 转换，别冻住事件循环。
    """
    from app.services.file_parser import parse_file

    try:
        # 先确认知识库归属，避免替别人的库上传
        await rag_write_service.get_knowledge_base(db, _uid(current_user), kb_id)
    except Exception as e:
        return _fail(e)

    raw = await file.read()
    if not raw:
        return error("文件为空", code=400)
    if len(raw) > MAX_UPLOAD_BYTES:
        return error(
            f"文件过大（{len(raw) // 1024 // 1024}MB），上限 {MAX_UPLOAD_BYTES // 1024 // 1024}MB",
            code=400,
        )

    filename = file.filename or "未命名文档"
    try:
        parsed = await asyncio.to_thread(parse_file, filename, raw)
    except Exception as e:
        return error(f"文档解析失败：{e}", code=400)

    text = (parsed.get("textContent") or "").strip()
    if not text:
        # 用户给的文件本身没法提取文本 → 属于输入问题，用 400 而不是 500
        return error(
            f"没能从「{filename}」中提取出文本：{parsed.get('error') or '内容为空'}", code=400
        )

    try:
        doc = await rag_write_service.create_document(
            db,
            _uid(current_user),
            kb_id,
            file_name=filename,
            raw_content=text,
            file_type=(filename.rsplit(".", 1)[-1].lower() if "." in filename else None),
            file_size=len(raw),
        )
    except Exception as e:
        return _fail(e)

    background.add_task(document_pipeline.process_document, doc.id)
    return success(
        {
            "docId": doc.id,
            "fileName": doc.file_name,
            "contentLength": len(text),
            "status": doc.status,
            "statusText": "待解析",
        },
        "上传成功，正在后台处理",
    )


@router.post("/document/uploadText")
async def import_text(
    data: TextImport,
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """纯文本导入（不经过文件解析）。"""
    if not (data.content or "").strip():
        return error("内容不能为空", code=400)
    try:
        doc = await rag_write_service.create_document(
            db,
            _uid(current_user),
            data.kbId,
            file_name=data.fileName or "未命名文档.txt",
            raw_content=data.content,
            file_type="txt",
            file_size=len(data.content.encode("utf-8")),
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
            }
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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重跑单篇（失败重试）。legacy 没有这个能力，失败文档只能干等。"""
    try:
        result = await document_pipeline.reprocess_document(
            db, _uid(current_user), doc_id
        )
        return success(result, "已重新处理")
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
