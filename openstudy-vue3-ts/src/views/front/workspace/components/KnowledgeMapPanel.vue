<template>
  <section class="map-page">
    <header class="map-hero">
      <div class="map-hero__copy">
        <div class="map-kicker"><span></span>资料知识网络 · 0.4.1</div>
        <h2>资料知识地图</h2>
        <p>
          资料页、章节页、笔记、题组和图组，按真实引用关系连起来。每个节点都能回到原文，
          每条连线都能说明为什么存在。
        </p>
      </div>
      <div class="map-hero__stats">
        <div><span>资料页</span><b>{{ scopeStats.documentCount }}</b></div>
        <div><span>章节页</span><b>{{ scopeStats.sectionCount }}</b></div>
        <div><span>引用关系</span><b>{{ scopeStats.referenceCount }}</b></div>
        <div><span>笔记</span><b>{{ scopeStats.noteCount }}</b></div>
      </div>
    </header>

    <div class="map-layout">
      <aside class="map-rail">
        <div class="map-rail__block">
          <div class="map-rail__label">按资料夹聚焦</div>
          <button
            type="button"
            class="map-group-item"
            :class="{ 'is-active': !activeGroup }"
            @click="focusGroup('')"
          >
            <span class="map-group-item__dot is-all"></span>
            <span class="map-group-item__name">全图</span>
            <span class="map-group-item__count">{{ rootNodeCount }}</span>
          </button>
          <button
            v-for="group in groups"
            :key="group.id"
            type="button"
            class="map-group-item"
            :class="{ 'is-active': activeGroup === group.id }"
            @click="focusGroup(group.id)"
          >
            <span class="map-group-item__dot" :style="{ background: group.color }"></span>
            <span class="map-group-item__name" :title="group.name">{{ group.name }}</span>
            <span class="map-group-item__count">{{ group.docCount }}</span>
          </button>
        </div>

        <div class="map-rail__block">
          <div class="map-rail__label">显示内容</div>
          <label v-for="item in typeFilters" :key="item.type" class="map-type-row">
            <input v-model="activeTypes" type="checkbox" :value="item.type" />
            <span class="map-type-row__mark" :class="`is-${item.type}`"></span>
            <span>{{ item.label }}</span>
            <em>{{ typeCount(item.type) }}</em>
          </label>
          <label class="map-switch-row">
            <span>只看有连接的页面</span>
            <input v-model="hideIsolated" type="checkbox" />
          </label>
        </div>

        <div class="map-rail__block map-rail__legend">
          <div class="map-rail__label">怎么看这张图</div>
          <div class="map-legend"><i class="is-doc"></i><span>资料页：颜色代表资料夹</span></div>
          <div class="map-legend"><i class="is-section"></i><span>章节页：原文标题切出的章节</span></div>
          <div class="map-legend"><i class="is-reference"></i><span>虚线：真实的引用关系</span></div>
          <div class="map-legend"><i class="is-source"></i><span>细线：题目 / 图片归属</span></div>
        </div>
      </aside>

      <main class="map-stage">
        <div class="map-toolbar">
          <el-input
            v-model="keyword"
            class="map-search"
            clearable
            placeholder="搜索页面标题或正文…"
            :prefix-icon="Search"
          />
          <button type="button" class="map-tool-btn" :class="{ 'is-on': hideIsolated }" @click="hideIsolated = !hideIsolated">
            隐藏孤立页
          </button>
          <button type="button" class="map-tool-btn" :disabled="!activeDocId" @click="clearFocus">
            返回全图 <kbd>Esc</kbd>
          </button>
          <span class="map-toolbar__spacer"></span>
          <span class="map-toolbar__hint">
            {{ activeDocId ? '正在聚焦一份资料：章节已展开' : '点击资料页展开章节，点击空白处取消' }}
          </span>
        </div>

        <div ref="chartRef" class="map-canvas" @click="onCanvasClick"></div>
        <div v-if="!loading && !visibleNodes.length" class="map-empty">
          <div class="map-empty__art"><el-icon><Share /></el-icon></div>
          <h3>还没有可展示的知识页面</h3>
          <p>先上传一份带章节的资料，或给图片补几条描述。地图不会用假节点凑数。</p>
          <el-button plain @click="emit('back')">去上传资料</el-button>
        </div>
        <div v-if="loading" class="map-loading" v-loading="true"></div>

        <div class="map-canvas__legend">
          <span><i class="is-doc"></i>资料</span>
          <span><i class="is-section"></i>章节</span>
          <span><i class="is-note"></i>笔记</span>
          <span><i class="is-question"></i>题组</span>
          <span><i class="is-image"></i>图组</span>
        </div>
      </main>

      <aside class="map-detail">
        <template v-if="selectedNode">
          <div class="map-detail__eyebrow">{{ typeLabel(selectedNode.type).toUpperCase() }}</div>
          <h3>{{ selectedNode.meta?.title || selectedNode.label }}</h3>
          <p v-if="selectedNode.meta?.summary" class="map-detail__summary">{{ selectedNode.meta.summary }}</p>
          <div v-if="selectedNode.type === 'section' && selectedNode.meta?.excerpt" class="map-detail__excerpt">
            {{ selectedNode.meta.excerpt }}
          </div>

          <div class="map-detail__metrics">
            <template v-if="selectedNode.type === 'document'">
              <div><span>章节</span><b>{{ selectedNode.meta?.sectionCount || 0 }}</b></div>
              <div><span>题目</span><b>{{ selectedNode.meta?.questionCount || 0 }}</b></div>
              <div><span>图片</span><b>{{ selectedNode.meta?.imageCount || 0 }}</b></div>
              <div><span>版本</span><b>v{{ selectedNode.meta?.version || 1 }}</b></div>
            </template>
            <template v-else-if="selectedNode.type === 'section'">
              <div><span>正文</span><b>{{ selectedNode.meta?.chars || 0 }} 字</b></div>
              <div><span>练习</span><b>{{ selectedNode.meta?.hasPractice ? '有' : '未识别' }}</b></div>
            </template>
            <template v-else>
              <div><span>数量</span><b>{{ selectedNode.meta?.count || selectedNode.value || 0 }}</b></div>
              <div v-if="selectedNode.docId"><span>来源</span><b>#{{ selectedNode.docId }}</b></div>
            </template>
          </div>

          <div class="map-detail__actions">
            <el-button
              v-if="selectedNode.type === 'document'"
              type="primary"
              plain
              @click="openDocument(selectedNode)"
            >
              查看资料
            </el-button>
            <el-button
              v-if="selectedNode.type === 'section' || selectedNode.type === 'note'"
              plain
              @click="locateNode(selectedNode)"
            >
              定位原文
            </el-button>
            <el-button
              v-if="selectedNode.type === 'document'"
              text
              @click="focusDocument(selectedNode)"
            >
              {{ activeDocId === selectedNode.docId ? '取消聚焦' : '展开章节' }}
            </el-button>
          </div>
          <div v-if="selectedNode.type === 'document'" class="map-detail__hint">
            章节页会围绕这份资料展开；点击空白处或按 Esc 返回全图。
          </div>
        </template>
        <template v-else>
          <div class="map-detail__placeholder">
            <div class="map-detail__placeholder-art"><el-icon><Aim /></el-icon></div>
            <h3>点一个页面看看</h3>
            <p>右侧会显示它的摘要、章节和来源。资料页可以展开章节，再跳回原文。</p>
          </div>
        </template>

        <div v-if="groups.length" class="map-detail__groups">
          <div class="map-detail__groups-title">分组主题</div>
          <div v-for="group in groups" :key="group.id" class="map-detail__group">
            <i :style="{ background: group.color }"></i>
            <div>
              <b>{{ group.name }}</b>
              <span>{{ group.description }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { Aim, Search, Share } from '@element-plus/icons-vue'
import { getKnowledgeMap } from '@/api/ai/workspace'

const props = defineProps<{ activeKbId?: number | null }>()
const emit = defineEmits<{
  (e: 'open-doc', payload: { docId: number; offset?: number; targetText?: string }): void
  (e: 'back'): void
}>()

type MapNode = {
  id: string
  type: string
  label: string
  groupId: string
  docId?: number | null
  noteId?: number | null
  value?: number
  meta?: Record<string, any>
  searchText?: string
  x?: number
  y?: number
  shortLabel?: string
}

const chartRef = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null
const loading = ref(false)
const nodes = ref<MapNode[]>([])
const edges = ref<any[]>([])
const groups = ref<any[]>([])
const stats = reactive({ documentCount: 0, sectionCount: 0, noteCount: 0, referenceCount: 0, questionCount: 0, imageCount: 0 })
const activeGroup = ref('')
const activeDocId = ref<number | null>(null)
const activeTypes = ref<string[]>(['document', 'section', 'note', 'question', 'image'])
const hideIsolated = ref(false)
const keyword = ref('')
const selectedNode = ref<MapNode | null>(null)
const groupInitialized = ref(false)

const typeFilters = [
  { type: 'document', label: '资料页' },
  { type: 'section', label: '章节页' },
  { type: 'note', label: '笔记' },
  { type: 'question', label: '题组' },
  { type: 'image', label: '图组' }
]

const typeCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const node of nodes.value) counts[node.type] = (counts[node.type] || 0) + 1
  return counts
})

const rootNodeCount = computed(() => nodes.value.filter((node) => node.type !== 'section').length)

/** 顶部数字跟随当前分组，避免“地图里 11 个点、标题写 38 份资料”的对不上。 */
const scopeStats = computed(() => {
  const inScope = activeGroup.value
    ? nodes.value.filter((node) => node.groupId === activeGroup.value)
    : nodes.value
  const ids = new Set(inScope.map((node) => node.id))
  const referenceCount = edges.value.filter(
    (edge) => edge.type === 'reference' && ids.has(edge.source) && ids.has(edge.target)
  ).length
  return {
    documentCount: inScope.filter((node) => node.type === 'document').length,
    sectionCount: inScope.filter((node) => node.type === 'section').length,
    noteCount: inScope.filter((node) => node.type === 'note').length,
    referenceCount
  }
})

function typeCount(type: string) {
  return typeCounts.value[type] || 0
}

function typeLabel(type: string) {
  return typeFilters.find((item) => item.type === type)?.label || '页面'
}

function focusGroup(groupId: string) {
  activeGroup.value = groupId
  activeDocId.value = null
  selectedNode.value = null
  render()
}

function clearFocus() {
  activeDocId.value = null
  selectedNode.value = null
  render()
}

function focusDocument(node: MapNode) {
  if (!node.docId) return
  activeDocId.value = activeDocId.value === Number(node.docId) ? null : Number(node.docId)
  selectedNode.value = activeDocId.value ? node : null
  render()
}

function selectNode(node: MapNode) {
  selectedNode.value = node
  render()
}

function openDocument(node: MapNode) {
  if (node.docId) emit('open-doc', { docId: Number(node.docId) })
}

function locateNode(node: MapNode) {
  if (node.docId && node.meta?.start != null) {
    emit('open-doc', {
      docId: Number(node.docId),
      offset: Number(node.meta.start || 0),
      targetText: String(node.meta.title || node.label || '')
    })
  } else if (node.docId) {
    emit('open-doc', { docId: Number(node.docId), targetText: String(node.meta?.title || node.label || '') })
  }
}

function onCanvasClick(event: MouseEvent) {
  // 点中节点由 ECharts click 事件处理；只有点在空白画布上才清空选择。
  const target = event.target as HTMLElement
  if (target?.tagName === 'CANVAS') {
    const instance = chart
    if (!instance) return
    const point = [event.offsetX, event.offsetY]
    const found = instance.containPixel({ seriesIndex: 1 }, point)
    if (!found) {
      selectedNode.value = null
      if (activeDocId.value) {
        activeDocId.value = null
        render()
      }
    }
  }
}

function applyData(data: any) {
  nodes.value = (data?.nodes || []).map((node: MapNode) => ({ ...node }))
  edges.value = data?.edges || []
  groups.value = data?.groups || []
  const s = data?.stats || {}
  stats.documentCount = Number(s.documentCount || 0)
  stats.sectionCount = Number(s.sectionCount || 0)
  stats.noteCount = Number(s.noteCount || 0)
  stats.referenceCount = Number(s.referenceCount || 0)
  stats.questionCount = Number(s.questionCount || 0)
  stats.imageCount = Number(s.imageCount || 0)
}

async function reload() {
  loading.value = true
  try {
    // 地图始终加载全部资料，左侧分组列表才有意义；当前资料夹只作为初始聚焦范围。
    const res = await getKnowledgeMap()
    if (res.code === 200) {
      applyData(res.data)
      if (!groupInitialized.value) {
        const target = props.activeKbId ? `kb:${props.activeKbId}` : ''
        activeGroup.value = groups.value.some((group) => group.id === target) ? target : ''
        groupInitialized.value = true
      }
    }
  } finally {
    loading.value = false
    await nextTick()
    render()
  }
}

/** 只保留当前视图需要的节点：默认不铺满章节，聚焦资料时才展开它的章节。 */
const visibleNodes = computed(() => {
  let result = nodes.value.filter((node) => {
    if (node.type === 'section') return activeDocId.value === Number(node.docId)
    return true
  })
  if (activeGroup.value) result = result.filter((node) => node.groupId === activeGroup.value)
  if (activeDocId.value) {
    const docId = Number(activeDocId.value)
    const relatedIds = new Set<string>()
    relatedIds.add(`doc:${docId}`)
    for (const edge of edges.value) {
      if (edge.source === `doc:${docId}`) relatedIds.add(edge.target)
      if (edge.target === `doc:${docId}`) relatedIds.add(edge.source)
    }
    result = result.filter((node) => relatedIds.has(node.id) || (node.type === 'section' && Number(node.docId) === docId))
  }
  const typeSet = new Set(activeTypes.value)
  result = result.filter((node) => typeSet.has(node.type))
  const q = keyword.value.trim().toLowerCase()
  if (q) {
    const matched = new Set(
      result.filter((node) => `${node.label} ${node.searchText || ''}`.toLowerCase().includes(q)).map((node) => node.id)
    )
    // 搜索命中后把直接相邻的页面也带出来，否则用户只看到孤立节点。
    for (const edge of edges.value) {
      if (matched.has(edge.source)) matched.add(edge.target)
      if (matched.has(edge.target)) matched.add(edge.source)
    }
    result = result.filter((node) => matched.has(node.id))
  }
  if (hideIsolated.value) {
    const withEdge = new Set<string>()
    for (const edge of edges.value) {
      withEdge.add(edge.source)
      withEdge.add(edge.target)
    }
    result = result.filter((node) => withEdge.has(node.id))
  }
  return result
})

function layoutNodes(list: MapNode[]) {
  const byId = new Map(list.map((node) => [node.id, node]))
  const docs = list.filter((node) => node.type === 'document')
  // 分组中心：一个组时放在画布中央；多个组用网格，避免互相挤压。
  const activeGroups = activeGroup.value
    ? groups.value.filter((g) => g.id === activeGroup.value)
    : groups.value.length
      ? groups.value
      : [{ id: 'all', color: '#4F6BED', name: '资料' }]
  const width = Math.max(620, chartRef.value?.clientWidth || 900)
  const height = Math.max(470, chartRef.value?.clientHeight || 570)
  const cols = Math.max(1, Math.ceil(Math.sqrt(activeGroups.length)))
  const rows = Math.max(1, Math.ceil(activeGroups.length / cols))
  const centers = new Map<string, { x: number; y: number; r: number }>()
  activeGroups.forEach((group: any, index: number) => {
    const col = index % cols
    const row = Math.floor(index / cols)
    const cellW = width / cols
    const cellH = height / rows
    centers.set(group.id, {
      x: cellW * (col + 0.5),
      y: cellH * (row + 0.5),
      r: Math.min(cellW, cellH) * 0.34
    })
  })

  for (const node of list) {
    if (node.type === 'document') {
      const groupDocs = docs.filter((doc) => doc.groupId === node.groupId)
      const index = groupDocs.findIndex((doc) => doc.id === node.id)
      const center = centers.get(node.groupId) || { x: width / 2, y: height / 2, r: 300 }
      const total = Math.max(groupDocs.length, 1)
      const golden = Math.PI * (3 - Math.sqrt(5))
      const radial = total === 1 ? 0 : center.r * Math.sqrt((index + 0.5) / total)
      const angle = index * golden
      node.x = center.x + Math.cos(angle) * radial * 1.18
      node.y = center.y + Math.sin(angle) * radial * 0.82
    }
  }

  // 题组 / 图组 / 笔记围绕各自的资料页；没有 docId 的笔记靠近其分组中心。
  const childrenByDoc = new Map<number, MapNode[]>()
  for (const node of list) {
    if (node.type === 'document') continue
    if (node.docId && ['question', 'image', 'note', 'section'].includes(node.type)) {
      if (!childrenByDoc.has(Number(node.docId))) childrenByDoc.set(Number(node.docId), [])
      childrenByDoc.get(Number(node.docId))!.push(node)
    }
  }
  for (const [docId, children] of childrenByDoc) {
    const doc = byId.get(`doc:${docId}`)
    if (!doc || doc.x == null || doc.y == null) continue
    const isFocused = activeDocId.value === Number(docId)
    const radius = isFocused && children.some((c) => c.type === 'section') ? 128 : 72
    const count = Math.max(children.length, 1)
    children.forEach((child, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / count + (isFocused ? Math.PI / 12 : 0)
      const ring = child.type === 'note' ? radius + 34 : radius
      child.x = doc.x! + Math.cos(angle) * ring
      child.y = doc.y! + Math.sin(angle) * ring * 0.8
    })
  }
  for (const node of list) {
    if (node.x != null) continue
    const center = centers.get(node.groupId) || { x: width / 2, y: height / 2, r: 320 }
    node.x = center.x + (Math.random() - 0.5) * center.r * 0.8
    node.y = center.y + (Math.random() - 0.5) * center.r * 0.8
  }
  return list
}

const nodeStyles: Record<string, { color: string; size: number; symbol: string; border: string }> = {
  document: { color: '#4F6BED', size: 34, symbol: 'circle', border: '#ffffff' },
  section: { color: '#8EA2D9', size: 12, symbol: 'circle', border: '#ffffff' },
  note: { color: '#8B6BB1', size: 18, symbol: 'roundRect', border: '#ffffff' },
  question: { color: '#C99A3D', size: 18, symbol: 'diamond', border: '#ffffff' },
  image: { color: '#2F9E8F', size: 16, symbol: 'rect', border: '#ffffff' }
}

function shortLabel(label: string, max = 13) {
  return label.length > max ? `${label.slice(0, max)}…` : label
}

function render() {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params: any) => {
      const node = params?.data?.rawNode as MapNode | undefined
      if (!node) return
      selectedNode.value = node
      // 点资料页就直接展开章节，让“点一下”与右侧提示一致；再点一次收回。
      if (node.type === 'document' && node.docId) {
        activeDocId.value = Number(node.docId)
      }
      render()
    })
  }
  const list = layoutNodes(visibleNodes.value.map((node) => ({ ...node })))
  const ids = new Set(list.map((node) => node.id))
  const visibleEdges = edges.value.filter((edge) => ids.has(edge.source) && ids.has(edge.target))
  const groupColor = new Map(groups.value.map((group) => [group.id, group.color]))
  const docLabelCounts = new Map<string, number>()
  for (const node of list.filter((item) => item.type === 'document')) {
    const base = (node.label || '').replace(/\.[^.]+$/, '')
    docLabelCounts.set(base, (docLabelCounts.get(base) || 0) + 1)
  }
  const edgeColors: Record<string, string> = {
    hierarchy: '#c9d2e8',
    reference: '#8b6bb1',
    question_source: '#e0c27a',
    image_source: '#92cfc7'
  }
  const chartWidth = Math.max(620, chartRef.value?.clientWidth || 900)
  const chartHeight = Math.max(470, chartRef.value?.clientHeight || 570)
  const posById = new Map(list.map((node) => [node.id, node]))
  const option = {
    backgroundColor: 'transparent',
    animationDuration: 420,
    animationEasingUpdate: 'quinticInOut',
    grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: false },
    xAxis: { type: 'value', min: 0, max: chartWidth, show: false },
    yAxis: { type: 'value', min: 0, max: chartHeight, inverse: true, show: false },
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(23, 32, 51, 0.92)',
      borderWidth: 0,
      padding: [9, 12],
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: any) => {
        const node = params.data?.rawNode as MapNode
        if (!node) return ''
        return `<b>${node.meta?.title || node.label}</b><br/><span style="opacity:.72">${typeLabel(node.type)}${node.docId ? ` · 资料 #${node.docId}` : ''}</span>`
      }
    },
    series: [
      {
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: false,
        silent: true,
        z: 1,
        data: visibleEdges
          .map((edge) => {
            const source = posById.get(edge.source)
            const target = posById.get(edge.target)
            if (source?.x == null || target?.x == null) return null
            return {
              coords: [
                [source.x, source.y],
                [target.x, target.y]
              ],
              lineStyle: {
                color: edgeColors[edge.type] || '#d4dbe9',
                width: edge.type === 'reference' ? 1.7 : 1,
                type: edge.type === 'reference' ? 'dashed' : 'solid',
                opacity: edge.type === 'reference' ? 0.78 : 0.5,
                curveness: 0.1
              }
            }
          })
          .filter(Boolean),
        lineStyle: { opacity: 0.6 }
      },
      {
        type: 'scatter',
        coordinateSystem: 'cartesian2d',
        z: 10,
        symbolSize: (_value: any, params: any) => params.data?.size || 12,
        data: list.map((node) => {
          const style = nodeStyles[node.type] || nodeStyles.document
          const isSelected = selectedNode.value?.id === node.id
          const dim = activeDocId.value && node.type === 'document' && Number(node.docId) !== Number(activeDocId.value)
          const nodeColor = node.type === 'document' ? groupColor.get(node.groupId) || style.color : style.color
          const baseName = (node.label || '').replace(/\.[^.]+$/, '')
          const duplicate = node.type === 'document' && (docLabelCounts.get(baseName) || 0) > 1
          const labelText = duplicate ? `${baseName.slice(0, 7)}…·${node.docId}` : node.label
          return {
            value: [Number(node.x || 0), Number(node.y || 0)],
            name: node.label,
            symbol: style.symbol,
            size: style.size + (node.type === 'document' ? Math.min(10, Math.log2((node.value || 100) / 80 + 1) * 3.2) : 0),
            itemStyle: {
              color: dim ? '#d8deea' : nodeColor,
              borderColor: isSelected ? '#172033' : style.border,
              borderWidth: isSelected ? 3 : node.type === 'document' ? 2.5 : 1,
              shadowColor: node.type === 'document' ? 'rgba(79,107,237,.22)' : 'transparent',
              shadowBlur: node.type === 'document' ? 10 : 0,
              opacity: dim ? 0.28 : 1
            },
            label: {
              show: node.type === 'document' || node.type === 'section' || node.type === 'note' || node.type === 'question' || node.type === 'image' || activeDocId.value === Number(node.docId),
              position: node.type === 'document' ? 'bottom' : 'right',
              distance: node.type === 'document' ? 7 : 5,
              color: node.type === 'document' ? '#2b3444' : '#6b7280',
              fontSize: node.type === 'document' ? 10.5 : 9.5,
              fontWeight: node.type === 'document' ? 600 : 400,
              width: node.type === 'document' ? 96 : node.type === 'note' ? 86 : 64,
              overflow: 'truncate',
              formatter: () => shortLabel(labelText, node.type === 'document' ? 15 : node.type === 'note' ? 12 : 9)
            },
            rawNode: node
          }
        }),
        emphasis: {
          scale: 1.15,
          label: { color: '#172033', fontWeight: 600 }
        }
      }
    ]
  }
  chart.setOption(option, { notMerge: true })
  chart.resize()
}

watch(keyword, () => render())
watch(activeTypes, () => render(), { deep: true })
watch(hideIsolated, () => render())
watch(
  () => props.activeKbId,
  () => {
    groupInitialized.value = false
    activeDocId.value = null
    selectedNode.value = null
    reload()
  }
)

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (activeDocId.value || selectedNode.value) {
      activeDocId.value = null
      selectedNode.value = null
      render()
    }
  }
}

onMounted(async () => {
  await reload()
  window.addEventListener('keydown', onKeydown)
  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.map-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px 2px 10px;
}

.map-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 22px;
  border: 1px solid rgba(79, 107, 237, 0.12);
  border-radius: 16px;
  background:
    radial-gradient(circle at 92% 0%, rgba(47, 158, 143, 0.09), transparent 34%),
    radial-gradient(circle at 8% 8%, rgba(79, 107, 237, 0.08), transparent 34%),
    linear-gradient(135deg, #fbfcff 0%, #f7f9fd 55%, #f7fbfa 100%);
}

.map-hero__copy h2 {
  margin: 8px 0 7px;
  color: #1f2937;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.4px;
}

.map-hero__copy p {
  max-width: 680px;
  margin: 0;
  color: #6b7280;
  font-size: 12.5px;
  line-height: 1.75;
}

.map-kicker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #4f6bed;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.map-kicker span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4f6bed;
  box-shadow: 0 0 0 4px rgba(79, 107, 237, 0.1);
}

.map-hero__stats {
  display: flex;
  flex: none;
  gap: 8px;
}

.map-hero__stats div {
  min-width: 70px;
  padding: 9px 11px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.7);
}

.map-hero__stats span {
  display: block;
  color: #8a91a0;
  font-size: 10px;
}

.map-hero__stats b {
  display: block;
  margin-top: 4px;
  color: #273246;
  font-size: 19px;
  line-height: 1;
}

.map-layout {
  display: grid;
  grid-template-columns: 188px minmax(0, 1fr) 268px;
  gap: 12px;
  align-items: stretch;
  height: clamp(560px, calc(100vh - 300px), 760px);
  min-height: 560px;
}

.map-rail,
.map-detail {
  overflow: auto;
  border: 1px solid #e9ecf2;
  border-radius: 13px;
  background: #fff;
}

.map-rail {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 15px 12px;
}

.map-rail__label {
  margin-bottom: 7px;
  color: #9aa1af;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.map-group-item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 7px;
  margin-bottom: 2px;
  padding: 7px 8px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #596173;
  cursor: pointer;
  font-size: 11.5px;
  text-align: left;
}

.map-group-item:hover {
  background: #f5f7fb;
}

.map-group-item.is-active {
  background: #eef2ff;
  color: #4f6bed;
  font-weight: 600;
}

.map-group-item__dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.map-group-item__dot.is-all {
  background: linear-gradient(135deg, #4f6bed, #2f9e8f);
}

.map-group-item__name {
  overflow: hidden;
  flex: 1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-group-item__count {
  color: #a6acb8;
  font-size: 10px;
}

.map-type-row,
.map-switch-row {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 4px;
  color: #6b7280;
  cursor: pointer;
  font-size: 11px;
}

.map-type-row input,
.map-switch-row input {
  display: none;
}

.map-type-row__mark {
  width: 9px;
  height: 9px;
  border: 1.5px solid #c7cede;
  border-radius: 3px;
}

.map-type-row__mark.is-document { background: #4f6bed; border-color: #4f6bed; }
.map-type-row__mark.is-section { background: #8ea2d9; border-color: #8ea2d9; border-radius: 50%; }
.map-type-row__mark.is-note { background: #8b6bb1; border-color: #8b6bb1; }
.map-type-row__mark.is-question { background: #c99a3d; border-color: #c99a3d; transform: rotate(45deg); }
.map-type-row__mark.is-image { background: #2f9e8f; border-color: #2f9e8f; }

.map-type-row:has(input:not(:checked)) .map-type-row__mark {
  opacity: 0.28;
}

.map-type-row em {
  margin-left: auto;
  color: #b0b6c1;
  font-size: 9px;
  font-style: normal;
}

.map-switch-row {
  justify-content: space-between;
  margin-top: 5px;
  padding-top: 10px;
  border-top: 1px dashed #edf0f5;
}

.map-switch-row input {
  display: block;
  width: 26px;
  height: 14px;
  border-radius: 99px;
  background: #dce2ee;
  appearance: none;
  cursor: pointer;
  position: relative;
}

.map-switch-row input:checked {
  background: #4f6bed;
}

.map-switch-row input::after {
  content: '';
  position: absolute;
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.15s;
}

.map-switch-row input:checked::after {
  transform: translateX(12px);
}

.map-rail__legend {
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px dashed #edf0f5;
}

.map-legend {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 2px;
  color: #8a91a0;
  font-size: 10px;
}

.map-legend i {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.map-legend i.is-doc { background: #4f6bed; }
.map-legend i.is-section { background: #8ea2d9; }
.map-legend i.is-reference { border-top: 1px dashed #8b6bb1; border-radius: 0; height: 0; }
.map-legend i.is-source { border-top: 1px solid #c9d2e8; border-radius: 0; height: 0; }

.map-stage {
  position: relative;
  overflow: hidden;
  border: 1px solid #e9ecf2;
  border-radius: 13px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.78)),
    radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.12) 1px, transparent 0);
  background-size: auto, 20px 20px;
}

.map-toolbar {
  position: absolute;
  z-index: 2;
  display: flex;
  top: 12px;
  right: 12px;
  left: 12px;
  align-items: center;
  gap: 7px;
  pointer-events: none;
}

.map-toolbar > * {
  pointer-events: auto;
}

.map-search {
  width: 250px;
}

.map-search :deep(.el-input__wrapper) {
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 2px 10px rgba(23, 32, 51, 0.06), 0 0 0 1px rgba(15, 23, 42, 0.06) inset;
}

.map-tool-btn {
  padding: 6px 9px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.92);
  color: #687083;
  cursor: pointer;
  font-size: 10.5px;
  box-shadow: 0 2px 8px rgba(23, 32, 51, 0.04);
}

.map-tool-btn:hover:not(:disabled),
.map-tool-btn.is-on {
  color: #4f6bed;
  border-color: rgba(79, 107, 237, 0.25);
  background: #f5f7ff;
}

.map-tool-btn:disabled {
  cursor: default;
  opacity: 0.35;
}

.map-tool-btn kbd {
  margin-left: 3px;
  padding: 0 3px;
  border: 1px solid #dce2ee;
  border-radius: 3px;
  color: #9aa1af;
  font-family: inherit;
  font-size: 9px;
}

.map-toolbar__spacer {
  flex: 1;
}

.map-toolbar__hint {
  color: #9aa1af;
  font-size: 10px;
}

.map-canvas {
  width: 100%;
  height: 100%;
  min-height: 0;
}

.map-canvas__legend {
  position: absolute;
  bottom: 12px;
  left: 14px;
  display: flex;
  gap: 12px;
  padding: 5px 9px;
  border: 1px solid rgba(15, 23, 42, 0.05);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.78);
  color: #8a91a0;
  font-size: 9.5px;
  pointer-events: none;
}

.map-canvas__legend span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.map-canvas__legend i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.map-canvas__legend i.is-doc { background: linear-gradient(135deg, #4f6bed, #2f9e8f); }
.map-canvas__legend i.is-section { background: #8ea2d9; }
.map-canvas__legend i.is-note { background: #8b6bb1; }
.map-canvas__legend i.is-question { background: #c99a3d; transform: rotate(45deg); border-radius: 1px; }
.map-canvas__legend i.is-image { background: #2f9e8f; border-radius: 2px; }

.map-empty,
.map-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  background: rgba(251, 252, 254, 0.94);
}

.map-empty__art {
  display: flex;
  width: 52px;
  height: 52px;
  align-items: center;
  justify-content: center;
  margin-bottom: 10px;
  border-radius: 16px;
  color: #4f6bed;
  background: #eef2ff;
  font-size: 22px;
}

.map-empty h3 {
  margin: 0 0 5px;
  color: #374151;
  font-size: 16px;
}

.map-empty p {
  max-width: 360px;
  margin: 0 0 13px;
  color: #8a91a0;
  font-size: 11.5px;
  line-height: 1.7;
  text-align: center;
}

.map-detail {
  display: flex;
  flex-direction: column;
  padding: 16px 15px;
}

.map-detail__eyebrow {
  color: #4f6bed;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.map-detail h3 {
  margin: 7px 0 5px;
  color: #1f2937;
  font-size: 16px;
  line-height: 1.45;
}

.map-detail__summary {
  margin: 0;
  color: #6b7280;
  font-size: 11.5px;
  line-height: 1.7;
}

.map-detail__excerpt {
  margin-top: 11px;
  padding: 10px;
  border-left: 2px solid #c9d2e8;
  border-radius: 0 7px 7px 0;
  color: #6b7280;
  background: #f7f8fb;
  font-size: 11px;
  line-height: 1.7;
}

.map-detail__metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
  margin: 16px 0 14px;
  padding: 11px 0;
  border-top: 1px solid #f0f2f6;
  border-bottom: 1px solid #f0f2f6;
}

.map-detail__metrics div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.map-detail__metrics span {
  color: #a0a6b2;
  font-size: 9.5px;
}

.map-detail__metrics b {
  color: #4b5563;
  font-size: 13px;
  font-weight: 600;
}

.map-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.map-detail__hint {
  margin-top: 10px;
  color: #a0a6b2;
  font-size: 10px;
  line-height: 1.6;
}

.map-detail__placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 4px;
  text-align: center;
}

.map-detail__placeholder-art {
  display: flex;
  width: 44px;
  height: 44px;
  align-items: center;
  justify-content: center;
  margin-bottom: 9px;
  border-radius: 14px;
  color: #4f6bed;
  background: #eef2ff;
  font-size: 20px;
}

.map-detail__placeholder h3 {
  margin: 0 0 5px;
  font-size: 14px;
}

.map-detail__placeholder p {
  margin: 0;
  color: #9aa1af;
  font-size: 10.5px;
  line-height: 1.7;
}

.map-detail__groups {
  margin-top: auto;
  padding-top: 14px;
  border-top: 1px dashed #edf0f5;
}

.map-detail__groups-title {
  margin-bottom: 8px;
  color: #9aa1af;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.map-detail__group {
  display: flex;
  gap: 7px;
  margin-bottom: 8px;
}

.map-detail__group > i {
  flex: none;
  width: 6px;
  height: 6px;
  margin-top: 4px;
  border-radius: 50%;
}

.map-detail__group b {
  display: block;
  color: #596173;
  font-size: 10.5px;
  font-weight: 600;
}

.map-detail__group span {
  display: block;
  margin-top: 2px;
  color: #a0a6b2;
  font-size: 9.5px;
  line-height: 1.55;
}

@media (max-width: 1180px) {
  .map-layout {
    grid-template-columns: 160px minmax(0, 1fr);
  }

  .map-detail {
    display: none;
  }

  .map-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .map-hero__stats {
    width: 100%;
  }

  .map-hero__stats div {
    flex: 1;
  }
}
</style>
