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
