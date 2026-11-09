"""笔记 ↔ 资料夹逻辑关联。

只建立 `note_kb_link` 引用，不复制笔记正文；笔记事实仍只在 `note` 表维护。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.note_kb_link import NoteKbLink


def _serialize_note(note: Note) -> Dict[str, Any]:
    return {
        "noteId": int(note.note_id),
        "id": int(note.note_id),
        "title": str(note.title or "未命名笔记"),
        "summary": str(note.markdown_content or note.content or "")[:180],
        "isPublic": int(note.is_public or 0),
        "createTime": note.create_time.isoformat(sep=" ", timespec="seconds") if note.create_time else "",
    }


async def linked_note_ids(db: AsyncSession, *, user_id: int, kb_id: int) -> List[int]:
    if int(user_id or 0) <= 0 or int(kb_id or 0) <= 0:
        return []
    rows = (
        await db.execute(
            select(NoteKbLink.note_id).where(
                NoteKbLink.user_id == int(user_id),
                NoteKbLink.kb_id == int(kb_id),
            )
        )
    ).scalars().all()
    return sorted({int(item) for item in rows if int(item or 0) > 0})


async def list_linked_notes(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    ids = await linked_note_ids(db, user_id=user_id, kb_id=kb_id)
    if not ids:
        return []
    notes = (
        await db.execute(
            select(Note).where(
                Note.note_id.in_(ids),
                Note.user_id == int(user_id),
                Note.del_flag == "0",
            )
        )
    ).scalars().all()
    return [_serialize_note(note) for note in notes]


async def list_available_notes(db: AsyncSession, *, user_id: int, kb_id: int) -> List[Dict[str, Any]]:
    linked = set(await linked_note_ids(db, user_id=user_id, kb_id=kb_id))
    notes = (
        await db.execute(
            select(Note)
            .where(Note.user_id == int(user_id), Note.del_flag == "0")
            .order_by(Note.update_time.desc(), Note.note_id.desc())
        )
    ).scalars().all()
    result = []
    for note in notes:
        item = _serialize_note(note)
        item["linked"] = int(note.note_id) in linked
        result.append(item)
    return result


async def link_note(db: AsyncSession, *, user_id: int, kb_id: int, note_id: int) -> Dict[str, Any]:
    note = (
        await db.execute(
            select(Note).where(
                Note.note_id == int(note_id or 0),
                Note.user_id == int(user_id),
                Note.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if not note:
        raise ValueError("笔记不存在或不属于当前用户")
    existing = (
        await db.execute(
            select(NoteKbLink).where(
                NoteKbLink.user_id == int(user_id),
                NoteKbLink.kb_id == int(kb_id),
                NoteKbLink.note_id == int(note_id),
            )
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(NoteKbLink(user_id=int(user_id), kb_id=int(kb_id), note_id=int(note_id)))
        await db.flush()
    return _serialize_note(note)


async def unlink_note(db: AsyncSession, *, user_id: int, kb_id: int, note_id: int) -> None:
    await db.execute(
        delete(NoteKbLink).where(
            NoteKbLink.user_id == int(user_id),
            NoteKbLink.kb_id == int(kb_id),
            NoteKbLink.note_id == int(note_id),
        )
    )
    await db.flush()


async def note_text(db: AsyncSession, *, user_id: int, note_id: int) -> str:
    note = (
        await db.execute(
            select(Note).where(
                Note.note_id == int(note_id),
                Note.user_id == int(user_id),
                Note.del_flag == "0",
            )
        )
    ).scalar_one_or_none()
    if not note:
        return ""
    return "\n".join(str(item or "") for item in (note.title, note.tags, note.markdown_content, note.content))


__all__ = [
    "linked_note_ids",
    "list_linked_notes",
    "list_available_notes",
    "link_note",
    "unlink_note",
    "note_text",
]
