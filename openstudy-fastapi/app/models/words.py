"""
英语学习模型（词书/单词）
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import BigInteger, String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WordBook(Base):
    """词书表"""
    __tablename__ = "word_books"

    book_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户；NULL = 系统预置词书（所有登录用户只读可见，不可改删）
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    book_name: Mapped[str] = mapped_column(String(255), nullable=False)
    book_description: Mapped[Optional[str]] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    cover_image: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(1), default="0")
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    words: Mapped[List["Word"]] = relationship(back_populates="book", lazy="selectin")


class Word(Base):
    """单词表"""
    __tablename__ = "words"

    word_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("word_books.book_id"), nullable=False)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    phonetic: Mapped[Optional[str]] = mapped_column(String(100))
    translation: Mapped[Optional[str]] = mapped_column(Text)
    example: Mapped[Optional[str]] = mapped_column(Text)
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    book: Mapped["WordBook"] = relationship(back_populates="words", lazy="selectin")
