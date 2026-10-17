<!--
  AgentOutline —— 对话「提问目录」（右侧竖直导航）
  ============================================================================
  用户 2026-10-17：「在智能对话的右侧水平中间的区域生成一个用户提问跳转目录」。

  形态参考 DSH Web 的对话导航：一条贴在内容右侧、**垂直居中**的细导航。
    · 每条用户提问 = 一根短横线（不是文字列表，不抢正文的注意力）；
    · hover 时才浮出该提问的文字摘要（左向弹出的小卡片）；
    · 当前所在的那一轮高亮；点击平滑滚过去；
    · 会话里只有 1 轮提问时整体隐藏（没有"跳转"的必要，纯噪音）。

  为什么放在 `chat.vue` 的 `.chat-body` 里、而不是 AiChatStream 内部：
    它是"页面级的导航"，要贴在**内容区**右边而不是消息列表右边；
    消息列表自己有 max-width 居中，挂进去会跟着一起收窄。

  实现要点：
    · 锚点用 `[data-msg-idx]`（AiChatStream 每条消息都带），不依赖组件实例；
    · 滚动监听用 `scroll` + rAF 节流（IntersectionObserver 在"多个元素同时在视口"时
      判定哪条是"当前"比较麻烦，这里用"最靠近吸顶线的那条用户消息"更直接）；
    · 滚动容器是 `.chat-messages`，通过 `scrollSelector` 传入，便于复用。
-->
<template>
  <nav v-if="items.length > 1" class="agent-outline" aria-label="提问目录">
    <button
      v-for="(item, i) in items"
      :key="item.idx"
      type="button"
      :class="['ao-dot', { 'is-active': i === activeIndex }]"
      :aria-label="`跳到第 ${i + 1} 条提问：${item.text}`"
      @click="jumpTo(item)"
      @mouseenter="hoverIndex = i"
      @mouseleave="hoverIndex = -1"
    >
      <span class="ao-bar" />
      <!-- hover 才出现的摘要（左向弹出，不遮挡右侧内容） -->
      <span v-if="hoverIndex === i" class="ao-tip">{{ item.text }}</span>
    </button>
  </nav>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 完整消息数组（与传给 AiChatStream 的是同一份） */
    messages: any[]
    /** 滚动容器的选择器（默认对话页的消息列表） */
    scrollSelector?: string
    /** 摘要最多显示多少字 */
    maxChars?: number
  }>(),
  {
    scrollSelector: '.chat-messages',
    maxChars: 60
  }
)

const hoverIndex = ref(-1)
const activeIndex = ref(0)

/** 只取「用户提问」作为目录项（工具卡 / 进度 / 思考都不算） */
const items = computed(() => {
  const list: Array<{ idx: number; text: string }> = []
  props.messages.forEach((m: any, idx: number) => {
    if (m?.role !== 'user') return
    const raw = String(m.content || '').replace(/\s+/g, ' ').trim()
    // 空提问（例如只发了附件）给一个兜底文案，否则目录里会出现一根"无名"横线
    const text = raw
      ? raw.length > props.maxChars
        ? raw.slice(0, props.maxChars) + '…'
        : raw
      : '（附件消息）'
    list.push({ idx, text })
  })
  return list
})

/* ==================== 滚动跟随 ==================== */
let scroller: HTMLElement | null = null
let raf = 0

function resolveScroller(): HTMLElement | null {
  return document.querySelector<HTMLElement>(props.scrollSelector)
}

/**
 * 计算当前处于第几条提问。
 *
 * 判据：容器顶部往下 `topOffset` 处画一条"读线"，取**读线之上最后一条**用户消息。
 * 比 IntersectionObserver 简单，且行为可预测（滚动到某条提问时它就立刻高亮）。
 */
function syncActive() {
  if (!scroller || !items.value.length) return
  const top = scroller.getBoundingClientRect().top + 24

  let found = 0
  items.value.forEach((item, i) => {
    const el = scroller!.querySelector<HTMLElement>(`[data-msg-idx="${item.idx}"]`)
    if (!el) return
    if (el.getBoundingClientRect().top <= top) found = i
  })
  activeIndex.value = found
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    syncActive()
  })
}

/** 点击跳转：滚到该消息（留一点上边距，别贴着顶栏） */
function jumpTo(item: { idx: number; text: string }) {
  if (!scroller) return
  const el = scroller.querySelector<HTMLElement>(`[data-msg-idx="${item.idx}"]`)
  if (!el) return
  const delta = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top
  const target = scroller.scrollTop + delta - 16
  scroller.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
}

/* ==================== 生命周期 ==================== */
function bind() {
  scroller = resolveScroller()
  if (!scroller) return
  scroller.addEventListener('scroll', onScroll, { passive: true })
  nextTick(syncActive)
}

function unbind() {
  if (scroller) scroller.removeEventListener('scroll', onScroll)
  scroller = null
  if (raf) {
    cancelAnimationFrame(raf)
    raf = 0
  }
}

onMounted(() => {
  // 消息列表可能还没渲染出来（首屏 hero 状态），稍等一拍再绑
  nextTick(() => window.setTimeout(bind, 60))
})

onBeforeUnmount(unbind)

// 切换会话 / 新对话时长列表会重建，重新绑定并刷新高亮
watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (!scroller) bind()
      syncActive()
    })
  }
)

// 用户换会话时位置会重置，回到第一条
watch(
  () => props.messages[0],
  () => {
    activeIndex.value = 0
    nextTick(syncActive)
  }
)
</script>

<style scoped lang="scss">
/*
 * 贴右侧、垂直居中。
 *
 * ⚠️ 位置用「内容列右缘 + 间距」而不是视口右缘：正文列是 max-width 820 居中的，
 *    窗口越宽、正文右侧的空白越大；若把目录钉在视口边上，它会飘到离正文很远的
 *    角落里（用户看到的观感是"孤零零贴在窗口边缘"）。
 *    1180/2 是正文列半宽（820/2=410，再留出一点呼吸），配合 `calc` 让目录始终
 *    落在"正文结束之后一小段"的位置。窗口更窄时由 @media 直接隐藏。
 */
.agent-outline {
  position: absolute;
  top: 50%;
  right: max(12px, calc(50% - 410px - 46px));
  transform: translateY(-50%);
  z-index: 6;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  padding: 8px 4px;
  pointer-events: none;
  /* 目录本身不要背景，免得像一块浮窗 */
  background: transparent;
}

.ao-dot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  width: 22px;
  height: 12px;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  pointer-events: auto;
}

.ao-bar {
  display: block;
  width: 12px;
  height: 2px;
  border-radius: 1px;
  background: var(--dsw-static-neutral-bluish-300);
  transition: width var(--ds-duration-fast) var(--ds-ease-in-out),
    background-color var(--ds-duration-fast) var(--ds-ease-in-out);
}

.ao-dot:hover .ao-bar {
  width: 18px;
  background: var(--os-text-3);
}

.ao-dot.is-active .ao-bar {
  width: 18px;
  background: var(--os-text);
}

/* hover 摘要：左向弹出的小卡 */
.ao-tip {
  position: absolute;
  right: 26px;
  top: 50%;
  transform: translateY(-50%);
  max-width: 260px;
  padding: 5px 9px;
  border-radius: var(--os-radius-sm);
  background: var(--os-primary);
  color: #fff;
  font-size: 12px;
  line-height: 1.45;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.16);
}

/* 窄屏（抽屉打开 / 小窗口）隐藏：右侧空间不够，会压到正文 */
@media (max-width: 1180px) {
  .agent-outline {
    display: none;
  }
}
</style>
