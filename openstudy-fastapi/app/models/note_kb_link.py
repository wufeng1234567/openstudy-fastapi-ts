"""笔记与资料夹的逻辑关联（不复制笔记正文）。

笔记仍是 `note` 表里的事实数据；`note_kb_link` 只记录用户 / 资料夹 / 笔记
三元组，供资料夹知识图谱按来源读取笔记并抽知识点。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NoteKbLink(Base):
    __tablename__ = "note_kb_link"
    __table_args__ = (
        UniqueConstraint("user_id", "kb_id", "note_id", name="uk_note_kb_link"),
        Index("idx_note_kb_link_user_kb", "user_id", "kb_id"),
        Index("idx_note_kb_link_note", "note_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
