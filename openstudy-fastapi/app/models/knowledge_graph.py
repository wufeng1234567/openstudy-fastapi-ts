"""知识图谱：实体、关系与来源分块。

区别于旧的「资料知识地图」：
  · 旧地图节点是文档/章节页，边是页面层级；它不能回答“两个知识点是什么关系”。
  · 这里的节点由 LLM 从资料正文抽取，关系带方向、类型、强度与 evidence chunk，
    属于真正的实体-关系图；存储使用 PostgreSQL JSON 列，不引入 Neo4j。

表设计刻意保留 `chunk_ids` / `doc_ids`：
前端详情可以回到来源资料与分块，回答“这条关系是从哪句话抽出来的”。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RagGraphEntity(Base):
    """知识图谱实体（按用户 + 资料夹聚合）。

    `normalized_name` 只用于同一资料夹内合并同名实体；展示名仍是原文里出现的
    `name`，避免把「随机变量」和「随机变量X」强行改写成另一个词。
    """

    __tablename__ = "rag_graph_entity"
    __table_args__ = (
        UniqueConstraint("user_id", "kb_id", "normalized_name", name="uk_rag_graph_entity_name"),
        Index("idx_rag_graph_entity_user_kb", "user_id", "kb_id"),
        Index("idx_rag_graph_entity_type", "type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, default="概念")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    doc_ids: Mapped[Optional[list]] = mapped_column(JSON)
    chunk_ids: Mapped[Optional[list]] = mapped_column(JSON)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RagGraphRelation(Base):
    """实体关系；方向由 source -> target 表达。"""

    __tablename__ = "rag_graph_relation"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "kb_id", "source_id", "target_id", "relation_type",
            name="uk_rag_graph_relation",
        ),
        Index("idx_rag_graph_relation_user_kb", "user_id", "kb_id"),
        Index("idx_rag_graph_relation_source", "source_id"),
        Index("idx_rag_graph_relation_target", "target_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False, default="相关")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    doc_ids: Mapped[Optional[list]] = mapped_column(JSON)
    chunk_ids: Mapped[Optional[list]] = mapped_column(JSON)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
