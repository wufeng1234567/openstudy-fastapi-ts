import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { renderMarkdownWithLatex } from './latex'

/**
 * 公式渲染需要放行的标签/属性
 *
 * ⚠️ 白名单漏一个，DOMPurify 就会把它剥掉，结果是**公式渲染了但看不见**
 *    （KaTeX 的标准输出是 `<span class="katex">` + 一份 MathML，
 *      MathML 用 `<math>/<mrow>/<mi>/<mo>/…`，视觉层还带 `<svg><path>`）。
 *    这类 bug 从截图上看是"空白"，很容易误判成"没渲染"。
 */
const MATH_TAGS = [
  'svg', 'path', 'math', 'mi', 'mo', 'mn', 'msup', 'msub', 'mover', 'munder',
  'mfrac', 'msqrt', 'mroot', 'mrow', 'mtext', 'mspace', 'mtable', 'mtr', 'mtd',
  'munderover', 'semantics', 'annotation', 'span'
]
const MATH_ATTR = [
  'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width', 'width', 'height',
  'style', 'encoding', 'aria-hidden', 'role', 'mathvariant', 'stretchy', 'fence',
  'separator', 'accent', 'accentunder', 'columnalign', 'rowalign', 'columnspan',
  'linethickness'
]

const ADD_TAGS = ['table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'pre', ...MATH_TAGS]
const ADD_ATTR = ['colspan', 'rowspan', 'align', 'class', ...MATH_ATTR]

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * 渲染结果缓存
 *
 * 症状：历史上下文很长时，悬浮助手「打开 / 拖拽边框」极卡。
 * 根因：模板里 `v-html="renderAgentMarkdown(msg.content)"` 是**内联调用**，
 *      每次重渲染（打开、resize、任意响应式变动）都会对**每一条**消息重跑
 *      `marked.parse + DOMPurify.sanitize`——几百条消息 × 每次都重解析，
 *      主线程被占满 → 掉帧。
 * 处理：按 `content` 缓存渲染结果。消息内容不变时命中缓存，重渲染几乎零成本。
 *      Map 插满后整体清空（简单够用；历史里重复内容很少，清空代价可接受）。
 */
const mdCache = new Map<string, string>()
const MD_CACHE_MAX = 800

/**
 * 这段文本里是否**可能**有公式
 *
 * 有意放宽（宁可多走一次公式管线，也不漏渲染）：误判的代价只是多几百微秒，
 * 漏判的代价是用户在屏幕上看到一堆 `$\lim_{x\to 0}\frac{\sin x}{x}$` 原文。
 *
 * 覆盖：
 *   · `$...$` / `$$...$$`     —— 最常用
 *   · `\(...\)` / `\[...\]`   —— LaTeX / MathJax 原生定界符（模型很爱用）
 *   · `\命令{...}`            —— 裸 LaTeX 命令（`\frac{a}{b}`）
 *
 * ⚠️ 只看 `$` 不够：2026-10-27 实测 AI 回复写的是 `\(...\)`，
 *    只认 `$` 会让这类回复整段不渲染。
 */
function mayContainMath(text: string): boolean {
  if (text.indexOf('$') !== -1) return true
  if (text.indexOf('\\(') !== -1 || text.indexOf('\\[') !== -1) return true
  return /\\[a-zA-Z]{2,}/.test(text)
}

export function renderAgentMarkdown(content: string): string {
  if (!content) return ''
  const cached = mdCache.get(content)
  if (cached !== undefined) return cached
  const html = _renderAgentMarkdownUncached(content)
  if (mdCache.size >= MD_CACHE_MAX) mdCache.clear()
  mdCache.set(content, html)
  return html
}

function _renderAgentMarkdownUncached(content: string): string {
  const toolJsonRegex = /([\s\S]*?)(tool_call|tool_result)[ \t]*\r?\n?\s*(\{[\s\S]*)/m
  const match = content.match(toolJsonRegex)

  if (match) {
    const textPart = match[1]
    const jsonPart = match[3]
    let html = ''
    if (textPart.trim()) {
      html += renderTextPart(textPart)
    }
    html += `<div class="tool-json-block"><pre class="tool-json-content">${escapeHtml(jsonPart)}</pre></div>`
    return DOMPurify.sanitize(html, { ADD_TAGS, ADD_ATTR })
  }

  const html = renderTextPart(content)
  return DOMPurify.sanitize(html as string, { ADD_TAGS, ADD_ATTR })
}

/**
 * 渲染一段正文（可能含公式）
 *
 * ── 为什么聊天要单独处理（2026-10-27 修复）────────────────────
 * 在此之前这里只有 `marked.parse(content)` —— **完全没有公式渲染**。
 *
 * 后果很具体：AI 回复里写
 *
 *     极限：$\lim_{x\to 0}\frac{\sin x}{x}$
 *
 * 用户在屏幕上看到的就是这串原文（带着反斜杠和花括号）。
 * 而同一道题在题库页 / 笔记页是正常公式 —— 因为那两处走
 * `renderMarkdownWithLatex`。**同一份 LaTeX，两种显示**。
 *
 * 所以这里在「有公式迹象时」改用统一管线 `renderMarkdownWithLatex`：
 * 它已经处理了「先占位、再 Markdown、再回填」的顺序问题
 * （避免 `_` 被当斜体、`|` 被当表格分隔）。
 *
 * 没有公式时仍走原来的 `marked.parse`：那条路径更快，
 * 也不会给纯文字消息引入 KaTeX 的 DOM 结构。
 */
function renderTextPart(text: string): string {
  if (mayContainMath(text)) {
    return renderMarkdownWithLatex(text)
  }
  return marked.parse(text) as string
}
