---
name: 指挥家模式探针 tests/_probe_conductor.py
description: 指挥家（Orchestrator）+子代理模式的全部验证入口是 openstudy-fastapi\tests\_probe_conductor.py；它用 fake LLM 零成本验证，不依赖真实模型调用
type: reference
from: Agent
---

指挥家（Orchestrator）+ 子代理（Sub-Agents）模式的验证入口是 `openstudy-fastapi\tests\_probe_conductor.py`（2026-10-09 建立，与既有 `tests/_probe_*.py` 同属刻意入库的探针）。

**覆盖项（6 类）：**
1. 每个可委派子代理都有 `capability`。
2. `render_sub_agents_briefing()` 输出含各子代理、**general 不在内**、可含 `extra_agents`。
3. `delegate_task` 被 `compute_exclude` **永远**排除。
4. 指挥家提示词含子代理清单。
5. `DelegateTaskTool` 元数据（非写操作 `write_operation=False`、参数 `sub_agent`/`task`）。
6. `run_sub_agent` 用 **fake LLM** 验证工具裁剪 + 返回文本。

**关键约束：** 测 `run_sub_agent` 需注入 fake LLM——实现 `ainvoke` + `bind_tools` 的假客户端即可，**零成本、不调真实模型**；另需 `registry` 暴露 `get(name)` 方法供 `run_sub_agent` 取工具。

**Why:** 子代理内层循环不走 `run_agent_stream`（自包含精简 ReAct 循环），无法用现有端到端探针覆盖，必须单测内层循环逻辑；用伪 LLM 避免真实调用成本与不确定性。
**How to apply:** 改动 `roles.py`（RoleSpec persona/capability、render_sub_agents_briefing）、`orchestrator.compute_exclude`、`delegate.py`、`sub_agent.py`、指挥家 `prompts.py`/`loop.py` 后，跑 `_probe_conductor.py` 回归。

**2026-10-10 并行委派轮：`run_sub_agent` 加 `own_session` 默认值参数后探针仍 23/23 绿**——因新增参数带默认值（False），`_probe_conductor` 不传仍兼容；它虽传 `db=object()`，`own_session=False` 时不走独立会话。另新增**并发委派单元级探针** `tests/_probe_parallel_delegate.py`（验证 `run_sub_agent` 的 `own_session` 契约、`DelegateTaskTool` 读 `ctx.extra["delegate_parallel"]`、指挥家提示词含并行指引；用 fake LLM 不开真实工具）。**该并行委派轮已收尾：三步骤全完成、全量回归逐项 `EXIT=0` 全绿 + `app.main` `APP_OK`；本轮后端改动= `loop.py`/`sub_agent.py`/`tools/delegate.py`/`prompts.py` + 新增该探针。**

**2026-10-09 全量回归基线（实测定稿）：** 指挥家探针 **23/23** 全绿；当日全量回归为：角色探针 21/21、用户智能体探针 22/22、指挥家探针 **23/23**、`_toolpref_probe` 32/32、`_probe_knowledge_ingest` 28/28，`app.main` 导入 OK（`APP_OK`）、编译通过。此为阶段 3B（指挥家模式）交付时的验收口径。

**2026-10-10 回归洞见（断言依赖文案，文案改动必红）：** 该轮因「专家管理」重构把 `roles.py` 的 capability/name 口语化、并把指挥家提示词标题由 `## ... (CONDUCTOR MODE)` 改为 **"You Are the Main Assistant..."** 等，触发探针回归：**角色探针 21/21 仍绿**（AR-01 只查工具名存在、路由断言用 key 不依赖文案），但**指挥家探针 22/23**，唯一红项 **CD-11（"指挥家提示词含 CONDUCTOR 段"）——因断言写死了旧标题关键词 `CONDUCTOR`**。修法=把 CD-11 断言改为匹配新标题关键词。**教训：指挥家提示词/角色文案改措辞时，`_probe_conductor.py` 里依赖具体文案字面的断言（尤其 CD-11）会失效，须同步更新；改动提示词措辞后必跑该探针。** 本轮 `app.main` 仍 `APP_OK`。

**2026-10-10 本轮（专家管理）改动含 `_probe_conductor.py`：** 因指挥家提示词标题/文案改动，本轮同步修改了 `tests/_probe_conductor.py` 的文案断言；专家管理全量回归中指挥家探针 **23/23** 全绿。

**2026-10-10 文案断言修复已完成，全量回归全绿：** 新标题定为 `## You Are the Main Assistant (with a Team of Experts)`；**CD-11 与 CD-14 两条断言都写死了旧标题 `CONDUCTOR` → 均随标题改动而红**（CD-11 找 `CONDUCTOR`、CD-14 找 `CONDUCTOR MODE`），**已改为匹配新标题关键词 `"Main Assistant"`（CD-14 可用 `"team of specialist"`）→ 指挥家探针 23/23 全绿**。另核对 CD-12：`role_spec.persona` 断言不受影响——本轮只改了 capability/description/name，**未改 persona**，故其中残留的 "Question Bank Specialist" 仍在且断言正确。**用户智能体探针 22/22 绿**；`_toolpref_probe` 与 config/ingest 随后回归（`_toolpref_probe` 尾部打印的 MD5 是它**自检"探针未改动源码"**，非异常，看全绿需向上找"共 N 项"汇总行）。**结论：一次改标题会同时红 CD-11 与 CD-14 两条断言，改指挥家提示词标题后须同时更新这两处字面匹配。**

**2026-10-11 子代理协议文本检测落地后，指挥家探针为何应仍绿（重要前提）：** 在 `sub_agent.py` 的 `_run_sub_agent_inner` 新增"检测工具调用协议文本并回灌纠正"逻辑后，`_probe_conductor.py` 理论上应仍 **23/23**——因为它测 `run_sub_agent` 用的是 **fake LLM**，其返回**纯文本**（如 `"Found 2 banks: A, B."`），**不含 tool/action key、也不含 DSML/`invoke name=` 等协议特征**，故**不会进入新的协议检测分支**。**How to apply：** 以后为该探针或任何 mock LLM 写"子代理最终产出"的假文本时，**必须避开 tool/action key 与 DSML 特征串**，否则假文本会被新协议检测当成"伪工具调用"拦下回灌，令探针行为和断言漂移。参见 project-dsml-subagent-protocol-text-leak。

**2026-10-11 探针再次扩容：`_probe_parallel_delegate.py` 新增源码级断言 PD-19/PD-20（验 index 唯一性契约）**——修「专家状态不同步」的 `delegate_seq` 改动后，为避免依赖 asyncio 端到端，追加**纯静态断言**：检查 `loop.py` 中 `delegate_seq` 存在于 LLM 轮次循环且 `delegate index` 使用该整轮全局计数器。**关键坑：`_probe_parallel_delegate.py` 脚本开头 `run_probe()` 是 async，整脚本会被 asyncio 卡死（沙箱禁），故 PD-19/20 这类静态检查无法随该探针一起跑** → 本轮**另起独立同步微校验文件 `tests/_probe_delegate_index.py`**（纯同步、单独跑）验证 PD-19/20 逻辑，见 feedback-sandbox-blocks-asyncio-event-loop 的退化路径。**How to apply：** 给该类探针加"可同步跑"的断言时，不要塞进 async 主脚本，应单独落一个同步探针文件。

**2026-10-11 新增同步回归探针 `tests/_probe_delegate_index.py`（已随 bug 修复入库 ★已推送）：** 它是「专家工作组状态不同步（delegate index 跨 LLM 轮次撞车）」bug 的**回归探针**——纯同步可跑（不受沙箱禁 asyncio 影响），验 loop 的 delegate index 使用整轮全局 `delegate_seq`。**决策：此类"纯同步、可独立跑"的回归探针应一并入库**（用户认可其保留价值），与 async 主探针分开。**该探针已随修复提交 `9ef3a44` 推送（区间 `b96af7d..9ef3a44`）到 gitcode/main，确认属于刻意入库的 `tests/_probe_*.py` 白名单（见 feedback-probe-gitignore）。**

**2026-10-11 最新回归基线（全绿）：指挥家 + 角色 + 知识库 + 并行委派 组合回归 18/18 全绿**——本轮按批次跑 `_probe_conductor.py`（指挥家）、角色探针、`_probe_knowledge_ingest.py`（knowledge_ingest）、`_probe_parallel_delegate.py`（并行委派）四条，全部通过。**How to apply：** 后续再改 prompts/roles/delegate/loop/sub_agent 后的验收，先跑这四条组合回归（18/18）作为当前最新口径。

**2026-10-11 探针扩容：`_probe_parallel_delegate.py` 新增协议检测断言 PD-09~PD-12**——用户定案"加进现有探针更集中"，在 PD-08 之后追加，验证私有函数 `_looks_like_tool_protocol`（探针内 import 下划线私有函数可接受，同 `_collect_attachments` 惯例）。**构造测试串的硬约束**：该函数正则要求 `DSML` 后**紧接（可选竖线+空白）`>`/`＞`**，故必须用真实形态 `＜｜｜DSML｜｜＞` 或 `｜DSML｜`；全角 `＜｜｜DSML｜｜` 变体、或 `DSML` 后夹 ` invoke name=` 的长串都**不命中**（本轮 PD-09 假红即因此）。
