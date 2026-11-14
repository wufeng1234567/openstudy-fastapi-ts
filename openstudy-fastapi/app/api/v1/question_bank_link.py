"""资料夹 ↔ 题库逻辑导入 API。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services import bank_knowledge_service, question_bank_link_service
from app.services.rag import source_graph_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class LinkBankRequest(BaseModel):
    bankId: int = 0


_EXTRACTING: set[tuple[int, int, int]] = set()


async def _extract_bank_knowledge(user_id: int, kb_id: int, bank_id: int) -> None:
    """后台抽取题库知识点，避免阻塞关联操作或首次打开。"""
    from app.database import async_session_factory

    key = (int(user_id), int(kb_id), int(bank_id))
    if key in _EXTRACTING:
        return
    _EXTRACTING.add(key)
    try:
        async with async_session_factory() as db:
            await source_graph_service.sync_bank_graph(
                db,
                user_id=int(user_id),
                kb_id=int(kb_id),
                bank_id=int(bank_id),
                source_name="题库",
            )
    except Exception:
        # 抽取失败不反向影响关联关系，后续可在更新知识百科里重试。
        pass
    finally:
        _EXTRACTING.discard(key)


@router.get("/workspace/kbs/{kb_id}/question-banks")
async def list_kb_question_banks(
    kb_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        linked = await question_bank_link_service.list_linked_banks(db, user_id=_uid(current_user), kb_id=int(kb_id))
        available = await question_bank_link_service.list_available_banks(db, user_id=_uid(current_user), kb_id=int(kb_id))
        return success({"linked": linked, "available": available})
    except Exception as exc:  # noqa: BLE001
        return error(f"读取资料夹题库失败：{exc}")


@router.post("/workspace/kbs/{kb_id}/question-banks")
async def link_kb_question_bank(
    kb_id: int,
    data: LinkBankRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        bank = await question_bank_link_service.link_bank(
            db,
            user_id=_uid(current_user),
            kb_id=int(kb_id),
            bank_id=int(data.bankId or 0),
        )
        background_tasks.add_task(
            _extract_bank_knowledge,
            _uid(current_user),
            int(kb_id),
            int(data.bankId or 0),
        )
        return success(bank, "题库已关联，知识点抽取在后台进行")
    except ValueError as exc:
        return error(str(exc))
    except Exception as exc:  # noqa: BLE001
        return error(f"关联题库失败：{exc}")


@router.get("/workspace/kbs/{kb_id}/question-banks/{bank_id}/knowledge")
async def get_bank_knowledge(
    kb_id: int,
    bank_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取题库已落库的知识点；没有缓存时快速返回 pending 并后台抽取。"""
    try:
        result = await bank_knowledge_service.load_bank_knowledge(
            db,
            user_id=_uid(current_user),
            kb_id=int(kb_id),
            bank_id=int(bank_id),
        )
        if result is not None:
            return success(result)

        # 不在请求里调用 LLM：首次点击也立即返回，由后台 sync_bank_graph 落库，
        # 前端轮询到缓存后显示完整知识点。
        background_tasks.add_task(
            _extract_bank_knowledge,
            _uid(current_user),
            int(kb_id),
            int(bank_id),
        )
        return success(
            {
                "summary": "",
                "questionCount": 0,
                "entities": [],
                "relations": [],
                "questions": [],
                "degraded": {"pending": True},
            },
            "题库知识点正在后台抽取",
        )
    except Exception as exc:  # noqa: BLE001
        return error(f"读取题库知识点失败：{exc}")


@router.delete("/workspace/kbs/{kb_id}/question-banks/{bank_id}")
async def unlink_kb_question_bank(
    kb_id: int,
    bank_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await question_bank_link_service.unlink_bank(
            db,
            user_id=_uid(current_user),
            kb_id=int(kb_id),
            bank_id=int(bank_id),
        )
        return success({"unlinked": int(bank_id)})
    except Exception as exc:  # noqa: BLE001
        return error(f"取消关联题库失败：{exc}")
