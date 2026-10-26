"""
单词记忆曲线（SM-2 简化版，2026-10-26）
============================================================================

## 为什么单独一个文件

间隔重复的核心是**一组纯函数**：给定「当前状态 + 这次答对还是答错」，
算出「新状态 + 下次什么时候复习」。

把它和数据库操作混在一起会很难测 —— 而"背单词下次该隔几天"这种逻辑
一旦算错，用户是感知不到的（只会觉得"这个 App 怎么老让我背同样的词"），
所以必须能被单元测试逐个用例钉死。

## 算法：SM-2 简化版

原始 SM-2 由 SuperMemo 在 1987 年提出，Anki / 墨墨 / 欧路都在用它的变体。
本实现做了两处简化，都是为了"用户能理解"：

**① 不给 0~5 的回忆质量评分，只区分对/错**
   完整 SM-2 要用户自评"刚才回忆得有多轻松"，实际没人会认真填。
   二元信号（对/错）信息量低一点，但**采集成本为零** —— 听写页天然就有。

**② stage 用固定 0~8 的档位，不再无限增长**
   完整 SM-2 的 repetition 可以一直涨。这里封顶 8 档：
   到 8 就视为「已掌握」，不再进日常复习队列。
   否则一个练了两年的词会算出间隔 3000 天，等于从队列里消失了 ——
   但用户其实希望它偶尔还出现一次。

## 间隔公式

    stage 0（新词）+ 答对  → interval = 1,  stage = 1
    stage 1 + 答对          → interval = 3,  stage = 2
    stage n + 答对（n>=2）  → interval = round(上次 interval × ease), stage = n+1
    任意 stage + 答错       → interval = 1,  stage = max(0, stage - 2),
                              ease = max(1.3, ease - 0.2), lapses += 1

答错时 stage 退 2 档而不是清零：
    退 2 档表示"掉回两组前"，比清零温和 —— 清零会让一个练了很久的词
    因为一次手滑就从头再来，用户会觉得白练了。

## 为什么 ease 下限是 1.3

这是 SM-2 原论文给的常数。低于 1.3 时间隔会越来越短，
最终退化成"每个词每天都复习"，那不是记忆曲线，是折磨。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

#: 默认难度系数（SM-2 原值）
DEFAULT_EASE = 2.5

#: ease 下限（SM-2 原论文常数）—— 低于它间隔会退化成每天
MIN_EASE = 1.3

#: ease 上限。不设上限的话连续答对会让间隔涨到荒谬的天数
MAX_EASE = 3.0

#: 答对时 ease 的增量
EASE_UP = 0.15

#: 答错时 ease 的减量
EASE_DOWN = 0.2

#: 视为「已掌握」的档位
MASTERED_STAGE = 8

#: stage 上限（到 8 就封顶）
MAX_STAGE = MASTERED_STAGE

#: 单次复习间隔上限（天）
#
# ⚠️ 这个常数是实测出来的，不是抄的。
#    不加限制时，连续答对 7 次的间隔序列是：
#        3 → 8 → 21 → 59 → 174 → 522 → 1566 天
#    最后一个是 4.3 年 —— 等于这个词从复习队列里消失了。
#    但 stage 要到 8 才算"已掌握"，于是 stage 3~7 之间会出现
#    "间隔一年多、却不算掌握"的荒谬状态。
#
#    180 天（半年）之后强制复查一次：真的记住的词，半年后仍然记得；
#    没记住的，半年后暴露出来正好。这个值也接近多数背单词 App 的上限。
MAX_INTERVAL_DAYS = 180


@dataclass
class LearningState:
    """一个词当前的学习状态（对应 `word_learning_state` 一行）"""

    stage: int = 0
    ease: float = DEFAULT_EASE
    interval_days: int = 0
    due_date: Optional[date] = None
    right_count: int = 0
    wrong_count: int = 0
    lapses: int = 0
    first_seen_at: Optional[datetime] = None
    last_review_at: Optional[datetime] = None

    @property
    def is_new(self) -> bool:
        """从未练过"""
        return self.stage == 0 and self.right_count == 0 and self.wrong_count == 0

    @property
    def is_mastered(self) -> bool:
        """已掌握（不再进日常复习队列）"""
        return self.stage >= MASTERED_STAGE


def review(
    state: Optional[LearningState],
    correct: bool,
    *,
    today: Optional[date] = None,
    now: Optional[datetime] = None,
) -> LearningState:
    """核心函数：喂进「当前状态 + 这次对错」，吐出「新状态」

    Args:
        state: 当前状态；`None` 表示新词（数据库里还没有这一行）
        correct: 这次答对了没有
        today: 基准日期（默认今天）。显式传入是为了测试能固定时间
        now: 基准时间

    Returns:
        新的 `LearningState`。**不修改入参**，返回的是新对象 ——
        调用方可以安全地拿去做 diff / 打日志。
    """
    today = today or date.today()
    now = now or datetime.now()

    cur = state or LearningState()

    new = LearningState(
        stage=cur.stage,
        ease=cur.ease,
        interval_days=cur.interval_days,
        due_date=cur.due_date,
        right_count=cur.right_count,
        wrong_count=cur.wrong_count,
        lapses=cur.lapses,
        first_seen_at=cur.first_seen_at or now,
        last_review_at=now,
    )

    if correct:
        new.right_count += 1

        if cur.stage == 0:
            # 新词首次答对：明天再来一次（趁热打铁，但必须隔天）
            new.stage = 1
            new.interval_days = 1
        elif cur.stage == 1:
            # 第二次答对：隔 3 天。这一步是 SM-2 的固定值，不乘 ease
            new.stage = 2
            new.interval_days = 3
        else:
            # 之后每次：上次间隔 × ease，并封顶 MAX_INTERVAL_DAYS
            new.stage = min(MAX_STAGE, cur.stage + 1)
            new.interval_days = min(
                MAX_INTERVAL_DAYS,
                max(1, round(cur.interval_days * cur.ease)),
            )
            # 答对提升 ease，但不超过上限
            new.ease = min(MAX_EASE, cur.ease + EASE_UP)

    else:
        new.wrong_count += 1
        # 只有"练过又忘了"才算 lapse；新词第一次就错不算遗忘
        if cur.stage > 0:
            new.lapses += 1

        # 退 2 档（不清零），ease 降一档，明天再来
        new.stage = max(0, cur.stage - 2)
        new.ease = max(MIN_EASE, cur.ease - EASE_DOWN)
        new.interval_days = 1

    # 「已掌握」不再排进日常复习；但仍给一个远期复查
    if new.stage >= MASTERED_STAGE:
        new.interval_days = max(new.interval_days, 90)

    # 统一封顶，避免任何分支算出超长间隔
    new.interval_days = min(new.interval_days, MAX_INTERVAL_DAYS)

    new.due_date = today + timedelta(days=new.interval_days)
    return new


def is_due(state: Optional[LearningState], today: Optional[date] = None) -> bool:
    """这个（词, 用户）今天要不要复习

    判定规则：
      · 没状态（新词）        → 要（但"要不要出新词"由调用方按配额决定）
      · 已掌握                → 不要（除非到期）
      · 有 due_date 且 <= 今天 → 要
      · 没有 due_date         → 要（异常兜底，不把词永久锁死）
    """
    if state is None:
        return True
    if state.is_mastered and state.due_date is None:
        return False

    today = today or date.today()
    if state.due_date is None:
        return True
    return state.due_date <= today


def mastery_of(states) -> dict:
    """把一批状态聚合成「掌握情况」摘要（词库页/统计页展示用）

    Args:
        states: 可迭代的 `LearningState`

    Returns:
        {"mastered": n, "learning": n, "new": n, "total": n, "masteryRate": 0~100}
    """
    mastered = learning = new = 0
    for s in states:
        if s.is_new:
            new += 1
        elif s.is_mastered:
            mastered += 1
        else:
            learning += 1

    total = mastered + learning + new
    return {
        "mastered": mastered,
        "learning": learning,
        "new": new,
        "total": total,
        # 掌握率的分母用「练过的词」而不是「全部词」——
        # 一个 1000 词的词书，用户只练了 10 个，掌握率显示 1% 会让人泄气；
        # 用"练过的里面掌握了多少"更能反映真实进展。
        "masteryRate": int(round(mastered * 100.0 / (mastered + learning)))
        if (mastered + learning)
        else 0,
    }


__all__ = [
    "DEFAULT_EASE",
    "MIN_EASE",
    "MAX_EASE",
    "MAX_INTERVAL_DAYS",
    "MASTERED_STAGE",
    "LearningState",
    "review",
    "is_due",
    "mastery_of",
]
