import katex from 'katex'
import 'katex/dist/katex.min.css'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * 将文本中的 LaTeX 公式命令渲染为可显示 HTML
 * 支持嵌套括号（如 \overline{\mathrm{B}}）和多个连续的 {}{}{} 组（如 \frac{A}{k(k+1)}）
 */
function renderLatexCommands(text: string): string {
  const commands: Array<{ start: number; end: number; text: string }> = []
  const cmdRegex = /\\([a-zA-Z]+)/g
  let match: RegExpExecArray | null

  while ((match = cmdRegex.exec(text)) !== null) {
    const cmdStart = match.index
    let pos = cmdRegex.lastIndex
    while (pos < text.length && text[pos] === ' ') pos++

    const braceGroups: string[] = []
    let scanPos = pos
    while (scanPos < text.length && text[scanPos] === '{') {
      let depth = 0
      let end = -1
      for (let i = scanPos; i < text.length; i++) {
        if (text[i] === '{') depth++
        else if (text[i] === '}') {
          depth--
          if (depth === 0) { end = i + 1; break }
        }
      }
      if (end > 0) {
        braceGroups.push(text.substring(scanPos, end))
        scanPos = end
        while (scanPos < text.length && text[scanPos] === ' ') scanPos++
      } else {
        break
      }
    }

    if (braceGroups.length > 0) {
      const end = scanPos
      commands.push({ start: cmdStart, end, text: text.substring(cmdStart, end) })
      cmdRegex.lastIndex = end
    }
  }

  let result = text
  for (let i = commands.length - 1; i >= 0; i--) {
    const cmd = commands[i]
    try {
      const rendered = katex.renderToString(cmd.text, {
        throwOnError: false,
        output: 'html',
        displayMode: false
      })
      if (rendered && !rendered.startsWith('\\')) {
        result = result.substring(0, cmd.start) + rendered + result.substring(cmd.end)
      }
    } catch {
      // 渲染失败则保持原样
    }
  }

  return result
}

/**
 * 将文本中的零散 LaTeX 符号命令替换为 Unicode 字符
 */
function replaceLatexSymbols(text: string): string {
  const symMap: Record<string, string> = {
    '\\alpha': 'α', '\\beta': 'β', '\\gamma': 'γ', '\\theta': 'θ',
    '\\pi': 'π', '\\mu': 'μ', '\\sigma': 'σ', '\\phi': 'φ',
    '\\omega': 'ω', '\\Delta': 'Δ', '\\Sigma': 'Σ', '\\Omega': 'Ω',
    '\\to': '→', '\\rightarrow': '→', '\\leftarrow': '←',
    '\\times': '×', '\\div': '÷', '\\pm': '±', '\\neq': '≠',
    '\\le': '≤', '\\ge': '≥', '\\approx': '≈', '\\infty': '∞',
    '\\cdot': '·', '\\cdots': '…', '\\dots': '…', '\\cup': '∪',
    '\\cap': '∩', '\\subset': '⊂', '\\supset': '⊃', '\\in': '∈',
    '\\notin': '∉', '\\emptyset': '∅', '\\partial': '∂', '\\nabla': '∇',
    '\\imath': 'ı', '\\jmath': 'ȷ', '\\ell': 'ℓ', '\\hbar': 'ℏ',
    '\\Re': 'ℜ', '\\Im': 'ℑ', '\\wp': '℘', '\\prime': '′',
  }
  let result = text
  for (const [cmd, unicode] of Object.entries(symMap)) {
    result = result.replaceAll(cmd, unicode)
  }
  return result
}

/**
 * 渲染题目内容：预处理 WPS 别名 → KaTeX 公式 → Unicode 符号 → Markdown 表格 → 安全过滤
 */
export function renderQuestionContent(text: string, options: { renderMarkdown?: boolean } = {}): string {
  if (!text) return ''

  const { renderMarkdown: renderMd = false } = options

  // 1. 替换填空占位符 ___N___ → 高亮下划线样式
  let result = text.replace(/___(\d+)___/g, '<strong style="color: #409eff; text-decoration: underline;">[$1]</strong>')

  // 2. 预处理 WPS 旧版公式命令别名 → 标准 LaTeX
  result = result
    .replace(/\\overbar\{/g, '\\overline{')
    .replace(/\\underbar\{/g, '\\underline{')

  // 3. KaTeX 渲染 LaTeX 命令
  result = renderLatexCommands(result)

  // 4. Unicode 符号映射（兜底）
  result = replaceLatexSymbols(result)

  // 5. \n 转换为 <br>
  result = result.replace(/\n/g, '<br>')

  // 6. 安全过滤
  const allowedTags = [
    'svg', 'path', 'math', 'mi', 'mo', 'mn', 'msup', 'msub', 'mover', 'munder',
    'mfrac', 'msqrt', 'mrow', 'mtext', 'annotation', 'semantics',
    'strong', 'em', 'u', 'span', 'br', 'sub', 'sup', 'img'
  ]
  const allowedAttrs = [
    'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width',
    'width', 'height', 'style', 'encoding', 'src', 'alt'
  ]

  return DOMPurify.sanitize(result, {
    ADD_TAGS: allowedTags,
    ADD_ATTR: allowedAttrs
  })
}

/**
 * 渲染带 Markdown 的内容（用于答案解析等可能包含表格/列表的内容）
 */
export function renderMarkdownContent(text: string): string {
  if (!text) return ''

  // 1. 预处理 WPS 旧版公式命令别名
  let result = text
    .replace(/\\overbar\{/g, '\\overline{')
    .replace(/\\underbar\{/g, '\\underline{')

  // 2. KaTeX 渲染 LaTeX 命令
  result = renderLatexCommands(result)

  // 3. Unicode 符号映射
  result = replaceLatexSymbols(result)

  // 4. Markdown 渲染（表格、列表等）
  const html = marked.parse(result, { gfm: true, breaks: true })

  // 5. 安全过滤（允许表格标签）
  return DOMPurify.sanitize(html, {
    ADD_TAGS: [
      'svg', 'path', 'math', 'mi', 'mo', 'mn', 'msup', 'msub', 'mover', 'munder',
      'mfrac', 'msqrt', 'mrow', 'mtext', 'annotation', 'semantics',
      'strong', 'em', 'u', 'span', 'br', 'sub', 'sup', 'img',
      'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption'
    ],
    ADD_ATTR: [
      'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width',
      'width', 'height', 'style', 'encoding', 'src', 'alt',
      'colspan', 'rowspan', 'align'
    ]
  })
}

/**
 * 渲染文本中的 LaTeX 公式（$...$ 和 $$...$$ 标记）
 */
export function renderLatex(text: string): string {
  if (!text) return ''

  // 先处理 $$...$$ 块级公式
  let result = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false })
    } catch {
      return `<span class="latex-error">${formula}</span>`
    }
  })

  // 再处理 $...$ 行内公式
  result = result.replace(/\$([^\$\n]+?)\$/g, (_, formula) => {
    try {
      return katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false })
    } catch {
      return `<span class="latex-error">${formula}</span>`
    }
  })

  return result
}

/**
 * 渲染文本中的 LaTeX 公式，并用 DOMPurify 做 XSS 防护
 */
export function renderLatexSafe(text: string): string {
  if (!text) return ''
  const rawHtml = renderLatex(text)
  return DOMPurify.sanitize(rawHtml, {
    ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac', 'msqrt', 'mroot', 'mtext', 'mspace', 'annotation', 'semantics', 'mtable', 'mtr', 'mtd', 'mover', 'munder', 'munderover'],
    ADD_ATTR: ['class', 'style', 'aria-hidden', 'role', 'encoding', 'mathvariant', 'stretchy', 'fence', 'separator', 'accent', 'accentunder', 'columnalign', 'rowalign', 'columnspan', 'rowspan', 'linethickness', 'lspace', 'rspace', 'stackalign', 'align', 'alignmentscope', 'columnlines', 'rowlines', 'frame', 'framespacing', 'equalrows', 'equalcolumns', 'displaystyle', 'scriptlevel', 'location', 'side', 'bevelled', 'notation', 'charalign', 'stackshift', 'height', 'depth', 'width', 'voffset', 'lquote', 'rquote', 'crossout', 'dir'],
    KEEP_CONTENT: true
  })
}

/**
 * 渲染纯文本中的 LaTeX 公式
 */
export function renderLatexPlainText(text: string): string {
  if (!text) return ''

  const placeholders: string[] = []
  const placeholderPrefix = '@@LATEX_PH_'
  const placeholderSuffix = '@@'
  const placeholderRegex = /@@LATEX_PH_(\d+)@@/g

  const escapeHtml = (str: string): string => {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
  }

  // 先处理 $$...$$ 块级公式
  let result = text.replace(/\$\$([\s\S]*?)\$\$/g, (_, formula) => {
    try {
      const html = katex.renderToString(formula.trim(), { displayMode: true, throwOnError: false })
      placeholders.push(html)
      return `${placeholderPrefix}${placeholders.length - 1}${placeholderSuffix}`
    } catch {
      const escaped = escapeHtml(formula)
      placeholders.push(`<span class="latex-error">${escaped}</span>`)
      return `${placeholderPrefix}${placeholders.length - 1}${placeholderSuffix}`
    }
  })

  // 处理 $...$ 行内公式
  result = result.replace(/\$([^\$\n]+?)\$/g, (_, formula) => {
    try {
      const html = katex.renderToString(formula.trim(), { displayMode: false, throwOnError: false })
      placeholders.push(html)
      return `${placeholderPrefix}${placeholders.length - 1}${placeholderSuffix}`
    } catch {
      const escaped = escapeHtml(formula)
      placeholders.push(`<span class="latex-error">${escaped}</span>`)
      return `${placeholderPrefix}${placeholders.length - 1}${placeholderSuffix}`
    }
  })

  // 转义剩余文本的 HTML 特殊字符
  result = escapeHtml(result)

  // 还原占位符为 KaTeX 渲染结果
  result = result.replace(placeholderRegex, (_, idx) => placeholders[Number(idx)])

  return result
}

/**
 * 检查文本是否包含 LaTeX 公式
 */
export function hasLatex(text: string): boolean {
  return /\$[^$]+\$/.test(text || '')
}

export default renderQuestionContent
