---
name: Node 直跑 TS 模块须转译+剔 CSS import+处理 CJS/浏览器导出差异
description: 本环境用 node 实测前端 TS 模块（如 latex.ts）时的三步改造——ts.transpileModule 转 CJS、剔掉 CSS import 行、mock 掉 CJS interop 不一致的浏览器型依赖（如 DOMPurify）
type: feedback
from: Agent
---

**在本环境（win / CodeArts CLI）想用 node「真实跑」前端 TS 模块（如 `openstudy-vue3-ts\src\utils\latex.ts`）来自测渲染管线时，直接 require(`.ts`) 跑不通，须落一个临时 `.cjs` 脚本做三步改造：**

1. **转译**：用 `typescript` 的 `ts.transpileModule` 把 `.ts` 转成 CJS（模块里 `import katex/marked` 等能解析到项目 `node_modules`）；`latex.ts` 依赖多、直接提取函数不现实，转译整模块更省事。
2. **剔 CSS import**：模块内 `import 'katex/dist/katex.min.css'` 被转成 `require('...css')` → node 解析 CSS 抛错；**转译前删掉该 css import 行**。
3. **mock 浏览器型 CJS 依赖**：`DOMPurify` 在 node 里 CJS interop 的形状与浏览器不同（浏览器里 `default` 是实例），直接跑会报错——**这属环境差异、非代码 bug**（vite/浏览器下正常）；解法是在 `require` 后把其导出 patch 成可用的 `sanitize`（原样返回），以验证渲染逻辑本身。

**Why:** 2026-10-11 实测统一管线 `renderMarkdownWithLatex` 时，先后撞上 CSS `require` 报错与 `DOMPurify` interop 报错；两处都靠改临时脚本（剔 import / 打补丁）而非改产品代码解决。
**How to apply:** 后续要 node 实跑任何含 CSS/浏览器全局的前端 TS 模块做端到端验证时，直接按此三步搭临时 `.cjs`（用完删除）；遇到 interop/shape 类报错先判断是环境差异再决定是否动代码。

**2026-10-11 补充（盲区显式化 + 环境边界）**：
- **此法的结论适用边界**：因必须 mock `DOMPurify`，**所有"渲染出 `<table>`/`<img>`"的实测都绕过了真实白名单 → 对"标签是否被 sanitize 过滤"这类结论无效（假阳性）**；涉及白名单必须改用真实 DOM（jsdom）复核。
- **⚠️ 本环境未安装 `jsdom`** → 上述"用 jsdom 复核"的补正路线**目前不可行**（勿再假设 jsdom 可用）。Agent 定的替代法＝**放弃 node 侧继续实测，直接取浏览器 console 真实报错**（见 `project-formula-table-rendering-in-questionbank` 十七轮：vite dev 下可在 F12 Console 跑 `await import('/src/utils/latex.ts')` 直调源码）。
- **判据纪律**：当"node 实测 + 静态核对全绿、用户浏览器页面仍不对"时，**应判定为"实测环境与真实浏览器环境的差异"而非继续加测**——这是本类验证法的系统性盲区。
- **2026-10-11 补充（mock 盲区被真实浏览器证伪，收口）**：让用户在**浏览器 F12 Console** 直跑 `await import('/src/utils/latex.ts')` + `renderMarkdownWithLatex(真实题干)`，实测 **`✅ 渲染成功 | 含table: true`** → **真实 DOMPurify + 真实 DOM 下 `<table>` 存活**，"白名单是否过滤标签"这一 mock 盲区**就此关闭**。**How to apply**：此后凡涉标签存活/白名单的结论，**优先用浏览器 Console 实跑源码**（一次即可定性），不要再花成本在 node + mock 上反复实测；node 路线仅用于验纯逻辑。

**2026-10-11 且：node 侧验证 Vue 3 响应式行为时，`effect` + 同步 `.then` 的测法不可靠**——Vue `effect` 的调度是**异步**的，`Promise.resolve()` 可能**早于 flush**，会得出"改代理也没触发"的**假象**。**正解=用 `watch(src, cb, { flush: 'sync' })` 做同步对照**（实测据此得决定性结论：改 raw 对象 → watch 不触发；改 `messages.value[i]` 代理 → 触发）。**How to apply：** 任何"改 A 是否触发响应式更新"的 node 微实验，一律用 `flush:'sync'` 的 watch（或 `nextTick` 等 flush），勿用裸 `effect` 下结论。
