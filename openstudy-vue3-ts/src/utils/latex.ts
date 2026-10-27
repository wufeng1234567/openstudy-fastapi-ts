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
 * 行内公式正则（**严格要求**，用户 2026-10-11 定案）：
 *   - `$...$` 必须**成对**、内容**非空**（至少 1 个字符）；
 *   - **边界不含空白**：左 `$` 后不能紧跟空白、右 `$` 前不能是空白 —— 避免把
 *     货币金额（`价格 $5 到 $10`）误判为公式；
 *   - 内容不跨行、不含 `$`。
 * 用 lookahead/lookbehind 表达边界（JS 支持固定长度 lookbehind）。
 */
const INLINE_MATH_RE = /\$(?!\s)([^\$\n]+?)(?<!\s)\$/g

/** 块级公式 `$$...$$`（可跨行） */
const BLOCK_MATH_RE = /\$\$(?!\s)([\s\S]+?)(?<!\s)\$\$/g

/**
 * LaTeX 原生定界符：行内 `\(...\)`、块级 `\[...\]`
 *
 * ── 为什么必须支持（2026-10-26 实测）──────────────────────────
 * 让 AI 出一道带公式的题，模型吐的是：
 *
 *     概率为 \(P(X=1)=2p(1-p)\)
 *
 * 而不是 `$...$`。因为 `\(...\)` / `\[...\]` 是 MathJax / KaTeX 的
 * **默认行内/块级语法**，也是 arXiv、数学 StackExchange 等数学语料的写法。
 *
 * 只认 `$...$` 的后果很具体：这些内容被当普通文本原样显示，
 * 用户看到满屏 `\(` `\)`。而且**导出侧已经修好了**（后端
 * `bank_export_service._split_delimited_math`），若前端不修就会出现
 * "下载的 Word 公式是对的、屏幕上却是乱码" —— 比两边都错更让人困惑。
 *
 * 边界与 `$...$` 保持一致：成对、非空。空壳 `\(\)` 由调用方跳过。
 */
const INLINE_PAREN_MATH_RE = /\\\(([\s\S]+?)\\\)/g

/** 块级 `\[...\]`（可跨行） */
const BLOCK_PAREN_MATH_RE = /\\\[([\s\S]+?)\\\]/g

/**
 * 渲染文本中的 LaTeX 公式（`$...$` 行内 与 `$$...$$` 块级）
 *
 * ⚠️ 公式标记的边界约定：**成对、非空、不含空格边界**（见 `INLINE_MATH_RE`/`BLOCK_MATH_RE`）。
 * 这样纯文本里的货币等零散 `$` 不会被误渲染。
 */
export function renderLatex(text: string): string {
  if (!text) return ''

  const render = (formula: string, display: boolean): string => {
    const body = formula.trim()
    // 空壳 `\(\)` / `$$$$` 原样返回，不产出空公式
    if (!body) return ''
    try {
      return katex.renderToString(body, { displayMode: display, throwOnError: false })
    } catch {
      return `<span class="latex-error">${body}</span>`
    }
  }

  // 块级：先 `$$...$$`，再 `\[...\]`
  let result = text.replace(BLOCK_MATH_RE, (_, f) => render(f, true))
  result = result.replace(BLOCK_PAREN_MATH_RE, (_, f) => render(f, true))

  // 行内：先 `$...$`，再 `\(...\)`
  result = result.replace(INLINE_MATH_RE, (_, f) => render(f, false))
  result = result.replace(INLINE_PAREN_MATH_RE, (_, f) => render(f, false))

  return result
}

/**
 * **表格格式容错**：把「无表头分隔行的裸竖线表格」补成合法 Markdown 表格（用户 2026-10-11 要求"两种格式都要适配"）。
 *
 * 为什么要它：**Word 里的表格本来就不是 Markdown**（它是 OOXML 结构），解析/入库的中间形态有两种：
 *   ① **新格式**（后端 `_emit_table` 已改）：已是合法 md 表格，含 `| --- |` 分隔行 → `marked` 直接能渲；
 *   ② **旧格式/裸表格文本**（历史数据、或别处拼出来的）：形如
 *        `X\Y | 0 | 1 | 2`
 *        `0 | 0.1 | 0.3 | 0.2`
 *      每行用 `|` 分隔但**没有分隔行** → `marked` 认不出、原样显示成一串竖线。
 *   本函数把 ② 就地"补"成 ①，于是**两种格式都能渲染**（对话/新旧数据通吃）。
 *
 * 判据（**保守**，宁可不转也不误伤正文）：
 *   - 连续 **≥2 行**，每行含 **≥2 个 `|`**（至少 2 列）；
 *   - 这些行的**列数一致**；
 *   - 该组行里的**任意一行都不是**分隔行（`| --- |`）——已是 md 表格就**不动**；
 *   - 该组行**不紧跟在**一个已是"表格块"的上下文里（避免重复补）。
 * 满足则在该组第 1 行后插入一行 `| --- | ... |`。
 */
function normalizePipeTables(text: string): string {
  if (!text || !text.includes('|')) return text

  const isSeparatorRow = (s: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(s)
  // 单元格数（用于列数一致性判定）：按未转义的 `|` 切；首尾竖线不计空段
  const countCells = (s: string): number => {
    const t = s.trim().replace(/^\|/, '').replace(/\|$/, '')
    return t.split('|').length
  }
  const isPipeRow = (s: string) => {
    const t = s.trim()
    if (!t || !t.includes('|')) return false
    if (isSeparatorRow(t)) return false
    // 必须是"真表格形态"之一，避免误伤正文（用户 2026-10-11 折中判据）：
    //   · 以 `|` 开头或结尾（`| a | b |`）；或
    //   · `|` 两侧都带空格（`a | b`，常见的手写/解析表格分隔）。
    // 纯 `a|b`（无空格、无首尾竖线）不算——那多半是正文里的竖线，不是表格。
    const startsOrEndsWithPipe = t.startsWith('|') || t.endsWith('|')
    const spacedPipe = / \| | \|$|^\| /.test(t)
    return startsOrEndsWithPipe || spacedPipe
  }

  const lines = text.split('\n')
  const out: string[] = []

  /**
   * 单元格转义：把单元格文本里的反斜杠 `\` 转成 `\\`。
   *
   * 为什么需要：用户 2026-10-11——表头 `X\Y` 被渲染成 `XY`（`marked` 把 `\Y` 当转义、吃掉了 `\`）。
   * 表格单元格里的 `\` 是**普通文本**（此步之前公式已被占位符替换，不会误伤 KaTeX 的反斜杠命令），
   * 故统一转义成 `\\`，`marked` 才会原样输出一个 `\`。
   */
  const escapeCells = (row: string): string => {
    const t = row.trim().replace(/^\|/, '').replace(/\|$/, '')
    const cells = t.split('|').map((c) => c.trim().replace(/\\/g, '\\\\'))
    return '| ' + cells.join(' | ') + ' |'
  }

  let i = 0
  while (i < lines.length) {
    if (isPipeRow(lines[i])) {
      // 收集连续 pipe 行
      let j = i
      while (j < lines.length && isPipeRow(lines[j])) j++
      const group = lines.slice(i, j)
      // 该组里若出现分隔行，说明已经是合法 md 表格 → 原样放行
      const hasSep = group.some(isSeparatorRow)
      const cols = group.map(countCells)
      const consistent = cols.every((c) => c === cols[0]) && cols[0] >= 2
      if (!hasSep && group.length >= 2 && consistent) {
        const ncol = cols[0]
        // 表头 + 分隔行 + 数据行；每行都对单元格做 `\` 转义（否则 `X\Y` 会被 marked 吃掉反斜杠）
        out.push(escapeCells(group[0]))
        out.push('| ' + Array(ncol).fill('---').join(' | ') + ' |')
        for (let k = 1; k < group.length; k++) out.push(escapeCells(group[k]))
      } else {
        for (const g of group) out.push(g)
      }
      i = j
    } else {
      out.push(lines[i])
      i++
    }
  }
  return out.join('\n')
}

/**
 * **制表符表格容错**：把「TAB 分隔的表格文本」转成合法 Markdown 表格（用户 2026-10-11"三重保险"的第三重）。
 *
 * 背景：**模型在生成题目 JSON 时，可能自己把表格重写成 TAB 分隔文本**（如 `X\Y\t0\t1\t2`），
 * 而不是保留我们喂给它的 Markdown 表格 —— 用户实测到了这个形态。这种文本既无 `|`
 * （`normalizePipeTables` 认不出），也不是 md 表格（`marked` 不认）。
 * 且**前端全链路已确认不存在 `|`→TAB 的转换**（制表符来源=模型输出）。
 * 故：提示词要求模型输出 md 表格（第一重）+ 后端 `_emit_table` 产合法 md 表格（第二重）
 * + **本函数把 TAB 表格就地转成 md 表格（第三重兜底）**，三重保险。
 *
 * 判据（**保守**，避免误伤正文里的单个 TAB）：
 *   - 连续 **≥2 行**，每行含 **≥1 个 TAB**；
 *   - 各行的**列数一致**（按 TAB 切分，列数 ≥2）；
 *   - 满足则整组转成 md 表格（首行当表头 + `| --- |` 分隔行）。
 */
function normalizeTabTables(text: string): string {
  if (!text || !text.includes('\t')) return text

  const isTabRow = (s: string) => {
    const t = s.replace(/\r$/, '')
    return t.includes('\t') && t.trim().length > 0 && t.split('\t').length >= 2
  }
  const cellCount = (s: string) => s.replace(/\r$/, '').split('\t').length
  // 单元格转义：内部 `|` 要转成 `\|`（否则会破坏生成的 md 表格）
  const toCell = (c: string) => c.trim().split(/\s+/).join(' ').replace(/\|/g, '\\|')

  const lines = text.split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    if (isTabRow(lines[i])) {
      let j = i
      while (j < lines.length && isTabRow(lines[j])) j++
      const group = lines.slice(i, j)
      const cols = group.map(cellCount)
      const consistent = cols.every((c) => c === cols[0]) && cols[0] >= 2
      if (group.length >= 2 && consistent) {
        const ncol = cols[0]
        const toMdRow = (row: string) =>
          '| ' + row.replace(/\r$/, '').split('\t').map(toCell).join(' | ') + ' |'
        out.push(toMdRow(group[0]))
        out.push('| ' + Array(ncol).fill('---').join(' | ') + ' |')
        for (let k = 1; k < group.length; k++) out.push(toMdRow(group[k]))
      } else {
        for (const g of group) out.push(g)
      }
      i = j
    } else {
      out.push(lines[i])
      i++
    }
  }
  return out.join('\n')
}

/**
 * 找出文本里**没有被 `$` 包裹**的裸 LaTeX 命令（如 `\overline{A}`、`\frac{a}{b}`）
 *
 * 为什么需要它（用户 2026-10-19 报「刷题页公式显示成 P(A B)」）：
 *   题库里大量公式是**裸 LaTeX**（Word/WPS 导入时没加 `$`），
 *   而统一管线 `renderMarkdownWithLatex` 原先只认 `$...$`／`$$...$$`，
 *   于是 `\overline{A}` 原样漏进 HTML，KaTeX 从没参与渲染 ——
 *   浏览器把反斜杠当普通字符、把 `{A}` 当文本，最终显示成 "A B"，
 *   上划线完全丢失（正是用户截图里的效果）。
 *
 * 与 `renderLatexCommands()` 的区别：
 *   那个函数**直接产出 HTML**，但会在 Markdown 渲染前就把 `<span>` 塞进正文，
 *   导致 `marked` 把 HTML 块包进 `<p>` 时错位。这里只**定位区间**，
 *   交给调用方换成占位符，保持"先占位、后渲染、再回填"的顺序不乱。
 *
 * 只认「命令 + 至少一个 `{}` 组」：裸的 `\n`、`\t`、`&` 之类不碰，
 * 避免把转义字符或普通文本误当公式。
 */
/**
 * Unicode 数学「大运算符」——这些字符后面紧跟 `_{...}` / `^{...}` 就是公式
 *
 * 与后端 `bank_export_service._UNICODE_BIG_OPS` 保持**完全一致**，
 * 这样"页面上看到的"与"导出到 Word/PDF 的"才是同一批公式。
 */
const UNICODE_BIG_OPS = '∫∬∭∮∑∏∐⋃⋂√'

/**
 * 裸上标/下标的匹配正则
 *
 * ⚠️ **不要复用这个带 `g` 的实例** —— JS 的正则对象带 `lastIndex` 状态，
 * 跨调用复用时第二次会从上次结束位置继续，导致**前面的匹配被跳过**。
 * （2026-10-26 实测：`C_7^3` 在第一次调用里被找到，同一个页面里
 *   第二次渲染同一段文本时就找不到了 —— 表现为"某些题有公式、某些没有"。）
 *
 * 所以 `findBareScripts` 内部每次都用 `makeBareScriptRe()` 造新实例。
 */
const BARE_SCRIPT_SOURCE =
  `(?:[${UNICODE_BIG_OPS}]|[A-Za-z\\u0391-\\u03A9\\u03B1-\\u03C9](?![A-Za-z])|[0-9](?![0-9]))` +
  '(?:[_^](?:\\{[^{}]{0,40}\\}|[A-Za-z0-9]))+'

/** 每次调用返回一个**全新的**正则实例（避免 `lastIndex` 状态污染） */
function makeBareScriptRe(): RegExp {
  return new RegExp(BARE_SCRIPT_SOURCE, 'g')
}

/**
 * 找出「裸上标/下标」形态的公式区间
 *
 * ── 为什么需要这个函数（2026-10-26）────────────────────────────────
 * 后端 `bank_export_service` 早在 v3 里就支持了裸写法识别，但**前端没有**。
 * 后果是同一个 `C_7^3=35`：
 *
 *   页面上看到  → `C_7^3=35`（下划线、花括号原样呈现）
 *   导出的 Word → 正确的组合数排版
 *
 * 用户会发现"屏幕上和下载的不一样"，这比两边都错更让人困惑。
 * 所以这里把识别规则**与后端对齐**，保证两端行为一致。
 *
 * @param text 已把 `$...$` 公式替换成占位符之后的文本
 * @param occupied 已被反斜杠命令占用的区间（避免重复圈选）
 */
function findBareScripts(
  text: string,
  occupied: Array<{ start: number; end: number }> = [],
): Array<{ start: number; end: number; latex: string }> {
  if (!text) return []
  const out: Array<{ start: number; end: number; latex: string }> = []
  const isFree = (s: number, e: number) =>
    !occupied.some((o) => s < o.end && e > o.start)

  const re = makeBareScriptRe()
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const s = m.index
    const e = s + m[0].length
    if (!isFree(s, e)) continue
    // 前面若紧贴 **ASCII 字母/数字/下划线**，说明是更长单词的一部分
    // （`value_1`、`abc^2`），不当作公式。
    //
    // ⚠️ 这里**不能**用 JS 的 `\w` 或 `[A-Za-z0-9_]` 之外的宽松判断：
    //    中文紧邻公式是常态（`由∫_{-∞}^{+∞}f(x)dx=1`），
    //    若把汉字也算作"单词的一部分"就会漏掉整条积分式
    //    （后端踩过这个坑，用的是 `isascii() and isalnum()`）。
    if (s > 0) {
      const prev = text[s - 1]
      if (/[A-Za-z0-9_]/.test(prev) || prev === '^' || prev === '_') continue
    }
    out.push({ start: s, end: e, latex: text.substring(s, e) })
  }
  return out
}

function findBareLatexCommands(text: string): Array<{ start: number; end: number; latex: string }> {
  const found: Array<{ start: number; end: number; latex: string }> = []
  const cmdRegex = /\\([a-zA-Z]+)/g
  let match: RegExpExecArray | null

  while ((match = cmdRegex.exec(text)) !== null) {
    const cmdStart = match.index
    // ⚠️ 前面若紧跟 `$`，说明已在 `$...$` 里，交给块级/行内公式那条路径处理
    let back = cmdStart - 1
    while (back >= 0 && text[back] === ' ') back--
    if (back >= 0 && text[back] === '$') continue

    let pos = cmdRegex.lastIndex
    while (pos < text.length && text[pos] === ' ') pos++

    // 收集连续的 `{...}` 组（支持嵌套），如 \frac{A}{k(k+1)}
    //
    // ⚠️ 还要吃掉紧贴在花括号前的 `_` / `^` 标记（2026-10-27 修）：
    //    大运算符的上下限写法是 `\sum_{i=1}^{n}` / `\int_{0}^{1}`，
    //    命令和花括号之间夹着 `_`。
    //    原来的实现只找"紧跟着就是 `{`"，于是 `\sum_{i=1}^{n}i` 里的
    //    `\sum` 找不到任何花括号组 → 整条被当成普通文本漏掉，
    //    用户看到的是 `\sum_{i=1}^{n}i` 原文。
    const braceGroups: string[] = []
    let scanPos = pos
    while (scanPos < text.length) {
      // 允许一个可选的下标/上标标记
      let cursor = scanPos
      if (text[cursor] === '_' || text[cursor] === '^') {
        cursor++
        while (cursor < text.length && text[cursor] === ' ') cursor++
      }
      if (text[cursor] !== '{') break

      let depth = 0
      let end = -1
      for (let i = cursor; i < text.length; i++) {
        if (text[i] === '{') depth++
        else if (text[i] === '}') {
          depth--
          if (depth === 0) {
            end = i + 1
            break
          }
        }
      }
      if (end > 0) {
        // 把可能存在的 `_` / `^` 一起纳入（保留 LaTeX 语义）
        braceGroups.push(text.substring(scanPos, end))
        scanPos = end
        while (scanPos < text.length && text[scanPos] === ' ') scanPos++
      } else {
        break
      }
    }

    if (braceGroups.length > 0) {
      found.push({ start: cmdStart, end: scanPos, latex: text.substring(cmdStart, scanPos) })
      cmdRegex.lastIndex = scanPos
    }
  }
  return found
}

/**
 * **统一渲染管线**：同时支持 `$...$` 公式 + Markdown（表格/列表等）（用户 2026-10-11 方案 A）
 *
 * 背景：项目原先三条路径各管一半——`renderQuestionContent`（裸 `\命令{}`，不认 `$`、不认表格）、
 * `renderMarkdownContent`（认表格、不认 `$`）、`renderLatexSafe`（认 `$`、不认表格）。
 * Word 导入的数学题同时有 `$...$` 公式**和** `| a | b |` 表格 → 需要一条**两者都认**的管线。
 *
 * 实现顺序（关键，不能反）：
 *   ① 先把 `$...$`/`$$...$$` 渲染成 **占位符**（避免公式内部的 `|`、`*`、`_` 被 Markdown 解析器吃掉）；
 *   ①-c 再把**裸 LaTeX 命令**（`\overline{A}` 这种没有 `$` 包裹的）也换成占位符 ——
 *       题库里绝大多数公式就是这个形态，漏掉它就会出现「反斜杠原样显示」；
 *   ② 再 `marked.parse` 渲染 Markdown（表格/列表/加粗…）；
 *   ③ 最后把占位符**回填**成 KaTeX 生成的 HTML。
 * 若先做 Markdown 再做公式，公式里的下划线会被当成斜体、`|` 会被当成表格分隔。
 */
export function renderMarkdownWithLatex(text: string): string {
  if (!text) return ''

  const stash: string[] = []
  const PH = (i: number) => `\u0000MATH${i}\u0000`

  /** 渲染一段公式并塞进 stash，返回占位符；空公式返回空串 */
  const stashMath = (formula: string, display: boolean): string => {
    const body = formula.trim()
    if (!body) return ''
    let html: string
    try {
      html = katex.renderToString(body, { displayMode: display, throwOnError: false })
    } catch {
      html = `<span class="latex-error">${body}</span>`
    }
    stash.push(html)
    return PH(stash.length - 1)
  }

  let src = text
    // ①-a 块级公式 → 占位符（`$$...$$` 与 `\[...\]` 两种写法都认）
    .replace(BLOCK_MATH_RE, (_, formula) => stashMath(formula, true))
    .replace(BLOCK_PAREN_MATH_RE, (_, formula) => stashMath(formula, true))
    // ①-b 行内公式 → 占位符（`$...$` 与 `\(...\)` 两种写法都认）
    .replace(INLINE_MATH_RE, (_, formula) => stashMath(formula, false))
    .replace(INLINE_PAREN_MATH_RE, (_, formula) => stashMath(formula, false))

  // ①-c 裸 LaTeX（无 `$` 包裹）→ 占位符。放在 Markdown 之前，避免 `_`/`|` 被误解析。
  //      ⚠️ 必须**倒序**替换，否则前面的偏移量会被后面的替换句柄搞乱。
  let bareCmds = findBareLatexCommands(src)

  // ①-d 裸上标/下标（`e^{-x}` / `C_7^3` / `∫_{0}^{10}` / `2^k`）→ 占位符
  //
  // ⚠️ 优先级（2026-10-26 与后端对齐）：**裸上标压过它内部的反斜杠命令**。
  //    典型失败案例 `e^{-\lambda}`：
  //      · 反斜杠逻辑先把 `\lambda` 圈走
  //      · 上标逻辑再找 `e^{-\lambda}` 时被"已占用"挡掉
  //      · 结果页面印成 `e^{-}`，公式只剩一个孤零零的 λ
  //    所以先跑上标，再把「被上标完整包含」的反斜杠片段剔掉。
  const scriptHits = findBareScripts(src, [])
  if (scriptHits.length) {
    bareCmds = bareCmds.filter(
      (c) => !scriptHits.some((s) => s.start <= c.start && c.end <= s.end),
    )
  }
  const allBare = [...bareCmds, ...scriptHits].sort((a, b) => a.start - b.start)

  for (let i = allBare.length - 1; i >= 0; i--) {
    const { start, end, latex } = allBare[i]
    let html: string
    try {
      // WPS 旧版别名先归一（\overbar → \overline，与 renderQuestionContent 同口径）
      const normalized = latex.replace(/^\\overbar\{/, '\\overline{').replace(/^\\underbar\{/, '\\underline{')
      html = katex.renderToString(normalized, { displayMode: false, throwOnError: false })
    } catch {
      html = `<span class="latex-error">${latex}</span>`
    }
    stash.push(html)
    src = src.substring(0, start) + PH(stash.length - 1) + src.substring(end)
  }

  // ② 表格格式容错：把"无表头分隔行的裸竖线表格"补成合法 md 表格（用户 2026-10-11：新旧两种格式都要适配）
  //    ⚠️ 放在公式占位化**之后**：此时公式已被替换成占位符，行内的 `|` 只可能来自真表格，
  //       不会被 `$a|b$` 这类公式内容干扰。
  src = normalizePipeTables(src)
  // ②-b 制表符表格容错：把"TAB 分隔的表格文本"（模型可能自己重写出的形态）转成 md 表格（第三重保险）
  src = normalizeTabTables(src)

  // ③ Markdown（gfm 启表格；breaks 让单个 \n 也换行，贴合题目文本习惯）
  src = marked.parse(src, { gfm: true, breaks: true }) as string

  // ④ 回填公式 HTML（占位符可能被 marked 包进 <p>，用 indexOf 定位替换即可）
  src = src.replace(/\u0000MATH(\d+)\u0000/g, (_, idx) => stash[Number(idx)] ?? '')

  // ⑤ 安全过滤：允许 KaTeX 的 MathML/SVG + 表格标签
  return DOMPurify.sanitize(src, {
    ADD_TAGS: [
      'svg', 'path', 'math', 'mi', 'mo', 'mn', 'msup', 'msub', 'mover', 'munder',
      'mfrac', 'msqrt', 'mrow', 'mtext', 'annotation', 'semantics', 'mspace',
      'mtable', 'mtr', 'mtd', 'munderover', 'semantics',
      'strong', 'em', 'u', 'span', 'br', 'sub', 'sup', 'img',
      'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption'
    ],
    ADD_ATTR: [
      'xmlns', 'viewBox', 'd', 'fill', 'stroke', 'stroke-width',
      'width', 'height', 'style', 'encoding', 'src', 'alt',
      'class', 'aria-hidden', 'role', 'colspan', 'rowspan', 'align',
      'mathvariant', 'stretchy', 'fence', 'separator', 'accent', 'accentunder',
      'columnalign', 'rowalign', 'columnspan', 'linethickness'
    ],
    KEEP_CONTENT: true
  })
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
