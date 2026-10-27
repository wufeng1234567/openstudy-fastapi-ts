<!--
  运行状态行（2026-10-27 第三版）

  ============================================================================
  两版都做错了，这里记下来避免再走回头路
  ============================================================================

  **第一版**：浮在输入框上方的胶囊卡片（淡蓝底 + 圆角边框 + 滚动进度条 + 「已完成 N 步」按钮）
  用户反馈：「状态样式不好看…不能抢眼…而且不对齐」

    → 错在：消息流里所有元素都是无边框透明底（`AgentReasoning` 的注释明确写着
      "要更贴合思考的图形 + 低调"），一张带底色带边框的卡片成了全屏最显眼的东西。

  **第二版**：改成对话流内的阶段清单（连接 / 理解需求 / 深度思考 / 调用工具 / 写正文 / 完成）
  用户反馈：「效果太乱 不需要四个时间表述 只需要一个类似 DSH 那样的
            正在xxx，耗时多少 就行」

    → 错在：把"过程"当成"要展示的数据"。用户等待时只想确认两件事 ——
      **现在在干什么、已经等了多久**。六行带各自耗时是审计报告，不是状态提示。

  ============================================================================
  这一版
  ============================================================================

  一行字 + 我们的 logo + 流光：

       🅾 正在深度求索中，用时 4 秒…

  运行中：整行有一道流光从左往右扫过（表达"活着、在动"）；
  结束后：流光消失，留下静态的一行「用时 12 秒」，低调地作为记录。

  为什么用流光而不是转圈：
    转圈是"加载中"的通用符号，反复出现会让界面显得焦躁；
    流光贴着文字走，视觉上更像"文字本身在呼吸"，安静但确实是活的。
-->
<template>
  <div v-if="visible" :class="['rline', { 'is-running': running, 'is-failed': failed }]" role="status"
    aria-live="polite">
    <!-- 品牌标：与侧栏、hero 同一枚（OsLogo），尺寸压到 14px 融入文字行 -->
    <span class="rline-logo" aria-hidden="true">
      <OsLogo :size="14" bg="#1f2430" fg="#fff" />
    </span>

    <!--
      单行文案

      ⚠️ 三个 span 必须**紧贴书写**、中间不留换行/缩进（2026-10-27 实测）：
         Vue 会把模板里的换行+缩进压成一个空格，于是渲染出
         「正在连接中 ，用时 2秒」—— 逗号前多出空格，很难看。
         写成同一行才对。
    -->
    <span class="rline-text"><span class="rline-label">{{ label }}</span><span v-if="timeText" class="rline-time">，用时 {{ timeText }}</span><span v-if="running" class="rline-dots" aria-hidden="true">…</span></span>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import OsLogo from '@/components/OsLogo/index.vue'

export type RunPhase =
  | 'connecting'
  | 'understanding'
  | 'thinking'
  | 'composing'
  | 'tool'
  | 'done'
  | 'error'

const props = withDefaults(
  defineProps<{
    /** 本轮是否在跑 */
    running?: boolean
    /** 当前阶段 */
    phase?: RunPhase
    /** 当前执行的工具名（`tool` 阶段用） */
    tool?: string
    /** 本轮开始时间（ms） */
    startedAt?: number
    /** 最近一次活动时间（ms）；结束后用它封口，避免继续走表 */
    lastActivityAt?: number
    /** 是否失败收场 */
    failed?: boolean
  }>(),
  {
    running: false,
    phase: 'connecting',
    tool: '',
    startedAt: 0,
    lastActivityAt: 0,
    failed: false
  }
)

/** 每秒走动的"现在"（运行中才启用定时器） */
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

/** 可见性：在跑，或失败时留一行说明（成功且结束就不显示了，只留 turn_end 里的耗时记录） */
const visible = computed(() => props.running || props.failed)

/**
 * 文案（用户指定格式：「正在xxx，用时 N 秒」）
 *
 * ⚠️ 措辞都用「正在…」句式，与 DSH 一致。
 *    特别地，长思考阶段说「深度求索中」而不是「深度思考中」——
 *    "求索"更贴合这个产品（学习场景），也避免和推理块的「深度思考」重复。
 */
const label = computed(() => {
  if (!props.running) return props.failed ? '已中断' : '已完成'
  switch (props.phase) {
    case 'connecting':
      return '正在连接中'
    case 'understanding':
      return '正在理解需求'
    case 'thinking':
      return '正在深度求索中'
    case 'composing':
      return '正在撰写内容'
    case 'tool':
      return props.tool ? `正在执行「${props.tool}」` : '正在执行操作'
    default:
      return '正在处理'
  }
})

/**
 * 耗时文案
 *
 * 用户给的样子是「用时 4秒」—— **数字与"秒"紧贴**，中间不留空格。
 * 中文排版里"4秒"比"4 秒"更紧凑，也更接近用户手写的样式。
 *
 * ⚠️ 不做「1 分 23 秒」这种复合表述：用户要的是"大致多久"，
 *    复合格式要在脑子里换算，超过 60 秒就显示「75秒」一眼可比。
 */
const timeText = computed(() => {
  if (!props.startedAt) return ''
  const end = props.running ? now.value : (props.lastActivityAt || now.value)
  const s = Math.max(0, Math.round((end - props.startedAt) / 1000))
  return `${s}秒`
})

/** 定时器：只在运行中启用；停下立刻清掉，别空转 */
watch(
  () => props.running,
  (running) => {
    if (running) {
      now.value = Date.now()
      if (!timer) timer = setInterval(() => { now.value = Date.now() }, 1000)
    } else if (timer) {
      clearInterval(timer)
      timer = null
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
/*
 * 视觉基准：与 `.rs-head`（推理块头部）同级 —— 12.5px、灰字、无边框无底色。
 *
 * ⚠️ 不要加 background / border / box-shadow（前两版都栽在这）：
 *    这一行的角色是"安静地说明状态"，一旦有底色就会变成整屏最显眼的东西。
 */
.rline {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 2px;
  margin: 1px 0 7px;
  font-size: 12.5px;
  line-height: 1.6;
  /*
   * 基础文字色。运行中会被 `.is-running .rline-text` 的渐变覆盖
   * （那里用 background-clip: text 把字当遮罩），结束后自动回到这个纯色。
   */
  color: var(--rline-base, #5b6577);
  border-radius: 4px;
}

.rline.is-failed {
  color: #c0504d;
}

.rline-logo {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  /* 运行中轻微呼吸，呼应"在跑"；结束后静止 */
  opacity: 0.82;
}

.rline.is-running .rline-logo {
  animation: rline-logo-breathe 2.4s ease-in-out infinite;
}

@keyframes rline-logo-breathe {
  0%, 100% { opacity: 0.82; }
  50%      { opacity: 1; }
}

/*
 * 文案容器
 *
 * ⚠️ 必须是 `inline`（不是 inline-flex）：
 *    用 inline-flex 时，子 span 会各成一个 flex item，
 *    浏览器在它们之间渲染出**可感知的间隙** —— 实测出来就是
 *    「正在连接中 ，用时 2秒」里逗号前那个多余空格。
 *    普通行内布局下，相邻 span 是紧贴的，标点才能正确前贴。
 *
 *    流光是 `position: absolute` 的子层，不需要 flex 也能量满整行。
 */
/*
 * 单行文案 —— 字体流光（2026-10-27 二次修）
 *
 * ============================================================================
 * 用户明确指出第一版做错了
 * ============================================================================
 *
 *   「流光效果不是周围出现一个流光的框 而是字体流光 能理解什么叫做字体流光嘛？
 *     文字本身保持基础亮度，但有一道高光带（渐变光斑）从文字左侧匀速滑动
 *     到右侧并循环往复。」
 *
 * 第一版是在整行外面盖了一层 `linear-gradient` 光带（`inset: 0` + 宽 300% 平移），
 * 那是**外框光带** —— 像给文字套了个发光的塑料袋，而不是字在发光。
 *
 * ============================================================================
 * 字体流光的正确做法
 * ============================================================================
 *
 * 靠 `background-clip: text` 把**文字本身**当遮罩，然后让渐变背景在里面平移：
 *
 *   ① 文字颜色设为 `transparent`（否则纯色字会盖住背景，看不到渐变）
 *   ② `background-image` = 一段"暗-亮-暗"的渐变（基础亮度 + 高光带）
 *   ③ `background-size` 设得比文字宽（300%），这样才能有"扫过"的过程
 *   ④ `animation` 平移 `background-position-x` 从 0 到 100%
 *
 * 效果：字保持可读的基础灰，一道更亮的光斑从左边滑到右边，循环。
 * 这才是"字体在流动"，而不是"外面有个框在动"。
 *
 * ⚠️ 运行结束后必须回到纯色文字：
 *    `-webkit-text-fill-color: transparent` 一旦留着而动画停了，
 *    文字会变成"渐变卡的某一帧"，看起来像渲染坏了。
 *    所以流光样式只挂在 `.is-running` 上，结束后自动回到 `.rline` 的纯色。
 */
.rline-text {
  position: relative;
  display: inline;
  white-space: nowrap;
}

/* 运行中：文字变"透明"，由背景渐变透出来 */
.rline.is-running .rline-text {
  /*
   * 基础亮度 = var(--rline-base)，高光 = var(--rline-hi)。
   *
   * 渐变按"3 段等宽"排：暗 / 亮 / 暗。
   * `background-size: 300% 100%` 让这三段正好铺满 3 倍文字宽，
   * 于是任一时刻文字上只显示其中一段 —— 平移时就是光斑扫过。
   */
  background-image: linear-gradient(
    100deg,
    var(--rline-base) 0%,
    var(--rline-base) 35%,
    var(--rline-hi) 50%,
    var(--rline-base) 65%,
    var(--rline-base) 100%
  );
  background-size: 300% 100%;
  background-repeat: no-repeat;
  /* 文字的"墨"是背景渐变，而不是纯色 */
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: rline-text-sweep 2.8s linear infinite;
}

/*
 * 高光从左扫到右
 *
 * `background-position-x` 从 `100%` 走到 `0%` 时，渐变整体向左移 ——
 * 视觉上就是亮段从左侧进入、向右侧离开。
 * 用 `100% → 0%` 而不是 `0% → 100%`，方向才是"从左往右"（与阅读方向一致）。
 */
@keyframes rline-text-sweep {
  0%   { background-position-x: 100%; }
  100% { background-position-x: 0%; }
}

/* 基础色与高光色：定义在容器上，子 span 继承不到渐变，但 keyframes 里要用 */
.rline {
  --rline-base: #5b6577;
  --rline-hi: #1c2430;
}

/*
 * 耗时与省略号也要参与流光，否则它们会是"死的纯色"，视觉上割裂。
 *
 * ⚠️ 但它们各自是独立元素，`background-clip: text` 不会自动继承 ——
 *    所以这里让它们也挂同一套渐变与动画（`background-size` 相同、相位相同，
 *    看起来像同一道光扫过整行）。
 */
.rline.is-running .rline-time,
.rline.is-running .rline-dots {
  background-image: linear-gradient(
    100deg,
    var(--rline-base) 0%,
    var(--rline-base) 35%,
    var(--rline-hi) 50%,
    var(--rline-base) 65%,
    var(--rline-base) 100%
  );
  background-size: 300% 100%;
  background-repeat: no-repeat;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: rline-text-sweep 2.8s linear infinite;
}

.rline-label {
  position: relative;
}

/*
 * 耗时：比正文淡，但**不用 opacity**
 *
 * ⚠️ 不能用 `opacity`（2026-10-27 实测）：运行中这一行是
 *    `background-clip: text` + `-webkit-text-fill-color: transparent` 实现的，
 *    而 `opacity` 作用在整个元素盒上，会把渐变的亮部一起压暗，
 *    结果是"流光几乎看不见"。
 *
 *    想让它淡，就把**渐变的基色**调淡（已经是 --rline-base），
 *    或者用 `color` 在非运行态区分 —— 不要用 opacity。
 */
.rline-time {
  position: relative;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}

/* 非运行态：耗时比主句更淡（此时是纯色，用 opacity 没问题） */
.rline:not(.is-running) .rline-time {
  opacity: 0.75;
}

/*
 * 省略号
 *
 * 用 CSS 动画而不是 JS 改文本 —— 后者每秒触发布局，
 * 而这条文字就在视口里，长任务跑几分钟会白费不少渲染。
 */
.rline-dots {
  position: relative;
}

/* 非运行态不做闪烁（正常情况下运行结束这一行就没了，这里是兜底） */
.rline:not(.is-running) .rline-dots {
  opacity: 0.55;
}

/*
 * 系统开启"减少动态效果"时关掉所有动画
 *
 * 流光和呼吸对光敏感的用不友好；`prefers-reduced-motion` 是标准做法。
 *
 * ⚠️ 关掉流光时必须**把文字恢复成纯色**：
 *    光流的实现是 `-webkit-text-fill-color: transparent` + 渐变背景。
 *    如果只是 `animation: none` 而透明填充还在，
 *    文字会定格在渐变的某一帧上（可能整行都是最暗或最亮那一段），
 *    看起来像渲染坏了。所以这里显式把填充色改回来。
 */
@media (prefers-reduced-motion: reduce) {
  .rline-dots,
  .rline.is-running .rline-logo {
    animation: none;
  }

  .rline.is-running .rline-text,
  .rline.is-running .rline-time,
  .rline.is-running .rline-dots {
    animation: none;
    background-image: none;
    -webkit-text-fill-color: currentColor;
    color: inherit;
  }
}
</style>
