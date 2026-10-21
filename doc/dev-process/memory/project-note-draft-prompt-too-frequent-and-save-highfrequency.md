---
name: 草稿恢复提示频繁弹出 + 「操作太快了」限流（saveDraft 高频打后端）
description: 2026-10-11 用户报——「已恢复上次未发布的草稿」触发过多条，且很容易出现「操作太快了，请稍候再试」
type: project
from: Agent
---

2026-10-11 用户报（紧接 422 修复之后）：`GET /notes/note/draft` 422 问题修好了，但出现两个新现象：
1. **「已恢复上次未发布的草稿」提示触发过多次数**——用用户原话「加多条 已恢复上次未发布的草稿」，即多次进入就弹多次/多出一条。
2. **「操作太快了，请稍候再试」**——用户形容「很容易触发、操作太快了」。

**Agent 本轮定位（诊断进行中，尚未定案）：**
- **「操作太快了，请稍候再试」来源（本已查实）**：**后端 `notes.py` / 后端代码里查无此句** → 出处实锤在**前端 `openstudy-vue3-ts\src\utils\request.ts` 的「防重复提交」拦截器（约 135-146 行）**：判定条件=**同一 url + 同 data（JSON.stringify 相同）+ 距上次请求 < 500ms** → **拦下请求并在拦截器内直接 `ElMessage` 弹「操作太快了，请稍候再试」**（请求发出**前**就弹）。**注意：这是"防重复提交"式提示，与「已恢复…草稿」是两条不同的提示，别混为一谈。**
- **高频打后端嫌疑点（`src/views/front/notes/editor.vue`）**：`saveDraft` 现在**每次内容变化都调 `saveNoteDraft(payload)` 打后端**（约 477 行），而 `watch`（约 638）监听 5 个字段、**500ms 防抖** → 用户打字时**每 500ms 就发一次 `PUT /notes/note/draft`** → 这是「操作太快」的最可能来源。
- **「弹多次」的另一嫌疑**：`syncEditorMode` 的 else 分支守卫 `if (newNoteDraftSettled) return`（约 355 行）会被 **`numId` 分支（约 341-343）复位**——在「写笔记」与「编辑某笔记」之间来回切换（或 `route.query.id` 变化）时，`numId` 有值 → 复位 `newNoteDraftSettled=false` → 切回写笔记又读草稿又弹一次。另有 `onMounted` + `onActivated`（keep-alive 双钩子）+ `watch(() => route.query.id)` 三处都可能触发 `syncEditorMode`（详见 project-note-draft-restore-double-toast）。
- **`numId` 细节**：`route.query.id` 为空字符串时 `Number("")=0`（falsy → 走 else ✓）；`"0"` 亦 falsy → else ✓。

**2026-10-11 本轮深挖（`request.ts` 拦截器已读全 + 「操作太快」命中链路定论）：**
- **命中链路**：`saveDraft` 走 `PUT /notes/note/draft`，payload 含 `title/content/...`；`watch` 500ms 防抖触发。**若连续两次触发间隔 < 500ms 且 payload `JSON.stringify` 完全相同 → 命中 `request.ts` 防重拦截 → 弹「操作太快了」**。触发场景：打字时 watch 抖动/切字段导致短间隔内两次相同 payload 的 PUT。
- **关键坑**：拦截器的 `ElMessage` 在**请求发出前**就弹，`.catch` **挡不住**（不能靠"静默 catch"消掉弹窗）→ **根因是"不该在高频路径上发重复 PUT"**，而非"提示没静默"。
- **「操作太快」修复方向（治 A）**：①`saveDraft` 后端同步**内容未变则不发**（缓存上次发送的 payload 字符串比对，相同跳过）；②后端同步用**更长防抖**（如 2s）与本地 localStorage 的 500ms 解耦（本地保持即时兜底）。
- **`getNoteDraft`（GET）不受此拦截**（GET 无 data）→ **「已恢复…草稿」弹多次与本拦截器无关**，不是同一根因。

**2026-10-11 重大更正：`notes/index.vue` 实际结构与旧 memory 假设矛盾（editor 不在 keep-alive 内）。**
- **实测代码**：`notes/index.vue` 第 4 行 `<keep-alive>` **只包 `FrontNotesList`**（list 路由 v-if 分支）；**editor 走 else 分支（第 9-11 行）`<component :is="Component" :key="route.fullPath" />`，无 keep-alive 包裹**。
- **推论**：editor **不在 keep-alive 内** → 正常情况下 **`onActivated` 不该触发**（无 keep-alive 即无 activated 钩子）。**故 project-note-draft-restore-double-toast 中"keep-alive 首挂载 onMounted+onActivated 双触发 loadDraft"的根因描述，与当前 `notes/index.vue` 实际代码不符**（该 memory 记录的 `notes/index.vue:5` 在 keep-alive 内属旧/错误假设）。
- **更可能的真相**：editor 每次进入都是**新建组件**（`onMounted` 跑 1 次）→ `newNoteDraftSettled` 初值 false → 弹 1 次，属正常；**"弹多次"更可能来自 `key=route.fullPath`——若停留在 editor 页时 `route.fullPath` 变化（query 变化），组件会被销毁重建 → 又弹 1 次**；或用户**多次进入页面**（每次都新建组件、都弹）。
- **已核销一条嫌疑**：**编辑器内不改 route query（只 push 离开）** → 故 `watch(() => route.query.id)` 正常、不会因路由微变反复触发。
- **「已恢复」弹多次修复方向（治 B）**：提示**跨组件重建的幂等**——用**时间戳记录**（如 localStorage `note_draft_toast_at`），**同一草稿（按 `updatedAt`）在时间窗内（如 10s）只提示一次**。

**2026-10-11 已闭环推送：提交 `d9a8e32`（区间 `56af46e..d9a8e32 HEAD -> main`）= 治 A「静默拦截」修复落地——`request.ts` 请求侧静默 `reject`（`__repeatSubmit`）+ 响应侧静默分支成对 + 轻提示/注释收敛，worktree `.wt_toast` 已清。** 以下为用户定案与实施细节。

**2026-10-11 实测口径（对应用户原话「不提示，但保留静默拦截高频点击=防抖节流」）：`request.ts` 命中重复提交（同 url + 同 data + 间隔 < 500ms）时改为「静默节流」——①**不弹任何提示**（`ElMessage` 全删）②仅一条 `console.warn` + `reject({ __repeatSubmit: true })`，窗口内后续同请求丢弃、连点只发第一发；③响应拦截器新增 `__repeatSubmit` 分支 → 直接静默 reject、不落通用红提示。** 另：**`editor.vue` 的草稿自动保存 `watch` 防抖（约 638`watch` 内）仍是 500ms（未随拦截窗口改动）**——实施时看清「500ms」出现两处：`request.ts` 防重拦截窗口（本轮 1000→500 收紧）与 `editor.vue` saveDraft 防抖（仍是 500ms）。

**2026-10-11 后续又有一轮以 `56af46e` 为基线、worktree `.wt_tab` 提交 push 的 `prompts.py` 改动（提交说明 `.wt_tab\_commit_tab.txt`），该提交 hash 窗口内未确证：**

**2026-10-11 交付状态：`d9a8e32` 已推 main、worktree 已清；此修复已收尾但用户尚未实机验证。** `request.ts` 在主工作区混有历史未提交改动（`clientToken` 豁免 @76），故从 main 干净基线建 worktree **手工只落本轮改动 `+21/-6`（无夹带）**——`request.ts` 亦属"不可整文件搬运"（同 `editor.vue`/`notes.py`）。

**2026-10-11 用户定案（治 A 落地）：不弹提示，但要保留「静默拦截高频重复点击」本身（防抖/节流）。**
- 用户历次表述演进：①先「操作太快了，请稍候再试 就不该出现这个提示 直接干掉」→ ②修正为「**不提示就行，改成静默拦截高频点击，防抖节流那种操作**」。
- **最终语义**：「操作太快了」这个**弹窗**要去掉，但**防重复提交的拦截逻辑本身不能删**——命中高频重复点击时**静默拦下请求（`Promise.reject`，不弹任何 `ElMessage`）**，即"防抖/节流式地拦掉真正的重复请求，只是不弹窗"。
- **实施（改 `openstudy-vue3-ts\src\utils\request.ts` 防重拦截器）**：命中重复（同 url+同 `JSON.stringify(data)`+距上次<500ms）的 `if` 分支**保留 reject（静默拦下）**，**仅去掉 `ElMessage` 弹窗**。
- **关键教训**：中途曾改为「仅 `console.warn` 后放行」——这是**错的**，因为**放行就不拦截了**，违背「静默拦截」诉求；正确做法是**保留 reject、只删弹窗**。
- **保留 import**：`ElMessage` 在 request.ts 仍有其他引用，故 import 不动。
- 校验：建 `openstudy-vue3-ts\_v.cjs` 单文件校验 `request.ts`（TS 语法），校验后删除。

**2026-10-11 提交阶段重要发现（`request.ts` 也耦合历史未提交改动，须 worktree 手工落本轮改动）：**
- **工作区 `src/utils/request.ts` 相对 main 是 `+36/-6`，但本轮预期只 ~20 行** → 说明混入历史改动。逐 hunk 核对得 **3 hunk：@76(+15)=`clientToken` 豁免、@121(+25)、@197(+10)**。
- **@76 的 `clientToken` 豁免（+15）不是本轮改动、main 上也没有** → 是**工作区里的历史未提交改动**（"clientToken 豁免"是之前某轮做的）。**故 `request.ts` 不能整文件搬运，须在 worktree（main 干净版）内按文本锚点手工只落本轮改动（静默拦截 + 注释）** —— 与 `editor.vue`/`myNotes/index.vue` 同病（整文件耦合历史改动）。
- **main 版基线 vs 工作区版文案不同（关键）**：main 版 `request.ts` 是 **`interval = 1000`** + 提示 **`'数据正在处理，请勿重复提交'`**；工作区版是 **`'操作太快了，请稍候再试'`**。**用户抱怨的提示「操作太快了，请稍候再试」= 工作区（未提交）版**，**main 上根本没有这句** → **证明用户跑的是未提交的工作区版**，故修复必须在 main 基线上重新落地、而非仅改工作区。
- **worktree 上落本轮改动目标**：①`interval` 500（与工作区对齐，保守取 500；main 是 1000）；②命中时**不弹提示**（main 版无 `ElMessage`，但有 `console.warn` + reject）→ **改为静默 `reject`**（去掉 `console.warn`/提示，保留拦截）。

**Why:** 草稿"后端存储 + 前端双源合并"上线（`c112d00`）后，`saveDraft` 由「只写 localStorage」变成「每次变化都打后端」，把原本纯本地的防抖写放大成对后端的 500ms 高频写；而 `request.ts` 的防重拦截器（同 url+同 data+<500ms）会把"内容没变但被 watch 连续触发"的重复 PUT 拦下并弹「操作太快了」——故是两个独立根因：**高频重复 PUT 撞防重拦截**（A）与**组件重建/重复进入导致提示不幂等**（B）。

**How to apply:** 排查「操作太快了，请稍候再试」时**认准 `src/utils/request.ts` 的防重复提交拦截器（约 135-146）**（判定=同 url+同 `JSON.stringify(data)`+<500ms；弹窗在请求前发，`.catch` 挡不住）——**别默认是后端限流**，也别指望靠静默 catch 消掉。治本＝让高频路径不发重复 PUT（**内容未变不发 + 后端同步降频解耦**）。排查"提示弹多次"**不要照搬"keep-alive 双钩子"结论**——`notes/index.vue` 里 **editor 实际不在 keep-alive 内**（keep-alive 只包 `FrontNotesList`），须按最新代码结构判断（重点看 `key=route.fullPath` 引起的重建 + 多次进入），并用**时间戳/updatedAt 幂等**让提示跨重建去重。
