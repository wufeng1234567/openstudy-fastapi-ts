"""
`agent_manage` —— 智能体（用户自定义助手）管理工具

产品口径（用户 2026-10-12）：用户在智能体页面对话里说「帮我建一个数学老师」，
由「智能体专家」这个角色调用本工具**按对话创建智能体**（名称 / 人设 / 工具白名单 / 模型）。

本工具只是把 `agent_config_service` 的能力暴露给模型，不自己写库：
- 服务层自己开数据库会话（见其模块 docstring），因此这里**不要**动 `ctx.db`
  （`_execute_tool` 对 write_operation 工具开的 SAVEPOINT 不影响它自己的会话）。
- 名字冲突 / 超额度等业务错误由服务层抛 `AgentConfigError`，这里转成 `fail()` 回灌模型。

两条语言道（见 `base.AgentTool` 说明）：`description` / `parameters` 英文（模型侧），
`label` / `description_zh` 中文（界面侧）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.ai.agent.base import (
    OP_RESTORE,
    OP_SOFT_DELETE,
    REASON_MISSING_TARGET_ID,
    AgentTool,
    ToolContext,
    fail,
    ok,
)
from app.services.ai.agent import agent_config_service as svc
from app.services.ai.agent.registry import ensure_tools_loaded, registry

#: 需要二次确认（会真正落库）的动作
_WRITE_ACTIONS = {"create", "update", "delete"}


def _to_int(value: Any) -> "int | None":
    """把「可能是字符串的 id」转成 int；转不动返回 None（**绝不抛**）

    ⚠️ `undo_plan` 里不能抛异常：`record_op` 会兜住，但兜住的结果是「当作没声明」，
    于是该可回退的操作静默变成不可回退 —— 用户点回退会看到「这一轮没有可回退的操作」，
    而实际上是他刚删的智能体没被记账。
    """
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_tool_names() -> set:
    """当前注册表里合法的工具名（用于校验模型传来的 tools 白名单）。

    ⚠️ 必须校验：模型可能编出 `web_search` 这类不存在的工具名，存进白名单后
    该智能体运行时那些名字既不会报错也不会生效（静默失效），用户以为配好了其实没有。
    与 API 层 `ai.py:_validate_agent_tools` 同一口径。
    """
    ensure_tools_loaded()
    return set(registry.names())


class AgentManageTool(AgentTool):
    name = "agent_manage"
    #: ⚠️ 描述与参数说明一律英文（进系统提示词 `{{TOOLS}}` 与 Function Calling）
    description = (
        "Create and manage the user's OWN custom assistants (also called agents / "
        "personas). Use it when the user wants to build, design or set up a new "
        "assistant ('make me a math-teacher assistant', 'create an assistant that only "
        "helps with notes'), tweak an existing one, delete one, or list their existing "
        "assistants. "
        "action values: "
        "create=create ONE new assistant (requires `name`; optional `persona_prompt` = "
        "the English system instruction that defines its behaviour, `description` = a "
        "one-line intro shown in the picker, `greeting` = its opening line, `tools` = an "
        "array of tool names it may use (omit / empty = it may use ALL tools), `model` = "
        "an optional model name it is bound to), "
        "update=change an existing assistant (pass `agent_id` plus the fields to change), "
        "delete=remove an assistant (pass `agent_id`), "
        "list=list the user's existing assistants. "
        "TIP: when the user is vague, ASK for the name and what the assistant should do "
        "before calling create; write `persona_prompt` in English."
    )
    #: 界面专用（只给前端看；不进 definitions() / describe()）
    label = "智能体管理"
    description_zh = (
        "创建 / 管理你的自定义智能体：create=新建（需 name，可选人设/工具/模型）、"
        "update=修改、delete=删除、list=列出。"
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Operation to perform",
                "enum": ["create", "update", "delete", "list"],
            },
            "agent_id": {
                "type": "integer",
                "description": "Target assistant id (required for update / delete).",
            },
            "name": {
                "type": "string",
                "description": "Assistant name (required for create; max 64 chars).",
            },
            "persona_prompt": {
                "type": "string",
                "description": (
                    "The assistant's system instruction / persona, in ENGLISH (max 4000 "
                    "chars). Defines who it is and what it does."
                ),
            },
            "description": {
                "type": "string",
                "description": "A one-line Chinese intro shown next to the assistant.",
            },
            "greeting": {
                "type": "string",
                "description": "The assistant's opening line when a chat starts.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Tool names this assistant may use (its whitelist). Omit or leave "
                    "empty to allow ALL tools."
                ),
            },
            "model": {
                "type": "string",
                "description": "Optional model name this assistant is bound to.",
            },
        },
        "required": ["action"],
    }
    write_operation = True

    def needs_confirmation(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") in _WRITE_ACTIONS

    def is_destructive(self, params: Dict[str, Any]) -> bool:
        return str(params.get("action") or "") == "delete"

    def confirm_policy(self, params: Dict[str, Any]) -> bool:
        """`create` 一次只建一个智能体（规模固定），不额外强制确认"""
        return False

    async def preview(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        """确认卡片上摊开「会创建 / 改 / 删什么」，而不是光秃秃一个 id。"""
        action = str(params.get("action") or "")
        try:
            if action == "create":
                return {
                    "action": "create",
                    "name": str(params.get("name") or "").strip(),
                    "description": str(params.get("description") or "").strip(),
                    "personaPrompt": str(params.get("persona_prompt") or "").strip(),
                    "tools": params.get("tools") or "全部工具",
                    "model": str(params.get("model") or "").strip() or "跟随默认",
                }
            if action == "delete":
                aid = int(params.get("agent_id") or 0)
                row = await svc.get_agent_dict(ctx.user_id, aid) if aid else None
                return {
                    "action": "delete",
                    "agentId": aid,
                    "name": (row or {}).get("name") or f"#{aid}",
                }
            if action == "update":
                aid = int(params.get("agent_id") or 0)
                row = await svc.get_agent_dict(ctx.user_id, aid) if aid else None
                return {
                    "action": "update",
                    "agentId": aid,
                    "name": (row or {}).get("name") or f"#{aid}",
                }
        except Exception:  # noqa: BLE001 - 预览失败不许抛，交给循环层兜底
            pass
        return {}

    async def execute(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        action = str(params.get("action") or "")
        if action == "create":
            return await self._create(params, ctx)
        if action == "update":
            return await self._update(params, ctx)
        if action == "delete":
            return await self._delete(params, ctx)
        if action == "list":
            return await self._list(params, ctx)
        return fail(f"未知操作: {action}", "action 只能是 create / update / delete / list")

    # ------------------------------------------------------------------
    # 动作实现
    # ------------------------------------------------------------------

    def _clean_tools(self, raw: Any) -> tuple:
        """归一 + 校验工具白名单；(clean, invalid) —— invalid 非空则拒绝整个请求。"""
        names: List[str] = []
        if isinstance(raw, str):
            candidates = [p.strip() for p in raw.replace("，", ",").split(",")]
        elif isinstance(raw, (list, tuple, set)):
            candidates = [str(p).strip() for p in raw]
        elif raw is None:
            candidates = []
        else:
            candidates = [str(raw).strip()]
        for n in candidates:
            if n and n not in names:
                names.append(n)
        if not names:
            return None, []  # 空 = 不限工具
        valid = _valid_tool_names()
        invalid = [n for n in names if n not in valid]
        return ([] if invalid else names), invalid

    async def _create(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        name = str(params.get("name") or "").strip()
        if not name:
            return fail("缺少智能体名称", "请先问用户想给这个智能体起什么名字（name），再创建")
        tools, invalid = self._clean_tools(params.get("tools"))
        if invalid:
            return fail(
                f"包含不存在的工具名：{', '.join(invalid)}",
                "请只用合法工具名（可先 list 一下你有哪些可用工具），或省略 tools 表示不限",
            )
        try:
            info = await svc.create_agent(
                ctx.user_id,
                name=name,
                persona_prompt=str(params.get("persona_prompt") or ""),
                description=str(params.get("description") or ""),
                greeting=str(params.get("greeting") or ""),
                tools=tools,
                model=(str(params.get("model") or "").strip() or None),
            )
        except svc.AgentConfigError as e:
            return fail(str(e), "换一个名字，或先删掉同名的旧智能体再创建")
        return ok(
            action="create",
            agent=info,
            message=f"已创建智能体「{info.get('name')}」（ID={info.get('agentId')}）",
        )

    async def _update(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        aid = int(params.get("agent_id") or 0)
        if aid <= 0:
            return fail("缺少 agent_id", "update 必须带 agent_id（可先 list 拿到）")
        tools, invalid = self._clean_tools(params.get("tools")) if params.get("tools") is not None else (None, [])
        if invalid:
            return fail(
                f"包含不存在的工具名：{', '.join(invalid)}",
                "请只用合法工具名，或省略 tools 表示不改动该项",
            )
        try:
            info = await svc.update_agent(
                ctx.user_id,
                aid,
                name=(str(params.get("name")).strip() or None) if params.get("name") is not None else None,
                persona_prompt=params.get("persona_prompt"),
                description=params.get("description"),
                greeting=params.get("greeting"),
                tools=tools,
                model=(str(params.get("model")).strip() or None) if params.get("model") is not None else None,
            )
        except svc.AgentConfigError as e:
            return fail(str(e), "检查名字是否与已有智能体冲突")
        if info is None:
            return fail("智能体不存在或不属于你", "先 list 确认 agent_id")
        return ok(action="update", agent=info, message=f"已更新智能体「{info.get('name')}」")

    async def _delete(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        aid = int(params.get("agent_id") or 0)
        if aid <= 0:
            return fail("缺少 agent_id", "delete 必须带 agent_id（可先 list 拿到）")
        # 回退要用「改前名字」写回执文案（删完之后再也查不到了）
        before_name = ""
        try:
            row = await svc.get_agent_dict(ctx.user_id, aid) if aid else None
            before_name = str((row or {}).get("name") or "")
        except Exception:  # noqa: BLE001 - 取不到名字不影响删除
            before_name = ""
        try:
            info = await svc.delete_agent(ctx.user_id, aid)
        except svc.AgentConfigError as e:
            return fail(str(e), "先 list 确认 agent_id")
        return ok(
            action="delete",
            agentId=aid,
            agentName=str(info.get("name") or before_name),
            message=f"已删除智能体「{info.get('name')}」",
        )

    # ------------------------------------------------------------------
    # 回退（2026-10-20 新增）
    # ------------------------------------------------------------------

    def undo_plan(self, params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any] | None:
        """声明这一笔智能体操作怎么撤（契约见 `base.AgentTool.undo_plan`）

        | action   | 逆操作                  | 为什么                        |
        |----------|-------------------------|-------------------------------|
        | create   | `soft_delete`            | 建错了就把它逻辑删掉           |
        | delete   | `restore`（`del_flag='0'`）| 本来就有 del_flag，翻回来即可  |
        | update   | **不可回退**             | 见下                           |

        ⚠️ **`update` 为什么不做**：`agent_config_service.update_agent` 只接受「要改成什么」，
        不接受「原来是什么」，而它的会话在服务层内部（本工具拿不到改前值）。
        要做就得改服务层签名 —— 而「改错了智能体人设」这件事的挽回成本极低
        （再改一次即可），不值得为它动一个被 API 路由共用的服务函数。
        按契约「宁可为空，绝不谎报」，这里返回 `None` 并由回退结果如实告知。

        ⚠️ `create` / `delete` 的 id 从回执里取：`agentId` 是回执本来就有的字段
        （给模型看的），不需要额外塞 `UNDO_BEFORE_KEY`。
        """
        action = str(params.get("action") or "")
        aid = _to_int(result.get("agentId")) or _to_int(params.get("agent_id"))
        if aid is None or aid <= 0:
            return {"undoable": False, "reason": REASON_MISSING_TARGET_ID}
        if action == "create":
            return {
                "op": OP_SOFT_DELETE,
                "targetTable": "ai_agent_config",
                "targetIds": [aid],
                "undoable": True,
            }
        if action == "delete":
            return {
                "op": OP_RESTORE,
                "targetTable": "ai_agent_config",
                "targetIds": [aid],
                "undoable": True,
            }
        return None

    async def _list(self, params: Dict[str, Any], ctx: ToolContext) -> Dict[str, Any]:
        agents = await svc.list_agents(ctx.user_id, include_disabled=True)
        return ok(action="list", count=len(agents), agents=agents)
