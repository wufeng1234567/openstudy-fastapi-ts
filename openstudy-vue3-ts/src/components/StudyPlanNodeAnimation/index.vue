<template>
  <div class="spna" :class="{ 'is-animating': animating }">
    <div class="spna__top">
      <div class="spna__status">
        <span class="spna__pulse"></span>
        <span>{{ animating ? '正在展开规划路径' : '规划路径已生成' }}</span>
      </div>
      <button type="button" class="spna__replay" title="重新播放" @click="play">
        <OsIcon name="refresh" :size="13" />
      </button>
    </div>

    <svg class="spna__canvas" viewBox="0 0 720 330" role="img" aria-label="规划建议节点连接动画">
      <defs>
        <linearGradient id="spna-ray" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#f08a24" stop-opacity=".15" />
          <stop offset="55%" stop-color="#f08a24" stop-opacity=".7" />
          <stop offset="100%" stop-color="#2f9e8f" stop-opacity=".75" />
        </linearGradient>
        <filter id="spna-soft" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="3" />
        </filter>
      </defs>

      <g v-for="edge in visibleEdges" :key="`edge-${edge.index}`" class="spna__edge-group">
        <line class="spna__ray-glow" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" />
        <line class="spna__ray" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" />
        <circle r="3" class="spna__ray-dot">
          <animateMotion :dur="`${edge.duration}ms`" fill="freeze" :path="`M ${edge.x1} ${edge.y1} L ${edge.x2} ${edge.y2}`" />
        </circle>
      </g>

      <g v-for="node in visibleNodes" :key="node.id" class="spna__node" :class="{ 'is-seed': node.isSeed }"
        :transform="`translate(${node.x} ${node.y})`">
        <circle v-if="node.isSeed" class="spna__seed-halo" :r="node.r + 15" />
        <circle class="spna__node-dot" :r="node.r" :fill="node.color" />
        <circle class="spna__node-ring" :r="node.r + 4" :stroke="node.color" />
        <text class="spna__label" :class="{ 'is-seed-label': node.isSeed }" text-anchor="middle" :y="node.r + 17">
          {{ node.label }}
        </text>
        <text v-if="node.isSeed" class="spna__seed-kicker" text-anchor="middle" :y="node.r + 31">
          主节点
        </text>
      </g>
    </svg>

    <div v-if="hiddenCount" class="spna__more">另有 {{ hiddenCount }} 个关联节点未展开</div>
    <div class="spna__legend">
      <span><i class="is-topic"></i>知识主题</span>
      <span><i class="is-bank"></i>题库</span>
      <span><i class="is-source"></i>来源</span>
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

const seedId = computed(() => String(props.trace?.seedNodeId || props.trace?.visitedNodeIds?.[0] || ''))
const graphNodes = computed(() => {
  const nodes = Array.isArray(props.nodes) ? props.nodes : []
  if (nodes.length) return nodes
  // 数据降级：没有图时用建议阶段画一张可读的主节点图，仍不伪造边。
  return [
    { id: 'seed:advice', kind: 'topic', title: props.title || '规划建议', isFallback: true },
    ...(props.phases || []).map((phase: any, index: number) => ({
      id: `phase:${index}`,
      kind: 'topic',
      title: phase.title || '阶段',
      isFallback: true
    }))
  ]
})

const layout = computed(() => {
  const all = graphNodes.value
  if (!all.length) return { nodes: [], edges: [], hidden: 0 }
  const seed = all.find((node: any) => String(node.id) === seedId.value) || all[0]
  const visitedOrder = new Map<string, number>(
    (props.trace?.visitedNodeIds || []).map((id: any, index: number) => [String(id), index])
  )
  const rest = all
    .filter((node: any) => String(node.id) !== String(seed.id))
    .sort((a: any, b: any) => (visitedOrder.get(String(a.id)) ?? 99) - (visitedOrder.get(String(b.id)) ?? 99))
  const visibleRest = rest.slice(0, 8)
  const count = visibleRest.length
  const cx = 360
  const cy = 155
  const rx = count > 6 ? 238 : 218
  const ry = count > 4 ? 92 : 78
  const nodes = [
    { ...seed, x: cx, y: cy, r: 22, isSeed: true, color: nodeColor(seed), label: shortLabel(seed.title || props.title || '主节点', 12) },
    ...visibleRest.map((node: any, index: number) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(count, 1)
      return {
        ...node,
        x: cx + Math.cos(angle) * rx,
        y: cy + Math.sin(angle) * ry,
        r: 13,
        isSeed: false,
        color: nodeColor(node),
        label: shortLabel(node.title, 10)
      }
    })
  ]
  const edges = visibleRest.map((node: any, index: number) => ({
    index,
    x1: cx,
    y1: cy,
    x2: cx + Math.cos(-Math.PI / 2 + (Math.PI * 2 * index) / Math.max(count, 1)) * rx,
    y2: cy + Math.sin(-Math.PI / 2 + (Math.PI * 2 * index) / Math.max(count, 1)) * ry,
    duration: 460
  }))
  return { nodes, edges, hidden: Math.max(0, rest.length - visibleRest.length) }
})

const hiddenCount = computed(() => layout.value.hidden)

async function play() {
  timers.forEach((timer) => clearTimeout(timer))
  timers = []
  visibleNodes.value = []
  visibleEdges.value = []
  animating.value = true
  const nodes = layout.value.nodes
  if (!nodes.length) {
    animating.value = false
    return
  }
  // 第一拍只出现主节点，名字先被用户看见；之后逐条射线、再出现目标节点。
  visibleNodes.value = [nodes[0]]
  await sleep(560)
  for (let index = 0; index < layout.value.edges.length; index += 1) {
    visibleEdges.value = [...visibleEdges.value, layout.value.edges[index]]
    await sleep(250)
    const node = nodes[index + 1]
    if (node) visibleNodes.value = [...visibleNodes.value, node]
    await sleep(140)
  }
  animating.value = false
}

watch(
  () => [props.trace?.traceId, props.trace?.seedNodeId, props.nodes?.length, props.title],
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
    radial-gradient(circle at 50% 45%, rgba(240, 138, 36, .055), transparent 42%),
    #fbfcff;
}
.spna__top { display: flex; align-items: center; justify-content: space-between; padding: 7px 9px 0; }
.spna__status { display: inline-flex; align-items: center; gap: 5px; color: #9aa1af; font-size: 9.5px; }
.spna__pulse { width: 5px; height: 5px; border-radius: 50%; background: #f08a24; box-shadow: 0 0 0 0 rgba(240,138,36,.3); animation: spna-pulse 1.4s ease-out infinite; }
.spna__replay { display: inline-flex; padding: 2px; border: 0; color: #a5adba; background: transparent; cursor: pointer; }
.spna__replay:hover { color: #2f5fce; }
.spna__canvas { display: block; width: 100%; height: 248px; overflow: visible; }
.spna__edge-group { pointer-events: none; }
.spna__ray-glow { stroke: #f08a24; stroke-width: 8; opacity: .08; filter: url(#spna-soft); }
.spna__ray { stroke: url(#spna-ray); stroke-width: 1.35; stroke-dasharray: 4 5; animation: spna-ray-in .5s ease-out both; }
.spna__ray-dot { fill: #f08a24; opacity: .7; }
.spna__node { animation: spna-node-in .34s cubic-bezier(.2,.8,.2,1) both; }
.spna__node-dot { stroke: #fff; stroke-width: 2; }
.spna__node-ring { fill: none; stroke-width: 1; opacity: .28; }
.spna__seed-halo { fill: rgba(240, 138, 36, .1); animation: spna-halo 2.1s ease-in-out infinite; }
.spna__label { fill: #5f6b7d; font-size: 10px; font-weight: 500; paint-order: stroke; stroke: #fbfcff; stroke-width: 3px; stroke-linejoin: round; }
.spna__label.is-seed-label { fill: #253247; font-size: 13px; font-weight: 700; }
.spna__seed-kicker { fill: #b2b8c3; font-size: 8.5px; letter-spacing: .08em; }
.spna__more { padding: 0 10px 3px; color: #a0a8b6; font-size: 9.5px; }
.spna__legend { display: flex; gap: 10px; padding: 0 10px 8px; color: #a0a8b6; font-size: 9px; }
.spna__legend span { display: inline-flex; align-items: center; gap: 4px; }
.spna__legend i { width: 5px; height: 5px; border-radius: 50%; }
.spna__legend .is-topic { background: #f08a24; }
.spna__legend .is-bank { background: #2f9e8f; }
.spna__legend .is-source { background: #3b7cff; }
@keyframes spna-node-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes spna-ray-in { from { opacity: 0; stroke-dashoffset: 32; } to { opacity: 1; stroke-dashoffset: 0; } }
@keyframes spna-pulse { 0% { box-shadow: 0 0 0 0 rgba(240,138,36,.3); } 70% { box-shadow: 0 0 0 6px rgba(240,138,36,0); } 100% { box-shadow: 0 0 0 0 rgba(240,138,36,0); } }
@keyframes spna-halo { 0%, 100% { opacity: .7; transform: scale(.94); } 50% { opacity: 1; transform: scale(1.04); } }
</style>
