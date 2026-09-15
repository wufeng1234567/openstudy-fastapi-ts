"""定向站内通知服务

极简写入封装，供题库分享等业务调用。
"""

from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import UserNotification


async def create_notification(
    db: AsyncSession,
    user_id: int,
    title: str,
    content: Optional[str] = None,
    notify_type: str = "system",
    link: Optional[str] = None,
) -> UserNotification:
    """给指定用户投递一条通知（调用方负责 commit）"""
    notification = UserNotification(
        user_id=user_id,
        notify_type=notify_type,
        title=title,
        content=content,
        link=link,
    )
    db.add(notification)
    await db.flush()
    return notification


async def unread_count(db: AsyncSession, user_id: int) -> int:
    """未读数"""
    count = await db.scalar(
        select(func.count()).where(
            UserNotification.user_id == user_id,
            UserNotification.is_read == 0,
        )
    )
    return count or 0
