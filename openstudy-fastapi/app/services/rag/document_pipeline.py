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

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import or_, select
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


def apply_excluded_ranges(raw: str, ranges: list | None) -> str:
    """按软剔除范围过滤检索文本；原始 raw_content 永远不动。"""
    if not ranges:
        return raw
    spans = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        start = item.get("start")
        end = item.get("end")
        if start is None or end is None:
            continue
        spans.append((max(0, int(start)), min(len(raw), int(end))))
    if not spans:
        return raw
    spans.sort()
    out = []
    pos = 0
    for start, end in spans:
        if end <= pos:
            continue
        if start > pos:
            out.append(raw[pos:start])
        out.append("\n")
        pos = max(pos, end)
    out.append(raw[pos:])
    return "".join(out)
from app.services.rag.embedding import embed_texts
from app.services.rag.rag_write_service import (
    get_document,
    mark_document_failed,
    replace_chunks,
)


async def queue_reprocess_document(db: AsyncSession, user_id: int, doc_id: int) -> dict:
    """只把文档置为待解析并立即返回，真正的解析/向量化交给 BackgroundTasks。

    为什么单独拆出来：
      · 旧接口 `reprocess_document` 会在请求里同步跑完 embedding，30~60 秒不返回，
        用户点一下只能看到按钮"没反应"；前端请求超时后还会误以为失败。
      · 现在先返回 queued，前端用 `/document/status/{docId}` 轮询 1→2→3→5，
        按钮可以展示真实阶段和进度，而不是一个不确定的等待。
    """
    doc = await get_document(db, user_id, doc_id)
    if not (doc.raw_content or "").strip():
        raise ValueError(
            "该文档没有可用的原始内容（raw_content 为空），无法重新处理，请重新上传"
        )
    if doc.status in (DOC_PENDING, DOC_PARSING):
        raise ValueError("这份资料正在处理中，等它完成后再试")
    doc.status = DOC_PENDING
    doc.error_msg = None
    doc.update_time = datetime.utcnow()
    await db.commit()
    return {
        "docId": doc.id,
        "fileName": doc.file_name,
        "status": doc.status,
        "statusText": "待解析",
        "queued": True,
    }


#: 同一文档只允许一条在跑的流水线。上传、重解析、整理后重建索引
#: 都可能从不同入口触发；没有这个锁时同一篇文档会被重复切分/向量化，
#: 后完成的旧任务也可能覆盖新任务的状态。
_PIPELINE_LOCKS: dict[int, asyncio.Lock] = {}


def _pipeline_lock(doc_id: int) -> asyncio.Lock:
    lock = _PIPELINE_LOCKS.get(doc_id)
    if lock is None:
        lock = asyncio.Lock()
        _PIPELINE_LOCKS[doc_id] = lock
    return lock


async def process_document(doc_id: int) -> dict:
    """完整处理一篇文档（基于已落库的 `raw_content`）。

    单文档单飞：如果已有同文档任务在跑，直接返回 duplicate，不重复消耗 embedding。
    自身开会话：调用方通常只把它丢进 BackgroundTasks，那时请求会话已经关了。
    """
    lock = _pipeline_lock(doc_id)
    if lock.locked():
        logger.info(f"[rag.pipeline] id={doc_id} 已有任务在跑，跳过重复任务")
        return {"docId": doc_id, "ok": True, "duplicate": True, "status": "running"}
    async with lock:
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


async def recover_stale_documents(max_age_minutes: int = 15) -> dict:
    """启动时回收上次进程崩溃留下的「解析中」文档。

    不自动重跑：embedding 可能仍不可用，自动重跑会把所有卡住文档重新打一遍。
    先统一标记失败并给出明确原因，用户可从文档行手动重试。
    """
    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
    async with async_session_factory() as db:
        rows = (
            await db.execute(
                select(RagDocument).where(
                    RagDocument.status == DOC_PARSING,
                    or_(RagDocument.update_time.is_(None), RagDocument.update_time < cutoff),
                )
            )
        ).scalars().all()
        for doc in rows:
            doc.status = DOC_FAILED
            doc.error_msg = "处理中断（服务重启或任务异常），请重新解析"
            doc.update_time = datetime.utcnow()
        if rows:
            await db.commit()
            logger.warning(f"[rag.pipeline] 回收 {len(rows)} 个卡在解析中的文档")
    return {"recovered": len(rows)}


async def _run(db: AsyncSession, doc: RagDocument) -> dict:
    raw = (doc.raw_content or "").strip()
    if not raw:
        raise ValueError("文档内容为空，无法处理")

    doc.status = DOC_PARSING
    doc.error_msg = None
    doc.update_time = datetime.utcnow()
    await db.commit()

    searchable = apply_excluded_ranges(raw, doc.excluded_ranges)
    chunks = chunk_text(searchable)
    if not chunks:
        raise ValueError("分块结果为空（内容可能全是空白）")
    contents = [c.content for c in chunks]

    doc.status = DOC_PARSED
    doc.update_time = datetime.utcnow()
    await db.commit()

    logger.info(f"[rag.pipeline] id={doc.id} 切出 {len(contents)} 块，开始向量化")
    vectors = await embed_texts(contents)

    n = await replace_chunks(db, doc, contents, vectors)
    logger.info(f"[rag.pipeline] id={doc.id} 完成，{n} 块已向量化（status=5）")

    # 解析完成后自动更新该文档所在资料夹的知识图谱。
    # 后台任务里失败不能影响文档本身已经成功的解析状态，所以只记日志。
    try:
        from app.services.rag.knowledge_graph_service import build_graph

        graph_result = await build_graph(
            db,
            int(doc.user_id),
            int(doc.kb_id),
            doc_ids=[int(doc.id)],
        )
        logger.info(
            f"[rag.pipeline] id={doc.id} 知识图谱自动更新："
            f"{graph_result.get('entities', 0)} 实体 / {graph_result.get('relations', 0)} 关系"
        )
    except Exception as graph_error:  # noqa: BLE001
        logger.warning(f"[rag.pipeline] id={doc.id} 知识图谱自动更新失败：{graph_error}")

    # 文档变化后，已经生成的主题页可能过期；标记为 stale，避免它继续参与 RAG。
    try:
        from app.services.rag.wiki_service import mark_wiki_pages_stale

        marked = await mark_wiki_pages_stale(
            db, int(doc.user_id), int(doc.kb_id), [int(doc.id)]
        )
        if marked:
            logger.info(f"[rag.pipeline] id={doc.id} 标记 {marked} 个知识百科页面待更新")
    except Exception as wiki_error:  # noqa: BLE001
        logger.warning(f"[rag.pipeline] id={doc.id} 标记知识百科页面失效失败：{wiki_error}")

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
    doc.update_time = datetime.utcnow()
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
    "recover_stale_documents",
    "kb_has_vectorized_content",
]
