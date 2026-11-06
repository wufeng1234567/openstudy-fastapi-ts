"""资料知识网络：图片资产与统一引用。

这两张表只负责「可追溯」本身，不复制文档正文：
  · `rag_image_asset` 是图片的索引/描述缓存，原图仍然落在 `rag_document.image_map`
    或 `chat_upload_image.url`；
  · `content_reference` 只存引用关系 + 原文锚点，不复制被引用内容。

放在独立模块是为了让 `models/rag.py` 继续只表达 RAG 四表，避免把
gallery / reference 的演进绑在向量表上。`database.register_all_models()`
会统一导入它，`create_all` 自动建表。
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


class RagImageAsset(Base):
    """图片资产索引。

    `asset_key` 与 `material_asset_usage.asset_key` 完全一致：
      · 文档图片 `doc:{docId}:{seq}`
      · 聊天图片 `chat:{imageId}`

    这样「画廊搜索」「被谁引用」「插入题目/笔记」共用同一个稳定键，
    不需要再维护第二套映射表。
    """

    __tablename__ = "rag_image_asset"
    __table_args__ = (
        UniqueConstraint("user_id", "asset_key", name="uk_rag_image_asset_key"),
        Index("idx_rag_image_asset_user", "user_id"),
        Index("idx_rag_image_asset_doc", "doc_id"),
        Index("idx_rag_image_asset_status", "description_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    doc_id: Mapped[Optional[int]] = mapped_column(BigInteger)

    asset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="document")
    url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    #: 预留统一视觉语义：photo / diagram / table / formula / screenshot
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="image")

    section_index: Mapped[Optional[int]] = mapped_column(Integer)
    section_title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: 图片标记【图N】在 raw_content 里的字符位置，用于「定位原文」。
    offset: Mapped[Optional[int]] = mapped_column(Integer)
    surrounding_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keywords: Mapped[Optional[list]] = mapped_column(JSON)

    description_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    description_model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    describe_error: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    described_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


class RagImageDescribeJob(Base):
    """图片描述批量任务。

    为什么放到数据库：浏览器切到别的页面后，前端组件会被销毁；如果进度只存在
    组件内存里，回来时「生成中」就消失了。任务状态落库后，画廊重新挂载可以
    继续显示进度并轮询，不依赖原请求的生命周期。
    """

    __tablename__ = "rag_image_describe_job"
    __table_args__ = (
        Index("idx_rag_image_describe_job_user", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_asset_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    asset_keys: Mapped[Optional[list]] = mapped_column(JSON)
    error: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class ContentReference(Base):
    """统一内容引用。

    语义：
      · `source_*` = 引用是从哪里发起的（哪张图/哪份文档/哪条笔记）；
      · `target_*` = 被引用的对象（目前支持笔记、题目、文档、图片资产）。

    对「资料图片 → 笔记」这条演示链路：
        source_type=document_image, source_id=docId, source_sub_id=图片序号
        target_type=note, target_id=noteId
        quote=图片所在段落/描述，start_offset=图片标记位置

    对「题目 → 原文」沿用现有 `QuestionSource` 作为兼容层，不在这里重复写。
    """

    __tablename__ = "content_reference"
    __table_args__ = (
        Index("idx_content_reference_user", "user_id"),
        Index("idx_content_reference_target", "target_type", "target_id"),
        Index("idx_content_reference_source", "source_type", "source_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sub_id: Mapped[Optional[str]] = mapped_column(String(64))

    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    quote: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_offset: Mapped[Optional[int]] = mapped_column(Integer)
    end_offset: Mapped[Optional[int]] = mapped_column(Integer)

    created_by: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
