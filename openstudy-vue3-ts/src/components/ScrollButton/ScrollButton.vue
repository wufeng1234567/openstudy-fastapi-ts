<!--
  ScrollButton —— 单个「一键滚动」悬浮按钮（方向随滚动位置自动切换）
  ============================================================================
  设计意图（用户 2026-10-18 明确）：
    **只有一个按钮**。它检测当前滚动位置——
      · 已经滚下去（不在顶部）→ 显示 ↑，点它回到顶部；
      · 已经在底部附近       → 显示 ↓，点它去底部。
    也就是"同一个按钮，箭头方向随你在哪而变"，不是两个按钮并排。

  ⚠️ 我在 2026-10-18 那轮改动里把它拆成了**两个**按钮（↑ 和 ↓ 各一个），
     属于误读需求，用户随后指出「你把他们区分开来了」。
     这里恢复成单按钮，并保留那次修好的两件事（见下）。

  ## 那一轮修对的部分（必须保留）

  1. **滚动容器必须自动侦测**。旧实现只读 `document.documentElement.scrollTop`，
     而练习页真正在滚的是外壳 `.os-content`（实测 sh 4938 / ch 948），
     `documentElement` 恒为 0 → 按钮永不出现（这正是用户报的 bug4）。
  2. **不要 2 秒自动隐藏**：手一停按钮就没了，想点时已经找不到。

  ## 方向判定

  优先用"是否还能继续往下滚"：
    · 还能往下（`top < max - 容差`）→ 显示 ↓（去底部）
    · 已经到底（`top >= max - 容差`）且不在顶部 → 显示 ↑（回顶部）
    · 内容根本不溢出 → 不显示

  这比"上次滚动方向"可靠：用户点完 ↓ 到达底部后，按钮会**自动变成 ↑**，
  再点一次就回到顶部——符合"一个按钮走完全程"的预期。
-->
<template>
  <!--
    ⚠️ 外面这层 `div.os-scroll-fab-host` **必须存在且不受 v-if 影响**：
       它既是定位容器，也是 `onMounted` 里"从挂载点向上找可滚动祖先"的起点。
       若把 v-if 放到最外层，`<transition>` 下可能渲染成注释节点，
       `vnode.el` 拿不到元素 → 找不到滚动容器 → 按钮永不出现。
  -->
  <div class="os-scroll-fab-host">
    <transition name="os-scroll-fade">
      <button
        v-if="visible"
        type="button"
        class="os-scroll-btn"
        :style="posStyle"
        :aria-label="direction === 'down' ? '滚动到底部' : '回到顶部'"
        :title="direction === 'down' ? '滚动到底部' : '回到顶部'"
        @click="onClick"
      >
        <svg
          v-if="direction === 'down'"
          viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
          stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
        <svg
          v-else
          viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
          stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
        >
          <path d="m18 15-6-6-6 6" />
        </svg>
      </button>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, getCurrentInstance, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 距底距离 */
    bottom?: number
    /** 距右距离 */
    right?: number
    /**
     * 滚动容器：DOM 元素或选择器字符串。
     * 不传则自动向上找最近的可滚动祖先 / 全文档主滚动区，最后退回 window。
     */
    scrollContainer?: any
  }>(),
  { bottom: 24, right: 24, scrollContainer: null }
)

/**
 * 端点容差：离顶部/底部多少像素以内算"已经在端点"
 *
 * 取 40 而不是 1：避免"差几像素没到底"时按钮一直显示 ↓，
 * 用户点了也几乎不动（因为已经接近底部），观感像"点了没反应"。
 */
const EDGE_TOLERANCE = 40

const direction = ref<'up' | 'down'>('down')
const visible = ref(false)

const posStyle = computed(() => ({
  right: `${props.right}px`,
  bottom: `${props.bottom}px`
}))

/** @type {HTMLElement | Window | null} 真正在滚的东西 */
let target: any = null
let raf = 0
let resizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null
let hostEl: HTMLElement | null = null

/** 向上找一个"内容确实超出"的可滚动祖先 */
function findScrollParent(el: HTMLElement | null): any {
  let node: HTMLElement | null = el
  while (node && node !== document.body && node !== document.documentElement) {
    const style = getComputedStyle(node)
    const scrollable = /(auto|scroll|overlay)/.test(style.overflowY)
    if (scrollable && node.scrollHeight > node.clientHeight + 4) return node
    node = node.parentElement
  }
  return window
}

/**
 * 兜底：全文档里找"最像主滚动区"的元素
 *
 * 为什么要它：`.os-scroll-fab-host` 挂在页面组件里，而组件可能在 `<transition>` /
 * KeepAlive 下、于外壳内容区尚未撑开时 mount —— 那时向上找每一层都不溢出，
 * 只能退回 window；但整页高度 = 视口时 window 根本不动，`top/max` 恒为 0。
 * 判据：overflowY 可滚 + 内容溢出，取**溢出量最大**的那个。
 */
function findMainScroller(): any {
  let best: HTMLElement | null = null
  let bestOverflow = 0
  const nodes = document.querySelectorAll<HTMLElement>(
    '.os-content, .os-main, .main-content, .overview-question-stream, [class*="content"]'
  )
  for (const node of nodes) {
    const style = getComputedStyle(node)
    if (!/(auto|scroll|overlay)/.test(style.overflowY)) continue
    const overflow = node.scrollHeight - node.clientHeight
    if (overflow > bestOverflow) {
      best = node
      bestOverflow = overflow
    }
  }
  return bestOverflow > 4 ? best : null
}

/** 解析目标容器 */
function resolveTarget(): any {
  const given = props.scrollContainer
  if (given) {
    if (typeof given === 'string') return document.querySelector(given) || window
    if (given.$el) return given.$el
    if (given instanceof HTMLElement) return given
  }
  const fromParent = findScrollParent(hostEl)
  if (fromParent !== window) return fromParent
  const main = findMainScroller()
  if (main) return main
  return window
}

/** 读取滚动位置（window 与元素两种口径） */
function readScroll() {
  if (!target) return { top: 0, max: 0 }
  if (target === window) {
    const doc = document.documentElement
    return {
      top: window.scrollY || doc.scrollTop || 0,
      max: Math.max(0, doc.scrollHeight - window.innerHeight)
    }
  }
  return {
    top: target.scrollTop || 0,
    max: Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0))
  }
}

/**
 * 重算"是否显示"与"箭头朝哪"
 *
 * 规则（单一按钮能走完全程）：
 *   · 内容不溢出（max 很小）→ 不显示；
 *   · 还能往下滚            → 显示 ↓（去底部）；
 *   · 已经快到底且不在顶部  → 显示 ↑（回顶部）；
 *   · 顶部且已到底（不可能同时成立，兜底隐藏）。
 */
function recalc() {
  const { top, max } = readScroll()

  if (max <= EDGE_TOLERANCE) {
    // 内容没溢出 / 几乎不溢出：没有滚动这回事
    visible.value = false
    return
  }

  const atTop = top <= EDGE_TOLERANCE
  const atBottom = top >= max - EDGE_TOLERANCE

  if (atBottom && atTop) {
    visible.value = false
    return
  }

  // 还能往下 → 去底部；否则（已在底部）→ 回顶部
  direction.value = atBottom ? 'up' : 'down'
  visible.value = true

  // 调试出口：排查"按钮不出现"时可在控制台读它
  ;(window as any).__osScrollDebug = {
    targetTag:
      target === window
        ? 'window'
        : (target as HTMLElement)?.className || (target as HTMLElement)?.tagName,
    top,
    max,
    atTop,
    atBottom,
    direction: direction.value,
    visible: visible.value
  }
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    recalc()
  })
}

function onClick() {
  if (!target) return
  const to = direction.value === 'down' ? readScroll().max : 0
  if (target === window) {
    window.scrollTo({ top: to, behavior: 'smooth' })
  } else {
    target.scrollTo({ top: to, behavior: 'smooth' })
  }
  // 平滑滚动会连续触发 scroll 事件，recalc 会自动把方向翻过来（到底后变 ↑）
}

function bind() {
  unbind()
  target = resolveTarget()
  if (!target) return
  target.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)

  // 内容尺寸/结构变化时也要重算（切题、展开解析、图片加载都不触发 scroll）
  if (typeof ResizeObserver !== 'undefined' && target !== window) {
    resizeObserver = new ResizeObserver(onScroll)
    resizeObserver.observe(target)
    const inner = (target as HTMLElement).firstElementChild
    if (inner) resizeObserver.observe(inner)
  }
  if (typeof MutationObserver !== 'undefined' && target !== window) {
    mutationObserver = new MutationObserver(onScroll)
    mutationObserver.observe(target as HTMLElement, { childList: true, subtree: true })
  }

  recalc()
}

function unbind() {
  if (target) target.removeEventListener?.('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  resizeObserver?.disconnect()
  resizeObserver = null
  mutationObserver?.disconnect()
  mutationObserver = null
  target = null
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
}

onMounted(() => {
  const inst = getCurrentInstance()
  const el =
    (inst?.vnode.el as HTMLElement | null) ??
    document.querySelector<HTMLElement>('.os-scroll-fab-host')
  hostEl = el instanceof HTMLElement ? el : null

  requestAnimationFrame(bind)
  /*
   * 再补两次重绑：首次 mount 时外层容器可能还没把内容撑开（每层都"不溢出"，
   * 只能退回 window），等布局稳定后再绑一次才能真正对上。
   */
  setTimeout(bind, 300)
  setTimeout(bind, 1200)
})

onBeforeUnmount(unbind)

// 容器变化（例如切换练习模式）→ 重新绑定
watch(
  () => props.scrollContainer,
  () => {
    requestAnimationFrame(bind)
  }
)

/** 对外暴露，页面切换视图后可手动重算 */
defineExpose({ recalc, onClick })
</script>

<style scoped>
.os-scroll-fab-host {
  /* 定位容器本身不占位；按钮是 fixed，挂在它下面只为有个稳定挂载点 */
  display: contents;
}

.os-scroll-btn {
  position: fixed;
  z-index: 900;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 50%;
  background: #fff;
  color: var(--os-text-3, #61666b);
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: color var(--ds-duration-fast, 0.15s) var(--ds-ease-in-out, ease),
    border-color var(--ds-duration-fast, 0.15s) var(--ds-ease-in-out, ease),
    background-color var(--ds-duration-fast, 0.15s) var(--ds-ease-in-out, ease),
    transform var(--ds-duration-fast, 0.15s) var(--ds-ease-in-out, ease);
}

.os-scroll-btn:hover {
  color: var(--os-text, #0f1115);
  border-color: var(--os-border-strong, #d1d5db);
  background: var(--os-bg-hover, #f9fafb);
  transform: translateY(-1px);
}

.os-scroll-btn:active {
  transform: translateY(0);
}

.os-scroll-btn:focus-visible {
  outline: 2px solid var(--os-primary, #0f1115);
  outline-offset: 2px;
}

.os-scroll-fade-enter-active,
.os-scroll-fade-leave-active {
  transition: opacity 0.16s ease;
}

.os-scroll-fade-enter-from,
.os-scroll-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .os-scroll-btn,
  .os-scroll-fade-enter-active,
  .os-scroll-fade-leave-active {
    transition: none;
  }
}
</style>
