<!--
  思考态 —— 深度思考的**推理正文**（可折叠、**运行中实时流式**）

  用户 2026-10-11（二次定案，回退"不暴露"）：**重新把思维链暴露给用户**——
  "深度思考思维链暴露出来给用户看"。故本组件恢复**渲染推理正文**（`content`），
  并保证**运行中实时逐字增长 + 自动跟随滚动**（这是此前"先出几个字符→卡住→最后才
  一次性刷出"的观感修复点之一：前端必须接住每一个增量并即时上屏）。

  数据来源（上游 `useAgentChat`）：`thinking` 事件逐 chunk 传入 → `appendReasoning` 累加进
  `content`；收口时写 `secs`。故：
    · 运行中（`secs == null`）：显示"深度思考中…" + **实时推理正文**（自动滚动到底）
    · 收口后（`secs` 有值）：**默认折起**为一行「已深度思考 X 秒」，点击可展开看全文

  交互：
  · 运行中默认展开并跟随底部（用户要看到它在"实时思考"）；
  · 用户手动收起后，运行中不再强拉展开（尊重用户操作）；收口时**延迟片刻**再折，避免
    "自动折"与"内容仍在增长"打架（否则会看着看着突然折起来，像卡住）。
-->
<template>
  <div class="rs-box" :class="{ 'rs-running': running, 'rs-collapsed': !expanded }">
    <!-- 头部：可点击折叠/展开 -->
    <div class="rs-head" role="button" tabindex="0" @click="toggle" @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle">
      <span class="rs-status">
        <!--
          状态图标（用户 2026-10-17：不要绿色对勾徽章，要更贴合"思考"的图形 + 低调）：
            · 运行中 → 一枚缓慢旋转的四角星（表达"在想"，不是"在加载"）；
            · 已收口 → 同一枚四角星，静止、更淡，不再用"✓ 成功"的语义。
          两态共用同一个形状，切换时只是动画与透明度变化，观感更连贯。
        -->
        <span class="rs-spark" :class="{ 'rs-spark-running': running }" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="13" height="13">
            <path
              d="M8 1.6c.5 2.6 1.3 3.4 3.9 3.9-2.6.5-3.4 1.3-3.9 3.9-.5-2.6-1.3-3.4-3.9-3.9C6.7 5 7.5 4.2 8 1.6Z"
              fill="currentColor" />
            <path
              d="M12.4 9.6c.28 1.45.72 1.9 2.17 2.17-1.45.28-1.9.72-2.17 2.17-.28-1.45-.72-1.9-2.17-2.17 1.45-.27 1.9-.72 2.17-2.17Z"
              fill="currentColor" opacity=".55" />
          </svg>
        </span>
        <span class="rs-title">
          <template v-if="running">深度思考中…</template>
          <template v-else>已深度思考 {{ secs }} 秒</template>
        </span>
        <span v-if="running && content.length" class="rs-live-hint">实时</span>
      </span>
      <span class="rs-caret" :class="{ 'rs-caret-open': expanded }" aria-hidden="true">
        <svg viewBox="0 0 16 16" width="14" height="14">
          <path d="M5 6l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6"
            stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
    </div>

    <!-- 正文：推理文本（可折叠；运行中实时增长）
         ⚠️ 2026-10-27：原来是 `{{ content }}` 纯文本插值，
            于是思考过程里的 LaTeX 全部原样露出（用户截图那一大片
            `$\lim_{x\to 0}\frac{\sin 3x}{x}$`）。
            但推理正文有几个和聊天正文不同的约束，不能直接套同一套渲染：

              1. 它是**流式**的 —— 半截公式是常态（`$\lim_{x\to` 时
                 `$` 还没闭合），强行渲染会满屏 KaTeX 报错。
              2. 它会被**截断**（TIMELINE_REASONING_LIMIT=4000），
                 可能切在公式中间。
              3. 它是灰色小字、行高更紧，样式不能照搬正文。

            所以用 `renderStreamingMath()`：会把末尾未闭合的定界符
            整段当原文输出，等写完了自然变成公式。 -->
    <div v-show="expanded" ref="bodyRef" class="rs-body">
      <span v-if="content" class="rs-md" v-html="renderedContent"></span>
      <span v-else class="rs-empty">正在思考…</span>
      <!-- 运行中的光标，暗示"还在往下写" -->
      <span v-if="running" class="rs-cursor" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onBeforeUnmount } from 'vue'
import { useSmoothAutoScroll } from '@/composables/useSmoothAutoScroll'
import { renderStreamingMath } from '@/utils/latex'

const props = withDefaults(
  defineProps<{
    /** 推理正文（逐 chunk 累加；运行中实时增长） */
    content?: string
    /** 思考耗时（秒）。**null/undefined 表示还在跑**（`useAgentChat.closeReasoning` 写值） */
    secs?: number
  }>(),
  { content: '', secs: undefined }
)

/**
 * 渲染后的推理正文（含公式）
 *
 * 用 `renderStreamingMath` 而不是普通的 `renderMarkdownWithLatex`：
 * 推理正文是**流式**的，末尾经常有未闭合的 `$`（模型正写到一半），
 * 普通渲染会把那半截当普通文字露出来、或者强行渲染成报错块。
 * `renderStreamingMath` 会把未闭合的尾巴整段当原文，写完自然恢复。
 *
 * 不做 Markdown 渲染（标题/列表/表格）：
 * 推理正文里出现 Markdown 结构的概率很低，而多一层解析会拖慢
 * 流式刷新的流畅度（每次 chunk 都要重跑一遍 AST）。
 */
const renderedContent = computed(() =>
  props.content ? renderStreamingMath(props.content) : '',
)

/** `secs` 有值 = 已收口 */
const running = computed(() => props.secs == null)

// ---- 折叠状态 ----
// 运行中默认展开（用户要看到实时思考）；用户手动切换后尊重其选择。
const expanded = ref(true)
/** 用户是否手动点过折叠/展开——点过之后就不再"运行中自动展开/收口自动折"地打扰他 */
let userToggled = false
const toggle = () => {
  userToggled = true
  expanded.value = !expanded.value
  if (expanded.value) nextTick(scrollToBottom)
}

// ---- 自动跟随滚动（运行中内容增长时滚到底）----
// ⚠️ 用 useSmoothAutoScroll 而非无条件 `scrollTop = scrollHeight`：
//    后者会在用户上滑回看时把视口强行拽回底部（用户无法自由滚动）。
//    该 composable 只在「用户位于底部附近」时才跟随，用户一旦上滑立即停止，
//    与「题目 AI 解析」页的滚动行为完全一致。
const bodyRef = ref<HTMLElement | null>(null)
const { keepAtBottom, scrollToBottom } = useSmoothAutoScroll(bodyRef)

// 内容增长：仅在跟随时滚到底（用户上滑后不再打扰）；收口后若有迟到增量也跟随
watch(
  () => props.content,
  () => {
    // 内容一到就取消"收口延迟折叠"，说明还在长
    if (collapseTimer) {
      clearTimeout(collapseTimer)
      collapseTimer = null
    }
    if (expanded.value) nextTick(keepAtBottom)
  }
)

// 展开时落到底（用户主动展开默认想看到最新内容）——用即时定位，直接到底
watch(expanded, (open) => {
  if (open) nextTick(scrollToBottom)
})

// 收口：延迟片刻再折叠（避免"自动折"与"内容仍在增长"打架；用户手动操作过则不自动折）
let collapseTimer: ReturnType<typeof setTimeout> | null = null
watch(running, (isRunning) => {
  if (isRunning) {
    // 又开始跑了：只有用户没手动收起过才自动展开
    if (!userToggled) expanded.value = true
    return
  }
  if (userToggled) return
  collapseTimer = setTimeout(() => {
    expanded.value = false
    collapseTimer = null
  }, 1000)
})

onBeforeUnmount(() => {
  if (collapseTimer) clearTimeout(collapseTimer)
})
</script>

<style scoped>
/* ============ 容器 ============
   用户 2026-10-17：「不要边框，要低调，有边框感觉突兀」。
   做法与工具结果一致 —— 不套卡片，让"已深度思考 1 秒"直接躺在对话流里，
   只有 hover 时给一层极淡的底（提示这里可点），不做常驻描边。 */
.rs-box {
  border: none;
  border-radius: 8px;
  background: transparent;
  overflow: hidden;
  max-width: 100%;
}

/* ============ 头部 ============ */
.rs-head {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  max-width: 100%;
  padding: 2px 8px 2px 2px;
  margin-left: -2px;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  font-size: 12.5px;
  color: var(--os-text-3);
  transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out);
}

.rs-head:hover {
  background: var(--os-bg-hover);
}

.rs-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.rs-title {
  white-space: nowrap;
}

.rs-running .rs-title {
  color: var(--os-text-2);
}

/* ============ 状态星标 ============
   形状固定（四角星），只靠"转不转"和"深浅"区分运行/收口：
   · 运行中：缓慢旋转 + 主色，暗示"在想"；
   · 已收口：静止 + 更淡，退回背景层。 */
.rs-spark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--os-text-4);
}

.rs-spark-running {
  color: var(--os-accent);
  animation: rs-spin 3.2s linear infinite;
}

.rs-live-hint {
  font-size: 11px;
  color: var(--os-accent);
  background: var(--dsw-static-blue-50);
  border-radius: 999px;
  padding: 0 7px;
  line-height: 16px;
  animation: rs-blink 1.4s ease-in-out infinite;
}

.rs-caret {
  display: inline-flex;
  flex-shrink: 0;
  color: var(--os-text-4);
  transition: transform 0.2s ease;
}

.rs-caret-open {
  transform: rotate(180deg);
}

/* ============ 正文 ============ */
/* 也不描边：用左侧一条极淡的竖线表示"这是附属内容"，比整框更轻。 */
.rs-body {
  margin: 2px 0 2px 8px;
  padding: 2px 10px 4px;
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--os-text-3);
  /*
   * ⚠️ pre-wrap 会给**容器内所有文本节点**保留空白与换行。
   *    纯文本时这是对的（保住模型输出的换行），
   *    但 KaTeX 的 HTML 结构里塞满了用于对齐的空白 span，
   *    在 pre-wrap 下会被全部保留 → 公式被撑开、字符间出现大间隔。
   *    所以真正的文本放进 .rs-md，由它控制空白策略。
   */
  white-space: normal;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  border-left: 1px solid var(--os-border-soft);
}

/* 推理正文（含公式）
   换行已经由 renderStreamingMath 转成 <br>，这里不需要 pre-wrap；
   但保留 pre-wrap 会让公式错乱，所以用 normal。 */
.rs-md {
  white-space: normal;
}

/* ⚠️ 必须 :deep()：v-html 注入的 KaTeX 节点拿不到 scoped 属性 */
.rs-body :deep(.katex) {
  /* 思考区字号是 12.5px，公式跟着略缩，避免比正文大一圈显得突兀 */
  font-size: 1.02em;
}

.rs-body :deep(.katex-display) {
  margin: 4px 0;
  overflow-x: auto;
  overflow-y: hidden;
}

/* 公式下方的基线微调：KaTeX 的 strut 在小字号下会略显下沉 */
.rs-body :deep(.katex-html) {
  line-height: 1.2;
}

.rs-empty {
  color: var(--os-text-4);
}

/* 运行中的光标（在正文末尾闪，暗示还在写） */
.rs-cursor {
  display: inline-block;
  width: 5px;
  height: 12px;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: var(--os-accent);
  border-radius: 1px;
  animation: rs-blink 1s steps(2, start) infinite;
}

@keyframes rs-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes rs-blink {
  50% {
    opacity: 0.25;
  }
}

@media (prefers-reduced-motion: reduce) {
  .rs-spark-running,
  .rs-live-hint,
  .rs-cursor {
    animation: none;
  }
}
</style>
