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

    #: 来源标记：self = 用户自己的；share = 从分享领取的物理副本
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="self", server_default="self"
    )
    source_kb_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    share_id: Mapped[Optional[int]] = mapped_column(BigInteger)

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
    #: 自动整理后保留上传时的原始文件名；file_name 可以是整理后的展示名
    original_file_name: Mapped[Optional[str]] = mapped_column(String(255))
    #: 规则化自动分类；只是建议，不是权限/检索范围
    subject: Mapped[Optional[str]] = mapped_column(String(50))
    material_type: Mapped[Optional[str]] = mapped_column(String(30))
    #: facet 快照：公式数 / 图片数 / 表格数 / 置信度
    facets: Mapped[Optional[dict]] = mapped_column(JSON)
    #: 软剔除范围：只影响检索/展示，不物理删除原文。
    #: [{"start": 1200, "end": 1280, "kind": "text", "reason": "...", "planId": "..."}]
    excluded_ranges: Mapped[Optional[list]] = mapped_column(JSON)
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

    #: 解析层产出的块结构提示（不给用户直接展示）：
    #: [{"blockId":"B0001","start":0,"end":10,"kind":"code","language":"python",
    #:   "confidence":0.9,"evidence":"..."}]
    #: 智能整理用它区分代码/公式/表格/答案，避免只靠正文正则误判。
    content_structure: Mapped[Optional[list]] = mapped_column(JSON)

    #: 用户给这份资料写的一句话说明（如「高二期末卷」「第四章课件」）。
    #:
    #: 为什么需要它：工作空间里的文件往往名字很随便（`新建文档(2).docx`、
    #: `扫描件001.pdf`），只靠文件名 AI 分不清哪份是用户说的「那份概率论的资料」。
    #: 用户写一句人话说明，AI 找文件时就能对上。
    #: NULL = 没写（此时 AI 只能靠文件名 + 正文内容判断）。
    user_note: Mapped[Optional[str]] = mapped_column(String(200))

    #: 来源标记：self = 用户自己的；share = 从分享领取的物理副本
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="self", server_default="self"
    )
    source_doc_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    share_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: 当前可检索的索引版本。正文更新/版本恢复时递增，旧 chunks 继续留在库里
    #: 但版本号不匹配，检索会在 SQL 层直接排除，避免重向量化期间命中旧内容。
    index_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=DOC_PENDING)
    #: 单文档检索开关：0=可检索，1=屏蔽（不参与搜索/问答；管理列表仍可见）
    disabled: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
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
    #: 该 chunk 属于文档的哪一版索引；检索时与 rag_document.index_version 对齐。
    index_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

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


class MaterialAssetUsage(Base):
    """资料资产用途账本：图片被哪些题目/笔记/文档使用过。

    `asset_key` 是稳定键：文档图片用 `doc:{docId}:{imageIndex}`，
    聊天独立图片用 `chat:{imageId}`。写入时记账，读取时聚合，
    不在题目正文里做 LIKE 反查。
    """

    __tablename__ = "material_asset_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_key", "target_type", "target_id",
                         name="uk_material_asset_usage_target"),
        Index("idx_material_asset_usage_user", "user_id"),
        Index("idx_material_asset_usage_asset", "asset_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    asset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_url: Mapped[Optional[str]] = mapped_column(String(500))
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MaterialOrganizeLog(Base):
    """资料智能整理快照：一次整理的前后字段 + 可回退批次。

    也用于文档历史版本快照：`batch_id` 以 `version:` 开头时，
    `before_json` 是保存前的完整文档快照（复用现有表，不新增独立实体）。
    """

    __tablename__ = "material_organize_log"
    __table_args__ = (
        Index("idx_material_organize_user_batch", "user_id", "batch_id"),
        Index("idx_material_organize_doc", "doc_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    before_json: Mapped[Optional[dict]] = mapped_column(JSON)
    after_json: Mapped[Optional[dict]] = mapped_column(JSON)
    undone_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MaterialOrganizePlan(Base):
    """智能整理计划：先预览、后应用，支持深度整理阶段和剔除建议。"""

    __tablename__ = "material_organize_plan"
    __table_args__ = (
        Index("idx_material_organize_plan_user", "user_id"),
        Index("idx_material_organize_plan_doc", "doc_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="deep")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    stage: Mapped[Optional[str]] = mapped_column(String(30))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base_revision: Mapped[Optional[str]] = mapped_column(String(64))
    options_json: Mapped[Optional[dict]] = mapped_column(JSON)
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON)
    summary_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_msg: Mapped[Optional[str]] = mapped_column(String(500))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


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

class RagMicroCourse(Base):
    """教学微课历史记录（每次生成保存一个版本）。

    用户再次打开同一文档时直接读取最新版本，不重复调用模型；
    用户点「重新生成」才创建新版本。HTML 与结构化 deck 都保存，
    这样既能在线演示，也能随时导出 PPT。
    """

    __tablename__ = "rag_micro_course"
    __table_args__ = (
        Index("idx_rag_micro_course_user_doc", "user_id", "doc_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), nullable=False
    )
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="教学课件")
    change_summary: Mapped[Optional[str]] = mapped_column(String(300))
    html: Mapped[str] = mapped_column(Text, nullable=False)
    deck_json: Mapped[Optional[dict]] = mapped_column(JSON)
    meta_json: Mapped[Optional[dict]] = mapped_column(JSON)
    ai_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_file_name: Mapped[Optional[str]] = mapped_column(String(255))
    generation_status: Mapped[str] = mapped_column(
        "status", String(16), nullable=False, default="ready", server_default="ready"
    )
    progress_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error_msg: Mapped[Optional[str]] = mapped_column(String(300))
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
