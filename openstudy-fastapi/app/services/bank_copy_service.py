"""题库深拷贝服务

供 `POST /questionBank/questionBank/copy/{bank_id}` 使用 —— 用户手动「复制为我的题库」。

**只用于「用户主动复制」**：领取分享（`bankShare.receive`）默认**只写收藏**（只读），
不自动导入「我的题库」，避免未经用户同意就在其名下产生一堆副本。

只复制题库本身（题库 + 题目 + 子题），不带入错题 / 收藏 / 笔记等个人数据。
"""

import copy as _copy

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.question import QuestionBank, QuestionMain, QuestionSub


def copy_suffix_name(source_name: str) -> str:
    """副本默认名称（与手动复制保持一致）"""
    return f"{source_name}（副本）"[:100]


async def recalc_bank_total(db: AsyncSession, bank_id: int) -> None:
    """重算题库题目总数（COUNT status='0' 的题目，与 SpringBoot 一致）"""
    count = await db.scalar(
        select(func.count()).where(
            QuestionMain.bank_id == bank_id,
            QuestionMain.status == "0",
        )
    ) or 0
    await db.execute(
        sa_update(QuestionBank).where(QuestionBank.id == bank_id).values(total_questions=count)
    )


async def copy_bank_to_user(
    db: AsyncSession,
    source_bank: QuestionBank,
    target_user_id: int,
    new_name: str | None = None,
) -> QuestionBank:
    """把 source_bank 深拷贝成 target_user_id 名下的新题库并返回

    调用方负责 commit / flush。副本沿用原题库的可见性设置。
    """
    bank = source_bank
    if not bank:
        raise ValueError("源题库不存在")

    new_bank = QuestionBank(
        bank_name=(new_name or copy_suffix_name(bank.bank_name))[:100],
        subject=bank.subject,
        description=bank.description,
        cover_image=bank.cover_image,
        total_questions=0,
        status="0",
        user_id=target_user_id,
        is_public=bank.is_public,
        allow_fork=getattr(bank, "allow_fork", 1),
    )
    db.add(new_bank)
    await db.flush()

    # 深拷贝题目与子题
    q_result = await db.execute(
        select(QuestionMain)
        .options(selectinload(QuestionMain.sub_questions))
        .where(QuestionMain.bank_id == bank.id)
        .order_by(QuestionMain.sort_order, QuestionMain.id)
    )
    for q in q_result.scalars().all():
        new_q = QuestionMain(
            bank_id=new_bank.id,
            question_type=q.question_type,
            difficulty=q.difficulty,
            question_text=q.question_text,
            content=q.content,
            options=_copy.deepcopy(q.options),
            answer=q.answer,
            analysis=q.analysis,
            has_sub_questions=q.has_sub_questions,
            sort_order=q.sort_order,
            score=q.score,
            status=q.status,
        )
        db.add(new_q)
        await db.flush()

        for s in (q.sub_questions or []):
            db.add(QuestionSub(
                main_id=new_q.id,
                question_text=s.question_text,
                question_type=s.question_type,
                options=_copy.deepcopy(s.options),
                answer=s.answer,
                analysis=s.analysis,
                sort_order=s.sort_order,
                score=s.score,
            ))

    await db.flush()
    await recalc_bank_total(db, new_bank.id)
    await db.refresh(new_bank)

    return new_bank
