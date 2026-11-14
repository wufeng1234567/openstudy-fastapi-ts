import { computed } from 'vue'
import { normalizeEntityKind } from '../utils/knowledgeGraphMeta'
import { buildMapEdge } from './wikiMapGeometry'

/**
 * 知识图谱的边（连线）纯展示 computed。
 *
 * 从 KnowledgeWikiPanel.vue 抽出：首屏只画节点、题库连线首屏隐藏、
 * 图片节点折叠、按焦点/学习路线过滤、按 key 去重。全部是惰性 computed，
 * 只读传入的 ref，不含任何 API、事件监听、拖拽/缩放或计时逻辑。
 */
export function useWikiMapEdges(options: {
  mapHoveredId: any
  mapSelectedNodeId: any
  routeActive: any
  detailVisible?: any
  adviceAnimating?: any
  mapNodes: any
  allMapNodes: any
  mapImageExpanded: any
  mapGraph: any
  IMAGE_CLUSTER_ID: string
  isCrossSourceEdge: (edge: any) => boolean
}) {
  const {
    mapHoveredId, mapSelectedNodeId, routeActive, detailVisible, adviceAnimating, mapNodes, allMapNodes,
    mapImageExpanded, mapGraph, IMAGE_CLUSTER_ID, isCrossSourceEdge
  } = options

  // 这些集合只在节点列表变化时重算；hover 不应重复扫描 200+ 节点。
  const nodePositions = computed(() =>
    new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  )
  const imageIds = computed(() =>
    new Set(
      allMapNodes.value
        .filter((node: any) => normalizeEntityKind(node.kind) === 'image')
        .map((node: any) => String(node.id))
    )
  )
  // 邻接索引只在图数据变化时重建；hover 时直接从索引取边，避免扫描全图。
  const edgesByNode = computed(() => {
    const index = new Map<string, any[]>()
    for (const edge of mapGraph.value?.edges || []) {
      const source = String(edge.source || '')
      const target = String(edge.target || '')
      if (!source || !target) continue
      if (!index.has(source)) index.set(source, [])
      if (!index.has(target)) index.set(target, [])
      index.get(source)!.push(edge)
      index.get(target)!.push(edge)
    }
    return index
  })

  const mapEdges = computed(() => {
    // 详情抽屉打开时不再渲染选中节点周边连线，避免 200+ 节点场景下
    // 抽屉滑入和全图连线同时重绘造成 2-3 秒掉帧。
    if (detailVisible?.value) return []
    // 建议射线动画播放期间，hover 边必须让位，避免两套连线叠在同一张图上。
    if (adviceAnimating?.value) return []
    // 首屏只显示节点：避免资料/主题/题库之间的大量连线把结构盖住。
    // 只有悬停、选中节点，或进入学习路线后，才显示相关连线。
    const focusId = mapHoveredId.value || mapSelectedNodeId.value
    if (!focusId && !routeActive.value) return []
    const positions = nodePositions.value
    const collapseImages = !mapImageExpanded.value && imageIds.value.size > 8
    const endpoint = (id: any) => collapseImages && imageIds.value.has(String(id)) ? IMAGE_CLUSTER_ID : String(id)
    const allEdges = mapGraph.value?.edges || []
    // 先按焦点过滤原始边，再做端点映射和坐标计算；否则每次 hover 都要
    // 遍历整张图（题库边可能上千条），这是 200 节点图谱卡顿的主要来源。
    const indexed = focusId ? edgesByNode.value.get(String(focusId)) : null
    const focusedEdges = focusId
      ? indexed || allEdges.filter((edge: any) =>
          String(edge.source) === String(focusId) ||
          String(edge.target) === String(focusId)
        )
      : allEdges
    const edges = focusedEdges
      .map((edge: any) => {
        const sourceId = endpoint(edge.source)
        const targetId = endpoint(edge.target)
        if (sourceId === targetId) return null
        const source = positions.get(sourceId)
        const target = positions.get(targetId)
        if (!source || !target) return null
        // 题库节点很多，进页面先看知识结构；学习路线模式下仍保留题库关系。
        const touchesBank = [source, target].some((node: any) =>
          normalizeEntityKind(node.kind || node.pageType) === 'bank'
        )
        if (!focusId && !routeActive.value && touchesBank) return null
        return buildMapEdge(source, target, sourceId, targetId, edge, isCrossSourceEdge)
      })
      .filter(Boolean) as any[]
    const unique = new Map<string, any>()
    for (const edge of edges) {
      if (!unique.has(edge.key)) unique.set(edge.key, edge)
    }
    const visible = [...unique.values()]
    if (focusId) {
      return visible.filter((edge: any) => edge.source === focusId || edge.target === focusId)
    }
    return visible
  })

  return { mapEdges }
}
