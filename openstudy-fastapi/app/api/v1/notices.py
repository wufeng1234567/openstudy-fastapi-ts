"""
通知公告 API - 后台管理端
问题原因：此前端通知页面无法跳转，是因为前端调用的 /system/notice/listAll 端点有两个：
1. 本文件 (notices.py) - 在 main.py 中先注册
2. app/api/v1/notice_front.py - 在 main.py 后注册

由于 FastAPI 按注册顺序匹配路由，本文件的 /listAll 会先被匹配并处理请求，
而 notice_front.py 的 /listAll 被忽略。

原本 format_notice 函数缺少 remark 字段（用于存储评论跳转信息），
导致前端无法获取通知中的 noteId 和 commentId，无法实现跳转功能。

修复：在 format_notice 中添加 remark 字段。
"""

import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from loguru import logger
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate, error
from app.models.notice import SysNotice, SysNoticeRead
from datetime import datetime

# 路由前缀：/system/notice
router = APIRouter(prefix="/system/notice")

# 用户通知（普通用户产生）的 remark.type 取值
USER_NOTICE_TYPES = ("comment", "reply", "mention")


def parse_remark_str(remark: Optional[str]) -> dict:
    """安全解析 remark 字符串，非 JSON / 非对象统一返回空 dict"""
    if not remark:
        return {}
    try:
        parsed = json.loads(remark)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def parse_notice_remark(notice) -> dict:
    """安全解析 notice.remark"""
    if not notice:
        return {}
    return parse_remark_str(notice.remark)


def is_system_notice(notice) -> bool:
    """系统公告：没有 remark，或 remark 不是用户通知类型"""
    return parse_notice_remark(notice).get("type") not in USER_NOTICE_TYPES


def is_notice_visible(notice, user_id) -> bool:
    """
    通知可见性：
    - 系统公告（无 remark / 非定向）：所有人可见
    - 定向通知（remark.toUserId 有值）：仅接收者本人可见
    """
    to_user_id = parse_notice_remark(notice).get("toUserId")
    if to_user_id in (None, "", 0, "0"):
        return True
    return str(to_user_id) == str(user_id)


async def get_read_notice_ids(db: AsyncSession, user_id) -> set:
    """当前用户已读的通知 id 集合"""
    read_query = select(SysNoticeRead.notice_id).where(SysNoticeRead.user_id == user_id)
    read_result = await db.execute(read_query)
    return set(row[0] for row in read_result.all())


async def mark_notices_read(db: AsyncSession, user_id, notice_ids: list) -> None:
    """为当前用户批量写入已读记录（幂等，已存在则跳过）"""
    # 去重，避免同一请求里重复 add 触发唯一约束
    notice_ids = list(dict.fromkeys(notice_ids))
    if not notice_ids:
        return
    existing_query = select(SysNoticeRead.notice_id).where(
        SysNoticeRead.user_id == user_id,
        SysNoticeRead.notice_id.in_(notice_ids),
    )
    existing_result = await db.execute(existing_query)
    existing_ids = set(row[0] for row in existing_result.all())
    for notice_id in notice_ids:
        if notice_id not in existing_ids:
            db.add(SysNoticeRead(user_id=user_id, notice_id=notice_id))


async def get_visible_notice_ids(db: AsyncSession, user_id, notice_ids: list) -> list:
    """从给定 id 中筛出当前用户可见的通知 id（系统公告 + 发给我自己的）"""
    if not notice_ids:
        return []
    query = select(SysNotice).where(SysNotice.notice_id.in_(notice_ids))
    result = await db.execute(query)
    notices = list(result.scalars().all())
    return [n.notice_id for n in notices if is_notice_visible(n, user_id)]


def format_notice(notice, is_read=False):
    """
    格式化公告数据

    注意：remark 字段存储 JSON 字符串，包含评论跳转信息：
    {
        "type": "comment" 或 "reply",
        "fromUserId": 评论者ID,
        "toUserId": 接收者ID,
        "noteId": 笔记ID,
        "commentId": 评论ID
    }
    前端通过解析 remark 实现通知点击跳转到对应评论。
    """
    return {
        "noticeId": notice.notice_id,
        "noticeTitle": notice.notice_title,
        "noticeType": notice.notice_type,
        "noticeContent": notice.notice_content,
        "status": notice.status,
        "createBy": notice.create_by,
        "createTime": notice.create_time.isoformat() if notice.create_time else None,
        "read": is_read,
        "remark": notice.remark or "",  # 关键字段：评论跳转信息
    }


@router.get("/list")
async def list_notices(
    notice_title: Optional[str] = Query(None),
    notice_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询公告列表"""
    query = select(SysNotice).where(SysNotice.status == "0")

    if notice_title:
        query = query.where(SysNotice.notice_title.ilike(f"%{notice_title}%"))
    if notice_type:
        query = query.where(SysNotice.notice_type == notice_type)

    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # 分页
    query = query.order_by(SysNotice.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    notices = list(result.scalars().all())

    # 获取用户已读的公告ID
    user_id = current_user.get("user_id")
    read_query = select(SysNoticeRead.notice_id).where(SysNoticeRead.user_id == user_id)
    read_result = await db.execute(read_query)
    read_ids = set(row[0] for row in read_result.all())

    rows = [format_notice(n, n.notice_id in read_ids) for n in notices]

    return paginate(total, rows)


@router.get("/listAll")
async def list_all_notices(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    查询「当前用户可见」的全部通知（带已读标记）

    只下发两类：
    1. 系统公告（无 remark / 非用户通知类型）—— 所有人可见
    2. 定向用户通知（remark.toUserId == 当前用户）—— 仅接收者可见
    其他用户之间的评论 / 回复 / @ 通知不再下发，避免越权与前端兜底过滤。
    """
    user_id = current_user.get("user_id")

    query = select(SysNotice).where(SysNotice.status == "0").order_by(SysNotice.create_time.desc())
    result = await db.execute(query)
    notices = list(result.scalars().all())

    read_ids = await get_read_notice_ids(db, user_id)

    rows = [
        format_notice(n, n.notice_id in read_ids)
        for n in notices
        if is_notice_visible(n, user_id)
    ]

    # 日志：记录用户通知的跳转信息（便于排查）
    for row in rows:
        remark_obj = parse_remark_str(row.get("remark"))
        if remark_obj.get("noteId"):
            logger.info(
                f"[通知跳转] noticeId={row.get('noticeId')}, "
                f"type={remark_obj.get('type')}, noteId={remark_obj.get('noteId')}, "
                f"commentId={remark_obj.get('commentId')}"
            )

    return success(rows)


@router.get("/listTop")
async def list_top_notices(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取顶部系统公告（最多5条，不包含用户通知）"""
    user_id = current_user.get("user_id")

    query = select(SysNotice).where(SysNotice.status == "0").order_by(SysNotice.create_time.desc())
    result = await db.execute(query)
    notices = list(result.scalars().all())

    read_ids = await get_read_notice_ids(db, user_id)

    # 只取系统公告；先过滤再截断，避免用户通知占用名额
    system_notices = [n for n in notices if is_system_notice(n)][:5]
    rows = [format_notice(n, n.notice_id in read_ids) for n in system_notices]

    return success(rows)


@router.get("/unreadCount")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的未读通知数（系统公告 + 发给我的用户通知）"""
    user_id = current_user.get("user_id")

    query = select(SysNotice).where(SysNotice.status == "0")
    result = await db.execute(query)
    notices = list(result.scalars().all())

    read_ids = await get_read_notice_ids(db, user_id)
    unread = sum(
        1 for n in notices
        if is_notice_visible(n, user_id) and n.notice_id not in read_ids
    )

    return success({"count": unread})


@router.get("/{notice_id}")
async def get_notice(
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """查询公告详情"""
    query = select(SysNotice).where(SysNotice.notice_id == notice_id)
    result = await db.execute(query)
    notice = result.scalar_one_or_none()

    if not notice:
        return error("公告不存在")

    # 检查是否已读
    user_id = current_user.get("user_id")
    read_query = select(SysNoticeRead).where(
        SysNoticeRead.user_id == user_id,
        SysNoticeRead.notice_id == notice_id,
    )
    read_result = await db.execute(read_query)
    is_read = read_result.scalar_one_or_none() is not None

    return success(format_notice(notice, is_read))


@router.post("")
async def create_notice(
    notice_title: str = Query(...),
    notice_type: str = Query(...),
    notice_content: Optional[str] = Query(None),
    status: Optional[str] = Query("0"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建公告"""
    notice = SysNotice(
        notice_title=notice_title,
        notice_type=notice_type,
        notice_content=notice_content,
        status=status,
        create_by=current_user.get("user_name"),
    )
    db.add(notice)
    await db.flush()

    return success({"notice_id": notice.notice_id})


@router.put("")
async def update_notice(
    notice_id: int = Query(...),
    notice_title: Optional[str] = Query(None),
    notice_type: Optional[str] = Query(None),
    notice_content: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新公告"""
    query = select(SysNotice).where(SysNotice.notice_id == notice_id)
    result = await db.execute(query)
    notice = result.scalar_one_or_none()

    if not notice:
        return error("公告不存在")

    if notice_title is not None:
        notice.notice_title = notice_title
    if notice_type is not None:
        notice.notice_type = notice_type
    if notice_content is not None:
        notice.notice_content = notice_content
    if status is not None:
        notice.status = status

    return success()


@router.delete("/{notice_ids}")
async def delete_notices(
    notice_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除公告"""
    ids = [int(id) for id in notice_ids.split(",")]
    stmt = delete(SysNotice).where(SysNotice.notice_id.in_(ids))
    await db.execute(stmt)
    return success()


@router.post("/markRead")
async def mark_read(
    noticeId: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记公告已读（仅允许操作当前用户可见的通知）"""
    user_id = current_user.get("user_id")

    query = select(SysNotice).where(SysNotice.notice_id == noticeId)
    result = await db.execute(query)
    notice = result.scalar_one_or_none()
    if not notice or not is_notice_visible(notice, user_id):
        # 不可见：静默忽略，避免越权 / 信息泄露
        return success()

    await mark_notices_read(db, user_id, [noticeId])
    return success()


@router.post("/markReadAll")
async def mark_read_all(
    ids: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量标记已读（只标记当前用户可见的通知）"""
    user_id = current_user.get("user_id")

    if ids:
        raw_ids = [int(i) for i in ids.split(",") if i]
        notice_ids = await get_visible_notice_ids(db, user_id, raw_ids)
    else:
        # 标记所有「当前用户可见」的通知为已读
        query = select(SysNotice).where(SysNotice.status == "0")
        result = await db.execute(query)
        notices = list(result.scalars().all())
        notice_ids = [n.notice_id for n in notices if is_notice_visible(n, user_id)]

    await mark_notices_read(db, user_id, notice_ids)
    return success()


@router.delete("/front/{notice_id}")
async def delete_front_notice(
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台删除通知（标记为该用户已读；仅允许操作可见通知）"""
    user_id = current_user.get("user_id")

    query = select(SysNotice).where(SysNotice.notice_id == notice_id)
    result = await db.execute(query)
    notice = result.scalar_one_or_none()
    if not notice or not is_notice_visible(notice, user_id):
        return success()

    await mark_notices_read(db, user_id, [notice_id])
    return success()


@router.delete("/front/batch/{notice_ids}")
async def delete_front_notice_batch(
    notice_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台批量删除通知（只处理当前用户可见的通知）"""
    user_id = current_user.get("user_id")
    raw_ids = [int(i) for i in notice_ids.split(",") if i]
    visible_ids = await get_visible_notice_ids(db, user_id, raw_ids)

    await mark_notices_read(db, user_id, visible_ids)
    return success()
