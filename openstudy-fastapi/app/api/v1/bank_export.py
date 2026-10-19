"""
题库导出 API —— Word / PDF

单独成文件而不是塞进 `questions.py`（那个文件已经 3600+ 行），
但路由仍挂在同一个 `router` 前缀下，前端调用方式与其它题库接口一致。
"""

from __future__ import annotations

import io
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.response import error
from app.core.security import get_current_user
from app.database import get_db
from app.models.question import QuestionBank, QuestionMain
from app.api.v1.questions import format_bank, format_question, _can_view_bank

router = APIRouter()

#: 题型 → 中文（与 question_write_service.QUESTION_TYPE_TEXT 同源，这里避免循环导入直接取）
def _type_text(qtype: int) -> str:
    from app.services.question_write_service import QUESTION_TYPE_TEXT

    return QUESTION_TYPE_TEXT.get(qtype, "未知")


#: 文件名里不允许出现的字符（Windows 最严：\ / : * ? " < > |）
_RE_BAD_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _safe_filename(name: str, fallback: str = "题库") -> str:
    """把题库名清洗成可做文件名的形式（保留中文，去掉非法字符）"""
    s = _RE_BAD_FILENAME.sub("_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    if not s:
        s = fallback
    return s[:80]


def _content_disposition(filename: str) -> str:
    """
    构造 Content-Disposition

    ⚠️ 中文文件名必须同时给 `filename`（ASCII 兜底）和 `filename*`（RFC 5987）。
    只给 `filename="中文.docx"` 时，Starlette 会按 latin-1 编码头部 → UnicodeEncodeError → 500。
    """
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "export"
    return (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


@router.get("/questionBank/questionBank/{bank_id}/export")
async def export_bank(
    bank_id: int,
    format: str = Query("docx", description="导出格式：docx / pdf"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    导出题库为 Word / PDF

    权限与「查看题库详情」一致（私密题库仅作者与已领取分享者可导出）：
    既然能看到题目内容，导出只是换一种呈现方式，不该额外设卡；
    反过来，看不到的题库也不能借导出接口绕过限制。
    """
    fmt = (format or "docx").lower().strip()
    if fmt not in ("docx", "pdf"):
        return error("不支持的导出格式（仅支持 docx / pdf）", code=400)

    bank = (
        await db.execute(select(QuestionBank).where(QuestionBank.id == bank_id))
    ).scalar_one_or_none()
    if not bank:
        return error("题库不存在")

    if not await _can_view_bank(db, bank, current_user.get("user_id")):
        return error("无权导出该题库（私密题库仅作者与已获取分享的用户可见）", code=403)

    # 题目按 sort_order 排（与练习时的顺序一致）；子题一并预取，避免 N+1
    q_rows = (
        await db.execute(
            select(QuestionMain)
            .options(selectinload(QuestionMain.sub_questions))
            .where(QuestionMain.bank_id == bank_id, QuestionMain.status == "0")
            .order_by(QuestionMain.sort_order, QuestionMain.id)
        )
    ).scalars().all()

    bank_dict = format_bank(bank)
    questions = []
    for q in q_rows:
        item = format_question(q)
        item["questionTypeText"] = _type_text(q.question_type)
        # 子题也补一遍题型中文，导出时直接用
        for sub in item.get("subQuestions") or []:
            sub["questionTypeText"] = _type_text(sub.get("questionType") or 1)
        questions.append(item)

    base_name = _safe_filename(bank.bank_name, f"题库{bank_id}")

    try:
        if fmt == "docx":
            from app.services.bank_export_service import export_bank_docx

            data = export_bank_docx(bank_dict, questions)
            media_type = (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            filename = f"{base_name}.docx"
        else:
            from app.services.bank_export_service import export_bank_pdf

            data = export_bank_pdf(bank_dict, questions)
            media_type = "application/pdf"
            filename = f"{base_name}.pdf"
    except Exception as exc:  # noqa: BLE001
        from loguru import logger

        logger.exception("[export] 题库 {} 导出 {} 失败", bank_id, fmt)
        return error(f"导出失败：{exc}", code=500)

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition(filename),
            # 让前端能从响应头读到文件名（跨域时需要显式暴露）
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
