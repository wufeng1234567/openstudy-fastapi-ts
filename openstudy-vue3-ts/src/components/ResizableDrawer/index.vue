<!-- components/ResizableDrawer/index.vue -->
<!--
  可拖拽拉伸的通用抽屉容器
  ==========================
  提炼自 OpenStudy 悬浮助手（`AiAssistant/index.vue`）里那个「右侧、可鼠标拖拽调宽」的
  抽屉 —— 它的拖拽实现质量很高，值得复用：

    · rAF 节流 + **拖拽期间直接写 DOM 宽度**（不改响应式 ref）：改 ref 会让每帧 diff
      整个组件；消息一多（几百节点、markdown、卡片）单帧几十毫秒 → 拖动像幻灯片。
      直接写 style 只让浏览器做一次布局，完全不进 Vue 渲染管线。
    · 拖拽期关闭 `transition`（el-drawer 自带 `transition: all .3s` 会把拖拽"拖住"）。
    · **可选**的滚动锚点：拖拽时记住"视口顶部那条消息"，松手后复原，避免跳位。
      （只有含长列表的抽屉需要，如悬浮助手；知识库这种没列表的不用传 `anchorSelector`。）
    · 宽度持久化（可关）：`storageKey` 有值才读写 localStorage。

  ⚠️ 本组件是**纯容器**：不关心内容，全部由默认插槽提供。调用方只管：
     `<ResizableDrawer v-model="visible" storage-key="x" direction="rtl">…内容…</ResizableDrawer>`

  ⚠️ 组件用 `defineExpose` 暴露 `open()/close()`，方便上层（如工具栏按钮）直接开。
-->

<template>
  <el-drawer
    v-model="innerVisible"
    :direction="direction"
    :size="width + 'px'"
    :with-header="false"
    append-to-body
    :class="['rd-drawer', `rd-${direction}`, drawerClass]"
  >
    <!-- 拖拽调宽手柄（贴在被拉伸的那条边） -->
    <div
      v-if="resizable"
      class="rd-resize-handle"
      :class="`rd-resize-${direction}`"
      title="拖动调整宽度"
      @mousedown.stop="startResize"
    ></div>
    <div class="rd-body">
      <slot />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 开合（v-model） */
    modelValue: boolean
    /** 抽屉方向：右侧 rtl / 左侧 ltr（默认右侧） */
    direction?: 'rtl' | 'ltr'
    /** 是否允许拖拽调宽（默认 true） */
    resizable?: boolean
    /** 宽度下限（px） */
    min?: number
    /** 宽度上限（px） */
    max?: number
    /** 初始 / 默认宽度（px） */
    defaultWidth?: number
    /** 宽度持久化 key：有值才读写 localStorage（设置类固定宽度抽屉不传） */
    storageKey?: string
    /**
     * 可选：拖拽期间保持滚动位置的滚动容器选择器。
     * 传了才启用「滚动锚点」逻辑（含长列表的抽屉才有必要，如聊天消息流）。
     * 选择器应能命中**本抽屉内**的滚动容器。
     */
    anchorSelector?: string
  }>(),
  {
    direction: 'rtl',
    resizable: true,
    min: 320,
    max: 900,
    defaultWidth: 520,
    storageKey: '',
    anchorSelector: ''
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 打开动画完成后触发（调用方可在此时懒加载内容） */
  (e: 'open'): void
}>()

/* ---------- 开合代理（v-model → el-drawer）---------- */
const innerVisible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})
watch(
  () => props.modelValue,
  (v) => {
    if (v) nextTick(() => emit('open'))
  }
)

/* ---------- 宽度状态 ---------- */
//: 持久化：只在传了 storageKey 时读写
const readStored = (): number => {
  if (!props.storageKey) return props.defaultWidth
  const raw = localStorage.getItem(props.storageKey)
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : props.defaultWidth
}
const width = ref(readStored())
watch(
  () => props.defaultWidth,
  (v) => {
    // 调用方改了默认值且当前没在用持久化 → 跟随（保持受控）
    if (!props.storageKey) width.value = v
  }
)

const clamp = (n: number) => Math.max(props.min, Math.min(props.max, n))

/* ---------- 定位本抽屉的 DOM ---------- */
//: 唯一 class：多个抽屉同时存在（可能同方向）时，靠它精确定位到"我自己"那一个
//: （append-to-body 会把抽屉挪出组件树，不能靠 $el / 组件引用）。
const drawerClass = `rd-drawer-${Math.random().toString(36).slice(2, 8)}`

const getDrawerEl = () =>
  document.querySelector<HTMLElement>(`.rd-drawer.${drawerClass}`)

/** 拖拽期关闭过渡（与 el-drawer 官方 is-dragging 类一致），结束后恢复 */
const setTransition = (enabled: boolean) => {
  const el = getDrawerEl()
  if (!el) return
  if (enabled) {
    el.classList.remove('is-dragging')
    el.style.transition = ''
  } else {
    el.classList.add('is-dragging')
    el.style.transition = 'none'
  }
}

/* ---------- 拖拽 ---------- */
let isResizing = false
let startX = 0
let startSize = 0
let raf = 0
let nextSize = width.value

const startResize = (e: MouseEvent) => {
  e.preventDefault()
  e.stopPropagation()
  isResizing = true
  startX = e.clientX
  startSize = width.value
  nextSize = width.value
  setTransition(false)
  captureAnchor()
  document.addEventListener('mousemove', onResize, { passive: false })
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const onResize = (e: MouseEvent) => {
  if (!isResizing) return
  e.preventDefault()
  // rtl：向左拖变宽（起点 - 当前）；ltr：向右拖变宽（当前 - 起点）
  const delta = props.direction === 'rtl' ? startX - e.clientX : e.clientX - startX
  nextSize = clamp(startSize + delta)
  // rAF 节流：每帧只写一次宽度
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    // ⚡ 直接写 DOM 宽度，不进 Vue 渲染管线（见文件头注释）
    const el = getDrawerEl()
    if (el) el.style.width = nextSize + 'px'
  })
}

const stopResize = () => {
  if (!isResizing) return
  isResizing = false
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
  // 收尾：把最终值同步回 ref（只渲染一次，值相同无跳动）
  width.value = nextSize
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  if (props.storageKey) localStorage.setItem(props.storageKey, String(nextSize))
  nextTick(() => {
    if (isResizing) return
    setTransition(true)
    requestAnimationFrame(() => {
      if (!isResizing) restoreAnchor()
    })
  })
}

/* ---------- 滚动锚点（可选，仅传了 anchorSelector 才启用）---------- */
let anchorEl: HTMLElement | null = null
let anchorOffset = 0
let wasAtBottom = false
let hasAnchor = false

const getAnchorEl = () =>
  props.anchorSelector
    ? document.querySelector<HTMLElement>(props.anchorSelector)
    : null

const captureAnchor = () => {
  hasAnchor = false
  if (!props.anchorSelector) return
  const box = getAnchorEl()
  if (!box) return
  wasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50
  const boxTop = box.getBoundingClientRect().top
  for (const el of Array.from(box.children) as HTMLElement[]) {
    const rect = el.getBoundingClientRect()
    if (rect.bottom > boxTop) {
      anchorEl = el
      anchorOffset = rect.top - boxTop
      hasAnchor = true
      return
    }
  }
}

const restoreAnchor = () => {
  if (!hasAnchor && !wasAtBottom) return
  const box = getAnchorEl()
  const anchor = anchorEl
  const atBottom = wasAtBottom
  const off = anchorOffset
  anchorEl = null
  hasAnchor = false
  wasAtBottom = false
  if (!box) return
  if (atBottom) {
    box.scrollTop = box.scrollHeight
    return
  }
  if (!anchor || !anchor.isConnected) return
  const boxTop = box.getBoundingClientRect().top
  const delta = anchor.getBoundingClientRect().top - boxTop - off
  if (Math.abs(delta) > 1) box.scrollTop += delta
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onResize)
  document.removeEventListener('mouseup', stopResize)
})

defineExpose({
  open: () => emit('update:modelValue', true),
  close: () => emit('update:modelValue', false),
  getWidth: () => width.value
})
</script>

<style scoped>
/* 拖拽手柄：贴在被拉伸的那条边，窄条 + 悬停变色 */
.rd-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 6px;
  z-index: 10;
  cursor: col-resize;
  background: transparent;
  transition: background 0.15s ease;
}
.rd-resize-handle:hover {
  background: rgba(79, 110, 247, 0.25);
}
/* rtl（右侧抽屉）：手柄在抽屉**左**边 */
.rd-resize-rtl {
  left: 0;
}
/* ltr（左侧抽屉）：手柄在抽屉**右**边 */
.rd-resize-ltr {
  right: 0;
}

.rd-body {
  height: 100%;
  overflow: hidden;
}
</style>

<style>
/* 抽屉 body 去内边距（内容自管）——与 KnowledgeBaseDrawer 同口径 */
.rd-drawer .el-drawer__body {
  padding: 0;
  overflow: hidden;
  position: relative;
}
</style>
