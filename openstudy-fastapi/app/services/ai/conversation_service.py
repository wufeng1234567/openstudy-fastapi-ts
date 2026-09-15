"""
AI 对话历史服务（Redis 存储）

移植自 springboot3 的 ConversationHistoryService：按 (userId, sessionId)
维度保存 / 读取 / 清空消息流，并提供上下文拼接。

存储结构：Redis String -> JSON list[dict]
    key : ai:conversation:{userId}:{sessionId}
    item: {"role": "user"|"assistant", "content": str, "timestamp": int}
"""

import time
import uuid
from typing import List, Optional

from app.utils.redis_util import delete_cache, get_cache_json, set_cache

# 单会话最多保留的消息条数
HISTORY_LIMIT = 50
# 拼接上下文时取最近 N 条
CONTEXT_LIMIT = 10
# 会话过期时间（秒）：7 天
SESSION_TTL = 7 * 24 * 3600
# 会话列表最多保留条数
SESSIONS_LIMIT = 100
# 会话标题最长字符数
SESSION_TITLE_LIMIT = 30


def build_key(user_id: Optional[int], session_id: str) -> str:
    """会话 Redis key（与 /ai/conversation 接口保持一致）"""
    return f"ai:conversation:{user_id or 0}:{session_id or 'assistant'}"


# ===================== 会话索引（会话列表） =====================

def sessions_key(user_id: Optional[int]) -> str:
    """会话列表 Redis key"""
    return f"ai:sessions:{user_id or 0}"


def new_session_id() -> str:
    """生成一个新的会话 id"""
    return f"asst_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


async def list_sessions(user_id: Optional[int]) -> List[dict]:
    """获取会话列表（按最后更新时间倒序）"""
    data = await get_cache_json(sessions_key(user_id))
    if not isinstance(data, list):
        return []
    return sorted(data, key=lambda s: s.get("updatedAt") or 0, reverse=True)


async def _save_sessions(user_id: Optional[int], sessions: List[dict]) -> None:
    await set_cache(sessions_key(user_id), sessions, expire=SESSION_TTL)


async def touch_session(
    user_id: Optional[int],
    session_id: str,
    title: Optional[str] = None,
    delta_messages: int = 0,
) -> None:
    """在会话索引里新建 / 更新一个会话（title 只在首次写入时生效）"""
    sessions = await list_sessions(user_id)
    now = int(time.time() * 1000)
    current = next((s for s in sessions if s.get("sessionId") == session_id), None)

    if current is None:
        current = {
            "sessionId": session_id,
            "title": (title or "新会话")[:SESSION_TITLE_LIMIT],
            "createdAt": now,
            "updatedAt": now,
            "messageCount": 0,
        }
        sessions.append(current)
    elif title and current.get("title") in (None, "", "新会话"):
        # 空会话的占位标题，会被首条用户消息替换
        current["title"] = title[:SESSION_TITLE_LIMIT]

    current["updatedAt"] = now
    if delta_messages:
        current["messageCount"] = (current.get("messageCount") or 0) + delta_messages

    sessions = sorted(
        sessions, key=lambda s: s.get("updatedAt") or 0, reverse=True
    )[:SESSIONS_LIMIT]
    await _save_sessions(user_id, sessions)


async def delete_session(user_id: Optional[int], session_id: str) -> None:
    """删除会话：同时清掉消息和列表条目"""
    await clear_messages(user_id, session_id)
    sessions = [
        s for s in await list_sessions(user_id) if s.get("sessionId") != session_id
    ]
    await _save_sessions(user_id, sessions)


async def get_messages(user_id: Optional[int], session_id: str) -> List[dict]:
    """获取某个会话的全部历史消息"""
    data = await get_cache_json(build_key(user_id, session_id))
    return data if isinstance(data, list) else []


async def get_recent_messages(
    user_id: Optional[int], session_id: str, limit: int = CONTEXT_LIMIT
) -> List[dict]:
    """获取最近 N 条历史消息"""
    messages = await get_messages(user_id, session_id)
    if limit and limit > 0:
        return messages[-limit:]
    return messages


async def save_message(
    user_id: Optional[int], session_id: str, role: str, content: str, **extra
) -> None:
    """追加一条消息到会话历史"""
    messages = await get_messages(user_id, session_id)
    item = {
        "role": role,
        "content": content or "",
        "timestamp": int(time.time() * 1000),
    }
    if extra:
        item.update(extra)
    messages.append(item)
    if len(messages) > HISTORY_LIMIT:
        messages = messages[-HISTORY_LIMIT:]
    await set_cache(build_key(user_id, session_id), messages, expire=SESSION_TTL)

    # 同步维护会话列表：用首条用户消息作为会话标题
    title = None
    if role == "user" and content:
        title = content.strip().replace("\n", " ")
    await touch_session(user_id, session_id, title=title, delta_messages=1)


async def clear_messages(user_id: Optional[int], session_id: str) -> bool:
    """清空某个会话的历史"""
    return await delete_cache(build_key(user_id, session_id))


async def build_context_prompt(
    user_id: Optional[int], session_id: str, limit: int = CONTEXT_LIMIT
) -> str:
    """把最近的历史对话拼接成上下文提示词（对齐 springboot3 的 buildContextPrompt）"""
    history = await get_recent_messages(user_id, session_id, limit)
    if not history:
        return ""

    lines = ["【对话历史】"]
    for msg in history:
        role_name = "AI" if msg.get("role") == "assistant" else "用户"
        lines.append(f"{role_name}：{msg.get('content', '')}")
    lines.append("---")
    return "\n".join(lines)