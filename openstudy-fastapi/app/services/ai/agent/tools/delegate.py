"""
`delegate_task` —— 指挥家把任务派给某个**子代理**的元工具

在「指挥家 + 子代理」架构里（见 `docs/fastapi_v2_指挥家模式方案.md`），这是**唯一**
让指挥家"调用别的智能体"的入口。用户看不到子代理；指挥家调用本工具 → 内部启动对应
子代理（`sub_agent.run_sub_agent`）→ 把子代理的产出作为工具结果回灌给指挥家 →
指挥家整合后统一回复用户。

⚠️ 用户能"选智能体"，但那是**显式指定**（用户点名要它答），走的是另一条路
====================================================================
本工具服务于**自动路由**：用户没点名时，指挥家自行判断"这该派给谁"。用户若显式选了
某智能体，`loop` 会直接把该子代理作为"面向用户的助手"，**不会**再由指挥家委派。

⚠️ 依赖 `ctx.extra` 里的「指挥家环境」
===================================
指挥家模式启动时，`loop.run_agent_stream` 会往 `ToolContext.extra` 注入：
  · `delegate_llm`        —— 已构造好的 LLM 客户端（与指挥家同一个模型）；
  · `delegate_roles`      —— `{role_key: RoleSpec}`（官方 + 用户自定义，供按名查找）；
  · `delegate_exclude`    —— `{role_key: set(排除工具名)}`（预计算的子代理工具排除集）；
  · `delegate_extra`      —— 透传给子代理 `ToolContext.extra` 的附加键（如 attachments）。
本工具从这些键取用；缺任何一个都返回明确的 `fail()`（而不是崩）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.ai.agent.base import AgentTool, ToolContext, fail, ok


class DelegateTaskTool(AgentTool):
    name = "delegate_task"
    #: 面向模型（英文）：说明何时、如何委派
    description = (
        "Delegate a task to one of your specialist sub-agents and get its result back. "
        "You (the conductor) talk to the user; the sub-agent works in the background. "
        "Call this ONLY when the request clearly belongs to a specialist and you cannot "
        "(or should not) handle it with your own tools. Pass `sub_agent` = the specialist "
        "key from your team list, and `task` = a clear, self-contained instruction "
        "including all context the specialist needs (it does NOT see the user's chat). "
        "After it returns, integrate the result into ONE unified reply to the user and "
        "never mention that a sub-agent was involved."
    )
    label = "派发任务"
    description_zh = (
        "把一个任务派给某个专业子代理（后台执行，用户不可见），拿回结果后由你统一回复用户。"
        "仅在请求明确属于某专家时使用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "sub_agent": {
                "type": "string",
                "description": (
                    "The specialist key to delegate to (from your team list, e.g. "
                    "\"bank\", \"note\", \"kb\", \"stats\", or a user-defined \"user:<id>\")."
                ),
            },
            "task": {
                "type": "string",
                "description": (
                    "A clear, self-contained task for the specialist. Include the "
                    "context it needs; it cannot see the conversation."
                ),
            },
        },
        "required": ["sub_agent", "task"],
    }
    #: 委派本身不直接改数据（内部子代理的工具各自按写操作处理），故不是写操作
    write_operation = False

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        key = str(params.get("sub_agent") or "").strip()
        task = str(params.get("task") or "").strip()
        if not key:
            return fail("缺少 sub_agent", "请填要派给哪个子代理（见你的团队清单里的 key）")
        if not task:
            return fail("缺少 task", "请用一句话说清要子代理做什么（它看不到对话，要自包含）")

        extra = ctx.extra or {}
        llm = extra.get("delegate_llm")
        roles: Dict[str, Any] = dict(extra.get("delegate_roles") or {})
        excludes: Dict[str, Any] = dict(extra.get("delegate_exclude") or {})
        sub_extra = dict(extra.get("delegate_extra") or {})

        if llm is None or not roles:
            # 没运行在指挥家模式（例如 ds-free 单步链路）——明确引导，别假装成功
            return fail(
                "当前环境不支持委派子代理",
                "请直接用你自己的工具完成任务，或告诉用户这项能力当前不可用",
            )

        role_spec = roles.get(key)
        if role_spec is None:
            available = ", ".join(sorted(roles.keys()))
            return fail(
                f"没有名为 {key} 的子代理",
                f"可选子代理：{available}",
            )

        # 懒 import：避免模块级循环依赖（sub_agent 会 import loop，loop 又会 import 本模块）
        from app.services.ai.agent.sub_agent import run_sub_agent

        result = await run_sub_agent(
            ctx.db,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            role_spec=role_spec,
            task=task,
            llm=llm,
            excluded_tools=excludes.get(key),
            extra=sub_extra,
        )

        if not result.get("success"):
            return fail(
                f"子代理「{getattr(role_spec, 'name', key)}」执行失败：{result.get('error') or '未知错误'}",
                "请改用你自己的工具完成任务，或换一种方式",
            )

        return ok(
            subAgent=key,
            subAgentName=getattr(role_spec, "name", key),
            result=result.get("text") or "",
            steps=result.get("steps") or [],
        )


__all__ = ["DelegateTaskTool"]
