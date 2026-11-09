"""`note_kb_link` —— 把笔记逻辑导入/移出资料夹，并预览可抽取的知识点。

只写 `note_kb_link` 引用，不复制笔记正文；笔记仍是 note 表的事实数据。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services import note_kb_link_service, source_entity_service
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _resolve_kb_id(ctx: ToolContext, params: Dict[str, Any]) -> int:
    from app.services.rag import rag_write_service as rws

    kid = _to_int(params.get("kb_id"))
    if kid and kid > 0:
        try:
            await rws.get_knowledge_base(ctx.db, ctx.user_id, kid)
            return kid
        except Exception:  # noqa: BLE001
            return 0
    bases = await rws.list_knowledge_bases(ctx.db, ctx.user_id)
    if not bases:
        return 0
    ordered = sorted(
        bases,
        key=lambda item: (
            0 if int(item.get("isDefault") or 0) == 1 else 1,
            -int(item.get("docCount") or 0),
        ),
    )
    return int(ordered[0].get("kbId") or 0)


class NoteKbLinkTool(AgentTool):
    name = "note_kb_link"
    description = (
        "List, link or unlink the user's study notes to a material folder (资料夹), "
        "or preview the knowledge points that can be extracted from one note. "
        "Use it when the user says '把这笔记放进资料夹', '把笔记导入资料夹', "
        "'资料夹里有哪些笔记', or asks what knowledge a note contains. "
        "It only creates a logical reference in note_kb_link; it never copies the "
        "note body. action values: list / link / unlink / knowledge."
    )
    label = "笔记资料夹"
    description_zh = (
        "笔记资料夹：list=资料夹已关联/可关联的笔记，link=把笔记关联到资料夹，"
        "unlink=取消关联，knowledge=预览笔记可抽取的知识点；不复制笔记正文。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["list", "link", "unlink", "knowledge"],
            },
            "kb_id": {
                "type": "integer",
                "description": "Material folder (knowledge base) ID. Omit to use the default workspace.",
            },
            "note_id": {
                "type": "integer",
                "description": "Note ID for link / unlink / knowledge.",
            },
        },
        "required": ["action"],
    }
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "").strip().lower() == "unlink"

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "").strip().lower() == "unlink"

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "list").strip().lower()
        if action not in {"list", "link", "unlink", "knowledge"}:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / link / unlink / knowledge。",
            )
        kb_id = await _resolve_kb_id(ctx, params)
        if kb_id <= 0:
            return fail("没有可用资料夹", "请先创建一个资料夹，或显式传 kb_id。")
        note_id = _to_int(params.get("note_id")) or 0

        if action == "list":
            linked = await note_kb_link_service.list_linked_notes(
                ctx.db, user_id=ctx.user_id, kb_id=kb_id
            )
            available = await note_kb_link_service.list_available_notes(
                ctx.db, user_id=ctx.user_id, kb_id=kb_id
            )
            return ok(
                action="list",
                kbId=kb_id,
                linked=linked,
                available=available,
                message=f"资料夹已关联 {len(linked)} 条笔记，另有 {len(available)} 条可关联。",
            )

        if note_id <= 0:
            return fail(f"{action} 需要 note_id", "请先确认要操作的笔记 ID。")

        if action == "link":
            try:
                note = await note_kb_link_service.link_note(
                    ctx.db, user_id=ctx.user_id, kb_id=kb_id, note_id=note_id
                )
            except ValueError as exc:
                return fail(str(exc), "请确认这条笔记属于当前用户。")
            return ok(
                action="link",
                kbId=kb_id,
                note=note,
                message=f"已把「{note.get('title')}」关联到资料夹。",
            )

        if action == "unlink":
            await note_kb_link_service.unlink_note(
                ctx.db, user_id=ctx.user_id, kb_id=kb_id, note_id=note_id
            )
            return ok(action="unlink", kbId=kb_id, noteId=note_id, message="已取消笔记与资料夹的关联。")

        text = await note_kb_link_service.note_text(ctx.db, user_id=ctx.user_id, note_id=note_id)
        if not text.strip():
            return fail("笔记正文为空", "请先补全笔记内容再抽取知识点。")
        result = await source_entity_service.extract_entities_from_text(
            ctx.db,
            user_id=ctx.user_id,
            source_type="note",
            source_id=note_id,
            source_name="笔记",
            text=text,
            use_llm=True,
        )
        return ok(
            action="knowledge",
            kbId=kb_id,
            noteId=note_id,
            entities=result.get("entities") or [],
            relations=result.get("relations") or [],
            degraded=result.get("degraded") or {},
            message="已按笔记正文抽取可入库的知识点。",
        )
