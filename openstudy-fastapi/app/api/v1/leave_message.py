"""
留言板 API - 完整实现
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user, require_admin
from app.core.response import success, paginate, error
from datetime import datetime

router = APIRouter()

from sqlalchemy import BigInteger, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class LeaveMessage(Base):
    __tablename__ = "leave_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    reply_content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(1), default="0")
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def format_message(msg):
    return {
        "id": msg.id,
        "userId": msg.user_id,
        "content": msg.content,
        "replyContent": msg.reply_content,
        "status": msg.status,
        "createTime": msg.create_time.isoformat() if msg.create_time else None,
    }


@router.get("/leaveMessage/list")
async def list_messages(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("user_id")
    query = select(LeaveMessage).where(LeaveMessage.user_id == user_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(LeaveMessage.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    return paginate(total, [format_message(m) for m in messages])


@router.get("/leaveMessage/admin/list")
async def admin_list_messages(
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """管理端留言列表（2026-10-28：挂 require_admin，此前任意登录用户可读全站留言）"""
    query = select(LeaveMessage)

    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    query = query.order_by(LeaveMessage.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    return paginate(total, [format_message(m) for m in messages])


@router.post("/leaveMessage/add")
async def add_message(
    content: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user.get("user_id")
    message = LeaveMessage(user_id=user_id, content=content)
    db.add(message)
    await db.flush()
    return success(format_message(message))


@router.post("/leaveMessage/admin/add")
async def admin_add_message(
    content: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    message = LeaveMessage(content=content)
    db.add(message)
    await db.flush()
    return success(format_message(message))


@router.delete("/leaveMessage/{ids}")
async def delete_messages(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin),
):
    """删除留言（2026-10-28：挂 require_admin —— 前端删除入口只在管理页，
    此前任意登录用户可删任意人的留言）"""
    id_list = [int(id) for id in ids.split(",")]
    stmt = delete(LeaveMessage).where(LeaveMessage.id.in_(id_list))
    await db.execute(stmt)
    return success()
