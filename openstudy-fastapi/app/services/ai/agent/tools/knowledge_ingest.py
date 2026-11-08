"""
`knowledge_ingest` —— 把「内容」写进知识库的 Agent 工具

与 `knowledge_base_manage`（**管理**知识库/文档：建库、改名、删库、删文档）分工：
本工具负责**内容入库**，即把一段文本（模型的总结 / 笔记 / 生成内容）或用户
**本轮上传的附件正文**变成知识库里一篇会走「解析 → 分块 → 向量化」的文档；
`update_document` 则在原文档上替换正文，不删除、不新建，并自动重建 chunks。

放行说明（回应当初的封禁注释）
=============================
`knowledge_base_manage` 的模块 docstring 写着「刻意不做从纯文本建文档：会花钱调
embedding，谁要加先拿放行」。本工具就是那次**放行**的落地 —— 既然是付费操作，
就用三重闸门把成本摁住：

  1. `needs_confirmation=True`：每个 action 都要用户点确认，确认卡片明确告诉用户
     「将向【某库】写入约 N 块、约需 M 次向量化调用」（`preview()` 只切块计数，
     **绝不落库、绝不调 embedding**）；
  2. 单文档块数上限沿用 `chunker.MAX_CHUNKS=100`，单库文档数上限由
     `rag_write_service.MAX_DOCS_PER_KB=200` 兜底；
  3. 工具层再拒空正文 / 明显超长正文。

等待体验 vs 解析时长（方案 B：解析提前、向量化后台）
==================================================
`process_document` 里 `embed_texts` 是**同步 await**（每批最多 16 块调一次 embedding
接口），一篇几百块的长文会里外等好几十秒。若在工具里直接 `await process_document()`，
整个 Agent 流式响应会被卡住（用户盯着光标干等）—— 这正是要避免的。

所以采用**方案 B**：

  工具内：独立会话 → `create_document(status=DOC_PENDING)` 落库（正文已持久化）
          → `asyncio.create_task(document_pipeline.process_document(doc_id))` 丢后台
          → **立即返回** `ok(docId, status="处理中", ...)`

用户马上看到「已写入、正在向量化」，模型也能如实回复进度；真正的耗时（embedding）
被推到后台任务里跑。后台任务自带会话、与本次请求会话无关，所以流响应结束也不会
被关掉。

⚠️ 为什么自己开会话（不借 `ctx.db`）
----------------------------------
与 `knowledge_base_manage` 同一原因：`rag_write_service` 的写函数**内部会 `commit()`**，
而 `loop._execute_tool` 会把写工具包进 SAVEPOINT —— 两者相遇会抛
`Can't operate on closed transaction inside context manager`。本工具只把 `ctx.db` 用于
**只读校验**（`get_knowledge_base` / `get_document`），写入一律走独立会话。

⚠️ `process_document` 是**唯一**分块入口
---------------------------------------
本工具**不在工具里自己做 `chunk_text` + `replace_chunks`** —— 那会让分块逻辑出现第二份
实现，早晚与流水线漂移。落库后一律交给 `process_document`（它基于已落库的
`raw_content`，幂等、可重跑）。

回退语义
========
`from_text` / `from_attachment` 新建的文档，逆操作 = **物理删该文档**（`delete_document`：
先删分块再删文档、重算计数）。这是**本次新建**的东西，删掉不影响用户原有数据，
所以 `undoable=True`；但分块重建要重算 embedding、要花钱，故 reason 用
`REASON_CONTENT_DESTROYED` 提示「删了要重建会花钱」，卡片据此措辞。
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any, Dict, List, Optional

from loguru import logger

from app.models.rag import DOC_PENDING, RagDocument
from app.services.ai.agent.base import (
    OP_DELETE_RECORD,
    REASON_CONTENT_DESTROYED,
    REASON_MISSING_TARGET_ID,
    AgentTool,
    ToolContext,
    fail,
    ok,
)
from app.services.rag import rag_write_service as rws
from app.services.rag.chunker import MAX_CHUNKS, chunk_text
from app.services.rag.rag_write_service import RagConflict, RagNotFound

#: 单篇文档正文最大字符数（与 chunker.MAX_CONTENT_LENGTH 同口径；工具层先拦，
#: 避免把明显超长的内容送进流水线再被静默截断）
MAX_RAW_LENGTH = 50_000

#: `embed_texts` 每批最多多少块（用于 preview 估算「约需几次向量化调用」）。
#: ⚠️ 这个数字只是**给用户看的估算**，真实分批在 `embedding.py` 里；调大调小只影响
#: 卡片文案，不影响行为。取值参考 embedding 服务的批大小。
_EMBED_BATCH = 16


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_chunks(text: str) -> int:
    """只切块、**不落库不调 embedding**，估算这篇正文会有几块。

    `chunk_text` 是纯函数（jieba 分词只在落库时做），用它估算不会产生任何副作用。
    """
    if not text:
        return 0
    try:
        return len(chunk_text(text))
    except Exception:  # noqa: BLE001 - 估算失败不能影响主流程
        return 0


_DIFF_CONTEXT_LINES = 3
_DIFF_MAX_LINES = 240


def _build_text_diff(old_text: str, new_text: str, path: str) -> dict:
    """生成确认卡用的行级 diff（与 DSH 的 data-diff 展示同口径）。

    · 3 行上下文 + 相邻修改合并成 hunk；
    · 每个 hunk 之间放 `gap` 行，前端折叠时只展示头尾；
    · 最多 240 行，避免长文档把确认卡撑爆。
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    rows: list[dict[str, Any]] = []
    added = 0
    removed = 0

    for group_index, group in enumerate(matcher.get_grouped_opcodes(_DIFF_CONTEXT_LINES)):
        if group_index:
            rows.append({"kind": "gap", "text": "⋯", "oldLine": None, "newLine": None})
        for tag, old_start, old_end, new_start, new_end in group:
            if tag == "equal":
                for offset, value in enumerate(old_lines[old_start:old_end]):
                    rows.append({
                        "kind": "context",
                        "text": value,
                        "oldLine": old_start + offset + 1,
                        "newLine": new_start + offset + 1,
                    })
                continue
            if tag in ("replace", "delete"):
                for offset, value in enumerate(old_lines[old_start:old_end]):
                    rows.append({
                        "kind": "del",
                        "text": value,
                        "oldLine": old_start + offset + 1,
                        "newLine": None,
                    })
                    removed += 1
            if tag in ("replace", "insert"):
                for offset, value in enumerate(new_lines[new_start:new_end]):
                    rows.append({
                        "kind": "add",
                        "text": value,
                        "oldLine": None,
                        "newLine": new_start + offset + 1,
                    })
                    added += 1

    truncated = len(rows) > _DIFF_MAX_LINES
    if truncated:
        rows = rows[:_DIFF_MAX_LINES]
    return {
        "path": path,
        "added": added,
        "removed": removed,
        "changed": bool(added or removed),
        "truncated": truncated,
        "lines": rows,
    }


def _apply_document_edits(base_text: str, edits: Any) -> Any:
    """把模型给出的精确文本补丁应用到当前正文；返回 str 或 fail() 信封。"""
    if not isinstance(edits, list) or not edits:
        return fail("update_document 没有提供 edits", "请提供至少一条 old_text/new_text 替换")
    current = base_text or ""
    for index, raw_edit in enumerate(edits, start=1):
        if not isinstance(raw_edit, dict):
            return fail(f"第 {index} 条 edit 不是对象", "每条 edit 需要 old_text 和 new_text")
        old_text = str(raw_edit.get("old_text") or "")
        new_text = str(raw_edit.get("new_text") or "")
        if not old_text:
            return fail(f"第 {index} 条 edit 的 old_text 为空", "请提供要替换的原文片段")
        occurrences = current.count(old_text)
        if occurrences == 0:
            return fail(
                f"第 {index} 条 edit 在当前文档中找不到 old_text",
                "请先用 knowledge_base_manage action=get_document 读取完整正文，"
                "并复制其中一段原文作为 old_text（必须逐字匹配）",
            )
        replace_all = bool(raw_edit.get("replace_all"))
        if occurrences > 1 and not replace_all:
            return fail(
                f"第 {index} 条 edit 的 old_text 出现了 {occurrences} 次，无法确定替换哪一处",
                "请把 old_text 扩展到前后文使其唯一，或显式传 replace_all=true",
            )
        current = current.replace(old_text, new_text, -1 if replace_all else 1)
    return current


class KnowledgeIngestTool(AgentTool):
    name = "knowledge_ingest"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Write content INTO one of the user's knowledge bases, so it becomes a "
        "searchable document (it will be parsed, chunked and vectorized). "
        "action values: "
        "from_text=store a piece of text you provide via `text` (e.g. a summary, note "
        "or explanation you just generated) as a document in the knowledge base "
        "(requires `kb_id` and `text`, optional `file_name`), "
        "from_attachment=store the plain text of a file the USER attached in THIS "
        "message as a document (requires `kb_id`; optional `index` to pick which "
        "attachment when several were sent, 0-based), "
        "from_url=fetch one public web page and store it as a document in the knowledge "
        "base (requires `kb_id` and `url`; optional `file_name`), "
        "update_document=replace/update an EXISTING document in place (requires `doc_id` "
        "and either `text` or `edits`; optional `file_name` to rename). Use this for "
        "edits instead of deleting and recreating a document. "
        "restore_document_version=restore one saved version of an existing document "
        "(requires `doc_id` and `version_id`). "
        "IMPORTANT: this WRITES into the user's knowledge base and costs embedding "
        "calls, so the user must confirm first and you should use it only when the "
        "user clearly wants to save the content. Vectorization runs in the background "
        "and takes a moment — the document is not searchable immediately; tell the "
        "user it is being processed. The knowledge base is created by "
        "`knowledge_base_manage`; run action=list there first if you do not know the "
        "`kb_id`."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "存入我的资料"
    description_zh = (
        "把内容存入我的资料并生成可检索文档：from_text=把一段文本（总结/笔记/生成内容）"
        "存入、from_attachment=把用户本轮上传的附件正文存入、from_url=抓取一个公开网页"
        "并存入、update_document=修改已有文档正文（支持精确补丁，不删除重建）、"
        "restore_document_version=恢复历史版本。"
        "会消耗 embedding 额度，需用户确认；向量化在后台进行，文档稍后才可检索。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": [
                    "from_text",
                    "from_attachment",
                    "from_url",
                    "update_document",
                    "restore_document_version",
                ],
            },
            "kb_id": {
                "type": "integer",
                "description": (
                    "Target knowledge base ID (required for from_text/from_attachment; "
                    "for update_document it is derived from doc_id). Take it from "
                    "`knowledge_base_manage` action=list."
                ),
            },
            "doc_id": {
                "type": "integer",
                "description": (
                    "Existing document ID to update (required for action=update_document). "
                    "Take it from `knowledge_base_manage` action=list_documents or a "
                    "knowledge_search result."
                ),
            },
            "version_id": {
                "type": "integer",
                "description": (
                    "Saved version ID to restore (required for action=restore_document_version; "
                    "get it from knowledge_base_manage action=list_document_versions)."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "The full text to store (required for from_text) or the full replacement "
                    "content (update_document alternative to `edits`). Strip it to the "
                    "essential content; very long text is rejected."
                ),
            },
            "edits": {
                "type": "array",
                "description": (
                    "Preferred for update_document: apply one or more exact text replacements "
                    "instead of rewriting the whole document. Each old_text must match the "
                    "current document exactly once unless replace_all=true."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {
                            "type": "string",
                            "description": "Exact existing text to find in the document.",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text; empty string deletes old_text.",
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "Allow replacing every occurrence (default false).",
                        },
                    },
                    "required": ["old_text", "new_text"],
                },
            },
            "file_name": {
                "type": "string",
                "description": (
                    "Optional display name for the new document (from_text) or the new "
                    "name when update_document renames it."
                ),
            },
            "index": {
                "type": "integer",
                "description": (
                    "Which attachment to use for action=from_attachment (0-based, default "
                    "0) when the user attached more than one file."
                ),
            },
            "url": {
                "type": "string",
                "description": (
                    "Public http(s) URL of the web page to import (required for "
                    "action=from_url). Use `web_search` first if you need to find it."
                ),
            },
        },
        "required": ["action"],
    }
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        # 写操作判定改为「按规模」：小内容不再强制弹卡（详见 confirm_policy）。
        # ⚠️ 工具清单的探测调用只传 `action`、没有正文 → confirm_policy 保守回 True，
        #    所以本工具仍会出现在 `GET /ai/agent/tools` 的 write 清单里。
        return self.confirm_policy(params)

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """按**数据规模**决定是否强制确认：长文（≥3000 字 或 ≥8 块）才弹卡

        `from_text` 的正文就在参数里，能量出规模；`from_attachment` 的正文在
        `ctx.extra`（本钩子拿不到 ctx），量不到 → 保守保留确认。
        探测调用（只传 `action`、`text is None`）同样保守返回 True。
        ⚠️ 跑在流式热路径：防御式解析，解析失败一律 False。
        """
        try:
            action = str(params.get("action") or "")
            if action == "from_text":
                raw = params.get("text")
                if raw is None:
                    return True
                text = str(raw)
                return len(text) >= 3000 or _estimate_chunks(text) >= 8
            if action in ("from_attachment", "from_url"):
                return True
            if action in ("update_document", "restore_document_version"):
                return True
            return False
        except Exception:  # noqa: BLE001
            return False

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        # 这里只表示“删除类”语义；修改/恢复正文都会先保存当前版本，
        # 仍通过 confirm_policy 强制确认，但不能让确认卡误显示成“删除操作”。
        return False

    def undo_plan(
        self,
        params: Dict[str, Any],
        result: Dict[str, Any],
        before: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        """新建文档的逆 = 物理删该文档。

        文档是**本次新建**的，删掉不影响用户原有数据，故 `undoable=True`；
        但分块重建要重算 embedding（花钱），reason 用 `content_destroyed` 提示部分语义。
        走 `OP_DELETE_RECORD`（物理删一行，与 `rag` 的删除语义一致）。
        """
        if str(params.get("action") or "") in ("update_document", "restore_document_version"):
            # 正文修改/版本恢复会在 rag_write_service 里生成历史版本，但本工具的
            # 通用回退还没有 rag_document 的字段恢复执行器；不要错误地声明“删文档”回退。
            return None
        doc_id = _to_int(result.get("docId"))
        if doc_id is None:
            return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
        return {
            "op": OP_DELETE_RECORD,
            "targetTable": "rag_document",
            "targetIds": [doc_id],
            "undoable": True,
            "reason": REASON_CONTENT_DESTROYED,
        }

    # ------------------------------------------------------------------ 预览

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片要说清「写进哪个库、大约多少块、花几次 embedding」

        ⚠️ 只做**只读反查**（库名走 `get_knowledge_base` 自带归属校验）+ 纯函数切块估算，
        **绝不落库、绝不调 embedding**。卡片上的库名取自数据库而非模型传参 —— 否则
        显示的和实际写的可能不是一回事。
        """
        try:
            action = str(params.get("action") or "")
            out: Dict[str, Any] = {}
            before_text = ""
            restore_version: Optional[dict] = None

            # 1) 反查目标（update/restore 用 doc_id，其他 action 用 kb_id）
            if action == "restore_document_version":
                doc_id = _to_int(params.get("doc_id"))
                version_id = _to_int(params.get("version_id"))
                if doc_id is None or version_id is None:
                    return {"hint": "（恢复历史版本需要 doc_id 和 version_id）"}
                try:
                    doc = await rws.get_document(ctx.db, ctx.user_id, doc_id)
                    restore_version = await rws.get_document_version(
                        ctx.db, ctx.user_id, doc_id, version_id
                    )
                except RagNotFound:
                    return {"hint": f"（没有找到属于你的文档或版本：docId={doc_id}）"}
                out["docId"] = doc.id
                out["versionId"] = version_id
                out["fileName"] = restore_version.get("fileName") or doc.file_name
                before_text = doc.raw_content or ""
                try:
                    kb = await rws.get_knowledge_base(ctx.db, ctx.user_id, doc.kb_id)
                    out["kbId"] = kb.id
                    out["kbName"] = kb.name
                except RagNotFound:
                    out["kbId"] = doc.kb_id
            elif action == "update_document":
                doc_id = _to_int(params.get("doc_id"))
                if doc_id is None:
                    return {"hint": "（没有指定文档 ID）"}
                try:
                    doc = await rws.get_document(ctx.db, ctx.user_id, doc_id)
                except RagNotFound:
                    return {"hint": f"（没有找到属于你的文档：docId={doc_id}）"}
                out["docId"] = doc.id
                out["fileName"] = doc.file_name
                before_text = doc.raw_content or ""
                try:
                    kb = await rws.get_knowledge_base(ctx.db, ctx.user_id, doc.kb_id)
                    out["kbId"] = kb.id
                    out["kbName"] = kb.name
                except RagNotFound:
                    out["kbId"] = doc.kb_id
            else:
                kid = _to_int(params.get("kb_id"))
                if kid is None:
                    return {"hint": "（没有指定资料夹 ID）"}
                try:
                    kb = await rws.get_knowledge_base(ctx.db, ctx.user_id, kid)
                    out["kbId"] = kb.id
                    out["kbName"] = kb.name
                except RagNotFound:
                    return {"hint": f"（没有找到属于你的资料夹：kbId={kid}）"}

            # from_url 的正文在网页上，预览阶段不为了估算再抓一次网络（也避免费用）；
            # 确认卡只显示目标库和来源 URL，真实块数由执行后回执给出。
            if action == "from_url":
                url = str(params.get("url") or "").strip()
                out["action"] = action
                out["source"] = url or "（未提供网址）"
                out["chunks"] = 0
                out["embedCalls"] = 0
                out["charCount"] = 0
                return out

            # 2) 取正文（只读）+ 估算块数；update_document 的补丁要基于当前正文应用
            if action == "restore_document_version":
                text = str((restore_version or {}).get("content") or "")
            else:
                text = await self._resolve_text(params, ctx, base_text=before_text)
            if isinstance(text, dict):  # 正文取用失败（envelope），直接透出提示
                out.update(text)
                return out

            chunks = _estimate_chunks(text)
            out["action"] = action
            out["chunks"] = chunks
            out["embedCalls"] = (chunks + _EMBED_BATCH - 1) // _EMBED_BATCH if chunks else 0
            out["charCount"] = len(text)
            if action in ("update_document", "restore_document_version"):
                out["beforeCharCount"] = len(before_text)
                out["diff"] = _build_text_diff(before_text, text, str(out.get("fileName") or ""))
            if action == "from_attachment":
                out["source"] = (params.get("file_name") or "").strip() or "本轮上传的附件"
            return out
        except Exception:  # noqa: BLE001 - 预览失败不能影响主流程
            return {}

    # ------------------------------------------------------------------ 执行

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        if action == "update_document":
            return await self._execute_update(params, ctx)
        if action == "restore_document_version":
            return await self._execute_restore_version(params, ctx)
        if action == "from_url":
            return await self._execute_from_url(params, ctx)
        if action not in ("from_text", "from_attachment"):
            return fail(
                f"未知操作: {action}",
                "action 只能是 from_text / from_attachment / from_url / "
                "update_document / restore_document_version",
            )

        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail(
                "存入我的资料需要 kb_id",
                "请先用 knowledge_base_manage 的 action=list 拿到 kbId",
            )

        # 取正文（from_text 用参数 / from_attachment 用本轮附件）
        text = await self._resolve_text(params, ctx)
        if isinstance(text, dict):
            return text  # 已是 fail() 信封
        if not text.strip():
            return fail(
                "没有可写入的正文内容",
                "请提供非空的 text；若是 from_attachment，请确认本轮确实上传了可解析的文档",
            )
        if len(text) > MAX_RAW_LENGTH:
            return fail(
                f"正文过长（{len(text)} 字，上限 {MAX_RAW_LENGTH} 字）",
                "请精简内容后再写入，或拆成多篇文档分次写入",
            )

        file_name = self._resolve_file_name(params, action)

        from app.database import async_session_factory

        # ⚠️ 独立会话：rag_write_service 的写函数内部 commit（见模块 docstring）
        try:
            async with async_session_factory() as db:
                doc = await rws.create_document(
                    db,
                    ctx.user_id,
                    kb_id,
                    file_name=file_name,
                    raw_content=text,
                    file_type="text",
                    status=DOC_PENDING,
                )
                doc_id = doc.id
                kb_name = None
                # 反查库名只为回执文案（同会话只读，无副作用）
                try:
                    kb_name = (await rws.get_knowledge_base(db, ctx.user_id, kb_id)).name
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        # ---- 方案 B：向量化丢后台，立即返回 ----
        # process_document 自带会话、幂等、可重跑；不借 ctx.db（请求会话会被关）
        self._schedule_processing(doc_id)

        chunk_hint = _estimate_chunks(text)
        return ok(
            **{
                "action": action,
                "docId": doc_id,
                "kbId": kb_id,
                "kbName": kb_name,
                "fileName": file_name,
                "status": DOC_PENDING,
                "statusText": "处理中",
                "estimatedChunks": chunk_hint,
                "message": (
                    f"已把「{file_name}」存入我的资料"
                    f"{('「' + kb_name + '」') if kb_name else ''}（docId={doc_id}），"
                    "正在后台分块并向量化，稍后即可用 knowledge_search 检索到"
                ),
                # 2026-10-26：导入后能直接跳到知识库看处理进度。
                # 「上传完了却没地方确认它好了没」是资料入库这条链路最容易断的地方 ——
                # 用户看到"处理中"却不知道去哪里看，只能等。
                "jumpUrl": f"/front/workspace?kbId={kb_id}&docId={doc_id}&open=1",
            }
        )

    async def _execute_from_url(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """抓取一个公开网页并写入知识库（与手动入口共用官方 Fetch 服务）。"""
        kb_id = _to_int(params.get("kb_id"))
        if kb_id is None:
            return fail(
                "网页入库需要 kb_id",
                "请先用 knowledge_base_manage 的 action=list 拿到知识库 ID；"
                "如果不知道要存入哪个库，先问用户。",
            )
        url = str(params.get("url") or "").strip()
        if not url:
            return fail(
                "网页入库需要 url",
                "请先用 web_search 找到目标网页，或让用户提供公开网址。",
            )
        try:
            await rws.get_knowledge_base(ctx.db, ctx.user_id, kb_id)
        except RagNotFound:
            return fail(f"没有找到属于你的知识库：kbId={kb_id}", "请重新确认知识库 ID。")

        from app.services.ai.web_search_service import WebSearchError, fetch_web_page

        try:
            page = await fetch_web_page(
                ctx.db,
                url,
                max_chars=MAX_RAW_LENGTH - 1200,
                user_id=ctx.user_id or None,
            )
        except WebSearchError as exc:
            return fail(str(exc), "请换一个公开网页，或确认网址可以正常访问。")

        title = str(page.get("title") or "网页资料").strip()
        content = str(page.get("content") or "").strip()
        if len(content) < 80:
            return fail("这个网页没有足够的可读正文，无法作为学习资料。", "请换一个内容完整的网页。")
        safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" ._")[:80] or "网页资料"
        file_name = str(params.get("file_name") or f"{safe_title}.md").strip()
        if not file_name.lower().endswith((".md", ".markdown", ".txt")):
            file_name += ".md"
        body_text = f"# {title}\n\n> 来源：{page.get('url') or url}\n\n{content}"

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                doc = await rws.create_document(
                    db,
                    ctx.user_id,
                    kb_id,
                    file_name=file_name,
                    raw_content=body_text,
                    file_type="url",
                    source_url=page.get("url") or url,
                    status=DOC_PENDING,
                )
                doc_id = int(doc.id)
                unchanged = bool(getattr(doc, "_upload_unchanged", False))
                try:
                    kb_name = (await rws.get_knowledge_base(db, ctx.user_id, kb_id)).name
                except Exception:  # noqa: BLE001
                    kb_name = ""
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        if not unchanged:
            self._schedule_processing(doc_id)
        return ok(
            action="from_url",
            docId=doc_id,
            kbId=kb_id,
            kbName=kb_name,
            fileName=file_name,
            sourceUrl=page.get("url") or url,
            title=title,
            status=DOC_PENDING,
            statusText="处理中" if not unchanged else "内容未变化",
            unchanged=unchanged,
            message=(
                f"已把网页《{title}》存入我的资料"
                f"{('「' + kb_name + '」') if kb_name else ''}（docId={doc_id}）。"
                + ("这个网页之前导入过，内容没有变化。" if unchanged else "正在后台分块并向量化，稍后即可检索。")
            ),
            jumpUrl=f"/front/workspace?kbId={kb_id}&docId={doc_id}&open=1",
        )

    async def _execute_update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """原地修改已有文档正文，不删除、不新建。"""
        doc_id = _to_int(params.get("doc_id"))
        if doc_id is None:
            return fail(
                "修改文档需要 doc_id",
                "请先用 knowledge_base_manage 的 action=list_documents 拿到文档 ID",
            )

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                doc = await rws.get_document(db, ctx.user_id, doc_id)
                # update_document 支持两种写法：完整 text，或精确 edits 补丁。
                # 补丁必须基于当前库里的正文应用，避免模型在上下文里重建全文。
                text = await self._resolve_text(params, ctx, base_text=doc.raw_content or "")
                if isinstance(text, dict):
                    return text
                if not text.strip():
                    return fail(
                        "没有可写入的正文内容",
                        "请提供完整的 text，或提供非空的 edits 作为修改后的正文",
                    )
                if len(text) > MAX_RAW_LENGTH:
                    return fail(
                        f"正文过长（{len(text)} 字，上限 {MAX_RAW_LENGTH} 字）",
                        "请精简内容后再修改，或拆成多篇文档分次写入",
                    )
                kb_id = doc.kb_id
                old_file_name = doc.file_name
                new_file_name = (params.get("file_name") or "").strip() or None
                updated = await rws.update_document_content(
                    db,
                    ctx.user_id,
                    doc_id,
                    text,
                    file_name=new_file_name,
                )
                kb_name = None
                try:
                    kb_name = (await rws.get_knowledge_base(db, ctx.user_id, kb_id)).name
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        # update_document_content 只把状态置为待解析；这里必须显式重跑流水线，
        # 否则旧 chunks/向量还留在库里，检索会继续命中旧内容。
        self._schedule_processing(doc_id)
        file_name = updated.get("fileName") or new_file_name or old_file_name
        chunk_hint = _estimate_chunks(text)
        return ok(
            **{
                "action": "update_document",
                "docId": doc_id,
                "kbId": kb_id,
                "kbName": kb_name,
                "fileName": file_name,
                "status": DOC_PENDING,
                "statusText": "待重新解析",
                "estimatedChunks": chunk_hint,
                "versionId": updated.get("versionId"),
                "message": (
                    f"已原地更新「{file_name}」的正文（docId={doc_id}），"
                    "旧内容不会留下重复文档；正在后台重新分块并向量化，"
                    "完成后即可用 knowledge_search 检索到新内容"
                ),
                "jumpUrl": f"/front/workspace?kbId={kb_id}&docId={doc_id}&open=1",
            }
        )

    async def _execute_restore_version(
        self, params: Dict[str, Any], ctx: ToolContext
    ) -> Dict[str, Any]:
        """把文档恢复到一个已保存的历史版本，并自动重建索引。"""
        doc_id = _to_int(params.get("doc_id"))
        version_id = _to_int(params.get("version_id"))
        if doc_id is None or version_id is None:
            return fail(
                "恢复历史版本需要 doc_id 和 version_id",
                "请先用 knowledge_base_manage action=list_document_versions 列出可恢复版本",
            )

        from app.database import async_session_factory

        try:
            async with async_session_factory() as db:
                doc = await rws.get_document(db, ctx.user_id, doc_id)
                kb_id = doc.kb_id
                result = await rws.restore_document_version(
                    db, ctx.user_id, doc_id, version_id
                )
                kb_name = None
                try:
                    kb_name = (await rws.get_knowledge_base(db, ctx.user_id, kb_id)).name
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            return self._fail_from(e)

        self._schedule_processing(doc_id)
        return ok(
            **{
                "action": "restore_document_version",
                "docId": doc_id,
                "versionId": version_id,
                "kbId": kb_id,
                "kbName": kb_name,
                "fileName": result.get("fileName") or doc.file_name,
                "status": DOC_PENDING,
                "statusText": "待重新解析",
                "message": (
                    f"已把「{result.get('fileName') or doc.file_name}」恢复到历史版本 "
                    f"versionId={version_id}；正在后台重新分块并向量化，完成后检索到的是恢复后的内容"
                ),
                "jumpUrl": f"/front/workspace?kbId={kb_id}&docId={doc_id}&open=1",
            }
        )

    # ------------------------------------------------------------------ 辅助

    @staticmethod
    def _schedule_processing(doc_id: int) -> None:
        """把 `process_document` 丢进当前事件循环的后台任务。

        ⚠️ 不能用 `BackgroundTasks`（那是 FastAPI 请求级注入，工具层拿不到）；
        `asyncio.create_task` 在正在运行的循环里跑，工具调用本就在循环里。
        任务内部自己吞异常（`process_document` 失败会落 status=4），所以这里
        不需要额外包一层；但为稳妥仍加 done-callback 记日志，避免「任务异常无人知」。
        """
        from app.services.rag import document_pipeline

        try:
            task = asyncio.get_running_loop().create_task(
                document_pipeline.process_document(doc_id)
            )
        except RuntimeError:
            # 理论上不会发生（工具总在事件循环里被 await）；退化为同步跑，
            # 保证「内容不丢」优先于「不阻塞」。
            logger.warning("[agent.knowledge_ingest] 无运行中的事件循环，改为同步处理 docId={}", doc_id)
            asyncio.get_event_loop().run_until_complete(
                document_pipeline.process_document(doc_id)
            )
            return

        task.add_done_callback(
            lambda t: (
                t.exception() and logger.error(
                    "[agent.knowledge_ingest] 后台向量化任务异常 docId={}: {}", doc_id, t.exception()
                )
            )
        )

    async def _resolve_text(
        self, params: Dict[str, Any], ctx: ToolContext, base_text: Optional[str] = None
    ) -> Any:
        """取待写入的正文；返回 `str` 成功，返回 `dict` 则是 `fail()` 信封。

        · from_text：直接取 `text` 参数
        · update_document：优先用 `edits` 补丁应用到当前正文；否则取完整 `text`
        · from_attachment：从 `ctx.extra["attachments"]` 里取本轮附件的**已解析正文**
        """
        action = str(params.get("action") or "")
        if action == "from_text":
            return str(params.get("text") or "")

        if action == "update_document":
            edits = params.get("edits")
            raw_text = str(params.get("text") or "")
            if edits:
                if raw_text.strip():
                    return fail(
                        "update_document 不能同时提供 text 和 edits",
                        "二选一：整篇替换用 text；局部修改用 edits 补丁",
                    )
                if base_text is None:
                    return fail(
                        "无法应用 edits：没有读取到当前文档正文",
                        "请先读取文档，再基于原文提交补丁",
                    )
                return _apply_document_edits(base_text, edits)
            return raw_text

        if action == "from_attachment":
            attachments: List[Dict[str, Any]] = list(ctx.extra.get("attachments") or [])
            if not attachments:
                return fail(
                    "本轮对话没有可用的附件正文",
                    "用户这次没有上传可解析的文档。请告诉用户重新上传文件，"
                    "或改用 from_text 直接写入你生成的文本",
                )
            index = _to_int(params.get("index")) or 0
            if index < 0 or index >= len(attachments):
                return fail(
                    f"附件序号越界：index={index}，本轮共 {len(attachments)} 个附件",
                    f"请把 index 改成 0 到 {len(attachments) - 1} 之间",
                )
            att = attachments[index] or {}
            text = str(att.get("text") or "")
            if not text.strip():
                return fail(
                    "该附件没有可写入的正文（可能只含图片或解析失败）",
                    "请改用其它附件，或告诉用户该文件无法作为文本文档入库",
                )
            return text

        return fail(
            f"未知操作: {action}",
            "action 只能是 from_text / from_attachment / update_document",
        )

    @staticmethod
    def _resolve_file_name(params: Dict[str, Any], action: str) -> str:
        """文档显示名：优先模型给的 `file_name`，其次附件名，最后按来源兜一个。"""
        name = (params.get("file_name") or "").strip()
        if name:
            return name
        if action == "from_attachment":
            return "用户上传的文档"
        return "AI 写入的文档"

    @staticmethod
    def _fail_from(e: Exception) -> Dict[str, Any]:
        """把 rag 服务的异常翻成给模型的 `fail()`（`hint` 必填）"""
        if isinstance(e, RagNotFound):
            return fail(
                str(e),
                "请先用 knowledge_base_manage 的 action=list / list_documents "
                "确认 kb_id 或 doc_id 是不是你的",
            )
        if isinstance(e, RagConflict):
            return fail(str(e), "该资料夹文档数已达上限，请先删除一些文档或换一个资料夹")
        if isinstance(e, ValueError):
            return fail(
                str(e),
                "如果是文档正在处理中，请等当前解析/向量化完成后再修改或恢复版本",
            )
        return fail(
            f"写入我的资料失败：{type(e).__name__}: {e}",
            "请检查 doc_id / kb_id 与正文是否符合要求；若反复失败，请先用 "
            "knowledge_base_manage 的 action=list 或 list_documents 重新确认目标",
        )


__all__ = ["KnowledgeIngestTool"]
