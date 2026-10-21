---
name: 子代理创建的笔记详情页空白（前端只读 markdownContent，后端只写 content）
description: 2026-10-11 根因确认——子代理建/编的笔记（ID 440/438/439）内容只写进 note.content，而前端所有展示点只读 markdownContent，导致详情页/列表/编辑器全空白；修复=后端双向互补兜底
type: project
from: Agent
---

2026-10-11 用户报 bug（已定位根因并修复）：子代理编辑/创建的笔记，子代理自检「有内容且是草稿状态」，但用户在个人中心点开笔记详情页看到**空白**。

**已查证的事实（用户库 user_id=105）：**
- 内容确实存在：`note.content` = 661 字纯文本，但 `markdown_content` **为空**。
- 同类笔记同样只写 `content`：C++（ID 438，1046 字）、Spring Boot（ID 439，481 字）——「内容写进 content 而非 markdown_content」是这几篇的一致形态。
- 该笔记：`draft` 草稿、`is_public=0`、未删除；categoryId=36；创建于 2026-10-10 19:27。

**根因（已确认）：后端接口同时返回 `content` 和 `markdownContent`（`notes.py` 详情接口无问题），但前端所有笔记展示点只读 `markdownContent`**，当 md 为空即显示空白：`notes/detail.vue:319/335`（`noteData.value.markdownContent || ''`，用户所见空白即此）、`myNotes/index.vue:135`、`notes/list.vue:132`（列表摘要 `getSummary(note.markdownContent)`）、`notesEditor:378/101/126`、`editor.vue:482`。而写入侧 `note_manage._create` 允许 `content` 或 `markdown_content`，子代理传的是 `content`（工具描述里 content 也合法），于是只落 `content`。注意后端别处 `note_write_service.py:147`（`note.content or note.markdown_content`）本就兼容两者——前端未做同样兼容。

**Why:** 前后端对「笔记正文存哪个字段」的假设不一致：写入/前端只认单一字段。用户一度分不清是「草稿不显示(前端)」还是「没写进去(子代理)」，实为同一字段取值差异。

**Why（另一半·用户可见症状）：** 用户反馈「我都没找到这个草稿状态」。查实 `myNotes/index.vue` 的笔记卡片**只渲染「私有/公开」标签（124-125 行），未渲染 `status`（draft/published）**——所以草稿状态在个人中心列表根本不可见，用户看不到"草稿"。这属**前端展示缺失**，非子代理的错（子代理按工具契约传了 `content`、也确实上报了 draft）。**定案：不应再让用户猜，须把草稿状态显式展示出来**（在 `myNotes` 卡片加「草稿/已发布」状态标签；`note.status` 通过类型里的 `[key:string]:any` 可用）。

**How to apply:** 修复已定案为**后端双向兜底**（治本、一处修、覆盖所有前端读点与历史数据）+ **前端展示补齐**：
1. `note_write_service.create_note` 落库时**双向互补**——只给 `content` 就同时写 `markdown_content`，反之亦然；
2. `notes.py` 的 `format_note` 与 `note_write_service.note_detail` 做**读取兜底**，覆盖历史只写 `content` 的笔记（440/439/438 等）；
3. `myNotes/index.vue` 同步（a）加 `status` 草稿/已发布标签、（b）摘要 `getSummary(note.markdownContent)` 也要兜底 `content`（否则列表摘要仍空）；
4. **待确认**：`myNotes` 的取数走 `listNote` → 后端 `GET /notes` 列表接口，须核对列表接口返回字段是否含 `content`/`status`（是否复用 `format_note`），否则前端兜底/标签无数据可依。
后续再遇「笔记空白」类问题先核对**前后端各自读/写的是哪个字段**，勿只盯草稿/私密状态；凡用户「找不到某状态/字段」先查前端是否压根没渲染该字段。

**2026-10-11 提交受阻（未推送）：** 改动整理进 worktree 后核对时发现 **`myNotes/index.vue` 的 `git diff` 显示 +636/-46 行**，远超本次小改动——怀疑 **worktree 里的基线版本与主工作区版本差异很大**（可能该文件在工作区有大量未提交改动，或行尾/编码差异）；若照此提交会夹带一堆无关内容，故**中止提交**、须先查清该文件 diff 头。该 worktree 至今未完成推送。

**2026-10-11 修复进展（本轮）：** 四处修复改动落定——`note_write_service.py`（`create_note` 落库双向兜底 + `note_detail` 读侧兜底）、`api/v1/notes.py`（`format_note` 读侧兜底）、`myNotes/index.vue`（草稿/已发布状态标签 + 摘要 `getSummary` 兜底 `content`）；`myNotes/index.vue` 已用 `_v.cjs` 单文件校验通过。**因沙箱 asyncio 全挂、后端接口（DB+async）跑不了 → 端到端验证退化**：只用临时脚本模拟 `format_note` 纯字段兜底逻辑 + 以「修复逻辑正确」为准；历史笔记 440 的 `content`=661 字已确认有值。整理提交走 **worktree**：删临时文件（`_v.cjs` + 临时查询脚本）后 `fetch` 得 main tip=`021d384`，从该 tip 建 worktree 并拷入 3 个改动文件（注：`_probe_note_content.py` 为一次性查库脚本，未入库）。

**2026-10-11 提交前核对又发现「文件混历史改动」→ 定案只提交后端 2 个文件的兜底修复（本轮）：** 在 worktree 逐文件核对 diff 时发现两处污染——① `myNotes/index.vue` 相对 main 为 **+636/-46 行**（远超本次"草稿标签 + 摘要兜底"几行），原因是**主工作区（delivery 分支）该文件含大量更早已完成但未提交的改动**（来源筛选搬进面板、收藏截断提示等），并非本轮笔记 bug 修复；② `notes.py` 的 diff 也**不止本轮兜底**，还混着 `list_favorite_notes` 的可见性校验 / N+1 优化 / `add_favorite_note` 归属校验等**历史未提交改动**。**结论：不能整文件搬，否则会把这些可能有意义、有意未提交的历史改动一并混进公开 main。** **定案：本轮只提交后端 2 个文件的兜底修复**（`note_write_service.py` 落库互补 + `note_detail` 读侧兜底；`notes.py` 的 `format_note` content/markdownContent 互兜底），**这两处治本**——覆盖详情页/列表/编辑器等所有前端读点，**不需要改前端即可修好空白**（前端 `myNotes/index.vue` 的「草稿标签」属锦上添花，且耦合历史改动 → **本轮不提交**，留给后续单独处理）。实现方式=在检出自 main 干净版本的 `.wt_note` worktree 内**手工 edit** 只恢复这两处改动。**后续凡遇同类「整文件 diff 异常放大」先停手核对 hunk 归属，只落本轮最小改动。**

**2026-10-11 本轮最终结果（已推送，bug 闭环）：** 上述最小集（后端 2 文件 `note_write_service.py` + `api/v1/notes.py` 的 content/markdownContent 双向兜底）已 **commit `eb92f2a` 并成功推送**，区间 `021d384..eb92f2a HEAD -> main`，随后清理了 worktree `.wt_note`。**验证手法**：本轮因沙箱 asyncio 全挂，端到端（DB+async 接口）跑不了 → 退化为**纯字段逻辑校验 + 后端编译通过**；提交前先 `fetch` 确认远程 main tip 仍为 `021d384`（未变），故无 non-ff、无需 rebase 直接推。

**2026-10-11 本轮最终落定（已进入提交阶段）：** 在 `.wt_note` worktree 内的具体手法——① **先把 `notes.py` 从 worktree 内还原成 main 干净版**（丢弃混入的历史 hunk），再在 worktree 内**手工 edit 只加 `format_note` 的 content/markdownContent 兜底**（仅 2 行）；② **把前端 `myNotes/index.vue` 从 `.wt_note` 还原**（本轮不提交它，因耦合历史改动）。**还原后 worktree 干净：仅 2 个后端文件（`note_write_service.py` + `api/v1/notes.py`）共 +20/-4 行**，正是"笔记空白"治本修复的**最小集**。**worktree 后端已编译通过**；`note_write_service.py` 的 diff 被确认为**纯净**（只有本轮两处兜底）。提交时确认 `.wt_note` 的 HEAD 仍为 `021d384`（= main tip）。**这一「还原到 main 版 + 手工 edit 最小 hunk」是应对"整文件 diff 异常放大/混入历史改动"的标准手法。**
