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
            <!--
              标题**跟着模式实时变**（对齐 sp3）：智能体 → `OpenStudy-Agent`、聊天 → `OpenStudy-Chat`。
              所以底部工具栏的 `@` 旁边不再挂模式文字标签（那个不好看），模式信息集中在这里表达。
            -->
            <span class="header-title">{{ headerTitle }}</span>
          </div>
          <div class="header-right">
            <AiModelSelector v-if="activeTab === 'chat'" v-model="selectedModel" scene="chat" width="140px" />
            <!-- 「新建会话」已移到输入区工具栏（附件上传右边）；这里只留历史会话 / 关闭 -->

            <span v-if="activeTab === 'chat'" class="action-icon" :class="{ active: sessionListVisible }" title="历史会话"
              @mousedown.stop @click="toggleSessionList">
              <el-icon>
                <Clock />
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
          <div :class="['tab-item', { active: activeTab === 'knowledge' }]" @click="switchToKnowledge">
            <el-icon>
              <Collection />
            </el-icon>
            <span>我的知识库</span>
          </div>
          <!-- 自检：仅开发环境。跑的是 ds-free 端到端用例，见 DfSelfCheckPanel -->
          <!-- 注：不能把条件写成 `import.meta.env.DEV`（Vue 模板编译器不认），只能用 isDev。
               代价是这个 tab 的 DOM 与图标引用会留在生产包里（永远不渲染，因为 isDev 恒 false），
               约两百字节 —— 真正的大头（面板组件 + 用例表）是动态 import，已被完整摇掉。 -->
          <div v-if="isDev" :class="['tab-item', { active: activeTab === 'self' }]"
            @click="switchToSelf">
            <el-icon>
              <Tools />
            </el-icon>
            <span>自检</span>
            <span v-if="selfCheckRunning" class="tab-dot" title="正在跑"></span>
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
          <!-- 我的知识库 -->
          <!-- 与智能体页右侧抽屉共用同一个面板组件，功能完全一致 -->
          <div v-else-if="activeTab === 'knowledge'" class="knowledge-panel">
            <KnowledgeBasePanel ref="kbPanelRef" />
          </div>

          <!-- 自检（仅开发环境） -->
          <DfSelfCheckPanel v-else-if="activeTab === 'self'" />

          <!-- 对话 -->
          <AiChatStream v-else :messages="agentMode ? agentMessages : messages"
            :is-generating="agentMode ? agentGenerating : isGenerating" :is-paused="isPaused"
            :disabled="selfCheckRunning"
            :thinking="thinkingEnabled" :has-attachment="attachmentCount > 0" placeholder="输入消息...（Enter 发送）"
            :mode="chatModeValue" @update:mode="onModeChange" show-new-session
            @send="handleChatSend" @stop="stopGeneration" @toggle-pause="onTogglePause" @new-session="newSession">
            <!-- 工具调用卡片（智能体模式） -->
            <template v-if="agentMode" #tool-result="{ message }">
              <AgentToolResult :tool="message.tool" :action="message.action" :content="message.content"
                :detail="message.detail" :status="message.status" :errors="message.errors"
                :params="message.params" :data="message.data" />
            </template>
            <!-- 写操作二次确认卡片 -->
            <template v-if="agentMode" #tool-confirm="{ message }">
              <AgentConfirmCard :tool="message.tool" :action="message.action" :content="message.content"
                :status="message.status" :destructive="message.destructive" :preview="message.preview"
                @resolve="(ok) => agentResolveConfirm(message.confirmId, ok)" />
            </template>
            <!-- 输入框上方：待发送附件预览（对齐 DS 网页端，可点击放大、可单独删除） -->
            <template #input-header>
              <ChatAttachmentList :items="attachmentItems" removable :disabled="agentMode ? agentGenerating : isGenerating"
                @remove="removeAttachment" />
            </template>
            <!-- 工具栏左侧：附件上传（模仿 DS 网页的单一入口，图片与文档按类型自动分流） -->
            <template #input-footer>
              <ChatFileUploader v-model="chatAttachments" :disabled="agentMode ? agentGenerating : isGenerating" />
            </template>
            <!-- 工具栏右侧（发送键左边）：智能体模式下的写操作开关 -->
            <template #input-toolbar-right>
              <div v-if="agentMode" class="agent-autoconfirm" title="自动模式：创建/导入直接执行；删除操作始终需要确认">
                <el-switch v-model="agentAutoConfirm" size="small" :disabled="agentGenerating" />
                <span class="ac-text">{{ agentAutoConfirm ? '自动执行' : '仅给方案' }}</span>
              </div>
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
                  <!-- 走 `note_manage` 工具（后端 Agent 工具，2026-09-19 起支持）。
                       提问特意写成「可立即执行」的形式：Agent 模式是默认打开的，
                       点一下就会弹确认卡片 → 确认后真建出一条笔记，
                       让用户一眼看到助手是**能动手的**而不只是会聊天。 -->
                  <div class="quick-item" @click="sendQuickMessage('帮我新建一条笔记，标题叫「我的第一条笔记」，内容写：这是用 OpenStudy 助手创建的笔记。')">
                    <el-icon>
                      <Notebook />
                    </el-icon>
                    <span>写笔记</span>
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
import { ref, reactive, computed, watch, nextTick, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import {
  ChatDotRound, Close, FolderOpened, ArrowRight,
  InfoFilled, QuestionFilled, EditPen, Delete, Clock, Tools, Notebook, Collection
} from '@element-plus/icons-vue'
import {
  assistantStream, getConversationHistory, saveConversationMessages,
  listSessions, createSession, deleteSession,
  getAgentTimeline, attachmentPlaceholder, fillAttachmentMetas
} from '@/api/ai/ai'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { useStreamGeneration } from '@/composables/useStreamGeneration'
import { useAgentChat, isDsFreeModel } from '@/composables/useAgentChat'
import { ElMessage } from 'element-plus'
import AiChatStream from '@/components/AiChatStream/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AgentToolResult from '@/components/AgentToolResult/index.vue'
import AgentConfirmCard from '@/components/AgentConfirmCard/index.vue'
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel/index.vue'
import { useDsDeepThinkSync } from '@/composables/useDsDeepThinkSync'
import ChatFileUploader from '@/components/ChatFileUploader/index.vue'
import ChatAttachmentList from '@/components/ChatAttachmentList/index.vue'
import { compressImageDataUrl } from '@/utils/image-compress'
import { resolveFileName } from '@/utils/doc-parse'
import { supportsVision, DEFAULT_VISION_MODEL } from '@/utils/ai-model-capability'
import useUserStore from '@/store/modules/user'
import { running as selfCheckRunning } from '@/devtools/dfSelfCheck/store'

defineOptions({ name: 'AiAssistant' })

// ===================== 自检面板（仅开发环境） =====================
/**
 * ds-free 自检：在**你当前这个已经登录好的浏览器里**跑端到端用例，
 * 不用另起 Chrome、不用手动给测试实例登录 —— 那正是它取代 Node 版 LIVE 的理由。
 *
 * ⚠️ 写法不能改：`import.meta.env.DEV` 必须**字面写在三元条件里**，
 *    这样 `vite build` 才能静态替换成 `false`、把整条动态 import 分支摇掉 ——
 *    面板与用例表（`tests/df_cases.mjs`）就都不会进生产包。
 *    谁要是改成 `const isDev = ...` 再在别处静态 import 面板，立刻进生产包；
 *    P7 的 `grep dist/` 就是这条的守门人。
 */
const isDev = import.meta.env.DEV
const DfSelfCheckPanel = import.meta.env.DEV
  ? defineAsyncComponent(() => import('@/components/DfSelfCheckPanel/index.vue'))
  : null

const router = useRouter()
const userStore = useUserStore()
const userId = computed(() => userStore.id || userStore.userId)

const visible = ref(false)
const activeTab = ref<'chat' | 'banks' | 'knowledge' | 'self'>('chat')
// 当前选中的模型名（如 deepseek-flash）；历史记忆按 scene=chat 单独保存
const selectedModel = ref('')

// ===================== 智能体模式 =====================
// 与「大屏智能体页」共用同一套引擎（useAgentChat）：普通聊天里也能调工具建题库 / 导题。
// ds-free（网页版）走前端工具调用循环，api 付费模型走后端循环，定位完全一致。
const agentMode = ref(true)
/** 写操作是否自动执行（默认开：智能体自动建题库 / 导题） */
const agentAutoConfirm = ref(true)
const {
  messages: agentMessages,
  isGenerating: agentGenerating,
  tools: agentTools,
  activeModel: agentActiveModel,
  metaWarnings: agentWarnings,
  imageCount: agentImageCount,
  corrections: agentCorrections,
  errors: agentErrors,
  toolCalls: agentToolCalls,
  hasRun: agentHasRun,
  send: agentSend,
  stop: agentStop,
  reset: agentReset,
  resolveConfirm: agentResolveConfirm
} = useAgentChat()

// ===================== 深度思考（不再单独开关，随对话模式走） =====================
//
// 规则：**智能体模式恒开、聊天模式恒关**。
//   · 智能体要调工具、多步推理，思考质量比几百毫秒更重要；
//   · 纯聊天追求响应快，默认不思考。
//
// 用 ref（而不是 computed）+ watch：`useDsDeepThinkSync` 在 ds-free 下需要**写回**本 ref
// （DS 网页端的深度思考是页面上的按钮，轮询到变化会赋回来），computed 是只读的会报错。
const thinkingEnabled = ref(agentMode.value)
watch(agentMode, (on) => {
  thinkingEnabled.value = on
}, { immediate: true })

useDsDeepThinkSync(selectedModel, thinkingEnabled)

// 上面那个 composable 的方向是「页面按钮 → 回填这里」，但本组件已经把**模式**定成了
// 深度思考的唯一事实来源（智能体恒开 / 聊天恒关），所以回填要按模式纠正回来 ——
// 否则在聊天模式选了 `deepseek-free` 时，DS 网页端残留的思考按钮会把聊天模式的思考又打开。
//
// 说明：纠正发生在 watch 回调里（同一轮 flush，早于渲染），所以界面/loading 文案不会闪；
// 而要传给接口的值由发送链路兜底（ds-free 发送前会 `setDeepThink(thinkingEnabled.value)`）。
watch(thinkingEnabled, (on) => {
  if (on !== agentMode.value) thinkingEnabled.value = agentMode.value
})

/** 传给底部输入区的模式值（`agent` / `chat`） */
const chatModeValue = computed<'agent' | 'chat'>(() => (agentMode.value ? 'agent' : 'chat'))

/** 底部输入区切换模式（替代原来的头部开关） */
const onModeChange = (mode: 'agent' | 'chat') => {
  const next = mode === 'agent'
  if (next === agentMode.value) return
  agentMode.value = next
  onAgentModeChange()
  // ⚠️ 切模式**不换会话**：把当前这条对话原样搬给另一条链路的列表（实现见下方
  // `syncMessagesForMode`，就在 `loadMessages` 旁边）。少了这一步，模板会换到
  // 另一个空数组上渲染 → 看起来就像「一切聊天模式就变成新会话」。
  syncMessagesForMode(next)
}

/**
 * 抽屉左上角标题 —— 跟着模式**实时变**（对齐 sp3 的头部做法）：
 * 智能体 → `OpenStudy-Agent`，聊天 → `OpenStudy-Chat`；不在对话 tab 时退回品牌名。
 * 这也替代了原先把模式文字挂在输入区 `@` 旁边的做法（那样太吵）。
 */
const headerTitle = computed(() => {
  if (activeTab.value !== 'chat') return 'OpenStudy'
  return agentMode.value ? 'OpenStudy-Agent' : 'OpenStudy-Chat'
})

// 待发送的附件（图片走 images、文档走 files），由 ChatFileUploader 维护
const chatAttachments = ref<{ images: Array<{ name: string; type: string; base64: string }>; files: Array<{ name: string; type: string; base64: string }> }>({
  images: [],
  files: []
})

// 附件总数：决定「只发附件不写文字」是否允许发送
const attachmentCount = computed(() => chatAttachments.value.images.length + chatAttachments.value.files.length)

// 扁平化后的附件列表，供输入框上方的预览条渲染（图片在前、文档在后）
const attachmentItems = computed(() => [...chatAttachments.value.images, ...chatAttachments.value.files])

// 删除预览条里的某一项（索引对应上面的扁平列表）
const removeAttachment = (idx: number) => {
  const images = [...chatAttachments.value.images]
  const files = [...chatAttachments.value.files]
  if (idx < images.length) images.splice(idx, 1)
  else files.splice(idx - images.length, 1)
  chatAttachments.value = { images, files }
}

/* ===================== Ctrl+V 粘贴图片 ===================== */
// 挂在 document 上，但**只处理焦点在聊天输入框时**的粘贴，
// 否则会影响笔记编辑器等其它地方正常的粘贴行为。
let _pasteBound = false
const PASTE_MAX_IMAGES = 6
const PASTE_MAX_MB = 5

const _readAsDataURL = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })

const isChatInputFocused = () => {
  const el = document.activeElement as HTMLElement | null
  if (!el) return false
  if (el.tagName !== 'TEXTAREA' && !el.isContentEditable) return false
  // 用 AiChatStream 的 placeholder 识别本聊天输入框
  return (el.getAttribute('placeholder') || '').includes('输入消息')
}

const handlePaste = async (e: ClipboardEvent) => {
  if (!isChatInputFocused()) return
  const items = Array.from(e.clipboardData?.items || [])
  const files = items
    .filter((it) => it.kind === 'file' && it.type.startsWith('image/'))
    .map((it) => it.getAsFile())
    .filter((f): f is File => !!f)
  if (!files.length) return

  // 阻止默认行为，避免图片被当作二进制塞进输入框
  e.preventDefault()

  const next = { images: [...chatAttachments.value.images], files: [...chatAttachments.value.files] }
  for (const file of files) {
    if (next.images.length >= PASTE_MAX_IMAGES) {
      ElMessage.warning(`最多上传 ${PASTE_MAX_IMAGES} 张图片`)
      break
    }
    if (file.size > PASTE_MAX_MB * 1024 * 1024) {
      ElMessage.warning(`粘贴的图片超过 ${PASTE_MAX_MB}MB，已跳过`)
      continue
    }
    try {
      // 与文件选择一致：粘贴进来的大图先压缩，避免撑爆扩展通道
      const base64 = await compressImageDataUrl(await _readAsDataURL(file))
      next.images.push({
        // 剪贴板图片在浏览器里往往只有一个通用的 "image.png"，多张就全同名了；
        // 这种情况兜底成可读名（粘贴图片-时间戳-N.扩展名），有自带命名的照旧用自带的。
        name: resolveFileName(file.name, {
          mime: file.type,
          label: '粘贴图片',
          index: next.images.length
        }),
        type: file.type,
        base64
      })
    } catch (err) {
      console.warn('[paste] 读取剪贴板图片失败:', err)
    }
  }
  chatAttachments.value = next
}

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

/* ---------- 拖拽期间的滚动锚点 ---------- */
//: 「视口顶部那条消息」+ 它相对滚动容器顶部的位移；松手后据此复原
let resizeScrollAnchor: { el: HTMLElement; offset: number } | null = null
//: 拖拽前是否贴着底部 —— 贴着底部就说明用户在等最新消息，松手后应回到最新
let resizeWasAtBottom = false

const getMessagesEl = () =>
  (document.querySelector('.ai-assistant .chat-messages') ||
    // 兜底：抽屉被 teleport 出组件树时，`.chat-messages` 仍在抽屉里
    //（限定在 .el-drawer 之内，避免误取到大屏智能体页那一个）
    document.querySelector('.el-drawer .chat-messages')) as HTMLElement | null

/**
 * 记录滚动锚点（拖拽开始时调一次）
 *
 * 为什么需要它：拖拽期间离屏消息是「跳过布局、用记住的高度」渲染的 —— 高度理论上不变，
 * 但只要有一点变化，浏览器一钳制 `scrollTop`，用户看到的就是跳位。
 * 与其赌浏览器行为，不如自己记一条锚点、松手后复原：一次校正，完全可控。
 */
const captureScrollAnchor = () => {
  resizeScrollAnchor = null
  resizeWasAtBottom = false
  const box = getMessagesEl()
  if (!box) return
  // 与 AiChatStream 的「贴底」判定保持一致（50px 内算贴底）
  resizeWasAtBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50
  const boxTop = box.getBoundingClientRect().top
  for (const el of Array.from(box.querySelectorAll<HTMLElement>('.message'))) {
    const rect = el.getBoundingClientRect()
    if (rect.bottom > boxTop) {
      resizeScrollAnchor = { el, offset: rect.top - boxTop }
      return
    }
  }
}

/** 复原滚动锚点（松手、且布局稳定后调一次） */
const restoreScrollAnchor = () => {
  const box = getMessagesEl()
  const anchor = resizeScrollAnchor
  const wasAtBottom = resizeWasAtBottom
  resizeScrollAnchor = null
  resizeWasAtBottom = false
  if (!box) return
  if (wasAtBottom) {
    box.scrollTop = box.scrollHeight
    return
  }
  if (!anchor || !anchor.el.isConnected) return
  const boxTop = box.getBoundingClientRect().top
  const delta = anchor.el.getBoundingClientRect().top - boxTop - anchor.offset
  if (Math.abs(delta) > 1) box.scrollTop += delta
}

const startDrawerResize = (e: MouseEvent) => {
  e.preventDefault()
  e.stopPropagation()
  isResizingDrawer = true
  resizeStartX = e.clientX
  resizeStartSize = drawerSize.value
  resizeNextSize = drawerSize.value
  setDrawerTransition(false)
  // 记录滚动位置：拖拽期间离屏消息跳过布局，靠这条锚点保证松手后位置不变
  captureScrollAnchor()
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
    // ⚡ 拖拽期间**直接写 DOM 宽度**，不更新响应式 `drawerSize`。
    //
    // 为什么不改 ref：`drawerSize` 是模板里 `:size` 的取值，每帧改它 = 每帧触发
    // 整个组件重新 diff + patch；消息一多（几百个节点、markdown/卡片、文本要重新折行），
    // 单帧就要几十毫秒 → 拖动像幻灯片。直接写 style 只让浏览器做一次布局，
    // **完全不进 Vue 的渲染管线**。
    //
    // 宽度就绑在 `.el-drawer` 根节点上（Element Plus 的 `style: { width: size }`），
    // 所以写到 `getDrawerEl()` 即可；松手时再把最终值同步回 ref（只渲染一次，值相同无跳动）。
    const el = getDrawerEl()
    if (el) el.style.width = resizeNextSize + 'px'
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
    if (isResizingDrawer) return
    setDrawerTransition(true)
    // 等这一帧布局彻底算完（宽度 + 重新折行）再校正滚动位置，否则量到的是旧值
    requestAnimationFrame(() => {
      if (!isResizingDrawer) restoreScrollAnchor()
    })
  })
}

/* ===================== 我的题库 ===================== */
const myBanks = ref<any[]>([])
const bankLoading = ref(false)
const bankKeyword = ref('')

/** 知识库面板实例：切换 tab / 调 activate() 用 */
const kbPanelRef = ref<InstanceType<typeof KnowledgeBasePanel> | null>(null)

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

const switchToSelf = () => {
  activeTab.value = 'self'
  sessionListVisible.value = false
}
/**
 * 切到「我的知识库」
 *
 * ⚠️ 面板用 v-if 懒挂载：每次切进来都是新实例，必须在**切进来这一刻**调 activate() ——
 *    面板自己不自动加载（原因见面板注释），不调的话用户看到的是空列表。
 *    nextTick 等这一帧渲染完，ref 才有值。
 */
const switchToKnowledge = async () => {
  activeTab.value = 'knowledge'
  sessionListVisible.value = false
  await nextTick()
  await kbPanelRef.value?.activate()
}

/**
 * 自检运行期间挡掉发送。
 *
 * 为什么必须挡：`ds-proxy.ts` 是**全局单例**，全应用共用同一个 DS 标签页；
 * 而「协议/循环」组还会把模型调用整个脚本化。这时候用户发一句，两边会互相踩 ——
 * 自检结果不可信，用户的消息也会被当成测试脚本喂掉。
 *
 * 这里拦一道，`useAgentChat.send()` 里还有一道（覆盖大屏智能体页等其它入口）。
 */
const rejectIfSelfCheckRunning = (): boolean => {
  if (!selfCheckRunning.value) return false
  ElMessage.warning('自检正在运行，先等它结束（或去「自检」页点中止）')
  return true
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
/**
 * 聊天模式的消息列表。
 *
 * ⚠️ 它与 `agentMessages`（`useAgentChat` 那份）**不是两段对话，而是同一段对话的两个视图**：
 *   · `messages`        —— 纯问答视角（聊天模式）
 *   · `agentMessages`   —— 完整视角（多带工具卡片 / 过程提示 / 二次确认卡片）
 * 模板按模式二选一渲染，所以**切模式时必须把两边同步**（见 `syncMessagesForMode`），
 * 否则等于换到另一个空数组上渲染 —— 表现就是「一切模式会话就变成新会话」。
 */
const messages = reactive<any[]>([])
let aiMsgIndex = 0
/** 用户是否主动点了「停止生成」——用于区分「被中止」和「真报错」，兜底文案不同 */
let userAborted = false
/** 一个字都没收到时的兜底文案（不再是空白气泡） */
const EMPTY_REPLY_HINT =
  '（没有收到回复内容）请确认 AI 模型配置正常，或扩展侧的 chat.deepseek.com 已登录且可输入，然后重试。'

const stream = useStreamGeneration({
  onChunk: (fullContent: string) => {
    if (messages[aiMsgIndex]) messages[aiMsgIndex].content = fullContent
  },
  onComplete: (content?: string) => {
    // 兜底 1：流「正常结束」但一个字都没拿到（扩展链路的 DONE 可能先于所有分片
    // 到达，见 api/ai/ai.ts 的说明）。给一句可行动的提示，后到的分片会正常覆盖它。
    const text = (content || '').trim()
    const m = messages[aiMsgIndex]
    if (!text && m && !String(m.content ?? '').trim()) {
      m.content = EMPTY_REPLY_HINT
    }
    // 首条消息发出后后端才建立会话，这里刷新列表让新会话出现
    loadSessions()
  },
  onError: (error: any) => {
    console.error('AI 助手请求失败:', error)
    // 把真实原因一并显示出来：之前只显示「请重试」，导致扩展链路（图片上传、
    // 深度思考、DS 页面未打开等）的具体错误被完全掩盖，排查时毫无线索。
    const raw =
      error?.message || error?.error || error?.msg ||
      (typeof error === 'string' ? error : '') || ''
    const reason = String(raw).trim()
    const m = messages[aiMsgIndex]
    if (!m) return
    // 已经流出来的半截回复要保留 —— 直接覆盖成「发送失败」会把用户已经看到的
    // 内容一起抹掉，等于白问一次。
    const partial = String(m.content ?? '').trim()
    if (partial) {
      m.content = `${partial}\n\n> ⚠️ 生成中断${reason ? `：${reason}` : '（未返回原因）'}`
    } else {
      m.content = reason ? `抱歉，发送失败，请重试。\n\n> 原因：${reason}` : '抱歉，发送失败，请重试。'
    }
  }
})

const isGenerating = computed(() => stream.isGenerating.value)
const isPaused = computed(() => stream.isPaused.value)

// 兜底 2（终极）：无论走哪条分支 —— 成功 / 报错 / 函数里静默 return / 流异常结束 ——
// 只要「生成结束」且助手气泡仍为空，就补一句可读提示，绝不留空气泡。
// 这是唯一能覆盖「所有路径」的写法：万一将来又有人加了条不回调 onError 的 return，
// 这里仍然兜得住。
// ⚠️ 必须写在 isGenerating 的声明之后：computed 是 const，提前引用会命中 TDZ 直接抛错。
watch(isGenerating, (now, before) => {
  if (!before || now) return
  const aborted = userAborted
  userAborted = false
  const idx = aiMsgIndex
  nextTick(() => {
    // 期间切换过会话 / 重新加载过历史 → 放弃（避免把提示写到别的消息上）
    if (idx !== aiMsgIndex) return
    const m = messages[idx]
    if (m && m.role === 'assistant' && !String(m.content ?? '').trim()) {
      m.content = aborted ? '（已停止生成）' : EMPTY_REPLY_HINT
    }
  })
})

/**
 * 取「纯问答」形态的副本。
 *
 * 工具卡片（tool_result）/ 过程提示（agent_note）/ 等待占位（thinking）/
 * 二次确认卡片（tool_confirm）**都不带过去** —— 它们属于「智能体能力」，
 * 聊天模式既不显示也不该显示；这也正好对齐 `ai_chat_message` 只存
 * 「提问 + 回复」两行的落库形态。
 */
const toPlainMessages = (list: any[]) =>
  list
    .filter((m) => !m.type && (String(m.content ?? '').trim() || m.attachments?.length))
    .map((m) => ({
      role: m.role,
      content: m.content || '',
      ...(m.attachments?.length ? { attachments: m.attachments } : {})
    }))

/**
 * 切模式时把**同一条对话**搬给另一条链路的列表 —— 模式只决定「能不能用工具」，不动会话。
 *
 * 正常状态下 `messages` 恒等于 `toPlainMessages(agentMessages)` 这个「纯问答投影」；
 * 聊天模式里新发的内容只落到 `messages`，所以反向（聊天 → 智能体）时只要把**多出来的尾部**
 * 补进 `agentMessages` 即可 —— 用投影长度当下标，天然幂等，不需要额外记「搬到第几条」的状态。
 */
const syncMessagesForMode = (toAgent: boolean) => {
  if (toAgent) {
    const already = toPlainMessages(agentMessages.value).length
    const delta = messages.slice(already)
    if (delta.length) agentMessages.value.push(...delta)
    return
  }
  messages.length = 0
  aiMsgIndex = 0
  messages.push(...toPlainMessages(agentMessages.value))
}

const loadMessages = async () => {
  // ⚠️ 两个列表是同一段对话的两个视图，换会话时**两个都要清** ——
  // 只清当前模式那个，另一个会残留上一个会话的内容（切模式时立刻串台）。
  agentReset()
  messages.length = 0
  aiMsgIndex = 0
  if (!currentSessionId.value) return
  try {
    // 两个数据源并行取（都是小 GET）：
    //   · `ai_chat_message`  —— 纯问答，**一定是最全的**（两条链路都会写提问+回复两行）
    //   · 时间线快照          —— 只在智能体模式需要，多带工具卡片，但只到「上次 Agent 跑完」为止
    const [histRes, tlRes] = await Promise.all([
      getConversationHistory(currentSessionId.value, userId.value).catch((err: any) => {
        console.error('加载会话消息失败:', err)
        return null
      }),
      agentMode.value
        ? getAgentTimeline(currentSessionId.value, userId.value).catch(() => null)
        : Promise.resolve(null)
    ])
    const history: any[] = histRes?.code === 200 && Array.isArray(histRes.data) ? histRes.data : []
    const tlMsgs = (tlRes as any)?.data?.messages

    if (agentMode.value && Array.isArray(tlMsgs) && tlMsgs.length) {
      // 智能体：优先用「完整时间线快照」复原（含工具卡片）；老会话没有快照就走下面的普通问答。
      agentMessages.value.push(...tlMsgs)
      // 快照只覆盖到上次 Agent 运行结束；期间如果切到聊天模式聊过，那几轮只会落在
      // `ai_chat_message` 里 → 把快照缺的尾部补回来，否则「切过模式再刷新」会感觉
      // 对话凭空少了一截（用纯问答投影的长度当断点，和 `syncMessagesForMode` 同一套算法）。
      const shown = toPlainMessages(agentMessages.value).length
      if (history.length > shown) agentMessages.value.push(...history.slice(shown))
      return
    }
    // ⚠️ agentMessages 是 useAgentChat 返回的 Ref，脚本里必须走 .value
    //（早期写成 agentMessages.push 会抛 TypeError 且被本 catch 吞掉 →
    //  历史一条都加载不出来，表现为「切换历史会话无反应 / 看起来没保存」）
    if (agentMode.value) agentMessages.value.push(...history)
    else messages.push(...history)
  } catch (e) {
    console.error('加载会话消息失败:', e)
  }
}

// 新建会话：后端立即落一条「新会话」到列表（首条消息后标题自动替换）
const newSession = async () => {
  sessionListVisible.value = false
  if (stream.isGenerating.value) stream.abort()
  if (agentGenerating.value) agentStop()
  // 当前会话还是空的就不再新建，避免堆一堆空会话
  if (currentSessionId.value && messages.length === 0 && agentMessages.value.length === 0) {
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
  agentReset()
  await loadSessions()
}

// 切换到历史会话，继续聊天
const switchSession = async (s: any) => {
  sessionListVisible.value = false
  if (!s?.sessionId || s.sessionId === currentSessionId.value) return
  if (stream.isGenerating.value || agentGenerating.value) return
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
  if (rejectIfSelfCheckRunning()) return
  if (agentMode.value) return handleAgentSend(content)
  if (stream.isGenerating.value) return
  const text = (content || '').trim()
  // 附件一次性快照：发送后立刻清空输入区的预览，避免重复发送
  const sent = {
    images: [...chatAttachments.value.images],
    files: [...chatAttachments.value.files]
  }
  const hasAttachment = sent.images.length > 0 || sent.files.length > 0
  // 只发附件、不写文字也允许发送（对齐 DS 网页端），所以两者至少有其一即可
  if (!text && !hasAttachment) return

  // 图片只有多模态模型能看。用户若选了「仅文本」的模型（如 deepseek-v4-pro）又带了图片，
  // 就在**发送这一刻**自动切到 deepseek-flash 并说明原因 —— 否则请求会被上游以
  // 「该模型不支持图片输入」打回，用户只看到一句莫名其妙的报错。
  // 注意：这里**不写 localStorage**，用户在模型下拉框里的选择照旧记着，
  // 下次进来仍然是 pro（自动切换只是本轮权宜，不该覆盖用户偏好）。
  if (sent.images.length > 0 && !supportsVision(selectedModel.value)) {
    const from = selectedModel.value
    selectedModel.value = DEFAULT_VISION_MODEL
    ElMessage.warning(
      `${from} 暂时不支持上传图片，只支持文本内容上传；已自动切换为 ${DEFAULT_VISION_MODEL}`
    )
  }

  if (!currentSessionId.value) currentSessionId.value = `asst_${Date.now()}`
  chatAttachments.value = { images: [], files: [] }
  // 新一轮开始，重置「已中止」标记（上一轮可能点过停止）
  userAborted = false

  const attachments = [...sent.images, ...sent.files]
  messages.push({
    role: 'user',
    // 纯附件时正文为空，给个占位文案，否则气泡里会是一片空白
    content: text || (sent.images.length ? '[图片]' : '[附件]'),
    ...(attachments.length ? { attachments } : {})
  })
  aiMsgIndex = messages.length
  messages.push({ role: 'assistant', content: '' })
  stream.start((handleChunk, handleComplete, handleError, signal) => {
    assistantStream(
      text,
      handleChunk,
      handleComplete,
      handleError,
      signal,
      selectedModel.value || undefined,
      userId.value,
      currentSessionId.value,
      thinkingEnabled.value,
      // 附件：ds-free 交给浏览器扩展转 DS 网页端；其它模型走后端多模态接口
      { images: sent.images, files: sent.files }
    )
  })
}

/** 智能体模式发送：与「大屏智能体页」同引擎（ds-free 前端循环 / api 付费后端循环） */
const handleAgentSend = async (content: string) => {
  if (rejectIfSelfCheckRunning()) return
  if (agentGenerating.value) return
  const text = (content || '').trim()
  const sent = {
    images: [...chatAttachments.value.images],
    files: [...chatAttachments.value.files]
  }
  const hasAttachment = sent.images.length > 0 || sent.files.length > 0
  if (!text && !hasAttachment) return

  if (sent.images.length > 0 && !supportsVision(selectedModel.value)) {
    const from = selectedModel.value
    selectedModel.value = DEFAULT_VISION_MODEL
    ElMessage.warning(`${from} 暂时不支持上传图片；已自动切换为 ${DEFAULT_VISION_MODEL}`)
  }

  if (!currentSessionId.value) currentSessionId.value = `asst_${Date.now()}`
  chatAttachments.value = { images: [], files: [] }
  userAborted = false

  // 附件元信息：先用「只有名字 / 类型」的占位**立即入流**，发送不被文档解析拖住
  // （单份文档解析硬超时 20s，而预览只是锦上添花）。
  // 缩略图与文档预览块随后异步补齐 —— 必须用 reactive 代理，补齐后气泡里的附件
  // 才能点开预览（普通数组改属性不会触发刷新）。
  const attachments = reactive<any[]>(
    [...sent.images, ...sent.files].map(attachmentPlaceholder)
  )
  const metasReady = fillAttachmentMetas(attachments, sent.images, sent.files)

  const answer = await agentSend({
    message: text,
    // 传对象而不是 .map(i => i.base64)：下游要靠 name 给 DS 的图片附件起名
    images: sent.images,
    files: sent.files.map((d) => ({ name: d.name, type: d.type, base64: d.base64 })),
    attachments,
    model: selectedModel.value || undefined,
    sessionId: currentSessionId.value,
    userId: userId.value,
    autoConfirm: agentAutoConfirm.value
  })

  // ds-free 链路后端不落库，这里补写「提问 + 最终回复」
  if (isDsFreeModel(selectedModel.value) && currentSessionId.value?.startsWith('asst_') && answer) {
    try {
      // 落库要拿到最终的预览块，不能写半截 —— 等补齐完再写
      await metasReady
      await saveConversationMessages(
        currentSessionId.value,
        {
          userMessage: text || (sent.images.length ? '[图片]' : '[附件]'),
          assistantMessage: answer,
          // 展开成普通对象：attachments 是 reactive 代理，直接丢给序列化会有额外开销
          attachments: attachments.map((a) => ({ ...a }))
        },
        userId.value
      )
    } catch (e) {
      console.warn('[assistant] ds-free 历史落库失败', e)
    }
  }
  loadSessions()
}

/** 对话模式变了（输入区 `@` → 模式卡片）→ 确保有个会话 id，模式切换后能立刻产生归属 */
const onAgentModeChange = () => {
  if (!currentSessionId.value) currentSessionId.value = `asst_${Date.now()}`
}

const sendQuickMessage = (text: string) => {
  activeTab.value = 'chat'
  handleChatSend({ content: text })
}

const stopGeneration = () => {
  userAborted = true
  if (agentMode.value) agentStop()
  else stream.abort()
}

/** 生成中「停止」按钮（AiChatStream 在 isGenerating 时发 toggle-pause） */
const onTogglePause = () => {
  if (agentMode.value) {
    userAborted = true
    agentStop()
  } else {
    stream.togglePause()
  }
}

/* ===================== 生命周期 ===================== */
onMounted(async () => {
  // Ctrl+V 粘贴图片：只绑定一次，避免重挂载造成重复监听
  if (!_pasteBound) {
    _pasteBound = true
    document.addEventListener('paste', handlePaste)
  }
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
    /*
     * 干掉抽屉自带的大面积阴影：Element Plus 的 `--el-box-shadow-dark` 是三层大模糊
     * （48px 级），抽屉高近一屏 → 宽度一变，整条阴影区域**每帧重绘**，是拖拽卡顿的大头。
     *
     * ⚠️ 必须用 inset 阴影、**不要用 border**：`box-sizing: border-box` 下 border 会吃掉
     *    1px 内容宽，会让消息重新折行（哪怕只差 1px），平白多一次全量重排。
     */
    box-shadow: inset 1px 0 0 var(--el-border-color-lighter, #e4e7ed);

    .assistant-container {
      pointer-events: none;
    }
  }

  /*
   * 长会话拖拽跟手的**关键**：让离屏消息跳过布局
   *
   * 宽度一变，普通元素连「看不见的」消息也要重新折行 —— 几百条消息时，
   * 单帧几十毫秒基本都花在这儿。拖拽期间临时开 `content-visibility: auto`，
   * 离屏消息直接跳过布局，每帧只处理可视区那几条。
   *
   * ⚠️ 两个坑（第一次就踩了，务必别改回去）：
   *
   *  ① **高度必须可信**：`.message` 上**常驻** `contain-intrinsic-size: auto 90px`。
   *     `auto` 关键字会让浏览器记住每条消息**上一次真实渲染的高度**，于是「跳过布局」时
   *     用的还是真实高度 → 总高度几乎不变（只是不再重新计算）。
   *     没有 `content-visibility` 在场时，这条属性**完全无副作用**，所以可以常驻。
   *
   *  ② **绝不要动 `overflow-anchor`**：滚动锚定是浏览器自己「高度突变时保住可视位置」的机制。
   *     上次我为了省一点锚点重算写成 `overflow-anchor: none`，结果 scrollTop 被钳制 →
   *     松手后滚动条「跳到很上方」。现在改由 JS 记录/复原锚点兜底
   *     （见 `captureScrollAnchor` / `restoreScrollAnchor`），不依赖浏览器行为。
   */
  :deep(.el-drawer .message) {
    contain-intrinsic-size: auto 90px;
  }

  :deep(.el-drawer.is-dragging .message) {
    content-visibility: auto;
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
      /* 标题随模式变长（OpenStudy-Agent 比「OpenStudy 助手」长），抽屉可以拖到很窄（MIN 320px）
         → 允许左侧被压缩、标题省略号，别把右侧的模型选择器和图标挤出去 */
      min-width: 0;

      .el-icon {
        flex-shrink: 0;
      }

      .header-title {
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .header-right {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
      /* 空间不够时让左边的标题去省略号，右侧的模型选择器与图标保持完整 */
      flex-shrink: 0;

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

  /* ========== 智能体写操作开关（输入区工具栏右侧，发送键左边） ========== */
  .agent-autoconfirm {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .ac-text {
    font-size: 12px;
    color: #6b7280;
    white-space: nowrap;
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

      /* 自检运行中的小红点：切到别的 tab 也能看见它在跑 */
      .tab-dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #f56c6c;
        animation: sc-pulse 1.2s ease-in-out infinite;
      }
    }
  }

  @keyframes sc-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.25;
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

  /* ========== 我的知识库 ========== */
  /* 面板自己管滚动与内边距（见 KnowledgeBasePanel 的 .kb-panel / .kb-main），
     这里只负责把它撑满内容区 —— 高度链断掉的话 .kb-main 的 overflow-y 就不生效 */
  .knowledge-panel {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
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
