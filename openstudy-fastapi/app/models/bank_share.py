"""题库分享模型

设计说明
--------
- BankShare          分享记录（题库主 A 主动发起，带分享令牌/分享码/有效期/撤销状态）
- BankShareReceive   领取记录（用户 B 通过分享获取题库，作为「来自分享」的权威来源）

约定
----
- status: '0' = 有效 / '1' = 已撤销（接收记录的 status: '0' = 正常 / '1' = 已失效）
- 题库是否可编辑，永远取决于 question_bank.user_id（题库主），分享只授予只读
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Integer, DateTime, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BankShare(Base):
    """题库分享记录表"""
    __tablename__ = "bank_share"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bank_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    share_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    share_code: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(16), default="read")
    message: Mapped[Optional[str]] = mapped_column(String(200))
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    receive_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class BankShareReceive(Base):
    """题库分享领取记录表"""
    __tablename__ = "bank_share_receive"
    __table_args__ = (
        UniqueConstraint('share_id', 'receiver_id', name='uk_share_receiver'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    share_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    bank_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receiver_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="share")
    # '0' 正常 / '1' 已失效（分享被撤销或过期）
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
