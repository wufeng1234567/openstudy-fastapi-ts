import { computed } from 'vue'
import { normalizeEntityKind, entityTypeMeta } from '../utils/knowledgeGraphMeta'

/**
 * 知识图谱的派生展示数据：类型计数、连通/孤立节点、跨源桥接、
 * 分组与分组索引、搜索建议、学习理由文案。
 *
 * 从 KnowledgeWikiPanel.vue 抽出的纯 computed / 纯函数，只读传入的 ref，
 * 不含任何 API、轮询、拖拽、缩放或计时逻辑。返回的名字以原名解构回
 * `<script setup>`，模板与脚本调用点保持不变。
 */
export function useWikiGraphDerived(options: {
  allMapNodes: any
  mapGraph: any
  props: any
  searchSuppressed: any
  view: any
  learningRoute: any
}) {
  const { allMapNodes, mapGraph, props, searchSuppressed, view, learningRoute } = options

  const mapTypeCounts = computed(() => {
    const counts: Record<string, number> = {}
    for (const node of allMapNodes.value) {
      const kind = normalizeEntityKind(node.kind || node.pageType)
      counts[kind] = (counts[kind] || 0) + 1
    }
    return counts
  })
  const mapConnectedNodeIds = computed(() => {
    const ids = new Set(allMapNodes.value.map((node: any) => String(node.id)))
    const connected = new Set<string>()
    for (const edge of mapGraph.value?.edges || []) {
      const source = String(edge.source || '')
      const target = String(edge.target || '')
      if (ids.has(source) && ids.has(target)) {
        connected.add(source)
        connected.add(target)
      }
    }
    return connected
  })
  const unlinkedCount = computed(() =>
    allMapNodes.value.filter((node: any) => !mapConnectedNodeIds.value.has(String(node.id))).length
  )

  const graphSearchSuggestions = computed(() => {
    const query = String(props.searchQuery || '').trim().toLowerCase()
    if (searchSuppressed.value || !query || view.value !== 'map') return []
    return allMapNodes.value
      .filter((node: any) => {
        const detail = node.detail || {}
        const haystack = [
          node.title,
          node.summary,
          detail.summary,
          node.subtitle,
          ...(node.aliases || []),
          ...(detail.aliases || [])
        ].join(' ').toLowerCase()
        return haystack.includes(query)
      })
      .sort((a: any, b: any) => {
        const at = String(a.title || '').toLowerCase()
        const bt = String(b.title || '').toLowerCase()
        return Number(bt === query) - Number(at === query) || at.localeCompare(bt)
      })
      .slice(0, 8)
  })

  const mapComponents = computed(() => {
    const nodes = allMapNodes.value
    const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
    const groups = Array.isArray(mapGraph.value?.groups) ? mapGraph.value.groups : []
    if (groups.length) {
      return {
        components: groups
          .map((group: any) => ({
            key: String(group.id || group.kind),
            kind: normalizeEntityKind(group.kind),
            label: String(group.title || entityTypeMeta(group.kind).label),
            ids: (group.nodeIds || []).map(String).filter((id: string) => byId.has(id))
          }))
          .filter((group: any) => group.ids.length),
        byId
      }
    }
    const grouped = new Map<string, string[]>()
    for (const node of nodes) {
      const kind = normalizeEntityKind(node.kind || node.pageType)
      if (!grouped.has(kind)) grouped.set(kind, [])
      grouped.get(kind)!.push(String(node.id))
    }
    return {
      components: [...grouped.entries()].map(([kind, ids]) => ({
        key: kind,
        kind,
        label: entityTypeMeta(kind).label,
        ids
      })),
      byId
    }
  })

  const groupKeyByNode = computed(() => {
    const result = new Map<string, string>()
    for (const component of mapComponents.value.components) {
      for (const id of component.ids) result.set(String(id), component.key)
    }
    return result
  })

  function isCrossSourceEdge(edge: any) {
    if (String(edge.type || '') === 'document_image') return false
    const source = allMapNodes.value.find((node: any) => String(node.id) === String(edge.source))
    const target = allMapNodes.value.find((node: any) => String(node.id) === String(edge.target))
    if (!source || !target) return false
    if (normalizeEntityKind(source.kind) === 'topic' || normalizeEntityKind(target.kind) === 'topic') return false
    return groupKeyByNode.value.get(String(edge.source)) !== groupKeyByNode.value.get(String(edge.target))
  }

  const bridgeNodeIds = computed(() => {
    const result = new Set<string>()
    for (const edge of mapGraph.value?.edges || []) {
      if (!isCrossSourceEdge(edge)) continue
      result.add(String(edge.source))
      result.add(String(edge.target))
    }
    return result
  })

  function learningReason(node: any) {
    const routeStop = (learningRoute.value?.stops || []).find(
      (stop: any) => Number(stop.pageId) === Number(node?.pageId ?? node?.id)
    )
    if (routeStop?.reason) return routeStop.reason
    const learning = node?.learning || {}
    const accuracy = Number(learning.accuracy || 0)
    if (!Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
      return `还没读过 · 连接 ${Number(node?.degree || 0)} 个主题`
    }
    if (Number(learning.practiceCount || 0) && accuracy < 60) {
      return `练习正确率 ${accuracy}% · 建议回看`
    }
    if (Number(learning.viewCount || 0) && !Number(learning.practiceCount || 0)) {
      return '已读但还没练过'
    }
    if (Number(learning.practiceCount || 0) && accuracy < 80) {
      return `正确率 ${accuracy}% · 再练一轮`
    }
    if (learning.level === 'mastered') return '已掌握 · 可快速复习'
    return '按图谱连接继续探索'
  }

  return {
    mapTypeCounts,
    mapConnectedNodeIds,
    unlinkedCount,
    graphSearchSuggestions,
    mapComponents,
    groupKeyByNode,
    isCrossSourceEdge,
    bridgeNodeIds,
    learningReason
  }
}
