<template>
  <div class="spna" :class="{ 'is-animating': animating }">
    <div class="spna__top">
      <div class="spna__status">
        <span class="spna__pulse"></span>
        <span>{{ hasPath ? (animating ? '正在展开规划路径' : '规划路径已生成') : '暂无可用图谱路径' }}</span>
      </div>
      <button v-if="hasPath" type="button" class="spna__replay" title="重新播放" @click="play">
        <OsIcon name="refresh" :size="13" />
      </button>
    </div>

    <template v-if="hasPath">
      <svg class="spna__canvas" viewBox="0 0 760 188" role="img" aria-label="规划建议路径动画">
        <defs>
          <linearGradient id="spna-ray" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#f08a24" stop-opacity=".3" />
            <stop offset="52%" stop-color="#f08a24" stop-opacity=".9" />
            <stop offset="100%" stop-color="#2f9e8f" stop-opacity=".9" />
          </linearGradient>
          <marker id="spna-arrow" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
            <path d="M0 0 L10 3.5 L0 7 L2 3.5 Z" fill="#c2a27d" />
          </marker>
        </defs>

        <g v-for="edge in visibleEdges" :key="`edge-${edge.index}`" class="spna__edge-group">
          <line class="spna__ray-glow" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" />
          <line class="spna__ray" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" marker-end="url(#spna-arrow)" />
        </g>

        <g v-for="node in visibleNodes" :key="node.id" class="spna__node" :class="{ 'is-seed': node.isSeed }"
          :transform="`translate(${node.x} ${node.y})`">
          <circle v-if="node.isSeed" class="spna__seed-halo" :r="node.r + 13" />
          <circle class="spna__node-dot" :r="node.r" :fill="node.color" />
          <circle class="spna__node-ring" :r="node.r + 4" :stroke="node.color" />
          <text class="spna__label" :class="{ 'is-seed-label': node.isSeed }" text-anchor="middle" :y="node.r + 17">
            {{ node.label }}
          </text>
          <text v-if="node.isSeed" class="spna__seed-kicker" text-anchor="middle" :y="node.r + 30">
            主节点
          </text>
        </g>
      </svg>
      <div v-if="hiddenCount" class="spna__more">另有 {{ hiddenCount }} 个后续节点未展开</div>
      <div class="spna__legend">
        <span><i class="is-topic"></i>知识主题</span>
        <span><i class="is-bank"></i>题库</span>
        <span><i class="is-source"></i>来源</span>
      </div>
    </template>

    <div v-else class="spna__empty">
      <b>当前没有可用的真实图谱路径</b>
      <span>已按建议阶段给出方向，不伪造节点之间的连线。</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'
import { entityTypeMeta, normalizeEntityKind } from '@/views/front/workspace/utils/knowledgeGraphMeta'

const props = withDefaults(defineProps<{
  nodes?: any[]
  edges?: any[]
  trace?: any
  title?: string
  phases?: any[]
}>(), {
  nodes: () => [],
  edges: () => [],
  trace: null,
  title: '',
  phases: () => []
})

const visibleNodes = ref<any[]>([])
const visibleEdges = ref<any[]>([])
const animating = ref(false)
let timers: ReturnType<typeof setTimeout>[] = []

const sleep = (ms: number) => new Promise<void>((resolve) => {
  timers.push(setTimeout(resolve, ms))
})

function shortLabel(value: any, max = 11) {
  const text = String(value || '未命名节点').trim()
  return text.length > max ? `${text.slice(0, max)}…` : text
}



function nodeColor(node: any) {
  const kind = normalizeEntityKind(node?.kind)
  return entityTypeMeta(kind).color
}

const nodeById = computed(() => {
  const map = new Map<string, any>()
  for (const node of props.nodes || []) map.set(String(node.id), node)
  return map
})

/**
 * 规划建议是一条“路径”，不是一圈星图。
 * 优先使用 trace.steps 的真实遍历顺序；没有真实边时只显示空态，
 * 不再把阶段节点拼成假连线。
 */
const pathData = computed(() => {
  const steps = Array.isArray(props.trace?.steps) ? props.trace.steps : []
  const byId = nodeById.value
  const seedId = String(props.trace?.seedNodeId || props.trace?.visitedNodeIds?.[0] || '')
  const seed = byId.get(seedId) || (props.nodes || [])[0]
  if (!seed) return { nodes: [], edges: [], hidden: 0 }
  const pathNodes: any[] = [seed]
  const pathEdges: any[] = []
  for (const [index, step] of steps.entries()) {
    const next = byId.get(String(step?.to || ''))
    if (!next) continue
    const previous = pathNodes[pathNodes.length - 1]
    pathEdges.push({
      index,
      from: String(previous.id),
      to: String(next.id),
      kind: String(step?.kind || '')
    })
    pathNodes.push(next)
  }
  // trace 只有 visited、没有 steps 时，按 visited 顺序找图里真实的相邻边。
  if (!pathEdges.length) {
    const visited = (props.trace?.visitedNodeIds || []).map(String)
    for (let index = 1; index < visited.length; index += 1) {
      const from = byId.get(visited[index - 1])
      const to = byId.get(visited[index])
      if (!from || !to) continue
      const edge = (props.edges || []).find((item: any) =>
        (String(item.source) === String(from.id) && String(item.target) === String(to.id)) ||
        (String(item.source) === String(to.id) && String(item.target) === String(from.id))
      )
      if (!edge) continue
      pathEdges.push({
        index: pathEdges.length,
        from: String(from.id),
        to: String(to.id),
        kind: String(edge.kind || '')
      })
      pathNodes.push(to)
    }
  }
  return { nodes: pathNodes, edges: pathEdges, hidden: 0 }
})

const hasPath = computed(() => pathData.value.nodes.length >= 2 && pathData.value.edges.length > 0)
const hiddenCount = computed(() => pathData.value.hidden)

const layout = computed(() => {
  const sourceNodes = pathData.value.nodes.slice(0, 8)
  const count = sourceNodes.length
  if (!count) return { nodes: [], edges: [] }
  const startX = 52
  const endX = 708
  const gap = count > 1 ? (endX - startX) / (count - 1) : 0
  const y = 83
  const nodes = sourceNodes.map((node: any, index: number) => ({
    ...node,
    x: startX + gap * index,
    y,
    r: index === 0 ? 21 : 13,
    isSeed: index === 0,
    color: nodeColor(node),
    label: shortLabel(node.title || (index === 0 ? props.title : '节点'), index === 0 ? 11 : 8)
  }))
  const edges = pathData.value.edges
    .slice(0, Math.max(0, count - 1))
    .map((edge: any, index: number) => ({
      ...edge,
      index,
      x1: nodes[index].x + nodes[index].r,
      y1: y,
      x2: nodes[index + 1].x - nodes[index + 1].r,
      y2: y,
      midX: (nodes[index].x + nodes[index + 1].x) / 2,
      midY: y
    }))
  return { nodes, edges }
})

async function play() {
  timers.forEach((timer) => clearTimeout(timer))
  timers = []
  visibleNodes.value = []
  visibleEdges.value = []
  animating.value = true
  if (!hasPath.value) {
    animating.value = false
    return
  }
  visibleNodes.value = [layout.value.nodes[0]]
  await sleep(540)
  for (let index = 0; index < layout.value.edges.length; index += 1) {
    visibleEdges.value = [...visibleEdges.value, layout.value.edges[index]]
    await sleep(300)
    const node = layout.value.nodes[index + 1]
    if (node) visibleNodes.value = [...visibleNodes.value, node]
    await sleep(120)
  }
  animating.value = false
}

watch(
  () => [props.trace?.traceId, props.trace?.seedNodeId, props.nodes?.length, props.trace?.steps?.length],
  () => { void play() },
  { immediate: true }
)

onBeforeUnmount(() => timers.forEach((timer) => clearTimeout(timer)))
</script>

<style scoped>
.spna {
  position: relative;
  overflow: hidden;
  margin: 2px 0 4px;
  border: 1px solid #edf1f7;
  border-radius: 11px;
  background:
    linear-gradient(90deg, rgba(240, 138, 36, .035), transparent 38%, rgba(47, 158, 143, .035)),
    #fbfcff;
}
.spna__top { display: flex; align-items: center; justify-content: space-between; padding: 7px 9px 0; }
.spna__status { display: inline-flex; align-items: center; gap: 5px; color: #9aa1af; font-size: 9.5px; }
.spna__pulse { width: 5px; height: 5px; border-radius: 50%; background: #f08a24; box-shadow: 0 0 0 0 rgba(240,138,36,.3); animation: spna-pulse 1.4s ease-out infinite; }
.spna__replay { display: inline-flex; padding: 2px; border: 0; color: #a5adba; background: transparent; cursor: pointer; }
.spna__replay:hover { color: #2f5fce; }
.spna__canvas { display: block; width: 100%; height: 176px; overflow: visible; }
.spna__edge-group { pointer-events: none; }
.spna__ray-glow { stroke: #f08a24; stroke-width: 7; opacity: .07; }
.spna__ray { stroke: url(#spna-ray); stroke-width: 1.8; stroke-dasharray: 5 4; animation: spna-ray-in .48s ease-out both; }
.spna__node { animation: spna-node-in .34s cubic-bezier(.2,.8,.2,1) both; }
.spna__node-dot { stroke: #fff; stroke-width: 2; }
.spna__node-ring { fill: none; stroke-width: 1; opacity: .32; }
.spna__seed-halo { fill: rgba(240, 138, 36, .1); animation: spna-halo 2.1s ease-in-out infinite; }
.spna__label { fill: #5f6b7d; font-size: 9.5px; font-weight: 500; paint-order: stroke; stroke: #fbfcff; stroke-width: 3px; stroke-linejoin: round; }
.spna__label.is-seed-label { fill: #253247; font-size: 12px; font-weight: 700; }
.spna__seed-kicker { fill: #b2b8c3; font-size: 8.5px; letter-spacing: .08em; }
.spna__more { padding: 0 10px 3px; color: #a0a8b6; font-size: 9.5px; }
.spna__legend { display: flex; gap: 10px; padding: 0 10px 8px; color: #a0a8b6; font-size: 9px; }
.spna__legend span { display: inline-flex; align-items: center; gap: 4px; }
.spna__legend i { width: 5px; height: 5px; border-radius: 50%; }
.spna__legend .is-topic { background: #f08a24; }
.spna__legend .is-bank { background: #2f9e8f; }
.spna__legend .is-source { background: #3b7cff; }
.spna__empty { display: flex; min-height: 104px; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 8px 16px 16px; text-align: center; }
.spna__empty b { color: #8d96a5; font-size: 11px; font-weight: 600; }
.spna__empty span { color: #b0b6c0; font-size: 9.5px; }
@keyframes spna-node-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes spna-ray-in { from { opacity: 0; stroke-dashoffset: 32; } to { opacity: 1; stroke-dashoffset: 0; } }
@keyframes spna-pulse { 0% { box-shadow: 0 0 0 0 rgba(240,138,36,.3); } 70% { box-shadow: 0 0 0 6px rgba(240,138,36,0); } 100% { box-shadow: 0 0 0 0 rgba(240,138,36,0); } }
@keyframes spna-halo { 0%, 100% { opacity: .7; transform: scale(.94); } 50% { opacity: 1; transform: scale(1.04); } }
</style>
