"""定向站内通知模型

与 sys_notice（全局广播公告）不同，本表是**面向单个用户**的通知，
用于题库分享等需要精确投递的场景：
- 有人领取了你的分享  -> 通知题库主
- 你收藏的分享已失效  -> 通知领取者
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Integer, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class UserNotification(Base):
    """用户定向通知表"""
    __tablename__ = "user_notification"

    notification_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # share_receive / share_invalid / system
    notify_type: Mapped[str] = mapped_column(String(32), default="system")
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    # 点击跳转路径，如 /front/questionPractice/12?from=myLearning
    link: Mapped[Optional[str]] = mapped_column(String(255))
    is_read: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
