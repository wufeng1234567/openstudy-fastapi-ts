"""资料夹 ↔ 题库逻辑导入 API。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.models.question import QuestionMain
from app.services import question_bank_link_service, source_entity_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class LinkBankRequest(BaseModel):
    bankId: int = 0


async def _extract_bank_knowledge(user_id: int, bank_id: int) -> None:
    """后台抽取题库知识点，避免阻塞关联操作。"""
    from app.database import async_session_factory

    async with async_session_factory() as db:
        try:
            await source_entity_service.extract_bank_entities(
                db,
                user_id=int(user_id),
                bank_id=int(bank_id),
                limit=200,
                chunk_size=20,
                use_llm=True,
            )
        except Exception:
            # 抽取失败不反向影响关联关系，后续可在更新知识百科里重试。
            pass


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
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取题库已抽取的知识点，并附上可回看的题目样例。"""
    try:
        result = await source_entity_service.extract_bank_entities(
            db,
            user_id=_uid(current_user),
            bank_id=int(bank_id),
            limit=80,
            chunk_size=20,
            use_llm=True,
        )
        rows = (
            await db.execute(
                select(QuestionMain.id, QuestionMain.question_text, QuestionMain.analysis)
                .where(QuestionMain.bank_id == int(bank_id), QuestionMain.status == "0")
                .order_by(QuestionMain.id.asc())
                .limit(200)
            )
        ).all()
        return success(
            {
                "summary": result.get("summary") or "",
                "questionCount": result.get("questionCount") or 0,
                "entities": result.get("entities") or [],
                "relations": result.get("relations") or [],
                "questions": [
                    {
                        "id": int(row.id),
                        "text": str(row.question_text or "")[:500],
                        "analysis": str(row.analysis or "")[:500],
                    }
                    for row in rows
                ],
                "degraded": result.get("degraded") or {},
            }
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
