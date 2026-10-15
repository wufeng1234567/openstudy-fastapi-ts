"""
题库 / 题目的**写入与统计**单一事实来源

为什么单独抽一层：同一套写逻辑现在有两个调用方 ——
  1. 后台接口 `app/api/v1/questions.py`（创建/导入题库，前端直接调）；
  2. AI Agent 的工具（`services/ai/agent/tools/*`，模型间接调）。
两边各写一份的后果很具体：Agent 建的题库「科目推断」和 UI 建的不一样、
`total_questions` 统计口径不一致、子题 sort_order 从 0 还是 1 开始都可能不同。

所以规则统一收在这里；`questions.py` 里原有的同名私有函数改成**委托调用**，
对外行为不变。
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_share import BankShare, BankShareReceive
from app.models.note_question import NoteQuestion
from app.models.note_question_bank import NoteQuestionBank
from app.models.question import (
    QuestionBank,
    QuestionMain,
    QuestionSub,
    UserBankFavorite,
    UserQuestionError,
    UserQuestionFavorite,
    UserQuestionMarked,
)

#: 题库名关键词 → 科目（与后台创建题库的口径一致）
SUBJECT_KEYWORDS: Dict[str, str] = {
    "java": "Java",
    "python": "Python",
    "mysql": "MySQL",
    "数据结构": "计算机基础",
    "算法": "计算机基础",
    "英语": "英语",
    "数学": "数学",
    "物理": "物理",
    "化学": "化学",
    "历史": "历史",
    "政治": "政治",
}

#: 题型编码 → 中文（提示词与展示共用）
QUESTION_TYPE_TEXT: Dict[int, str] = {
    1: "单选题",
    2: "多选题",
    3: "判断题",
    4: "填空题",
    5: "简答题",
    6: "阅读理解（组合题）",
    7: "完形填空（组合题）",
}


def infer_subject(bank_name: str) -> str:
    """根据题库名自动推断科目"""
    name_lower = (bank_name or "").lower()
    for key, subject in SUBJECT_KEYWORDS.items():
        if key in name_lower:
            return subject
    return "未分类"


def generate_description(bank_name: str, subject: str) -> str:
    """根据题库名自动生成 10-50 字描述"""
    desc = f"《{bank_name}》是{subject}科目的练习题库，包含多种题型，适合系统复习与自测。"
    if len(desc) > 50:
        return desc[:50]
    if len(desc) < 10:
        return f"《{bank_name}》练习题库，包含多种题型，助你高效学习。"
    return desc


def normalize_options(options: Any) -> Optional[list]:
    """选项归一化成 JSON 数组（模型能吐出的所有形态都兼容）

    - `None` / 空 → `None`（非选择题不写这个字段）
    - 已是 list → 过滤空值
    - JSON 字符串 `'["A","B"]'` → 解析成 list
    - 逗号分隔字符串 `'A,B,C'` → 拆开（模型偶尔偷懒）
    """
    if options is None:
        return None
    if isinstance(options, str):
        text = options.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            return normalize_options(parsed)
        except Exception:  # noqa: BLE001 - 退化成逗号分隔
            parts = [p.strip() for p in text.replace("，", ",").split(",")]
            parts = [p for p in parts if p]
            return parts or None
    if isinstance(options, (list, tuple)):
        cleaned = []
        for item in options:
            if item is None:
                continue
            if isinstance(item, str) and not item.strip():
                continue
            cleaned.append(item)
        return cleaned or None
    if isinstance(options, dict):
        return [options]
    return None


def _get(source: Any, *keys: str, default: Any = None) -> Any:
    """从 dict 或 pydantic 模型里按多个候选键取值（模型输出的字段名不总是规范的）"""
    for key in keys:
        if isinstance(source, dict):
            if key in source and source[key] is not None:
                return source[key]
        else:
            value = getattr(source, key, None)
            if value is not None:
                return value
    return default


async def recalc_bank_total(db: AsyncSession, bank_id: int) -> int:
    """重算题库题目总数（COUNT status='0'，与后台口径一致）"""
    count = await db.scalar(
        select(func.count()).where(
            QuestionMain.bank_id == bank_id,
            QuestionMain.status == "0",
        )
    ) or 0
    await db.execute(
        sa_update(QuestionBank).where(QuestionBank.id == bank_id).values(total_questions=count)
    )
    return int(count)


async def insert_sub_questions(
    db: AsyncSession, main_id: int, sub_questions: Sequence[Any], start_order: int = 0
) -> int:
    """批量插入子题；返回插入条数

    `sub_questions` 允许是 dict 或 pydantic 模型（Agent 侧给的是 dict）。
    """
    if not sub_questions:
        return 0
    inserted = 0
    for idx, sub in enumerate(sub_questions):
        question_text = _get(sub, "questionText", "question_text", "text")
        if not question_text:
            continue
        sort_order = _get(sub, "sortOrder", "sort_order")
        db.add(
            QuestionSub(
                main_id=main_id,
                question_text=str(question_text),
                question_type=int(_get(sub, "questionType", "question_type", default=1) or 1),
                options=normalize_options(_get(sub, "options")),
                answer=str(_get(sub, "answer", default="") or ""),
                analysis=_get(sub, "analysis"),
                sort_order=int(sort_order) if sort_order is not None else start_order + idx,
                score=_get(sub, "score", default=0) or 0,
            )
        )
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


async def create_bank(
    db: AsyncSession,
    *,
    user_id: int,
    bank_name: str,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    cover_image: Optional[str] = None,
    is_public: Optional[int] = None,
    allow_fork: Optional[int] = None,
    status: str = "0",
) -> QuestionBank:
    """创建题库（未给 subject / description 时自动推断生成）"""
    final_subject = (subject or "").strip() or infer_subject(bank_name)
    final_description = (description or "").strip() or generate_description(
        bank_name, final_subject
    )
    bank = QuestionBank(
        bank_name=bank_name,
        subject=final_subject,
        description=final_description,
        cover_image=cover_image,
        is_public=is_public if is_public is not None else 0,
        allow_fork=allow_fork if allow_fork is not None else 1,
        status=status or "0",
        user_id=user_id,
    )
    db.add(bank)
    await db.flush()
    await db.refresh(bank)
    return bank


async def create_question(
    db: AsyncSession,
    *,
    bank_id: int,
    question_type: int = 1,
    question_text: str,
    answer: str = "",
    options: Any = None,
    analysis: Optional[str] = None,
    content: Optional[str] = None,
    difficulty: int = 1,
    score: float = 0,
    sort_order: int = 0,
    sub_questions: Optional[Sequence[Any]] = None,
    recalc_total: bool = True,
) -> QuestionMain:
    """创建题目（含子题）并刷新题库总数"""
    subs = list(sub_questions or [])
    question = QuestionMain(
        bank_id=bank_id,
        question_type=int(question_type or 1),
        difficulty=int(difficulty or 1),
        question_text=question_text,
        content=content,
        options=normalize_options(options),
        answer="" if answer is None else str(answer),
        analysis=analysis,
        has_sub_questions=1 if subs else 0,
        sort_order=int(sort_order or 0),
        score=score or 0,
        status="0",
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)

    if subs:
        await insert_sub_questions(db, question.id, subs)
    if recalc_total:
        await recalc_bank_total(db, bank_id)
    return question


async def find_bank_by_name(
    db: AsyncSession, user_id: int, bank_name: str
) -> Optional[QuestionBank]:
    """按**精确名称**在「当前用户自己的题库」里查（Agent 不该碰别人的题库）"""
    if not bank_name:
        return None
    result = await db.execute(
        select(QuestionBank).where(
            QuestionBank.user_id == user_id,
            QuestionBank.bank_name == bank_name,
        )
    )
    return result.scalars().first()


async def list_user_banks(
    db: AsyncSession,
    user_id: int,
    keyword: Optional[str] = None,
    subject: Optional[str] = None,
) -> List[QuestionBank]:
    """列出用户自己的题库（可按名称模糊 / 科目过滤）"""
    query = select(QuestionBank).where(QuestionBank.user_id == user_id)
    if keyword:
        query = query.where(QuestionBank.bank_name.like(f"%{keyword}%"))
    if subject:
        query = query.where(QuestionBank.subject == subject)
    query = query.order_by(QuestionBank.create_time.desc(), QuestionBank.id.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_banks(
    db: AsyncSession, user_id: int, bank_ids: Iterable[int]
) -> Dict[str, Any]:
    """删除题库（只允许删自己的；按「应用层级联」清理所有关联数据）

    ⚠️ 为什么不用 ORM 的 `db.delete(bank)`：
      `QuestionBank.questions` 关系没有配 delete / delete-orphan cascade，
      ORM 删父对象时会把子表的**外键置空** —— 而 `question_main.bank_id` 是 NOT NULL，
      于是报 `IntegrityError: Column 'bank_id' cannot be null`（Agent 删题库就踩了这个）。
      这里改为 Core 批量 delete，并且显式清理「没有 DB 外键约束」的关联表
      （note_question / note_question_bank / bank_share*，它们不会自动级联），
      顺序与后台接口 `DELETE /questionBank/questionBank/{ids}` 完全一致。

    Returns:
        {"deleted": [{"id":..,"bankName":..}], "missing": [id, ...]}
    """
    ids = [int(i) for i in bank_ids if i is not None]
    if not ids:
        return {"deleted": [], "missing": []}

    # 只取「属于当前用户」的题库（标量列 → 不加载 ORM 对象，避免级联副作用）
    rows = (
        await db.execute(
            select(QuestionBank.id, QuestionBank.bank_name).where(
                QuestionBank.id.in_(ids), QuestionBank.user_id == user_id
            )
        )
    ).all()
    own_ids = [int(r[0]) for r in rows]
    deleted = [{"id": int(r[0]), "bankName": r[1]} for r in rows]
    found = set(own_ids)
    if not own_ids:
        return {"deleted": [], "missing": ids}

    # 1. 收集受影响题目 ID
    question_ids = [
        int(r[0])
        for r in (
            await db.execute(
                select(QuestionMain.id).where(QuestionMain.bank_id.in_(own_ids))
            )
        ).all()
    ]

    if question_ids:
        # 2. 子题
        await db.execute(
            delete(QuestionSub).where(QuestionSub.main_id.in_(question_ids))
        )
        # 3. 用户题目关联（收藏 / 错题 / 斩题 / 笔记）
        await db.execute(
            delete(UserQuestionFavorite).where(
                UserQuestionFavorite.question_id.in_(question_ids)
            )
        )
        await db.execute(
            delete(UserQuestionError).where(
                UserQuestionError.question_id.in_(question_ids)
            )
        )
        await db.execute(
            delete(UserQuestionMarked).where(
                UserQuestionMarked.question_id.in_(question_ids)
            )
        )
        await db.execute(
            delete(NoteQuestion).where(NoteQuestion.question_id.in_(question_ids))
        )

    # 4. 用户题库收藏 + 笔记-题库关联
    await db.execute(
        delete(UserBankFavorite).where(UserBankFavorite.bank_id.in_(own_ids))
    )
    await db.execute(
        delete(NoteQuestionBank).where(
            NoteQuestionBank.question_bank_id.in_(own_ids)
        )
    )

    # 5. 分享与领取记录（题库没了，分享自然失效）
    await db.execute(
        delete(BankShareReceive).where(BankShareReceive.bank_id.in_(own_ids))
    )
    await db.execute(delete(BankShare).where(BankShare.bank_id.in_(own_ids)))

    # 6. 题目 → 7. 题库
    if question_ids:
        await db.execute(
            delete(QuestionMain).where(QuestionMain.id.in_(question_ids))
        )
    await db.execute(delete(QuestionBank).where(QuestionBank.id.in_(own_ids)))
    await db.flush()

    return {"deleted": deleted, "missing": [i for i in ids if i not in found]}


def bank_brief(bank: QuestionBank) -> Dict[str, Any]:
    """题库摘要（Agent / 提示词统一用它，字段名保持 camelCase 以免前端再转）"""
    return {
        "bankId": bank.id,
        "bankName": bank.bank_name,
        "subject": bank.subject,
        "description": bank.description,
        "totalQuestions": bank.total_questions or 0,
        "isPublic": bank.is_public,
        "createTime": bank.create_time.strftime("%Y-%m-%d %H:%M:%S")
        if bank.create_time
        else None,
    }


def question_brief(
    question: QuestionMain, sub_count: int = 0, *, with_detail: bool = False
) -> Dict[str, Any]:
    """题目摘要；`with_detail=True` 时带上选项 / 答案 / 解析"""
    data: Dict[str, Any] = {
        "questionId": question.id,
        "bankId": question.bank_id,
        "questionType": question.question_type,
        "questionTypeText": QUESTION_TYPE_TEXT.get(question.question_type, "未知"),
        "questionText": question.question_text,
        "difficulty": question.difficulty,
        "sortOrder": question.sort_order,
        "hasSubQuestions": question.has_sub_questions,
        "subCount": sub_count,
    }
    if with_detail:
        data.update(
            {
                "options": question.options,
                "answer": question.answer,
                "analysis": question.analysis,
                "content": question.content,
            }
        )
    else:
        # 列表场景只给题干前 80 字，省 token
        text = question.question_text or ""
        data["preview"] = text[:80] + ("…" if len(text) > 80 else "")
    return data


__all__ = [
    "SUBJECT_KEYWORDS",
    "QUESTION_TYPE_TEXT",
    "infer_subject",
    "generate_description",
    "normalize_options",
    "recalc_bank_total",
    "insert_sub_questions",
    "create_bank",
    "create_question",
    "find_bank_by_name",
    "list_user_banks",
    "delete_banks",
    "bank_brief",
    "question_brief",
]
