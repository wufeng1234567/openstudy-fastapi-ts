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
