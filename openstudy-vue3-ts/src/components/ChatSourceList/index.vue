<template>
  <div ref="rootRef" class="chat-sources" :class="{ 'chat-sources--compact': showLabel === false, 'chat-sources--web': webRefs.length }" @mouseleave="scheduleClose">
    <!-- 网页来源：一个可展开的汇总胶囊，避免几十个 chip 把回答底部铺满。 -->
    <template v-if="webRefs.length">
      <button type="button" class="chat-web-summary" :class="{ 'is-open': webExpanded }"
        :title="webExpanded ? '收起参考来源' : '展开参考来源'" @click.stop="webExpanded = !webExpanded">
        <span class="chat-sources__label">参考来源</span>
        <span class="chat-web-icons" aria-hidden="true">
          <span v-for="(icon, index) in webSiteIcons" :key="`${icon.letter}-${index}`" class="chat-web-icon">
            <img v-if="icon.icon" :src="icon.icon" alt="" loading="lazy" />
            <template v-else>{{ icon.letter }}</template>
          </span>
        </span>
        <b class="chat-web-count">{{ webRefs.length }} 个网页</b>
        <span class="chat-web-caret" :class="{ 'is-open': webExpanded }">▾</span>
      </button>
      <div v-if="webExpanded" class="chat-web-panel" @click.stop>
        <a v-for="(ref, index) in webRefs" :key="ref.url || index" class="chat-web-row" :href="ref.url"
          target="_blank" rel="noopener noreferrer">
          <span class="chat-web-index">W{{ ref.index || index + 1 }}</span>
          <span class="chat-web-main">
            <span class="chat-web-title">{{ ref.webTitle || ref.docName || ref.url }}</span>
            <span class="chat-web-meta">{{ ref.source || hostOf(ref.url) }}<template v-if="ref.date"> · {{ ref.date }}</template></span>
          </span>
          <span class="chat-web-arrow" aria-hidden="true">↗</span>
        </a>
      </div>
    </template>

    <!-- 文档/主题页来源：保留原有 chip + 悬浮切片；网页不再混进这一排。 -->
    <template v-if="docGroups.length">
      <span v-if="showLabel !== false && !webRefs.length" class="chat-sources__label">{{ labelText }}</span>
      <button v-for="group in docGroups" :key="group.key" type="button" class="chat-source-chip"
        :class="{ 'is-active': float.visible && float.groupKey === group.key }"
        :title="group.chunks.some((chunk: any) => chunk.docId) ? '点击查看文档原文' : group.docName"
        @mouseenter="showGroup(group, $event)" @focus="showGroup(group, $event)" @mouseleave="scheduleClose"
        @mousedown.stop @click.stop="onChipClick(group, $event)">
        <el-icon class="chat-source-chip__icon"><Document /></el-icon>
        <span class="chat-source-chip__name">{{ group.docName }}</span>
        <span v-if="group.chunks.length > 1" class="chat-source-chip__count">{{ group.chunks.length }}</span>
      </button>
    </template>

    <Teleport to="body">
      <div v-if="float.visible" class="chat-source-float" :style="{ top: `${float.top}px`, left: `${float.left}px` }"
        @mouseenter="cancelClose" @mouseleave="scheduleClose">
        <div class="chat-source-float__head">
          <el-icon><Document /></el-icon>
          <span>{{ float.docName }}</span>
          <em v-if="float.chunks.length > 1">{{ float.chunks.length }} 个片段</em>
        </div>
        <div class="chat-source-float__body">
          <div v-for="(chunk, index) in float.chunks" :key="chunkKey(chunk, index)" class="chat-source-chunk">
            <div class="chat-source-chunk__meta">
              <span>{{ chunkLabel(chunk, index) }}</span>
              <span v-if="chunk.source" class="chat-source-chunk__source">{{ chunk.source }}</span>
            </div>
            <p>{{ cleanContent(chunk.snippet || chunk.content) || '这个片段暂无可读内容。' }}</p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Document } from '@element-plus/icons-vue'

const props = defineProps<{ references: any[]; showLabel?: boolean }>()
const emit = defineEmits<{ (e: 'open-document', item: any): void }>()

type SourceGroup = { key: string; docName: string; chunks: any[] }
const float = ref<{ visible: boolean; groupKey: string; docName: string; chunks: any[]; top: number; left: number }>({
  visible: false,
  groupKey: '',
  docName: '',
  chunks: [],
  top: 0,
  left: 0
})
let closeTimer: ReturnType<typeof setTimeout> | null = null
const rootRef = ref<HTMLElement | null>(null)
const webExpanded = ref(false)

/** 点击参考来源面板以外的空白/其它消息时自动收起。 */
function onDocumentClick(event: MouseEvent) {
  if (!webExpanded.value) return
  const root = rootRef.value
  if (root && !root.contains(event.target as Node)) {
    webExpanded.value = false
  }
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') webExpanded.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick, true)
  document.addEventListener('keydown', onDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick, true)
  document.removeEventListener('keydown', onDocumentKeydown)
  cancelClose()
})

const labelText = computed(() => '参考文档')
const webRefs = computed(() =>
  (props.references || []).filter((ref: any) => ref?.sourceType === 'web' && /^https?:\/\//i.test(String(ref?.url || '')))
)
const webSiteIcons = computed(() => {
  const seen = new Set<string>()
  const icons: Array<{ icon: string; letter: string }> = []
  for (const ref of webRefs.value) {
    const icon = String(ref?.siteIcon || '').trim()
    if (!icon || seen.has(icon)) continue
    seen.add(icon)
    const site = String(ref?.source || ref?.siteName || ref?.url || '')
    icons.push({ icon, letter: (site.match(/[A-Za-z\u4e00-\u9fff]/)?.[0] || '?').toUpperCase() })
    if (icons.length >= 3) break
  }
  return icons
})

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

const docGroups = computed<SourceGroup[]>(() => {
  const map = new Map<string, SourceGroup>()
  for (const ref of props.references || []) {
    if (ref?.sourceType === 'web') continue
    const docName = String(ref?.docName || ref?.wikiPageTitle || ref?.source || '未命名文档')
    const key = String(ref?.docId || ref?.wikiPageId || docName)
    if (!map.has(key)) map.set(key, { key, docName, chunks: [] })
    map.get(key)!.chunks.push(ref)
  }
  return Array.from(map.values())
})

function cleanContent(content: string) {
  return String(content || '')
    .replace(/^\s*([-*_])\1{2,}\s*$/gm, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/(\*\*|__|`)/g, '')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

function chunkLabel(chunk: any, index: number) {
  if (chunk?.sourceType === 'web') {
    return chunk?.source || chunk?.siteName || '网页'
  }
  if (chunk?.sourceType === 'image') {
    return chunk.sectionTitle || chunk.source || '图片'
  }
  const number = Number.isFinite(Number(chunk?.chunkIndex)) ? Number(chunk.chunkIndex) + 1 : index + 1
  return chunk?.sourceType === 'wiki' ? (chunk?.wikiPageTitle || `主题页 ${number}`) : `第 ${number} 段`
}

function chunkKey(chunk: any, index: number) {
  return String(chunk?.chunkId ?? `${chunk?.docId || ''}-${chunk?.chunkIndex ?? index}-${index}`)
}

function onChipClick(group: SourceGroup, event: Event) {
  const webChunk = group.chunks.find((chunk: any) => chunk.url)
  if (webChunk) {
    window.open(String(webChunk.url), '_blank', 'noopener,noreferrer')
    return
  }
  const documentChunk = group.chunks.find((chunk: any) => chunk.docId)
  if (documentChunk) {
    emit('open-document', { ...documentChunk, docName: group.docName })
    return
  }
  showGroup(group, event)
}

function showGroup(group: SourceGroup, event: Event) {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
  const el = event.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const width = 340
  const cardHeight = 280
  const gap = 8
  // 优先放右侧：不要把浮层盖在触发 chip 上，否则用户点不到跳转。
  let left = rect.right + gap
  let top = rect.top
  if (left + width > window.innerWidth - 12) {
    left = rect.left - width - gap
  }
  if (left < 12) {
    // 左右都放不下时，放到 chip 上方/下方；保证不覆盖触发点。
    left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
    const above = rect.top - cardHeight - gap
    top = above >= 12 ? above : rect.bottom + gap
  }
  if (top + cardHeight > window.innerHeight - 12) {
    top = Math.max(12, window.innerHeight - cardHeight - 12)
  }
  float.value = { visible: true, groupKey: group.key, docName: group.docName, chunks: group.chunks, top, left }
}

function cancelClose() {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
}

function scheduleClose() {
  cancelClose()
  closeTimer = setTimeout(() => { float.value.visible = false }, 160)
}

</script>

<style scoped>
.chat-sources { position: relative; display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.chat-sources--compact { display: inline-flex; margin-top: 2px; vertical-align: baseline; }
.chat-sources--compact .chat-source-chip { padding: 1px 5px; font-size: 9px; }
.chat-sources__label { margin-right: 1px; color: #a0a7b4; font-size: 10px; }

/* 网页参考来源：一个汇总胶囊 + 点击展开的列表；不再堆几十个 chip。 */
.chat-web-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 9px 3px 7px;
  border: 1px solid #e4e9f2;
  border-radius: 999px;
  color: #6f7b8d;
  background: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  line-height: 1.5;
  transition: border-color .15s ease, background .15s ease, color .15s ease;
}
.chat-web-summary:hover,
.chat-web-summary.is-open { border-color: #c7d7f4; color: #3f5f9d; background: #f8faff; }
.chat-web-icons { display: inline-flex; align-items: center; padding-left: 2px; }
.chat-web-icon { display: inline-flex; width: 16px; height: 16px; align-items: center; justify-content: center; margin-left: -4px; overflow: hidden; border: 1px solid #fff; border-radius: 50%; color: #6f86b8; background: #eef3fb; font-size: 9px; font-weight: 700; }
.chat-web-icon:first-child { margin-left: 0; }
.chat-web-icon img { width: 100%; height: 100%; object-fit: cover; }
.chat-web-count { color: #5f6b7d; font-weight: 600; white-space: nowrap; }
.chat-web-caret { display: inline-flex; color: #9aa3b2; font-size: 12px; line-height: 1; transition: transform .18s ease; }
.chat-web-caret.is-open { transform: rotate(180deg); }
.chat-web-panel {
  position: absolute;
  z-index: 30;
  bottom: calc(100% + 7px);
  left: 0;
  display: flex;
  width: min(430px, calc(100vw - 48px));
  max-height: 260px;
  flex-direction: column;
  overflow-y: auto;
  padding: 5px;
  border: 1px solid #e1e7f0;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(31, 47, 75, .14);
}
.chat-web-row { display: flex; align-items: flex-start; gap: 7px; padding: 7px 6px; border-radius: 7px; color: #38465c; text-decoration: none; }
.chat-web-row:hover { background: #f5f8ff; }
.chat-web-index { flex: none; width: 22px; color: #2f5fce; font-size: 10px; font-weight: 700; line-height: 1.6; }
.chat-web-main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 2px; }
.chat-web-title { overflow: hidden; color: #3f5f9d; font-size: 11.5px; font-weight: 600; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.chat-web-meta { color: #9aa3b2; font-size: 10px; line-height: 1.35; }
.chat-web-arrow { flex: none; padding-top: 1px; color: #a9b7cf; font-size: 12px; }
.chat-source-chip { display: inline-flex; max-width: 240px; align-items: center; gap: 4px; padding: 2px 7px; border: 1px solid #e6eaf1; border-radius: 999px; color: #7a8494; background: #f7f9fc; cursor: pointer; font: inherit; font-size: 10px; line-height: 1.5; transition: background .15s ease, border-color .15s ease, color .15s ease; }
.chat-source-chip:hover, .chat-source-chip.is-active { border-color: #cddaf4; color: #3f5f9d; background: #f0f5ff; }
.chat-source-chip__icon { flex: none; font-size: 12px; }
.chat-source-chip__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-source-chip__count { display: inline-flex; min-width: 14px; height: 14px; align-items: center; justify-content: center; border-radius: 50%; color: #6f86b8; background: #e5edfd; font-size: 9px; }
.chat-source-float { position: fixed; z-index: 10000; width: 340px; max-width: calc(100vw - 24px); max-height: 360px; overflow-y: auto; padding: 10px 12px 12px; border: 1px solid #e1e6ef; border-radius: 9px; color: #38465c; background: #fff; box-shadow: 0 6px 24px rgba(31, 47, 75, .14); font-size: 12px; line-height: 1.65; animation: source-float-in .15s ease-out both; }
.chat-source-float__head { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; margin-bottom: 7px; border-bottom: 1px solid #edf0f5; color: #34425a; font-size: 12px; font-weight: 600; }
.chat-source-float__head .el-icon { color: #7d8ba3; }
.chat-source-float__head em { margin-left: auto; color: #a0a7b4; font-size: 10px; font-style: normal; font-weight: 400; }
.chat-source-chunk + .chat-source-chunk { margin-top: 9px; padding-top: 9px; border-top: 1px dashed #edf0f5; }
.chat-source-chunk__meta { display: flex; gap: 7px; margin-bottom: 2px; color: #7d8ba3; font-size: 10px; }
.chat-source-chunk__source { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-source-chunk p { display: -webkit-box; overflow: hidden; margin: 0; color: #5f6b7d; -webkit-box-orient: vertical; -webkit-line-clamp: 7; line-clamp: 7; white-space: pre-line; overflow-wrap: anywhere; }
@keyframes source-float-in { from { opacity: 0; transform: translateY(-3px); } }
</style>
