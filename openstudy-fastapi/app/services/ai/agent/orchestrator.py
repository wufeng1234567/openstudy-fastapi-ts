"""
Agent 编排层 —— 「本轮该用哪个官方角色」+「该把哪些工具排除掉」

这是「多智能体协同」的**轻量编排层**（不引入 LangGraph 等框架，理由见
`docs/fastapi_v2_多智能体协同方案.md` §3）。它只做两件事，都是**纯计算**：

1. `resolve_role(...)` —— 决定本轮用哪个官方角色（题库 / 笔记 / 知识库 / 记忆 / 统计 / 通用）。
2. `compute_exclude(...)` —— 把「角色工具白名单」换算成注册表要的 **exclude（黑名单）**，
   并与「用户级工具屏蔽集」求并。

⚠️ 路由**绝不用大模型空跑**
=========================
省 token 是这件事的初衷之一，若为了「判断该用谁」先打一次大模型，省下的又被花回去。
所以路由只做：**显式指定**（前端选了某角色）→ 命中则用；否则**关键词规则**；
再否则退 `general`（全工具）。全部零 LLM 成本。

⚠️ 路由不确定就退 `general`（全工具）
===================================
绝不能因为「没匹配上关键词」就让模型没有工具可用 —— 那比多花一点 token 严重得多
（参见 `roles.GENERAL_ROLE` 的注释）。所以本模块**永远返回一个有效角色**。

⚠️ 工具叠加语义（红线，别改）
============================
    最终可用工具 = 角色白名单 ∩ (全部工具 − 用户屏蔽集)

即：**用户级工具开关依然生效**，且只能进一步**收窄**，不能突破角色边界。
实现上就是把两部分的「排除名」**并集**起来交给注册表的 `exclude=`。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from app.services.ai.agent.roles import (
    DELEGATE_TOOL_NAME,
    GENERAL_ROLE,
    GLOBAL_TOOLS,
    OFFICIAL_ROLES,
    RoleSpec,
    role_or_none,
)


def _keyword_hits(message: str, role: RoleSpec) -> int:
    """这条消息命中该角色多少个关键词（0 = 没命中）。"""
    text = (message or "").strip().lower()
    if not text or not role.keywords:
        return 0
    return sum(1 for kw in role.keywords if kw and str(kw).lower() in text)


def resolve_role(
    *,
    role: str = "",
    message: str = "",
) -> RoleSpec:
    """解析本轮该用的官方角色（**永远返回有效角色**）

    优先级（从高到低）：
      1. **显式指定** `role`（前端选了角色 / 传了角色 key）—— 合法就直接用；非法则忽略继续往下。
      2. **关键词规则**：各角色（除 general）命中数最多者胜；命中数相同取
         `OFFICIAL_ROLES` 的声明顺序（先声明优先，稳定可测）。
      3. **兜底 `general`**（全工具）。

    Args:
        role: 前端显式指定的角色 key（可为空）。
        message: 用户本轮消息（用于关键词路由；可为空）。

    Returns:
        `RoleSpec`（绝不返回 None）。
    """
    # 1) 显式指定
    explicit = role_or_none(role)
    if explicit is not None:
        return explicit

    # 2) 关键词规则（跳过 general —— 它没有关键词，也不该抢命中）
    best: RoleSpec | None = None
    best_hits = 0
    for spec in OFFICIAL_ROLES.values():
        if spec.key == GENERAL_ROLE:
            continue
        hits = _keyword_hits(message, spec)
        # 严格大于才替换 → 平局保留先声明者（`OFFICIAL_ROLES` 的 dict 顺序稳定）
        if hits > best_hits:
            best, best_hits = spec, hits
    if best is not None:
        return best

    # 3) 兜底
    return OFFICIAL_ROLES[GENERAL_ROLE]


def compute_exclude(
    role: RoleSpec,
    *,
    all_tool_names: Iterable[str],
    user_disabled: Iterable[str] = (),
) -> Set[str]:
    """算出要交给 `registry.definitions/describe(exclude=...)` 的**排除集合**

    排除集 = (全部工具 − 有效白名单) ∪ 用户屏蔽集
             = 角色外工具 ∪ 用户屏蔽集

    其中「有效白名单 = 角色白名单 ∪ `GLOBAL_TOOLS`（全局默认工具）」。

    语义即「最终可用 = (角色白名单 ∪ 全局工具) ∩ (全部 − 用户屏蔽)」（见模块 docstring 红线）。
    全局工具（记忆）对所有角色始终可见 —— 见 `roles.GLOBAL_TOOLS` 的说明。

    Args:
        role: 已解析出的角色。
        all_tool_names: 注册表里**全部**工具名（`registry.names()`）。
        user_disabled: 用户级屏蔽的工具名集合（`tool_pref_service.disabled_tool_names`）。

    Returns:
        需要排除的工具名集合。

    ⚠️ `role.tools` 为空元组 = 该角色**不限制工具**（等价于白名单含全部）——
       这正是 `general` 的语义。此时「角色外工具」为空集，只剩用户屏蔽集生效。
    """
    all_names = {str(n) for n in all_tool_names}
    disabled = {str(n) for n in user_disabled}
    # `delegate_task` 是**指挥家专属元工具**，任何角色/子代理都不该拿到它
    # （防子代理递归委派）。永远纳入排除集；指挥家模式由 loop 单独挂上。
    meta_exclude = {DELEGATE_TOOL_NAME} if DELEGATE_TOOL_NAME in all_names else set()

    if not role.tools:
        # general / 不限工具：只有用户屏蔽 + 元工具排除生效
        # （全局工具本就在全部之内，无需叠加）
        return {n for n in (disabled | meta_exclude) if n in all_names}

    # 有效白名单 = 角色白名单 ∪ 全局默认工具（记忆等）—— 全局工具对所有角色可见
    allow = {str(n) for n in role.tools} | set(GLOBAL_TOOLS)
    outside_role = all_names - allow
    # 与用户屏蔽求并集后再收敛回「真实存在的工具名」——
    # 用户屏蔽集里可能有历史遗留的、已下线工具名，交给注册表 exclude 虽无害，
    # 但收敛掉能让返回值更干净、也便于探针断言。
    return {n for n in (outside_role | disabled | meta_exclude) if n in all_names}


def build_user_role(agent: Dict[str, Any]) -> RoleSpec:
    """把「用户自定义智能体」的记录转成一个 `RoleSpec`（供复用官方角色的工具裁剪机制）

    用户 Agent 与官方角色最终在编排层汇合：都归约成「一组工具白名单 + 一段系统指令」。
    用户 Agent 额外可绑模型 —— 但那由调用方（`loop.py`）读 `model` 字段处理，不进 RoleSpec
    （RoleSpec 只描述「工具 + 指令」这一层）。

    Args:
        agent: `agent_config_service.to_dict()` 的形状（camelCase）：
               `{agentId, name, personaPrompt, tools, model, ...}`。

    Returns:
        `RoleSpec`：
          · `key = "user:<agentId>"`（与官方角色 key 区分，`meta` 事件据此标注来源）；
          · `name` = 用户起的名字（**中文**，只给界面，不进提示词）；
          · `tools` = 用户的白名单（空 = 不限制）；
          · `prompt_fragment` = 用户人设（用户自由文本，会进系统提示词）。
    """
    raw_tools = agent.get("tools") or []
    tools = tuple(str(t) for t in raw_tools if str(t).strip())
    agent_id = agent.get("agentId")
    return RoleSpec(
        key=f"user:{agent_id}",
        name=str(agent.get("name") or "我的智能体"),
        description=str(agent.get("description") or ""),
        tools=tools,
        # 用户人设：非空才拼（避免空行）。前缀一句英文分隔，让模型知道这是「角色指令」。
        prompt_fragment=(
            f"## Role: {agent.get('name') or 'Custom Assistant'}\n"
            f"{str(agent.get('personaPrompt') or '').strip()}"
            if str(agent.get("personaPrompt") or "").strip()
            else ""
        ),
        keywords=(),
    )


__all__ = [
    "resolve_role",
    "compute_exclude",
    "build_user_role",
]
