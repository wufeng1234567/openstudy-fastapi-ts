"""
Agent 工具注册表

对齐 springboot3 的 `AgentToolRegistry`：工具自己声明 name/description/schema，
注册表负责把它们变成模型能理解的两样东西：

1. `definitions()` → 原生 Function Calling 的 `tools` 参数
   （`[{"type":"function","function":{"name","description","parameters"}}]`）
2. `describe()` → 注入系统提示词的工具清单文本

**为什么要两套？** 官方 API 用 (1)；将来接 ds-free（网页端不能挂 tools 参数）
只能用 (2)，让模型在正文里吐 ```tool_call 块。两套描述来自**同一份声明**，
所以不会漂移 —— 这也是把工具定义收在 `AgentTool` 上的原因。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from app.services.ai.agent.base import AgentTool


class ToolRegistry:
    """工具注册表（进程内单例，见文件末尾的 `registry`）"""

    def __init__(self) -> None:
        self._tools: Dict[str, AgentTool] = {}

    # ------------------------------------------------------------------
    # 注册 / 查询
    # ------------------------------------------------------------------

    def register(self, tool: AgentTool) -> AgentTool:
        name = getattr(tool, "name", "") or ""
        if not name:
            raise ValueError(f"{type(tool).__name__} 缺少 name")
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def all(self) -> List[AgentTool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ------------------------------------------------------------------
    # 给模型的两套表达
    # ------------------------------------------------------------------

    def definitions(
        self, *, exclude: Optional[List[str]] = None
    ) -> List[Dict[str, object]]:
        """OpenAI Function Calling 格式的工具定义

        ⚠️ 只读**模型侧**的三个类属性（`name` / `description` / `parameters`）——
        它们的语言必须是英文。工具上的 `label` / `description_zh` 是**界面专用**的
        中文层，**永远不许在这里（或 `describe()` 里）被读到**：那两条道只会进
        系统提示词与 Function Calling 的 `tools` 参数，混进中文等于让模型面对
        两套语言约定。界面要它，走 `api/v1/ai.py: _agent_tools_payload` 挂在
        `function` **外面**的兄弟字段（`label` / `descriptionZh`）。
        守卫见 `tests/_toolpref_probe.py` 的 CJK 扫描。
        """
        blocked = set(exclude or [])
        tools: List[Dict[str, object]] = []
        for tool in self._tools.values():
            if tool.name in blocked:
                continue
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        return tools

    def describe(self, *, exclude: Optional[List[str]] = None) -> str:
        """工具清单文本（注入系统提示词的 `{{TOOLS}}` 占位）

        ⚠️ 输出全英文 —— 它会嵌进全英文的 Agent 系统提示词（见
        `prompts.AGENT_SYSTEM_PROMPT_TEMPLATE` 的 `{{TOOLS}}`）。因此工具的
        `description` 与参数 `description` 也必须写英文，两处语言必须一致。

        形如::

            - bank_manage: Manage question banks. ...
              action values: list / detail / create / update / delete / delete_by_name
        """
        blocked = set(exclude or [])
        lines: List[str] = []
        for tool in self._tools.values():
            if tool.name in blocked:
                continue
            lines.append(f"- {tool.name}: {tool.description}")
            enum_hint = self._enum_hint(tool)
            if enum_hint:
                lines.append(f"  {enum_hint}")
        return "\n".join(lines).strip()

    @staticmethod
    def _enum_hint(tool: AgentTool) -> str:
        """把 action 的枚举值拼成一行提示（模型最容易搞错的就是这个）"""
        schema = tool.parameters or {}
        action_schema = (schema.get("properties") or {}).get("action") or {}
        enum = action_schema.get("enum")
        if enum:
            return "action values: " + " / ".join(map(str, enum))

        # 没有 action 参数：列一下必填字段，避免模型漏参
        required = schema.get("required") or []
        if required:
            return "required: " + ", ".join(required)
        return ""


#: 全局注册表。工具在 `app.services.ai.agent.tools` 导入时注册进来。
registry = ToolRegistry()


def ensure_tools_loaded() -> ToolRegistry:
    """确保内置工具已注册（幂等；循环层与路由都先调一次）"""
    from app.services.ai.agent import tools as _tools  # noqa: F401  触发注册

    return registry


__all__ = ["ToolRegistry", "registry", "ensure_tools_loaded"]
