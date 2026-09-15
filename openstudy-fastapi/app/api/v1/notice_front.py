"""
前台通知 API - ⚠️ 当前未使用

原因：FastAPI 按注册顺序匹配路由。在 main.py 中：
- notices.py (后台通知) 先注册
- notice_front.py (本文件) 后注册

两个文件都有 /system/notice/listAll 端点，由于 notices.py 先注册，
它的 /listAll 会先被匹配并处理请求，本文件的 /listAll 被忽略。

如需使用本文件，请在 main.py 中将 notice_front 移到 notices 之前注册，
或删除 notices.py 中的 /listAll 端点。

实际使用的端点是 notices.py 中的 /listAll。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, paginate
from app.models.notice import SysNotice
from loguru import logger

# 路由前缀：/system/notice (与 notices.py 冲突)
router = APIRouter(prefix="/system/notice")


@router.get("/listTop")
async def list_top_notices(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取置顶公告"""
    return success([])


@router.get("/listAll")
async def list_all_notices(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取所有通知（系统公告 + 评论通知）"""
    user_id = current_user.get("user_id")

    # 查询所有活跃通知
    query = select(SysNotice).where(
        SysNotice.status == "0",
    ).order_by(SysNotice.create_time.desc())

    result = await db.execute(query)
    notices = list(result.scalars().all())

    # 格式化通知数据
    formatted = []
    for notice in notices:
        remark = notice.remark or ""
        # 解析 remark 获取 toUserId，判断是否是当前用户的通知
        is_current_user_notice = True
        try:
            if remark:
                import json
                remark_obj = json.loads(remark)
                if remark_obj.get("toUserId") and remark_obj["toUserId"] != user_id:
                    is_current_user_notice = False
        except:
            pass

        if not remark or is_current_user_notice:
            formatted_notice = {
                "noticeId": notice.notice_id,
                "noticeTitle": notice.notice_title,
                "noticeContent": notice.notice_content,
                "noticeType": notice.notice_type,
                "status": notice.status,
                "read": notice.status == "1",
                "createBy": notice.create_by,
                "createTime": notice.create_time.isoformat() if notice.create_time else None,
                "remark": remark,
            }
            formatted.append(formatted_notice)

    return success(formatted)


@router.get("/unreadCount")
async def get_unread_notice_count(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取未读通知数"""
    user_id = current_user.get("user_id")

    count_query = select(func.count()).where(
        SysNotice.status == "0",
    )
    count = await db.scalar(count_query) or 0

    return success({"count": count})


@router.post("/markRead")
async def mark_read(
    noticeId: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记单条通知为已读"""
    from sqlalchemy import update as sa_update
    stmt = (
        sa_update(SysNotice)
        .where(SysNotice.notice_id == noticeId)
        .values(status="1")
    )
    await db.execute(stmt)
    logger.info(f"[markRead] 通知 {noticeId} 已标记为已读\n")
    return success()


@router.post("/markReadAll")
async def mark_read_all(
    ids: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记所有通知为已读"""
    from sqlalchemy import update as sa_update
    if ids:
        id_list = [int(i) for i in ids.split(",") if i]
        stmt = (
            sa_update(SysNotice)
            .where(SysNotice.notice_id.in_(id_list))
            .values(status="1")
        )
    else:
        stmt = (
            sa_update(SysNotice)
            .where(SysNotice.status == "0")
            .values(status="1")
        )
    await db.execute(stmt)
    return success()


@router.delete("/front/{notice_id}")
async def delete_front_notice(
    notice_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台删除单条通知"""
    from sqlalchemy import delete as sa_delete
    stmt = sa_delete(SysNotice).where(SysNotice.notice_id == notice_id)
    await db.execute(stmt)
    return success()


@router.delete("/front/batch/{notice_ids}")
async def delete_front_notice_batch(
    notice_ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """前台批量删除通知"""
    from sqlalchemy import delete as sa_delete
    id_list = [int(i) for i in notice_ids.split(",") if i]
    stmt = sa_delete(SysNotice).where(SysNotice.notice_id.in_(id_list))
    await db.execute(stmt)
    return success()
