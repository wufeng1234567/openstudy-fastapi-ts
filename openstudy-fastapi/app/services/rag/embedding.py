"""
文本向量化

走 `dynamic_ai` 动态路由（默认 `BAAI/bge-m3`，硅基流动）。
选它的实测理由：DeepSeek 官方**没有** embeddings 接口（`/embeddings` 对所有模型名都 404），
智谱 key 有效但余额不足。

⚠️ 维度必须与 `models/rag.py: EMBEDDING_DIM`（= 建表时 `vector(1024)`）一致。
换了维度不同的模型，插入会直接失败 —— 所以这里每次调用都校验维度并给出明确报错，
而不是等 asyncpg 抛一句难懂的 `expected 1024 dimensions`。
"""

from __future__ import annotations

from loguru import logger

from app.config import settings
from app.models.rag import EMBEDDING_DIM
from app.services.ai.dynamic_ai import dynamic_ai

#: 单批条数。embedding 接口对 batch 大小有限制，且过大容易超时
BATCH_SIZE = 16


class EmbeddingError(RuntimeError):
    """向量化失败（配置缺失、上游报错、维度不符）"""


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化。返回顺序与入参一一对应。"""
    if not texts:
        return []

    model = settings.AI_DEFAULT_EMBEDDING_MODEL
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        try:
            got = await dynamic_ai.embeddings(texts=batch, model=model)
        except Exception as e:  # 上游/网络/额度问题统一收口
            raise EmbeddingError(f"向量化调用失败（model={model}）: {e}") from e

        if len(got) != len(batch):
            raise EmbeddingError(
                f"向量化返回条数不符：请求 {len(batch)} 条，返回 {len(got)} 条"
            )
        vectors.extend(got)

    _validate_dim(vectors, model)
    return vectors


async def embed_query(text: str) -> list[float]:
    """查询词向量化。返回单个向量。"""
    vectors = await embed_texts([text])
    if not vectors:
        raise EmbeddingError("查询向量化返回空结果")
    return vectors[0]


def _validate_dim(vectors: list[list[float]], model: str) -> None:
    """只校验第一条 —— 同一模型同一次调用不会有不同维度，逐条查是浪费。"""
    if not vectors:
        return
    got = len(vectors[0])
    if got != EMBEDDING_DIM:
        raise EmbeddingError(
            f"向量维度不符：model={model} 返回 {got} 维，"
            f"但表结构是 vector({EMBEDDING_DIM})。"
            f"请改用 {EMBEDDING_DIM} 维的 embedding 模型"
            f"（或在 models/rag.py 改 EMBEDDING_DIM 并重建向量索引）。"
        )
