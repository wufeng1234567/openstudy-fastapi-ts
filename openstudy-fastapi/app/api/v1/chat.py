"""
聊天 API - 适配实际数据库 schema（基于 sender/receiver，无 conversation_id）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.core.security import get_current_user
from app.core.response import success, error
from datetime import datetime

router = APIRouter(prefix="/system/chat")

# 聊天模型
from sqlalchemy import BigInteger, String, Text, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_message"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_name: Mapped[Optional[str]] = mapped_column(String(100))
    sender_nickname: Mapped[Optional[str]] = mapped_column(String(100))
    sender_avatar: Mapped[Optional[str]] = mapped_column(String(255))
    receiver_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receiver_name: Mapped[Optional[str]] = mapped_column(String(100))
    receiver_nickname: Mapped[Optional[str]] = mapped_column(String(100))
    receiver_avatar: Mapped[Optional[str]] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    is_deleted: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    hidden_by: Mapped[Optional[str]] = mapped_column(String(500))


def format_message(msg):
    return {
        "id": msg.id,
        "senderId": msg.sender_id,
        "senderName": msg.sender_name,
        "senderNickname": msg.sender_nickname,
        "senderAvatar": msg.sender_avatar,
        "receiverId": msg.receiver_id,
        "receiverName": msg.receiver_name,
        "receiverNickname": msg.receiver_nickname,
        "receiverAvatar": msg.receiver_avatar,
        "content": msg.content,
        "isRead": msg.is_read,
        "createTime": msg.create_time.isoformat() if msg.create_time else None,
    }


@router.get("/users")
async def list_chat_users(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取可聊天用户列表"""
    from app.models.user import SysUser

    query = select(SysUser).where(SysUser.del_flag == "0", SysUser.status == "0")
    result = await db.execute(query)
    users = list(result.scalars().all())

    return success([{
        "userId": u.user_id,
        "userName": u.user_name,
        "nickName": u.nick_name,
        "avatar": u.avatar,
        "status": u.status,
    } for u in users])


@router.get("/history/{other_user_id}")
async def get_chat_history(
    other_user_id: int,
    pageNum: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    hidden: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取与某用户的聊天历史"""
    user_id = current_user.get("user_id")

    # 查询双方之间的消息
    query = select(ChatMessage).where(
        or_(
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_user_id),
            and_(ChatMessage.sender_id == other_user_id, ChatMessage.receiver_id == user_id),
        ),
        ChatMessage.is_deleted == 0,
    )

    # 排除当前用户隐藏的消息
    if not hidden:
        query = query.where(
            (ChatMessage.hidden_by.is_(None)) | (ChatMessage.hidden_by.notlike(f'%,{user_id},%'))
        )

    query = query.order_by(ChatMessage.create_time.desc())
    query = query.offset((pageNum - 1) * pageSize).limit(pageSize)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    # 检查是否还有更多消息
    total_query = select(func.count()).select_from(
        select(ChatMessage).where(
            or_(
                and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_user_id),
                and_(ChatMessage.sender_id == other_user_id, ChatMessage.receiver_id == user_id),
            ),
            ChatMessage.is_deleted == 0,
        ).subquery()
    )
    total = await db.scalar(total_query) or 0
    hasMore = (pageNum * pageSize) < total

    return success({
        "messages": [format_message(m) for m in reversed(messages)],
        "hasMore": hasMore,
    })


@router.get("/history/clear/{other_user_id}")
async def clear_chat_history(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """清空与某用户的聊天历史"""
    user_id = current_user.get("user_id")

    # 软删除：将当前用户发送的消息标记为删除，或将消息 hidden_by 添加当前用户
    query = select(ChatMessage).where(
        or_(
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_user_id),
            and_(ChatMessage.sender_id == other_user_id, ChatMessage.receiver_id == user_id),
        ),
    )
    result = await db.execute(query)
    messages = list(result.scalars().all())

    for msg in messages:
        if msg.hidden_by:
            msg.hidden_by = f"{msg.hidden_by},{user_id}"
        else:
            msg.hidden_by = f",{user_id},"

    return success()


@router.post("/send")
async def send_message(
    receiverId: int = Query(...),
    content: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """发送消息"""
    user_id = current_user.get("user_id")
    user_name = current_user.get("user_name", "")
    nick_name = current_user.get("nick_name", "")
    avatar = current_user.get("avatar", "")

    # 获取接收者信息
    from app.models.user import SysUser
    receiver_query = select(SysUser).where(SysUser.user_id == receiverId)
    receiver_result = await db.execute(receiver_query)
    receiver = receiver_result.scalar_one_or_none()
    receiver_name = receiver.user_name if receiver else ""
    receiver_nickname = receiver.nick_name if receiver else ""
    receiver_avatar = receiver.avatar if receiver else ""

    message = ChatMessage(
        sender_id=user_id,
        sender_name=user_name,
        sender_nickname=nick_name,
        sender_avatar=avatar,
        receiver_id=receiverId,
        receiver_name=receiver_name,
        receiver_nickname=receiver_nickname,
        receiver_avatar=receiver_avatar,
        content=content,
    )
    db.add(message)
    await db.flush()

    return success(format_message(message))


@router.post("/markRead/{other_user_id}")
async def mark_read(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """标记与某用户的消息为已读"""
    user_id = current_user.get("user_id")

    stmt = (
        update(ChatMessage)
        .where(
            ChatMessage.sender_id == other_user_id,
            ChatMessage.receiver_id == user_id,
            ChatMessage.is_read == 0,
        )
        .values(is_read=1)
    )
    await db.execute(stmt)

    return success()


@router.get("/unreadCount")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取未读消息总数"""
    user_id = current_user.get("user_id")

    count_query = select(func.count()).where(
        ChatMessage.receiver_id == user_id,
        ChatMessage.is_read == 0,
        ChatMessage.is_deleted == 0,
    )
    count = await db.scalar(count_query) or 0

    return success({"count": count})


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """获取会话列表（与当前用户有消息往来的所有用户）"""
    user_id = current_user.get("user_id")

    # 查找所有与当前用户有消息往来的用户
    # 获取每个对话的最后一条消息
    from sqlalchemy import case

    # 子查询：获取每个对话用户的最后消息时间
    sent_query = select(
        ChatMessage.receiver_id.label('other_id'),
        func.max(ChatMessage.create_time).label('last_time')
    ).where(
        ChatMessage.sender_id == user_id,
        ChatMessage.is_deleted == 0,
    ).group_by(ChatMessage.receiver_id)

    received_query = select(
        ChatMessage.sender_id.label('other_id'),
        func.max(ChatMessage.create_time).label('last_time')
    ).where(
        ChatMessage.receiver_id == user_id,
        ChatMessage.is_deleted == 0,
    ).group_by(ChatMessage.sender_id)

    # 合并查询
    sent_result = await db.execute(sent_query)
    received_result = await db.execute(received_query)

    # 构建用户ID到时间的映射
    user_times = {}
    for row in sent_result.all():
        user_times[row[0]] = row[1]
    for row in received_result.all():
        if row[0] not in user_times or row[1] > user_times[row[0]]:
            user_times[row[0]] = row[1]

    if not user_times:
        return success([])

    # 获取用户信息
    from app.models.user import SysUser
    user_ids = list(user_times.keys())
    user_query = select(SysUser).where(SysUser.user_id.in_(user_ids))
    user_result = await db.execute(user_query)
    users = {u.user_id: u for u in user_result.scalars().all()}

    # 获取每个对话的最后一条消息
    conversations = []
    for other_id, last_time in sorted(user_times.items(), key=lambda x: x[1], reverse=True):
        user = users.get(other_id)
        if not user:
            continue

        # 获取最后一条消息
        msg_query = select(ChatMessage).where(
            or_(
                and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_id),
                and_(ChatMessage.sender_id == other_id, ChatMessage.receiver_id == user_id),
            ),
        ).order_by(ChatMessage.create_time.desc()).limit(1)
        msg_result = await db.execute(msg_query)
        last_msg = msg_result.scalar_one_or_none()

        # 获取未读数
        unread_query = select(func.count()).where(
            ChatMessage.sender_id == other_id,
            ChatMessage.receiver_id == user_id,
            ChatMessage.is_read == 0,
            ChatMessage.is_deleted == 0,
        )
        unread_count = await db.scalar(unread_query) or 0

    conversations.append({
        "userId": other_id,
        "nickname": user.nick_name or user.user_name,
        "avatar": user.avatar,
        "lastMessage": last_msg.content if last_msg else "",
        "lastMessageTime": last_time.isoformat() if last_time else None,
        "unreadCount": unread_count,
    })

    return success(conversations)


@router.get("/message/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除消息（软删除）"""
    user_id = current_user.get("user_id")

    query = select(ChatMessage).where(ChatMessage.id == message_id)
    result = await db.execute(query)
    message = result.scalar_one_or_none()

    if not message:
        return error("消息不存在")

    # 只有发送者或接收者可以删除
    if message.sender_id != user_id and message.receiver_id != user_id:
        return error("无权删除")

    # 软删除：添加到 hidden_by
    if message.hidden_by:
        if str(user_id) not in message.hidden_by:
            message.hidden_by = f"{message.hidden_by},{user_id}"
    else:
        message.hidden_by = f",{user_id},"

    return success()


@router.delete("/conversation/{other_user_id}")
async def delete_conversation(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除与某用户的整个会话"""
    user_id = current_user.get("user_id")

    # 获取所有相关消息
    query = select(ChatMessage).where(
        or_(
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == other_user_id),
            and_(ChatMessage.sender_id == other_user_id, ChatMessage.receiver_id == user_id),
        ),
    )
    result = await db.execute(query)
    messages = list(result.scalars().all())

    # 软删除：添加到 hidden_by
    for msg in messages:
        if msg.hidden_by:
            if str(user_id) not in msg.hidden_by:
                msg.hidden_by = f"{msg.hidden_by},{user_id}"
        else:
            msg.hidden_by = f",{user_id},"

    return success()


@router.post("/conversation/{other_user_id}")
async def create_conversation(
    other_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建会话（实际上不需要创建，因为是基于 sender/receiver 的）"""
    # 只需返回接收者信息
    from app.models.user import SysUser
    receiver_query = select(SysUser).where(SysUser.user_id == other_user_id)
    receiver_result = await db.execute(receiver_query)
    receiver = receiver_result.scalar_one_or_none()

    if not receiver:
        return error("用户不存在")

    return success({
        "targetUserId": receiver.user_id,
        "targetUserName": receiver.user_name,
        "targetNickName": receiver.nick_name,
        "targetAvatar": receiver.avatar,
    })


@router.post("/sync")
async def sync_messages(
    lastMessageId: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """同步新消息"""
    user_id = current_user.get("user_id")

    query = select(ChatMessage).where(
        ChatMessage.receiver_id == user_id,
        ChatMessage.is_deleted == 0,
    )

    if lastMessageId:
        query = query.where(ChatMessage.id > lastMessageId)

    query = query.order_by(ChatMessage.create_time.desc()).limit(50)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    return success([format_message(m) for m in messages])
