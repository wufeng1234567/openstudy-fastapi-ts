"""
学情诊断引擎 —— 「从报数字到下诊断」

为什么要重做（2026-10-20，用户口径）
====================================
原来的「学情分析」是**五个聚合数字**（总览 / 按科目 / 趋势 / 错题分析 / 成长），
LLM 拿到它们之后只能做一件事：把数字翻译成一句人话。所以用户看到的永远是

    「你一共做了 254 道题，正确率 53.5%，有 40 道错题」

—— 这句话**任何**接了大模型的题库产品都能说，因为它是聚合数字的复述。用户的原话：
「好像目前只能做到 llm 自己拿到数据分析一下 然后发给用户就没了 感觉没什么新颖的地方」。

真正的缺口是：**系统手里有逐题作答流水，却只用了它的总和。**
`user_practice_log` 每作答一次写一条，它记录的是「哪道题、第几次、对还是错、什么时候」。
把这四次信息按题聚合，就能算出一批**聚合数字表达不了**的东西：

    · 这道题你做了 12 次、只对 2 次      → 不是"没掌握"，是**前置知识缺失**
                                            再刷它没有用，要回去补基础
    · 这道题你连续对了 4 次              → 其实**已经会了**，却还占着错题本的注意力
    · 这道题上次做错是 23 天前          → **欠复习**，而且已经过了该复习的窗口
    · 这道题 9 次全错                    → **反复失败**，需要人介入而不是继续练

这些结论**不是大模型推理出来的，是确定性算出来的** —— 同一份数据永远得到同一个结论，
可复现、可测试、可解释。LLM 在这套设计里的职责变成「把诊断结果讲成人话并给出建议」，
而不是「看着几个数字自由发挥」。这是本模块与原 `learning_stats` 最根本的分工差异。

⚠️ 本模块**不重写**原有五个统计的 SQL
=====================================
`user_stats_service` 那五个函数仍然服务着「学习统计」页面，用户在那里看到的数字
与 Agent 报出来的必须一模一样（见该模块 docstring 的说明）。本模块是**增量**：
它读的是同一张 `user_practice_log`，但看的是**逐题序列**而不是聚合值。

⚠️ 两列「死结构」被本模块救活
=============================
`user_question_error.next_review_time` 与 `review_count` 在库里**一直有列、一直被写
无意义的值**（`review_count` 恒为 0、`next_review_time` 恒为 NULL —— 2026-10-20 实测
user 105 的 40 条错题全部如此）。原因是：**没有任何地方计算过复习计划**。它们当初是为
间隔重复留的位，但从没接上算法。

本模块做两件事，职责分开：
  · `diagnose(...)`        —— 只读。算出每道题的诊断 + 建议的复习间隔。
  · `persist_plan(...)`    —— 写。把算出来的 `next_review_time` / `review_count` 落库，
                              让「今天该复习哪几道」从此可查询、可筛选。
只读与写刻意分成两个函数：诊断要能在任何地方随便调（包括渲染报告），
而写库必须由用户显式触发（见 `learning_stats` 工具的 `plan_review` action）。

间隔重复的算法（为什么是「观察式」而不是「排程式」）
==================================================
经典的 SM-2 / Anki 是**排程式**：系统给一个 due date，用户按日期复习，系统再调整。
我们没有那个前提 —— 用户的复习是自由的（他什么时候想刷就刷），系统从来没有排过期。
所以本模块用**观察式**：从**已经发生的作答序列**反推「他现在的记忆稳定到什么程度」，
再据此给一个建议间隔。

    连续正确 0 次（最近一次做错） → 明天就该再练（间隔 0 天）
    连续正确 1 次                 → 1 天
    连续正确 2 次                 → 3 天
    连续正确 3 次                 → 7 天
    连续正确 4 次                 → 16 天
    连续正确 ≥5 次                → 35 天

这条曲线是 2 倍左右的指数增长（1/3/7/16/35），与间隔重复的经验值同量级，但**只依赖
可观测的事实**（连续对了几次），不假装系统知道一条用户从没走过的排程。
准确率作为修正项：准确率越低，间隔按比例缩短（见 `_due_window_days`）。

⚠️ 为什么不用「最后一次作答时间」当复习起点
==========================================
`waiting_days = 今天 - 最后一次作答`。但「最后一次作答」可能是**做对**的那次 ——
做对之后再等 35 天是合理的；做错之后再等 35 天是灾难。所以起点取
`最后一次**做错**的时间`（若之后没有做对过）或 `最后一次作答时间`（若最后一次是对）。
判据收在 `_review_anchor(...)` 一处，别在别处再算一遍。

⚠️ 边界
=======
· **只统计真实作答**：`user_practice_log` 是唯一权威源（见 `models/question.py` 的说明）。
  错题表的 `error_count` 是「做错次数」，不含做对的那几次 —— 拿它算准确率会偏高。
· **180 天窗口**：超过半年的作答不再参与「记忆稳定度」判断（那么久以前的对错，
  对今天的记忆强度没有参考价值），但**仍然参与总量统计**（总量属于历史事实）。
· **空数据必须说「没有数据」**：用户还没做过题时，返回 `hasData=False` 与一句
  可执行的引导，而不是给一堆 0 让他以为系统坏了（见 `_empty_diagnosis`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import (
    QuestionBank,
    QuestionMain,
    UserPracticeLog,
    UserQuestionError,
)

#: 「记忆稳定度」的回看窗口（天）。
#: 超出这个窗口的作答仍进总量，但不再用来判断「现在还记得多少」——
#: 半年前做对过一次，推不出今天还记得。
MEMORY_WINDOW_DAYS = 180

#: 单次诊断最多回看多少条作答流水。
#: 不是性能上限，是**防爆**上限：真有用户刷十万道时，诊断本身要几秒才能算完，
#: 而他要的是「今天该复习什么」。超过就只看最近的（`ORDER BY create_time DESC`），
#: 结论仍然成立 —— 记忆判断本来就只该用近期数据。
MAX_LOG_ROWS = 20000

#: 连续正确次数 → 建议复习间隔（天）。
#:
#: ⚠️ 键是「从最近一次作答往回数，连续答对了几次」（`streak`）。最近一次做错 → 0。
#:    值是「**从最后一次作答算起**，隔多少天该再练一次」。
#:    这条曲线是 2 倍指数增长，与间隔重复的经验量级一致；刻意保持**整数、可解释**，
#:    因为它的值会直接出现在用户看的报告里（"建议 3 天后复习"），
#:    而一个算出来的 `2.7183 天` 只会让人怀疑系统。
_STREAK_INTERVAL_DAYS: Tuple[Tuple[int, int], ...] = (
    (0, 0),
    (1, 1),
    (2, 3),
    (3, 7),
    (4, 16),
)

#: 连续正确 ≥5 次时的间隔（曲线封顶）
_STREAK_MAX_INTERVAL_DAYS = 35

#: 诊断分档（`level`）→ 给人看的中文
#:
#: ⚠️ 取值域是**稳定的机器码**，中文只在渲染时映射 —— 与 `rollback_service.REASON_TEXT`
#:    同一条规则（把中文写进返回值，改一次文案就要改前端判断）。
LEVEL_TEXT: Dict[str, str] = {
    "repeated_failure": "反复失守",     # 做了多次、几乎没对过 → 缺前置
    "lapsing": "一做就错",             # 稳定在低准确率 → 需要换学法
    "overdue": "欠复习",               # 会，但已经过了该复习的窗口
    "due_soon": "该复习了",            # 快到期
    "on_track": "稳步推进",            # 在计划内
    "mastered": "可以毕业",            # 连续答对够多 → 应从错题本归档
    "fresh": "刚接触",                 # 只做过一两次，还看不出趋势
}

#: 分档的**优先级**（数字越小越该先处理）—— 报告按它排序
LEVEL_PRIORITY: Dict[str, int] = {
    "repeated_failure": 0,
    "lapsing": 1,
    "overdue": 2,
    "due_soon": 3,
    "on_track": 4,
    "mastered": 5,
    "fresh": 6,
}

#: 「反复失守」的判据：至少做了这么多次，且准确率低于阈值
REPEATED_FAILURE_MIN_ATTEMPTS = 3
REPEATED_FAILURE_MAX_ACCURACY = 0.34

#: 「一做就错」的判据：至少做了这么多次，准确率低于阈值
LAPSING_MIN_ATTEMPTS = 3
LAPSING_MAX_ACCURACY = 0.6

#: 「可以毕业」的判据：连续答对的次数
MASTERED_MIN_STREAK = 3

#: 报告里每类最多列几道题（够用即可，多了没人看）
MAX_ITEMS_PER_LEVEL = 8


# ---------------------------------------------------------------------------
# 数据形状
# ---------------------------------------------------------------------------


@dataclass
class _Attempt:
    """一条作答流水（只取诊断需要的四列）"""

    question_id: int
    is_correct: bool
    create_time: datetime
    bank_id: Optional[int]


@dataclass
class _QuestionHistory:
    """一道题的**完整作答序列**（已按时间升序）"""

    question_id: int
    bank_id: Optional[int]
    attempts: List[_Attempt] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.attempts)

    @property
    def correct(self) -> int:
        return sum(1 for a in self.attempts if a.is_correct)

    @property
    def accuracy(self) -> float:
        return (self.correct / self.total) if self.total else 0.0

    @property
    def first_time(self) -> Optional[datetime]:
        return self.attempts[0].create_time if self.attempts else None

    @property
    def last_time(self) -> Optional[datetime]:
        return self.attempts[-1].create_time if self.attempts else None

    @property
    def last_wrong_time(self) -> Optional[datetime]:
        for a in reversed(self.attempts):
            if not a.is_correct:
                return a.create_time
        return None

    @property
    def last_correct_time(self) -> Optional[datetime]:
        for a in reversed(self.attempts):
            if a.is_correct:
                return a.create_time
        return None

    @property
    def streak(self) -> int:
        """从最近一次作答往回数，连续答对了几次（最近一次错 → 0）"""
        n = 0
        for a in reversed(self.attempts):
            if a.is_correct:
                n += 1
            else:
                break
        return n


# ---------------------------------------------------------------------------
# 算法核心（纯函数，不碰数据库 —— 便于单测与在报告里复用）
# ---------------------------------------------------------------------------


def _due_window_days(streak: int, accuracy: float) -> int:
    """按「连续正确次数」给出建议的复习间隔（天）

    准确率作为修正项：整体准确率低的题，即使最近连对几次，也不该按满额间隔放走 ——
    那更可能是「刚好碰到会做的」，而不是真的稳了。

    Args:
        streak: 连续答对次数（0 = 最近一次做错）。
        accuracy: 该题历史准确率（0~1）。

    Returns:
        间隔天数（>=0）。0 表示「明天就该再练」。
    """
    interval = _STREAK_MAX_INTERVAL_DAYS
    for need, days in reversed(_STREAK_INTERVAL_DAYS):
        if streak >= need:
            interval = days
            break

    # 准确率修正：低于 50% 打对折，低于 70% 打七折。只在「有间隔可缩」时才缩。
    if interval > 0:
        if accuracy < 0.5:
            interval = max(1, round(interval * 0.5))
        elif accuracy < 0.7:
            interval = max(1, round(interval * 0.7))
    return interval


def _review_anchor(history: _QuestionHistory) -> Optional[datetime]:
    """复习计时从哪一刻起算

    ⚠️ 不能一律用「最后一次作答」：做对之后等 35 天是合理的，做错之后等 35 天是灾难。
    所以——若最后一次是**错的**，起点就是那次错（间隔会很小，很快被判定欠复习）；
    若最后一次是**对的**，起点仍用最后一次作答（此时 streak >= 1，间隔本来就短）。

    实现上直接用 `last_time`（最后一次作答），因为「最后一次是错的」时
    `last_time == last_wrong_time`，两者等价。单独写这个函数是为了把**语义**说清：
    将来若要改成「从最后一次做错起算」，只改这里。
    """
    return history.last_time


def _days_between(later: datetime, earlier: datetime) -> int:
    """两个时间相差几个**整天**（向下取整，负数归零）"""
    delta = later - earlier
    return max(0, delta.days)


def _classify(
    history: _QuestionHistory, *, now: datetime
) -> Tuple[str, int, int]:
    """给一道题分档

    Returns:
        `(level, overdue_days, due_in_days)`
        · `level` 取值域见 `LEVEL_TEXT`
        · `overdue_days` 已经超出复习窗口多少天（>0 = 欠复习）
        · `due_in_days` 距离建议的复习日期还有几天（负数 = 已过期）
    """
    streak = history.streak
    accuracy = history.accuracy
    total = history.total

    # 只做过一两次：还看不出趋势，不该被诊断吓到（也不能被判定成"已掌握"）
    if total < 2:
        return "fresh", 0, 0

    # 反复失守：做了不少次、几乎没对过 —— 这不是"再练练"，是缺前置
    if (
        total >= REPEATED_FAILURE_MIN_ATTEMPTS
        and accuracy <= REPEATED_FAILURE_MAX_ACCURACY
    ):
        return "repeated_failure", 0, 0

    # 一做就错：稳定低准确率
    if total >= LAPSING_MIN_ATTEMPTS and accuracy <= LAPSING_MAX_ACCURACY:
        return "lapsing", 0, 0

    # 可以毕业：连续答对够多 —— 与「欠复习」互斥，毕业优先
    # （连对 3 次以上还在错题本里，那更该归档，而不是催他复习）
    if streak >= MASTERED_MIN_STREAK:
        return "mastered", 0, 0

    anchor = _review_anchor(history)
    if anchor is None:
        return "fresh", 0, 0

    window = _due_window_days(streak, accuracy)
    waited = _days_between(now, anchor)
    due_in = window - waited
    if due_in < 0:
        return "overdue", -due_in, due_in
    if due_in == 0:
        return "due_soon", 0, due_in
    return "on_track", 0, due_in


def _priority_score(
    *, level: str, history: _QuestionHistory, overdue_days: int
) -> float:
    """报告里的排序分（越大越该先处理）

    由三样东西合成，都是**可观测的事实**，没有拍出来的权重魔法：
      · 分档优先级（反复失守 > 一做就错 > 欠复习 > …）
      · 欠复习了多少天（拖得越久越优先）
      · 错误次数与准确率（错得多的优先）

    刻意做成「分档优先 + 同类内按紧急度」两层，而不是一个混合大分数：
    这样报告读起来是「先看这 3 道反复失守，再看这 5 道欠复习」，
    而不是一串让人不知道为什么排第一的数字。
    """
    base = (10 - LEVEL_PRIORITY.get(level, 9)) * 1000.0
    urgency = overdue_days * 2.0
    wrong_weight = (history.total - history.correct) * 3.0
    accuracy_weight = (1.0 - history.accuracy) * 20.0
    return base + urgency + wrong_weight + accuracy_weight


def _advice(level: str, history: _QuestionHistory, overdue_days: int) -> str:
    """按分档给一句**具体**建议（不是"继续加油"这类废话）

    ⚠️ 这些中文会进报告也给模型看，模型可以改写措辞，但**不要**改判断 ——
    判断是算出来的，措辞是可以变的。
    """
    streak = history.streak
    if level == "repeated_failure":
        return (
            f"做了 {history.total} 次只对了 {history.correct} 次 —— "
            "反复失守通常不是「再刷几遍」能解决的，多半是缺前置知识。"
            "建议先看这道题的解析和相关概念，再来练它"
        )
    if level == "lapsing":
        return (
            f"做了 {history.total} 次、准确率 {round(history.accuracy * 100)}% —— "
            "稳定在低准确率，说明现在这种方法没奏效，换个学法（看解析 / 找同类题对比）"
        )
    if level == "overdue":
        return (
            f"上一次做错是 {overdue_days} 天前，已经超出建议的复习间隔 —— "
            "现在最该先练的是它"
        )
    if level == "due_soon":
        return "到了该复习的时间点，趁现在还记得住练一遍，效果最好"
    if level == "mastered":
        return (
            f"已经连续答对 {streak} 次 —— 这道题其实会了，"
            "可以从错题本归档，别让它继续占你的注意力"
        )
    if level == "fresh":
        return "只做过一两次，还看不出掌握程度，多练几遍再判断"
    return "在计划内，按正常节奏继续即可"


# ---------------------------------------------------------------------------
# 数据库读取
# ---------------------------------------------------------------------------


async def load_histories(
    db: AsyncSession, user_id: int, *, now: Optional[datetime] = None
) -> Dict[int, _QuestionHistory]:
    """读出该用户**逐题作答序列**（按题聚合、按时间升序）

    ⚠️ 一次查询取回全部流水再在内存里分组，而不是「每道题查一次」：
    后者是 N+1（一个用户几十道错题就是几十次往返）。本查询带 `LIMIT`（`MAX_LOG_ROWS`），
    按 `create_time DESC` 取最近的，再反转成升序 —— 超量时丢的是**最旧**的流水，
    而记忆判断本来就只该用近期数据。
    """
    moment = now or datetime.now()
    since = moment - timedelta(days=MEMORY_WINDOW_DAYS)

    rows = (
        await db.execute(
            select(
                UserPracticeLog.question_id,
                UserPracticeLog.bank_id,
                UserPracticeLog.is_correct,
                UserPracticeLog.create_time,
            )
            .where(
                UserPracticeLog.user_id == int(user_id),
                UserPracticeLog.create_time >= since,
            )
            .order_by(UserPracticeLog.create_time.desc())
            .limit(MAX_LOG_ROWS)
        )
    ).all()

    out: Dict[int, _QuestionHistory] = {}
    # 取到的是「新 → 旧」，反转后按时间升序追加，保证 streak / last_* 的语义正确
    for question_id, bank_id, is_correct, create_time in reversed(rows):
        qid = int(question_id)
        hist = out.get(qid)
        if hist is None:
            hist = out[qid] = _QuestionHistory(question_id=qid, bank_id=bank_id)
        hist.attempts.append(
            _Attempt(
                question_id=qid,
                is_correct=bool(is_correct),
                create_time=create_time,
                bank_id=bank_id,
            )
        )
    return out


async def load_question_meta(
    db: AsyncSession, question_ids: Sequence[int]
) -> Dict[int, Dict[str, Any]]:
    """取题目 + 题库的展示信息（题干 / 题库名 / 科目），供报告渲染

    ⚠️ `question_main` 可能已被物理删除（流水表刻意不加外键，见 `models/question.py`），
    所以查不到的题**不能报错**，返回空 dict 即可 —— 报告里退化成「题目已删除」。
    """
    ids = [int(i) for i in question_ids if i is not None]
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(
                QuestionMain.id,
                QuestionMain.question_text,
                QuestionMain.question_type,
                QuestionMain.difficulty,
                QuestionBank.bank_name,
                QuestionBank.subject,
            )
            .join(QuestionBank, QuestionBank.id == QuestionMain.bank_id)
            .where(QuestionMain.id.in_(ids))
        )
    ).all()
    out: Dict[int, Dict[str, Any]] = {}
    for (
        qid,
        question_text,
        question_type,
        difficulty,
        bank_name,
        subject,
    ) in rows:
        out[int(qid)] = {
            "questionId": int(qid),
            "questionText": (question_text or "").strip(),
            "questionType": question_type,
            "difficulty": difficulty,
            "bankName": bank_name or "",
            "subject": subject or "未分类",
        }
    return out


async def load_error_flags(
    db: AsyncSession, user_id: int
) -> Dict[int, Dict[str, Any]]:
    """取该用户「错题本」里的状态（是否仍在册 / 是否已掌握 / 记错次数）

    诊断要用它回答一个很实际的问题：**这道题我明明会了，为什么还占着错题本？**
    """
    rows = (
        await db.execute(
            select(
                UserQuestionError.question_id,
                UserQuestionError.is_mastered,
                UserQuestionError.status,
                UserQuestionError.error_count,
                UserQuestionError.next_review_time,
                UserQuestionError.review_count,
            ).where(UserQuestionError.user_id == int(user_id))
        )
    ).all()
    return {
        int(r[0]): {
            "isMastered": bool(r[1]),
            "status": int(r[2] or 0),
            "errorCount": int(r[3] or 0),
            "nextReviewTime": r[4],
            "reviewCount": int(r[5] or 0),
        }
        for r in rows
    }


async def load_recent_activity(
    db: AsyncSession, user_id: int, *, days: int = 30, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """最近 N 天的**学习节奏**（哪天练了、练了多少、对了多少）

    为什么要它：连续学习天数只能回答「有没有断」，回答不了「是不是突击」。
    一个 20 天里集中在 3 天刷完 200 道的用户，和一个每天稳定 10 道的用户，
    连续天数可能一样，但学情完全不同 —— 后者才是真的在学。
    """
    moment = now or datetime.now()
    since = moment - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                func.date(UserPracticeLog.create_time).label("d"),
                func.count(UserPracticeLog.log_id),
                func.coalesce(func.sum(UserPracticeLog.is_correct), 0),
            )
            .where(
                UserPracticeLog.user_id == int(user_id),
                UserPracticeLog.create_time >= since,
            )
            .group_by(func.date(UserPracticeLog.create_time))
            .order_by(func.date(UserPracticeLog.create_time))
        )
    ).all()

    daily = [
        {
            "date": str(d),
            "practiceCount": int(total or 0),
            "correctCount": int(correct or 0),
        }
        for d, total, correct in rows
    ]
    active_days = len(daily)
    total_count = sum(d["practiceCount"] for d in daily)
    peak = max((d["practiceCount"] for d in daily), default=0)
    average = (total_count / active_days) if active_days else 0.0

    # 突击判据：最高一天的量超过「活跃日均」的 2.5 倍，且活跃天数不多
    # （不是精确科学，是给用户一个「你是不是最近才突击」的提示，宁宽不严）
    burst = bool(active_days >= 1 and peak >= 30 and average > 0 and peak >= average * 2.5)

    return {
        "windowDays": days,
        "activeDays": active_days,
        "totalPractice": total_count,
        "averagePerActiveDay": round(average, 1),
        "peakDayCount": peak,
        "looksLikeBurst": burst,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# 对外：诊断
# ---------------------------------------------------------------------------


def _empty_diagnosis(now: datetime) -> Dict[str, Any]:
    """没有任何作答记录时的返回

    ⚠️ 必须与「有数据但都很好」区分开：给一堆 0 会让用户以为系统坏了，
    而一句可执行的引导（"先去练几道"）才是他需要的东西。
    """
    return {
        "hasData": False,
        "generatedAt": now.isoformat(timespec="seconds"),
        "summary": {
            "questionsSeen": 0,
            "totalAttempts": 0,
            "overallAccuracy": 0.0,
            "needsAttention": 0,
            "canArchive": 0,
            "overdueCount": 0,
        },
        "items": [],
        "byLevel": {},
        "bySubject": [],
        "activity": {},
        "headline": "还没有作答记录 —— 先去题库里练几道，这里就会有诊断结果了",
        "suggestions": ["挑一个题库开始练习，做够 10 道就能看出趋势"],
    }


async def diagnose(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = MAX_ITEMS_PER_LEVEL,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """算出该用户的**学情诊断**（只读，不写库）

    Args:
        limit: 每类（分档）最多返回几道题。
        now: 当前时间（测试可注入，避免跨天抖动）。

    Returns:
        结构化诊断：逐题诊断 + 分档汇总 + 学科分布 + 学习节奏 + 建议。
        `items` 已按「该先处理谁」排好序。

    ⚠️ 返回值**不含任何 LLM 生成的内容** —— 全是算出来的。LLM 在上层拿到它之后
    只负责表达。
    """
    moment = now or datetime.now()
    limit = max(1, min(int(limit or MAX_ITEMS_PER_LEVEL), 50))

    histories = await load_histories(db, user_id, now=moment)
    if not histories:
        return _empty_diagnosis(moment)

    meta = await load_question_meta(db, list(histories.keys()))
    flags = await load_error_flags(db, user_id)

    items: List[Dict[str, Any]] = []
    by_level: Dict[str, int] = {}
    subject_agg: Dict[str, Dict[str, Any]] = {}

    for qid, hist in histories.items():
        level, overdue_days, due_in_days = _classify(hist, now=moment)
        by_level[level] = by_level.get(level, 0) + 1

        info = meta.get(qid) or {}
        subject = info.get("subject") or "未分类"
        agg = subject_agg.setdefault(
            subject,
            {"subject": subject, "questions": 0, "attempts": 0, "correct": 0},
        )
        agg["questions"] += 1
        agg["attempts"] += hist.total
        agg["correct"] += hist.correct

        flag = flags.get(qid) or {}
        text = (info.get("questionText") or "").strip()
        if len(text) > 120:
            text = text[:120] + "…"

        items.append(
            {
                "questionId": qid,
                "bankName": info.get("bankName") or "",
                "subject": subject,
                "questionText": text or "（题目内容已不可用，可能已被删除）",
                "questionType": info.get("questionType"),
                "difficulty": info.get("difficulty"),
                "attempts": hist.total,
                "correctCount": hist.correct,
                "accuracy": round(hist.accuracy * 100, 1),
                "streak": hist.streak,
                "level": level,
                "levelText": LEVEL_TEXT.get(level, level),
                "overdueDays": overdue_days,
                "dueInDays": due_in_days,
                "recommendedIntervalDays": _due_window_days(hist.streak, hist.accuracy),
                "lastPracticeTime": hist.last_time.isoformat(timespec="seconds")
                if hist.last_time
                else "",
                "lastWrongTime": hist.last_wrong_time.isoformat(timespec="seconds")
                if hist.last_wrong_time
                else "",
                # 错题本里的状态 —— 用来回答「我会了为什么它还在错题本里」
                "inErrorBook": bool(flag) and flag.get("status") == 1,
                "errorCount": int(flag.get("errorCount") or 0),
                "advice": _advice(level, hist, overdue_days),
                "_score": _priority_score(
                    level=level, history=hist, overdue_days=overdue_days
                ),
            }
        )

    # 按「该先处理谁」排序；同分时按题目 id 稳定排序（否则每次调用顺序都在跳）
    items.sort(key=lambda it: (-it["_score"], it["questionId"]))

    # 按分档取前 N 条（避免一类刷屏，把别的档位挤没了）
    picked: List[Dict[str, Any]] = []
    per_level: Dict[str, int] = {}
    for it in items:
        lv = it["level"]
        if per_level.get(lv, 0) >= limit:
            continue
        per_level[lv] = per_level.get(lv, 0) + 1
        picked.append(it)

    for it in picked:
        it.pop("_score", None)
    # 排序键 `_score` 只用于排序，不对外（它是内部权重，用户看了只会困惑）

    total_attempts = sum(h.total for h in histories.values())
    total_correct = sum(h.correct for h in histories.values())
    overall_accuracy = round(total_correct / total_attempts * 100, 1) if total_attempts else 0.0

    needs_attention = sum(
        by_level.get(lv, 0) for lv in ("repeated_failure", "lapsing", "overdue")
    )
    can_archive = by_level.get("mastered", 0)
    overdue_count = by_level.get("overdue", 0)

    activity = await load_recent_activity(db, user_id, days=30, now=moment)

    by_subject = [
        {
            "subject": v["subject"],
            "questions": v["questions"],
            "attempts": v["attempts"],
            "accuracy": round(v["correct"] / v["attempts"] * 100, 1)
            if v["attempts"]
            else 0.0,
        }
        for v in subject_agg.values()
    ]
    # 最该优先处理的学科排前面（准确率低 + 题量大的先看）
    by_subject.sort(key=lambda s: (s["accuracy"], -s["attempts"]))

    return {
        "hasData": True,
        "generatedAt": moment.isoformat(timespec="seconds"),
        "summary": {
            "questionsSeen": len(histories),
            "totalAttempts": total_attempts,
            "overallAccuracy": overall_accuracy,
            "needsAttention": needs_attention,
            "canArchive": can_archive,
            "overdueCount": overdue_count,
        },
        "items": picked,
        "byLevel": {
            lv: {"count": n, "text": LEVEL_TEXT.get(lv, lv)}
            for lv, n in sorted(by_level.items(), key=lambda kv: LEVEL_PRIORITY.get(kv[0], 9))
        },
        "bySubject": by_subject,
        "activity": activity,
        "headline": _headline(
            questions_seen=len(histories),
            needs_attention=needs_attention,
            can_archive=can_archive,
            overdue_count=overdue_count,
            overall_accuracy=overall_accuracy,
            by_level=by_level,
        ),
        "suggestions": _suggestions(
            by_level=by_level,
            by_subject=by_subject,
            activity=activity,
            overall_accuracy=overall_accuracy,
        ),
    }


def _headline(
    *,
    questions_seen: int,
    needs_attention: int,
    can_archive: int,
    overdue_count: int,
    overall_accuracy: float,
    by_level: Optional[Dict[str, int]] = None,
) -> str:
    """一句话结论（报告第一行，也是对话里那句"最该说的话"）

    ⚠️ 顺序是「最该行动的排最前」：欠复习比"可以归档"紧急得多，
    而"你这次考得不错"永远不该排在"你有 N 道该复习"前面。

    ⚠️ **样本太少时不许下"节奏正常"的结论**（2026-10-20 实测踩到）：
    user 106 只有 6 条流水、全部落在 `fresh` 档，原来的文案会说「整体准确率 16.7%，
    节奏正常」—— 那是**错误的安全感**。数据不足以判断时说"还看不出"，比说"正常"诚实。
    """
    if questions_seen == 0:
        return "还没有作答记录"
    levels = by_level or {}
    # 全部落在「刚接触」= 每条题只做过一两次，任何趋势判断都不成立
    only_fresh = bool(levels) and set(levels.keys()) <= {"fresh"}
    if only_fresh:
        return (
            f"练了 {questions_seen} 道但每道都只做过一两次 —— "
            "现在还看不出掌握情况，多练几遍这里的诊断才有意义"
        )
    if overdue_count > 0:
        return f"有 {overdue_count} 道题已经过了复习窗口，现在练它们效果最好"
    if needs_attention > 0:
        return f"有 {needs_attention} 道题反复失守，问题多半不在练得少"
    if can_archive > 0:
        return f"有 {can_archive} 道题其实已经会了，可以从错题本毕业"
    return f"整体准确率 {overall_accuracy}%，节奏正常"


def _suggestions(
    *,
    by_level: Dict[str, int],
    by_subject: List[Dict[str, Any]],
    activity: Dict[str, Any],
    overall_accuracy: float,
) -> List[str]:
    """给出可执行的下一步（每条都要能落地，不能是"继续努力"）

    ⚠️ 数量上限 3 条：给 8 条建议等于没给建议 —— 用户一条都不会做。
    按「先处理最严重的」排序。
    """
    out: List[str] = []

    n = by_level.get("repeated_failure", 0)
    if n:
        out.append(
            f"先停下反复刷 {n} 道「反复失守」的题 —— 它们要的是补前置知识，"
            "不是继续练（下面列了具体是哪几道）"
        )

    n = by_level.get("overdue", 0)
    if n:
        out.append(f"今天优先复习 {n} 道「欠复习」的题，它们已经过了记忆窗口")

    n = by_level.get("mastered", 0)
    if n and len(out) < 3:
        out.append(
            f"把 {n} 道已连续答对的题从错题本归档，"
            "错题本越干净，你越会真的去翻它"
        )

    if activity.get("looksLikeBurst") and len(out) < 3:
        out.append(
            "最近是突击式学习（单日峰值远高于日均）—— 记忆的留存靠间隔，不靠单次时长，"
            "把量摊到每天效果会好很多"
        )

    # ⚠️ 只有「刚接触」档时不许说"没有需要特别处理的地方"（实测踩到：会给新用户
    #    错误的安全感）。数据不足以判断时，建议是「多练几遍」，不是「一切正常」。
    if not out and by_level and set(by_level.keys()) <= {"fresh"}:
        return ["每道题都只做过一两次，先多练几遍 —— 有足够的作答记录后，这里会给出具体诊断"]

    if not by_subject:
        return out[:3]

    worst = by_subject[0]
    if worst["attempts"] >= 5 and worst["accuracy"] < 60 and len(out) < 3:
        out.append(
            f"「{worst['subject']}」是当前最薄弱的一科（准确率 {worst['accuracy']}%）"
        )

    if not out:
        out.append("暂时没有需要特别处理的地方，按现在的节奏继续就行")
    return out[:3]


# ---------------------------------------------------------------------------
# 对外：把复习计划写进库（救活 next_review_time / review_count）
# ---------------------------------------------------------------------------


async def persist_plan(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int = 50,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """把诊断算出的复习间隔**写回错题本**（`next_review_time` / `review_count`）

    为什么需要它（这是本模块从「报告」变成「能用的功能」的关键一步）：
    诊断只在内存里算出一个 `recommendedIntervalDays`，刷新页面就没了。
    写回库之后，「今天该复习哪几道」就能被**查询**（`WHERE next_review_time <= now`），
    刷题页也才有可能做出「今日待复习」这个入口。

    ⚠️ 只更新**仍在错题本里**的行（`status=1`）：
      已归档的题（用户标记已掌握）不该被复习计划重新拖回注意力 —— 那等于打脸他刚才的操作。

    ⚠️ `review_count` 的口径：这里写的是**建议复习的轮次**（按 streak 推），
      不是「用户实际复习了几次」。后者已经由 `user_practice_log` 权威记录，
      在错题表上再记一遍必然会漂移。所以本列只作为「计划轮次」的冗余快照，
      真正判断复习走流水表。

    Returns:
        `{"updated": n, "dueToday": [...], "dueSoon": [...]}`
    """
    moment = now or datetime.now()
    diag = await diagnose(db, user_id, limit=max(1, int(limit or 50)), now=moment)
    if not diag.get("hasData"):
        return {"updated": 0, "dueToday": [], "dueSoon": [], "message": diag["headline"]}

    # 拉一遍错题状态：只更新仍在册的
    flags = await load_error_flags(db, user_id)

    updated = 0
    due_today: List[Dict[str, Any]] = []
    due_soon: List[Dict[str, Any]] = []

    for it in diag["items"]:
        qid = int(it["questionId"])
        flag = flags.get(qid)
        if not flag or flag.get("status") != 1:
            # 不在错题本里（或已归档）→ 不需要复习计划；它可能是收藏/斩题，别乱写
            continue

        interval = int(it["recommendedIntervalDays"] or 0)
        next_time = moment + timedelta(days=interval)
        row = await db.execute(
            UserQuestionError.__table__.update()
            .where(
                UserQuestionError.user_id == int(user_id),
                UserQuestionError.question_id == qid,
            )
            .values(
                next_review_time=next_time,
                # 计划轮次 = streak + 1（做过 base 轮），与 next_review_time 同源
                review_count=int(it["streak"]) + 1,
                update_time=moment,
            )
        )
        if (row.rowcount or 0) > 0:
            updated += 1

        brief = {
            "questionId": qid,
            "bankName": it["bankName"],
            "questionText": it["questionText"],
            "level": it["level"],
            "levelText": it["levelText"],
            "dueDate": next_time.strftime("%Y-%m-%d"),
        }
        if interval == 0:
            due_today.append(brief)
        elif interval <= 3:
            due_soon.append(brief)

    await db.flush()

    return {
        "updated": updated,
        "dueToday": due_today[:MAX_ITEMS_PER_LEVEL],
        "dueSoon": due_soon[:MAX_ITEMS_PER_LEVEL],
        "message": (
            f"已为 {updated} 道错题排好复习计划："
            f"{len(due_today)} 道今天该练、{len(due_soon)} 道三天内该练"
            if updated
            else "没有需要排复习计划的错题"
        ),
    }


__all__ = [
    "LEVEL_PRIORITY",
    "LEVEL_TEXT",
    "MAX_LOG_ROWS",
    "MEMORY_WINDOW_DAYS",
    "diagnose",
    "load_error_flags",
    "load_histories",
    "load_question_meta",
    "load_recent_activity",
    "persist_plan",
]
