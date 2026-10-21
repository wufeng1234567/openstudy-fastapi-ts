---
name: _probe_subagent_refusal.py 中文/英文无工具拒答正则（14/14）
description: 2026-10-11 无工具拒答检测正则三处漏识别修正——中文补「无法+动词」，「无法创建」等须命中；英文补 no tool available；探针同步扩到 14 条
type: project
from: Agent
---

2026-10-11 修正子代理「无工具可用」拒答检测正则，**同步探针 `tests\_probe_subagent_refusal.py` 从 12/12 扩到 14/14 全绿**。

**Why:** 原正则漏识别三类真实拒答措辞（探针先红后修）——
1. 中文只覆盖「无法执行」，漏掉「**无法创建**/无法完成/无法进行」等「无法+动词」句式（真实语料：「因此**无法创建**名为「cpp」的知识库」）。
2. 英文漏 `**no** **tool available**`（「There is no tool available」）。
3. 中文漏「**环境不支持**该操作」——原正则只有英文形态 `environment\s+does\s+not\s+support`。

**How to apply:** 修正口径 = 英文放宽 + 中文补「无法+动词」通用式；改动集中在 `openstudy-fastapi\app\services\ai\agent\sub_agent.py` 的 `_NO_TOOL_REFUSAL_PATTERNS`。该探针**纯同步、只做正则匹配**，是受阻沙箱下（asyncio 全挂）唯一能跑的无工具拒答验证入口（见 feedback-sandbox-blocks-asyncio-event-loop）。探针 import 的私有符号 = `_SUB_AGENT_BASE_RULES` 与 `_NO_TOOL_REFUSAL_PATTERNS`，改名会连带打断探针。
