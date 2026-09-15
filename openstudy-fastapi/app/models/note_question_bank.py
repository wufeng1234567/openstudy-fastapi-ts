"""笔记-题库关联模型"""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class NoteQuestionBank(Base):
    """笔记-题库关联表"""
    __tablename__ = "note_question_bank"
    __table_args__ = (
        UniqueConstraint('note_id', 'question_bank_id', name='uk_note_bank'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    note_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("note.note_id"), nullable=False)
    question_bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
