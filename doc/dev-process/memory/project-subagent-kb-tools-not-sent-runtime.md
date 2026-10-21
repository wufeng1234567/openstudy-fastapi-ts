---
name: 子代理 kb 工具在真实链路未发出（运行时问题，非模型行为）
description: 2026-10-11 纠正「子代理瞎编」根因——用户走普通 API+Function Calling（非 ds-free），探针证明工具集逻辑正确，真凶在运行时真实链路未把 kb 工具发给子代理
type: project
from: Agent
---

2026-10-11 排查「子代理没有 kb 工具、被问就瞎编」问题，本轮把根因从「模型行为」纠正为「运行时链路」。

**链路定案（Agent 问、用户答）：** 用户实际走**普通 API + Function Calling 链路**，**不是** ds-free（网页反代）链路。依据：前端 `agentDsFree.ts` **没有实现 delegate 逻辑**，故所有「指挥家/子代理」行为都来自普通后端链路 `loop.run_agent_stream`。**Why:** 两种链路修复方案完全不同，盲目改会跑偏（此前 AgentReasoning 误判为前车之鉴）。

**探针证据 CD-19~22（关键）：** 用**假 LLM + 正确传 `excluded_tools`** 时，`run_sub_agent` 拿到的工具集是**对的**（kb 工具在列）。**故问题必在运行时真实链路**——真实链路里 `llm.bind_tools(tool_defs)` 是否真把 kb 工具发出去 / `tool_defs` 是否为空。

**候选假设（按可能性排序，未定案）：**
1. `bound_llm` 传递问题：`loop.py` 第 1069 行 `bound_llm = llm if tools_all_disabled else llm.bind_tools(tool_defs)`——指挥家 bind 的是**含 `delegate_task` 的全工具**；`delegate_llm` 传的是**原始 `llm`（未 bind）**，第 1095 行确认传 `llm` 而非 `bound_llm`（✓ 该点正确，已排除）。
2. `tool_defs` 为空：`_run_sub_agent_inner`（sub_agent.py 约 197-203）若 `excluded_tools is None` 就用 `user_disabled=set()` 重算；delegate.py 传 `excludes.get(key)` = `compute_exclude(kb, all_names, user_disabled=disabled_tools)`。若 `tool_defs` 为空，则 `bound = llm if not tool_defs else llm.bind_tools(...)` 走**裸 `llm` 调用（无工具）**→ 模型瞎编"我没有工具"。
3. 并行委派 `asyncio.gather` 下 registry 未就绪（候选：`ensure_tools_loaded()` 时序）。注：`ChatOpenAI.bind_tools()` 返回 RunnableBinding 不改原对象，**并发 bind 本身安全**（已排除）。

**已排除：** `llm=None`（子代理确实跑了）、取键错误、并发 bind 竞态、`bound_llm` 误传。

**下一步（Agent 定策）：** 不再纯静态推测——写探针用**真实 registry + 真实 kb RoleSpec + `compute_exclude`**，打印子代理实际会得到的 `tool_defs` 名字，据此证伪/证实「工具集为空」。

**Why:** 这是「知识库/题库创建失败」现象的真正落点——此前 project-dsml-subagent-protocol-text-leak / project_agent_protocol_text_and_ui_fixes 记的「根因=模型吐 DSML 文本」是表象层（协议文本兜底已解乱码），但**底层「子代理根本没拿到 kb 工具」才是工具没执行、库没建成的更根本原因**。
**How to apply:** 排查此类「子代理能力缺失」时，先确认走哪条链路（普通 API vs ds-free，本次=普通 API+Function Calling），再用「假 LLM 探针证明逻辑对」+「真实链路探针打印实际 tool_defs」两段式定位法，把「逻辑错」与「运行时未生效」分开。
