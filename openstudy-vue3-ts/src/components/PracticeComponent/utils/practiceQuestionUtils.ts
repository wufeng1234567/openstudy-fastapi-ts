import type { MockExamConfig } from '@/types'

/** 题型归一：后端数字题型 → 前端字符串。 */
export function normalizeType(raw: any): string {
  switch (Number(raw)) {
    case 1: return 'single'
    case 2: return 'multiple'
    case 3: return 'truefalse'
    case 4: return 'fillblank'
    case 5: return 'essay'
    case 6: return 'readingComprehension'
    case 7: return 'cloze'
    default: return String(raw || 'unknown')
  }
}

/** 按模拟考试配置组卷；每道题带 _mockScore / _mockType 供交卷判分。 */
export function buildMockPaper(cfg: MockExamConfig, pool: any[]): any[] {
  const byType = new Map<string, any[]>()
  for (const q of pool) {
    const t = normalizeType(q.questionType ?? q.question_type)
    if (!byType.has(t)) byType.set(t, [])
    byType.get(t)!.push(q)
  }

  const picked: any[] = []
  for (const row of cfg.typeRows) {
    const list = byType.get(row.type) || []
    if (!list.length || row.count <= 0) continue
    const shuffled = [...list]
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    for (const q of shuffled.slice(0, row.count)) {
      picked.push({ ...q, _mockScore: Number(row.score) || 0, _mockType: row.type })
    }
  }

  for (let i = picked.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[picked[i], picked[j]] = [picked[j], picked[i]]
  }
  return picked
}

export function fullStem(q: any): string {
  const raw = String(q?.content ?? q?.questionText ?? q?.question ?? '')
  return raw.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

export function plainText(raw: any): string {
  if (!raw) return ''
  return String(raw).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

export function normalizeOptionList(opts: any): any[] {
  if (!Array.isArray(opts)) return []
  return opts.map((o: any) => {
    if (o === null || o === undefined) return ''
    if (typeof o === 'object') {
      const v = o.text ?? o.value ?? o.content ?? o.label ?? o.key ?? ''
      return typeof v === 'string' ? v : String(v)
    }
    return String(o)
  })
}
