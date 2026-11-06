"""知识百科（Wiki）页面、页面链接与检索分块。

设计边界
--------
- `rag_graph_entity` / `rag_graph_relation` 仍是底层实体索引，供 GraphRAG 使用；
- `rag_wiki_page` 是面向用户的可读主题页，内容来自原始 chunk，不是凭空扩写；
- `rag_wiki_page_link` 是页面之间的导航图（知识图谱的页面关系），不是第二套实体图；
- `rag_wiki_chunk` 让知识百科本身也能被 RAG 检索到，但每条命中都必须能回到原资料。

页面正文同时保留 `content_md` 与结构化 `sections`：
  · 前端按 sections 渲染标题/段落/来源；
  · 导出或复制时用 content_md。
"""

from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    BigInteger,
    Computed,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.rag import EMBEDDING_DIM


class RagWikiPage(Base):
    """一个资料夹内的可读知识主题页。"""

    __tablename__ = "rag_wiki_page"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kb_id", "normalized_title", name="uk_rag_wiki_page_title"
        ),
        Index("idx_rag_wiki_page_user_kb", "user_id", "kb_id"),
        Index("idx_rag_wiki_page_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: concept/entity/synthesis/comparison/summary/overview；旧数据 topic 仍兼容
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default="topic")
    #: 同义名/缩写，供页面内链识别与展示；不是第二套标题
    aliases: Mapped[Optional[list]] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    #: [{"heading":"核心要点","body":"...","sourceChunkIds":[1,2]}]
    sections: Mapped[Optional[list]] = mapped_column(JSON)
    #: [{"docId":1,"chunkId":2,"docName":"...","chunkIndex":0,"quote":"..."}]
    source_refs: Mapped[Optional[list]] = mapped_column(JSON)
    source_doc_ids: Mapped[Optional[list]] = mapped_column(JSON)
    source_chunk_ids: Mapped[Optional[list]] = mapped_column(JSON)
    entity_ids: Mapped[Optional[list]] = mapped_column(JSON)

    #: draft / ready / stale / failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    generation_meta: Mapped[Optional[dict]] = mapped_column(JSON)

    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RagWikiPageRevision(Base):
    """主题页版本快照：手动编辑 / AI 重生成 / 恢复前各留一份。"""

    __tablename__ = "rag_wiki_page_revision"
    __table_args__ = (
        Index("idx_rag_wiki_revision_page", "page_id", "version"),
        Index("idx_rag_wiki_revision_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sections: Mapped[Optional[list]] = mapped_column(JSON)
    source_refs: Mapped[Optional[list]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    change_type: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RagWikiPageLink(Base):
    """主题页之间的导航边，构成“知识图谱”的页面关系。"""

    __tablename__ = "rag_wiki_page_link"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kb_id",
            "from_page_id",
            "to_page_id",
            "link_type",
            name="uk_rag_wiki_page_link",
        ),
        Index("idx_rag_wiki_page_link_from", "from_page_id"),
        Index("idx_rag_wiki_page_link_to", "to_page_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: related / prerequisite / contrast / part_of
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="graph")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RagWikiChunk(Base):
    """知识百科小节级检索块，使 Wiki 页面参与 RAG。"""

    __tablename__ = "rag_wiki_chunk"
    __table_args__ = (
        Index("idx_rag_wiki_chunk_page", "page_id"),
        Index("idx_rag_wiki_chunk_kb", "kb_id"),
        Index(
            "idx_rag_wiki_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("idx_rag_wiki_chunk_fts", "search_vec", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section_title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tokens: Mapped[Optional[str]] = mapped_column(Text)
    embedding: Mapped[Optional[list]] = mapped_column(VECTOR(EMBEDDING_DIM))
    search_vec: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content_tokens, ''))", persisted=True),
    )
    source_chunk_ids: Mapped[Optional[list]] = mapped_column(JSON)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
