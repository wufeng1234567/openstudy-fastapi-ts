<template>
  <div class="ai-assistant">
    <!-- 悬浮按钮 -->
    <div class="float-btn" :style="btnStyle" title="OpenStudy 助手" @mousedown="startDrag" @click="onFloatClick">
      <el-icon :size="24">
        <ChatDotRound />
      </el-icon>
    </div>

    <!-- 抽屉面板 -->
    <el-drawer v-model="visible" direction="rtl" :size="drawerSize + 'px'" :with-header="false"
      :close-on-click-modal="true">
      <!-- 拖拽调整宽度手柄 -->
      <div class="drawer-resize-handle" @mousedown.stop="startDrawerResize"></div>

      <div class="assistant-container">
        <!-- 头部 -->
        <div class="assistant-header">
          <div class="header-left">
            <el-icon :size="18">
              <ChatDotRound />
            </el-icon>
            <span>OpenStudy 助手</span>
          </div>
          <div class="header-right">
            <AiModelSelector v-if="activeTab === 'chat'" v-model="selectedProvider" width="140px" />
            <span v-if="activeTab === 'chat'" class="action-icon" :class="{ active: sessionListVisible }" title="历史会话"
              @mousedown.stop @click="toggleSessionList">
              <el-icon>
                <Clock />
              </el-icon>
            </span>
            <span v-if="activeTab === 'chat'" class="action-icon" title="新建会话" @click="newSession">
              <el-icon>
                <Plus />
              </el-icon>
            </span>
            <span class="action-icon close-icon" title="关闭" @click="visible = false">
              <el-icon>
                <Close />
              </el-icon>
            </span>
          </div>
        </div>

        <!-- 历史会话列表（悬浮面板） -->
        <div v-if="sessionListVisible" ref="sessionPopoverRef" class="session-popover">
          <div class="session-popover-header">
            <span>历史会话</span>
            <span class="session-count">{{ sessions.length }}</span>
          </div>
          <div class="session-list" v-loading="sessionsLoading">
            <div v-for="s in sessions" :key="s.sessionId"
              :class="['session-item', { active: s.sessionId === currentSessionId }]" @click="switchSession(s)">
              <div class="session-title">{{ s.title || '新会话' }}</div>
              <div class="session-meta">
                <span>{{ formatSessionTime(s.updatedAt) }}</span>
                <span>{{ s.messageCount || 0 }} 条</span>
              </div>
              <span class="session-delete" title="删除会话" @click.stop="removeSession(s)">
                <el-icon>
                  <Delete />
                </el-icon>
              </span>
            </div>
            <el-empty v-if="!sessionsLoading && sessions.length === 0" description="暂无历史会话" :image-size="50" />
          </div>
        </div>

        <!-- Tab 切换：对话 / 我的题库 -->
        <div class="assistant-tabs">
          <div :class="['tab-item', { active: activeTab === 'chat' }]"
            @click="activeTab = 'chat'; sessionListVisible = false">
            <el-icon>
              <ChatDotRound />
            </el-icon>
            <span>对话</span>
          </div>
          <div :class="['tab-item', { active: activeTab === 'banks' }]" @click="switchToBanks">
            <el-icon>
              <FolderOpened />
            </el-icon>
            <span>我的题库</span>
          </div>
        </div>

        <!-- 内容区 -->
        <div class="assistant-body">
          <!-- 我的题库 -->
          <div v-if="activeTab === 'banks'" class="banks-panel">
            <el-input v-model="bankKeyword" placeholder="搜索题库名称或科目" clearable size="small" />
            <div class="bank-list" v-loading="bankLoading">
              <div v-for="bank in filteredBanks" :key="bank.id" class="bank-item" @click="jumpToBank(bank.id)">
                <div class="bank-info">
                  <div class="bank-name">{{ bank.bankName }}</div>
                  <div class="bank-meta">
                    <span>{{ bank.subject || '未分类' }}</span>
                    <span>{{ bank.totalQuestions || 0 }} 题</span>
                  </div>
                </div>
                <el-icon class="bank-arrow">
                  <ArrowRight />
                </el-icon>
              </div>
              <el-empty v-if="!bankLoading && filteredBanks.length === 0" description="暂无题库" :image-size="60" />
            </div>
          </div>

          <!-- 对话 -->
          <AiChatStream v-else v-model:messages="messages" :is-generating="isGenerating" :is-paused="isPaused"
            :thinking="thinkingEnabled" placeholder="输入消息...（Enter 发送）" @send="handleChatSend"
            @stop="stopGeneration" @toggle-pause="stream.togglePause()">
            <!-- 深度思考开关（输入框下方工具行，不挤压文本域，也不影响上方聊天区） -->
            <template #input-footer>
              <AiThinkingToggle v-model="thinkingEnabled" :disabled="isGenerating" />
            </template>
            <template #empty>
              <div class="welcome-card">
                <div class="welcome-icon">🤖</div>
                <div class="welcome-title">你好，我是 OpenStudy 助手</div>
                <div class="welcome-desc">开源、低成本、低门槛的 AI 学习平台</div>
                <div class="quick-actions">
                  <div class="quick-item" @click="sendQuickMessage('介绍一下 OpenStudy 平台')">
                    <el-icon>
                      <InfoFilled />
                    </el-icon>
                    <span>介绍平台</span>
                  </div>
                  <div class="quick-item" @click="switchToBanks">
                    <el-icon>
                      <FolderOpened />
                    </el-icon>
                    <span>我的题库</span>
                  </div>
                  <div class="quick-item" @click="sendQuickMessage('如何创建题库？')">
                    <el-icon>
                      <QuestionFilled />
                    </el-icon>
                    <span>创建题库</span>
                  </div>
                  <div class="quick-item" @click="sendQuickMessage('怎么刷题？')">
                    <el-icon>
                      <EditPen />
                    </el-icon>
                    <span>刷题指南</span>
                  </div>
                </div>
              </div>
            </template>
          </AiChatStream>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound, Close, FolderOpened, ArrowRight,
  InfoFilled, QuestionFilled, EditPen, Delete, Clock, Plus
} from '@element-plus/icons-vue'
import {
  assistantStream, getConversationHistory,
  listSessions, createSession, deleteSession
} from '@/api/ai/ai'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { useStreamGeneration } from '@/composables/useStreamGeneration'
import AiChatStream from '@/components/AiChatStream/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AiThinkingToggle from '@/components/AiThinkingToggle/index.vue'
import useUserStore from '@/store/modules/user'

defineOptions({ name: 'AiAssistant' })

const router = useRouter()
const userStore = useUserStore()
const userId = computed(() => userStore.id || userStore.userId)

const visible = ref(false)
const activeTab = ref<'chat' | 'banks'>('chat')
const selectedProvider = ref('')

// ===================== 深度思考开关（记忆用户偏好） =====================
const THINKING_KEY = 'openstudy_ai_thinking'
const thinkingEnabled = ref(localStorage.getItem(THINKING_KEY) === '1')
watch(thinkingEnabled, (val) => {
  localStorage.setItem(THINKING_KEY, val ? '1' : '0')
})

/* ===================== 悬浮按钮拖拽 ===================== */
const isDragging = ref(false)
const dragStart = { x: 0, y: 0 }
const btnPos = ref({ x: 0, y: 0 })
const btnStyle = ref<Record<string, string>>({})
let lastDragEndAt = 0
let dragMoved = false
let dragStartClient = { x: 0, y: 0 }

const updateBtnStyle = (transition = '') => {
  btnStyle.value = {
    left: btnPos.value.x + 'px',
    top: btnPos.value.y + 'px',
    right: 'auto',
    bottom: 'auto',
    ...(transition ? { transition } : {})
  }
}

const initPosition = () => {
  btnPos.value = { x: window.innerWidth - 76, y: window.innerHeight - 130 }
  updateBtnStyle()
}

const startDrag = (e: MouseEvent) => {
  isDragging.value = true
  dragMoved = false
  dragStartClient = { x: e.clientX, y: e.clientY }
  dragStart.x = e.clientX - btnPos.value.x
  dragStart.y = e.clientY - btnPos.value.y
  document.body.style.userSelect = 'none'
}

const onDrag = (e: MouseEvent) => {
  if (!isDragging.value) return
  // 位移小于阈值不算拖拽，避免“鼠标轻微抖动导致点击被吞掉”
  if (!dragMoved) {
    const dx = Math.abs(e.clientX - dragStartClient.x)
    const dy = Math.abs(e.clientY - dragStartClient.y)
    if (dx < 4 && dy < 4) return
    dragMoved = true
  }
  e.preventDefault()
  const size = 52
  btnPos.value = {
    x: Math.max(10, Math.min(window.innerWidth - size - 10, e.clientX - dragStart.x)),
    y: Math.max(10, Math.min(window.innerHeight - size - 10, e.clientY - dragStart.y))
  }
  updateBtnStyle('none')
}

const stopDrag = () => {
  // 只有真正拖动过，才做吸边并标记“刚拖拽过”（否则会把单击也当成拖拽）
  if (isDragging.value && dragMoved) {
    const size = 52
    const centerX = btnPos.value.x + size / 2
    btnPos.value.x = centerX < window.innerWidth / 2 ? 20 : window.innerWidth - size - 20
    updateBtnStyle('left 0.25s ease')
    lastDragEndAt = Date.now()
  }
  isDragging.value = false
  dragMoved = false
  document.body.style.userSelect = ''
}

const onFloatClick = () => {
  // 刚拖拽过就不触发“打开抽屉”
  if (Date.now() - lastDragEndAt < 300) return
  visible.value = true
}

/* ===================== 抽屉宽度拖拽 ===================== */
const DRAWER_SIZE_KEY = 'openstudy_ai_drawer_size'
const DRAWER_MIN = 320
const DRAWER_MAX = 800
const drawerSize = ref(Number(localStorage.getItem(DRAWER_SIZE_KEY)) || 420)

let isResizingDrawer = false
let resizeStartX = 0
let resizeStartSize = 0
let resizeRaf = 0
let resizeNextSize = drawerSize.value

const getDrawerEl = () =>
  (document.querySelector('.ai-assistant .el-drawer') ||
    // 兜底：万一抽屉被 teleport 出组件树
    document.querySelector('.el-drawer.rtl')) as HTMLElement | null

/**
 * el-drawer 自带 `transition: all .3s`，拖拽时每次改宽度都会被动画“拖住”，
 * 表现就是跟手性很差。这里在拖拽期间关掉过渡（顺带加上 el-drawer 官方的 is-dragging 类），
 * 结束后再恢复。
 */
const setDrawerTransition = (enabled: boolean) => {
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

const startDrawerResize = (e: MouseEvent) => {
  e.preventDefault()
  e.stopPropagation()
  isResizingDrawer = true
  resizeStartX = e.clientX
  resizeStartSize = drawerSize.value
  resizeNextSize = drawerSize.value
  setDrawerTransition(false)
  document.addEventListener('mousemove', onDrawerResize, { passive: false })
  document.addEventListener('mouseup', stopDrawerResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

const onDrawerResize = (e: MouseEvent) => {
  if (!isResizingDrawer) return
  e.preventDefault()
  const delta = resizeStartX - e.clientX
  resizeNextSize = Math.max(DRAWER_MIN, Math.min(DRAWER_MAX, resizeStartSize + delta))
  // rAF 节流：高频 mousemove 每帧只写一次宽度，避免重复重排
  if (resizeRaf) return
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = 0
    drawerSize.value = resizeNextSize
  })
}

const stopDrawerResize = () => {
  if (!isResizingDrawer) return
  isResizingDrawer = false
  if (resizeRaf) {
    cancelAnimationFrame(resizeRaf)
    resizeRaf = 0
  }
  // 补上最后一帧（若 rAF 还没执行）
  drawerSize.value = resizeNextSize
  document.removeEventListener('mousemove', onDrawerResize)
  document.removeEventListener('mouseup', stopDrawerResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  localStorage.setItem(DRAWER_SIZE_KEY, String(resizeNextSize))
  // 等 Vue 把最终宽度写入 DOM 后再恢复过渡，避免收尾又播放一次 0.3s 动画
  nextTick(() => {
    if (!isResizingDrawer) setDrawerTransition(true)
  })
}

/* ===================== 我的题库 ===================== */
const myBanks = ref<any[]>([])
const bankLoading = ref(false)
const bankKeyword = ref('')

const loadMyBanks = async () => {
  if (bankLoading.value) return
  bankLoading.value = true
  try {
    const res: any = await listMyQuestionBank()
    if (res.code === 200) myBanks.value = res.data || []
  } catch (e) {
    console.error('加载题库失败:', e)
  } finally {
    bankLoading.value = false
  }
}

const switchToBanks = () => {
  activeTab.value = 'banks'
  sessionListVisible.value = false
  if (myBanks.value.length === 0) loadMyBanks()
}

const filteredBanks = computed(() => {
  const kw = bankKeyword.value.trim().toLowerCase()
  if (!kw) return myBanks.value
  return myBanks.value.filter((b: any) =>
    (b.bankName || '').toLowerCase().includes(kw) || (b.subject || '').toLowerCase().includes(kw)
  )
})

const jumpToBank = (bankId: number | string) => {
  visible.value = false
  router.push(`/front/studio/create?bankId=${bankId}`)
}

/* ===================== 会话管理 ===================== */
const currentSessionId = ref('')
const sessions = ref<any[]>([])
const sessionsLoading = ref(false)
const sessionListVisible = ref(false)
const sessionPopoverRef = ref<HTMLElement | null>(null)

const formatSessionTime = (ts?: number) => {
  if (!ts) return ''
  const d = new Date(ts)
  const diff = Date.now() - d.getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${d.getMonth() + 1}-${d.getDate()} ${hh}:${mm}`
}

const loadSessions = async () => {
  sessionsLoading.value = true
  try {
    const res: any = await listSessions(userId.value)
    if (res.code === 200 && Array.isArray(res.data)) sessions.value = res.data
  } catch (e) {
    console.error('加载会话列表失败:', e)
  } finally {
    sessionsLoading.value = false
  }
}

const toggleSessionList = () => {
  sessionListVisible.value = !sessionListVisible.value
  if (sessionListVisible.value) loadSessions()
}

const onDocMousedown = (e: MouseEvent) => {
  if (!sessionListVisible.value) return
  const el = sessionPopoverRef.value
  if (el && !el.contains(e.target as Node)) sessionListVisible.value = false
}

/* ===================== 对话 ===================== */
const messages = reactive<any[]>([])
let aiMsgIndex = 0

const stream = useStreamGeneration({
  onChunk: (fullContent: string) => {
    if (messages[aiMsgIndex]) messages[aiMsgIndex].content = fullContent
  },
  onComplete: () => {
    // 首条消息发出后后端才建立会话，这里刷新列表让新会话出现
    loadSessions()
  },
  onError: (error: any) => {
    console.error('AI 助手请求失败:', error)
    if (messages[aiMsgIndex]) messages[aiMsgIndex].content = '抱歉，发送失败，请重试。'
  }
})

const isGenerating = computed(() => stream.isGenerating.value)
const isPaused = computed(() => stream.isPaused.value)

const loadMessages = async () => {
  messages.length = 0
  aiMsgIndex = 0
  if (!currentSessionId.value) return
  try {
    const res: any = await getConversationHistory(currentSessionId.value, userId.value)
    if (res.code === 200 && Array.isArray(res.data)) messages.push(...res.data)
  } catch (e) {
    console.error('加载会话消息失败:', e)
  }
}

// 新建会话：后端立即落一条「新会话」到列表（首条消息后标题自动替换）
const newSession = async () => {
  sessionListVisible.value = false
  if (stream.isGenerating.value) stream.abort()
  // 当前会话还是空的就不再新建，避免堆一堆空会话
  if (currentSessionId.value && messages.length === 0) {
    await loadSessions()
    return
  }
  try {
    const res: any = await createSession(userId.value)
    currentSessionId.value = res?.data?.sessionId || `asst_${Date.now()}`
  } catch (e) {
    currentSessionId.value = `asst_${Date.now()}`
  }
  messages.length = 0
  aiMsgIndex = 0
  await loadSessions()
}

// 切换到历史会话，继续聊天
const switchSession = async (s: any) => {
  sessionListVisible.value = false
  if (!s?.sessionId || s.sessionId === currentSessionId.value) return
  if (stream.isGenerating.value) return
  currentSessionId.value = s.sessionId
  await loadMessages()
}

const removeSession = async (s: any) => {
  try {
    await deleteSession(s.sessionId, userId.value)
  } catch (e) {
    console.error('删除会话失败:', e)
  }
  sessions.value = sessions.value.filter((x: any) => x.sessionId !== s.sessionId)
  if (s.sessionId === currentSessionId.value) {
    // 先清空当前会话 id，避免 newSession 的「空会话复用」判断命中已删除的会话
    currentSessionId.value = ''
    messages.length = 0
    await newSession()
  }
}

const handleChatSend = ({ content }: { content: string }) => {
  if (!content || stream.isGenerating.value) return
  if (!currentSessionId.value) currentSessionId.value = `asst_${Date.now()}`
  messages.push({ role: 'user', content })
  aiMsgIndex = messages.length
  messages.push({ role: 'assistant', content: '' })
  stream.start((handleChunk, handleComplete, handleError, signal) => {
    assistantStream(
      content,
      handleChunk,
      handleComplete,
      handleError,
      signal,
      selectedProvider.value || undefined,
      userId.value,
      currentSessionId.value,
      thinkingEnabled.value
    )
  })
}

const sendQuickMessage = (text: string) => {
  activeTab.value = 'chat'
  handleChatSend({ content: text })
}

const stopGeneration = () => stream.abort()

/* ===================== 生命周期 ===================== */
onMounted(async () => {
  initPosition()
  await loadSessions()
  if (sessions.value.length > 0) {
    // 默认打开最近一次会话
    currentSessionId.value = sessions.value[0].sessionId
    await loadMessages()
  } else {
    await newSession()
  }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
  window.addEventListener('resize', initPosition)
  document.addEventListener('mousedown', onDocMousedown)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
  window.removeEventListener('resize', initPosition)
  document.removeEventListener('mousedown', onDocMousedown)
  stopDrawerResize()
})
</script>

<style scoped lang="scss">
.ai-assistant {

  /* 抽屉内容铺满，去掉 Element Plus 默认内边距 */
  :deep(.el-drawer) {
    overflow: visible;
  }

  /* 拖拽调宽时：关掉内部交互与重绘，进一步保证跟手（Element Plus 官方也有 is-dragging 约定） */
  :deep(.el-drawer.is-dragging) {
    user-select: none;

    .assistant-container {
      pointer-events: none;
    }
  }

  :deep(.el-drawer__body) {
    position: relative;
    overflow: hidden;
    padding: 0;
  }

  /* ========== 悬浮按钮 ========== */
  .float-btn {
    position: fixed;
    left: auto;
    right: 24px;
    bottom: 80px;
    width: 52px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(0, 0, 0, 0.06);
    color: #4b5563;
    cursor: grab;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    transition: box-shadow 0.2s ease, color 0.2s ease;
    z-index: 1000;
    user-select: none;

    &:hover {
      background: #fff;
      color: #1f2937;
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.14);
    }

    &:active {
      cursor: grabbing;
    }
  }

  /* ========== 抽屉宽度拖拽手柄 ========== */
  .drawer-resize-handle {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 10px;
    cursor: col-resize;
    z-index: 10;

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

  /* ========== 整体容器 ========== */
  .assistant-container {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #fff;
  }

  /* ========== 头部 ========== */
  .assistant-header {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 14px 16px 10px;

    .header-left {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 600;
      color: #1f2937;
      white-space: nowrap;
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;

      .action-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        cursor: pointer;
        color: #909399;
        font-size: 16px;
        transition: color 0.2s ease;

        &:hover,
        &.active {
          color: #409eff;
        }
      }

      .close-icon:hover {
        color: #303133;
      }
    }
  }

  /* ========== 历史会话悬浮面板 ========== */
  .session-popover {
    position: absolute;
    top: 52px;
    right: 12px;
    width: 264px;
    max-height: 62%;
    display: flex;
    flex-direction: column;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    z-index: 30;
    overflow: hidden;

    .session-popover-header {
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 12px;
      font-size: 13px;
      font-weight: 600;
      color: #1f2937;
      border-bottom: 1px solid #e5e7eb;

      .session-count {
        font-weight: 400;
        color: #9ca3af;
      }
    }

    .session-list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 6px;
    }

    .session-item {
      position: relative;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.2s ease;

      &:hover {
        background: #f3f4f6;
      }

      &.active {
        background: #ecf5ff;
      }

      .session-title {
        padding-right: 20px;
        font-size: 13px;
        color: #1f2937;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .session-meta {
        margin-top: 3px;
        display: flex;
        gap: 10px;
        font-size: 11px;
        color: #9ca3af;
      }

      .session-delete {
        position: absolute;
        top: 8px;
        right: 6px;
        display: none;
        color: #9ca3af;
      }

      &:hover .session-delete {
        display: inline-flex;
      }

      .session-delete:hover {
        color: #f56c6c;
      }
    }
  }

  /* ========== Tabs ========== */
  .assistant-tabs {
    flex-shrink: 0;
    display: flex;
    gap: 4px;
    padding: 0 16px;
    border-bottom: 1px solid #e5e7eb;

    .tab-item {
      display: flex;
      align-items: center;
      gap: 5px;
      padding: 8px 14px;
      font-size: 13px;
      color: #6b7280;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;

      &:hover {
        color: #409eff;
      }

      &.active {
        color: #409eff;
        border-bottom-color: #409eff;
        font-weight: 600;
      }
    }
  }

  /* ========== 内容区 ========== */
  .assistant-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  /* ========== 我的题库 ========== */
  .banks-panel {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px;

    .bank-list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
    }

    .bank-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 10px 12px;
      margin-bottom: 8px;
      background: #fafafa;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        background: #f0f7ff;
        border-color: #c6e2ff;
      }

      .bank-name {
        margin-bottom: 4px;
        font-size: 14px;
        font-weight: 600;
        color: #1f2937;
      }

      .bank-meta {
        display: flex;
        gap: 10px;
        font-size: 12px;
        color: #9ca3af;
      }

      .bank-arrow {
        flex-shrink: 0;
        color: #c0c4cc;
      }
    }
  }

  /* ========== 欢迎卡片 ========== */
  .welcome-card {
    padding: 20px 8px;
    text-align: center;

    .welcome-icon {
      font-size: 40px;
    }

    .welcome-title {
      margin-top: 10px;
      font-size: 16px;
      font-weight: 600;
      color: #1f2937;
    }

    .welcome-desc {
      margin-top: 6px;
      font-size: 13px;
      color: #9ca3af;
    }

    .quick-actions {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .quick-item {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px;
      font-size: 13px;
      color: #4b5563;
      background: #f8f9fa;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      cursor: pointer;
      transition: all 0.2s ease;

      &:hover {
        color: #409eff;
        border-color: #c6e2ff;
        background: #ecf5ff;
      }
    }
  }
}
</style>
