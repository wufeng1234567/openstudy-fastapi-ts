"""
笔记-题目关联 API

实现 6 个端点:
1. POST   /noteQuestion/noteQuestion                              新增关联(JSON body)
2. DELETE /noteQuestion/noteQuestion/note/{noteId}/question/{questionId}  删除关联
3. GET    /noteQuestion/noteQuestion/byNote/{noteId}              按笔记查关联题目(返回题目详情列表)
4. GET    /noteQuestion/noteQuestion/byQuestion/{questionId}      按题目查关联笔记(返回笔记 ID/标题列表)
5. POST   /noteQuestion/noteQuestion/batchLink                    批量关联(JSON body)
6. GET    /noteQuestion/noteQuestion/check/{noteId}/{questionId}  检查是否已关联

新增关联时若传了 questionBankId，自动也关联题库(NoteQuestionBank)。
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.note_question import NoteQuestion
from app.models.note_question_bank import NoteQuestionBank
from app.models.question import QuestionMain
from app.models.note import Note
from app.api.v1.questions import format_question

router = APIRouter()


async def _get_body(request: Request) -> dict:
    """安全读取 JSON body"""
    try:
        return await request.json()
    except Exception:
        return {}


async def _deny_not_note_owner(db: AsyncSession, note_id, user_id):
    """笔记归属校验：只有笔记作者能维护笔记的关联（水平越权防护）"""
    row = (await db.execute(
        select(Note.user_id).where(Note.note_id == note_id, Note.del_flag == "0")
    )).first()
    if not row:
        return error("笔记不存在", code=400)
    if int(row[0] or 0) != int(user_id or 0):
        return error("无权操作他人笔记的关联", code=403)
    return None


async def _ensure_bank_link(db: AsyncSession, note_id: int, question_bank_id: int, user_id: int):
    """确保笔记-题库关联存在(若不存在则创建)"""
    check_query = select(NoteQuestionBank).where(
        NoteQuestionBank.note_id == note_id,
        NoteQuestionBank.question_bank_id == question_bank_id,
    )
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        return

    link = NoteQuestionBank(
        note_id=note_id,
        question_bank_id=question_bank_id,
        user_id=user_id,
    )
    db.add(link)
    await db.flush()


@router.post("/noteQuestion/noteQuestion")
async def add_note_question(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增关联(JSON body: {noteId, questionId, questionBankId, userId})

    若传了 questionBankId，自动也关联题库。
    """
    body = await _get_body(request)

    note_id = body.get("noteId") or body.get("note_id")
    question_id = body.get("questionId") or body.get("question_id")

    if not note_id or not question_id:
        return error("noteId 和 questionId 不能为空", code=400)

    user_id = current_user.get("user_id")

    # 归属校验：只有笔记作者能添加关联（body 里的 userId 一律不信任）
    denied = await _deny_not_note_owner(db, note_id, user_id)
    if denied:
        return denied
    question_bank_id = body.get("questionBankId") or body.get("question_bank_id")

    # 未传 questionBankId 时从题目中推断
    if not question_bank_id:
        q_query = select(QuestionMain).where(QuestionMain.id == question_id)
        q_result = await db.execute(q_query)
        question = q_result.scalar_one_or_none()
        if not question:
            return error("题目不存在")
        question_bank_id = question.bank_id

    # 检查是否已存在
    check_query = select(NoteQuestion).where(
        NoteQuestion.note_id == note_id,
        NoteQuestion.question_id == question_id,
    )
    check_result = await db.execute(check_query)
    if check_result.scalar_one_or_none():
        return error("关联已存在", code=400)

    link = NoteQuestion(
        note_id=note_id,
        question_id=question_id,
        user_id=user_id,
    )
    db.add(link)
    await db.flush()
    # create_time 为库端默认值，flush 后过期；不 refresh 直接序列化会触发 MissingGreenlet
    await db.refresh(link)

    # 笔记-题库的关联信息统一维护在 note_question_bank 表（note_question 表没有该列）
    await _ensure_bank_link(db, note_id, question_bank_id, user_id)

    return success({
        "id": link.id,
        "noteId": link.note_id,
        "questionId": link.question_id,
        "questionBankId": question_bank_id,
        "userId": link.user_id,
        "relationType": link.relation_type,
        "createTime": link.create_time.isoformat() if link.create_time else None,
    })


@router.post("/noteQuestion/noteQuestion/batchLink")
async def batch_link(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量关联(JSON body: {noteId, questionIds: [], questionBankId})"""
    body = await _get_body(request)

    note_id = body.get("noteId") or body.get("note_id")
    question_ids = body.get("questionIds") or body.get("question_ids") or []
    question_bank_id = body.get("questionBankId") or body.get("question_bank_id")

    if not note_id or not question_ids:
        return error("noteId 和 questionIds 不能为空", code=400)

    user_id = current_user.get("user_id")

    # 归属校验
    denied = await _deny_not_note_owner(db, note_id, user_id)
    if denied:
        return denied

    # 查询已存在的关联(避免重复)
    existing_query = select(NoteQuestion.question_id).where(
        NoteQuestion.note_id == note_id,
        NoteQuestion.question_id.in_(question_ids),
    )
    existing_result = await db.execute(existing_query)
    existing_ids = {row[0] for row in existing_result.all()}

    # 需要新建的题目 ID
    new_ids = [qid for qid in question_ids if qid not in existing_ids]

    # 收集每个题目的 bank_id(若未传 questionBankId)
    bank_id_for_question = {}
    if not question_bank_id and new_ids:
        q_query = select(QuestionMain.id, QuestionMain.bank_id).where(
            QuestionMain.id.in_(new_ids),
        )
        q_result = await db.execute(q_query)
        bank_id_for_question = {row[0]: row[1] for row in q_result.all()}

    created_count = 0
    affected_bank_ids = set()
    for qid in new_ids:
        bid = question_bank_id or bank_id_for_question.get(qid)
        if not bid:
            continue
        link = NoteQuestion(
            note_id=note_id,
            question_id=qid,
            user_id=user_id,
        )
        db.add(link)
        created_count += 1
        affected_bank_ids.add(bid)

    if new_ids:
        await db.flush()

    # 自动也关联题库
    for bid in affected_bank_ids:
        await _ensure_bank_link(db, note_id, bid, user_id)

    return success({
        "total": len(question_ids),
        "created": created_count,
        "skipped": len(existing_ids),
    })


@router.delete("/noteQuestion/noteQuestion/note/{note_id}/question/{question_id}")
async def delete_by_note_and_question(
    note_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按笔记+题目删除关联（仅笔记作者可删）"""
    denied = await _deny_not_note_owner(db, note_id, current_user.get("user_id"))
    if denied:
        return denied
    await db.execute(delete(NoteQuestion).where(
        NoteQuestion.note_id == note_id,
        NoteQuestion.question_id == question_id,
    ))
    return success()


@router.get("/noteQuestion/noteQuestion/byNote/{note_id}")
async def list_questions_by_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按笔记查关联题目(返回题目详情列表；仅笔记作者可见)"""
    # 归属校验：关联题目属于作者的私人整理信息，不对他人暴露（水平越权防护）
    denied = await _deny_not_note_owner(db, note_id, current_user.get("user_id"))
    if denied:
        return denied
    link_query = select(NoteQuestion.question_id).where(
        NoteQuestion.note_id == note_id,
    )
    link_result = await db.execute(link_query)
    question_ids = [row[0] for row in link_result.all()]

    if not question_ids:
        return success([])

    q_query = select(QuestionMain).options(
        selectinload(QuestionMain.sub_questions)
    ).where(
        QuestionMain.id.in_(question_ids),
        QuestionMain.status == "0",
    ).order_by(QuestionMain.sort_order, QuestionMain.id)
    q_result = await db.execute(q_query)
    questions = list(q_result.scalars().all())

    return success([format_question(q) for q in questions])


@router.get("/noteQuestion/noteQuestion/byQuestion/{question_id}")
async def list_notes_by_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按题目查关联笔记(返回笔记 ID/标题列表)"""
    link_query = select(NoteQuestion.note_id).where(
        NoteQuestion.question_id == question_id,
    )
    link_result = await db.execute(link_query)
    note_ids = [row[0] for row in link_result.all()]

    if not note_ids:
        return success([])

    note_query = select(Note.note_id, Note.title).where(
        Note.note_id.in_(note_ids),
        Note.del_flag == "0",
    )
    note_result = await db.execute(note_query)
    rows = [
        {"noteId": row[0], "noteTitle": row[1]}
        for row in note_result.all()
    ]

    return success(rows)


@router.get("/noteQuestion/noteQuestion/check/{note_id}/{question_id}")
async def check_note_question(
    note_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查是否已关联"""
    query = select(func.count()).where(
        NoteQuestion.note_id == note_id,
        NoteQuestion.question_id == question_id,
    )
    count = await db.scalar(query)
    return success(count > 0)
