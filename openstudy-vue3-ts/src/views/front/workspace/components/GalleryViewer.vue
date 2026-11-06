<template>
  <Teleport to="body">
    <div v-if="visible && current" class="gv" :class="{ 'has-info': showInfo }" role="dialog" aria-modal="true">
      <div class="gv-main">
        <header class="gv-topbar">
          <div class="gv-title">
            <span class="gv-counter">{{ position }} / {{ items.length }}</span>
            <span class="gv-name" :title="current.sourceName || current.fileName">{{ current.sourceName || current.fileName || '图片' }}</span>
          </div>
          <div class="gv-tools">
            <button type="button" class="gv-tool" title="缩小" :disabled="!loaded" @click="zoomOut"><el-icon><ZoomOut /></el-icon></button>
            <button type="button" class="gv-tool gv-tool--text" title="重置缩放" :disabled="!loaded" @click="resetView">{{ zoomPercent }}</button>
            <button type="button" class="gv-tool" title="放大" :disabled="!loaded" @click="zoomIn"><el-icon><ZoomIn /></el-icon></button>
            <button type="button" class="gv-tool gv-tool--text" title="原始尺寸" :disabled="!loaded" @click="zoomActual">1:1</button>
            <button type="button" class="gv-tool" title="旋转" :disabled="!loaded" @click="rotate"><el-icon><Refresh /></el-icon></button>
            <span class="gv-tools__sep"></span>
            <button type="button" class="gv-tool" title="下载" :disabled="!loaded" @click="download"><el-icon><Download /></el-icon></button>
            <button type="button" class="gv-tool" title="打开原图" :disabled="!loaded" @click="openOriginal"><el-icon><TopRight /></el-icon></button>
            <button type="button" class="gv-tool" :class="{ 'is-on': showInfo }" title="显示/隐藏信息" @click="toggleInfo"><el-icon><InfoFilled /></el-icon></button>
            <span class="gv-tools__sep"></span>
            <button type="button" class="gv-tool" title="关闭" @click="emit('close')"><el-icon><Close /></el-icon></button>
          </div>
        </header>

        <div ref="stageEl" class="gv-stage" :class="{ 'can-pan': canPan, 'is-dragging': dragging }"
          @wheel.prevent="onWheel" @dblclick="onDblClick" @click.self="emit('close')"
          @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp">
          <img v-if="src && !failed" ref="imgEl" :src="src" :alt="current.caption || current.fileName"
            class="gv-image" :class="{ 'is-loaded': loaded }" :style="imgStyle" draggable="false"
            @load="onImgLoad" @error="onImgError" />
          <div v-if="failed" class="gv-state">图片加载失败</div>
          <el-icon v-else-if="!loaded" class="gv-state gv-state--loading"><Loading /></el-icon>

          <button type="button" class="gv-nav gv-nav--prev" :disabled="position <= 1" @click.stop="prev">
            <el-icon><ArrowLeft /></el-icon>
          </button>
          <button type="button" class="gv-nav gv-nav--next" :disabled="position >= items.length" @click.stop="next">
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>

        <div v-if="items.length > 1" ref="stripEl" class="gv-strip">
          <button v-for="(item, i) in items" :key="item.assetKey" type="button"
            class="gv-strip__item" :class="{ 'is-current': i === index }" @click="emit('select', i)">
            <img :src="displayUrl(item.url)" alt="" draggable="false" />
          </button>
        </div>
      </div>

      <aside v-if="showInfo" class="gv-info">
        <div class="gv-info__content">
          <section class="gv-section">
            <div class="gv-section__head">
              <button type="button" class="gv-section__toggle" @click="captionExpanded = !captionExpanded">
                <h3>图片描述</h3>
                <el-icon><ArrowDown v-if="captionExpanded" /><ArrowRight v-else /></el-icon>
              </button>
              <div class="gv-section__actions">
                <button type="button" class="gv-action-icon" title="复制描述" @click="copyText(current.caption)"><el-icon><CopyDocument /></el-icon></button>
                <button v-if="current.descriptionStatus !== 'done'" type="button" class="gv-action-icon" title="生成描述" @click="emit('describe', current.assetKey)"><el-icon><MagicStick /></el-icon></button>
              </div>
            </div>
            <div v-show="captionExpanded">
              <p v-if="current.caption" class="gv-text">{{ current.caption }}</p>
              <p v-else class="gv-text is-muted">这张图还没有生成描述。</p>
            </div>
          </section>

          <section class="gv-section">
            <div class="gv-section__head">
              <button type="button" class="gv-section__toggle" @click="ocrExpanded = !ocrExpanded">
                <h3>图中文字</h3>
                <el-icon><ArrowDown v-if="ocrExpanded" /><ArrowRight v-else /></el-icon>
              </button>
              <button type="button" class="gv-action-icon" title="复制文字" @click="copyText(current.ocrText)"><el-icon><CopyDocument /></el-icon></button>
            </div>
            <div v-show="ocrExpanded">
              <pre v-if="current.ocrText" class="gv-ocr">{{ current.ocrText }}</pre>
              <p v-else class="gv-text is-muted">这张图暂未识别到文字。</p>
            </div>
          </section>
        </div>

        <section class="gv-section gv-info__details">
          <div class="gv-section__head"><h3>基本信息</h3></div>
          <dl class="gv-props">
            <dt>来源文档</dt>
            <dd><button type="button" class="gv-source" @click="emit('locate', current)">{{ current.sourceName || '未命名资料' }}</button></dd>
            <template v-if="natural">
              <dt>尺寸</dt>
              <dd>{{ natural.w }} × {{ natural.h }}</dd>
            </template>
            <dt>状态</dt>
            <dd><span class="gv-status" :class="`is-${current.descriptionStatus}`">{{ statusLabel(current.descriptionStatus) }}</span></dd>
            <template v-if="current.createTime">
              <dt>创建时间</dt>
              <dd>{{ current.createTime }}</dd>
            </template>
          </dl>
          <div class="gv-actions">
            <button type="button" class="gv-action" @click="emit('insert-question', current)">插入题目</button>
            <button type="button" class="gv-action" @click="emit('insert-note', current)">加入笔记</button>
            <button type="button" class="gv-action" @click="emit('insert-wiki', current)">插入知识百科</button>
          </div>
        </section>
      </aside>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ArrowDown, ArrowLeft, ArrowRight, Close, CopyDocument, Download, InfoFilled,
  Loading, MagicStick, Refresh, TopRight, ZoomIn, ZoomOut
} from '@element-plus/icons-vue'

const props = defineProps<{
  visible: boolean
  items: any[]
  index: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', index: number): void
  (e: 'describe', assetKey: string): void
  (e: 'insert-question', item: any): void
  (e: 'insert-note', item: any): void
  (e: 'insert-wiki', item: any): void
  (e: 'locate', item: any): void
}>()

const current = computed(() => props.items[props.index] || null)
const position = computed(() => props.index + 1)
const src = computed(() => displayUrl(current.value?.url || ''))
const loaded = ref(false)
const failed = ref(false)
const natural = ref<{ w: number; h: number } | null>(null)
const scale = ref(1)
const rotation = ref(0)
const tx = ref(0)
const ty = ref(0)
const dragging = ref(false)
const stageEl = ref<HTMLElement | null>(null)
const imgEl = ref<HTMLImageElement | null>(null)
const stripEl = ref<HTMLElement | null>(null)
const showInfo = ref(true)
const captionExpanded = ref(true)
const ocrExpanded = ref(true)

function displayUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
}

function statusLabel(status: string) {
  return ({ done: '已描述', pending: '待描述', processing: '生成中', failed: '失败' } as Record<string, string>)[status] || '待描述'
}

const zoomPercent = computed(() => `${Math.round(scale.value * 100)}%`)
const canPan = computed(() => loaded.value && scale.value > 1)
const imgStyle = computed(() => ({ transform: `translate(${tx.value}px, ${ty.value}px) rotate(${rotation.value}deg) scale(${scale.value})` }))

function resetView() {
  scale.value = 1
  rotation.value = 0
  tx.value = 0
  ty.value = 0
}

function zoomTo(target: number, anchor?: { x: number; y: number }) {
  const next = Math.min(8, Math.max(0.2, target))
  const k = next / scale.value
  const ax = anchor?.x || 0
  const ay = anchor?.y || 0
  tx.value = ax - (ax - tx.value) * k
  ty.value = ay - (ay - ty.value) * k
  scale.value = next
}

function anchorOf(event: { clientX: number; clientY: number }) {
  const rect = stageEl.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return { x: event.clientX - rect.left - rect.width / 2, y: event.clientY - rect.top - rect.height / 2 }
}

function zoomIn() { zoomTo(scale.value * 1.25) }
function zoomOut() { zoomTo(scale.value / 1.25) }
function zoomActual() {
  if (!imgEl.value || !natural.value) return
  zoomTo(natural.value.w / Math.max(1, imgEl.value.clientWidth))
}
function rotate() {
  rotation.value = (rotation.value + 90) % 360
  resetView()
}
function onWheel(event: WheelEvent) {
  if (!loaded.value) return
  zoomTo(scale.value * Math.exp(-event.deltaY * 0.002), anchorOf(event))
}
function onDblClick(event: MouseEvent) {
  if (!loaded.value) return
  if (Math.abs(scale.value - 1) > 0.01) resetView()
  else zoomTo(2, anchorOf(event))
}
let dragStart: { x: number; y: number; tx: number; ty: number } | null = null
function onPointerDown(event: PointerEvent) {
  if (event.button !== 0 || !canPan.value) return
  dragStart = { x: event.clientX, y: event.clientY, tx: tx.value, ty: ty.value }
  dragging.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
function onPointerMove(event: PointerEvent) {
  if (!dragStart) return
  tx.value = dragStart.tx + event.clientX - dragStart.x
  ty.value = dragStart.ty + event.clientY - dragStart.y
}
function onPointerUp() {
  dragStart = null
  dragging.value = false
}
function onImgLoad() {
  loaded.value = true
  if (imgEl.value) natural.value = { w: imgEl.value.naturalWidth, h: imgEl.value.naturalHeight }
}
function onImgError() {
  failed.value = true
  loaded.value = false
}
function prev() { if (props.index > 0) emit('select', props.index - 1) }
function next() { if (props.index < props.items.length - 1) emit('select', props.index + 1) }
function toggleInfo() { showInfo.value = !showInfo.value }
function copyText(text: string) {
  if (!text) return
  navigator.clipboard?.writeText(text).catch(() => {})
}
async function download() {
  if (!src.value) return
  try {
    const blob = await (await fetch(src.value)).blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = current.value?.fileName || 'image.png'
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch {
    openOriginal()
  }
}
function openOriginal() {
  if (src.value) window.open(src.value, '_blank', 'noopener')
}

watch(() => [props.visible, props.index], async () => {
  resetView()
  loaded.value = false
  failed.value = false
  natural.value = null
  if (!props.visible) return
  await nextTick()
  const el = stripEl.value?.querySelector<HTMLElement>('.gv-strip__item.is-current')
  el?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: 'smooth' })
}, { immediate: true })

function onKey(event: KeyboardEvent) {
  if (!props.visible || event.defaultPrevented) return
  const target = event.target as HTMLElement | null
  if (target?.closest?.('input, textarea, select, [contenteditable="true"]')) return
  if (event.key === 'Escape') { event.preventDefault(); emit('close') }
  else if (event.key === 'ArrowLeft') { event.preventDefault(); prev() }
  else if (event.key === 'ArrowRight') { event.preventDefault(); next() }
  else if (event.key === '+' || event.key === '=') { event.preventDefault(); zoomIn() }
  else if (event.key === '-') { event.preventDefault(); zoomOut() }
  else if (event.key === '0') { event.preventDefault(); resetView() }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.gv { position: fixed; inset: 0; z-index: 3000; display: grid; grid-template-columns: minmax(0, 1fr); background: #111214; color: rgba(255, 255, 255, .88); }
.gv.has-info { grid-template-columns: minmax(0, 1fr) 420px; }
.gv-main { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.gv-topbar { display: flex; height: 54px; flex: none; align-items: center; justify-content: space-between; gap: 16px; padding: 0 14px 0 22px; }
.gv-title { display: flex; min-width: 0; align-items: baseline; gap: 12px; }
.gv-counter { color: rgba(255,255,255,.55); font-size: 15px; white-space: nowrap; }
.gv-name { overflow: hidden; color: rgba(255,255,255,.9); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.gv-tools { display: flex; flex: none; align-items: center; gap: 2px; }
.gv-tools__sep { width: 1px; height: 18px; margin: 0 6px; background: rgba(255,255,255,.16); }
.gv-tool { display: inline-flex; width: 32px; height: 32px; align-items: center; justify-content: center; padding: 0; border: 0; border-radius: 5px; color: rgba(255,255,255,.86); background: transparent; cursor: pointer; font: inherit; font-size: 15px; transition: background .15s ease; }
.gv-tool:hover:not(:disabled), .gv-tool.is-on { background: rgba(255,255,255,.12); }
.gv-tool:disabled { opacity: .3; cursor: default; }
.gv-tool--text { width: auto; min-width: 48px; font-size: 11px; font-variant-numeric: tabular-nums; }
.gv-stage { position: relative; display: flex; flex: 1; min-height: 0; align-items: center; justify-content: center; overflow: hidden; padding: 16px 72px; user-select: none; touch-action: none; }
.gv-stage.can-pan { cursor: grab; }
.gv-stage.is-dragging { cursor: grabbing; }
.gv-image { max-width: 100%; max-height: 100%; object-fit: contain; opacity: 0; transition: transform .15s ease, opacity .15s ease; will-change: transform; }
.gv-image.is-loaded { opacity: 1; }
.gv-stage.is-dragging .gv-image { transition: opacity .15s ease; }
.gv-state { position: absolute; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.55); font-size: 13px; }
.gv-state--loading { font-size: 28px; animation: gv-spin 1s linear infinite; }
.gv-nav { position: absolute; top: 50%; display: flex; width: 44px; height: 44px; margin-top: -22px; align-items: center; justify-content: center; border: 0; border-radius: 50%; color: rgba(255,255,255,.86); background: rgba(255,255,255,.1); cursor: pointer; font-size: 24px; }
.gv-nav:hover:not(:disabled) { background: rgba(255,255,255,.2); }
.gv-nav:disabled { opacity: .2; cursor: default; }
.gv-nav--prev { left: 16px; }
.gv-nav--next { right: 16px; }
.gv-strip { display: flex; flex: none; gap: 6px; overflow-x: auto; padding: 10px 20px 14px; scrollbar-width: thin; }
.gv-strip__item { flex: 0 0 auto; width: 62px; height: 46px; padding: 0; overflow: hidden; border: 2px solid transparent; border-radius: 4px; opacity: .5; background: rgba(255,255,255,.08); cursor: pointer; }
.gv-strip__item img { display: block; width: 100%; height: 100%; object-fit: cover; }
.gv-strip__item:hover { opacity: .85; }
.gv-strip__item.is-current { opacity: 1; border-color: #4f6bed; }
.gv-info { display: flex; min-width: 0; min-height: 0; flex-direction: column; overflow: hidden; border-left: 1px solid #2a2d33; color: #253247; background: #fff; }
.gv-info__content { flex: 1; min-height: 0; overflow-y: auto; padding: 0 20px 20px; }
.gv-section + .gv-section { margin-top: 18px; padding-top: 16px; border-top: 1px solid #edf0f5; }
.gv-section__head { display: flex; min-height: 24px; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 10px; }
.gv-section__toggle { display: flex; min-width: 0; flex: 1; align-items: center; justify-content: space-between; gap: 8px; padding: 0; border: 0; color: #253247; background: transparent; cursor: pointer; font: inherit; text-align: left; }
.gv-section__toggle h3 { position: relative; margin: 0; padding-left: 10px; font-size: 14px; font-weight: 600; }
.gv-section__toggle h3::before { position: absolute; top: 2px; left: 0; width: 3px; height: 14px; border-radius: 2px; background: #10b981; content: ''; }
.gv-section__actions { display: flex; gap: 3px; }
.gv-action-icon { display: inline-flex; width: 25px; height: 25px; align-items: center; justify-content: center; padding: 0; border: 0; border-radius: 4px; color: #7d8596; background: transparent; cursor: pointer; font-size: 14px; }
.gv-action-icon:hover { color: #2f5fce; background: #f3f7ff; }
.gv-text { margin: 0; color: #4b5563; font-size: 13px; line-height: 1.8; white-space: pre-wrap; word-break: break-word; }
.gv-text.is-muted { color: #9aa1af; }
.gv-ocr { max-height: 230px; margin: 0; overflow: auto; color: #4b5563; font-family: inherit; font-size: 12.5px; line-height: 1.75; white-space: pre-wrap; }
.gv-info__details { flex: none; max-height: 44%; overflow-y: auto; padding: 16px 20px 20px; border-top: 1px solid #edf0f5; }
.gv-props { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 9px 14px; margin: 0; font-size: 12px; line-height: 21px; }
.gv-props dt { color: #9aa1af; }
.gv-props dd { min-width: 0; margin: 0; color: #4b5563; word-break: break-word; }
.gv-source { padding: 0; border: 0; color: #12a882; background: transparent; cursor: pointer; font: inherit; text-align: left; }
.gv-source:hover { text-decoration: underline; }
.gv-status { display: inline-block; padding: 1px 8px; border-radius: 4px; color: #12a882; background: #edf9f4; font-size: 11px; }
.gv-status.is-pending { color: #b7791f; background: #fff8e8; }
.gv-status.is-failed { color: #c53030; background: #fff1f1; }
.gv-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.gv-action { padding: 5px 9px; border: 1px solid #e5eaf2; border-radius: 5px; color: #5f6b7d; background: #fff; cursor: pointer; font: inherit; font-size: 11px; }
.gv-action:hover { border-color: #c9d9f8; color: #2f5fce; }
@keyframes gv-spin { to { transform: rotate(360deg); } }
@media (max-width: 900px) { .gv.has-info { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) 44%; } .gv-info { border-top: 1px solid #2a2d33; border-left: 0; } .gv-stage { padding: 12px 52px; } }
</style>
