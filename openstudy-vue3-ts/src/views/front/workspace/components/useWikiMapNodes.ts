import { computed } from 'vue'
import { normalizeEntityKind, normalizePageType, entityTypeMeta } from '../utils/knowledgeGraphMeta'

/**
 * 知识图谱节点布局：把实体分组、过滤、排布成可渲染的节点数组。
 *
 * 从 KnowledgeWikiPanel.vue 抽出的纯 computed，逐字搬迁原逻辑（含全部注释）。
 * 只读以 options 传入的 ref / reactive / 常量，不含 API、事件监听、计时器或 DOM 操作；
 * 计算顺序、迭代次数、坐标夹取等逐字照搬，拖拽/缩放/力导向手感不变。
 */
export function useWikiMapNodes(options: {
  mapComponents: any
  graphSourceTypeFilter: any
  graphPageTypeFilter: any
  graphLearningFilter: any
  allMapNodes: any
  routeActive: any
  mapHideUnlinked: any
  mapConnectedNodeIds: any
  mapLayoutScale: any
  mapImageExpanded: any
  mapTypeVisible: any
  mapSize: any
  mapNodeOffsets: any
  mapSimPositions: any
  IMAGE_CLUSTER_ID: string
}) {
  const {
    mapComponents, graphSourceTypeFilter, graphPageTypeFilter, graphLearningFilter,
    allMapNodes, routeActive, mapHideUnlinked, mapConnectedNodeIds,
    mapLayoutScale, mapImageExpanded, mapTypeVisible, mapSize,
    mapNodeOffsets, mapSimPositions, IMAGE_CLUSTER_ID
  } = options

  const mapNodes = computed(() => {
    const { components, byId } = mapComponents.value
    const sourceTypes = graphSourceTypeFilter.value
    const pageTypes = graphPageTypeFilter.value
    const learningLevels = graphLearningFilter.value
    const visibleIds = new Set(
      allMapNodes.value
        .filter((node: any) => routeActive.value || mapTypeVisible[normalizeEntityKind(node.kind || node.pageType)] !== false)
        .filter((node: any) => !sourceTypes.length || sourceTypes.includes(normalizeEntityKind(node.kind || node.pageType)))
        .filter((node: any) => {
          if (!pageTypes.length || normalizeEntityKind(node.kind) !== 'topic') return true
          return pageTypes.includes(normalizePageType(node.pageType))
        })
        .filter((node: any) => {
          if (!learningLevels.length || normalizeEntityKind(node.kind) !== 'topic') return true
          return learningLevels.includes(String(node.detail?.learning?.level || node.learning?.level || 'unread'))
        })
        .filter((node: any) => routeActive.value || !mapHideUnlinked.value || mapConnectedNodeIds.value.has(String(node.id)))
        .map((node: any) => String(node.id))
    )
    const visibleComponents = components
      .map((component) => ({ ...component, ids: component.ids.filter((id: string) => visibleIds.has(id)) }))
      .filter((component) => component.ids.length)
    const width = Number(mapSize.width || 1200)
    const height = Number(mapSize.height || 760)
    const layoutScale = Number(mapLayoutScale.value || 1)
    // 右侧实体集面板按分辨率占 220–320px；节点布局只使用左侧可用区域，避免来源组被面板盖住。
    const panelReserve = Math.min(320, Math.max(220, width * 0.12))
    const usableWidth = Math.max(640, width - panelReserve)
    const topicSpacingX = Math.round(60 * layoutScale)
    const topicSpacingY = Math.round(58 * layoutScale)
    const kindCenters: Record<string, { x: number; y: number }> = {
      topic: { x: usableWidth * 0.52, y: height * 0.5 },
      document: { x: usableWidth * 0.10, y: height * 0.64 },
      bank: { x: usableWidth * 0.90, y: height * 0.64 },
      web: { x: usableWidth * 0.10, y: height * 0.15 },
      note: { x: usableWidth * 0.52, y: height * 0.94 },
      image: { x: usableWidth * 0.90, y: height * 0.15 }
    }
    const nodePadding = 28 * Math.min(1.35, layoutScale)
    // 组间留白是硬间隔，不用“看起来差不多”；窗口小也至少保留 48px。
    const groupGap = Math.max(96, 120 * layoutScale)
    const groupLayouts = visibleComponents.map((component, componentIndex) => {
      const collapseImages = component.kind === 'image' && !mapImageExpanded.value && component.ids.length > 8
      const members = collapseImages
        ? [{
            id: IMAGE_CLUSTER_ID,
            kind: 'image',
            title: `图片资产（${component.ids.length}）`,
            subtitle: '点击展开图片节点',
            pageId: 0,
            pageType: 'image',
            degree: component.ids.length,
            sourceType: 'image',
            sourceId: 0,
            color: entityTypeMeta('image').color
          }]
        : component.ids.map((id: string) => byId.get(id)).filter(Boolean) as any[]
      const hub = [...members].sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))[0]
      const fallbackCenter = {
        x: 80 + ((componentIndex % 3) + 0.5) * Math.max(1, (usableWidth - 160) / 3),
        y: 80 + (Math.floor(componentIndex / 3) + 0.5) * Math.max(1, (height - 160) / Math.max(1, Math.ceil(visibleComponents.length / 3)))
      }
      const center = { ...(kindCenters[component.kind] || fallbackCenter) }
      const topicCols = component.kind === 'topic'
        ? Math.max(4, Math.ceil(Math.sqrt(members.length * 0.75)))
        : 0
      const topicRows = topicCols ? Math.ceil(members.length / topicCols) : 0
      const sourceCols = component.kind !== 'topic' && members.length > 6
        ? Math.ceil(Math.sqrt(members.length))
        : 0
      const sourceRows = sourceCols ? Math.ceil(members.length / sourceCols) : 0
      const orbitRadius = (component.kind === 'topic'
        ? Math.min(260, 72 + Math.sqrt(members.length) * 24)
        : Math.min(170, 62 + Math.sqrt(members.length) * 22)) * Math.min(1.45, layoutScale)
      const maxNodeRadius = component.kind === 'topic' ? 14 : 16
      let halfWidth = maxNodeRadius + nodePadding
      let halfHeight = maxNodeRadius + nodePadding
      if (component.kind === 'topic' && topicCols) {
        halfWidth = ((topicCols - 1) / 2) * topicSpacingX + maxNodeRadius + nodePadding
        halfHeight = ((topicRows - 1) / 2) * topicSpacingY + maxNodeRadius + nodePadding
      } else if (sourceCols) {
        const sourceSpacing = 40 * layoutScale
        halfWidth = ((sourceCols - 1) / 2) * sourceSpacing + maxNodeRadius + nodePadding
        halfHeight = ((sourceRows - 1) / 2) * sourceSpacing + maxNodeRadius + nodePadding
      } else if (members.length > 1) {
        halfWidth = orbitRadius + maxNodeRadius + nodePadding
        halfHeight = halfWidth
      }
      return {
        component,
        members,
        hub,
        center,
        topicCols,
        topicRows,
        sourceCols,
        sourceRows,
        orbitRadius,
        radius: Math.max(halfWidth, halfHeight)
      }
    })
    // 如果当前窗口宽度不足以容纳最大的两组，就扩展虚拟画布；再由 fitMapView 统一缩放。
    // 这样宁可整体缩小一点，也不会把组强行压到互相重叠。
    let maxPairRadius = 0
    for (let i = 0; i < groupLayouts.length; i += 1) {
      for (let j = i + 1; j < groupLayouts.length; j += 1) {
        maxPairRadius = Math.max(maxPairRadius, groupLayouts[i]!.radius + groupLayouts[j]!.radius)
      }
    }
    const layoutWidth = Math.max(
      usableWidth,
      Math.ceil(maxPairRadius * 2 + groupGap + 36)
    )
    if (layoutWidth > usableWidth) {
      const ratio = layoutWidth / usableWidth
      groupLayouts.forEach((layout) => {
        layout.center.x = Math.round(layout.center.x * ratio)
      })
    }
    // 组间分离：把每个实体集当成有半径的圆，用简单迭代把重叠的组推开。
    // 这是实际几何计算，不再依赖某一组固定坐标，窗口变大/变小时组与组之间始终保留 gap。
    for (let pass = 0; pass < 90; pass += 1) {
      for (let i = 0; i < groupLayouts.length; i += 1) {
        const a = groupLayouts[i]!
        for (let j = i + 1; j < groupLayouts.length; j += 1) {
          const b = groupLayouts[j]!
          let dx = b.center.x - a.center.x
          let dy = b.center.y - a.center.y
          let distance = Math.hypot(dx, dy)
          const minimum = a.radius + b.radius + groupGap
          if (distance >= minimum) continue
          if (distance < 0.01) {
            dx = 1
            dy = 0
            distance = 1
          }
          const push = (minimum - distance) / 2
          const ux = dx / distance
          const uy = dy / distance
          a.center.x -= ux * push
          a.center.y -= uy * push
          b.center.x += ux * push
          b.center.y += uy * push
        }
      }
      for (const layout of groupLayouts) {
        layout.center.x = Math.min(
          Math.max(layout.radius + 18, layoutWidth - layout.radius - 18),
          Math.max(layout.radius + 18, layout.center.x)
        )
        layout.center.y = Math.min(
          Math.max(layout.radius + 18, height - layout.radius - 18),
          Math.max(layout.radius + 18, layout.center.y)
        )
      }
    }
    const result: any[] = []
    groupLayouts.forEach((layout) => {
      const { component, members, hub, center, topicCols, topicRows, sourceCols, sourceRows, orbitRadius } = layout
      const orbit = members.filter((node) => node !== hub)
      const hubOnCenter = members.length > 1
      let orbitIndex = 0
      for (let memberIndex = 0; memberIndex < members.length; memberIndex += 1) {
        const node = members[memberIndex]
        const degree = Number(node.degree || 0)
        let x = center.x
        let y = center.y
        if (component.kind === 'topic' && topicCols) {
          const col = memberIndex % topicCols
          const row = Math.floor(memberIndex / topicCols)
          x = center.x + (col - (topicCols - 1) / 2) * topicSpacingX
          y = center.y + (row - (topicRows - 1) / 2) * topicSpacingY
        } else if (sourceCols) {
          const col = memberIndex % sourceCols
          const row = Math.floor(memberIndex / sourceCols)
          const sourceSpacing = 40 * layoutScale
          x = center.x + (col - (sourceCols - 1) / 2) * sourceSpacing
          y = center.y + (row - (sourceRows - 1) / 2) * sourceSpacing
        } else if (members.length > 1 && !(hubOnCenter && node === hub)) {
          const count = orbit.length
          const angle = -Math.PI / 2 + (Math.PI * 2 * orbitIndex) / Math.max(1, count)
          const jitter = Math.sin((Number(node.id) || orbitIndex + 1) * 12.9898) * 0.16
          x = center.x + Math.cos(angle + jitter) * orbitRadius
          y = center.y + Math.sin(angle + jitter) * orbitRadius
          orbitIndex += 1
        }
        const offset = mapNodeOffsets[String(node.id)]
        // 多实体集使用稳定的分区布局，禁止复用单组阶段产生的旧力导向坐标。
        // 否则首次渲染和二次刷新时序不同，会把几组节点一起吸到旧坐标里。
        const simulated = mapComponents.value.components.length < 2
          ? mapSimPositions[String(node.id)]
          : undefined
        const kind = normalizeEntityKind(node.kind || node.pageType)
        const offsetX = Number(offset?.x)
        const offsetY = Number(offset?.y)
        const simulatedX = Number(simulated?.x)
        const simulatedY = Number(simulated?.y)
        const resolvedX = Number.isFinite(offsetX) ? offsetX : Number.isFinite(simulatedX) ? simulatedX : x
        const resolvedY = Number.isFinite(offsetY) ? offsetY : Number.isFinite(simulatedY) ? simulatedY : y
        result.push({
          ...node,
          kind,
          pageType: normalizePageType(node.pageType),
          x: resolvedX,
          y: resolvedY,
          r: Math.max(kind === 'topic' ? 5 : 9, Math.min(kind === 'topic' ? 14 : 16, 4 + Math.sqrt(Math.max(0, degree)) * 1.35)) * Math.min(1.35, layoutScale),
          color: entityTypeMeta(kind).color
        })
      }
    })
    return result
  })

  return { mapNodes }
}
