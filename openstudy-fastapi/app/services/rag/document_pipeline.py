"""
文档处理流水线：解析 → 分块 → 分词 → 向量化 → 落库

状态机（与 SpringBoot 版一致，便于对照）：
    1 待解析 → 2 解析中 → 3 已解析 → 5 已向量化
                        ↘ 4 处理失败（带 error_msg）
⚠️ legacy **没有重试**：`status=4` 的文档只能人工再调一次接口。
   这里保留了显式的重跑入口（`reprocess_document` / `process_pending_documents`）。

异步方式：FastAPI `BackgroundTasks`（在事件循环里跑，不额外起进程）。
⚠️ 因此任务里**必须自己开会话** —— 请求的会话在响应返回后就关了。

文档解析复用 `app/services/file_parser.py`，不另写一套。
"""

from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.rag import (
    DOC_FAILED,
    DOC_PARSED,
    DOC_PARSING,
    DOC_PENDING,
    RagDocument,
)
from app.services.rag.chunker import chunk_text
from app.services.rag.embedding import embed_texts
from app.services.rag.rag_write_service import (
    get_document,
    mark_document_failed,
    replace_chunks,
)


async def process_document(doc_id: int) -> dict:
    """完整处理一篇文档（基于已落库的 `raw_content`）。

    自身开会话：调用方通常只把它丢进 BackgroundTasks，那时请求会话已经关了。
    """
    async with async_session_factory() as db:
        doc = (
            await db.execute(select(RagDocument).where(RagDocument.id == doc_id))
        ).scalar_one_or_none()
        if doc is None:
            logger.warning(f"[rag.pipeline] 文档不存在，跳过: id={doc_id}")
            return {"docId": doc_id, "ok": False, "error": "文档不存在"}

        try:
            return await _run(db, doc)
        except Exception as e:
            logger.exception(f"[rag.pipeline] 文档处理失败 id={doc_id}")
            await db.rollback()
            # 失败必须落 status=4 并记原因，否则前端只会看到文档「卡住」没有任何线索
            await mark_document_failed(db, doc, f"{type(e).__name__}: {e}")
            return {"docId": doc_id, "ok": False, "error": str(e)}


async def _run(db: AsyncSession, doc: RagDocument) -> dict:
    raw = (doc.raw_content or "").strip()
    if not raw:
        raise ValueError("文档内容为空，无法处理")

    doc.status = DOC_PARSING
    doc.error_msg = None
    await db.commit()

    chunks = chunk_text(raw)
    if not chunks:
        raise ValueError("分块结果为空（内容可能全是空白）")
    contents = [c.content for c in chunks]

    doc.status = DOC_PARSED
    await db.commit()

    logger.info(f"[rag.pipeline] id={doc.id} 切出 {len(contents)} 块，开始向量化")
    vectors = await embed_texts(contents)

    n = await replace_chunks(db, doc, contents, vectors)
    logger.info(f"[rag.pipeline] id={doc.id} 完成，{n} 块已向量化（status=5）")
    return {"docId": doc.id, "ok": True, "chunks": n}


async def process_pending_documents(
    user_id: int, kb_id: Optional[int] = None, limit: int = 20
) -> dict:
    """把「还没向量化」的文档补跑一遍。

    覆盖两种半成品状态：
      - `status=1` 待解析
      - `status=3` **已解析但没向量化** —— SpringBoot 的 `/parse/pending` 端点
        只做 parse+chunk 就停了，这些文档永远停在 3、检索不到。这里一并补上。
    失败态（4）**不自动纳入**：避免把一直失败的文档反复重试打穿额度，交给显式重跑。

    ⚠️ `user_id` **必传**：省略 `kb_id` 时也只补跑**该用户自己的**文档。
    这里曾漏掉归属过滤 —— 省略 kbId 时会拿调用方的 embedding 额度替**全部用户**跑，
    并把别人的 `docId` 原样回给调用方。
    """
    async with async_session_factory() as db:
        q = (
            select(RagDocument)
            .where(
                RagDocument.user_id == user_id,
                RagDocument.status.in_([DOC_PENDING, DOC_PARSED]),
                RagDocument.raw_content.isnot(None),
            )
            .limit(limit)
        )
        if kb_id:
            q = q.where(RagDocument.kb_id == kb_id)
        doc_ids = [d.id for d in (await db.execute(q)).scalars().all()]

    ok = failed = 0
    for did in doc_ids:
        r = await process_document(did)
        if r.get("ok"):
            ok += 1
        else:
            failed += 1
    return {"total": len(doc_ids), "ok": ok, "failed": failed, "docIds": doc_ids}


async def reprocess_document(db: AsyncSession, user_id: int, doc_id: int) -> dict:
    """显式重跑单篇（失败重试入口）。会先校验归属，给「重试」按钮用。"""
    doc = await get_document(db, user_id, doc_id)
    if not (doc.raw_content or "").strip():
        # raw_content 是重跑的唯一依据。早期实现把全文只写临时文件、库里仅存 500 字预览，
        # 那种文档在这里会失败 —— 明确报出来，而不是静默产出一堆残缺块。
        raise ValueError(
            "该文档没有可用的原始内容（raw_content 为空），无法重新处理，请重新上传"
        )

    doc.status = DOC_PENDING
    doc.error_msg = None
    await db.commit()

    return await process_document(doc.id)


async def kb_has_vectorized_content(db: AsyncSession, kb_id: int) -> bool:
    """知识库里是否已有可检索内容（给「这个库还是空的」这类提示用）。"""
    row = (
        await db.execute(
            select(RagDocument.id)
            .where(RagDocument.kb_id == kb_id, RagDocument.status == 5)
            .limit(1)
        )
    ).first()
    return row is not None


__all__ = [
    "DOC_FAILED",
    "process_document",
    "process_pending_documents",
    "reprocess_document",
    "kb_has_vectorized_content",
]
