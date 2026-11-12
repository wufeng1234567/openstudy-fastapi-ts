<template>
  <section class="gallery-page">
    <div class="gallery-toolbar">
      <div class="gallery-toolbar__filters">
        <div class="gallery-scope-tabs">
          <button type="button" :class="{ 'is-active': scope === 'current' }" @click="setScope('current')">
            当前资料夹
          </button>
          <button type="button" :class="{ 'is-active': scope === 'all' }" @click="setScope('all')">
            全部资料
          </button>
        </div>
        <span class="gallery-toolbar__divider"></span>
        <button
          v-for="item in sources"
          :key="item.key"
          type="button"
          class="gallery-source-tab"
          :class="{ 'is-active': sourceFilter === item.key }"
          @click="setSource(item.key)"
        >
          {{ item.label }}
          <span>{{ item.count }}</span>
        </button>
        <el-select v-model="docFilter" class="gallery-doc-filter" size="small" clearable filterable
          popper-class="gallery-doc-filter-popper"
          placeholder="按文档筛选" @change="() => reload()">
          <el-option v-for="doc in documentOptions" :key="doc.docId"
            :label="`${doc.fileName}（${doc.count}）`" :value="doc.docId" />
        </el-select>
        <span class="gallery-toolbar__hint">
          已描述 {{ stats.described }} · 待补 {{ stats.pending }} · 描述只在点击时生成
        </span>
      </div>
      <div v-if="jobActive" class="gallery-describe-progress">
        <div class="gallery-describe-progress__top">
          <span>正在生成图片描述 {{ describeJob.done }}/{{ describeJob.total }}</span>
          <span v-if="describeJob.failed">失败 {{ describeJob.failed }}</span>
        </div>
        <div class="gallery-describe-progress__bar">
          <i :style="{ width: `${jobProgress}%` }"></i>
        </div>
        <p>切换页面不会中断；回到画廊会自动恢复进度。</p>
      </div>
    </div>

    <!-- 描述按钮挂到页面顶部的搜索框旁；样式沿用 context bar 的轻量文字按钮。 -->
    <Teleport to="#workspace-gallery-describe">
      <el-button
        class="gallery-describe-trigger"
        text
        size="small"
        :loading="describing || jobActive"
        :disabled="!pendingKeys.length && !jobActive"
        @click="describePending"
      >
        <el-icon><MagicStick /></el-icon>
        {{ jobActive ? `补全中 ${describeJob.done}/${describeJob.total}` : pendingKeys.length ? `补全描述（${Math.min(pendingKeys.length, 40)}）` : '图片已描述' }}
      </el-button>
    </Teleport>

    <div v-if="loading" class="gallery-grid gallery-grid--loading">
      <div v-for="i in 8" :key="i" class="gallery-skeleton"></div>
    </div>

    <div v-else-if="displayItems.length" class="gallery-grid">
      <article
        v-for="item in displayItems"
        :key="item.assetKey"
        class="gallery-card"
        tabindex="0"
        @click="openDetail(item)"
        @keydown.enter="openDetail(item)"
      >
        <div class="gallery-card__media">
          <el-image :src="displayUrl(item.url)" fit="cover" lazy>
            <template #placeholder>
              <div class="gallery-card__img-empty">图片加载中…</div>
            </template>
            <template #error>
              <div class="gallery-card__img-empty">原图暂不可用</div>
            </template>
          </el-image>
          <div class="gallery-card__hover">
            <span>查看详情</span>
          </div>
        </div>
        <div class="gallery-card__body">
          <p class="gallery-card__caption" :class="{ 'is-muted': !item.displayName }">
            {{ item.displayName || item.fileName || '未命名图片' }}
          </p>
          <div class="gallery-card__source">
            <span class="gallery-card__source-name" :title="item.sourceName">{{ item.sourceName }}</span>
            <span v-if="item.sectionTitle" class="gallery-card__section">{{ item.sectionTitle }}</span>
          </div>
          <div class="gallery-card__foot">
            <span class="gallery-card__state" :class="`is-${item.descriptionStatus}`">{{ statusLabel(item.descriptionStatus) }}</span>
            <span>{{ item.usedCount ? `已用于 ${item.usedCount} 处` : item.referenceCount ? `${item.referenceCount} 条引用` : item.ocrText ? '含 OCR' : '未使用' }}</span>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="gallery-empty">
      <div class="gallery-empty__art"><el-icon><Picture /></el-icon></div>
      <h3>{{ hasFilter ? '没有匹配的图片' : '画廊还没有图片' }}</h3>
      <p>{{ hasFilter ? '换个关键词，或切回「全部图片」。' : '上传带图片的课件、真题，或直接在对话里贴图，这里会自动汇总。' }}</p>
      <el-button v-if="hasFilter" plain @click="clearFilters">清空筛选</el-button>
      <el-button v-else text @click="emit('back')">回到资料夹上传</el-button>
    </div>

    <GalleryViewer
      :visible="viewerVisible"
      :items="displayItems"
      :index="viewerIndex"
      @close="closeViewer"
      @select="selectViewer"
      @describe="describeViewerItem"
      @insert-question="(item) => viewerUseImage(item, 'question')"
      @insert-note="(item) => viewerUseImage(item, 'note')"
      @insert-wiki="viewerOpenWiki"
      @locate="locate"
    />

    <GalleryDetailDrawer
      v-model:visible="detailVisible"
      :detail="detail"
      :describing-one="describingOne"
      :display-url="displayUrl"
      :kind-label="kindLabel"
      :status-label="statusLabel"
      @describe="describeOne"
      @locate="locate"
      @use-question="(item) => useImage(item, 'question')"
      @use-note="(item) => useImage(item, 'note')"
      @insert-wiki="openWikiPicker"
    />

    <el-dialog v-model="wikiPickerVisible" title="插入知识百科主题页" width="560px" append-to-body>
      <div v-loading="wikiLoading" class="gallery-wiki-picker">
        <button v-for="page in wikiPages" :key="page.pageId" type="button" class="gallery-wiki-pick"
          :disabled="insertingWiki" @click="insertToWiki(page)">
          <b>{{ page.title }}</b>
          <span>{{ page.summary || '打开主题页查看内容' }}</span>
        </button>
        <div v-if="!wikiLoading && !wikiPages.length" class="gallery-wiki-empty">
          当前资料夹还没有知识百科主题页，先去「知识百科」生成一页。
        </div>
      </div>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Picture } from '@element-plus/icons-vue'
import GalleryViewer from './GalleryViewer.vue'
import GalleryDetailDrawer from './GalleryDetailDrawer.vue'
import { displayUrl, hasGalleryFilter, kindLabel, statusLabel } from './galleryUtils'
import {
  createContentReference,
  describeGalleryAssets,
  getGalleryAsset,
  getGalleryDescribeJob,
  getLatestGalleryDescribeJob,
  listGalleryAssets,
  listWikiPages
} from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  activeKbName?: string
  searchQuery?: string
  filters?: Record<string, any>
  focusAssetKey?: string
}>()

const emit = defineEmits<{
  (e: 'use-image', image: any): void
  (e: 'locate', payload: { docId: number; offset: number; targetText?: string }): void
  (e: 'back'): void
  (e: 'stats', payload: { total: number }): void
  (e: 'update:searchQuery', value: string): void
}>()

const loading = ref(false)
const items = ref<any[]>([])
const sources = ref<Array<{ key: string; label: string; count: number }>>([
  { key: 'all', label: '全部图片', count: 0 },
  { key: 'document', label: '文档图片', count: 0 },
  { key: 'upload', label: '独立图片', count: 0 },
  { key: 'chat', label: '聊天图片', count: 0 }
])
const stats = reactive({ total: 0, described: 0, pending: 0, failed: 0, used: 0 })
const query = ref(props.searchQuery || '')
const scope = ref<'current' | 'all'>('current')
const sourceFilter = ref<'all' | 'document' | 'upload' | 'chat'>('all')
const docFilter = ref<number | null>(null)
const documentOptions = ref<Array<{ docId: number; fileName: string; count: number }>>([])
const describing = ref(false)
const describeJob = ref<any>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)
const viewerVisible = ref(false)
const viewerIndex = ref(0)
const describingOne = ref(false)
const wikiPickerVisible = ref(false)
const wikiLoading = ref(false)
const wikiPages = ref<any[]>([])
const insertingWiki = ref(false)

const displayItems = computed(() => {
  const kinds = Array.isArray(props.filters?.kind) ? props.filters.kind : []
  const statuses = Array.isArray(props.filters?.descriptionStatus) ? props.filters.descriptionStatus : []
  return items.value.filter((item) => {
    if (kinds.length && !kinds.includes(item.kind)) return false
    if (statuses.length && !statuses.includes(item.descriptionStatus)) return false
    return true
  })
})

const pendingKeys = computed(() =>
  displayItems.value
    .filter((item) => item.descriptionStatus === 'pending' || item.descriptionStatus === 'failed')
    .map((item) => item.assetKey)
)
const jobActive = computed(() => describeJob.value?.status === 'running')
const jobProgress = computed(() => {
  const total = Number(describeJob.value?.total || 0)
  const done = Number(describeJob.value?.done || 0)
  return total ? Math.min(100, Math.round((done / total) * 100)) : 0
})
const hasFilter = computed(() =>
  hasGalleryFilter(query.value, sourceFilter.value, docFilter.value, props.filters || {})
)

function applyData(data: any) {
  items.value = data?.items || []
  const serverStats = data?.stats || {}
  stats.total = Number(serverStats.total || 0)
  stats.described = Number(serverStats.described || 0)
  stats.pending = Number(serverStats.pending || 0)
  stats.failed = Number(serverStats.failed || 0)
  stats.used = Number(serverStats.used || 0)
  if (Array.isArray(data?.sources) && data.sources.length) {
    sources.value = data.sources
  }
  documentOptions.value = Array.isArray(data?.documents) ? data.documents : []
  emit('stats', { total: stats.total })
}

async function reload(silent = false) {
  if (!silent) loading.value = true
  try {
    const res = await listGalleryAssets({
      scope: scope.value,
      kbId: scope.value === 'current' ? props.activeKbId : undefined,
      docId: docFilter.value,
      source: sourceFilter.value,
      status: 'all',
      q: query.value.trim(),
      limit: 300
    })
    if (res.code !== 200) {
      if (!silent) ElMessage.error(res.msg || '画廊加载失败')
      return
    }
    applyData(res.data)
  } catch (error: any) {
    if (!silent) ElMessage.error('画廊加载失败：' + (error?.message || error))
  } finally {
    if (!silent) loading.value = false
  }
}

function setScope(next: 'current' | 'all') {
  scope.value = next
  docFilter.value = null
  reload()
}

function setSource(source: 'all' | 'document' | 'upload' | 'chat') {
  sourceFilter.value = source
  if (source === 'chat') docFilter.value = null
  reload()
}

function clearFilters() {
  query.value = ''
  emit('update:searchQuery', '')
  sourceFilter.value = 'all'
  docFilter.value = null
  reload()
}

let describeTimer: ReturnType<typeof setInterval> | null = null
let describePollFailures = 0

function stopDescribePolling() {
  if (describeTimer) {
    clearInterval(describeTimer)
    describeTimer = null
  }
}

function startDescribePolling(jobId: number) {
  stopDescribePolling()
  describePollFailures = 0
  describeTimer = setInterval(async () => {
    try {
      const res = await getGalleryDescribeJob(jobId)
      if (res.code !== 200 || !res.data) return
      describePollFailures = 0
      describeJob.value = res.data
      // 同步刷新卡片状态，用户能看到每张图从「生成中」变成「已描述」
      await reload(true)
      if (res.data.status !== 'running') {
        stopDescribePolling()
        if (res.data.status === 'failed') {
          ElMessage.error(res.data.error || '图片描述任务失败')
        } else if (Number(res.data.failed || 0)) {
          ElMessage.warning(`完成 ${res.data.done || 0} 张，${res.data.failed} 张失败，可在详情里查看原因`)
        } else {
          ElMessage.success(`已为 ${res.data.done || 0} 张图片补上描述`)
        }
        if (detail.value?.assetKey) await loadDetail(detail.value.assetKey, false)
      }
    } catch (error: any) {
      // 后端重启/断网时不能无限转圈：连续 3 次失败就结束当前轮询并提示。
      describePollFailures += 1
      console.warn('[gallery] describe job poll failed', error)
      if (describePollFailures >= 3) {
        stopDescribePolling()
        describeJob.value = {
          ...(describeJob.value || {}),
          status: 'failed',
          error: '图片描述任务连接中断，请重新发起'
        }
        ElMessage.error('图片描述任务连接中断，请重新发起')
      }
    }
  }, 1500)
}

async function resumeDescribeJob() {
  try {
    const res = await getLatestGalleryDescribeJob()
    const job = res.code === 200 ? res.data : null
    if (job?.status === 'running') {
      describeJob.value = job
      startDescribePolling(job.jobId)
    }
  } catch {
    // 恢复进度失败不影响画廊本身
  }
}

async function describePending() {
  const keys = pendingKeys.value.slice(0, 40)
  if (!keys.length || jobActive.value) return
  describing.value = true
  describePollFailures = 0
  try {
    const res = await describeGalleryAssets({ assetKeys: keys, limit: 40 })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '生成图片描述失败')
      return
    }
    describeJob.value = res.data
    if (res.data?.jobId && res.data.status === 'running') {
      ElMessage.info(res.msg || '已开始生成图片描述，切换页面不会中断')
      startDescribePolling(res.data.jobId)
    } else {
      ElMessage.success(res.msg || '图片描述已完成')
      await reload()
    }
  } catch (error: any) {
    ElMessage.error('生成图片描述失败：' + (error?.message || error))
  } finally {
    describing.value = false
  }
}

async function openDetail(item: any) {
  const index = displayItems.value.findIndex((candidate: any) => candidate.assetKey === item.assetKey)
  viewerIndex.value = index >= 0 ? index : 0
  viewerVisible.value = true
  detail.value = item
}

function selectViewer(index: number) {
  if (!displayItems.value.length) return
  viewerIndex.value = Math.max(0, Math.min(displayItems.value.length - 1, index))
  detail.value = displayItems.value[viewerIndex.value]
}

function closeViewer() {
  viewerVisible.value = false
}

async function describeViewerItem(assetKey: string) {
  const item = displayItems.value.find((candidate: any) => candidate.assetKey === assetKey)
  if (!item) return
  detail.value = item
  await describeOne()
  await reload(true)
  const fresh = displayItems.value.find((candidate: any) => candidate.assetKey === assetKey)
  if (fresh) Object.assign(item, fresh)
}

function viewerUseImage(item: any, target: 'question' | 'note') {
  detail.value = item
  useImage(item, target)
}

function viewerOpenWiki(item: any) {
  detail.value = item
  void openWikiPicker()
}

async function loadDetail(assetKey: string, showLoading = true) {
  if (showLoading) detailLoading.value = true
  try {
    const res = await getGalleryAsset(assetKey)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '图片详情加载失败')
      return
    }
    detail.value = res.data
  } catch (error: any) {
    ElMessage.error('图片详情加载失败：' + (error?.message || error))
  } finally {
    detailLoading.value = false
  }
}

async function describeOne() {
  if (!detail.value?.assetKey) return
  describingOne.value = true
  try {
    const res = await describeGalleryAssets({ assetKeys: [detail.value.assetKey], limit: 1 })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '生成描述失败')
      return
    }
    describeJob.value = res.data
    if (res.data?.jobId && res.data.status === 'running') {
      startDescribePolling(res.data.jobId)
      ElMessage.info('已开始生成描述')
    } else {
      await loadDetail(detail.value.assetKey)
      await reload()
    }
  } catch (error: any) {
    ElMessage.error('生成描述失败：' + (error?.message || error))
  } finally {
    describingOne.value = false
  }
}

function imagePayload(item: any, target: 'question' | 'note') {
  const tail = String(item.assetKey || '').split(':').pop() || '1'
  return {
    ...item,
    url: displayUrl(item.url),
    rawUrl: item.url,
    docName: item.sourceName,
    seq: item.sourceType === 'chat' ? 1 : Number(tail) + 1,
    target
  }
}

function useImage(item: any, target: 'question' | 'note') {
  if (!item?.assetKey) return
  emit('use-image', imagePayload(item))
}

function locate(item: any) {
  if (!item?.docId || item?.offset == null) return
  emit('locate', {
    docId: Number(item.docId),
    offset: Number(item.offset),
    targetText: item.sectionTitle || ''
  })
}

async function openWikiPicker() {
  if (!detail.value?.assetKey) return
  wikiPickerVisible.value = true
  wikiLoading.value = true
  try {
    const res = await listWikiPages({ kbId: props.activeKbId || undefined })
    wikiPages.value = res.code === 200 ? (res.data?.pages || []) : []
  } catch {
    wikiPages.value = []
  } finally {
    wikiLoading.value = false
  }
}

async function insertToWiki(page: any) {
  if (!detail.value?.assetKey || !page?.pageId || insertingWiki.value) return
  const key = String(detail.value.assetKey)
  const parts = key.split(':')
  const isDoc = key.startsWith('doc:')
  const sourceType = isDoc ? 'document_image' : 'chat_image'
  const sourceId = Number(parts[1] || 0)
  const sourceSubId = isDoc ? parts[2] : undefined
  if (!sourceId) {
    ElMessage.error('这张图片缺少来源，暂时不能关联')
    return
  }
  insertingWiki.value = true
  try {
    const res = await createContentReference({
      sourceType,
      sourceId,
      sourceSubId,
      targetType: 'wiki_page',
      targetId: Number(page.pageId),
      quote: String(detail.value.caption || detail.value.surroundingText || detail.value.fileName || '').slice(0, 800)
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '插入知识百科失败')
      return
    }
    ElMessage.success(`已关联到《${page.title}》`)
    wikiPickerVisible.value = false
    await loadDetail(detail.value.assetKey, false)
  } catch (error: any) {
    ElMessage.error('插入知识百科失败：' + (error?.message || error))
  } finally {
    insertingWiki.value = false
  }
}

watch(
  () => [props.activeKbId, props.activeKbName],
  () => {
    if (scope.value === 'current') {
      docFilter.value = null
      reload()
    }
  }
)

watch(
  () => props.searchQuery,
  (value) => {
    query.value = value || ''
    reload()
  }
)

async function focusRequestedAsset() {
  const key = String(props.focusAssetKey || '')
  if (!key) return
  if (!items.value.length) await reload()
  const item = displayItems.value.find((candidate: any) => String(candidate.assetKey) === key)
  if (item) await openDetail(item)
}

watch(
  () => props.focusAssetKey,
  () => { void focusRequestedAsset() }
)

onMounted(async () => {
  await reload()
  await focusRequestedAsset()
  await resumeDescribeJob()
})

onBeforeUnmount(stopDescribePolling)
</script>

<style scoped src="./GalleryPanel.style1.css"></style>

<!--
  el-select 的 popper 默认挂到 body，scoped 样式命中不到。
  只约束「按文档筛选」这一个 popper，避免长文件名把下拉撑到 500px+。
-->
<style src="./GalleryPanel.style2.css"></style>
