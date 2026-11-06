"""`wiki_manage` —— 知识百科主题页与画廊图片联动工具。

为什么单独一个工具，而不是把 actions 塞进 `knowledge_search`
------------------------------------------------------------
`knowledge_search` 是**只读检索**：它回答“资料里哪段相关”，结果要回灌给模型。
主题页的 list/get/create/update/delete/attach_image 是**内容管理**：有归属校验、
版本快照、确认卡、破坏性删除，和检索不在一个安全层级。

本工具只负责参数校验与给人看的回执；真正写库、留版本、重建 Wiki 检索块
全部复用 `services/rag/wiki_service.py`。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

_WRITE_ACTIONS = {"create", "update", "delete", "attach_image", "detach_image"}
_DESTRUCTIVE_ACTIONS = {"delete"}
_MAX_SECTIONS = 8


def _as_sections(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value[:_MAX_SECTIONS]:
        if isinstance(item, dict):
            out.append(item)
    return out


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class WikiManageTool(AgentTool):
    name = "wiki_manage"
    description = (
        "Manage the user's Knowledge Wiki pages (readable topic pages generated from "
        "their materials) and their gallery-image links. "
        "action values: list=list pages (optional `kb_id`, `query`, `limit`), "
        "get=read one page including sections/sources/images (requires `page_id`), "
        "search=find pages by title/summary (`query`), "
        "create=create a manual page (requires `kb_id`, `title`, `sections`), "
        "update=edit page title/summary/sections (requires `page_id`; at least one field), "
        "delete=delete one page (requires `page_id`; irreversible), "
        "attach_image=link a gallery image to a page (requires `page_id`, `asset_key`; "
        "optional `quote`), detach_image=remove a page-image link (requires `page_id` "
        "and `reference_id`). "
        "IMPORTANT: page sections must be an array of {heading, body, sourceChunkIds}. "
        "For generated pages, preserve existing sourceChunkIds when editing. "
        "Never invent page IDs, asset keys or reference IDs; call list/get first."
    )
    label = "知识百科管理"
    description_zh = (
        "管理知识百科主题页与画廊图片关联：list/get/search=查看，"
        "create/update=新建或编辑，delete=删除，attach_image/detach_image=挂图或取消挂图。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "list", "get", "search", "create", "update", "delete",
                    "attach_image", "detach_image",
                ],
            },
            "kb_id": {
                "type": "integer",
                "description": "Knowledge base ID (used by list/create).",
            },
            "page_id": {
                "type": "integer",
                "description": "Wiki page ID (used by get/update/delete/attach_image/detach_image).",
            },
            "query": {
                "type": "string",
                "description": "Optional title/summary keyword for list/search.",
            },
            "limit": {
                "type": "integer",
                "description": "Max pages to return (default 20, max 100).",
            },
            "title": {
                "type": "string",
                "description": "Page title (required for create; editable via update).",
            },
            "summary": {
                "type": "string",
                "description": "One-paragraph summary shown above the page.",
            },
            "sections": {
                "type": "array",
                "description": (
                    "Page sections, each {heading: string, body: string, "
                    "sourceChunkIds: number[]}. Required for create, optional for update."
                ),
                "items": {"type": "object"},
            },
            "asset_key": {
                "type": "string",
                "description": "Gallery asset key, e.g. doc:123:0 or chat:45 (used by attach_image).",
            },
            "reference_id": {
                "type": "integer",
                "description": "Existing content-reference ID returned by attach_image (used by detach_image).",
            },
            "quote": {
                "type": "string",
                "description": "Optional note/quote explaining why the image belongs to the page.",
            },
        },
        "required": ["action"],
    }
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _DESTRUCTIVE_ACTIONS

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        if action not in {"update", "delete"}:
            return {}
        page_id = _to_int(params.get("page_id"))
        if page_id is None:
            return {}
        try:
            from app.services.rag.wiki_service import get_wiki_page

            page = await get_wiki_page(ctx.db, ctx.user_id, page_id)
            return {"pageId": page["pageId"], "title": page["title"], "status": page["status"]}
        except Exception:  # noqa: BLE001
            return {}

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "").strip().lower()
        if action in {"list", "search"}:
            return await self._list(params, ctx, search=(action == "search"))
        if action == "get":
            return await self._get(params, ctx)
        if action == "create":
            return await self._create(params, ctx)
        if action == "update":
            return await self._update(params, ctx)
        if action == "delete":
            return await self._delete(params, ctx)
        if action == "attach_image":
            return await self._attach_image(params, ctx)
        if action == "detach_image":
            return await self._detach_image(params, ctx)
        return fail(
            f"未知操作: {action}",
            "action 只能是 list / get / search / create / update / delete / attach_image / detach_image",
        )

    async def _list(self, params: Dict[str, Any], ctx: ToolContext, *, search: bool) -> Dict[str, Any]:
        from app.services.rag.wiki_service import list_wiki_pages

        kb_id = _to_int(params.get("kb_id"))
        limit = _to_int(params.get("limit")) or 20
        try:
            result = await list_wiki_pages(
                ctx.db,
                ctx.user_id,
                kb_id=kb_id,
                q=str(params.get("query") or ""),
                limit=max(1, min(100, limit)),
            )
        except Exception as exc:  # noqa: BLE001
            return fail(f"读取知识百科失败：{exc}", "请先确认资料夹 ID，或 action=list 不带 kb_id")
        pages = result.get("pages") or []
        return ok(
            action="search" if search else "list",
            count=len(pages),
            pages=pages,
            stats=result.get("stats") or {},
            message=(
                f"找到 {len(pages)} 个主题页" if pages
                else ("没有匹配的主题页" if search else "当前还没有知识百科主题页")
            ),
        )

    async def _get(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        page_id = _to_int(params.get("page_id"))
        if page_id is None:
            return fail("读取主题页需要 page_id", "请先 action=list 找到 pageId")
        try:
            from app.services.rag.wiki_service import get_wiki_page

            page = await get_wiki_page(ctx.db, ctx.user_id, page_id)
        except Exception as exc:  # noqa: BLE001
            return fail(f"读取主题页失败：{exc}", "请确认这个 pageId 是否属于当前用户")
        return ok(action="get", **page, message=f"已读取主题页「{page['title']}」")

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        title = str(params.get("title") or "").strip()
        if kb_id is None or not title:
            return fail("创建主题页需要 kb_id 和 title", "请先 action=list 确认资料夹，再传标题")
        from app.database import async_session_factory
        from app.services.rag.wiki_service import create_manual_wiki_page

        try:
            async with async_session_factory() as db:
                page = await create_manual_wiki_page(
                    db,
                    ctx.user_id,
                    kb_id,
                    title=title,
                    summary=str(params.get("summary") or ""),
                    sections=_as_sections(params.get("sections")),
                )
        except Exception as exc:  # noqa: BLE001
            return fail(f"创建主题页失败：{exc}", "请检查标题是否重复、资料夹是否存在")
        return ok(action="create", **page, message=f"主题页「{page['title']}」已创建")

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        page_id = _to_int(params.get("page_id"))
        if page_id is None:
            return fail("编辑主题页需要 page_id", "请先 action=list 找到 pageId")
        if params.get("title") is None and params.get("summary") is None and params.get("sections") is None:
            return fail("没有提供任何要修改的字段", "请至少给出 title / summary / sections 之一")
        from app.database import async_session_factory
        from app.services.rag.wiki_service import update_wiki_page

        try:
            async with async_session_factory() as db:
                page = await update_wiki_page(
                    db,
                    ctx.user_id,
                    page_id,
                    title=params.get("title"),
                    summary=params.get("summary"),
                    sections=_as_sections(params.get("sections")) if params.get("sections") is not None else None,
                    change_type="agent",
                    created_by="agent",
                )
        except Exception as exc:  # noqa: BLE001
            return fail(f"编辑主题页失败：{exc}", "请确认 pageId 是否属于当前用户、字段是否合法")
        return ok(action="update", **page, message=f"主题页「{page['title']}」已更新")

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        page_id = _to_int(params.get("page_id"))
        if page_id is None:
            return fail("删除主题页需要 page_id", "请先 action=list 找到 pageId")
        from app.database import async_session_factory
        from app.services.rag.wiki_service import delete_wiki_page

        try:
            async with async_session_factory() as db:
                result = await delete_wiki_page(db, ctx.user_id, page_id)
        except Exception as exc:  # noqa: BLE001
            return fail(f"删除主题页失败：{exc}", "请确认 pageId 是否属于当前用户")
        return ok(action="delete", **result, message=f"主题页「{result['title']}」已删除")

    async def _attach_image(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        page_id = _to_int(params.get("page_id"))
        asset_key = str(params.get("asset_key") or "").strip()
        if page_id is None or not asset_key:
            return fail("关联图片需要 page_id 和 asset_key", "请先从画廊列表拿到 assetKey")
        from app.database import async_session_factory
        from app.services.rag.wiki_service import attach_wiki_image

        try:
            async with async_session_factory() as db:
                result = await attach_wiki_image(
                    db, ctx.user_id, page_id, asset_key, str(params.get("quote") or "")
                )
        except Exception as exc:  # noqa: BLE001
            return fail(f"关联图片失败：{exc}", "请确认图片和主题页都属于当前用户")
        return ok(action="attach_image", **result, message="图片已关联到主题页")

    async def _detach_image(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        page_id = _to_int(params.get("page_id"))
        reference_id = _to_int(params.get("reference_id"))
        if page_id is None or reference_id is None:
            return fail("取消关联需要 page_id 和 reference_id", "请先 action=get 查看主题页图片引用")
        from app.database import async_session_factory
        from app.services.rag.wiki_service import detach_wiki_image

        try:
            async with async_session_factory() as db:
                result = await detach_wiki_image(db, ctx.user_id, page_id, reference_id)
        except Exception as exc:  # noqa: BLE001
            return fail(f"取消图片关联失败：{exc}", "请确认引用属于该主题页")
        return ok(action="detach_image", **result, message="图片关联已取消")


__all__ = ["WikiManageTool"]
