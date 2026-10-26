/**
 * 词库导出（2026-10-26）
 * ============================================================================
 * 三种格式，全部在**纯前端**生成 Blob 并触发下载，不经过后端。
 *
 * 为什么不用后端：
 *   · Anki 就是纯文本（`单词<TAB>释义`），Excel 用 SpreadsheetML（单个 XML
 *     就能表达表格），Word 用 HTML + `.doc` 扩展名（Word 能直接打开）。
 *     三种都只是字符串拼接，为它们各写一个 FastAPI 端点属于杀鸡用牛刀。
 *   · 不占后端带宽、不依赖网络 —— 用户离线也能导出。
 *   · 也不用装 `xlsx` / `docx` 这类重包（前者 900KB+、后者 1MB+），
 *     只为导出一个表格不值当。
 *
 * 三种格式各自解决什么：
 *   anki  —— 导入 Anki / 墨墨 / 欧路等记忆卡软件，带 tag 便于分牌组
 *   excel —— 打印、二次编辑、发给同事
 *   word  —— 打印成纸质单词表
 */

/** 一条待导出的单词 */
export interface ExportWord {
  word: string
  translation?: string | null
  phonetic?: string | null
  example?: string | null
}

/** 导出时的元信息 */
export interface ExportMeta {
  /** 词库名，用作文件名与文档标题 */
  bookName: string
  /** 可选说明 */
  description?: string | null
}

/* ============================================================
 * 通用
 * ============================================================ */

/** 文件名里的非法字符替换掉（Windows 不允许 `\ / : * ? " < > |`） */
function safeFileName(name: string, fallback = '词库'): string {
  const cleaned = String(name || '')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned || fallback
}

/** 触发浏览器下载 */
function downloadBlob(content: string | Blob, filename: string, mime: string): void {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  // 立刻 revoke 在部分浏览器会让下载失败，留一帧
  setTimeout(() => {
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, 100)
}

/**
 * 清洗文本：去掉换行/制表符
 *
 * ⚠️ 这对 TSV（Anki）和 SpreadsheetML（Excel）是**必须**的 ——
 *    一个换行就会把一条记录切成两行，导入时直接错位。
 */
function oneLine(text: unknown): string {
  return String(text ?? '')
    .replace(/[\r\n\t]+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/** HTML 转义（Excel / Word 都是 XML 或 HTML，内容里的 `<` `&` 必须转义） */
function escapeXml(text: unknown): string {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

/* ============================================================
 * Anki —— TSV 纯文本
 * ============================================================ */

/**
 * 导出 Anki 可导入的 TSV
 *
 * 格式说明：
 *   · 每行一条，字段用 **制表符** 分隔（Anki 默认分隔符）；
 *   · 第 1 列 = 正面，第 2 列 = 背面，第 3 列起 = 额外字段；
 *   · 不给表头 —— Anki 会把表头当成第一条卡片导进去。
 *
 * 背面用 `<br>` 换行（Anki 支持部分 HTML）：音标一行、例句一行，
 * 卡片翻过来时层次清楚，不会挤成一坨。
 */
export function exportAnki(words: ExportWord[], meta: ExportMeta): void {
  const lines = words.map((w) => {
    const front = oneLine(w.word)
    const parts: string[] = []
    if (w.phonetic) parts.push(`/${oneLine(w.phonetic)}/`)
    parts.push(oneLine(w.translation) || '(无释义)')
    if (w.example) parts.push(`<i>${oneLine(w.example)}</i>`)
    // 词库名做成 tag，导入后自动归到一个牌组/标签下
    const tags = oneLine(meta.bookName) ? `\t${oneLine(meta.bookName)}` : ''
    return `${front}\t${parts.join('<br>')}${tags}`
  })

  const content = lines.join('\n') + '\n'
  // 加 BOM：Windows 下用记事本打开不乱码；Anki 也接受
  downloadBlob('\ufeff' + content, `${safeFileName(meta.bookName)}-Anki.txt`, 'text/plain;charset=utf-8')
}

/* ============================================================
 * Excel —— SpreadsheetML（单个 XML，Excel 能直接打开）
 * ============================================================ */

/**
 * 导出 Excel 2003 XML（SpreadsheetML）
 *
 * 为什么不用 `xlsx` 包：只为导一个表装 900KB 的依赖不值当。
 * SpreadsheetML 是微软官方格式，Excel / WPS / LibreOffice 都能打开，
 * 而且**原生支持中文表头**、能设列宽。
 *
 * 扩展名用 `.xls`（Excel 认这个后缀；用 `.xml` 双击可能被浏览器打开）。
 */
export function exportExcel(words: ExportWord[], meta: ExportMeta): void {
  const header = ['单词', '释义', '音标', '例句']
  const rows = words.map((w) => [
    oneLine(w.word),
    oneLine(w.translation),
    w.phonetic ? `/${oneLine(w.phonetic)}/` : '',
    oneLine(w.example)
  ])

  const cell = (value: string, style?: string) =>
    `<Cell${style ? ` ss:StyleID="${style}"` : ''}><Data ss:Type="String">${escapeXml(value)}</Data></Cell>`

  const headerXml = `<Row>${header.map((h) => cell(h, 'header')).join('')}</Row>`
  const bodyXml = rows
    .map((r) => `<Row>${r.map((v, i) => cell(v, i === 0 ? 'word' : undefined)).join('')}</Row>`)
    .join('')

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Styles>
    <Style ss:ID="header">
      <Font ss:Bold="1"/>
      <Interior ss:Color="#F1F5F9" ss:Pattern="Solid"/>
    </Style>
    <Style ss:ID="word">
      <Font ss:Bold="1"/>
    </Style>
  </Styles>
  <Worksheet ss:Name="${escapeXml(safeFileName(meta.bookName, '单词表').slice(0, 30))}">
    <Table>
      <Column ss:Width="140"/>
      <Column ss:Width="280"/>
      <Column ss:Width="120"/>
      <Column ss:Width="320"/>
      ${headerXml}
      ${bodyXml}
    </Table>
  </Worksheet>
</Workbook>`

  downloadBlob(xml, `${safeFileName(meta.bookName)}.xls`, 'application/vnd.ms-excel;charset=utf-8')
}

/* ============================================================
 * Word —— HTML + .doc 扩展名
 * ============================================================ */

/**
 * 导出 Word 文档
 *
 * 用 HTML 而不是真 `.docx`：真 docx 是 ZIP 容器（要 jszip + 手写
 * OOXML 关系表），而 Word 能**直接打开**带正确 MSO 头的 HTML 并保留格式。
 * 写进 `.doc` 扩展名即可，代价是排版能力有限 —— 但对"打印单词表"
 * 这个需求，表格 + 加粗已经够了。
 *
 * 打印优化：`@page` 设 A4 边距，表头 `page-break-inside: avoid`，
 * 避免一条单词被分页切成两半。
 */
export function exportWord(words: ExportWord[], meta: ExportMeta): void {
  const title = escapeXml(meta.bookName || '单词表')
  const desc = meta.description ? `<p class="desc">${escapeXml(meta.description)}</p>` : ''
  const today = new Date().toLocaleDateString('zh-CN')

  const rows = words
    .map(
      (w) => `<tr>
      <td class="w">${escapeXml(oneLine(w.word))}</td>
      <td class="p">${w.phonetic ? '/' + escapeXml(oneLine(w.phonetic)) + '/' : ''}</td>
      <td class="t">${escapeXml(oneLine(w.translation))}</td>
      <td class="e">${escapeXml(oneLine(w.example))}</td>
    </tr>`
    )
    .join('')

  const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<title>${title}</title>
<!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument></xml><![endif]-->
<style>
  @page { size: A4; margin: 2cm 1.6cm; }
  body { font-family: "微软雅黑", "Microsoft YaHei", sans-serif; font-size: 10.5pt; color: #111; }
  h1 { font-size: 18pt; margin: 0 0 4pt; }
  .desc { font-size: 10pt; color: #666; margin: 0 0 4pt; }
  .meta { font-size: 9pt; color: #999; margin: 0 0 14pt; }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; font-size: 10pt; padding: 6pt 8pt;
       border-bottom: 1.5pt solid #333; background: #f5f5f5; }
  td { padding: 5pt 8pt; border-bottom: 0.5pt solid #ddd; vertical-align: top; }
  /* 一条单词不跨页 */
  tr { page-break-inside: avoid; }
  .w { font-weight: bold; width: 20%; }
  .p { width: 18%; color: #666; font-style: italic; }
  .t { width: 32%; }
  .e { width: 30%; color: #555; font-size: 9.5pt; }
</style>
</head>
<body>
  <h1>${title}</h1>
  ${desc}
  <p class="meta">共 ${words.length} 个单词 · 导出于 ${today}</p>
  <table>
    <thead><tr><th>单词</th><th>音标</th><th>释义</th><th>例句</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
</body>
</html>`

  downloadBlob('\ufeff' + html, `${safeFileName(meta.bookName)}.doc`, 'application/msword;charset=utf-8')
}

/** 导出格式 */
export type ExportFormat = 'anki' | 'excel' | 'word'

/** 统一入口 */
export function exportWordBook(
  format: ExportFormat,
  words: ExportWord[],
  meta: ExportMeta
): void {
  if (!words.length) return
  if (format === 'anki') exportAnki(words, meta)
  else if (format === 'excel') exportExcel(words, meta)
  else exportWord(words, meta)
}
