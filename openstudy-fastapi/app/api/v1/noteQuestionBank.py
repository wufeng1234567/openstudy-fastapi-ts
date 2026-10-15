"""
笔记-题库关联 API

实现前端 noteQuestionBank.ts 期望的 8 个端点:
1. GET  /noteQuestionBank/noteQuestionBank/list                       分页查询关联列表
2. GET  /noteQuestionBank/noteQuestionBank/{id}                       查询关联详情
3. POST /noteQuestionBank/noteQuestionBank                            新增关联
4. PUT  /noteQuestionBank/noteQuestionBank                            修改关联
5. DELETE /noteQuestionBank/noteQuestionBank/{id}                     删除关联
6. GET  /noteQuestionBank/noteQuestionBank/byNote/{noteId}            按笔记查关联题库(返回题库详情列表)
7. GET  /noteQuestionBank/noteQuestionBank/byBank/{bankId}            按题库查关联笔记(返回笔记 ID/标题列表)
8. DELETE /noteQuestionBank/noteQuestionBank/note/{noteId}/bank/{bankId}  按笔记+题库删除关联
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.note_question_bank import NoteQuestionBank
from app.models.question import QuestionBank
from app.models.note import Note
from app.api.v1.questions import format_bank

router = APIRouter()


def format_note_bank(link: NoteQuestionBank):
    """格式化关联记录"""
    return {
        "id": link.id,
        "noteId": link.note_id,
        "questionBankId": link.question_bank_id,
        "userId": link.user_id,
        "createTime": link.create_time.isoformat() if link.create_time else None,
    }


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


async def _deny_not_link_owner(db: AsyncSession, link_id, user_id):
    """按关联 id 定位并校验归属"""
    link = (await db.execute(
        select(NoteQuestionBank).where(NoteQuestionBank.id == link_id)
    )).scalar_one_or_none()
    if not link:
        return None, error("关联记录不存在")
    if int(link.user_id or 0) != int(user_id or 0):
        return None, error("无权操作他人的关联记录", code=403)
    return link, None


# ========== 关联 CRUD ==========

@router.get("/noteQuestionBank/noteQuestionBank/list")
async def list_note_question_bank(
    noteId: Optional[int] = Query(None),
    questionBankId: Optional[int] = Query(None),
    userId: Optional[int] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """分页查询笔记-题库关联列表"""
    query = select(NoteQuestionBank)

    if noteId is not None:
        query = query.where(NoteQuestionBank.note_id == noteId)
    if questionBankId is not None:
        query = query.where(NoteQuestionBank.question_bank_id == questionBankId)
    if userId is not None:
        query = query.where(NoteQuestionBank.user_id == userId)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(NoteQuestionBank.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    links = list(result.scalars().all())

    return paginate(total, [format_note_bank(l) for l in links])


@router.get("/noteQuestionBank/noteQuestionBank/byNote/{note_id}")
async def list_banks_by_note(
    note_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按笔记查关联题库(JOIN question_bank，返回题库详情列表；仅笔记作者可见)"""
    # 归属校验：关联题库属于作者的私人整理信息，不对他人暴露（水平越权防护）
    denied = await _deny_not_note_owner(db, note_id, current_user.get("user_id"))
    if denied:
        return denied
    link_query = select(NoteQuestionBank.question_bank_id).where(
        NoteQuestionBank.note_id == note_id,
    )
    link_result = await db.execute(link_query)
    bank_ids = [row[0] for row in link_result.all()]

    if not bank_ids:
        return success([])

    bank_query = select(QuestionBank).where(QuestionBank.id.in_(bank_ids))
    bank_result = await db.execute(bank_query)
    banks = list(bank_result.scalars().all())

    return success([format_bank(b) for b in banks])


@router.get("/noteQuestionBank/noteQuestionBank/byBank/{bank_id}")
async def list_notes_by_bank(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按题库查关联笔记(返回笔记 ID/标题列表)"""
    link_query = select(NoteQuestionBank.note_id).where(
        NoteQuestionBank.question_bank_id == bank_id,
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


@router.get("/noteQuestionBank/noteQuestionBank/{link_id}")
async def get_note_question_bank(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询关联详情"""
    query = select(NoteQuestionBank).where(NoteQuestionBank.id == link_id)
    result = await db.execute(query)
    link = result.scalar_one_or_none()

    if not link:
        return error("关联记录不存在")

    return success(format_note_bank(link))


@router.post("/noteQuestionBank/noteQuestionBank")
async def add_note_question_bank(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增关联(JSON body: {noteId, questionBankId, userId})"""
    body = await _get_body(request)

    note_id = body.get("noteId") or body.get("note_id")
    question_bank_id = body.get("questionBankId") or body.get("question_bank_id")

    if not note_id or not question_bank_id:
        return error("noteId 和 questionBankId 不能为空", code=400)

    user_id = current_user.get("user_id")

    # 归属校验（body 里的 userId 一律不信任）
    denied = await _deny_not_note_owner(db, note_id, user_id)
    if denied:
        return denied

    # 检查是否已存在
    check_query = select(NoteQuestionBank).where(
        NoteQuestionBank.note_id == note_id,
        NoteQuestionBank.question_bank_id == question_bank_id,
    )
    check_result = await db.execute(check_query)
    existing = check_result.scalar_one_or_none()
    if existing:
        return error("关联已存在", code=400)

    link = NoteQuestionBank(
        note_id=note_id,
        question_bank_id=question_bank_id,
        user_id=user_id,
    )
    db.add(link)
    await db.flush()
    await db.refresh(link)

    return success(format_note_bank(link))


@router.put("/noteQuestionBank/noteQuestionBank")
async def update_note_question_bank(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改关联（仅关联归属者可改）"""
    body = await _get_body(request)

    link_id = body.get("id")
    if not link_id:
        return error("id 不能为空", code=400)

    link, err = await _deny_not_link_owner(db, link_id, current_user.get("user_id"))
    if err:
        return err

    note_id = body.get("noteId") or body.get("note_id")
    question_bank_id = body.get("questionBankId") or body.get("question_bank_id")

    if note_id is not None:
        # 目标笔记也必须是自己的
        denied = await _deny_not_note_owner(db, note_id, current_user.get("user_id"))
        if denied:
            return denied
        link.note_id = note_id
    if question_bank_id is not None:
        link.question_bank_id = question_bank_id

    return success()


@router.delete("/noteQuestionBank/noteQuestionBank/{link_id}")
async def delete_note_question_bank(
    link_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据关联 ID 删除（仅关联归属者可删）"""
    link, err = await _deny_not_link_owner(db, link_id, current_user.get("user_id"))
    if err:
        return err
    await db.execute(delete(NoteQuestionBank).where(NoteQuestionBank.id == link_id))
    return success()


@router.delete("/noteQuestionBank/noteQuestionBank/note/{note_id}/bank/{bank_id}")
async def delete_by_note_and_bank(
    note_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """按笔记+题库删除关联（仅笔记作者可删）"""
    denied = await _deny_not_note_owner(db, note_id, current_user.get("user_id"))
    if denied:
        return denied
    await db.execute(delete(NoteQuestionBank).where(
        NoteQuestionBank.note_id == note_id,
        NoteQuestionBank.question_bank_id == bank_id,
    ))
    return success()
