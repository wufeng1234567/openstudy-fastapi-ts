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

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.words import EnglishPracticeLog, WordBook

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

    return success(
        {
            **_brief(row),
            "wrongCount": total - correct,
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
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """练习汇总：各模式次数与平均正确率、最近 7 天趋势、最常错的词"""
    uid = _uid(current_user)

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

    # ② 最近 7 天趋势（按天聚合）
    since = datetime.now() - timedelta(days=7)
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
                EnglishPracticeLog.create_time >= since,
            )
            .group_by(func.date(EnglishPracticeLog.create_time))
            .order_by(func.date(EnglishPracticeLog.create_time))
        )
    ).all()

    trend = [
        {
            "date": str(d),
            "sessions": int(sessions or 0),
            "total": int(total or 0),
            "accuracy": (
                int(round(int(correct or 0) * 100.0 / int(total)))
                if int(total or 0)
                else 0
            ),
        }
        for d, sessions, total, correct in trend_rows
    ]

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
            "topWrong": [{"word": w, "count": c} for w, c in top_wrong],
        }
    )
