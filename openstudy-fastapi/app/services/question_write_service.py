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
    QuestionSource,
    QuestionSub,
    UserBankFavorite,
    UserQuestionError,
    UserQuestionFavorite,
    UserQuestionMarked,
    UserPracticeLog,
    UserPracticeSession,
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


async def update_bank(
    db: AsyncSession,
    bank: QuestionBank,
    *,
    bank_name: Optional[str] = None,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    is_public: Optional[int] = None,
) -> tuple:
    """更新题库字段（**只应用给出且非空的字段**），返回 `(changed, conflict)`

    · `changed`：被修改的字段名列表（空 = 什么都没给）。
    · `conflict`：想改成的名字已被**同用户的另一个题库**占用时，是那个题库
      （此时**一个字都不改**，调用方据此回报失败）；否则为 None。

    ⚠️ 与后台 `PUT /questionBank/questionBank` 的字段口径一致；改名重名校验沿用
       `bank_manage._update` 的规则（改重名会让「按名字定位 / 按名字删」变得不确定）。
    """
    new_name = (bank_name or "").strip()
    if new_name and new_name != bank.bank_name:
        dup = await find_bank_by_name(db, bank.user_id, new_name)
        if dup is not None and dup.id != bank.id:
            return [], dup

    changed: List[str] = []
    if new_name:
        bank.bank_name = new_name
        changed.append("bank_name")
    subject_text = (subject or "").strip()
    if subject_text:
        bank.subject = subject_text
        changed.append("subject")
    description_text = (description or "").strip()
    if description_text:
        bank.description = description_text
        changed.append("description")
    if is_public is not None:
        bank.is_public = int(is_public)
        changed.append("is_public")
    if changed:
        await db.flush()
    return changed, None


def _source_value(source: Any, *keys: str) -> Any:
    """从 dict / pydantic 模型里读 source 字段（兼容 camelCase 与 snake_case）。"""
    return _get(source, *keys, default=None)


def _to_int_or_none(value: Any) -> Optional[int]:
    """模型输出可能把数字写成任意脏格式；转换失败按「没给」处理，绝不让整题回滚。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def attach_question_source(
    db: AsyncSession,
    *,
    question_id: int,
    user_id: int,
    source: Any,
) -> Optional[QuestionSource]:
    """给一道题挂上「原文锚点」；source 为空时什么都不做。

    source 允许三种形态：
      · {"docId": 12, "chunkId": 3, "quote": "……", "startOffset": 100, "endOffset": 160}
      · 模型偶尔用 snake_case：doc_id / chunk_id / start_offset
      · source 为 None / 空 dict → 明确表示「没有锚点」，不写空行。
    """
    if not source:
        return None
    doc_id = _source_value(source, "docId", "doc_id", "sourceDocId", "source_doc_id")
    if doc_id is None:
        return None
    try:
        doc_id = int(doc_id)
    except (TypeError, ValueError):
        return None
    if doc_id <= 0:
        return None

    # 写入前必须确认文档属于当前用户：doc_id 是裸 BigInteger，没有数据库外键兜底。
    # 复用 rag_write_service.get_document 的严格归属校验，避免用户 A 把 B 的资料
    # 挂到自己的题上，再通过「原文依据」读到 B 的文件名/正文。
    try:
        from app.services.rag.rag_write_service import get_document

        await get_document(db, int(user_id), doc_id)
    except Exception:
        return None

    chunk_id = _to_int_or_none(
        _source_value(source, "chunkId", "chunk_id", "sourceChunkId", "source_chunk_id")
    )
    quote = str(_source_value(source, "quote", "sourceQuote", "source_quote") or "").strip() or None
    start_raw = _source_value(source, "startOffset", "start_offset", "start")
    end_raw = _source_value(source, "endOffset", "end_offset", "end")
    start = _to_int_or_none(start_raw)
    end = _to_int_or_none(end_raw)
    if start is not None and start < 0:
        start = None
    if end is not None and end < 0:
        end = None
    if start is not None and end is not None and end <= start:
        start = end = None
    # 只有 doc_id、没有 quote 也没有 offset 的锚点没有展示价值，不写。
    if not quote and start is None and end is None:
        return None

    # 同题重复导入/更新时覆盖旧锚点，不制造多条；只在同一 user 内覆盖。
    existing = (
        await db.execute(
            select(QuestionSource).where(
                QuestionSource.question_id == question_id,
                QuestionSource.user_id == int(user_id),
            )
        )
    ).scalars().first()
    if existing:
        existing.doc_id = doc_id
        existing.chunk_id = chunk_id
        existing.quote = quote
        existing.start_offset = start
        existing.end_offset = end
        await db.flush()
        return existing

    row = QuestionSource(
        question_id=question_id,
        user_id=int(user_id),
        doc_id=doc_id,
        chunk_id=chunk_id,
        quote=quote,
        start_offset=start,
        end_offset=end,
    )
    db.add(row)
    await db.flush()
    return row


async def get_question_source(
    db: AsyncSession,
    *,
    user_id: int,
    question_id: int,
) -> Optional[Dict[str, Any]]:
    """读取一道题的原文锚点；没有记录返回 None（前端据此隐藏「原文依据」）。"""
    source = (
        await db.execute(
            select(QuestionSource).where(
                QuestionSource.question_id == question_id,
                QuestionSource.user_id == user_id,
            )
        )
    ).scalars().first()
    if not source:
        return None
    # 用 get_document 再核一次资料归属 + 知识库未删除，避免直接 join 绕过软删除口径。
    try:
        from app.services.rag.rag_write_service import get_document

        doc = await get_document(db, user_id, source.doc_id)
    except Exception:
        return None
    raw = doc.raw_content or ""
    raw_len = len(raw)
    start, end = source.start_offset, source.end_offset
    if start is not None:
        start = max(0, min(int(start), raw_len))
    if end is not None:
        end = max(0, min(int(end), raw_len))
    if start is not None and end is not None and end <= start:
        start = end = None

    matched = ""
    if source.quote:
        idx = raw.find(source.quote)
        if idx >= 0:
            matched = source.quote
            # 以实际命中的位置为准，避免 quote 与 offset 不一致导致前端高亮错位。
            start, end = idx, idx + len(source.quote)
    elif start is not None and end is not None:
        matched = raw[start:end]
    return {
        "hasSource": True,
        "questionId": question_id,
        "docId": doc.id,
        "docName": doc.file_name or "资料",
        "chunkId": source.chunk_id,
        "quote": matched or source.quote or "",
        "startOffset": start,
        "endOffset": end,
        "sourceAvailable": bool(doc.raw_content),
    }


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
    source: Any = None,
    source_user_id: Optional[int] = None,
) -> QuestionMain:
    """创建题目（含子题）并刷新题库总数。

    `source` / `source_user_id` 只影响「原文锚点」这张附加表，不改变题目本体；
    老调用方不传时行为完全不变。
    """
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
    if source and source_user_id:
        await attach_question_source(
            db, question_id=question.id, user_id=int(source_user_id), source=source
        )
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

    # 练习流水/会话属于历史学习数据，但题库被物理删除后其 question_id 已成为
    # 孤儿；按题库清掉，避免统计继续把已删题库算进去（与题库删除语义一致）。
    await db.execute(delete(UserPracticeLog).where(UserPracticeLog.bank_id.in_(own_ids)))
    await db.execute(delete(UserPracticeSession).where(UserPracticeSession.bank_id.in_(own_ids)))

    if question_ids:
        # 2. 子题 + 原文锚点（锚点无 DB 级联时必须应用层先删）
        await db.execute(
            delete(QuestionSub).where(QuestionSub.main_id.in_(question_ids))
        )
        await db.execute(
            delete(QuestionSource).where(QuestionSource.question_id.in_(question_ids))
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
    "update_bank",
    "create_question",
    "find_bank_by_name",
    "list_user_banks",
    "delete_banks",
    "bank_brief",
    "question_brief",
]
