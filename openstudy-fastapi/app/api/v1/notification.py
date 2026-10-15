"""
定向站内通知 API

与全局公告（/system/notice）不同，这里只返回**当前用户**的通知，
用于题库分享等精确投递场景。

端点
----
GET    /notification/notification/myList        我的通知列表
GET    /notification/notification/unreadCount   未读数
POST   /notification/notification/markRead/{id} 单条已读
POST   /notification/notification/markReadAll   全部已读
DELETE /notification/notification/{id}          删除单条
DELETE /notification/notification/clear/all     清空
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, update as sa_update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success
from app.models.notification import UserNotification

router = APIRouter()


def format_notification(n: UserNotification):
    return {
        "notificationId": n.notification_id,
        "userId": n.user_id,
        "notifyType": n.notify_type,
        "title": n.title,
        "content": n.content,
        "link": n.link,
        "isRead": n.is_read,
        "read": n.is_read == 1,
        "createTime": n.create_time.isoformat() if n.create_time else None,
    }


@router.get("/notification/notification/myList")
async def my_notification_list(
    onlyUnread: Optional[bool] = Query(None),
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """我的通知列表（按时间倒序）"""
    user_id = current_user.get("user_id")
    query = select(UserNotification).where(UserNotification.user_id == user_id)
    if onlyUnread:
        query = query.where(UserNotification.is_read == 0)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(UserNotification.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)
    result = await db.execute(query)
    rows = list(result.scalars().all())

    return success({
        "total": total or 0,
        "rows": [format_notification(n) for n in rows],
    })


@router.get("/notification/notification/unreadCount")
async def my_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """我的未读通知数"""
    user_id = current_user.get("user_id")
    count = await db.scalar(
        select(func.count()).where(
            UserNotification.user_id == user_id,
            UserNotification.is_read == 0,
        )
    )
    return success(count or 0)


@router.post("/notification/notification/markRead/{notification_id}")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记单条已读"""
    user_id = current_user.get("user_id")
    await db.execute(
        sa_update(UserNotification)
        .where(
            UserNotification.notification_id == notification_id,
            UserNotification.user_id == user_id,
        )
        .values(is_read=1)
    )
    return success()


@router.post("/notification/notification/markReadAll")
async def mark_read_all(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """全部标记已读"""
    user_id = current_user.get("user_id")
    await db.execute(
        sa_update(UserNotification)
        .where(UserNotification.user_id == user_id)
        .values(is_read=1)
    )
    return success()


@router.delete("/notification/notification/clear/all")
async def clear_all(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """清空我的通知"""
    user_id = current_user.get("user_id")
    await db.execute(delete(UserNotification).where(UserNotification.user_id == user_id))
    return success()


@router.delete("/notification/notification/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除单条通知"""
    user_id = current_user.get("user_id")
    await db.execute(
        delete(UserNotification).where(
            UserNotification.notification_id == notification_id,
            UserNotification.user_id == user_id,
        )
    )
    return success()
