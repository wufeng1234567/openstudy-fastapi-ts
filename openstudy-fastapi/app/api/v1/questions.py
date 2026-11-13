"""
题库/题目 API - 完整实现（对齐 DB 实际 schema）

关键变更:
- 物理删除 + 应用层级联（DB 无 del_flag，与 SpringBoot 一致）
- 字段名对齐 DB: id/subject/description/total_questions/question_text/answer/main_id 等
- 题目排序: ORDER BY sort_order, id
- 子题 CRUD: 全量替换（先 DELETE 再 INSERT）
- 题库总数: COUNT status='0' 重算
- 题库创建: 自动推断科目与描述
"""

import copy

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional
from decimal import Decimal
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.utils.pagination import paginate as paginate_query
from app.models.question import (
    QuestionBank, QuestionMain, QuestionSource, QuestionSub,
    UserBankFavorite, UserQuestionFavorite, UserQuestionError, UserQuestionMarked,
    UserPracticeLog, UserPracticeSession,
)
from app.models.bank_share import BankShare, BankShareReceive
from app.models.user import SysUser
from app.schemas.question import (
    QuestionCreate, QuestionUpdate, QuestionBatchInfoRequest,
    QuestionBankCreate, QuestionBankUpdate,
    ErrorRecordRequest, FavoriteQuestionRequest, FavoriteBankRequest,
    MarkedRequest, BatchCheckRequest, MarkMasteredRequest,
    ErrorRecordUpdate, ErrorRecordCreate,
    FavoriteQuestionUpdate, FavoriteBankUpdate, MarkedUpdate,
    RecordStudyTimeRequest,
    PracticeReportRequest,
)
from app.utils.excel_util import export_to_excel
from app.services.bank_copy_service import copy_bank_to_user
from app.services import question_write_service
from app.services.question_grading_service import grade_question
from datetime import datetime
import json

router = APIRouter()

from .question_helpers import (_infer_subject, _generate_description, _score_to_float, _begin_of_date, _end_of_date, format_bank, format_sub_question, format_question, _format_error_record, _format_favorite_question, _fetch_banks_map, _apply_favorite_question_fields, _format_marked_record, _share_effective, _enrich_share_source, _format_favorite_bank, _fetch_questions_map, _recalc_bank_total, _insert_sub_questions, _shared_bank_ids, _can_view_bank, _is_bank_owner, _visibility_condition, _deny_if_not_owner, _deny_path_owner, _deny_foreign_ids, _is_admin_user, _parse_id_list)
from .question_schemas import QuestionBankSaveRequest
from .question_field_helpers import _apply_favorite_bank_fields, _apply_marked_fields
from .question_export_headers import (
    BANK_HEADERS, QUESTION_HEADERS, FAVORITE_BANK_HEADERS,
    FAVORITE_QUESTION_HEADERS, ERROR_HEADERS, MARKED_HEADERS,
)
from .question_export_rows import (
    bank_rows as export_bank_rows, question_rows, favorite_bank_rows, favorite_question_rows,
    error_rows, marked_rows, FAVORITE_STATUS_TEXT,
)
from .question_patch_helpers import _apply_question_fields, _apply_error_optional_fields
from .question_check_formatters import (
    check_question_payload, check_user_payload, check_question_and_user_payload,
)
from .question_lookup_formatters import (
    simple_question_info_payload, favorite_bank_exists_payload, favorite_question_payload,
)
from .question_list_filters import apply_favorite_bank_filters, apply_favorite_question_filters
from .question_batch_check import batch_check_result
from .question_query_scope import apply_owner_scope
from .question_record_filters import apply_error_filters, apply_marked_filters
from .question_query_builders import bank_by_id_query, question_by_id_query, user_id_query


# ========== 辅助函数 ==========

# ========== 题库 API

@router.get("/questionBank/questionBank/list")
async def list_banks(
    bankName: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    subject: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    userId: Optional[int] = Query(None),
    beginTime: Optional[str] = Query(None),
    endTime: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题库列表（status='0' 为正常，status='1' 为停用）"""
    query = select(QuestionBank)

    if bankName:
        query = query.where(QuestionBank.bank_name.ilike(f"%{bankName}%"))
    if status:
        query = query.where(QuestionBank.status == status)
    # category 向后兼容，映射到 subject
    subject_filter = subject or category
    if subject_filter:
        query = query.where(QuestionBank.subject == subject_filter)
    if userId:
        query = query.where(QuestionBank.user_id == userId)
    # beginTime/endTime 后台传的是 YYYY-MM-DD，补全时分秒，保证 endTime 含当天
    if beginTime:
        query = query.where(QuestionBank.create_time >= _begin_of_date(beginTime))
    if endTime:
        query = query.where(QuestionBank.create_time <= _end_of_date(endTime))

    # 可见性：别人的私密题库不出现在列表里（分享给我的除外）
    query = query.where(await _visibility_condition(db, current_user.get("user_id")))

    # 分页
    total, banks = await paginate_query(
        db,
        query.order_by(QuestionBank.create_time.desc()),
        page_num=pageNum,
        page_size=pageSize,
    )
    banks = list(banks)

    return paginate(total, [format_bank(b) for b in banks])


@router.get("/questionBank/questionBank/all")
async def list_all_banks(
    bankName: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    onlyPublic: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询所有题库（不分页）

    :param onlyPublic: 传入 true 时只返回**公开题库**（供前台「题库练习」使用）。
        私有题库即使属于自己、或已分享给自己，也不应出现在公开题库广场。
        不传则沿用「公开 OR 自己的 OR 分享给我的」可见性规则（后台管理/名称映射用）。
    """
    query = select(QuestionBank)

    if bankName:
        query = query.where(QuestionBank.bank_name.ilike(f"%{bankName}%"))
    if status:
        query = query.where(QuestionBank.status == status)

    if onlyPublic:
        # 公开题库广场：只认 is_public == 0（0=公开，1=私有）
        query = query.where(QuestionBank.is_public == 0)
    else:
        # 可见性：别人的私密题库不出现（分享给我的除外）
        query = query.where(await _visibility_condition(db, current_user.get("user_id")))

    query = query.order_by(QuestionBank.create_time.desc())
    result = await db.execute(query)
    banks = list(result.scalars().all())

    return success([format_bank(b) for b in banks])


@router.get("/questionBank/questionBank/my")
async def my_banks(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的题库"""
    user_id = current_user.get("user_id")
    query = select(QuestionBank).where(
        QuestionBank.user_id == user_id,
        QuestionBank.status == "0",
    ).order_by(QuestionBank.create_time.desc())

    result = await db.execute(query)
    banks = list(result.scalars().all())

    return success([format_bank(b) for b in banks])


@router.get("/questionBank/questionBank/{bank_id}")
async def get_bank(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题库详情"""
    query = bank_by_id_query(bank_id)
    result = await db.execute(query)
    bank = result.scalar_one_or_none()

    if not bank:
        return error("题库不存在", code=404)

    # 私密题库：仅题库主或已领取分享者可查看
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题库（私密题库仅作者与已获取分享的用户可见）", code=403)

    return success(format_bank(bank))


@router.post("/questionBank/questionBank")
async def create_bank(
    payload: QuestionBankCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建题库（JSON body，自动推断科目与描述）"""
    user_id = current_user.get("user_id")
    bank_name = payload.bankName
    if not bank_name:
        return error("题库名称不能为空")

    # 智能推断：未传 subject 时自动推断
    final_subject = payload.subject
    if not final_subject:
        final_subject = _infer_subject(bank_name)

    # 智能生成：未传 description 时自动生成
    final_description = payload.description
    if not final_description:
        final_description = _generate_description(bank_name, final_subject)

    bank = QuestionBank(
        bank_name=bank_name,
        subject=final_subject,
        description=final_description,
        cover_image=payload.coverImage,
        is_public=payload.isPublic or 0,
        allow_fork=payload.allowFork if payload.allowFork is not None else 1,
        status=payload.status or "0",
        user_id=user_id,
    )
    db.add(bank)
    await db.flush()
    await db.refresh(bank)

    return success(format_bank(bank))


@router.post("/questionBank/questionBank/createWithReturn")
async def create_bank_with_return(
    payload: QuestionBankCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建题库并返回完整信息（JSON body，自动推断科目与描述）"""
    user_id = current_user.get("user_id")
    bank_name = payload.bankName
    if not bank_name:
        return error("题库名称不能为空")

    final_subject = payload.subject
    if not final_subject:
        final_subject = _infer_subject(bank_name)

    final_description = payload.description
    if not final_description:
        final_description = _generate_description(bank_name, final_subject)

    bank = QuestionBank(
        bank_name=bank_name,
        subject=final_subject,
        description=final_description,
        cover_image=payload.coverImage,
        is_public=payload.isPublic or 0,
        allow_fork=payload.allowFork if payload.allowFork is not None else 1,
        status=payload.status or "0",
        user_id=user_id,
    )
    db.add(bank)
    await db.flush()
    await db.refresh(bank)

    return success(format_bank(bank))


@router.post("/questionBank/questionBank/saveWithQuestions")
async def save_bank_with_questions(
    payload: QuestionBankSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """题库搭建保存：题库 + 题目 + 子题一次事务完成。

    兼容新建与编辑；`deleteQuestionIds` 只允许删除当前题库下的题。
    任何校验/写入异常都会 rollback，返回明确错误，不留半成品。
    """
    uid = current_user.get("user_id")
    if not (payload.bankName or "").strip():
        return error("题库名称不能为空", code=400)
    try:
        if payload.bankId:
            bank = (await db.execute(
                bank_by_id_query(payload.bankId)
            )).scalar_one_or_none()
            if not bank:
                return error("题库不存在", code=404)
            if int(bank.user_id) != int(uid):
                return error("只有题库主才能保存该题库", code=403)
            bank.bank_name = payload.bankName.strip()
            if payload.subject is not None:
                bank.subject = payload.subject
            if payload.description is not None:
                bank.description = payload.description
            if payload.coverImage is not None:
                bank.cover_image = payload.coverImage
            if payload.status is not None:
                bank.status = payload.status or "0"
            if payload.isPublic is not None:
                bank.is_public = int(payload.isPublic)
            if payload.allowFork is not None:
                bank.allow_fork = int(payload.allowFork)
            await db.flush()
        else:
            bank = await question_write_service.create_bank(
                db,
                user_id=uid,
                bank_name=payload.bankName.strip(),
                subject=payload.subject,
                description=payload.description,
                cover_image=payload.coverImage,
                is_public=payload.isPublic,
                allow_fork=payload.allowFork,
                status=payload.status or "0",
            )

        existing = list((await db.execute(
            select(QuestionMain).where(QuestionMain.bank_id == bank.id)
        )).scalars().all())
        existing_map = {int(q.id): q for q in existing}

        # 显式删除：必须先确认所有 id 都属于当前题库，避免借保存删别人的题
        delete_ids = [int(x) for x in (payload.deleteQuestionIds or [])]
        foreign = [x for x in delete_ids if x not in existing_map]
        if foreign:
            return error("只能删除当前题库下的题目", code=403)

        kept_ids = set()
        for idx, item in enumerate(payload.questions or []):
            qid = item.get("id") or item.get("questionId") or item.get("backendId")
            qtext = str(item.get("questionText") or item.get("title") or "").strip()
            if not qtext:
                raise ValueError(f"第 {idx + 1} 题题干不能为空")
            qtype = int(item.get("questionType") or 1)
            subs = item.get("questionSubList") or item.get("subQuestions") or []
            if qid:
                qid = int(qid)
                question = existing_map.get(qid)
                if not question:
                    raise ValueError(f"题目 {qid} 不属于当前题库")
                question.question_type = qtype
                question.difficulty = int(item.get("difficulty") or 2)
                question.question_text = qtext
                question.content = item.get("content")
                question.options = item.get("options")
                question.answer = str(item.get("answer") or "")
                question.analysis = item.get("questionAnalysis") or item.get("analysis")
                question.has_sub_questions = 1 if subs else 0
                question.sort_order = int(item.get("sortOrder") if item.get("sortOrder") is not None else idx)
                question.score = item.get("score") or 0
                question.status = str(item.get("status") or "0")
                await db.execute(delete(QuestionSub).where(QuestionSub.main_id == qid))
                if subs:
                    await question_write_service.insert_sub_questions(db, qid, subs)
                kept_ids.add(qid)
            else:
                question = await question_write_service.create_question(
                    db,
                    bank_id=bank.id,
                    question_type=qtype,
                    question_text=qtext,
                    answer=str(item.get("answer") or ""),
                    options=item.get("options"),
                    analysis=item.get("questionAnalysis") or item.get("analysis"),
                    content=item.get("content"),
                    difficulty=int(item.get("difficulty") or 2),
                    score=item.get("score") or 0,
                    sort_order=int(item.get("sortOrder") if item.get("sortOrder") is not None else idx),
                    sub_questions=subs,
                    recalc_total=False,
                )
                kept_ids.add(int(question.id))

        if delete_ids:
            await db.execute(delete(QuestionSub).where(QuestionSub.main_id.in_(delete_ids)))
            await db.execute(delete(QuestionSource).where(QuestionSource.question_id.in_(delete_ids)))
            await db.execute(delete(UserQuestionFavorite).where(UserQuestionFavorite.question_id.in_(delete_ids)))
            await db.execute(delete(UserQuestionError).where(UserQuestionError.question_id.in_(delete_ids)))
            await db.execute(delete(UserQuestionMarked).where(UserQuestionMarked.question_id.in_(delete_ids)))
            from app.models.note_question import NoteQuestion
            await db.execute(delete(NoteQuestion).where(NoteQuestion.question_id.in_(delete_ids)))
            await db.execute(delete(QuestionMain).where(
                QuestionMain.id.in_(delete_ids), QuestionMain.bank_id == bank.id
            ))
        # 题库里原有的题如果既没出现在本次保存里、也没显式删除，视为保留
        await question_write_service.recalc_bank_total(db, bank.id)
        await db.flush()
        await db.refresh(bank)
        return success(format_bank(bank), "保存成功")
    except Exception as e:  # noqa: BLE001 - 保存是事务边界，统一回滚并回显原因
        await db.rollback()
        return error(f"保存失败，已回滚：{str(e)[:300]}", code=400)


@router.post("/questionBank/questionBank/copy/{bank_id}")
async def copy_bank(
    bank_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """复制题库为当前用户的新题库（深拷贝题库 + 题目 + 子题）

    - 用于「分享来的题库」二次编辑：复制后 user_id=自己，可自由修改
    - 副本默认沿用原题库的可见性；可在 body 传 bankName 自定义名称
    - 只复制题目本身，不带入错题/收藏/笔记等个人数据
    """
    user_id = current_user.get("user_id")

    src_result = await db.execute(bank_by_id_query(bank_id))
    bank = src_result.scalar_one_or_none()
    if not bank:
        return error("题库不存在")
    if not await _can_view_bank(db, bank, user_id):
        return error("无权复制该题库", code=403)

    # 非题库主复制时，校验题库主的「允许他人复制」开关
    if bank.user_id != user_id and not getattr(bank, "allow_fork", 1):
        return error("题库主未开放复制", code=403)

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    new_bank = await copy_bank_to_user(
        db,
        bank,
        user_id,
        new_name=(body.get("bankName") or None),
    )

    return success(format_bank(new_bank))


@router.put("/questionBank/questionBank")
async def update_bank(
    payload: QuestionBankUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新题库（JSON body）"""
    if not payload.bankId:
        return error("题库ID不能为空")

    query = bank_by_id_query(payload.bankId)
    result = await db.execute(query)
    bank = result.scalar_one_or_none()

    if not bank:
        return error("题库不存在")

    if bank.user_id != current_user.get("user_id"):
        return error("只有题库主才能修改该题库", code=403)

    if payload.bankName is not None:
        bank.bank_name = payload.bankName
    if payload.description is not None:
        bank.description = payload.description
    if payload.coverImage is not None:
        bank.cover_image = payload.coverImage
    if payload.subject is not None:
        bank.subject = payload.subject
    if payload.isPublic is not None:
        bank.is_public = payload.isPublic
    if payload.allowFork is not None:
        bank.allow_fork = payload.allowFork
    if payload.status is not None:
        bank.status = payload.status

    return success()


@router.delete("/questionBank/questionBank/{bank_ids}")
async def delete_banks(
    bank_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除题库（物理删除 + 应用层级联）

    级联顺序：
    1. 收集受影响题目 ID
    2. 物理删除子题
    3. 物理删除 user_question_favorite/error/marked
    4. 物理删除 user_bank_favorite
    5. 物理删除题目
    6. 物理删除题库
    """
    ids = [int(x) for x in bank_ids.split(",")]

    # 权限：只能删除自己的题库
    user_id = current_user.get("user_id")
    owners_result = await db.execute(
        select(func.count()).where(
            QuestionBank.id.in_(ids),
            QuestionBank.user_id != user_id,
        )
    )
    # owners_result 已是 execute() 的结果集，只能对其调用 .scalar()；
    # 不能再传给 db.scalar()（该方法只接受 SQL 语句/text()）
    if owners_result.scalar() or 0:
        return error("只能删除自己的题库", code=403)

    # 1. 收集受影响题目 ID
    q_id_query = select(QuestionMain.id).where(QuestionMain.bank_id.in_(ids))
    q_id_result = await db.execute(q_id_query)
    question_ids = [row[0] for row in q_id_result.all()]

    # 题库删除后练习流水/成绩也一并清理，避免统计继续计入已删题库
    await db.execute(delete(UserPracticeLog).where(UserPracticeLog.bank_id.in_(ids)))
    await db.execute(delete(UserPracticeSession).where(UserPracticeSession.bank_id.in_(ids)))

    if question_ids:
        # 2. 物理删除子题
        await db.execute(delete(QuestionSub).where(QuestionSub.main_id.in_(question_ids)))
        # 3. 物理删除用户题目关联
        await db.execute(delete(UserQuestionFavorite).where(UserQuestionFavorite.question_id.in_(question_ids)))
        await db.execute(delete(UserQuestionError).where(UserQuestionError.question_id.in_(question_ids)))
        await db.execute(delete(UserQuestionMarked).where(UserQuestionMarked.question_id.in_(question_ids)))
        # 物理删除笔记-题目关联
        from app.models.note_question import NoteQuestion
        await db.execute(delete(NoteQuestion).where(NoteQuestion.question_id.in_(question_ids)))

    # 4. 物理删除用户题库收藏
    await db.execute(delete(UserBankFavorite).where(UserBankFavorite.bank_id.in_(ids)))
    # 物理删除笔记-题库关联
    from app.models.note_question_bank import NoteQuestionBank
    await db.execute(delete(NoteQuestionBank).where(NoteQuestionBank.question_bank_id.in_(ids)))

    # 物理删除分享与领取记录（题库已删除，分享自然失效）
    await db.execute(delete(BankShareReceive).where(BankShareReceive.bank_id.in_(ids)))
    await db.execute(delete(BankShare).where(BankShare.bank_id.in_(ids)))

    # 5. 物理删除题目
    if question_ids:
        await db.execute(delete(QuestionMain).where(QuestionMain.id.in_(question_ids)))

    # 6. 物理删除题库
    await db.execute(delete(QuestionBank).where(QuestionBank.id.in_(ids)))

    return success()


@router.post("/questionBank/questionBank/export")
async def export_banks(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出题库列表为 Excel"""
    query = select(QuestionBank).where(QuestionBank.status == "0")
    # 可见性：与列表接口同口径，别人的私密题库不入导出
    query = query.where(await _visibility_condition(db, current_user.get("user_id")))
    query = query.order_by(QuestionBank.create_time.desc())
    result = await db.execute(query)
    banks = list(result.scalars().all())

    rows = export_bank_rows(banks)

    headers = BANK_HEADERS

    return export_to_excel(rows, headers, "questionBank")


# ========== 题目 API ==========

@router.get("/questionMain/questionMain/list")
async def list_questions(
    bankId: Optional[int] = Query(None),
    questionType: Optional[int] = Query(None),
    difficulty: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    beginTime: Optional[str] = Query(None),
    endTime: Optional[str] = Query(None),
    ownedOnly: bool = Query(False, description="只返回当前用户自己题库下的题目（可编辑）"),
    withAnswer: bool = Query(False, description="后台编辑页传 true；公开浏览默认脱敏"),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题目列表（按 sort_order, id 排序）"""
    if bankId:
        bank_row = await db.execute(bank_by_id_query(bankId))
        bank_obj = bank_row.scalar_one_or_none()
        if bank_obj and not await _can_view_bank(db, bank_obj, current_user.get("user_id")):
            return error("无权访问该题库的题目", code=403)

    # JOIN 题库 + 可见性条件：无 bankId 的列表同样不得泄露私密题库的题目
    # （公开 OR 自己的 OR 分享给我的，与 _can_view_bank 同一套口径）
    base = select(QuestionMain).join(
        QuestionBank, QuestionMain.bank_id == QuestionBank.id
    ).where(await _visibility_condition(db, current_user.get("user_id")))

    # 资料图片「插入题目」只展示当前用户自己的题目：公开/分享题库中的题目
    # 虽然可见，但 update_question 只允许题库主修改，提前过滤避免用户点进去
    # 才收到“没有权限”。
    if ownedOnly:
        base = base.where(QuestionBank.user_id == current_user.get("user_id"))

    if bankId:
        base = base.where(QuestionMain.bank_id == bankId)
    if questionType:
        base = base.where(QuestionMain.question_type == questionType)
    if difficulty:
        base = base.where(QuestionMain.difficulty == difficulty)
    if status is not None:
        base = base.where(QuestionMain.status == status)
    else:
        base = base.where(QuestionMain.status == "0")
    if keyword:
        base = base.where(QuestionMain.question_text.ilike(f"%{keyword}%"))
    if beginTime:
        base = base.where(QuestionMain.create_time >= _begin_of_date(beginTime))
    if endTime:
        base = base.where(QuestionMain.create_time <= _end_of_date(endTime))

    # 计算总数
    count_query = select(func.count()).select_from(base.subquery())
    total = await db.scalar(count_query)

    # 分页（按 sort_order, id 排序，与 SpringBoot 一致）
    data_query = base.options(selectinload(QuestionMain.sub_questions))
    data_query = data_query.order_by(QuestionMain.sort_order, QuestionMain.id)
    data_query = data_query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(data_query)
    questions = list(result.scalars().all())
    bank_ids = {int(q.bank_id) for q in questions if q.bank_id}
    bank_map = {}
    if bank_ids:
        bank_rows = (
            await db.execute(select(QuestionBank.id, QuestionBank.bank_name, QuestionBank.user_id).where(QuestionBank.id.in_(bank_ids)))
        ).all()
        bank_map = {int(bid): (bname or "", int(owner or 0)) for bid, bname, owner in bank_rows}
    rows = []
    from app.services.question_grading_service import question_payload
    can_reveal_any = _is_admin_user(current_user)
    current_uid = int(current_user.get("user_id") or 0)
    for q in questions:
        bank_name, bank_owner = bank_map.get(int(q.bank_id), ("", 0))
        reveal = bool(withAnswer and (can_reveal_any or bank_owner == current_uid))
        item = format_question(q) if reveal else question_payload(q, reveal=False)
        item["bankName"] = bank_name
        rows.append(item)
    return paginate(total, rows)


@router.get("/questionMain/questionMain/all")
async def list_all_questions(
    bankId: Optional[int] = Query(None),
    questionType: Optional[int] = Query(None),
    withAnswer: bool = Query(False, description="后台编辑页传 true；练习/公开浏览默认脱敏"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询所有题目（不分页）

    `withAnswer=false` 时只返回题干/选项/子题结构，答案与解析完全不下发，
    供练习页在作答前安全加载；作答后由 `/questionPractice/session/*` 返回。
    """
    if bankId:
        bank_row = await db.execute(bank_by_id_query(bankId))
        bank_obj = bank_row.scalar_one_or_none()
        if bank_obj and not await _can_view_bank(db, bank_obj, current_user.get("user_id")):
            return error("无权访问该题库的题目", code=403)

    # JOIN 题库 + 可见性条件：与分页列表同口径，私密题库题目不下发
    base = select(QuestionMain).join(
        QuestionBank, QuestionMain.bank_id == QuestionBank.id
    ).where(QuestionMain.status == "0").where(
        await _visibility_condition(db, current_user.get("user_id"))
    )

    if bankId:
        base = base.where(QuestionMain.bank_id == bankId)
    if questionType:
        base = base.where(QuestionMain.question_type == questionType)

    data_query = base.options(selectinload(QuestionMain.sub_questions))
    data_query = data_query.order_by(QuestionMain.sort_order, QuestionMain.id)
    result = await db.execute(data_query)
    questions = list(result.scalars().all())

    from app.services.question_grading_service import question_payload
    bank_ids = {int(q.bank_id) for q in questions if q.bank_id}
    owners = {}
    if bank_ids:
        rows = (await db.execute(
            select(QuestionBank.id, QuestionBank.user_id).where(QuestionBank.id.in_(bank_ids))
        )).all()
        owners = {int(bid): int(uid or 0) for bid, uid in rows}
    can_reveal_any = _is_admin_user(current_user)
    current_uid = int(current_user.get("user_id") or 0)
    out = []
    for q in questions:
        reveal = bool(withAnswer and (can_reveal_any or owners.get(int(q.bank_id), 0) == current_uid))
        out.append(format_question(q) if reveal else question_payload(q, reveal=False))
    return success(out)


@router.get("/questionMain/questionMain/search")
async def search_questions(
    keyword: Optional[str] = Query(None),
    bankId: Optional[int] = Query(None),
    withAnswer: bool = Query(False),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """搜索题目"""
    # JOIN 题库 + 可见性条件：关键词搜索同样不得命中私密题库的题目
    base = select(QuestionMain).join(
        QuestionBank, QuestionMain.bank_id == QuestionBank.id
    ).where(QuestionMain.status == "0").where(
        await _visibility_condition(db, current_user.get("user_id"))
    )

    if keyword:
        base = base.where(QuestionMain.question_text.ilike(f"%{keyword}%"))
    if bankId:
        base = base.where(QuestionMain.bank_id == bankId)

    count_query = select(func.count()).select_from(base.subquery())
    total = await db.scalar(count_query)

    data_query = base.options(selectinload(QuestionMain.sub_questions))
    data_query = data_query.order_by(QuestionMain.sort_order, QuestionMain.id)
    data_query = data_query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(data_query)
    questions = list(result.scalars().all())
    bank_ids = {int(q.bank_id) for q in questions if q.bank_id}
    bank_map = {}
    if bank_ids:
        bank_rows = (
            await db.execute(select(QuestionBank.id, QuestionBank.bank_name, QuestionBank.user_id).where(QuestionBank.id.in_(bank_ids)))
        ).all()
        bank_map = {int(bid): (bname or "", int(owner or 0)) for bid, bname, owner in bank_rows}
    rows = []
    from app.services.question_grading_service import question_payload
    can_reveal_any = _is_admin_user(current_user)
    current_uid = int(current_user.get("user_id") or 0)
    for q in questions:
        bank_name, bank_owner = bank_map.get(int(q.bank_id), ("", 0))
        reveal = bool(withAnswer and (can_reveal_any or bank_owner == current_uid))
        item = format_question(q) if reveal else question_payload(q, reveal=False)
        item["bankName"] = bank_name
        rows.append(item)
    return paginate(total, rows)


@router.get("/questionMain/questionMain/{question_id}")
async def get_question(
    question_id: int,
    withAnswer: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题目详情（含子题）

    答案/解析只对「题目所属题库的 owner」或管理员下发；公开题库的普通浏览者
    即使直接猜 question_id 也只能拿到题干/选项，不能提前看答案。
    """
    query = select(QuestionMain).options(selectinload(QuestionMain.sub_questions)).where(QuestionMain.id == question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()

    if not question:
        return error("题目不存在", code=404)

    # 可见性：题目归属在题库上，私密题库的题目只对题库主/已领取分享者开放
    bank = (await db.execute(
        bank_by_id_query(question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    can_reveal = bool(
        bank and (
            int(bank.user_id or 0) == int(current_user.get("user_id") or 0)
            or _is_admin_user(current_user)
        )
    )
    if withAnswer and can_reveal:
        return success(format_question(question))
    from app.services.question_grading_service import question_payload
    return success(question_payload(question, reveal=False))


@router.get("/questionMain/questionMain/{question_id}/source")
async def get_question_source_api(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """题目的原文依据：这道题是从哪份资料、哪一段生成的。

    没有锚点（历史题 / 手工录入题）返回 `hasSource=false`，前端据此隐藏按钮，
    绝不伪造一段“原文”。
    """
    uid = int(current_user.get("user_id") or 0)
    try:
        question = (
            await db.execute(question_by_id_query(question_id))
        ).scalar_one_or_none()
        if not question:
            return error("题目不存在", code=404)
        bank = (
            await db.execute(
                bank_by_id_query(question.bank_id)
            )
        ).scalar_one_or_none()
        if not await _can_view_bank(db, bank, uid):
            return error("无权访问该题目（所属题库为私密题库）", code=403)

        source = await question_write_service.get_question_source(
            db,
            user_id=uid,
            question_id=question_id,
        )
        if not source:
            return success({"hasSource": False, "questionId": question_id})
        return success(source)
    except Exception as e:  # noqa: BLE001 - 原文依据是可选展示，不能把整页打成 500
        return error(f"读取原文依据失败：{str(e)[:200]}", code=500)


@router.post("/questionMain/questionMain/recordStudyTime")
async def record_study_time(
    payload: RecordStudyTimeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """记录刷题学习时间（开始刷题时调用，覆盖所有练习模式）"""
    user_id = current_user.get("user_id")
    bank_id = payload.bankId
    question_ids = payload.questionIds
    now = datetime.now()

    # 1. 更新题库收藏的学习时间和次数
    if bank_id:
        fav_query = select(UserBankFavorite).where(
            UserBankFavorite.user_id == user_id,
            UserBankFavorite.bank_id == bank_id,
            UserBankFavorite.favorite_status == 1,
        )
        fav_result = await db.execute(fav_query)
        fav = fav_result.scalar_one_or_none()
        if fav:
            fav.last_study_time = now
            fav.study_count = (fav.study_count or 0) + 1

    # 2. 题目收藏的复习次数只在**真正作答**时累加（见 /questionPractice/report
    #    与练习会话 submit），不能因为“进入题库”就按全库题目 id 批量 +1。

    await db.flush()

    return success({
        "bankStudyTime": now.isoformat(),
        "questionCount": len(question_ids),
    })


@router.post("/questionPractice/report")
async def report_practice(
    payload: PracticeReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """答题上报（兼容旧客户端；判分口径已改为服务端权威）

    ⚠️ 2026-11 起不再采信请求体里的 `isCorrect`：
       - 服务端按 `payload.answer` + 题库标准答案重新判分；
       - 简答题返回 `pending=true`，不写错题本、不污染正确率；
       - 新前端请优先使用 `/questionPractice/session/*`（有会话与成绩快照）。
    """
    user_id = current_user.get("user_id")
    question_id = payload.questionId
    now = datetime.now()

    question = (await db.execute(
        select(QuestionMain).options(selectinload(QuestionMain.sub_questions)).where(QuestionMain.id == question_id)
    )).scalar_one_or_none()
    if not question:
        return error("题目不存在", code=404)

    answer_value = payload.answer
    if isinstance(answer_value, str) and answer_value.strip().startswith(("{", "[")):
        try:
            answer_value = json.loads(answer_value)
        except Exception:
            pass
    if answer_value is None or answer_value == "":
        return error("缺少作答内容，无法服务端判分", code=400)

    grade = grade_question(question, answer_value)
    if grade.get("pending"):
        return success({
            "isCorrect": None,
            "pending": True,
            "errorId": None,
            "correctAnswer": grade.get("correctAnswer"),
            "analysis": grade.get("analysis"),
        })

    is_correct = 1 if grade.get("isCorrect") else 0
    bank_id = payload.bankId if payload.bankId is not None else question.bank_id
    answer_text = payload.answer
    if isinstance(answer_text, (dict, list)):
        answer_text = json.dumps(answer_text, ensure_ascii=False)
    if answer_text is not None and len(str(answer_text)) > 2000:
        answer_text = str(answer_text)[:2000]
    db.add(UserPracticeLog(
        user_id=user_id,
        question_id=question_id,
        bank_id=bank_id,
        is_correct=is_correct,
        answer=answer_text,
        create_time=now,
    ))

    q_fav = (await db.execute(
        select(UserQuestionFavorite).where(
            UserQuestionFavorite.user_id == user_id,
            UserQuestionFavorite.question_id == question_id,
            UserQuestionFavorite.favorite_status == 1,
        )
    )).scalar_one_or_none()
    if q_fav:
        if is_correct:
            q_fav.correct_times = (q_fav.correct_times or 0) + 1
        else:
            q_fav.error_times = (q_fav.error_times or 0) + 1
        q_fav.last_review_time = now
        q_fav.review_count = (q_fav.review_count or 0) + 1

    error_id = None
    if not is_correct:
        err = (await db.execute(
            select(UserQuestionError).where(
                UserQuestionError.user_id == user_id,
                UserQuestionError.question_id == question_id,
            )
        )).scalar_one_or_none()
        if err:
            err.error_count = (err.error_count or 0) + 1
            err.last_error_time = now
            err.status = 1
            err.is_mastered = 0
            _apply_error_optional_fields(err, payload)
            error_id = err.error_id
        else:
            err = UserQuestionError(
                user_id=user_id,
                question_id=question_id,
                bank_id=bank_id,
                error_count=1,
                error_time=now,
                last_error_time=now,
                notes=payload.notes,
                tags=payload.tags,
                difficulty_rating=payload.difficultyRating,
                status=1,
                is_mastered=0,
            )
            db.add(err)
            await db.flush()
            error_id = err.error_id

    await db.flush()
    return success({
        "isCorrect": bool(grade.get("isCorrect")),
        "pending": False,
        "errorId": error_id,
        "correctAnswer": grade.get("correctAnswer"),
        "analysis": grade.get("analysis"),
    })


@router.post("/questionMain/questionMain")
async def create_question(
    payload: QuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建题目（支持子题，JSON body）

    参考 SpringBoot insertQuestionMain:
    1. 插入主题
    2. 遍历 sub_questions 插入子题
    3. 重算题库 total_questions
    """
    # 验证题库是否存在
    bank_query = bank_by_id_query(payload.bankId)
    bank_result = await db.execute(bank_query)
    bank = bank_result.scalar_one_or_none()

    if not bank:
        return error("题库不存在")

    if bank.user_id != current_user.get("user_id"):
        return error("只有题库主才能在该题库下新增题目", code=403)

    # 判断是否有子题
    has_sub = 1 if payload.questionSubList else 0

    question = QuestionMain(
        bank_id=payload.bankId,
        question_type=payload.questionType,
        difficulty=payload.difficulty or 1,
        question_text=payload.questionText,
        content=payload.content,
        options=payload.options,
        answer=payload.answer,
        analysis=payload.questionAnalysis,
        has_sub_questions=has_sub,
        sort_order=payload.sortOrder or 0,
        score=payload.score if payload.score is not None else 0,
        status=payload.status or "0",
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)

    # 插入子题（参考 SpringBoot insertQuestionSub）
    if payload.questionSubList:
        await _insert_sub_questions(db, question.id, payload.questionSubList)

    # 重算题库题目总数（参考 SpringBoot updateBankTotalQuestions）
    await _recalc_bank_total(db, payload.bankId)

    # 显式查询子题（避免 format_question 中 lazy loading 触发 greenlet 错误）
    subs = []
    if payload.questionSubList:
        sub_query = select(QuestionSub).where(QuestionSub.main_id == question.id).order_by(QuestionSub.sort_order, QuestionSub.id)
        sub_result = await db.execute(sub_query)
        subs = list(sub_result.scalars().all())
    return success(format_question(question, subs))


@router.put("/questionMain/questionMain")
async def update_question(
    payload: QuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新题目（支持子题全量替换，JSON body）

    参考 SpringBoot updateQuestionMain:
    1. 记录新旧题库 ID（题库变更时需刷新两个题库总数）
    2. 删除旧子题（DELETE WHERE main_id = id）
    3. 插入新子题
    4. 更新主题
    5. 题库变更时重算新旧题库总数
    """
    query = question_by_id_query(payload.id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()

    if not question:
        return error("题目不存在")

    # 权限：只能改自己题库下的题目
    if not await _is_bank_owner(db, question.bank_id, current_user.get("user_id")):
        return error("只有题库主才能修改题目", code=403)
    if payload.bankId is not None and not await _is_bank_owner(db, payload.bankId, current_user.get("user_id")):
        return error("只能把题目移动到自己的题库", code=403)

    # 记录旧题库 ID（用于题库变更时重算）
    old_bank_id = question.bank_id

    # 更新主题字段
    _apply_question_fields(question, payload)

    # 子题全量替换：先删除旧子题，再插入新子题（与 SpringBoot 一致）
    if payload.questionSubList is not None:
        await db.execute(delete(QuestionSub).where(QuestionSub.main_id == payload.id))
        if payload.questionSubList:
            await _insert_sub_questions(db, payload.id, payload.questionSubList)
            question.has_sub_questions = 1
        else:
            question.has_sub_questions = 0

    # 题库变更/上下架状态变化时重算总数（状态为 '1' 的题不计入 total_questions）
    new_bank_id = payload.bankId
    if new_bank_id is not None and old_bank_id is not None and new_bank_id != old_bank_id:
        await _recalc_bank_total(db, old_bank_id)
        await _recalc_bank_total(db, new_bank_id)
    elif payload.status is not None and old_bank_id is not None:
        await _recalc_bank_total(db, old_bank_id)

    return success()


@router.delete("/questionMain/questionMain/{question_ids}")
async def delete_questions(
    question_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除题目（物理删除 + 应用层级联）

    参考 SpringBoot deleteQuestionMainByIds:
    1. 删除前收集受影响题库 ID
    2. 物理删除子题
    3. 物理删除 user_question_favorite/error/marked
    4. 物理删除题目
    5. 重算受影响题库总数
    """
    ids = [int(x) for x in question_ids.split(",")]

    # 1. 删除前收集受影响题库 ID
    bank_id_query = select(QuestionMain.bank_id).where(QuestionMain.id.in_(ids)).distinct()
    bank_id_result = await db.execute(bank_id_query)
    affected_bank_ids = [row[0] for row in bank_id_result.all()]

    # 题目全部不存在时明确报错，避免静默返回成功
    if not affected_bank_ids:
        return error("题目不存在")

    # 权限：只能删除自己题库下的题目
    user_id = current_user.get("user_id")
    if affected_bank_ids:
        foreign = await db.scalar(
            select(func.count()).where(
                QuestionBank.id.in_(affected_bank_ids),
                QuestionBank.user_id != user_id,
            )
        )
        if foreign:
            return error("只能删除自己题库下的题目", code=403)

    # 2. 物理删除子题
    await db.execute(delete(QuestionSub).where(QuestionSub.main_id.in_(ids)))
    # 3. 物理删除用户题目关联
    await db.execute(delete(UserQuestionFavorite).where(UserQuestionFavorite.question_id.in_(ids)))
    await db.execute(delete(UserQuestionError).where(UserQuestionError.question_id.in_(ids)))
    await db.execute(delete(UserQuestionMarked).where(UserQuestionMarked.question_id.in_(ids)))
    # 物理删除笔记-题目关联
    from app.models.note_question import NoteQuestion
    await db.execute(delete(NoteQuestion).where(NoteQuestion.question_id.in_(ids)))
    # 4. 物理删除题目
    await db.execute(delete(QuestionMain).where(QuestionMain.id.in_(ids)))

    # 5. 重算受影响题库总数
    for bid in affected_bank_ids:
        await _recalc_bank_total(db, bid)

    return success()


@router.get("/questionMain/questionMain/checkExists/{question_id}")
async def check_question_exists(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查题目是否存在（status='0' 为正常）

    返回字段供后台「添加错题记录」自动填充：exists / questionText / bankId / bankName / difficulty
    """
    question = (await db.execute(
        select(QuestionMain).where(
            QuestionMain.id == question_id,
            QuestionMain.status == "0",
        )
    )).scalar_one_or_none()

    if not question:
        return success({"exists": False, "questionId": question_id})

    # 可见性：私密题库的题干不对不可见用户泄露（匿名请求已被 get_current_user 拦下）
    bank = (await db.execute(
        bank_by_id_query(question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    bank_name = bank.bank_name if bank else None

    return success(check_question_payload(question, bank_name))


@router.get("/questionMain/questionMain/checkUserExists/{user_id}")
async def check_user_exists(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查用户是否存在（后台「添加错题记录」校验用户ID用）

    注意：该路由必须存在，否则会落到 catch_all 兜底返回 success(False)，
    前端会误判成「用户ID不存在」。
    登录后才可调用（返回结构不变）：未鉴权时它是一个「用户名/昵称探测」接口。
    """
    from app.models.user import SysUser
    user = (await db.execute(
        select(SysUser).where(
            SysUser.user_id == user_id,
            SysUser.del_flag == "0",
        )
    )).scalar_one_or_none()

    if not user:
        return success({"exists": False, "userId": user_id})

    return success(check_user_payload(user))


@router.get("/questionMain/questionMain/simpleInfo/{question_id}")
async def get_question_simple_info(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取题目简单信息"""
    query = question_by_id_query(question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()

    if not question:
        return error("题目不存在")

    # 可见性：题干/解析属私密题库时不对外泄露
    bank = (await db.execute(
        bank_by_id_query(question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    bank_name = bank.bank_name if bank else None

    return success(simple_question_info_payload(question, bank_name))


@router.get("/questionMain/questionMain/checkQuestionAndUser/{question_id}/{user_id}")
async def check_question_and_user(
    question_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查题目和用户是否存在（返回详情供后台表单自动填充）"""
    from app.models.user import SysUser

    # 检查题目（status='0' 为正常）
    question = (await db.execute(
        select(QuestionMain).where(
            QuestionMain.id == question_id,
            QuestionMain.status == "0",
        )
    )).scalar_one_or_none()
    question_exists = question is not None

    # 可见性：私密题库的题目信息不对不可见用户回填
    if question_exists:
        bank = (await db.execute(
            bank_by_id_query(question.bank_id)
        )).scalar_one_or_none()
        if not await _can_view_bank(db, bank, current_user.get("user_id")):
            return error("无权访问该题目（所属题库为私密题库）", code=403)

    # 检查用户
    user = (await db.execute(
        select(SysUser).where(
            SysUser.user_id == user_id,
            SysUser.del_flag == "0",
        )
    )).scalar_one_or_none()
    user_exists = user is not None

    return success(check_question_and_user_payload(
        question_exists, user_exists, user, user_id, question_id, question
    ))


@router.post("/questionMain/questionMain/batchInfo")
async def batch_question_info(
    payload: QuestionBatchInfoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量获取题目信息

    参考 SpringBoot getQuestionListByIds:
    - 校验：非空、最多 100 个
    - 批量查询题目（status='0'）
    - 批量查 QuestionBank 避免 N+1
    """
    question_ids = payload.questionIds
    if not question_ids:
        return error("题目ID列表不能为空")
    if len(question_ids) > 100:
        return error("最多查询 100 条题目")

    # 批量查询题目
    q_query = select(QuestionMain).options(
        selectinload(QuestionMain.sub_questions)
    ).where(
        QuestionMain.id.in_(question_ids),
        QuestionMain.status == "0",
    ).order_by(QuestionMain.sort_order, QuestionMain.id)
    q_result = await db.execute(q_query)
    questions = list(q_result.scalars().all())

    if not questions:
        return success([])

    # 可见性过滤：私密题库的题目对不可见用户直接过滤（不报错、不泄露）
    bank_ids = list({q.bank_id for q in questions})
    bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
    bank_map = {b.id: b for b in bank_result.scalars().all()}
    user_id = current_user.get("user_id")
    shared_ids = await _shared_bank_ids(db, user_id)
    visible_bank_ids = {
        bid for bid, b in bank_map.items()
        if (not b.is_public) or b.user_id == user_id or bid in shared_ids
    }
    questions = [q for q in questions if q.bank_id in visible_bank_ids]
    if not questions:
        return success([])

    # 组装结果：答案/解析只给题库主/管理员，普通用户批量查题也拿不到答案
    rows = []
    from app.services.question_grading_service import question_payload
    can_reveal_any = _is_admin_user(current_user)
    uid = int(current_user.get("user_id") or 0)
    for q in questions:
        bank = bank_map.get(q.bank_id)
        reveal = bool(can_reveal_any or (bank and int(bank.user_id or 0) == uid))
        row = format_question(q) if reveal else question_payload(q, reveal=False)
        row["bankName"] = bank.bank_name if bank else ""
        rows.append(row)

    return success(rows)


@router.post("/questionMain/questionMain/export")
async def export_questions(
    bankId: Optional[int] = Query(None),
    beginTime: Optional[str] = Query(None),
    endTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出题目列表为 Excel"""
    # JOIN 题库 + 可见性条件：导出内容与列表口径一致，私密题库题目不入 Excel
    query = select(QuestionMain).join(
        QuestionBank, QuestionMain.bank_id == QuestionBank.id
    ).where(QuestionMain.status == "0").where(
        await _visibility_condition(db, current_user.get("user_id"))
    )
    if bankId:
        query = query.where(QuestionMain.bank_id == bankId)
    if beginTime:
        query = query.where(QuestionMain.create_time >= _begin_of_date(beginTime))
    if endTime:
        query = query.where(QuestionMain.create_time <= _end_of_date(endTime))
    query = query.order_by(QuestionMain.sort_order, QuestionMain.id)

    result = await db.execute(query)
    questions = list(result.scalars().all())

    rows = question_rows(questions)

    headers = QUESTION_HEADERS

    return export_to_excel(rows, headers, "questionMain")


# ========== 收藏题库 API ==========

@router.get("/favoriteBank/favoriteBank/list")
async def list_favorite_banks(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    userId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    bankName: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    isStarred: Optional[int] = Query(None),
    favoriteStatus: Optional[int] = Query(None),
    studyCount: Optional[int] = Query(None),
    lastStudyTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询收藏题库列表（后台管理页：支持多条件筛选；管理员可查看/筛选任意用户）

    与前台「我的题库收藏」的区别：管理员不传 userId 时返回全部用户的记录，
    普通用户无论传什么 userId 都只返回自己的。
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)

    query = select(UserBankFavorite)
    query = apply_owner_scope(query, UserBankFavorite, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_favorite_bank_filters(
        query,
        favoriteStatus=favoriteStatus, bankId=bankId, bankName=bankName,
        notes=notes, tags=tags, isStarred=isStarred, studyCount=studyCount,
        lastStudyTime=lastStudyTime
    )

    total, favorites = await paginate_query(
        db,
        query.order_by(UserBankFavorite.create_time.desc()),
        page_num=pageNum,
        page_size=pageSize,
    )
    favorites = list(favorites)

    # 批量获取题库详情（避免 N+1）
    bank_ids = [f.bank_id for f in favorites]
    rows = []
    if bank_ids:
        bank_query = select(QuestionBank).where(QuestionBank.id.in_(bank_ids))
        bank_result = await db.execute(bank_query)
        bank_map = {b.id: b for b in bank_result.scalars().all()}

        for fav in favorites:
            bank = bank_map.get(fav.bank_id)
            if bank:
                rows.append(_format_favorite_bank(fav, bank))

    await _enrich_share_source(db, current_id, rows)

    return paginate(total, rows)


@router.get("/favoriteBank/favoriteBank/all")
async def list_all_favorite_banks(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户所有收藏题库（不分页）"""
    user_id = current_user.get("user_id")
    query = select(UserBankFavorite).where(
        UserBankFavorite.user_id == user_id,
        UserBankFavorite.favorite_status == 1,
    ).order_by(UserBankFavorite.create_time.desc())

    result = await db.execute(query)
    favorites = list(result.scalars().all())

    bank_ids = [f.bank_id for f in favorites]
    rows = []
    if bank_ids:
        bank_query = select(QuestionBank).where(QuestionBank.id.in_(bank_ids))
        bank_result = await db.execute(bank_query)
        bank_map = {b.id: b for b in bank_result.scalars().all()}

        for fav in favorites:
            bank = bank_map.get(fav.bank_id)
            if bank:
                rows.append(_format_favorite_bank(fav, bank))

    await _enrich_share_source(db, user_id, rows)

    return success(rows)


@router.get("/favoriteBank/favoriteBank/check/{bank_id}")
async def check_favorite_bank_exists(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """验证题库是否存在（供后台「新增/修改用户题库收藏」对话框自动填充）

    返回体对齐 SpringBoot 参考版与前端契约：`{exists, bankId, bankName, ...}`。
    历史实现只返回裸布尔 true/false，而前端读的是 `response.data.exists` →
    任何题库ID都会被判成「题库ID不存在，请检查输入」（后台对话框必现）。
    另外参考版只校验「题库是否存在」，不额外限制 status，这里保持一致。
    """
    bank = (await db.execute(
        bank_by_id_query(bank_id)
    )).scalar_one_or_none()

    if not bank:
        return success({"exists": False, "bankId": bank_id})

    return success(favorite_bank_exists_payload(bank))


@router.get("/favoriteBank/favoriteBank/checkFavorite/{user_id}/{bank_id}")
async def check_favorite_bank(
    user_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查指定用户是否已收藏题库

    普通用户只能查自己（路径 uid 不可信）；管理员可查任意用户。
    """
    current_id = current_user.get("user_id")
    if int(user_id) != int(current_id or 0) and not _is_admin_user(current_user):
        return error("无权查看他人的收藏状态", code=403)

    query = select(func.count()).where(
        UserBankFavorite.user_id == user_id,
        UserBankFavorite.bank_id == bank_id,
        UserBankFavorite.favorite_status == 1,
    )
    count = await db.scalar(query)
    return success(count > 0)


@router.post("/favoriteBank/favoriteBank/recordStudy/{bank_id}")
async def record_bank_study(
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """记录题库学习时间（进入题库时自动调用）"""
    user_id = current_user.get("user_id")
    query = select(UserBankFavorite).where(
        UserBankFavorite.user_id == user_id,
        UserBankFavorite.bank_id == bank_id,
        UserBankFavorite.favorite_status == 1,
    )
    result = await db.execute(query)
    fav = result.scalar_one_or_none()
    if not fav:
        return error("收藏记录不存在")

    fav.last_study_time = datetime.now()
    fav.study_count = (fav.study_count or 0) + 1

    return success({
        "lastStudyTime": fav.last_study_time.isoformat(),
        "studyCount": fav.study_count,
    })


@router.post("/favoriteBank/favoriteBank")
async def add_favorite_bank(
    payload: FavoriteBankRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """收藏题库（JSON body）

    - 前台「收藏题库」：不传 userId，数据落在当前登录用户名下
    - 后台「新增用户题库收藏」：管理员可通过 payload.userId 代任意用户录入；
      普通用户传他人 userId 一律 403（防止向他人收藏夹注入数据）
    """
    current_id = current_user.get("user_id")
    if payload.userId is not None and int(payload.userId) != int(current_id or 0) \
            and not _is_admin_user(current_user):
        return error("无权为他人新增收藏记录", code=403)
    user_id = int(payload.userId) if payload.userId is not None else current_id
    bank_id = payload.bankId

    # 目标用户必须存在（否则 FK 约束会在 commit 时抛 IntegrityError → 500）
    target_user = (await db.execute(
        user_id_query(user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户ID %s 不存在，请输入有效的用户ID" % user_id)

    # 检查题库是否存在
    bank_query = bank_by_id_query(bank_id)
    bank_result = await db.execute(bank_query)
    if not bank_result.scalar_one_or_none():
        return error("题库ID %s 不存在，请输入有效的题库ID" % bank_id)

    # 检查是否已收藏
    check_query = select(UserBankFavorite).where(
        UserBankFavorite.user_id == user_id,
        UserBankFavorite.bank_id == bank_id,
    )
    check_result = await db.execute(check_query)
    existing = check_result.scalar_one_or_none()
    if existing:
        if existing.favorite_status == 1:
            return error("该用户已收藏此题库，请不要重复收藏", code=400)
        # 取消收藏后重新收藏：恢复有效并同步后台表单字段
        existing.favorite_status = 1
        _apply_favorite_bank_fields(existing, payload)
        return success({"favoriteId": existing.favorite_id})

    favorite = UserBankFavorite(user_id=user_id, bank_id=bank_id)
    _apply_favorite_bank_fields(favorite, payload)
    db.add(favorite)
    await db.flush()

    return success({"favoriteId": favorite.favorite_id})


@router.put("/favoriteBank/favoriteBank")
async def update_favorite_bank(
    payload: FavoriteBankUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改收藏题库记录（管理员可修改任意用户；普通用户仅限本人）"""
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)

    query = select(UserBankFavorite).where(UserBankFavorite.favorite_id == payload.favoriteId)
    result = await db.execute(query)
    fav = result.scalar_one_or_none()
    if not fav:
        return error("收藏记录不存在")
    if not is_admin:
        denied = _deny_if_not_owner(fav, user_id, "收藏记录")
        if denied:
            return denied

    # 变更归属 / 题库（后台表单里可编辑，仅管理员生效）
    new_user_id = fav.user_id
    new_bank_id = fav.bank_id
    if is_admin:
        if payload.userId is not None:
            new_user_id = int(payload.userId)
        if payload.bankId is not None:
            new_bank_id = int(payload.bankId)

    if new_user_id != fav.user_id or new_bank_id != fav.bank_id:
        owner = (await db.execute(
            user_id_query(new_user_id)
        )).scalar_one_or_none()
        if not owner:
            return error("用户ID %s 不存在，请输入有效的用户ID" % new_user_id)
        bank = (await db.execute(
            select(QuestionBank.id).where(QuestionBank.id == new_bank_id)
        )).scalar_one_or_none()
        if not bank:
            return error("题库ID %s 不存在，请输入有效的题库ID" % new_bank_id)
        # 预检唯一约束 uk_user_bank，避免直接抛 IntegrityError（500）
        dup = (await db.execute(
            select(UserBankFavorite.favorite_id).where(
                UserBankFavorite.user_id == new_user_id,
                UserBankFavorite.bank_id == new_bank_id,
                UserBankFavorite.favorite_id != fav.favorite_id,
            )
        )).first()
        if dup:
            return error("该用户已收藏此题库", code=400)
        fav.user_id = new_user_id
        fav.bank_id = new_bank_id

    _apply_favorite_bank_fields(fav, payload)
    fav.update_time = datetime.now()

    return success()


@router.get("/favoriteBank/favoriteBank/{favorite_id}")
async def get_favorite_bank(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询收藏题库详情（管理员可查看任意用户）"""
    user_id = current_user.get("user_id")
    query = select(UserBankFavorite).where(UserBankFavorite.favorite_id == favorite_id)
    result = await db.execute(query)
    fav = result.scalar_one_or_none()
    if not fav:
        return error("收藏记录不存在")
    if not _is_admin_user(current_user):
        denied = _deny_if_not_owner(fav, user_id, "收藏记录")
        if denied:
            return denied

    bank_query = bank_by_id_query(fav.bank_id)
    bank_result = await db.execute(bank_query)
    bank = bank_result.scalar_one_or_none()
    if not bank:
        return error("题库不存在")

    row = _format_favorite_bank(fav, bank)
    await _enrich_share_source(db, fav.user_id, [row])
    return success(row)


@router.delete("/favoriteBank/favoriteBank/deleteByUserAndBank/{user_id}/{bank_id}")
async def delete_favorite_bank_by_user_and_bank(
    user_id: int,
    bank_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据用户ID和题库ID删除收藏

    普通用户：路径上的 uid 必须等于当前登录用户（防止凭他人 uid 取消他人收藏）
    管理员：可代任意用户删除（后台管理场景）
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    if not is_admin:
        denied = _deny_path_owner(user_id, current_id, "收藏记录")
        if denied:
            return denied
    target_user = int(user_id) if is_admin else current_id

    await db.execute(delete(UserBankFavorite).where(
        UserBankFavorite.user_id == target_user,
        UserBankFavorite.bank_id == bank_id,
    ))

    return success()


@router.delete("/favoriteBank/favoriteBank/{ids}")
async def delete_favorite_banks(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取消收藏题库（管理员可删除任意用户；普通用户仅限本人）"""
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    id_list = _parse_id_list(ids)
    if not id_list:
        return error("收藏ID不能为空", code=400)

    if is_admin:
        await db.execute(delete(UserBankFavorite).where(
            UserBankFavorite.favorite_id.in_(id_list),
        ))
    else:
        denied = await _deny_foreign_ids(
            db, UserBankFavorite, UserBankFavorite.favorite_id, id_list, user_id, "收藏记录")
        if denied:
            return denied
        await db.execute(delete(UserBankFavorite).where(
            UserBankFavorite.favorite_id.in_(id_list),
            UserBankFavorite.user_id == user_id,
        ))

    return success()


@router.post("/favoriteBank/favoriteBank/export")
async def export_favorite_banks(
    userId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    bankName: Optional[str] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    isStarred: Optional[int] = Query(None),
    favoriteStatus: Optional[int] = Query(None),
    studyCount: Optional[int] = Query(None),
    lastStudyTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出收藏题库列表为 Excel（支持与列表页一致的筛选；管理员可导出任意用户）"""
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    query = select(UserBankFavorite)

    query = apply_owner_scope(query, UserBankFavorite, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_favorite_bank_filters(
        query,
        favoriteStatus=favoriteStatus, bankId=bankId, bankName=bankName,
        notes=notes, tags=tags, isStarred=isStarred, studyCount=studyCount,
        lastStudyTime=lastStudyTime
    )

    query = query.order_by(UserBankFavorite.create_time.desc())
    result = await db.execute(query)
    favorites = list(result.scalars().all())

    bank_ids = [f.bank_id for f in favorites]
    bank_map = {}
    if bank_ids:
        bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
        bank_map = {b.id: b for b in bank_result.scalars().all()}

    rows = favorite_bank_rows(favorites, bank_map)

    headers = FAVORITE_BANK_HEADERS

    return export_to_excel(rows, headers, "favoriteBank")


# ========== 收藏题目 API ==========

@router.get("/favoriteQuestion/favoriteQuestion/list")
async def list_favorite_questions(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    difficultyRating: Optional[int] = Query(None),
    errorTimes: Optional[int] = Query(None),
    correctTimes: Optional[int] = Query(None),
    reviewCount: Optional[int] = Query(None),
    isStarred: Optional[int] = Query(None),
    favoriteStatus: Optional[int] = Query(None),
    lastReviewTime: Optional[str] = Query(None),
    nextReviewTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询收藏题目列表（后台管理页：支持多条件筛选；管理员可查看/筛选任意用户）

    与前台「我的题目收藏」的区别：管理员不传 userId 时返回全部用户的记录，
    普通用户无论传什么 userId 都只返回自己的。
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)

    query = select(UserQuestionFavorite)
    query = apply_owner_scope(query, UserQuestionFavorite, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_favorite_question_filters(
        query,
        favoriteStatus=favoriteStatus, questionId=questionId, bankId=bankId,
        notes=notes, tags=tags, difficultyRating=difficultyRating,
        errorTimes=errorTimes, correctTimes=correctTimes, reviewCount=reviewCount,
        isStarred=isStarred, lastReviewTime=lastReviewTime, nextReviewTime=nextReviewTime
    )

    total, favorites = await paginate_query(
        db,
        query.order_by(UserQuestionFavorite.create_time.desc()),
        page_num=pageNum,
        page_size=pageSize,
    )
    favorites = list(favorites)

    # 批量获取题目/题库详情（避免 N+1）
    question_ids = [f.question_id for f in favorites]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
        b_map = await _fetch_banks_map(db, [f.bank_id for f in favorites])

        for fav in favorites:
            question = q_map.get(fav.question_id)
            if question:
                rows.append(_format_favorite_question(fav, question, b_map.get(fav.bank_id)))

    return paginate(total, rows)


@router.get("/favoriteQuestion/favoriteQuestion/all")
async def list_all_favorite_questions(
    bankId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户所有收藏题目（不分页，支持 bankId 筛选）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionFavorite).where(
        UserQuestionFavorite.user_id == user_id,
        UserQuestionFavorite.favorite_status == 1,
    )

    if bankId:
        query = query.where(UserQuestionFavorite.bank_id == bankId)

    query = query.order_by(UserQuestionFavorite.create_time.desc())
    result = await db.execute(query)
    favorites = list(result.scalars().all())

    question_ids = [f.question_id for f in favorites]
    q_map = await _fetch_questions_map(db, question_ids)
    b_map = await _fetch_banks_map(db, [f.bank_id for f in favorites])

    rows = []
    for fav in favorites:
        question = q_map.get(fav.question_id)
        if question:
            rows.append(_format_favorite_question(fav, question, b_map.get(fav.bank_id)))

    return success(rows)


@router.get("/favoriteQuestion/favoriteQuestion/check/{question_id}")
async def check_favorite_question_exists(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """验证题目是否存在（供后台「新增/修改收藏题目」对话框自动填充）

    返回体对齐 SpringBoot 参考版与前端契约：`{exists, questionId, title, bankId, bankName, difficulty}`。
    历史实现只返回裸布尔，而前端读的是 `response.data.exists`（还要用 bankId/bankName 自动填充）
    → 对话框会误报「题目ID不存在，请检查输入」。
    """
    q = (await db.execute(
        question_by_id_query(question_id)
    )).scalar_one_or_none()
    if not q:
        return success({"exists": False, "questionId": question_id})

    bank_name = (await db.execute(
        select(QuestionBank.bank_name).where(QuestionBank.id == q.bank_id)
    )).scalar_one_or_none()
    text = q.question_text or ""
    return success(favorite_question_payload(q, text, bank_name))


@router.get("/favoriteQuestion/favoriteQuestion/checkFavorite/{user_id}/{question_id}")
async def check_favorite_question(
    user_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查指定用户是否已收藏题目

    普通用户只能查自己（路径 uid 不可信）；管理员可查任意用户。
    """
    current_id = current_user.get("user_id")
    if int(user_id) != int(current_id or 0) and not _is_admin_user(current_user):
        return error("无权查看他人的收藏状态", code=403)

    query = select(func.count()).where(
        UserQuestionFavorite.user_id == user_id,
        UserQuestionFavorite.question_id == question_id,
        UserQuestionFavorite.favorite_status == 1,
    )
    count = await db.scalar(query)
    return success(count > 0)


@router.post("/favoriteQuestion/favoriteQuestion")
async def add_favorite_question(
    payload: FavoriteQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """收藏题目（JSON body）

    - 前台「收藏」按钮：不传 userId，数据落在当前登录用户名下
    - 后台「新增用户题目收藏」：管理员可通过 payload.userId 代任意用户录入；
      普通用户传他人 userId 一律 403（防止向他人收藏夹注入数据）
    """
    current_id = current_user.get("user_id")
    if payload.userId is not None and int(payload.userId) != int(current_id or 0) \
            and not _is_admin_user(current_user):
        return error("无权为他人新增收藏记录", code=403)
    user_id = int(payload.userId) if payload.userId is not None else current_id
    question_id = payload.questionId

    # 目标用户必须存在（否则 FK 约束会在 commit 时抛 IntegrityError → 500）
    target_user = (await db.execute(
        user_id_query(user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户ID %s 不存在，请输入有效的用户ID" % user_id)

    # 获取题目信息（含 bank_id，DB 要求非空）
    q_result = await db.execute(question_by_id_query(question_id))
    question = q_result.scalar_one_or_none()
    if not question:
        return error("题目ID %s 不存在，请输入有效的题目ID" % question_id)

    # 检查是否已收藏
    check_query = select(UserQuestionFavorite).where(
        UserQuestionFavorite.user_id == user_id,
        UserQuestionFavorite.question_id == question_id,
    )
    check_result = await db.execute(check_query)
    existing = check_result.scalar_one_or_none()
    if existing:
        if existing.favorite_status == 1:
            return error("该用户已收藏此题目，请不要重复收藏", code=400)
        # 取消收藏后重新收藏：恢复有效并同步后台表单字段
        existing.favorite_status = 1
        _apply_favorite_question_fields(existing, payload)
        return success({"favoriteId": existing.favorite_id})

    favorite = UserQuestionFavorite(
        user_id=user_id,
        question_id=question_id,
        bank_id=payload.bankId if payload.bankId is not None else question.bank_id,
    )
    _apply_favorite_question_fields(favorite, payload)
    db.add(favorite)
    await db.flush()

    return success({"favoriteId": favorite.favorite_id})


@router.post("/favoriteQuestion/favoriteQuestion/batchCheck")
async def batch_check_favorite_question(
    payload: BatchCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量检查收藏状态

    返回 { questionId(str): bool }
    """
    user_id = current_user.get("user_id")
    if not payload.questionIds:
        return success({})

    query = select(UserQuestionFavorite.question_id).where(
        UserQuestionFavorite.user_id == user_id,
        UserQuestionFavorite.question_id.in_(payload.questionIds),
        UserQuestionFavorite.favorite_status == 1,
    )
    result = await db.execute(query)
    return success(batch_check_result(result.all(), payload.questionIds))


@router.put("/favoriteQuestion/favoriteQuestion")
async def update_favorite_question(
    payload: FavoriteQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改收藏题目记录（管理员可修改任意用户；普通用户仅限本人）"""
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    query = select(UserQuestionFavorite).where(UserQuestionFavorite.favorite_id == payload.favoriteId)
    result = await db.execute(query)
    fav = result.scalar_one_or_none()
    if not fav:
        return error("收藏记录不存在")
    if not is_admin:
        denied = _deny_if_not_owner(fav, user_id, "收藏记录")
        if denied:
            return denied

    # 变更归属 / 题目（后台表单里可编辑，仅管理员生效）
    new_user_id = fav.user_id
    new_question_id = fav.question_id
    if is_admin:
        if payload.userId is not None:
            new_user_id = int(payload.userId)
        if payload.questionId is not None:
            new_question_id = int(payload.questionId)

    if new_user_id != fav.user_id or new_question_id != fav.question_id:
        owner = (await db.execute(
            user_id_query(new_user_id)
        )).scalar_one_or_none()
        if not owner:
            return error("用户ID %s 不存在，请输入有效的用户ID" % new_user_id)
        question = (await db.execute(
            question_by_id_query(new_question_id)
        )).scalar_one_or_none()
        if not question:
            return error("题目ID %s 不存在，请输入有效的题目ID" % new_question_id)
        # 预检唯一约束 uk_uq_favorite，避免直接抛 IntegrityError（500）
        dup = (await db.execute(
            select(UserQuestionFavorite.favorite_id).where(
                UserQuestionFavorite.user_id == new_user_id,
                UserQuestionFavorite.question_id == new_question_id,
                UserQuestionFavorite.favorite_id != fav.favorite_id,
            )
        )).first()
        if dup:
            return error("该用户已收藏此题目", code=400)
        fav.user_id = new_user_id
        fav.question_id = new_question_id
        if payload.bankId is None:
            fav.bank_id = question.bank_id

    _apply_favorite_question_fields(fav, payload)
    fav.update_time = datetime.now()

    return success()


@router.get("/favoriteQuestion/favoriteQuestion/{favorite_id}")
async def get_favorite_question(
    favorite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询收藏题目详情（管理员可查看任意用户）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionFavorite).where(UserQuestionFavorite.favorite_id == favorite_id)
    result = await db.execute(query)
    fav = result.scalar_one_or_none()
    if not fav:
        return error("收藏记录不存在")
    if not _is_admin_user(current_user):
        denied = _deny_if_not_owner(fav, user_id, "收藏记录")
        if denied:
            return denied

    q_map = await _fetch_questions_map(db, [fav.question_id])
    question = q_map.get(fav.question_id)
    if not question:
        return error("题目不存在")

    b_map = await _fetch_banks_map(db, [fav.bank_id])
    return success(_format_favorite_question(fav, question, b_map.get(fav.bank_id)))


@router.delete("/favoriteQuestion/favoriteQuestion/deleteByUserAndQuestion/{user_id}/{question_id}")
async def delete_favorite_question_by_user_and_question(
    user_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据用户ID和题目ID删除收藏

    普通用户：路径上的 uid 必须等于当前登录用户（防止凭他人 uid 取消他人收藏）
    管理员：可代任意用户删除（后台管理场景）
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    if not is_admin:
        denied = _deny_path_owner(user_id, current_id, "收藏记录")
        if denied:
            return denied
    target_user = int(user_id) if is_admin else current_id

    await db.execute(delete(UserQuestionFavorite).where(
        UserQuestionFavorite.user_id == target_user,
        UserQuestionFavorite.question_id == question_id,
    ))

    return success()


@router.delete("/favoriteQuestion/favoriteQuestion/{ids}")
async def delete_favorite_questions(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取消收藏题目（管理员可删除任意用户；普通用户仅限本人）"""
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    id_list = _parse_id_list(ids)
    if not id_list:
        return error("收藏ID不能为空", code=400)

    if is_admin:
        await db.execute(delete(UserQuestionFavorite).where(
            UserQuestionFavorite.favorite_id.in_(id_list),
        ))
    else:
        denied = await _deny_foreign_ids(
            db, UserQuestionFavorite, UserQuestionFavorite.favorite_id, id_list, user_id, "收藏记录")
        if denied:
            return denied
        await db.execute(delete(UserQuestionFavorite).where(
            UserQuestionFavorite.favorite_id.in_(id_list),
            UserQuestionFavorite.user_id == user_id,
        ))

    return success()


@router.post("/favoriteQuestion/favoriteQuestion/export")
async def export_favorite_questions(
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    difficultyRating: Optional[int] = Query(None),
    errorTimes: Optional[int] = Query(None),
    correctTimes: Optional[int] = Query(None),
    reviewCount: Optional[int] = Query(None),
    isStarred: Optional[int] = Query(None),
    favoriteStatus: Optional[int] = Query(None),
    lastReviewTime: Optional[str] = Query(None),
    nextReviewTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出收藏题目列表为 Excel（支持与列表页一致的筛选；管理员可导出任意用户）"""
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    query = select(UserQuestionFavorite)

    query = apply_owner_scope(query, UserQuestionFavorite, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_favorite_question_filters(
        query,
        favoriteStatus=favoriteStatus, questionId=questionId, bankId=bankId,
        notes=notes, tags=tags, difficultyRating=difficultyRating,
        errorTimes=errorTimes, correctTimes=correctTimes, reviewCount=reviewCount,
        isStarred=isStarred, lastReviewTime=lastReviewTime, nextReviewTime=nextReviewTime
    )

    query = query.order_by(UserQuestionFavorite.create_time.desc())
    result = await db.execute(query)
    favorites = list(result.scalars().all())

    question_ids = [f.question_id for f in favorites]
    b_map = await _fetch_banks_map(db, [f.bank_id for f in favorites])
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
        rows = favorite_question_rows(favorites, q_map, b_map, FAVORITE_STATUS_TEXT)

    headers = FAVORITE_QUESTION_HEADERS

    return export_to_excel(rows, headers, "favoriteQuestion")


# ========== 错题本 API ==========

@router.post("/questionError/questionError")
async def create_error_question(
    payload: ErrorRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """新增错题记录（后台管理，JSON body）"""
    current_id = current_user.get("user_id")
    # 只有管理员可以代他人写入；普通用户传了别人的 userId 一律拒绝，防止向他人错题本注入数据
    if payload.userId is not None and int(payload.userId) != int(current_id or 0) \
            and "admin" not in (current_user.get("roles") or []):
        return error("无权为他人新增错题记录", code=403)
    user_id = payload.userId or current_id
    question_id = payload.questionId

    if not question_id:
        return error("题目ID不能为空")

    # 验证题目是否存在
    q_result = await db.execute(question_by_id_query(question_id))
    question = q_result.scalar_one_or_none()
    if not question:
        return error("题目不存在")

    # 防止重复插入：user_id + question_id 上有唯一约束 uk_uq_error，
    # 直接 INSERT 会抛 IntegrityError（500），这里提前拦下并给出明确提示
    dup = (await db.execute(
        select(UserQuestionError.error_id).where(
            UserQuestionError.user_id == user_id,
            UserQuestionError.question_id == question_id,
        )
    )).first()
    if dup:
        return error("该用户已存在此题的错题记录，请改用更新接口", code=400)

    # 解析时间字段
    error_time = None
    if payload.errorTime:
        try:
            error_time = datetime.fromisoformat(payload.errorTime)
        except (ValueError, TypeError):
            pass

    last_error_time = None
    if payload.lastErrorTime:
        try:
            last_error_time = datetime.fromisoformat(payload.lastErrorTime)
        except (ValueError, TypeError):
            pass

    last_review_time = None
    if payload.lastReviewTime:
        try:
            last_review_time = datetime.fromisoformat(payload.lastReviewTime)
        except (ValueError, TypeError):
            pass

    next_review_time = None
    if payload.nextReviewTime:
        try:
            next_review_time = datetime.fromisoformat(payload.nextReviewTime)
        except (ValueError, TypeError):
            pass

    error_record = UserQuestionError(
        user_id=user_id,
        question_id=question_id,
        bank_id=payload.bankId if payload.bankId is not None else question.bank_id,
        error_count=payload.errorCount or 0,
        error_time=error_time or datetime.now(),
        last_error_time=last_error_time or datetime.now(),
        notes=payload.notes,
        tags=payload.tags,
        difficulty_rating=payload.difficultyRating or 3,
        review_count=payload.reviewCount or 0,
        last_review_time=last_review_time,
        next_review_time=next_review_time,
        is_mastered=payload.isMastered or 0,
        status=payload.status if payload.status is not None else 1,
    )
    db.add(error_record)
    await db.flush()

    return success({"errorId": error_record.error_id})


@router.get("/questionError/questionError/list")
async def list_error_questions(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    errorCount: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    difficultyRating: Optional[int] = Query(None),
    isMastered: Optional[int] = Query(None),
    status: Optional[int] = Query(None),
    beginErrorTime: Optional[str] = Query(None),
    endErrorTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询错题列表（支持多条件筛选；管理员可查看/筛选任意用户）"""
    current_id = current_user.get("user_id")
    is_admin = "admin" in (current_user.get("roles") or [])
    query = select(UserQuestionError)

    query = apply_owner_scope(query, UserQuestionError, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_error_filters(
        query,
        status=status, questionId=questionId, bankId=bankId, errorCount=errorCount,
        notes=notes, difficultyRating=difficultyRating, isMastered=isMastered,
        begin_error_time=_begin_of_date(beginErrorTime) if beginErrorTime else None,
        end_error_time=_end_of_date(endErrorTime) if endErrorTime else None,
    )

    total, errors = await paginate_query(
        db,
        query.order_by(UserQuestionError.last_error_time.desc()),
        page_num=pageNum,
        page_size=pageSize,
    )
    errors = list(errors)

    # 批量获取题目详情（避免 N+1）
    question_ids = [e.question_id for e in errors]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)

        for err in errors:
            question = q_map.get(err.question_id)
            if question:
                rows.append(_format_error_record(err, question))

    return paginate(total, rows)


@router.get("/questionError/questionError/all")
async def list_all_error_questions(
    bankId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户所有错题（不分页，支持 bankId 筛选）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionError).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.status == 1,
    )

    if bankId:
        query = query.where(UserQuestionError.bank_id == bankId)

    query = query.order_by(UserQuestionError.last_error_time.desc())
    result = await db.execute(query)
    errors = list(result.scalars().all())

    question_ids = [e.question_id for e in errors]
    q_map = await _fetch_questions_map(db, question_ids)

    rows = []
    for err in errors:
        question = q_map.get(err.question_id)
        if question:
            rows.append(_format_error_record(err, question))

    return success(rows)


@router.get("/questionError/questionError/checkUserErrorExists/{question_id}")
async def check_user_error_exists(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查当前用户对某题的错题记录是否存在"""
    user_id = current_user.get("user_id")
    query = select(func.count()).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.question_id == question_id,
        UserQuestionError.status == 1,
    )
    count = await db.scalar(query)
    return success(count > 0)


@router.post("/questionError/questionError/recordOrUpdateError")
async def record_error(
    payload: ErrorRecordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """记录或更新错题（JSON body，智能记录逻辑）

    1. 已有记录：error_count += 1，last_error_time = now()，更新 notes/tags/difficulty_rating
    2. 无记录：新建，error_count = 1
    3. 传 isMastered=1：标记已掌握 (is_mastered=1, status=0)
    """
    user_id = current_user.get("user_id")
    question_id = payload.questionId

    # 获取题目信息（含 bank_id，DB 要求非空）
    q_result = await db.execute(question_by_id_query(question_id))
    question = q_result.scalar_one_or_none()
    if not question:
        return error("题目不存在")

    # 检查是否已存在
    check_query = select(UserQuestionError).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.question_id == question_id,
    )
    check_result = await db.execute(check_query)
    error_record = check_result.scalar_one_or_none()

    now = datetime.now()
    if error_record:
        # 已有记录：错误次数 +1，更新最近出错时间
        error_record.error_count = (error_record.error_count or 0) + 1
        error_record.last_error_time = now
        # 关键：重新激活。题目被标记「已掌握」(status=0) 后再做错，
        # 必须回到错题本，否则会从错题列表和所有统计里永久消失
        error_record.status = 1
        error_record.is_mastered = 0
        # 更新可选字段（如果传了）
        _apply_error_optional_fields(error_record, payload)
    else:
        # 新建错题记录
        error_record = UserQuestionError(
            user_id=user_id,
            question_id=question_id,
            bank_id=payload.bankId if payload.bankId is not None else question.bank_id,
            error_count=1,
            error_time=now,
            last_error_time=now,
        )
        _apply_error_optional_fields(error_record, payload)
        db.add(error_record)

    # 如果传了 isMastered=1，则标记为已掌握
    if payload.isMastered == 1:
        error_record.is_mastered = 1
        error_record.status = 0

    return success(True)


@router.post("/questionError/questionError/batchCheck")
async def batch_check_error(
    payload: BatchCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量检查错题状态

    返回 { questionId(str): bool }
    """
    user_id = current_user.get("user_id")
    if not payload.questionIds:
        return success({})

    query = select(UserQuestionError.question_id).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.question_id.in_(payload.questionIds),
        UserQuestionError.status == 1,
    )
    result = await db.execute(query)
    return success(batch_check_result(result.all(), payload.questionIds))


@router.post("/questionError/questionError/markMastered")
async def mark_error_mastered(
    payload: MarkMasteredRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记错题为已掌握（is_mastered=1, status=0）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionError).where(
        UserQuestionError.user_id == user_id,
        UserQuestionError.question_id == payload.questionId,
    )
    result = await db.execute(query)
    err = result.scalar_one_or_none()
    if not err:
        return error("错题记录不存在")

    err.is_mastered = 1
    err.status = 0

    return success(True)


@router.put("/questionError/questionError")
async def update_error_question(
    payload: ErrorRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改错题记录（用于标记已掌握等；管理员可修改任意用户）"""
    user_id = current_user.get("user_id")
    is_admin = "admin" in (current_user.get("roles") or [])
    query = select(UserQuestionError).where(UserQuestionError.error_id == payload.errorId)
    result = await db.execute(query)
    err = result.scalar_one_or_none()
    if not err:
        return error("错题记录不存在")
    if not is_admin:
        denied = _deny_if_not_owner(err, user_id, "错题记录")
        if denied:
            return denied

    _apply_error_optional_fields(err, payload)
    if payload.reviewCount is not None:
        err.review_count = payload.reviewCount
    if payload.isMastered is not None:
        err.is_mastered = payload.isMastered
    if payload.status is not None:
        err.status = payload.status

    return success()


@router.get("/questionError/questionError/{error_id}")
async def get_error_question(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询错题详情（管理员可查看任意用户）"""
    user_id = current_user.get("user_id")
    is_admin = "admin" in (current_user.get("roles") or [])
    query = select(UserQuestionError).where(UserQuestionError.error_id == error_id)
    result = await db.execute(query)
    err = result.scalar_one_or_none()
    if not err:
        return error("错题记录不存在")
    if not is_admin:
        denied = _deny_if_not_owner(err, user_id, "错题记录")
        if denied:
            return denied

    q_map = await _fetch_questions_map(db, [err.question_id])
    question = q_map.get(err.question_id)
    if not question:
        return error("题目不存在")

    return success(_format_error_record(err, question))


@router.delete("/questionError/questionError/{ids}")
async def delete_error_questions(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除错题（管理员可删除任意用户）"""
    user_id = current_user.get("user_id")
    is_admin = "admin" in (current_user.get("roles") or [])
    id_list = [int(x) for x in ids.split(",")]
    if is_admin:
        # 管理员：不限制归属，按 id 直接删除
        await db.execute(delete(UserQuestionError).where(
            UserQuestionError.error_id.in_(id_list),
        ))
    else:
        denied = await _deny_foreign_ids(
            db, UserQuestionError, UserQuestionError.error_id, id_list, user_id, "错题记录")
        if denied:
            return denied
        await db.execute(delete(UserQuestionError).where(
            UserQuestionError.error_id.in_(id_list),
            UserQuestionError.user_id == user_id,
        ))

    return success()


@router.post("/questionError/questionError/export")
async def export_errors(
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    errorCount: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    difficultyRating: Optional[int] = Query(None),
    isMastered: Optional[int] = Query(None),
    status: Optional[int] = Query(None),
    beginErrorTime: Optional[str] = Query(None),
    endErrorTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出错题列表为 Excel（支持筛选条件；管理员可导出任意用户）"""
    current_id = current_user.get("user_id")
    is_admin = "admin" in (current_user.get("roles") or [])
    query = select(UserQuestionError)

    query = apply_owner_scope(query, UserQuestionError, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_error_filters(
        query,
        status=status, questionId=questionId, bankId=bankId, errorCount=errorCount,
        notes=notes, difficultyRating=difficultyRating, isMastered=isMastered,
        begin_error_time=beginErrorTime if beginErrorTime else None,
        end_error_time=_end_of_date(endErrorTime) if endErrorTime else None,
    )

    query = query.order_by(UserQuestionError.last_error_time.desc())

    result = await db.execute(query)
    errors = list(result.scalars().all())

    # 批量获取题目信息
    question_ids = [e.question_id for e in errors]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
        rows = error_rows(errors, q_map)

    headers = ERROR_HEADERS

    return export_to_excel(rows, headers, "questionError")


# ========== 斩题 API ==========

@router.get("/questionMarked/questionMarked/list")
async def list_marked_questions(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    markedType: Optional[int] = Query(None),
    difficultyLevel: Optional[int] = Query(None),
    isMastered: Optional[int] = Query(None),
    markedStatus: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    errorTimesBeforeMark: Optional[int] = Query(None),
    reviewCount: Optional[int] = Query(None),
    beginCreateTime: Optional[str] = Query(None),
    endCreateTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询斩题列表（后台管理页：支持多条件筛选；管理员可查看/筛选任意用户）

    与前台「我的斩题」的区别：管理员不传 userId 时返回全部用户的记录，
    普通用户无论传什么 userId 都只返回自己的。
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)

    query = select(UserQuestionMarked)
    query = apply_owner_scope(query, UserQuestionMarked, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_marked_filters(
        query,
        markedStatus=markedStatus, questionId=questionId, bankId=bankId,
        markedType=markedType, difficultyLevel=difficultyLevel, isMastered=isMastered,
        errorTimesBeforeMark=errorTimesBeforeMark, reviewCount=reviewCount,
        notes=notes, tags=tags,
        begin_create_time=_begin_of_date(beginCreateTime) if beginCreateTime else None,
        end_create_time=_end_of_date(endCreateTime) if endCreateTime else None,
    )

    total, marked = await paginate_query(
        db,
        query.order_by(UserQuestionMarked.create_time.desc()),
        page_num=pageNum,
        page_size=pageSize,
    )
    marked = list(marked)

    # 批量获取题目详情（避免 N+1）
    question_ids = [m.question_id for m in marked]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)

        for m in marked:
            question = q_map.get(m.question_id)
            if question:
                rows.append(_format_marked_record(m, question))

    return paginate(total, rows)


@router.get("/questionMarked/questionMarked/all")
async def list_all_marked_questions(
    bankId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询当前用户所有斩题（不分页，支持 bankId 筛选）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionMarked).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.marked_status == 1,
    )

    if bankId:
        query = query.where(UserQuestionMarked.bank_id == bankId)

    query = query.order_by(UserQuestionMarked.create_time.desc())
    result = await db.execute(query)
    marked = list(result.scalars().all())

    question_ids = [m.question_id for m in marked]
    q_map = await _fetch_questions_map(db, question_ids)

    rows = []
    for m in marked:
        question = q_map.get(m.question_id)
        if question:
            rows.append(_format_marked_record(m, question))

    return success(rows)


@router.get("/questionMarked/questionMarked/check")
async def check_marked(
    questionId: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检查题目是否已斩（GET，前端用 params 调用）"""
    user_id = current_user.get("user_id")
    check_query = select(UserQuestionMarked).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.question_id == questionId,
        UserQuestionMarked.marked_status == 1,
    )
    check_result = await db.execute(check_query)
    marked = check_result.scalar_one_or_none()

    return success(marked is not None)


@router.post("/questionMarked/questionMarked")
async def add_marked(
    payload: MarkedRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记题目（斩题，JSON body）

    - 前台「斩题」按钮：不传 userId，数据落在当前登录用户名下
    - 后台「新增用户斩题」：管理员可通过 payload.userId 代任意用户录入；
      普通用户传他人 userId 一律 403（防止向他人斩题本注入数据）
    """
    current_id = current_user.get("user_id")
    if payload.userId is not None and int(payload.userId) != int(current_id or 0) \
            and not _is_admin_user(current_user):
        return error("无权为他人新增斩题记录", code=403)
    user_id = int(payload.userId) if payload.userId is not None else current_id
    question_id = payload.questionId

    # 目标用户必须存在（否则 FK 约束会在 commit 时抛 IntegrityError → 500）
    target_user = (await db.execute(
        user_id_query(user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户不存在")

    # 获取题目信息（含 bank_id，DB 要求非空）
    q_result = await db.execute(question_by_id_query(question_id))
    question = q_result.scalar_one_or_none()
    if not question:
        return error("题目不存在")

    # 检查是否已标记
    check_query = select(UserQuestionMarked).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.question_id == question_id,
    )
    check_result = await db.execute(check_query)
    existing = check_result.scalar_one_or_none()
    if existing:
        if existing.marked_status == 1:
            return error("已标记该题目", code=400)
        # 取消斩题后重新标记：恢复有效并同步后台表单字段
        existing.marked_status = 1
        _apply_marked_fields(existing, payload, question)
        return success({"markedId": existing.marked_id})

    marked = UserQuestionMarked(
        user_id=user_id,
        question_id=question_id,
        bank_id=payload.bankId if payload.bankId is not None else question.bank_id,
    )
    _apply_marked_fields(marked, payload, question)
    db.add(marked)
    await db.flush()

    return success({"markedId": marked.marked_id})


@router.post("/questionMarked/questionMarked/batchCheck")
async def batch_check_marked(
    payload: BatchCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量检查斩题状态

    返回 { questionId(str): bool }
    """
    user_id = current_user.get("user_id")
    if not payload.questionIds:
        return success({})

    query = select(UserQuestionMarked.question_id).where(
        UserQuestionMarked.user_id == user_id,
        UserQuestionMarked.question_id.in_(payload.questionIds),
        UserQuestionMarked.marked_status == 1,
    )
    result = await db.execute(query)
    return success(batch_check_result(result.all(), payload.questionIds))


@router.put("/questionMarked/questionMarked")
async def update_marked_question(
    payload: MarkedUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """修改斩题记录（管理员可修改任意用户；普通用户仅限本人）

    与错题管理 update_error_question 口径一致：
    - 归属校验只有非管理员才做（否则后台「修改」按钮点他人记录必然 403）
    - 后台表单里的字段（错误次数/复习次数/复习时间/掌握状态…）全部落库
    """
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    query = select(UserQuestionMarked).where(UserQuestionMarked.marked_id == payload.markedId)
    result = await db.execute(query)
    m = result.scalar_one_or_none()
    if not m:
        return error("斩题记录不存在")
    if not is_admin:
        denied = _deny_if_not_owner(m, user_id, "斩题记录")
        if denied:
            return denied

    # 变更归属 / 题目（后台表单里可编辑，仅管理员生效）
    new_user_id = m.user_id
    new_question_id = m.question_id
    if is_admin:
        if payload.userId is not None:
            new_user_id = int(payload.userId)
        if payload.questionId is not None:
            new_question_id = int(payload.questionId)

    if new_user_id != m.user_id or new_question_id != m.question_id:
        owner = (await db.execute(
            user_id_query(new_user_id)
        )).scalar_one_or_none()
        if not owner:
            return error("用户不存在")
        question = (await db.execute(
            question_by_id_query(new_question_id)
        )).scalar_one_or_none()
        if not question:
            return error("题目不存在")
        # 预检唯一约束 uk_uq_favorite，避免直接抛 IntegrityError（500）
        dup = (await db.execute(
            select(UserQuestionMarked.marked_id).where(
                UserQuestionMarked.user_id == new_user_id,
                UserQuestionMarked.question_id == new_question_id,
                UserQuestionMarked.marked_id != m.marked_id,
            )
        )).first()
        if dup:
            return error("该用户已存在此题的斩题记录", code=400)
        m.user_id = new_user_id
        m.question_id = new_question_id
        if payload.bankId is None:
            m.bank_id = question.bank_id

    _apply_marked_fields(m, payload)
    m.update_time = datetime.now()

    return success()


@router.get("/questionMarked/questionMarked/{marked_id}")
async def get_marked_question(
    marked_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询斩题详情（管理员可查看任意用户）"""
    user_id = current_user.get("user_id")
    query = select(UserQuestionMarked).where(UserQuestionMarked.marked_id == marked_id)
    result = await db.execute(query)
    m = result.scalar_one_or_none()
    if not m:
        return error("斩题记录不存在")
    if not _is_admin_user(current_user):
        denied = _deny_if_not_owner(m, user_id, "斩题记录")
        if denied:
            return denied

    q_map = await _fetch_questions_map(db, [m.question_id])
    question = q_map.get(m.question_id)
    if not question:
        return error("题目不存在")

    return success(_format_marked_record(m, question))


@router.delete("/questionMarked/questionMarked/deleteByUserAndQuestion/{user_id}/{question_id}")
async def delete_marked_by_user_and_question(
    user_id: int,
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """根据用户ID和题目ID删除斩题

    普通用户：路径上的 uid 必须等于当前登录用户（防止凭他人 uid 取消他人斩题）
    管理员：可代任意用户删除（后台管理场景）
    """
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    if not is_admin:
        denied = _deny_path_owner(user_id, current_id, "斩题记录")
        if denied:
            return denied
    target_user = int(user_id) if is_admin else current_id

    await db.execute(delete(UserQuestionMarked).where(
        UserQuestionMarked.user_id == target_user,
        UserQuestionMarked.question_id == question_id,
    ))

    return success()


@router.delete("/questionMarked/questionMarked/{ids}")
async def delete_marked(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """取消斩题（管理员可删除任意用户；普通用户仅限本人）"""
    user_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    id_list = _parse_id_list(ids)
    if not id_list:
        return error("斩题ID不能为空", code=400)

    if is_admin:
        await db.execute(delete(UserQuestionMarked).where(
            UserQuestionMarked.marked_id.in_(id_list),
        ))
    else:
        denied = await _deny_foreign_ids(
            db, UserQuestionMarked, UserQuestionMarked.marked_id, id_list, user_id, "斩题记录")
        if denied:
            return denied
        await db.execute(delete(UserQuestionMarked).where(
            UserQuestionMarked.marked_id.in_(id_list),
            UserQuestionMarked.user_id == user_id,
        ))

    return success()


@router.post("/questionMarked/questionMarked/export")
async def export_marked(
    userId: Optional[int] = Query(None),
    questionId: Optional[int] = Query(None),
    bankId: Optional[int] = Query(None),
    markedType: Optional[int] = Query(None),
    difficultyLevel: Optional[int] = Query(None),
    isMastered: Optional[int] = Query(None),
    markedStatus: Optional[int] = Query(None),
    notes: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    beginCreateTime: Optional[str] = Query(None),
    endCreateTime: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导出斩题列表为 Excel（支持与列表页一致的筛选；管理员可导出任意用户）"""
    current_id = current_user.get("user_id")
    is_admin = _is_admin_user(current_user)
    query = select(UserQuestionMarked)

    query = apply_owner_scope(query, UserQuestionMarked, is_admin=is_admin, current_id=current_id, user_id=userId)

    query = apply_marked_filters(
        query,
        markedStatus=markedStatus, questionId=questionId, bankId=bankId,
        markedType=markedType, difficultyLevel=difficultyLevel, isMastered=isMastered,
        notes=notes, tags=tags,
        begin_create_time=_begin_of_date(beginCreateTime) if beginCreateTime else None,
        end_create_time=_end_of_date(endCreateTime) if endCreateTime else None,
    )

    query = query.order_by(UserQuestionMarked.create_time.desc())

    result = await db.execute(query)
    marked = list(result.scalars().all())

    question_ids = [m.question_id for m in marked]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
        rows = marked_rows(marked, q_map)

    headers = MARKED_HEADERS

    return export_to_excel(rows, headers, "questionMarked")
