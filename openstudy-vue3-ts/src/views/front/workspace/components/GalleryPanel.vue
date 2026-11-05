<template>
  <section class="gallery-page">
    <header class="gallery-hero">
      <div class="gallery-hero__main">
        <div class="gallery-kicker">
          <span class="gallery-kicker__dot"></span>
          资料知识网络 · 0.4.0 · 画廊
        </div>
        <h2>把每一张图，变成找得到、说得清、用得上的资料资产</h2>
        <p>
          搜索图片描述与 OCR，追到来源章节；补一次描述，题目、笔记和知识地图都能复用。
        </p>
      </div>
      <div class="gallery-hero__stats">
        <div class="gallery-stat">
          <span>图片资产</span>
          <strong>{{ stats.total }}</strong>
        </div>
        <div class="gallery-stat is-good">
          <span>已有描述</span>
          <strong>{{ stats.described }}</strong>
        </div>
        <div class="gallery-stat is-warn">
          <span>待补描述</span>
          <strong>{{ stats.pending }}</strong>
        </div>
        <div class="gallery-stat">
          <span>已使用</span>
          <strong>{{ stats.used }}</strong>
        </div>
      </div>
    </header>

    <div class="gallery-toolbar">
      <div class="gallery-toolbar__row">
        <el-input
          v-model="query"
          class="gallery-search"
          clearable
          placeholder="搜图片描述、OCR、文件名或来源资料…"
          :prefix-icon="Search"
          @input="onQueryInput"
        />
        <el-radio-group v-model="scope" size="small" @change="reload">
          <el-radio-button value="current">当前资料夹</el-radio-button>
          <el-radio-button value="all">全部资料</el-radio-button>
        </el-radio-group>
        <el-select v-model="statusFilter" size="small" class="gallery-status" @change="reload">
          <el-option label="全部状态" value="all" />
          <el-option label="已有描述" value="done" />
          <el-option label="待补描述" value="pending" />
          <el-option label="生成失败" value="failed" />
        </el-select>
        <el-button
          class="gallery-describe-btn"
          :loading="describing"
          :disabled="!pendingKeys.length"
          @click="describePending"
        >
          <el-icon><MagicStick /></el-icon>
          {{ pendingKeys.length ? `补全未描述（${Math.min(pendingKeys.length, 40)}）` : '图片已描述' }}
        </el-button>
      </div>
      <div class="gallery-source-tabs">
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
        <span class="gallery-toolbar__hint">
          描述由视觉模型生成，只在你点击时运行；不会上传前偷偷消耗额度。
        </span>
      </div>
    </div>

    <div v-if="loading" class="gallery-grid gallery-grid--loading">
      <div v-for="i in 8" :key="i" class="gallery-skeleton"></div>
    </div>

    <div v-else-if="items.length" class="gallery-grid">
      <article
        v-for="item in items"
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
          <span class="gallery-kind">{{ kindLabel(item.kind) }}</span>
          <span class="gallery-status" :class="`is-${item.descriptionStatus}`">
            {{ statusLabel(item.descriptionStatus) }}
          </span>
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
            <span>{{ item.usedCount ? `已用于 ${item.usedCount} 处` : '尚未被使用' }}</span>
            <span v-if="item.referenceCount">{{ item.referenceCount }} 条引用</span>
            <span v-else-if="item.ocrText">含 OCR</span>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="gallery-empty">
      <div class="gallery-empty__art"><el-icon><Picture /></el-icon></div>
      <h3>{{ hasFilter ? '没有匹配的图片' : '画廊还没有图片' }}</h3>
      <p>{{ hasFilter ? '换个关键词，或把状态切回「全部状态」。' : '上传带图片的课件、真题，或直接在对话里贴图，这里会自动汇总。' }}</p>
      <el-button v-if="hasFilter" plain @click="clearFilters">清空筛选</el-button>
      <el-button v-else text @click="emit('back')">回到资料夹上传</el-button>
    </div>

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
              <span>{{ ref.targetType === 'question' ? '题目' : ref.targetType === 'note' ? '笔记' : '资料' }}</span>
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
          <el-button plain @click="copyMarkdown(detail)">复制图片</el-button>
          <el-button v-if="detail.canLocate" plain @click="locate(detail)">定位原文</el-button>
          <el-button plain @click="useImage(detail, 'question')">插入题目</el-button>
          <el-button type="primary" plain @click="useImage(detail, 'note')">加入笔记</el-button>
        </div>
      </div>
      <div v-else class="gallery-detail__loading" v-loading="true"></div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Picture, Search } from '@element-plus/icons-vue'
import {
  describeGalleryAssets,
  getGalleryAsset,
  listGalleryAssets
} from '@/api/ai/workspace'

const props = defineProps<{
  activeKbId?: number | null
  activeKbName?: string
}>()

const emit = defineEmits<{
  (e: 'use-image', image: any): void
  (e: 'locate', payload: { docId: number; offset: number; targetText?: string }): void
  (e: 'back'): void
}>()

const loading = ref(false)
const items = ref<any[]>([])
const sources = ref<Array<{ key: string; label: string; count: number }>>([
  { key: 'all', label: '全部图片', count: 0 },
  { key: 'document', label: '文档图片', count: 0 },
  { key: 'chat', label: '聊天图片', count: 0 }
])
const stats = reactive({ total: 0, described: 0, pending: 0, failed: 0, used: 0 })
const query = ref('')
const scope = ref<'current' | 'all'>('current')
const sourceFilter = ref<'all' | 'document' | 'chat'>('all')
const statusFilter = ref<'all' | 'pending' | 'processing' | 'done' | 'failed'>('all')
const describing = ref(false)
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<any>(null)
const describingOne = ref(false)
let queryTimer: number | undefined

const pendingKeys = computed(() =>
  items.value
    .filter((item) => item.descriptionStatus === 'pending' || item.descriptionStatus === 'failed')
    .map((item) => item.assetKey)
)
const hasFilter = computed(
  () => !!query.value.trim() || sourceFilter.value !== 'all' || statusFilter.value !== 'all'
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
}

async function reload() {
  loading.value = true
  try {
    const res = await listGalleryAssets({
      scope: scope.value,
      kbId: scope.value === 'current' ? props.activeKbId : undefined,
      source: sourceFilter.value,
      status: statusFilter.value,
      q: query.value.trim(),
      limit: 300
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '画廊加载失败')
      return
    }
    applyData(res.data)
  } catch (error: any) {
    ElMessage.error('画廊加载失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

function onQueryInput() {
  window.clearTimeout(queryTimer)
  queryTimer = window.setTimeout(reload, 260)
}

function setSource(source: 'all' | 'document' | 'chat') {
  sourceFilter.value = source
  reload()
}

function clearFilters() {
  query.value = ''
  sourceFilter.value = 'all'
  statusFilter.value = 'all'
  reload()
}

async function describePending() {
  const keys = pendingKeys.value.slice(0, 40)
  if (!keys.length) return
  describing.value = true
  try {
    const res = await describeGalleryAssets({ assetKeys: keys, limit: 40 })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '生成图片描述失败')
      return
    }
    const failed = Number(res.data?.failed || 0)
    if (failed) {
      ElMessage.warning(`完成 ${res.data?.done || 0} 张，${failed} 张失败，可在详情里查看原因`)
    } else {
      ElMessage.success(`已为 ${res.data?.done || 0} 张图片补上描述`)
    }
    await reload()
    if (detail.value?.assetKey) await loadDetail(detail.value.assetKey, false)
  } catch (error: any) {
    ElMessage.error('生成图片描述失败：' + (error?.message || error))
  } finally {
    describing.value = false
  }
}

async function openDetail(item: any) {
  detailVisible.value = true
  detail.value = item
  await loadDetail(item.assetKey, true)
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
    if (res.data?.failed) {
      ElMessage.warning('生成失败，失败原因已显示在详情里')
    } else {
      ElMessage.success('描述已更新')
    }
    await loadDetail(detail.value.assetKey)
    await reload()
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

async function copyMarkdown(item: any) {
  const alt = `${item.sourceName || '资料'}·${item.fileName || '图片'}`
  const text = `![${alt}](${item.url})`
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制图片 Markdown')
  } catch {
    ElMessage.warning('复制失败，请打开图片后手动复制')
  }
}

watch(
  () => [props.activeKbId, props.activeKbName],
  () => {
    if (scope.value === 'current') reload()
  }
)

onMounted(reload)
</script>

<style scoped>
.gallery-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 620px;
  padding: 4px 2px 10px;
}

.gallery-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 24px 26px 22px;
  border: 1px solid rgba(79, 107, 237, 0.12);
  border-radius: 16px;
  background:
    radial-gradient(circle at 8% 10%, rgba(79, 107, 237, 0.08), transparent 36%),
    linear-gradient(135deg, #fbfcff 0%, #f6f8fd 58%, #f8fbfb 100%);
}

.gallery-hero__main h2 {
  max-width: 720px;
  margin: 8px 0 8px;
  color: #1f2937;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.3px;
  line-height: 1.35;
}

.gallery-hero__main p {
  max-width: 720px;
  margin: 0;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
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

.gallery-hero__stats {
  display: flex;
  flex: none;
  gap: 8px;
}

.gallery-stat {
  min-width: 76px;
  padding: 10px 12px;
  border: 1px solid rgba(15, 23, 42, 0.06);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
}

.gallery-stat span {
  display: block;
  color: #8a91a0;
  font-size: 10px;
  letter-spacing: 0.04em;
}

.gallery-stat strong {
  display: block;
  margin-top: 5px;
  color: #1f2937;
  font-size: 21px;
  font-weight: 700;
  line-height: 1;
}

.gallery-stat.is-good strong {
  color: #2f9e8f;
}

.gallery-stat.is-warn strong {
  color: #c47a55;
}

.gallery-toolbar {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 13px 15px;
  border: 1px solid var(--os-border, #e9ecf2);
  border-radius: 12px;
  background: #fff;
}

.gallery-toolbar__row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gallery-search {
  width: 320px;
}

.gallery-search :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08) inset;
}

.gallery-status {
  width: 108px;
}

.gallery-describe-btn {
  margin-left: auto;
  border-color: rgba(79, 107, 237, 0.25);
  color: #4f6bed;
  background: #f7f9ff;
}

.gallery-source-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
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
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(218px, 1fr));
  gap: 14px;
}

.gallery-card {
  display: flex;
  flex-direction: column;
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
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: #f3f5f9;
}

.gallery-card__media :deep(.el-image) {
  width: 100%;
  height: 100%;
  display: block;
}

.gallery-card__media :deep(img) {
  width: 100%;
  height: 100%;
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
  justify-content: space-between;
  margin-top: auto;
  color: #a0a6b2;
  font-size: 10px;
}

.gallery-grid--loading {
  grid-template-columns: repeat(auto-fill, minmax(218px, 1fr));
}

.gallery-skeleton {
  aspect-ratio: 4 / 3.72;
  border-radius: 12px;
  background: linear-gradient(90deg, #f1f3f7 25%, #f8f9fb 37%, #f1f3f7 63%);
  background-size: 400% 100%;
  animation: gallery-shimmer 1.25s ease infinite;
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

.gallery-detail__loading {
  height: 500px;
}

@media (max-width: 1180px) {
  .gallery-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .gallery-hero__stats {
    width: 100%;
  }

  .gallery-stat {
    flex: 1;
  }
}

@media (max-width: 840px) {
  .gallery-toolbar__row {
    flex-wrap: wrap;
  }

  .gallery-search {
    width: 100%;
  }

  .gallery-describe-btn {
    margin-left: 0;
  }

  .gallery-toolbar__hint {
    display: none;
  }
}
</style>
