"""
系统配置模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SysConfig(Base):
    """系统配置表"""
    __tablename__ = "sys_config"

    config_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_name: Mapped[Optional[str]] = mapped_column(String(100))
    config_key: Mapped[Optional[str]] = mapped_column(String(100))
    config_value: Mapped[Optional[str]] = mapped_column(String(500))
    config_type: Mapped[str] = mapped_column(String(1), default="N")
    create_by: Mapped[Optional[str]] = mapped_column(String(64))
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    update_by: Mapped[Optional[str]] = mapped_column(String(64))
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    remark: Mapped[Optional[str]] = mapped_column(String(500))
