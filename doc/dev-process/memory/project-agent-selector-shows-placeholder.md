---
name: 智能体选择页选择框首次进入显示「请选择」而非默认「自动」
description: 2026-10-10 用户报智能体选择框显示"请选择"；根因 Element Plus el-select 不认 value="" 的选项；已改用哨兵值 'auto'
type: project
from: Agent
---

2026-10-10 用户报 bug（工具清单顺序敏感 bug 根治并推送 `ee78533` 之后新报的第四个问题）：**「智能体选择页面」的智能体选择框（`selectedAgentKey` 对应的 `el-select`）最外面显示「请选择」，用户期望显示默认的「自动（按需求智能选择）」。**

**真因结论（2026-10-10 已定位）**：`chat.vue` 该 `el-select` 的「自动」选项写作 `<el-option label="自动（按需求智能选择）" value="" />`，`value` 是**空串 `''`**；而 **Element Plus `el-select` 把空串 value 视为「无选中」**（与 `undefined`/`null` 同等），因此**不会显示该 option 的 label，转而显示 placeholder**（该框未设 placeholder → 落到默认文案「请选择」）。

**关键对比**：这与 `61af866` 修的 `AiModelSelector` 是**同一类空值陷阱**，但两者的"用 placeholder 兜底"修法不同——`AiModelSelector` 是加了 `placeholder="自动（跟随默认）"` 才修好；本处 `chat.vue` 智能体框**没设 placeholder**，故显示默认「请选择」。**结论：`value=""` 的 option 在 Element Plus el-select 里不会被选中显示。**

**修复方案（已选 B，2026-10-10 已落地并走 worktree 提交推送，`_v.cjs` 校验通过）**：
- **A（最小改动）**：加 placeholder（与 `AiModelSelector` 一致）。
- **B（更正确，已采用）**：用**非空哨兵值** `'auto'`（常量 `AUTO_AGENT_KEY`）代表"自动"，彻底避开空串陷阱，使 el-select 能真正选中并显示「自动（按需求智能选择）」。
- 采用 B 需同步改 **4 处**：① `selectedAgentKey` 初值 `''`→`'auto'`；② `<el-option>` 的 `value`；③ `removeAgent` 里的回落赋值 `''`→`AUTO_AGENT_KEY`；④ 对外解析（`selectedRole`/`selectedAgentId`）在 `'auto'` 时返回空/undefined，保持"自动"语义不变。

**Why:** 空值语义 = 跟随默认（自动按需求智能选择），但 Element Plus 把空串 value 当"无选中"，UI 就渲染成「请选择」，语义误导用户；且这是组件层行为，仅靠设默认值/placeholder 只是绕过，用非空哨兵值才是治本。
**How to apply:** 后续 el-select 若需要表示"自动/默认"选项，**避免把选项 value 设为空串**，改用非空哨兵值（如 `'auto'`）；涉及智能体（`selectedAgentKey`）选择框时勿与 `61af866`/`AiModelSelector` 模型框混淆——两者虽同为空值语义问题，但修法不同（模型框用 placeholder 兜底，智能体框改用哨兵值）。
