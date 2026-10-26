"""
英语学习模型（词书 / 单词 / 练习记录）
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class EnglishPracticeLog(Base):
    """英语练习记录（听写 / 阅读 / 识词）

    ## 为什么要有这张表

    三个英语子页面原先是**开环**的：听写关掉就忘了练到哪、阅读做完错题不留存。
    没有记录就没有"下次"，也谈不上复盘 —— 而复盘恰恰是学习产品最核心的价值。

    这张表只做一件事：**把一次练习的结果落下来**，供三处使用：
      ① 页面上的「上次练到哪」入口（`GET /words/practice/last`）；
      ② 智能体 `english_practice` 工具读出来做诊断
         （「我哪类词老错」「阅读正确率在涨吗」）；
      ③ 未来的复习计划（错词按遗忘曲线重排）。

    ## 设计取舍

    · `detail` 用 JSONB 存逐题明细，**不建第二张"逐题表"** ——
      明细只被整体读取（渲染结果页 / 算正确率），从不按单题查询；
      拆表只会让每次练习多写 N 行、多一次 join。
    · `mode` 用一个字段装三类练习：它们的字段形状完全一致
      （总题数 / 对几题 / 正确率 / 用时），拆三个表只会让统计要写三遍。
    """

    __tablename__ = "english_practice_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 归属用户
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: dictation=单词听写 / reading=阅读练习 / ocr=拍照识词
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 关联词书（阅读 / 识词可为空）
    book_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    #: 词书名 / 阅读主题（冗余存一份，列表展示不必回表 join）
    title: Mapped[Optional[str]] = mapped_column(String(255))
    #: 题量 / 总词数
    total: Mapped[int] = mapped_column(Integer, default=0)
    #: 答对 / 写对的数量
    correct: Mapped[int] = mapped_column(Integer, default=0)
    #: 正确率（0~100 整数，避免前端再算一遍导致口径不一致）
    accuracy: Mapped[int] = mapped_column(Integer, default=0)
    #: 用时（秒）
    duration: Mapped[int] = mapped_column(Integer, default=0)
    #: 逐题明细 [{"word": "abandon", "input": "abandan", "ok": false}, ...]
    detail: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, default=list)
    del_flag: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WordLearningState(Base):
    """单词记忆状态（SM-2 简化的间隔重复，2026-10-26）

    ## 为什么要有这张表

    在这之前，`words` 表只是一份**静态清单**：它知道"这个库有 42 个词"，
    不知道"哪几个我已经记住了""今天该复习哪几个"。

    结果是每次打开听写页看到的永远是同一批词、同一个起点 ——
    练完关掉，下次还得从头翻。

    ## 状态怎么流转

    算法在 `app/services/english/spaced_repetition.py`（纯函数，有 29 条用例），
    这张表只负责**存当前快照**：

        stage 0            → 新词，没练过
        stage 1 ~ 7        → 复习中，按 due_date 排期
        stage 8            → 已掌握，不再进日常队列

    每次练习提交时，`/words/practice/submit` 会按明细里的对错
    逐词更新这里的状态 —— 所以用户"刷完一批"，下一批自然就变了。

    ## 设计取舍

    · 主键 (user_id, word_id)：同一个词在不同用户下进度必须独立。
    · 只存当前状态，不存历史明细 —— 历史已经在
      `english_practice_log.detail` 里，这里再存一遍就是双写。
    · 用 `word_id` 而不是 `word` 文本：同形不同义（如 `bank`）也要分开算。
    """

    __tablename__ = "word_learning_state"

    #: 归属用户
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    #: 对应 words.word_id
    word_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    #: 复习阶段：0=新词 / 1~7=复习中 / 8=已掌握
    stage: Mapped[int] = mapped_column(SmallInteger, default=0)
    #: SM-2 难度系数 [1.3, 3.0]
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    #: 当前复习间隔（天）
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    #: 下次该复习的日期
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    #: 累计答对 / 答错
    right_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    #: 遗忘次数（记住后又答错）
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    #: 首次 / 最近练习时间
    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
