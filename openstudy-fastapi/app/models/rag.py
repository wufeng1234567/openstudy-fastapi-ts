"""
RAG 知识库模型（**仅 PostgreSQL**）

为什么是 PG 专有
----------------
向量列用 pgvector 的 `vector(1024)`，全文列用 PG 的 `tsvector` 生成列 ——
这两者 MySQL 都没有。所以本模块只在 `IS_POSTGRES` 时才被 `init_db()` 导入；
用 `DB_DRIVER=mysql` 回滚时不会试图建这些表（否则 DDL 会直接失败）。

与 SpringBoot 时代那 4 张 `rag_*` 表的关系
------------------------------------------
**不复用**。老表留在 MySQL 里当归档，原因：
  1. 老的向量存在 Redis，已实测**全部丢失**（`embedding:*` 零键），115 个 chunk 是孤儿
  2. 老表用 `document_id`，且没有「混合检索」需要的 `content_tokens` / `kb_id` 冗余列
如果要把老文档迁过来，正确做法是读 `rag_document.raw_content` **重新分块 + 重新向量化**。

检索设计（相对 legacy 的三处修正）
----------------------------------
1. `kb_id` 冗余到 chunk 上 → 检索可直接 `WHERE kb_id = ANY(...)`，
   而不是 legacy 那样「超取 topK×3 再在内存里按 kb 过滤」（其它用户向量排在前面时会漏光）
2. `content_tokens` + `search_vec` → 关键词那一路能真正检索中文
   （PG 内置 `to_tsvector('simple', ...)` 不切分中文，整串会变成一个 token）
3. 向量索引 HNSW + 余弦距离 → 走原生 ANN，不用全表扫
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import VECTOR

from app.database import Base

#: 向量维度。与 `BAAI/bge-m3` 一致；换 embedding 模型必须同时改这里和索引。
EMBEDDING_DIM = 1024

#: 默认 embedding 模型（硅基流动，实测可用；DeepSeek 官方没有 embeddings 接口）
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"

#: 分块参数（对齐 SpringBoot 实现）
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 100

#: 文档处理状态机（对齐 SpringBoot 的 status 语义）
DOC_PENDING = 1      # 待解析
DOC_PARSING = 2      # 解析中
DOC_PARSED = 3       # 已解析（未向量化）
DOC_FAILED = 4       # 处理失败
DOC_VECTORIZED = 5   # 已向量化（可检索）

DOC_STATUS_TEXT = {
    DOC_PENDING: "待解析",
    DOC_PARSING: "解析中",
    DOC_PARSED: "已解析",
    DOC_FAILED: "处理失败",
    DOC_VECTORIZED: "已向量化",
}


class RagKnowledgeBase(Base):
    """知识库"""
    __tablename__ = "rag_knowledge_base"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # 记下用哪个模型、多少维、怎么切的 —— 否则换了模型就无从判断老向量还能不能用
    embedding_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default=DEFAULT_EMBEDDING_MODEL
    )
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=EMBEDDING_DIM)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_CHUNK_SIZE)
    chunk_overlap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_CHUNK_OVERLAP
    )

    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(1), nullable=False, default="0")
    del_flag: Mapped[str] = mapped_column(String(1), nullable=False, default="0")

    #: 「屏蔽」开关：`0` = 启用（默认，与历史行为完全一致），`1` = 已屏蔽。
    #: 屏蔽是**一道闸门** —— 被屏蔽的知识库对模型彻底不可见（提示词清单、list、
    #: 显式点名检索全部拿不到），但在管理列表里**照样看得见**，用户能自己再关掉。
    #:
    #: ⚠️ **不复用 `status`**（上一行）：那一列全仓**零读零写**、语义未定义（死列）。
    #: ⚠️ **不复用 `del_flag`**：那是逻辑删除（`'2'` = 已删，唯一写点在
    #:    `rag_write_service.delete_knowledge_base`）。屏蔽若走 del_flag，知识库会从
    #:    管理列表里消失、用户再也找不到那个开关，等于把自己的资料锁死。
    #: ⚠️ 语义方向是 `0 = 启用`（**不是** `1 = 启用`）：这样历史行不用回填、也不存在写反。
    disabled: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )

    #: 「工作空间」标记：`1` = 该用户的工作空间（每人一个），`0` = 普通知识库。
    #:
    #: 为什么复用知识库表而不是新建 Workspace 表：
    #:   工作空间里的文件同样要「解析 → 分块 → 向量化 → 被 AI 检索」，
    #:   与知识库是同一套链路。新建表等于把这套逻辑再抄一遍（早晚漂移），
    #:   而且 AI 的 `knowledge_search` 工具还得再写一份。
    #:
    #: 与普通知识库的差别只在**产品语义**：工作空间是「用户的资料抽屉」，
    #: 前端单独入口展示，不参与「选哪个库来出题」的显式选择。
    is_workspace: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )

    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RagDocument(Base):
    """知识库文档"""
    __tablename__ = "rag_document"
    __table_args__ = (
        Index("idx_rag_doc_kb", "kb_id"),
        Index("idx_rag_doc_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_knowledge_base.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(50))
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger)
    file_path: Mapped[Optional[str]] = mapped_column(String(500))

    # 解析出来的全文。留着它才能「不重新上传就重新分块 / 重新向量化」
    # ⚠️ 含 `【图N】` 图片位置标记（见 `file_parser.build_marked_document`）—— 标记本身
    #    很短且携带「这里有一张图」的真实信息，参与向量化不会明显污染语义。
    raw_content: Mapped[Optional[str]] = mapped_column(Text)

    #: 文档的图片清单：`{"0": "/profile/upload/...", "1": "...", ...}`（键即 `【图N】` 的 N）。
    #:
    #: 为什么单独一列、而不是把 base64 塞进 raw_content：
    #:   · data URL 动辄上百 KB，塞 JSON 列会白白撑大库；
    #:   · 落盘成 `/profile/upload/...` 后：① 前端（方案 B）能直接 `<img>` 显示、
    #:     ② 回给模型前用 `chat_engine.stored_image_to_data_url` 转回 data URL 即可。
    #: 空 / NULL = 该文档没有图。
    image_map: Mapped[Optional[dict]] = mapped_column(JSON)

    #: 用户给这份资料写的一句话说明（如「高二期末卷」「第四章课件」）。
    #:
    #: 为什么需要它：工作空间里的文件往往名字很随便（`新建文档(2).docx`、
    #: `扫描件001.pdf`），只靠文件名 AI 分不清哪份是用户说的「那份概率论的资料」。
    #: 用户写一句人话说明，AI 找文件时就能对上。
    #: NULL = 没写（此时 AI 只能靠文件名 + 正文内容判断）。
    user_note: Mapped[Optional[str]] = mapped_column(String(200))

    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=DOC_PENDING)
    error_msg: Mapped[Optional[str]] = mapped_column(String(500))

    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RagDocumentChunk(Base):
    """文档分块（含向量与分词，检索的最小单位）"""
    __tablename__ = "rag_document_chunk"
    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", name="uk_rag_chunk_doc_index"),
        # 隔离过滤走这个索引（检索时按 kb_id 收窄，不能靠内存过滤）
        Index("idx_rag_chunk_kb", "kb_id"),
        Index("idx_rag_chunk_doc", "doc_id"),
        # 向量路：HNSW + 余弦距离
        Index(
            "idx_rag_chunk_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # 关键词路：中文/代码标识符的模糊兜底
        Index(
            "idx_rag_chunk_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
        # 关键词路主力：分词后的 tsvector
        Index("idx_rag_chunk_fts", "search_vec", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 冗余 kb_id：检索时直接 SQL 过滤，避免 legacy「超取再内存过滤」的漏召回
    kb_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_knowledge_base.id"), nullable=False
    )
    doc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rag_document.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_length: Mapped[Optional[int]] = mapped_column(Integer)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)

    #: jieba 分词结果（空格连接）。PG 内置分词不切中文，中文检索必须靠它
    content_tokens: Mapped[Optional[str]] = mapped_column(Text)

    #: 向量。NULL 表示还没向量化
    embedding: Mapped[Optional[list]] = mapped_column(VECTOR(EMBEDDING_DIM))

    #: 全文检索列：由 content_tokens 自动生成，不用应用层维护
    search_vec: Mapped[Optional[str]] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content_tokens, ''))", persisted=True),
    )

    meta_data: Mapped[Optional[dict]] = mapped_column(JSON)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RagQaRecord(Base):
    """知识库问答记录（含检索命中，便于回溯「这句是从哪来的」）"""
    __tablename__ = "rag_qa_record"
    __table_args__ = (
        Index("idx_rag_qa_kb", "kb_id"),
        Index("idx_rag_qa_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    kb_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("rag_knowledge_base.id")
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[Optional[str]] = mapped_column(Text)
    #: 命中的 chunk（含出处与分数），JSON 存一份快照
    retrieved_chunks: Mapped[Optional[list]] = mapped_column(JSON)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    feedback: Mapped[Optional[int]] = mapped_column(Integer)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
