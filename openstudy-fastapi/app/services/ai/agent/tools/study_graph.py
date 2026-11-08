"""`study_graph` —— 让智能体查询知识图谱、题库与真实题→页映射。

这是「学习计划」的只读上游：LLM 先看清知识页/题库/薄弱题，再调用
`study_plan` 生成或调整同一份计划。工具不写库、不猜知识点、不判定完成。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.rag import study_graph_service, wiki_service


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _resolve_kb_id(ctx: ToolContext, params: Dict[str, Any]) -> int:
    """明确 kb_id 时校验；否则优先默认资料夹，没有资料夹则返回 0（纯题库）。"""
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


def _page_brief(page: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pageId": int(page.get("pageId") or 0),
        "title": str(page.get("title") or ""),
        "pageType": str(page.get("pageType") or ""),
        "summary": str(page.get("summary") or "")[:240],
        "status": str(page.get("status") or ""),
        "learning": page.get("learning") or {},
        "weakCount": int(page.get("weakCount") or 0),
        "weakQuestionIds": list(page.get("weakQuestionIds") or []),
        "bankIds": list(page.get("bankIds") or []),
    }


def _bank_brief(bank: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "bankId": int(bank.get("bankId") or 0),
        "bankName": str(bank.get("title") or ""),
        "subject": str(bank.get("subject") or ""),
        "questionCount": int(bank.get("questionCount") or 0),
        "practicedQuestionCount": int(bank.get("practicedQuestionCount") or 0),
        "attemptCount": int(bank.get("attemptCount") or 0),
        "accuracy": float(bank.get("accuracy") or 0),
        "weakCount": int(bank.get("weakCount") or 0),
        "mappedQuestionCount": int(bank.get("mappedQuestionCount") or 0),
        "pageIds": list(bank.get("pageIds") or []),
        "legacy": bool(bank.get("legacy")),
    }


class StudyGraphTool(AgentTool):
    name = "study_graph"
    description = (
        "Read the user's learning graph: knowledge pages, their prerequisite/related "
        "edges and real learning state, plus the user's question banks and real weak "
        "questions. Use this when the user asks what their knowledge graph contains, "
        "which topics are weak, which question bank to study, how a question bank maps "
        "to knowledge pages, or when you need bank IDs before calling study_plan. "
        "action values: overview=page/bank counts and page summaries; search=search "
        "page titles/summaries, bank names/subjects and question text; page=one wiki "
        "page's summary and learning state; bank=one bank's real statistics and weak "
        "questions; question_map=map one or more question IDs to their real "
        "QuestionSource anchor and knowledge page (pageId=0 when there is no anchor). "
        "It never invents knowledge-point links: bank→page edges exist only when "
        "QuestionSource doc/chunk anchors really match."
    )
    label = "知识图谱"
    description_zh = (
        "知识图谱：overview=知识页+题库总览、search=搜知识页/题库/题目、"
        "page=看一个知识页的学习状态、bank=看一个题库的真实薄弱题、"
        "question_map=查题目真实落在哪个知识页（无锚点返回 0）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["overview", "search", "page", "bank", "question_map"],
            },
            "kb_id": {
                "type": "integer",
                "description": "Knowledge base ID. Omit to use the user's default knowledge base; 0 means question-bank-only.",
            },
            "q": {
                "type": "string",
                "description": "Search keyword for action=search (page title/summary, bank name/subject, question text).",
            },
            "page_id": {
                "type": "integer",
                "description": "Wiki page ID for action=page.",
            },
            "bank_id": {
                "type": "integer",
                "description": "Question bank ID for action=bank.",
            },
            "bank_name": {
                "type": "string",
                "description": "Question bank name for action=bank when bank_id is not known.",
            },
            "question_id": {
                "type": "integer",
                "description": "Question ID for action=question_map.",
            },
            "question_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Question IDs for action=question_map (batch).",
            },
            "limit": {
                "type": "integer",
                "description": "Max results for search/overview (default 8, max 20).",
            },
        },
        "required": ["action"],
    }
    write_operation = False

    async def execute(self, params: Dict[str, Any], tool_ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "overview").strip().lower()
        if action not in {"overview", "search", "page", "bank", "question_map"}:
            return fail(
                f"未知操作: {action}",
                "action 只能是 overview / search / page / bank / question_map。",
            )
        kb_id = await _resolve_kb_id(tool_ctx, params)
        limit = max(1, min(_to_int(params.get("limit")) or 8, 20))

        if action == "question_map":
            raw_ids = params.get("question_ids") or []
            if not isinstance(raw_ids, list):
                raw_ids = []
            if params.get("question_id") is not None:
                raw_ids = [*raw_ids, params.get("question_id")]
            ids = [_to_int(item) for item in raw_ids if _to_int(item) is not None]
            if not ids:
                return fail("question_map 需要 question_id 或 question_ids", "请提供至少一个题号。")
            rows = await study_graph_service.map_questions_to_pages(
                tool_ctx.db, tool_ctx.user_id, ids, kb_id=kb_id
            )
            anchored = sum(1 for item in rows if item.get("anchored"))
            return ok(
                action="question_map",
                kbId=kb_id,
                questions=rows,
                message=(
                    f"共查询 {len(rows)} 道题，{anchored} 道有真实资料锚点；"
                    "没有锚点的题 pageId=0，不猜测知识页。"
                ),
            )

        if action == "overview":
            graph = await study_graph_service.build_study_graph(
                tool_ctx.db,
                tool_ctx.user_id,
                kb_id,
                bank_limit=min(max(limit, 4), 12),
            )
            pages = [
                _page_brief(item)
                for item in graph.get("nodes") or []
                if item.get("kind") == "page"
            ][:limit]
            banks = [_bank_brief(item) for item in graph.get("banks") or []]
            return ok(
                action="overview",
                kbId=kb_id,
                stats=graph.get("stats") or {},
                pages=pages,
                banks=banks,
                degraded=graph.get("degraded") or {},
                message=(
                    f"当前图谱有 {int((graph.get('stats') or {}).get('pageCount') or 0)} 个知识页、"
                    f"{int((graph.get('stats') or {}).get('bankCount') or 0)} 个题库；"
                    f"其中 {int((graph.get('stats') or {}).get('linkedBankCount') or 0)} 个题库有真实题源锚点。"
                ),
                jumpUrl=f"/front/myQuestion/myStats?tab=plan&kbId={kb_id}",
            )

        if action == "search":
            q = str(params.get("q") or "").strip()
            if not q:
                return fail("search 需要关键词 q", "请提供要搜索的主题、题库名或题目关键词。")
            result = await study_graph_service.search_study_graph(
                tool_ctx.db, tool_ctx.user_id, q, kb_id=kb_id, limit=limit
            )
            return ok(
                action="search",
                kbId=kb_id,
                **result,
                message=(
                    f"找到 {len(result.get('pages') or [])} 个知识页、"
                    f"{len(result.get('banks') or [])} 个题库、"
                    f"{len(result.get('questions') or [])} 道题。"
                ),
            )

        if action == "page":
            page_id = _to_int(params.get("page_id"))
            if not page_id:
                return fail("page 需要 page_id", "请先用 overview/search 找到知识页 ID。")
            try:
                page = await wiki_service.get_wiki_page(
                    tool_ctx.db, tool_ctx.user_id, int(page_id)
                )
            except Exception as exc:  # noqa: BLE001
                return fail(f"读取知识页失败：{exc}", "请确认 page_id 属于当前用户。")
            if not page:
                return fail("没有找到这个知识页", "请先用 study_graph overview 确认可用的 page_id。")
            return ok(
                action="page",
                kbId=kb_id,
                pageId=int(page_id),
                title=page.get("title") or "",
                summary=page.get("summary") or "",
                learning=page.get("learning") or {},
                practice=page.get("practice") or {},
                sourceCount=len(page.get("sources") or []),
                sectionHeadings=[
                    str(item.get("heading") or "")
                    for item in (page.get("sections") or [])
                    if item.get("heading")
                ],
                related=page.get("related") or [],
                jumpUrl=f"/front/workspace?view=wiki&kbId={kb_id}&pageId={int(page_id)}",
            )

        # action == bank
        bank_id = _to_int(params.get("bank_id"))
        bank_name = str(params.get("bank_name") or "").strip()
        if not bank_id:
            graph = await study_graph_service.build_study_graph(
                tool_ctx.db,
                tool_ctx.user_id,
                kb_id,
                bank_limit=20,
            )
            candidates = graph.get("banks") or []
            if bank_name:
                exact = next(
                    (item for item in candidates if str(item.get("title") or "") == bank_name),
                    None,
                )
                fuzzy = next(
                    (item for item in candidates if bank_name in str(item.get("title") or "")),
                    None,
                )
                chosen = exact or fuzzy
                bank_id = int(chosen.get("bankId") or 0) if chosen else 0
            if not bank_id:
                return ok(
                    action="bank",
                    banks=[_bank_brief(item) for item in candidates],
                    message=(
                        "没有指定题库，请先从列表里选择题库；"
                        "也可以用 bank_manage action=list 查看全部题库。"
                    ),
                )
        bank = await study_graph_service.get_study_bank(
            tool_ctx.db, tool_ctx.user_id, int(bank_id), kb_id=kb_id
        )
        if not bank:
            return fail("没有找到这个题库或它不属于当前用户", "请先用 study_graph overview 或 bank_manage list 确认。")
        return ok(
            action="bank",
            kbId=kb_id,
            bank=_bank_brief(bank),
            weakQuestions=bank.get("weakQuestions") or [],
            message=(
                f"题库《{bank.get('title') or ''}》共 {int(bank.get('questionCount') or 0)} 题，"
                f"当前有 {int(bank.get('weakCount') or 0)} 道需要优先处理。"
                + (
                    "有真实题源锚点，可映射到知识页。"
                    if int(bank.get("mappedQuestionCount") or 0) > 0
                    else "没有可反查的知识页锚点，只能按题库直接安排。"
                )
            ),
            jumpUrl=f"/front/questionPractice/{int(bank_id)}",
        )


__all__ = ["StudyGraphTool"]
