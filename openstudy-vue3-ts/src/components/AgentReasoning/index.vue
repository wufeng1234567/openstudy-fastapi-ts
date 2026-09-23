<!--
  思考块 —— 深度思考的推理过程（可折叠）

  数据从哪来：DS 页面把 reasoning 发出来 → 扩展 `background.js` 透传 →
  SDK 解析成 `thinking` 事件 → `ds-proxy.chatWithDSAccumulated` 累积 + 节流 →
  `agentDsFree` 转成 `thinking` 事件 → `useAgentChat` 累加成一条
  `type:'reasoning'` 的消息（见那边的注释）。

  ⚠️ 只有 ds-free 链路有推理文本；api 付费链路走 LangChain 没取 reasoning。
  所以这个组件**可能整场都不出现** —— 但它不需要调用方判断有没有，没有对应消息自然不渲染。

  交互取舍（别随手改）：
  · **跑的时候默认展开** —— 「看得见它在推理」正是这个块存在的理由。
    在这之前 Agent 跑半分钟，用户面对的是一个不动的「深度思考中」转圈。
  · **跑完自动折起来** —— 把版面让给答案。用户要的是结论，不是推理全文。
  · 折起来后仍显示「已思考 X 秒」—— 让人知道刚才那半分钟花在哪了。
  · 用户手动展开/收起过之后，**尊重用户的选择**（`userToggled`），
    不再被「跑完自动折」覆盖。否则用户刚展开就被收走，很恼人。
-->
<template>
  <div :class="['reasoning', { 'is-running': running }]">
    <button class="rs-head" type="button" @click="toggle">
      <span class="rs-caret" :class="{ open: expanded }">▸</span>
      <span class="rs-label">
        <template v-if="running">深度思考中</template>
        <template v-else>已思考 {{ secs }} 秒</template>
      </span>
      <span v-if="running" class="rs-pulse" aria-hidden="true"></span>
      <span v-else class="rs-hint">{{ expanded ? '收起' : '展开' }}</span>
    </button>

    <div v-show="expanded" ref="bodyRef" class="rs-body">{{ content }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

const props = withDefaults(
  defineProps<{
    content: string
    /** 思考耗时（秒）。**null/undefined 表示还在跑** —— 没有 status 字段 */
    secs?: number
  }>(),
  { secs: undefined }
)

/** `secs` 有值 = 已经收口（见 useAgentChat.closeReasoning 的注释） */
const running = computed(() => props.secs == null)

/**
 * 初始展开态直接由「是否还在跑」定 —— 不要先写成 true 再在 onMounted 里改，
 * 那样从会话历史复原已完成块时会闪一下展开的内容。
 */
const expanded = ref(props.secs == null)
/** 用户手动点过之后就不再自动折叠 —— 否则「刚展开就被收走」 */
const userToggled = ref(false)

const bodyRef = ref<HTMLElement | null>(null)

/** 贴着底部跟随：推理是持续追加的，不跟随就只能看到开头 */
const scrollToBottom = async () => {
  if (!running.value || !expanded.value) return
  await nextTick()
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(() => props.content, scrollToBottom)
// 跑完自动折起来（除非用户自己动过）
watch(running, (nowRunning) => {
  if (nowRunning || userToggled.value) return
  expanded.value = false
})

const toggle = () => {
  expanded.value = !expanded.value
  userToggled.value = true
  if (expanded.value) scrollToBottom()
}
</script>

<style scoped>
.reasoning {
  border-left: 3px solid #cbd5e1;
  background: #f8fafc;
  border-radius: 8px;
  overflow: hidden;
  max-width: min(92%, 720px);
}

.reasoning.is-running {
  border-left-color: #a5b4fc;
  background: #f8faff;
}

.rs-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 12px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-size: 12.5px;
  line-height: 1.6;
  color: #4a5a72;
}

.rs-head:hover {
  background: #eef2f7;
}

.rs-caret {
  flex-shrink: 0;
  display: inline-block;
  transition: transform 0.15s ease;
  color: #94a3b8;
  font-size: 10px;
}

.rs-caret.open {
  transform: rotate(90deg);
}

.rs-label {
  font-weight: 600;
}

.rs-hint {
  margin-left: auto;
  color: #94a3b8;
  font-size: 11.5px;
}

/* 「正在思考」的小圆点：只是让人知道它活着，不抢注意力 */
.rs-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #6366f1;
  animation: rs-pulse 1.2s ease-in-out infinite;
}

@keyframes rs-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.rs-body {
  max-height: 260px;
  overflow-y: auto;
  padding: 0 12px 9px 30px;
  font-size: 12.5px;
  line-height: 1.75;
  color: #64748b;
  /* 推理的换行/缩进有意义（模型会分行列步骤）→ 原样保留 */
  white-space: pre-wrap;
  word-break: break-word;
}

@media (prefers-reduced-motion: reduce) {
  .rs-pulse {
    animation: none;
  }
}
</style>
