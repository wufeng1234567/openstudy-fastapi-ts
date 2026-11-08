"""资料诊疗室新接口：智能报告。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error, success
from app.core.security import get_current_user
from app.database import get_db
from app.services.document_smart_report_service import generate_smart_report
from app.services.rag import rag_write_service

router = APIRouter(prefix="/rag")


def _uid(current_user: dict) -> int:
    return int(current_user.get("userId") or current_user.get("user_id") or 0)


class SmartReportRequest(BaseModel):
    instruction: str = ""
    useLlm: bool = True


@router.post("/workspace/documents/{doc_id}/smart-report/generate")
async def generate_document_smart_report(
    doc_id: int,
    data: SmartReportRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        from app.services.document_health_service import build_document_health

        doc = await rag_write_service.get_document(db, _uid(current_user), int(doc_id))
        report = await asyncio.to_thread(build_document_health, doc)
        smart = await generate_smart_report(
            db,
            doc_name=str(getattr(doc, "file_name", "") or "未命名资料"),
            report=report,
            instruction=data.instruction,
            use_llm=bool(data.useLlm),
        )
        return success(
            {
                "report": smart,
                "baseline": {
                    "score": report.get("score"),
                    "grade": report.get("grade") or {},
                    "issueCount": len(report.get("issues") or []),
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return error(f"生成智能报告失败：{exc}")


__all__ = ["router"]
