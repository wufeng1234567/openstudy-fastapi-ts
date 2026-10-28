/**
 * Markdown 表格归一化测试（无浏览器 / 无网络）
 *
 * 复现并锁死用户 2026-10-28 报告的 bug：
 *   合法 Markdown 表格（已有 `| --- |` 分隔行）被 normalizePipeTables 当成
 *   “无表头的裸表格”又补了一行分隔行，最终页面上多渲染一行 `---`。
 *
 * 运行：node tests/latex-table.test.mjs
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'
import { marked } from 'marked'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')

const results = []
function check(name, cond, detail = '') {
  results.push({ name, ok: !!cond, detail })
  console.log(`  ${cond ? 'PASS' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`)
}

const count = (text, re) => (text.match(re) || []).length
const tableRows = (html) => {
  const m = html.match(/<table[\s\S]*?<\/table>/i)
  if (!m) return 0
  return count(m[0], /<tr\b/gi)
}
const tableCells = (html) => count(html, /<t[hd]\b/gi)
const visibleText = (html) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()

const server = await createServer({
  root: ROOT,
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
})
const mod = await server.ssrLoadModule('/src/utils/latex.ts')

try {
  const { normalizePipeTables, normalizeTabTables } = mod

  const md = [
    '| Y \\ X | 0 | 1 | 2 |',
    '| --- | --- | --- | --- |',
    '| 0 | 0.1 | 0.3 | 0.2 |',
    '| 1 | 0.2 | 0.1 | 0.1 |',
  ].join('\n')

  // ── 1. 合法 Markdown 表格：只允许一个分隔行，--- 不能变成数据行 ──
  const normalized = normalizePipeTables(md)
  const separatorLines = normalized.split('\n').filter((l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l))
  check('合法表格只保留 1 个分隔行', separatorLines.length === 1, `实际 ${separatorLines.length} 个`)
  check('合法表格没有被改写（行数不变）', normalized.split('\n').length === 4, `实际 ${normalized.split('\n').length} 行`)

  const html = marked.parse(normalized, { gfm: true, breaks: true })
  check('marked 识别为 1 张表', count(html, /<table\b/gi) === 1, `table=${count(html, /<table\b/gi)}`)
  check('表格只有 3 行（表头 + 2 数据行）', tableRows(html) === 3, `tr=${tableRows(html)}`)
  check('表格共 12 个单元格', tableCells(html) === 12, `cells=${tableCells(html)}`)
  check('页面上没有残留的 --- 行', !visibleText(html).includes('---'), visibleText(html).slice(0, 120))
  check('表头保留 Y \\ X', visibleText(html).includes('Y \\ X'), visibleText(html).slice(0, 80))

  // ── 2. 裸竖线表格（无分隔行）：应补 1 个分隔行，且不重复 ──
  const bare = [
    'X\\Y | 0 | 1 | 2',
    '0 | 0.1 | 0.3 | 0.2',
    '1 | 0.2 | 0.1 | 0.1',
  ].join('\n')
  const bareNorm = normalizePipeTables(bare)
  const bareSep = bareNorm.split('\n').filter((l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l))
  const bareHtml = marked.parse(bareNorm, { gfm: true, breaks: true })
  check('裸表格补 1 个分隔行', bareSep.length === 1, `实际 ${bareSep.length} 个`)
  check('裸表格渲染 3 行', tableRows(bareHtml) === 3, `tr=${tableRows(bareHtml)}`)
  check('裸表格无 --- 残留', !visibleText(bareHtml).includes('---'), visibleText(bareHtml).slice(0, 120))

  // ── 3. TAB 表格（无分隔行）：应补 1 个分隔行 ──
  const tab = [
    'Y \\ X\t0\t1\t2',
    '0\t0.1\t0.3\t0.2',
    '1\t0.2\t0.1\t0.1',
  ].join('\n')
  const tabNorm = normalizeTabTables(tab)
  const tabSep = tabNorm.split('\n').filter((l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l))
  const tabHtml = marked.parse(tabNorm, { gfm: true, breaks: true })
  check('TAB 表格补 1 个分隔行', tabSep.length === 1, `实际 ${tabSep.length} 个`)
  check('TAB 表格渲染 3 行', tableRows(tabHtml) === 3, `tr=${tableRows(tabHtml)}`)

  // ── 4. TAB 表格自带分隔行：不能再补一行 ──
  const tabWithSep = [
    'Y \\ X\t0\t1\t2',
    '---\t---\t---\t---',
    '0\t0.1\t0.3\t0.2',
    '1\t0.2\t0.1\t0.1',
  ].join('\n')
  const tabWithSepNorm = normalizeTabTables(tabWithSep)
  const tabWithSepCount = tabWithSepNorm.split('\n').filter((l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l))
  const tabWithSepHtml = marked.parse(tabWithSepNorm, { gfm: true, breaks: true })
  check('TAB 表格自带分隔行时不重复补', tabWithSepCount.length === 1, `实际 ${tabWithSepCount.length} 个`)
  check('TAB 表格自带分隔行渲染 3 行', tableRows(tabWithSepHtml) === 3, `tr=${tableRows(tabWithSepHtml)}`)
} finally {
  await server.close()
}

const failed = results.filter((r) => !r.ok)
console.log(`\n结果：${results.length - failed.length} / ${results.length} 项通过`)
if (failed.length) process.exit(1)
