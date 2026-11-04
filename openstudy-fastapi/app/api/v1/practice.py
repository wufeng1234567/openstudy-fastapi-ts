"""题库练习会话与成绩（服务端权威判分）

为什么单独一个 API 文件：
- `questions.py` 已经承担题库/题目 CRUD，练习会话是**另一条读写生命周期**；
- 这里只依赖 `question_grading_service`，不把答案/解析重新散落到路由里。

安全口径：
1. 开始会话只返回脱敏题目（无 answer/analysis）；
2. 每次作答由服务端判分，客户端传的 isCorrect 不作为事实；
3. 交卷时汇总成绩并写 `user_practice_log` / 错题本，简答题标记 pending。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.response import success, error
from app.core.security import get_current_user
from app.database import get_db
from app.models.bank_share import BankShareReceive
from app.models.question import (
    QuestionBank,
    QuestionMain,
    UserPracticeLog,
    UserPracticeSession,
    UserQuestionError,
    UserQuestionFavorite,
)
from app.services.question_grading_service import grade_question, question_payload

router = APIRouter()


class SessionStartRequest(BaseModel):
    bankId: int
    moduleType: str = Field(default="sequential", max_length=20)
    questionIds: Optional[List[int]] = None
    count: Optional[int] = Field(default=None, ge=1)
    #: 模拟考试按题型配置的分值快照：{questionId: score}
    scores: Optional[Dict[str, float]] = None


class SessionAnswerRequest(BaseModel):
    questionId: int
    answer: Any = None


class SessionSubmitRequest(BaseModel):
    durationSec: Optional[int] = Field(default=None, ge=0)
    #: 考试模式不在逐题时上报，交卷时必须把本地答案一并提交（否则服务端只能看到空会话）
    answers: Optional[Dict[str, Any]] = None


def _uid(current_user: dict) -> int:
    return int(current_user.get("user_id") or 0)


async def _expire_stale_sessions(db: AsyncSession, user_id: int) -> None:
    """把超过 2 小时仍未交卷的练习标记为 expired，避免 endless ongoing 记录。"""
    await db.execute(
        update(UserPracticeSession)
        .where(
            UserPracticeSession.user_id == user_id,
            UserPracticeSession.status == "ongoing",
            UserPracticeSession.create_time < datetime.now() - timedelta(hours=2),
        )
        .values(status="expired", update_time=datetime.now())
    )


def _dec(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


async def _assert_bank_visible(db: AsyncSession, bank_id: int, user_id: int) -> QuestionBank:
    bank = (await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))).scalar_one_or_none()
    if not bank or str(bank.status or "0") != "0":
        raise ValueError("题库不存在或已停用")
    if int(bank.user_id or 0) == user_id:
        return bank
    # 0 = 公开
    if int(bank.is_public or 0) == 0:
        return bank
    shared = await db.scalar(
        select(BankShareReceive.id).where(
            BankShareReceive.receiver_id == user_id,
            BankShareReceive.bank_id == bank_id,
        ).limit(1)
    )
    if shared:
        return bank
    raise PermissionError("无权访问该题库（私密题库仅作者与已获取分享的用户可见）")


def _has_answer(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, dict):
        return any(_has_answer(v) for v in value.values())
    return True


def _norm_answer(value: Any) -> Any:
    """把前端传来的 answers 对象统一成可 JSON 存储的结构。"""
    if isinstance(value, dict):
        return {str(k): _norm_answer(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm_answer(v) for v in value]
    return value


def _session_brief(session: UserPracticeSession) -> Dict[str, Any]:
    total_score = _dec(session.total_score)
    score = _dec(session.score)
    return {
        "sessionId": session.session_key,
        "bankId": session.bank_id,
        "moduleType": session.module_type,
        "status": session.status,
        "totalCount": session.total_count,
        "answeredCount": session.answered_count,
        "correctCount": session.correct_count,
        "wrongCount": session.wrong_count,
        "pendingCount": session.pending_count,
        "score": round(score, 2),
        "totalScore": round(total_score, 2),
        "percentage": round(score / total_score * 100, 1) if total_score > 0 else 0,
        "durationSec": session.duration_sec,
        "createTime": session.create_time.isoformat() if session.create_time else None,
        "submitTime": session.submit_time.isoformat() if session.submit_time else None,
    }


async def _load_session(
    db: AsyncSession, session_key: str, user_id: int
) -> UserPracticeSession:
    session = (
        await db.execute(
            select(UserPracticeSession).where(
                UserPracticeSession.session_key == session_key,
                UserPracticeSession.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise LookupError("练习会话不存在")
    return session


async def _load_questions(db: AsyncSession, ids: List[int]) -> Dict[int, QuestionMain]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(QuestionMain)
            .options(selectinload(QuestionMain.sub_questions))
            .where(QuestionMain.id.in_(ids))
        )
    ).scalars().all()
    return {int(q.id): q for q in rows}


def _score_for(session: UserPracticeSession, question_id: int) -> Optional[float]:
    config = session.score_config or {}
    value = config.get(str(question_id))
    if value is None:
        value = config.get(question_id)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply_counts(session: UserPracticeSession, grades: List[Dict[str, Any]], answered_ids: set) -> None:
    session.answered_count = len(answered_ids)
    session.correct_count = sum(1 for g in grades if g.get("isCorrect") is True and not g.get("pending"))
    session.wrong_count = sum(1 for g in grades if g.get("isCorrect") is False and not g.get("pending") and g.get("answered"))
    session.pending_count = sum(1 for g in grades if g.get("pending"))
    session.score = sum(
        _dec(g.get("scoreAwarded")) for g in grades if not g.get("pending")
    )
    session.total_score = sum(
        _dec(g.get("maxScore")) for g in grades if not g.get("pending")
    )


async def _write_practice_log(
    db: AsyncSession,
    *,
    user_id: int,
    question: QuestionMain,
    bank_id: int,
    answer: Any,
    grade: Dict[str, Any],
) -> Optional[int]:
    """写一条答题流水 + 同步收藏/错题；简答题 pending 不写错题本。"""
    if grade.get("pending"):
        return None
    answer_text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
    if len(answer_text) > 2000:
        answer_text = answer_text[:2000]
    now = datetime.now()
    db.add(
        UserPracticeLog(
            user_id=user_id,
            question_id=question.id,
            bank_id=bank_id,
            is_correct=1 if grade.get("isCorrect") else 0,
            answer=answer_text,
            create_time=now,
        )
    )
    q_fav = (
        await db.execute(
            select(UserQuestionFavorite).where(
                UserQuestionFavorite.user_id == user_id,
                UserQuestionFavorite.question_id == question.id,
                UserQuestionFavorite.favorite_status == 1,
            )
        )
    ).scalar_one_or_none()
    if q_fav:
        if grade.get("isCorrect"):
            q_fav.correct_times = (q_fav.correct_times or 0) + 1
        else:
            q_fav.error_times = (q_fav.error_times or 0) + 1
        q_fav.review_count = (q_fav.review_count or 0) + 1
        q_fav.last_review_time = now

    error_id = None
    if not grade.get("isCorrect"):
        err = (
            await db.execute(
                select(UserQuestionError).where(
                    UserQuestionError.user_id == user_id,
                    UserQuestionError.question_id == question.id,
                )
            )
        ).scalar_one_or_none()
        if err:
            err.error_count = (err.error_count or 0) + 1
            err.last_error_time = now
            err.status = 1
            err.is_mastered = 0
            error_id = err.error_id
        else:
            err = UserQuestionError(
                user_id=user_id,
                question_id=question.id,
                bank_id=bank_id,
                error_count=1,
                error_time=now,
                last_error_time=now,
                status=1,
                is_mastered=0,
            )
            db.add(err)
            await db.flush()
            error_id = err.error_id
    return error_id


@router.post("/questionPractice/session/start")
async def start_practice_session(
    payload: SessionStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = _uid(current_user)
    await _expire_stale_sessions(db, uid)
    try:
        await _assert_bank_visible(db, payload.bankId, uid)
    except PermissionError as e:
        return error(str(e), code=403)
    except ValueError as e:
        return error(str(e), code=404)

    if payload.questionIds:
        ids = [int(x) for x in payload.questionIds]
        rows = await _load_questions(db, ids)
        missing = [x for x in ids if x not in rows]
        if missing:
            return error(f"题目不存在或已删除：{missing[:5]}", code=404)
        if any(int(rows[x].bank_id) != payload.bankId for x in ids):
            return error("题目不属于当前题库", code=400)
        qmap = rows
        ordered = [qmap[x] for x in ids]
    else:
        query = (
            select(QuestionMain)
            .options(selectinload(QuestionMain.sub_questions))
            .where(QuestionMain.bank_id == payload.bankId, QuestionMain.status == "0")
            .order_by(QuestionMain.sort_order, QuestionMain.id)
        )
        ordered = list((await db.execute(query)).scalars().all())
        if payload.count:
            ordered = ordered[: payload.count]
        if not ordered:
            return success({"sessionId": None, "questions": [], "total": 0})

    session = UserPracticeSession(
        session_key=uuid.uuid4().hex,
        user_id=uid,
        bank_id=payload.bankId,
        module_type=payload.moduleType or "sequential",
        question_ids=[int(q.id) for q in ordered],
        answers={},
        score_config={str(k): float(v) for k, v in (payload.scores or {}).items()},
        status="ongoing",
        total_count=len(ordered),
    )
    db.add(session)
    await db.flush()
    return success(
        {
            "sessionId": session.session_key,
            "bankId": session.bank_id,
            "moduleType": session.module_type,
            "total": len(ordered),
            "questions": [_question_for_session(q, session) for q in ordered],
        }
    )


def _question_for_session(question: QuestionMain, session: UserPracticeSession) -> Dict[str, Any]:
    return question_payload(question, reveal=False, score_override=_score_for(session, int(question.id)))


@router.post("/questionPractice/session/{session_key}/answer")
async def answer_practice_session(
    session_key: str,
    payload: SessionAnswerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = _uid(current_user)
    try:
        session = await _load_session(db, session_key, uid)
    except LookupError as e:
        return error(str(e), code=404)
    if session.status != "ongoing":
        return error("本次练习已交卷，不能修改答案", code=400)
    if int(payload.questionId) not in [int(x) for x in (session.question_ids or [])]:
        return error("题目不属于本次练习", code=400)
    if not _has_answer(payload.answer):
        return error("答案不能为空", code=400)

    question = await db.get(QuestionMain, int(payload.questionId), options=[selectinload(QuestionMain.sub_questions)])
    if not question:
        return error("题目不存在", code=404)

    grade = grade_question(question, payload.answer, _score_for(session, int(question.id)))
    old = (session.answers or {}).get(str(question.id)) or {}
    answers = dict(session.answers or {})
    answers[str(question.id)] = {
        "answer": _norm_answer(payload.answer),
        "isCorrect": grade.get("isCorrect"),
        "pending": bool(grade.get("pending")),
        "scoreAwarded": grade.get("scoreAwarded"),
        "maxScore": grade.get("maxScore"),
    }
    session.answers = answers

    # 用存储后的所有答案重算计数，避免改答案时计数漂移（只做轻量判分，不写流水）
    grades: List[Dict[str, Any]] = []
    answered_ids = set()
    qmap = await _load_questions(db, [int(x) for x in (session.question_ids or [])])
    for qid in session.question_ids or []:
        stored = answers.get(str(qid))
        if not stored:
            continue
        answered_ids.add(int(qid))
        q = qmap.get(int(qid))
        if q:
            g = grade_question(q, stored.get("answer"), _score_for(session, int(qid)))
            g["answered"] = True
            grades.append(g)
    _apply_counts(session, grades, answered_ids)
    session.update_time = datetime.now()
    await db.flush()
    return success(
        {
            **grade,
            "session": _session_brief(session),
            "previousAnswered": bool(old),
        }
    )


@router.post("/questionPractice/session/{session_key}/submit")
async def submit_practice_session(
    session_key: str,
    payload: SessionSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = _uid(current_user)
    try:
        session = await _load_session(db, session_key, uid)
    except LookupError as e:
        return error(str(e), code=404)

    already_submitted = session.status == "submitted"
    # 考试模式没有逐题上报，交卷请求必须把本地答案合并进会话。
    # 只接受本次会话题目 id；空答案不算作答。
    if not already_submitted and payload.answers:
        merged = dict(session.answers or {})
        session_qids = {int(x) for x in (session.question_ids or [])}
        for key, value in payload.answers.items():
            try:
                qid = int(key)
            except (TypeError, ValueError):
                continue
            if qid in session_qids and _has_answer(value):
                merged[str(qid)] = {
                    "answer": _norm_answer(value),
                    "isCorrect": None,
                    "pending": False,
                    "scoreAwarded": 0,
                    "maxScore": 0,
                }
        session.answers = merged
    qmap = await _load_questions(db, [int(x) for x in (session.question_ids or [])])
    answers = session.answers or {}
    items: List[Dict[str, Any]] = []
    grades: List[Dict[str, Any]] = []
    answered_ids = set()

    for qid in session.question_ids or []:
        question = qmap.get(int(qid))
        if not question:
            continue
        stored = answers.get(str(qid))
        if stored:
            answer = stored.get("answer")
            answered_ids.add(int(qid))
            grade = grade_question(question, answer, _score_for(session, int(qid)))
            grade["answered"] = True
            grade["userAnswer"] = answer
            grade["question"] = question_payload(question, reveal=False, score_override=_score_for(session, int(qid)))
            items.append(grade)
            grades.append(grade)
            if not already_submitted:
                await _write_practice_log(
                    db,
                    user_id=uid,
                    question=question,
                    bank_id=session.bank_id,
                    answer=answer,
                    grade=grade,
                )
        else:
            score_override = _score_for(session, int(qid))
            payload_question = question_payload(question, reveal=False, score_override=score_override)
            grade = {
                "questionId": int(qid),
                "isCorrect": False,
                "pending": False,
                "answered": False,
                "scoreAwarded": 0.0,
                "maxScore": float(payload_question.get("score") or 1.0),
                "correctAnswer": None,
                "analysis": "",
                "userAnswer": None,
                "question": payload_question,
            }
            items.append(grade)
            grades.append(grade)

    _apply_counts(session, grades, answered_ids)
    # 未作答也计入 total_score，但不计 correct/wrong（前端单独显示未答）
    if session.total_score <= 0:
        session.total_score = sum(_dec(g.get("maxScore")) for g in grades if not g.get("pending"))
    session.status = "submitted"
    session.submit_time = datetime.now()
    session.update_time = datetime.now()
    if payload.durationSec is not None:
        session.duration_sec = payload.durationSec
    await db.flush()
    return success(
        {
            **_session_brief(session),
            "items": items,
        },
        "交卷成功" if not already_submitted else "本次练习已交卷",
    )


@router.get("/questionPractice/session/{session_key}")
async def get_practice_session(
    session_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = _uid(current_user)
    try:
        session = await _load_session(db, session_key, uid)
    except LookupError as e:
        return error(str(e), code=404)

    qmap = await _load_questions(db, [int(x) for x in (session.question_ids or [])])
    questions = [
        question_payload(q, reveal=False, score_override=_score_for(session, int(qid)))
        for qid in session.question_ids or []
        if (q := qmap.get(int(qid))) is not None
    ]
    if session.status == "submitted":
        # 交卷后可以安全展示参考答析（用户已作答完）
        items = []
        for qid in session.question_ids or []:
            question = qmap.get(int(qid))
            if not question:
                continue
            stored = (session.answers or {}).get(str(qid))
            if stored:
                grade = grade_question(question, stored.get("answer"), _score_for(session, int(qid)))
                grade["answered"] = True
                grade["userAnswer"] = stored.get("answer")
            else:
                payload_question = question_payload(question, reveal=True, score_override=_score_for(session, int(qid)))
                grade = {
                    "questionId": int(qid),
                    "isCorrect": False,
                    "pending": False,
                    "answered": False,
                    "scoreAwarded": 0,
                    "maxScore": float(payload_question.get("score") or 1),
                    "correctAnswer": None,
                    "analysis": "",
                    "userAnswer": None,
                }
            # 只有真正作答过的题才在成绩回看里展开答案解析；
            # 否则「开一场空练习 → 直接交卷 → 回看」就能白拿整套答案。
            grade["question"] = question_payload(
                question, reveal=bool(stored), score_override=_score_for(session, int(qid))
            )
            items.append(grade)
        return success({**_session_brief(session), "items": items})
    return success({**_session_brief(session), "questions": questions})


@router.get("/questionPractice/sessions")
async def list_practice_sessions(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    uid = _uid(current_user)
    await _expire_stale_sessions(db, uid)
    rows = (
        await db.execute(
            select(UserPracticeSession)
            .where(UserPracticeSession.user_id == uid)
            .order_by(UserPracticeSession.create_time.desc())
            .limit(limit)
        )
    ).scalars().all()
    return success([_session_brief(r) for r in rows])
