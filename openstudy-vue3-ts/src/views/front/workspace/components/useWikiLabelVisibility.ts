import { computed } from 'vue'
import { normalizeEntityKind } from '../utils/knowledgeGraphMeta'
import { pickNonOverlappingLabelIds } from './wikiMapGeometry'

/**
 * 图谱标签可见性（候选筛选 + 避让）的纯展示 computed。
 *
 * 从 KnowledgeWikiPanel.vue 抽出。`visibleLabelIds` 原本声明在
 * `useWikiMapDisplay` 之前，却惰性使用后者返回的 `isMapSelected` /
 * `isRouteNode` / `mapNodeLabel`；同时 `useWikiMapDisplay` 又以
 * `visibleLabelIds` 为入参，构成双向顺序约束。为不改变任何声明位置，
 * 这里以 `getDisplay()` 惰性取这三个函数：只在 computed getter 求值时调用，
 * 与原行为等价。
 */
export function useWikiLabelVisibility(options: {
  mapNodes: any
  mapHoveredId: any
  adviceLitPageIds: any
  mapComponents: any
  mapView: any
  IMAGE_CLUSTER_ID: string
  getDisplay: () => {
    isMapSelected: (node: any) => boolean
    isRouteNode: (node: any) => boolean
    mapNodeLabel: (node: any) => string
  }
}) {
  const {
    mapNodes, mapHoveredId, adviceLitPageIds, mapComponents,
    mapView, IMAGE_CLUSTER_ID, getDisplay
  } = options

  const visibleLabelIds = computed(() => {
    const { isMapSelected, isRouteNode, mapNodeLabel } = getDisplay()
    const total = mapNodes.value.length
    // 大图默认只展示更高连接度的主题标签；选中/悬停/路线节点仍然优先保留。
    const degreeThreshold = total > 120 ? 18 : 12
    const maxLabels = total > 150 ? 36 : total > 80 ? 48 : 72
    const candidates = [...mapNodes.value]
      .filter((node: any) => {
        const kind = normalizeEntityKind(node.kind)
        if (node.id === IMAGE_CLUSTER_ID) return true
        if (isMapSelected(node) || isRouteNode(node) || mapHoveredId.value === String(node.id)) return true
        if (adviceLitPageIds.value.includes(String(node.pageId))) return true
        if (kind !== 'topic') {
          const component = mapComponents.value.components.find((item) => item.ids.includes(String(node.id)))
          return !(component?.kind === 'image' && component.ids.length > 8)
        }
        return mapView.scale >= 1.25 || Number(node.degree || 0) >= degreeThreshold
      })
      .sort((a: any, b: any) => {
        const priority = (node: any) => {
          if (isMapSelected(node) || mapHoveredId.value === String(node.id)) return 0
          if (normalizeEntityKind(node.kind) !== 'topic') return 1
          return 2
        }
        return priority(a) - priority(b) || Number(b.degree || 0) - Number(a.degree || 0)
      })
    return pickNonOverlappingLabelIds(
      candidates,
      mapNodeLabel,
      Number(mapView.scale),
      Number(mapView.x),
      Number(mapView.y),
      maxLabels
    )
  })

  return { visibleLabelIds }
}
