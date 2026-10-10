"""
笔记模型
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, Text, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Note(Base):
    """笔记表"""
    __tablename__ = "note"

    note_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    # 库列为 NOT NULL（SpringBoot 迁移遗留），应用层必须在建笔记时校验/补默认分类
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("note_category.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # 兼容库中既有结构：note.filename 为 NOT NULL 且无默认值（SpringBoot 迁移遗留列）
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    content: Mapped[Optional[str]] = mapped_column(Text)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(500))
    public_section_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    cover_image: Mapped[Optional[str]] = mapped_column(String(500))
    # 库列为 tinyint(1)：前端传的是数字 1/0，且用 `isPublic === 1` 判断
    is_public: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    # 库列为 varchar(20) default 'draft'；前端只识别 draft/published，
    # 此前的 default="0" 会覆盖库默认值，导致前端状态列空白
    status: Mapped[str] = mapped_column(String(20), default="draft")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关系
    category: Mapped[Optional["NoteCategory"]] = relationship(back_populates="notes", lazy="selectin")
    comments: Mapped[List["NoteComment"]] = relationship(back_populates="note", lazy="selectin")


class NoteCategory(Base):
    """笔记分类表"""
    __tablename__ = "note_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    notes: Mapped[List["Note"]] = relationship(back_populates="category", lazy="selectin")


class NoteComment(Base):
    """笔记评论表"""
    __tablename__ = "note_comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("note.note_id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    reply_to_user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    status: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    note: Mapped["Note"] = relationship(back_populates="comments", lazy="selectin")


class UserNoteFavorite(Base):
    """笔记收藏表"""
    __tablename__ = "user_note_favorite"
    __table_args__ = (
        UniqueConstraint('user_id', 'note_id', name='uk_user_note_favorite'),
    )

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    note_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("note.note_id"), nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NotePublicSection(Base):
    """笔记公开分区表

    此前只被 `api/v1/notes.py` 的一处裸 SQL 读取，没有 ORM 模型 —— 在 MySQL 上
    因为表早已存在所以没暴露问题，但迁移到全新的 PostgreSQL 库后该表不会被
    `create_all` 建出来，接口会直接报 relation does not exist。这里补上模型。
    """
    __tablename__ = "note_public_section"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())


class UserNoteDraft(Base):
    """用户「写笔记」草稿（用户 2026-10-11：智能体要能真正写进系统草稿）

    ⚠️ **这不是一篇笔记**：它没有 `note_id`、不在「我的笔记」列表里、随时可被覆盖/丢弃。
    与 `note` 表里 `status='draft'` 的**正式笔记**是两回事（后者已落库、有 noteId、列表可见）。

    设计：**一个用户至多一篇草稿**（`user_id` 既是主键也是归属）。前端「写笔记」页加载时
    把本表草稿与浏览器 localStorage 草稿合并（谁新用谁）；智能体 `note_manage.save_draft`
    写入本表（不建 note 行）；发布笔记成功后清空。
    """
    __tablename__ = "user_note_draft"

    #: 用户维度：一个用户一行
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id"), primary_key=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(255))
    #: 正文：与 note 一致，content 与 markdown_content 互补（见 note_write_service.create_note）
    content: Mapped[Optional[str]] = mapped_column(Text)
    markdown_content: Mapped[Optional[str]] = mapped_column(Text)
    category_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    tags: Mapped[Optional[str]] = mapped_column(String(500))
    #: 1=公开 / 0=私密（与 note 同口径，**与题库相反**）
    is_public: Mapped[int] = mapped_column(Integer, default=1)
    public_section_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
