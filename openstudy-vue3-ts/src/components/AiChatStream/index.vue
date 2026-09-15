<template>
  <div class="ai-chat-stream">
    <!-- 消息列表 -->
    <div class="chat-messages" ref="messagesRef">
      <!-- 空状态插槽 -->
      <slot name="empty" v-if="messages.length === 0 && !isGenerating"></slot>

      <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role, msg.type ? 'msg-' + msg.type : '']">
        <!-- 工具确认卡片 -->
        <div v-if="msg.type === 'tool_confirm'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <slot name="tool-confirm" :message="msg" :index="idx">
            <div class="message-text">{{ msg.content }}</div>
          </slot>
        </div>
        <!-- 工具执行结果 -->
        <div v-else-if="msg.type === 'tool_result'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <slot name="tool-result" :message="msg" :index="idx">
            <div class="message-text">{{ msg.content }}</div>
          </slot>
        </div>
        <!-- 思考过程 -->
        <div v-else-if="msg.type === 'thinking'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <div class="ai-loading-inline">
            <LoadingDots size="small" :label="msg.content || loadingText" />
          </div>
        </div>
        <!-- 普通 assistant 消息 -->
        <div class="message-content" v-else-if="msg.role === 'assistant'">
          <div class="message-role agent-role">Agent</div>
          <div class="message-text rendered-md" @click="copyText(msg.content)" v-html="renderAgentMarkdown(msg.content)">
          </div>
          <el-button class="msg-copy-btn" size="small" text @click.stop="copyText(msg.content)"
            v-if="msg.content && msg.content.trim()">
            复制
          </el-button>
          <div v-if="isGenerating && (!msg.content || msg.content.trim() === '') && isLastAssistantEmpty(idx)" class="ai-loading-inline">
            <LoadingDots size="small" :label="loadingText" />
          </div>
        </div>
        <!-- user 消息 -->
        <div class="message-content" v-else>
          <div class="message-role">我</div>
          <div class="message-text">{{ msg.content }}</div>
        </div>
      </div>
    </div>

    <!-- 滚动按钮 -->
    <ScrollButton :scroll-container="messagesRef" :bottom="16" :right="16" />

    <!-- 输入区 -->
    <div class="chat-input-area">
      <div class="input-box">
        <!-- 上层：用户输入，独占整行 -->
        <el-input v-model="inputContent" type="textarea" :rows="1" :placeholder="placeholder"
          @keydown.enter.exact.prevent="handleSend" :disabled="isGenerating" class="chat-textarea" resize="none" />
        <!-- 下层：工具按钮行（左：深度思考等插槽 / 右：发送、停止），与输入互不干扰 -->
        <div class="input-bottom">
          <div v-if="$slots['input-footer']" class="input-bottom-left">
            <slot name="input-footer"></slot>
          </div>
          <button v-if="isGenerating" class="send-btn stop-btn" @click="$emit('toggle-pause')">
            <svg v-if="!isPaused" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </button>
          <button v-else class="send-btn" @click="handleSend" :disabled="!inputContent.trim()">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { renderAgentMarkdown } from '@/utils/markdown'
import LoadingDots from '@/components/LoadingDots/index.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  isGenerating: { type: Boolean, default: false },
  isPaused: { type: Boolean, default: false },
  /** 是否处于「深度思考」模式（只影响等待文案） */
  thinking: { type: Boolean, default: false },
  placeholder: { type: String, default: '输入消息...（Enter 发送，Ctrl+Enter 换行）' }
})

// 等待文案：深度思考时显示「深度思考中」（配合共用的三点抖动组件）
const loadingText = computed(() => (props.thinking ? '深度思考中' : 'AI 思考中'))

const emit = defineEmits(['update:messages', 'send', 'stop', 'toggle-pause'])

const inputContent = ref('')
const messagesRef = ref(null)
const isNearBottom = ref(true)

// 判断是否是最后一条空的 assistant 消息（用于显示 loading 动画）
const isLastAssistantEmpty = (idx) => {
  // 从当前位置往前找，看是否是最后一条 assistant 消息
  for (let i = props.messages.length - 1; i > idx; i--) {
    if (props.messages[i].role === 'assistant' && props.messages[i].type !== 'tool_confirm' && props.messages[i].type !== 'tool_result') {
      return false
    }
  }
  return true
}

const copyText = async (text) => {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('复制成功')
  } catch {
    ElMessage.error('复制失败')
  }
}

const handleSend = () => {
  const content = inputContent.value.trim()
  if (!content || props.isGenerating) return
  emit('send', { content })
  inputContent.value = ''
}

// 检测是否在底部附近（50px 内）
const checkNearBottom = () => {
  if (!messagesRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  isNearBottom.value = scrollHeight - scrollTop - clientHeight < 50
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// 只在用户在底部附近时自动滚动
const autoScrollIfNearBottom = async () => {
  if (!isNearBottom.value) return
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

onMounted(() => {
  if (messagesRef.value) {
    messagesRef.value.addEventListener('scroll', checkNearBottom, { passive: true })
  }
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', checkNearBottom)
  }
})

// 新消息到来时：如果在底部附近则滚动
watch(() => props.messages.length, () => {
  autoScrollIfNearBottom()
})

// 流式内容更新时：如果在底部附近则滚动
watch(() => {
  if (props.messages.length > 0) {
    const last = props.messages[props.messages.length - 1]
    return last?.content?.length || 0
  }
  return 0
}, () => {
  if (props.isGenerating) {
    autoScrollIfNearBottom()
  }
})

defineExpose({ scrollToBottom, messagesRef })
</script>

<style scoped lang="scss">
.ai-chat-stream {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  position: relative;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background-color: #f8f9fa;
  position: relative;
  overflow-x: hidden;
}

.message {
  margin-bottom: 16px;
  display: flex;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  background-color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
  border: 1px solid #e5e7eb;
  position: relative;
}

.message.user .message-content {
  background-color: #f3f4f6;
  color: #1f2937;
  border: 1px solid #e5e7eb;
}

.message-role {
  font-size: 12px;
  margin-bottom: 6px;
  opacity: 0.7;
}

.agent-role {
  color: #059669;
  font-weight: 600;
  font-size: 13px;
  opacity: 1;
}

.message-text {
  line-height: 1.6;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.msg-copy-btn {
  position: absolute;
  bottom: 8px;
  right: 12px;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 12px;
  z-index: 10;
  color: #6b7280;
  background: #f3f4f6;
  border: 1px solid #e5e7eb;
  transition: all 0.2s;
}

.msg-copy-btn:hover {
  background: #fff;
  border-color: #d1d5db;
}

/* AI 加载动画（内联在消息内） */
.ai-loading-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.ai-loading-text {
  color: #909399;
  font-size: 13px;
}

/* 打字动画 */
.typing {
  display: flex;
  gap: 4px;
  align-items: center;
  min-height: 20px;
}

.typing span {
  width: 8px;
  height: 8px;
  background-color: #999;
  border-radius: 50%;
  animation: typing 1.4s infinite ease-in-out both;
}

.typing span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes typing {

  0%,
  80%,
  100% {
    transform: scale(0);
  }

  40% {
    transform: scale(1);
  }
}

/* 输入区 */
.chat-input-area {
  background-color: white;
  padding: 12px 16px;
  border-top: 1px solid #e5e7eb;
}

/* 输入框下层：工具按钮行（左：深度思考等插槽 / 右：发送按钮），与上层输入互不干扰 */
.input-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  min-height: 36px;
}

.input-bottom-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.input-box {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  background: #f8f9fa;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 10px 10px 10px 14px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 66px;
  margin-bottom: 0px;

  &:hover {
    border-color: #d1d5db;
  }

  &:focus-within {
    border-color: #b3b3b3;
    background: #fff;
  }

  .chat-textarea {
    width: 100%;

    :deep(.el-textarea__inner) {
      border: none;
      box-shadow: none;
      background: transparent;
      padding: 4px 0;
      font-size: 14px;
      line-height: 1.5;
      resize: none;
      height: 100% !important;
      min-height: 36px;
      max-height: 120px;

      &::placeholder {
        color: #9ca3af;
        font-size: 13px;
      }

      &:hover,
      &:focus {
        box-shadow: none;
      }
    }
  }

  .send-btn {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    margin-left: auto; /* 下层靠右，与左侧工具按钮同层 */
    border-radius: 8px;
    border: none;
    background: #e5e7eb;
    color: #9ca3af;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    padding: 0;

    &:hover:not(:disabled) {
      background: #1f2937;
      color: #fff;
    }

    &:active:not(:disabled) {
      transform: scale(0.95);
    }

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    &.stop-btn {
      background: #fef2f2;
      color: #b45353;

      &:hover {
        background: #fee2e2;
        color: #991b1b;
      }
    }

    svg {
      display: block;
    }
  }
}
</style>

<style lang="scss">
.tool-json-block {
  margin-top: 12px;
  padding: 16px 18px;
  max-height: 300px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f5f7fa;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: #dcdfe6;
    border-radius: 3px;

    &:hover {
      background: #c0c4cc;
    }
  }
}

.tool-json-content {
  margin: 0;
  font-family: 'SF Mono', 'Monaco', 'Cascadia Code', 'Consolas', monospace;
  font-size: 14px;
  line-height: 1.8;
  color: #1a1a1a;
  white-space: pre-wrap;
  word-break: break-word;
}

.rendered-md {
  line-height: 1.7;
  font-size: 15px;
  color: #1f2937;
  padding-bottom: 20px;
  cursor: pointer;
  overflow-wrap: break-word;
  word-break: break-word;

  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    margin: 1em 0 0.5em;
    color: #1f2937;
    font-weight: 700;
    line-height: 1.3;
    word-break: break-word;
  }

  h1 {
    font-size: 1.75em;
  }

  h2 {
    font-size: 1.35em;
  }

  h3 {
    font-size: 1.15em;
  }

  p {
    margin: 0 0 10px;
  }

  ul,
  ol {
    padding-left: 1.5em;
    margin: 0.4em 0;
  }

  li {
    word-break: break-word;
  }

  blockquote {
    margin: 0.6em 0;
    padding: 6px 14px;
    border-left: 4px solid #d1d5db;
    color: #6b7280;
    background: #f9fafb;
    border-radius: 0 8px 8px 0;
  }

  pre {
    background: #fff;
    color: #1a1a1a;
    padding: 16px 18px;
    border: 1px solid #e4e7ed;
    border-radius: 8px;
    margin: 0.6em 0;
    overflow-x: auto;
    overflow-y: auto;
    max-height: 300px;
    font-size: 14px;
    line-height: 1.8;
    max-width: 100%;
    white-space: pre-wrap;
    word-break: break-word;

    &::-webkit-scrollbar {
      width: 6px;
      height: 6px;
    }

    &::-webkit-scrollbar-track {
      background: #f5f7fa;
      border-radius: 3px;
    }

    &::-webkit-scrollbar-thumb {
      background: #dcdfe6;
      border-radius: 3px;

      &:hover {
        background: #c0c4cc;
      }
    }
  }

  code {
    background: #f3f4f6;
    color: #b45353;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    word-break: break-word;
  }

  pre code {
    color: inherit;
    background: none;
    padding: 0;
    word-break: normal;
    white-space: pre-wrap;
  }

  table {
    border-collapse: collapse;
    margin: 0.8em 0;
    width: 100%;
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  th,
  td {
    border: 1px solid #e5e7eb;
    padding: 8px 12px;
    text-align: left;
    white-space: nowrap;
    min-width: 60px;
  }

  th {
    background: #f9fafb;
    font-weight: 600;
  }

  tr:nth-child(even) {
    background: #fafbfc;
  }

  hr {
    border: none;
    border-top: 1px solid #e5e7eb;
    margin: 1em 0;
  }

  img {
    max-width: 100%;
    border-radius: 8px;
  }

  a {
    color: #409eff;
    text-decoration: none;
    word-break: break-word;
  }

  a:hover {
    text-decoration: underline;
  }
}
</style>
