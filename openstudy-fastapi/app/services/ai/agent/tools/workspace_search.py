"""
`workspace_search` —— 工作空间找文件工具（Agent 自封装，**只读**）

解决的是「用户说的那份资料到底在哪」：
  用户把资料丢进「我的空间」后，会在对话里说「用那份概率论的资料出题」
  「把我上次传的期末卷拿来建题库」。这个工具负责**把文件找出来**，
  把 docId / 文件名 / 备注 / 是否可检索告诉模型，后续出题再交给
  `knowledge_search`（它拿 docId 去检索正文）。

为什么需要它（而不是直接用 knowledge_search）
========================================
`knowledge_search` 搜的是**正文片段**（语义检索），它回答「哪段话相关」。
用户说「那份概率论的资料」时，他要的是**整个文件**——用语义检索去拼一个
文件列表，会得到「命中了 5 个片段，来自 3 个文件」这种噪音。

这个工具按 **文件名 + 用户备注 + 正文是否包含** 打分，
直接返回「文件级」结果，模型才能说「我找到 3 份，最像的是《概率论与数理统计.pdf》」。

调用约定
========
- `action=search`：按 query 找（默认）
- `action=list`：列出空间里全部文件（用户说「我空间里有什么」时用）
- 找到后，模型应把 `docId` 交给 `knowledge_search` 去读正文，或直接 `bank_manage` 建库
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok

#: 一次最多返回几个文件（多了模型也挑不过来，反而干扰判断）
MAX_FILES = 8
DEFAULT_LIMIT = 5


class WorkspaceSearchTool(AgentTool):
    name = "workspace_search"
    description = (
        "Look up files the user put in their personal workspace ('我的空间'). "
        "Use this FIRST when the user refers to a document by description "
        "(e.g. 'the probability notes I uploaded', 'my final exam paper') "
        "instead of naming an exact file. "
        "Returns file-level results: docId, fileName, note, readiness. "
        "Then pass docId to knowledge_search to read its content, "
        "or use bank_manage/question_manage to build a question bank from it. "
        "action=list lists every file in the workspace."
    )
    description_zh = (
        "在用户的「我的空间」里查找资料文件。"
        "当用户用描述指代某份文件（如「我传的那份概率论资料」「上次的期末卷」）时，"
        "先用它把文件找出来，再去读正文或建题库。"
        "action=list 可列出空间里的全部文件。"
    )
    label = "工作空间"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["search", "list"],
            },
            "query": {
                "type": "string",
                "description": (
                    "What the user is looking for, in their own words. "
                    "Include any hints: subject, grade, document type, or a phrase "
                    "they used to describe it."
                ),
            },
            "limit": {
                "type": "integer",
                "description": f"Max files to return (default {DEFAULT_LIMIT}, max {MAX_FILES}).",
            },
        },
        "required": ["action"],
    }
    #: 只读 —— 不写库，不会被记进长期记忆
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "search").strip().lower()
        if action == "list":
            return await self._list(params, ctx)
        if action == "search":
            return await self._search(params, ctx)
        return fail(f"未知操作：{action}", "action 只能是 search / list")

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        from app.services.rag import workspace_service as ws

        files = await ws.list_space_files(ctx.db, ctx.user_id)
        stats = await ws.space_stats(ctx.db, ctx.user_id)

        if not files:
            return ok(
                action="list",
                count=0,
                files=[],
                stats=stats,
                message="工作空间里还没有文件。可以让用户先在「我的空间」上传资料，或者直接上传到对话里。",
            )

        limit = _clamp_limit(params.get("limit"))
        return ok(
            action="list",
            count=len(files),
            files=files[:limit],
            stats=stats,
            message=f"工作空间里有 {len(files)} 份文件（已列前 {min(limit, len(files))} 份）",
        )

    async def _search(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        from app.services.rag import workspace_service as ws

        query = str(params.get("query") or "").strip()
        if not query:
            return fail(
                "search 需要 query",
                "请把用户描述那份文件的话放进 query（如「概率论的资料」）",
            )

        limit = _clamp_limit(params.get("limit"))
        files = await ws.search_files(ctx.db, ctx.user_id, query, limit)
        stats = await ws.space_stats(ctx.db, ctx.user_id)

        if not files:
            total = stats.get("docCount", 0)
            if total == 0:
                return ok(
                    action="search",
                    query=query,
                    count=0,
                    files=[],
                    stats=stats,
                    message="工作空间里还没有文件，先让用户上传资料。",
                )
            return ok(
                action="search",
                query=query,
                count=0,
                files=[],
                stats=stats,
                message=(
                    f"空间里有 {total} 份文件，但没有一份和「{query}」对得上。"
                    "可以把空间里的文件列表给用户看，让他确认是哪一份。"
                ),
            )

        best = files[0]
        return ok(
            action="search",
            query=query,
            count=len(files),
            files=files,
            stats=stats,
            message=(
                f"找到 {len(files)} 份相关文件，最匹配的是「{best['fileName']}」"
                + (f"（备注：{best['note']}）" if best.get("note") else "")
            ),
        )


def _clamp_limit(v: Any) -> int:
    try:
        n = int(v)
    except Exception:
        return DEFAULT_LIMIT
    return max(1, min(MAX_FILES, n))
