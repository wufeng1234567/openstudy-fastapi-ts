/** AgentToolResult 卡片摘要的纯文本工具。 */

export const labelOf = (map: Record<string, string>, key: string) => map[key] || key

export const FILLER_MESSAGES = new Set([
  'ok',
  'ok.',
  'success',
  'success.',
  'done',
  'done.',
  '成功',
  '已完成',
  '完成',
  '失败'
])

export const DATA_SUMMARIES: [string, (n: number) => string][] = [
  ['banks', (n) => `共 ${n} 个题库`],
  ['questions', (n) => `共 ${n} 道题目`],
  ['notes', (n) => `共 ${n} 篇笔记`],
  ['categories', (n) => `共 ${n} 个笔记分类`],
  ['imported', (n) => `已导入 ${n} 道题目`],
  ['deleted', (n) => `已删除 ${n} 项`],
  ['items', (n) => `共 ${n} 条结果`],
  ['count', (n) => `共 ${n} 条`],
  ['total', (n) => `共 ${n} 条`]
]

export const MAX_SUMMARY_CHARS = 80

export const clip = (text: string) => {
  const s = (text || '').trim()
  return s.length > MAX_SUMMARY_CHARS ? `${s.slice(0, MAX_SUMMARY_CHARS)}…` : s
}

export function summarizeData(data: any): string {
  if (!data || typeof data !== 'object') return ''
  if (typeof data.headline === 'string' && data.headline.trim()) {
    return clip(data.headline)
  }
  for (const [key, render] of DATA_SUMMARIES) {
    const value = data[key]
    const isList = Array.isArray(value)
    const n = isList ? value.length : typeof value === 'number' ? value : null
    if (n === null) continue
    if (isList && typeof data.total === 'number' && data.total > n) {
      return `${render(data.total)}（本次返回 ${n} 条）`
    }
    return render(n)
  }
  const named =
    data.bankName ||
    data.bank_name ||
    data.name ||
    data.note?.title ||
    data.title ||
    data.bank?.bankName ||
    data.question?.questionText ||
    data.keyword
  return named ? clip(String(named)) : ''
}
