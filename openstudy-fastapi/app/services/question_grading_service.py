"""题库练习的服务端判分与题目脱敏。

单一事实来源：练习会话接口、旧的 `/questionPractice/report` 统计入口都走这里，
避免「页面判一套、统计判另一套」。核心原则：
- 未作答的题绝不把 `answer` / `analysis` 下发；
- 客观题由服务端按数据库答案重算，客户端传来的 `isCorrect` 不再被信任；
- 简答题（essay）不自动判对错，标记 `pending`，不写错题本；
- 填空题做空白/标点归一化，避免大小写或全半角差异造成误判。
"""

from __future__ import annotations

import html
import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.models.question import QuestionMain, QuestionSub
from app.services.question_write_service import QUESTION_TYPE_TEXT

_OPTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PUNCT_RE = re.compile(r"[\s，,。.；;：:、!?！？'\"“”‘’（）()\[\]【】<>《》]+")
_TAG_RE = re.compile(r"<[^>]+>")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _plain(value: Any) -> str:
    return html.unescape(_TAG_RE.sub("", _text(value))).strip()


def normalize_fillblank(value: Any) -> str:
    """填空归一化：去 HTML、去空白与常见标点、统一小写与全角。"""
    text = _plain(value).lower()
    text = text.replace("　", " ")
    return _PUNCT_RE.sub("", text)


def _answer_variants(raw: Any) -> List[str]:
    """填空题参考答案可能用 `|` / `;` / `；` 列多个可接受写法。"""
    text = _plain(raw)
    if not text:
        return []
    parts = re.split(r"[|｜;；]", text)
    return [p.strip() for p in parts if p.strip()] or [text]


def _to_index(value: Any, options: Any = None) -> Optional[int]:
    """把单选/判断题答案转成 0 基下标（兼容 A/B/1/选项文本）。"""
    if isinstance(value, bool):
        return 0 if value else 1
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = _plain(value)
    if not text:
        return None
    upper = text.upper()
    if len(upper) == 1 and upper in _OPTION_LETTERS:
        return _OPTION_LETTERS.index(upper)
    if re.fullmatch(r"\d+", upper):
        return int(upper)
    if isinstance(options, list):
        for idx, opt in enumerate(options):
            if _plain(opt).lower() == text.lower():
                return idx
    return None


def _truefalse_index(value: Any) -> Optional[int]:
    # 前端判断题答案存 0=正确 / 1=错误；数字必须直接按 0 基下标解释，
    # 不能把 int 1 当成字符串 "1"（那会被误读成“正确”）。
    if isinstance(value, int) and not isinstance(value, bool):
        return 0 if value == 0 else 1
    text = _plain(value).lower()
    if text in {"t", "true", "1", "a", "正确", "对", "是"}:
        return 0
    if text in {"f", "false", "0", "b", "错误", "错", "否"}:
        return 1
    return _to_index(value)


def _parse_multi(value: Any, options: Any = None) -> List[int]:
    if value is None:
        return []
    if isinstance(value, list):
        out: List[int] = []
        for item in value:
            idx = _to_index(item, options)
            if idx is not None:
                out.append(idx)
        return sorted(set(out))
    if isinstance(value, (int, float)):
        return [int(value)]
    text = _plain(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return _parse_multi(parsed, options)
        except Exception:
            pass
    # "A,B" / "A、B" / "AB" 都接受
    stripped = re.sub(r"[\s,，、/|｜;；]+", "", text).upper()
    if stripped and all(ch in _OPTION_LETTERS for ch in stripped):
        return sorted({_OPTION_LETTERS.index(ch) for ch in stripped})
    return sorted({i for i in (_to_index(p, options) for p in re.split(r"[,，、/|｜;；\s]+", text)) if i is not None})


def _max_score(question: Any, override: Optional[float] = None) -> float:
    if override is not None:
        return max(0.0, float(override))
    raw = getattr(question, "score", None)
    try:
        value = float(raw or 0)
    except (TypeError, ValueError):
        value = 0.0
    return value if value > 0 else 1.0


def grade_sub_question(sub: QuestionSub, user_answer: Any) -> Dict[str, Any]:
    qtype = int(getattr(sub, "question_type", 1) or 1)
    options = getattr(sub, "options", None)
    raw_answer = getattr(sub, "answer", "")
    base = {
        "subId": sub.id,
        "questionType": qtype,
        "correctAnswer": None,
        "analysis": getattr(sub, "analysis", None) or "",
        "isCorrect": None,
        "pending": False,
        "scoreAwarded": 0.0,
        "maxScore": _max_score(sub),
    }
    if qtype == 5:
        base.update({"pending": True, "correctAnswer": _plain(raw_answer), "analysis": base["analysis"] or _plain(raw_answer)})
        return base
    if qtype == 3:
        user = _truefalse_index(user_answer)
        correct = _truefalse_index(raw_answer)
        base["correctAnswer"] = correct
        base["isCorrect"] = user is not None and user == correct
    elif qtype == 4:
        user_norm = normalize_fillblank(user_answer)
        variants = [normalize_fillblank(v) for v in _answer_variants(raw_answer)]
        base["correctAnswer"] = _plain(raw_answer)
        base["isCorrect"] = bool(user_norm) and user_norm in variants
    elif qtype == 2:
        user = _parse_multi(user_answer, options)
        correct = _parse_multi(raw_answer, options)
        base["correctAnswer"] = correct
        base["isCorrect"] = bool(correct) and user == correct
    else:
        user = _to_index(user_answer, options)
        correct = _to_index(raw_answer, options)
        base["correctAnswer"] = correct if correct is not None else raw_answer
        base["isCorrect"] = user is not None and user == correct
    if base["isCorrect"]:
        base["scoreAwarded"] = base["maxScore"]
    return base


def grade_question(question: QuestionMain, user_answer: Any, score_override: Optional[float] = None) -> Dict[str, Any]:
    """对一道题（含组合题子题）做服务端判分。

    返回的 `correctAnswer` / `analysis` 只应在本函数被调用后（即用户已作答）
    返回给前端；未作答的题目由 `question_payload(reveal=False)` 完全脱敏。
    """
    qtype = int(getattr(question, "question_type", 1) or 1)
    max_score = _max_score(question, score_override)
    result: Dict[str, Any] = {
        "questionId": question.id,
        "questionType": qtype,
        "userAnswer": user_answer,
        "correctAnswer": None,
        "analysis": getattr(question, "analysis", None) or "",
        "isCorrect": False,
        "pending": False,
        "scoreAwarded": 0.0,
        "maxScore": max_score,
        "subResults": [],
    }

    if qtype in (6, 7):
        # 必须与 question_payload 的排序一致：关系表的默认顺序不保证是 sort_order，
        # 否则会把第 4 个子题的答案套到第 1 个子题上（全错但看不出来）。
        subs = sorted(
            list(getattr(question, "sub_questions", None) or []),
            key=lambda s: (s.sort_order or 0, s.id or 0),
        )
        if not subs:
            result["pending"] = True
            return result
        sub_results = [
            grade_sub_question(sub, _sub_answer(user_answer, qtype, idx, int(sub.question_type or 1)))
            for idx, sub in enumerate(subs)
        ]
        result["subResults"] = sub_results
        result["pending"] = any(item["pending"] for item in sub_results)
        has_wrong = any(item["isCorrect"] is False for item in sub_results if not item["pending"])
        all_graded_correct = all(
            item["isCorrect"] is True for item in sub_results if not item["pending"]
        )
        result["isCorrect"] = bool(all_graded_correct and not has_wrong)
        # 组合题按子题得分累计，满分按题目分值；子题分值合计超出时按比例归一
        child_total = sum(float(item.get("maxScore") or 0) for item in sub_results)
        child_got = sum(float(item.get("scoreAwarded") or 0) for item in sub_results)
        if child_total > 0:
            result["scoreAwarded"] = round(max_score * child_got / child_total, 2)
        result["correctAnswer"] = [
            {"subIndex": idx, "answer": item.get("correctAnswer")}
            for idx, item in enumerate(sub_results)
        ]
        return result

    if qtype == 5:
        result["pending"] = True
        result["correctAnswer"] = _plain(getattr(question, "answer", ""))
        result["analysis"] = result["analysis"] or _plain(getattr(question, "answer", ""))
        return result

    raw_answer = getattr(question, "answer", "")
    options = getattr(question, "options", None)
    if qtype == 3:
        user = _truefalse_index(user_answer)
        correct = _truefalse_index(raw_answer)
        result["correctAnswer"] = correct
        result["isCorrect"] = user is not None and user == correct
    elif qtype == 4:
        user_norm = normalize_fillblank(user_answer)
        variants = [normalize_fillblank(v) for v in _answer_variants(raw_answer)]
        result["correctAnswer"] = _plain(raw_answer)
        result["isCorrect"] = bool(user_norm) and user_norm in variants
    elif qtype == 2:
        user = _parse_multi(user_answer, options)
        correct = _parse_multi(raw_answer, options)
        result["correctAnswer"] = correct
        result["isCorrect"] = bool(correct) and user == correct
    else:
        user = _to_index(user_answer, options)
        correct = _to_index(raw_answer, options)
        result["correctAnswer"] = correct if correct is not None else raw_answer
        result["isCorrect"] = user is not None and user == correct
    if result["isCorrect"]:
        result["scoreAwarded"] = max_score
    return result


def _sub_answer(user_answer: Any, qtype: int, sub_index: int, sub_type: int) -> Any:
    """组合题答案：与前端 answers[i] 的结构保持一致。

    - 选择/判断：`{subIndex: value}`
    - 填空：`{fillblank: {subIndex: value}}`
    - 简答：`{essay: {subIndex: value}}`

    ⚠️ 必须按**子题自身题型**取桶：阅读题里可能同时有填空和简答，
      只按主题型或固定顺序取会张冠李戴（把填空答案当简答判）。
    """
    if not isinstance(user_answer, dict):
        return None
    bucket = "fillblank" if sub_type == 4 else ("essay" if sub_type == 5 else None)
    if bucket:
        box = user_answer.get(bucket)
        if isinstance(box, dict):
            if str(sub_index) in box:
                return box[str(sub_index)]
            if sub_index in box:
                return box[sub_index]
        return None
    if str(sub_index) in user_answer:
        return user_answer[str(sub_index)]
    return user_answer.get(sub_index)


def _strip_sub(sub: QuestionSub, reveal: bool) -> Dict[str, Any]:
    data = {
        "id": sub.id,
        "subId": sub.id,
        "mainId": sub.main_id,
        "questionText": sub.question_text,
        "questionType": sub.question_type,
        "options": sub.options,
        "sortOrder": sub.sort_order,
        "score": float(sub.score) if isinstance(sub.score, Decimal) else sub.score,
    }
    if reveal:
        data["answer"] = sub.answer
        data["analysis"] = sub.analysis
    return data


def question_payload(question: QuestionMain, reveal: bool = False, score_override: Optional[float] = None) -> Dict[str, Any]:
    """练习接口的安全题目载荷；`reveal=False` 时绝不包含答案/解析。"""
    subs = sorted(list(getattr(question, "sub_questions", None) or []), key=lambda s: (s.sort_order or 0, s.id or 0))
    data = {
        "id": question.id,
        "questionId": question.id,
        "bankId": question.bank_id,
        "questionType": question.question_type,
        "questionTypeText": QUESTION_TYPE_TEXT.get(question.question_type, "未知"),
        "questionText": question.question_text,
        "questionContent": question.question_text,
        "content": question.content,
        "options": question.options,
        "difficulty": question.difficulty,
        "hasSubQuestions": question.has_sub_questions,
        "sortOrder": question.sort_order,
        "status": getattr(question, "status", None),
        "createTime": question.create_time.isoformat() if getattr(question, "create_time", None) else None,
        "score": score_override if score_override is not None else (
            float(question.score) if isinstance(question.score, Decimal) else question.score
        ),
        "subQuestions": [_strip_sub(s, reveal) for s in subs],
    }
    if reveal:
        data.update(
            {
                "answer": question.answer,
                "questionAnswer": question.answer,
                "analysis": question.analysis,
                "questionAnalysis": question.analysis,
            }
        )
    return data


__all__ = [
    "grade_question",
    "grade_sub_question",
    "question_payload",
    "normalize_fillblank",
]
