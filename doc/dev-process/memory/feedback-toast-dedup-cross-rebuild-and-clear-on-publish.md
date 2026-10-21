---
name: 前端轻提示须做跨组件重建幂等（localStorage 签名+时间戳），发布/成功后清记录
description: 2026-10-11 定案——进入页面类轻提示不能只靠组件内 settle 标记（重建即失效），须用 localStorage 记「签名+时间戳」做冷却期去重，并在发布成功后清掉记录
type: feedback
from: Agent
---

**2026-10-11 更正（用户改口径）：`request.ts` 防重拦截器的「拦截逻辑要保留」，只去掉弹窗。** 用户先说「操作太快了…直接干掉」，随后改为「**不提示就行，改成静默拦截高频点击，防抖节流那种操作**」——即**保留高频重复请求的拦截（防抖/节流式拦掉重复点击）**，**命中时静默 `Promise.reject`、不弹 `ElMessage`**。**关键：不要误改成"仅 `console.warn` 后放行"**——放行=不再拦截，违背诉求；正解＝保留 reject、只删弹窗。**Why:** 用户要的是防狂点保护仍在、只是别弹噪音提示。**How to apply:** 面向 C 端的限流/防重提示，"去提示"与"去拦截"是两个独立诉求，务必问清/确认；默认可保留拦截、去掉弹窗。这与"进入页面类轻提示须跨重建幂等"是两码事。**2026-10-11 补充：请求拦截器里以 `__repeatSubmit`（防重拦下的标识）reject 后，`request.ts` 的「响应拦截器」也必须对该标识加静默分支——否则会被通用错误分支接住、可能仍弹 error 提示；即请求侧 reject 与响应侧静默须成对处理。** **2026-10-11 已落地推送：提交 `d9a8e32`（区间 `56af46e..d9a8e32 HEAD -> main`），改动收敛为 `request.ts` `+21/-6`（静默拦截 + 注释 + 响应侧静默分支）。**

前端「进入页面/恢复类」轻提示（如「已恢复上次未发布的草稿」）**必须做跨组件重建的幂等**：把源数据**签名 + 时间戳**（如 localStorage 记 `sig` + time）持久化，同一签名在冷却期内（如 60s）只提示一次；**并在"发布成功/该场景结束"时清掉这条 toast 记录，让下一次新草稿能正常提示**（否则冷却期会误挡新提示）。

**Why:** 本轮用户报「已恢复…草稿」连续弹多次；组件内 `newNoteDraftSettled` 幂等标记在组件**销毁重建（`key=route.fullPath` 变化 / 多次进入页面）后立即失效**，挡不住重复提示。localStorage 跨重建仍存活，故只有持久化签名+时间戳才能跨重建去重。另有一个隐患：`watch(() => route.query.id, () => void syncEditorMode())` 在 route.query.id「从有到无」（编辑→写笔记）时会复位 `newNoteDraftSettled=false` 而重新弹——**实靠 maybeToastRestored 的 60s 冷却期挡住**（同签名 60s 内不重复）。但冷却期反过来会误挡新草稿 → 故须在发布成功（`clearDraft`）时一并清掉 toast 记录并复位签名。

**How to apply:** 在本仓给任何"进入页面弹一次"的轻提示复用时：①提示判重键取源数据签名（如草稿 `updatedAt`/内容签名），不取组件内布尔标记；②记录写 localStorage（签名+时间戳），设冷却窗口；③在业务成功路径（发布/提交/清空草稿 = `clearDraft`）里清该记录；④实现手法=让 `loadDraft` 返回**恢复出的草稿签名**（`string | null`，而非 bool），调用侧 `maybeToastRestored(sig)` 统一判重。见 project-note-draft-restore-double-toast / project-note-draft-prompt-too-frequent-and-save-highfrequency。
