/**
 * AI 解析内容渲染工具
 * 分段输出：按标题行（📋【考点分析】等）拆分为独立段落展示
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { renderMarkdownWithLatex } from './latex'

marked.setOptions({
  breaks: true,
  gfm: true
})

/**
 * 放行标签/属性
 *
 * ⚠️ 公式相关的标签必须在白名单里，否则 DOMPurify 会把 KaTeX 产出的
 *    MathML 结构剥掉 —— 表现是"公式渲染了但看不见"（一个空白块）。
 */
const ADD_TAGS = [
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'pre',
  'svg', 'path', 'math', 'mi', 'mo', 'mn', 'msup', 'msub', 'mover', 'munder',
  'mfrac', 'msqrt', 'mroot', 'mrow', 'mtext', 'mspace', 'mtable', 'mtr', 'mtd',
  'munderover', 'semantics', 'annotation', 'span'
]
const ADD_ATTR = [
  'colspan', 'rowspan', 'align', 'class',
  'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width', 'width', 'height',
  'style', 'encoding', 'aria-hidden', 'role', 'mathvariant', 'stretchy', 'fence',
  'separator', 'accent', 'accentunder', 'columnalign', 'rowalign', 'columnspan',
  'linethickness'
]

/**
 * 这段文本是否可能含公式
 *
 * 与 `utils/markdown.ts:mayContainMath` 同一套判据。
 */
function mayContainMath(text: string): boolean {
  if (text.indexOf('$') !== -1) return true
  if (text.indexOf('\\(') !== -1 || text.indexOf('\\[') !== -1) return true
  return /\\[a-zA-Z]{2,}/.test(text)
}

// 标题行：emoji + 空格? + 【标题】（也兼容无 emoji 直接【标题】）
const SEGMENT_HEADER_RE = /^(?:[📋💡✅📌⭐🧠🎯📊🔑❌📎✏️📚🔍❗️⚠️❣️]+\s*)?【[^】]+】/u

export interface AiSegment {
  title: string | null
  body: string
}

/**
 * 将 AI 解析内容按标题拆分为段落数组
 * 流式过程中最后一个段落会持续累积，天然支持增量渲染
 */
export function splitAiSegments(content: string): AiSegment[] {
  if (!content) return []
  const segments: AiSegment[] = []
  let current: AiSegment | null = null

  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    if (trimmed && SEGMENT_HEADER_RE.test(trimmed)) {
      current = { title: trimmed, body: '' }
      segments.push(current)
    } else {
      if (!current) {
        current = { title: null, body: '' }
        segments.push(current)
      }
      current.body += line + '\n'
    }
  }
  return segments.map(s => ({ title: s.title, body: s.body.trim() }))
}

/**
 * 将单个段落的 Markdown 渲染为安全的 HTML（含 LaTeX 支持）
 *
 * ── 2026-10-27 修复：顺序错了 ──────────────────────────────────
 * 原实现是「先 `marked.parse` → 再对**已生成的 HTML** 调 `renderLatexSafe`」。
 * 这个顺序会漏公式，原因很具体：
 *
 *   1. `marked` 先跑，把正文里的 `_` 当斜体、`*` 当加粗、`|` 当表格分隔
 *      —— 于是 `\sum_{i=1}^{n}x_i` 里的 `_{i=1}` 已经被吃掉/改写成 `<em>`
 *   2. 再交给 `renderLatexSafe` 时，那段文本早已不是合法 LaTeX
 *   3. 结果：`$...$` 形式的公式能渲染（因为 `$` 不在 Markdown 特殊字符里），
 *      而**裸命令形式 `\sum_{i=1}^{n}x_i` 渲染不出来**，页面上留一串源码
 *
 * 实测差异：同一段含 5 个公式的内容，旧实现只渲染出 4 个。
 *
 * 现在改用 `renderMarkdownWithLatex` —— 它内部是「先把公式换成占位符 →
 * 再 Markdown → 最后回填」，天然避开上述问题，也与题目页/笔记页/聊天
 * 走同一套规则（同一份 LaTeX 在任何页面都长得一样）。
 */
export function renderAiMarkdown(content: string): string {
  if (!content) return ''

  // 预处理：特殊分隔线统一为 markdown 的 ---
  const processed = content.replace(/^[━─]{3,}$/gm, '---')

  // ① 渲染（含公式）。没有公式时走轻量的 marked，避免给纯文字引入 KaTeX 结构。
  let html: string
  if (mayContainMath(processed)) {
    html = renderMarkdownWithLatex(processed)
  } else {
    try {
      html = marked.parse(processed) as string
    } catch {
      html = processed
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>')
    }
  }

  // ② 后处理：增强特殊符号样式
  //
  // ⚠️ 这几条规则都只匹配「emoji / 星标 / `#标签`」，
  //    不会碰 KaTeX 生成的 DOM（那是 `<span class="katex">` + MathML，
  //    内部只有 ASCII 标签名与数学字符）。
  //    曾考虑把公式块先挖出来保护，但用正则配对 `<span class="katex">` 的
  //    嵌套结构不可靠，反而可能把 HTML 切坏 —— 不做多余的"保护"。
  html = html.replace(/([🧠🎯📌📊✅❌💡🔑])/gu, '<span class="emoji-icon">$1</span>')
  html = html.replace(/⭐/g, '<span class="star">⭐</span>')
  html = html.replace(
    /(^|[\s>])#([a-zA-Z\u4e00-\u9fa5][\w\u4e00-\u9fa5-]*)/g,
    (_m, prefix, tag) => `${prefix}<span class="tag">#${tag}</span>`
  )

  // ③ XSS 防护
  return DOMPurify.sanitize(html, { ADD_TAGS, ADD_ATTR })
}
