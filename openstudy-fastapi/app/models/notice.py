"""
通知公告模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SysNotice(Base):
    """通知公告表"""
    __tablename__ = "sys_notice"

    notice_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    notice_title: Mapped[str] = mapped_column(String(50), nullable=False)
    notice_type: Mapped[str] = mapped_column(String(1), nullable=False)
    notice_content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(64), default="")
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(String(255))


class SysNoticeRead(Base):
    """用户已读公告记录表"""
    __tablename__ = "sys_notice_read"
    __table_args__ = (
        UniqueConstraint('user_id', 'notice_id', name='uk_user_notice'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    notice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_notice.notice_id"), nullable=False)
    read_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SysNoticeDelete(Base):
    """用户「删除」公告记录表（**按用户隐藏**，不真删 sys_notice 行）

    为什么需要这张表：
    - `sys_notice` 里有两类行：**用户通知**（remark.toUserId 指向唯一接收者）与
      **系统公告**（无 toUserId，全体共用一行）。
    - 用户通知可安全**真删行**（只影响接收者本人）。
    - 系统公告是**全局共享行**，任何单个用户「清空/删除」都**绝不能**删 sys_notice 行
      —— 否则会把这则公告从所有人的列表、乃至管理员后台里一并抹掉（越权破坏）。
      正确做法是「对当前用户隐藏」：在此表记一条 (user_id, notice_id)，
      列表查询时排除「当前用户已删」的行；其它用户不受影响。

    与 `sys_notice_read` 的区别：read=已读（仍显示，仅去红点），delete=已删（从列表隐藏）。
    """
    __tablename__ = "sys_notice_delete"
    __table_args__ = (
        UniqueConstraint('user_id', 'notice_id', name='uk_user_notice_delete'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    notice_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_notice.notice_id"), nullable=False)
    delete_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
