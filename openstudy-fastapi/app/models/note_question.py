"""笔记-题目关联模型"""
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class NoteQuestion(Base):
    """笔记-题目关联表

    ⚠️ 与库表结构对齐：note_question 表没有 question_bank_id 列（该信息在
    note_question_bank 表中维护），实际列是 relation_type（默认 'cited'）。
    此前 ORM 多声明了 question_bank_id，导致所有走 ORM 的关联读写
    全部报 1054 Unknown column，接口 100% 返回 500。
    """
    __tablename__ = "note_question"
    __table_args__ = (
        # 关联按用户隔离：作者与收藏者各维护自己的关联，唯一键必须带 user_id。
        UniqueConstraint('note_id', 'question_id', 'user_id', name='uk_note_question_user'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("note.note_id"), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_main.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    relation_type: Mapped[Optional[str]] = mapped_column(String(32), default="cited")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
