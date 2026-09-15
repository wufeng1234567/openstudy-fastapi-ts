"""
题库/题目模型（对齐 DB 实际 schema）

DB schema 关键点:
- 无 del_flag 字段，采用物理删除 + DB ON DELETE CASCADE 级联
- 主键列名为 id（非 bank_id/question_id/sub_id）
- question_bank: subject/description/total_questions/is_public
- question_main: question_text/content/options/answer/analysis/has_sub_questions/sort_order
- question_sub: main_id/question_text/question_type/options/answer/analysis/sort_order/score
- status='0' 表示正常
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    BigInteger, String, Integer, Text, DateTime, ForeignKey, func,
    UniqueConstraint, JSON, Numeric, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class QuestionBank(Base):
    """题库表"""
    __tablename__ = "question_bank"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(String(500))
    cover_image: Mapped[Optional[str]] = mapped_column(String(255))
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(1), default="0")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_public: Mapped[int] = mapped_column(Integer, default=0)
    # 是否允许他人复制（Fork）：0=不允许，1=允许
    allow_fork: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # 关系
    questions: Mapped[List["QuestionMain"]] = relationship(back_populates="bank", lazy="selectin")


class QuestionMain(Base):
    """题目主表"""
    __tablename__ = "question_main"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    question_type: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    question_text: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[Optional[str]] = mapped_column(Text)
    options: Mapped[Optional[dict]] = mapped_column(JSON)
    answer: Mapped[Optional[str]] = mapped_column(Text)
    analysis: Mapped[Optional[str]] = mapped_column(Text)
    has_sub_questions: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(1), nullable=False, default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    bank: Mapped["QuestionBank"] = relationship(back_populates="questions", lazy="selectin")
    sub_questions: Mapped[List["QuestionSub"]] = relationship(
        back_populates="parent", lazy="selectin",
        foreign_keys="QuestionSub.main_id",
    )


class QuestionSub(Base):
    """子题表（组合题的子题）"""
    __tablename__ = "question_sub"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    main_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_main.id"), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    options: Mapped[Optional[dict]] = mapped_column(JSON)
    answer: Mapped[str] = mapped_column(String(500), nullable=False)
    analysis: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))

    # 关系
    parent: Mapped["QuestionMain"] = relationship(
        back_populates="sub_questions", lazy="selectin",
        foreign_keys=[main_id],
    )


class UserBankFavorite(Base):
    """题库收藏表"""
    __tablename__ = "user_bank_favorite"
    __table_args__ = (
        UniqueConstraint('user_id', 'bank_id', name='uk_user_bank'),
    )

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(200))
    tags: Mapped[Optional[str]] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[int] = mapped_column(Integer, default=0)
    last_study_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    study_count: Mapped[int] = mapped_column(Integer, default=0)
    favorite_status: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserQuestionFavorite(Base):
    """题目收藏表"""
    __tablename__ = "user_question_favorite"
    __table_args__ = (
        UniqueConstraint('user_id', 'question_id', name='uk_user_question'),
    )

    favorite_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_main.id"), nullable=False)
    bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(100))
    difficulty_rating: Mapped[Optional[int]] = mapped_column(Integer)
    error_times: Mapped[int] = mapped_column(Integer, default=0)
    correct_times: Mapped[int] = mapped_column(Integer, default=0)
    last_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[int] = mapped_column(Integer, default=0)
    favorite_status: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserQuestionError(Base):
    """错题本表"""
    __tablename__ = "user_question_error"
    __table_args__ = (
        UniqueConstraint('user_id', 'question_id', name='uk_user_question'),
    )

    error_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_main.id"), nullable=False)
    bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    error_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_error_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    error_count: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(100))
    difficulty_rating: Mapped[Optional[int]] = mapped_column(Integer)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_mastered: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserQuestionMarked(Base):
    """斩题表"""
    __tablename__ = "user_question_marked"
    __table_args__ = (
        UniqueConstraint('user_id', 'question_id', name='uk_user_question'),
    )

    marked_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sys_user.user_id"), nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_main.id"), nullable=False)
    bank_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question_bank.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[str]] = mapped_column(String(100))
    marked_type: Mapped[int] = mapped_column(Integer, default=1)
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer)
    error_times_before_mark: Mapped[int] = mapped_column(Integer, default=0)
    correct_times_before_mark: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    last_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_review_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_mastered: Mapped[int] = mapped_column(Integer, default=0)
    mastery_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    marked_status: Mapped[int] = mapped_column(Integer, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    update_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class UserPracticeLog(Base):
    """答题流水表（学习行为事件表）

    设计要点：
    - **每作答一道题写一条**，是「学习行为」的唯一权威数据源。正确率、练习次数、
      学习趋势、连续学习天数等统计全部基于本表，与上面几张「状态表」区分开：
      状态表只保存「当前是什么状态」，本表保存「历史上发生过什么」。
    - 状态表（错题/斩题/收藏）的 create_time 只记录「第一次产生该状态」的时间，
      无法反映「今天重做了一道老错题」这类行为，因此不能拿来做趋势统计。
    - **刻意不加外键约束**：日志表需要独立存活。若 question_id 加 FK（MySQL 默认
      RESTRICT），删除题库/题目时会被外键拦下或把历史统计一并清空，二者都不可接受。
      代价是题目被删后会出现孤儿行，但统计只按 user_id 聚合，不受影响。
    """
    __tablename__ = "user_practice_log"
    __table_args__ = (
        Index("idx_practice_user_time", "user_id", "create_time"),
        Index("idx_practice_user_question", "user_id", "question_id"),
    )

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    question_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    bank_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    is_correct: Mapped[int] = mapped_column(Integer, default=0)  # 1=答对 0=答错
    answer: Mapped[Optional[str]] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
