<!--
  思考态 —— 深度思考时的**等待动画**（**不暴露推理正文**）

  用户 2026-10-11：「深度思考的思维链不再暴露，改成更好的等待动画效果，不输出流式思考数据了」

  ⚠️ 与旧版的根本区别：**这里不再渲染 `content`（推理文本）**。推理内容对用户是
     "内部思维链"，暴露它既冗长又带格式噪声；C 端只需一个**体面、有信息量的等待动画**。
    所以本组件把 `content` 这个 prop **只用来判断"有没有在思考"、不再显示**——
      · 运行中：一条「深度思考」脉冲动画（呼吸光点 + 文案流光扫过）
      · 收口后：收成一行轻量「已深度思考 X 秒」，把版面让给答案

  数据从哪来（保持不变，上游零改动）：`useAgentChat` 仍按 `thinking` 事件累加成一条
  `type:'reasoning'` 的消息并维护 `secs`（跑完写值）。本组件只消费 `secs` 的
  「有值=收口 / null=还在跑」语义。

  交互取舍：
  · **不提供展开** —— 既然不显示内容，就没有"展开/收起"这回事（旧版的折叠交互一并去掉）。
  · 收口后保留耗时 —— 让用户知道刚才那段等待花在哪了，且不泄露任何推理内容。
-->
<template>
  <!-- 运行中：等待动画 -->
  <div v-if="running" class="rs-wait" role="status" aria-live="polite">
    <span class="rs-orbits" aria-hidden="true">
      <span class="rs-orbit rs-orbit-1"></span>
      <span class="rs-orbit rs-orbit-2"></span>
      <span class="rs-orbit rs-orbit-3"></span>
    </span>
    <span class="rs-shimmer">深度思考中…</span>
  </div>

  <!-- 收口后：一行轻量耗时，无内容 -->
  <div v-else class="rs-done">
    <span class="rs-check" aria-hidden="true">
      <svg viewBox="0 0 16 16" width="12" height="12">
        <path
          d="M3.5 8.5l3 3 6-6.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </span>
    <span class="rs-done-text">已深度思考 {{ secs }} 秒</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    /**
     * 推理正文 —— **已不再展示**（用户 2026-10-11：不暴露思维链）。
     * 仍保留该 prop 以免动上游：仅用于兼容旧调用点，不参与渲染。
     */
    content?: string
    /** 思考耗时（秒）。**null/undefined 表示还在跑**（`useAgentChat.closeReasoning` 写值） */
    secs?: number
  }>(),
  { content: '', secs: undefined }
)

/** `secs` 有值 = 已收口（与上游 `closeReasoning` 的口径一致） */
const running = computed(() => props.secs == null)
</script>

<style scoped>
/* ============ 运行中：脉冲等待动画 ============ */
.rs-wait {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px 7px 12px;
  border-radius: 999px;
  /* 温柔的蓝紫渐变底 + 外发光，比裸三点更有"在运转"的质感 */
  background: linear-gradient(100deg, #eef2ff 0%, #f5f3ff 50%, #eef2ff 100%);
  background-size: 200% 100%;
  border: 1px solid #e0e7ff;
  box-shadow: 0 1px 8px rgba(99, 102, 241, 0.12);
  animation: rs-bg-drift 3s ease-in-out infinite;
}

/* 三条错峰呼吸的短弧（旋转 + 明暗），替代老三点的上下抖 */
.rs-orbits {
  position: relative;
  display: inline-block;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.rs-orbit {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: #6366f1;
  animation: rs-spin 1.3s linear infinite;
}

.rs-orbit-2 {
  inset: 3px;
  border-top-color: #8b5cf6;
  animation-duration: 1.7s;
  animation-direction: reverse;
}

.rs-orbit-3 {
  inset: 6px;
  border-top-color: #a5b4fc;
  animation-duration: 1.1s;
}

/* 文案：柔和流光扫过（shimmer），暗示"正在处理"而不喧哗 */
.rs-shimmer {
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.2px;
  background: linear-gradient(90deg, #818cf8 0%, #4f46e5 25%, #a78bfa 50%, #4f46e5 75%, #818cf8 100%);
  background-size: 200% auto;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: rs-shimmer 2.2s linear infinite;
}

/* ============ 收口后：一行轻量耗时 ============ */
.rs-done {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 2px;
  font-size: 12px;
  color: #94a3b8;
}

.rs-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  color: #818cf8;
  background: #eef2ff;
}

.rs-done-text {
  font-weight: 500;
}

/* ============ animations ============ */
@keyframes rs-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes rs-bg-drift {
  0%,
  100% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
}

@keyframes rs-shimmer {
  to {
    background-position: -200% center;
  }
}

/* 尊重"减少动态"偏好：关掉持续动画，保留静态可见状态 */
@media (prefers-reduced-motion: reduce) {
  .rs-wait,
  .rs-orbits .rs-orbit,
  .rs-shimmer {
    animation: none;
  }
}
</style>
