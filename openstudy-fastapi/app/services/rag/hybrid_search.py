"""
混合检索：pgvector 向量召回 + 全文召回，用 RRF 融合

为什么不做纯向量
----------------
纯向量对**专有名词 / 代码标识符 / 缩写**（`is_public`、`RAII`、`2PC`）召回很差 ——
这类词在语义空间里没有稳定的近邻，但关键词能精确命中。所以两路都要。

为什么用 RRF 而不是加权分数
--------------------------
向量相似度（0~1 的余弦）与全文 `ts_rank_cd`（无上界的词频分）**量纲完全不同**，
直接加权需要拍一个没有依据的系数。RRF 只看**排名**，天然规避了这个问题，
且不需要调参：

    score(d) = Σ_lens  1 / (K + rank_lens(d))      K 取 60（原论文推荐值）

相对 legacy 的三处修正
----------------------
1. **SQL 级按 kb 过滤**（`WHERE kb_id = ANY(...)`），而不是 legacy 的
   「超取 topK×3 再在内存里过滤」—— 后者在别人向量排在前面时会**漏光**
2. 关键词那一路走 jieba 分词（PG 内置分词不切中文，见 tokenizer.py）
3. 保留 `vector_score` / `keyword_score` 两路原始分，便于回溯与调阈值
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from loguru import logger
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag import RagDocument, RagDocumentChunk
from app.services.rag.tokenizer import query_tokens

#: RRF 平滑常数（原论文建议 60）
RRF_K = 60

#: 每一路各取多少条候选。取 top_k 的 3 倍以给融合留空间，但**不像 legacy 那样靠超取来补过滤**
CANDIDATE_MULTIPLIER = 3

#: 向量相似度下限 —— **只是个「垃圾过滤」，不是相关性判据**。
#:
#: ⚠️ 别指望靠调这个值来解决「不相关的问题也被检索到」。实测（`BAAI/bge-m3`）：
#:
#:     相关查询「二叉搜索树的时间复杂度」   top1=0.7467  top2=0.3657  top3=0.2647
#:     无关查询「量子纠缠和薛定谔猫…」       top1=0.6182  top2=0.3005  top3=0.2562
#:
#: 无关查询的 top1 甚至**高于**相关查询的 top2 —— BGE 系 embedding 对中文有一个很高的
#: 「相似度地板」。所以设 0.3 等于全放行，设 0.65 又会误杀真相关内容。
#: 相关性真正的信号是 `keyword_hit`（关键词那一路有没有命中，见 `has_keyword_agreement`），
#: 以及最后由模型自己判断「背景知识里没有」。
DEFAULT_MIN_SIMILARITY = 0.30

#: to_tsquery 里非法的字符。只保留中英文/数字/下划线，其余当分隔符
_UNSAFE_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


@dataclass
class ChunkHit:
    """一条命中分块。`score` 是融合后的分，两路原始分另存备查。"""
    chunk_id: int
    doc_id: int
    kb_id: int
    chunk_index: int
    content: str
    doc_name: Optional[str] = None
    score: float = 0.0
    vector_score: Optional[float] = None
    keyword_score: Optional[float] = None
    vec_rank: Optional[int] = None
    kw_rank: Optional[int] = None
    #: 该分块关联的图片 URL 列表（`/profile/upload/...` 或 http(s) 外链）。
    #: 来自 `rag_document_chunk.meta_data["images"]`（分块时按正文 `【图N】` 归属）。
    #: 空 = 这一块没有图。检索命中时把它作为多模态图片一起回给模型（见
    #: `rag_query_service` / `chat_engine._retrieve_kb_context`）。
    images: list[str] = field(default_factory=list)

    @property
    def source(self) -> str:
        """给模型/前端看的出处文案。"""
        name = self.doc_name or f"文档#{self.doc_id}"
        return f"{name} 第 {self.chunk_index + 1} 段"

    def to_dict(self) -> dict:
        return {
            "chunkId": self.chunk_id,
            "docId": self.doc_id,
            # kbId 必须带出来：`knowledge_search` 默认是**跨库**检索的，
            # 模型要靠它说清「这条出自哪个知识库」（只给文件名不够 —— 不同库里
            # 完全可能有一模一样的文件名）。
            "kbId": self.kb_id,
            "docName": self.doc_name,
            "chunkIndex": self.chunk_index,
            "content": self.content,
            "score": round(self.score, 6),
            "vectorScore": None if self.vector_score is None else round(self.vector_score, 4),
            "keywordScore": None if self.keyword_score is None else round(self.keyword_score, 4),
            "source": self.source,
            # 图片：模型/前端据此把命中片段里的插图一起用上
            "images": list(self.images),
        }


def _kb_filter(stmt: Select, kb_ids: Sequence[int]) -> Select:
    if kb_ids:
        return stmt.where(RagDocumentChunk.kb_id.in_(list(kb_ids)))
    # 没有可用知识库时，用一个恒假条件短路，避免退化成「检索全库」
    return stmt.where(RagDocumentChunk.kb_id < 0)


def _chunk_images(chunk: RagDocumentChunk) -> list[str]:
    """从分块 `meta_data` 里取图片 URL 列表（分块时按 `【图N】` 归属写入）。

    容错：`meta_data` 可能是 None / 非 dict / images 非 list（历史数据或手改），
    任何异常都当作「没有图」，绝不让它影响检索主流程。
    """
    try:
        meta = chunk.meta_data
        if not isinstance(meta, dict):
            return []
        imgs = meta.get("images")
        if not isinstance(imgs, list):
            return []
        return [str(u) for u in imgs if u]
    except Exception:  # noqa: BLE001
        return []


async def vector_search(
    db: AsyncSession,
    query_vector: list[float],
    kb_ids: Sequence[int],
    top_k: int,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[ChunkHit]:
    """向量召回（pgvector 余弦距离，走 HNSW 索引）。"""
    distance = RagDocumentChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(RagDocumentChunk, RagDocument.file_name, distance.label("distance"))
        .join(RagDocument, RagDocument.id == RagDocumentChunk.doc_id)
        .where(RagDocumentChunk.embedding.isnot(None))
        .order_by(distance)
        .limit(top_k)
    )
    stmt = _kb_filter(stmt, kb_ids)

    rows = (await db.execute(stmt)).all()
    hits: list[ChunkHit] = []
    for row in rows:
        chunk: RagDocumentChunk = row[0]
        similarity = 1.0 - float(row[2])
        if similarity < min_similarity:
            continue
        hits.append(
            ChunkHit(
                chunk_id=chunk.id,
                doc_id=chunk.doc_id,
                kb_id=chunk.kb_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                doc_name=row[1],
                vector_score=similarity,
                images=_chunk_images(chunk),
            )
        )
    return hits


async def keyword_search(
    db: AsyncSession,
    query: str,
    kb_ids: Sequence[int],
    top_k: int,
) -> list[ChunkHit]:
    """全文召回（jieba 分词 + tsvector，走 GIN 索引）。"""
    tokens = [_UNSAFE_RE.sub("", t) for t in query_tokens(query)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return []

    # 用 OR 连接以提高召回率（AND 太严，中文短查询经常一条都匹配不上）
    tsquery = func.to_tsquery("simple", " | ".join(tokens))
    rank = func.ts_rank_cd(RagDocumentChunk.search_vec, tsquery)

    stmt = (
        select(RagDocumentChunk, RagDocument.file_name, rank.label("rank"))
        .join(RagDocument, RagDocument.id == RagDocumentChunk.doc_id)
        .where(RagDocumentChunk.search_vec.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(top_k)
    )
    stmt = _kb_filter(stmt, kb_ids)

    rows = (await db.execute(stmt)).all()
    return [
        ChunkHit(
            chunk_id=row[0].id,
            doc_id=row[0].doc_id,
            kb_id=row[0].kb_id,
            chunk_index=row[0].chunk_index,
            content=row[0].content,
            doc_name=row[1],
            keyword_score=float(row[2]),
            images=_chunk_images(row[0]),
        )
        for row in rows
    ]


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[ChunkHit]],
    top_k: int,
    k: int = RRF_K,
) -> list[ChunkHit]:
    """把多路结果按 RRF 融合。

    只依赖**排名**，所以向量分和全文分不需要归一化、也不用拍权重系数。
    """
    fused: dict[int, ChunkHit] = {}
    for hits in result_lists:
        for rank, hit in enumerate(hits):
            entry = fused.get(hit.chunk_id)
            if entry is None:
                entry = ChunkHit(
                    chunk_id=hit.chunk_id,
                    doc_id=hit.doc_id,
                    kb_id=hit.kb_id,
                    chunk_index=hit.chunk_index,
                    content=hit.content,
                    doc_name=hit.doc_name,
                    images=list(hit.images),
                )
                fused[hit.chunk_id] = entry
            elif hit.images and not entry.images:
                # 两路都命中同一块时，images 取非空的一路（两路都来自同一行，值一致）
                entry.images = list(hit.images)
            entry.score += 1.0 / (k + rank)
            # 同一块可能两路都命中，两路原始分都留一份
            if hit.vector_score is not None:
                entry.vector_score = hit.vector_score
                entry.vec_rank = rank
            if hit.keyword_score is not None:
                entry.keyword_score = hit.keyword_score
                entry.kw_rank = rank

    ordered = sorted(fused.values(), key=lambda h: h.score, reverse=True)
    return ordered[:top_k]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    query_vector: Optional[list[float]],
    kb_ids: Sequence[int],
    top_k: int = 5,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> list[ChunkHit]:
    """向量 + 全文混合检索。

    `query_vector` 为 None 时降级为纯关键词检索（向量化失败不该让整个检索挂掉）。
    """
    if not kb_ids:
        return []

    pool = max(top_k * CANDIDATE_MULTIPLIER, top_k)

    vec_hits: list[ChunkHit] = []
    if query_vector:
        try:
            vec_hits = await vector_search(db, query_vector, kb_ids, pool, min_similarity)
        except Exception as e:  # pragma: no cover - 向量路异常不应拖垮关键词路
            logger.warning(f"[rag] 向量检索失败，降级为纯关键词检索: {e}")

    kw_hits = await keyword_search(db, query, kb_ids, pool)

    if not vec_hits and not kw_hits:
        return []
    if not vec_hits:
        return kw_hits[:top_k]
    if not kw_hits:
        return vec_hits[:top_k]

    return reciprocal_rank_fusion([vec_hits, kw_hits], top_k)


def has_keyword_agreement(hits: Sequence[ChunkHit]) -> bool:
    """结果里是否至少有一条是**关键词那一路**命中的。

    这是比余弦阈值可靠得多的相关性信号：真正切题的查询，用户问法和文档用词总会有
    共同词（术语、实体名、标识符）；而完全跑题的查询，两边的词几乎不重合。

    注意它只是**置信度提示**而非拦截 —— 换词提问（「哪种树查找是 O(logn)」）也可能
    关键词零命中但语义相关，所以不能据此拒绝回答，只能据此降低置信度。
    """
    return any(h.keyword_score is not None for h in hits)
