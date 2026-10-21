---
name: 沙箱间歇性禁止 asyncio 事件循环（socketpair 被拦）
description: 2026-10-11 本环境沙箱动态收紧后，任何 asyncio 事件循环都建不起来（socketpair OS 级被拦）；探针须退化为同步校验或改用 .env 主工作区；但同日稍后沙箱放宽已恢复
type: feedback
from: Agent
---

**在本环境（CodeArts CLI / Sandbox）跑 `asyncio` 事件循环**可能被拦——`socketpair` 被 OS 级拒绝，报错表现为「事件循环建不起来」，与代码无关。**此为间歇性：同日稍后沙箱放宽，asyncio 探针又恢复正常**（2026-10-11 晚复跑 `_probe_conductor` 得 23/23 全绿，其余探针亦全绿）。

**Why:** 2026-10-11 排查 `_probe_parallel_delegate.py` 时踩中：同一批 asyncio 探针（`_probe_conductor.py`、`_probe_subagent_tools.py`）**先前能跑通、当时全军覆没**。核实：
- 曾一度以为「该探针传 `db=None, own_session=True` 真开 DB 会话（asyncpg 需 socket）才被拦」；改用不连 DB 的 `_probe_subagent_tools.py` 复跑**同样失败**（连最小 `asyncio.get_event_loop()` 都起不来）→ 证明是**环境动态收紧**，非某个探针改动导致、也不是「连 DB vs 不连 DB」的差别。
- `WindowsSelectorEventLoopPolicy`、手动设 `_ssock`、`asyncio.Runner`、`nest_asyncio` 等变通均**无效**——socketpair 是 OS 层被拦，**任何事件循环都建不了**。
- **恢复证据（2026-10-11 晚）**：`_probe_conductor` 23/23、角色/config/toolpref/知识库入库/parallel_delegate 探针全部全绿 → 沙箱已放宽，asyncio 可用。**故这不是永久禁制，而是波动，遇错先重试再判定。**

**How to apply:**
- 判据：跑前先做「最小 asyncio 测试」确认当前是否允许；若不允许，**不要**再试各种 loop 策略浪费轮次，**先退化为同步/源码级校验，稍后重试**（环境会自行恢复）。
- 退化路径 1：把纯同步函数抽出来单测（如 `_looks_like_no_tool_refusal`/`_looks_like_tool_protocol` 是纯正则、可同步测）。
- 退化路径 2：async 端到端逻辑在收缴期跑不了 → 改**源码级断言**（检查关键常量/分支/引用是否存在）或回主工作区跑（依赖 DB 的探针须在含 `.env` 的主工作区；worktree 无 `.env` 跑不了）。
- 退化路径 3：本沙箱内做 prompts/系统提示词校验，最终宜走**源码级静态断言**（裸 import prompts 有重依赖/副作用，见 feedback-import-prompts-side-effects-in-sandbox）。
