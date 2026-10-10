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
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'

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

/**
 * 贴着底部跟随：推理是持续追加的，不跟随就只能看到开头。
 *
 * ⚠️ 判据只看 `expanded`（**不再要求 `running`**）：思考正文可能在块"收口"之后
 * 才迟到（见下面第二个 watch 的说明），那时 `running` 已是 false 但内容还在涨 ——
 * 若因 `!running` 就停止跟随，用户就看不到后续内容。
 */
const scrollToBottom = async () => {
  if (!expanded.value) return
  await nextTick()
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

/**
 * 内容仍在**追加剧增**时，若还没折过也保持展开
 *
 * ⚠️ 为什么需要：上游 reasoning 与正文/工具事件的先后**没有保证** ——
 * `closeReasoning()` 可能因为「正文/工具卡先到」而先把块收口（`secs` 有值 → `running=false`），
 * 但**思考正文还在后续到达**（`appendReasoning` 的"迟到增量"分支会继续 `content += delta`）。
 * 此时若 `running` 已为 false 就收起，用户看到的就是「思考块一闪而过 / 只能看到开头，
 * 剩下的要等全部结束才看得到」（用户 2026-10-10 报的现象）。
 * 故：只要**内容还在增长**、且用户没手动收起过，就保持展开并跟随底部。
 */
let collapseTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => props.content,
  () => {
    // 有新内容 → 取消"将要折叠"的挂起动作，保持展开并跟随
    if (collapseTimer) {
      clearTimeout(collapseTimer)
      collapseTimer = null
    }
    if (!userToggled.value && !expanded.value) expanded.value = true
    scrollToBottom()
  }
)

// 跑完（收口）后**稍等片刻**再折叠：给"迟到的思考增量"一个窗口 ——
// 若窗口内又有内容到达，上面的 watch 会取消这次折叠，块保持展开。
watch(running, (nowRunning) => {
  if (nowRunning || userToggled.value) return
  if (collapseTimer) clearTimeout(collapseTimer)
  collapseTimer = setTimeout(() => {
    collapseTimer = null
    if (!userToggled.value) expanded.value = false
  }, 1000)
})

const toggle = () => {
  expanded.value = !expanded.value
  userToggled.value = true
  if (expanded.value) scrollToBottom()
}

onBeforeUnmount(() => {
  if (collapseTimer) {
    clearTimeout(collapseTimer)
    collapseTimer = null
  }
})
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
