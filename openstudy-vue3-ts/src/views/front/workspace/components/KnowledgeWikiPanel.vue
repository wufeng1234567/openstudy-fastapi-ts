<template>
  <section class="kw-page">
    <header class="kw-head">
      <div class="kw-head__copy">
        <div class="kw-kicker">KNOWLEDGE WIKI · 知识百科</div>
        <h2>资料知识百科</h2>
        <p>把资料里的概念整理成能读、能查、能回到原文的主题页。</p>
        <div v-if="stats.pageCount" class="kw-stats">
          <b>{{ stats.pageCount }}</b> 个主题
          <span>·</span>
          <b>{{ stats.docCount }}</b> 份资料
          <span v-if="stats.staleCount">·</span>
          <b v-if="stats.staleCount">{{ stats.staleCount }}</b><span v-if="stats.staleCount"> 个待更新</span>
        </div>
      </div>
      <div class="kw-head__actions">
        <div class="kw-switch">
          <button type="button" :class="{ 'is-active': view === 'pages' }" @click="view = 'pages'">主题页</button>
          <button type="button" :class="{ 'is-active': view === 'map' }" :disabled="!pages.length" @click="switchMap">知识地图</button>
        </div>
        <el-button size="small" :loading="loading" @click="reload">刷新</el-button>
        <el-button size="small" class="kw-build-btn" :loading="building" :disabled="!activeKbId" @click="build">
          {{ pages.length ? '更新知识百科' : '生成知识百科' }}
        </el-button>
      </div>
    </header>

    <div v-if="loading" class="kw-loading" v-loading="true"></div>

    <template v-else-if="pages.length">
      <div v-if="view === 'pages'" class="kw-grid">
        <article
          v-for="page in filteredPages"
          :key="page.pageId"
          class="kw-card"
          tabindex="0"
          @click="openPage(page.pageId)"
          @keydown.enter="openPage(page.pageId)"
        >
          <div class="kw-card__top">
            <span class="kw-card__type">主题页</span>
            <span class="kw-card__status" :class="`is-${page.status}`">{{ statusLabel(page.status) }}</span>
          </div>
          <h3>{{ page.title }}</h3>
          <p>{{ page.summary || '还没有摘要，打开主题页查看整理内容。' }}</p>
          <div class="kw-card__meta">
            <span>{{ page.sourceCount || 0 }} 条来源</span>
            <span>{{ page.relatedCount || 0 }} 个关联</span>
            <span>{{ formatTime(page.updateTime) }}</span>
          </div>
        </article>
        <div v-if="!filteredPages.length" class="kw-filter-empty">
          没有匹配的主题页，换个关键词试试。
        </div>
      </div>

      <div v-else ref="mapCanvasRef" class="kw-map" @wheel.prevent="onMapWheel" @pointerdown="onMapDown"
        @pointermove="onMapMove" @pointerup="onMapUp" @pointerleave="onMapUp">
        <svg class="kw-map__svg" viewBox="0 0 1000 640" aria-label="知识地图：主题页之间的关联">
          <g :transform="`translate(${mapView.x} ${mapView.y}) scale(${mapView.scale})`">
            <line v-for="edge in mapEdges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              class="kw-map-edge" :class="`is-${edge.type}`" />
            <g v-for="node in mapNodes" :key="node.id" class="kw-map-node" :transform="`translate(${node.x} ${node.y})`"
              @pointerdown.stop @pointerup.stop @click.stop="openPage(node.pageId)">
              <circle class="kw-map-node__halo" :r="node.r + 7" />
              <circle class="kw-map-node__dot" :r="node.r" :fill="node.color" />
              <text class="kw-map-node__label" :x="node.r + 8" y="3">{{ node.title }}</text>
            </g>
          </g>
        </svg>
        <div class="kw-map__legend">
          <span><i class="is-part_of"></i>结构</span>
          <span><i class="is-prerequisite"></i>先学</span>
          <span><i class="is-contrast"></i>对比</span>
          <span><i class="is-related"></i>相关</span>
          <em>滚轮缩放 · 空白处拖拽平移 · 点节点打开主题页</em>
        </div>
      </div>
    </template>

    <div v-else class="kw-empty">
      <div class="kw-empty__art">◇</div>
      <h3>这个资料夹还没有知识百科</h3>
      <p>先生成知识图谱，再把图谱里的概念整理成可读主题页。不会补充资料里没有的内容。</p>
      <el-button class="kw-build-btn" type="primary" :loading="building" :disabled="!activeKbId" @click="build">
        生成知识百科
      </el-button>
    </div>

    <el-drawer v-model="detailVisible" size="780px" :with-header="false" append-to-body class="kw-detail-drawer">
      <div v-if="pageLoading" class="kw-detail-loading" v-loading="true"></div>
      <div v-else-if="activePage" class="kw-detail">
        <header class="kw-detail__head">
          <div>
            <div class="kw-kicker">KNOWLEDGE PAGE</div>
            <h2>{{ activePage.title }}</h2>
            <div class="kw-detail__badges">
              <span class="kw-detail__type">{{ activePage.pageType === 'overview' ? '资料夹总览' : '主题页' }}</span>
              <span>{{ activePage.sources?.length || 0 }} 条来源</span>
              <span>{{ activePage.version || 1 }} 版</span>
              <span v-if="activePage.status === 'stale'" class="is-stale">待更新</span>
              <span v-if="activePage.generatedBy === 'manual'" class="is-manual">手动编辑</span>
            </div>
          </div>
          <div class="kw-detail__head-actions">
            <el-button size="small" plain @click="openEditor">编辑</el-button>
            <el-button size="small" plain @click="openRevisions">历史版本</el-button>
            <el-button size="small" plain @click="askPage('practice')">生成练习</el-button>
            <el-button size="small" type="primary" plain @click="askPage()">问 AI 这一页</el-button>
            <button type="button" class="kw-detail__close" @click="detailVisible = false">×</button>
          </div>
        </header>

        <div v-if="activePage.status === 'stale'" class="kw-detail__warning">
          资料已经更新，这一页的内容可能过期。请回到知识百科点击「更新知识百科」重新整理。
        </div>
        <p class="kw-detail__lead">{{ activePage.summary }}</p>

        <section v-for="(section, index) in activePage.sections || []" :key="`${index}-${section.heading}`" class="kw-detail__section">
          <h3>{{ section.heading }}</h3>
          <LatexRenderer :content="section.body" class="kw-detail__body" />
        </section>

        <section class="kw-detail__block">
          <div class="kw-detail__block-head">
            <span>画廊图片</span>
            <b>{{ activePage.images?.length || 0 }}</b>
            <el-button size="small" text type="primary" @click="openGalleryPicker">从画廊添加</el-button>
          </div>
          <div v-if="activePage.images?.length" class="kw-image-grid">
            <div v-for="image in activePage.images" :key="image.referenceId" class="kw-image-card">
              <el-image :src="imageUrl(image.url)" fit="cover" />
              <div class="kw-image-card__foot">
                <span :title="image.caption || image.fileName">{{ image.caption || image.fileName || '图片' }}</span>
                <button type="button" title="取消关联" @click="removeImage(image)">×</button>
              </div>
            </div>
          </div>
          <div v-else class="kw-image-empty">还没有关联画廊图片，可以从画廊选择。</div>
        </section>

        <section v-if="activePage.sources?.length" class="kw-detail__block">
          <div class="kw-detail__block-head"><span>来源</span><b>{{ activePage.sources.length }}</b></div>
          <button v-for="source in activePage.sources" :key="`${source.docId}-${source.chunkId}`" type="button"
            class="kw-source" @click="locateSource(source)">
            <span class="kw-source__name">{{ source.docName }}</span>
            <span class="kw-source__index">第 {{ Number(source.chunkIndex || 0) + 1 }} 段</span>
            <span class="kw-source__quote">{{ source.quote }}</span>
          </button>
        </section>

        <section v-if="activePage.related?.length" class="kw-detail__block">
          <div class="kw-detail__block-head"><span>相关主题</span><b>{{ activePage.related.length }}</b></div>
          <div class="kw-related">
            <button v-for="item in activePage.related" :key="`${item.pageId}-${item.linkType}`" type="button"
              class="kw-related__item" @click="openPage(item.pageId)">
              <b>{{ item.title }}</b>
              <span>{{ linkTypeLabel(item.linkType) }}</span>
            </button>
          </div>
        </section>

        <footer class="kw-detail__foot">
          基于 {{ activePage.sourceDocIds?.length || 0 }} 份资料生成 · {{ formatTime(activePage.updateTime) }}
        </footer>
      </div>
    </el-drawer>

    <KnowledgeWikiEditor v-model="editorVisible" :page="activePage" @saved="onPageSaved" />

    <el-dialog v-model="revisionVisible" title="主题页历史版本" width="560px" append-to-body>
      <div v-if="revisions.length" class="kw-revisions">
        <div v-for="revision in revisions" :key="revision.revisionId" class="kw-revision">
          <div>
            <b>v{{ revision.version }}</b>
            <span>{{ revision.changeType === 'manual' ? '手动编辑' : revision.changeType === 'before_restore' ? '恢复前快照' : '生成' }}</span>
            <em>{{ revision.createTime }}</em>
          </div>
          <el-button size="small" plain @click="restoreRevision(revision)">恢复</el-button>
        </div>
      </div>
      <div v-else class="kw-image-empty">还没有历史版本。</div>
    </el-dialog>

    <el-dialog v-model="galleryPickerVisible" title="从画廊选择图片" width="760px" append-to-body>
      <div v-loading="galleryLoading" class="kw-gallery-picker">
        <button v-for="item in galleryItems" :key="item.assetKey" type="button" class="kw-gallery-pick"
          @click="attachImage(item)">
          <el-image :src="imageUrl(item.url)" fit="cover" />
          <span>{{ item.caption || item.fileName || item.assetKey }}</span>
        </button>
        <div v-if="!galleryLoading && !galleryItems.length" class="kw-image-empty">当前资料夹还没有可用的画廊图片。</div>
      </div>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import KnowledgeWikiEditor from './KnowledgeWikiEditor.vue'
import {
  attachWikiImage,
  buildWikiPages,
  detachWikiImage,
  getWikiGraph,
  getWikiPage,
  listGalleryAssets,
  listWikiPages,
  listWikiRevisions,
  restoreWikiRevision
} from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  searchQuery?: string
}>()

const emit = defineEmits<{
  (e: 'stats', payload: { total: number }): void
  (e: 'locate', payload: { docId: number; chunkId?: number; chunkIndex?: number }): void
  (e: 'ask', prompt: string): void
}>()

const loading = ref(false)
const building = ref(false)
const pages = ref<any[]>([])
const stats = reactive({ pageCount: 0, docCount: 0, staleCount: 0 })
const view = ref<'pages' | 'map'>('pages')
const detailVisible = ref(false)
const pageLoading = ref(false)
const activePage = ref<any>(null)
const editorVisible = ref(false)
const revisionVisible = ref(false)
const revisions = ref<any[]>([])
const galleryPickerVisible = ref(false)
const galleryLoading = ref(false)
const galleryItems = ref<any[]>([])

const mapCanvasRef = ref<HTMLElement | null>(null)
const mapGraph = ref<any>({ nodes: [], edges: [] })
const mapView = reactive({ x: 0, y: 0, scale: 1 })
let mapDrag: any = null

const filteredPages = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (!query) return pages.value
  return pages.value.filter((page: any) =>
    `${page.title || ''} ${page.summary || ''}`.toLowerCase().includes(query)
  )
})

const mapNodes = computed(() => {
  const nodes = mapGraph.value?.nodes || []
  const total = nodes.length
  return nodes.map((node: any, index: number) => {
    const inner = total <= 12
    const ring = inner ? 0 : index < 8 ? 0 : 1
    const count = inner ? total : ring === 0 ? Math.min(8, total) : Math.max(1, total - 8)
    const localIndex = ring === 0 ? index : index - Math.min(8, total)
    const angle = -Math.PI / 2 + (Math.PI * 2 * localIndex) / Math.max(1, count)
    const radius = inner ? 220 : ring === 0 ? 145 : 272
    const degree = Number(node.degree || 0)
    return {
      ...node,
      x: 500 + Math.cos(angle) * radius,
      y: 320 + Math.sin(angle) * radius,
      r: 11 + Math.min(8, Math.sqrt(degree + 1) * 4),
      color: degree > 4 ? '#2f5fce' : degree > 1 ? '#4f86d9' : '#8da9d8'
    }
  })
})

const mapEdges = computed(() => {
  const positions = new Map(mapNodes.value.map((node: any) => [String(node.id), node]))
  return (mapGraph.value?.edges || [])
    .map((edge: any) => {
      const source = positions.get(String(edge.source))
      const target = positions.get(String(edge.target))
      if (!source || !target) return null
      return {
        key: `${edge.source}-${edge.target}-${edge.type}`,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        type: edge.type || 'related'
      }
    })
    .filter(Boolean)
})

function statusLabel(status: string) {
  if (status === 'stale') return '待更新'
  if (status === 'failed') return '生成失败'
  if (status === 'draft') return '整理中'
  return '已整理'
}

function linkTypeLabel(type: string) {
  if (type === 'prerequisite') return '先学'
  if (type === 'contrast') return '对比'
  if (type === 'part_of') return '结构'
  return '相关'
}

function formatTime(value?: string) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 16)
}

async function reload() {
  loading.value = true
  try {
    const res = await listWikiPages({ kbId: props.activeKbId || undefined })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识百科加载失败')
      return
    }
    pages.value = res.data?.pages || []
    Object.assign(stats, res.data?.stats || {})
    emit('stats', { total: pages.value.length })
    if (!pages.value.length) view.value = 'pages'
  } catch (error: any) {
    ElMessage.error('知识百科加载失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

async function build() {
  if (!props.activeKbId || building.value) return
  building.value = true
  try {
    const res = await buildWikiPages({
      kbId: Number(props.activeKbId),
      force: pages.value.length > 0,
      limit: 10
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '知识百科生成失败')
      return
    }
    const data = res.data || {}
    const errors = Array.isArray(data.errors) ? data.errors.length : 0
    if (errors) ElMessage.warning(`已完成 ${data.pages || 0} 个主题，${errors} 个生成失败`)
    else ElMessage.success(`已整理 ${data.pages || 0} 个主题页`)
    await reload()
  } catch (error: any) {
    ElMessage.error('知识百科生成失败：' + (error?.message || error))
  } finally {
    building.value = false
  }
}

async function switchMap() {
  if (!pages.value.length) return
  view.value = 'map'
  try {
    const res = await getWikiGraph(Number(props.activeKbId))
    if (res.code === 200) mapGraph.value = res.data || { nodes: [], edges: [] }
  } catch {
    // 地图失败时保持主题页入口，不影响阅读。
    view.value = 'pages'
  }
}

async function openPage(pageId: number) {
  detailVisible.value = true
  pageLoading.value = true
  activePage.value = null
  try {
    const res = await getWikiPage(pageId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '主题页加载失败')
      detailVisible.value = false
      return
    }
    activePage.value = res.data
  } catch (error: any) {
    ElMessage.error('主题页加载失败：' + (error?.message || error))
    detailVisible.value = false
  } finally {
    pageLoading.value = false
  }
}

function locateSource(source: any) {
  if (!source?.docId) return
  emit('locate', {
    docId: Number(source.docId),
    chunkId: Number(source.chunkId) || undefined,
    chunkIndex: Number(source.chunkIndex) || undefined
  })
  detailVisible.value = false
}

function imageUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
}

function openEditor() {
  if (!activePage.value) return
  editorVisible.value = true
}

async function onPageSaved(page: any) {
  if (page?.pageId) activePage.value = page
  await reload()
}

async function openRevisions() {
  if (!activePage.value) return
  revisionVisible.value = true
  try {
    const res = await listWikiRevisions(activePage.value.pageId)
    revisions.value = res.code === 200 ? (res.data || []) : []
  } catch {
    revisions.value = []
  }
}

async function restoreRevision(revision: any) {
  if (!activePage.value) return
  try {
    const res = await restoreWikiRevision(activePage.value.pageId, revision.revisionId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '恢复失败')
      return
    }
    activePage.value = res.data
    revisionVisible.value = false
    await reload()
    ElMessage.success('已恢复历史版本')
  } catch (error: any) {
    ElMessage.error('恢复失败：' + (error?.message || error))
  }
}

async function openGalleryPicker() {
  galleryPickerVisible.value = true
  galleryLoading.value = true
  try {
    const res = await listGalleryAssets({
      scope: 'current',
      kbId: props.activeKbId || undefined,
      limit: 200
    })
    galleryItems.value = res.code === 200 ? (res.data?.items || []) : []
  } catch {
    galleryItems.value = []
  } finally {
    galleryLoading.value = false
  }
}

async function attachImage(item: any) {
  if (!activePage.value || !item?.assetKey) return
  try {
    const res = await attachWikiImage(activePage.value.pageId, { assetKey: item.assetKey })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '关联图片失败')
      return
    }
    await refreshActivePage()
    galleryPickerVisible.value = false
    ElMessage.success('图片已关联到主题页')
  } catch (error: any) {
    ElMessage.error('关联图片失败：' + (error?.message || error))
  }
}

async function removeImage(image: any) {
  if (!activePage.value || !image?.referenceId) return
  try {
    const res = await detachWikiImage(activePage.value.pageId, image.referenceId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '取消关联失败')
      return
    }
    await refreshActivePage()
  } catch (error: any) {
    ElMessage.error('取消关联失败：' + (error?.message || error))
  }
}

async function refreshActivePage() {
  if (!activePage.value?.pageId) return
  const res = await getWikiPage(activePage.value.pageId)
  if (res.code === 200) activePage.value = res.data
}

function askPage(kind: 'ask' | 'practice' = 'ask') {
  if (!activePage.value) return
  const title = activePage.value.title
  const prompt = kind === 'practice'
    ? `请基于知识百科主题页《${title}》生成 5 道练习题，并在每题后标出对应的主题页小节和原文来源。`
    : `请基于知识百科主题页《${title}》回答我，并在回答里标出引用的主题页和原文来源。`
  emit('ask', prompt)
  detailVisible.value = false
}

function onMapWheel(event: WheelEvent) {
  const rect = mapCanvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  const old = mapView.scale
  const next = Math.max(0.5, Math.min(2.2, old * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
  const wx = (px - mapView.x) / old
  const wy = (py - mapView.y) / old
  mapView.scale = next
  mapView.x = px - wx * next
  mapView.y = py - wy * next
}

function onMapDown(event: PointerEvent) {
  if (event.button !== 0) return
  mapDrag = { x: event.clientX, y: event.clientY, vx: mapView.x, vy: mapView.y }
}

function onMapMove(event: PointerEvent) {
  if (!mapDrag) return
  mapView.x = mapDrag.vx + event.clientX - mapDrag.x
  mapView.y = mapDrag.vy + event.clientY - mapDrag.y
}

function onMapUp() {
  mapDrag = null
}

watch(() => props.activeKbId, () => reload())
onMounted(reload)
</script>

<style scoped>
.kw-page { display: flex; flex-direction: column; gap: 14px; padding: 2px 2px 12px; }
.kw-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 2px 2px 12px; border-bottom: 1px solid #edf0f5; }
.kw-kicker { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.kw-head h2 { margin: 5px 0 4px; color: #1f2937; font-size: 22px; font-weight: 700; }
.kw-head p { margin: 0; color: #8a91a0; font-size: 12px; }
.kw-stats { display: flex; align-items: center; gap: 5px; margin-top: 7px; color: #9aa1af; font-size: 10px; }
.kw-stats b { color: #2f5fce; font-weight: 600; }
.kw-head__actions { display: flex; flex: none; align-items: center; gap: 8px; }
.kw-switch { display: inline-flex; padding: 2px; border: 1px solid #e6ebf4; border-radius: 8px; background: #f8fafc; }
.kw-switch button { padding: 5px 10px; border: 0; border-radius: 6px; color: #7d8596; background: transparent; cursor: pointer; font-size: 11px; }
.kw-switch button.is-active { color: #2f5fce; background: #fff; box-shadow: 0 1px 4px rgba(47, 95, 206, 0.1); font-weight: 600; }
.kw-switch button:disabled { opacity: 0.45; cursor: not-allowed; }
.kw-build-btn { border-color: rgba(47, 95, 206, 0.28); color: #2f5fce; background: #f5f8ff; }
.kw-loading { min-height: 420px; }
.kw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.kw-card { display: flex; min-height: 160px; flex-direction: column; padding: 15px 16px 13px; border: 1px solid #e7ebf3; border-radius: 13px; background: #fff; cursor: pointer; transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease; }
.kw-card:hover { border-color: #cbd9f2; box-shadow: 0 8px 24px rgba(47, 95, 206, 0.08); transform: translateY(-1px); }
.kw-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.kw-card__type { color: #2f5fce; font-size: 10px; font-weight: 600; }
.kw-card__status { color: #9aa1af; font-size: 9px; }
.kw-card__status.is-stale { color: #c47a55; }
.kw-card__status.is-failed { color: #c05c7e; }
.kw-card h3 { margin: 11px 0 7px; color: #253247; font-size: 16px; font-weight: 700; line-height: 1.4; }
.kw-card p { display: -webkit-box; overflow: hidden; flex: 1; margin: 0; color: #697386; font-size: 11px; line-height: 1.7; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.kw-card__meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; color: #a0a6b2; font-size: 9.5px; }
.kw-filter-empty { grid-column: 1 / -1; padding: 60px 0; color: #9aa1af; text-align: center; font-size: 12px; }
.kw-map { position: relative; min-height: 590px; overflow: hidden; border: 1px solid #e6ebf4; border-radius: 13px; background: radial-gradient(circle at 1px 1px, rgba(95, 111, 150, 0.1) 1px, transparent 0), #fbfcfe; background-size: 20px 20px; cursor: grab; touch-action: none; user-select: none; }
.kw-map:active { cursor: grabbing; }
.kw-map__svg { width: 100%; height: 590px; }
.kw-map-edge { stroke: #c9d4e5; stroke-width: 1.1; opacity: 0.8; vector-effect: non-scaling-stroke; }
.kw-map-edge.is-part_of { stroke: #b8c5dc; }
.kw-map-edge.is-prerequisite { stroke: #73a6dd; stroke-dasharray: 4 4; }
.kw-map-edge.is-contrast { stroke: #d38e7d; stroke-dasharray: 3 5; }
.kw-map-edge.is-related { stroke: #c7d2e5; }
.kw-map-node { cursor: pointer; }
.kw-map-node__halo { fill: rgba(255, 255, 255, 0.86); }
.kw-map-node__dot { stroke: #fff; stroke-width: 2; }
.kw-map-node__label { fill: #4b5563; font-size: 11px; pointer-events: none; }
.kw-map-node:hover .kw-map-node__dot { stroke: #253247; stroke-width: 3; }
.kw-map-node:hover .kw-map-node__label { fill: #1f2937; font-weight: 600; }
.kw-map__legend { position: absolute; right: 14px; bottom: 12px; display: flex; align-items: center; flex-wrap: wrap; gap: 10px; max-width: calc(100% - 28px); padding: 6px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 7px; background: rgba(255, 255, 255, 0.88); color: #7d8596; font-size: 9.5px; pointer-events: none; }
.kw-map__legend span { display: inline-flex; align-items: center; gap: 4px; }
.kw-map__legend i { width: 15px; height: 1px; background: #c9d4e5; }
.kw-map__legend i.is-prerequisite { background: #73a6dd; }
.kw-map__legend i.is-contrast { background: #d38e7d; }
.kw-map__legend em { color: #a0a6b2; font-style: normal; }
.kw-empty { display: flex; min-height: 520px; flex-direction: column; align-items: center; justify-content: center; border: 1px dashed #dfe6f2; border-radius: 13px; background: #fcfdff; text-align: center; }
.kw-empty__art { display: flex; width: 56px; height: 56px; align-items: center; justify-content: center; margin-bottom: 10px; border-radius: 16px; color: #2f5fce; background: #eef4ff; font-size: 28px; }
.kw-empty h3 { margin: 0 0 6px; color: #374151; font-size: 16px; }
.kw-empty p { max-width: 420px; margin: 0 0 16px; color: #9aa1af; font-size: 11px; line-height: 1.7; }
.kw-detail-drawer :deep(.el-drawer__body) { padding: 24px 30px 40px; }
.kw-detail { display: flex; flex-direction: column; gap: 18px; }
.kw-detail__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding-bottom: 14px; border-bottom: 1px solid #edf0f5; }
.kw-detail__head h2 { margin: 6px 0 7px; color: #1f2937; font-size: 25px; line-height: 1.3; }
.kw-detail__badges { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; color: #9aa1af; font-size: 10px; }
.kw-detail__type { padding: 3px 7px; border-radius: 5px; color: #2f5fce; background: #eef4ff; font-weight: 600; }
.kw-detail__badges .is-stale { color: #c47a55; }
.kw-detail__badges .is-manual { color: #2f9e8f; }
.kw-detail__head-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.kw-detail__close { flex: none; padding: 0 4px; border: 0; color: #9aa1af; background: transparent; cursor: pointer; font-size: 24px; line-height: 1; }
.kw-detail__warning { padding: 9px 11px; border: 1px solid #f0d9cc; border-radius: 8px; color: #a96545; background: #fff8f3; font-size: 11px; line-height: 1.6; }
.kw-detail__lead { margin: 0; padding: 14px 16px; border-left: 3px solid #5f87e6; border-radius: 0 8px 8px 0; color: #4b5563; background: #f7f9ff; font-size: 13px; line-height: 1.8; }
.kw-detail__section h3 { margin: 0 0 7px; color: #253247; font-size: 15px; font-weight: 700; }
.kw-detail__body { color: #4b5563; font-size: 13px; line-height: 1.85; }
.kw-detail__body :deep(.latex-content) { font-size: 13px; line-height: 1.85; }
.kw-detail__block { padding-top: 13px; border-top: 1px solid #edf0f5; }
.kw-detail__block-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; color: #6b7280; font-size: 10px; font-weight: 700; letter-spacing: 0.08em; }
.kw-detail__block-head b { color: #2f5fce; font-weight: 600; }
.kw-source { display: grid; width: 100%; grid-template-columns: auto auto 1fr; align-items: center; gap: 9px; margin-bottom: 6px; padding: 8px 9px; border: 1px solid #eef1f6; border-radius: 8px; background: #fbfcfe; color: #697386; cursor: pointer; font-size: 10.5px; text-align: left; }
.kw-source:hover { border-color: #d9e1f4; background: #f5f7fc; }
.kw-source__name { overflow: hidden; color: #4b5563; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.kw-source__index { color: #9aa1af; white-space: nowrap; }
.kw-source__quote { overflow: hidden; color: #9aa1af; text-overflow: ellipsis; white-space: nowrap; }
.kw-related { display: flex; flex-wrap: wrap; gap: 7px; }
.kw-related__item { display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid #e6ebf4; border-radius: 8px; background: #fff; color: #4b5563; cursor: pointer; font-size: 11px; }
.kw-related__item:hover { border-color: #cbd9f2; background: #f7f9ff; }
.kw-related__item span { color: #9aa1af; font-size: 9px; }
.kw-detail__foot { padding-top: 5px; color: #a0a6b2; font-size: 10px; }
.kw-image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.kw-image-card { overflow: hidden; border: 1px solid #e8edf5; border-radius: 8px; background: #fbfcfe; }
.kw-image-card :deep(.el-image) { display: block; width: 100%; height: 110px; }
.kw-image-card__foot { display: flex; align-items: center; gap: 5px; padding: 5px 7px; color: #697386; font-size: 10px; }
.kw-image-card__foot span { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; }
.kw-image-card__foot button { border: 0; color: #c05c7e; background: transparent; cursor: pointer; font-size: 16px; line-height: 1; }
.kw-image-empty { padding: 12px; border: 1px dashed #e4eaf3; border-radius: 7px; color: #a0a6b2; font-size: 10.5px; text-align: center; }
.kw-gallery-picker { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; max-height: 55vh; overflow-y: auto; }
.kw-gallery-pick { display: flex; min-width: 0; flex-direction: column; gap: 5px; padding: 6px; border: 1px solid #e8edf5; border-radius: 8px; background: #fff; color: #697386; cursor: pointer; font-size: 10px; text-align: left; }
.kw-gallery-pick:hover { border-color: #cbd9f2; }
.kw-gallery-pick :deep(.el-image) { width: 100%; height: 95px; border-radius: 5px; }
.kw-gallery-pick span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-revisions { display: flex; flex-direction: column; gap: 7px; }
.kw-revision { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 10px; border: 1px solid #eef1f6; border-radius: 7px; background: #fbfcfe; }
.kw-revision > div { display: flex; align-items: center; gap: 8px; color: #697386; font-size: 11px; }
.kw-revision b { color: #2f5fce; }
.kw-revision em { color: #a0a6b2; font-style: normal; font-size: 10px; }
.kw-detail-loading { height: 500px; }
@media (max-width: 900px) { .kw-head { flex-direction: column; align-items: flex-start; gap: 10px; } .kw-head__actions { flex-wrap: wrap; } .kw-map, .kw-map__svg { min-height: 460px; height: 460px; } .kw-detail-drawer { width: 92vw !important; } }
</style>
