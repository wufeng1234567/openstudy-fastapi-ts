"""资料夹与题库的逻辑连接。

用户上传题库时不在资料夹里复制题目，只建立 `question_bank_kb_link` 引用；
题库的事实数据仍然只在 `question_bank` / `question_main` 中维护。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import QuestionBank, QuestionMain
from app.models.question_bank_link import QuestionBankKbLink


def _serialize_bank(bank: QuestionBank, question_count: int = 0) -> Dict[str, Any]:
    return {
        "bankId": int(bank.id),
        "id": int(bank.id),
        "bankName": str(bank.bank_name or "未命名题库"),
        "name": str(bank.bank_name or "未命名题库"),
        "subject": str(bank.subject or ""),
        "description": str(bank.description or ""),
        "questionCount": int(question_count or bank.total_questions or 0),
        "totalQuestions": int(question_count or bank.total_questions or 0),
        "createTime": bank.create_time.isoformat(sep=" ", timespec="seconds") if bank.create_time else "",
    }


async def _question_counts(db: AsyncSession, bank_ids: List[int]) -> Dict[int, int]:
    if not bank_ids:
        return {}
    rows = (
        await db.execute(
            select(QuestionMain.bank_id, func.count(QuestionMain.id))
            .where(QuestionMain.bank_id.in_(bank_ids), QuestionMain.status == "0")
            .group_by(QuestionMain.bank_id)
        )
    ).all()
    return {int(row[0]): int(row[1]) for row in rows}


async def linked_bank_ids(db: AsyncSession, *, user_id: int, kb_id: int) -> List[int]:
    if int(user_id or 0) <= 0 or int(kb_id or 0) <= 0:
        return []
    rows = (
        await db.execute(
            select(QuestionBankKbLink.bank_id).where(
                QuestionBankKbLink.user_id == int(user_id),
                QuestionBankKbLink.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    return sorted({int(item) for item in rows if int(item or 0) > 0})


async def list_linked_banks(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    ids = await linked_bank_ids(db, user_id=user_id, kb_id=kb_id)
    if not ids:
        return []
    banks = (
        await db.execute(
            select(QuestionBank).where(
                QuestionBank.id.in_(ids),
                QuestionBank.user_id == int(user_id),
                QuestionBank.status == "0",
            )
        )
    ).scalars().all()
    counts = await _question_counts(db, [int(bank.id) for bank in banks])
    return [_serialize_bank(bank, counts.get(int(bank.id), 0)) for bank in banks]


async def list_available_banks(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    ids = set(await linked_bank_ids(db, user_id=user_id, kb_id=kb_id))
    banks = (
        await db.execute(
            select(QuestionBank)
            .where(QuestionBank.user_id == int(user_id), QuestionBank.status == "0")
            .order_by(QuestionBank.create_time.desc(), QuestionBank.id.desc())
        )
    ).scalars().all()
    counts = await _question_counts(db, [int(bank.id) for bank in banks])
    result = []
    for bank in banks:
        item = _serialize_bank(bank, counts.get(int(bank.id), 0))
        item["linked"] = int(bank.id) in ids
        result.append(item)
    return result


async def link_bank(
    db: AsyncSession,
    *,
    user_id: int,
    kb_id: int,
    bank_id: int,
) -> Dict[str, Any]:
    if int(bank_id or 0) <= 0:
        raise ValueError("题库 ID 不正确")
    bank = (
        await db.execute(
            select(QuestionBank).where(
                QuestionBank.id == int(bank_id),
                QuestionBank.user_id == int(user_id),
                QuestionBank.status == "0",
            )
        )
    ).scalar_one_or_none()
    if not bank:
        raise ValueError("题库不存在或不属于当前用户")
    existing = (
        await db.execute(
            select(QuestionBankKbLink).where(
                QuestionBankKbLink.user_id == int(user_id),
                QuestionBankKbLink.kb_id == int(kb_id),
                QuestionBankKbLink.bank_id == int(bank_id),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return _serialize_bank(bank, int(bank.total_questions or 0))
    db.add(
        QuestionBankKbLink(
            user_id=int(user_id),
            kb_id=int(kb_id),
            bank_id=int(bank_id),
        )
    )
    await db.flush()
    counts = await _question_counts(db, [int(bank.id)])
    return _serialize_bank(bank, counts.get(int(bank.id), 0))


async def unlink_bank(db: AsyncSession, *, user_id: int, kb_id: int, bank_id: int) -> None:
    await db.execute(
        delete(QuestionBankKbLink).where(
            QuestionBankKbLink.user_id == int(user_id),
            QuestionBankKbLink.kb_id == int(kb_id),
            QuestionBankKbLink.bank_id == int(bank_id),
        )
    )
    await db.flush()


__all__ = [
    "linked_bank_ids",
    "list_linked_banks",
    "list_available_banks",
    "link_bank",
    "unlink_bank",
]
