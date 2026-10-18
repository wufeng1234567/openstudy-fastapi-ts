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
  <!--
    抽屉容器
    ==========================================================================
    ⚠️ 为什么**不再**用外层 `v-if` 卸载（这是"点空白没有退场动画"的根因）
    --------------------------------------------------------------------------
    历史：为了修「抽屉越点越多」（overlay 关掉后仍留在 body 上、反复叠加），
    我曾给 el-drawer 加 `v-if`，关闭即卸载。副作用是：

      · 用「设置按钮」关闭 —— 走的是我们自己的 `visible = false`，
        当时 `transitioning` 还能撑住挂载，动画有时间跑完 → 看起来正常；
      · 用「点空白」关闭 —— Element Plus 内部直接改 `visible`，
        组件比动画更早被卸载 → **没有任何退场动画，抽屉直接消失**
        （用户 2026-10-18 报的正是这一条）。

    现在改用 Element Plus 官方的 `destroy-on-close`：
      · 关闭时先完整播放退场动画，动画结束才销毁内部 DOM；
      · overlay 由 EP 自己在销毁时回收 —— 同样解决"越点越多"，
        而且不需要我们用 `v-if` 抢时序。
  -->
  <el-drawer
    v-model="innerVisible"
    :direction="direction"
    :size="width + 'px'"
    :with-header="false"
    append-to-body
    destroy-on-close
    :class="['rd-drawer', `rd-${direction}`, drawerClass]"
    @closed="onClosed"
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
    /**
     * 可选：抽屉与视口边缘的偏移量（px）。
     *
     * 场景：设置入口在左侧常驻导航栏里。抽屉从左侧展开时若从 x=0 开始，
     * 会把导航整个盖住；传了这个值后抽屉从导航右缘展开，导航仍可见（遮罩也一起内缩）。
     * 不传 = 传统贴边抽屉（默认 0）。
     */
    offsetLeft?: number
  }>(),
  {
    direction: 'rtl',
    resizable: true,
    min: 320,
    max: 900,
    defaultWidth: 520,
    storageKey: '',
    anchorSelector: '',
    offsetLeft: 0
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

/**
 * 关闭动画期间保持挂载
 *
 * `v-if` 直接跟 `innerVisible` 会把关闭动画"切没"（抽屉瞬间消失、没有滑出过程）。
 * 所以关闭时先让 EP 走完动画（`@closed` 回调），再把 `transitioning` 置 false
 * 触发卸载 —— 见上面模板注释里说的 overlay 残留问题。
 */
const transitioning = ref(false)
watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      transitioning.value = true
      nextTick(() => emit('open'))
    }
    // 关闭时不立刻置 false：等 el-drawer 的 @closed（动画结束）再卸
  },
  { immediate: true }
)

/** 抽屉关闭动画结束 → 可以安全卸载（Element Plus 会把 overlay 一起回收） */
function onClosed() {
  transitioning.value = false
  // 退场动画走完，再收掉让位用的 left / 内联 transform（见 cleanupOffsetAfterLeave 的说明）
  cleanupOffsetAfterLeave()
}
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

/* ---------- 边缘偏移（给常驻导航让位） ---------- */
//: 抽屉贴在 ltr 的左边 / rtl 的右边，所以「偏移」要作用在它靠外的那条边上。
const offsetPx = computed(() => Math.max(0, Number(props.offsetLeft) || 0))
const offsetCss = computed(() => `${offsetPx.value}px`)

/* ---------- 定位本抽屉的 DOM ---------- */
//: 唯一 class：多个抽屉同时存在（可能同方向）时，靠它精确定位到"我自己"那一个
//: （append-to-body 会把抽屉挪出组件树，不能靠 $el / 组件引用）。
const drawerClass = `rd-drawer-${Math.random().toString(36).slice(2, 8)}`

const getDrawerEl = () =>
  document.querySelector<HTMLElement>(`.rd-drawer.${drawerClass}`)

/**
 * 遮罩跟随抽屉一起让位 + 修正抽屉的入场起点
 * ------------------------------------------
 * 用户 2026-10-18：「从抽屉伸出的效果不行，会有闪现；起始位置是从左侧菜单内部
 * 开始移动的，视觉效果不行」。
 *
 * 实测（改前）：抽屉入场时 `left:-380 / transform:-380px`，终点才是 280 ——
 * 也就是它从屏幕最左（穿过菜单）滑进来。
 *
 * 根因：Element Plus 的 `.el-drawer-fade-enter-from .ltr { transform: translate(-100%) }`。
 * 这个 -100% 相对抽屉宽度，而遮罩被我们推到了 `left:280px`，
 * 于是起点变成 280 - 380 = -100px（实测更远）。
 *
 * ⚠️ 试过两条路都不稳：
 *   ① 用 CSS 提高特异性覆盖 transform —— EP 的样式加载顺序在生产构建里不固定；
 *   ② 给遮罩设 `left` —— 被 `el-overlay` 自身的定位规则盖掉（实测 `left:0px`）。
 *
 * 现在改成**纯内联样式**（内联优先级最高，不吃加载顺序）：
 *   · overlay：`left` 直接写在元素上；
 *   · drawer：用**独立的 `translate` 属性**（不与 EP 的 `transform` 冲突，
 *     两者是分开的 CSS 属性，浏览器会叠加），把入场方向补上侧栏宽度。
 */
/**
 * 让抽屉从**侧栏右缘**长出来（而不是穿过菜单）
 * ============================================================================
 * 用户 2026-10-18：「抽屉出现的瞬间是从路由菜单内部出现的，而不是很好地从左侧
 * 路由菜单的边界那边长出来」。
 *
 * ## 为什么之前一直修不好（查了仓库历史 + EP 源码才看清）
 *
 * 1. **原实现本来是对的**：对话页那个抽屉一直是 `ltr` + `offset-left`，
 *    用户从没报过闪现。差别是——它**常驻挂载**，overlay 早在动画开始前
 *    就已经带着 `left:280px` 躺在那儿了。
 *
 * 2. 我上一批为了修「抽屉越点越多」，给 `el-drawer` 加了 `v-if`：
 *    关闭即卸载 → 下次打开**新建** overlay → `left` 是**动画开始之后**才补上的。
 *
 * 3. 而 EP 给 overlay 和 drawer 都写了 `transition: all`
 *    （`.el-drawer-fade-enter-active{transition:all …}`）。所以补 `left` 这一下
 *    本身就被 animate 了 —— 视觉上就是"抽屉从菜单内部平移出来"的那道闪现。
 *
 * ## 所以修法不是"改位移公式"，而是把这两件事拆开
 *
 * · `left`（让位给侧栏）：**同步写、且禁掉过渡** —— 位置瞬间就位，不产生动画；
 * · 位移（滑入效果）：交给抽屉自己的 `transform`，由 EP 的动画负责。
 *
 * 写 `left` 的时机用 MutationObserver 在 overlay **插入的同一批任务**里完成
 * （比 nextTick 早，浏览器还没绘制第一帧），并在同一帧内临时关掉过渡。
 */
/** 入场结束后释放内联 transform 的定时器（见 applyOffset 里的说明） */
let _releaseTimer: ReturnType<typeof setTimeout> | null = null

function applyOffset(overlay: HTMLElement) {
  const drawer = getDrawerEl()
  const on = offsetPx.value > 0 && props.direction === 'ltr'
  if (on) {
    /*
     * 关掉过渡再写 left：
     * 不关的话，EP 的 `transition: all` 会把这次 `left` 变化也做成动画，
     * 这正是"从菜单内部平移出来"的来源。
     */
    const prevTransition = overlay.style.transition
    overlay.style.transition = 'none'
    overlay.style.setProperty('left', offsetCss.value, 'important')
    // 强制读一次布局，让"无过渡定位"立刻落地，再恢复过渡
    void overlay.offsetWidth
    overlay.style.transition = prevTransition

    if (drawer) {
      drawer.classList.add('rd-offset-drawer')
      /*
       * ⚠️ 这里**不碰 transform**，让 Element Plus 自己的滑入动画完整跑。
       *
       * 关键机制（之前一直没想通，绕了很多弯路）：
       *   Element Plus 给 overlay 加了 `overflow: hidden`
       *   （`.el-drawer-fade-enter-active{overflow:hidden!important}`），
       *   而抽屉的入场位移是 `translateX(-100%)`。
       *   只要 overlay 的 `left` 在**首帧之前**就是 280，
       *   抽屉从 -380 滑向 280 的过程中，处在 280 左侧的部分会被 overlay **裁掉** ——
       *   视觉上它就是从侧栏右缘"长出来"的，既顺滑又不会压到菜单。
       *
       * 反过来，如果 `left` 晚了一帧（默认 0），裁剪区从屏幕最左开始，
       * 抽屉就会完整地从菜单内部扫过去 —— 这才是用户看到的那道闪现。
       *
       * 之前我为了"压住"位移去写内联 `transform: translate(0)`，
       * 结果把滑入动画也一起压成静止，只剩淡入 → 用户反馈
       * 「打开动画原本很丝滑的，现在变成唰的一下出现了」。
       * 现在把 transform 完全交还给 EP，只负责把 `left` 抢在首帧前设好。
       */
      drawer.style.setProperty('--rd-offset', offsetCss.value)
    }
  } else {
    /*
     * 关闭：`left` / class 留到 `@closed` 之后再收（见 cleanupOffsetAfterLeave），
     * 否则抽屉会先跳回 0 再滑出，又是一道闪。
     */
    void overlay
  }
}

function syncOverlayOffset() {
  const drawer = getDrawerEl()
  const overlay = drawer?.closest('.el-overlay') as HTMLElement | null
  if (!overlay) return
  applyOffset(overlay)
}

/**
 * 盯住 body，overlay 一插进来就立刻设偏移
 *
 * 比 nextTick 更早：`childList` 回调在 DOM 变更的同一批 microtask 里跑，
 * 浏览器还没开始第一帧绘制，所以用户看不到"从 0 开始"的那一帧。
 */
let _bodyObserver: MutationObserver | null = null

function watchElementInsertion() {
  if (_bodyObserver || typeof MutationObserver === 'undefined') return
  _bodyObserver = new MutationObserver(() => {
    if (!props.modelValue) return
    syncOverlayOffset()
  })
  _bodyObserver.observe(document.body, { childList: true, subtree: false })
}

/**
 * 入场时**提前**把 `left` 和 `transform` 定死
 *
 * 为什么还要这一步：MutationObserver 的回调虽然在 microtask 里，
 * 但实测（`open-raf` 采样）首帧仍能看到 `transform: -380` —— 因为
 * Vue 把 `el-drawer` 的 v-if 展开和 EP 的 transition 类挂在同一批更新里，
 * 观察器赶到时浏览器已经开始记录了。
 *
 * 这里在 `modelValue` 变 true 的同步阶段就把「待打开的抽屉」定位好：
 * 只要 DOM 已经存在（v-if 之前的旧节点、或 keep-alive 残留），先摆正再说。
 * 元素不存在时静默跳过，交给观察器兜底。
 */
function prePositionOnOpen() {
  if (!(offsetPx.value > 0 && props.direction === 'ltr')) return
  // 用 rAF 抢在 EP 的 transition 起始之前（同一帧内、绘制前）
  requestAnimationFrame(() => {
    if (!props.modelValue) return
    syncOverlayOffset()
    // 再补一次，覆盖"动画第一个 tick 已经按 -100% 记录了起点"的情况
    requestAnimationFrame(() => {
      if (!props.modelValue) return
      syncOverlayOffset()
    })
  })
}

function stopWatchingInsertion() {
  if (_bodyObserver) {
    _bodyObserver.disconnect()
    _bodyObserver = null
  }
}

// 打开 / 偏移 / 方向变化时同步
watch(
  [() => props.modelValue, offsetPx, () => props.direction],
  (v) => {
    const open = Array.isArray(v) ? v[0] : v
    if (open) {
      // 开之前就开始盯：overlay 插入的第一时间就带上偏移
      watchElementInsertion()
      prePositionOnOpen()
      // 下面两次是兜底（元素可能已经存在，或观察器建立前就插好了）
      syncOverlayOffset()
      nextTick(() => {
        syncOverlayOffset()
        window.setTimeout(syncOverlayOffset, 0)
      })
    } else {
      stopWatchingInsertion()
      /*
       * 关闭：**先放开 transform 锁**，让 EP 的退场动画正常跑。
       *
       * 用户 2026-10-18：「展开效果很好了，但是没有抽屉关闭效果了」。
       * 原因：入场时我写了内联 `transform: translate(0) !important`，
       * 它比 EP 的 `.el-drawer-fade-leave-to .ltr{transform:translate(-100%)}` 更强，
       * 把退场位移一起压死了 → 抽屉"啪"地消失，没有滑出过程。
       *
       * 处理：
       *   · 立刻撤掉内联 transform（退场位移恢复由 EP 控制）；
       *   · `left` 保持到动画结束再清（否则抽屉会先跳回 0 再滑出，又是一道闪）。
       *      清理时机放在 `@closed`（见 onClosed）。
       */
      const drawer = getDrawerEl()
      if (drawer) drawer.style.removeProperty('transform')
      /*
       * 诊断出口（排查"点空白关闭没有退场动画"）：
       * 控制台/自动化脚本读 `window.__rdClose` 就能看到关闭瞬间的状态。
       */
      ;(window as any).__rdClose = {
        at: Date.now(),
        source: 'watch(modelValue=false)',
        hasDrawerEl: !!drawer,
        hadInlineTransform: drawer ? !!drawer.style.transform : null,
        cls: drawer ? drawer.className : null
      }
    }
  },
  { immediate: true }
)

/** 退场动画结束后，再把让位用的 `left` 收掉（避免下一次别的抽屉被带歪） */
/**
 * 退场动画结束后，再把让位用的 `left` 收掉
 *
 * ⚠️ 不能一收到 `@closed` 就清 —— 实测（2026-10-18）会出现
 *    `left` 从 280 瞬间跳回 0 的画面：抽屉已经滑出到侧栏外面了，
 *    结果位置基座被抽走，视觉上"闪一下回到原地"。
 *
 * 所以延后一帧再清，并且只在**确实已经不可见**的时候清。
 */
function cleanupOffsetAfterLeave() {
  const drawer = getDrawerEl()
  const overlay = drawer?.closest('.el-overlay') as HTMLElement | null

  window.setTimeout(() => {
    // 期间又打开了（用户快速开→关→开）：不要清，否则下次打开又要重设一遍
    if (props.modelValue) return
    if (overlay) {
      overlay.style.removeProperty('left')
      overlay.classList.remove('rd-modal-offset')
    }
    if (drawer) {
      drawer.classList.remove('rd-offset-drawer')
      drawer.style.removeProperty('--rd-offset')
      drawer.style.removeProperty('transform')
    }
  }, 60)
}

// 抽屉关闭时把 overlay 恢复原样，避免下次别的抽屉（无偏移）被带歪
onBeforeUnmount(() => {
  const drawer = getDrawerEl()
  const overlay = drawer?.closest('.el-overlay') as HTMLElement | null
  if (overlay) overlay.style.left = ''
})

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
/* 拖拽手柄：贴在被拉伸的那条边，窄条 + 悬停变色
   与 AiAssistant 的 .drawer-resize-handle 同款：小竖条 + hover 变灰，
   不是整条边变色（那样视觉太重） */
.rd-resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 10px;
  z-index: 10;
  cursor: col-resize;
  background: transparent;

  &::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 32px;
    border-radius: 2px;
    background: transparent;
    transition: background 0.15s;
  }

  &:hover::after {
    background: #c0c4cc;
  }
}
/*
 * 带偏移的左抽屉：**动画起点**也要一并挪开
 * ---------------------------------------------------------------------------
 * 用户 2026-10-18：「从抽屉伸出的效果不行，会有闪现；就是起始位置是从
 * 左侧菜单内部开始移动的，视觉效果不行」。
 *
 * 原因：el-drawer 的 ltr 抽屉关闭态是 `transform: translateX(-100%)`，
 * 这个 -100% 是相对**抽屉自身宽度**算的。如果只给遮罩设 `left:280px`，
 * 抽屉的起点仍然在 `280 - 380 = -100px` —— 视觉上它从侧栏**内部**穿过来，
 * 也就是用户看到的那道闪现。
 *
 * 修法：给抽屉也加同样的位移补偿。`--rd-offset` 由组件内联写在遮罩上，
 * 这里把它同步到抽屉元素，让 `translateX` 从「侧栏右缘」开始算：
 *   关闭态 → `translateX(calc(-100% + var(--rd-offset)))`
 *   打开态 → `translateX(0)`（不变）
 * 这样抽屉就是**紧贴侧栏右缘滑出**，不会穿过菜单。
 */
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

/*
 * 带偏移的抽屉：遮罩也要跟着让位
 * ------------------------------
 * 场景：设置入口在左侧常驻导航栏里，抽屉从左侧展开时如果遮罩从 x=0 铺满，
 * 会把导航一并盖住（看起来整块界面都灰掉了，用户以为导航不可用）。
 * 这里让遮罩从抽屉偏移处开始 —— 导航保持明亮、仍然可点。
 * 偏移值由组件内联写在 `.rd-modal-offset` 的 `--rd-offset` 上（见下方 tab 内实现）。
 */
.rd-modal-offset {
  left: var(--rd-offset, 0) !important;
}

/*
 * 带偏移的左抽屉：**入场起点**要贴在侧栏右缘，而不是从屏幕最左穿过来
 * ---------------------------------------------------------------------------
 * 用户 2026-10-18：「从抽屉伸出的效果不行，会有闪现；起始位置是从左侧菜单内部
 * 开始移动的，视觉效果不行」。
 *
 * 实测（改前）：
 *   raf    left:-380  transform:-380px   ← 起点在屏幕最左之外（穿过菜单）
 *   80ms   left:  10  transform:-248px
 *   480ms  left: 280  transform:none     ← 终点正确
 *
 * 根因：Element Plus 用 `.el-drawer-fade-enter-from .ltr { transform: translate(-100%) }`
/*
 * 带偏移的左抽屉：入场只淡入，不做横向位移
 * ---------------------------------------------------------------------------
 * 用户 2026-10-18：「抽屉出现的瞬间是从路由菜单内部出现的，而不是很好地从左侧
 * 路由菜单的边界那边长出来」。
 *
 * 前面已经确认过位移是怎么来的：
 *   · overlay 的 `left` 让它从侧栏右缘开始（已在 JS 里瞬间就位、禁掉过渡）；
 *   · EP 的 `.el-drawer-fade-enter-from .ltr { transform: translate(-100%) }`
 *     会让抽屉**再多退自身宽度**，于是起点跑到侧栏左边之外 ——
 *     划过菜单的那一段，就是用户看到的"从菜单里长出来"。
 *
 * 既然 `left` 已经把抽屉摆到了侧栏右缘，再叠加 -100% 就是多余的。
 * 这里把这层位移抵掉，只保留透明度淡入 —— 视觉上就是**贴着侧栏边界展开**，
 * 不再有横向扫过的过程。
 *
 * 只对「有偏移的左抽屉」生效（`.rd-offset-drawer`），
 * 其余抽屉（知识库独立抽屉、AiAssistant 等）保持 EP 原生行为不变。
 */
.rd-drawer.rd-offset-drawer.rd-ltr {
  --rd-offset: 0px;
}

/*
 * 入场：抵消 EP 的 -100% 位移（由 JS 内联设置，见 applyOffset）
 * 退场：**放开**，让 EP 的 translate(-100%) 正常跑出动画
 *
 * 所以这里**不要**给 `.rd-offset-drawer` 写退场的 transform 覆盖 ——
 * 写了会把"滑出去"也压成 0，抽屉就僵在原地然后消失（实测过）。
 */
</style>
