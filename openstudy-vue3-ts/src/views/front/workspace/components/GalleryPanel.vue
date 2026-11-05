<template>
  <section class="gallery-page">
    <div class="gallery-toolbar">
      <div class="gallery-toolbar__head">
        <div class="gallery-summary">
          <span class="gallery-summary__title">{{ scope === 'current' ? (activeKbName || '当前资料夹') : '全部资料' }}</span>
          <span class="gallery-summary__meta">已描述 {{ stats.described }} · 待补 {{ stats.pending }} · 已使用 {{ stats.used }}</span>
        </div>
        <div class="gallery-toolbar__tools">
          <el-input
            v-model="query"
            class="gallery-search"
            clearable
            placeholder="搜索图片描述或文字…"
            :prefix-icon="Search"
            @input="onQueryInput"
          />
          <el-button
            class="gallery-describe-btn"
            :loading="describing"
            :disabled="!pendingKeys.length"
            @click="describePending"
          >
            <el-icon><MagicStick /></el-icon>
            {{ pendingKeys.length ? `补全描述（${Math.min(pendingKeys.length, 40)}）` : '图片已描述' }}
          </el-button>
        </div>
      </div>
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
        <span class="gallery-toolbar__hint">描述只在点击时生成，不提前消耗额度</span>
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
const hasFilter = computed(() => !!query.value.trim() || sourceFilter.value !== 'all')

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
      status: 'all',
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

function setScope(next: 'current' | 'all') {
  scope.value = next
  reload()
}

function setSource(source: 'all' | 'document' | 'chat') {
  sourceFilter.value = source
  reload()
}

function clearFilters() {
  query.value = ''
  sourceFilter.value = 'all'
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

.gallery-toolbar__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.gallery-summary {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 10px;
}

.gallery-summary__title {
  overflow: hidden;
  max-width: 260px;
  color: #1f2937;
  font-size: 18px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-summary__meta {
  overflow: hidden;
  color: #a0a6b2;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gallery-toolbar__tools {
  display: flex;
  flex: none;
  align-items: center;
  gap: 8px;
}

.gallery-search {
  width: 290px;
}

.gallery-search :deep(.el-input__wrapper) {
  border-radius: 7px;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08) inset;
}

.gallery-describe-btn {
  border-color: rgba(79, 107, 237, 0.25);
  color: #4f6bed;
  background: #f7f9ff;
}

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

.gallery-detail__loading {
  height: 500px;
}

@media (max-width: 860px) {
  .gallery-toolbar__head {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .gallery-toolbar__tools {
    width: 100%;
  }

  .gallery-search {
    flex: 1;
    width: auto;
  }

  .gallery-summary__meta {
    display: none;
  }

  .gallery-toolbar__hint {
    display: none;
  }
}
</style>
