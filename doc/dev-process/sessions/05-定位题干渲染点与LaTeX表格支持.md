# 定位题干渲染点与LaTeX/表格支持 (@explore subagent)

> 会话 ID：`ses_ed51b9f1fffe5hB5sZp4LLyk5w`  
> 时间：2026-10-11 20:16:12 — 2026-10-11 20:18:15  
> 消息数：124  
> 所属项目：OpenStudy（FastAPI + Vue3 全栈学习平台）

---

## 对话记录

**用户提问**

```
在前端仓库 <PROJECT>\openstudy-vue3-ts 中，调查「题目题干（question content / mainContent）」在**各个页面**是怎么渲染的，重点是：**哪些页面渲染题干时用了 `LatexRenderer` 组件（支持 KaTeX 公式 + markdown 表格），哪些没有用（直接 {{ }} 插值或 v-html 纯文本）**。

背景：用户看到题干里的数学公式显示成源码 `$(X,Y)$`、`$Z=\max\{X,Y\}$`，表格显示成 `a | b | c` 竖线文本。需要定位**用户可能正在看的那些题干展示组件**，判断它们各自有没有走 KaTeX/markdown 渲染。

请彻底排查（thorough 级别）以下场景的题目正文渲染点：
1. **题库 AI 搭建 / 导入预览页**：搜索 `AiQuestionBuilder`、`questionBuilder`、`studio` 下的组件，看生成的题目预览怎么显示题干（是否 LatexRenderer）。
2. **题库管理 / 题目列表 / 题目编辑页**：搜索 `questionManage`、`QuestionForm`、`question/edit`、`bank` 相关组件，看题干如何渲染。
3. **做题/练习页**：已知 `src/components/PracticeComponent/QuestionDisplay.vue`、`QuestionAnalysis.vue` 用了 `LatexRenderer`——确认它们传的 `markdown`/`rawHtml` 属性是什么（决定是否走 `renderMarkdownContent` 渲染表格）。
4. **题目详情/预览弹层**：搜索 `questionPre

…（后略）
```

**用户提问**

```
<system-reminder>重要提示：你必须使用简体中文回复，包括内部思考和推理过程也必须使用简体中文。即使用户用英文提问，也必须用简体中文回复。</system-reminder>
```

**AI**

开始彻底排查。我先定位 LatexRenderer 组件本身以及它的属性语义。

> 🔧 `bash` — description=查找 LatexRenderer 组件文件

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts

**AI**

我先读 LatexRenderer 组件和 latex.ts 工具，弄清三个渲染函数的语义。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\LatexRenderer\LatexRenderer.vue

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\utils\latex.ts

**AI**

关键发现：`rawLatex` 默认 `true`，所以 LatexRenderer 默认走 `renderQuestionContent`（第二步）。注意 `renderQuestionContent` **不处理 `$...$` 和表格**，只处理 `\命令{...}` 形式的 LaTeX。这意味着即使包了 LatexRenderer，`$...$` 公式和 markdown 表格也会显示成源码！

现在彻底排查各页面。先看目录结构。

> 🔧 `bash` — description=列出前端 src 目录结构

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src

**AI**

现在针对各场景逐个排查。先看 studio（AI 搭建）和 questionMain 题库管理。

> 🔧 `bash` — description=列出题目相关目录文件

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src\views\front\studio

**AI**

发现 AiQuestionBuilder.vue 第 405 行直接用 `{{ stripMarkers(q.questionText) }}` 插值——这是重点嫌疑。我详细查看该文件相关区域，以及 QuestionBuilder.vue 的预览。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\AiQuestionBuilder.vue

> 🔧 `bash` — description=检查 QuestionBuilder 渲染方式

**AI**

AiQuestionBuilder 确认嫌疑。现在看 QuestionBuilder.vue 的模板预览部分（它用 textToHtml），以及 QuestionFullEditor.vue。同时看 textToHtml 定义。

> 🔧 `bash` — description=查看 QuestionBuilder 模板渲染

> 🔧 `bash` — description=查看 QuestionFullEditor 渲染

> 🔧 `bash` — description=查看 textToHtml 定义

**AI**

现在查看 QuestionBuilder.vue 的预览区域（468-610）与 create/index.vue 的题目预览。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\studio\components\QuestionBuilder.vue

**AI**

注意：QuestionBuilder 的预览用的是 `el-input`（可编辑输入框），不是渲染展示，所以 `$...$` 会显示为原始文本（在输入框里）。第 78-79 行列表用 `getPlainText(element.title)` 纯文本插值。

现在看题库管理 questionMain 和 questionBank 页面，以及 bankDetail/practice。

> 🔧 `bash` — description=查看题库管理主页面渲染

> 🔧 `bash` — description=查看题库页面渲染

> 🔧 `bash` — description=查看练习页面渲染

**AI**

questionMain 是表格管理页（`el-table-column` 的 `questionText` 显示列用 show-overflow-tooltip，属纯文本；编辑表单用 el-input）。questionBank/index.vue 无匹配，practice 也无匹配。看看这些文件是否为空/仅列表，以及 bankDetail 的内容。

> 🔧 `bash` — description=检查各页面组件构成

**AI**

练习页走 PracticeComponent → QuestionDisplay（已用 LatexRenderer）。但题干渲染可能还出现在 QuestionBankDetail 组件。现在详细看 PracticeComponent/QuestionDisplay.vue 的属性，以及 QuestionBankDetail 组件、myQuestion 详情等。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\PracticeComponent\QuestionDisplay.vue

> 🔧 `bash` — description=检查 QuestionBankDetail 组件

**AI**

QuestionBankDetail 是题库卡片页（不含题目正文）。现在看 MyQuestion 组件（题目详情弹层，做题/预览）和 views/front/myQuestion 下的详情组件。

> 🔧 `bash` — description=检查 MyQuestion 详情弹层渲染

> 🔧 `bash` — description=列出前台题目相关页面

**AI**

MyQuestion.vue 是题目详情弹层核心。查看它的模板和是否有 LatexRenderer。

> 🔧 `bash` — description=检查 MyQuestion.vue 渲染方式

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src\views\front\myQuestion

**AI**

MyQuestion.vue 本身没有 LatexRenderer，它的题目展示在弹层里。让我看它的模板主体（题干在哪里显示）以及 myMistakes/myMarked 用的弹层组件。先看 MyQuestion.vue 模板。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\MyQuestion\MyQuestion.vue

**AI**

关键：`QuestionDetailDialog.vue`。以及 `QuestionCard.vue`。查看这两个组件。

> 🔧 `bash` — description=列出 MyQuestion 组件并检查 QuestionCard

**AI**

QuestionCard 用 `v-html="formatQuestionText(...)"`。查看 formatQuestionText 和 QuestionDetailDialog。

> 🔧 `bash` — description=检查 QuestionDetailDialog 渲染

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\MyQuestion\QuestionCard.vue

**AI**

QuestionCard 的 `formatQuestionText` 只做换行替换，**不渲染 LaTeX/markdown**，且用 v-html 直接输出——这是明确的嫌疑点（题目卡片列表）。

QuestionDetailDialog.vue 无匹配说明它可能不直接在模板里渲染题干。查看它的模板。

> 🔧 `bash` — description=查看 QuestionDetailDialog 内容

**AI**

QuestionDetailDialog 内部用同一个 `QuestionDisplay`（做题页组件），所以详情弹层里题目正文是走 LatexRenderer 的（`raw-html`）。但卡片列表用 QuestionCard 的 v-html，不走渲染。

现在检查 myMistakes/myMarked/myFavoriteQuestion 是否复用了 QuestionCard/MyQuestion。以及 AiAnalysisDialog。还要查全局其他 v-html 渲染题干的地方。

> 🔧 `bash` — description=检查错题/标记页面复用组件

> 🔧 `bash` — description=检查 AI 解析弹框渲染

**AI**

AiAnalysisDialog 里题干 `{{ getPlainText(question) }}` 纯文本（第 11 行）。现在做全局搜索，把所有直接插值题干的地方列全，并搜索所有用 v-html 渲染题干的位置。

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src

**AI**

重要发现：`PracticeResult.vue` 第 54 行 `v-html="q.questionText"` 直接输出题干，不走渲染。另外 QuestionCardGrid.vue 第164行也是 v-html。检查这两个以及 PracticeResult 的上下文。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\PracticeComponent\PracticeResult.vue

> 🔧 `bash` — description=查看 QuestionCardGrid 渲染

**AI**

现在检查 myStats（题目错误统计）、ReadingComprehensionDisplay 的 mainContent 渲染，以及 QuestionBuilder 的 create/index.vue 预览。还要确认 notes/detail.vue 第204行。

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\views\front\myQuestion\myStats\index.vue

> 🔧 `read` — filePath=<PROJECT>\openstudy-vue3-ts\src\components\PracticeComponent\ReadingComprehensionDisplay.vue

**AI**

现在检查 create/index.vue（AI 搭建导入页）的预览及 notes/detail.vue。以及搜索是否还有其它题目预览组件（如 questionPreview/detail）。

> 🔧 `bash` — description=检查 studio 页面组件用法

> 🔧 `bash` — description=查看 notes/detail.vue 题目文本用法

**AI**

create/index.vue 直接复用了 QuestionBuilder 和 AiQuestionBuilder。notes/detail.vue 是笔记预览（用 getPlainText）。现在检查共享的 QuestionDetailDialog 里的 QuestionDisplay 属性——已确认。还需确认 QuestionBuilder 顶部列表(78行)的 getPlainText，以及是否有其它题目详情预览组件（比如 questionMain 里的预览弹层）。

全局再搜 renderMarkdownContent / renderQuestionContent 的调用者，以及 :content 传 markdown 属性的地方。

> 🔧 `grep` — path=<PROJECT>\openstudy-vue3-ts\src

**AI**

重要确认：全局**没有任何地方**给 LatexRenderer 传 `markdown` 属性，也没有 `:markdown` 用法。几乎所有调用都是 `raw-html` 或默认。这意味着 `renderMarkdownContent`（能渲表格）**从未在模板里被启用**——所以表格 `a|b|c` 永远显示为源码！

这是核心结论。现在验证 PracticeComponent 里 currentQuestion 是否含 mainContent 及 formatMainContent（QuestionDisplay 已用），以及 QuestionAnalysis 用法。最后确认 questionMarked/questionError 的 `:content` 是 notes（富文本编辑器组件）。

现在检查 editor/TiptapEditor 是否是渲染，及练习页的 PracticeResult 触发场景。

> 🔧 `bash` — description=查找 PracticeResult 使用位置

> 🔧 `bash` — description=查看 questionMarked 的 content 渲染

**AI**

questionMarked 的 `:content` 是 el-tooltip 的 content（备注），与题干无关。

现在确认练习页 PracticeResult 的场景——用户在**练习结果/交卷页**看题干时走 `v-html="q.questionText"`，不渲染公式。同时确认 QuestionBuilder 顶部列表 getPlainText。最后看下 QuestionBuilder 78行的上下文和 renderAgentMarkdown 无关。

我已收集足够信息。做最后验证：确认 `markdown` 属性在全局确实无用例，以及 renderQuestionContent 是否处理 `$...$`（它不处理，只有 renderLatex/renderMarkdownContent 内部经替换……注意 renderMarkdownContent 也不处理 `$...$`！只有 renderLatexSafe 走 renderLatex 处理 `$...$`）。

验证 renderMarkdownContent 是否处理 `$...$`：

> 🔧 `bash` — description=确认各函数是否处理 $...$ 公式

**AI**

确认：只有 `renderLatex`(173行) 处理 `$...$`，而它仅被 `renderLatexSafe`(200行) 调用。`renderQuestionContent` 和 `renderMarkdownContent` 都**不处理 `$...$`**！

但注意 LatexRenderer 的逻辑：`rawLatex` 默认 true → 走 renderQuestionContent/renderMarkdownContent；此时 `rawHtml` 分支被跳过，走 renderLatexSafe 的条件是 `rawLatex=false`。所以模板里传 `raw-html` 属性配合默认 `rawLatex=true` → **`raw-html` 属性被忽略**！这解释了为什么 `$...$` 公式在 QuestionDisplay 里仍然显示源码。

让我再次确认这个逻辑链的准确性，并检查是否有全局注册 markdown 的其他方式（如 PracticeComponent 内是否有 prop 传递 markdown）。

> 🔧 `bash` — description=检查练习组件是否传 markdown 属性

**AI**

确认练习组件全都不传 markdown。现在完整梳理完毕，给出结论。

## 调查结论

### 一、`LatexRenderer` 的属性与渲染路径（先讲清机理，这是理解全部问题的钥匙）

`<PROJECT>\openstudy-vue3-ts\src\components\LatexRenderer\LatexRenderer.vue:22-38`

```js
const renderedContent = computed(() => {
  if (!props.content) return ''
  if (props.rawLatex) {                              // 默认 true！
    if (props.markdown) {
      return renderMarkdownContent(props.content)    // 路径A：能渲表格
    }
    return renderQuestionContent(props.content, { renderMarkdown: props.markdown }) // 路径B：不能
  }
  if (props.rawHtml) {
    return renderLatexSafe(props.content)            // 路径C：能渲 $...$
  }
  return renderLatexPlainText(props.content)         // 路径D
})
```

三个工具函数的实际能力（`src\utils\latex.ts`）：

| 函数 | 处理 `$...$`/`$$...$$` | 处理 `\命令{}` | 处理 markdown 表格 `a|b|c` |
|---|---|---|---|
| `renderQuestionContent` (L95) | 否 | 是 | 否 |
| `renderMarkdownContent` (L137) | 否 | 是 | **是**（marked.parse + gfm） |
| `renderLatexSafe` (L200) → `renderLatex` (L173) | **是** | 否 | 否 |

关键事实：全局搜索 `markdown` / `:markdown` / `rawLatex` / `raw-latex`，**没有任何一个模板给 `LatexRenderer` 传过 `markdown` 属性**。而 `rawLatex` 默认为 `true`，所以：

- 所有 `<LatexRenderer :content="..." raw-html />` 调用，

…（后略）


---

## 统计

- 工具调用次数：**44**

- 本会话为 AI 在 OpenStudy 项目中执行代码定位与分析的完整记录，用于说明开发过程中如何借助 AI 完成问题定位。
