"""
AI 限流违规记录模型（sys_ai_rate_limit_log 表）

每次 AI 接口触发限流（IP/用户每分钟/用户每日）写一行，
供后台「限流监控」页查询：谁在什么时候被限的、踩的哪条线、当时计数多少。
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Integer, String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SysAiRateLimitLog(Base):
    """AI 限流违规记录表"""
    __tablename__ = "sys_ai_rate_limit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    user_name: Mapped[Optional[str]] = mapped_column(String(64))
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    path: Mapped[Optional[str]] = mapped_column(String(255))
    # 触发的限制类型：ip = 每 IP 每分钟；user_min = 每用户每分钟；user_day = 每用户每日
    limit_type: Mapped[Optional[str]] = mapped_column(String(20))
    current_count: Mapped[Optional[int]] = mapped_column(Integer)
    limit_value: Mapped[Optional[int]] = mapped_column(Integer)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.now)


Index("idx_ai_rl_log_user_time", SysAiRateLimitLog.user_id, SysAiRateLimitLog.create_time)
Index("idx_ai_rl_log_ip_time", SysAiRateLimitLog.ip, SysAiRateLimitLog.create_time)
