<template>
  <section class="kg-page">
    <div class="kg-head">
      <div>
        <div class="kg-kicker">资料知识网络 · 知识图谱</div>
        <h2>实体-关系图</h2>
        <p>实体由资料正文抽取，关系带方向和来源 chunk；点击实体可查看证据并回到原文。</p>
        <div v-if="stats.entityCount" class="kg-stats">
          <b>{{ stats.entityCount }}</b> 个实体
          <span>·</span>
          <b>{{ stats.relationCount }}</b> 条关系
          <span>·</span>
          <b>{{ stats.docCount }}</b> 份资料
        </div>
      </div>
      <div class="kg-head__actions">
        <el-checkbox v-model="hideIsolated" size="small">隐藏孤立实体</el-checkbox>
        <el-button size="small" :loading="loading" @click="reload">刷新</el-button>
        <el-button size="small" class="kg-build-btn" :loading="building" :disabled="!activeKbId" @click="buildGraph">
          抽取当前资料夹
        </el-button>
      </div>
    </div>

    <div class="kg-stage">
      <div ref="chartRef" class="kg-canvas"></div>
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
        <span>滚轮缩放 · 拖拽节点 · 点击实体看证据</span>
      </div>
      <div class="kg-legend">
        <span v-for="item in typeLegend" :key="item.type" class="kg-legend__item">
          <i :style="{ background: item.color }"></i>{{ item.type }}
        </span>
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
          <div class="kg-detail__section-head"><span>来源证据</span><b>{{ detail.chunks?.length || 0 }}</b></div>
          <div v-if="detail.chunks?.length" class="kg-chunks">
            <button v-for="c in detail.chunks" :key="c.chunkId" type="button" class="kg-chunk" @click="locateChunk(c)">
              <b>{{ c.fileName }} · 第 {{ c.chunkIndex + 1 }} 段</b>
              <span>{{ c.excerpt }}</span>
            </button>
          </div>
          <div v-else class="kg-detail__empty">没有可定位的原文证据。</div>
        </section>
      </div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { buildKnowledgeGraph, getKnowledgeGraph, getKnowledgeGraphEntity } from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  searchQuery?: string
  typeFilter?: string[]
}>()

const emit = defineEmits<{
  (e: 'stats', payload: { total: number }): void
  (e: 'locate', payload: { docId: number; chunkId?: number; chunkIndex?: number }): void
  (e: 'back'): void
}>()

const TYPE_META: Array<{ type: string; color: string; bg: string }> = [
  { type: '概念', color: '#4F6BED', bg: '#EEF2FF' },
  { type: '定理/公式', color: '#C47A55', bg: '#FFF4EE' },
  { type: '方法', color: '#2F9E8F', bg: '#EDF9F6' },
  { type: '人物', color: '#8B6BB1', bg: '#F5F0FB' },
  { type: '机构', color: '#B78B2A', bg: '#FFF8E8' },
  { type: '事件', color: '#5C8FA8', bg: '#EFF7FA' },
  { type: '作品', color: '#C05C7E', bg: '#FFF1F5' },
  { type: '其他', color: '#9AA1AF', bg: '#F3F5F9' }
]

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null
const loading = ref(false)
const building = ref(false)
const graph = ref<any>({ nodes: [], edges: [], stats: {} })
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)
const hideIsolated = ref(true)

const allNodes = computed(() => graph.value?.nodes || [])
const allEdges = computed(() => graph.value?.edges || [])
const typeLegend = computed(() =>
  TYPE_META.filter((item) => allNodes.value.some((node: any) => node.type === item.type))
)
const typeCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const node of allNodes.value) counts[node.type] = (counts[node.type] || 0) + 1
  return counts
})
const stats = computed(() => graph.value?.stats || {})

const visibleGraph = computed(() => {
  const selectedTypes = Array.isArray(props.typeFilter) ? props.typeFilter : []
  let nodes = allNodes.value
  if (selectedTypes.length) nodes = nodes.filter((node: any) => selectedTypes.includes(node.type))
  if (hideIsolated.value && allEdges.value.length) nodes = nodes.filter((node: any) => Number(node.degree || 0) > 0)
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

function typeColor(type: string) {
  return TYPE_META.find((item) => item.type === type)?.color || '#9AA1AF'
}
function typeBg(type: string) {
  return TYPE_META.find((item) => item.type === type)?.bg || '#F3F5F9'
}
function typeIndex(type: string) {
  return Math.max(0, TYPE_META.findIndex((item) => item.type === type))
}

function nodesCountForLabels() {
  return visibleGraph.value.nodes.length
}

function buildNode(node: any) {
  const degree = Number(node.degree || 0)
  const size = 13 + Math.min(18, Math.sqrt(degree + 1) * 5)
  return {
    id: String(node.id),
    name: node.name,
    value: Number(node.mentionCount || 1),
    symbolSize: size,
    category: typeIndex(node.type),
    itemStyle: {
      color: typeColor(node.type),
      borderColor: '#ffffff',
      borderWidth: 2,
      shadowColor: `${typeColor(node.type)}33`,
      shadowBlur: 8
    },
    label: {
      // 节点多时只给枢纽实体常驻标签，其余 hover 时显示，避免标签盖住关系线。
      show: nodesCountForLabels() <= 30 || degree >= 2,
      position: 'right',
      distance: 6,
      color: '#4b5563',
      fontSize: 10,
      width: 86,
      overflow: 'truncate',
      formatter: () => node.name
    },
    rawNode: node
  }
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      const node = params?.data?.rawNode
      if (node) openDetail(node.id)
    })
  }
  const { nodes, edges } = visibleGraph.value
  const option = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(23,32,51,.94)',
      borderWidth: 0,
      padding: [9, 12],
      textStyle: { color: '#fff', fontSize: 11 },
      formatter: (params: any) => {
        if (params.dataType === 'edge') {
          const data = params.data || {}
          return `<b>${data.type || '关系'}</b><br/><span style="opacity:.72">强度 ${data.strength || 5}</span>${data.description ? `<br/>${data.description}` : ''}`
        }
        const node = params.data?.rawNode
        return node ? `<b>${node.name}</b><br/><span style="opacity:.72">${node.type} · 出现 ${node.mentionCount} 次</span>${node.description ? `<br/>${node.description}` : ''}` : ''
      }
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      zoom: nodes.length > 60 ? 0.66 : nodes.length > 35 ? 0.78 : 1,
      force: {
        repulsion: Math.max(180, 360 - nodes.length * 2),
        edgeLength: [55, 150],
        gravity: 0.1,
        friction: 0.8,
        layoutAnimation: true
      },
      labelLayout: { hideOverlap: true },
      categories: TYPE_META.map((item) => ({ name: item.type })),
      data: nodes.map(buildNode),
      edges: edges.map((edge: any) => ({
        source: String(edge.source),
        target: String(edge.target),
        value: Number(edge.strength || 5),
        type: edge.type,
        strength: edge.strength,
        description: edge.description,
        lineStyle: {
          color: '#c7d0e0',
          width: 0.8 + Number(edge.strength || 5) / 10,
          opacity: 0.72,
          curveness: 0.1
        },
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 5
      })),
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 2, opacity: 1 },
        label: { show: true, color: '#172033', fontWeight: 600 }
      }
    }]
  }
  chart.setOption(option, { notMerge: true })
  chart.resize()
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
    render()
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
    if (failed) {
      ElMessage.warning(`完成 ${data.processedDocs || 0} 份资料，${failed} 份抽取失败`)
    } else {
      ElMessage.success(`已抽取 ${data.entities || 0} 个实体、${data.relations || 0} 条关系`)
    }
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
  if (allNodes.value.some((item: any) => String(item.id) === String(entityId))) {
    openDetail(String(entityId))
  }
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
  () => render(),
  { deep: true }
)
watch(hideIsolated, () => render())

onMounted(async () => {
  await reload()
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.kg-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 2px 2px 10px;
}

.kg-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 2px 2px 10px;
  border-bottom: 1px solid #edf0f5;
}

.kg-kicker {
  color: #4f6bed;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.kg-head h2 {
  margin: 5px 0 4px;
  color: #1f2937;
  font-size: 22px;
  font-weight: 700;
}

.kg-head p {
  margin: 0;
  color: #8a91a0;
  font-size: 11px;
}

.kg-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 7px;
  color: #9aa1af;
  font-size: 10px;
}

.kg-stats b {
  color: #4f6bed;
  font-weight: 600;
}

.kg-head__actions {
  display: flex;
  flex: none;
  gap: 8px;
}

.kg-build-btn {
  border-color: rgba(79, 107, 237, 0.25);
  color: #4f6bed;
  background: #f7f9ff;
}

.kg-stage {
  position: relative;
  min-height: 620px;
  overflow: hidden;
  border: 1px solid #e9ecf2;
  border-radius: 13px;
  background:
    radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.11) 1px, transparent 0),
    #fbfcfe;
  background-size: 20px 20px;
}

.kg-canvas {
  width: 100%;
  height: 660px;
}

.kg-search-hint {
  position: absolute;
  bottom: 13px;
  left: 14px;
  display: flex;
  gap: 12px;
  padding: 5px 9px;
  border: 1px solid rgba(15, 23, 42, 0.05);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.82);
  color: #9aa1af;
  font-size: 9.5px;
  pointer-events: none;
}

.kg-search-hint span + span::before {
  margin-right: 12px;
  color: #d1d5db;
  content: '·';
}

.kg-legend {
  position: absolute;
  top: 12px;
  left: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 7px 11px;
  max-width: 700px;
  padding: 6px 9px;
  border: 1px solid rgba(15, 23, 42, 0.05);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.86);
  pointer-events: none;
}

.kg-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #7d8596;
  font-size: 9.5px;
}

.kg-legend__item i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.kg-empty,
.kg-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(251, 252, 254, 0.94);
  text-align: center;
}

.kg-empty__art {
  display: flex;
  width: 54px;
  height: 54px;
  align-items: center;
  justify-content: center;
  margin-bottom: 9px;
  border-radius: 16px;
  color: #4f6bed;
  background: #eef2ff;
  font-size: 27px;
}

.kg-empty h3 {
  margin: 0 0 5px;
  color: #374151;
  font-size: 16px;
}

.kg-empty p {
  max-width: 380px;
  margin: 0 0 14px;
  color: #9aa1af;
  font-size: 11px;
  line-height: 1.7;
}

.kg-detail-drawer :deep(.el-drawer__body) {
  padding: 20px;
}

.kg-detail {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.kg-detail__eyebrow {
  color: #4f6bed;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.kg-detail h3 {
  margin: -8px 0 0;
  color: #1f2937;
  font-size: 20px;
  line-height: 1.4;
}

.kg-detail__meta {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #9aa1af;
  font-size: 10px;
}

.kg-type {
  padding: 3px 7px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 600;
}

.kg-detail__desc {
  margin: 0;
  color: #596173;
  font-size: 12px;
  line-height: 1.75;
}

.kg-detail__section {
  padding-top: 12px;
  border-top: 1px solid #eef0f5;
}

.kg-detail__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #6b7280;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.kg-detail__section-head b {
  color: #4f6bed;
  font-weight: 600;
}

.kg-neighbors,
.kg-chunks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kg-neighbor,
.kg-chunk {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  padding: 8px 9px;
  border: 1px solid #eef0f5;
  border-radius: 8px;
  background: #fbfcfe;
  color: #596173;
  cursor: pointer;
  font-size: 10.5px;
  text-align: left;
}

.kg-neighbor:hover,
.kg-chunk:hover {
  border-color: #d9e1f4;
  background: #f5f7fc;
}

.kg-neighbor__type {
  flex: none;
  font-size: 9px;
}

.kg-neighbor b {
  overflow: hidden;
  flex: 1;
  color: #374151;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kg-neighbor__rel {
  flex: none;
  color: #9aa1af;
  font-size: 9.5px;
}

.kg-chunk {
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
}

.kg-chunk b {
  overflow: hidden;
  color: #4b5563;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kg-chunk span {
  overflow: hidden;
  color: #9aa1af;
  font-size: 10px;
  line-height: 1.55;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kg-detail__empty {
  padding: 12px 0;
  color: #a0a6b2;
  font-size: 10.5px;
}

.kg-detail-loading {
  height: 500px;
}

@media (max-width: 900px) {
  .kg-stage,
  .kg-canvas {
    min-height: 480px;
    height: 480px;
  }

  .kg-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}
</style>
