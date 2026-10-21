---
name: 写笔记页草稿恢复弹窗弹两次（keep-alive 双钩子）
description: 2026-10-11 用户报——有草稿时进入写笔记页「已恢复上次未发布的草稿」连续弹两次；根因=keep-alive 首挂载 onMounted+onActivated 双触发 loadDraft
type: project
from: Agent
---

2026-10-11 用户报 **弹窗弹两次 bug**：「当拥有/永远草稿后进入写笔记页面，连续弹窗两次『已恢复上次未发布的草稿』」。

**根因**：C 端 `src/views/front/notes/editor.vue` 的笔记编辑器组件被放在 `<keep-alive>` 内（`notes/index.vue:5`）。Vue 的 keep-alive 组件**首次挂载时 `onMounted` 和 `onActivated` 两个钩子都会触发**：
- `onMounted`（约 549）→ `syncEditorMode()` → `loadDraft()` → **弹窗 1**
- `onActivated`（约 570）→ `nextTick(syncEditorMode())` → 又走 else 分支 → `loadDraft()` 再次返回 true → **弹窗 2**

**修复方案（幂等守卫，改 `notes/editor.vue`）**：新增状态变量 `newNoteDraftSettled`（声明须放在 `syncEditorMode` **之前**，避免 TDZ 风险 + 代码清晰），标记「本次进入新笔记模式已处理过草稿」：
- `syncEditorMode` 的 else 分支开头：`if (newNoteDraftSettled) return`（else 只处理"新笔记态"，settled 后无需再读）——首次进入 settled=false → 继续读并置 true（弹1次）；onActivated 二次触发 settled=true → return（不重复弹）。
- **切换到编辑某笔记时（`numId` 分支）复位 `newNoteDraftSettled = false`**，以便从编辑切回新笔记能重新读草稿。
- 附带好处：用户在新笔记页继续输入后，从别处返回再触发 onActivated 时，守卫挡住 `loadDraft`，不会覆盖用户当前输入。

**2026-10-11 修复已校验通过并完成提交推送（本 bug 闭环）：** 抽纯逻辑到临时 `openstudy-vue3-ts\_t.cjs` 模拟 `onMounted`+`onActivated` 双触发做**幂等自测 5/5 全绿**（双触发只弹 1 次、重复 activated 不覆盖用户当前输入、切回写笔记能重读草稿），校验后已删 `_t.cjs`。**提交阶段实测：本轮 `fetch` 得远程 main tip 仍为 `c079c82`（未变，无 non-ff）；暂存复核确认只含 `editor.vue`（worktree 版 diff 收敛 `+11` 行）→ 写提交说明（`.wt_dup\_commit_dup.txt`）→ 提交 → 推送。**
- **worktree 实操（本轮）：** 上轮 `.wt_draft` 已清，本轮重新 `fetch` 得 main tip=`c079c82`（＝上轮草稿提交）→ 重建 worktree → 因 `editor.vue` 长驻脏工作区（耦合大量历史未提交改动），**仍走 worktree 内手工 `edit` 按锚点落本轮 hunk，不整文件拷贝**。
- **幂等守卫 diff 收敛核对（本轮收口）：** worktree 版 `editor.vue` 相对 main 仅 **`+11` 行**（干净收敛，只含幂等守卫：`newNoteDraftSettled` 声明 + `numId` 分支复位 + else 分支 `if (newNoteDraftSettled) return`），diff 内容逐行核对**完全纯净**、无历史遗留混入。
- **校验口径（再次实证）：** worktree 内无 `node_modules`，须**从主工作区跑 `_v.cjs` 校验 worktree 文件**（复用 feedback-frontend-validate-per-file 的单文件口径，先重建 `_v.cjs`）。

**Why:** 草稿自动保存/恢复功能（见 project-note-draft-autosave-feature）上线后，提示弹两次属回归 bug，根因是 keep-alive 双挂载钩子而非 `loadDraft` 本身逻辑错。

**How to apply:** 本仓凡 `<keep-alive>` 内组件，`onMounted` + `onActivated` **首次都会触发**——任何"只应执行一次"的初始化/副作用（读缓存、弹提示、埋点、上报）都必须自己加幂等守卫，不能依赖"两个钩子只会跑一个"。校验走 `_v.cjs` 单文件（见 feedback-frontend-validate-per-file），在主工作区跑、传 worktree/目标文件绝对路径。

**2026-10-11 重要更正（后续复核发现本 memory 的前提与实际代码不符）：**
- **实测 `notes/index.vue`**：第 4 行 `<keep-alive>` **只包 `FrontNotesList`**；**editor 走 else 分支（第 9-11 行）`<component :is="Component" :key="route.fullPath" />`，并不在 keep-alive 内**。故上文"editor 在 keep-alive 内（`notes/index.vue:5`）"是**旧/错误假设**——按当前代码 editor 无 keep-alive → **`onActivated` 不该触发**，"onMounted+onActivated 双触发"的根因描述**与现行代码不符**。
- **更可能的真相**：editor 每次进入=**新建组件**（`onMounted` 1 次、`newNoteDraftSettled` 初值 false → 弹 1 次，属正常）；**"多次弹"更可能来自 `key=route.fullPath`——停留 editor 页时 `route.fullPath` 变化会导致组件销毁重建 → 再弹 1 次**，或用户多次进入（每次都新建、都弹）；另**已核销**：编辑器内**不改 route query**（只 push 离开），故 `watch(() => route.query.id)` 正常。
**2026-10-11 修复定案（跨重建 Toast 去重，已按此实施）：**
- **实现**：新增 `lastSentDraftSig`（声明在 `DRAFT_KEY` 附近）；`loadDraft` **返回值改为「恢复出的草稿签名」`string | null`**（不再返回 bool）；`syncEditorMode`（约 369-377 的 else 分支）的提示逻辑抽成 `maybeToastRestored(sig)` —— 内部用 localStorage 记「签名 + 时间戳」做冷却（**同签名 60s 内不重复弹**）。
- **隐患与配套**：`watch(() => route.query.id, () => void syncEditorMode())` 在 `route.query.id` **从有到无**（编辑笔记 → 写笔记）时会把 `newNoteDraftSettled` 复位为 false → 有重新弹风险，**实由 `maybeToastRestored` 的 60s 冷却期挡住**（同签名 60s 内不重复）✓；**代价=冷却期会误挡新草稿的首次提示 → 故须在发布成功后清掉该 toast 记录**：改 `clearDraft` 时一并清 toast 记录 + 复位签名。改 `loadDraft` 返回值后**须扫全仓调用点**（`syncEditorMode` 约 371 等）。

- **How to apply:** 复现/排查"提示弹多次"前**先读 `notes/index.vue` 现网结构**（editor 是否真在 keep-alive 内、是否有 `:key`），别照搬"keep-alive 双钩子"结论；更稳的修法是**跨组件重建的提示幂等**（时间戳 localStorage + 按草稿 `updatedAt` 在时间窗内只提示一次），而非只依赖组件内 `newNoteDraftSettled` 幂等标记（重建即失效）。上述幂等自测 5/5 全绿结论仍成立（对当时被保护的那个场景有效），但根因定性与"editor 在 keep-alive 内"的判断须以上文更正为准。
