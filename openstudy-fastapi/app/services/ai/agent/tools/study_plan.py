"""`study_plan` —— 在智能对话里生成/查看「知航 · 活计划」。

用户说「我 7 天后考微积分，帮我安排」时，模型不应该自己编一份计划，
也不应该把用户踢回某个页面。这个工具直接复用 `study_plan_service` 的
确定性排程，返回与知识图谱、学习统计同一份 StudyPlan。

只读：不建表、不写完成态、不复制题目。真正完成由答题流水和主题页阅读
自动回写。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

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
    names = "、".join(str(item.get("name") or "未命名") for item in bases[:8])
    return fail(
        "生成学习计划需要先确定用哪个资料夹的知识图谱",
        f"当前有 {len(bases)} 个资料夹：{names}。请让用户指定一个，再传 kb_id。",
    )


def _public_plan(plan: Dict[str, Any], limit_days: int = MAX_DAYS_RETURNED) -> Dict[str, Any]:
    """控制回灌模型的长度：完整 route 保留，days 最多前 N 天。"""
    return {
        "planId": plan.get("planId"),
        "generatedAt": plan.get("generatedAt"),
        "intent": plan.get("intent") or {},
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
        "Build or read the user's single knowledge-graph-driven study plan "
        "(知航 · 活计划). Use this whenever the user asks what to study today, asks for "
        "a study plan / schedule / exam countdown plan, mentions a goal such as "
        "'in 7 days I have an exam', or asks to connect study tasks to their knowledge "
        "graph. The plan is computed deterministically from the real knowledge graph, "
        "practice diagnosis and practice logs; it does not invent pages, questions or "
        "completion. action values: plan=return the full plan; today=return today's "
        "tasks and progress; adjust=recompute with new parameters; reassess=recompute "
        "from the latest real learning data. Always pass kb_id when the user has more "
        "than one knowledge base; if you do not know it, ask the user or call "
        "knowledge_base_manage action=list first. Do not use this for simply querying "
        "statistics; use learning_stats for raw numbers."
    )
    label = "学习规划"
    description_zh = (
        "知航 · 活计划：按知识图谱生成今天/未来几天的可执行学习任务；"
        "plan=完整计划、today=今日任务、adjust=按新目标重算、reassess=按最新学习数据重算。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["plan", "today", "adjust", "reassess"],
            },
            "kb_id": {
                "type": "integer",
                "description": "Knowledge base ID whose knowledge graph should drive the plan. Required when the user has multiple knowledge bases.",
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
        if action not in {"plan", "today", "adjust", "reassess"}:
            return fail(
                f"未知操作: {action}",
                "action 只能是 plan / today / adjust / reassess。",
            )
        kb = await _resolve_kb_id(ctx, params)
        if isinstance(kb, dict):
            return kb
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
        try:
            plan = await build_study_plan(
                ctx.db,
                ctx.user_id,
                kb,
                goal=goal,
                exam_date=exam_date,
                horizon_days=horizon,
                daily_minutes=daily,
                rest_days=[int(x) for x in rest_days if _to_int(x)],
                focus_page_id=_to_int(params.get("focus_page_id")),
                doc_id=_to_int(params.get("doc_id")),
                section_indexes=[int(x) for x in section_indexes if _to_int(x) is not None],
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
        if action == "today" and not today_tasks and plan.get("days"):
            today_tasks = list((plan.get("days") or [])[0].get("tasks") or [])

        message = (
            f"已生成「知航 · 活计划」：{len(plan.get('days') or [])} 天，"
            f"共 {(plan.get('progress') or {}).get('totalTasks', 0)} 个任务。"
            "今天先做："
            + ("、".join(str(t.get("title") or "") for t in today_tasks[:3]) if today_tasks else "暂无任务，先读一个主题页。")
            + "。完成后重新调用 reassess 即可看到进度自动推进。"
        )
        payload: Dict[str, Any] = {
            "action": action,
            "kbId": kb,
            "planId": plan.get("planId"),
            "planVersion": plan.get("planVersion"),
            "progress": plan.get("progress") or {},
            "todayTasks": today_tasks,
            "message": message,
            "jumpUrl": f"/front/workspace?view=wiki&kbId={kb}&plan=1",
        }
        # today 只回今日任务与摘要，避免整份 days 灌进对话上下文；
        # plan/adjust/reassess 才返回最多 14 天的计划。
        if action != "today":
            payload["plan"] = _public_plan(plan)
        return ok(**payload)


__all__ = ["StudyPlanTool"]
