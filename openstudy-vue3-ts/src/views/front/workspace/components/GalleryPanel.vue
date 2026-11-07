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
          <p class="gallery-card__caption" :class="{ 'is-muted': !item.caption }">
            {{ item.caption || '还没有描述，点开补一张索引' }}
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

    <el-drawer v-model="detailVisible" class="gallery-detail-drawer" size="560px" :with-header="false" append-to-body>
      <div v-if="detail" class="gallery-detail">
        <header class="gallery-detail__head">
          <div>
            <span class="gallery-kicker">IMAGE ASSET</span>
            <h3>{{ detail.fileName || '图片资产' }}</h3>
          </div>
          <button type="button" class="gallery-detail__close" @click="detailVisible = false">×</button>
        </header>

        <div class="gallery-detail__image">
          <el-image :src="displayUrl(detail.url)" fit="contain" :preview-src-list="[displayUrl(detail.url)]" preview-teleported />
        </div>

        <div class="gallery-detail__badges">
          <span class="gallery-kind">{{ kindLabel(detail.kind) }}</span>
          <span class="gallery-status" :class="`is-${detail.descriptionStatus}`">{{ statusLabel(detail.descriptionStatus) }}</span>
          <span v-if="detail.descriptionModel" class="gallery-detail__model">{{ detail.descriptionModel }}</span>
        </div>

        <section class="gallery-detail__section">
          <div class="gallery-detail__section-title">
            <span>图片描述</span>
            <el-button text size="small" :loading="describingOne" @click="describeOne">
              {{ detail.descriptionStatus === 'done' ? '重新描述' : '生成描述' }}
            </el-button>
          </div>
          <p class="gallery-detail__caption" :class="{ 'is-muted': !detail.caption }">
            {{ detail.caption || '这张图还没有生成描述。生成后会同时写入画廊索引和检索。' }}
          </p>
          <div v-if="detail.describeError" class="gallery-detail__error">{{ detail.describeError }}</div>
        </section>

        <section v-if="detail.ocrText" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>OCR 文本</span></div>
          <pre class="gallery-detail__ocr">{{ detail.ocrText }}</pre>
        </section>

        <section class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>来源</span></div>
          <div class="gallery-detail__meta-grid">
            <div><span>来源资料</span><b>{{ detail.sourceName }}</b></div>
            <div><span>所在章节</span><b>{{ detail.sectionTitle || '未识别章节' }}</b></div>
            <div><span>图片类型</span><b>{{ kindLabel(detail.kind) }}</b></div>
            <div><span>被使用</span><b>{{ detail.usedCount || 0 }} 处</b></div>
          </div>
          <p v-if="detail.surroundingText" class="gallery-detail__context">
            {{ detail.surroundingText }}
          </p>
        </section>

        <section v-if="detail.references?.length" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>引用关系</span></div>
          <div class="gallery-detail__usages">
            <div v-for="ref in detail.references" :key="`ref-${ref.id}`" class="gallery-detail__usage">
              <span>{{ ref.targetType === 'question' ? '题目' : ref.targetType === 'note' ? '笔记' : ref.targetType === 'wiki_page' ? '知识百科' : '资料' }}</span>
              <b>{{ ref.targetTitle }}</b>
              <em>{{ ref.createTime }}</em>
            </div>
          </div>
        </section>

        <section v-if="detail.usages?.length" class="gallery-detail__section">
          <div class="gallery-detail__section-title"><span>使用记录</span></div>
          <div class="gallery-detail__usages">
            <div v-for="usage in detail.usages" :key="`${usage.targetType}-${usage.targetId}`" class="gallery-detail__usage">
              <span>{{ usage.targetType === 'question' ? '题目' : usage.targetType === 'note' ? '笔记' : '资料' }}</span>
              <b>{{ usage.title }}</b>
              <em>{{ usage.createTime }}</em>
            </div>
          </div>
        </section>

        <div class="gallery-detail__actions">
          <el-button v-if="detail.canLocate" plain @click="locate(detail)">定位原文</el-button>
          <el-button plain @click="useImage(detail, 'question')">插入题目</el-button>
          <el-button type="primary" plain @click="useImage(detail, 'note')">加入笔记</el-button>
          <el-button plain @click="openWikiPicker">插入知识百科</el-button>
        </div>
      </div>
      <div v-else class="gallery-detail__loading" v-loading="true"></div>
    </el-drawer>

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
  { key: 'chat', label: '聊天图片', count: 0 }
])
const stats = reactive({ total: 0, described: 0, pending: 0, failed: 0, used: 0 })
const query = ref(props.searchQuery || '')
const scope = ref<'current' | 'all'>('current')
const sourceFilter = ref<'all' | 'document' | 'chat'>('all')
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
const hasFilter = computed(
  () =>
    !!query.value.trim() ||
    sourceFilter.value !== 'all' ||
    docFilter.value != null ||
    Object.values(props.filters || {}).some((value) => Array.isArray(value) && value.length > 0)
)

function displayUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
}

function kindLabel(kind: string) {
  return (
    {
      photo: '照片',
      diagram: '示意图',
      table: '表格',
      formula: '公式',
      screenshot: '截图',
      image: '图片'
    } as Record<string, string>
  )[kind] || '图片'
}

function statusLabel(status: string) {
  return (
    {
      done: '已描述',
      pending: '待描述',
      processing: '生成中',
      failed: '失败'
    } as Record<string, string>
  )[status] || '待描述'
}

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

function setSource(source: 'all' | 'document' | 'chat') {
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

function stopDescribePolling() {
  if (describeTimer) {
    clearInterval(describeTimer)
    describeTimer = null
  }
}

function startDescribePolling(jobId: number) {
  stopDescribePolling()
  describeTimer = setInterval(async () => {
    try {
      const res = await getGalleryDescribeJob(jobId)
      if (res.code !== 200 || !res.data) return
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
      // 网络抖动不立刻终止任务状态，下一轮继续；只有组件卸载才清理定时器
      console.warn('[gallery] describe job poll failed', error)
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

onMounted(async () => {
  await reload()
  await resumeDescribeJob()
})

onBeforeUnmount(stopDescribePolling)
</script>

<style scoped>
.gallery-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 620px;
  padding: 4px 2px 10px;
}

.gallery-kicker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #4f6bed;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.gallery-kicker__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #4f6bed;
  box-shadow: 0 0 0 4px rgba(79, 107, 237, 0.1);
}

.gallery-toolbar {
  display: flex;
  flex-direction: column;
  gap: 11px;
  padding: 2px 2px 15px;
}

.gallery-doc-filter {
  width: 190px;
}

.gallery-describe-trigger {
  margin-left: 2px;
  color: #6b7280;
  font-size: 12px;
  font-weight: 400;
}
.gallery-describe-trigger:hover {
  color: #374151;
  background: #f3f4f6;
}

.gallery-describe-progress {
  padding: 9px 12px;
  border: 1px solid #e2e9fb;
  border-radius: 7px;
  background: #f8faff;
}
.gallery-describe-progress__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #4f6bed;
  font-size: 11px;
  font-weight: 600;
}
.gallery-describe-progress__top span:last-child { color: #d97706; font-weight: 400; }
.gallery-describe-progress__bar {
  height: 5px;
  margin-top: 7px;
  overflow: hidden;
  border-radius: 99px;
  background: #e7edfb;
}
.gallery-describe-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #6f8df2, #4f6bed);
  transition: width .35s ease;
}
.gallery-describe-progress p { margin: 6px 0 0; color: #9aa1af; font-size: 10px; }

.gallery-toolbar__filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.gallery-scope-tabs {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid #e8ebf2;
  border-radius: 7px;
  background: #f7f9fc;
}

.gallery-scope-tabs button {
  padding: 4px 9px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #8a91a0;
  cursor: pointer;
  font: inherit;
  font-size: 10.5px;
}

.gallery-scope-tabs button:hover {
  color: #4b5563;
}

.gallery-scope-tabs button.is-active {
  color: #4f6bed;
  background: #fff;
  box-shadow: 0 1px 4px rgba(23, 32, 51, 0.08);
  font-weight: 600;
}

.gallery-toolbar__divider {
  width: 1px;
  height: 18px;
  margin: 0 5px;
  background: #e9ecf2;
}

.gallery-source-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  font-size: 12px;
}

.gallery-source-tab span {
  color: #a2a8b6;
  font-size: 11px;
}

.gallery-source-tab:hover {
  background: #f5f7fa;
  color: #374151;
}

.gallery-source-tab.is-active {
  background: #eef2ff;
  color: #4f6bed;
  font-weight: 600;
}

.gallery-source-tab.is-active span {
  color: #4f6bed;
}

.gallery-toolbar__hint {
  margin-left: auto;
  color: #a0a6b2;
  font-size: 11px;
}

.gallery-grid {
  columns: 252px;
  column-gap: 14px;
}

.gallery-card {
  display: inline-flex;
  width: 100%;
  margin: 0 0 14px;
  flex-direction: column;
  break-inside: avoid;
  overflow: hidden;
  border: 1px solid #e9ecf2;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  outline: none;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.gallery-card:hover,
.gallery-card:focus-visible {
  border-color: rgba(79, 107, 237, 0.32);
  box-shadow: 0 12px 28px rgba(38, 58, 118, 0.09);
  transform: translateY(-2px);
}

.gallery-card__media {
  position: relative;
  min-height: 100px;
  overflow: hidden;
  background: #f3f5f9;
  line-height: 0;
}

.gallery-card__media :deep(.el-image) {
  display: block;
  width: 100%;
  height: auto;
}

.gallery-card__media :deep(img) {
  display: block;
  width: 100%;
  height: auto;
  max-height: 360px;
  object-fit: cover;
  transition: transform 0.35s ease;
}

.gallery-card:hover .gallery-card__media :deep(img) {
  transform: scale(1.035);
}

.gallery-card__img-empty {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  color: #a2a8b6;
  font-size: 11px;
}

.gallery-kind,
.gallery-status {
  position: absolute;
  top: 9px;
  padding: 3px 7px;
  border-radius: 5px;
  font-size: 10px;
  line-height: 1.2;
  backdrop-filter: blur(8px);
}

.gallery-kind {
  left: 9px;
  color: #fff;
  background: rgba(28, 37, 54, 0.58);
}

.gallery-status {
  right: 9px;
}

.gallery-status.is-done {
  color: #1f7a6d;
  background: rgba(226, 248, 244, 0.94);
}

.gallery-status.is-pending {
  color: #946523;
  background: rgba(255, 248, 230, 0.94);
}

.gallery-status.is-processing {
  color: #3f5fc9;
  background: rgba(235, 240, 255, 0.94);
}

.gallery-status.is-failed {
  color: #b34141;
  background: rgba(255, 236, 236, 0.94);
}

.gallery-card__hover {
  position: absolute;
  inset: auto 0 0;
  display: flex;
  justify-content: center;
  padding: 8px;
  color: #fff;
  font-size: 11px;
  background: linear-gradient(transparent, rgba(15, 23, 42, 0.56));
  opacity: 0;
  transition: opacity 0.18s ease;
}

.gallery-card:hover .gallery-card__hover {
  opacity: 1;
}

.gallery-card__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 7px;
  padding: 11px 12px 10px;
}

.gallery-card__caption {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  min-height: 36px;
  margin: 0;
  color: #374151;
  font-size: 12px;
  line-height: 1.5;
}

.gallery-card__caption.is-muted {
  color: #a0a6b2;
}

.gallery-card__source {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 6px;
  color: #8a91a0;
  font-size: 10.5px;
}

.gallery-card__source-name {
  overflow: hidden;
  max-width: 72%;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-card__section {
  overflow: hidden;
  padding: 1px 5px;
  border-radius: 4px;
  background: #f3f5f9;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-card__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-card__state {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #9aa1af;
}

.gallery-card__state::before {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #c8cedb;
  content: '';
}

.gallery-card__state.is-done {
  color: #2f9e8f;
}

.gallery-card__state.is-done::before {
  background: #2f9e8f;
}

.gallery-card__state.is-pending {
  color: #b78b2a;
}

.gallery-card__state.is-pending::before {
  background: #c99a3d;
}

.gallery-card__state.is-failed {
  color: #c45656;
}

.gallery-card__state.is-failed::before {
  background: #c45656;
}

.gallery-grid--loading {
  columns: 252px;
  column-gap: 14px;
}

.gallery-skeleton {
  display: inline-block;
  width: 100%;
  height: 210px;
  margin-bottom: 14px;
  break-inside: avoid;
  border-radius: 12px;
  background: linear-gradient(90deg, #f1f3f7 25%, #f8f9fb 37%, #f1f3f7 63%);
  background-size: 400% 100%;
  animation: gallery-shimmer 1.25s ease infinite;
}

.gallery-skeleton:nth-child(3n + 1) {
  height: 290px;
}

.gallery-skeleton:nth-child(3n + 2) {
  height: 170px;
}

@keyframes gallery-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: 0 0; }
}

.gallery-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 340px;
  padding: 28px;
  border: 1px dashed #dfe4ec;
  border-radius: 14px;
  background: #fbfcfe;
  text-align: center;
}

.gallery-empty__art {
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

.gallery-empty h3 {
  margin: 0 0 6px;
  color: #374151;
  font-size: 16px;
}

.gallery-empty p {
  max-width: 460px;
  margin: 0 0 14px;
  color: #8a91a0;
  font-size: 12px;
  line-height: 1.7;
}

.gallery-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 2px 4px 18px;
}

.gallery-detail__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.gallery-detail__head h3 {
  margin: 6px 0 0;
  color: #1f2937;
  font-size: 18px;
  line-height: 1.35;
}

.gallery-detail__close {
  border: none;
  background: transparent;
  color: #9aa1af;
  cursor: pointer;
  font-size: 24px;
  line-height: 1;
}

.gallery-detail__image {
  overflow: hidden;
  border: 1px solid #eceff4;
  border-radius: 12px;
  background: #f5f7fa;
}

.gallery-detail__image :deep(.el-image) {
  display: block;
  width: 100%;
  max-height: 360px;
}

.gallery-detail__image :deep(img) {
  max-height: 360px;
  object-fit: contain;
}

.gallery-detail__badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gallery-detail__badges .gallery-kind,
.gallery-detail__badges .gallery-status {
  position: static;
  backdrop-filter: none;
}

.gallery-detail__badges .gallery-kind {
  color: #596173;
  background: #f1f3f7;
}

.gallery-detail__model {
  margin-left: auto;
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-detail__section {
  padding: 13px 14px;
  border: 1px solid #eef0f5;
  border-radius: 10px;
  background: #fff;
}

.gallery-detail__section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.gallery-detail__caption {
  margin: 0;
  color: #374151;
  font-size: 13px;
  line-height: 1.75;
}

.gallery-detail__caption.is-muted {
  color: #9aa1af;
}

.gallery-detail__error {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 7px;
  color: #b34141;
  background: #fff4f4;
  font-size: 11px;
  line-height: 1.6;
}

.gallery-detail__ocr {
  overflow: auto;
  max-height: 160px;
  margin: 0;
  padding: 10px;
  border-radius: 7px;
  color: #4b5563;
  background: #f7f8fa;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 11px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.gallery-detail__meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}

.gallery-detail__meta-grid div {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.gallery-detail__meta-grid span {
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-detail__meta-grid b {
  overflow: hidden;
  color: #4b5563;
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-detail__context {
  margin: 10px 0 0;
  padding-top: 10px;
  border-top: 1px dashed #eceff4;
  color: #8a91a0;
  font-size: 11px;
  line-height: 1.7;
}

.gallery-detail__usages {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.gallery-detail__usage {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6b7280;
  font-size: 11px;
}

.gallery-detail__usage span {
  flex: none;
  padding: 1px 5px;
  border-radius: 4px;
  color: #4f6bed;
  background: #eef2ff;
  font-size: 10px;
}

.gallery-detail__usage b {
  overflow: hidden;
  color: #374151;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-detail__usage em {
  margin-left: auto;
  color: #b0b6c1;
  font-size: 10px;
  font-style: normal;
}

.gallery-detail__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-top: 4px;
}

.gallery-wiki-picker {
  display: flex;
  min-height: 120px;
  flex-direction: column;
  gap: 8px;
  max-height: 52vh;
  overflow-y: auto;
}

.gallery-wiki-pick {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  background: #fff;
  color: #4b5563;
  cursor: pointer;
  text-align: left;
}

.gallery-wiki-pick:hover {
  border-color: #cbd9f2;
  background: #f7f9ff;
}

.gallery-wiki-pick b {
  font-size: 13px;
}

.gallery-wiki-pick span {
  overflow: hidden;
  color: #9aa1af;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-wiki-empty {
  padding: 30px 0;
  color: #a0a6b2;
  font-size: 12px;
  text-align: center;
}

.gallery-detail__loading {
  height: 500px;
}

@media (max-width: 860px) {
  .gallery-toolbar__hint {
    display: none;
  }
}
</style>
