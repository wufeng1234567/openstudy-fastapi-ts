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
from typing import Optional, List
from decimal import Decimal
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.question import (
    QuestionBank, QuestionMain, QuestionSub,
    UserBankFavorite, UserQuestionFavorite, UserQuestionError, UserQuestionMarked,
    UserPracticeLog,
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
from datetime import datetime

router = APIRouter()


# ========== 辅助函数 ==========

def _infer_subject(bank_name: str) -> str:
    """根据题库名自动推断科目

    实现已搬到 `app/services/question_write_service.py` —— AI Agent 建题库时
    也要用同一套推断规则，否则「Agent 建的」和「UI 建的」科目会不一致。
    """
    return question_write_service.infer_subject(bank_name)


def _generate_description(bank_name: str, subject: str) -> str:
    """根据题库名自动生成 10-50 字符描述（实现见 question_write_service）"""
    return question_write_service.generate_description(bank_name, subject)


def _score_to_float(score) -> Optional[float]:
    """Decimal/None -> float"""
    if score is None:
        return None
    if isinstance(score, Decimal):
        return float(score)
    return float(score)


def _begin_of_date(value: str) -> str:
    """后台日期范围传的是 YYYY-MM-DD，补成当天 00:00:00（已是完整时间则原样返回）"""
    return value if len(value) > 10 else f"{value} 00:00:00"


def _end_of_date(value: str) -> str:
    """后台日期范围传的是 YYYY-MM-DD，补成当天 23:59:59，保证 endTime 含当天"""
    return value if len(value) > 10 else f"{value} 23:59:59"


def format_bank(bank):
    """格式化题库数据"""
    return {
        "id": bank.id,
        "bankId": bank.id,
        "bankName": bank.bank_name,
        "subject": bank.subject,
        "description": bank.description,
        # 向后兼容字段
        "bankDescription": bank.description,
        "category": bank.subject,
        "userId": bank.user_id,
        "coverImage": bank.cover_image,
        "totalQuestions": bank.total_questions,
        "questionCount": bank.total_questions,
        "status": bank.status,
        "isPublic": bank.is_public,
        "allowFork": bank.allow_fork if hasattr(bank, "allow_fork") else 1,
        "createTime": bank.create_time.isoformat() if bank.create_time else None,
    }


def format_sub_question(sub):
    """格式化子题数据"""
    return {
        "id": sub.id,
        "subId": sub.id,
        "mainId": sub.main_id,
        "questionText": sub.question_text,
        "questionType": sub.question_type,
        "options": sub.options,
        "answer": sub.answer,
        "analysis": sub.analysis,
        "sortOrder": sub.sort_order,
        "score": _score_to_float(sub.score),
    }


def format_question(q, sub_question_objs=None):
    """格式化题目数据（含子题）"""
    # 子题列表
    sub_list = []
    if sub_question_objs is not None:
        sorted_subs = sorted(sub_question_objs, key=lambda s: (s.sort_order or 0, s.id or 0))
        sub_list = [format_sub_question(s) for s in sorted_subs]
    elif hasattr(q, "sub_questions") and q.sub_questions is not None:
        # 按 sort_order 排序
        sorted_subs = sorted(q.sub_questions, key=lambda s: (s.sort_order or 0, s.id or 0))
        sub_list = [format_sub_question(s) for s in sorted_subs]

    return {
        "id": q.id,
        "questionId": q.id,
        "bankId": q.bank_id,
        "questionType": q.question_type,
        # 题型中文名：与 `question_write_service.QUESTION_TYPE_TEXT` 同源（`_get_question_type_text`
        # 现在只是它的薄封装）。列表接口此前只回数字，任何直接读 `questionTypeText` 的界面都会空白。
        "questionTypeText": _get_question_type_text(q.question_type),
        "questionText": q.question_text,
        # 向后兼容字段
        "questionContent": q.question_text,
        "content": q.content,
        "options": q.options,
        "answer": q.answer,
        "questionAnswer": q.answer,
        "analysis": q.analysis,
        "questionAnalysis": q.analysis,
        "difficulty": q.difficulty,
        "hasSubQuestions": q.has_sub_questions,
        "sortOrder": q.sort_order,
        "score": _score_to_float(q.score),
        "status": q.status,
        "createTime": q.create_time.isoformat() if q.create_time else None,
        "subQuestions": sub_list,
    }


def _format_error_record(err, question):
    """格式化错题记录（含题目信息）"""
    row = format_question(question)
    row["errorId"] = err.error_id
    row["userId"] = err.user_id
    row["errorCount"] = err.error_count
    row["errorTime"] = err.error_time.isoformat() if err.error_time else None
    row["lastErrorTime"] = err.last_error_time.isoformat() if err.last_error_time else None
    row["notes"] = err.notes
    row["tags"] = err.tags
    row["difficultyRating"] = err.difficulty_rating
    row["reviewCount"] = err.review_count
    row["isMastered"] = err.is_mastered
    row["status"] = err.status
    return row


def _format_favorite_question(fav, question, bank=None):
    """格式化收藏题目记录（含题目信息）

    后台「题目收藏」表格有「所属题库」(prop=bankName) 一列，而 format_question 只给 bankId；
    修改对话框还要 difficultyRating，列表要 updateTime —— 都必须在这里补齐，否则页面该列空白。
    """
    row = format_question(question)
    row["favoriteId"] = fav.favorite_id
    row["userId"] = fav.user_id
    row["bankId"] = fav.bank_id
    row["bankName"] = bank.bank_name if bank else None
    row["isStarred"] = fav.is_starred
    row["favoriteStatus"] = fav.favorite_status
    row["notes"] = fav.notes
    row["tags"] = fav.tags
    row["difficultyRating"] = fav.difficulty_rating
    row["reviewCount"] = fav.review_count
    # 练习明细：答题上报（/questionPractice/report）会在收藏记录上累加这两个计数，
    # 前端「收藏题目」列表需要展示答对/答错次数，此前漏返回导致前端恒为 0
    row["correctTimes"] = fav.correct_times
    row["errorTimes"] = fav.error_times
    row["lastReviewTime"] = fav.last_review_time.isoformat() if fav.last_review_time else None
    row["nextReviewTime"] = fav.next_review_time.isoformat() if fav.next_review_time else None
    row["createTime"] = fav.create_time.isoformat() if fav.create_time else None
    row["updateTime"] = fav.update_time.isoformat() if fav.update_time else None
    return row


async def _fetch_banks_map(db: AsyncSession, bank_ids: list) -> dict:
    """批量查询题库，返回 {id: QuestionBank}（避免行级 N+1）"""
    if not bank_ids:
        return {}
    result = await db.execute(select(QuestionBank).where(QuestionBank.id.in_(set(bank_ids))))
    return {b.id: b for b in result.scalars().all()}


def _apply_favorite_question_fields(fav, payload):
    """把请求体里的收藏业务字段写入 ORM 对象（新增/修改/恢复共用）

    只覆盖请求里显式传入的字段，None 表示"不动该字段"，避免误清空。
    """
    if getattr(payload, "notes", None) is not None:
        fav.notes = payload.notes
    if getattr(payload, "tags", None) is not None:
        fav.tags = payload.tags
    if getattr(payload, "difficultyRating", None) is not None:
        fav.difficulty_rating = payload.difficultyRating
    if getattr(payload, "errorTimes", None) is not None:
        fav.error_times = payload.errorTimes
    if getattr(payload, "correctTimes", None) is not None:
        fav.correct_times = payload.correctTimes
    if getattr(payload, "reviewCount", None) is not None:
        fav.review_count = payload.reviewCount
    if getattr(payload, "isStarred", None) is not None:
        fav.is_starred = payload.isStarred
    if getattr(payload, "favoriteStatus", None) is not None:
        fav.favorite_status = payload.favoriteStatus
    if getattr(payload, "lastReviewTime", None) is not None:
        fav.last_review_time = _parse_dt(payload.lastReviewTime) if payload.lastReviewTime else None
    if getattr(payload, "nextReviewTime", None) is not None:
        fav.next_review_time = _parse_dt(payload.nextReviewTime) if payload.nextReviewTime else None
    if getattr(payload, "bankId", None) is not None:
        fav.bank_id = payload.bankId
    return fav


def _format_marked_record(m, question):
    """格式化斩题记录（含题目信息）

    注意：后台「斩题管理」表格要展示 错误次数/复习次数/最后复习 等列，
    修改对话框也要回填这些字段，故这里必须把 user_question_marked 的业务字段全量返回，
    不能只返回 notes/tags/markedType/difficultyLevel。
    """
    row = format_question(question)
    row["markedId"] = m.marked_id
    row["userId"] = m.user_id
    row["bankId"] = m.bank_id
    row["markedType"] = m.marked_type
    row["difficultyLevel"] = m.difficulty_level
    row["errorTimesBeforeMark"] = m.error_times_before_mark
    row["correctTimesBeforeMark"] = m.correct_times_before_mark
    row["reviewCount"] = m.review_count
    row["lastReviewTime"] = m.last_review_time.isoformat() if m.last_review_time else None
    row["nextReviewTime"] = m.next_review_time.isoformat() if m.next_review_time else None
    row["isMastered"] = m.is_mastered
    row["masteryDate"] = m.mastery_date.isoformat() if m.mastery_date else None
    row["markedStatus"] = m.marked_status
    row["notes"] = m.notes
    row["tags"] = m.tags
    row["createTime"] = m.create_time.isoformat() if m.create_time else None
    row["updateTime"] = m.update_time.isoformat() if m.update_time else None
    return row


def _share_effective(share) -> bool:
    """分享是否仍然有效（未撤销 && 未过期）"""
    if not share:
        return False
    if share.status != "0":
        return False
    if share.expire_time and share.expire_time < datetime.now():
        return False
    return True


async def _enrich_share_source(db: AsyncSession, user_id, rows: list):
    """给收藏题库行补充「来自分享」信息：来源 / 分享状态 / 分享者 / 是否可编辑

    非分享来源的收藏：source='self'，可正常取消收藏。
    分享来源的收藏：source='share'，canEdit=False（只读）；分享被撤销或过期时
    shareStatus='invalid'，前端据此打「已失效」标识。
    """
    for r in rows:
        r["source"] = "self"
        r["shareStatus"] = None
        r["shareOwnerName"] = None
        r["canEdit"] = False
        r["canCopy"] = int(r.get("allowFork", 1) or 0) != 0

    if not rows or not user_id:
        return rows

    bank_ids = [r.get("bankId") for r in rows if r.get("bankId")]
    if not bank_ids:
        return rows

    rec_result = await db.execute(
        select(BankShareReceive)
        .where(
            BankShareReceive.receiver_id == user_id,
            BankShareReceive.bank_id.in_(bank_ids),
        )
        .order_by(BankShareReceive.create_time.desc())
    )
    rec_map = {}
    for rec in rec_result.scalars().all():
        rec_map.setdefault(rec.bank_id, rec)
    if not rec_map:
        return rows

    share_result = await db.execute(
        select(BankShare).where(BankShare.id.in_([rec.share_id for rec in rec_map.values()]))
    )
    share_map = {s.id: s for s in share_result.scalars().all()}

    owner_result = await db.execute(
        select(SysUser.user_id, SysUser.nick_name).where(
            SysUser.user_id.in_(list({rec.owner_id for rec in rec_map.values()}))
        )
    )
    owner_map = {row[0]: row[1] for row in owner_result.all()}

    for r in rows:
        rec = rec_map.get(r.get("bankId"))
        if not rec:
            continue
        share = share_map.get(rec.share_id)
        r["source"] = "share"
        r["canEdit"] = False
        r["canCopy"] = int(r.get("allowFork", 1) or 0) != 0
        r["shareOwnerName"] = owner_map.get(rec.owner_id)
        r["shareStatus"] = "valid" if _share_effective(share) else "invalid"

    return rows


def _format_favorite_bank(fav, bank):
    """格式化收藏题库记录（含题库信息）

    注意：后台「题库收藏」表格有「排序」列（prop=sortOrder）与修改对话框的 updateTime，
    故这里必须把 sort_order / update_time 一并返回，否则页面该列永远空白。
    """
    row = format_bank(bank)
    row["favoriteId"] = fav.favorite_id
    row["userId"] = fav.user_id
    row["bankId"] = fav.bank_id
    row["isStarred"] = fav.is_starred
    row["favoriteStatus"] = fav.favorite_status
    row["sortOrder"] = fav.sort_order if fav.sort_order is not None else 0
    row["notes"] = fav.notes
    row["tags"] = fav.tags
    row["createTime"] = fav.create_time.isoformat() if fav.create_time else None
    row["updateTime"] = fav.update_time.isoformat() if fav.update_time else None
    row["lastStudyTime"] = fav.last_study_time.isoformat() if fav.last_study_time else None
    row["studyCount"] = fav.study_count or 0
    return row


async def _fetch_questions_map(db: AsyncSession, question_ids: list) -> dict:
    """批量获取题目并返回 {id: question} 映射"""
    if not question_ids:
        return {}
    q_query = select(QuestionMain).options(selectinload(QuestionMain.sub_questions)).where(QuestionMain.id.in_(question_ids))
    q_result = await db.execute(q_query)
    return {q.id: q for q in q_result.scalars().all()}


def _get_question_type_text(qtype: int) -> str:
    """题型编码转中文

    ⚠️ 单一事实来源 = `question_write_service.QUESTION_TYPE_TEXT`（含 6/7 组合题）。
    原先这里自己维护了一张**残缺副本**（只有 1-6，缺 7「完形填空」，且 6 的文案也不同），
    与 Agent 侧 `question_brief` 的口径不一致 —— 导出/列表会与 Agent 回执说法不同。
    改为直接引用正规表，消除漂移。
    """
    return question_write_service.QUESTION_TYPE_TEXT.get(qtype, "未知")


def _get_marked_type_text(value) -> str:
    """斩题类型编码转中文（与后台页面下拉一致）"""
    type_map = {1: "错题", 2: "难题", 3: "重点", 4: "易错", 5: "技巧"}
    return type_map.get(value, "未知")


def _get_difficulty_text(value) -> str:
    """难度等级编码转中文（与后台页面下拉一致）"""
    type_map = {1: "简单", 2: "中等", 3: "困难", 4: "极难"}
    return type_map.get(value, "未知")


async def _recalc_bank_total(db: AsyncSession, bank_id: int):
    """重算题库题目总数（COUNT status='0' 的题目，与 SpringBoot 一致）

    实现见 `question_write_service.recalc_bank_total`（AI Agent 导入题目后
    也要刷新总数，必须同一套口径）。
    """
    return await question_write_service.recalc_bank_total(db, bank_id)


async def _insert_sub_questions(db: AsyncSession, main_id: int, sub_questions: list):
    """批量插入子题（参考 SpringBoot insertQuestionSub；实现见 question_write_service）"""
    return await question_write_service.insert_sub_questions(db, main_id, sub_questions)


# ========== 权限辅助（分享 = 只读；编辑权只属于题库主） ==========

async def _shared_bank_ids(db: AsyncSession, user_id) -> set:
    """当前用户通过「分享」获取到的题库 ID 集合（含已失效，失效仍可查看）"""
    if not user_id:
        return set()
    result = await db.execute(
        select(BankShareReceive.bank_id).where(BankShareReceive.receiver_id == user_id)
    )
    return {row[0] for row in result.all()}


async def _can_view_bank(db: AsyncSession, bank, user_id) -> bool:
    """题库可见性：公开题库(is_public=0)任何人可看；私密题库仅题库主或已领取分享者可看"""
    if bank is None:
        return False
    if not bank.is_public:
        return True
    if bank.user_id == user_id:
        return True
    return bank.id in await _shared_bank_ids(db, user_id)


async def _is_bank_owner(db: AsyncSession, bank_id, user_id) -> bool:
    """当前用户是否为该题库的题库主"""
    if not bank_id or not user_id:
        return False
    owner = await db.scalar(select(QuestionBank.user_id).where(QuestionBank.id == bank_id))
    return owner is not None and owner == user_id


async def _visibility_condition(db: AsyncSession, user_id):
    """列表查询用的可见性条件：公开 OR 自己的 OR 分享给我的"""
    shared = await _shared_bank_ids(db, user_id)
    cond = QuestionBank.is_public == 0
    cond = cond | (QuestionBank.user_id == user_id)
    if shared:
        cond = cond | QuestionBank.id.in_(list(shared))
    return cond


# ---------------------------------------------------------------- 个人数据归属校验
# 错题 / 斩题 / 收藏 属于「个人学习行为数据」，只能由记录归属者本人操作。
# 这类记录的 id 是全局自增的，若只按 id 定位（如 GET /questionError/questionError/{id}），
# 任何登录用户都能凭 id 读取、篡改甚至删除他人的记录（水平越权）。
# 因此这里统一按「记录自身的 user_id」校验，绝不信任请求体里的 id 或路径上的 uid。

def _deny_if_not_owner(record, user_id, label: str = "记录"):
    """归属校验：返回 None 表示通过，否则返回统一的 403 响应体。"""
    if int(record.user_id or 0) != int(user_id or 0):
        return error("无权访问该%s" % label, code=403)
    return None


def _deny_path_owner(path_user_id, user_id, label: str = "记录"):
    """路径携带 uid 的接口：路径 uid 必须等于当前登录用户，否则一律拒绝。"""
    if int(path_user_id or 0) != int(user_id or 0):
        return error("无权操作他人的%s" % label, code=403)
    return None


async def _deny_foreign_ids(db: AsyncSession, model, id_column, id_list, user_id, label: str = "记录"):
    """批量删除前预检：只要请求里含他人记录 id，就整体拒绝，避免越权删除。

    校验通过后调用方仍需在 delete 语句里带上 user_id 条件（双保险）。
    """
    if not id_list:
        return None
    foreign = await db.scalar(
        select(func.count()).select_from(model).where(
            id_column.in_(id_list),
            model.user_id != user_id,
        )
    )
    if foreign:
        return error("无权删除他人的%s" % label, code=403)
    return None


def _is_admin_user(current_user: dict) -> bool:
    """是否管理员（斩题/收藏/错题等个人数据后台管理共用的口径）"""
    return "admin" in (current_user.get("roles") or [])


def _parse_dt(value):
    """把前端传来的时间字符串解析成 datetime，非法/空值一律返回 None（不抛异常）"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "").replace("T", " "))
    except (ValueError, TypeError):
        return None


def _parse_id_list(ids: str):
    """解析 REST 路径里的逗号分隔 id 串；忽略空段与非法段，避免 int('') 抛 500"""
    out = []
    for x in str(ids).split(","):
        x = x.strip()
        if x.lstrip("-").isdigit():
            out.append(int(x))
    return out


# ========== 题库 API ==========

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

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # 分页
    query = query.order_by(QuestionBank.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    banks = list(result.scalars().all())

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
    query = select(QuestionBank).where(QuestionBank.id == bank_id)
    result = await db.execute(query)
    bank = result.scalar_one_or_none()

    if not bank:
        return error("题库不存在")

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

    src_result = await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
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

    query = select(QuestionBank).where(QuestionBank.id == payload.bankId)
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

    rows = [{
        "id": b.id,
        "bankName": b.bank_name,
        "subject": b.subject,
        "description": b.description,
        "totalQuestions": b.total_questions,
        "isPublic": b.is_public,
        "createTime": b.create_time.isoformat() if b.create_time else "",
    } for b in banks]

    headers = [
        {"key": "id", "label": "题库ID"},
        {"key": "bankName", "label": "题库名称"},
        {"key": "subject", "label": "科目"},
        {"key": "description", "label": "描述"},
        {"key": "totalQuestions", "label": "题目总数"},
        {"key": "isPublic", "label": "是否公开"},
        {"key": "createTime", "label": "创建时间"},
    ]

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
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题目列表（按 sort_order, id 排序）"""
    if bankId:
        bank_row = await db.execute(select(QuestionBank).where(QuestionBank.id == bankId))
        bank_obj = bank_row.scalar_one_or_none()
        if bank_obj and not await _can_view_bank(db, bank_obj, current_user.get("user_id")):
            return error("无权访问该题库的题目", code=403)

    # JOIN 题库 + 可见性条件：无 bankId 的列表同样不得泄露私密题库的题目
    # （公开 OR 自己的 OR 分享给我的，与 _can_view_bank 同一套口径）
    base = select(QuestionMain).join(
        QuestionBank, QuestionMain.bank_id == QuestionBank.id
    ).where(await _visibility_condition(db, current_user.get("user_id")))

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

    return paginate(total, [format_question(q) for q in questions])


@router.get("/questionMain/questionMain/all")
async def list_all_questions(
    bankId: Optional[int] = Query(None),
    questionType: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询所有题目（不分页）"""
    if bankId:
        bank_row = await db.execute(select(QuestionBank).where(QuestionBank.id == bankId))
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

    return success([format_question(q) for q in questions])


@router.get("/questionMain/questionMain/search")
async def search_questions(
    keyword: Optional[str] = Query(None),
    bankId: Optional[int] = Query(None),
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

    return paginate(total, [format_question(q) for q in questions])


@router.get("/questionMain/questionMain/{question_id}")
async def get_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询题目详情（含子题）"""
    query = select(QuestionMain).options(selectinload(QuestionMain.sub_questions)).where(QuestionMain.id == question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()

    if not question:
        return error("题目不存在")

    # 可见性：题目归属在题库上，私密题库的题目只对题库主/已领取分享者开放
    bank = (await db.execute(
        select(QuestionBank).where(QuestionBank.id == question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    return success(format_question(question))


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

    # 2. 更新题目收藏的复习时间
    if question_ids:
        q_fav_query = select(UserQuestionFavorite).where(
            UserQuestionFavorite.user_id == user_id,
            UserQuestionFavorite.question_id.in_(question_ids),
            UserQuestionFavorite.favorite_status == 1,
        )
        q_fav_result = await db.execute(q_fav_query)
        for q_fav in q_fav_result.scalars().all():
            q_fav.last_review_time = now
            q_fav.review_count = (q_fav.review_count or 0) + 1

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
    """答题上报（答对 / 答错都要调用）

    一次调用做三件事：
    1. 写一条答题流水 user_practice_log —— 学习行为统计的唯一数据源
    2. 若该题在「收藏题目」里，累加 correct_times / error_times / review_count（兼容旧字段）
    3. 答错时 upsert 错题记录，并**强制把 status / is_mastered 重置为活跃**：
       「标记已掌握后再做错」的题目必须能回到错题本，否则会永久消失
    """
    user_id = current_user.get("user_id")
    question_id = payload.questionId
    now = datetime.now()

    # 题目必须存在，避免脏数据污染统计
    question = (await db.execute(
        select(QuestionMain).where(QuestionMain.id == question_id)
    )).scalar_one_or_none()
    if not question:
        return error("题目不存在")

    bank_id = payload.bankId if payload.bankId is not None else question.bank_id
    is_correct = 1 if payload.isCorrect else 0

    # 1) 写答题流水
    answer_text = payload.answer
    if answer_text is not None and len(answer_text) > 2000:
        answer_text = answer_text[:2000]
    db.add(UserPracticeLog(
        user_id=user_id,
        question_id=question_id,
        bank_id=bank_id,
        is_correct=is_correct,
        answer=answer_text,
        create_time=now,
    ))

    # 2) 收藏题目计数（老字段保持同步，供错题/收藏页复用）
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

    # 3) 答错 → 错题本 upsert
    error_id = None
    if not payload.isCorrect:
        err = (await db.execute(
            select(UserQuestionError).where(
                UserQuestionError.user_id == user_id,
                UserQuestionError.question_id == question_id,
            )
        )).scalar_one_or_none()
        if err:
            err.error_count = (err.error_count or 0) + 1
            err.last_error_time = now
            # 关键：重新激活（已掌握后再做错，要回到错题本）
            err.status = 1
            err.is_mastered = 0
            if payload.notes is not None:
                err.notes = payload.notes
            if payload.tags is not None:
                err.tags = payload.tags
            if payload.difficultyRating is not None:
                err.difficulty_rating = payload.difficultyRating
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
        "isCorrect": payload.isCorrect,
        "errorId": error_id,
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
    bank_query = select(QuestionBank).where(QuestionBank.id == payload.bankId)
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
    query = select(QuestionMain).where(QuestionMain.id == payload.id)
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
    if payload.bankId is not None:
        question.bank_id = payload.bankId
    if payload.questionType is not None:
        question.question_type = payload.questionType
    if payload.questionText is not None:
        question.question_text = payload.questionText
    if payload.content is not None:
        question.content = payload.content
    if payload.options is not None:
        question.options = payload.options
    if payload.answer is not None:
        question.answer = payload.answer
    if payload.questionAnalysis is not None:
        question.analysis = payload.questionAnalysis
    if payload.difficulty is not None:
        question.difficulty = payload.difficulty
    if payload.sortOrder is not None:
        question.sort_order = payload.sortOrder
    if payload.score is not None:
        question.score = payload.score
    if payload.status is not None:
        question.status = payload.status

    # 子题全量替换：先删除旧子题，再插入新子题（与 SpringBoot 一致）
    if payload.questionSubList is not None:
        await db.execute(delete(QuestionSub).where(QuestionSub.main_id == payload.id))
        if payload.questionSubList:
            await _insert_sub_questions(db, payload.id, payload.questionSubList)
            question.has_sub_questions = 1
        else:
            question.has_sub_questions = 0

    # 题库变更时重算新旧题库总数
    new_bank_id = payload.bankId
    if new_bank_id is not None and old_bank_id is not None and new_bank_id != old_bank_id:
        await _recalc_bank_total(db, old_bank_id)
        await _recalc_bank_total(db, new_bank_id)

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
        select(QuestionBank).where(QuestionBank.id == question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    bank_name = bank.bank_name if bank else None

    return success({
        "exists": True,
        "questionId": question.id,
        "questionText": question.question_text,
        "bankId": question.bank_id,
        "bankName": bank_name,
        "difficulty": question.difficulty,
    })


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

    return success({
        "exists": True,
        "userId": user.user_id,
        "userName": user.user_name,
        "nickName": user.nick_name,
    })


@router.get("/questionMain/questionMain/simpleInfo/{question_id}")
async def get_question_simple_info(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取题目简单信息"""
    query = select(QuestionMain).where(QuestionMain.id == question_id)
    result = await db.execute(query)
    question = result.scalar_one_or_none()

    if not question:
        return error("题目不存在")

    # 可见性：题干/解析属私密题库时不对外泄露
    bank = (await db.execute(
        select(QuestionBank).where(QuestionBank.id == question.bank_id)
    )).scalar_one_or_none()
    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权访问该题目（所属题库为私密题库）", code=403)

    bank_name = bank.bank_name if bank else None

    return success({
        "questionId": question.id,
        "questionText": question.question_text,
        "questionType": question.question_type,
        "bankId": question.bank_id,
        "bankName": bank_name,
        "difficulty": question.difficulty,
        "analysis": question.analysis,
    })


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
            select(QuestionBank).where(QuestionBank.id == question.bank_id)
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

    return success({
        "questionValid": question_exists,
        "questionExists": question_exists,
        "userValid": user_exists,
        "userExists": user_exists,
        "allValid": question_exists and user_exists,
        "userId": user_id,
        "userName": user.user_name if user else None,
        "nickName": user.nick_name if user else None,
        "questionId": question_id,
        "questionText": question.question_text if question else None,
        "bankId": question.bank_id if question else None,
        "difficulty": question.difficulty if question else None,
    })


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

    # 组装结果
    rows = []
    for q in questions:
        row = format_question(q)
        row["bankName"] = bank_map.get(q.bank_id).bank_name
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

    rows = [{
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

    headers = [
        {"key": "id", "label": "题目ID"},
        {"key": "bankId", "label": "题库ID"},
        {"key": "questionType", "label": "题型"},
        {"key": "questionText", "label": "题干"},
        {"key": "options", "label": "选项"},
        {"key": "answer", "label": "答案"},
        {"key": "analysis", "label": "解析"},
        {"key": "difficulty", "label": "难度"},
        {"key": "sortOrder", "label": "排序"},
    ]

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
    if is_admin:
        if userId is not None:
            query = query.where(UserBankFavorite.user_id == userId)
    else:
        query = query.where(UserBankFavorite.user_id == current_id)

    # 默认只看有效收藏，除非显式指定 favoriteStatus（后台可查已失效记录）
    if favoriteStatus is not None:
        query = query.where(UserBankFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserBankFavorite.favorite_status == 1)

    if bankId is not None:
        query = query.where(UserBankFavorite.bank_id == bankId)
    if bankName:
        query = query.where(UserBankFavorite.bank_id.in_(
            select(QuestionBank.id).where(QuestionBank.bank_name.ilike(f"%{bankName}%"))
        ))
    if notes:
        query = query.where(UserBankFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserBankFavorite.tags.ilike(f"%{tags}%"))
    if isStarred is not None:
        query = query.where(UserBankFavorite.is_starred == isStarred)
    if studyCount is not None:
        query = query.where(UserBankFavorite.study_count == studyCount)
    if lastStudyTime:
        query = query.where(
            UserBankFavorite.last_study_time >= _begin_of_date(lastStudyTime),
            UserBankFavorite.last_study_time <= _end_of_date(lastStudyTime),
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserBankFavorite.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    favorites = list(result.scalars().all())

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
        select(QuestionBank).where(QuestionBank.id == bank_id)
    )).scalar_one_or_none()

    if not bank:
        return success({"exists": False, "bankId": bank_id})

    return success({
        "exists": True,
        "bankId": bank.id,
        "bankName": bank.bank_name,
        "description": bank.description,
        "subject": bank.subject,
        "totalQuestions": bank.total_questions,
        "isPublic": bank.is_public,
        "userId": bank.user_id,
    })


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
        select(SysUser.user_id).where(SysUser.user_id == user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户ID %s 不存在，请输入有效的用户ID" % user_id)

    # 检查题库是否存在
    bank_query = select(QuestionBank).where(QuestionBank.id == bank_id)
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


def _apply_favorite_bank_fields(fav, payload):
    """把请求体里的收藏业务字段写入 ORM 对象（新增/修改/恢复共用）

    只覆盖请求里显式传入的字段，None 表示"不动该字段"，避免误清空。
    """
    if getattr(payload, "notes", None) is not None:
        fav.notes = payload.notes
    if getattr(payload, "tags", None) is not None:
        fav.tags = payload.tags
    if getattr(payload, "sortOrder", None) is not None:
        fav.sort_order = payload.sortOrder
    if getattr(payload, "isStarred", None) is not None:
        fav.is_starred = payload.isStarred
    if getattr(payload, "favoriteStatus", None) is not None:
        fav.favorite_status = payload.favoriteStatus
    if getattr(payload, "studyCount", None) is not None:
        fav.study_count = payload.studyCount
    if getattr(payload, "lastStudyTime", None) is not None:
        # 允许传空字符串表示清空
        fav.last_study_time = _parse_dt(payload.lastStudyTime) if payload.lastStudyTime else None
    return fav


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
            select(SysUser.user_id).where(SysUser.user_id == new_user_id)
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

    bank_query = select(QuestionBank).where(QuestionBank.id == fav.bank_id)
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

    if is_admin:
        if userId is not None:
            query = query.where(UserBankFavorite.user_id == userId)
    else:
        query = query.where(UserBankFavorite.user_id == current_id)

    if favoriteStatus is not None:
        query = query.where(UserBankFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserBankFavorite.favorite_status == 1)

    if bankId is not None:
        query = query.where(UserBankFavorite.bank_id == bankId)
    if bankName:
        query = query.where(UserBankFavorite.bank_id.in_(
            select(QuestionBank.id).where(QuestionBank.bank_name.ilike(f"%{bankName}%"))
        ))
    if notes:
        query = query.where(UserBankFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserBankFavorite.tags.ilike(f"%{tags}%"))
    if isStarred is not None:
        query = query.where(UserBankFavorite.is_starred == isStarred)
    if studyCount is not None:
        query = query.where(UserBankFavorite.study_count == studyCount)
    if lastStudyTime:
        query = query.where(
            UserBankFavorite.last_study_time >= _begin_of_date(lastStudyTime),
            UserBankFavorite.last_study_time <= _end_of_date(lastStudyTime),
        )

    query = query.order_by(UserBankFavorite.create_time.desc())
    result = await db.execute(query)
    favorites = list(result.scalars().all())

    bank_ids = [f.bank_id for f in favorites]
    bank_map = {}
    if bank_ids:
        bank_result = await db.execute(select(QuestionBank).where(QuestionBank.id.in_(bank_ids)))
        bank_map = {b.id: b for b in bank_result.scalars().all()}

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

    headers = [
        {"key": "favoriteId", "label": "收藏ID"},
        {"key": "userId", "label": "用户ID"},
        {"key": "bankId", "label": "题库ID"},
        {"key": "bankName", "label": "题库名称"},
        {"key": "subject", "label": "科目"},
        {"key": "notes", "label": "收藏备注"},
        {"key": "tags", "label": "标签"},
        {"key": "sortOrder", "label": "排序"},
        {"key": "isStarred", "label": "是否标星"},
        {"key": "lastStudyTime", "label": "最后学习时间"},
        {"key": "studyCount", "label": "学习次数"},
        {"key": "favoriteStatus", "label": "收藏状态"},
        {"key": "createTime", "label": "收藏时间"},
    ]

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
    if is_admin:
        if userId is not None:
            query = query.where(UserQuestionFavorite.user_id == userId)
    else:
        query = query.where(UserQuestionFavorite.user_id == current_id)

    # 默认只看有效收藏，除非显式指定 favoriteStatus（后台可查已取消/待复习等状态）
    if favoriteStatus is not None:
        query = query.where(UserQuestionFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserQuestionFavorite.favorite_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionFavorite.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionFavorite.bank_id == bankId)
    if notes:
        query = query.where(UserQuestionFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionFavorite.tags.ilike(f"%{tags}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionFavorite.difficulty_rating == difficultyRating)
    if errorTimes is not None:
        query = query.where(UserQuestionFavorite.error_times == errorTimes)
    if correctTimes is not None:
        query = query.where(UserQuestionFavorite.correct_times == correctTimes)
    if reviewCount is not None:
        query = query.where(UserQuestionFavorite.review_count == reviewCount)
    if isStarred is not None:
        query = query.where(UserQuestionFavorite.is_starred == isStarred)
    if lastReviewTime:
        query = query.where(
            UserQuestionFavorite.last_review_time >= _begin_of_date(lastReviewTime),
            UserQuestionFavorite.last_review_time <= _end_of_date(lastReviewTime),
        )
    if nextReviewTime:
        query = query.where(
            UserQuestionFavorite.next_review_time >= _begin_of_date(nextReviewTime),
            UserQuestionFavorite.next_review_time <= _end_of_date(nextReviewTime),
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserQuestionFavorite.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    favorites = list(result.scalars().all())

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
        select(QuestionMain).where(QuestionMain.id == question_id)
    )).scalar_one_or_none()
    if not q:
        return success({"exists": False, "questionId": question_id})

    bank_name = (await db.execute(
        select(QuestionBank.bank_name).where(QuestionBank.id == q.bank_id)
    )).scalar_one_or_none()
    text = q.question_text or ""
    return success({
        "exists": True,
        "questionId": q.id,
        "title": (text[:50] + "...") if len(text) > 50 else text,
        "questionText": text,
        "bankId": q.bank_id,
        "bankName": bank_name,
        "difficulty": q.difficulty,
    })


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
        select(SysUser.user_id).where(SysUser.user_id == user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户ID %s 不存在，请输入有效的用户ID" % user_id)

    # 获取题目信息（含 bank_id，DB 要求非空）
    q_query = select(QuestionMain).where(QuestionMain.id == question_id)
    q_result = await db.execute(q_query)
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
    existing_ids = {row[0] for row in result.all()}

    data = {str(qid): (qid in existing_ids) for qid in payload.questionIds}
    return success(data)


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
            select(SysUser.user_id).where(SysUser.user_id == new_user_id)
        )).scalar_one_or_none()
        if not owner:
            return error("用户ID %s 不存在，请输入有效的用户ID" % new_user_id)
        question = (await db.execute(
            select(QuestionMain).where(QuestionMain.id == new_question_id)
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

    if is_admin:
        if userId is not None:
            query = query.where(UserQuestionFavorite.user_id == userId)
    else:
        query = query.where(UserQuestionFavorite.user_id == current_id)

    if favoriteStatus is not None:
        query = query.where(UserQuestionFavorite.favorite_status == favoriteStatus)
    else:
        query = query.where(UserQuestionFavorite.favorite_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionFavorite.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionFavorite.bank_id == bankId)
    if notes:
        query = query.where(UserQuestionFavorite.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionFavorite.tags.ilike(f"%{tags}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionFavorite.difficulty_rating == difficultyRating)
    if errorTimes is not None:
        query = query.where(UserQuestionFavorite.error_times == errorTimes)
    if correctTimes is not None:
        query = query.where(UserQuestionFavorite.correct_times == correctTimes)
    if reviewCount is not None:
        query = query.where(UserQuestionFavorite.review_count == reviewCount)
    if isStarred is not None:
        query = query.where(UserQuestionFavorite.is_starred == isStarred)
    if lastReviewTime:
        query = query.where(
            UserQuestionFavorite.last_review_time >= _begin_of_date(lastReviewTime),
            UserQuestionFavorite.last_review_time <= _end_of_date(lastReviewTime),
        )
    if nextReviewTime:
        query = query.where(
            UserQuestionFavorite.next_review_time >= _begin_of_date(nextReviewTime),
            UserQuestionFavorite.next_review_time <= _end_of_date(nextReviewTime),
        )

    query = query.order_by(UserQuestionFavorite.create_time.desc())
    result = await db.execute(query)
    favorites = list(result.scalars().all())

    question_ids = [f.question_id for f in favorites]
    b_map = await _fetch_banks_map(db, [f.bank_id for f in favorites])
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
        status_map = {1: "正常收藏", 2: "已掌握", 3: "待复习", 0: "取消收藏"}
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

    headers = [
        {"key": "favoriteId", "label": "收藏ID"},
        {"key": "userId", "label": "用户ID"},
        {"key": "questionId", "label": "题目ID"},
        {"key": "bankId", "label": "题库ID"},
        {"key": "bankName", "label": "题库名称"},
        {"key": "questionType", "label": "题型"},
        {"key": "questionText", "label": "题干"},
        {"key": "answer", "label": "答案"},
        {"key": "notes", "label": "收藏备注"},
        {"key": "tags", "label": "标签"},
        {"key": "difficultyRating", "label": "难度评级"},
        {"key": "errorTimes", "label": "错误次数"},
        {"key": "correctTimes", "label": "正确次数"},
        {"key": "reviewCount", "label": "复习次数"},
        {"key": "lastReviewTime", "label": "最后复习时间"},
        {"key": "nextReviewTime", "label": "下次复习时间"},
        {"key": "isStarred", "label": "是否星标"},
        {"key": "favoriteStatus", "label": "收藏状态"},
        {"key": "createTime", "label": "收藏时间"},
    ]

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
    q_query = select(QuestionMain).where(QuestionMain.id == question_id)
    q_result = await db.execute(q_query)
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

    if is_admin:
        # 后台管理：传 userId 则按该用户筛选，不传则查看全部用户
        if userId is not None:
            query = query.where(UserQuestionError.user_id == userId)
    else:
        # 普通用户：只能看自己的错题
        query = query.where(UserQuestionError.user_id == current_id)

    # 默认只查活跃记录，除非显式指定 status
    if status is not None:
        query = query.where(UserQuestionError.status == status)
    else:
        query = query.where(UserQuestionError.status == 1)

    # 动态过滤条件
    if questionId is not None:
        query = query.where(UserQuestionError.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionError.bank_id == bankId)
    if errorCount is not None:
        query = query.where(UserQuestionError.error_count == errorCount)
    if notes:
        query = query.where(UserQuestionError.notes.ilike(f"%{notes}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionError.difficulty_rating == difficultyRating)
    if isMastered is not None:
        query = query.where(UserQuestionError.is_mastered == isMastered)
    if beginErrorTime:
        query = query.where(UserQuestionError.error_time >= _begin_of_date(beginErrorTime))
    if endErrorTime:
        query = query.where(UserQuestionError.error_time <= _end_of_date(endErrorTime))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserQuestionError.last_error_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    errors = list(result.scalars().all())

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
    q_query = select(QuestionMain).where(QuestionMain.id == question_id)
    q_result = await db.execute(q_query)
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
        if payload.notes is not None:
            error_record.notes = payload.notes
        if payload.tags is not None:
            error_record.tags = payload.tags
        if payload.difficultyRating is not None:
            error_record.difficulty_rating = payload.difficultyRating
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
        if payload.notes is not None:
            error_record.notes = payload.notes
        if payload.tags is not None:
            error_record.tags = payload.tags
        if payload.difficultyRating is not None:
            error_record.difficulty_rating = payload.difficultyRating
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
    existing_ids = {row[0] for row in result.all()}

    data = {str(qid): (qid in existing_ids) for qid in payload.questionIds}
    return success(data)


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

    if payload.notes is not None:
        err.notes = payload.notes
    if payload.tags is not None:
        err.tags = payload.tags
    if payload.difficultyRating is not None:
        err.difficulty_rating = payload.difficultyRating
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

    if is_admin:
        if userId is not None:
            query = query.where(UserQuestionError.user_id == userId)
    else:
        query = query.where(UserQuestionError.user_id == current_id)

    if status is not None:
        query = query.where(UserQuestionError.status == status)
    else:
        query = query.where(UserQuestionError.status == 1)

    if questionId is not None:
        query = query.where(UserQuestionError.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionError.bank_id == bankId)
    if errorCount is not None:
        query = query.where(UserQuestionError.error_count == errorCount)
    if notes:
        query = query.where(UserQuestionError.notes.ilike(f"%{notes}%"))
    if difficultyRating is not None:
        query = query.where(UserQuestionError.difficulty_rating == difficultyRating)
    if isMastered is not None:
        query = query.where(UserQuestionError.is_mastered == isMastered)
    if beginErrorTime:
        query = query.where(UserQuestionError.error_time >= beginErrorTime)
    if endErrorTime:
        query = query.where(UserQuestionError.error_time <= _end_of_date(endErrorTime))

    query = query.order_by(UserQuestionError.last_error_time.desc())

    result = await db.execute(query)
    errors = list(result.scalars().all())

    # 批量获取题目信息
    question_ids = [e.question_id for e in errors]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
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

    headers = [
        {"key": "errorId", "label": "错题ID"},
        {"key": "questionId", "label": "题目ID"},
        {"key": "questionText", "label": "题干"},
        {"key": "questionType", "label": "题型"},
        {"key": "answer", "label": "正确答案"},
        {"key": "errorCount", "label": "错误次数"},
        {"key": "isMastered", "label": "是否已掌握"},
        {"key": "lastErrorTime", "label": "最近错误时间"},
        {"key": "notes", "label": "备注"},
    ]

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
    if is_admin:
        if userId is not None:
            query = query.where(UserQuestionMarked.user_id == userId)
    else:
        query = query.where(UserQuestionMarked.user_id == current_id)

    # 默认只看有效斩题，除非显式指定 markedStatus（后台可查已失效记录）
    if markedStatus is not None:
        query = query.where(UserQuestionMarked.marked_status == markedStatus)
    else:
        query = query.where(UserQuestionMarked.marked_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionMarked.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionMarked.bank_id == bankId)
    if markedType is not None:
        query = query.where(UserQuestionMarked.marked_type == markedType)
    if difficultyLevel is not None:
        query = query.where(UserQuestionMarked.difficulty_level == difficultyLevel)
    if isMastered is not None:
        query = query.where(UserQuestionMarked.is_mastered == isMastered)
    if errorTimesBeforeMark is not None:
        query = query.where(UserQuestionMarked.error_times_before_mark == errorTimesBeforeMark)
    if reviewCount is not None:
        query = query.where(UserQuestionMarked.review_count == reviewCount)
    if notes:
        query = query.where(UserQuestionMarked.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionMarked.tags.ilike(f"%{tags}%"))
    if beginCreateTime:
        query = query.where(UserQuestionMarked.create_time >= _begin_of_date(beginCreateTime))
    if endCreateTime:
        query = query.where(UserQuestionMarked.create_time <= _end_of_date(endCreateTime))

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserQuestionMarked.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    marked = list(result.scalars().all())

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
        select(SysUser.user_id).where(SysUser.user_id == user_id)
    )).scalar_one_or_none()
    if not target_user:
        return error("用户不存在")

    # 获取题目信息（含 bank_id，DB 要求非空）
    q_query = select(QuestionMain).where(QuestionMain.id == question_id)
    q_result = await db.execute(q_query)
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


def _apply_marked_fields(marked, payload, question=None):
    """把请求体里的斩题业务字段写入 ORM 对象（新增/修改/恢复共用）

    只覆盖请求里显式传入的字段，None 表示"不动该字段"，避免误清空。
    """
    if payload.notes is not None:
        marked.notes = payload.notes
    if getattr(payload, "tags", None) is not None:
        marked.tags = payload.tags
    if payload.markedType is not None:
        marked.marked_type = payload.markedType
    if payload.difficultyLevel is not None:
        marked.difficulty_level = payload.difficultyLevel
    if getattr(payload, "errorTimesBeforeMark", None) is not None:
        marked.error_times_before_mark = payload.errorTimesBeforeMark
    if getattr(payload, "correctTimesBeforeMark", None) is not None:
        marked.correct_times_before_mark = payload.correctTimesBeforeMark
    if getattr(payload, "reviewCount", None) is not None:
        marked.review_count = payload.reviewCount
    if getattr(payload, "lastReviewTime", None):
        marked.last_review_time = _parse_dt(payload.lastReviewTime)
    if getattr(payload, "nextReviewTime", None):
        marked.next_review_time = _parse_dt(payload.nextReviewTime)
    if getattr(payload, "isMastered", None) is not None:
        marked.is_mastered = payload.isMastered
    if getattr(payload, "masteryDate", None):
        marked.mastery_date = _parse_dt(payload.masteryDate)
    if getattr(payload, "markedStatus", None) is not None:
        marked.marked_status = payload.markedStatus
    if getattr(payload, "bankId", None) is not None:
        marked.bank_id = payload.bankId
    return marked


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
    existing_ids = {row[0] for row in result.all()}

    data = {str(qid): (qid in existing_ids) for qid in payload.questionIds}
    return success(data)


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
            select(SysUser.user_id).where(SysUser.user_id == new_user_id)
        )).scalar_one_or_none()
        if not owner:
            return error("用户不存在")
        question = (await db.execute(
            select(QuestionMain).where(QuestionMain.id == new_question_id)
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

    if is_admin:
        if userId is not None:
            query = query.where(UserQuestionMarked.user_id == userId)
    else:
        query = query.where(UserQuestionMarked.user_id == current_id)

    if markedStatus is not None:
        query = query.where(UserQuestionMarked.marked_status == markedStatus)
    else:
        query = query.where(UserQuestionMarked.marked_status == 1)

    if questionId is not None:
        query = query.where(UserQuestionMarked.question_id == questionId)
    if bankId is not None:
        query = query.where(UserQuestionMarked.bank_id == bankId)
    if markedType is not None:
        query = query.where(UserQuestionMarked.marked_type == markedType)
    if difficultyLevel is not None:
        query = query.where(UserQuestionMarked.difficulty_level == difficultyLevel)
    if isMastered is not None:
        query = query.where(UserQuestionMarked.is_mastered == isMastered)
    if notes:
        query = query.where(UserQuestionMarked.notes.ilike(f"%{notes}%"))
    if tags:
        query = query.where(UserQuestionMarked.tags.ilike(f"%{tags}%"))
    if beginCreateTime:
        query = query.where(UserQuestionMarked.create_time >= _begin_of_date(beginCreateTime))
    if endCreateTime:
        query = query.where(UserQuestionMarked.create_time <= _end_of_date(endCreateTime))

    query = query.order_by(UserQuestionMarked.create_time.desc())

    result = await db.execute(query)
    marked = list(result.scalars().all())

    question_ids = [m.question_id for m in marked]
    rows = []
    if question_ids:
        q_map = await _fetch_questions_map(db, question_ids)
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

    headers = [
        {"key": "markedId", "label": "斩题ID"},
        {"key": "userId", "label": "用户ID"},
        {"key": "questionId", "label": "题目ID"},
        {"key": "questionText", "label": "题干"},
        {"key": "questionType", "label": "题型"},
        {"key": "answer", "label": "答案"},
        {"key": "markedType", "label": "斩题类型"},
        {"key": "difficultyLevel", "label": "难度等级"},
        {"key": "errorTimesBeforeMark", "label": "错误次数"},
        {"key": "reviewCount", "label": "复习次数"},
        {"key": "isMastered", "label": "是否已掌握"},
        {"key": "lastReviewTime", "label": "最后复习时间"},
        {"key": "notes", "label": "备注"},
        {"key": "tags", "label": "标签"},
        {"key": "createTime", "label": "斩题时间"},
    ]

    return export_to_excel(rows, headers, "questionMarked")
