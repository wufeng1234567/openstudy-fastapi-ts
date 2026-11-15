/**
 * 主题页展示类型：六个后端类型收敛为四组。
 *
 * 后端仍保留 summary/entity/concept/synthesis/comparison/overview 六个值，
 * 前端统一映射到四组，避免节点颜色过多、图例难读。
 */
export const PAGE_TYPE_META = [
  { type: 'concept', label: '概念 / 实体', color: '#F08A24', legacyTypes: ['concept', 'entity'] },
  { type: 'method', label: '方法 / 公式', color: '#2F9E8F', legacyTypes: ['method'] },
  { type: 'synthesis', label: '综合 / 概览', color: '#2D8CF0', legacyTypes: ['synthesis', 'overview', 'summary'] },
  { type: 'comparison', label: '对比', color: '#D95757', legacyTypes: ['comparison'] }
] as const

/** 知识图谱的六个实体集类型。 */
export const ENTITY_TYPE_META = [
  { type: 'topic', label: '知识主题', color: '#F08A24' },
  { type: 'bank', label: '题库', color: '#2F9E8F' },
  { type: 'document', label: '资料', color: '#3B7CFF' },
  { type: 'web', label: '网页', color: '#2D8CF0' },
  { type: 'note', label: '笔记', color: '#8A94A6' },
  { type: 'image', label: '图片', color: '#D95757' }
] as const

export function normalizeEntityKind(value?: string) {
  const type = String(value || '').trim()
  if (type === 'wiki') return 'topic'
  if (['topic', 'bank', 'document', 'web', 'note', 'image'].includes(type)) return type
  return 'topic'
}

export function normalizePageType(value?: string) {
  const type = String(value || '').trim()
  if (!type || type === 'topic' || type === 'wiki') return 'concept'
  // 合并旧类型：摘要/总览进入综合，实体进入概念，避免图谱出现六种颜色。
  if (type === 'summary' || type === 'overview') return 'synthesis'
  if (type === 'entity') return 'concept'
  if (['concept', 'method', 'synthesis', 'comparison'].includes(type)) return type
  return 'concept'
}

/**
 * 主题页类型推断：后端历史页面大量是 concept，单纯按 pageType 着色仍会一片橙。
 * 这里按标题/度做一层展示分类，让“方法/公式”“综合/概览”“对比”在图上可见。
 */
export function inferPageType(value: string | undefined, title: string | undefined, degree: number | string | undefined) {
  const base = normalizePageType(value)
  if (base !== 'concept') return base
  if (Number(degree || 0) >= 8) return 'synthesis'
  const text = String(title || '')
  if (/对比|比较|异同|区别/.test(text)) return 'comparison'
  if (/综合|总览|概览/.test(text)) return 'synthesis'
  if (/求导|判定|计算|求解|证明|推导|方法|公式|定理|算法|流程|步骤/.test(text)) return 'method'
  return 'concept'
}

export function entityTypeMeta(value?: string) {
  const kind = normalizeEntityKind(value)
  return ENTITY_TYPE_META.find((item) => item.type === kind) || ENTITY_TYPE_META[0]
}

export function pageTypeMeta(value?: string) {
  const type = normalizePageType(value)
  return PAGE_TYPE_META.find((item) => item.type === type) || PAGE_TYPE_META[0]
}

export function pageTypeLabel(value?: string) {
  return pageTypeMeta(value).label
}
