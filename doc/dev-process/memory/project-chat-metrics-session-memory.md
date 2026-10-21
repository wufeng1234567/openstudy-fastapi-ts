---
name: 聊天底部状态条 metrics 刷新丢失需加会话记忆
description: 2026-10-10 用户报 bug——底部状态条（多少轮/多少步/llm毫秒）刷新页面后丢失，需给 metrics 加会话持久化记忆
type: project
from: Agent
---

2026-10-10 用户报 bug：智能体聊天页底部状态条显示的 **「多少轮 / 多少步 / llm 多少毫秒」刷新页面后再次进入对应会话就看不见了**，要求添加**会话记忆功能**（持久化 metrics）。

**根因（已排查确认）：** 底部状态条消费的是 `metrics` 事件，而 metrics 是**每轮**数据、由**前端累加**成会话总量（后端注释第 25 行明确写"前端负责把它累加成会话总量"）。刷新后从会话历史复原时没有 metrics 数据——因为落库链路不回存 metrics：
- `save_message`/`save_turn` 只存 role/content/attachments/turn_id，**没有 metrics 字段**。
- `AiChatMessage` 模型同样无 metrics 字段。
- 但 `AiAgentTimeline` 存的是**前端整条消息流 JSON 快照**——它**本可以包含 metrics**，只要前端把 metrics 一并写进该快照、复原时读回即可。

**Why:** 用户实际会遇到"刷新即丢统计"的体验，属于需要持久化的会话级数据，而非一次性渲染数据。

**How to apply:** 修复方向已定案——**timeline 快照里额外加一个 `metrics` 字段**（会话累计）：前端保存时写入、加载时读回并投影到 `metrics`。这是最干净的方案，**零 DB 迁移**（`AiAgentTimeline.payload` 是 JSON）。而非改造 `save_message`/`save_turn` 落库结构。

**链路已确认（2026-10-10 排查）：**
- 前端 `chat.vue` 的 `loadHistory`（约 775 行）**优先**用 `getAgentTimeline(sid, userId)` 的 `tl.data.messages` 复原完整时间线（含工具卡片），为空才回退 `getConversationHistory`；所以 metrics 只要进 timeline 快照即可随 `messages` 一并读回。
- 存 metrics 的**天然位置**就是 timeline 写入点（`body.messages` / `save_agent_timeline` 服务），无需动 `AiChatMessage`。
- 落库链路（`saveConversationMessages`，chat.vue 约 920 行；`save_message`/`save_turn`）只存 role/content/attachments/turn/turnId，无 metrics 字段；`AiChatMessage` 亦无 metrics 字段。
- 相关改动面：前端 `useAgentChat`（metrics 累加 + timeline 快照构造）、`chat.vue` 的 `loadHistory` 与保存处、后端 timeline 写接口/`save_agent_timeline`。排查线索="metrics 的产出→消费→历史复原链路"。

**实施细节（2026-10-10 定案）：**
- **timeline payload 由数组改对象**：原 payload 是纯数组 `[msg...]`，新格式 `{messages: [...], metrics: {...}}`；**读取端必须兼容旧数组格式**（旧会话无 metrics → 退回全 0，与现状一致，不倒退）。
- 改动清单（后端 2 处 + 前端 4 处）：① 后端 `AgentTimelineBody` 加 `metrics`；`save_agent_timeline` 存 `{messages, metrics}`；`get_agent_timeline` 返回 `{messages, metrics}`（兼容旧数组）。② 后端路由读写放行 `metrics`。③ 前端 `ai.ts` 的 `saveAgentTimeline` 加 `metrics` 参数、`getAgentTimeline` 返回兼容。④ `useAgentChat` 的 `send`/`rollback` 保存时带 metrics，新增 expose `restoreMetrics`。⑤ `chat.vue` 的 `loadHistory` 读回 metrics 并投影到 metrics ref。
- 前端 timeline 写入点：`saveAgentTimeline(sessionId, slimTimeline(messages.value), userId)`；`slimTimeline` 负责快照瘦身。
- 数据流：发送轮次 → `useAgentChat` 累加 `sessionAgg` → metrics → 保存时随 timeline 快照持久化 → 刷新后 `getAgentTimeline` 读回 metrics → 投影到 metrics ref。

**实施进展（2026-10-10，后端已改、前端部分已完成）：**
- 后端已改：`AgentTimelineBody` 加 `metrics`（ai.py）；`save_agent_timeline` 存 `{messages, metrics}`、`get_agent_timeline` 返回 `{messages, metrics}` 并兼容旧数组（conversation_service.py，文件已 import `Optional`）；`save_agent_timeline_route` 传 metrics、`get_agent_timeline_route` 由 `success({"messages": messages})` 改为返回 `{"messages":..., "metrics":...}`。
- 前端已改：`ai.ts` 的 `saveAgentTimeline` 加 `metrics` 参数、`getAgentTimeline` 返回兼容；`useAgentChat` 的 `send`/`rollback` 保存时带 metrics，新增 expose `restoreMetrics`。
- **待办/风险**：`get_agent_timeline` 返回类型由 list 变 dict（`{messages, metrics}`）——须排查是否有其他调用方消费旧结构；也须检查 `save_agent_timeline` 是否存在其他调用（如 delete/清理流程）会受影响。

**风险已解除（2026-10-10）：** 排查确认 `get_agent_timeline`/`save_agent_timeline` 均**只有路由一个调用点**（无其他消费方，如 delete/清理流程未受影响），后端改动编译通过。

**前端实施细节（2026-10-10）：**
- `useAgentChat`：把 `sessionAgg` 暴露为可读快照 `getMetricsSnapshot()`；保存 timeline 两处（`send` 的 finally、`rollback`）带 metrics 快照；新增 `restoreMetrics(agg)` 供历史加载还原。`getMetricsSnapshot` 定义在 composable 的 setup 作用域，`send` 为同作用域内部函数可直接访问。
- `ai.ts`：`saveAgentTimeline` 增加 `metrics` 参数（第 4 参），`getAgentTimeline` 类型兼容。
- `chat.vue` 的 `loadHistory` 读回 metrics 并投影到 metrics ref。
- **回退(rollback)语义（2026-10-10）**：回退后 metrics **不因摘掉消息而变**（metrics 是执行统计、与会话消息无关），但**保存时必须带上当前 metrics 快照**，否则回退会用不含 metrics 的新 payload 把 timeline 里既有的 metrics 抹掉。即"metrics 不随消息增减、但保存时须一并回写"。
- **新会话/切换会话边界**：老会话无 metrics 时（`tl.data.metrics` 缺失），`loadHistory` 后须显式 restore 归零；`reset()` 已清 metrics，但仅靠 reset 不够，loadHistory 场景要显式还原。

**已完成并验证（2026-10-10）：**
- 改动文件：后端 `ai.py`、`conversation_service.py`；前端 `ai.ts`、`useAgentChat.ts`、`chat.vue`；新增探针 `tests/_probe_timeline_metrics.py`。
- 端到端验证：新探针 `_probe_timeline_metrics.py` **10/10 全绿**——① 存带 metrics → 读回 metrics；② 存旧数组格式 → 读回 metrics=None + messages（向后兼容成立）。
- 回归：`_toolpref_probe` 32/32 全绿、`app.main` 导入 APP_OK。
- 新会话语义再确认：`newSession` 调 `reset()`（清 metrics，无历史不调 loadHistory，正确）；`switchSession` 调 `reset()` 再 `loadHistory`（restore 已覆盖 switch）。
- 前端校验方式（esbuild 已禁用）：`@vue/compiler-sfc` 校验 .vue + `tsc` 校验 .ts，三个前端文件全过。

**⚠️ 已被推翻（2026-10-10）：** 本持久化修复方向已被用户**定案废弃**——用户决定**直接去掉聊天页底部状态条**（学习产品非开发工具，token 耗时是噪音，需求本身不成立）。详见 feedback-chat-status-bar-removed.md。后端 timeline `{messages, metrics}` 接口改动与 `_probe_timeline_metrics.py` 探针仍在，但前端 metrics 消费/展示已移除。后续不要在此基础上继续投入。

**最终处置（2026-10-10，已提交推送）：** 尽管状态条 UI 已删、metrics 前端不再有界面消费，本轮仍决定**保留并提交 metrics 会话持久化后端能力**，理由是：① 后端能力保留（未来可能回来）；② 删状态条前用户先报了 metrics 丢失 bug，两者同批处理；③ 已完成的代码不浪费。同时确保「删状态条」是本提交主体。最终连同 loop.py 并行优化一起，作为同一提交推至 GitCode main（`6c6a2bc`）。
