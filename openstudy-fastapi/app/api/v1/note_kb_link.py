"""资料夹 ↔ 笔记逻辑导入 API（P2 补齐「笔记导入资料夹」）。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services import note_kb_link_service, source_entity_service
from app.services.rag import source_graph_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class LinkNoteRequest(BaseModel):
    noteId: int = 0


async def _extract_note_knowledge(user_id: int, kb_id: int, note_id: int) -> None:
    """后台把笔记文本抽成图谱实体/关系；失败不影响关联本身。"""
    from app.database import async_session_factory

    async with async_session_factory() as db:
        try:
            text = await note_kb_link_service.note_text(db, user_id=int(user_id), note_id=int(note_id))
            if not text.strip():
                return
            await source_graph_service.sync_text_source(
                db,
                user_id=int(user_id),
                kb_id=int(kb_id),
                source_type="note",
                source_id=int(note_id),
                source_name="笔记",
                text=text,
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - 后台可选增强，不能反向破坏关联
            logger.warning("笔记知识点抽取失败 note={} kb={}: {}", note_id, kb_id, exc)
            await db.rollback()


@router.get("/workspace/kbs/{kb_id}/notes")
async def list_kb_notes(
    kb_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        linked = await note_kb_link_service.list_linked_notes(db, user_id=_uid(current_user), kb_id=int(kb_id))
        available = await note_kb_link_service.list_available_notes(db, user_id=_uid(current_user), kb_id=int(kb_id))
        return success({"linked": linked, "available": available})
    except Exception as exc:  # noqa: BLE001
        return error(f"读取资料夹笔记失败：{exc}")


@router.post("/workspace/kbs/{kb_id}/notes")
async def link_kb_note(
    kb_id: int,
    data: LinkNoteRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        note = await note_kb_link_service.link_note(
            db,
            user_id=_uid(current_user),
            kb_id=int(kb_id),
            note_id=int(data.noteId or 0),
        )
        background_tasks.add_task(
            _extract_note_knowledge,
            _uid(current_user),
            int(kb_id),
            int(data.noteId or 0),
        )
        return success(note, "笔记已关联到资料夹，知识点抽取在后台进行")
    except ValueError as exc:
        return error(str(exc))
    except Exception as exc:  # noqa: BLE001
        return error(f"关联笔记失败：{exc}")


@router.get("/workspace/kbs/{kb_id}/notes/{note_id}/knowledge")
async def get_note_knowledge(
    kb_id: int,
    note_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取笔记可抽取的知识点，供资料夹设置页预览。"""
    try:
        text = await note_kb_link_service.note_text(db, user_id=_uid(current_user), note_id=int(note_id))
        if not text.strip():
            return error("笔记正文为空，无法抽取知识点")
        result = await source_entity_service.extract_entities_from_text(
            db,
            user_id=_uid(current_user),
            source_type="note",
            source_id=int(note_id),
            source_name="笔记",
            text=text,
            use_llm=True,
        )
        return success(result)
    except Exception as exc:  # noqa: BLE001
        return error(f"读取笔记知识点失败：{exc}")


@router.delete("/workspace/kbs/{kb_id}/notes/{note_id}")
async def unlink_kb_note(
    kb_id: int,
    note_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await note_kb_link_service.unlink_note(
            db,
            user_id=_uid(current_user),
            kb_id=int(kb_id),
            note_id=int(note_id),
        )
        return success({"unlinked": int(note_id)})
    except Exception as exc:  # noqa: BLE001
        return error(f"取消关联笔记失败：{exc}")
