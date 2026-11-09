"""教学微课生成工具 —— 手动页面与智能对话共用同一份导出能力。

对话示例：
  「用我资料里的《智能体基础概念》生成一份教学 HTML」
  「把这份文档做成 PPT」
  「围绕人工智能知识库生成一套教学课件」

与页面按钮走同一个 service：`micro_course_export_service`。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select

from app.models.rag import RagDocument, RagKnowledgeBase
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.ai.agent.tools.bank_export import save_export_file
from app.services.micro_course_export_service import build_pptx_bytes, get_or_create_micro_course_record


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class MicroCourseTool(AgentTool):
    name = "micro_course_generate"
    label = "生成教学微课"
    description = (
        "Generate a ready-to-present teaching course from one of the user's documents. "
        "It produces a self-contained HTML slide deck and/or a PowerPoint (.pptx) file. "
        "Use it when the user says 'make a micro-course', 'turn this document into a "
        "teaching deck', 'generate slides / PPT', or '用这份资料生成教学课件'. "
        "The source may be identified by `doc_id` (preferred) or by `query` "
        "(file name / keyword). If the user refers to a whole knowledge base, first "
        "resolve one document with `knowledge_base_manage` action=list_documents. "
        "Never invent a document id."
    )
    description_zh = (
        "把资料生成可在线演示的教学 HTML，并可同时导出 PPT；支持手动页面和智能对话。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "doc_id": {
                "type": "integer",
                "description": "Document ID from knowledge_base_manage list_documents.",
            },
            "kb_id": {
                "type": "integer",
                "description": "Knowledge base ID. When doc_id/query is omitted, use the most recent document in this base.",
            },
            "query": {
                "type": "string",
                "description": "Document file name or keyword when doc_id is unknown.",
            },
            "prompt": {
                "type": "string",
                "description": "Optional natural-language instruction for how to revise the deck, e.g. 'add a chart slide and use the architecture image'.",
            },
            "format": {
                "type": "string",
                "enum": ["html", "pptx", "both"],
                "description": "Output format. Default both (HTML for preview + PPT download).",
            },
        },
        "required": [],
    }

    #: 生成 HTML/PPTX 文件，属于产物落盘；不写用户数据，因此不弹确认
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext):
        if not ctx.db:
            return fail("数据库会话不可用，暂时无法生成教学课件")

        doc_id = _int(params.get("doc_id"))
        kb_id = _int(params.get("kb_id"))
        query = str(params.get("query") or "").strip()
        doc = None
        if doc_id:
            doc = await ctx.db.scalar(
                select(RagDocument).where(
                    RagDocument.id == doc_id,
                    RagDocument.user_id == ctx.user_id,
                )
            )
        elif query:
            # 在所有自己的知识库里按文件名找；找不到再按文件名模糊匹配
            rows = (
                await ctx.db.execute(
                    select(RagDocument)
                    .join(RagKnowledgeBase, RagKnowledgeBase.id == RagDocument.kb_id)
                    .where(
                        RagDocument.user_id == ctx.user_id,
                        RagKnowledgeBase.user_id == ctx.user_id,
                        RagKnowledgeBase.del_flag == "0",
                        RagDocument.file_name.ilike(f"%{query}%"),
                    )
                    .order_by(RagDocument.id.desc())
                    .limit(1)
                )
            ).scalars().all()
            doc = rows[0] if rows else None
            if not doc:
                # 文件名没命中时，退回默认资料夹全量文档的关键词匹配
                from app.services.rag import workspace_service
                hits = await workspace_service.search_files(ctx.db, ctx.user_id, query, 1)
                if hits:
                    doc = await ctx.db.scalar(
                        select(RagDocument).where(RagDocument.id == int(hits[0]["docId"]))
                    )
        elif kb_id:
            doc = (
                await ctx.db.execute(
                    select(RagDocument)
                    .where(
                        RagDocument.kb_id == kb_id,
                        RagDocument.user_id == ctx.user_id,
                    )
                    .order_by(RagDocument.id.desc())
                    .limit(1)
                )
            ).scalars().first()
        if not doc:
            return fail("没有找到这份资料。请先告诉我文件名，或到「我的资料」里确认文档名称。")

        fmt = str(params.get("format") or "both").lower()
        if fmt not in ("html", "pptx", "both"):
            fmt = "both"
        try:
            export = await get_or_create_micro_course_record(
                ctx.db,
                ctx.user_id,
                doc,
                prompt=str(params.get("prompt") or "").strip(),
            )
            payload: Dict[str, Any] = {
                "docId": int(doc.id),
                "recordId": export.get("recordId"),
                "version": export.get("version"),
                "fileName": doc.file_name,
                "slideCount": export["slides"],
                "jumpUrl": f"/front/microCourse?docId={int(doc.id)}",
                "message": f"已生成「{doc.file_name}」教学课件，共 {export['slides']} 页",
            }
            if fmt in ("html", "both"):
                rel, name = save_export_file(export["html"].encode("utf-8"), f"{doc.file_name or '教学课件'}.html")
                payload["htmlFile"] = name
                payload["htmlDownloadUrl"] = f"/profile/{rel}"
                payload.setdefault("downloadUrl", f"/profile/{rel}")
                payload.setdefault("fileName", name)
            if fmt in ("pptx", "both"):
                data = build_pptx_bytes(export["deck"], export["html"])
                rel, name = save_export_file(data, f"{doc.file_name or '教学课件'}.pptx")
                payload["fileName"] = name
                payload["downloadUrl"] = f"/profile/{rel}"
            return ok(**payload)
        except Exception as e:  # noqa: BLE001
            return fail(f"生成教学课件失败：{e}")


__all__ = ["MicroCourseTool"]
