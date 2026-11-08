<template>
  <section class="sgc" :class="{ 'is-fullscreen': fullscreen, 'is-compact': compact }">
    <div class="sgc__top">
      <div class="sgc__status" :class="`is-${phase || 'idle'}`">
        <i></i>
        <span>{{ statusText }}</span>
      </div>
      <div class="sgc__actions">
        <button type="button" class="sgc__icon-btn" :title="fullscreen ? '退出全屏' : '全屏查看'" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>
        </button>
        <button type="button" class="sgc__icon-btn" title="重置视图" @click="resetView">
          <el-icon><Refresh /></el-icon>
        </button>
      </div>
    </div>
    <div ref="chartRef" class="sgc__chart"></div>
    <div v-if="!nodes.length" class="sgc__empty">
      <b>还没有可画的图谱</b>
      <span>先导入资料、生成知识百科，或在题库里做几道题。</span>
    </div>
    <footer class="sgc__legend">
      <span><i class="is-topic"></i>知识主题</span>
      <span><i class="is-bank"></i>题库</span>
      <span><i class="is-doc"></i>资料/网页</span>
      <span><i class="is-note"></i>笔记</span>
      <span><i class="is-image"></i>图片</span>
      <em>实线=真实图谱关系 · 虚线=真实题源锚点</em>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { FullScreen, Refresh } from '@element-plus/icons-vue'

interface GraphNode {
  id: string
  kind: string
  title?: string
  metrics?: Record<string, any>
  ref?: Record<string, any>
  detail?: Record<string, any>
  [key: string]: any
}

interface GraphEdge {
  id?: string
  source: string
  target: string
  kind?: string
  label?: string
  weight?: number
  [key: string]: any
}

const props = withDefaults(
  defineProps<{
    nodes?: GraphNode[]
    edges?: GraphEdge[]
    groups?: any[]
    trace?: any
    activeStep?: number
    phase?: string
    selectedId?: string
    visitedIds?: string[]
    compact?: boolean
  }>(),
  {
    nodes: () => [],
    edges: () => [],
    groups: () => [],
    trace: null,
    activeStep: -1,
    phase: 'idle',
    selectedId: '',
    visitedIds: () => [],
    compact: false
  }
)

const emit = defineEmits<{
  (e: 'select', node: GraphNode): void
  (e: 'fullscreen', value: boolean): void
}>()

const chartRef = ref<HTMLElement | null>(null)
const fullscreen = ref(false)
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const statusText = computed(() => {
  const phase = String(props.phase || 'idle')
  if (phase === 'reading') return '正在读取知识图谱…'
  if (phase === 'traversing') return '正在沿真实图谱关系读取…'
  if (phase === 'thinking') return 'LLM 正在思考…'
  if (phase === 'ready') return '建议已生成'
  return '点一个节点，或直接生成建议'
})

const activeEdge = computed(() => {
  const steps = props.trace?.steps || []
  return steps[Number(props.activeStep)] || null
})

const trailSteps = computed(() => {
  const steps = props.trace?.steps || []
  const count = props.phase === 'ready' ? steps.length : Math.max(0, Number(props.activeStep) + 1)
  return steps.slice(0, count)
})

const visitedSet = computed(() => {
  const set = new Set<string>((props.visitedIds || []).map(String))
  if (props.selectedId) set.add(String(props.selectedId))
  return set
})

const nodeColor = (node: GraphNode) => {
  if (node.kind === 'topic') {
    const learning = node.detail?.learning || {}
    const level = String(learning.level || '')
    if (level === 'mastered') return '#2f9e8f'
    if (level === 'practicing') return '#e6a23c'
    if (level === 'reading') return '#5b8def'
    return '#9aa7ba'
  }
  if (node.kind === 'bank') return '#7c6cf2'
  if (node.kind === 'question') return '#9aa7ba'
  if (node.kind === 'note') return '#2f9e8f'
  if (node.kind === 'image') return '#c47a55'
  if (node.kind === 'web') return '#5c8fa8'
  return '#8b6bb1'
}

function nodeSize(node: GraphNode) {
  const degree = Number(node.metrics?.degree || 0)
  if (node.kind === 'topic') return 15 + Math.min(9, Math.sqrt(degree + 1) * 2.4)
  if (node.kind === 'bank') return 18
  if (node.kind === 'question') return 9
  return 13
}

function layoutNodes(nodes: GraphNode[]) {
  const width = Math.max(580, chartRef.value?.clientWidth || 900)
  const height = Math.max(360, chartRef.value?.clientHeight || 470)
  const groupDefs = (props.groups || []).filter((group: any) => (group.nodeIds || []).length)
  const positions = new Map<string, { x: number; y: number }>()
  const boxes: any[] = []

  if (groupDefs.length) {
    const gap = 10
    const header = 26
    const placeGroup = (group: any, box: any) => {
      boxes.push({ ...box, group })
      const items = nodes.filter((node) => (group.nodeIds || []).map(String).includes(String(node.id)))
      const innerCols = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(items.length))))
      const innerRows = Math.max(1, Math.ceil(items.length / innerCols))
      const innerW = Math.max(40, box.w - 18)
      const innerH = Math.max(40, box.h - header - 12)
      items.forEach((node, index) => {
        const innerCol = index % innerCols
        const innerRow = Math.floor(index / innerCols)
        positions.set(String(node.id), {
          x: box.x + 9 + (innerCol + 0.5) * (innerW / innerCols),
          y: box.y + header + (innerRow + 0.5) * (innerH / innerRows)
        })
      })
    }
    const topicGroup = groupDefs.find((group: any) => group.kind === 'topic')
    const sideGroups = groupDefs.filter((group: any) => group.kind !== 'topic')
    if (topicGroup) {
      const wikiBox = { x: gap, y: gap, w: width * 0.48, h: height - gap * 2 }
      placeGroup(topicGroup, wikiBox)
      const sideX = width * 0.52
      const sideW = width - sideX - gap
      const sideCols = sideGroups.length <= 1 ? 1 : 2
      const sideRows = Math.max(1, Math.ceil(sideGroups.length / sideCols))
      const sideCellW = (sideW - gap * (sideCols - 1)) / sideCols
      const sideCellH = (height - gap * (sideRows + 1)) / sideRows
      sideGroups.forEach((group: any, index: number) => {
        placeGroup(group, {
          x: sideX + (index % sideCols) * (sideCellW + gap),
          y: gap + Math.floor(index / sideCols) * (sideCellH + gap),
          w: sideCellW,
          h: sideCellH
        })
      })
    } else {
      const cols = groupDefs.length <= 2 ? 1 : 2
      const rows = Math.ceil(groupDefs.length / cols)
      const cellW = (width - gap * (cols + 1)) / cols
      const cellH = (height - gap * (rows + 1)) / rows
      groupDefs.forEach((group: any, groupIndex: number) => {
        placeGroup(group, {
          x: gap + (groupIndex % cols) * (cellW + gap),
          y: gap + Math.floor(groupIndex / cols) * (cellH + gap),
          w: cellW,
          h: cellH
        })
      })
    }
    return {
      list: nodes.map((node) => ({
        ...node,
        x: positions.get(String(node.id))?.x ?? width / 2,
        y: positions.get(String(node.id))?.y ?? height / 2
      })),
      boxes
    }
  }

  const cx = width / 2
  const cy = height / 2
  const topics = nodes.filter((n) => n.kind === 'topic')
  const banks = nodes.filter((n) => n.kind === 'bank')
  const sources = nodes.filter((n) => !['topic', 'bank'].includes(n.kind))
  const neighborIds = new Set<string>()
  if (props.selectedId) {
    for (const edge of props.edges || []) {
      if (String(edge.source) === String(props.selectedId)) neighborIds.add(String(edge.target))
      if (String(edge.target) === String(props.selectedId)) neighborIds.add(String(edge.source))
    }
  }
  const selected = props.selectedId ? nodes.find((n) => String(n.id) === String(props.selectedId)) : null
  if (selected) positions.set(String(selected.id), { x: cx, y: cy })
  const placeRing = (items: GraphNode[], radius: number, startAngle = -Math.PI / 2) => {
    items.forEach((node, index) => {
      if (positions.has(String(node.id))) return
      const angle = startAngle + (Math.PI * 2 * index) / Math.max(items.length, 1)
      positions.set(String(node.id), {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius * 0.78
      })
    })
  }
  if (selected) {
    const near = nodes.filter((n) => neighborIds.has(String(n.id)) && String(n.id) !== String(selected.id))
    placeRing(near, 135)
    const restTopics = topics.filter((n) => !positions.has(String(n.id)))
    placeRing(restTopics, 225)
    const restBanks = banks.filter((n) => !positions.has(String(n.id)))
    placeRing(restBanks, 280, Math.PI * 0.18)
    const restSources = sources.filter((n) => !positions.has(String(n.id)))
    placeRing(restSources, 320, Math.PI * 0.05)
  } else {
    placeRing(topics, Math.min(width, height) * 0.29)
    placeRing(banks, Math.min(width, height) * 0.43, Math.PI * 0.18)
    placeRing(sources, Math.min(width, height) * 0.47, Math.PI * 0.02)
  }
  return {
    list: nodes.map((node) => ({
      ...node,
      x: positions.get(String(node.id))?.x ?? cx,
      y: positions.get(String(node.id))?.y ?? cy
    })),
    boxes: []
  }
}

function isDimmed(id: string) {
  if (!visitedSet.value.size) return false
  return !visitedSet.value.has(String(id))
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      const node = params?.data?.rawNode as GraphNode | undefined
      if (node) emit('select', node)
    })
  }
  const width = Math.max(580, chartRef.value.clientWidth || 900)
  const height = Math.max(360, chartRef.value.clientHeight || 470)
  const layout = layoutNodes(props.nodes || [])
  const list = layout.list
  const pos = new Map(list.map((node) => [String(node.id), node]))
  const active = activeEdge.value
  const activeSource = active?.from ? pos.get(String(active.from)) : null
  const activeTarget = active?.to ? pos.get(String(active.to)) : null
  const edgeData = (props.edges || [])
    .map((edge) => {
      const source = pos.get(String(edge.source))
      const target = pos.get(String(edge.target))
      if (!source || !target) return null
      const isActive = active && String(edge.source) === String(active.from) && String(edge.target) === String(active.to)
      const dim = visitedSet.value.size > 0 && !isActive
      return {
        coords: [
          [source.x, source.y],
          [target.x, target.y]
        ],
        lineStyle: {
          color: isActive ? '#2f5fce' : edge.kind === 'question_source' ? '#c7b9ee' : '#cfd9ea',
          width: isActive ? 2.4 : edge.kind === 'question_source' ? 1.5 : 1.1,
          type: edge.kind === 'question_source' ? 'dashed' : 'solid',
          opacity: isActive ? 0.95 : dim ? 0.12 : 0.55,
          curveness: 0.08
        },
        rawEdge: edge
      }
    })
    .filter(Boolean) as any[]

  // 已经走过的射线保留下来：当前步用带粒子的 effect，上一步用普通高亮线。
  const trailData = trailSteps.value
    .map((step: any) => {
      const source = pos.get(String(step.from))
      const target = pos.get(String(step.to))
      if (!source || !target) return null
      return {
        coords: [
          [source.x, source.y],
          [target.x, target.y]
        ]
      }
    })
    .filter(Boolean) as any[]

  const nodeData = list
    .filter((node) => node.kind !== 'bank')
    .map((node) => {
      const dim = isDimmed(node.id) && String(node.id) !== String(active?.to || '')
      const isActive = active && (String(node.id) === String(active.from) || String(node.id) === String(active.to))
      return {
        name: node.title || node.id,
        value: [node.x, node.y],
        symbol: node.kind === 'document' ? 'diamond' : node.kind === 'question' ? 'roundRect' : 'circle',
        symbolSize: nodeSize(node),
        rawNode: node,
        itemStyle: {
          color: node.kind === 'topic' ? '#ffffff' : nodeColor(node),
          borderColor: isActive ? '#2f5fce' : nodeColor(node),
          borderWidth: isActive ? 3 : 1.6,
          opacity: dim ? 0.28 : 1,
          shadowBlur: isActive ? 18 : 0,
          shadowColor: 'rgba(47,95,206,.45)'
        },
        label: {
          show: true,
          formatter: String(node.title || '').slice(0, 8),
          position: 'bottom',
          distance: 3,
          color: dim ? '#b8c0cd' : '#5f6b7d',
          fontSize: 9,
          fontWeight: isActive ? 700 : 500
        }
      }
    })

  const effectData = activeSource && activeTarget ? [[[activeSource.x, activeSource.y], [activeTarget.x, activeTarget.y]]] : []
  const option: any = {
    backgroundColor: 'transparent',
    animationDuration: 420,
    graphic: (layout.boxes || []).map((entry: any) => ({
      type: 'group',
      left: entry.x,
      top: entry.y,
      silent: true,
      children: [
        {
          type: 'rect',
          shape: { width: entry.w, height: entry.h, r: 10 },
          style: { fill: '#f7f8fb', stroke: '#dfe5ee', lineWidth: 1 }
        },
        {
          type: 'text',
          style: {
            text: `${entry.group.title || ''} · ${(entry.group.nodeIds || []).length}`,
            x: 10,
            y: 8,
            fill: '#7d8798',
            fontSize: 10,
            fontWeight: 600
          }
        }
      ]
    })),
    grid: { left: 4, right: 4, top: 4, bottom: 4, containLabel: false },
    xAxis: { type: 'value', min: 0, max: width, show: false },
    yAxis: { type: 'value', min: 0, max: height, inverse: true, show: false },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(23,32,51,.92)',
      borderWidth: 0,
      padding: [8, 10],
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: any) => {
        const node = params?.data?.rawNode as GraphNode
        if (!node) return ''
        return `<b>${node.title || node.id}</b><br/><span style="opacity:.7">${node.kind}</span>`
      }
    },
    series: [
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        silent: true,
        z: 1,
        data: edgeData
      },
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        silent: true,
        z: 2,
        lineStyle: { color: '#2f5fce', width: 2, opacity: 0.55, curveness: 0.08 },
        data: trailData
      },
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        silent: true,
        z: 3,
        effect: {
          show: true,
          period: 0.65,
          trailLength: 0.45,
          symbol: 'circle',
          symbolSize: 5,
          color: '#2f5fce'
        },
        lineStyle: { color: '#2f5fce', width: 2, opacity: 0.6 },
        data: effectData
      },
      {
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        z: 10,
        data: nodeData,
        emphasis: { scale: 1.15 }
      },
      {
        type: 'effectScatter',
        coordinateSystem: 'cartesian2d',
        z: 11,
        rippleEffect: { brushType: 'stroke', scale: 3.2, period: 1.1 },
        symbolSize: activeSource ? nodeSize(activeSource) + 6 : 0,
        itemStyle: { color: '#2f5fce', opacity: 0.7 },
        data: activeSource ? [{ value: [activeSource.x, activeSource.y] }] : []
      }
    ]
  }
  chart.setOption(option, true)
}

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
  emit('fullscreen', fullscreen.value)
  nextTick(() => {
    setTimeout(() => chart?.resize(), 60)
  })
}

function resetView() {
  emit('select', { id: '', kind: '', title: '' } as GraphNode)
  render()
}

function onResize() {
  chart?.resize()
  render()
}

watch(
  () => [props.nodes, props.edges, props.trace, props.activeStep, props.phase, props.selectedId, props.visitedIds],
  () => nextTick(render),
  { deep: true }
)

onMounted(() => {
  nextTick(() => {
    render()
    if (chartRef.value) {
      observer = new ResizeObserver(onResize)
      observer.observe(chartRef.value)
    }
  })
})

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.sgc {
  position: relative;
  display: flex;
  min-width: 0;
  flex-direction: column;
  min-height: 420px;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  background: #fbfcff;
  overflow: hidden;
}
.sgc.is-fullscreen {
  position: fixed;
  inset: 0;
  z-index: 3000;
  min-height: 100vh;
  border-radius: 0;
  background: #fbfcff;
  padding: 10px 14px 8px;
}
.sgc__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px 0;
}
.sgc__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #8a91a0;
  font-size: 11px;
}
.sgc__status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #b8c1d0;
}
.sgc__status.is-reading i,
.sgc__status.is-traversing i {
  background: #2f5fce;
  box-shadow: 0 0 0 4px rgba(47, 95, 206, 0.12);
  animation: sgc-pulse 1.1s ease-in-out infinite;
}
.sgc__status.is-thinking i {
  background: #e6a23c;
  animation: sgc-pulse 1.1s ease-in-out infinite;
}
.sgc__status.is-ready i {
  background: #2f9e8f;
}
@keyframes sgc-pulse {
  50% { opacity: 0.35; transform: scale(0.8); }
}
.sgc__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.sgc__icon-btn {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid #e3eaf5;
  border-radius: 6px;
  color: #7d8798;
  background: #fff;
  cursor: pointer;
}
.sgc__icon-btn:hover {
  color: #2f5fce;
  border-color: #c9d8f2;
}
.sgc__chart {
  width: 100%;
  height: 430px;
}
.sgc.is-compact {
  min-height: 240px;
}
.sgc.is-compact .sgc__chart {
  height: 220px;
}
.sgc.is-compact .sgc__legend {
  display: none;
}
.sgc.is-fullscreen .sgc__chart {
  height: calc(100vh - 92px);
}
.sgc__empty {
  position: absolute;
  inset: 42px 0 44px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #9aa3b2;
  text-align: center;
}
.sgc__empty b { color: #5f6b7d; font-size: 13px; }
.sgc__empty span { font-size: 11px; }
.sgc__legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 2px 10px 8px;
  color: #8a91a0;
  font-size: 10px;
}
.sgc__legend span { display: inline-flex; align-items: center; gap: 4px; }
.sgc__legend i { width: 8px; height: 8px; border-radius: 50%; }
.sgc__legend i.is-topic { background: #9aa7ba; }
.sgc__legend i.is-bank { border-radius: 3px; background: #7c6cf2; }
.sgc__legend i.is-doc { background: #8b6bb1; }
.sgc__legend i.is-note { background: #2f9e8f; }
.sgc__legend i.is-image { background: #c47a55; }
.sgc__legend em { margin-left: auto; color: #a6adba; font-style: normal; }
@media (max-width: 760px) {
  .sgc__chart { height: 300px; }
  .sgc__legend em { width: 100%; margin-left: 0; }
}
</style>
