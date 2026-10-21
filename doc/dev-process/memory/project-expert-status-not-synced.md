---
name: 专家工作组「进行中」状态不同步为「已完成」bug（已双端修复）
description: 2026-10-11 用户报——题库专家已建库+已输出正文，但专家卡片仍转圈「工作中」，另三个专家正常标完成；真因=index 跨 LLM 轮次撞车，已双端修复（全局 delegate_seq + 前端仅回填 running 行）
type: project
from: Agent
---

2026-10-11 用户报新 bug：**专家工作组的「进行中」状态没有同步为「已完成」**。

**现象（用户原话要点）：** 让智能体一次并行做四件事，其中「计算机网络题库」已创建成功、正式回复也输出出来了，但**「题库专家」那一行卡片还在转圈显示「工作中」**，而**另外三个专家（笔记专家/知识库专家/学习统计专家）都正常标识「已完成」**。

**任务细节（用于复现）：** 同一轮并行委派四件事——① 创建「计算机网络基础题库」（学科「计算机网络」，描述「计算机网络基础知识练习题库」，公开可见）并在其中导入 3 道单选题（OSI 七层模型 / TCP 三次握手 / HTTP 与 HTTPS 的区别，各 4 选项+答案+解析）；② 创建笔记「Spring Boot 核心注解速记」；③ 创建知识库「SpringBoot」；④ 学习统计概览。**后端本次全部成功**（题库 ID 1173、3 题；笔记 ID 439；知识库 ID 567；统计 227 次作答/正确率 58.6%）——即数据操作成功，只有前端状态行未收敛。

**Agent 本轮深挖根因（代码级收敛，尚未修复）：** `delegate_done` 没回填到对应行，真因基本锁定为 **`index` 作用域是「每个 LLM 轮次局部」，而非整轮（turn）全局唯一，导致跨 LLM 轮次 index 撞车**。
- 后端：`delegate_jobs` 定义在**每个 model-turn 内**（`loop.py` 约 1249 行，`for ... in tool_calls` 循环之前）——即**每个 LLM 轮次重置一次**；`delegate_start` 发 `index = len(delegate_jobs)` → **每轮都从 0 重新计**；`delegate_done` 发对应 `item["idx"]`。后端自身 start/done 口径是自洽的。
- 前端：`findExpertCard()` 只按**轮边界（`turn_end`）**找当轮 experts 卡片，**不区分 LLM 轮次**；`useAgentChat.ts` 的 `fillExpertDone` 用 `find((e) => e.index === idx)` 回填。
- **撞车机制**：若指挥家**分多个 LLM 轮次**发起委派（一轮只发 1 个 delegate 时 index 又从 0 开始），轮次 A 的 `index=0` 与轮次 B 的 `index=0` 冲突 → 回填被错误应用到**另一个同 index 的已先行**（已 ok），而 B 的新行**永远回填不到** → 一直转圈。完全解释「4 专家里只有 1 个（题库专家）转圈、其余 3 个正常」。
- 已排除：`except` 分支 `results=[]` 只在 `asyncio.gather` 整批抛异常时触发（会导致**所有** done 都不发，与「3 完成 1 未完成」不符）；单个 job 卡死不返回也会导致全批不完成，同样不符。

**修复（2026-10-11 已实施，双端兜底）：**
- **后端治本**：在 loop 的 LLM 轮次循环**之外**声明全局计数器 `delegate_seq = 0`（`loop.py` 约 1161 行前）；`delegate_start` 发 `index: delegate_seq` 并自增、`delegate_jobs` 记该 index；`_run_delegate` 解包相应多出第 7 个元素（seq）；`delegate_done` 的 index 改发 `item["seq"]`（**不再用 `item["idx"]`——后者是 `lc_messages` 下标**）。
- **前端兜底（`useAgentChat.ts` 的 `fillExpertDone`）**：按 index 查行时**要求该行仍 `running`**（`find((e) => e.index === idx && e.status === 'running')`），防止撞号时把已完成的同 index 行**重复回填**；找不到 running 行再回退按 `key` 找 running 行。该层对**跨轮撞号的老数据**同样有效。

**Why:** 这是「多专家并行可视化」在真实四专家并发场景下暴露的状态收敛缺陷——与 `project-agent-experts-ui-polish` 修的「结论恒（无输出）」同属 `delegate_done` 事件的取值/定位口径问题，但那条修的是 `summary` 取值，本条是**行定位（index）作用域**，不要混为一谈。

**How to apply:** 排查此类「某一行卡在进行中」时，先核对 `delegate_start`/`delegate_done` 的 `index` 是否跨 LLM 轮次全局唯一（重点看 `delegate_jobs` 是否每轮重置、计数器是否落在 LLM 轮次循环之外），再看前端 `fillExpertDone` 是否按 index 命中「本轮最近一条 experts 消息」且**仅回填 running 行**（轮边界口径见 `project-parallel-expert-delegation-design`）。改动后须跑 `tests/_probe_parallel_delegate.py` 与全量回归。

**收尾（2026-10-11）：推送成功 `b96af7d..9ef3a44 HEAD -> main`（提交 `9ef3a44`）；推后已清理 worktree。** 本次修复的 `useAgentChat.ts` 已通过 `_v.cjs` 单文件校验（见 feedback-frontend-validate-per-file），临时脚本已删、**已随 4 文件提交推送**。验证补充：`_probe_parallel_delegate.py` 内追加了 PD-19/PD-20 源码级断言（验 loop 的 delegate index 用整轮全局 `delegate_seq`），但因该探针主入口 `run_probe()` 为 async 在沙箱跑不了，PD-19/20 单独落到**新的同步微校验 `tests/_probe_delegate_index.py`**（详见 tests-probe-conductor）。

**本轮提交内容（2026-10-11，4 文件）：** ① 后端 `loop.py`（delegate index 改整轮全局 `delegate_seq`）；② 后端探针 `_probe_parallel_delegate.py`（+PD-19/20）；③ **新增同步探针 `tests/_probe_delegate_index.py`**；④ 前端 `useAgentChat.ts`（`fillExpertDone` 要求该行 running + 幂等回退）。**决定：`_probe_delegate_index.py` 一并入库**——它是本 bug 的**回归探针（纯同步可跑，有保留价值）**，故加入提交。走 worktree 提交前：5/5 校验全绿、临时校验脚本 `_v.cjs` 已删、fetch 得 main tip=`b96af7d`。
