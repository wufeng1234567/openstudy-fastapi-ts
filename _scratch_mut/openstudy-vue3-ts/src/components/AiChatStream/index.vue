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
        <!--
          思考过程（深度思考的推理文本）
          只有 ds-free 链路会产出 `type:'reasoning'` —— 后端 api 链路的 LangChain
          没有把 reasoning 取出来，所以这类消息可能整场都不出现。
        -->
        <div v-else-if="msg.type === 'reasoning'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <AgentReasoning :content="msg.content" :secs="msg.secs" />
        </div>
        <!--
          「等待中」占位（三点抖动）
          ⚠️ 这是 `type:'thinking'`，和上面的 `reasoning` **不是一回事**：
             · thinking  = 还没有内容时的占位，`content` 是一句状态文案（「正在理解你的需求…」）
             · reasoning = 深度思考的**推理正文**，可折叠
             两者都由 `useAgentChat` 维护，别合并。
        -->
        <div v-else-if="msg.type === 'thinking'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <div class="ai-loading-inline">
            <LoadingDots size="small" :label="msg.content || loadingText" />
          </div>
        </div>
        <!--
          Agent 过程提示（自我纠正 / 警告 / 错误）
          只有智能体链路会产出 type='agent_note'，别的调用方不会走到这个分支。
        -->
        <div v-else-if="msg.type === 'agent_note'" class="message-content">
          <div class="message-role agent-role">Agent</div>
          <slot name="agent-note" :message="msg" :index="idx">
            <div :class="['agent-note', 'note-' + (msg.noteKind || 'warning')]">
              <span class="note-icon">{{ noteIcon(msg.noteKind) }}</span>
              <span class="note-text">
                <template v-if="msg.noteKind === 'correct' && msg.attempt">
                  <span class="note-badge">自我纠正 #{{ msg.attempt }}</span>
                </template>
                {{ msg.content }}
              </span>
            </div>
          </slot>
        </div>
        <!-- 普通 assistant 消息 -->
        <div class="message-content" v-else-if="msg.role === 'assistant'">
          <div class="message-role agent-role">Agent</div>
          <!--
            ⚠️ 正文**不要**绑点击复制：回答里点一下（想看链接、想选中一段、误触）
            就会把整段复制走 + 弹「复制成功」，很打扰。复制只走下面这个按钮。
          -->
          <div class="message-text rendered-md" v-html="renderAgentMarkdown(msg.content)">
          </div>
          <el-button class="msg-copy-btn" size="small" text @click="copyText(msg.content)"
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
          <!-- 已发送的附件（图片可点击放大，文档显示扩展名） -->
          <ChatAttachmentList v-if="msg.attachments && msg.attachments.length" :items="msg.attachments" compact />
          <div v-if="msg.content" class="message-text">{{ msg.content }}</div>
        </div>
      </div>
    </div>

    <!-- 滚动按钮 -->
    <ScrollButton :scroll-container="messagesRef" :bottom="scrollButtonBottom" :right="16" />
    <!-- 输入区（底部组件：模式切换 / 附件 / 放大输入 / 工具栏 / 发送） -->
    <ChatInputArea v-model="inputContent" :mode="mode" :show-mode-switch="showModeSwitch"
      :show-new-session="showNewSession" :generating="isGenerating" :paused="isPaused" :placeholder="placeholder"
      :has-attachment="hasAttachment" :disabled="isGenerating || disabled"
      @update:mode="$emit('update:mode', $event)" @send="handleSend" @toggle-pause="$emit('toggle-pause')"
      @new-session="$emit('new-session')">
      <!-- 插槽名保持向后兼容：老调用方仍在用 `#input-header` / `#input-footer` -->
      <template v-if="$slots['input-header']" #attachments>
        <slot name="input-header"></slot>
      </template>
      <template v-if="$slots['input-footer']" #toolbar-extra>
        <slot name="input-footer"></slot>
      </template>
      <template v-if="$slots['input-toolbar-right']" #toolbar-right-before>
        <slot name="input-toolbar-right"></slot>
      </template>
    </ChatInputArea>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  watch,
  nextTick,
  computed,
  onMounted,
  onUnmounted,
  onActivated,
  onDeactivated
} from 'vue'
import { ElMessage } from 'element-plus'
import { renderAgentMarkdown } from '@/utils/markdown'
import LoadingDots from '@/components/LoadingDots/index.vue'
import AgentReasoning from '@/components/AgentReasoning/index.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import ChatAttachmentList from '@/components/ChatAttachmentList/index.vue'
import ChatInputArea from '@/components/ChatInputArea/index.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  isGenerating: { type: Boolean, default: false },
  isPaused: { type: Boolean, default: false },
  /**
   * 外部强制禁用输入区（与 `isGenerating` 是「或」的关系）。
   * 用它的场景：ds-free 自检运行中 —— 那时 DS 标签页被自检占用，
   * 用户敲进去也发不出去，不如直接置灰。
   */
  disabled: { type: Boolean, default: false },
  /** 是否处于「深度思考」模式（只影响等待文案） */
  thinking: { type: Boolean, default: false },
  /**
   * 是否已有待发送附件（图片/文件）。
   * DS 网页端允许「只发附件、不写文字」，所以有附件时即使输入框为空也应能发送。
   */
  hasAttachment: { type: Boolean, default: false },
  placeholder: { type: String, default: '输入消息...（Enter 发送，Ctrl+Enter 换行）' },
  /** 'agent' | 'chat'：底部输入区的模式标签与切换卡片用 */
  mode: { type: String, default: 'agent' },
  /** 是否显示模式切换入口（`@` 按钮，点开是模式卡片）；大屏智能体页固定智能体模式，可关掉 */
  showModeSwitch: { type: Boolean, default: true },
  /** 是否在底部工具栏（附件上传右边）显示「新建会话」按钮；由上层决定，收到点击后发 `new-session` */
  showNewSession: { type: Boolean, default: false },
  /**
   * 「回到底部」悬浮按钮距容器底部的高度。
   * 大屏智能体页把输入区做成了**悬浮卡片**（盖在消息流上），按钮默认位置会正好压在
   * 输入卡片上，所以要把它抬到卡片上方 —— 由那个页面传一个更大的值。
   */
  scrollButtonBottom: { type: Number, default: 16 }
})

// 等待文案：深度思考时显示「深度思考中」（配合共用的三点抖动组件）
const loadingText = computed(() => (props.thinking ? '深度思考中' : 'AI 思考中'))

const emit = defineEmits(['update:messages', 'send', 'stop', 'toggle-pause', 'update:mode', 'new-session'])

const inputContent = ref('')
const messagesRef = ref(null)
const isNearBottom = ref(true)

/**
 * 滚动过程中**实时**记下的位置（离开本页时要拿它还原，见 `leftStash`）
 *
 * ⚠️ 必须是「滚动事件里顺手记」，**不能**等到离开那一刻再去读 DOM —— 原因见 `leftStash`。
 */
const lastScrollTop = ref(0)

// 判断是否是最后一条空的 assistant 消息（用于显示 loading 动画）
const isLastAssistantEmpty = (idx) => {
  // 从当前位置往前找，看是否是最后一条 assistant 消息
  for (let i = props.messages.length - 1; i > idx; i--) {
    const t = props.messages[i].type
    // 工具卡片与过程提示都不是「正文」，不算数（agent_note 由智能体链路产出）
    if (
      props.messages[i].role === 'assistant' &&
      t !== 'tool_confirm' &&
      t !== 'tool_result' &&
      t !== 'agent_note'
    ) {
      return false
    }
  }
  return true
}

/** agent_note 的图标（自我纠正 / 警告 / 错误） */
const noteIcon = (kind) => {
  if (kind === 'correct') return '↻'
  if (kind === 'error') return '✕'
  return '!'
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

/**
 * 发送（由底部组件触发）
 *
 * 输入内容现在由 `ChatInputArea` 持有并负责清空，这里只做最后一道校验后向上抛。
 */
const handleSend = (payload?: { content?: string }) => {
  if (props.isGenerating) return
  const content = (payload?.content ?? '').trim()
  // 允许纯附件发送（与 DS 网页端一致）：有附件时 content 可以为空
  if (!content && !props.hasAttachment) return
  emit('send', { content })
}

// 检测是否在底部附近（50px 内）
const checkNearBottom = () => {
  if (!messagesRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  // 顺手把当前位置记下来：离开本页（keep-alive 收起）时用它还原 ——
  // 那一刻 DOM 已经被摘出文档，再读 scrollTop 只会得到 0（见 leftStash 的注释）
  lastScrollTop.value = scrollTop
  isNearBottom.value = scrollHeight - scrollTop - clientHeight < 50
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

/** 等一帧（等布局真正算出来） */
const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

/**
 * 「进页面 / 切会话」时**无条件**落到最新一条（不管当前视口在哪儿）
 *
 * ⚠️⚠️ 为什么必须等两帧、还要滚两次 —— 这是「每次进来都停在最上面」那条 bug 的根因：
 *    挂载当刻父级 flex 还没算出 `.chat-messages` 的 `clientHeight`，此时
 *    `scrollHeight ≈ clientHeight`，`scrollTop = scrollHeight` 会被**钳成 0**；
 *    更糟的是**不会触发 scroll 事件**，所以 `isNearBottom` 一直是 `true`（"看起来在底部"），
 *    后面也没有任何一次纠正 —— 页面就永远停在最上面。
 *    第一帧后布局出来了（高度、滚动条），再滚一次才真的到底；
 *    第二条 rAF 是为了让最后一条的 markdown / 卡片把高度撑完（它可能是这一帧才长出来的）。
 *
 * ⚠️ 这里**刻意不看 `isNearBottom`**：进入页面时视口本来就在最上面，那个条件永远不成立
 *    —— 这正是当初漏掉整条路径的原因。它是一次性的「定位」动作，不是「跟随」动作。
 */
const pinToLatest = async () => {
  await nextTick()
  await nextFrame()
  if (!messagesRef.value) return
  // 程序化落底之后，跟随状态也要一起回到「跟随中」（否则流式内容来了不会继续跟）
  isNearBottom.value = true
  messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  await nextFrame()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

/**
 * 这一份清单有没有**已经落过底**
 *
 * 一次性：加载完历史/切完会话落一次，之后交给「跟随」那套（`autoScrollIfNearBottom`）。
 * 清单被清空（新对话 / 切会话的 `reset()`）时复位 —— 下一次加载要重新落一次底。
 */
const pinnedToLatest = ref(false)

/**
 * 离开本页时留下的滚动现场（`null` = 还没离开过本页）
 *
 * ⚠️ 存的是**滚动事件里实时记下来的**值，不是 `onDeactivated` 当刻读的 DOM：
 *    keep-alive 收起是「先把 DOM 摘出文档、再回调 deactivated」，摘出去的滚动容器读
 *    `scrollTop` 只会得到 0 —— 拿它当现场，切回来就必然停在**最上面**。
 *
 * ⚠️ `atBottom` 得一起记：离开期间可能有新内容追加（例如用户切走时那一轮还在跑），
 *    硬还原旧像素等于**停在旧消息上**、看起来像「回来没在底部」。
 *    贴底离开的 → 回来继续贴底；在读旧消息的 → 严格还原像素。
 */
const leftStash = ref<{ top: number; atBottom: boolean } | null>(null)

/**
 * 把滚动位置还原到**离开本页那一刻**的像素
 *
 * ⚠️ 与 `pinToLatest` 是同一个坑：`onActivated` 跑的时候 DOM 刚被 keep-alive 塞回文档，
 *    滚动容器的高度/滚动条要这一帧之后才算得出来 —— 当刻写 `scrollTop` 会被**钳成 0**。
 *    所以照样要等两帧；第二帧再写一次，是为了校正「最后一条的 markdown / 卡片是在
 *    这一帧才把高度撑完」。
 */
const restoreScrollTop = async (top: number) => {
  await nextTick()
  await nextFrame()
  if (!messagesRef.value) return
  messagesRef.value.scrollTop = top
  await nextFrame()
  if (messagesRef.value) messagesRef.value.scrollTop = top
  // 还原之后把「跟随中」状态与**真实**位置对齐，否则之后的流式内容会按老状态乱跟
  checkNearBottom()
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
  // 挂载时**已经**有一份历史（父级在更早的生命周期里就填好了 `messages`）：
  // 此时 `messages.length` 的 watch **不会触发**（没有「变化」），只靠它接不住。
  if (props.messages.length) pinToLatest()
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', checkNearBottom)
  }
})

/**
 * keep-alive 把本页收起：记下现场
 *
 * ⚠️ 这里**只读内存里实时记的值**，一个 DOM 都不碰 —— 此刻容器已经被摘出文档，
 *    读 `scrollTop` 拿到的是 0（见 `leftStash` 的注释）。
 */
onDeactivated(() => {
  leftStash.value = { top: lastScrollTop.value, atBottom: isNearBottom.value }
})

/**
 * keep-alive 把本页塞回来：还原离开时的滚动位置
 *
 * ⚠️ **首次挂载时这个钩子也会跟着 `onMounted` 跑一次** —— 那时 `leftStash` 还是 `null`，
 *    直接返回：首屏的语义是「落到最新一条」（交给 `onMounted` / `length` 的 watch），
 *    不是「还原」；两边都去写 `scrollTop` 只会互相打断。
 */
onActivated(() => {
  if (!leftStash.value) return
  const { top, atBottom } = leftStash.value
  if (atBottom) {
    // 贴底离开的：离开期间追加的新内容不该被「还原」到旧像素上 —— 底才是他离开时的位置
    pinToLatest()
    return
  }
  restoreScrollTop(top)
})

// 新消息到来时：第一次拿到非空清单 → 无条件落底；之后 → 在底部附近才跟随
watch(() => props.messages.length, (n) => {
  if (n === 0) {
    // 清空 = 新对话 / 切会话：复位，让下一次加载重新落到底
    pinnedToLatest.value = false
    return
  }
  if (!pinnedToLatest.value) {
    // ⚠️ 这里**必须**走 `pinToLatest`（无条件），不能走 `autoScrollIfNearBottom`：
    //    进入页面时视口就在最上面 → `isNearBottom` 那个条件恰好不成立 → 一次都不滚。
    pinnedToLatest.value = true
    pinToLatest()
    return
  }
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
  /*
   * ⚠️ `min-height: 0` 这行不能删（少了它就是「输入框被挤出视线」那个 bug）。
   * flex item 的 `min-height` 默认是 `auto` = 内容高度，于是 `flex: 1` 形同虚设：
   * 消息一多，这一块会**跟着内容长高**、`overflow-y` 永远不触发（clientHeight ===
   * scrollHeight），滚动条跑到整份文档上。显式归零后它才会被父级压住、自己出滚动条。
   */
  min-height: 0;
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

/* 工具卡片 / 过程提示属于「结构化内容」，比正文更需要横向空间（正文仍保持 75%） */
.message.msg-tool_result .message-content,
.message.msg-agent_note .message-content {
  max-width: 92%;
}

/*
 * 工具结果卡片是**三层信息的结构化卡片**（状态+结果 · 工具动作 · 详情），不是聊天气泡，
 * 所以给它比正文（75%）更宽的上限 —— 但**不撑满**，让它跟着内容走。
 *
 * 踩过的两个极端，都别再回去：
 *   · 不给宽度（纯 fit-content）：内容一短就缩成又窄又高的一条（实测 147px 宽 / 5 行高），
 *     不同工具之间宽度还会来回跳；
 *   · 给 `width: 100%`：宽抽屉里被拉成一条空荡荡的长条 ——「共 30 道题目」几个字
 *     占着 686px 的卡，右边一整片空白。
 *
 * 折中：`min-width` 兜住下限（窄屏用 `100%` 兜底，永远不溢出），上限 720px，
 * 中间由内容自己决定；展开详情时 `.at-body` 会把卡片自然撑开。
 */
.message.msg-tool_result .message-content {
  min-width: min(240px, 100%);
  max-width: min(92%, 720px);
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

/* ------------------------------------------------------------------
   Agent 过程提示（type='agent_note'）：自我纠正 / 警告 / 错误
   三态只用左边框 + 底色区分，避免在消息流里刷出一堆彩色块
   ------------------------------------------------------------------ */
.agent-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 12px;
  border-radius: 8px;
  border-left: 3px solid #cbd5e1;
  background: #f8fafc;
  font-size: 12.5px;
  line-height: 1.65;
  color: #4a5a72;
  word-break: break-word;
}

.note-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 1px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: #94a3b8;
}

.note-text {
  min-width: 0;
}

.agent-note.note-correct {
  border-left-color: #fb923c;
  background: #fff7ed;
  color: #9a3412;
}

.agent-note.note-correct .note-icon {
  background: #f97316;
}

.agent-note.note-warning {
  border-left-color: #fbbf24;
  background: #fffbeb;
  color: #b45309;
}

.agent-note.note-warning .note-icon {
  background: #f59e0b;
}

.agent-note.note-error {
  border-left-color: #f87171;
  background: #fef2f2;
  color: #b91c1c;
}

.agent-note.note-error .note-icon {
  background: #ef4444;
}

.note-badge {
  display: inline-block;
  margin-right: 6px;
  padding: 0 7px;
  border-radius: 9px;
  background: #f97316;
  color: #fff;
  font-size: 11px;
  line-height: 17px;
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

/*
 * 输入区样式已迁到 `components/ChatInputArea/index.vue`
 *（类名保持不变：`.chat-input-area` / `.input-box` / `.input-header` / `.input-bottom` / `.send-btn`，
 *  所以调用方（含 `views/front/agent/chat.vue`）针对这些类的样式覆盖继续有效。）
 */
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
  /* 给右下角「复制」按钮留位，免得正文最后一行被它压住 */
  padding-bottom: 20px;
  /*
   * ⚠️ 这里**不要**再写 `cursor: pointer`（随「点正文即复制」一起删掉了）。
   *    pointer 是「这里能点」的暗示，会让人以为还能点；去掉后正文恢复默认光标，
   *    选中文字 / 点链接的手感也才对。
   */
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
