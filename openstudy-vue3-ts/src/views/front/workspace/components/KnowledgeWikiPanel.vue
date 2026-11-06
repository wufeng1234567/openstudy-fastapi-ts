<template>
  <section class="kw-page">
    <header class="kw-head">
      <div class="kw-head__copy">
        <div class="kw-kicker">KNOWLEDGE WIKI · 知识百科</div>
        <!-- 知识图谱与知识百科融合：一个主题页 = 一个节点，点击节点打开百科详情。 -->
        <h2>资料知识百科</h2>
        <p>把资料里的概念整理成能读、能查、能回到原文的主题页。</p>
        <div v-if="stats.pageCount" class="kw-stats">
          <b>{{ stats.pageCount }}</b> 个主题
          <span>·</span>
          <b>{{ stats.docCount }}</b> 份资料
          <span v-if="stats.linkCount">·</span>
          <b v-if="stats.linkCount">{{ stats.linkCount }}</b><span v-if="stats.linkCount"> 条页面链接</span>
          <span v-if="stats.staleCount">·</span>
          <b v-if="stats.staleCount">{{ stats.staleCount }}</b><span v-if="stats.staleCount"> 个待更新</span>
        </div>
      </div>
      <div class="kw-head__actions">
        <div class="kw-switch">
          <button type="button" :class="{ 'is-active': view === 'pages' }" @click="view = 'pages'">主题页</button>
          <button type="button" :class="{ 'is-active': view === 'map' }" :disabled="!pages.length" @click="switchMap">知识图谱</button>
        </div>
        <el-button size="small" :loading="loading" @click="reload">刷新</el-button>
        <el-button size="small" class="kw-build-btn" :loading="building || buildActive" :disabled="!activeKbId || buildActive" @click="build">
          {{ buildActive ? `更新中 ${buildJob.done}/${buildJob.total}` : pages.length ? '更新知识百科' : '生成知识百科' }}
        </el-button>
      </div>
    </header>

    <div v-if="buildActive" class="kw-build-progress">
      <div class="kw-build-progress__top">
        <span>正在更新知识百科 {{ buildJob.done }}/{{ buildJob.total }}</span>
        <span v-if="buildJob.failed">失败 {{ buildJob.failed }}</span>
      </div>
      <div class="kw-build-progress__bar">
        <i :style="{ width: `${buildProgress}%` }"></i>
      </div>
      <p v-if="buildJob.currentTitle">正在整理：{{ buildJob.currentTitle }}</p>
      <p>切换页面不会中断；回到知识百科会自动恢复进度。</p>
    </div>

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
        <svg class="kw-map__svg" viewBox="0 0 1000 640" aria-label="知识图谱：每个主题页一个节点">
          <defs>
            <marker id="kw-arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#aeb5c0" />
            </marker>
            <marker id="kw-arrow-hl" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">
              <path d="M0,0 L10,3 L0,6 L2,3 Z" fill="#7e94bf" />
            </marker>
          </defs>
          <g :transform="`translate(${mapView.x} ${mapView.y}) scale(${mapView.scale})`">
            <path v-for="hull in mapHulls" :key="hull.key" :d="hull.path" class="kw-map-hull"
              :class="{ 'is-hovered': mapHoveredId && hull.ids.includes(String(mapHoveredId)) }" />
            <line v-for="edge in mapEdges" :key="edge.key" :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              class="kw-map-edge" :class="[`is-${edge.type}`, { 'is-active': isMapEdgeActive(edge), 'is-dimmed': isMapEdgeDimmed(edge) }]"
              :marker-end="isMapEdgeActive(edge) ? 'url(#kw-arrow-hl)' : 'url(#kw-arrow)'" />
            <g v-for="node in mapNodes" :key="node.id" class="kw-map-node"
              :class="{ 'is-selected': isMapSelected(node), 'is-hovered': mapHoveredId === String(node.id), 'is-dimmed': isMapNodeDimmed(node) }"
              :transform="`translate(${node.x} ${node.y})`"
              @mouseenter="mapHoveredId = String(node.id)" @mouseleave="mapHoveredId = null"
              @pointerdown.stop="onMapNodeDown($event, node)" @pointerup.stop @click.stop="onMapNodeClick(node)">
              <circle class="kw-map-node__halo" :r="node.r + 8" />
              <circle v-if="isMapSelected(node)" class="kw-map-node__active" :r="node.r + 7" :stroke="node.color" />
              <circle class="kw-map-node__dot" :r="node.r + (isMapSelected(node) || mapHoveredId === String(node.id) ? 3 : 0)" :fill="node.color" />
              <text v-if="showMapLabel(node)" class="kw-map-node__label" text-anchor="middle" :y="node.r + 14">{{ node.title }}</text>
            </g>
          </g>
        </svg>
        <div class="kw-map__legend">
          <span v-for="item in pageTypeLegend" :key="item.type"><i :class="`is-${item.type}`"></i>{{ item.label }}</span>
          <em>滚轮缩放 · 空白处拖拽平移 · 点节点打开主题页</em>
        </div>
      </div>
    </template>

    <div v-else class="kw-empty">
      <div class="kw-empty__art">◇</div>
      <h3>这个资料夹还没有知识百科</h3>
      <p>先生成知识图谱，再把图谱里的概念整理成可读主题页。不会补充资料里没有的内容。</p>
      <el-button class="kw-build-btn" type="primary" :loading="building || buildActive" :disabled="!activeKbId || buildActive" @click="build">
        {{ buildActive ? `更新中 ${buildJob.done}/${buildJob.total}` : '生成知识百科' }}
      </el-button>
    </div>

    <el-drawer v-model="detailVisible" size="620px" :with-header="false" :modal="false" append-to-body class="kw-detail-drawer">
      <div v-if="pageLoading" class="kw-detail-loading" v-loading="true"></div>
      <div v-else-if="activePage" class="kw-detail">
        <header class="kw-detail__head">
          <div>
            <div class="kw-kicker">KNOWLEDGE PAGE</div>
            <h2>{{ activePage.title }}</h2>
            <div class="kw-detail__badges">
              <span class="kw-detail__type" :style="{ color: pageTypeMeta(activePage.pageType).color }">{{ pageTypeLabel(activePage.pageType) }}</span>
              <span>{{ activePage.sources?.length || 0 }} 条来源</span>
              <span>{{ activePage.linkStats?.outCount || 0 }} 条出链</span>
              <span>{{ activePage.linkStats?.inCount || 0 }} 条反链</span>
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
        <LatexRenderer :content="activePage.summary" wiki-mode class="kw-detail__lead"
          @wiki-link-click="openPage" />

        <section v-for="(section, index) in activePage.sections || []" :key="`${index}-${section.heading}`" class="kw-detail__section">
          <h3>{{ section.heading }}</h3>
          <LatexRenderer :content="section.body" wiki-mode class="kw-detail__body"
            @wiki-link-click="openPage" />
        </section>

        <section class="kw-detail__block kw-link-block">
          <div class="kw-detail__block-head">
            <span>页面链接</span>
            <b>{{ activePage.linkStats?.outCount || 0 }} 出 / {{ activePage.linkStats?.inCount || 0 }} 入</b>
            <el-button size="small" text type="primary" @click="openLinkDialog">添加页面链接</el-button>
            <el-button size="small" text type="primary" :loading="linkRefreshing" @click="refreshLinks">刷新链接</el-button>
          </div>
          <div v-if="activePage.outLinks?.length" class="kw-link-group">
            <div class="kw-link-group__label">本页链接到</div>
            <div class="kw-link-list">
              <div v-for="item in activePage.outLinks" :key="`out-${item.pageId}-${item.sectionIndex}-${item.anchorText}`"
                class="kw-link-item">
                <button type="button" class="kw-link-main" @click="openPage(item.pageId)">
                  <b>{{ item.title }}</b>
                  <span>“{{ item.anchorText }}”</span>
                  <em>{{ sectionLabel(item.sectionIndex) }}</em>
                </button>
                <button type="button" class="kw-link-remove" title="移除这条链接"
                  @click="removeLink(item)">×</button>
              </div>
            </div>
          </div>
          <div v-if="activePage.inLinks?.length" class="kw-link-group">
            <div class="kw-link-group__label">反向链接</div>
            <div class="kw-link-list">
              <button v-for="item in activePage.inLinks" :key="`in-${item.pageId}-${item.sectionIndex}-${item.anchorText}`"
                type="button" class="kw-link-main" @click="openPage(item.pageId)">
                <b>{{ item.title }}</b>
                <span>“{{ item.anchorText }}”</span>
                <em>{{ sectionLabel(item.sectionIndex) }}</em>
              </button>
            </div>
          </div>
          <div v-if="!activePage.outLinks?.length && !activePage.inLinks?.length" class="kw-image-empty">
            正文里还没有页面链接。点击「添加页面链接」，或先在正文里写上目标主题名。
          </div>
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
          <div class="kw-detail__block-head"><span>来源</span><b>{{ activePage.sourceDocIds?.length || 0 }} 份资料 · {{ activePage.sources.length }} 个片段</b></div>
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

    <el-dialog v-model="linkDialogVisible" title="添加页面链接" width="540px" append-to-body>
      <div class="kw-link-dialog">
        <p class="kw-link-dialog__hint">链接的锚文本必须已经出现在本页正文里；保存后会变成绿色下划线，点击就能跳到目标主题页。</p>
        <label class="kw-link-dialog__label">目标主题页</label>
        <el-select v-model="linkForm.targetPageId" filterable placeholder="选择一个主题页" style="width: 100%"
          @change="onLinkTargetChange">
          <el-option v-for="page in linkTargets" :key="page.pageId" :label="page.title" :value="page.pageId" />
        </el-select>
        <label class="kw-link-dialog__label">正文锚文本</label>
        <el-input v-model="linkForm.anchorText" maxlength="120" show-word-limit
          placeholder="例如：智能体" />
        <label class="kw-link-dialog__label">添加位置</label>
        <el-select v-model="linkForm.sectionIndex" style="width: 100%">
          <el-option label="摘要" :value="-1" />
          <el-option v-for="(section, index) in activePage?.sections || []" :key="index"
            :label="`第 ${index + 1} 节 · ${section.heading}`" :value="index" />
        </el-select>
      </div>
      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="linkSaving" :disabled="!linkForm.targetPageId || !linkForm.anchorText.trim()"
          @click="addLink">添加链接</el-button>
      </template>
    </el-dialog>

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
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import KnowledgeWikiEditor from './KnowledgeWikiEditor.vue'
import {
  addWikiPageLink,
  attachWikiImage,
  buildWikiPages,
  detachWikiImage,
  getLatestWikiBuildJob,
  getWikiBuildJob,
  getWikiGraph,
  getWikiPage,
  listGalleryAssets,
  listWikiPages,
  listWikiRevisions,
  refreshWikiPageLinks,
  removeWikiPageLink,
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

const PAGE_TYPE_META = [
  { type: 'summary', label: '摘要', color: '#3B7CFF' },
  { type: 'entity', label: '实体', color: '#2F9E8F' },
  { type: 'concept', label: '概念', color: '#F08A24' },
  { type: 'synthesis', label: '综合', color: '#2D8CF0' },
  { type: 'comparison', label: '对比', color: '#D95757' },
  { type: 'overview', label: '总览', color: '#8A94A6' }
]

const loading = ref(false)
const building = ref(false)
const buildJob = ref<any>(null)
const pages = ref<any[]>([])
const stats = reactive({ pageCount: 0, docCount: 0, staleCount: 0, linkCount: 0 })
const linkDialogVisible = ref(false)
const linkSaving = ref(false)
const linkRefreshing = ref(false)
const linkForm = reactive<{ targetPageId: number | null; anchorText: string; sectionIndex: number }>({
  targetPageId: null,
  anchorText: '',
  sectionIndex: -1
})
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
const mapHoveredId = ref<string | null>(null)
const mapSelectedPageId = ref<number | null>(null)
const mapNodeOffsets = reactive<Record<string, { x: number; y: number }>>({})
let mapDrag: any = null
let mapNodeDrag: any = null
let suppressMapNodeClick = false

const filteredPages = computed(() => {
  const query = String(props.searchQuery || '').trim().toLowerCase()
  if (!query) return pages.value
  return pages.value.filter((page: any) =>
    `${page.title || ''} ${page.summary || ''}`.toLowerCase().includes(query)
  )
})

const linkTargets = computed(() =>
  pages.value.filter((page: any) => Number(page.pageId) !== Number(activePage.value?.pageId))
)

const buildActive = computed(() => buildJob.value?.status === 'running')
const buildProgress = computed(() => {
  const total = Number(buildJob.value?.total || 0)
  const done = Number(buildJob.value?.done || 0)
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})

const pageTypeLegend = computed(() =>
  PAGE_TYPE_META.filter((item) => item.type !== 'overview')
)

function normalizePageType(value?: string) {
  const type = String(value || '').trim()
  if (type === 'topic' || !type) return 'concept'
  return type
}

function pageTypeMeta(value?: string) {
  const type = normalizePageType(value)
  return PAGE_TYPE_META.find((item) => item.type === type) || PAGE_TYPE_META[2]
}

function pageTypeLabel(value?: string) {
  return pageTypeMeta(value).label
}

const mapNodes = computed(() => {
  const nodes = mapGraph.value?.nodes || []
  const total = nodes.length
  const sorted = [...nodes].sort((a: any, b: any) => Number(b.degree || 0) - Number(a.degree || 0))
  const hubId = total <= 12 ? String(sorted[0]?.id ?? '') : ''
  const orbit = nodes.filter((node: any) => String(node.id) !== hubId)
  let orbitIndex = 0
  return nodes.map((node: any) => {
    const degree = Number(node.degree || 0)
    const pageType = normalizePageType(node.pageType)
    let x = 500
    let y = 320
    if (String(node.id) === hubId) {
      x = 500
      y = 320
    } else if (total <= 12) {
      const angle = -Math.PI / 2 + (Math.PI * 2 * orbitIndex) / Math.max(1, orbit.length)
      x = 500 + Math.cos(angle) * 225
      y = 320 + Math.sin(angle) * 225
      orbitIndex += 1
    } else {
      const index = nodes.indexOf(node)
      const ring = index < 8 ? 0 : 1
      const count = ring === 0 ? Math.min(8, total) : Math.max(1, total - 8)
      const localIndex = ring === 0 ? index : index - Math.min(8, total)
      const angle = -Math.PI / 2 + (Math.PI * 2 * localIndex) / Math.max(1, count)
      const radius = ring === 0 ? 145 : 272
      x = 500 + Math.cos(angle) * radius
      y = 320 + Math.sin(angle) * radius
    }
    const offset = mapNodeOffsets[String(node.id)]
    return {
      ...node,
      pageType,
      x: offset?.x ?? x,
      y: offset?.y ?? y,
      // 与 WeKnora 的 graphNodeRadius 同一条公式：叶子小、枢纽大。
      r: Math.max(5, Math.min(20, 4 + Math.sqrt(Math.max(0, degree)) * 1.8)),
      color: pageTypeMeta(pageType).color
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
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.hypot(dx, dy) || 1
      const ux = dx / distance
      const uy = dy / distance
      const startPad = Number(source.r || 5) + 5
      const endPad = Number(target.r || 5) + 7
      return {
        key: `${edge.source}-${edge.target}-${edge.type}`,
        source: String(edge.source),
        target: String(edge.target),
        x1: source.x + ux * startPad,
        y1: source.y + uy * startPad,
        x2: target.x - ux * endPad,
        y2: target.y - uy * endPad,
        type: edge.type || 'related'
      }
    })
    .filter(Boolean)
})

const mapNeighborIds = computed(() => {
  const id = mapHoveredId.value
  const result = new Set<string>()
  if (!id) return result
  result.add(id)
  for (const edge of mapEdges.value) {
    if (edge.source === id) result.add(edge.target)
    if (edge.target === id) result.add(edge.source)
  }
  return result
})

function isMapSelected(node: any) {
  return Number(node.pageId) === Number(mapSelectedPageId.value)
}

function isMapNodeDimmed(node: any) {
  return !!mapHoveredId.value && !mapNeighborIds.value.has(String(node.id))
}

function isMapEdgeActive(edge: any) {
  return !!mapHoveredId.value && (edge.source === mapHoveredId.value || edge.target === mapHoveredId.value)
}

function isMapEdgeDimmed(edge: any) {
  return !!mapHoveredId.value && !isMapEdgeActive(edge)
}

function showMapLabel(node: any) {
  return (
    isMapSelected(node) ||
    mapHoveredId.value === String(node.id) ||
    mapView.scale >= 0.72 ||
    Number(node.degree || 0) >= 3
  )
}

function selectMapNode(node: any) {
  mapSelectedPageId.value = Number(node.pageId)
  // 点击节点后把它移到画布左侧中央，右侧留给详情抽屉（与 WeKnora 一致）。
  mapView.x = 330 - Number(node.x) * mapView.scale
  mapView.y = 320 - Number(node.y) * mapView.scale
  openPage(Number(node.pageId))
}

function onMapNodeClick(node: any) {
  if (suppressMapNodeClick || mapNodeDrag?.moved) {
    suppressMapNodeClick = false
    mapNodeDrag = null
    return
  }
  selectMapNode(node)
}

function onMapNodeDown(event: PointerEvent, node: any) {
  if (event.button !== 0) return
  suppressMapNodeClick = false
  mapNodeDrag = {
    node,
    nodeId: String(node.id),
    startX: event.clientX,
    startY: event.clientY,
    origX: Number(node.x),
    origY: Number(node.y),
    moved: false
  }
  window.addEventListener('pointermove', onMapNodeMove)
  window.addEventListener('pointerup', onMapNodeUp)
}

function onMapNodeMove(event: PointerEvent) {
  if (!mapNodeDrag) return
  const dx = (event.clientX - mapNodeDrag.startX) / mapView.scale
  const dy = (event.clientY - mapNodeDrag.startY) / mapView.scale
  if (Math.abs(dx) + Math.abs(dy) > 4) mapNodeDrag.moved = true
  mapNodeOffsets[mapNodeDrag.nodeId] = {
    x: Math.max(30, Math.min(970, mapNodeDrag.origX + dx)),
    y: Math.max(30, Math.min(610, mapNodeDrag.origY + dy))
  }
}

function onMapNodeUp() {
  if (!mapNodeDrag) return
  const state = mapNodeDrag
  mapNodeDrag = null
  window.removeEventListener('pointermove', onMapNodeMove)
  window.removeEventListener('pointerup', onMapNodeUp)
  if (state.moved) {
    // 拖拽结束后浏览器仍会补发一次 click；暂时压掉，避免误打开详情。
    suppressMapNodeClick = true
    window.setTimeout(() => { suppressMapNodeClick = false }, 80)
  }
}

function stopMapNodeDrag() {
  mapNodeDrag = null
  suppressMapNodeClick = false
  window.removeEventListener('pointermove', onMapNodeMove)
  window.removeEventListener('pointerup', onMapNodeUp)
}

function clusterOutline(points: any[]) {
  if (!points.length) return ''
  const samples = 20
  const expanded = points.flatMap((p) => {
    const radius = Number(p.r || 0) + 20
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

const mapHulls = computed(() => {
  const nodes = mapNodes.value
  if (!nodes.length) return []
  const byId = new Map(nodes.map((node: any) => [String(node.id), node]))
  const adjacency = new Map<string, string[]>()
  for (const node of nodes) adjacency.set(String(node.id), [])
  for (const edge of mapEdges.value) {
    adjacency.get(edge.source)?.push(edge.target)
    adjacency.get(edge.target)?.push(edge.source)
  }
  const visited = new Set<string>()
  const hulls: any[] = []
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
    if (component.length < 2) continue
    const points = component.map((id) => byId.get(id)).filter(Boolean)
    hulls.push({ key: component[0], ids: component, path: clusterOutline(points) })
  }
  return hulls
})

function statusLabel(status: string) {
  if (status === 'stale') return '待更新'
  if (status === 'failed') return '生成失败'
  if (status === 'draft') return '整理中'
  return '已整理'
}

function sectionLabel(index: number) {
  return Number(index) < 0 ? '摘要' : `第 ${Number(index) + 1} 节`
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

let buildTimer: ReturnType<typeof setInterval> | null = null

function stopBuildPolling() {
  if (buildTimer) {
    clearInterval(buildTimer)
    buildTimer = null
  }
}

function startBuildPolling(jobId: number) {
  stopBuildPolling()
  buildTimer = setInterval(async () => {
    try {
      const res = await getWikiBuildJob(jobId)
      if (res.code !== 200 || !res.data) return
      buildJob.value = res.data
      if (res.data.status !== 'running') {
        stopBuildPolling()
        await reload()
        if (res.data.status === 'failed') {
          ElMessage.error(res.data.error || '知识百科生成失败')
        } else if (Number(res.data.failed || 0)) {
          ElMessage.warning(`已整理 ${res.data.done || 0} 个主题，${res.data.failed} 个生成失败`)
        } else {
          ElMessage.success(`已整理 ${res.data.done || 0} 个主题页`)
        }
      }
    } catch (error: any) {
      // 网络短暂抖动不立刻结束进度；组件卸载时会清理定时器
      console.warn('[wiki] build job poll failed', error)
    }
  }, 1500)
}

async function resumeBuildJob() {
  try {
    const res = await getLatestWikiBuildJob(props.activeKbId || undefined)
    const job = res.code === 200 ? res.data : null
    if (job?.status === 'running') {
      buildJob.value = job
      startBuildPolling(job.jobId)
    }
  } catch {
    // 恢复失败不影响知识百科本身
  }
}

async function build() {
  if (!props.activeKbId || building.value || buildActive.value) return
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
    if (data.jobId) {
      buildJob.value = data
      if (data.status === 'running') {
        ElMessage.info(res.msg || '已开始更新知识百科，切换页面不会中断')
        startBuildPolling(data.jobId)
      } else {
        await reload()
      }
      return
    }
    // 兼容旧后端：没有 jobId 时按原同步结果处理
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

function resetMapNodeOffsets() {
  Object.keys(mapNodeOffsets).forEach((key) => delete mapNodeOffsets[key])
}

async function switchMap() {
  if (!pages.value.length) return
  view.value = 'map'
  resetMapNodeOffsets()
  try {
    const res = await getWikiGraph(Number(props.activeKbId))
    if (res.code === 200) mapGraph.value = res.data || { nodes: [], edges: [] }
  } catch {
    // 地图失败时保持主题页入口，不影响阅读。
    view.value = 'pages'
  }
}

async function openPage(pageId: number) {
  mapSelectedPageId.value = Number(pageId)
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

function openLinkDialog() {
  linkForm.targetPageId = null
  linkForm.anchorText = ''
  linkForm.sectionIndex = activePage.value?.sections?.length ? 0 : -1
  linkDialogVisible.value = true
}

function onLinkTargetChange(value: number) {
  const target = linkTargets.value.find((page: any) => Number(page.pageId) === Number(value))
  if (target && !linkForm.anchorText.trim()) linkForm.anchorText = String(target.title || '')
}

async function addLink() {
  if (!activePage.value || !linkForm.targetPageId || !linkForm.anchorText.trim()) return
  linkSaving.value = true
  try {
    const res = await addWikiPageLink(activePage.value.pageId, {
      targetPageId: Number(linkForm.targetPageId),
      anchorText: linkForm.anchorText.trim(),
      sectionIndex: linkForm.sectionIndex
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '添加页面链接失败')
      return
    }
    activePage.value = res.data
    linkDialogVisible.value = false
    await reload()
    ElMessage.success('页面链接已添加')
  } catch (error: any) {
    ElMessage.error('添加页面链接失败：' + (error?.message || error))
  } finally {
    linkSaving.value = false
  }
}

async function removeLink(item: any) {
  if (!activePage.value) return
  try {
    await ElMessageBox.confirm(
      `移除「${item.title}」这条页面链接？正文会保留锚文本，只去掉跳转。`,
      '移除页面链接',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' }
    )
    const res = await removeWikiPageLink(activePage.value.pageId, {
      targetPageId: Number(item.pageId),
      anchorText: item.anchorText,
      sectionIndex: Number(item.sectionIndex)
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '移除页面链接失败')
      return
    }
    activePage.value = res.data
    await reload()
    ElMessage.success('页面链接已移除')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error('移除页面链接失败：' + (error?.message || error))
  }
}

async function refreshLinks() {
  if (!activePage.value) return
  linkRefreshing.value = true
  try {
    const res = await refreshWikiPageLinks(activePage.value.pageId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '刷新页面链接失败')
      return
    }
    activePage.value = res.data
    await reload()
    ElMessage.success(`页面链接已刷新，新增 ${res.data?.refreshStats?.links ?? 0} 条`)
  } catch (error: any) {
    ElMessage.error('刷新页面链接失败：' + (error?.message || error))
  } finally {
    linkRefreshing.value = false
  }
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
  const pageId = activePage.value.pageId
  const kbId = activePage.value.kbId
  const pageRef = `知识百科主题页《${title}》（pageId=${pageId}，kbId=${kbId}）`
  const prompt = kind === 'practice'
    ? `请基于${pageRef}生成 5 道练习题，并在每题后标出对应的主题页小节和原文来源。`
    : `请基于${pageRef}回答我，并在回答里标出引用的主题页和原文来源。`
  emit('ask', prompt)
  detailVisible.value = false
}

function onMapWheel(event: WheelEvent) {
  const rect = mapCanvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const px = event.clientX - rect.left
  const py = event.clientY - rect.top
  const old = mapView.scale
  const next = Math.max(0.35, Math.min(3, old * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
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

watch(() => props.activeKbId, async () => {
  stopBuildPolling()
  stopMapNodeDrag()
  resetMapNodeOffsets()
  buildJob.value = null
  await reload()
  await resumeBuildJob()
})
onMounted(async () => {
  await reload()
  await resumeBuildJob()
})
onBeforeUnmount(() => {
  stopBuildPolling()
  stopMapNodeDrag()
})
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
.kw-build-progress {
  padding: 9px 12px;
  border: 1px solid #e2e9fb;
  border-radius: 8px;
  background: #f8faff;
}
.kw-build-progress__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #2f5fce;
  font-size: 11px;
  font-weight: 600;
}
.kw-build-progress__top span:last-child { color: #d97706; font-weight: 400; }
.kw-build-progress__bar {
  height: 5px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 99px;
  background: #e7edfb;
}
.kw-build-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #6f8df2, #2f5fce);
  transition: width .35s ease;
}
.kw-build-progress p { margin: 6px 0 0; color: #9aa1af; font-size: 10px; }
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
.kw-map-hull { fill: #f1f3f7; fill-opacity: 0.72; stroke: #e5e8ef; stroke-width: 1; vector-effect: non-scaling-stroke; transition: fill 0.2s ease, stroke 0.2s ease; }
.kw-map-hull.is-hovered { fill: #ebeef5; stroke: #dce2ed; }
.kw-map-edge { stroke: #c7d0e0; stroke-width: 0.8; opacity: 0.42; vector-effect: non-scaling-stroke; transition: stroke 0.2s, stroke-width 0.2s, stroke-opacity 0.2s; }
.kw-map-edge.is-part_of { stroke: #c7d0e0; }
.kw-map-edge.is-prerequisite { stroke: #73a6dd; stroke-dasharray: 4 4; }
.kw-map-edge.is-contrast { stroke: #d38e7d; stroke-dasharray: 3 5; }
.kw-map-edge.is-related { stroke: #c7d0e0; }
.kw-map-edge.is-mention { stroke: #77bfae; }
.kw-map-edge.is-active { stroke: #7e94bf; stroke-width: 1.5; opacity: 0.85; }
.kw-map-edge.is-dimmed { opacity: 0.08; }
.kw-map-node { cursor: grab; transition: opacity 0.18s ease; }
.kw-map-node:active { cursor: grabbing; }
.kw-map-node.is-dimmed { opacity: 0.2; }
.kw-map-node__halo { fill: rgba(255, 255, 255, 0.86); }
.kw-map-node__dot { stroke: #fff; stroke-width: 1.5; transition: r 0.2s ease, stroke-width 0.2s ease, opacity 0.2s ease; }
.kw-map-node__active { fill: none; stroke-width: 2; pointer-events: none; transform-box: fill-box; transform-origin: center; animation: kw-node-pulse 1.5s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite; }
.kw-map-node__label { fill: #4b5563; font-size: 11px; pointer-events: none; paint-order: stroke; stroke: #fff; stroke-width: 3px; stroke-linejoin: round; }
.kw-map-node.is-hovered .kw-map-node__dot { stroke: #253247; stroke-width: 2.5; }
.kw-map-node.is-hovered .kw-map-node__label { fill: #1f2937; font-weight: 600; }
@keyframes kw-node-pulse {
  0% { opacity: 0.8; transform: scale(1); }
  100% { opacity: 0; transform: scale(1.6); }
}
.kw-map__legend { position: absolute; right: 14px; bottom: 12px; display: flex; align-items: center; flex-wrap: wrap; gap: 10px; max-width: calc(100% - 28px); padding: 6px 9px; border: 1px solid rgba(15, 23, 42, 0.05); border-radius: 7px; background: rgba(255, 255, 255, 0.88); color: #7d8596; font-size: 9.5px; pointer-events: none; }
.kw-map__legend span { display: inline-flex; align-items: center; gap: 4px; }
.kw-map__legend i { width: 7px; height: 7px; border-radius: 50%; background: #c9d4e5; }
.kw-map__legend i.is-summary { background: #3b7cff; }
.kw-map__legend i.is-entity { background: #2f9e8f; }
.kw-map__legend i.is-concept { background: #f08a24; }
.kw-map__legend i.is-synthesis { background: #2d8cf0; }
.kw-map__legend i.is-comparison { background: #d95757; }
.kw-map__legend i.is-overview { background: #8a94a6; }
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
.kw-link-block .kw-detail__block-head { gap: 8px; }
.kw-link-block .kw-detail__block-head > span:first-child { margin-right: auto; }
.kw-link-group { margin-top: 9px; }
.kw-link-group__label { margin-bottom: 5px; color: #9aa1af; font-size: 9.5px; font-weight: 600; }
.kw-link-list { display: flex; flex-direction: column; gap: 5px; }
.kw-link-item { display: flex; align-items: center; gap: 5px; }
.kw-link-main { display: flex; min-width: 0; flex: 1; align-items: center; gap: 7px; padding: 7px 9px; border: 1px solid #e7f2ee; border-radius: 8px; background: #fbfefd; color: #4b5563; cursor: pointer; font-size: 10.5px; text-align: left; }
.kw-link-main:hover { border-color: #b9dfd5; background: #f1fbf8; }
.kw-link-main b { overflow: hidden; max-width: 42%; color: #256e5d; text-overflow: ellipsis; white-space: nowrap; }
.kw-link-main span { overflow: hidden; color: #7d8596; text-overflow: ellipsis; white-space: nowrap; }
.kw-link-main em { flex: none; margin-left: auto; color: #a0a6b2; font-style: normal; font-size: 9px; }
.kw-link-remove { flex: none; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; color: #b26a7f; background: transparent; cursor: pointer; font-size: 16px; line-height: 1; }
.kw-link-remove:hover { background: #fff1f5; }
.kw-link-dialog { display: flex; flex-direction: column; gap: 7px; }
.kw-link-dialog__hint { margin: 0 0 3px; padding: 8px 10px; border-radius: 7px; color: #6b7280; background: #f6fbf9; font-size: 11px; line-height: 1.65; }
.kw-link-dialog__label { margin-top: 4px; color: #4b5563; font-size: 11px; font-weight: 600; }
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
