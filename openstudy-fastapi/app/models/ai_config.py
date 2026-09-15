"""
AI 模型配置模型（sys_ai_config 表）
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, SmallInteger, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SysAiConfig(Base):
    """AI 模型配置表"""
    __tablename__ = "sys_ai_config"

    config_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(50))
    provider_name: Mapped[Optional[str]] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    api_key: Mapped[Optional[str]] = mapped_column(String(500))
    base_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_default: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_enabled: Mapped[int] = mapped_column(SmallInteger, default=1)
    status: Mapped[Optional[str]] = mapped_column(String(1), default="0")
    remark: Mapped[Optional[str]] = mapped_column(String(500))
    thinking_mode: Mapped[Optional[str]] = mapped_column(String(20))
    reasoning_effort: Mapped[Optional[str]] = mapped_column(String(20))
    context_length: Mapped[Optional[str]] = mapped_column(String(20))
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_by: Mapped[Optional[str]] = mapped_column(String(64))
    update_by: Mapped[Optional[str]] = mapped_column(String(64))
