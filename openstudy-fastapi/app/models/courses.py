"""
课程模型
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Course(Base):
    """课程表"""
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    course_description: Mapped[Optional[str]] = mapped_column(Text)
    cover_image: Mapped[Optional[str]] = mapped_column(String(500))
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(1), default="0")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
