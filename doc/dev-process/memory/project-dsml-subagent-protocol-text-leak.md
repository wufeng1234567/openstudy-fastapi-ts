---
name: 子代理吐 DSML 协议文本泄漏给用户（根因已定位）
description: 指挥家委派返回乱码的根因——DeepSeek 模型未走 Function Calling，把 tool_call 写成 DSML 文本，_run_sub_agent_inner 无处理
type: project
from: Agent
---

2026-10-11 用户报「指挥家委派子代理后，气泡里出现乱码」（形如 `＜｜｜DSML｜｜ calls＞＜｜｜DSML｜｜ invoke name="create_knowledge_base"＞...`）。

**真凶（Agent 读代码定位）：** 子代理（DeepSeek 某 model，经本地网关 magpie）**没走 Function Calling 通道**，而是把工具调用**写成了纯文本**（DSML = DeepSeek 自有的工具调用标记），导致 `ai.tool_calls` 为空 → `_run_sub_agent_inner` 走到 `if not tool_calls: return text` → 把**原始协议文本**当成"子代理最终产出"返回 → 指挥家又原样当 `delegate_task` 的 result 回报 → 用户看到乱码。

**Why:** 这与项目既有的 `discard_text` / `langchain_reasoning_patch` 机制相关——**主链路对"模型吐协议文本"有处理（`discard_text` 事件），但子代理的 `_run_sub_agent_inner` 没有**。这属 DeepSeek 模型行为差异：某些 model 会吐 DSML 文本而非结构化 tool_calls。

**关键排查结论（2026-10-11 本轮）：** **后端代码里没有任何 `discard_text` / DSML 处理**（grep `discard_text|DSML|dsml` 无命中）——说明后端从没处理过这种"模型吐协议文本"的情况。

**链路口径核实（2026-10-11 继续）：** `delegate.py` 取 `extra.get("delegate_llm")` 传给 `run_sub_agent`，子代理内 `llm.bind_tools(tool_defs)`。用户实际记录里**子代理确实"跑了"并返回了文本**，说明 `llm` 非 None、取键无误——**排除"取键错误 → llm=None"**这一假设。故根因确认=**模型行为**（子代理用**指挥家同一模型**、bind_tools 后仍吐文本形式工具调用，而非结构化 `tool_calls`）。

**成熟度对比（2026-10-11）：** 前端 ds-free 链路已有成熟做法可借鉴——`openstudy-vue3-ts\src\api\ai\agentDsFree.ts` 内有 `looksLikeToolCallAttempt` 检测 + `TOOL_CALL`/`FORMAT_FIX_LIMIT` 常量（探测"模型想调用工具却吐成文本"并回灌修复）。**后端完全缺失等价逻辑——这正是 bug 所在。**

**修复方案（3 项，待实施）：** ①**子代理协议文本兜底**（核心）：`_run_sub_agent_inner` 检测"模型吐的是工具调用协议文本"（含 `DSML`/`tool_calls`/`invoke name=` 等特征）→ 不当成最终产出，而是**回灌提示**让模型改用真实工具调用（或重试）——直接解决用户看到的乱码；②**前端 delegate 结果渲染**：`experts` 卡片"结论"若含协议文本不应原样显示（根子在①，前端可加兜底截断）；③**知识库/题库创建失败的真因**=子代理从没真正执行工具（吐的是文本掉进 `if not tool_calls: return text`），所以知识库/题库都没建成——**修好①即连带解决③**。

**修复 1 已实施（2026-10-11，已编译通过、未提交）：** 用户定案"回灌纠正 + 计数，超限则 `success=False` 带明确错误"。落地于 `onopenstudy-fastapi\app\services\ai\agent\sub_agent.py`：① 顶部 import `re`；② 新增 `format_fix_streak` 计数声明（须在循环外声明）；③ 把原 `if not tool_calls: return text`（约第 174-177 行）改为**先检测 text 是否为工具调用协议文本** → 是则**回灌纠正提示并 `continue`**（`format_fix_streak += 1`），超过 `FORMAT_FIX_LIMIT` 则 `return success=False` 并带明确错误信息。计数与前端 `agentDsFree.ts` 的 `FORMAT_FIX_LIMIT` 同口径。

**修复 2 经评估后跳过：** 原本想在 `delegate.py` 的 `ok(subAgent=..., result=...)` 对 result 做同样兜底，但**修复 1 已在子代理层保证 result 不含协议文本**，故 delegate 层不必重复。

**修复 3（前端体验，待办、根子在修复 1）：** 用户明确反馈「专家输出的内容 是带格式文本的不好看 需要优化掉 不能给用户看那些json格式或者特殊格式」——**指工具卡片里 `AgentToolResult` 组件展示的 `data`（`tool_result` 的 data）显示了原始 JSON**，需改造该组件如何展示 `data`（不原样展示 JSON/特殊格式）。同时 experts 卡片"结论"若含协议文本/JSON 也不应原样展示。

**2026-10-11 修复 3 排查修正（重要，勿再重复怀疑 AgentToolResult）：** 已读 `AgentToolDetail :data="data"`（`AgentToolResult` 的「查看详情」展开组件）——它实为**结构化渲染**（`td-row`/`td-chip`），**并非 `JSON.stringify` dump**，做得挺好。**故用户看到的"JSON/特殊格式"更可能是修复 1 要拦的那类"子代理返回的协议文本"（`<|DSML|>`/`{"tool":...}`）被当成专家"结论"显示在 `experts` 卡片的"它的结论"里——修复 1 已解决该根因**，前端不必把 `AgentToolDetail` 的 data 渲染去 JSON 化当作主线改造点。

**2026-10-11 收尾（修复 1 落地已校验，待提交）：**
- **`chat.vue` 残留 import 清理已完成**：`listAgentRoles` import 与 `AgentRoleMeta` 类型已确认无用（只剩 import、无使用）→ 均已删除。
- **前端校验口径**：本环境 esbuild 已禁用，用项目根 `openstudy-vue3-ts\_v.cjs`（基于 `@vue/compiler-sfc`+`typescript`）做 SFC/TS 单文件校验；该临时脚本已删则**重写一份再到用完删除**。
- **后端回归预期（尚未跑完）**：`sub_agent.py` 改动影响指挥家探针 `_probe_conductor.py`；其 `_probe_conductor` 用 fake LLM 测 `run_sub_agent`，**fake LLM 返回纯文本（如 `"Found 2 banks: A, B."`，不含 tool/action key，也不含协议特征）→ 不会触发新的协议检测 → 应仍 23/23 全绿**。此为设计中的"fake LLM 文本安全"前提：写回归用的假文本时**不得含 tool/action key 或 DSML 特征**，否则会撞上新协议检测分支。

**2026-10-11 修复 3 落地：协议检测单元探针 + 正则特征串修正（本轮，未提交）：**
- **探针落点=加进既有 `tests/_probe_parallel_delegate.py`**（用户定案"加进现有探针更集中"，不新建文件）：在 PD-08 之后追加协议检测断言 **PD-09~PD-12**，验证后端私有函数 `_looks_like_tool_protocol` 能识别 DSML/invoke/JSON 且不误伤正常文本。**探针内 import 下划线私有函数是可接受惯例**（同 `_collect_attachments` 先例）。
- **⚠️ 特征串关键陷阱（本轮踩坑，务必记住）：** `_looks_like_tool_protocol` 的正则以 **`[<＜]` … `[|｜]{0,2}\s*[>＞]`** 包裹 **`DSML`** 为判据——即要求 `DSML` 后**紧接着（可选 0~2 个竖线/全角竖线 + 空白）就是 `>`/`＞`**。**故：① 全角变体 `＜｜｜DSML｜｜`（全角尖括号/竖线）不是有效形态，会被漏判；② 中间夹内容的长串（如 `＜｜｜DSML｜｜ invoke name="..."＞`，`DSML` 后是 `｜｜ invoke name=` 而非直接 `>`）也不会命中。** 写探针/测试串时**必须用真实 DSML 形态**：`＜｜｜DSML｜｜＞`（紧随 `>`）或 `｜DSML｜`；**用户实际记录里是半角 `<｜｜DSML｜｜>` 形态**。
- **教训/How to apply：** 排此类"协议文本检测"bug 时，先核对正则对分隔符（全角/半角、间隔字符）的具体要求，再构造负/正样本串；否则会像本轮一样先得到 PD-09 假红（测试串不真实），而非被测逻辑真错。修复方向概述见下。

**2026-10-11 正则放宽定案（本轮首选方案二：`DSML` 作强特征直接命中）：**
- **背景**：原正则要求 `DSML` 后**紧接** `>`/`＞`，仍会漏掉用户实际记录里的 `＜｜｜DSML｜｜ calls＞＜｜｜DSML｜｜ invoke name="..."＞` 形态（全角 + `DSML` 后跟 `｜｜ calls` 而非 `>`）。
- **定案（方案二）**：把 **`DSML`（大小写不敏感）本身当作强特征直接命中**——理由：`DSML` 这个词在正常学习对话文本里几乎不会出现，误伤风险极低；**同时保留 `<invoke>`/`<parameter>` 形状特征**作为辅助判据。
- **安全前提验证**：PD-12 的"正常文本不误伤"用的是中文学习文本、不含 `DSML` → 放宽后仍安全。
- **实测结果**：单元探针 **12/12 全绿**；随后全量回归 **全部 8 个探针 `EXIT=0` 全绿**（`sub_agent.py`/`_probe_parallel_delegate.py`/`chat.vue` 相对 `gitcode/main` 均有差异、均已推送过）。
- **⚠️ 注意**：前端 `ds-free` 侧曾用严格式 `<|DSML|>`，但用户记录证明存在**全角变体**——故后端放宽为"命中 `DSML` 词"是刻意为之。

**2026-10-11 新立项（与本次修复并行，另一件事，勿混入本提交）：** 用户报「看不见深度思考的流式输出——深度思考只有输出完毕才能查看」。用户要求**与协议文本兜底 + 下拉框整合分开处理**：先提交当下这批修复（协议文本兜底 + 下拉框整合），**深度思考流式单独立项**（需查 `thinking`/`reasoning` 事件流）。

**2026-10-11 深度思考流式排查进展（本轮，已定位方向，未改动代码）：**
- **后端流式 thinking 是完整的**：`loop.py` 主循环约 **1177 行用 `astream`（真流式）**，**1180-1182 行逐 chunk 发 `thinking` SSE 事件**；即后端确有流式 thinking 输出，**排除"后端只 `ainvoke` 一次性返回"的假设**。
- **故问题收窄到两处：① 前端消费/渲染**（收到逐 chunk `thinking` 却未增量渲染，只等完毕才显示）；**② 模型侧不发 `reasoning_content`**（用户用的 DeepSeek 经本地网关 `magpie`，若某 model 不吐 `reasoning_content` → `astream` chunk 无思考内容 → 前端自然看不到流式）。
- **下一步待查**：`langchain_reasoning_patch`（`app/services/ai/agent/loop.py` 内）是否真把 `reasoning_content` 注入 `additional_kwargs`，以及 `_reasoning_of` 如何读取——用于判定"模型不发"还是"patch 未处理该 chunk 形态"。
- **与既有记忆关联**：此 bug 与 `project-chat-first-token-latency`（首 token 前停顿）同属"深度思考前端观感"类问题；deepseek 推理模型的思考态是该模型特性。

**2026-10-11 关联真 bug（专家卡片"它的结论"显示"（无输出）"）——已修复（工作区未提交）：** 用户报题库专家卡片里"交给它的任务"有内容、但"它的结论"显示"（无输出）"，且**每次**都如此。根因=后端 `loop.py` 的 `delegate_done` 事件 `summary` 取 `res.get("message")`，而 `DelegateTaskTool` 成功返回 `ok(subAgent=..., subAgentName=..., result=..., steps=...)` **没有 `message` 字段**（结论在 `result` 里）→ summary 恒为空 → 前端恒显"（无输出）"。**修复=summary 取 `result`**（仅 result 亦空时才显"（无输出）"，为合理兜底）。详见 `project-parallel-expert-delegation-design.md`。

**How to apply:** 修复方向=在子代理 `_run_sub_agent_inner` 补与前端 `agentDsFree.ts` 同口径的"协议文本检测/回灌"逻辑（检测到 DSML/伪工具调用文本 → 不当正文返回，回灌修正提示）。特征串可抄前端 `looksLikeToolCallAttempt`。修复 1 已按此落地（子代理层拦截+回灌+超限失败）。修复 3 的排查修正=前端 `AgentToolDetail` 是结构化渲染而非 JSON dump，用户看到的"特殊格式"实为修复 1 要拦的协议文本。后续排查"模型吐协议文本"问题时，注意**前端有检测、后端（主链路与子代理链路均）无**这一处理能力不一致的根因；如需真实复现，模型是 DeepSeek 且走本地网关 magpie（127.0.0.1:3425）。
