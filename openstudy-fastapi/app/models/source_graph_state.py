"""资料夹来源实体集处理状态（增量更新用）。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceGraphState(Base):
    __tablename__ = "source_graph_state"
    __table_args__ = (
        UniqueConstraint("user_id", "kb_id", "source_type", "source_id", name="uk_source_graph_state"),
        Index("idx_source_graph_state_kb", "user_id", "kb_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    entity_set_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error: Mapped[str] = mapped_column(String(480), nullable=False, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
