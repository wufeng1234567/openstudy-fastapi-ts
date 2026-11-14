import { computed } from 'vue'
import { normalizeEntityKind, entityTypeMeta } from '../utils/knowledgeGraphMeta'

/**
 * 知识图谱节点/边的展示判定与标签格式化。
 *
 * 从 KnowledgeWikiPanel.vue 抽出的纯展示逻辑：选中/灰化/高亮判定、路线判定、
 * 邻居集合、显示标签、图片 URL 拼装。所有依赖均以 ref/computed 形式从 options 传入，
 * 返回的函数保持原签名与名称，模板调用点无需改动。
 */
export function useWikiMapDisplay(options: {
  mapHoveredId: any
  mapSelectedNodeId: any
  mapSelectedPageId: any
  mapEdges: any
  mapDraggingId: any
  detailVisible: any
  routeActive: any
  learningRoute: any
  activeRouteStop: any
  visibleLabelIds: any
  mapComponents: any
  IMAGE_CLUSTER_ID: string
}) {
  const {
    mapHoveredId, mapSelectedNodeId, mapSelectedPageId, mapEdges,
    mapDraggingId, detailVisible, routeActive, learningRoute,
    activeRouteStop, visibleLabelIds, mapComponents, IMAGE_CLUSTER_ID
  } = options

  function entitySetLabel(node: any) {
    const type = normalizeEntityKind(node?.kind || node?.sourceType)
    const typeLabel = entityTypeMeta(type).label
    const name = String(node?.title || node?.sourceName || '').trim()
    return name ? `${typeLabel}：${name}` : typeLabel
  }

  function neighborIdsFor(id: string | null) {
    const result = new Set<string>()
    if (!id) return result
    result.add(id)
    for (const edge of mapEdges.value) {
      if (edge.source === id) result.add(edge.target)
      if (edge.target === id) result.add(edge.source)
    }
    return result
  }

  const mapFocusId = computed(() => mapHoveredId.value || mapSelectedNodeId.value)
  const mapNeighborIds = computed(() => neighborIdsFor(mapFocusId.value))

  // hover 是高频事件：合并到一帧内只提交一次，避免迅速划过多个节点时
  // 每个 mouseenter 都重算全图边、标签和灰化状态。
  let hoverFrame = 0
  let pendingHoverId: string | null | undefined

  function scheduleHover(id: string | null) {
    pendingHoverId = id
    if (hoverFrame) return
    hoverFrame = requestAnimationFrame(() => {
      hoverFrame = 0
      mapHoveredId.value = pendingHoverId ?? null
      if (pendingHoverId && typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('openstudy:performance', {
            detail: { action: 'graph-hover', nodeId: pendingHoverId }
          })
        )
      }
    })
  }

  function onMapNodeEnter(node: any) {
    // 拖拽期间冻结悬停态：指针扫过其他节点时不能反复切换高亮/灰化。
    if (mapDraggingId.value || detailVisible.value) return
    scheduleHover(String(node.id))
  }

  function onMapNodeLeave(node: any) {
    if (mapDraggingId.value || detailVisible.value) return
    if (mapHoveredId.value === String(node.id) || pendingHoverId === String(node.id)) scheduleHover(null)
  }

  function isMapSelected(node: any) {
    if (mapSelectedNodeId.value) return String(node.id) === mapSelectedNodeId.value
    if (mapSelectedPageId.value == null) return false
    return Number(node.pageId) === Number(mapSelectedPageId.value)
  }

  function isMapNodeDimmed(node: any) {
    if (routeActive.value && !isRouteNode(node)) return true
    // 悬停灰化由 `.kw-map.is-hovering` 的 CSS 统一处理：
    // 不再给 300+ 节点逐个切换 is-dimmed，避免 hover 时整图 patch 掉帧。
    return false
  }

  function isMapEdgeActive(edge: any) {
    // 基础边只跟随“选中”状态；hover 的边由独立高亮层渲染，
    // 避免每次 hover 都让全部 SVG 边重新计算 class。
    return !!mapSelectedNodeId.value &&
      (edge.source === mapSelectedNodeId.value || edge.target === mapSelectedNodeId.value)
  }

  function isMapEdgeDimmed(edge: any) {
    if (routeActive.value) {
      const routeIds = new Set((learningRoute.value?.stops || []).map((stop: any) => String(stop.pageId)))
      return !(routeIds.has(edge.source) && routeIds.has(edge.target))
    }
    // 悬停时的非关联边由 `.kw-map.is-hovering` 统一淡化。
    return false
  }

  function isRouteNode(node: any) {
    return (learningRoute.value?.stops || []).some(
      (stop: any) => Number(stop.pageId) === Number(node?.pageId)
    )
  }

  function isRouteEdge(edge: any) {
    const routeIds = new Set((learningRoute.value?.stops || []).map((stop: any) => String(stop.pageId)))
    return routeIds.has(edge.source) && routeIds.has(edge.target)
  }

  function isNextStopNode(node: any) {
    return activeRouteStop.value
      ? Number(activeRouteStop.value.pageId) === Number(node?.pageId)
      : false
  }

  function showMapLabel(node: any) {
    if (node.id === IMAGE_CLUSTER_ID) return true
    if (mapHoveredId.value === String(node.id)) return true
    if (!visibleLabelIds.value.has(String(node.id))) return false
    if (normalizeEntityKind(node.kind) === 'topic') return true
    const component = mapComponents.value.components.find((item: any) => item.ids.includes(String(node.id)))
    if (component?.kind === 'image' && component.ids.length > 8) {
      return isMapSelected(node) || mapHoveredId.value === String(node.id)
    }
    return true
  }

  function mapNodeLabel(node: any) {
    const title = String(node?.title || '')
    const limit = normalizeEntityKind(node?.kind) === 'topic' ? 12 : 14
    return title.length > limit ? `${title.slice(0, limit)}…` : title
  }

  function imageUrl(url: string) {
    const value = String(url || '').trim()
    if (!value) return ''
    if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
    const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
    return base + (value.startsWith('/') ? value : '/' + value)
  }

  return {
    entitySetLabel,
    neighborIdsFor,
    mapFocusId,
    mapNeighborIds,
    onMapNodeEnter,
    onMapNodeLeave,
    isMapSelected,
    isMapNodeDimmed,
    isMapEdgeActive,
    isMapEdgeDimmed,
    isRouteNode,
    isRouteEdge,
    isNextStopNode,
    showMapLabel,
    mapNodeLabel,
    imageUrl
  }
}
