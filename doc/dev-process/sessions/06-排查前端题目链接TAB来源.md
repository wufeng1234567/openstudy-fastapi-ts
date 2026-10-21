# 排查前端题目链接TAB来源 (@explore subagent)

> 会话 ID：`ses_ed4f1cb58ffeeH4oAnp6p89nn8`  
> 时间：2026-10-11 21:01:53 — 2026-10-11 21:04:10  
> 消息数：143  
> 所属项目：OpenStudy（FastAPI + Vue3 全栈学习平台）

---

## 对话记录

**用户提问**

```
在前端仓库 <PROJECT>\openstudy-vue3-ts 中，排查**是否存在某处代码把题目文本里的 `|`（竖线）替换/转换成了 TAB（制表符 `\t`）**，或把表格结构"拍平"成制表符分隔文本。

背景：用户看到导出的题目里表格变成了 `X\Y\t0\t1\t2`（制表符分隔、无竖线）。后端已排查（`question_manage.batch_import`、`file_parser._emit_table` 都不做 `|`→`\t`）；现在要确认**前端**有没有这种转换。

请彻底排查（thorough 级别）：
1. 全局搜索 `\t`（TAB 字符）、`\\t`、`\u0009`、`chr(9)`、`split('\t')`、`join('\t')`、`replace(/[|]/g, '\t')` 一类把 `|` 换成 TAB 的写法。
2. 重点查**题目展示/编辑/导入**相关组件：`src/components/PracticeComponent/*`、`src/components/QuestionCard*.vue`、`src/components/MyQuestion/*`、`src/views/front/studio/**`（AiQuestionBuilder / QuestionBuilder）、`src/views/questionMain/**`、`src/views/questionBank/**`。
3. 查**表格渲染**相关：`src/utils/latex.ts`、`src/utils/*markdown*`、`src/components/LatexRenderer/*`——看有没有对表格做"转成制表符/去竖线"的处理。
4. 查**题目组装/序列化**：任何把题目对象拼成字符

…（后略）
```

**用户提问**

```
<system-reminder>重要提示：你必须使用简体中文回复，包括内部思考和推理过程也必须使用简体中文。即使用户用英文提问，也必须用简体中文回复。</system-reminder>
```

**AI**

我将系统性地排查前端代码中是否存在把 `|` 或 `<table>` 转成制表符的转换。先从目录结构和全局搜索开始。

> 🔧 `bash` — description=列出前端 src 目录结构

> 🔧 `bash` — description=列出 components 与 utils 目录

**AI**

现在进行全局搜索关键模式。

> 🔧 `bash` — description=搜索反斜杠t转义写法

> 🔧 `bash` — description=搜索制表符其它写法

**AI**

环境不支持 `-P`，改用默认正则语法。

> 🔧 `bash` — description=搜索反斜杠t转义写法

> 🔧 `bash` — description=搜索制表符其它写法

**AI**

`\\t` 的搜索被 `\n`（换行注释）污染了。需要精确搜索制表符相关的实际用法。让我用更精确的模式。

> 🔧 `bash` — description=搜索split/join/replace制表符

> 🔧 `bash` — description=过滤出真正的制表符操作

**AI**

注意到 `src/utils/latex.ts:238` 有 `t.split('|')`，这可能是竖线相关处理。让我读取该文件并搜索 `|` → TAB 的转换模式。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\latex.ts

> 🔧 `bash` — description=搜索竖线与制表符共存行

**AI**

发现关键线索：`src/composables/useAgentChat.ts:122` 有 `.split('|')`。让我读取该处上下文，同时检查 latex.ts 剩余部分（是否有把 `|` 表格转 TAB）。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\composables\useAgentChat.ts

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\latex.ts

**AI**

重要发现：`useAgentChat.ts` 的 `stripMarkdownTables` 把 markdown 表格转成 `：` 或 ` · ` 分隔（不是 TAB）。这解释了为什么"无竖线"，但分隔符是冒号/点而非 TAB。需要确认这个函数何时被调用。同时看 latex.ts 是把 `|` 表格补成合法 markdown（保留竖线），不是转 TAB。

继续排查 TiptapEditor、QuestionFullEditor、编辑器相关的 HTML→文本 逻辑，以及 `<table>` 处理。

> 🔧 `bash` — description=查stripMarkdownTables调用点

> 🔧 `bash` — description=搜索innerText/textContent/table处理

**AI**

发现多处 `innerText`/`textContent` 采集（`src/utils/index.ts:146`、`src/utils/questionUtils.ts:21`、`src/components/MyQuestion/QuestionCard.vue:248`）。这些是 HTML→文本的关键嫌疑点——`innerText` 会把 `<td>` 用 TAB 连接。让我详细读取这几处。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\index.ts

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\questionUtils.ts

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\MyQuestion\QuestionCard.vue

**AI**

这些是 HTML→文本工具函数（用 `textContent`，不会产出 TAB，`textContent` 只是拼接无分隔符）。但需确认 `html2Text`/`getPlainText` 是否被用于题目提交路径。现在重点排查富文本编辑器（TiptapEditor、QuestionBuilder、AiQuestionBuilder）的 HTML→文本导出逻辑。

> 🔧 `bash` — description=列出编辑器目录并查html2Text调用

> 🔧 `bash` — description=搜索编辑器取内容方法

**AI**

TiptapEditor 用 `getHTML()`（保留 `<table>`，非转文本）。现在重点看 QuestionBuilder 和 QuestionFullEditor——它们是题目组装/序列化的关键。查找是否有把 HTML/表格转成纯文本或制表符的地方，以及 `questionText` 的组装。

> 🔧 `bash` — description=搜索studio组件table/text处理

> 🔧 `bash` — description=搜索replace制表符及字面TAB

**AI**

未发现把 `|`/`<table>` 转 TAB 的 replace/split/join。注意到 `AiQuestionBuilder.vue:405` 和 `:851` 有 `stripMarkers`/`replace(/【图\d+】/g,...)`。现在检查 AiQuestionBuilder 的 `replaceImageMarkers` 和表格相关处理，以及 QuestionFullEditor 全文。同时检查 latex.ts 前 180 行和 MarkedButton/LatexRenderer 的表格渲染。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\QuestionFullEditor.vue

> 🔧 `bash` — description=搜索文本抽取函数名与用法

**AI**

QuestionFullEditor 用 TiptapEditor（`getHTML()`）。现在看 AiQuestionBuilder 的 `stripMarkers`（:849）、`replaceImageMarkers`（:1442）以及提交处（:1525 附近），确认对 questionText 的处理是否涉及表格/竖线。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

**AI**

`replaceImageMarkers` 只替换图片标记，`stripMarkers` 只去图片标记。现在读 AiQuestionBuilder 提交题目处（1520-1560），看 questionText 如何落库。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

> 🔧 `bash` — description=搜索批量导入调用

**AI**

AiQuestionBuilder 直接透传 `questionText`（只替换图片标记），没有任何表格→制表符转换。现在检查 `addQuestionMain` API 及 `questionMain` 相关处理，以及 `views/questionMain`、`views/questionBank`、`PracticeComponent`、`QuestionCardGrid` 的题目处理逻辑。

> 🔧 `bash` — description=查API与相关目录

> 🔧 `bash` — description=定向搜索相关目录制表符与竖线

**AI**

我的 grep 匹配到了所有行（因为 `|` 在正则中）。让我用更精确的固定字符串搜索。同时检查 PracticeComponent/QuestionDisplay 和 QuestionCardGrid 的题目渲染。

> 🔧 `bash` — description=精确固定串搜索制表符操作

> 🔧 `bash` — description=查markdown渲染调用点

**AI**

只有两处 `.split('|')`，且都是"解析"竖线表格（latex.ts 补分隔行、useAgentChat 转冒号/点），不做 `|`→TAB。现在读取 `src/utils/markdown.ts` 全文，并检查 LatexRenderer 和 renderMarkdownContent 是否对表格有转制表符逻辑。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\markdown.ts

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\LatexRenderer\LatexRenderer.vue

**AI**

LatexRenderer 走 `renderMarkdownWithLatex`，只做渲染（`|` → `<table>`），不产出制表符。现在检查 TiptapEditor 的 HTML 输出与表格扩展，确认富文本编辑器是否有 `<table>`→纯文本 导出逻辑，并看 PracticeComponent/QuestionDisplay 的题目展示与 `renderQuestionContent`。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\latex.ts

**AI**

latex.ts 全部是对 `|` 表格的"识别/渲染"，无 TAB 生成。现在检查 TiptapEditor 是否含 table 扩展及导出逻辑，以及 QuestionDisplay/QuestionCardGrid/PracticeComponent 的题目渲染与提交路径。

> 🔧 `bash` — description=查TiptapEditor表格与导出

> 🔧 `bash` — description=查题目展示渲染方式

**AI**

TiptapEditor 用 `getHTML()` 输出（含 `<table>` 标签，不转文本）。题目展示用 `v-html` 直接渲染。现在检查 `TiptapEditor` 的 `getHTML` 附近（640-660）确认没有额外文本转换，以及 `QuestionCardGrid` 的 `formatQuestionText`。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\TiptapEditor\index.vue

> 🔧 `bash` — description=定位formatQuestionText

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\QuestionCardGrid\QuestionCardGrid.vue

> 🔧 `bash` — description=查PracticeComponent与MyQuestion文本处理

**AI**

`QuestionCard.vue:248` 的 `truncateHtml` 用 `textContent`（拼接无分隔符，不会产 TAB），且仅用于卡片摘要截断展示，不提交。现在检查 QuestionDetailDialog 和 PracticeComponent 的 `QuestionDisplay.vue` 展示方式，以及提交答案路径是否涉及题目文本转换。

同时确认 PracticeComponent 是否收集题干文本（如错题本提交时把题目 HTML 转文本）。

> 🔧 `bash` — description=定向搜索文本抽取

> 🔧 `bash` — description=搜索其他TAB生成方式

**AI**

已确认前端无 `String.fromCharCode(9)`/`\u0009`/`\x09`。现在检查 QuestionBuilder.vue 是否有导入解析（AI 结果 → 题目）中对表格的处理，以及 exports（导出）相关功能，因为用户提到"导出的题目"。搜索导出相关代码。

> 🔧 `bash` — description=搜索题目导出功能

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\QuestionBuilder.vue

**AI**

题目导出用的是 RuoYi 通用 `download` 后端接口（xlsx），与前端文本转换无关。QuestionBuilder 的 AI 题目归一化也是透传字段（`textToHtml` 只在无 HTML 时包裹 `<p>`，见 questionUtils.ts:4-12，不涉及竖线/TAB）。

现在做最后一轮彻底核查：搜索所有 `|`→空白/换行/分隔符 的 replace，以及 `\t` 作为分隔符字面量，并检查 `doc-parse.ts` 解析（Word 解析可能在客户端）。

> 🔧 `bash` — description=搜索竖线替换操作

> 🔧 `bash` — description=查前端Word/docx解析

**AI**

关键发现：`src/utils/doc-parse.ts:8` 明确说 docx 解析是"表格转成 `|` 分隔文本"（竖线，不是 TAB）。让我完整阅读 doc-parse.ts 的解析流程，确认表格转成什么分隔符——这是最可能相关的部分。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\doc-parse.ts

**AI**

确认：doc-parse.ts 的表转 `|` 是**后端** `file_parser.py` 的行为，前端只是接收 `blocks`/`textContent` 原样透传，不做 `|`→TAB 转换。

现在检查 AiQuestionBuilder 如何处理解析出的 blocks/textContent（是否有表格相关处理），以及 doc-parse.ts 剩余部分和 PracticeComponent/QuestionDisplay 的提交路径。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\doc-parse.ts

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

**AI**

确认 `parsedTextContent` 直接来自后端 `data.textContent`（透传，无转换）。现在检查 AiQuestionBuilder 把 `parsedTextContent`/`parsedBlocks` 送给 AI 出题及落库的路径，确认无 `|`/`<table>` 处理。同时检查 PracticeComponent 错题提交时的题目文本处理，以及 `useQuestionPractice`（题目练习组合式）是否有文本转换。

> 🔧 `bash` — description=查解析文本使用点

> 🔧 `bash` — description=查练习与题库题目文本

**AI**

`parsedContent` 可在 UI 中编辑（textarea），但用户手动编辑不算代码转换。`buildMarkedText()` 值得检查——它处理 blocks 组装文本（可能是图片标记拼接）。让我读取 `buildMarkedText`（约 :805 附近）。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

> 🔧 `bash` — description=最终扫描制表符字面量

**AI**

全库扫描结果一致：没有任何一处把 `|` 或 `<table>` 转成制表符 `\t` 的代码。`buildMarkedText` 用 `\n` 连接 blocks，不含 TAB。

现在做最后一项确认：检查 `useAgentChat.ts:85-95` 附近 `stripMarkdownTables` 的触发上下文（是否是题目导出相关），并确认 Agent 工具 `question_manage.batch_import` 的题目预览是否经过该函数。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\composables\useAgentChat.ts

> 🔧 `bash` — description=查stripMarkdownTables函数调用上下文

**AI**

`stripMarkdownTables` 仅用于 `stripMarkdown`，而 `stripMarkdown` 只处理**专家子代理结论摘要**（`ex.summary` 的纯文本插值展示），跟题目导入/导出完全无关，且它把表格转成 `：`/` · `（不是 TAB）。

排查已充分。下面是完整结论。

## 排查结论

### 一、核心结论

**前端未发现把 `|`（竖线）或 `<table>` 转成制表符 `\t` 的代码。**

全仓库（`openstudy-vue3-ts/src`）针对以下模式的彻底扫描均无命中：
- `\t` 字面制表符 / `\\t` 转义 / `\u0009` / `\x09` / `chr(9)` → 除了正则里的 `[ \t]*`（匹配空白，非生成 TAB），无任何 TAB 生成
- `split('\t')` / `join('\t')` / `replace(/[|]/g, '\t')` → 无
- `replace(/\|/g, ...)` 把竖线替换成别的字符 → 无（只有 `replace(/^\|/, '')` / `replace(/\|$/, '')` 剥离**首尾**竖线）

制表符来源应为**模型输出**，与前端无关。

### 二、竖线表格相关的全部命中（均为"识别/渲染/可读化"，均不产出 TAB）

**1. `<PROJECT>\openstudy-vue3-ts\src\utils\latex.ts:231-281`（`normalizePipeTables`）**
```ts
function normalizePipeTables(text: string): string {
  if (!text || !text.includes('|')) return text
  const isSeparatorRow = (s: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(s)
  const countCells = (s: string): number => {
    const t = s.trim().replace(/^\|/, '').replace(/\|$/, '')
    return t.split('|').length          // ← 仅"计数"，非转换
  }
  ...
  if (!hasSep && group.length >= 2 && consistent) {
    out.push(group[0])
    out.push('| ' + Array(ncol).fill('---').j

…（后略）


---

## 统计

- 工具调用次数：**55**

- 本会话为 AI 在 OpenStudy 项目中执行代码定位与分析的完整记录，用于说明开发过程中如何借助 AI 完成问题定位。
