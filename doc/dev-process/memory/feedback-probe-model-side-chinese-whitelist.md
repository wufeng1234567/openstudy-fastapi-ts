---
name: 模型侧中文白名单探针（_toolpref_probe P11d）
description: 精简工具 description 时不得新增模型侧中文短语，P11d 会扫 describe/definitions/系统提示词
type: feedback
from: Agent
---

**精简工具 `description` 时，绝不能新增模型侧的中文短语/括注，否则 `_toolpref_probe` 的 P11d 会判红。**

**Why:** 2026-10-09 精简 `question_flag_manage` description 时，Agent 手滑加了 `(收藏)`，引入了第 5 处模型侧中文，触发 P11d「模型侧中文普查：只允许已知的 4 处」。探针扫描的是**模型侧输出**（`describe()` / `definitions()` / 系统提示词），白名单为 `{错题本, 斩题, 二次函数, 副本}`。旧 description 本就有 `错题本`/`斩题` 中文（在白名单内），Agent 新增的 `(收藏)` 不在白名单，导致计数变化判红。去掉 `(收藏)` 后 `_toolpref_probe` 恢复 **32/32 全绿**。

**How to apply:** 编辑任何工具 description / 系统提示词时，只保留原有中文括号注释，不新增中文词（如 `(收藏)` 这类括注一律不加）；改完必跑 `tests/_toolpref_probe.py` 回归。该探针**依赖 DB**。这是探针**正确地**抓到了 Agent 引入的模型侧中文，属于该保留的防护，不要为图省事改探针白名单。

**二次印证（2026-10-09 上下文优化收尾）：** 本轮修改系统提示词/工具 description 后再次跑 `_toolpref_probe.py`，32/32 全绿；说明此防护对「去 `{{TOOLS}}`/`Available Tools` 段、精简 description」类改动仍有效，未误报。

**三次印证（2026-10-09 阶段 1 实施）：** 因 P11d 会扫**系统提示词**中的中文，多智能体阶段 1 新增 `agent/roles.py` 时，决定把进系统提示词的 `prompt_fragment` 一律写**英文**，仅界面侧的 `name`/`description` 保留中文——从源头规避新增模型侧中文。该「两轨语言约定」应作为后续所有注入系统提示词的默认做法。

**探针与实现口径脱节时，须同步更新探针的断言口径（2026-10-11）：** 为「切断旧路径」删掉 `note_manage` 的 `status` 参数后，`tests\_probe_note_draft.py` 里 ND-12 仍断言「status 说明指向 save_draft」→ 探针必然判红。正确做法＝把该断言口径改成「status 参数已删除」，而不是为让探针变绿去回填已删的 `status`。**How to apply: 改动工具入参形状（删参数/硬编码）后，立刻同步扫描并更新对应探针里引用该参数的断言（本仓 `_probe_note_draft.py` ND-11/ND-12）；探针口径必须跟随实现口径，不能为实现反向妥协。**

**系统提示词里的"强制规则"也属模型侧中文禁区（2026-10-11 量化）：** 为扭转模型工具选择，在 `prompts.py` 的 `AGENT_WORKFLOW_RULES` 第 8 条后新增第 9 条「笔记草稿规则」时，**规则正文必须全英文**（中文只能放界面侧/`description_zh`）——因为 P11d 会把**系统提示词**中的中文一并扫入统计，新增汉字即判红。写完先扫一遍汉字再跑 `_toolpref_probe`。

**工具 description 硬约束（2026-10-11 再犯实证）：** 编辑 `note_manage` 的 `save_draft` description 时，Agent 手滑写入中文关键词 `草稿/draft/未完成/先存着`——description 是模型侧（进 `registry.describe()`），**必须全英文**，中文关键词只能放 `description_zh`。自检：写完 description 立刻扫一遍是否含任何汉字，再跑 `_toolpref_probe`。此坑已犯多次（见本文件开头 `(收藏)` 案例），属高频失误，须形成"先写英文、后补 description_zh"的固定顺序。
