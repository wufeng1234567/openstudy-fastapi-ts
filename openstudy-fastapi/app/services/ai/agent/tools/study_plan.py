"""`study_plan` —— 在智能对话里生成/查看「规划建议」。

旧 action（plan/today/adjust/reassess）仍返回可重建的学习计划；新 action
`advise` 返回可反复修改的 `StudyAdvice` + 真实图遍历 `trace`，供页面/对话
生成式卡片复用。

不建任务表、不写完成态、不复制题目。历史只存建议快照。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.services import study_advice_service, study_plan_history_service
from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok
from app.services.study_plan_service import build_study_plan

MAX_DAYS_RETURNED = 14


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


async def _resolve_kb_id(ctx: ToolContext, params: Dict[str, Any]) -> int | Dict[str, Any]:
    from app.services.rag import rag_write_service as rws

    kid = _to_int(params.get("kb_id"))
    if kid:
        try:
            await rws.get_knowledge_base(ctx.db, ctx.user_id, kid)
            return kid
        except Exception:  # noqa: BLE001
            return fail(f"没有找到属于你的知识库：kbId={kid}", "请确认知识库 ID，或先让用户选择资料夹。")
    bases = await rws.list_knowledge_bases(ctx.db, ctx.user_id)
    if len(bases) == 1:
        return int(bases[0]["kbId"])
    # 用户明确只按题库安排时，不需要知识图谱资料夹。
    if params.get("bank_ids"):
        return 0
    if not bases:
        return 0
    names = "、".join(str(item.get("name") or "未命名") for item in bases[:8])
    return fail(
        "生成学习计划需要先确定用哪个资料夹的知识图谱",
        f"当前有 {len(bases)} 个资料夹：{names}。请让用户指定一个，再传 kb_id；如果只想按题库安排，请传 bank_ids。",
    )


def _compact_graph(graph: Dict[str, Any], trace: Dict[str, Any]) -> Dict[str, Any]:
    """对话卡片只需要 trace 子图，避免整张图灌进模型上下文。"""
    visited = {str(x) for x in (trace.get("visitedNodeIds") or [])}
    nodes = [node for node in (graph.get("nodes") or []) if str(node.get("id")) in visited]
    node_ids = {str(node["id"]) for node in nodes}
    edges = [
        edge
        for edge in (graph.get("edges") or [])
        if str(edge.get("source")) in node_ids and str(edge.get("target")) in node_ids
    ]
    return {"nodes": nodes[:30], "edges": edges[:40], "stats": graph.get("stats") or {}}


async def _run_advise(ctx: ToolContext, params: Dict[str, Any], kb_id: int) -> Dict[str, Any]:
    source_types = params.get("source_types") or ["wiki", "bank"]
    if not isinstance(source_types, list):
        source_types = ["wiki", "bank"]
    preview = await study_advice_service.prepare_trace(
        ctx.db,
        int(ctx.user_id),
        kb_id=int(kb_id or 0),
        bank_ids=[int(x) for x in (params.get("bank_ids") or []) if _to_int(x)],
        source_types=source_types,
        seed_node_id=str(params.get("seed_node_id") or ""),
        goal=str(params.get("goal") or "weakness"),
        daily_minutes=_to_int(params.get("daily_minutes")) or 30,
        horizon_days=_to_int(params.get("horizon_days")) or 14,
        instruction=str(params.get("instruction") or ""),
    )
    advice = await study_advice_service.generate_advice(
        ctx.db,
        facts=preview["facts"],
        trace=preview["trace"],
        instruction=str(params.get("instruction") or ""),
        use_llm=True,
    )
    # 用独立会话保存快照，避免在 Agent 的工具事务里 commit 污染外层。
    from app.database import async_session_factory

    async with async_session_factory() as save_db:
        saved = await study_plan_history_service.save_snapshot(
            save_db,
            user_id=int(ctx.user_id),
            kb_id=int(kb_id or 0),
            title=str(advice.get("title") or ""),
            scope=advice.get("scope") or {},
            advice=advice,
            trace=preview["trace"],
            graph=_compact_graph(preview["graph"], preview["trace"]),
            parent_id=_to_int(params.get("parent_advice_id")) or 0,
            source="chat",
        )
    return ok(
        action="advise",
        kbId=kb_id,
        adviceId=saved.get("id") or 0,
        advice=advice,
        trace=preview["trace"],
        graph=_compact_graph(preview["graph"], preview["trace"]),
        message=str(advice.get("summary") or "已生成规划建议"),
        jumpUrl=f"/front/myQuestion/myStats?tab=plan&adviceId={saved.get('id') or 0}",
    )


def _public_plan(plan: Dict[str, Any], limit_days: int = MAX_DAYS_RETURNED) -> Dict[str, Any]:
    """控制回灌模型的长度：完整 route 保留，days 最多前 N 天。"""
    return {
        "planId": plan.get("planId"),
        "generatedAt": plan.get("generatedAt"),
        "intent": plan.get("intent") or {},
        "bankIds": plan.get("bankIds") or [],
        "axisSummary": plan.get("axisSummary") or {},
        "window": plan.get("window") or {},
        "route": plan.get("route") or {},
        "days": (plan.get("days") or [])[:limit_days],
        "progress": plan.get("progress") or {},
        "sources": plan.get("sources") or {},
        "degraded": plan.get("degraded") or {},
    }


class StudyPlanTool(AgentTool):
    name = "study_plan"
    description = (
        "Give the user a study recommendation grounded in the real knowledge graph and "
        "question banks. Use action=advise whenever the user asks for a study plan, "
        "what to study next, how to improve, or asks to connect a topic/note/document/"
        "question bank to a plan. `advise` returns a StudyAdvice (no tasks/checkboxes), "
        "a real graph traversal trace, a compact graph for the generative card, and a "
        "snapshot id. It never invents nodes, edges, questions or completion. Old "
        "actions plan/today/adjust/reassess remain for backward compatibility; prefer "
        "advise for new conversations. Pass kb_id when the user has multiple knowledge "
        "bases; pass bank_ids for specific banks; pass seed_node_id when the user picked "
        "a node. Use study_graph for raw graph search, learning_stats for raw numbers."
    )
    label = "规划建议"
    description_zh = (
        "规划建议：基于真实知识图谱与题库生成可反复修改的建议（不是任务清单）；"
        "advise=生成/调整建议（含真实遍历 trace），plan/today/adjust/reassess=旧版兼容。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["advise", "plan", "today", "adjust", "reassess"],
            },
            "kb_id": {
                "type": "integer",
                "description": "Knowledge base ID whose knowledge graph should drive the plan. Required when the user has multiple knowledge bases and wants graph tasks.",
            },
            "bank_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Question bank IDs to include as a real question-bank axis in the same plan. Use study_graph action=bank first if the user names a bank instead of an ID. Omit to use graph-only tasks; when there is no knowledge base, the tool falls back to the user's real weak questions.",
            },
            "source_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["wiki", "bank", "document", "web", "note", "image"]},
                "description": "Graph source layers to include. Default wiki+bank. Add document/web/note/image when the user explicitly mentions those materials.",
            },
            "seed_node_id": {
                "type": "string",
                "description": "Optional unified node id selected by the user, e.g. topic:12, bank:1293, note:9, doc:45, web:45, image:45.",
            },
            "instruction": {
                "type": "string",
                "description": "The user's natural-language adjustment, e.g. 'more basic' or 'only 20 minutes per day'.",
            },
            "parent_advice_id": {
                "type": "integer",
                "description": "Previous snapshot id when this is an adjustment of an existing advice.",
            },
            "goal": {
                "type": "string",
                "description": "Learning goal",
                "enum": ["weakness", "foundation", "explore", "exam", "today", "sections"],
            },
            "exam_date": {
                "type": "string",
                "description": "Exam date in YYYY-MM-DD (used for exam countdown mode).",
            },
            "horizon_days": {
                "type": "integer",
                "description": "How many calendar days to include (1-30, default 7).",
            },
            "daily_minutes": {
                "type": "integer",
                "description": "Minutes the user can study per day (10-240, default 40).",
            },
            "rest_days": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Weekdays to rest, 1=Monday ... 7=Sunday.",
            },
            "focus_page_id": {
                "type": "integer",
                "description": "Optional knowledge page ID to use as the route target.",
            },
            "doc_id": {
                "type": "integer",
                "description": "Optional document ID to restrict the route to pages sourced from that document.",
            },
            "section_indexes": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional document section indexes the user wants to focus on.",
            },
            "mode": {
                "type": "string",
                "description": "Exam plan intensity: balanced or sprint.",
                "enum": ["balanced", "sprint"],
            },
        },
        "required": ["action"],
    }
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "plan").strip().lower()
        if action not in {"advise", "plan", "today", "adjust", "reassess"}:
            return fail(
                f"未知操作: {action}",
                "action 只能是 advise / plan / today / adjust / reassess。",
            )
        kb = await _resolve_kb_id(ctx, params)
        if isinstance(kb, dict):
            return kb
        if action == "advise":
            return await _run_advise(ctx, params, int(kb or 0))
        goal = str(params.get("goal") or ("today" if action == "today" else "weakness"))
        if action == "today" and goal not in {"today", "weakness", "foundation", "explore"}:
            goal = "today"
        exam_date = _parse_date(params.get("exam_date"))
        horizon = 1 if action == "today" else _to_int(params.get("horizon_days")) or 7
        daily = _to_int(params.get("daily_minutes")) or 40
        rest_days = params.get("rest_days") or []
        if not isinstance(rest_days, list):
            rest_days = []
        section_indexes = params.get("section_indexes") or []
        if not isinstance(section_indexes, list):
            section_indexes = []
        bank_ids = params.get("bank_ids") or []
        if not isinstance(bank_ids, list):
            bank_ids = []
        try:
            plan = await build_study_plan(
                ctx.db,
                ctx.user_id,
                int(kb or 0),
                goal=goal,
                exam_date=exam_date,
                horizon_days=horizon,
                daily_minutes=daily,
                rest_days=[int(x) for x in rest_days if _to_int(x)],
                focus_page_id=_to_int(params.get("focus_page_id")),
                doc_id=_to_int(params.get("doc_id")),
                section_indexes=[int(x) for x in section_indexes if _to_int(x) is not None],
                bank_ids=[int(x) for x in bank_ids if _to_int(x) is not None],
                mode=str(params.get("mode") or "balanced"),
            )
        except ValueError as exc:
            return fail(str(exc), "请检查知识库、日期和每日时间后再试。")
        except Exception as exc:  # noqa: BLE001
            return fail(f"生成学习计划失败：{exc}", "请稍后重试，或先确认知识库已经生成知识百科主题页。")

        today_tasks: List[Dict[str, Any]] = []
        today_date = date.today().isoformat()
        for day in plan.get("days") or []:
            if str(day.get("date") or "") == today_date:
                today_tasks = list(day.get("tasks") or [])
                break
        # 不再把第一天冒充“今天”：今天没有任务就如实说没有。
        next_day = next(
            (day for day in (plan.get("days") or []) if str(day.get("date") or "") > today_date),
            None,
        )
        if today_tasks:
            today_text = "今天先做：" + "、".join(
                str(t.get("title") or "") for t in today_tasks[:3]
            ) + "。"
        elif next_day:
            today_text = (
                f"今天没有安排；下一段计划从 {next_day.get('date')} 开始："
                + "、".join(
                    str(t.get("title") or "")
                    for t in (next_day.get("tasks") or [])[:3]
                )
                + "。"
            )
        else:
            today_text = "当前没有可执行任务，先读一个主题页或做一道题。"

        message = (
            f"已生成学习计划：{len(plan.get('days') or [])} 天，"
            f"共 {(plan.get('progress') or {}).get('totalTasks', 0)} 个任务。"
            + today_text
            + "完成后重新调用 reassess 即可看到进度自动推进。"
        )
        payload: Dict[str, Any] = {
            "action": action,
            "kbId": kb,
            "planId": plan.get("planId"),
            "planVersion": plan.get("planVersion"),
            "progress": plan.get("progress") or {},
            "todayTasks": today_tasks,
            "message": message,
            "jumpUrl": (
                f"/front/myQuestion/myStats?tab=plan&kbId={kb}"
                if int(kb or 0) > 0
                else "/front/myQuestion/myStats?tab=plan"
            ),
        }
        # today 只回今日任务与摘要，避免整份 days 灌进对话上下文；
        # plan/adjust/reassess 才返回最多 14 天的计划。
        if action != "today":
            payload["plan"] = _public_plan(plan)
        return ok(**payload)


__all__ = ["StudyPlanTool"]
