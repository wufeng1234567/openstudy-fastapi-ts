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

  // hover 进入必须跟手：下一帧直接提交，不再等“意图窗口”。
  // 离开保留约 70ms 缓冲，解决鼠标擦过节点外圈时 enter/leave 抖动；
  // activePointerNodeId 用于识别 enter(B) 先于 leave(A) 的事件顺序，避免误清 B。
  let hoverFrame = 0
  let leaveTimer: ReturnType<typeof setTimeout> | null = null
  let activePointerNodeId: string | null = null

  function commitHover(id: string | null) {
    if (mapHoveredId.value === (id ?? null)) return
    mapHoveredId.value = id ?? null
    if (id && typeof window !== 'undefined') {
      window.dispatchEvent(
        new CustomEvent('openstudy:performance', {
          detail: { action: 'graph-hover', nodeId: id }
        })
      )
    }
  }

  function scheduleHover(id: string | null) {
    if (leaveTimer) {
      clearTimeout(leaveTimer)
      leaveTimer = null
    }
    if (id) {
      activePointerNodeId = id
      if (hoverFrame) cancelAnimationFrame(hoverFrame)
      hoverFrame = requestAnimationFrame(() => {
        hoverFrame = 0
        commitHover(id)
      })
      return
    }
    activePointerNodeId = null
    leaveTimer = setTimeout(() => {
      leaveTimer = null
      if (activePointerNodeId === null) commitHover(null)
    }, 70)
  }

  function onMapNodeEnter(node: any) {
    // 拖拽期间冻结悬停态：指针扫过其他节点时不能反复切换高亮/灰化。
    if (mapDraggingId.value || detailVisible.value) return
    activePointerNodeId = String(node.id)
    scheduleHover(String(node.id))
  }

  function onMapNodeLeave(node: any) {
    if (mapDraggingId.value || detailVisible.value) return
    // 已经进入新节点时，旧节点的 leave 不能清掉新节点。
    if (activePointerNodeId !== String(node.id)) return
    scheduleHover(null)
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
