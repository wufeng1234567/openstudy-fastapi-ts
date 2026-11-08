<template>
  <section class="smg">
    <div class="smg__canvas">
      <svg v-if="layoutNodes.length" class="smg__svg" viewBox="0 0 980 560" role="img"
        aria-label="学习图谱：知识页与题库">
        <defs>
          <marker id="smg-arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="7" markerHeight="6" orient="auto">
            <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#aeb9cb" />
          </marker>
          <marker id="smg-arrow-active" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="7" markerHeight="6" orient="auto">
            <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#5b8def" />
          </marker>
        </defs>
        <g>
          <line
            v-for="edge in edgeLines"
            :key="edge.key"
            :x1="edge.x1"
            :y1="edge.y1"
            :x2="edge.x2"
            :y2="edge.y2"
            class="smg__edge"
            :class="[`is-${edge.type}`, { 'is-active': edge.active, 'is-dimmed': edge.dimmed }]"
            :marker-end="edge.type === 'prerequisite' ? `url(#${edge.active ? 'smg-arrow-active' : 'smg-arrow'})` : undefined"
          />
          <g
            v-for="node in layoutNodes"
            :key="node.id"
            class="smg__node"
            :class="[`is-${node.kind}`, { 'is-hovered': hoveredId === node.id, 'is-dimmed': isNodeDimmed(node.id) }]"
            :transform="node.kind === 'page' ? `translate(${node.x} ${node.y})` : undefined"
            @mouseenter="hoveredId = node.id"
            @mouseleave="hoveredId = null"
            @click.stop="emit('select', node.raw)"
          >
            <title>{{ node.raw.title }}{{ node.kind === 'page' ? ` · ${learningLabel(node.raw.learning)}` : ` · ${node.raw.questionCount || 0} 题` }}</title>
            <template v-if="node.kind === 'page'">
              <circle class="smg__page-halo" :r="node.r + 8" />
              <circle class="smg__page-dot" :r="node.r" :fill="pageColor(node.raw)" />
              <circle v-if="routeOrder.has(Number(node.raw.pageId))" class="smg__route-ring" :r="node.r + 5" />
              <text class="smg__route-num" :x="node.r + 7" :y="-node.r - 1">{{ routeOrder.get(Number(node.raw.pageId)) }}</text>
              <text class="smg__label" text-anchor="middle" :y="node.r + 15">{{ shortLabel(node.raw.title) }}</text>
            </template>
            <template v-else>
              <rect class="smg__bank-shadow" :x="node.x - node.w / 2 + 2" :y="node.y - node.h / 2 + 3" :width="node.w" :height="node.h" rx="10" />
              <rect class="smg__bank-rect" :class="{ 'is-linked': Number(node.raw.mappedQuestionCount || 0) > 0 }"
                :x="node.x - node.w / 2" :y="node.y - node.h / 2" :width="node.w" :height="node.h" rx="10" />
              <text class="smg__bank-title" text-anchor="middle" :x="node.x" :y="node.y - 5">{{ shortLabel(node.raw.title, 12) }}</text>
              <text class="smg__bank-meta" text-anchor="middle" :x="node.x" :y="node.y + 14">
                {{ node.raw.questionCount || 0 }} 题 · 薄弱 {{ node.raw.weakCount || 0 }}
              </text>
              <circle v-if="routeOrder.has(-Number(node.raw.bankId))" class="smg__route-ring is-bank" :r="12" :cx="node.x + node.w / 2 - 4" :cy="node.y - node.h / 2 + 1" />
            </template>
          </g>
        </g>
      </svg>
      <div v-else class="smg__empty">
        <b>还没有可画的学习地图</b>
        <span>先上传资料生成知识百科，或在题库里做几道题，地图会按真实节点长出来。</span>
      </div>
    </div>
    <footer class="smg__legend">
      <span><i class="is-unread"></i>未学习</span>
      <span><i class="is-reading"></i>已阅读</span>
      <span><i class="is-practicing"></i>练习中</span>
      <span><i class="is-mastered"></i>已掌握</span>
      <span><i class="is-bank"></i>题库</span>
      <em>实线=知识页关系 · 虚线=真实题源锚点</em>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface GraphNode {
  id: string
  kind: 'page' | 'bank'
  pageId?: number
  bankId?: number
  title?: string
  pageType?: string
  degree?: number
  learning?: any
  questionCount?: number
  weakCount?: number
  mappedQuestionCount?: number
  pageIds?: number[]
  [key: string]: any
}

const props = defineProps<{
  nodes?: GraphNode[]
  edges?: any[]
  routePageIds?: number[]
  selectedId?: string
}>()

const emit = defineEmits<{
  (e: 'select', node: GraphNode): void
}>()

const hoveredId = ref<string | null>(null)
const WIDTH = 980
const HEIGHT = 560

const pageNodes = computed(() => (props.nodes || []).filter((node) => node.kind === 'page'))
const bankNodes = computed(() => (props.nodes || []).filter((node) => node.kind === 'bank'))

const routeOrder = computed(() => {
  const map = new Map<number, number>()
  ;(props.routePageIds || []).forEach((pageId, index) => map.set(Number(pageId), index + 1))
  return map
})

function pageLayout(index: number, total: number) {
  if (total <= 1) return { x: 350, y: 245, r: 26 }
  const rings = total <= 8 ? [8] : total <= 16 ? [8, 14] : [8, 14, 20]
  let ringIndex = 0
  let remain = index
  while (ringIndex < rings.length - 1 && remain >= rings[ringIndex]) {
    remain -= rings[ringIndex]
    ringIndex += 1
  }
  const count = rings[ringIndex]
  const radius = 125 + ringIndex * 82
  const angle = -Math.PI / 2 + (Math.PI * 2 * remain) / Math.max(count, 1)
  const node = pageNodes.value[index]
  const r = 13 + Math.min(9, Math.sqrt(Number(node?.degree || 0) + 1) * 2.4)
  return {
    x: 350 + Math.cos(angle) * radius,
    y: 235 + Math.sin(angle) * radius * 0.82,
    r
  }
}

const layoutNodes = computed(() => {
  const pages = pageNodes.value.map((node, index) => {
    const pos = pageLayout(index, pageNodes.value.length)
    return { ...pos, kind: 'page' as const, id: node.id, raw: node, w: 0, h: 0 }
  })
  const banks = bankNodes.value.map((node, index) => {
    const cols = Math.min(4, Math.max(1, bankNodes.value.length))
    const row = Math.floor(index / cols)
    const col = index % cols
    const totalRows = Math.ceil(bankNodes.value.length / cols)
    const rowCount = Math.min(cols, bankNodes.value.length - row * cols)
    const gap = 14
    const w = 150
    const startX = (WIDTH - (rowCount * w + (rowCount - 1) * gap)) / 2 + w / 2
    const baseY = pageNodes.value.length ? 430 : 235
    return {
      x: startX + col * (w + gap),
      y: baseY + (row - (totalRows - 1) / 2) * 66,
      r: 0,
      w,
      h: 50,
      kind: 'bank' as const,
      id: node.id,
      raw: node
    }
  })
  return [...pages, ...banks]
})

const positionById = computed(() => {
  const map = new Map<string, any>()
  for (const node of layoutNodes.value) map.set(String(node.id), node)
  return map
})

const neighborIds = computed(() => {
  const id = hoveredId.value
  const set = new Set<string>()
  if (!id) return set
  set.add(id)
  for (const edge of props.edges || []) {
    if (String(edge.source) === id) set.add(String(edge.target))
    if (String(edge.target) === id) set.add(String(edge.source))
  }
  return set
})

const edgeLines = computed(() => {
  return (props.edges || [])
    .map((edge, index) => {
      const source = positionById.value.get(String(edge.source))
      const target = positionById.value.get(String(edge.target))
      if (!source || !target) return null
      const active = hoveredId.value === String(edge.source) || hoveredId.value === String(edge.target)
      const dimmed = !!hoveredId.value && !active
      return {
        key: `${edge.source}-${edge.target}-${index}`,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        type: String(edge.type || 'related'),
        active,
        dimmed
      }
    })
    .filter(Boolean) as any[]
})

function isNodeDimmed(id: string) {
  return !!hoveredId.value && !neighborIds.value.has(id)
}

function pageColor(node: GraphNode) {
  const level = String(node.learning?.level || 'unread')
  if (level === 'mastered') return '#2f9e8f'
  if (level === 'practicing') return '#e6a23c'
  if (level === 'reading') return '#5b8def'
  return '#9aa7ba'
}

function learningLabel(learning: any) {
  return String(learning?.label || '未学习')
}

function shortLabel(title: any, limit = 10) {
  const text = String(title || '未命名')
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text
}
</script>

<style scoped>
.smg { min-width: 0; }
.smg__canvas {
  position: relative;
  overflow: hidden;
  min-height: 360px;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  background:
    radial-gradient(circle at 1px 1px, rgba(145, 160, 184, 0.16) 1px, transparent 0) 0 0 / 18px 18px,
    #fbfcff;
}
.smg__svg { display: block; width: 100%; height: 360px; }
.smg__edge { stroke: #d7dfeb; stroke-width: 1.2; transition: opacity .15s ease, stroke .15s ease; }
.smg__edge.is-prerequisite { stroke: #a9c1e8; stroke-dasharray: 4 4; }
.smg__edge.is-question_source { stroke: #c7b9ee; stroke-dasharray: 3 3; }
.smg__edge.is-active { stroke: #5b8def; stroke-width: 2; }
.smg__edge.is-dimmed { opacity: .16; }
.smg__node { cursor: pointer; }
.smg__node.is-dimmed { opacity: .28; }
.smg__page-halo { fill: rgba(47, 95, 206, 0.06); }
.smg__page-dot { stroke: #fff; stroke-width: 2; filter: drop-shadow(0 2px 3px rgba(38, 56, 84, .14)); transition: transform .15s ease; }
.smg__node.is-hovered .smg__page-dot { transform: scale(1.1); }
.smg__route-ring { fill: none; stroke: #2f5fce; stroke-width: 1.5; stroke-dasharray: 3 3; }
.smg__route-ring.is-bank { stroke: #7c6cf2; }
.smg__route-num {
  fill: #2f5fce;
  font-size: 10px;
  font-weight: 700;
  text-anchor: middle;
}
.smg__label {
  fill: #5f6b7d;
  font-size: 10px;
  font-weight: 600;
  pointer-events: none;
}
.smg__bank-shadow { fill: rgba(71, 55, 139, 0.08); }
.smg__bank-rect { fill: #f6f3ff; stroke: #d7cff6; stroke-width: 1.2; }
.smg__bank-rect.is-linked { fill: #f1edff; stroke: #b9a9ef; }
.smg__bank-title { fill: #51428e; font-size: 10px; font-weight: 700; pointer-events: none; }
.smg__bank-meta { fill: #8d84ad; font-size: 9px; pointer-events: none; }
.smg__empty {
  display: flex;
  min-height: 360px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  color: #9aa3b2;
  text-align: center;
}
.smg__empty b { color: #5f6b7d; font-size: 13px; }
.smg__empty span { max-width: 360px; font-size: 11px; line-height: 1.6; }
.smg__legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 8px 2px 0;
  color: #8a91a0;
  font-size: 10px;
}
.smg__legend span { display: inline-flex; align-items: center; gap: 4px; }
.smg__legend i { width: 8px; height: 8px; border-radius: 50%; }
.smg__legend i.is-unread { background: #9aa7ba; }
.smg__legend i.is-reading { background: #5b8def; }
.smg__legend i.is-practicing { background: #e6a23c; }
.smg__legend i.is-mastered { background: #2f9e8f; }
.smg__legend i.is-bank { border-radius: 3px; background: #7c6cf2; }
.smg__legend em { margin-left: auto; color: #a6adba; font-style: normal; }
@media (max-width: 760px) {
  .smg__svg { height: 300px; }
  .smg__canvas { min-height: 300px; }
  .smg__legend em { width: 100%; margin-left: 0; }
}
</style>
