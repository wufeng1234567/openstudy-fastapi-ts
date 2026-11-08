"""资料夹 ↔ 题库逻辑导入 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services import question_bank_link_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class LinkBankRequest(BaseModel):
    bankId: int = 0


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
        return success(bank)
    except ValueError as exc:
        return error(str(exc))
    except Exception as exc:  # noqa: BLE001
        return error(f"关联题库失败：{exc}")


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
