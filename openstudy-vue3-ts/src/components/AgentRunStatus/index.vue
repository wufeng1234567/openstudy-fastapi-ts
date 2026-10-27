<!--
  运行状态条（2026-10-27 新增）

  ============================================================================
  它解决什么
  ============================================================================

  用户实测反馈：

      「AI 在执行长任务（如生成 3000 字文档）时，从提交到输出结果的整个过程中，
        前端界面缺乏有效的过程状态反馈。目前仅输入框右下角有一个微弱的
        "等待/生成中"符号，用户无法感知 AI 当前处于"思考中""调用工具中"
        还是"正在输出文字"等具体阶段，导致长任务等待体验近似"黑箱"。」

  实测证据（真实长任务，31 秒采样，500ms 一次）：

      4559ms   思考块开始流式输出（用户能看到字在滚）
      8116ms   思考收口折叠 → 屏幕内容长度从 1612 骤降到 86
      ...
      30474ms  才出现下一段文字
      → **连续 21.3 秒屏幕上没有任何变化**

  也就是说：问题不是"完全没有反馈"，而是**反馈在 8 秒后就消失了**。
  既有机制各管一段、且都不常驻：

      · `waiting`   一闪而过，真实内容一到就被替换掉
      · `progress`  只在文档解析等少数环节发
      · 推理块      收口后默认折叠成一行「已深度思考 N 秒」
      · 工具卡片    只有真的调了工具才有

  中间那段"模型在长输出/长思考但没有正文"的时期，界面上什么都不动。

  ============================================================================
  设计
  ============================================================================

  ① **常驻**：只要本轮在跑就一直在，不因为某个事件到了就消失
  ② **实时计时**：每秒走一次，用户任何时候都能知道"已经等了多久"
  ③ **分阶段**：从事件流推断当前处于哪一步，而不是只说"处理中"
  ④ **不打断**：纯展示层，不发请求、不改消息流、不抢焦点
  ⑤ **可见的"在动"**：等待期有一条来回走的细条，
     即使正文还没出来，用户也能看出"系统没死"

  ⚠️ 为什么阶段要在**前端推断**而不是让后端多发明事件：
     后端已经发了 `waiting` / `thinking` / `tool_start` / `tool_result` / `text`，
     足够拼出阶段。加新事件要改双链路（还有 ds-free），成本高且容易漂移。
     前端推断只有一个真值来源：**最近发生了什么事件**。
-->
<template>
  <div v-if="visible" :class="['ars', `ars-${tone}`]" role="status" aria-live="polite">
    <!-- 左侧：状态图标（跑动时转圈，完成/失败时换成对错号） -->
    <span class="ars-mark" aria-hidden="true">
      <span v-if="running" class="ars-spinner"></span>
      <OsIcon v-else-if="tone === 'ok'" name="check" :size="12" />
      <OsIcon v-else name="close" :size="12" />
    </span>

    <!-- 中间：当前阶段 + 计时 -->
    <div class="ars-main">
      <div class="ars-line">
        <span class="ars-phase">{{ phaseLabel }}</span>
        <span v-if="running" class="ars-elapsed">{{ elapsedText }}</span>
        <span v-else class="ars-elapsed ars-elapsed-done">用时 {{ elapsedText }}</span>
      </div>

      <!--
        细进度条
        · `stalled`（正在等模型，没有正文在流）→ 来回走的"不确定进度"动画
        · 正文正在流 → 从左到右缓慢推进的确定感动画
        两者都不显示具体百分比：我们确实不知道还要多久，显示假百分比是骗用户。
      -->
      <div v-if="running" :class="['ars-bar', stalled ? 'ars-bar-wait' : 'ars-bar-live']" aria-hidden="true">
        <span class="ars-bar-fill"></span>
      </div>
    </div>

    <!-- 右侧：已完成步骤（默认收起，点开看明细） -->
    <button
      v-if="steps.length"
      type="button"
      class="ars-toggle"
      @click="showSteps = !showSteps"
    >
      {{ showSteps ? '收起' : `已完成 ${doneCount} 步` }}
      <span class="ars-caret" :class="{ 'ars-caret-open': showSteps }" aria-hidden="true"></span>
    </button>
  </div>

  <!-- 步骤明细（放在外层，避免被 flex 挤压） -->
  <ul v-if="visible && showSteps && steps.length" class="ars-steps">
    <li v-for="(s, i) in steps" :key="i" :class="['ars-step', `is-${s.state}`]">
      <span class="ars-step-dot" aria-hidden="true"></span>
      <span class="ars-step-text">{{ s.label }}</span>
      <span v-if="s.detail" class="ars-step-detail">{{ s.detail }}</span>
    </li>
  </ul>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

/**
 * 阶段键
 *
 * 顺序即"正常流程的先后"，用于判断"某阶段是否已经过了"。
 * `done` / `error` 是终态。
 */
export type RunPhase =
  | 'connecting'   // 已发出请求，还没收到任何事件
  | 'understanding'// 收到 waiting（模型开始处理）
  | 'thinking'     // 有 reasoning 增量在流（深度思考）
  | 'composing'    // 有正文增量在流
  | 'tool'         // 工具执行中
  | 'done'
  | 'error'

interface StepItem {
  label: string
  detail?: string
  state: 'done' | 'running' | 'failed'
}

const props = withDefaults(
  defineProps<{
    /** 本轮是否在跑（由父级 `isGenerating` 驱动） */
    running?: boolean
    /**
     * 当前阶段。父级从事件流推断后传进来。
     *
     * ⚠️ 这里**不在组件内自己听事件**：状态条是纯展示组件，
     *    把"事件 → 阶段"的推断留在页面层，组件才能被单测和复用。
     */
    phase?: RunPhase
    /** 当前正在执行的工具名（`tool` 阶段显示「正在调用 XX」） */
    tool?: string
    /** 本轮开始时间戳（ms）。用于算耗时；父级只记一次 */
    startedAt?: number
    /** 最近一次"有内容在动"的时间戳（ms）——用来判断是否进入"停滞等待" */
    lastActivityAt?: number
    /** 本轮是否以失败结束 */
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

const emit = defineEmits<{ (e: 'toggle-steps', open: boolean): void }>()

/** 用户是否展开了步骤明细 */
const showSteps = ref(false)

/** 计时用的"现在"，每秒刷新一次 */
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

/** 是否可见：跑着，或刚结束但失败（让用户看到失败原因的存在感） */
const visible = computed(() => props.running || props.failed)

/**
 * 视觉基调
 * 跑动中 → 中性；结束且失败 → 失败色；正常结束 → 成功色
 */
const tone = computed(() => {
  if (props.running) return 'run'
  return props.failed ? 'fail' : 'ok'
})

/** 已耗时（ms） */
const elapsedMs = computed(() => {
  if (!props.startedAt) return 0
  // 结束后不再走表：用"最后一次活动"封口，避免显示成越等越久
  const end = props.running ? now.value : (props.lastActivityAt || now.value)
  return Math.max(0, end - props.startedAt)
})

/**
 * 耗时文案
 *
 * 一分钟以内显示 `12 秒`（精确到秒，用户对前 60 秒最敏感）；
 * 超过一分钟显示 `1 分 23 秒`（此时秒数已不重要，但保留能体现"在动"）。
 */
const elapsedText = computed(() => {
  const s = Math.floor(elapsedMs.value / 1000)
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  const rest = s % 60
  return `${m} 分 ${rest} 秒`
})

/**
 * 是否处于"停滞等待"
 *
 * 判据：正在跑，且距上次活动超过 2.5 秒。
 *
 * 为什么是 2.5 秒：实测正常流式输出时事件间隔多在 1 秒内；
 * 超过 2.5 秒还没动静，用户就会开始觉得"卡住了"。
 * 这个阈值只影响进度条动画风格，不影响功能，宁可早一点切过去。
 */
const stalled = computed(() => {
  if (!props.running) return false
  const last = props.lastActivityAt || props.startedAt
  if (!last) return false
  return now.value - last > 2500
})

/**
 * 阶段文案
 *
 * ⚠️ 措辞原则：说"我现在在做什么"，而不是"正在处理"。
 *    「正在写正文」比「处理中」有信息量得多 —— 用户能据此判断还要不要等。
 */
const phaseLabel = computed(() => {
  if (!props.running) {
    return props.failed ? '任务中断' : '任务完成'
  }
  switch (props.phase) {
    case 'connecting':
      return '正在连接…'
    case 'understanding':
      return '正在理解你的需求…'
    case 'thinking':
      // 长思考最容易让人以为卡死 → 明确说"在推演"
      return stalled.value ? '正在深入推演（内容较长，请稍候）…' : '正在深度思考…'
    case 'composing':
      return '正在写正文…'
    case 'tool':
      return props.tool ? `正在调用「${props.tool}」…` : '正在执行工具…'
    default:
      return '正在处理…'
  }
})

/**
 * 步骤清单
 *
 * 只在**已经过去**的阶段上生成，让用户看到"前面做了什么"。
 * 当前阶段不列进来 —— 它已经占着 `ars-phase` 那一行，重复显示是噪声。
 */
const steps = computed<StepItem[]>(() => {
  const out: StepItem[] = []
  const p = props.phase

  // 阶段顺序（用于判断"是否已过"）
  const order: RunPhase[] = ['connecting', 'understanding', 'thinking', 'tool', 'composing']
  const idx = order.indexOf(p)

  if (idx > 0 || !props.running) out.push({ label: '理解需求', state: 'done' })
  if (idx > 2 || (idx === -1 && !props.running && !props.failed)) {
    out.push({ label: '深度思考', state: 'done' })
  }
  if (idx > 3 || (idx === -1 && !props.running && !props.failed)) {
    out.push({ label: '调用工具', state: 'done' })
  }
  if (!props.running && !props.failed) {
    out.push({ label: '生成正文', state: 'done' })
  }
  if (props.failed) {
    out.push({ label: '任务中断', state: 'failed' })
  }
  return out
})

/** 已完成步骤数（用于「已完成 N 步」按钮文案） */
const doneCount = computed(() => steps.value.filter((s) => s.state === 'done').length)

/** 计时器：跑动时每秒刷新；停下来立刻清掉，别让定时器空转 */
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

/** 步骤展开状态变化时通知父级（父级可能需要滚动跟随） */
watch(showSteps, (open) => emit('toggle-steps', open))

onBeforeUnmount(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
.ars {
  display: flex;
  align-items: center;
  gap: 8px;
  /* 与消息内容区同宽但不撑满（太长会显得笨重），居中偏左 */
  width: fit-content;
  min-width: 260px;
  max-width: min(560px, 100%);
  padding: 7px 12px;
  margin: 0 0 8px;
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.4;
  color: #475569;
  background: #f5f7fa;
  border: 1px solid #e6ebf2;
}

/* 跑动中：淡蓝背景，暗示"正在进行" */
.ars-run {
  background: #f2f7fd;
  border-color: #dbe8f7;
  color: #2c4a6b;
}

/* 成功：浅绿，短暂停留 */
.ars-ok {
  background: #f2faf4;
  border-color: #d8ecdd;
  color: #2b6339;
}

/* 失败：浅红 */
.ars-fail {
  background: #fdf4f4;
  border-color: #f3dcdc;
  color: #8c3030;
}

.ars-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex: 0 0 14px;
}

/* 转圈：12px 细环，比大 spinner 轻 */
.ars-spinner {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 1.6px solid currentColor;
  border-top-color: transparent;
  opacity: 0.75;
  animation: ars-spin 0.8s linear infinite;
}

@keyframes ars-spin {
  to { transform: rotate(360deg); }
}

.ars-main {
  flex: 1 1 auto;
  min-width: 0;
}

.ars-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.ars-phase {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 计时用等宽数字，走动时不会左右抖 */
.ars-elapsed {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
  font-size: 11.5px;
  opacity: 0.72;
}

.ars-elapsed-done {
  opacity: 0.6;
}

/* ── 细进度条 ──
 *
 * ⚠️ 宽度必须收窄（2026-10-27 截图确认）：
 *    第一版让它撑满整条状态条，1440px 视口下是一根 900px 的长线，
 *    中间那段滚动的深色块像"进度条坏了"，很难看。
 *
 *    它不是真的进度指示（我们确实不知道还要多久），
 *    只是"系统在动"的信号 —— 那么短一点就够，长了反而抢注意力。
 *    收在文案下方 120px 内，视觉上是文案的附属标注。
 */
.ars-bar {
  position: relative;
  height: 2px;
  width: 120px;
  max-width: 100%;
  margin-top: 5px;
  border-radius: 1px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.06);
}

.ars-bar-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: 1px;
  background: currentColor;
  opacity: 0.5;
}

/* 等待期：来回走的"不确定"动画 —— 明确表达"在动但不知道还要多久" */
.ars-bar-wait .ars-bar-fill {
  width: 34%;
  animation: ars-indeterminate 1.5s ease-in-out infinite;
}

@keyframes ars-indeterminate {
  0%   { left: -34%; }
  50%  { left: 50%; }
  100% { left: 100%; }
}

/* 有内容在流：缓慢从短到长的确定感动画 */
.ars-bar-live .ars-bar-fill {
  width: 22%;
  animation: ars-breathe 2.2s ease-in-out infinite;
}

@keyframes ars-breathe {
  0%   { left: 0;    width: 18%; }
  50%  { left: 40%;  width: 30%; }
  100% { left: 82%;  width: 18%; }
}

/* ── 步骤折叠按钮 ── */
.ars-toggle {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 6px;
  font-size: 11.5px;
  color: inherit;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 0.15s, background 0.15s;
}

.ars-toggle:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.04);
}

.ars-caret {
  width: 0;
  height: 0;
  border-left: 3.5px solid transparent;
  border-right: 3.5px solid transparent;
  border-top: 4px solid currentColor;
  transition: transform 0.18s;
}

.ars-caret-open {
  transform: rotate(180deg);
}

/* ── 步骤明细 ── */
.ars-steps {
  margin: 0 0 8px;
  padding: 6px 12px 6px 26px;
  width: fit-content;
  min-width: 260px;
  max-width: min(560px, 100%);
  list-style: none;
  font-size: 12px;
  color: #5a6b80;
  background: #fafbfd;
  border: 1px solid #eef1f6;
  border-radius: 8px;
}

.ars-step {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2.5px 0;
}

.ars-step-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.35;
}

.ars-step.is-done .ars-step-dot {
  background: #3f9c56;
  opacity: 0.9;
}

.ars-step.is-running .ars-step-dot {
  background: #3b82c4;
  opacity: 1;
}

.ars-step.is-failed .ars-step-dot {
  background: #c0504d;
  opacity: 1;
}

.ars-step-detail {
  font-size: 11px;
  opacity: 0.6;
}

/* 窄屏：计时与阶段换行，别挤成一坨 */
@media (max-width: 640px) {
  .ars {
    flex-wrap: wrap;
    gap: 4px 8px;
  }
  .ars-line {
    flex-wrap: wrap;
    gap: 2px 8px;
  }
}
</style>
