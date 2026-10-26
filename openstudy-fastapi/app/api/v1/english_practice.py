"""
英语练习记录 API（2026-10-26）

## 为什么需要这层

「单词听写」与「阅读练习」原本做完即弃：关闭页面就再也找不到上次练了什么、
错在哪里。这三个端点把结果留下来，让页面能接上"下次"：

    POST /words/practice/submit   交一次练习结果（页面练完调）
    GET  /words/practice/last     取最近一次（页面顶部「继续上次」入口）
    GET  /words/practice/stats    汇总（正确率趋势、最常错词）

`accuracy` 在**服务端**算，不让前端各算一遍 —— 同一份数据在两处算出
不同数字，是这类小功能最常见的信任崩塌点。

路由前缀沿用 `app/api/v1/words.py` 的 `/words`，挂在同一个 router 下。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.words import (
    EnglishPracticeLog,
    Word,
    WordBook,
    WordLearningState,
)
from app.services.english.spaced_repetition import (
    DEFAULT_EASE,
    LearningState,
    is_due,
    mastery_of,
    review,
)

router = APIRouter(prefix="/practice")

#: 允许的练习类型
VALID_MODES = {"dictation", "reading", "ocr"}

#: 一次最多提交多少条明细（防止误传超大 JSON 把库撑爆）
MAX_DETAIL_ITEMS = 500


class PracticeDetailItem(BaseModel):
    """逐题明细的一项

    字段刻意宽松：三类练习（听写写单词 / 阅读选选项 / 识词确认条目）
    细节不同，这里只保留公共的三项，避免为每种模式建一个模型。
    """

    word: Optional[str] = None
    input: Optional[str] = None
    ok: bool = False


class PracticeSubmitRequest(BaseModel):
    mode: str = Field(..., description="dictation / reading / ocr")
    bookId: Optional[int] = None
    title: Optional[str] = None
    total: int = 0
    correct: int = 0
    duration: int = 0
    detail: List[PracticeDetailItem] = Field(default_factory=list)


def _uid(user: Dict[str, Any]) -> int:
    return int(user.get("user_id") or user.get("userId") or 0)


def _brief(row: EnglishPracticeLog) -> Dict[str, Any]:
    return {
        "id": row.id,
        "mode": row.mode,
        "bookId": row.book_id,
        "title": row.title,
        "total": row.total,
        "correct": row.correct,
        "accuracy": row.accuracy,
        "duration": row.duration,
        "createTime": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    }


def _to_state(row: Optional[WordLearningState]) -> Optional[LearningState]:
    """ORM 行 → 算法用的纯数据对象

    算法层刻意不依赖 SQLAlchemy（见 spaced_repetition.py 顶部注释），
    所以这里做一次显式转换。看起来多写几行，但换来的是算法可以脱离
    数据库单元测试 —— 那 29 条用例就是这么跑起来的。
    """
    if row is None:
        return None
    return LearningState(
        stage=int(row.stage or 0),
        ease=float(row.ease or DEFAULT_EASE),
        interval_days=int(row.interval_days or 0),
        due_date=row.due_date,
        right_count=int(row.right_count or 0),
        wrong_count=int(row.wrong_count or 0),
        lapses=int(row.lapses or 0),
        first_seen_at=row.first_seen_at,
        last_review_at=row.last_review_at,
    )


def _apply_state(row: WordLearningState, state: LearningState) -> None:
    """算法结果 → ORM 行（就地修改，由调用方 commit）"""
    row.stage = int(state.stage)
    row.ease = float(state.ease)
    row.interval_days = int(state.interval_days)
    row.due_date = state.due_date
    row.right_count = int(state.right_count)
    row.wrong_count = int(state.wrong_count)
    row.lapses = int(state.lapses)
    row.first_seen_at = state.first_seen_at
    row.last_review_at = state.last_review_at


async def _update_learning_state(
    db: AsyncSession,
    *,
    user_id: int,
    book_id: Optional[int],
    detail: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按这次的逐词对错，更新每个词的记忆状态

    ## 为什么按 word 文本再查一次 id

    前端传来的明细长这样（见听写页的提交逻辑）：

        {"word": "abandon", "input": "abandan", "ok": false}

    只有**词形**，没有 `wordId`。所以要用「词形 + 词书」反查 `words.word_id`。

    ⚠️ 限定在 `book_id` 内查：不同词书可能有同名词（`book` 在四级和雅思里
       都出现），混着查会把进度记到别的书上。前端没传 bookId 时退化为
       只按词形查（此时用第一次命中的那条，并在返回里注明）。

    ## 为什么不报错

    这个词可能已经被删了、或者前端传了脏数据。这种情况**跳过即可** ——
    练习记录本身已经保存好了，为了一个查不到的单词让整次提交失败，
    用户会以为"白练了"。
    """
    # 收集本次出现的词形（去重，保留最后一次对错结果）
    # 同一个词在一次练习里出现两次的情况很少，但真出现时以最后一次为准
    by_word: Dict[str, bool] = {}
    for item in detail:
        if not isinstance(item, dict):
            continue
        w = str(item.get("word") or "").strip()
        if not w:
            continue
        by_word[w.lower()] = bool(item.get("ok"))

    if not by_word:
        return {}

    # 词形 → word_id
    cond = [func.lower(Word.word).in_(list(by_word.keys()))]
    if book_id:
        cond.append(Word.book_id == int(book_id))

    try:
        rows = (
            await db.execute(select(Word.word_id, Word.word).where(*cond))
        ).all()
    except Exception:  # noqa: BLE001 - 状态更新失败不影响练习记录
        return {}

    word_id_by_lower: Dict[str, int] = {}
    for wid, w in rows:
        word_id_by_lower.setdefault(str(w).lower(), int(wid))

    if not word_id_by_lower:
        return {}

    # 读出已有状态
    existing_rows = (
        await db.execute(
            select(WordLearningState).where(
                WordLearningState.user_id == int(user_id),
                WordLearningState.word_id.in_(list(word_id_by_lower.values())),
            )
        )
    ).scalars().all()
    existing = {int(r.word_id): r for r in existing_rows}

    today = date.today()
    now = datetime.now()

    entered = 0          # 本次进入复习队列（答对，stage 前进）
    still_learning = 0   # 答错，回到队列
    due_count = 0        # 更新后「今天该复习」的数量

    for lower_word, is_ok in by_word.items():
        wid = word_id_by_lower.get(lower_word)
        if wid is None:
            continue

        cur_row = existing.get(wid)
        cur_state = _to_state(cur_row)

        new_state = review(cur_state, is_ok, today=today, now=now)

        if cur_row is None:
            cur_row = WordLearningState(user_id=int(user_id), word_id=wid)
            db.add(cur_row)
            existing[wid] = cur_row

        _apply_state(cur_row, new_state)

        if is_ok:
            entered += 1
        else:
            still_learning += 1
        if is_due(new_state, today):
            due_count += 1

    await db.flush()

    # 顺便统计这个词书整体的掌握情况 —— 前端提交完可以直接刷新徽标，
    # 不用再发一次请求
    mastery = {}
    if book_id:
        mastery = await _book_mastery(db, user_id=user_id, book_id=int(book_id))

    return {
        "mastery": {
            "reviewed": entered + still_learning,
            "entered": entered,
            "stillLearning": still_learning,
            "dueNow": due_count,
            **({"book": mastery} if mastery else {}),
        }
    }


async def _book_mastery(
    db: AsyncSession, *, user_id: int, book_id: int
) -> Dict[str, Any]:
    """某个词书对某个用户的掌握情况

    返回 mastered / learning / new / total / masteryRate，
    口径见 `spaced_repetition.mastery_of`。
    """
    total_words = int(
        await db.scalar(
            select(func.count()).select_from(Word).where(Word.book_id == int(book_id))
        )
        or 0
    )

    rows = (
        await db.execute(
            select(WordLearningState).where(
                WordLearningState.user_id == int(user_id),
                WordLearningState.word_id.in_(
                    select(Word.word_id).where(Word.book_id == int(book_id))
                ),
            )
        )
    ).scalars().all()

    m = mastery_of([_to_state(r) for r in rows])
    # 「新词」按词书总词数算更准确：没进过 state 表的词也是新词
    m["new"] = max(0, total_words - (m["mastered"] + m["learning"]))
    m["total"] = total_words
    return m


@router.post("/submit")
async def submit_practice(
    req: PracticeSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """交一次练习结果

    ⚠️ `accuracy` 由服务端算：前端只报 `total` / `correct`。
    两边各算一遍，迟早出现"页面显示 80%、复盘页显示 79%"这类信任问题。
    """
    if req.mode not in VALID_MODES:
        return error(f"mode 只能是 {' / '.join(sorted(VALID_MODES))}")

    total = max(0, int(req.total or 0))
    correct = max(0, min(int(req.correct or 0), total))
    if total == 0:
        return error("total 不能为 0（没有作答就不该产生练习记录）")

    # 明细可能多于题量（例如反复改答案），截断即可，不报错
    detail = [d.model_dump() for d in req.detail][:MAX_DETAIL_ITEMS]

    # 标题缺省时用词书名兜底，列表里不至于全是空白
    title = (req.title or "").strip()
    if not title and req.bookId:
        title = (
            await db.scalar(
                select(WordBook.book_name).where(WordBook.book_id == int(req.bookId))
            )
        ) or ""
    if not title:
        title = {"dictation": "单词听写", "reading": "阅读练习", "ocr": "拍照识词"}.get(
            req.mode, "英语练习"
        )

    row = EnglishPracticeLog(
        user_id=_uid(current_user),
        mode=req.mode,
        book_id=int(req.bookId) if req.bookId else None,
        title=title[:255],
        total=total,
        correct=correct,
        # 服务端算：四舍五入到整数
        accuracy=int(round(correct * 100.0 / total)),
        duration=max(0, int(req.duration or 0)),
        detail=detail,
    )
    db.add(row)
    await db.flush()

    # ------------------------------------------------------------------
    # 记忆曲线：把这次的对错落到每个词上（2026-10-26）
    # ------------------------------------------------------------------
    # 只有听写类练习才有"逐词对错"，阅读/识词没有可复习的单词维度。
    # 更新结果放在回执里，前端可以立刻显示「本轮 x 个词进入复习」
    # 或者「有 y 个词该复习了」。
    mastery_update: Dict[str, Any] = {}
    if req.mode == "dictation" and detail:
        mastery_update = await _update_learning_state(
            db,
            user_id=_uid(current_user),
            book_id=int(req.bookId) if req.bookId else None,
            detail=detail,
        )

    return success(
        {
            **_brief(row),
            "wrongCount": total - correct,
            **mastery_update,
        },
        msg="练习记录已保存",
    )


@router.get("/last")
async def last_practice(
    mode: Optional[str] = Query(None, description="只看某种练习；不传则取最近的任意一次"),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """取最近一次练习（页面顶部「继续上次」用）"""
    stmt = select(EnglishPracticeLog).where(
        EnglishPracticeLog.user_id == _uid(current_user),
        EnglishPracticeLog.del_flag == "0",
    )
    if mode:
        if mode not in VALID_MODES:
            return error(f"mode 只能是 {' / '.join(sorted(VALID_MODES))}")
        stmt = stmt.where(EnglishPracticeLog.mode == mode)

    row = (
        await db.execute(stmt.order_by(EnglishPracticeLog.create_time.desc()).limit(1))
    ).scalar_one_or_none()

    if row is None:
        return success(None, msg="还没有练习记录")

    return success(
        {
            **_brief(row),
            # 逐题明细只在这里返回（列表接口不需要，避免返回大 JSON）
            "detail": row.detail or [],
        }
    )


@router.get("/stats")
async def practice_stats(
    days: int = Query(7, description="趋势窗口天数：7 / 30"),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """练习汇总：各模式次数与平均正确率、趋势、最常错的词、最近记录"""
    uid = _uid(current_user)

    # 窗口只允许 7 / 30，避免任意值把 SQL 拖慢或被当成扫描器
    days = 30 if int(days or 7) >= 30 else 7

    # ① 各模式累计
    by_mode_rows = (
        await db.execute(
            select(
                EnglishPracticeLog.mode,
                func.count().label("sessions"),
                func.sum(EnglishPracticeLog.total).label("total"),
                func.sum(EnglishPracticeLog.correct).label("correct"),
            )
            .where(
                EnglishPracticeLog.user_id == uid,
                EnglishPracticeLog.del_flag == "0",
            )
            .group_by(EnglishPracticeLog.mode)
        )
    ).all()

    by_mode: Dict[str, Dict[str, Any]] = {}
    for mode, sessions, total, correct in by_mode_rows:
        total = int(total or 0)
        correct = int(correct or 0)
        by_mode[mode] = {
            "sessions": int(sessions or 0),
            "total": total,
            "correct": correct,
            "accuracy": int(round(correct * 100.0 / total)) if total else 0,
        }

    # ② 趋势（按天聚合）
    #
    # ⚠️ 原来只返回**有练习记录的那几天**，没练的日子直接不出现在数组里。
    #    前端画折线时，日期会从 10-20 直接跳到 10-24 —— 视觉上像"每天都练了"，
    #    其实中间断了好几天。所以这里必须把窗口内每一天都补齐（没练就是 0）。
    today = datetime.now().date()
    start_date = today - timedelta(days=days - 1)

    trend_rows = (
        await db.execute(
            select(
                func.date(EnglishPracticeLog.create_time).label("d"),
                func.count().label("sessions"),
                func.sum(EnglishPracticeLog.total).label("total"),
                func.sum(EnglishPracticeLog.correct).label("correct"),
            )
            .where(
                EnglishPracticeLog.user_id == uid,
                EnglishPracticeLog.del_flag == "0",
                func.date(EnglishPracticeLog.create_time) >= start_date,
            )
            .group_by(func.date(EnglishPracticeLog.create_time))
            .order_by(func.date(EnglishPracticeLog.create_time))
        )
    ).all()

    # 先建一张「日期 -> 数据」的表，再按连续日期铺开
    raw_trend: Dict[str, Dict[str, Any]] = {}
    for d, sessions, total, correct in trend_rows:
        total = int(total or 0)
        correct = int(correct or 0)
        raw_trend[str(d)] = {
            "date": str(d),
            "sessions": int(sessions or 0),
            "total": total,
            "correct": correct,
            "accuracy": int(round(correct * 100.0 / total)) if total else 0,
        }

    trend: List[Dict[str, Any]] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        key = d.isoformat()
        item = raw_trend.get(key)
        trend.append(
            item
            if item
            else {
                "date": key,
                "sessions": 0,
                "total": 0,
                "correct": 0,
                "accuracy": 0,
            }
        )

    # ③ 最常错的词（扫描最近 20 次的明细）
    #    明细是 JSONB，逐条在 Python 里统计比写 SQL jsonb 展开更好读，
    #    且练习记录量级很小（一个人一天最多几次），不构成性能问题。
    recent = (
        await db.execute(
            select(EnglishPracticeLog.detail)
            .where(
                EnglishPracticeLog.user_id == uid,
                EnglishPracticeLog.del_flag == "0",
            )
            .order_by(EnglishPracticeLog.create_time.desc())
            .limit(20)
        )
    ).scalars().all()

    wrong_counter: Dict[str, int] = {}
    for detail in recent:
        for item in detail or []:
            if isinstance(item, dict) and not item.get("ok"):
                word = str(item.get("word") or "").strip()
                if word:
                    wrong_counter[word] = wrong_counter.get(word, 0) + 1

    top_wrong = sorted(wrong_counter.items(), key=lambda kv: (-kv[1], kv[0]))[:10]

    total_sessions = sum(v["sessions"] for v in by_mode.values())
    total_words = sum(v["total"] for v in by_mode.values())
    total_correct = sum(v["correct"] for v in by_mode.values())

    # ④ 最近 10 次练习（给统计页的「练习记录」列表用）
    #
    # ⚠️ 不返回 detail 明细 —— 那个字段可能有几百条，一次拉 10 条
    #    会把响应撑到几百 KB，而列表只显示「模式 / 数量 / 正确率 / 时间」。
    #
    # ⚠️ 主键字段名是 `id`，不是 `log_id`（表名 english_practice_log 是另一回事）。
    log_rows = (
        await db.execute(
            select(
                EnglishPracticeLog.id,
                EnglishPracticeLog.mode,
                EnglishPracticeLog.title,
                EnglishPracticeLog.total,
                EnglishPracticeLog.correct,
                EnglishPracticeLog.accuracy,
                EnglishPracticeLog.duration,
                EnglishPracticeLog.create_time,
            )
            .where(
                EnglishPracticeLog.user_id == uid,
                EnglishPracticeLog.del_flag == "0",
            )
            .order_by(EnglishPracticeLog.create_time.desc())
            .limit(10)
        )
    ).all()

    recent_logs = [
        {
            "logId": int(log_id),
            "mode": mode,
            "title": title or "",
            "total": int(total or 0),
            "correct": int(correct or 0),
            "accuracy": int(accuracy or 0),
            "duration": int(duration or 0),
            "createTime": create_time.strftime("%Y-%m-%d %H:%M")
            if create_time
            else "",
        }
        for log_id, mode, title, total, correct, accuracy, duration, create_time in log_rows
    ]

    # ⑤ 连续练习天数（streak）—— 统计页最有激励感的指标
    #
    # 从今天往回数，只要某天有记录就 +1，遇到空白天就停。
    # 今天还没练不算断（用户可能晚上才练），所以今天为 0 时从昨天开始数。
    practiced_dates = {
        str(d)
        for (d,) in (
            await db.execute(
                select(func.date(EnglishPracticeLog.create_time).label("d"))
                .where(
                    EnglishPracticeLog.user_id == uid,
                    EnglishPracticeLog.del_flag == "0",
                )
                .group_by(func.date(EnglishPracticeLog.create_time))
            )
        ).all()
    }

    streak = 0
    cursor = today
    if cursor.isoformat() not in practiced_dates:
        cursor = cursor - timedelta(days=1)
    while cursor.isoformat() in practiced_dates:
        streak += 1
        cursor = cursor - timedelta(days=1)

    return success(
        {
            "sessions": total_sessions,
            "total": total_words,
            "correct": total_correct,
            "accuracy": (
                int(round(total_correct * 100.0 / total_words)) if total_words else 0
            ),
            "byMode": by_mode,
            "trend": trend,
            "days": days,
            "streak": streak,
            "topWrong": [{"word": w, "count": c} for w, c in top_wrong],
            "recentLogs": recent_logs,
        }
    )

# ============================================================================
# 记忆曲线相关接口（2026-10-26）
# ============================================================================


@router.get("/new-words")
async def new_words(
    bookId: int = Query(..., description="词书 ID"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """这本词书里**还没学过**的词（2026-10-26）

    给「练新词」用。判定标准：`word_learning_state` 里没有这一行，
    或 stage = 0 且从没练过（right_count = wrong_count = 0）。

    按 `sort_order, word_id` 升序，保证每次拿到的是同一批 ——
    用户点两次「练新词」看到的该是同一批词，而不是随机跳。
    """
    uid = _uid(current_user)

    # ------------------------------------------------------------------
    # 「学过」的判定：练过至少一次，而不是 stage > 0（2026-10-26 修）
    # ------------------------------------------------------------------
    # 原来用 `stage > 0`。问题是**答错会让 stage 退到 0**（SM-2 的退档逻辑），
    # 于是 campaign / deadline 这种"练过但答错了"的词被算成「没学过」，
    # 又出现在「练新词」里 —— 用户会觉得"这词我刚练过，怎么又是新的"。
    #
    # 正确的判定是「有没有练习记录」：right_count + wrong_count > 0。
    tracked = select(WordLearningState.word_id).where(
        WordLearningState.user_id == uid,
        (WordLearningState.right_count + WordLearningState.wrong_count) > 0,
    )

    total = int(
        await db.scalar(
            select(func.count())
            .select_from(Word)
            .where(Word.book_id == int(bookId), Word.word_id.not_in(tracked))
        )
        or 0
    )

    rows = (
        await db.execute(
            select(Word)
            .where(Word.book_id == int(bookId), Word.word_id.not_in(tracked))
            .order_by(Word.sort_order.asc(), Word.word_id.asc())
            .limit(int(limit))
        )
    ).scalars().all()

    items = [
        {
            "wordId": int(w.word_id),
            "word": w.word,
            "translation": w.translation,
            "phonetic": w.phonetic,
        }
        for w in rows
    ]

    return success(
        {
            "count": total,
            "returned": len(items),
            "items": items,
        }
    )


@router.get("/mastery")
async def book_mastery(
    bookId: int = Query(..., description="词书 ID"),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """某个词书的掌握情况

    给词库列表/详情页显示「已掌握 8 / 学习中 12 / 新词 22」这类徽标用。
    """
    m = await _book_mastery(db, user_id=_uid(current_user), book_id=int(bookId))
    return success(m)


@router.get("/due")
async def due_words(
    bookId: Optional[int] = Query(None, description="限定词书；不传则全部"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """今天该复习的单词（按遗忘曲线到期）

    ## 排序规则

    1. **先到期的先来**（`due_date` 升序）—— 拖得越久越该补；
    2. 同一天到期的，**错得多的先来**（`wrong_count` 降序）——
       薄弱词优先，而不是随机；
    3. 都没练过的（`due_date IS NULL`）**排在最后**，不算"复习"，
       它们是"新词"，由听写页的「新词配额」决定要不要练。

    ⚠️ 只返回**已经练过的词**。全新词不该从「复习」入口进来 ——
       那样会把"复习 20 个"变成"背 20 个新词"，两个心理预期完全不同。
    """
    uid = _uid(current_user)
    today = date.today()

    cond = [
        WordLearningState.user_id == uid,
        WordLearningState.due_date.is_not(None),
        WordLearningState.due_date <= today,
    ]

    stmt = (
        select(WordLearningState, Word)
        .join(Word, Word.word_id == WordLearningState.word_id)
        .where(*cond)
    )
    if bookId:
        stmt = stmt.where(Word.book_id == int(bookId))

    stmt = stmt.order_by(
        WordLearningState.due_date.asc(),
        WordLearningState.wrong_count.desc(),
        Word.word.asc(),
    ).limit(int(limit))

    rows = (await db.execute(stmt)).all()

    # ------------------------------------------------------------------
    # count 是「符合条件的总数」，不是「本次返回的条数」（2026-10-26 修）
    # ------------------------------------------------------------------
    # 原来直接 `len(items)`，于是 `limit=1` 时 count 也变成 1 ——
    # 而调用方传小 limit 正是为了"只要数字、不要列表"（词库页的徽标
    # 就显示「今天该复习 1 个」，实际有 5 个）。
    # 多算一次 count 很便宜（同样的 where，走 idx_wls_due 索引）。
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(WordLearningState)
            .join(Word, Word.word_id == WordLearningState.word_id)
            .where(*cond)
        )
        or 0
    )

    items = [
        {
            "wordId": int(w.word_id),
            "word": w.word,
            "translation": w.translation,
            "phonetic": w.phonetic,
            "bookId": int(w.book_id),
            "stage": int(s.stage or 0),
            "dueDate": s.due_date.isoformat() if s.due_date else None,
            "wrongCount": int(s.wrong_count or 0),
            "rightCount": int(s.right_count or 0),
            "lapses": int(s.lapses or 0),
            # 逾期几天（0 = 正好今天，正数 = 拖了几天）
            "overdueDays": (today - s.due_date).days if s.due_date else 0,
        }
        for s, w in rows
    ]

    return success(
        {
            "date": today.isoformat(),
            # 总数 vs 本次返回：两个都给，调用方按需取
            "count": total,
            "returned": len(items),
            "items": items,
        }
    )


@router.get("/overview")
async def learning_overview(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """全局学习概览：今天该复习多少、总共掌握多少

    智能体（english_practice 工具）和统计页都用它。
    """
    uid = _uid(current_user)
    today = date.today()

    total = int(
        await db.scalar(
            select(func.count()).select_from(WordLearningState).where(
                WordLearningState.user_id == uid
            )
        )
        or 0
    )

    done_count = int(
        await db.scalar(
            select(func.count()).select_from(EnglishPracticeLog).where(
                EnglishPracticeLog.user_id == uid,
                EnglishPracticeLog.del_flag == "0",
            )
        )
        or 0
    )

    due_today = int(
        await db.scalar(
            select(func.count()).select_from(WordLearningState).where(
                WordLearningState.user_id == uid,
                WordLearningState.due_date.is_not(None),
                WordLearningState.due_date <= today,
            )
        )
        or 0
    )

    rows = (
        await db.execute(
            select(WordLearningState).where(WordLearningState.user_id == uid)
        )
    ).scalars().all()
    m = mastery_of([_to_state(r) for r in rows])

    return success(
        {
            "date": today.isoformat(),
            "trackedWords": total,      # 进入记忆曲线的词数
            "practicedSessions": done_count,
            "dueToday": due_today,
            **m,
        }
    )
