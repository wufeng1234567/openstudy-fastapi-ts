"""题库模块各 Excel 导出接口的「行」纯格式化。

从 ``questions.py`` 抽出的 6 个纯函数：只把 ORM 对象与已查好的 map 拼成
导出用的 dict 列表，不连数据库、不做权限判断、不参与事务。
数据库查询与 ``if question_ids:`` 守卫仍留在各路由内，时序不变。

依赖的 ``_get_*_text`` 来自既有 ``question_helpers.py``（该模块不反向导入
``questions.py``，故无循环依赖）。
"""

from __future__ import annotations

from .question_helpers import (
    _get_question_type_text,
    _get_marked_type_text,
    _get_difficulty_text,
)


#: 收藏题目状态文案；前端回填的收藏状态值 → 导出列显示文本。
FAVORITE_STATUS_TEXT = {1: "正常收藏", 2: "已掌握", 3: "待复习", 0: "取消收藏"}


def bank_rows(banks) -> list[dict]:
    return [{
        "id": b.id,
        "bankName": b.bank_name,
        "subject": b.subject,
        "description": b.description,
        "totalQuestions": b.total_questions,
        "isPublic": b.is_public,
        "createTime": b.create_time.isoformat() if b.create_time else "",
    } for b in banks]


def question_rows(questions) -> list[dict]:
    return [{
        "id": q.id,
        "bankId": q.bank_id,
        "questionType": _get_question_type_text(q.question_type),
        "questionText": q.question_text,
        "options": str(q.options) if q.options else "",
        "answer": q.answer,
        "analysis": q.analysis,
        "difficulty": q.difficulty,
        "sortOrder": q.sort_order,
    } for q in questions]


def favorite_bank_rows(favorites, bank_map: dict) -> list[dict]:
    rows = []
    for fav in favorites:
        bank = bank_map.get(fav.bank_id)
        rows.append({
            "favoriteId": fav.favorite_id,
            "userId": fav.user_id,
            "bankId": fav.bank_id,
            "bankName": bank.bank_name if bank else "",
            "subject": bank.subject if bank else "",
            "notes": fav.notes or "",
            "tags": fav.tags or "",
            "sortOrder": fav.sort_order if fav.sort_order is not None else 0,
            "isStarred": "是" if fav.is_starred else "否",
            "lastStudyTime": fav.last_study_time.isoformat() if fav.last_study_time else "",
            "studyCount": fav.study_count or 0,
            "favoriteStatus": "有效" if fav.favorite_status == 1 else "失效",
            "createTime": fav.create_time.isoformat() if fav.create_time else "",
        })
    return rows


def favorite_question_rows(favorites, q_map: dict, b_map: dict, status_map: dict) -> list[dict]:
    rows = []
    for fav in favorites:
        q = q_map.get(fav.question_id)
        bank = b_map.get(fav.bank_id)
        rows.append({
            "favoriteId": fav.favorite_id,
            "userId": fav.user_id,
            "questionId": fav.question_id,
            "bankId": fav.bank_id,
            "bankName": bank.bank_name if bank else "",
            "questionType": _get_question_type_text(q.question_type) if q else "",
            "questionText": q.question_text if q else "",
            "answer": q.answer if q else "",
            "notes": fav.notes or "",
            "tags": fav.tags or "",
            "difficultyRating": fav.difficulty_rating if fav.difficulty_rating is not None else "",
            "errorTimes": fav.error_times or 0,
            "correctTimes": fav.correct_times or 0,
            "reviewCount": fav.review_count or 0,
            "lastReviewTime": fav.last_review_time.isoformat() if fav.last_review_time else "",
            "nextReviewTime": fav.next_review_time.isoformat() if fav.next_review_time else "",
            "isStarred": "是" if fav.is_starred else "否",
            "favoriteStatus": status_map.get(fav.favorite_status, fav.favorite_status),
            "createTime": fav.create_time.isoformat() if fav.create_time else "",
        })
    return rows


def error_rows(errors, q_map: dict) -> list[dict]:
    rows = []
    for e in errors:
        q = q_map.get(e.question_id)
        rows.append({
            "errorId": e.error_id,
            "questionId": e.question_id,
            "questionText": q.question_text if q else "",
            "questionType": _get_question_type_text(q.question_type) if q else "",
            "answer": q.answer if q else "",
            "errorCount": e.error_count,
            "isMastered": "是" if e.is_mastered else "否",
            "lastErrorTime": e.last_error_time.isoformat() if e.last_error_time else "",
            "notes": e.notes or "",
        })
    return rows


def marked_rows(marked, q_map: dict) -> list[dict]:
    rows = []
    for m in marked:
        q = q_map.get(m.question_id)
        rows.append({
            "markedId": m.marked_id,
            "userId": m.user_id,
            "questionId": m.question_id,
            "questionText": q.question_text if q else "",
            "questionType": _get_question_type_text(q.question_type) if q else "",
            "answer": q.answer if q else "",
            "markedType": _get_marked_type_text(m.marked_type),
            "difficultyLevel": _get_difficulty_text(m.difficulty_level),
            "errorTimesBeforeMark": m.error_times_before_mark,
            "reviewCount": m.review_count,
            "isMastered": "是" if m.is_mastered else "否",
            "lastReviewTime": m.last_review_time.isoformat() if m.last_review_time else "",
            "notes": m.notes or "",
            "tags": m.tags or "",
            "createTime": m.create_time.isoformat() if m.create_time else "",
        })
    return rows
