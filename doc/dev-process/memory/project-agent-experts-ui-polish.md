---
name: 专家协同 UI 五项打磨与"结论恒无输出"真因
description: 2026-10-11 提交 9523688——单专家隐藏协同UI、间距、去md、中文化；"（无输出）"真因=delegate_done.summary 取了 message 而 delegate 成功返回的是 result
type: project
from: Agent
---

2026-10-11 用户提出 5 项多专家可视化的界面打磨需求，全部落地并推送 **`9523688`**（区间 `50c0331..9523688`，4 文件：后端 `loop.py` + 前端 `useAgentChat.ts`/`AgentToolResult`/`AgentToolDetail`）。

## 五项需求与落点（均已实现）
1. **单专家不显示「专家协同」UI**（多专家才点亮）：
   - `delegate_start` 逐条到达、不可即时判定，故**先照常建卡（进行中 1 行可见），轮末收敛**。
   - `useAgentChat.ts` 新增 `dropSoloExpertCard()`，在 `turn_end` push **之前**调用；本轮 experts 卡片 **≤1 行则整卡移除**。
   - **同时隐藏 `delegate_task` 的工具卡片**：`tool_start`/`tool_result` 对 `DELEGATE_TOOL_NAME` 不建卡（内部机制，不露"请专家帮忙/派发"痕迹）。新增前端常量 `DELEGATE_TOOL_NAME`（与后端 `roles.DELEGATE_TOOL_NAME` 逐字一致）。
2. **`subAgentName` 与值「碰在一起」**：真因=`AgentToolDetail` 键值行 `.td-key` 宽仅 **68px**，delegate 字段 `subAgent`/`subAgentName`/`result`/`steps` **无中文映射**→显示超宽英文键名→挤压右侧值。修复=补 `FIELD_LABELS` 短中文标签（专家/结论/执行步骤/任务）。**故需求 2 与需求 4 同源**。
3. **子代理输出去 markdown**：`useAgentChat.ts` 新增导出 `stripMarkdown()`，在 `pushExpertStart`（task）/`fillExpertDone`（summary）**源头清洗**（专家结论走 `{{ }}` 纯文本插值，清洗后不露 `*`/`#`）。
4. **delegate 文案中文化**：`AgentToolResult` 的 `TOOL_LABELS` 补 `delegate_task: '请专家帮忙'`、`ACTION_LABELS` 补 `delegate: '派发'`（兜底）。
5. **⚠️ 真 bug：专家结论恒显示「（无输出）」**：真因=`loop.py` 并发委派批次里 `message = res.get("message") or res.get("error")`，而 **`DelegateTaskTool` 成功时返回 `ok(subAgent, subAgentName, result, steps)`——没有 `message` 字段**，结论在 `result` 里 → `message` 恒空 → `delegate_done.summary` 恒空。修复=新增 `expert_summary = res.get("result") or res.get("message") or res.get("error")`，`delegate_done.summary` 改用它（上限 500）。
   **Why:** 这属"工具返回契约与事件消费口径不匹配"的经典坑——**新增工具返回字段时，要核对所有消费该 result 的地方（尤其 SSE 事件取值）是否覆盖了新字段**。

**How to apply:** 后续给 `delegate_task` 的返回加字段/改字段时，务必同步 `loop.py` 里 `delegate_done.summary`/`tool_result.message` 的取值链（当前口径：result → message → error）。改 `.td-key` 相关布局或新增长英文键名时，记得补 `AgentToolDetail` 的 `FIELD_LABELS`（否则会溢出相碰）。
