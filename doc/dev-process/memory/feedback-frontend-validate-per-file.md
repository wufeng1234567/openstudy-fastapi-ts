---
name: 前端 SFC 校验须拆成单文件逐个跑
description: 本环境用 _v.cjs（@vue/compiler-sfc+typescript）校验前端时，一次传多个文件会失败，须一个文件一条命令分开校验
type: feedback
from: Agent
---

**在本环境（win/cmd / CodeArts CLI）用项目根 `openstudy-vue3-ts\_v.cjs` 校验前端改动时，一次传入多个文件会报错；必须拆成「一个文件一条命令」逐文件单独校验。**

**Why:** 2026-10-11 校验本轮改的 3 个前端文件时，一条命令传全部文件的批量校验失败（Sandbox Error），改为拆单文件跑即可逐个出结果。批量模式在该临时脚本上不可靠。**2026-10-11 再次实证：用重写的 `openstudy-vue3-ts\_v.cjs`（@vue/compiler-sfc + typescript）单文件校验 `AiChatStream` 通过，且该脚本每次都要重写（上轮已删）。** 另：`_v.cjs` 亦可单文件校验**纯 TS**（非 SFC）文件——2026-10-11 用它校验 `src/utils/request.ts` 通过。

**How to apply:**
- 校验前端 SFC/TS 时，对每个待校验文件**分别**执行一次 `_v.cjs`，不要拼一条多文件命令。
- 先确认 `_v.cjs` 存在（和 `@vue/compiler-sfc` 依赖可用）；该临时脚本若已被删则**重建**（`@vue/compiler-sfc` + `typescript`）再跑，用完删除。
- **worktree 内不能就地跑 `_v.cjs`（worktree 是干净检出、无 `node_modules`）——须在主工作区执行脚本、并把 worktree 目标文件的绝对路径作为参数传入。**（2026-10-11 校验 `.wt_draft` 内 `editor.vue` 即如此。）
- 相关：本环境 esbuild 被禁用（见 feedback-frontend-vite-build-esbuild-flake），前端校验只能走 `_v.cjs` 这条路。
