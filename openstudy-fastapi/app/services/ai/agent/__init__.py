"""
AI Agent 子系统（工具调用循环）

```
agent/
  base.py         工具契约（AgentTool / ToolContext / ok / fail）
  registry.py     工具注册表（同时产出 Function Calling 定义与提示词清单）
  guard.py        执行守卫：参数归一化 / 校验 / 死循环检测 / 结果压缩
  json_repair.py  模型输出 JSON 的清洗与修复（三级回退）
  loop.py         Agent 主循环 + 事件契约
  tools/          具体工具（bank_manage / question_manage …）
```

⚠️ 本文件**刻意只放说明、不 import 子模块**：`loop` 会 import `tools`，
`tools` 又会 import `base`，这里再反向 import 容易成环。需要什么直接
从具体模块导入（例如 `from app.services.ai.agent.loop import run_agent_stream`）。
"""
