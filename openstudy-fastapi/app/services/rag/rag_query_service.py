"""
RAG 查询服务（检索 + 问答）

设计要点
--------
1. **真做相关性判断** —— legacy 把阈值做成了死代码（`isInScope` 硬编码 `true`），
   检索不到内容也照样回答，等于没有兜底。这里检索为空就明确说「没找到」。
2. **带出处** —— legacy 的 `RagAnswerResponse` 没有 citations，用户无法核对。
   这里每个片段都带 `docName + 块序号`，回答里也用 `【1】【2】` 标注。
3. **上下文预算** —— 检索片段不是越多越好：单块截断 + 总量封顶，避免把上下文撑爆
   导致真正的问题被挤出去。
4. **权限** —— `user_id` 由调用方从 JWT 取得，知识库归属在写服务里逐个校验。
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagQaRecord
from app.services.ai.base_client import ChatMessage, ImageBlock, TextBlock
from app.services.ai.db_config import chat_with_config
from app.services.rag.embedding import embed_query
from app.services.rag.hybrid_search import (
    ChunkHit,
    has_keyword_agreement,
    hybrid_search,
)
from app.services.rag.rag_write_service import resolve_knowledge_bases, sanitize_text

#: 单块塞进 prompt 的最大字符数
MAX_CHUNK_CHARS = 1200
#: 全部检索片段加起来的上限
MAX_CONTEXT_CHARS = 6000
#: 默认检索条数
DEFAULT_TOP_K = 5

NO_HIT_ANSWER = "在当前知识库中没有找到与这个问题相关的内容。可以换个说法，或先往知识库里补充相关文档。"

SYSTEM_PROMPT_TEMPLATE = """你是 OpenStudy 的知识库问答助手，当前基于用户的知识库「{kb_names}」回答问题。

【背景知识】
{context}

【要求】
1. 优先依据上面的背景知识回答，不要凭自己的知识编造背景里没有的内容
2. 引用背景知识时用 【编号】 标出来源，例如「……是 O(log n)【1】」
3. 如果背景知识只有部分相关，就基于已有内容回答，并说明哪部分来自知识库
4. **如果背景知识完全没有相关信息，直接说「在当前知识库中没有找到相关内容」**，不要硬答
5. 用清晰的结构（标题、列表）组织回答
"""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_context(hits: Sequence[ChunkHit]) -> str:
    """把命中片段拼成带编号的上下文，并做总量预算。"""
    parts: list[str] = []
    used = 0
    for i, hit in enumerate(hits, start=1):
        piece = f"【{i}】来源：{hit.source}\n{_truncate(hit.content, MAX_CHUNK_CHARS)}"
        if used + len(piece) > MAX_CONTEXT_CHARS:
            logger.info(f"[rag] 上下文预算用尽，只放入前 {i - 1} 条片段")
            break
        parts.append(piece)
        used += len(piece)
    return "\n\n".join(parts)


async def search(
    db: AsyncSession,
    user_id: int,
    query: str,
    kb_ids: Optional[Sequence[int]] = None,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """只做检索，不调模型。给前端做「命中了哪些片段」的预览。"""
    # 先清 NUL / 非法 UTF-8：JSON 能编码 NUL，而 PG 的 text 参数拒收 0x00，
    # 留着它会一路带到向量化与全文检索（都会 500）。
    query = sanitize_text(query or "").strip()
    if not query:
        raise ValueError("查询内容不能为空")

    kbs = await resolve_knowledge_bases(db, user_id, kb_ids)
    if not kbs:
        return {"query": query, "hits": [], "knowledgeBases": [], "reason": "没有可检索的知识库"}

    query_vector = await embed_query(query)
    hits = await hybrid_search(
        db, query, query_vector, [kb.id for kb in kbs], top_k=top_k
    )
    return {
        "query": query,
        "hits": [h.to_dict() for h in hits],
        "knowledgeBases": [{"kbId": kb.id, "name": kb.name} for kb in kbs],
    }


async def answer(
    db: AsyncSession,
    user_id: int,
    query: str,
    kb_ids: Optional[Sequence[int]] = None,
    top_k: int = DEFAULT_TOP_K,
    session_id: Optional[str] = None,
    include_history: bool = True,
) -> dict:
    """RAG 问答：检索 → 拼 prompt → 调模型 → 落库。

    `session_id` 给定时会带上该会话的最近若干轮，让追问有上下文
    （「它」指什么、「那」是哪个 —— 没有历史的话多轮追问基本没法用）。
    """
    # 入口先清 NUL / 非法 UTF-8（见 search 里的说明）：
    # 这里既是提问的入口，也是 rag_qa_record.question 的唯一来源。
    query = sanitize_text(query or "").strip()
    if not query:
        raise ValueError("问题不能为空")

    kbs = await resolve_knowledge_bases(db, user_id, kb_ids)
    kb_names = "、".join(kb.name for kb in kbs) if kbs else "（无）"

    if not kbs:
        return await _no_hit_result(
            db, user_id, query, None, kbs, reason="没有可检索的知识库"
        )

    query_vector = await embed_query(query)
    hits = await hybrid_search(
        db, query, query_vector, [kb.id for kb in kbs], top_k=top_k
    )

    # 真正的相关性兜底：检索为空就不编答案（legacy 这里是硬编码 true）
    if not hits:
        return await _no_hit_result(
            db, user_id, query, kbs[0].id, kbs, reason="未检索到相关内容"
        )

    context = build_context(hits)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(kb_names=kb_names, context=context)

    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]

    if include_history and session_id:
        try:
            from app.services.ai import conversation_service

            history = await conversation_service.build_context_prompt(
                user_id, session_id, lang="zh"
            )
            if history:
                messages.append(
                    ChatMessage(role="user", content=f"（以下是之前的对话，供参考）\n{history}")
                )
        except Exception as e:  # 历史拿不到不该让问答挂掉
            logger.warning(f"[rag] 读取会话历史失败，忽略: {e}")

    # 命中片段夹带的图：读盘转 data URL，作为多模态内容块随提问一起交给模型。
    # 这样「基于知识库回答」时，模型也能看到原文里的公式图/表格图，而不是只读文字。
    hit_image_urls: list[str] = []
    for h in hits:
        for u in (getattr(h, "images", None) or []):
            if u and u not in hit_image_urls:
                hit_image_urls.append(u)
    user_content: Union[str, list] = query
    if hit_image_urls:
        from app.services.ai.chat_engine import stored_image_to_data_url

        blocks: list = [TextBlock(type="text", text=query)] if query else []
        added = 0
        for url in hit_image_urls:
            data_url = stored_image_to_data_url(url)
            if data_url:
                blocks.append(ImageBlock(type="image_url", image_url={"url": data_url}))
                added += 1
        if added:
            user_content = blocks
            logger.info(f"[rag] 命中片段夹带 {added} 张图，已作为多模态内容块提交")
    messages.append(ChatMessage(role="user", content=user_content))

    response = await chat_with_config(
        db, messages, temperature=0.3, user_id=user_id
    )
    # 模型输出同样要过一遍：写库前一律 sanitize（PG 拒收 NUL）
    text = sanitize_text(response.content or "").strip()

    citations = [
        {
            "index": i,
            "chunkId": h.chunk_id,
            "docId": h.doc_id,
            "docName": h.doc_name,
            "chunkIndex": h.chunk_index,
            "source": h.source,
            "score": round(h.score, 6),
            "vectorScore": None if h.vector_score is None else round(h.vector_score, 4),
            "keywordScore": None if h.keyword_score is None else round(h.keyword_score, 4),
            "preview": _truncate(h.content, 200),
            # 该片段夹带的图（前端可据 preview/图 URL 渲染；空列表 = 无图）
            "images": list(getattr(h, "images", None) or []),
        }
        for i, h in enumerate(hits, start=1)
    ]

    record = RagQaRecord(
        user_id=user_id,
        kb_id=kbs[0].id,
        # 写库点兜底（规范：写库前一律过 sanitize_text）——上面虽已清过，这里不省，
        # 免得以后有人从别处接进来一条没清过的 query。
        question=sanitize_text(query),
        answer=sanitize_text(text),
        retrieved_chunks=citations,
    )
    db.add(record)
    await db.commit()

    # ⚠️ `found` 表示「检索到了候选片段」，**不等于「答案一定对」**。
    #    余弦相似度不能用来判断相关性（见 hybrid_search.DEFAULT_MIN_SIMILARITY 的实测数据），
    #    所以额外给一个可靠得多的信号：关键词那一路有没有命中。
    #    只有向量路命中时，可能是换词提问（真相关），也可能是跑题（不相关）——交给调用方决定
    #    怎么提示，而不是在这里武断拒答。
    low_confidence = not has_keyword_agreement(hits)

    return {
        "answer": text,
        "found": True,
        "lowConfidence": low_confidence,
        "usedKnowledgeBase": True,
        "knowledgeBases": [{"kbId": kb.id, "name": kb.name} for kb in kbs],
        "citations": citations,
        "qaId": record.id,
    }


async def _no_hit_result(
    db: AsyncSession,
    user_id: int,
    query: str,
    kb_id: Optional[int],
    kbs,
    reason: str,
) -> dict:
    """没检索到内容时的统一返回。

    刻意**不调用模型**：没有依据的生成一定是幻觉，不如直接说没找到，
    并把原因讲清楚（是没知识库，还是知识库里确实没有）。
    """
    logger.info(f"[rag] 未命中，直接返回兜底话术：{reason}")
    record = RagQaRecord(
        user_id=user_id,
        kb_id=kb_id,
        # 同上：这是写库点，sanitize 不省（未命中路径同样会落一条 question）
        question=sanitize_text(query),
        answer=sanitize_text(NO_HIT_ANSWER),
        retrieved_chunks=[],
    )
    db.add(record)
    await db.commit()
    return {
        "answer": NO_HIT_ANSWER,
        "found": False,
        "usedKnowledgeBase": False,
        "knowledgeBases": [{"kbId": kb.id, "name": kb.name} for kb in kbs],
        "citations": [],
        "qaId": record.id,
        "reason": reason,
    }
