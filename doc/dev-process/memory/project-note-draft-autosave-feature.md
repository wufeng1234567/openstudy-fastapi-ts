---
name: 笔记编辑器草稿自动保存新功能需求
description: 2026-10-11 用户提出新功能——笔记编辑时未发布也未删除就离开/刷新，下次进入写笔记要自动恢复草稿内容；草稿不属于任何笔记（无笔记 ID）
type: project
from: Agent
---

2026-10-11 用户提出**新功能需求**（非 bug fix）：**笔记编辑器的草稿状态自动保存**。

需求要点（用户原话提炼）：
1. 用户写一篇笔记，**没提交也没删除**，就因各种原因**直接离开页面或刷新**了；
2. 下次进入「写笔记」（注意是**写笔记**这个场景）时，若存在处于**草稿状态**的笔记，要**自动把之前写过的内容展示给用户**（恢复/续写）；
3. **草稿不属于任何一篇笔记**——因为它此时还没发布，所以**没有笔记 ID 才合理**（即草稿是独立于已发布笔记的独立存储，不能挂靠在某个 note id 下）；
4. **必须做好 bug 检查**，例如：从其他地方点击「编辑笔记」时会不会把草稿覆盖掉？用户想查看草稿时怎么办？等边界场景都要覆盖到。

**Why:** 用户是在笔记编辑场景下发现目前缺乏草稿保存能力——编辑中途意外离开/刷新会丢失未提交内容，体验断裂。

**How to apply:** 这是涉及「前端编辑器 + 后端存储 + 大量边界处理」的**新功能**，属大改动，不是小修补。动手前须先理解现状并把「该不该构建、怎么构建」的方案讲清楚给用户确认（用户倾向：方向/方案一旦拍板就一路做到提交，见 feedback-auto-commit-with-message；但**方案本身待定时需先对齐**）。设计时重点关注草稿的**独立标识**（无 note id）、自动恢复入口（仅限"写笔记"新建场景）、与应用「编辑已有笔记」入口的**冲突/覆盖**问题、以及草稿查看/丢弃路径。

**与上一轮改动的关联（已闭环）：** 上一轮「笔记空白 bug 修复」已收敛为**后端最小集 2 文件**（`note_write_service.py` + `api/v1/notes.py` 的 content/markdownContent 双向兜底，不含 `myNotes/index.vue` 因该文件耦合大量历史改动）并推 **`eb92f2a`**（区间 `021d384..eb92f2a`）。详见 project-note-440-blank-detail-markdown-content。

**2026-10-11 本轮起点（正式开工做本新功能）：** 用户已把话题切到「笔记编辑器的草稿自动保存」，定位为**新功能**（区别于上一轮的 bug 修复）。Agent 已开始**摸现状**：先看笔记编辑器 `notesEditor`（`notesEditor/index.vue`）的编辑入口、如何判定「写新笔记」、`currentNote` 结构、创建/更新流程。**How to apply:** 实现前把「该不该构建、怎么构建」讲清待用户确认，再一路做到提交。

**2026-10-11 重大修正（本轮诊断）：需求不是「从零新功能」，而是「修好已有的草稿功能」——现有草稿实现有多个 bug。**
- **C 端笔记编辑器 = `src/views/front/notes/editor.vue`**（`notesEditor/notesEditor/index.vue` 是管理端，非 C 端入口）。
- **草稿功能其实早已存在**：`DRAFT_KEY = 'note_draft'` + localStorage。`saveDraft()`（约381）把 title/content/isPublic/categoryId/tags 存 localStorage；`loadDraft()`（约357）仅在**新笔记模式（无 `route.query.id`）**读回；`watch`（约547-552）内容变化 → **500ms 防抖自动 `saveDraft()`**；`syncEditorMode()`（约340-352）新笔记时调 `loadDraft()`；`goBack()`（约407）返回时也存一次。
- **用户报的 bug = 现有草稿失效**：不提交也不删除直接离开/刷新，下次进入写笔记看不到写过的东西。
- **根因确认（已定位）**：`editingNoteId = ref(null)`（约163）初始为 null。首次进入「写笔记」页/刷新后 → `syncEditorMode()` 走 else 分支 → **`if (!editingNoteId.value) return`（约341）直接 return → `loadDraft()` 永不执行** → 草稿读不出来。修法=else 分支**无条件** `loadDraft()`。
- **第二个 bug（草稿被污染）**：`watch`（监听 `editorHtmlContent` 等）**不区分是否新笔记**，编辑已有笔记时也会写 `note_draft`，把「编辑中笔记内容」错误存成草稿 → 污染。需按「仅新笔记才 saveDraft」修正。
- **第三个 bug（小）**：`loadDraft` 里 `isPublic.value = parsedDraft.isPublic || 1`——若存的是 0（私密）会被 falsy 成 1，丢失私密态。
- **语义判定（Agent 已核对）**：从「编辑某笔记」切到「写新笔记」时读草稿=正确（草稿独立于笔记）；有 id 的编辑分支不读草稿=正确（草稿只属新笔记）。
- **How to apply:** 这不是一行修补，涉及「是否新笔记」的语义贯穿 saveDraft/loadDraft/watch 多处，须先给用户**诊断+方案**、并就「草稿语义范围」这一关键决策对齐后再动手。**注意：真正的编辑器是 `notes/editor.vue`，不是 `notesEditor/index.vue`。**

**2026-10-11 方案已确认 + 实施中（用户同意后开工，改动全在 `notes/editor.vue`）：**
用户已确认**方案**：**localStorage 单草稿 + 进「写笔记」页自动带出 + 顶部提示恢复**，**不另做入口**（不加"查看草稿"按钮/页面）。改动清单（6 条，Agent 已逐项核对上下文，`ElMessage` 已 import、`selectedBankIds` 变量名已确认存在）：
1. **修主 bug**：`syncEditorMode` 的 else 分支去掉 `return` 挡路，**无条件** `loadDraft()`（对应前述根因）。
2. **修草稿被污染**：`saveDraft` 的 watch **仅在新笔记模式（无 id）时**才写草稿；编辑已有笔记不写。
3. **修 `isPublic || 1`**：改用 `?? 1`（0 也能保留）+ 只在草稿确有内容时才覆盖表单。
4. **草稿恢复提示**：`loadDraft` 恢复成功时轻提示（"已恢复上次未保存的草稿"）——**`loadDraft` 需返回"是否恢复到了东西"**供提示用。
5. **离开前兜底保存**：`onBeforeUnmount` 也 `saveDraft()`（现有只在 `goBack` 存，直接关标签页/切路由会丢掉最后一次 500ms 防抖内的内容）。
6. **空草稿不覆盖**：草稿为空（无标题且无内容）时不恢复/不弹提示。

**关键决策（Agent 拍板，已留档）：** 草稿**只存正文相关字段**（title/content/isPublic/categoryId/tags，保持现状），**不扩 `selectedBankIds`（关联题库）**——草稿职责是「内容」，为最小改动 + 贴合用户"想看自己写过的东西"的诉求，避免引入字段不一致。**How to apply:** 后续扩草稿字段前先与用户对齐「草稿职责范围」。

**2026-10-11 深入复核（改动 3~6 落实 + 新发现第 4 个 bug）：**
- **改 4/5/6 落实细节**：`saveDraft` 内加「仅新笔记模式才写」守卫（守卫放 `saveDraft` 函数内部最稳，因 `watch` 回调与 `onBeforeUnmount` 都调它）；空内容不写（避免清空后仍留脏草稿）；`onBeforeUnmount` 也调 `saveDraft()`（覆盖直接关页/切路由未走 `goBack`）。`draftTimer` 声明（约 546，`watch` 前）在 `onBeforeUnmount` 注册点（约 513）之后，但**回调延迟执行**，运行时 `let draftTimer` 已初始化，安全；为稳妥可把声明提前。
- **新发现 bug（第 4 个）：`clearDraft()` 误清用户草稿**。`handleSave`（约 680）保存成功后调 `clearDraft()`；**从"编辑已有笔记"保存成功后也会走到** → 会误清用户在"写笔记"存的草稿。**修法=`clearDraft()` 仅在新笔记保存成功时调用**（用局部变量记「是否新笔记发布」，只在发布成功时清）。
- **`goBack()`（约 407）现状核对**：`saveDraft()`（编辑模式因守卫不写）→ `router.push`，因 `saveDraft` 有守卫，编辑模式不再误写草稿 ✅。
- **`handleSave` 后**：`router.push('/front/notes/list')` 离开，故"发布成功清草稿 + `editingNoteId` 置 null 后若未跳转会重新 loadDraft"的担忧无碍。
- **How to apply:** 全部改动集中在 C 端 `src/views/front/notes/editor.vue`；改完须用 `_v.cjs` 校验（本环境一次传多文件会失败，须重建 `_v.cjs` 并**单文件**逐个校验，见 feedback-frontend-validate-per-file）。

**2026-10-11 再复核（第 4 个 bug 精确定位 + TDZ 结论）：**
- **`clearDraft()` 误清点精确行号=约 664**（在 `handleSave` 内，非 680）；`handleSave` 是**编辑模式专用保存**——只在 `editingNoteId.value` 存在时工作（else 分支仅警告"请先发布笔记"）→ 它必然处理"编辑已有笔记"，其中的 `clearDraft()` 是**多余的且有误清风险**（会清掉用户在"写笔记"存的草稿）。修法仍=仅新笔记保存成功才 `clearDraft()`。
- **TDZ 结论：安全**。`syncEditorMode`（约 359）调 `loadDraft()`（定义在约 380，`const` 不提升），但 `syncEditorMode` 的调用点全在 `onMounted`（约 513）+ `watch` 中，均为**延迟执行**；模块顶层顺序执行到 380 行后 `const loadDraft` 已初始化，故不会触发 TDZ 报错。
- **核对方向留档**：改动 `loadDraft` 返回值（供提示判断是否恢复成功）后，须扫全仓 `loadDraft` 调用点确认无遗漏。

**2026-10-11 草稿改动已完成并校验通过（改动全落在 C 端 `src/views/front/notes/editor.vue`）：**
- **`clearDraft()` 最终只在 `handlePublish` 内以 `if (isNewNote) clearDraft()` 调用（约 718/735 行）**；`handleSave` 里的多余 `clearDraft` 已删（该函数是「编辑模式专用」保存，else 分支仅提示"请先发布笔记"）。
- **`handlePublish` 同时处理新建/编辑**（`editingNoteId` 有值则走 update）；但**模板只把主按钮绑到 `handlePublish`（14 行，文案 `editingNoteId ? '保存' : '发布'`）**。`handleSave`（约 622）**只被 Ctrl+S 快捷键调用（`handleGlobalKeydown` 约 609 行）**——属**既有行为**（Ctrl+S 仅编辑模式存增量），**本轮刻意不改，避免扩大改动面**。
- **`goBack()` 的 `saveDraft()` 有守卫**（编辑模式不写）✅；`syncEditorMode` else 分支无条件 `loadDraft`；`onBeforeUnmount` 也 `saveDraft()`。
- **校验**：重写临时脚本 `openstudy-vue3-ts\_v.cjs`（@vue/compiler-sfc+typescript）**单文件**校验 `editor.vue` **通过**；随后单测成本高（依赖 Vue ref + localStorage），改用**人工边界场景核对清单**全部覆盖（首次进入无草稿→空表单/无提示；走返回键→存；直接关标签/切路由→onBeforeUnmount 存；改成空→removeItem；下次进写笔记→带出草稿+提示；写草稿时去编辑已有笔记→守卫不污染；编辑已有笔记保存成功→不清草稿；发布新笔记成功→清草稿；存量私密草稿 isPublic=0→`??1` 保留私密；刷新且在编辑已有笔记→有 id 不读草稿）；校验完已删 `_v.cjs`。
- **How to apply:** 草稿相关改动完成即进入提交流程（见 feedback-auto-commit-with-message）；`handleSave`/Ctrl+S 与 `handlePublish` 的语义差异属既有设计，后续勿顺手"统一"。

**2026-10-11 提交阶段（再次撞上"文件耦合历史改动"老问题）：**
- **建 worktree 前 fetch 得 main tip=`eb92f2a`**，worktree 已建好（基于 `eb92f2a`）。
- **`editor.vue` 相对 main 又是 `+276/-56` 的放大差异**——与本轮草稿改动无关的**历史未提交改动**大量堆积在同一文件（与上一轮 `myNotes/index.vue` 完全同类问题）。
- **判据：diff 块多且散落 → 大部分是历史改动 → 无法安全整文件 `Copy-Item`。** 决策=在 worktree（main 干净版）内**逐处手工 `edit`** 只落本轮 6 处改动，用**文本锚点**（依赖同名同结构的函数/变量）而非行号（worktree 是 main 版，行号与脏工作区不同）。本轮 6 处=①`syncEditorMode` else 分支 ②`loadDraft`（改写+返回 bool）③`saveDraft`（加守卫）④`onBeforeUnmount`（加 saveDraft）⑤`handleSave`（删 clearDraft）⑥`handlePublish`（`isNewNote` 守卫 clearDraft）。
- **How to apply:** 本仓 `notes/editor.vue`、`myNotes/index.vue` 这类长驻脏工作区文件会反复耦合历史改动；凡 `git diff <main> -- <file>` 出现远超预期的放大差异（如 `+276/-56`），一律判定"不可整文件搬运"，改走 worktree 内按锚点手工 edit 只落本轮 hunk。

**2026-10-11 worktree 逐处 edit 实操细节（main 版与脏工作区版的结构差异，按锚点核对）：**
- **main 版 `notes/editor.vue` 总行数比脏工作区版少 13 行**（main 版约 515 行处也有 `clearDraft()`，与脏工作区 `handleSave` 那处对应；main 版约 583 行是 `handlePublish`）。
- **`syncEditorMode` 的 else 分支：main 版本来就没有 `selectedBankIds.value = []`**（该项是脏工作区里额外加的）——为**保持最小改动**，worktree 内**不加**它（`selectedBankIds` 重置属额外清理，非草稿必需）。**How to apply:** 按锚点 edit 时若发现 main 版缺少脏工作区里"顺手加的清理行"，判断其非本轮必需则不加，避免把额外清理带进公开 main。
- **`draftTimer` 声明位置**：main 版声明约 488 行，`onBeforeUnmount` 注册约 455 行——回调**延迟执行**，运行时该 `let` 已初始化，安全（与脏工作区版同结论）。

**2026-10-11 worktree 逐处 edit 实操——行号漂移实证（重要）：** 在 worktree（main 版）内按锚点 edit 时，**实际行号与上面预估（main 版 handleSave/clearDraft 约 515、handlePublish 约 583）不一致**——实时读到的落点为：`handleSave` 尾部 `clearDraft()` 在 **545-560** 区段、`handlePublish` 的 `clearDraft()`（原 ~627）在 **615-635** 区段。**证明"对齐锚点比记行号更可靠"，行号只能当粗略定位，务必每次先读该区段再 edit。**
- **改 4 已落地**：删除 `handleSave` 里多余的 `clearDraft()`（该函数为编辑模式专用保存）。
- **改 5 已落地**：`handlePublish` 内 `clearDraft()` 加 `isNewNote` 守卫（仅新笔记发布成功才清草稿）。
- **全部 5 处改动（改1~改5，见上文 6 条清单去重后）已全部落地 worktree**，随后进入**校验阶段**：①重建临时 `_v.cjs`（@vue/compiler-sfc+typescript）对 **worktree 的 `editor.vue` 单文件**校验（须单文件跑，见 feedback-frontend-validate-per-file）；②复核 worktree 的 `git diff --stat` 是否收敛到最小（防止 edit 时混入额外改动）。
- **worktree 目录名=`.wt_draft`**（位于项目根，如 `.wt_draft\openstudy-vue3-ts\src\views\front\notes\editor.vue`），**How to apply:** 校验 worktree 文件时路径须走 `.wt_draft\...`，别误校验脏工作区原文件；校验后收尾清理该 worktree。

**2026-10-11 worktree 校验与行为自测（本阶段收口）：**
- **worktree diff 收敛核对**：worktree 版 `editor.vue` 相对 main 为 **`+80/-32`**，比脏工作区的 `+276/-56` **大幅收敛**（证明逐处锚点 edit 成功、只落了本轮草稿改动，无历史遗留混入）。
- **语法校验（关键实操）**：**worktree 内没有 `node_modules`，无法在 worktree 内跑 `_v.cjs`** → 正解=**在主工作区跑 `_v.cjs`、参数传 worktree 文件的绝对路径**；worktree 版 `editor.vue` 语法校验**通过**。
- **行为自测（零成本、可复现）**：把 `loadDraft`/`saveDraft` 纯逻辑抽到临时 node 脚本（模拟 localStorage + Vue ref），跑 **8 个边界场景 8/8 全绿**（无草稿/写入/带出/清空/编辑模式不污染/私密保留/空草稿不覆盖 等）。
- **`syncEditorMode` else 分支的重置守卫**：用 `if (lastLoadedId !== null || editingNoteId.value !== null)` 条件重置——**首次进入时两者都是 null → 跳过重置**（初值本就空，正确）。
- **How to apply:** **worktree 为前端校验时不能就地跑 `_v.cjs`（无 node_modules），改由主工作区执行并传 worktree 绝对路径**；行为类改动（localStorage/防抖/守卫）除语法校验外，抽纯逻辑跑临时脚本做边界自测是低成本高收益的验证手段（见 feedback-temp-script-files-not-multiline）。校验/自测完成后删临时脚本（`_v.cjs`/`_t.cjs`），再进入提交。

**2026-10-11 已闭环：草稿改动已提交推送，功能完成。**
- **提交 `c079c82`，推送区间 `eb92f2a..c079c82 HEAD -> main`（hook 通过），推后已清理 worktree `.wt_draft`。**
- 本轮最终落地的 4 个修复（全在 C 端 `src/views/front/notes/editor.vue`）：①去 `syncEditorMode` else 分支的 `if (!editingNoteId.value) return`（否则 `loadDraft()` 永不执行＝主 bug）；②`saveDraft` 加 `if (editingNoteId.value) return` 守卫（编辑已有笔记不写草稿，防污染）；③`isPublic || 1` 改 `?? 1`（保留私密 0）+ 空草稿不覆盖表单；④`clearDraft()` 只在 `handlePublish` 内以 `isNewNote` 守卫调用（编辑专用 `handleSave` 里多余的 `clearDraft` 已删）。
- **新增交互**：恢复草稿时轻提示「已恢复上次未发布的草稿」+ `onBeforeUnmount` 兜底 `saveDraft()`（防抖窗口内关页不丢）。
- **边界核对 9 场景全覆盖**：无草稿/写入/离开/带出/清空/编辑模式不污染/发布清草稿/私密保留/刷新编辑不误读；语法校验通过 + 草稿纯逻辑边界自测 **8/8 全绿**（临时脚本已删）。
- **方案维持用户确认的选择**：localStorage 单草稿 + 进「写笔记」页自动带出，**不另做草稿入口**。
- **How to apply:** 该功能已交付，后续若再动 `notes/editor.vue` 的草稿逻辑，先看 `c079c82` 的最终形态；`handleSave`(Ctrl+S)/`handlePublish` 的语义差异属既有设计，勿顺手统一。**该文件长驻脏工作区、耦合大量历史未提交改动（相对 main 达 `+276/-56`），故仍走 worktree 手工只落本轮 hunk（收敛到 `+80/-32`）。**

**2026-10-11 提交推送阶段（进入提交流程，进行中）：**
- 校验/自测完成后进入提交：写提交说明（落 `.wt_draft\_commit_draft.txt`，**该说明文件本身不得被暂存**）。
- **手工暂存口径 = 只 `git add` 本轮唯一改动的 `editor.vue`**，随后复核暂存清单确认「仅 editor.vue、未暂存 `_commit_draft.txt`」（本轮只 1 个改动文件 ✓）。
- 提交前最后一步：`git fetch` 确认远程 main tip 未变后提交推送（沿用 feedback-auto-commit-with-message 的 worktree 流程）。

**2026-10-11 后续（弹两次回归 bug 已修，仍走同一 worktree 套路）：** 发现「有草稿时进写笔记页提示弹两次」（keep-alive `onMounted`+`onActivated` 双触发 `loadDraft`），修法=`newNoteDraftSettled` 幂等守卫（详见 project-note-draft-restore-double-toast）。该修复亦全程走 **worktree `.wt_draft` + 按锚点手工 edit**（`editor.vue` 长驻脏工作区，绝不整文件拷贝）；修复前用临时 `_t.cjs` 做幂等自测 5/5 全绿。
