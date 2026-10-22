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
from app.services.rag import (
    document_pipeline,
    rag_config_service,
    rag_query_service,
    rag_write_service,
    workspace_service,
)
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

    # 图片：解析器已抽出（`blocks` 里带 data URL），此前**被整条链路丢弃**。
    # 现在落盘成 `/profile/upload/...` 建 `image_map`，并让正文带上 `【图N】` 位置标记 ——
    # 这样分块时能把图归属到具体 chunk，检索命中时把图一起回给模型/前端。
    # ⚠️ 无图文档：`build_marked_document` 返回的正文与 `textContent` 等价，行为不变。
    from app.services.file_parser import build_marked_document

    marked_text, image_data_urls = build_marked_document(parsed)
    # 解析器给不出图文块（老数据/降级）时退回纯 textContent，避免正文变短
    body_text = (marked_text or "").strip() or text
    image_map = rag_write_service.persist_document_images(image_data_urls)

    try:
        doc = await rag_write_service.create_document(
            db,
            _uid(current_user),
            kb_id,
            file_name=filename,
            raw_content=body_text,
            file_type=(filename.rsplit(".", 1)[-1].lower() if "." in filename else None),
            file_size=len(raw),
            image_map=image_map,
        )
    except Exception as e:
        return _fail(e)

    background.add_task(document_pipeline.process_document, doc.id)
    return success(
        {
            "docId": doc.id,
            "fileName": doc.file_name,
            "contentLength": len(body_text),
            "imageCount": len(image_map),
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
                # 图片清单：{"0": "/profile/upload/...", ...}，键即正文里 `【图N】` 的 N。
                # 前端据此把正文中的标记渲染成真实图片（否则只会看到「【图0】」文字）。
                "imageMap": doc.image_map or {},
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
    current_user: dict = Depends(get_current_user),
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
    current_user: dict = Depends(get_current_user),
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
            "检索结果会不准。请到知识库页面点「重建索引」，或重新上传文档。"
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
    file: UploadFile = File(...),
    note: Optional[str] = Query(None, description="用户给这份资料写的一句话说明"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上传文件到工作空间。

    与 `/rag/document/upload` 的差别只有两处：
      · 目标库自动取「该用户的工作空间」（没有就建），不需要传 kbId；
      · 可以顺手写一句 `note`（如「高二期末卷」），帮 AI 以后认出这份资料。
    解析/落图/分块/向量化全部复用同一条流水线。
    """
    from app.services.file_parser import build_marked_document, parse_file

    uid = _uid(current_user)
    try:
        kb = await workspace_service.get_or_create_workspace(db, uid)
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
        return error(
            f"没能从「{filename}」中提取出文本：{parsed.get('error') or '内容为空'}", code=400
        )

    marked_text, image_data_urls = build_marked_document(parsed)
    body_text = (marked_text or "").strip() or text
    image_map = rag_write_service.persist_document_images(image_data_urls)

    try:
        doc = await rag_write_service.create_document(
            db,
            uid,
            kb.id,
            file_name=filename,
            raw_content=body_text,
            file_type=(filename.rsplit(".", 1)[-1].lower() if "." in filename else None),
            file_size=len(raw),
            image_map=image_map,
        )
        # 用户备注（可选）
        if note and note.strip():
            doc.user_note = note.strip()[:200]
            await db.flush()
    except Exception as e:
        return _fail(e)

    background.add_task(document_pipeline.process_document, doc.id)
    return success(
        {
            "docId": doc.id,
            "kbId": kb.id,
            "fileName": doc.file_name,
            "note": doc.user_note or "",
            "contentLength": len(body_text),
            "imageCount": len(image_map),
            "status": doc.status,
            "statusText": "待解析",
        },
        "已放进工作空间，正在后台解析",
    )


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
