<template>
  <Teleport to="body">
    <Transition name="viewer-fade">
      <div v-if="visible" class="image-viewer-overlay" @mousedown.self="onOverlayMouseDown" @mouseup.self="onOverlayMouseUp">
        <div class="image-viewer-header">
          <span class="image-viewer-title">图片预览</span>
          <div class="image-viewer-controls">
            <span class="zoom-info">{{ Math.round(scale * 100) }}%</span>
            <button class="viewer-btn" @click="zoomIn" title="放大">
              <el-icon><ZoomIn /></el-icon>
            </button>
            <button class="viewer-btn" @click="zoomOut" title="缩小">
              <el-icon><ZoomOut /></el-icon>
            </button>
            <button class="viewer-btn" @click="resetTransform" title="重置">
              <el-icon><RefreshRight /></el-icon>
            </button>
            <button class="viewer-btn" @click="close" title="关闭">
              <el-icon><Close /></el-icon>
            </button>
          </div>
        </div>
        <div class="image-viewer-body" ref="bodyRef"
          @wheel.prevent="onWheel"
          @mousedown="startDrag"
          @mousemove="onDrag"
          @mouseup="stopDrag"
          @mouseleave="stopDrag">
          <img ref="imgRef" :src="src" alt="预览图片" draggable="false"
            :style="{
              transform: `translate(${posX}px, ${posY}px) scale(${scale})`,
              cursor: isDragging ? 'grabbing' : 'grab'
            }" @load="onImageLoad" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { ZoomIn, ZoomOut, RefreshRight, Close } from '@element-plus/icons-vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  src: { type: String, default: '' }
})

const emit = defineEmits(['update:visible'])

const bodyRef = ref<HTMLElement | null>(null)
const imgRef = ref<HTMLElement | null>(null)
const scale = ref(1)
const posX = ref(0)
const posY = ref(0)
const isDragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartPosX = 0
let dragStartPosY = 0
let overlayMouseDownTarget: EventTarget | null = null

function onImageLoad() {
  resetTransform()
}

function resetTransform() {
  scale.value = 1
  posX.value = 0
  posY.value = 0
}

function zoomIn() {
  scale.value = Math.min(10, scale.value + 0.25)
}

function zoomOut() {
  scale.value = Math.max(0.1, scale.value - 0.25)
}

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  scale.value = Math.max(0.1, Math.min(10, scale.value + delta))
}

function startDrag(e: MouseEvent) {
  if (e.button !== 0) return
  isDragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartPosX = posX.value
  dragStartPosY = posY.value
}

function onDrag(e: MouseEvent) {
  if (!isDragging.value) return
  posX.value = dragStartPosX + (e.clientX - dragStartX)
  posY.value = dragStartPosY + (e.clientY - dragStartY)
}

function stopDrag() {
  isDragging.value = false
}

function onOverlayMouseDown(e: MouseEvent) {
  overlayMouseDownTarget = e.target
}

function onOverlayMouseUp(e: MouseEvent) {
  if (overlayMouseDownTarget === e.target) {
    close()
  }
  overlayMouseDownTarget = null
}

function close() {
  emit('update:visible', false)
}

function onKeydown(e: KeyboardEvent) {
  if (!props.visible) return
  if (e.key === 'Escape') {
    close()
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    nextTick(() => resetTransform())
    document.addEventListener('keydown', onKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    document.removeEventListener('keydown', onKeydown)
    document.body.style.overflow = ''
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<style scoped>
.image-viewer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 9999;
  display: flex;
  flex-direction: column;
}

.image-viewer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: rgba(0, 0, 0, 0.4);
  z-index: 1;
}

.image-viewer-title {
  color: #fff;
  font-size: 14px;
  font-weight: 500;
}

.image-viewer-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.zoom-info {
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  min-width: 44px;
  text-align: center;
  background: rgba(255, 255, 255, 0.1);
  padding: 4px 8px;
  border-radius: 4px;
}

.viewer-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  font-size: 18px;
}

.viewer-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.image-viewer-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  user-select: none;
}

.image-viewer-body img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  transition: transform 0.05s ease;
  transform-origin: center center;
  pointer-events: none;
}

.viewer-fade-enter-active,
.viewer-fade-leave-active {
  transition: opacity 0.2s ease;
}

.viewer-fade-enter-from,
.viewer-fade-leave-to {
  opacity: 0;
}
</style>
