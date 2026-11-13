import { computed } from 'vue'
import { normalizeEntityKind } from '../utils/knowledgeGraphMeta'
import { buildMapEdge } from './wikiMapGeometry'

/**
 * 知识图谱的边（连线）纯展示 computed。
 *
 * 从 KnowledgeWikiPanel.vue 抽出：首屏不画线、图片节点折叠、按焦点/学习路线
 * 过滤、按 key 去重。全部是惰性 computed，只读传入的 ref，不含任何
 * API、事件监听、拖拽/缩放或计时逻辑。返回的名字以原名解构回 SFC。
 */
export function useWikiMapEdges(options: {
  mapHoveredId: any
  mapSelectedNodeId: any
  mapNodes: any
  allMapNodes: any
  mapImageExpanded: any
  mapGraph: any
  IMAGE_CLUSTER_ID: string
  isCrossSourceEdge: (edge: any) => boolean
}) {
  const {
    mapHoveredId, mapSelectedNodeId, mapNodes, allMapNodes,
    mapImageExpanded, mapGraph, IMAGE_CLUSTER_ID, isCrossSourceEdge
  } = options

  const mapEdges = computed(() => {
    // 连线默认常显：节点之间的关系本身就是知识图谱的核心信息。
    // 悬停/选中节点时仍会过滤到相关连线并高亮，避免焦点视图被其它边干扰。
    const focusId = mapHoveredId.value || mapSelectedNodeId.value
    const positions = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
    const imageIds = new Set(
      allMapNodes.value
        .filter((node: any) => normalizeEntityKind(node.kind) === 'image')
        .map((node: any) => String(node.id))
    )
    const collapseImages = !mapImageExpanded.value && imageIds.size > 8
    const endpoint = (id: any) => collapseImages && imageIds.has(String(id)) ? IMAGE_CLUSTER_ID : String(id)
    const edges = (mapGraph.value?.edges || [])
      .map((edge: any) => {
        const sourceId = endpoint(edge.source)
        const targetId = endpoint(edge.target)
        if (sourceId === targetId) return null
        const source = positions.get(sourceId)
        const target = positions.get(targetId)
        if (!source || !target) return null
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
