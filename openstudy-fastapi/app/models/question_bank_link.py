"""题库与资料夹的逻辑关联（不复制题目，不物理上传）。

题库仍然只存在 `question_bank` 一张事实表里；这里是资料夹侧的引用关系，
知识图谱构建时根据这张表决定当前资料夹可以读取哪些题库的知识点。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QuestionBankKbLink(Base):
    __tablename__ = "question_bank_kb_link"
    __table_args__ = (
        UniqueConstraint("user_id", "kb_id", "bank_id", name="uk_qb_kb_link"),
        Index("idx_qb_kb_link_user_kb", "user_id", "kb_id"),
        Index("idx_qb_kb_link_bank", "bank_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
