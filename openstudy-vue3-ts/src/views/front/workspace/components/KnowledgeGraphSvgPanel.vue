<template>
  <section class="kg-page">
    <div class="kg-head">
      <div>
        <div class="kg-kicker">资料知识网络 · 知识图谱</div>
        <h2>实体-关系图</h2>
        <p>实体由资料正文抽取，关系带方向和来源 chunk；点击实体可查看来源并回到原文。</p>
        <div v-if="stats.entityCount" class="kg-stats">
          <b>{{ stats.entityCount }}</b> 个实体
          <span>·</span>
          <b>{{ stats.relationCount }}</b> 条关系
          <span>·</span>
          <b>{{ stats.docCount }}</b> 份资料
        </div>
      </div>
      <div class="kg-head__actions">
        <el-checkbox v-model="hideIsolated" size="small">隐藏孤立实体与小碎片</el-checkbox>
        <el-button size="small" :loading="loading" @click="reload">刷新</el-button>
        <el-button size="small" class="kg-build-btn" :loading="building" :disabled="!activeKbId" @click="buildGraph">
          抽取当前资料夹
        </el-button>
      </div>
    </div>

    <div class="kg-stage">
      <div ref="canvasRef" class="kg-canvas"
        @wheel.prevent="onWheel"
        @pointerdown="onCanvasDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointerleave="onPointerUp"
        @dblclick="resetView">
        <svg ref="svgRef" class="kg-svg" aria-label="实体关系知识图谱">
          <g :transform="`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`">
            <path v-for="hull in hulls" :key="hull.key" :d="hull.path" class="kg-hull"
              :class="{ 'is-hovered': hoveredCluster === hull.key }" />
            <line v-for="edge in edgeLines" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              class="kg-edge" :class="{ 'is-active': isEdgeActive(edge), 'is-dimmed': isEdgeDimmed(edge) }" />
            <g v-for="node in layoutNodes" :key="node.id" class="kg-node"
              :class="{ 'is-hovered': hoveredId === String(node.id), 'is-dimmed': isNodeDimmed(node) }"
              :transform="`translate(${node.x} ${node.y})`"
              @pointerdown.stop="onNodeDown($event, node)"
              @pointerup.stop="onNodeUp($event, node)"
              @click.stop="onNodeClick(node)"
              @mouseenter="hoveredId = String(node.id)"
              @mouseleave="hoveredId = null">
              <circle class="kg-node__halo" :r="nodeRadius(node) + 7" />
              <circle class="kg-node__dot" :r="nodeRadius(node)" :fill="typeColor(node.type)" />
              <text v-if="node.isHub" class="kg-node__label" :x="nodeRadius(node) + 8" y="3">{{ node.name }}</text>
            </g>
          </g>
        </svg>
        <div v-if="!loading && !allNodes.length" class="kg-empty">
          <div class="kg-empty__art">◇</div>
          <h3>这个资料夹还没有知识图谱</h3>
          <p>从资料正文抽取实体与关系。抽取会调用模型，只在你点击后运行。</p>
          <el-button type="primary" :loading="building" :disabled="!activeKbId" @click="buildGraph">
            抽取当前资料夹
          </el-button>
        </div>
        <div v-if="loading" class="kg-loading" v-loading="true"></div>
        <div class="kg-search-hint">
          <span v-if="searchQuery">搜索：{{ searchQuery }}</span>
          <span>滚轮缩放 · 空白拖拽平移 · 拖拽节点 · 双击复位</span>
        </div>
        <div class="kg-legend">
          <span v-for="item in typeLegend" :key="item.type" class="kg-legend__item">
            <i :style="{ background: item.color }"></i>{{ item.type }}
          </span>
        </div>
      </div>
    </div>

    <el-drawer v-model="detailVisible" size="420px" :with-header="false" append-to-body class="kg-detail-drawer">
      <div v-if="detailLoading" class="kg-detail-loading" v-loading="true"></div>
      <div v-else-if="detail" class="kg-detail">
        <div class="kg-detail__eyebrow">ENTITY</div>
        <h3>{{ detail.entity.name }}</h3>
        <div class="kg-detail__meta">
          <span class="kg-type" :style="{ color: typeColor(detail.entity.type), background: typeBg(detail.entity.type) }">{{ detail.entity.type }}</span>
          <span>出现 {{ detail.entity.mentionCount }} 次</span>
        </div>
        <p class="kg-detail__desc">{{ detail.entity.description || '暂无描述' }}</p>

        <section class="kg-detail__section">
          <div class="kg-detail__section-head"><span>关联关系</span><b>{{ detail.neighbors?.length || 0 }}</b></div>
          <div v-if="detail.neighbors?.length" class="kg-neighbors">
            <button v-for="n in detail.neighbors" :key="`${n.entityId}-${n.relationType}-${n.direction}`"
              type="button" class="kg-neighbor" @click="focusEntity(n.entityId)">
              <span class="kg-neighbor__type" :style="{ color: typeColor(n.type) }">{{ n.type }}</span>
              <b>{{ n.name }}</b>
              <span class="kg-neighbor__rel">{{ n.direction === 'out' ? '→' : '←' }} {{ n.relationType }}</span>
            </button>
          </div>
          <div v-else class="kg-detail__empty">这条实体还没有抽到关系。</div>
        </section>

        <section class="kg-detail__section">
          <div class="kg-detail__section-head"><span>来源 chunk</span><b>{{ detail.chunks?.length || 0 }}</b></div>
          <div v-if="detail.chunks?.length" class="kg-chunks">
            <button v-for="c in detail.chunks" :key="c.chunkId" type="button" class="kg-chunk" @click="locateChunk(c)">
              <b>{{ c.fileName }} · 第 {{ c.chunkIndex + 1 }} 段</b>
              <span>{{ c.excerpt }}</span>
            </button>
          </div>
          <div v-else class="kg-detail__empty">没有可定位的原文来源。</div>
        </section>
      </div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { buildKnowledgeGraph, getKnowledgeGraph, getKnowledgeGraphEntity } from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  searchQuery?: string
  typeFilter?: string[]
}>()

const emit = defineEmits<{
  (e: 'stats', payload: { total: number }): void
  (e: 'locate', payload: { docId: number; chunkId?: number; chunkIndex?: number }): void
}>()

const TYPE_META = [
  { type: '概念', color: '#4F6BED', bg: '#EEF2FF' },
  { type: '定理/公式', color: '#C47A55', bg: '#FFF4EE' },
  { type: '方法', color: '#2F9E8F', bg: '#EDF9F6' },
  { type: '人物', color: '#8B6BB1', bg: '#F5F0FB' },
  { type: '机构', color: '#B78B2A', bg: '#FFF8E8' },
  { type: '事件', color: '#5C8FA8', bg: '#EFF7FA' },
  { type: '作品', color: '#C05C7E', bg: '#FFF1F5' },
  { type: '其他', color: '#9AA1AF', bg: '#F3F5F9' }
]

const canvasRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)
const loading = ref(false)
const building = ref(false)
const graph = ref<any>({ nodes: [], edges: [], stats: {} })
const layoutNodes = ref<any[]>([])
const layoutClusters = ref<any[]>([])
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)
const hideIsolated = ref(true)
const hoveredId = ref<string | null>(null)
const viewport = reactive({ x: 0, y: 0, scale: 1 })
let suppressClickUntil = 0
let pointerState: any = null
let resizeObserver: ResizeObserver | null = null

const allNodes = computed(() => graph.value?.nodes || [])
const allEdges = computed(() => graph.value?.edges || [])
const stats = computed(() => graph.value?.stats || {})
const typeLegend = computed(() =>
  TYPE_META.filter((item) => allNodes.value.some((node: any) => node.type === item.type))
)

const visibleGraph = computed(() => {
  const selectedTypes = Array.isArray(props.typeFilter) ? props.typeFilter : []
  let nodes = allNodes.value
  if (selectedTypes.length) nodes = nodes.filter((node: any) => selectedTypes.includes(node.type))
  if (hideIsolated.value && allEdges.value.length) {
    nodes = nodes.filter((node: any) => Number(node.degree || 0) > 0)
  }
  const q = String(props.searchQuery || '').trim().toLowerCase()
  if (!q) {
    const ids = new Set(nodes.map((node: any) => node.id))
    return { nodes, edges: allEdges.value.filter((edge: any) => ids.has(edge.source) && ids.has(edge.target)) }
  }
  const matched = new Set(
    nodes
      .filter((node: any) => `${node.name} ${node.description || ''}`.toLowerCase().includes(q))
      .map((node: any) => node.id)
  )
  for (const edge of allEdges.value) {
    if (matched.has(edge.source)) matched.add(edge.target)
    if (matched.has(edge.target)) matched.add(edge.source)
  }
  const visible = nodes.filter((node: any) => matched.has(node.id))
  const ids = new Set(visible.map((node: any) => node.id))
  return {
    nodes: visible,
    edges: allEdges.value.filter((edge: any) => ids.has(edge.source) && ids.has(edge.target))
  }
})

const hoveredNeighbors = computed(() => {
  const id = hoveredId.value
  const set = new Set<string>()
  if (!id) return set
  set.add(id)
  for (const edge of allEdges.value) {
    if (String(edge.source) === id) set.add(String(edge.target))
    if (String(edge.target) === id) set.add(String(edge.source))
  }
  return set
})

const hoveredCluster = computed(() => {
  const id = hoveredId.value
  if (!id) return -1
  return layoutClusters.value.findIndex((cluster) => cluster.ids.some((item: string) => String(item) === id))
})

const edgeLines = computed(() => {
  const pos = new Map(layoutNodes.value.map((node) => [String(node.id), node]))
  return visibleGraph.value.edges
    .map((edge: any, index: number) => {
      const source = pos.get(String(edge.source))
      const target = pos.get(String(edge.target))
      if (!source || !target) return null
      return {
        key: `${edge.source}-${edge.target}-${index}`,
        source: String(edge.source),
        target: String(edge.target),
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        strength: Number(edge.strength || 5)
      }
    })
    .filter(Boolean) as any[]
})

function typeColor(type: string) {
  return TYPE_META.find((item) => item.type === type)?.color || '#9AA1AF'
}
function typeBg(type: string) {
  return TYPE_META.find((item) => item.type === type)?.bg || '#F3F5F9'
}
function nodeRadius(node: any) {
  // 节点克制一些，把空间留给簇与簇之间的留白。
  return 8 + Math.min(12, Math.sqrt(Number(node.degree || 0) + 1) * 3)
}

function buildStaticLayout(nodes: any[], edges: any[], width: number, height: number) {
  const byId = new Map(nodes.map((node) => [String(node.id), { ...node, x: 0, y: 0, isHub: false }]))
  const adjacency = new Map<string, string[]>()
  for (const node of nodes) adjacency.set(String(node.id), [])
  for (const edge of edges) {
    adjacency.get(String(edge.source))?.push(String(edge.target))
    adjacency.get(String(edge.target))?.push(String(edge.source))
  }
  const visited = new Set<string>()
  let components: string[][] = []
  for (const node of nodes) {
    const start = String(node.id)
    if (visited.has(start)) continue
    const component: string[] = []
    const stack = [start]
    visited.add(start)
    while (stack.length) {
      const id = stack.pop()!
      component.push(id)
      for (const next of adjacency.get(id) || []) {
        if (!visited.has(next)) {
          visited.add(next)
          stack.push(next)
        }
      }
    }
    components.push(component)
  }
  // 小碎片（1~2 个实体）多半是抽取噪声；默认只展示两个主主题簇，
  // 每个簇占独立网格单元，避免簇与簇的多边形互相覆盖。
  // 排序优先概念/定理占比高的主题簇，避免把 make/main 这类代码工具簇
  // 误当成知识主题排到概率论前面。
  const componentScore = (component: string[]) =>
    component.reduce((score, id) => {
      const node: any = byId.get(id)
      if (!node) return score
      if (node.type === '概念' || node.type === '定理/公式') return score + 2
      if (node.type === '方法') return score + 1
      return score
    }, 0)
  components.sort((a, b) => componentScore(b) - componentScore(a) || b.length - a.length)
  if (hideIsolated.value) {
    // 只保留两个主主题簇，给多边形留出真正的外圈空白；小碎片仍可关掉开关查看。
    components = components.filter((component) => component.length >= 3).slice(0, 2)
  }

  const count = components.length
  const cols = count <= 3 ? Math.max(1, count) : count <= 4 ? 2 : 3
  const rows = Math.max(1, Math.ceil(count / cols))
  const cellW = width / cols
  const cellH = height / rows
  const laidOut: any[] = []
  const clusters: any[] = []

  components.forEach((component, index) => {
    const items = component.map((id) => byId.get(id)).filter(Boolean) as any[]
    if (!items.length) return
    const hub = [...items].sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))[0]
    const col = index % cols
    const row = Math.floor(index / cols)
    const centerX = cellW * (col + 0.5)
    const centerY = cellH * (row + 0.5)
    const others = items.filter((item) => item !== hub).sort((a, b) => Number(b.degree || 0) - Number(a.degree || 0))
    const baseRadius = Math.max(70, Math.min(150, Math.min(cellW * 0.24, cellH * 0.30)))
    const innerCount = Math.min(others.length, Math.max(6, Math.floor((Math.PI * 2 * baseRadius) / 78)))
    const inner = others.slice(0, innerCount)
    const outer = others.slice(innerCount)

    hub.x = centerX
    hub.y = centerY
    hub.isHub = index < 3 && items.length > 1
    laidOut.push(hub)
    const placeRing = (ring: any[], radius: number, offset = 0) => {
      ring.forEach((node, ringIndex) => {
        const angle = -Math.PI / 2 + (Math.PI * 2 * ringIndex) / Math.max(ring.length, 1) + offset
        node.x = centerX + Math.cos(angle) * radius
        node.y = centerY + Math.sin(angle) * radius
        laidOut.push(node)
      })
    }
    placeRing(inner, baseRadius, 0)
    placeRing(outer, baseRadius + 82, Math.PI / Math.max(outer.length, 1))
    clusters.push({ ids: component, nodes: [hub, ...inner, ...outer] })
  })

  // 自动检查节点间距：分离重叠节点，避免用户误触。
  for (let pass = 0; pass < 16; pass++) {
    let moved = false
    for (let i = 0; i < laidOut.length; i++) {
      for (let j = i + 1; j < laidOut.length; j++) {
        const a = laidOut[i]
        const b = laidOut[j]
        let dx = b.x - a.x
        let dy = b.y - a.y
        let distance = Math.hypot(dx, dy)
        if (distance >= 72) continue
        if (distance < 0.001) {
          dx = 1
          dy = 0
          distance = 1
        }
        const push = (72 - distance) / 2 + 0.5
        const ux = dx / distance
        const uy = dy / distance
        a.x = Math.max(26, Math.min(width - 26, a.x - ux * push))
        a.y = Math.max(26, Math.min(height - 26, a.y - uy * push))
        b.x = Math.max(26, Math.min(width - 26, b.x + ux * push))
        b.y = Math.max(26, Math.min(height - 26, b.y + uy * push))
        moved = true
      }
    }
    if (!moved) break
  }
  return { nodes: laidOut, clusters }
}

/** 与 WeKnora `graphClusterOutline` 同一个思路：对节点圆盘做凸包，再用闭合三次曲线描边。 */
function clusterOutline(points: any[]) {
  if (!points.length) return ''
  const samples = 20
  const expanded = points.flatMap((p) => {
    const radius = nodeRadius(p) + 20
    return Array.from({ length: samples }, (_, i) => ({
      x: p.x + Math.cos((i * 2 * Math.PI) / samples) * radius,
      y: p.y + Math.sin((i * 2 * Math.PI) / samples) * radius
    }))
  }).sort((a, b) => a.x - b.x || a.y - b.y)
  const unique = expanded.filter((p, i) => !i || p.x !== expanded[i - 1].x || p.y !== expanded[i - 1].y)
  const cross = (o: any, a: any, b: any) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x)
  const half = (list: any[]) => {
    const hull: any[] = []
    for (const point of list) {
      while (hull.length > 1 && cross(hull[hull.length - 2], hull[hull.length - 1], point) <= 0) hull.pop()
      hull.push(point)
    }
    hull.pop()
    return hull
  }
  const hull = [...half(unique), ...half([...unique].reverse())]
  if (!hull.length) return ''
  const at = (i: number) => hull[(i + hull.length) % hull.length]
  const fmt = (p: any) => `${Math.round(p.x * 10) / 10},${Math.round(p.y * 10) / 10}`
  const tangent = (from: any, to: any, length: number) => {
    const dx = to.x - from.x
    const dy = to.y - from.y
    const norm = Math.hypot(dx, dy) || 1
    return { x: (dx / norm) * length, y: (dy / norm) * length }
  }
  const path = [`M${fmt(hull[0])}`]
  hull.forEach((p, i) => {
    const next = at(i + 1)
    const reach = Math.hypot(next.x - p.x, next.y - p.y) * 0.36
    const out = tangent(at(i - 1), next, reach)
    const into = tangent(p, at(i + 2), reach)
    path.push(`C${fmt({ x: p.x + out.x, y: p.y + out.y })} ${fmt({ x: next.x - into.x, y: next.y - into.y })} ${fmt(next)}`)
  })
  return path.join(' ') + ' Z'
}

const hulls = computed(() =>
  layoutClusters.value.map((cluster, index) => ({
    key: index,
    path: clusterOutline(cluster.nodes)
  })).filter((item) => item.path)
)

const visibleEdges = computed(() => edgeLines.value)

function isNodeDimmed(node: any) {
  return !!hoveredId.value && !hoveredNeighbors.value.has(String(node.id))
}
function isEdgeActive(edge: any) {
  return !!hoveredId.value && (edge.source === hoveredId.value || edge.target === hoveredId.value)
}
function isEdgeDimmed(edge: any) {
  return !!hoveredId.value && !isEdgeActive(edge)
}

function layout() {
  const width = Math.max(680, canvasRef.value?.clientWidth || 1000)
  const height = Math.max(480, canvasRef.value?.clientHeight || 660)
  const result = buildStaticLayout(visibleGraph.value.nodes, visibleGraph.value.edges, width, height)
  layoutNodes.value = result.nodes
  layoutClusters.value = result.clusters
  const xs = result.nodes.map((node) => node.x)
  const ys = result.nodes.map((node) => node.y)
  if (xs.length) {
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const scale = Math.min(1, Math.max(0.35, Math.min((width - 100) / Math.max(120, maxX - minX), (height - 100) / Math.max(120, maxY - minY))))
    viewport.scale = scale
    viewport.x = width / 2 - ((minX + maxX) / 2) * scale
    viewport.y = height / 2 - ((minY + maxY) / 2) * scale
  }
}

function onWheel(event: WheelEvent) {
  const rect = svgRef.value?.getBoundingClientRect()
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  const oldScale = viewport.scale
  const factor = event.deltaY < 0 ? 1.14 : 1 / 1.14
  const nextScale = Math.max(0.35, Math.min(2.6, oldScale * factor))
  const wx = (px - viewport.x) / oldScale
  const wy = (py - viewport.y) / oldScale
  viewport.scale = nextScale
  viewport.x = px - wx * nextScale
  viewport.y = py - wy * nextScale
}

function onCanvasDown(event: PointerEvent) {
  if (event.button !== 0) return
  pointerState = {
    mode: 'pan',
    startX: event.clientX,
    startY: event.clientY,
    viewportX: viewport.x,
    viewportY: viewport.y,
    moved: false
  }
  svgRef.value?.setPointerCapture(event.pointerId)
}

function onNodeDown(event: PointerEvent, node: any) {
  if (event.button !== 0) return
  pointerState = {
    mode: 'node',
    node,
    startX: event.clientX,
    startY: event.clientY,
    nodeX: node.x,
    nodeY: node.y,
    moved: false
  }
  svgRef.value?.setPointerCapture(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!pointerState) return
  const dx = event.clientX - pointerState.startX
  const dy = event.clientY - pointerState.startY
  if (Math.abs(dx) + Math.abs(dy) > 2) pointerState.moved = true
  if (pointerState.mode === 'pan') {
    viewport.x = pointerState.viewportX + dx
    viewport.y = pointerState.viewportY + dy
  } else if (pointerState.mode === 'node') {
    pointerState.node.x = pointerState.nodeX + dx / viewport.scale
    pointerState.node.y = pointerState.nodeY + dy / viewport.scale
  }
}

function onPointerUp() {
  const state = pointerState
  if (state?.mode === 'node' && !state.moved) {
    // pointer capture 时 pointerup 会被重定向到 SVG 根节点，节点自身收不到；
    // 在画布层的 pointerup 补一次点击判定，保证点节点一定能开抽屉。
    suppressClickUntil = performance.now() + 300
    openDetail(String(state.node.id))
  } else if (state?.moved) {
    suppressClickUntil = performance.now() + 250
  }
  pointerState = null
}

function onNodeUp(_event: PointerEvent, node: any) {
  const state = pointerState
  if (state?.mode === 'node' && !state.moved) {
    // pointer capture 后 click 可能落在 SVG 根节点上，不能依赖 @click；
    // 在 pointerup 且没有拖动时直接打开详情，保证“点一下就有抽屉”。
    suppressClickUntil = performance.now() + 300
    openDetail(String(node.id))
  } else if (state?.moved) {
    suppressClickUntil = performance.now() + 250
  }
  pointerState = null
}

function onNodeClick(node: any) {
  if (performance.now() < suppressClickUntil) return
  openDetail(String(node.id))
}

function resetView() {
  viewport.x = 0
  viewport.y = 0
  viewport.scale = 1
}

async function reload() {
  loading.value = true
  try {
    const res = await getKnowledgeGraph({ kbId: props.activeKbId || undefined })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识图谱加载失败')
      return
    }
    graph.value = res.data || { nodes: [], edges: [], stats: {} }
    emit('stats', { total: Number(graph.value?.stats?.entityCount || 0) })
    await nextTick()
    layout()
  } catch (error: any) {
    ElMessage.error('知识图谱加载失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

async function buildGraph() {
  if (!props.activeKbId || building.value) return
  building.value = true
  try {
    const res = await buildKnowledgeGraph({ kbId: Number(props.activeKbId) })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识图谱抽取失败')
      return
    }
    const data = res.data || {}
    const failed = Number(data.errors?.length || 0)
    if (failed) ElMessage.warning(`完成 ${data.processedDocs || 0} 份资料，${failed} 份抽取失败`)
    else ElMessage.success(`已抽取 ${data.entities || 0} 个实体、${data.relations || 0} 条关系`)
    await reload()
  } catch (error: any) {
    ElMessage.error('知识图谱抽取失败：' + (error?.message || error))
  } finally {
    building.value = false
  }
}

async function openDetail(entityId: string) {
  detailVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const res = await getKnowledgeGraphEntity(entityId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '实体详情加载失败')
      return
    }
    detail.value = res.data
  } catch (error: any) {
    ElMessage.error('实体详情加载失败：' + (error?.message || error))
  } finally {
    detailLoading.value = false
  }
}

function focusEntity(entityId: number | string) {
  if (allNodes.value.some((item: any) => String(item.id) === String(entityId))) openDetail(String(entityId))
}

function locateChunk(chunk: any) {
  if (!chunk?.docId) return
  emit('locate', {
    docId: Number(chunk.docId),
    chunkId: Number(chunk.chunkId) || undefined,
    chunkIndex: Number(chunk.chunkIndex) || undefined
  })
  detailVisible.value = false
}

watch(
  () => props.activeKbId,
  () => reload()
)
watch(
  () => [props.typeFilter, props.searchQuery],
  () => layout(),
  { deep: true }
)
watch(hideIsolated, () => layout())
watch(visibleGraph, () => layout(), { deep: true })

onMounted(async () => {
  await reload()
  if (canvasRef.value) {
    resizeObserver = new ResizeObserver(() => layout())
    resizeObserver.observe(canvasRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})
</script>

<style scoped>
.kg-page { display: flex; flex-direction: column; gap: 12px; padding: 2px 2px 10px; }
.kg-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 2px 2px 10px; border-bottom: 1px solid #edf0f5; }
.kg-kicker { color: #4f6bed; font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.kg-head h2 { margin: 5px 0 4px; color: #1f2937; font-size: 22px; font-weight: 700; }
.kg-head p { margin: 0; color: #8a91a0; font-size: 11px; }
.kg-stats { display: flex; align-items: center; gap: 5px; margin-top: 7px; color: #9aa1af; font-size: 10px; }
.kg-stats b { color: #4f6bed; font-weight: 600; }
.kg-head__actions { display: flex; flex: none; align-items: center; gap: 8px; }
.kg-build-btn { border-color: rgba(79, 107, 237, 0.25); color: #4f6bed; background: #f7f9ff; }
.kg-stage { position: relative; min-height: 620px; overflow: hidden; border: 1px solid #e9ecf2; border-radius: 13px; background: radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.11) 1px, transparent 0), #fbfcfe; background-size: 20px 20px; }
.kg-canvas { width: 100%; height: 660px; position: relative; touch-action: none; cursor: grab; user-select: none; }
.kg-canvas:active { cursor: grabbing; }
.kg-svg { width: 100%; height: 100%; overflow: visible; }
.kg-hull { fill: #f1f3f7; fill-opacity: 0.72; stroke: #e5e8ef; stroke-width: 1; vector-effect: non-scaling-stroke; transition: fill 0.2s ease, stroke 0.2s ease; }
.kg-hull.is-hovered { fill: #ebeef5; stroke: #dce2ed; }
.kg-edge { stroke: #c7d0e0; stroke-width: 1; opacity: 0.78; vector-effect: non-scaling-stroke; transition: opacity 0.18s ease, stroke 0.18s ease; }
.kg-edge.is-active { stroke: #7e94bf; stroke-width: 1.5; opacity: 1; }
.kg-edge.is-dimmed { opacity: 0.16; }
.kg-node { cursor: pointer; transition: opacity 0.18s ease; }
.kg-node.is-dimmed { opacity: 0.18; }
.kg-node__halo { fill: rgba(255, 255, 255, 0.8); stroke: transparent; transition: fill 0.18s ease, stroke 0.18s ease; }
.kg-node.is-hovered .kg-node__halo { fill: rgba(255, 255, 255, 0.98); stroke: #cdd6e7; stroke-width: 1.5; }
.kg-node__dot { stroke: #ffffff; stroke-width: 2; }
.kg-node.is-hovered .kg-node__dot { stroke: #172033; stroke-width: 3; }
.kg-node__label { fill: #4b5563; font-size: 10px; pointer-events: none; }
.kg-node.is-hovered .kg-node__label { fill: #172033; font-weight: 600; }
.kg-search-hint { position: absolute; bottom: 13px; left: 14px; display: flex; gap: 12px; padding: 5px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 6px; background: rgba(255, 255, 255, 0.82); color: #9aa1af; font-size: 9.5px; pointer-events: none; }
.kg-search-hint span + span::before { margin-right: 12px; color: #d1d5db; content: '·'; }
.kg-legend { position: absolute; top: 12px; left: 14px; display: flex; flex-wrap: wrap; gap: 7px 11px; max-width: 700px; padding: 6px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 7px; background: rgba(255, 255, 255, 0.86); pointer-events: none; }
.kg-legend__item { display: inline-flex; align-items: center; gap: 4px; color: #7d8596; font-size: 9.5px; }
.kg-legend__item i { width: 7px; height: 7px; border-radius: 50%; }
.kg-empty, .kg-loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; background: rgba(251, 252, 254, 0.94); text-align: center; }
.kg-empty__art { display: flex; width: 54px; height: 54px; align-items: center; justify-content: center; margin-bottom: 9px; border-radius: 16px; color: #4f6bed; background: #eef2ff; font-size: 27px; }
.kg-empty h3 { margin: 0 0 5px; color: #374151; font-size: 16px; }
.kg-empty p { max-width: 380px; margin: 0 0 14px; color: #9aa1af; font-size: 11px; line-height: 1.7; }
.kg-detail-drawer :deep(.el-drawer__body) { padding: 20px; }
.kg-detail { display: flex; flex-direction: column; gap: 15px; }
.kg-detail__eyebrow { color: #4f6bed; font-size: 9px; font-weight: 700; letter-spacing: 0.14em; }
.kg-detail h3 { margin: -8px 0 0; color: #1f2937; font-size: 20px; line-height: 1.4; }
.kg-detail__meta { display: flex; align-items: center; gap: 9px; color: #9aa1af; font-size: 10px; }
.kg-type { padding: 3px 7px; border-radius: 5px; font-size: 10px; font-weight: 600; }
.kg-detail__desc { margin: 0; color: #596173; font-size: 12px; line-height: 1.75; }
.kg-detail__section { padding-top: 12px; border-top: 1px solid #eef0f5; }
.kg-detail__section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; color: #6b7280; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.kg-detail__section-head b { color: #4f6bed; font-weight: 600; }
.kg-neighbors, .kg-chunks { display: flex; flex-direction: column; gap: 6px; }
.kg-neighbor, .kg-chunk { display: flex; min-width: 0; align-items: center; gap: 7px; padding: 8px 9px; border: 1px solid #eef0f5; border-radius: 8px; background: #fbfcfe; color: #596173; cursor: pointer; font-size: 10.5px; text-align: left; }
.kg-neighbor:hover, .kg-chunk:hover { border-color: #d9e1f4; background: #f5f7fc; }
.kg-neighbor__type { flex: none; font-size: 9px; }
.kg-neighbor b { overflow: hidden; flex: 1; color: #374151; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.kg-neighbor__rel { flex: none; color: #9aa1af; font-size: 9.5px; }
.kg-chunk { flex-direction: column; align-items: flex-start; gap: 3px; }
.kg-chunk b { overflow: hidden; color: #4b5563; font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; }
.kg-chunk span { overflow: hidden; color: #9aa1af; font-size: 10px; line-height: 1.55; text-overflow: ellipsis; white-space: nowrap; }
.kg-detail__empty { padding: 12px 0; color: #a0a6b2; font-size: 10.5px; }
.kg-detail-loading { height: 500px; }
@media (max-width: 900px) { .kg-stage, .kg-canvas { min-height: 480px; height: 480px; } .kg-head { flex-direction: column; align-items: flex-start; gap: 8px; } }
</style>
