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

from app.models.rag import DOC_STATUS_TEXT, RagDocument, RagDocumentChunk, RagKnowledgeBase
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


def _as_list(value: Any) -> list:
    """把「可能是 None / 单值 / 列表」的参数统一成 list（批量动作用）"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


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
        "delete=delete ONE knowledge base AND all of its documents and text chunks (pass "
        "`kb_id`; irreversible), "
        "delete_many=delete SEVERAL knowledge bases at once (pass `kb_ids`). "
        "ALWAYS use this instead of calling delete repeatedly: the user gets ONE "
        "confirmation card where they can untick items they want to keep, "
        "list_documents=list documents (pass `kb_id` to narrow; omit it to search all user "
        "libraries, optional `query` matches file names; paged via `limit`/`offset`), "
        "get_document=read ONE document's full raw content by `doc_id`, or resolve it by "
        "`doc_name` (partial name allowed; if several match, an ambiguous result with "
        "candidate doc IDs/names is returned and you must ask the user which one), "
        "list_document_versions=list a document's saved versions (pass `doc_id`; latest first), "
        "delete_document=delete one document and its chunks (pass `doc_id`; irreversible). "
        "IMPORTANT: `disabled=1` means the knowledge base is EXCLUDED from retrieval — "
        "`knowledge_search` and your own context will not see its contents. Use "
        "`disabled=0` to let the user search it again. "
        "NOTE: you cannot UPLOAD documents or create one from text with this tool — the "
        "user uploads files themselves on the knowledge base page; point them there. "
        "To read the contents, use `knowledge_search` instead."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "资料管理"
    description_zh = (
        "管理我的资料（我上传的文档集合）：list=列资料夹（含文档数、是否已被屏蔽）、"
        "create=新建空资料夹、update=改名 / 改描述 / 启用或屏蔽、delete=删除资料夹、"
        "list_documents=列文档（可按资料夹或文件名搜索）、get_document=按 ID 或名称读取"
        "一篇文档完整正文（重名时返回候选让人选）、list_document_versions=列文档历史版本、"
        "delete_document=删文档。"
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
                    "delete_many",
                    "list_documents",
                    "get_document",
                    "list_document_versions",
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
            "kb_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Knowledge base IDs to delete in bulk (used by delete_many). Take them "
                    "from action=list. Prefer this over calling delete in a loop."
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
                    "Document ID (used by get_document / list_document_versions / "
                    "delete_document). Optional when get_document is resolving by doc_name."
                ),
            },
            "doc_name": {
                "type": "string",
                "description": (
                    "Document display name for get_document when the user did not provide an "
                    "ID. Partial names are supported; duplicates return candidates."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Optional file-name filter for list_documents. Case-insensitive partial "
                    "match; exact matches are listed first."
                ),
            },
            "limit": {
                "type": "integer",
                "description": (
                    f"Max results per page (used by list_documents / "
                    f"list_document_versions; default {DEFAULT_DOCS_PAGE}, "
                    f"max {MAX_DOCS_PAGE})."
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

    _WRITE_ACTIONS = {"create", "update", "delete", "delete_many", "delete_document"}
    _DESTRUCTIVE_ACTIONS = {"delete", "delete_many", "delete_document"}

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in self._DESTRUCTIVE_ACTIONS

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """`create` 一次只建一个知识库（规模固定），不额外强制确认"""
        return False

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
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
        # ⚠️ `delete_many` 2026-10-20 补上（原来落到 not_declared）：
        #    它逐个调 `rws.delete_knowledge_base`，而知识库是**逻辑删**（`del_flag`），
        #    所以整批都能 restore —— 没有理由只让单个 delete 能撤、批量 delete 不能。
        #    回执里有 `deleted: [{id, name, documents}]`，id 列表从这里取。
        #    与下面 `delete` 一样带 `documents_destroyed`：库能回来，文档与分块回不来。
        if action == "delete_many":
            ids: List[int] = []
            # ⚠️ `result.get("deleted")` 正常是 `[{id,name,documents}, ...]`，但这里必须
            #    **防御式**解析：`delete_many` 的失败分支会回 `fail(..., deleted=n)` 之类
            #    的标量。写成 `for item in result.get("deleted") or []` 时，一旦那个值是
            #    整数就抛 `TypeError: 'int' object is not iterable` —— 而 `undo_plan`
            #    抛异常会被 `record_op` 吞成「没声明」，用户只看到「还没实现」，
            #    真正的 TypeError 永远查不到。由 `_probe_undo_matrix` 抓到。
            raw_deleted = result.get("deleted")
            if isinstance(raw_deleted, list):
                for item in raw_deleted:
                    kid = _to_int((item or {}).get("id")) if isinstance(item, dict) else None
                    if kid is not None:
                        ids.append(kid)
            if not ids:
                # 回执里没有可用的 id 列表 → 退回到 `params.kb_ids`（批量删除的原始名单）。
                # 这条退路是安全的：`delete_many` 的入参就是它要删的那些 id，
                # 而恢复动作只动**自己的**知识库（`_Target.user_col` 兜着）。
                for value in _as_list(params.get("kb_ids")):
                    kid = _to_int(value)
                    if kid is not None:
                        ids.append(kid)
            ids = list(dict.fromkeys(ids))
            if not ids:
                return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
            return {
                "op": OP_RESTORE,
                "targetTable": "rag_knowledge_base",
                "targetIds": ids,
                "undoable": True,
                "reason": REASON_DOCUMENTS_DESTROYED,
            }
        if action == "delete_document":
            return {"undoable": False, "reason": REASON_CONTENT_DESTROYED}
        if action == "update":
            return {
                "undoable": False,
                "reason": "资料夹的名称 / 描述修改不会自动撤销"
                "（改前值写在资料服务自己的会话里，工具层拿不到；再改一次即可）",
            }
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
            if action == "delete_many":
                return await self._preview_delete_many(params, ctx)
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

    async def _preview_delete_many(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """批量删库的确认卡：**一份可勾选的清单**（用户 2026-10-17 需求）

        为什么要 `draft`：以前模型为了删 12 个库，会**循环调用 12 次 `delete`**，
        于是弹出 12 张确认卡片 —— 用户得点 12 次，且中途点错一张就只删了一半。
        改成一次 `delete_many` + 一张卡片，卡里逐条列出每个库（带文档数/分块数），
        用户勾选要删的、取消不要的，点一次「确认删除」由系统批量执行。

        `draft.kind = "batch_delete"` 是前端 `AgentDraftCard` 的渲染契约；
        `items[].key` 是勾选项的稳定标识（`kb:<id>`），回传时原样带回。
        """
        ids: List[int] = []
        for value in _as_list(params.get("kb_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        ids = list(dict.fromkeys(ids))
        if not ids:
            return {}

        rows = (
            await ctx.db.execute(
                select(
                    RagKnowledgeBase.id,
                    RagKnowledgeBase.name,
                    RagKnowledgeBase.doc_count,
                    RagKnowledgeBase.chunk_count,
                ).where(
                    RagKnowledgeBase.id.in_(ids),
                    RagKnowledgeBase.user_id == ctx.user_id,
                    RagKnowledgeBase.del_flag == "0",
                )
            )
        ).all()

        items: List[Dict[str, Any]] = []
        for r in rows:
            docs = int(r[2] or 0)
            chunks = int(r[3] or 0)
            items.append(
                {
                    "key": f"kb:{r[0]}",
                    "id": int(r[0]),
                    "title": str(r[1] or ""),
                    "subtitle": f"{docs} 篇文档 · {chunks} 个分块",
                }
            )
        # 保持用户/模型给的顺序，方便对照
        order = {int(i): n for n, i in enumerate(ids)}
        items.sort(key=lambda it: order.get(it["id"], 9999))

        missing = [i for i in ids if all(it["id"] != i for it in items)]
        out: Dict[str, Any] = {
            "count": len(items),
            "draft": {
                "kind": "batch_delete",
                "entity": "knowledge_base",
                "entityLabel": "资料夹",
                "items": items,
            },
        }
        if missing:
            out["missingIds"] = missing
        return out

    async def _delete_many(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """一次删除多个知识库（**用户勾选后的最终名单**已由 loop 覆盖进 `kb_ids`）

        逐个删（每个库要级联清文档 + 分块），任一失败不影响其余 —— 最后如实汇总
        「删了哪些 / 哪些没删成」，并把这份结果回灌给模型（它要知道有没有删干净）。
        """
        ids: List[int] = []
        for value in _as_list(params.get("kb_ids")):
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        ids = list(dict.fromkeys(ids))
        if not ids:
            return fail(
                "delete_many 缺少 kb_ids",
                "请传要删除的资料夹 ID 列表（kb_ids），或用 action=list 先查 ID",
            )

        from app.database import async_session_factory

        deleted: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []
        for kid in ids:
            try:
                async with async_session_factory() as db:
                    info = await rws.delete_knowledge_base(db, ctx.user_id, kid)
                deleted.append(
                    {
                        "id": kid,
                        "name": info.get("name"),
                        "documents": info.get("documents", 0),
                        "chunks": info.get("chunks", 0),
                    }
                )
            except Exception as e:  # noqa: BLE001 - 单个失败不牵连整批
                failed.append({"id": kid, "error": str(e)})

        parts = [f"已删除 {len(deleted)} 个资料夹"]
        if deleted:
            parts.append("、".join(f"「{d['name']}」" for d in deleted))
        if failed:
            parts.append(f"{len(failed)} 个失败：" + "、".join(str(f["id"]) for f in failed))

        return ok(
            action="delete_many",
            deleted=deleted,
            failed=failed,
            missingIds=[f["id"] for f in failed],
            message="；".join(parts),
        )

    # ------------------------------------------------------------------ 只读辅助

    async def _load_kb(self, ctx: ToolContext, kb_id: Any):
        """按 id **只读反查**知识库（`get_knowledge_base` 自带归属校验）"""
        kid = _to_int(kb_id)
        if kid is None:
            return {"name": "（没有指定资料夹 ID）"}
        try:
            return await rws.get_knowledge_base(ctx.db, ctx.user_id, kid)
        except RagNotFound:
            return {"name": f"（没有找到属于你的资料夹：kbId={kid}）"}

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
            return fail(str(e), "请先用 action=list 确认资料夹/文档的 ID 是不是你的")
        if isinstance(e, RagConflict):
            return fail(str(e), "请换一个名称，或先用 action=list 看看已有的资料夹")
        return fail(
            f"资料操作失败：{type(e).__name__}: {e}",
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
            "delete_many": self._delete_many,
            "list_documents": self._list_documents,
            "get_document": self._get_document,
            "list_document_versions": self._list_document_versions,
            "delete_document": self._delete_document,
        }.get(action)
        if handler is None:
            return fail(
                f"未知操作: {action}",
                "action 只能是 list / create / update / delete / list_documents / "
                "get_document / list_document_versions / delete_document",
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
            message = "这个用户还没有资料；资料需要他本人先上传，你可以引导他去「我的资料」页面"
        else:
            message = f"共 {len(items)} 个资料夹"
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
            return fail("创建资料夹需要名称", "请提供 name")

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
                    f"资料夹「{info['name']}」已创建（kbId={info['kbId']}），"
                    "接下来需要用户自己上传文档"
                ),
            }
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail("修改资料夹需要 kb_id", "请先用 action=list 拿到 kbId")

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
                "message": f"资料夹「{info['name']}」已更新（{'、'.join(changed)}）{note}",
            }
        )

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail("删除资料夹需要 kb_id", "请先用 action=list 拿到 kbId")

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
                    f"已删除资料夹「{info['name']}」及其 "
                    f"{info['documents']} 篇文档、{info['chunks']} 个分块"
                ),
            }
        )

    async def _list_documents(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        kb_id = _to_int(params.get("kb_id"))
        query = str(params.get("query") or "").strip().lower()

        try:
            if kb_id is not None:
                docs: List[Dict[str, Any]] = await rws.list_documents(
                    ctx.db, ctx.user_id, kb_id
                )
            else:
                # 用户经常只记得文档名、不记得在哪个资料夹；默认跨该用户的全部资料夹搜。
                kb_briefs = await rws.list_knowledge_bases(ctx.db, ctx.user_id)
                docs = []
                for kb in kb_briefs:
                    for doc in await rws.list_documents(ctx.db, ctx.user_id, int(kb["kbId"])):
                        doc["kbName"] = kb["name"]
                        docs.append(doc)
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        if query:
            # 精确同名优先，其次是前缀匹配，最后是包含匹配；重名时保留所有候选。
            docs = [
                doc
                for doc in docs
                if query in str(doc.get("fileName") or "").lower()
            ]
            docs.sort(
                key=lambda doc: (
                    0 if str(doc.get("fileName") or "").lower() == query else
                    1 if str(doc.get("fileName") or "").lower().startswith(query) else 2,
                    -int(doc.get("docId") or 0),
                )
            )

        limit = _to_int(params.get("limit")) or DEFAULT_DOCS_PAGE
        limit = max(1, min(MAX_DOCS_PAGE, limit))
        offset = max(_to_int(params.get("offset")) or 0, 0)
        total = len(docs)
        page = docs[offset : offset + limit]

        if total == 0:
            message = (
                f"没有找到名称包含「{query}」的文档" if query else "没有找到任何文档"
            )
        else:
            message = f"共找到 {total} 篇文档，本次返回 {len(page)} 篇"
        return ok(
            **{
                "action": "list_documents",
                "kbId": kb_id,
                "query": query or None,
                "offset": offset,
                "count": len(page),
                "total": total,
                "hasMore": offset + len(page) < total,
                "documents": page,
                "message": message,
            }
        )

    async def _find_document_candidates(
        self, ctx: ToolContext, name: str, kb_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        safe_name = str(name or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = (
            select(RagDocument, RagKnowledgeBase.name.label("kb_name"))
            .join(RagKnowledgeBase, RagKnowledgeBase.id == RagDocument.kb_id)
            .where(
                RagDocument.user_id == ctx.user_id,
                RagKnowledgeBase.user_id == ctx.user_id,
                RagKnowledgeBase.del_flag == "0",
                RagDocument.file_name.ilike(f"%{safe_name}%", escape="\\"),
            )
        )
        if kb_id is not None:
            stmt = stmt.where(RagDocument.kb_id == kb_id)
        stmt = stmt.order_by(RagDocument.file_name, RagDocument.id.desc())
        rows = (await ctx.db.execute(stmt)).all()
        return [
            {
                "docId": row[0].id,
                "kbId": row[0].kb_id,
                "kbName": row[1],
                "fileName": row[0].file_name,
                "status": row[0].status,
                "statusText": DOC_STATUS_TEXT.get(row[0].status, "未知"),
            }
            for row in rows
        ]

    async def _get_document(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """读取一篇文档的完整正文；支持按 ID 或按名称解析。"""
        doc_id = _to_int(params.get("doc_id"))
        doc_name = str(params.get("doc_name") or "").strip()
        if doc_id is None and not doc_name:
            return fail(
                "读取文档需要 doc_id 或 doc_name",
                "请让用户提供文档名，或先用 action=list_documents 搜索候选",
            )

        try:
            if doc_id is None:
                candidates = await self._find_document_candidates(
                    ctx, doc_name, _to_int(params.get("kb_id"))
                )
                if not candidates:
                    return fail(
                        f"没有找到名称包含「{doc_name}」的文档",
                        "请让用户确认文档名，或先用 action=list_documents 查看可用文档",
                    )
                if len(candidates) > 1:
                    return ok(
                        **{
                            "action": "get_document",
                            "ambiguous": True,
                            "query": doc_name,
                            "count": len(candidates),
                            "candidates": candidates,
                            "message": (
                                f"找到 {len(candidates)} 篇名称匹配的文档，请让用户根据文件名和"
                                "资料夹选择具体一篇，再传 doc_id。"
                            ),
                        }
                    )
                doc_id = int(candidates[0]["docId"])
            doc = await rws.get_document(ctx.db, ctx.user_id, doc_id)
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        return ok(
            **{
                "action": "get_document",
                "docId": doc.id,
                "kbId": doc.kb_id,
                "fileName": doc.file_name,
                "content": doc.raw_content or "",
                "contentLength": len(doc.raw_content or ""),
                "status": doc.status,
                "statusText": DOC_STATUS_TEXT.get(doc.status, "未知"),
                "message": f"已读取文档「{doc.file_name}」的完整正文（{len(doc.raw_content or '')} 字）",
            }
        )

    async def _list_document_versions(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        doc_id = _to_int(params.get("doc_id"))
        if doc_id is None:
            return fail("查看历史版本需要 doc_id", "请先用 action=list_documents 拿到 docId")
        try:
            versions = await rws.list_document_versions(
                ctx.db,
                ctx.user_id,
                doc_id,
                limit=_to_int(params.get("limit")) or 30,
            )
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)
        return ok(
            **{
                "action": "list_document_versions",
                "docId": doc_id,
                "count": len(versions),
                "versions": versions,
                "message": f"这篇文档共有 {len(versions)} 个历史版本",
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
