---
name: 智能体上传文档解析过程可视化（深度思考栏实时展示内部处理流程）
description: 2026-10-11 用户新需求——智能体解析用户上传的 Word 等文档时，深度思考栏不该只转圈，应实时展示内部处理流程（如"正在提取图片"/"正在解析公式"等阶段）
type: project
from: Agent
---

**2026-10-11 用户新需求（原话）**：「接下来要做智能体上传文档完整解析过程的优化。目前智能体在用户上传 word 之类的文档后，只能老老实实等待深度思考，这个深度思考就一直转圈。我需要那种体现内部函数处理流程的过程体现出来，比如 xx 在干嘛、图片提取之类的输出到深度思考那一栏那边，实时变化，这样用户等待体验更好。或者你有什么更好的方案说出来，仔细思考一下我说的」

**需求要点：**
- **痛点**：用户上传 Word 等文档后，智能体做文档解析/深度思考期间，前端深度思考栏**只是个一直转圈的等待态**，无信息量。
- **诉求**：把**内部处理流程的阶段性进展**（如"正在提取图片""正在解析公式""正在解析表格"等）**实时输出到"深度思考"那一栏**，随处理阶段变化。
- **目标**：改善用户等待体验（让等待有信息量、可感知进度）。
- **用户开放**：也欢迎 Agent 提出更好的替代方案（不局限于原设想）。

**Why:** 这是"文档自动变题库/多模态文档解析"体验链路的收尾优化（与 `project-word-image-extraction-to-questionbank` / `project-formula-table-rendering-in-questionbank` 同族）；用户日常真实使用中踩到"上传文档后只能干等转圈"。

**How to apply:**
- 用户本轮明确要求**先"仔细思考"、先梳理现状、先不写代码**（延续其「先读代码核实现状、先梳理不写码」的固定习惯）。Agent 已开始摸底：**需先确认后端在文档处理期间发了哪些 SSE 事件、前端是否有展示位**，再谈方案。
- **⚠️ 与既有决策的潜在张力（须留意）**：`project-deep-thinking-remove-reasoning-show-waiting-animation` 记录了 2026-10-11 早前的定案——**深度思考不暴露思维链内容、不再流式输出思考数据（"不输出流式输出数据了"）**。本新需求是"在深度思考栏展示**内部函数处理流程的阶段进展**"——**须与用户澄清这属"进度/阶段提示"（可展示）而非"思维链内容"（不展示）**，两者边界务必对齐，勿把被推翻的"思维链流式可见"方向重新引入；实现时应走"阶段化进度/步骤提示"而非"暴露推理正文"。

## 2026-10-11 现状摸底结论（Agent 已核实 loop.py）

已存在 `waiting` 事件（`loop.py` 约 1587/1660 发出）与 `meta` 事件（约 983 发出），前端 `useAgentChat.ts` 约 938 行**已有 `waiting` 消费**（即当前那个"转圈等待"占位）——**展示位现成，只缺有信息量的内容**。

**`loop.py` 实际时序**：附件 base64 上传 → `_collect_attachments`（同步阻塞：`parse_file` 提文本/图片/公式，**无任何事件**）→ `persist_agent_images`（图片落盘）→ `yield meta`（工具/模型/warnings）→ 每轮 `yield waiting`（抽象文案）→ LLM 流式 thinking/text。

**关键缺口：**
1. **`_collect_attachments` 完全静默**——这是"上传 Word 后干等"的主要时间来源（老 `.doc` 还要调 Word COM 转换 1~3 秒）；且 `meta` 事件在其**之后**才发（约 981 行），故**文档解析阶段根本没有事件可发**。
2. `waiting` 事件**只有抽象文案**（如"正在理解你的需求…"），无过程细节。
3. 前端 `waiting` 已有渲染位（`showPlaceholder` → `LoadingDots` 转圈），**位置现成、只缺内容**。

**⚠️ 硬技术前提（决定方案可行性）：** `_collect_attachments` 是 `asyncio.to_thread` 跑的**同步函数**——**执行期间无法 `yield` 事件**（事件只能由 async 生成器 yield）。故"解析中"要发事件，必须给 `file_parser` 加**进度回调**；否则只能在"解析前/解析后"两头发事件。

## 2026-10-11 待用户拍板的三方案（Agent 已给出，未开工）

1. **方案 A（最小）**：纯前端——用户点发送即先显示"📄 正在解析文档…"静态提示。**缺点=假进度**（不知后端真实状态）。
2. **方案 B（最理想但大）**：把 `_collect_attachments` 拆成带进度回调的异步步骤，逐步 `yield progress`；需**改 `file_parser` 加回调**（`file_parser.parse_file` 内是一次性返回，不逐步回调）。
3. **方案 C（Agent 推荐）**：**阶段事件 + 前端"处理清单"动画**。后端在**关键节点**各插一条 `progress` 事件（只用 `loop.py` 的现成节点 `yield`，**不碰 `file_parser` 内部**），如「📄 正在解析文档（共 N 个文件）」→「✅ 已提取文本 X 字、图片 Y 张」→「🖼 正在保存图片…」→（复用现有 `waiting`）「🤔 正在思考…」；前端把 `waiting` 占位从"单纯转圈"升级为**逐步追加的"处理步骤清单"**（像 ChatGPT 的 thinking steps，完成的打勾、当前的高亮/转圈）。C 的落地形态 = 把"解析"拆成「发事件 → await to_thread(解析) → 发事件」**三段**（事件在解析前后发、解析中不打扰）。

**待用户定两点：** ① 做到什么程度（A/B/C）；② 进度粒度——只做"文档处理段"（解析/提图/落盘），还是把后续"生成题目/建库"的工具调用阶段也纳入（后者可与现有 `tool_start/tool_result` 事件串成完整时间线）。

**P11d 边界（Agent 已判）**：`progress` 事件的 `message` 字段是**进前端 UI 展示**的（非模型侧 description/系统提示词），**不受 P11d 约束、可以中文**——但若要确认其归属须落在前端渲染路径而非喂模型路径。

## 2026-10-11 定案：用户选「方案 C」且范围=只覆盖「文档处理段」（已开工）

- **用户拍板原话：「按 C 做、覆盖文档处理段」**——即采纳 Agent 推荐的方案 C，**范围锁定在"文档处理段"**（解析/提图/落盘），**不含**后续"生成题目/建库"工具调用阶段的进度（那部分不加进度事件）。
- **落地形态（三段式，事件在前后发、解析中不打扰）**：① 解析前 `req.files` 非空 → `yield progress("📄 正在解析文档（共 N 个文件）…")`；② 解析后拿到 `file_text/doc_images` → `yield progress("✅ 已提取文本、图片 X 张")`；③ 落盘时 → `yield progress("🖼 正在保存图片…")` / 完成后 `"图片已保存"`。
- **前端**：`useAgentChat.ts` 新增 `progress` 事件消费，把 `waiting` 占位**升级为步骤清单**（完成的打勾、当前的高亮）。
- **前端 `progress` 事件类型的落点=** `openstudy-vue3-ts\src\api\ai\agent.ts`——需在 `AgentEventType` 枚举**加 `progress`**，并在 `AgentEvent` 接口**加可选字段**承载进度文案。
- **How to apply：** 后续实现继续本需求时，直接按上述三段式改 `loop.py`、按步骤清单改前端；**勿把范围扩到"生成题目/建库"阶段**（用户只批了文档处理段），也勿改 `file_parser` 内部（方案 C 的前提）。

## 2026-10-11 实施进度（已开始改码）

方案 C 已进入编码落地，按"前端类型 → 后端事件 → 编译"顺序推进：
1. **前端**：`openstudy-vue3-ts\src\api\ai\agent.ts` 的 `card`（`AgentEvent` 接口）在 `AgentEventType` 枚举后（约第 175 行后）**新增 `progress` 字段**承载进度文案。
2. **后端 `openstudy-fastapi\app\services\ai\agent\loop.py`**（方案 C 前提=只动 `loop.py`、不碰 `file_parser`）：
   - 约 871-877 段：在文件解析之前插 `yield progress("正在解析文档（含文件数）…")`；
   - 约 886 段：在 `persist_agent_images`（图片落盘）前后各插一条 `progress`（"正在保存图片…"/完成）事件。
3. **收尾**：`py_compile` 编译后端验证。

**How to apply：** 后续续做时先核实前端 `agent.ts` 的 `progress` 枚举/字段与后端 `loop.py` 事件名是否对齐；`useAgentChat.ts` 的 `progress` 消费若尚未加，须补上步骤清单渲染（完成的打勾、当前高亮）。

## 2026-10-11 实施进度（后端已编译通过，转前端 `useAgentChat.ts`）

- **后端已 `py_compile` 通过**，进入前端消费环节。
- **前端步骤清单数据结构（定案，最简不破坏现有架构）**：**新增消息类型 `progress`——一条消息承载整个步骤列表 `steps`**（而非一个步骤一条消息）；每次收到 `progress` 事件更新该消息内对应步骤。落点在 `openstudy-vue3-ts\src\composables\useAgentChat.ts`。
- **`AgentChatMessage` 加 `type: 'progress'`**（消息类型枚举）**+ `steps` 字段**（加在 `experts` 字段之后，位置约原文件 143-195 行的类型定义处）。`AgentChatMessage` 类型定义约在 143-195 行；`showPlaceholder`/`clearPlaceholder` 约在 693 行起（现有"转圈等待"占位逻辑，本需求把它升级为步骤清单）。
- **新增接口 `AgentProgressStep`**（`AgentChatMessage` 定义之前或附近），与既有 `AgentExpertProgress` 接口同族（后者定义在同一文件，可参照其风格）。
- **How to apply：** 后续续做前端时，`progress` 消息的 `steps` 更新逻辑应复用/参照 `experts` 卡片的"定位最近一条消息回填"思路；`AgentProgressStep` 的字段须能表达"待办/进行中/已完成"三态以支持打勾+当前高亮。

## 2026-10-11 前端消费逻辑落地（Agent 已在 `useAgentChat.ts` 完成编写）

- **类型层**：在既有 `AgentExpertProgress` 接口之后新增 `AgentProgressStep`；`AgentChatMessage` 在 `experts` 字段后加 `steps` 字段。
- **消费层（`handleEvent`）**：在 `case 'waiting'` 分支附近新增 `case 'progress'` 分支；`waiting` 分支处（原文件约 938 行）同步处理。
- **辅助函数**：在 `showPlaceholder` 之后新增 `upsertProgressStep`（按 step 去重/回填三态）与 `closeProgress`。
- **收口点**：在所有关键收口点（reasoning/tool 结束/本轮结束等）调用 `closeProgress()`，确保步骤清单在流程结束时整体置为完成态。

## 2026-10-11 `closeProgress()` 收口点定案（Agent 已核 `useAgentChat.ts`）

- **两个必须调用 `closeProgress()` 的收口点**：① **正文 `text` 到达（开始出答案）时**——处理阶段即告结束，`closeProgress()` 落在 `case 'text'` 分支的 `appendText` 里（正文开始=处理阶段结束）；② **轮末 `turn_end`**——落在 `send` 的 `finally`（`turn_end` push 之前，约 788 行附近；`turn_end` 相关处约 919 行）。
- **语义**：正文开始或本轮结束，都意味着"文档处理段"进度已走完，步骤清单应整体收口为完成态。
- **How to apply：** 续做时按这两点核对 `closeProgress()` 是否到位；改这段时以"正文开始/轮末"为收口判据，勿在解析中途提前收口。

## 2026-10-11 渲染层落地（Agent 正在改 `AiChatStream/index.vue`）

- **新增渲染点定案**：`AiChatStream/index.vue` 的 `card` **在既有 `thinking` 分支之前**插入新的 `progress` 分支，渲染"进度清单"（步骤列表）；`useAgentChat.ts` 另需在 `dropSoloExpertCard()` 之前补 `closeProgress()`（确保丢弃单专家卡片时同步收口进度）。
- **渲染顺序**：`progress` 分支置于 `thinking` 分支前——即进度清单显示在深度思考等待动画上方。
- **How to apply：** 续做渲染层时，先看 `AiChatStream` 的 `thinking` 分支附近再加 `progress` 分支；`closeProgress()` 的调用点除"正文开始/轮末"外，还须在 `dropSoloExpertCard()` 前补一处。

## 2026-10-11 样式落地 + 三文件校验通过（Agent 进度）

- **样式落地**：进度清单样式（`.progress-steps`）追加在 `AiChatStream/index.vue` 的 `card` 样式区**约 833 行之后**（`card` 样式块附近）。
- **前端校验已通过**：本轮 3 个前端文件逐文件跑 `_v.cjs` **全部通过**——`src/api/ai/agent.ts`、`src/composables/useAgentChat.ts`、`AiChatStream/index.vue`；校验用的临时 `_v.cjs` 建在 `openstudy-vue3-ts\_v.cjs`。
- **下一步=后端回归**：跑「指挥家 + 多模态」探针，确认本轮（前端为主）改动未破坏后端探针（对应 `tests/_probe_conductor.py` 与 `tests/_probe_multimodal_doc_images.py`）。
- **How to apply：** 续做完收尾时，确认样式类名 `.progress-steps` 落在 `AiChatStream` 的 `card` 样式区、且 progress 分支渲染的清单使用该类；改完前端 3 文件后按"逐文件 `_v.cjs`"校验，再跑后端探针回归。

## 2026-10-11 完成并已推送 `4a11da6`（方案 C 全链路闭环）

- **已推送完成**：提交 `4a11da6`，区间 `b772fc1..4a11da6 HEAD -> main`（hook PASSED），worktree 已清理。**共 5 文件（含新探针）**：后端 `loop.py`；前端 `api/ai/agent.ts`、`useAgentChat.ts`、`AiChatStream/index.vue`；新探针 `tests/_probe_progress_events.py`。
- **后端事件（`loop.py`）——"发事件→解析→发事件"三段式，不碰 `file_parser` 内部**，新增 `progress` 事件：
  - 解析**前**=`📄 正在解析文档（共 N 个文件）…`；
  - 解析**后**=`📄 文档解析完成（文本约 X 字、图片 Y 张）`；
  - 图片落盘**前**=`🖼 正在保存图片（共 N 张）…`；
  - 图片落盘**后**=`🖼 图片已保存（N 张）/ 图片保存失败`。
- **前端**：`agent.ts` 加 `progress` 事件类型 + `id`/`state`/`icon` 字段；`useAgentChat.ts` 新增 `AgentProgressStep`，`progress` 事件按 `id` 汇总进**同一条步骤清单消息**，正文开始/轮末自动**收口**（未完成步骤标 done、不永久转圈）；`AiChatStream/index.vue` 渲染步骤清单（进行中转圈⟳ / 完成✓ / 失败✕）+ 样式。
- **验证**：后端 `py_compile` 通过 + 新探针 `_probe_progress_events.py` **8/8 全绿**；前端 3 文件逐文件 `@vue/compiler-sfc` 校验通过；回归全绿（多模态文档图 18/18、指挥家 23/23、并行委派 20/20）。
- **边界（与既定一致）**：`progress` 是**进度提示、不含思维链**（与"不暴露思维链"定案一致）；**只覆盖 api 付费链路（后端循环）；ds-free 链路不改**（其循环在前端、无后端事件流）。
- **待用户实机验证**：需**重启后端 + 刷新前端**，上传 Word 验证步骤清单逐条推进。

## 2026-10-11 用户后续可选扩展方向（Agent 已提出，未开工）

1. **把工具调用阶段也纳入同一条清单**（如"🔍 正在检索知识库…""✍️ 正在生成题目…"）形成**完整时间线**——用户当时只选了"只覆盖文档处理段"，这块**随时可加**；
2. **真实百分比进度**——需给 `file_parser` 加进度回调，改动较大（即之前的**方案 B**）。

**How to apply：** 若用户后续要做"完整时间线"或"真实百分比"，按上述两条扩展；做时间线时把既有 `tool_start/tool_result` 事件与 `progress` 清单串起；做百分比则需回到方案 B（改 `file_parser` 加回调）。
