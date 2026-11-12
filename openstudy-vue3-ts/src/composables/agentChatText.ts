/** Agent 产出文本的保守 Markdown 清理（供专家结论纯文本渲染）。 */

/**
 * 去掉子代理产出里的 Markdown 标记（用户 2026-10-11：专家结论不该露 `*` `#` 之类符号）。
 *
 * 专家的结论走**纯文本插值**渲染（`AiChatStream` 的 `{{ ex.summary }}`），不是 md 渲染器
 * ——若后端把 `**加粗**`、`- 列表`、`# 标题`、`` `代码` `` 原样带过来，用户看到的就是一堆
 * 标记符号。这里做**保守剥离**（只去标记、不动正文），让结论读起来是干净的句子。
 *
 * 只处理常见行内/行首标记；不做完整 md 解析（专家结论多为短句，过度解析反而危险）。
 */
export function stripMarkdown(text: string): string {
  if (!text) return ''
  return (
    text
      // 行首：标题 #、引用 >、无序列表 -/*/+ 、有序列表 1.
      .replace(/^[ \t]*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/gm, '')
      // 围栏代码块标记 ``` / ~~~（保留里面的内容）
      .replace(/^[ \t]*(?:```|~~~).*$/gm, '')
      // 行内代码 `x` → x
      .replace(/`([^`]*)`/g, '$1')
      // 加粗 / 斜体：**x** __x__ *x* _x_ → x
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/__([^_]+)__/g, '$1')
      .replace(/\*([^*\n]+)\*/g, '$1')
      .replace(/_([^_\n]+)_/g, '$1')
      // 删除线 ~~x~~ → x
      .replace(/~~([^~]+)~~/g, '$1')
      // 链接 [文字](url) → 文字 ；图片 ![alt](url) → alt
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      // Markdown 表格 → 可读行（| 指标 | 数值 | 行转成「指标：数值」，分隔行删除）
      .replace(/[\s\S]*/, (s) => stripMarkdownTables(s))
      // 收尾：合并多余空行
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  )
}

/**
 * 把 **Markdown 表格**转成「可读的行」（用户 2026-10-11：子代理结论里会出现
 * `| 指标 | 数值 |` / `|---|---|` 这类表格语法，纯文本插值下就是把竖线和横线糊在脸上）。
 *
 * 处理规则（**保守**，只认"标准表格形态"，别误伤正常的 `|`）：
 *   1. **分隔行**（只由 `|`、`-`、`:` 和空白组成的行，如 `|---|---|`）→ 整行删除；
 *   2. **表头行 + 数据行**：形如 `| a | b | c |`（或首尾竖线可省）的连续行 → 去首尾 `|`，
 *      单元格 trim 后：两列用 `：` 连（`指标：数值`），三列及以上用 ` · ` 连（`a · b · c`）。
 *
 * ⚠️ 只在**真出现分隔行**或**该行首尾有 `|`** 时才当表格处理 —— 避免把正文里偶尔出现的
 *    单个 `|`（如 "TCP | UDP 的区别"）误转。
 */
function stripMarkdownTables(text: string): string {
  const lines = text.split('\n')
  const isSeparator = (s: string) => /^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$/.test(s)
  const isTableRow = (s: string) => {
    const t = s.trim()
    // 首尾都有 `|`，或中间有 >=2 个 `|`（≥3 单元格）才算表格行；单个 `|` 不算
    return (t.startsWith('|') && t.endsWith('|') && t.length > 1) || (t.match(/\|/g) || []).length >= 2
  }
  const renderRow = (s: string) => {
    const cells = s
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim())
      .filter((c) => c.length > 0)
    if (cells.length === 0) return ''
    if (cells.length === 2) return `${cells[0]}：${cells[1]}`
    return cells.join(' · ')
  }
  const out: string[] = []
  for (const line of lines) {
    if (isSeparator(line) && line.includes('-')) continue // 分隔行：丢弃
    if (isTableRow(line)) {
      const r = renderRow(line)
      if (r) out.push(r)
      continue
    }
    out.push(line)
  }
  return out.join('\n')
}

