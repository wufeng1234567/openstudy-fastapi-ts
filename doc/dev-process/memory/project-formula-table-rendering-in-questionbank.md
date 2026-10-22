---
name: 数学公式与表格在题库展示问题（解析侧已就绪、展示侧待查）
description: 2026-10-11 用户问「数学类型题目的 Word 解析内容怎么展示」——公式 OMML→LaTeX 后端已做，表格被压成文本行丢结构；前端有 LatexRenderer/latex.ts 待核是否渲染
type: project
from: Agent
---

2026-10-11 用户新问题（配两张图：图1=导入题库后的题目样式、图2=Word 里含公式与表格的正常样式）：**"数学类型题目的 Word 解析出来的内容，接下来要怎么展示？"** 关注点是**公式与表格格式**在题库题目里怎么呈现。

**Why:** 这是"文档自动变题库"体验的收尾环节——用户实测导入后（图1）与 Word 原本样式（图2）不一致（含各种表格格式），怀疑前端没渲染或渲染不佳。
**How to apply:** 延续用户"先读代码核实现状、先梳理不写码"的习惯；本轮先摸清「解析产出了什么 → 前端怎么渲染」，再谈改法。

---

**2026-10-11 现状梳理结论（已读源码核实）**：

- **解析侧（后端）已做得不错**：
  - **公式**：`app/services/file_parser.py` **已实现 OMML → LaTeX**（`_omml_to_latex`），产出 `$latex$` 形式（约第 586 行，如 `$\frac{1}{2}$`）。
  - **表格**：每行单元格用 ` | ` 连接成**文本行**（如 `x | y | z`）→ **丢失表格结构**（这是解析侧的真实缺口）。
- **问题落在"展示侧"**：这些 `$latex$` 与 `| a | b |` 文本进入题库题目后，前端须**正确渲染**（公式渲染成漂亮公式、表格渲染成表格）；用户看到图1（导入后）与图2（Word 里）**不像**，说明前端**未渲染或渲染不佳**。
- **前端已有相关资产（待核是否真正接入题干渲染）**：存在 `LatexRenderer` 组件 + `openstudy-vue3-ts\src\utils\latex.ts` 工具，须核对其如何处理公式、题干渲染点是否调用它、是否支持 markdown 表格。

**与本项目已有记忆的关联**：这是 `project-word-image-extraction-to-questionbank`（文档入题库=图片链路，已推 `99f8a98`/`a919e0d`）的**同族遗留**——该记忆开篇即列难点=「数学公式如何合理转化」+「图片如何插入」；图片链路已闭环，**公式/表格展示是本轮新开的另一半**。

---

**2026-10-11 二轮实锤（用户贴出前端实际显示的题目文本后确诊）**：用户贴样本题目原文含 `X\Y | 0 | 1 | 2` / `0 | 0.1 | 0.3 | 0.2` 等行，以及 `$(X,Y)$`、`$Z=\max\{X,Y\}$`、`$E(Z)$`。据"显示形态为纯文本、未渲染"判定两处根因，均为**展示侧**：
- **表格**：后端 `_emit_table` 每行用 ` | ` 连接、**无表头分隔行**（缺 `| --- |`），前端 `renderMarkdownContent` 走 `marked` **认不出是 markdown 表格** → 原样显成一串竖线。
- **公式**：`$...$` **原样带 `$` 显示**（`$` 未消失）→ 题干渲染点**根本没走 `LatexRenderer`/KaTeX**（或未调用渲染函数）。
- **修法方向**（已向用户提出、**尚未动手写码**）：表格改由后端输出标准 Markdown 表格（含表头 `\|---\|---\|`）以贯通全链路；公式逐处核对题干/选项/解析/列表摘要/AI 预览等视图是否都包在 `LatexRenderer` 内。

**How to apply:** 修复落在"后端 `_emit_table` 输出 md 表格语法" + "前端题目各展示点接入 `LatexRenderer`"+可选 KaTeX 字号/表格样式微调；动手前须按 `feedback-verify-code-not-memory-before-plan` 先读 `file_parser.py` 的 `_emit_table` 与题干渲染点。

**卡点（须注意）**：本环境 VLM/多模态对用户两张截图**分析失败**（报「未获取到可用的多模态模型」），Agent 当时无法读图、只能靠用户贴文本定位问题——后续遇"看图"请求勿假设多模态可用。

---

**2026-10-11 三轮实锤（读到源码，根因锁定在 `LatexRenderer` 分支短路）**：
- **`LatexRenderer` 的 computed 分支短路 bug**：`rawLatex` **默认 `true`**，故所有 `<LatexRenderer :content="..." raw-html />` 调用都命中 `rawLatex` 分支 → 走 `renderQuestionContent`（**不认 `$...$`**），`rawHtml` 属性被完全忽略；而能认 `$...$` 的 `renderLatexSafe`（`rawHtml` 分支）与能渲表格的 `renderMarkdownContent`（`markdown` 分支）**永远走不到**。全局搜索确认**无任何模板传过 `markdown` 属性** —— 路径 A（渲表格）从未启用。
- **`latex.ts` 三条函数现状**：`renderMarkdownContent`（认 markdown 表格、**不认 `$`**）、`renderLatexSafe`（认 `$`、**不认表格**）、`renderQuestionContent`（**两者都不认**）。**核心=须造一条同时支持 `$...$` 与 markdown 表格的统一管线**（`renderMarkdownWithLatex`：先渲公式为占位符 → `marked.parse` 渲表格 → 回填公式 HTML；顺序关键，先公式后 md，避免 `$` 内的 `|` 被当表格）。
- **受影响面（不止做题页）**：`QuestionDisplay.vue`（题干/选项/解析）、`ReadingComprehensionDisplay.vue`（组合题）、`QuestionAnalysis.vue`（解析）均包了 `LatexRenderer` 但走失效路径 B；~~`AiQuestionBuilder.vue`（AI 预览）~~〔2026-10-22 该文件已删除〕、`QuestionBuilder.vue`/`questionMain`（题库管理）、`PracticeResult.vue`（交卷 `v-html` 直出）、`QuestionCard.vue`/`QuestionCardGrid.vue`（卡片只换行）**连 `LatexRenderer` 都没用**。

**2026-10-11 用户拍板（本轮定案）**：
- **方案 A 被采纳**——修 `LatexRenderer` 让渲染管线让 `rawHtml`/`markdown` 真正生效，且默认就能渲 `$...$` + 表格（治本·前端核心）。
- **`$...$` 渲染约定定案**：**严格要求 `$...$` 成对且非空、不含空格边界才渲染**（用户原话选定此选项），**不采用**改成 `\(...\)`/`\[...\]` 的方案——为规避 `价格 $5 到 $10` 这类货币金额被误当公式。
- **落地顺序**：修 A（`LatexRenderer` + `latex.ts` 统管线，前提）→ 修 B（后端 `_emit_table` 输出标准 md 表格，含表头分隔行、单元格 `|` 转义）→ 修 C（覆盖未渲染点：`AiQuestionBuilder`/`PracticeResult`/`QuestionCard*` 接 `LatexRenderer`）。
- **行内公式正则收紧为** `\$(?!\s)([^\$\n]+?)(?<!\s)\$`（`$` 后不能是空格、`$` 前不能是空格、内容至少 1 字符）。

**How to apply:** 本轮已进入动手阶段（改造 `latex.ts`），动手顺序与用户拍板一致；后续改动须保证统管线先公式后 markdown，且不得把 `$...$` 约定改为 `\(...\)`。

---

**2026-10-11 修 A（前端 `LatexRenderer`）落地决策**：**默认走 `renderMarkdownWithLatex` 统一管线**（同时渲 `$...$` + 表格），即默认行为从"题目文本（`rawLatex` 短路）"改为"统一管线"，以修掉 `rawLatex` 默认 true 短路 bug。**兼容策略=默认改走统一管线最省事**：既有几十处 `LatexRenderer` 调用方无需逐一改；**选项/答案等短文本走同一管线无害**（不含表格、仅多支持 `$`）。**选项若为纯文本不应渲表格，故保留旧行为开关**——新增 prop `rich`（默认 `true`=走 `renderMarkdownWithLatex`；`rich=false`=`rawLatex` 旧行为）。**改动文件=`openstudy-vue3-ts\src\components\LatexRenderer\LatexRenderer.vue`（改 `computed`）**。

**2026-10-11 修 B（后端 `_emit_table`）落地决策**：把逐行 `add_text` 改为"拼成合法 md 表格块"——**收集行 → 首行当表头 + 加入 `| --- |` 分隔行**（标准 markdown 表格含表头分隔行）。**注意：图片仍要按行紧跟（保留现有 `【图N】` 行为）**。**改动文件=`openstudy-fastapi\app\services\file_parser.py`**。

**2026-10-11 修 B 验证口径**：`py_compile` 编译后端通过；跑现有 `check_file_parser.py`（内含真实 docx fixture 造表）**全 PASS**（表格改动未破坏既有断言——该测试原先断的是旧格式 `a | b`）；**须新增一条断言："表格输出为合法 md 表格"（含表头分隔行）**。**验证入口=`check_file_parser.py` 内的表格 fixture 与断言位置**（本仓文件解析检查脚本）。

**2026-10-11 后端已全绿 → 转入前端校验**：`check_file_parser.py` 新增的两条断言（① 表格是合法 md 表格；② 表格文本含表头分隔行 `| --- |`）已落地并跑通，后端全部 PASS。**下一步=校验前端改动的 3 个文件**（含 `latex.ts`、`LatexRenderer.vue`），按本环境常规=写临时 `_v.cjs` 脚本，并**逐文件单独校验**（见 `feedback-frontend-validate-per-file`）。

**2026-10-11 前端校验通过 + 统一管线 node 实测完成（最新进展）**：
- **前端 3 文件已用 `_v.cjs` 逐文件校验通过**。
- **用 node 真实跑通统一管线 `renderMarkdownWithLatex`**（临时 `.cjs` + `ts.transpileModule` 转 CJS；须删 `latex.ts` 里 `import 'katex/dist/katex.min.css'`（转成 `require(css)` 会报错）+ 把 `DOMPurify` 导出 patch 成可用 `sanitize`——后两者属**环境差异非代码 bug**，浏览器/vite 下正常）。
- **实测结果**：`$(X,Y)$`、`$Z=\max\{X,Y\}$`、`$E(Z)$` 全部渲成 KaTeX HTML、`$` 无残留 ✓；货币 `$5 到 $10` **原样不误伤** ✓（印证收紧正则 `\$(?!\s)([^\$\n]+?)(?<!\s)\$` 有效）；**表格用「旧后端格式」样本未渲染**——因该样本无 `| --- |` 分隔行（`marked` 不认），**恰好印证修 A+修 B 两层缺一不可**（须用新后端产出的合法 md 表格样本再测）。
- 相关技法见 `feedback-node-run-ts-requires-transpile-strip-css-and-mock-dominterop` 与 `feedback-marked-table-latex-pipe-conflict-and-endtoend-testing`。

**2026-10-11 新后端格式重测 → 全部通过（修 A+修 B 两层合起来生效）**：换用新后端产出的合法 md 表格样本再跑统一管线 `renderMarkdownWithLatex`，实测：① 含 KaTeX 渲染 ✓；② **含 `<table>`（表格成功渲染）** ✓；③ 无 `$` 残留 ✓；④ 货币不误伤 ✓；⑤ 行内公式正常 ✓。**证实"前端修 A + 后端修 B 两层缺一不可"的结论成立。**

**2026-10-11 提交阶段（进行中）**：本轮 4 个改动文件=后端 `file_parser.py` + `check_file_parser.py`；前端 `latex.ts` + `LatexRenderer.vue`。**建 worktree 前 fetch 得 main tip = `a919e0d`**（= 多模态图片 data URL 分流修复那次提交）。**核对 4 文件相对 main 的 diff stat 与各自 hunk 分布，与预期完全对应**（`file_parser` 2 处 / 测试 1 处 / `LatexRenderer` 2 处 / `latex.ts` 3 处）→ **无历史夹带，4 文件均可整文件拷贝**（见 `feedback-git-worktree-isolation` 的 hunk 纯净性判据）。已删临时脚本，进入 worktree 提交流程。

**2026-10-11 提交阶段（进展）**：worktree `.wt_math`（基于 main tip `a919e0d`）内已拷入 4 文件（`file_parser.py`/`check_file_parser.py`/`latex.ts`/`LatexRenderer.vue`）、核对 worktree 状态、**worktree 后端编译通过**；提交说明写入 `.wt_math\_commit_math.txt`，正逐文件暂存准备提交。

---

**2026-10-11 全部闭环（修 A + 修 B 已推送）**：
- **提交 `9e08382` 已推 gitcode/main（区间 `a919e0d..9e08382`），worktree `.wt_math` 已清理**。本轮 4 文件均已合入 main：前端 `latex.ts`（正则收紧 `/\$(?!\s)([^\$\n]+?)(?<!\s)\$/g` + 新增统一管线 `renderMarkdownWithLatex`「先公式→占位符→marked 表格→回填公式→DOMPurify」）+ `LatexRenderer.vue`（加 `rich` prop 默认 true 走统一管线，修掉 `rawLatex` 短路）；后端 `file_parser.py`（`_emit_table` 改输出标准 md 表格=首行表头+`| --- |` 分隔行；新增 `_md_cell` 转义单元格内 `|`；表格内插图仍照发）+ `check_file_parser.py`（新增 2 条"表格是合法 md 表格"断言，全 PASS）。
- **端到端实测（node 直跑）确认**：公式全部渲成 KaTeX、无 `$` 残留、表格渲出 `<table>`、货币 `$5 到 $10` 不误伤、行内公式正常。

**⚠️ 重要提示（老数据兼容性，非对称）**：
- **表格**：用户库里**已有旧题目文本仍是旧格式（无 `| --- |` 分隔行）→ 那批老数据仍会显示成竖线**。**必须重新导入/重新生成题目**才会得到新格式（后端 `_emit_table` 已改，新导入即正确）。
- **公式**：因渲染逻辑（前端）已改，**老数据也能立即正确显示，无需重导**。
- **验证建议**：重启后端 + 刷新前端，重新导入一份带公式和表格的 Word，看题干是否显示成"公式 + 整洁表格"。

**遗留（修 C 尚未做，待用户决策）**：`PracticeResult.vue`（交卷页）、`AiQuestionBuilder.vue`（AI 搭建预览）、`QuestionCard*.vue`（卡片列表）等**尚未接 `LatexRenderer`** 的点，仍不渲染公式/表格。Agent 已问"要我继续覆盖这些渲染点吗"，**用户未答，勿擅自动手**。

---

**2026-10-11 四轮（推送后再验用户复现，坐实"老数据仍不渲染"）**：用户再次贴同一段旧格式文本（`X\Y | 0 | 1 | 2` 三行、无 `| --- |` 分隔行）报"表格没渲染"。Agent 复核后**确认 `9e08382` 已在远程 main**（本地 `gitcode/main` ref 停在 `a919e0d` 系 fetch 在 worktree 内致滞后，fetch 刷新后确认）；工作区 `latex.ts` 已含修复 ✓；**写临时脚本（`openstudy-vue3-ts\_t.cjs`，node + ts.transpileModule）用用户贴的"原样文本"实跑统一管线**，实测=**旧格式文本表格不渲染**（`marked` 不认无分隔行）、**公式正常渲染** ✓。**结论=用户贴的这段是修复前导入的老数据（非修复后新数据，故非新 bug）**，完全印证记忆已有的"老数据兼容非对称：表格须重导、公式立即正确"。

**Agent 给出两条路供用户选（用户未答）**：
- **路径 1（容错）**：在 `latex.ts` 统一管线 `marked.parse` **之前**加预处理——当遇"连续多行、每行含 ≥2 个 `|`、列数一致、但无分隔行"时**自动补一行 `| --- |`** 使其成合法 md 表格 → **老数据无需重导即可渲染**。**风险=可能误伤正文里连续多行带 `|` 的文本（概率低、加列数一致约束）**。
- **路径 2（重新导入）**：用新后端（`_emit_table` 已改）重新导入一份 Word，新数据天然带分隔行。
- Agent **推荐"路径 1 + 路径 2 都做"**：路径 1 治当前可见问题、路径 2 已实现保证新数据合法。**Agent 另问了用户两件事：① 该文本是修复前旧数据还是修复后重导？（若后者则尚有别的 bug）② 选哪条路？两问均未答，勿擅自动手。**

**2026-10-11 五轮（用户拍板 → 采用路径 1 容错，已开工）**：用户明确回复**"需要适配两种格式"**（即采纳**路径 1**），并强调一条前置事实作为设计依据——**Word 里的表格本身不是 Markdown 格式**（Word 表格是 OOXML 表格结构），故**不能假设输入是"合法 md 表格"**，必须在**解析时就把 Word 表格转成统一的中间形态**，而不是靠"输入本来就是 md 表格"。**用户要求"想好怎么适配这两种格式"**。

据此 Agent **落地容错预处理 `normalizePipeTables`**（加在 `latex.ts`，置于 `renderMarkdownWithLatex` 第①步公式占位化之后、第②步 `marked.parse` 之前）：
- **目标=两种格式同时可渲染**：格式 1（新后端产出/标准 md 表格，含 `| --- |` 分隔行）→ `marked` 直接认；格式 2（老数据/无分隔行的连续带 `|` 裸表格文本）→ 自动补分隔行后渲染。
- **判据（保守，避免误伤）**：连续 ≥2 行为"裸表格行"（每行含 **≥2 个 `|`**）；**列数一致**；这组行**后面紧跟的不是分隔行**（若已有 `| --- |` 说明已是 md 表格，跳过）；仅在**块级**（前后有空行或行边界）时处理。
- **转换**：在第 1 行后插入 `| --- | --- |` 分隔行。

**2026-10-11 九轮收敛（三重保险均已实测 + 进入 worktree 提交）**：制表符容错 `normalizeTabTables` 已落地 `latex.ts`（位于 `normalizePipeTables` 之后接进管线），**node 实测 8/8 全绿**（制表符表格可渲、单行 TAB 与列数不一致均不误伤、竖线表格仍正常、制表符+公式混排正常）。本轮改动两文件=**前端 `latex.ts` + 后端 `prompts.py`**（提示词层英文规则）；临时实测脚本（`_v.cjs`/`_t.cjs`）已删，**走 worktree 提交流程**。

**How to apply:** 路径 1 已获用户授权并在实施中（两格式兼容）。用户再报"表格没渲染"时，**先确认样本是否含 `| --- |` 分隔行**；若为老数据（无分隔行），路径 1 落地后应能自动补分隔行渲染，届时若仍不渲染再排查 `normalizePipeTables` 判据；公式在老数据上应立即正确、勿误判。**关键设计原则（用户强调）：Word 表格非 md 格式，适配须在解析/预处理层做形态归一，勿假设输入合法。**

**2026-10-11 五轮收尾（判据折中定型 + 实测 9/9 全绿）**：初版 `isPipeRow` 判据=「每行 ≥2 个 `|`（≥3 列）」，node 实测 8/9——**唯一失败=两列裸表格 `a | b`（每行只 1 个 `|`）不被识别**。**Agent 提出放宽到"≥1 个 `|`、≥2 行、列数一致"会误伤常见的两列正文**，最终**折中定型判据**：允许 2 列（1 个 `|`），但**要求每个 `|` 两侧有空格（` | `）或首尾有竖线**——即只认"真正的表格形态"（`a | b`），正文里的 `a|b`（无空格）不算；列数须 ≥2 且一致。用户贴的样本 `X\Y | 0 | 1 | 2`（3 个 `|`）本就命中。同步调整 `countCells` 与其协调（`a | b` 记 2 列）。**改后复跑实测 9/9 全绿**：两种格式均可渲染，边界（单竖线、公式内竖线、列数不一致）均不误伤。`latex.ts` 改动后已语法校验 + 清理临时脚本（`_t.cjs`/`_v.cjs`）。
**How to apply:** 后续再动 `normalizePipeTables`/`isPipeRow`/`countCells` 判据时，勿把两列裸文本（无空格分隔）纳入，会引入正文误伤；"表格没渲染"排查顺序=先看是否含 `| --- |`、再看 `|` 两侧是否有空格。

**2026-10-11 六轮（两格式兼容提交阶段）**：`latex.ts` 单文件（含 `normalizePipeTables`）走 worktree 提交。流程=先删临时脚本（`_t.cjs`/`_v.cjs`）→ `fetch` 实测 main tip = `9e08382`（未变）→ 查 `latex.ts` 相对 main 的 diff = **`+78/-3`，2 个 hunk**（① 新增 `normalizePipeTables` ② 接进统一管线）**全属本轮、纯净** → 建 worktree。（hunk 纯净性判据与"本地 ref 滞后须 fetch"纪律见 `feedback-git-worktree-isolation`；本轮再证"单文件、2 块均落在预期区域即可整文件搬运"。）

**2026-10-11 六轮收尾（已提交推送 `ff9526c`）**：worktree 内拷入 `latex.ts` → 查 worktree 状态 → 写提交说明 → 暂存并复核（**暂存正确**）→ 提交推送。**推送成功区间 = `9e08382..ff9526c HEAD -> main`**（`latex.ts` 单文件、`normalizePipeTables` 两格式兼容），worktree 已清。**故远程 main 最新 tip = `ff9526c`。**

**2026-10-11 七轮（用户反馈「刷新后仍没表格」→ 定位到第三种输入形态，非配置 bug）**：
- 用户实测刷新前端后**仍无表格**，贴出的文本是 **`X\Y\t0\t1\t2` 三行（制表符 `\t` 分隔、完全无竖线）**，并称「没有那些表格竖线」。
- **实锤：该文本形态既不是格式 1（含 `| --- |` 的合法 md 表格），也不是格式 2（`X\Y | 0 | 1 | 2` 裸竖线表格）**——grep 全仓**无任何「制表符/表格转文本」命中**，说明**不是前端某处把 `|` 替换成了 `\t`**；`normalizePipeTables`/`isPipeRow` **只认含 `|` 的行**，对 `\t` 分隔文本**天然无效**（这正是「刷新后仍没表格」的直接原因）。
- **推断真凶=LLM 生成题目时把 Word 表格"重写"成了制表符文本**（模型从喂入的 md 表格读入、输出 JSON 时用 `\t` 分隔），即**表格在"模型产出 JSON"这一环就已丢结构**，根本没走 `_emit_table`。**待验**：`question_manage.batch_import`/题干落库链路是否在某处对题干做了替换/清洗把 `|` 变 `\t`。
- **用户给出的方向（本轮最新定案，优先于修 C）**：**「应该要做好提示词工程，告诉 LLM 回传 JSON 数据的时候，自动把 Word 表格文本转化成 md 格式，然后我们再采取其他措施兜底。」** → 即**首选在提示词层要求 LLM 输出合法 md 表格**，**前端/后端容错机制仅作兜底**；用户对"纯靠兜底补分隔行"的路线**不再首选**。
- **How to apply（后续排查顺序更新）**：「表格没渲染」须按三形态判：① 含 `| --- |`（合法 md，直接渲染）② 裸竖线 `a | b`（无分隔行，`normalizePipeTables` 兜底）③ **制表符 `a\tb`（无竖线，当前两条路径都不覆盖）**。第 ③ 类的正解是**提示词工程让 LLM 直接产出 md 表格**（见 `feedback-no-json-raw-jargon-to-end-users` 与提示词相关记忆），而非继续扩 `normalizePipeTables`。

**2026-10-11 八轮（真凶实锤 + 修复落点已定，正在实施）**：
- **真凶 100% 坐实**：`question_manage.batch_import` **只做 `_replace_image_markers`（`【图N】` → `<img>`）、不做任何 `|` → `\t` 转换** → **制表符是模型自己写出来的**。即模型在生成题目 JSON 时**用自己的方式（`\t` 分隔）"重绘"了表格**，而非原样保留后端喂入的 md 表格。**故第 ⑦ 轮"待验 batch_import 是否清洗"已排除**（不是落库链路把 `|` 变 `\t`）。
- **用户判断被证实**：用户提的**「提示词工程：告诉 LLM 回传 JSON 时把 Word 表格转成 md 格式」= 正解**。修复落在**提示词层**而非继续扩前端/后端兜底。
- **修复落点 = `app/services/ai/prompts.py` 的 `AGENT_DOC_BUILD_WORKFLOW`（"文档建库"工作流提示词，约 445-510 区）**：该工作流**第 4 条讲了保留 `【图N】`，但没有"表格必须保留/输出为 Markdown 表格"的规则** → 模型因此自行用制表符重写表格。
- **拟加规则（英文，守 P11d）**：**表格必须原样保留/输出为标准 Markdown 表格（`|` + `| --- |` 分隔行），禁止改成制表符/空格/纯文本** —— 插在 `AGENT_DOC_BUILD_WORKFLOW` 第 4 条之后。
- **How to apply**：改 `AGENT_DOC_BUILD_WORKFLOW`（及其他进系统提示词的规则段）时**正文必须全英文**（P11d 扫系统提示词中文，见 `feedback-probe-model-side-chinese-whitelist`）；改完 `py_compile` + 扫汉字 + 跑 `_toolpref_probe`。

**2026-10-11 九轮（用户拍板三重保险 + 前端链路排查已闭环）**：
- **P11d 自检通过**：本轮新增内容全为英文，**未新增任何模型侧中文**（`【图N】` 标记属既有、非本轮新增，不计入）→ `_toolpref_probe` P11d 通过；临时脚本已清理。
- **用户拍板两项**（Agent 提出后获确认）：① **再加「制表符表格」前端容错 = 三重保险**（在提示词规则之外）；② **前端链路也要排查一遍**，确认**不存在 `|` → TAB 的替换**。
- **前端链路排查结论（Task 并行核查）**：**前端不存在任何 `|`→TAB 的转换**，制表符**确系模型输出本身**——诊断闭环（与前面"模型自写制表符"结论互证）。
- **第三重保险实现落点**：在 `openstudy-vue3-ts\src\utils\latex.ts` 的 **`normalizePipeTables` 之后新增 `normalizeTabTables`**（制表符表格 → md 表格），并接进统一管线。判据（Agent 设计）=**连续 ≥2 行、每行含 ≥1 个 `\t`、列数一致** → 转成 md 表格。
- **Agent 明确的能力边界（重要）**：`_emit_table`（后端）+ `normalizePipeTables`（前端）都只认含 `|` 的文本；**"制表符表格"（`X\Y\t0\t1\t2`）两边都救不了**（既无 `|` 给 `normalizePipeTables` 识别、也不是 md 表格）→ **故根本仍靠提示词让模型不输出制表符**，`normalizeTabTables` 是第三重兜底。
- **How to apply**：本条反映"三重保险"分工——① `AGENT_DOC_BUILD_WORKFLOW` 英文规则让 LLM 输出 md 表格（治本）② `normalizePipeTables` 兜底裸竖线老数据 ③ `normalizeTabTables` 兜底制表符文本。再遇"表格没渲染"须先判输入属三形态中哪一种，再对号入座。

**2026-10-11 九轮提交阶段（三重保险本轮改动已进 worktree，待推送）**：
- **本轮（三重保险）改动文件 = `prompts.py` + `latex.ts` 两个**。建 worktree 前 fetch 得 **main tip = `ff9526c`**（= 八轮 `normalizePipeTables` 提交）；查两文件相对 `ff9526c` 的 diff = **共 3 个 hunk 全属本轮、纯净**——`prompts.py` @470（`AGENT_DOC_BUILD_WORKFLOW` 表格规则）、`latex.ts` @280（新增 `normalizeTabTables`）+ @382（接进统一管线）。判纯净 → 整文件拷贝进 worktree。
- **已建 worktree、拷入两文件、查状态、worktree 内编译后端**（编译验证口径同既往：worktree 无 `.env`，只做 `py_compile`，依赖 DB 的探针回主工作区跑）。
- **How to apply**：本轮推送后的新 tip 以实际 fetch 为准（`project-gitcode-push-requires-fresh-pat` 须同步更新）；两文件 hunk 落点=判纯净快判据的又一实例。

**2026-10-11 十轮（三重保险已推送 `560fee4`；用户改判"数据有问题"，转入查库）**：
- **三重保险本轮已推成功**：worktree 提交并推送 **`ff9526c..560fee4 HEAD -> main`**（2 文件：`prompts.py` 的 `AGENT_DOC_BUILD_WORKFLOW` 第 4b 条「题目里表格必须原样输出为 Markdown 表格（表头 + `| --- |` + 数据行），禁止用 TAB/空格/纯文本重写；源表格非 md（如 Word 表格）须先转 md 再输出」+ `latex.ts` 的 `normalizeTabTables`），worktree 已清。**故远程 main 最新 tip = `560fee4`。**
- **验证结果**：`prompts.py` 编译通过、**P11d 复检无新增模型侧中文**（仅既有 `图`）；前端 `normalizeTabTables` **node 实测 8/8 全绿**（TAB 表格 → `<table>` ✓、公式仍渲染 ✓、单行 TAB / 列数不一致不误伤 ✓、既有竖线表格仍正常 ✓）。
- **⚠️ 用户随后反馈「还是一样」（刷新后仍无表格）并改判**：**"我怀疑是数据有问题，你把数据修正一下 —— 概率论与数理统计题库"** → 用户不再认为纯是渲染/提示词问题，**明确要求直接修正该题库的库内数据**（首次把矛头指向"落库的旧数据本身"）。**这才是本轮真正的用户意图，修 C（渲染点覆盖）已被暂时推后。**
- **Agent 已开查库**：新建探针 `openstudy-fastapi\tests\_probe_qbank_data.py`，探查「概率论与数理统计题库」题目实际存储文本；**首探发现表结构不同 → 转而查 `question_bank` 与 `question_main` 的真实列名**（尚未出结论）。**How to apply**：下一轮先确定这两表列名与题目正文列，把该题库存的 TAB 形态文本真正读出来，再定性"数据是否需就地修正"；用户已知 `normalizeTabTables` 能渲染 TAB 形态，但库里老文本"还是一样"说明渲染链可能未真正命中该页面/或数据另有问题——须以查库实测为准，勿再凭推断下结论。

**2026-10-11 十一轮（用户下令"去数据库里查" → 已连库并读到题目数据）**：
- **用户明确要求直接查数据库**（原话："去数据库里面查啊 先查看 v2 项目链接的是哪个数据库"）→ 不再靠推断，须落库实测。
- **v2 连接库已确认**：v2 项目（`openstudy-fastapi/.env`）连的是 **PostgreSQL（pgvector）**，`DB_DRIVER=postgres`，`localhost:5432`，库名 **`openstudy_v2_pgsql`**，用户 `root`/密码 `123456`，连接串 `postgresql://root:123456@localhost:5432/openstudy_v2_pgsql`；**`.env` 注释明确"改回 `mysql` 可回滚 MySQL，业务代码无需改"**（DB 双轨切换设计）。
- **探针列名修正**：`_probe_qbank_data.py` 首探因 `question_bank`/`question_main` 表结构不同而失败，**实际题目表列名为 `bank_name`**（非臆测的写法）→ 探针改用 `bank_name` 后成功。
- **已读到关键数据**：**「概率论与数理统计题库」的 `bank=1175`**（用户新建的库、共 4 题）为要查对象；探针初显的是 `id=102`（属另一库/形态），须以 `bank=1175` 为准。
- **How to apply**：查题库数据一律用同步 psycopg2 直连 `openstudy_v2_pgsql`（沙箱 asyncio 不可靠，见 `feedback-sandbox-blocks-asyncio-event-loop`）；筛选条件用 `bank_name`/`bank` 列；下一步=读出 `bank=1175` 四题的实际题面文本，确认是否 TAB 形态、再决定是否就地修正库数据。

**2026-10-11 十二轮（库内数据实读 → 推翻"制表符形态"判断，根因再锁修 C）**：
- **`bank=1175` 四题已全部读出**：**只有 `id=2772`（二维随机变量）的题干含表格**，其余三题无表格。
- **⚠️ 重大纠正（推翻前几轮的"制表符"结论）**：库里**真实存储的是"竖线形态" `X\Y | 0 | 1 | 2`（裸竖线表格、无 `| --- |` 分隔行），不是制表符 `\t`**！用户此前贴的 `\t` 形态**系展示/复制层的 Tab 化呈现**（即复制题面时被 Tab 化），**而落库数据本身是竖线形态** → **这正是 `normalizePipeTables` 覆盖的"格式 2"**（每行 3 个 `|` ≥2 ✓、三行均 4 列一致 ✓、无分隔行 ✓）。
- **决定性实测**：**用库里这段"原样文本"跑统一管线 `renderMarkdownWithLatex` → 表格渲染成功（生成 `<table>`）、公式亦正常** ✓ → **数据无问题、渲染函数也能处理它**。
- **故"还是一样不渲染"的真因 = 用户所看的页面没走这条渲染管线**，**根因锁定回"修 C（渲染点覆盖）未做"**：用户看的页面很可能是**题库管理/题目预览/AI 搭建预览**，仍用 `{{ }}` 或 `v-html` 直出、**未接 `LatexRenderer`**。（前几轮"数据形态为制表符、两边都救不了"的结论在这一轮被库内实读推翻——**"TAB 形态"从未真正落库**。）
- **附带小瑕疵（新）**：表头 `X\Y` 渲染成 `XY`——**表格单元格里的 `\` 被当转义吃掉**（`\Y` 丢反斜杠）；**不影响表格结构渲染**，属独立小问题，暂未修。
- **当前动作**：Agent 已删临时实测脚本，**正等用户确认"你看的是哪个页面"**，以决定修 C 的覆盖面。
- **How to apply**：**再遇"表格不渲染"，勿再凭用户贴出的文本形态下结论**——用户贴的 `\t` 可能是展示层 Tab 化产物，**必须先用 psycopg2 读库内原样文本**再定性；`normalizePipeTables` 的"格式 2"兜底对本库老数据**是有效的**；后续重点=把未接 `LatexRenderer` 的页面（`PracticeResult.vue`/`AiQuestionBuilder.vue`/`QuestionCard*.vue` 等，即修 C）覆盖到位。

**2026-10-11 十三轮（用户确认页面 + 下令扩大覆盖 → 修 C 正式开工）**：
- **用户亲口确认报障页面**：**做题页 `http://localhost:3167/front/questionPractice/1175/practice/sequential`**（对应组件 `QuestionDisplay.vue`，已用 `LatexRenderer`）；并下令**「其他涉及浏览题目的页面也一起做」**，总目标是**优化用户体验**。→ 修 C 的覆盖面由用户拍板= 做题页 + 其他所有涉及浏览题目的页面（`PracticeResult.vue` 交卷结果页、`AiQuestionBuilder.vue` AI 搭建预览、`QuestionCard*.vue` 卡片列表等）。
- **Agent 实证方向**：确认 `LatexRenderer` 默认已走统一管线（+ 上一轮修复确在工作区）后，**转而核查做题页 `QuestionDisplay.vue` 的 `formatMainContent` 是否对题干做了转义/清洗把 `|` 或 `$` 破坏**——即"已接 `LatexRenderer` 但走失效路径"的可能。**How to apply**：做题页已接 `LatexRenderer` 却"还是一样"时，优先怀疑该页自身的题干预处理函数（`formatMainContent`）破坏了表格/公式语法，而非渲染组件本身。

**2026-10-11 十四轮（`formatMainContent` 已排除；发现新嫌疑 `transformQuestionForDisplay`）**：
- **`formatMainContent` 已排查通过**：它只替换填空题占位符、**不破坏 `|`/`$`** ✓；题干走 `LatexRenderer`（默认统一管线）✓ → 做题页"理论上应该渲染"。**故"还是一样不渲染"必有别处**。
- **新嫌疑锁定=上游数据转换**：`currentQuestion.question` 的值从哪来、是否被**上游数据转换**破坏（如 `questionType` 映射时把 `questionText` 转义）→ Agent 转去查 `PracticeComponent.vue` 如何构造 `currentQuestion`（含字段映射/转义）。
- **关键发现**：`PracticeComponent.vue` 内**多处调用 `transformQuestionForDisplay(q)`**（约 323/363/457/636 行）；**正在核查该函数是否对题干/`analysis` 字段做了转义/破坏**。**How to apply**：再查做题页为何不渲染时，**下一步落点=`transformQuestionForDisplay` 对 `question`/`analysis` 字段的赋值**（前半段 `formatMainContent` 已排除，勿重复查）；若该函数把表格/公式语法转义掉，则修点在此。
- **并列的第二个待修点**（见 `feedback-marked-table-latex-pipe-conflict-and-endtoend-testing`）：表头 `X\Y` 单元格内 `\` 被当转义吃掉 → 渲成 `XY`；修渲染点覆盖时**顺带修此问题**（用户本轮要求"顺带修"）。

**2026-10-11 十五轮（`transformQuestionForDisplay` 已排除、整条链路实证贯通；根因转判"用户跑的前端不是最新代码"）**：
- **`transformQuestionForDisplay` 已排查通过**：其主 return 对 `question: q.questionText`、`analysis: q.analysis` **原样透传、无任何转义** ✓ → 做题页数据链路（题干/解析）**全程无破坏**。
- **`question` 字段对 `type=5`（essay/问答题）不置空**，而 **`id=2772` 正是 `question_type=5`（essay）**；核查 `PracticeComponent.vue` 对 essay 型的分支渲染：**overview 模式（约第 38 行）与普通模式（约第 102 行）都渲染 `QuestionDisplay`** → 均走 `LatexRenderer` 统一管线 ✓ → **做题页链路彻底贯通**。
- **决定性实测（用库内 id=2772 真实题面原文跑统管线）**：竖线表格 + 公式经当前代码**渲染成功**（产出 `<table>` ✓、KaTeX ✓）→ **代码能渲、数据没问题**。
- **⇒ 最终结论：用户运行的前端不是最新代码**（`LatexRenderer` 的 `rich` 默认走统管线是 `9e08382` 之后才有的）。**自查实证逐环节全绿**：库内数据 ✅ / `renderMarkdownWithLatex` 实测能渲 ✅ / 做题页 `QuestionDisplay` → `LatexRenderer` 已接 ✅ / `transformQuestionForDisplay` 原样透传 ✅ → **唯一不绿的是"用户看到的不渲染"**。
- **关键操作结论（高复用）**：`9e08382`/`ff9526c`/`560fee4` **全是前端改动**，**必须重新构建前端（`npm run build` 或重启 dev server 热更）才生效**；**单纯刷新浏览器/F5 不够**（生产构建有缓存）。→ **再遇"改了前端但用户页面没变化"，须先排除"跑的是旧构建/缓存"，别急着重查代码。**
- **Agent 另发现一个库内数据真问题（顺带，非表格不渲染之因）**：`id=2772` 是 `question_type=5`（essay），但其 `answer` 字段里塞了**完整答案+解析**、题干里还有 `<img>`——**"组合式内容塞进单字段"是导入时的结构问题**（导入侧结构瑕疵，与表格渲染无关）。
- **遗留待验点**：若重建前端后**仍不渲染**，下一个怀疑点=`LatexRenderer` 的 **DOMPurify 白名单**在该构建里把 `<table>` 过滤掉了（Agent 实测时用的是 mock sanitize，未覆盖真实 DOMPurify 白名单）。
- **用户要求（本轮）**：**"其他涉及浏览题目的也一起做"** → 修 C 覆盖面=做题页 + 其他所有涉及浏览题目的页面；**但 Agent 建议先确认做题页重建后是否已好，再统一覆盖，避免在错误方向批量改**（用户未答，勿擅自动手）。

**2026-10-11 十六轮（先排除"缓存/旧构建"再查真实 DOMPurify；另确认跑的是 vite dev）**：
- **用户仍报"表格还是没出来"** → Agent 放弃继续推断，改为**直接看运行中前端真正加载的构建产物里有没有修复代码**（定性缓存/旧构建 vs 真代码问题）。
- **运行模式已确认（新事实）**：前端 dev 脚本 **`port: 3167`** 与用户访问的 `http://localhost:3167` 一致 → 用户跑的是 **`npm run dev`（vite dev server）**。**vite dev 实时编译源文件、改 `latex.ts`/`LatexRenderer.vue` 会热更，理论上应生效** → 既未生效，**必有一处真正的代码问题，不再是缓存**。**故"重启 dev server / 重新构建"这条解释在本轮被排除（对 dev 模式不适用）。**
- **新第一嫌疑前移到真实 DOMPurify 白名单**：核查 `latex.ts` 的 `renderMarkdownWithLatex` 最后一步 **DOMPurify 的 `ADD_TAGS` 白名单**——**配置看起来正确**（`table/thead/tbody/tr/th/td` 都在 `ADD_TAGS`），但 Agent 自省指出**此前所有实测用的都是 mock `sanitize`（见 `feedback-node-run-ts-requires-transpile-strip-css-and-mock-dominterop`），从未验证真实 DOMPurify 是否真把 `<table>` 留下** → **这是本环境 node 实测法的既有盲区**。
- **待办**：装 `jsdom` 在 node 里跑**真实 DOMPurify** 的 sanitize，直接判定 `<table>` 是否被真实白名单过滤（先查项目是否已含 `jsdom` 测试依赖）。
- **How to apply**：本环境 node 实测前端渲染管线时，**mock sanitize 会给"渲染成功"的假阳性**；凡涉及标签白名单的结论（表格/`<img>` 等）**必须用 jsdom + 真实 DOMPurify 复核一次**再收口。

**2026-10-11 十七轮（jsdom 路线被否决 → 转向"拿浏览器 console 真实报错"，并新增 essay 分支嫌疑）**：
- **jsdom 路线不可用**：本环境**未安装 `jsdom`** → "装 jsdom 用真实 DOMPurify 复核"这条待办**无法执行**，Agent 放弃。**教训**：本环境做前端渲染实测时，**不要假设 jsdom 可用**（与"不假设多模态可用"同类纪律）。
- **Agent 的自我反思（高价值）**：已多轮"node 实测 + 静态核对"全绿，但**用户页面就是不行** → **说明实测环境与浏览器真实环境有差异**（mock `DOMPurify` / 无真实 DOM），继续 node 实测是无效重复。**故定案换法：直接取"浏览器控制台的真实报错"**——`v-html` 渲染失败（KaTeX 抛异常 / `DOMPurify` 未定义等）通常会在 console 报错，这是**最直接有效的一步**。
- **dev server 缓存/旧构建已彻底排除（实机核实）**：① `vite dev server` 在跑（**pid 2752**、端口 `3167`）→ vite dev 实时编译，代码必为最新；② **从 dev server 拉取编译产物，确含 `renderMarkdownWithLatex` / `normalizePipeTables` / `normalizeTabTables`（命中 5 次）** → **跑的确是含全部修复的最新代码，缓存这条解释正式作废**。→ **剩余可能只在"浏览器运行时"**（如真实 DOMPurify 过滤、KaTeX 运行时抛异常）。
- **新增嫌疑（question 字段分支）**：核 `QuestionDisplay.vue` 模板 40-70：**`type !== 'cloze' && type !== 'readingComprehension'` 的 `v-if` 分支渲染 `currentQuestion.question`**，**essay（type=5）满足该条件 → 走 `currentQuestion.question` + `LatexRenderer`** ✓（此前怀疑的"essay 表格落在 `mainContent`、52 行 `hasMainContent` 不满足"这条**已被排除**）；另核查过 52 行绑的是 `formatMainContent(currentQuestion.mainContent)`。**故题干确实以 `LatexRenderer` 渲染，链路正确。**
- **给用户的可执行诊断法（Agent 已交付）**：让用户在**浏览器 F12 Console 粘贴运行**一段脚本——`await import('/src/utils/latex.ts')`（vite dev 支持直接 import 源码）→ 调 `renderMarkdownWithLatex(真实题干)` 并打印 `Object.keys(mod)`、输出前 500 字、`/<table/` 与 `/class="katex/` 命中情况，异常 `console.error(e)` → 直接暴露真实运行时报错。
- **How to apply**：再遇"改了前端、dev 模式、编译产物已含修复、用户页面仍无效果"时，**不要再堆 node 实测**——直接让用户给**浏览器 console 报错**（诊断脚本 import `/src/utils/latex.ts` 实跑），并以"dev server 编译产物是否含修复代码"作为排除缓存的硬证据。

**2026-10-11 十八轮（用户质疑"有时只是单纯你的代码问题，不是更新问题吧" → Agent 拉取 dev server 编译产物实锤"代码/缓存无问题"）**：
- **用户修正 Agent 的归因偏误**："有没有可能 只是单纯你的代码问题 不是什么更新问题呢？" → 用户不接受"旧构建/缓存/环境差异"式解释，要求直接验证代码本身。Agent 承认此前一直在替自己找理由、没落地验证。
- **实锤（拉运行中 dev server 返回给浏览器的 `LatexRenderer.vue` 编译产物）**：**产物 100% 含修复**（`renderMarkdownWithLatex`、`rich` 分支都在）→ **不是代码/缓存问题**（再次坐实"dev 编译产物含修复"这条硬证据）。
- **故问题收窄到"浏览器运行时"**：Agent 转而拉 `latex.ts` 的编译产物核查 `DOMPurify` 用法——**这是唯一尚未实证的环节**（承接十六/十七轮的 mock sanitize 盲区）。
- **How to apply**：用户对"更新/缓存/环境"类解释敏感且要求实证；遇"前端改了页面没效果"须**先用 dev 编译产物自证代码已生效**，再把怀疑点收敛到真实浏览器运行时（DOMPurify 真实白名单 / KaTeX 运行时异常），勿以"缓存"敷衍。

**2026-10-11 十九轮（关键突破：浏览器 Console 实测成功 → 定性为"做题页未拿到这段文本"，转查做题页实际传入值）**：
- **用户在浏览器 F12 Console 直跑 `await import('/src/utils/latex.ts')` + `renderMarkdownWithLatex(真实题干)`，实测 `✅ 渲染成功 | 含table: true`** → 产出含 `<table>` 的完整 HTML、KaTeX 公式正常。**这是首次"真实浏览器运行时"（非 mock）实证**，一举推翻此前所有"DOMPurify 白名单过滤 `<table>`"的怀疑 → **真实 DOM 下 `<table>` 能存活、渲染函数与 DOMPurify 配置均无问题**。
- **⇒ 定性收敛（Agent 结论）**：数据 ✅ / 渲染函数 ✅ / dev 编译产物含修复 ✅ / DOMPurify 白名单 ✅ → **唯一可能 = 做题页那个 `<LatexRenderer>` 根本没拿到这段文本 / 未执行到该渲染路径**，即**做题页渲染的字段不是 Console 里测的那段文本**。
- **做题页题干的两个候选渲染点（`QuestionDisplay.vue`）**：第 52 行 `formatMainContent(currentQuestion.mainContent)`（组合题主干）；第 59-61 行 `currentQuestion.question`。**`id=2772` 是 `question_type=5`（essay/问答题）**，走 `question` 字段。
- **Agent 交付的分叉诊断脚本**：在做题页（那道题显示时）用 `document.querySelector('.question-title'/'...').__vueParentComponent` 逐级上溯取 `props/setupState.currentQuestion`，打印其 `question`/`mainContent`/`type` 真实值；并给出了"含 table + img + 公式"的完整题面重测脚本。
- **下一步三选一（据做题页题干容器 `.question-title` 的 `outerHTML`/`currentQuestion` 值定性）**：① 含 `<table>` → 表格**已渲染只是无边框/无样式**（`.question-title` 无 `:deep(table)` 样式）→ 只需加 CSS；② 是 `<p>X\Y | 0 | 1 | 2 ...`（纯文本带竖线）→ 渲染没生效（页面拿到的值/路径不对）；③ 空 → 字段没传进来。
- **How to apply**：再遇"上游实测能渲、页面就是不渲"，**直接用浏览器 Console 测"页面实际拿到的字段值"**（而非测"题干原文"）；二者不一致即命中根因——**排查重点从"渲染函数"彻底转到"做题页数据流/字段绑定"**。真实浏览器 Console 的实测优先级高于一切 node + mock 实测。

**2026-10-11 二十轮（分叉①命中：`<table>` 其实已渲染，真因=**零样式**；修法=加表格 CSS）**：
- 用户贴出 `.question-title` 的 `outerHTML` → **DOM 里真有 `<table>`** ⇒ `renderMarkdownWithLatex` **正常跑通**、`<table>` **未被 DOMPurify 滤掉**（与十九轮浏览器 Console 结论一致）。**定性收敛到十九轮分叉①："表格渲染了，但没有任何样式"** —— 浏览器默认 `<table>` 无边框、无内边距、无对齐，看起来像"一堆数字挤成一块"、不像表格。
- **根因**：`QuestionDisplay.vue:588` 的 `.question-title` **只有 `:deep(img)`、`:deep(p)`，没有 `:deep(table)`**；且 **`LatexRenderer.vue` 自身完全没有 `<style>`**（见 `feedback-latexrenderer-vhtml-needs-nonscoped-table-style`）。
- **修法定案**：给 `LatexRenderer.vue` 加**表格样式**（边框、居中、单元格内边距，像 Word 表格）。**位置选 `LatexRenderer` 的 `.latex-content`**（全局共用渲染容器，所有接入页面自动受益）；**须非 scoped**（`v-html` 注入的 DOM 不受 scoped 约束）。
- **同轮并列第二修**：表头 `X\Y` 被 `marked` 当转义吃成 `XY` → 在 `normalizePipeTables` 内对单元格 `\` 转义为 `\\`（`hasSep` 与裸表格两条路径都处理；公式已占位化故安全），详见 `feedback-marked-table-latex-pipe-conflict-and-endtoend-testing`。
- **How to apply**：**报"表格没出来"时，先分清"没渲染"与"渲染了但没样式"**——取 `outerHTML` 看有没有 `<table>` 即可一锤定音；有标签则纯 CSS 问题（无需再查渲染链/白名单/数据流）。修 C（覆盖其他浏览题目页面）仍待做。

**2026-10-11 二十一轮（二十轮两处修复已完成前端校验 + 实测，进入 worktree 提交阶段）**：
- **两处修复均已落地**：① `LatexRenderer.vue` 加非 scoped 表格样式（`.latex-content` 内表格边框/内边距/对齐，修"渲染了但零样式"）；② `latex.ts` 的 `normalizePipeTables` 内对表格单元格 `\` 转义为 `\\`（修表头 `X\Y` 被吃成 `XY`）。
- **前端校验通过**：用 `_v.cjs` 分别校验 `latex.ts` + `LatexRenderer.vue` 两个文件（须逐文件单跑，见 `feedback-frontend-validate-per-file`）。
- **实测通过（node `.cjs` + `ts.transpileModule`）**——`X\Y` 转义 + 表格仍生成：① 含 `<table>` ✓ ② 含 KaTeX ✓ ③ **表头 `X\Y` 保留了反斜杠**（不再变 `XY`）✓。表格 CSS 属纯样式无法 node 测（须靠真实浏览器/人工目视）。
- **提交阶段**：临时脚本已删 → fetch 得 **main tip = `560fee4`** → 查两文件相对 main 的 diff stat + hunk，走入 worktree 提交流程。
- **How to apply**：本轮推送后新 tip 以实际 fetch 为准；修 C（覆盖 `PracticeResult.vue`/`AiQuestionBuilder.vue`/`QuestionCard*.vue` 等未接 `LatexRenderer` 的浏览题目页面）**仍待用户决策、勿擅自动手**。

**2026-10-11 二十二轮（二十轮两处修复已进 worktree，待提交推送）**：
- **hunk 纯净性复核通过**：本轮改动 **3 个 hunk 全落在本轮改动区**（`LatexRenderer.vue` 尾部新增非 scoped 表格 `<style>`；`latex.ts` 的 `normalizePipeTables` 内新增 `escapeCells` 转义单元格 `\` + 其调用点）→ **纯本轮、无历史夹带** ✓（判据同 `feedback-git-worktree-isolation`）。
- **已建 worktree `_wt_tblcss`**、拷入两文件（`LatexRenderer.vue`/`latex.ts`）、核对 worktree 状态、提交说明写入 `_wt_tblcss\_commit_tblcss.txt`，**正逐文件暂存并复核准备提交**。
- **How to apply**：本轮推送后新 tip 以实际 fetch 为准（`project-gitcode-push-requires-fresh-pat` 须同步更新）；修 C 仍待用户决策、勿擅自动手。

**2026-10-11 二十三轮（表格 CSS 修复已推送闭环 `b772fc1`）**：
- worktree `_wt_tblcss` 内两文件（`LatexRenderer.vue` + `latex.ts`）已提交并**推送成功：`560fee4..b772fc1 HEAD -> main`**，worktree 已清 → **远程 main 最新 tip = `b772fc1`**。
- 本轮修复内容=① `LatexRenderer.vue` 加非 scoped 表格样式（单元格边框 + `padding: 6px 12px` + 居中；表头灰底加粗 + 斑马纹；`overflow-x: auto` 防宽表撑破）；② `latex.ts` 的 `normalizePipeTables` 加 `escapeCells`（单元格 `\` → `\\`，修表头 `X\Y` 变 `XY`）。
- 验证：两文件 `@vue/compiler-sfc` 校验通过；node 实测含 `<table>` ✓、KaTeX ✓、表头 `X\Y` 保留反斜杠 ✓；**表格 CSS 属纯样式无法 node 测，须真实浏览器人工目视**。
- **Agent 交给用户的验证动作**：**刷新做题页**，表格应显示为带边框、有表头底色的正经表格；**若刷新后仍无边框**，疑"样式被更高优先级覆盖"（做题页 `.question-title` 的 scoped 规则或 Element Plus 全局样式压制）→ 让用户贴 F12 Elements 里选中 `<table>` 的 Styles 面板截图（看 `.latex-content table` 规则是否被划掉）据此调优先级。
- **修 C（未接 `LatexRenderer` 的其他浏览题目页面）仍待用户决策**：`PracticeResult.vue`（交卷页）、`QuestionCard*.vue`（卡片列表）、`AiQuestionBuilder.vue`（AI 预览）等；Agent 已再问"要现在一并覆盖吗"，**用户未答（转而提了新的文档解析进度需求），勿擅自动手**。
