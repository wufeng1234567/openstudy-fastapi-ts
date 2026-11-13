import { computed } from 'vue'

/**
 * 知识图谱「学习态」面板的纯展示 computed。
 *
 * 从 KnowledgeWikiPanel.vue 抽出：学习概览、推荐、路线站点、当前站点、
 * 离线路线页面、下一步、路径节点与路径 SVG path。全部是惰性 computed，
 * 只读传入的 ref / 函数，不改变任何 API、轮询、拖拽/缩放或事件时序。
 * 返回的名字以原名解构回 `<script setup>`，模板与脚本调用点保持不变。
 */
export function useWikiLearningDisplay(options: {
  mapNodes: any
  learningPriority: (node: any) => number
  learningReason: (node: any) => string
  learningRoute: any
  routeActive: any
  detailVisible: any
  activePage: any
  mapLearningPath: any
}) {
  const {
    mapNodes, learningPriority, learningReason, learningRoute,
    routeActive, detailVisible, activePage, mapLearningPath
  } = options

  const mapLearnSummary = computed(() => {
    const nodes = mapNodes.value
    const read = nodes.filter((node: any) => Number(node.learning?.viewCount || 0) > 0).length
    const practiced = nodes.filter((node: any) => Number(node.learning?.practiceCount || 0) > 0).length
    const mastered = nodes.filter((node: any) => node.learning?.level === 'mastered').length
    const weak = nodes.filter((node: any) => {
      const learning = node.learning || {}
      return Number(learning.practiceCount || 0) > 0 && Number(learning.accuracy || 0) < 60
    }).length
    return {
      total: nodes.length,
      read,
      practiced,
      mastered,
      weak,
      coverage: nodes.length ? Math.round((read / nodes.length) * 100) : 0
    }
  })

  const learningRecommendations = computed(() =>
    [...mapNodes.value]
      .map((node: any) => ({ node, score: learningPriority(node), reason: learningReason(node) }))
      .sort((a, b) => b.score - a.score || Number(b.node.degree || 0) - Number(a.node.degree || 0))
      .slice(0, 3)
  )

  const routeStopsView = computed(() => {
    const byId = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
    return (learningRoute.value?.stops || [])
      .map((stop: any) => {
        const node = byId.get(String(stop.pageId))
        return node ? { ...stop, node } : null
      })
      .filter(Boolean) as any[]
  })

  const activeRouteStop = computed(() =>
    routeStopsView.value.find((stop: any) => stop.status === 'current') ||
    routeStopsView.value.find((stop: any) => stop.learning?.level !== 'mastered') ||
    routeStopsView.value[0] ||
    null
  )

  const offRoutePage = computed(() => {
    if (!routeActive.value || !detailVisible.value || !activePage.value) return null
    const pageId = Number(activePage.value.pageId)
    const inRoute = (learningRoute.value?.stops || []).some(
      (stop: any) => Number(stop.pageId) === pageId
    )
    return inRoute ? null : activePage.value
  })

  const nextLearningStep = computed(() => {
    const routeStop = activeRouteStop.value
    if (routeStop?.node) return { node: routeStop.node, reason: routeStop.reason }
    return learningRecommendations.value[0] || null
  })

  const learningPathItems = computed(() => {
    if (routeStopsView.value.length) {
      return routeStopsView.value.map((stop: any) => ({ node: stop.node, reason: stop.reason }))
    }
    const byId = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
    return mapLearningPath.value
      .map((id) => {
        const node = byId.get(id)
        return node ? { node, reason: learningReason(node) } : null
      })
      .filter(Boolean) as Array<{ node: any; reason: string }>
  })

  const learningPathD = computed(() => {
    const items = learningPathItems.value
    if (items.length < 2) return ''
    const edges = learningRoute.value?.edges || []
    const routeEdgeSet = new Set(
      edges.map((edge: any) => `${String(edge.source)}|${String(edge.target)}`)
    )
    const segments: string[] = []
    for (let index = 1; index < items.length; index += 1) {
      const previous = items[index - 1].node
      const current = items[index].node
      const forward = `${String(previous.id)}|${String(current.id)}`
      const backward = `${String(current.id)}|${String(previous.id)}`
      // 只画图谱里真实存在的相邻边；没有边就不画，绝不把启发式顺序伪装成前置关系。
      if (!routeEdgeSet.has(forward) && !routeEdgeSet.has(backward)) continue
      segments.push(`M${Number(previous.x)} ${Number(previous.y)} L${Number(current.x)} ${Number(current.y)}`)
    }
    return segments.join(' ')
  })

  return {
    mapLearnSummary,
    learningRecommendations,
    routeStopsView,
    activeRouteStop,
    offRoutePage,
    nextLearningStep,
    learningPathItems,
    learningPathD
  }
}
