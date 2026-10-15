<template>
  <div v-if="items.length" class="chat-attachment-list" :class="{ 'is-compact': compact }">
    <!--
      每一项都显示**文件自带的名字**（含扩展名）。
      文档的图标里带扩展名只是「类型标识」，真正的名字必须显示在右边 ——
      只挂一个 "DOCX" 之类的后缀缩写顶替文件名是不可接受的。
    -->
    <div v-for="(att, i) in items" :key="i" class="att-item" :class="{ 'is-image': isImage(att) }"
      :title="att.name">
      <!-- 图片：列表用缩略图（小、快），点开查看器里换用大图（清晰） -->
      <img v-if="isImage(att)" class="att-thumb" :src="listSrcOf(att)" :alt="att.name"
        @click="openViewer(i)" />
      <!-- 文档：类型图标，点击可在线预览内容（图文交错） -->
      <div v-else class="att-icon" @click="openViewer(i)">
        <span class="att-ext">{{ extOf(att.name) }}</span>
      </div>
      <span class="att-name" @click="openViewer(i)">{{ att.name }}</span>

      <button v-if="removable" type="button" class="att-remove" :disabled="disabled"
        @click.stop="remove(i)">×</button>
    </div>

    <!-- 放大查看器：挂在 body 上，避免被抽屉/弹窗的 overflow 裁剪 -->
    <Teleport to="body">
      <div v-if="viewerVisible" class="att-viewer" @click.self="closeViewer">
        <!-- 查看器顶部显示完整文件名（图片也要能看到它自带的命名；
             文档面板自己已有表头，不重复） -->
        <div v-if="current && isImage(current)" class="att-viewer-caption" @click.stop>
          <span class="viewer-name">{{ current.name }}</span>
          <span v-if="current.type" class="viewer-type">{{ current.type }}</span>
        </div>
        <div class="att-viewer-stage" @mousedown="onDragStart" @wheel.prevent="onWheel" @dblclick="resetTransform"
          @click.self="onStageClick">
          <!-- 图片：可滚轮/按钮自由缩放、拖拽平移 -->
          <img v-if="current && isImage(current)" :src="viewSrcOf(current)" :alt="current.name"
            class="att-viewer-img" :style="imgStyle" :class="{ dragging }" draggable="false" />

          <!-- 文档：在线预览解析出来的图文块 -->
          <div v-else-if="current" class="att-viewer-doc" @mousedown.stop @dblclick.stop @wheel.stop>
            <div class="att-viewer-doc-head">
              <span class="doc-title">{{ current.name }}</span>
              <span v-if="docLoading" class="doc-hint">
                <span class="doc-spinner"></span>正在解析文档…
              </span>
              <span v-else-if="docError" class="doc-hint is-warn">{{ docError }}</span>
              <span v-else class="doc-hint">{{ docBlocks.length }} 个内容块</span>
            </div>
            <div class="att-viewer-doc-body">
              <template v-if="docBlocks.length">
                <div v-for="(blk, bi) in docBlocks" :key="bi" class="doc-block" :class="'is-' + blk.type">
                  <div v-if="blk.type === 'text'" class="doc-text">{{ blk.content }}</div>
                  <img v-else-if="blk.imageUrl" :src="blk.imageUrl" class="doc-image" :alt="`配图 ${bi + 1}`" />
                </div>
              </template>
              <div v-else-if="!docLoading" class="doc-empty">
                该文件类型暂不支持在线预览，已在消息中发送给 AI
              </div>
            </div>
          </div>
        </div>

        <div class="att-viewer-toolbar" @click.stop>
          <template v-if="current && isImage(current)">
            <button type="button" title="缩小" @click="zoomBy(0.8)">−</button>
            <span class="att-viewer-scale">{{ Math.round(scale * 100) }}%</span>
            <button type="button" title="放大" @click="zoomBy(1.25)">+</button>
            <button type="button" title="原始尺寸" class="text-btn" @click="resetTransform">1:1</button>
          </template>
          <button type="button" title="关闭" class="text-btn" @click="closeViewer">关闭</button>
        </div>

        <button v-if="items.length > 1" type="button" class="att-viewer-nav prev" title="上一个"
          @click.stop="step(-1)">‹</button>
        <button v-if="items.length > 1" type="button" class="att-viewer-nav next" title="下一个"
          @click.stop="step(1)">›</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { buildDocPreview, dataUrlToFile, isDocFile, parseDocFile } from '@/utils/doc-parse'

/**
 * 聊天附件预览条（输入框上方 / 消息气泡里共用）
 *
 * 行为对齐 DS 网页端：
 *   · 图片显示缩略图，点击**放大**，支持滚轮 / 按钮自由缩放、按住拖拽平移、双击复位
 *   · 文档显示扩展名标签，点击**在线预览内容**（图文交错，与「AI 搭建题库」的富预览一致）
 *   · removable=true 时每项带删除按钮（用于发送前的待发列表）
 *
 * 两个使用位置：
 *   1. AiChatStream 的 #input-header 插槽（发送前，可删除）
 *   2. 消息气泡里（已发送，不可删除）
 *
 * ⚠️ 图片有两套尺寸：列表用 `thumb`（长边 240），查看器用 `preview`（长边 ≤1600）。
 *    历史记录里**只存这两张**（不存原图）。早期记录只有 `thumb`，查看器会退回到它，
 *    看起来会糊 —— 那是老数据，新消息不会再有这个问题。
 */

export interface ChatAttachmentItem {
  name: string
  type?: string
  /** 完整 data URL（发送前 / 当轮对话用；文档的在线预览也靠它现场解析） */
  base64?: string
  /** 列表用的小缩略图（历史记录里存） */
  thumb?: string
  /** 点开查看用的大图（历史记录里存） */
  preview?: string
  /** 文档解析出的图文块（历史记录里存，点开即可预览，无需再请求） */
  blocks?: { type: 'text' | 'image'; content?: string; imageUrl?: string }[]
  /** 解析失败原因（落库时带上，预览里如实显示） */
  error?: string
}

const props = defineProps({
  items: { type: Array as () => ChatAttachmentItem[], default: () => [] },
  /** 待发送模式：显示删除按钮 */
  removable: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  /** 紧凑模式（气泡里用，尺寸略小） */
  compact: { type: Boolean, default: false }
})

const emit = defineEmits(['remove'])

/** 列表显示：优先小缩略图（快），没有才退到查看图 / 原图 */
const listSrcOf = (att?: ChatAttachmentItem) => att?.thumb || att?.preview || att?.base64 || ''
/** 查看器显示：优先原图（最清晰），其次是落库的查看图，最后才是小缩略图 */
const viewSrcOf = (att?: ChatAttachmentItem) => att?.base64 || att?.preview || att?.thumb || ''

const isImage = (att?: ChatAttachmentItem) => {
  if (!att) return false
  if (att.type?.startsWith('image/')) return true
  return /^data:image\//i.test(att.base64 || att.preview || att.thumb || '')
}

const extOf = (name: string) => {
  const i = (name || '').lastIndexOf('.')
  return i > 0 ? name.slice(i + 1).toUpperCase().slice(0, 4) : 'FILE'
}

const remove = (idx: number) => {
  if (props.disabled) return
  emit('remove', idx)
}

/* ===================== 放大 / 预览查看器 ===================== */
const MIN_SCALE = 0.2
const MAX_SCALE = 8
const WHEEL_STEP = 1.12

const viewerVisible = ref(false)
const viewerIndex = ref(0)
const scale = ref(1)
const tx = ref(0)
const ty = ref(0)
const dragging = ref(false)

// 文档在线预览
const docLoading = ref(false)
const docBlocks = ref<{ type: 'text' | 'image'; content?: string; imageUrl?: string }[]>([])
const docError = ref('')
/** 已解析过的块按「附件对象」缓存，来回翻页不重复请求 */
const docCache = new WeakMap<object, { type: 'text' | 'image'; content?: string; imageUrl?: string }[]>()

const current = computed(() => props.items[viewerIndex.value])
const imgStyle = computed(() => ({
  transform: `translate3d(${tx.value}px, ${ty.value}px, 0) scale(${scale.value})`
}))

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v))

const resetTransform = () => {
  scale.value = 1
  tx.value = 0
  ty.value = 0
}

/** 准备文档预览内容：优先用落库的块，其次现场解析 base64，都没有才提示不支持 */
const ensureDocPreview = async () => {
  const att = current.value
  docBlocks.value = []
  docError.value = ''
  if (!att || isImage(att)) return

  const cached = docCache.get(att)
  if (cached?.length) {
    docBlocks.value = cached
    return
  }
  if (att.blocks?.length) {
    docBlocks.value = att.blocks
    docCache.set(att, att.blocks)
    return
  }
  if (!att.base64 || !isDocFile(att.name, att.type)) {
    // 落库时如果带了具体的解析失败原因（例如老版 .doc），就如实告诉她怎么处理
    docError.value = att.error || '该文件类型暂不支持在线预览，已在消息中发送给 AI'
    return
  }

  docLoading.value = true
  try {
    const file = dataUrlToFile(att.base64, att.name, att.type)
    const parsed = file ? await parseDocFile(file) : null
    const preview = await buildDocPreview(parsed)
    if (preview?.blocks?.length) {
      docBlocks.value = preview.blocks
      docCache.set(att, preview.blocks)
    } else {
      docError.value = preview?.error || '没有解析出可预览的内容（可能是扫描件或老版 .doc）'
    }
  } catch (e) {
    console.warn('[ChatAttachmentList] 文档在线预览解析失败:', e)
    docError.value = '解析失败，已按附件发送给 AI'
  } finally {
    docLoading.value = false
  }
}

const openViewer = (idx: number) => {
  viewerIndex.value = idx
  resetTransform()
  viewerVisible.value = true
  document.addEventListener('keydown', onKeydown)
  void ensureDocPreview()
}

const closeViewer = () => {
  viewerVisible.value = false
  dragging.value = false
  docLoading.value = false
  document.removeEventListener('keydown', onKeydown)
}

const step = (delta: number) => {
  const next = (viewerIndex.value + delta + props.items.length) % props.items.length
  viewerIndex.value = next
  resetTransform()
  void ensureDocPreview()
}

const zoomBy = (factor: number) => {
  if (!current.value || !isImage(current.value)) return
  scale.value = clamp(scale.value * factor, MIN_SCALE, MAX_SCALE)
}

const onWheel = (e: WheelEvent) => {
  if (!current.value || !isImage(current.value)) return
  const factor = e.deltaY < 0 ? WHEEL_STEP : 1 / WHEEL_STEP
  zoomBy(factor)
}

let dragFrom = { x: 0, y: 0, tx: 0, ty: 0 }
const onDragStart = (e: MouseEvent) => {
  if (e.button !== 0) return
  // 文档预览里不要触发拖拽（否则选中文字时整块会跟着跑）
  if (!current.value || !isImage(current.value)) return
  dragging.value = true
  dragFrom = { x: e.clientX, y: e.clientY, tx: tx.value, ty: ty.value }
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}
const onDragMove = (e: MouseEvent) => {
  if (!dragging.value) return
  tx.value = dragFrom.tx + (e.clientX - dragFrom.x)
  ty.value = dragFrom.ty + (e.clientY - dragFrom.y)
}
const onDragEnd = () => {
  dragging.value = false
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
}

/** 点空白处关闭；点图片区域不关（避免放大后误关） */
const onStageClick = () => {
  if (current.value && !isImage(current.value)) closeViewer()
}

const onKeydown = (e: KeyboardEvent) => {
  if (!viewerVisible.value) return
  if (e.key === 'Escape') closeViewer()
  else if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
  else if (e.key === '+' || e.key === '=') zoomBy(1.25)
  else if (e.key === '-') zoomBy(0.8)
  else if (e.key === '0') resetTransform()
}

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
})
</script>

<style scoped>
.chat-attachment-list {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 附件是「缩略图 / 类型图标 + 真实文件名」的小卡片，而不是只有后缀缩写的方块 */
.att-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 196px;
  padding: 3px 22px 3px 3px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.is-compact .att-item {
  max-width: 168px;
  padding: 2px 20px 2px 2px;
}

.att-item.is-image {
  cursor: zoom-in;
}

.att-item:hover {
  border-color: #c7d2fe;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.att-thumb,
.att-icon {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.att-thumb {
  object-fit: cover;
  display: block;
  cursor: zoom-in;
}

.is-compact .att-thumb,
.is-compact .att-icon {
  width: 26px;
  height: 26px;
}

.att-icon {
  background: #eef2f7;
  color: #4b5563;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.2px;
  cursor: pointer;
}

/* 文件自带的文件名（超出用省略号，完整名在 title / 查看器里） */
.att-name {
  min-width: 0;
  font-size: 12px;
  line-height: 1.3;
  color: #374151;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.is-compact .att-name {
  font-size: 11px;
}

.att-remove {
  position: absolute;
  top: 50%;
  right: 4px;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 12px;
  line-height: 15px;
  cursor: pointer;
}

.att-remove:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.9);
}

.att-remove:disabled {
  cursor: not-allowed;
}

/* ===================== 放大查看器 ===================== */
.att-viewer {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.88);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  user-select: none;
}

/* 查看器顶部的文件名胶囊（显示图片自带的命名与 MIME） */
.att-viewer-caption {
  position: absolute;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  max-width: 86vw;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(8px);
  color: #f9fafb;
  font-size: 12px;
}

.att-viewer-caption .viewer-name {
  max-width: 60vw;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.att-viewer-caption .viewer-type {
  flex: none;
  opacity: 0.6;
}

.att-viewer-stage {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
}

.att-viewer-img {
  max-width: 88vw;
  max-height: 86vh;
  transform-origin: center center;
  will-change: transform;
  transition: transform 0.08s ease-out;
  -webkit-user-drag: none;
}

.att-viewer-img.dragging {
  cursor: grabbing;
  transition: none;
}

/* ===================== 文档在线预览 ===================== */
.att-viewer-doc {
  width: min(920px, 92vw);
  height: 84vh;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  background: #ffffff;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
  cursor: default;
  user-select: text;
}

.att-viewer-doc-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: #f9fafb;
}

.att-viewer-doc-head .doc-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.att-viewer-doc-head .doc-hint {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6b7280;
}

.att-viewer-doc-head .doc-hint.is-warn {
  color: #b45309;
}

.doc-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #d1d5db;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: doc-spin 0.7s linear infinite;
}

@keyframes doc-spin {
  to {
    transform: rotate(360deg);
  }
}

.att-viewer-doc-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px 22px 28px;
}

.doc-block + .doc-block {
  margin-top: 12px;
}

.doc-text {
  font-size: 13px;
  line-height: 1.75;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
}

.doc-image {
  display: block;
  max-width: 100%;
  max-height: 60vh;
  margin: 0 auto;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.doc-empty {
  padding: 60px 0;
  text-align: center;
  font-size: 13px;
  color: #9ca3af;
}

/* ===================== 工具条 / 翻页 ===================== */
.att-viewer-toolbar {
  position: absolute;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(8px);
}

.att-viewer-toolbar button {
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #f9fafb;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.att-viewer-toolbar button:hover {
  background: rgba(255, 255, 255, 0.18);
}

.att-viewer-toolbar .text-btn {
  font-size: 12px;
}

.att-viewer-scale {
  min-width: 52px;
  text-align: center;
  color: #f9fafb;
  font-size: 12px;
  opacity: 0.85;
}

.att-viewer-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #f9fafb;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;
}

.att-viewer-nav:hover {
  background: rgba(255, 255, 255, 0.22);
}

.att-viewer-nav.prev {
  left: 24px;
}

.att-viewer-nav.next {
  right: 24px;
}
</style>
