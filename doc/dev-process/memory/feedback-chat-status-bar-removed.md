---
name: 去掉智能体聊天页底部状态条
description: 2026-10-10 用户定案去掉聊天页底部状态条（轮/步/llm 毫秒），理由是学习产品非开发工具，token 耗时对用户是噪音
type: feedback
from: Agent
---

**智能体聊天页底部状态条（显示「多少轮 / 多少步 / llm 多少毫秒」的 API token 耗时统计）应整体去掉，不要为它做持久化。**

**Why:** 2026-10-10 用户明确指示："直接把这个底部工具栏去掉……因为我们这个不是用来写代码的系统，设置这个功能很多余，用户又不需要看他来统计什么 api 的 token 时间。"——即：本产品是**学习类应用而非开发者工具**，API token/耗时对终端用户是噪音，需求本身不成立。这直接推翻了此前"给 metrics 加会话持久化记忆"的修复方向（见 project-chat-metrics-session-memory.md）。

**How to apply:** 后续涉及聊天页底部状态条/统计类展示时，默认按**移除**处理，不要投入持久化/美化。判断"要不要保留某个统计/开发向功能"时，先对照产品定位——面向学习用户、非开发者，凡"只有开发者才看"的信息一律倾向删掉。此前那套 timeline metrics 持久化改动可能因此回退或废弃。

**实施方式（2026-10-10 定案并执行）：采取「最小改动」移除。** 删 `chat.vue` template 里的 `<footer>` 状态条，以及 script 中**仅 footer 使用**的 `formatMs`/`formatFirstToken` 两个函数；`restoreMetrics` 调用与 `useAgentChat` 契约**保留不动**。
**Why:** 用户目标只是隐藏界面展示，不必顺带清理数据流；动 composable 契约收益小风险大。
**How to apply:** 在此文件做同类"删 UI 元素"改动时，先用 grep 确认每个待删符号是否仅该处使用，然后只删"确定仅此元素使用"的部分，其余保留——避免大范围连带改动。

**解构清理（2026-10-10 补充，已执行）：** 删 footer 后**删掉了确定不再被模板/逻辑使用的解构** `imageCount, corrections, errors, metrics, hasRun`（`metrics` 仅供 footer 消费；`restoreMetrics` 是函数调用，不依赖解构的 `metrics`，故仍保留该调用）。**保留** `messages/isGenerating/tools/activeModel/metaWarnings/send/stop/reset/resolveConfirm/restoreMetrics/currentTurnId/rollbackStates/rollbackTurn`。
**Why:** 与"最小改动"策略一致——只删"确定无用"的解构；`activeModel`/`tools`/`metaWarnings` 等用途不确定的保守保留，避免删错。Vue script setup 中未使用的解构不报错（仅未用变量），无 lint 阻断构建。
**How to apply:** 删解构时逐个判定是否仅在已删元素（如 footer）处使用；不确定的一律保留。

**回归验证（2026-10-10）：** 前端改动后跑 `_toolpref_probe` **32/32 全绿**（它覆盖指挥家/角色链路的 `run_agent_stream` 真实链路，是最关键的回归）+ `app.main` 导入 **APP_OK**。`_probe_conductor` 测 `run_sub_agent` 内层循环，不涉本段改动故未重跑。
