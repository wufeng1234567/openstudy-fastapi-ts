"""
`note_draft_service` —— 用户「写笔记」草稿的读写服务

⚠️ 与 `note` 表里 `status='draft'` 的**正式笔记**是两回事（见 `models.note.UserNoteDraft` 文档）：
本服务管的是**用户维度、至多一篇、无 noteId、不进笔记列表**的临时草稿。前端「写笔记」页与
智能体 `note_manage.save_draft` 都走这里；发布笔记成功后由调用方清空。

存储 = `user_note_draft`（一个用户一行，`user_id` 即主键）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import UserNoteDraft

#: 标签上限（与 note.tags 一致，varchar(500)）
TAGS_MAX = 500


def _clean_tags(value: Any) -> Optional[str]:
    """标签归一成逗号串；空 → None（与 note_write_service.normalize_tags 同口径，独立实现避免循环依赖）"""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        text = str(value).strip()
        if not text:
            return None
        parts = [p.strip() for p in text.replace("，", ",").split(",") if p.strip()]
    if not parts:
        return None
    seen: set = set()
    uniq = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return ",".join(uniq)[:TAGS_MAX]


async def get_draft(db: AsyncSession, user_id: int) -> Optional[UserNoteDraft]:
    """取该用户的后端草稿；没有则 None"""
    row = await db.execute(select(UserNoteDraft).where(UserNoteDraft.user_id == user_id))
    return row.scalar_one_or_none()


async def has_draft(db: AsyncSession, user_id: int) -> bool:
    """该用户是否已有后端草稿（智能体覆盖前用它决定要不要弹确认）"""
    row = await db.execute(
        select(UserNoteDraft.user_id).where(UserNoteDraft.user_id == user_id).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def upsert_draft(
    db: AsyncSession,
    user_id: int,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    markdown_content: Optional[str] = None,
    category_id: Optional[int] = None,
    tags: Any = None,
    is_public: Any = None,
    public_section_id: Optional[int] = None,
) -> UserNoteDraft:
    """保存/覆盖该用户的后端草稿（一个用户一行，存在则更新）

    content 与 markdown_content **互相兜底**（口径同 `note_write_service.create_note`）：
    只给 content 就同时写 markdown_content，反之亦然 —— 前端「写笔记」页统一读 markdown_content。
    """
    if content and not markdown_content:
        markdown_content = content
    elif markdown_content and not content:
        content = markdown_content

    draft = await get_draft(db, user_id)
    if draft is None:
        draft = UserNoteDraft(user_id=user_id)
        db.add(draft)
    if title is not None:
        draft.title = title.strip()[:255] if title else None
    if content is not None:
        draft.content = content
    if markdown_content is not None:
        draft.markdown_content = markdown_content
    if category_id is not None:
        draft.category_id = category_id
    if tags is not None:
        draft.tags = _clean_tags(tags)
    if is_public is not None:
        try:
            draft.is_public = 1 if int(is_public) == 1 else 0
        except (TypeError, ValueError):
            draft.is_public = 1
    if public_section_id is not None:
        draft.public_section_id = public_section_id
    draft.update_time = datetime.now()
    await db.flush()
    await db.refresh(draft)
    return draft


async def clear_draft(db: AsyncSession, user_id: int) -> int:
    """清除该用户的后端草稿（发布成功 / 用户丢弃时）；返回删除行数"""
    res = await db.execute(delete(UserNoteDraft).where(UserNoteDraft.user_id == user_id))
    return int(res.rowcount or 0)


def draft_to_dict(draft: Optional[UserNoteDraft]) -> Optional[Dict[str, Any]]:
    """草稿 → 前端可用 dict（字段名与 notes API 的 camelCase 对齐）"""
    if draft is None:
        return None
    return {
        "title": draft.title or "",
        "content": draft.content or draft.markdown_content or "",
        "markdownContent": draft.markdown_content or draft.content or "",
        "categoryId": draft.category_id,
        "tags": draft.tags or "",
        "isPublic": int(draft.is_public or 0),
        "publicSectionId": draft.public_section_id,
        "updateTime": draft.update_time.isoformat() if draft.update_time else None,
    }
