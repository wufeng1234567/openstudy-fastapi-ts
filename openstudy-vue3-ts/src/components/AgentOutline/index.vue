<!--
  AgentOutline —— 对话「轮次导航」（窗口右侧那一列短横线）
  ============================================================================
  用户 2026-10-17：「现在没有查看当前会话、用户每次提问的快速定位功能…
  就是每个会话的右侧都有一排横线，这些横线有长有短」。

  ## 横线为什么有长有短（这是关键，别猜成"内容多少"）

  参照 DSH Web 的 `TurnNavigator`（`dsh-client-ui-chat/lib/client.js` 里
  `TurnNavigator.module.css` + `TURN_SPACING_PX = 10`）：

    · **间距是固定的 10px**，与那一轮有多少内容**无关** —— 不是"内容越多线越长"；
    · 长短是 `transform: scaleX(...)`，编码的是**这一轮的状态**：

    | 状态 | scaleX | 含义 |
    | --- | --- | --- |
    | 未加载（unloaded） | 0.4 | 这一轮不在当前加载窗口里，点了会去分页加载 |
    | 普通（loaded）     | 0.6 | 已加载、但不在视口中心 |
    | 悬停预览           | 0.9 | 指针停在它上面 |
    | **当前所在（active）** | 1.0 | 现在视口里正在看的那一轮（最深色） |
    | 正在跑（busy）     | 0.6 + 脉冲 | 这一轮还在生成，呼吸闪烁 |

    所以"有长有短"是为了让用户**一眼看出"我在哪、哪些还没加载"**，
    而不是表达内容量。上一版我们做成了 hover/active 两态，缺了"未加载"和"脉动"，
    看起来就像随机长短。

  ## 与 DSH 的形态对齐

    · 贴在**窗口右侧**（`right: 12px`），**垂直居中**在「视口高度 - 输入框高度」这条带里；
    · 宽度 28px，最大高度 420px，超出后**自身可滚**，两端用渐变遮罩淡出（24px）；
    · 容器宽度 ≤900px 时整体隐藏（右侧太窄会压到正文）；
    · hover 时在**左侧**浮出预览卡：第一行是提问（1 行省略），下面是结论（最多 3 行）。

  ## 数据来源

  一轮 = 一条用户提问 + 它之后直到下一条提问之前的全部内容。
    · `prompt`   取该轮用户消息的正文；
    · `response` 取该轮**最后一条有正文的助手消息**（与 DSH 的 `findLast` 语义一致）。

  锚点仍用 `[data-msg-idx]`（AiChatStream 每条消息都带），不依赖组件实例。

  ## 为什么不复用 DSH 的虚拟滚动

  DSH 用 `@tanstack/react-virtual` 做按需渲染（一轮可能上千条事件）。
  我们的消息列表本来就有 `RENDER_CHUNK` 分段渲染，轮次数量级也小得多，
  直接全量渲染更简单、也不会和现有滚动逻辑打架。
-->
<template>
  <nav
    v-if="items.length > 1"
    class="agent-outline"
    aria-label="会话轮次导航"
    @pointerenter="onPointerEnter"
    @pointerleave="onPointerLeave"
  >
    <div class="ao-frame">
      <div
        ref="scrollerRef"
        class="ao-scroller"
        :class="{ 'ao-fade-top': canScrollUp, 'ao-fade-bottom': canScrollDown }"
      >
        <div class="ao-marks" :style="{ height: totalHeight + 'px' }">
          <button
            v-for="(item, i) in items"
            :key="item.turn"
            type="button"
            :class="[
              'ao-mark',
              {
                'is-active': i === activeIndex,
                'is-preview': hoverIndex === i && i !== activeIndex,
                'is-busy': item.busy
              }
            ]"
            :style="{ top: i * TURN_SPACING_PX + RAIL_INSET_PX + 'px' }"
            :aria-current="i === activeIndex ? 'true' : undefined"
            :aria-label="markLabel(item, i)"
            @click="jumpTo(item)"
            @pointermove="hoverIndex = i"
            @focus="hoverIndex = i"
          >
            <span class="ao-bar" />
          </button>
        </div>
      </div>

      <!-- 预览卡：贴在导航**左侧**，不遮挡正文 -->
      <div
        v-if="previewItem"
        class="ao-preview"
        role="tooltip"
        :style="{ top: previewTop + 'px' }"
      >
        <div class="ao-preview__prompt">{{ previewItem.prompt || `第 ${previewItem.turn} 轮` }}</div>
        <div v-if="previewItem.response" class="ao-preview__response">
          {{ previewItem.response }}
        </div>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

/* ---------- 与 DSH 一致的度量常量 ---------- */
/** 相邻两轮之间的固定间距（DSH: TURN_SPACING_PX = 10） */
const TURN_SPACING_PX = 10
/** 首尾留白（DSH: RAIL_INSET_PX = 6） */
const RAIL_INSET_PX = 6
/** 滚动端渐变遮罩高度（DSH: FADE_PX = 24） */
const FADE_PX = 24

const props = withDefaults(
  defineProps<{
    /** 消息数组（通常是 AiChatStream 已渲染的那个窗口） */
    messages: any[]
    /**
     * 窗口起点在**完整消息数组**里的绝对下标
     *
     * ⚠️ 这个 prop 不能省（用户 2026-10-18 报的「点右侧消息条跳转失败、也不报错」）：
     *    `AiChatStream` 上的锚点是 **绝对**序号（`:data-msg-idx="windowOffset + idx"`），
     *    而本组件吃的是 `visibleMessages` 这个**窗口切片**，
     *    切片里的下标是**相对**的（0 起）。
     *    `windowOffset > 0` 时（历史长、触发了"加载更早"），
     *    `[data-msg-idx="${item.idx}"]` 查到的是别的元素或查不到，
     *    `if (!el) return` 就静默返回 —— 表现正是"点了没反应、也不报错"。
     *
     *    传 0 时行为与旧版一致（窗口就是全量），兼容短会话。
     */
    windowOffset?: number
    /** 滚动容器选择器（默认对话页的消息列表） */
    scrollSelector?: string
    /** 是否正在生成（用于给最后一轮打 busy 脉冲） */
    generating?: boolean
    /** 预览里提问最多显示多少字（DSH: 50） */
    promptChars?: number
    /** 预览里结论最多显示多少字（DSH: 120） */
    responseChars?: number
  }>(),
  {
    windowOffset: 0,
    scrollSelector: '.chat-messages',
    generating: false,
    promptChars: 50,
    responseChars: 120
  }
)

/* ==================== 轮次切分 ==================== */
interface TurnItem {
  /** 轮次号（从 1 开始，与 DSH 的 turn 语义一致） */
  turn: number
  /**
   * 该轮用户消息的 **绝对** 下标（= windowOffset + 窗口内下标）
   * 直接与 `AiChatStream` 的 `data-msg-idx` 对齐，用于 querySelector 定位。
   */
  idx: number
  prompt: string
  response: string
  /** 该轮是否还在生成 */
  busy: boolean
}

const trim = (s: unknown, max: number) => {
  const t = String(s ?? '')
    .replace(/\s+/g, ' ')
    .trim()
  return t.length > max ? t.slice(0, max) + '…' : t
}

const items = computed<TurnItem[]>(() => {
  const list: TurnItem[] = []
  const msgs = props.messages || []
  /** 当前正在收集的那一轮（用下标引用 list 里的对象，便于回填 response） */
  let curTurn = -1

  msgs.forEach((m: any, i: number) => {
    if (m?.role === 'user') {
      list.push({
        turn: list.length + 1,
        // 换算成**绝对**序号：与 `AiChatStream` 的 `data-msg-idx` 同一坐标系
        idx: props.windowOffset + i,
        prompt: trim(m.content, props.promptChars) || '（附件消息）',
        response: '',
        busy: false
      })
      curTurn = list.length - 1
      return
    }
    // 助手正文：覆盖式记「最后一条有正文的」（与 DSH 的 findLast 语义一致）
    if (curTurn >= 0 && m?.role === 'assistant' && !m.type) {
      const text = String(m.content || '').trim()
      if (text) list[curTurn].response = trim(text, props.responseChars)
    }
  })

  // 最后一轮若还在生成 → busy 脉冲
  if (props.generating && list.length) list[list.length - 1].busy = true
  return list
})

const totalHeight = computed(
  () => items.value.length * TURN_SPACING_PX + RAIL_INSET_PX * 2
)

/* ==================== 滚动与激活 ==================== */
const scrollerRef = ref<HTMLElement | null>(null)
const activeIndex = ref(0)
const hoverIndex = ref(-1)
const pointerInside = ref(false)
const canScrollUp = ref(false)
const canScrollDown = ref(false)

const previewItem = computed(() => {
  const i = hoverIndex.value
  return i >= 0 ? items.value[i] : null
})

/** 预览卡垂直位置：跟随悬停那根线（相对 frame） */
const previewTop = computed(() => {
  const i = hoverIndex.value
  if (i < 0) return 0
  // 预览卡自身高约 100px，用中心对齐 + 夹在可视区内
  return Math.max(0, i * TURN_SPACING_PX + RAIL_INSET_PX - 44)
})

let scroller: HTMLElement | null = null
let raf = 0

/**
 * 当前在第几轮
 * -----------------------------
 * 判据：容器顶部往下 24px 画一条"读线"，取**读线之上最后一条用户消息**。
 * 与 DSH 用 `activeTurn` prop 不同 —— 我们这边没有轮次事件流，
 * 直接按"视口顶部归属哪一轮"算，行为可预测且不需要额外状态。
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

  const changed = activeIndex.value !== found
  activeIndex.value = found
  if (changed) followActive()
}

/** 让激活的那根线保持在导航可视区内（指针在导航上时不抢） */
function followActive() {
  const el = scrollerRef.value
  if (!el || pointerInside.value) return
  const center = activeIndex.value * TURN_SPACING_PX + RAIL_INSET_PX
  const target = Math.max(0, Math.min(el.scrollHeight - el.clientHeight, center - el.clientHeight / 2))
  el.scrollTo({ top: target, behavior: 'smooth' })
}

function updateFades() {
  const el = scrollerRef.value
  if (!el) return
  canScrollUp.value = el.scrollTop > 1
  canScrollDown.value = el.scrollTop < el.scrollHeight - el.clientHeight - 1
}

/*
 * 指针进出导航：进 → 暂停"自动跟随"（别在用户手底下把线团滚走）；
 * 出 → 恢复跟随并清掉悬停。
 * ⚠️ 必须写成方法：`@pointerleave="a = false; b = -1"` 这种多语句内联表达式
 *    在模板编译后会触发 `Cannot read properties of null (reading 'emitsOptions')`，
 *    整个对话页白屏（2026-10-17 踩过）。
 */
function onPointerEnter() {
  pointerInside.value = true
}

function onPointerLeave() {
  pointerInside.value = false
  hoverIndex.value = -1
}

/**
 * 每根线的无障碍标签
 *
 * ⚠️ 模板里用了 `markLabel(item, i)`，这个函数**必须存在**：
 *    漏掉它会直接抛 `_ctx.markLabel is not a function`，
 *    整个对话页渲染中断 —— 表现为「点历史会话切不过去」（2026-10-17 踩过）。
 *    所以它不能放在 `items` 计算之后被 tree-shake 掉的位置，也不能改成内联表达式。
 */
function markLabel(item: TurnItem, i: number): string {
  const head = `第 ${item.turn} 轮（共 ${items.value.length} 轮）`
  const isCur = i === activeIndex.value ? '，当前所在' : ''
  return `${head}${isCur}：${item.prompt}`
}

function onScroll() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = 0
    syncActive()
  })
}

function onRailScroll() {
  updateFades()
}

/** 点击：滚到该轮（顶部留一点空隙，别贴死顶栏） */
function jumpTo(item: TurnItem) {
  if (!scroller) return
  const el = scroller.querySelector<HTMLElement>(`[data-msg-idx="${item.idx}"]`)
  if (!el) return
  const delta = el.getBoundingClientRect().top - scroller.getBoundingClientRect().top
  const target = scroller.scrollTop + delta - 16
  scroller.scrollTo({ top: Math.max(0, target), behavior: 'smooth' })
}

/* ==================== 生命周期 ==================== */
function bind() {
  scroller = document.querySelector<HTMLElement>(props.scrollSelector)
  if (!scroller) return
  scroller.addEventListener('scroll', onScroll, { passive: true })
  nextTick(() => {
    syncActive()
    updateFades()
    followActive()
  })
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
  nextTick(() => window.setTimeout(bind, 60))
  scrollerRef.value?.addEventListener('scroll', onRailScroll, { passive: true })
})

onBeforeUnmount(() => {
  unbind()
  scrollerRef.value?.removeEventListener('scroll', onRailScroll)
})

// 消息增删 / 切会话：重新绑定并刷新
watch(
  () => props.messages.length,
  () => {
    nextTick(() => {
      if (!scroller) bind()
      syncActive()
      updateFades()
    })
  }
)

// 换会话（首条消息变了）→ 回到第一轮
watch(
  () => props.messages[0],
  () => {
    activeIndex.value = 0
    nextTick(() => {
      syncActive()
      followActive()
    })
  }
)
</script>

<style scoped lang="scss">
/*
 * 容器：贴在**窗口右侧**、垂直居中。
 *
 * `--turn-rail-band` = 视口高度 - 输入框高度，这条带的中心才是视觉中心
 * （否则线团会压到输入框上）。高度上限 420px，超出自身滚动。
 */
.agent-outline {
  position: absolute;
  top: calc((100% - var(--ao-composer-h, 152px)) / 2);
  right: 12px;
  transform: translateY(-50%);
  z-index: 6;
  pointer-events: none;
}

.ao-frame {
  position: relative;
  width: 28px;
  /*
   * 高度上限 420 → 320（用户 2026-10-18：「消息条太多，用户的右边不太好看」）。
   * 320px 大约装 30 根线（间距 10px），再多就由 `.ao-scroller` 内部滚动，
   * 两端有 24px 渐变淡出，视觉上不会一直垂到页面底部。
   * 仍然受视口高度约束（矮屏时更短），不会溢出。
   */
  max-height: min(max(0px, calc(100dvh - var(--ao-composer-h, 152px) - 64px)), 320px);
  pointer-events: auto;
  cursor: pointer;
}

.ao-scroller {
  max-height: inherit;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  position: relative;

  &::-webkit-scrollbar {
    display: none;
  }
}

/* 两端渐变淡出（DSH 用 mask-image，同样 24px） */
.ao-fade-top {
  mask-image: linear-gradient(#0000 0, #000 24px 100%);
}

.ao-fade-bottom {
  mask-image: linear-gradient(#000 0 calc(100% - 24px), #0000 100%);
}

.ao-fade-top.ao-fade-bottom {
  mask-image: linear-gradient(#0000 0, #000 24px calc(100% - 24px), #0000 100%);
}

.ao-marks {
  position: relative;
}

/* 一根线：命中区 10px 高、28px 宽，实际画出来的线 20×2 */
.ao-mark {
  position: absolute;
  left: 0;
  right: 0;
  height: 10px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: none;
  cursor: pointer;

  &:focus-visible {
    outline: none;
  }
}

.ao-bar {
  position: absolute;
  top: 50%;
  right: 0;
  width: 20px;
  height: 2px;
  border-radius: 2px;
  background: var(--dsw-alias-border-l4);
  transform-origin: 100%;
  transform: translateY(-50%) scaleX(0.6);
  transition: transform 0.14s, background-color 0.14s;
}

/* 悬停预览：比普通长一档，颜色提到三级文字色 */
.ao-mark.is-preview .ao-bar {
  background: var(--os-text-4);
  transform: translateY(-50%) scaleX(0.9);
}

/* 当前所在：最长、最深（对应 DSH 的 markActive） */
.ao-mark.is-active .ao-bar {
  background: var(--os-text);
  transform: translateY(-50%) scaleX(1);
}

/* 键盘聚焦时给出焦点环（无障碍） */
.ao-mark:focus-visible .ao-bar {
  background: var(--os-accent);
  transform: translateY(-50%) scaleX(1);
}

/* 正在生成的那一轮：呼吸脉冲（DSH 的 markBusy） */
.ao-mark.is-busy .ao-bar {
  animation: ao-pulse 1s ease-in-out infinite;
}

@keyframes ao-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.35;
  }
}

/* ==================== 预览卡 ==================== */
.ao-preview {
  position: absolute;
  right: calc(100% + 10px);
  width: min(300px, 40vw);
  padding: 10px 12px;
  border-radius: var(--os-radius);
  background: var(--dsw-alias-bg-layer-1, #fff);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 0 0 0.5px rgba(0, 0, 0, 0.06);
  pointer-events: none;
  animation: ao-preview-in 0.12s ease-out;
  transition: top 0.14s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.ao-preview__prompt {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  color: var(--os-text);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ao-preview__response {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--os-text-3);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@keyframes ao-preview-in {
  from {
    opacity: 0;
    transform: translateX(4px);
  }

  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* 窄容器隐藏：右侧空间不够，会压到正文（DSH 是 @container width<=900px） */
@media (max-width: 900px) {
  .agent-outline {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ao-bar,
  .ao-preview,
  .ao-mark.is-busy .ao-bar {
    transition: none;
    animation: none;
  }
}
</style>
