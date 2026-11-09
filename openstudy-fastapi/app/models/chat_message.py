"""站内私信模型（原定义在 api/v1/chat.py，P1 分层治理迁出）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(100))
    sender_nickname: Mapped[Optional[str]] = mapped_column(String(100))
    sender_avatar: Mapped[Optional[str]] = mapped_column(String(255))
    receiver_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receiver_name: Mapped[Optional[str]] = mapped_column(String(100))
    receiver_nickname: Mapped[Optional[str]] = mapped_column(String(100))
    receiver_avatar: Mapped[Optional[str]] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    is_deleted: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    hidden_by: Mapped[Optional[str]] = mapped_column(String(500))
