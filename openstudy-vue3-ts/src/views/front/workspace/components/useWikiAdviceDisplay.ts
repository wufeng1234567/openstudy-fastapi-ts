import { computed } from 'vue'

/**
 * 学习建议射线动画所需的纯展示 computed（从 KnowledgeWikiPanel.vue 抽出）。
 *
 * `adviceNodeTitles` / `adviceTraceLines` 原本声明在 `mapNodes` 之前，却惰性读取
 * `mapNodes.value`。为保持声明位置不变、不引入「后置 const」的 TDZ 依赖，
 * 这里以 `getMapNodes()` 惰性取值：只在 computed getter 求值时才访问，
 * 与原来的 `mapNodes.value` 完全等价。
 */
export function useWikiAdviceDisplay(options: {
  adviceTrace: any
  getMapNodes: () => any[]
}) {
  const { adviceTrace, getMapNodes } = options

  const adviceNodeTitles = computed(() => {
    const result: Record<string, string> = {}
    for (const node of getMapNodes() || []) {
      result[String(node.id)] = String(node.title || '')
      if (Number(node.pageId)) result[String(node.pageId)] = String(node.title || '')
    }
    return result
  })

  const adviceTraceLines = computed(() => {
    const steps = adviceTrace.value?.steps || []
    const position = new Map(getMapNodes().map((node: any) => [String(node.id), node]))
    return steps
      .map((step: any, index: number) => {
        const rawFromId = String(step.from || '')
        const rawToId = String(step.to || '')
        const from = position.get(rawFromId) || position.get(`topic:${rawFromId}`)
        const to = position.get(rawToId) || position.get(`topic:${rawToId}`)
        if (!from || !to) return null
        return {
          key: `${rawFromId}-${rawToId}-${index}`,
          fromId: String(from.id),
          toId: String(to.id),
          fromPageId: String(from.pageId || from.id),
          toPageId: String(to.pageId || to.id),
          x1: from.x,
          y1: from.y,
          x2: to.x,
          y2: to.y
        }
      })
      .filter(Boolean) as any[]
  })

  return { adviceNodeTitles, adviceTraceLines }
}
