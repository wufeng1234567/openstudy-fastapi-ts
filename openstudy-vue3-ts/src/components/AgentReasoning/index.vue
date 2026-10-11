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
        <!-- 运行中：小旋转弧；收口：对勾 -->
        <span v-if="running" class="rs-spinner" aria-hidden="true"></span>
        <span v-else class="rs-check" aria-hidden="true">
          <svg viewBox="0 0 16 16" width="12" height="12">
            <path d="M3.5 8.5l3 3 6-6.5" fill="none" stroke="currentColor" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round" />
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

    <!-- 正文：推理文本（可折叠；运行中实时增长） -->
    <div v-show="expanded" ref="bodyRef" class="rs-body">
      <template v-if="content">{{ content }}</template>
      <span v-else class="rs-empty">正在思考…</span>
      <!-- 运行中的光标，暗示"还在往下写" -->
      <span v-if="running" class="rs-cursor" aria-hidden="true"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch, onBeforeUnmount } from 'vue'

const props = withDefaults(
  defineProps<{
    /** 推理正文（逐 chunk 累加；运行中实时增长） */
    content?: string
    /** 思考耗时（秒）。**null/undefined 表示还在跑**（`useAgentChat.closeReasoning` 写值） */
    secs?: number
  }>(),
  { content: '', secs: undefined }
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
const bodyRef = ref<HTMLElement | null>(null)
const scrollToBottom = () => {
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

// 内容增长：跟随时滚到底（不再要求 running —— 收口后若有迟到增量也应跟随）
watch(
  () => props.content,
  () => {
    // 内容一到就取消"收口延迟折叠"，说明还在长
    if (collapseTimer) {
      clearTimeout(collapseTimer)
      collapseTimer = null
    }
    if (expanded.value) nextTick(scrollToBottom)
  }
)

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
/* ============ 容器 ============ */
.rs-box {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #f9fafb;
  overflow: hidden;
  max-width: 100%;
}

.rs-box.rs-running {
  border-color: #e0e7ff;
  background: #f8f9ff;
}

/* ============ 头部 ============ */
.rs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 12.5px;
  color: #6b7280;
}

.rs-head:hover {
  background: rgba(99, 102, 241, 0.06);
}

.rs-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.rs-title {
  white-space: nowrap;
}

.rs-running .rs-title {
  color: #4f46e5;
  font-weight: 600;
}

/* 运行中的小旋转弧 */
.rs-spinner {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  border: 2px solid #c7d2fe;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: rs-spin 0.8s linear infinite;
}

.rs-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border-radius: 50%;
  color: #16a34a;
  background: #dcfce7;
}

.rs-live-hint {
  font-size: 11px;
  color: #6366f1;
  background: #eef2ff;
  border-radius: 999px;
  padding: 0 7px;
  line-height: 16px;
  animation: rs-blink 1.4s ease-in-out infinite;
}

.rs-caret {
  display: inline-flex;
  color: #9ca3af;
  transition: transform 0.2s ease;
}
.rs-caret-open {
  transform: rotate(180deg);
}

/* ============ 正文 ============ */
.rs-body {
  padding: 4px 12px 10px;
  font-size: 12.5px;
  line-height: 1.75;
  color: #4b5563;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
  border-top: 1px dashed #e5e7eb;
}

.rs-empty {
  color: #9ca3af;
}

/* 运行中的光标（在正文末尾闪，暗示还在写） */
.rs-cursor {
  display: inline-block;
  width: 6px;
  height: 13px;
  margin-left: 1px;
  vertical-align: text-bottom;
  background: #6366f1;
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
  .rs-spinner,
  .rs-live-hint,
  .rs-cursor {
    animation: none;
  }
}
</style>
