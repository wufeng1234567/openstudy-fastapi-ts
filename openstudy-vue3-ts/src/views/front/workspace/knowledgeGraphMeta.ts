export const PAGE_TYPE_META = [
  { type: 'summary', label: '摘要', color: '#3B7CFF' },
  { type: 'entity', label: '实体', color: '#2F9E8F' },
  { type: 'concept', label: '概念', color: '#F08A24' },
  { type: 'synthesis', label: '综合', color: '#2D8CF0' },
  { type: 'comparison', label: '对比', color: '#D95757' },
  { type: 'overview', label: '总览', color: '#8A94A6' }
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
  return type
}

export function entityTypeMeta(value?: string) {
  const kind = normalizeEntityKind(value)
  return ENTITY_TYPE_META.find((item) => item.type === kind) || ENTITY_TYPE_META[0]
}

export function pageTypeMeta(value?: string) {
  const type = normalizePageType(value)
  return PAGE_TYPE_META.find((item) => item.type === type) || PAGE_TYPE_META[2]
}

export function pageTypeLabel(value?: string) {
  return pageTypeMeta(value).label
}
