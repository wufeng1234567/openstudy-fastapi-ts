/** 知识百科/图谱的纯展示格式化函数。 */
export function useWikiPanelFormatters(options: { mapNodes: any }) {
  const { mapNodes } = options

function mapEdgeTitle(edge: any) {
  const source = mapNodes.value.find((node: any) => String(node.id) === String(edge.source))
  const target = mapNodes.value.find((node: any) => String(node.id) === String(edge.target))
  const label = String(edge.label || edge.type || '关系')
  return `${label}：${source?.title || edge.source} → ${target?.title || edge.target}`
}

const learningLegend = [
  { level: 'unread', label: '未学', color: '#cbd3df' },
  { level: 'reading', label: '已读', color: '#5b8def' },
  { level: 'practicing', label: '练习中', color: '#f0a13a' },
  { level: 'mastered', label: '已掌握', color: '#2f9e8f' }
]

function learningColor(learning: any) {
  return learningLegend.find((item) => item.level === learning?.level)?.color || '#cbd3df'
}

function learningPriority(node: any) {
  const learning = node?.learning || {}
  const accuracy = Number(learning.accuracy || 0)
  const degree = Number(node?.degree || 0)
  if (!Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return 100 + degree * 2
  }
  if (Number(learning.practiceCount || 0) && accuracy < 60) {
    return 140 + (60 - accuracy)
  }
  if (Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
    return 70 + degree
  }
  if (Number(learning.practiceCount || 0) && accuracy < 80) return 60
  if (learning.level === 'mastered') return 10
  return 20
}


function statusLabel(status: string) {
  if (status === 'stale') return '待更新'
  if (status === 'failed') return '生成失败'
  if (status === 'draft') return '整理中'
  return '已整理'
}

function sectionLabel(index: number) {
  return Number(index) < 0 ? '摘要' : `第 ${Number(index) + 1} 节`
}

function linkSectionsLabel(item: any) {
  const indexes = Array.isArray(item?.sectionIndexes) && item.sectionIndexes.length
    ? item.sectionIndexes
    : [item?.sectionIndex]
  const labels = indexes.map((index: number) => sectionLabel(index))
  if (labels.length <= 2) return labels.join('、')
  return `${labels.slice(0, 2).join('、')} 等 ${labels.length} 节`
}

function linkTypeLabel(type: string) {
  if (type === 'prerequisite') return '先学'
  if (type === 'contrast') return '对比'
  if (type === 'part_of') return '结构'
  return '相关'
}

function formatTime(value?: string) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}



  return {
    mapEdgeTitle,
    learningLegend,
    learningColor,
    learningPriority,
    statusLabel,
    sectionLabel,
    linkSectionsLabel,
    linkTypeLabel,
    formatTime
  }
}
