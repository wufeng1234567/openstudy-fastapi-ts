"""
`knowledge_base_manage` —— 知识库管理工具（Agent 自封装）

复用 `services/rag/rag_write_service.py` 的既有函数（`list_knowledge_bases` /
`create_knowledge_base` / `update_knowledge_base` / `delete_knowledge_base` /
`list_documents` / `get_document` / `delete_document`），**一行 SQL 都不重写** ——
归属校验、命名冲突、NUL 清洗、计数重算都在那里。

删除语义是**混合**的（报告里也写清了，别搞混）
--------------------------------------------
· **知识库本身 = 逻辑删**（`del_flag='2'`，与笔记一致）
· **它的文档与分块 = 物理删**（分块带 1024 维向量，留着既占空间又可能被检索到）
· **单个文档 = 物理删**（`delete_document`：先删分块再删文档，并重算知识库计数）
所以两个删除动作都是破坏性的：即使 `autoConfirm` 开着也必须二次确认。

`disabled` 是**检索闸门**，别动它的口径
-------------------------------------
`disabled=1` 的知识库**不参与检索**，也不进 L1 提示词（`runtime_context._kb_block`
与 `knowledge_search._list` 都用 `include_disabled=False`）。本工具是**管理**入口，
所以 `list` 用 `include_disabled=True`（管理列表口径）：看不见被屏蔽的库，
用户就永远没法把它开回来。为了让模型不误判，每一项都带上 `disabled` 与
`disabledText`（启用中 / 已屏蔽）—— 这与那两条**检索**路径的口径不冲突：
真正拦住检索的是 `resolve_knowledge_bases`，不是「列表里有没有它」。

⚠️ 刻意**不做**「从纯文本建文档」：`create_document` + `replace_chunks` 会真调
embedding 接口（花钱）。谁要加这个能力，先拿放行，别顺手接上。

⚠️ 写操作为什么自己开会话：`rag_write_service` 的写函数内部会 `commit()`，
而 `loop._execute_tool` 会把写工具包进 SAVEPOINT —— 两者相遇时数据写了却抛
`Can't operate on closed transaction inside context manager`（实测见
`tests/_probe_nested_commit.py`）。读操作仍走 `ctx.db`（只读、不 commit，无害）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from app.models.rag import RagDocument, RagDocumentChunk
from app.services.ai.agent.base import (
    OP_RESTORE,
    OP_SOFT_DELETE,
    REASON_CONTENT_DESTROYED,
    REASON_DOCUMENTS_DESTROYED,
    REASON_MISSING_TARGET_ID,
    REASON_NO_BEFORE_STATE,
    AgentTool,
    ToolContext,
    fail,
    ok,
)
from app.services.rag import rag_write_service as rws
from app.services.rag.rag_write_service import RagConflict, RagNotFound

#: 文档列表一页最多几条
MAX_DOCS_PAGE = 100
DEFAULT_DOCS_PAGE = 30

#: `update` 能改的字段 → 中文（确认卡片「将修改」直接打在用户脸上，别拼英文键名）
_WILL_CHANGE = (
    ("name", "名称"),
    ("description", "简介"),
    ("disabled", "启用状态"),
)


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _disabled_text(value: Any) -> str:
    return "已屏蔽（不参与检索）" if int(value or 0) else "启用中"


class KnowledgeBaseManageTool(AgentTool):
    name = "knowledge_base_manage"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Manage the user's knowledge bases (the collections of documents they uploaded). "
        "action values: "
        "list=show the user's knowledge bases with document counts and whether each one is "
        "blocked from retrieval, "
        "create=create an empty knowledge base (requires `name`), "
        "update=rename / re-describe / **enable or block** a knowledge base (pass `kb_id` "
        "plus at least one of `name` / `description` / `disabled`), "
        "delete=delete a knowledge base AND all of its documents and text chunks (pass "
        "`kb_id`; irreversible), "
        "list_documents=list the documents inside one knowledge base (pass `kb_id`, paged "
        "via `limit`/`offset`), "
        "delete_document=delete one document and its chunks (pass `doc_id`; irreversible). "
        "IMPORTANT: `disabled=1` means the knowledge base is EXCLUDED from retrieval — "
        "`knowledge_search` and your own context will not see its contents. Use "
        "`disabled=0` to let the user search it again. "
        "NOTE: you cannot UPLOAD documents or create one from text with this tool — the "
        "user uploads files themselves on the knowledge base page; point them there. "
        "To read the contents, use `knowledge_search` instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "知识库管理"
    description_zh = (
        "管理知识库（我上传的文档集合）：list=列库（含文档数、是否已被屏蔽）、"
        "create=新建空库、update=改名 / 改描述 / 启用或屏蔽、delete=删库、"
        "list_documents=列某个库里的文档、delete_document=删文档。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "list",
                    "create",
                    "update",
                    "delete",
                    "list_documents",
                    "delete_document",
                ],
            },
            "kb_id": {
                "type": "integer",
                "description": (
                    "Knowledge base ID (used by update/delete/list_documents). Take it from "
                    "action=list."
                ),
            },
            "name": {
                "type": "string",
                "description": "Knowledge base name (required for create; editable via update).",
            },
            "description": {
                "type": "string",
                "description": "Knowledge base description (optional on create/update).",
            },
            "disabled": {
                "type": "integer",
                "description": (
                    "Only for update: 1=block this knowledge base from retrieval, "
                    "0=enable it again."
                ),
                "enum": [0, 1],
            },
            "doc_id": {
                "type": "integer",
                "description": (
                    "Document ID (used by delete_document). Take it from "
                    "action=list_documents."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"Max documents per page (used by list_documents; default "
                    f"{DEFAULT_DOCS_PAGE}, max {MAX_DOCS_PAGE})."
                ),
            },
            "offset": {
                "type": "integer",
                "description": "0-based offset for list_documents (default 0).",
            },
        },
        "required": ["action"],
    }
    write_operation = True

    _WRITE_ACTIONS = {"create", "update", "delete", "delete_document"}
    _DESTRUCTIVE_ACTIONS = {"delete", "delete_document"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """`create` 一次只建一个知识库（规模固定），不额外强制确认"""
        return False

    def undo_plan(self, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
        """声明「这一笔知识库操作用什么撤」（契约见 `base.AgentTool.undo_plan`）

        ⚠️ 知识库的删除语义是**混合**的（见模块 docstring），所以「能不能撤」分四种情况：

          · `create` → 把新建的知识库**软删**（`del_flag='2'`）：库是空的，干净可撤
          · `delete` → 把库**恢复**（`del_flag='0'`），但 **`undoable=True` + reason
            `documents_destroyed`** = **部分回退**：它的文档与分块是被**物理删**的
            （分块带 1024 维向量，重建要重算 embedding、要花钱）。卡片必须显示
            「知识库恢复了，但里面的文档回不来」，不能只说「已回退」。
          · `delete_document` → **不可撤**：分块物理删 + 重算 embedding 花钱。
          · `update` → **不可撤**：本工具层拿不到改前值（写在 `rag_write_service` 的
            自己那个会话里，见 `rws.update_knowledge_base`），没有旧值就没法写回。
        """
        action = str(params.get("action") or "")
        if action in ("create", "delete"):
            kb_id = _to_int(result.get("kbId"))
            if kb_id is None:
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_SOFT_DELETE if action == "create" else OP_RESTORE,
                "targetTable": "rag_knowledge_base",
                "targetIds": [kb_id],
                "undoable": True,
                # 只有 delete 是部分回退（create 的逆是软删，库里本来就没别的东西）
                "reason": REASON_DOCUMENTS_DESTROYED if action == "delete" else "",
            }
        if action == "delete_document":
            return {"undoable": False, "reason": REASON_CONTENT_DESTROYED}
        if action == "update":
            return {"undoable": False, "reason": REASON_NO_BEFORE_STATE}
        return None

    # ------------------------------------------------------------------ 预览

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片要说清「删的是哪个库/哪篇文档、里面有多少东西」

        一律**只读反查**（`get_knowledge_base` / `get_document` 自带归属校验），
        绝不回显模型传进来的名字 —— 否则卡片显示的和实际动的不是一回事。
        """
        action = str(params.get("action") or "")
        try:
            if action == "create":
                return self._preview_create(params)
            if action == "update":
                return await self._preview_update(params, ctx)
            if action == "delete":
                return await self._preview_delete(params, ctx)
            if action == "delete_document":
                return await self._preview_delete_document(params, ctx)
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}
        return {}

    @staticmethod
    def _preview_create(params: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        name = (params.get("name") or "").strip()
        if name:
            out["name"] = name
        description = (params.get("description") or "").strip()
        if description:
            out["description"] = description
        return out

    async def _preview_update(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        kb = await self._load_kb(ctx, params.get("kb_id"))
        if isinstance(kb, dict):  # 「没找到」的提示
            return kb
        out: Dict[str, Any] = {"kbId": kb.id, "name": kb.name}
        changed: List[str] = []
        for key, label in _WILL_CHANGE:
            if params.get(key) is None:
                continue
            if label not in changed:
                changed.append(label)
        if changed:
            out["willChange"] = "、".join(changed)
        if params.get("disabled") is not None:
            out["disabledText"] = _disabled_text(params.get("disabled"))
        return out

    async def _preview_delete(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        kb = await self._load_kb(ctx, params.get("kb_id"))
        if isinstance(kb, dict):
            return kb
        docs, chunks = await self._count_contents(ctx, kb.id)
        return {
            "kbId": kb.id,
            "name": kb.name,
            "documents": docs,
            "chunks": chunks,
        }

    async def _preview_delete_document(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        doc_id = _to_int(params.get("doc_id"))
        if doc_id is None:
            return {}
        doc = await self._load_doc(ctx, doc_id)
        if isinstance(doc, dict):
            return doc
        chunks = int(
            await ctx.db.scalar(
                select(func.count())
                .select_from(RagDocumentChunk)
                .where(RagDocumentChunk.doc_id == doc.id)
            )
            or 0
        )
        return {
            "docId": doc.id,
            "fileName": doc.file_name,
            "kbId": doc.kb_id,
            "chunks": chunks,
        }

    # ------------------------------------------------------------------ 只读辅助

    async def _load_kb(self, ctx: ToolContext, kb_id: Any):
        """按 id **只读反查**知识库（`get_knowledge_base` 自带归属校验）"""
        kid = _to_int(kb_id)
        if kid is None:
            return {"name": "（没有指定知识库 ID）"}
        try:
            return await rws.get_knowledge_base(ctx.db, ctx.user_id, kid)
        except RagNotFound:
            return {"name": f"（没有找到属于你的知识库：kbId={kid}）"}

    async def _load_doc(self, ctx: ToolContext, doc_id: int):
        try:
            return await rws.get_document(ctx.db, ctx.user_id, doc_id)
        except RagNotFound:
            return {"preview": f"（没有找到属于你的文档：docId={doc_id}）"}

    async def _count_contents(self, ctx: ToolContext, kb_id: int) -> tuple:
        docs = int(
            await ctx.db.scalar(
                select(func.count()).select_from(RagDocument).where(RagDocument.kb_id == kb_id)
            )
            or 0
        )
        chunks = int(
            await ctx.db.scalar(
                select(func.count())
                .select_from(RagDocumentChunk)
                .where(RagDocumentChunk.kb_id == kb_id)
            )
            or 0
        )
        return docs, chunks

    @staticmethod
    def _fail_from(e: Exception) -> Dict[str, Any]:
        """把 rag 服务的异常翻成给模型的 `fail()`（`hint` 必填）"""
        if isinstance(e, RagNotFound):
            return fail(str(e), "请先用 action=list 确认知识库/文档的 ID 是不是你的")
        if isinstance(e, RagConflict):
            return fail(str(e), "请换一个名称，或先用 action=list 看看已有的知识库")
        return fail(
            f"知识库操作失败：{type(e).__name__}: {e}",
            "请检查参数是否符合要求；如果是数据本身的问题，请改用 action=list 重新确认",
        )

    # ------------------------------------------------------------------ 执行

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        handler = {
            "list": self._list,
            "create": self._create,
            "update": self._update,
            "delete": self._delete,
            "list_documents": self._list_documents,
            "delete_document": self._delete_document,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / create / update / delete / list_documents / "
                "delete_document",
            )
        return await handler(params, ctx)

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        try:
            # 管理列表口径：**被屏蔽的库照样列出来**（否则用户就永远开不回来了）
            kbs = await rws.list_knowledge_bases(ctx.db, ctx.user_id)
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        items = [{**kb, "disabledText": _disabled_text(kb.get("disabled"))} for kb in kbs]
        blocked = sum(1 for kb in items if int(kb.get("disabled") or 0))
        if not items:
            message = "这个用户还没有知识库；资料需要他本人先上传，你可以引导他去知识库页面"
        else:
            message = f"共 {len(items)} 个知识库"
            if blocked:
                message += f"，其中 {blocked} 个已屏蔽（不参与检索）"
        return ok(
            **{
                "action": "list",
                "count": len(items),
                "knowledgeBases": items,
                "message": message,
            }
        )

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        name = (params.get("name") or "").strip()
        if not name:
            return fail("创建知识库需要名称", "请提供 name")

        from app.database import async_session_factory

        # ⚠️ 自己的一次性会话：rag_write_service 的写函数内部 commit（见模块 docstring）
        try:
            async with async_session_factory() as db:
                kb = await rws.create_knowledge_base(
                    db, ctx.user_id, name, params.get("description")
                )
                info = {
                    "kbId": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "docCount": kb.doc_count,
                    "chunkCount": kb.chunk_count,
                }
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)
        return ok(
            **{
                "action": "create",
                **info,
                "disabled": 0,
                "disabledText": _disabled_text(0),
                "message": (
                    f"知识库「{info['name']}」已创建（kbId={info['kbId']}），"
                    "接下来需要用户自己上传文档"
                ),
            }
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail("修改知识库需要 kb_id", "请先用 action=list 拿到 kbId")

        name = params.get("name")
        description = params.get("description")
        disabled = params.get("disabled")
        if name is None and description is None and disabled is None:
            return fail(
                "没有提供任何要修改的字段",
                "请至少给出 name / description / disabled 之一",
            )

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                kb = await rws.update_knowledge_base(
                    db,
                    ctx.user_id,
                    kb_id,
                    name=name,
                    description=description,
                    disabled=None if disabled is None else int(disabled),
                )
                flag = rws.kb_disabled_flag(kb)
                info = {"kbId": kb.id, "name": kb.name, "disabled": flag}
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        changed = [
            label for key, label in _WILL_CHANGE if params.get(key) is not None
        ]
        # 走到这里 `changed` 一定非空（上面已经拦掉「一个字段都没给」）
        note = "，现在**不参与检索**" if info["disabled"] else "，现在可以正常检索"
        return ok(
            **{
                "action": "update",
                **info,
                "disabledText": _disabled_text(info["disabled"]),
                "changed": changed,
                "message": f"知识库「{info['name']}」已更新（{'、'.join(changed)}）{note}",
            }
        )

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail("删除知识库需要 kb_id", "请先用 action=list 拿到 kbId")

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                info = await rws.delete_knowledge_base(db, ctx.user_id, kb_id)
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        return ok(
            **{
                "action": "delete",
                "deleted": 1,
                **info,
                "message": (
                    f"已删除知识库「{info['name']}」及其 "
                    f"{info['documents']} 篇文档、{info['chunks']} 个分块"
                ),
            }
        )

    async def _list_documents(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail("列出文档需要 kb_id", "请先用 action=list 拿到 kbId")

        try:
            docs: List[Dict[str, Any]] = await rws.list_documents(
                ctx.db, ctx.user_id, kb_id
            )
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        limit = _to_int(params.get("limit")) or DEFAULT_DOCS_PAGE
        limit = max(1, min(MAX_DOCS_PAGE, limit))
        offset = max(_to_int(params.get("offset")) or 0, 0)
        total = len(docs)
        page = docs[offset : offset + limit]

        if total == 0:
            message = (
                "这个知识库里还没有文档 —— 需要用户自己在知识库页面上传，"
                "你没法替他上传"
            )
        else:
            message = f"这个知识库里有 {total} 篇文档，本次返回 {len(page)} 篇"
        return ok(
            **{
                "action": "list_documents",
                "kbId": kb_id,
                "offset": offset,
                "count": len(page),
                "total": total,
                "hasMore": offset + len(page) < total,
                "documents": page,
                "message": message,
            }
        )

    async def _delete_document(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        doc_id = _to_int(params.get("doc_id"))
        if doc_id is None:
            return fail("删除文档需要 doc_id", "请先用 action=list_documents 拿到 docId")

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                info = await rws.delete_document(db, ctx.user_id, doc_id)
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        return ok(
            **{
                "action": "delete_document",
                "deleted": 1,
                **info,
                "message": (
                    f"已删除文档「{info['fileName']}」及其 {info['chunks']} 个分块"
                ),
            }
        )


__all__ = ["KnowledgeBaseManageTool", "MAX_DOCS_PAGE"]
