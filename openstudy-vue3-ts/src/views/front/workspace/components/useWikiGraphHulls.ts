import { computed } from 'vue'
import { clusterOutline } from '../utils/knowledgeGraphGeometry'

/**
 * 知识图谱分组外轮廓（SVG path）的纯格式化。
 *
 * 从 KnowledgeWikiPanel.vue 抽出：按分组取可见节点坐标，算包围盒与标签位置，
 * 再交给 clusterOutline 生成轮廓路径。只读传入的 ref，不含任何交互或计时逻辑。
 */
export function useWikiGraphHulls(options: {
  mapNodes: any
  mapComponents: any
  mapLayoutScale: any
}) {
  const { mapNodes, mapComponents, mapLayoutScale } = options

  const mapHulls = computed(() => {
    const nodes = mapNodes.value
    if (!nodes.length) return []
    const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
    const visibleIds = new Set(byId.keys())
    const hulls: any[] = []
    for (const component of mapComponents.value.components) {
      const ids = component.ids.filter((id: string) => visibleIds.has(id))
      if (!ids.length) continue
      const points = ids.map((id: string) => byId.get(id)).filter(Boolean)
      if (!points.length) continue
      const minX = Math.min(...points.map((point: any) => Number(point.x || 0)))
      const minY = Math.min(...points.map((point: any) => Number(point.y || 0)))
      hulls.push({
        key: component.key,
        ids,
        label: component.label,
        labelX: minX - 6,
        labelY: minY - 24,
        path: clusterOutline(points, 18 * Math.min(1.35, mapLayoutScale.value))
      })
    }
    return hulls
  })

  return { mapHulls }
}
