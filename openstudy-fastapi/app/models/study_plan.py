"""学习建议快照（历史记录）。

只存“建议快照”，不存任务、完成态或每日计划。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StudyPlanSnapshot(Base):
    __tablename__ = "study_plan_snapshot"
    __table_args__ = (
        Index("idx_sps_user_created", "user_id", "deleted", "create_time"),
        Index("idx_sps_user_kb", "user_id", "kb_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    title: Mapped[str] = mapped_column(String(160), nullable=False, default="", server_default="")
    scope_json: Mapped[Optional[dict]] = mapped_column(JSON)
    advice_json: Mapped[Optional[dict]] = mapped_column(JSON)
    trace_json: Mapped[Optional[dict]] = mapped_column(JSON)
    graph_json: Mapped[Optional[dict]] = mapped_column(JSON)
    parent_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="page", server_default="page")
    pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)


__all__ = ["StudyPlanSnapshot"]
