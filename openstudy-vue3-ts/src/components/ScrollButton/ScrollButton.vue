<!--
  ScrollButton —— 「回到顶部 / 跳到底部」双向悬浮按钮
  ============================================================================
  用户 2026-10-18 bug4：「浏览模式下，右下角应该出现一键滚动顶部和底部的按钮，
  不知道为什么没了」。

  ## 旧实现的三个问题

  1. **只有一个按钮**，点它按"最近一次滚动方向"决定去顶还是去底
     （`scrollDirection === 'down' ? 到底 : 到顶`）。用户根本不知道该按钮会去哪，
     等于要"猜"——这不是它的名字（ScrollButton）承诺的能力。
  2. **只能监听 window**：`handleScroll` 里读的是 `document.documentElement.scrollTop`。
     但练习页的「整体浏览模式」是在 `.overview-question-stream` 这个**内部容器**里滚的
     （见 `PracticeComponent.vue` 的 `@scroll.passive="onStreamScroll"`），
     `documentElement.scrollTop` 恒为 0 → `visible` 永远 false → 按钮从不出现。
  3. **2 秒自动隐藏**：滚完手一停就消失，用户想点时已经没了。

  ## 现在的做法

  - **两个按钮**：↑ 回到顶部、↓ 跳到底部，各自独立、随时可点；
  - **容器可配置**：传 `scroll-container`（元素或选择器）就监听它，
    不传则监听最近一个**可滚动祖先**（自动向上找，找不到才退回 window）；
  - **不自动隐藏**：只在"需要时才出现"——已经在顶部就隐藏 ↑，
    已经在底部就隐藏 ↓，两个都不可用时整组隐藏；
  - 位置改为 `position: fixed` 贴右下角（旧实现在容器模式下算绝对坐标，
    容器一滚就飘）。

  ## 为什么用 ResizeObserver + MutationObserver

  内容高度变化（切题、展开解析、图片加载完）时用户并没有滚动，
  但"是否到底"的判断变了。只在 scroll 时更新会出现「明明能滚了但按钮没出现」，
  所以补一个尺寸/结构变化的重算。
-->
<template>
  <!--
    ⚠️ 外面这层 `div.os-scroll-fab-host` **必须存在且不受 v-if 影响**：
       它既是定位容器，也是 `onMounted` 里"从挂载点向上找可滚动祖先"的起点。
       之前把 v-if 放在最外层、组件又没有稳定根节点时，Vue 会把它渲染成注释节点，
       `vnode.el` 拿不到元素 → 向上找祖先直接失败 → 滚到哪按钮都不出现
       （用户 2026-10-18 bug4 实测）。
  -->
  <div class="os-scroll-fab-host">
    <transition name="os-scroll-fade">
      <div v-if="canUp || canDown" class="os-scroll-fab" :style="posStyle">
        <button
          v-if="canUp"
          type="button"
          class="os-scroll-btn"
          aria-label="回到顶部"
          title="回到顶部"
          @click="scrollToTop"
        >
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
            stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m18 15-6-6-6 6" />
          </svg>
        </button>
        <button
          v-if="canDown"
          type="button"
          class="os-scroll-btn"
          aria-label="跳到底部"
          title="跳到底部"
          @click="scrollToBottom"
        >
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
            stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>
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
     * 不传则自动向上找最近的可滚动祖先，兜底是 window（整页滚）。
     */
    scrollContainer?: any
  }>(),
  { bottom: 24, right: 24, scrollContainer: null }
)

/** 离顶部/底部多远才算"不在端点上"（避免 1px 抖动导致按钮闪烁） */
const EDGE_TOLERANCE = 24

const canUp = ref(false)
const canDown = ref(false)

const posStyle = computed(() => ({
  right: `${props.right}px`,
  bottom: `${props.bottom}px`
}))

/** @type {HTMLElement | Window | null} 真正在滚的东西 */
let target: any = null
let raf = 0
let resizeObserver: ResizeObserver | null = null
let mutationObserver: MutationObserver | null = null

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
 * 什么时候会走到这里（2026-10-18 bug4 实测）：
 *   `.os-scroll-fab-host` 挂在 `PracticeComponent` 里，而该组件在 `<transition>`
 *   和 KeepAlive 下可能于 `.os-content` 尚未挂载/尚未撑开时被 mount —— 那时向上找
 *   每一层都 `scrollHeight === clientHeight`，最后退回 window；可 window 又不滚
 *   （整页高度 = 视口），于是 `top/max` 恒为 0，按钮永不出现。
 *
 * 判据：overflowY 可滚 + 实际内容溢出，取**溢出量最大**的那个
 * （页面上可能同时有多个滚动区，主内容区通常溢出最多）。找不到才退回 window。
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
    // 组件 ref 拿到的可能是组件实例，取 $el
    if (given.$el) return given.$el
    if (given instanceof HTMLElement) return given
  }
  // 1) 从本组件挂载点往上找
  const fromParent = findScrollParent(hostEl)
  if (fromParent !== window) return fromParent

  // 2) 兜底：全文档找溢出最多的主滚动区
  const main = findMainScroller()
  if (main) return main

  // 3) 都没有：整页滚就监听 window，否则 window 也不会动（调用方应显式传容器）
  return window
}

let hostEl: HTMLElement | null = null

/** 读取滚动位置（window 与元素两种口径） */
function readScroll() {
  if (!target) return { top: 0, max: 0 }
  if (target === window) {
    const doc = document.documentElement
    return { top: window.scrollY || doc.scrollTop || 0, max: doc.scrollHeight - window.innerHeight }
  }
  return {
    top: target.scrollTop || 0,
    max: (target.scrollHeight || 0) - (target.clientHeight || 0)
  }
}

/** 重算两个方向按钮是否可用 */
function recalc() {
  const { top, max } = readScroll()
  canUp.value = top > EDGE_TOLERANCE
  canDown.value = max > EDGE_TOLERANCE && top < max - EDGE_TOLERANCE
  // 调试出口：排查"按钮不出现"时可在控制台读它（生产环境无副作用）
  ;(window as any).__osScrollDebug = {
    targetTag: target === window ? 'window' : (target as HTMLElement)?.className || (target as HTMLElement)?.tagName,
    top,
    max,
    canUp: canUp.value,
    canDown: canDown.value
  }
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    recalc()
  })
}

function goTo(top: number, smooth = true) {
  if (!target) return
  const behavior = smooth ? 'smooth' : 'auto'
  if (target === window) {
    window.scrollTo({ top, behavior })
  } else {
    target.scrollTo({ top, behavior })
  }
}

const scrollToTop = () => goTo(0)
const scrollToBottom = () => goTo(readScroll().max)

function bind() {
  unbind()
  target = resolveTarget()
  if (!target) return
  target.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)

  // 内容尺寸/结构变化时也要重算（图片加载、切题、展开解析都不会触发 scroll）
  if (typeof ResizeObserver !== 'undefined' && target !== window) {
    resizeObserver = new ResizeObserver(onScroll)
    resizeObserver.observe(target)
    // 监听内容层（target 的第一个子元素）高度变化
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
  /*
   * 定位起点：优先用模板里那层**稳定存在**的 `.os-scroll-fab-host`（它不受 v-if 影响）。
   * ⚠️ 不要用 `getCurrentInstance()?.vnode.el`：本组件被 `<transition>` 包裹时，
   *    v-if 为假的那一瞬间它可能是注释节点，向上找祖先会提前断掉。
   */
  const inst = getCurrentInstance()
  const el = (inst?.vnode.el as HTMLElement | null)
    ?? document.querySelector<HTMLElement>('.os-scroll-fab-host')
  hostEl = el instanceof HTMLElement ? el : null

  requestAnimationFrame(bind)
  /*
   * 再补两次重绑：首次 mount 时外层容器（`.os-content` 等）可能还没把内容撑开，
   * 那时每一层都"不溢出"，只能退回 window；等布局稳定后再绑一次才能真正对上。
   * 这是"内容异步加载 → 滚动区后出现"的通用补丁，代价只有两次 rAF/定时。
   */
  setTimeout(bind, 300)
  setTimeout(bind, 1200)
})

onBeforeUnmount(unbind)

// 容器变化（例如从"单题模式"切到"整体浏览模式"）→ 重新绑定
watch(
  () => props.scrollContainer,
  () => {
    requestAnimationFrame(bind)
  }
)

// 对外暴露，页面切换视图后可手动重算
defineExpose({ recalc, scrollToTop, scrollToBottom })
</script>

<style scoped>
.os-scroll-fab {
  position: fixed;
  z-index: 900;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.os-scroll-btn {
  width: 38px;
  height: 38px;
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
