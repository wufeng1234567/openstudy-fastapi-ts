"""题库/题目 API 的纯辅助函数：格式化、权限与通用转换。"""

from typing import Optional, List, Any, Dict
from decimal import Decimal
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.response import error
from app.services import question_write_service
from app.models.question import (
    QuestionBank, QuestionMain, QuestionSource, QuestionSub,
    UserBankFavorite, UserQuestionFavorite, UserQuestionError, UserQuestionMarked,
    UserPracticeLog, UserPracticeSession,
)
from app.models.bank_share import BankShare, BankShareReceive
from app.models.user import SysUser


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
