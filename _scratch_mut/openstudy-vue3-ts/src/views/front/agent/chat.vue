<!-- ==================== 智能体（大屏对话） ==================== -->
<!--
  智能体 = 大屏版的 OS 助手 + 工具调用能力

  与原「题库搭建 > Agent 搭建」标签页的关系（那个页已去掉）：
    · 那个页是一次性任务表单（选文件 → 点开始 → 看时间线 → 结束），
      适合「我就想把这份文档导进去」，但不适合连续对话；
    · 这里是**常驻对话页**：工具调用过程内联在消息流里（不是折叠面板），
      可以追问、可以连续管题库，也有会话历史。

  形态对齐 sp3 的 `views/front/agent/chat.vue`：消息流 + 底部输入区，
  工具卡片走 AiChatStream 的 `#tool-result` 插槽（它本来就是为 Agent 留的）。

  ⚠️ 与 sp3 的差别：**顶部标题栏已删**（用户要求），原来在标题栏里的控件全部并进底部工具栏，
  详见下方 `.agent-main` 上的注释。输入区也**不再做 `position: absolute` 的贴纸式悬浮**
  （那种做法要靠 `padding-bottom` 的魔法数字给消息区垫位，输入框长一行就会盖住最后一条消息）。
-->
<template>
  <div class="agent-page">
    <div class="agent-shell">
      <!--
        ⚠️ 这里**没有左侧历史栏**（2026-09-20 用户要求改形态）：
        原来它是 `.agent-shell` 里的 flex 兄弟（`.agent-sidebar`，固定 248px、常驻占位），
        后来改成**输入卡片上方的浮动面板** `.session-popover`（见 `#input-footer` 里那一段）。
        理由：历史会话是「偶尔看一眼就关」的东西，不该长期占掉一列对话宽度；
        新形态与 os 助手（`AiAssistant`）的历史会话面板是同一套观感/交互。
        旧形态的 `.agent-sidebar` / `.side-*` / `slide-left` 已**整块删除**，不留死代码。
      -->
      <!-- ── 主区 ── -->
      <!--
        ⚠️ 这里**没有顶部标题栏**（原来那条 `.agent-head`：「OpenStudy 智能体 / 能查题库…」
        + 自动执行开关 + 模型选择器 + 新对话 已被删掉）。
        理由：智能体是「对话页」，标题栏那行文字没人会第二次读，却常驻吃掉一行高度、
        还把顶部视觉重心压在输入框之外。现在控件都并到**底部工具栏**里：
          · 左侧（AiChatStream 的 `#input-footer` → ChatInputArea 的 `toolbar-extra`）：
            附件上传 / 知识库 / 历史会话 / 自动执行开关 / 可用工具弹层
          · 右侧（`#input-toolbar-right` → `toolbar-right-before`）：
            模型选择器（窄版）+ 新对话 +（ChatInputArea 自带的）发送按钮
        历史会话的开关原来在标题栏里（`.head-toggle` 时钟图标），已挪到左侧工具栏 ——
        功能没丢，只是换了入口；它现在开的是**输入卡片上方的浮层**（不是左侧常驻栏，
        见上面 `.agent-shell` 那条注释）。
      -->
      <div class="agent-main">

        <!-- 附件告警（文档解析失败 / 插图丢失等） -->
        <div v-for="(warn, i) in metaWarnings" :key="'w' + i" class="meta-warn">
          {{ warn }}
        </div>

        <!-- 消息流 -->
        <!--
          ⚠️ 停止按钮的接线：AiChatStream 在 isGenerating 时那个按钮发的是
          `toggle-pause` 而**不是** `stop`（它在聊天助手那里是「暂停/继续」）。
          Agent 没有暂停语义（事件流暂停没有意义），所以这里把两个事件都接到 stop，
          否则运行中那个按钮会点了没反应、用户停不下来。
        -->
        <AiChatStream ref="chatRef" :messages="messages" :is-generating="isGenerating" :is-paused="false"
          :has-attachment="attachmentCount > 0" placeholder="告诉我你想做什么…（Enter 发送，Ctrl+Enter 换行）"
          :show-mode-switch="false" @send="handleSend" @stop="stop" @toggle-pause="stop">
          <!-- 工具调用卡片 -->
          <template #tool-result="{ message }">
            <AgentToolResult :tool="message.tool" :action="message.action" :content="message.content"
              :detail="message.detail" :status="message.status" :errors="message.errors"
              :params="message.params" :data="message.data" />
          </template>

          <!-- 写操作二次确认卡片 -->
          <template #tool-confirm="{ message }">
            <AgentConfirmCard :tool="message.tool" :action="message.action" :content="message.content"
              :status="message.status" :destructive="message.destructive" :preview="message.preview"
              @resolve="(ok) => resolveConfirm(message.confirmId, ok)" />
          </template>

          <!-- 输入框上方：待发送附件预览 -->
          <template #input-header>
            <ChatAttachmentList :items="attachmentItems" removable :disabled="isGenerating"
              @remove="removeAttachment" />
          </template>

          <!-- 输入框下方工具行（左半）：附件 / 知识库 / 历史会话 / 执行开关 / 工具清单 -->
          <template #input-footer>
            <ChatFileUploader v-model="attachments" :disabled="isGenerating" />
            <!-- 知识库：嵌在本页（输入栏按钮 + 右侧抽屉），不做独立入口 ——
                 资料是给「这次提问」用的，入口就该在发消息的地方。
                 这里不需要在改动后做任何失效处理：运行时背景本来就不缓存
                 （见 `agentDsFree.fetchAgentContext`），下一轮提问自然带上新的库清单。 -->
            <KnowledgeBaseDrawer />

            <!-- 历史会话开关（原来在顶部标题栏里，标题栏删掉后挪到这里）：浮层从按钮**上方**弹出 -->
            <!--
              ⚠️ `@mousedown.stop` 不能删：浮层的「点外面关闭」挂在 document 的 mousedown 上，
              不拦下这一下，点按钮会先被判成「点在外面」而关掉、紧接着 click 又把它打开 ——
              表现是「点按钮关不掉」（`AiAssistant` 的历史会话按钮同样带这个修饰符）。
            -->
            <button type="button" class="tb-btn" :class="{ 'is-on': historyOpen }" title="历史会话"
              @mousedown.stop @click="toggleHistory">
              <el-icon>
                <Clock />
              </el-icon>
            </button>

            <!--
              历史会话浮层（形态照 os 助手 `AiAssistant` 的 `.session-popover`）：
              白卡片 + 圆角 + 描边 + 阴影，**覆盖**在消息区上、不占布局 —— 打开时不再挤窄对话区。
              锚点写在 `.session-popover` 的样式里（`bottom: calc(100% + 8px)`，即以输入卡片为基准）。
            -->
            <transition name="pop-fade">
              <div v-if="historyOpen" ref="sessionPopoverRef" class="session-popover">
                <div class="session-popover-header">
                  <span>历史会话</span>
                  <span class="session-count">{{ sessionCountText }}</span>
                </div>

                <!-- 搜索：**只按标题**过滤，且是纯客户端过滤。
                     按消息正文搜会话前端做不到（没有正文可搜，得后端加检索接口），本轮不做。 -->
                <div class="session-search">
                  <el-input v-model="sessionKeyword" size="small" clearable placeholder="搜索会话标题"
                    @keydown.esc="historyOpen = false">
                    <template #prefix>
                      <el-icon><Search /></el-icon>
                    </template>
                  </el-input>
                </div>

                <div class="session-list" v-loading="sessionsLoading">
                  <div v-for="s in filteredSessions" :key="s.sessionId"
                    :class="['session-item', { active: s.sessionId === sessionId }]" @click="switchSession(s)">
                    <div class="session-title">{{ sessionTitle(s) }}</div>
                    <div class="session-meta">
                      <span>{{ formatTime(s.updatedAt) }}</span>
                      <span>{{ s.messageCount || 0 }} 条</span>
                    </div>
                    <span class="session-delete" title="删除会话" @click.stop="removeSession(s)">
                      <el-icon>
                        <Delete />
                      </el-icon>
                    </span>
                  </div>

                  <!--
                    两种「空」必须分成两句话 ——
                      · 一条会话都没有：确实没有历史；
                      · 有会话但搜索没命中：要说清是**搜索**没命中，并带上关键词（用户才知道该改词）。
                    复用第一句等于对用户说假话（知识库列表踩过同一个坑）。
                  -->
                  <div v-if="!sessionsLoading && !sessions.length" class="session-empty">暂无历史会话</div>
                  <div v-else-if="!sessionsLoading && !filteredSessions.length" class="session-empty">
                    没有标题包含「{{ sessionKeyword.trim() }}」的会话
                  </div>
                </div>
              </div>
            </transition>

            <!-- 写操作开关：关掉后 Agent 只给方案不落库 -->
            <div class="mode-switch" :title="autoConfirm ? '自动模式：创建/导入直接执行' : '手动模式：写操作只给方案'">
              <el-switch v-model="autoConfirm" size="small" :disabled="isGenerating" />
              <span class="mode-text">{{ autoConfirm ? '自动执行' : '仅给方案' }}</span>
            </div>

            <!-- 可用工具：原来是一整行常驻横条，现在收进这个弹层（点开才看清单） -->
            <!--
              ⚠️ 必须传的是 `model || activeModel`，不能只传 `activeModel`：
                · `activeModel` 是**后端 `meta` 事件回报的「上次实际跑用的模型」** ——
                  它只在**一次请求跑完之后**才会变；用户刚在下拉里换模型、还没发消息时，
                  这里会一直显示上一次的模型（用户 2026-09-19 报的就是这个 bug：
                  「前一秒用 ds-free，下一秒切 ds-flash，工具里的模型介绍不更新」）。
                · `model` 是**选择器当前选中的值**，它就是下一次请求真正会用的模型 ——
                  所以它更能代表「当前模型」。选择器为空（未显式选过）时才回落到 `activeModel`。

              ⚠️ 这里**只**传这一个 prop。`:tools` 与 `:run-model` 曾为「本次运行…」那块脚注而传，
                 用户 2026-09-21 裁决删掉整块脚注后它们一起去掉了 —— 别再往这个组件上加回来，
                 L43 会断「只允许 `:model`」。
            -->
            <AgentToolPopover :model="model || activeModel" />

            <span class="footer-hint">支持 Word / PDF / TXT / MD 与题目截图</span>
          </template>

          <!-- 输入框下方工具行（右半）：模型选择器（窄版）+ 新对话 + 发送按钮 -->
          <template #input-toolbar-right>
            <AiModelSelector v-model="model" scene="agent" width="120px" :disabled="isGenerating" />
            <el-button class="tb-new" :icon="Plus" text :disabled="isGenerating" @click="newSession">
              新对话
            </el-button>
          </template>

          <!-- 空状态：引导语 + 快捷指令 -->
          <template #empty>
            <div class="hero">
              <div class="hero-badge">Agent</div>
              <h2 class="hero-title">嗨，我是 OpenStudy 智能体</h2>
              <p class="hero-desc">
                上传题库文档或题目截图，我会<strong>自己创建题库</strong>并<strong>分批导入题目</strong>。
                调了什么工具、导了多少题、哪里出错又怎么改回来，你都能实时看到。
              </p>
              <div class="hero-actions">
                <div v-for="(q, i) in quickActions" :key="i" class="hero-card" @click="handleSend({ content: q.text })">
                  <span class="hero-card-icon">
                    <el-icon>
                      <component :is="q.icon" />
                    </el-icon>
                  </span>
                  <span class="hero-card-text">
                    <span class="hero-card-title">{{ q.label }}</span>
                    <span class="hero-card-desc">{{ q.desc }}</span>
                  </span>
                </div>
              </div>
            </div>
          </template>
        </AiChatStream>

        <!--
          底部状态条：**水平居中**的执行统计（用户 2026-09-19 指定）
            1 轮 · 25 步 | LLM 1分8秒 · 工具调用 1分26秒 | 首 token 平均 1.6秒
          口径见 `useAgentChat.ts` 的 `AgentMetrics`（两条链路共用，改一处必须改另一处）。
          ⚠️ 用户原稿里还有「tok/s」与「缓存命中」两项，**本次不做**：ds-free 走的是
             DeepSeek 网页版 SSE，那两项在免费链路上拿不到；只在一侧显示会让两条链路
             的观感与数字口径分叉（双链路同口径是红线）→ 用户拍板「两侧都不显示」。
        -->
        <footer v-if="hasRun" class="agent-foot">
          <span class="foot-group">
            <span class="foot-item">{{ metrics.rounds }} 轮</span>
            <span class="foot-dot">·</span>
            <span class="foot-item">{{ metrics.steps }} 步</span>
          </span>

          <span class="foot-bar">|</span>

          <span class="foot-group">
            <span class="foot-item">LLM {{ formatMs(metrics.llmMs) }}</span>
            <span class="foot-dot">·</span>
            <span class="foot-item">工具调用 {{ formatMs(metrics.toolMs) }}</span>
          </span>

          <span class="foot-bar">|</span>

          <span class="foot-group">
            <!-- 没有样本时后端给 null → 显示 `—`；不能显示 0，那会被读成「瞬间返回」 -->
            <span class="foot-item">首 token 平均 {{ formatFirstToken(metrics.firstTokenMs) }}</span>
          </span>

          <!-- 异常项：只在真的出现时才占位（正常情况这条不渲染） -->
          <template v-if="corrections || errors.length || imageCount">
            <span class="foot-bar">|</span>
            <span class="foot-group">
              <span v-if="corrections" class="foot-item is-warn">自我纠正 {{ corrections }} 次</span>
              <span v-if="errors.length" class="foot-item is-error">错误 {{ errors.length }} 条</span>
              <span v-if="imageCount" class="foot-item">图片落盘 {{ imageCount }} 张</span>
            </span>
          </template>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontAgentChat' })

import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Clock, Delete, Plus,
  FolderOpened, QuestionFilled, UploadFilled, Search
} from '@element-plus/icons-vue'
import AiChatStream from '@/components/AiChatStream/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AgentToolPopover from '@/components/AgentToolPopover/index.vue'
import AgentToolResult from '@/components/AgentToolResult/index.vue'
import AgentConfirmCard from '@/components/AgentConfirmCard/index.vue'
import ChatFileUploader from '@/components/ChatFileUploader/index.vue'
import ChatAttachmentList from '@/components/ChatAttachmentList/index.vue'
import KnowledgeBaseDrawer from '@/components/KnowledgeBaseDrawer/index.vue'
import { useAgentChat } from '@/composables/useAgentChat'
import { listSessions, createSession, deleteSession, getConversationHistory, saveConversationMessages, getAgentTimeline, attachmentPlaceholder, fillAttachmentMetas } from '@/api/ai/ai'
import useUserStore from '@/store/modules/user'

/**
 * 「回到底部」悬浮按钮距消息区底边的高度。
 *
 * 用 AiChatStream 的默认值（16）就够，这里**不再传**一个手算的大数：
 * 输入区是消息列表的**兄弟节点**（在文档流里、在消息列表下方），
 * 消息列表的底边本身就落在输入卡片上方，按钮按「消息区底边往上 56px」定位自然就
 * 落在卡片上方。以前输入区被做成 `position: absolute` 的贴纸时，
 * 消息区一直延伸到面板底部、按钮会压住输入卡片，才需要垫一个 162 的魔法数字 ——
 * 那个数字只要输入框多一行就会失准，已经连同 FLOAT_INPUT_* 常量一起删掉了。
 */

const userStore = useUserStore()
const userId = computed(() => userStore.id || userStore.userId)

/* ===================== Agent 状态 ===================== */
// 必须解构出来：对象里的 ref 在模板中**不会**自动解包，`agent.messages` 拿到的是 Ref
const {
  messages, isGenerating, tools, activeModel, metaWarnings,
  imageCount, corrections, errors, metrics, hasRun,
  send, stop, reset, resolveConfirm
} = useAgentChat()

/**
 * 毫秒 → 人类可读时长（状态条用）
 *
 * 分档与用户给的样例一致（`1分8秒` / `1.6秒`）：
 *   ≥ 1 分钟 → `X分Y秒`；≥ 1 秒 → `X.X秒`；否则 `XXX毫秒`
 * ⚠️ 不要写成 `1.6s` / `190 tok/s` 那种混合单位 —— 这条状态条全中文，单位也统一。
 */
const formatMs = (ms: number) => {
  const n = Number(ms) || 0
  if (n < 1000) return `${Math.round(n)}毫秒`
  if (n < 60000) return `${(n / 1000).toFixed(1)}秒`
  const m = Math.floor(n / 60000)
  const s = Math.round((n % 60000) / 1000)
  return `${m}分${s}秒`
}

/**
 * 首 token 平均值
 *
 * ⚠️ `null`（还没测到样本）必须显示 `—`，**不能**落进 `formatMs` 变成 `0毫秒` ——
 * 「0 毫秒」的意思是「瞬间返回」，与「没有样本」是两件相反的事。
 */
const formatFirstToken = (ms: number | null) =>
  ms == null ? '—' : formatMs(ms)

/** 模型（scene='agent'，与聊天助手的选择互不干扰） */
const model = ref('')
/** 写操作是否自动执行 */
const autoConfirm = ref(true)

const chatRef = ref<any>(null)

/** ds-free 由扩展代发、挂不了 tools，Agent 用不了 */
const isDsFree = computed(() => model.value === 'deepseek-free')

/* ===================== 附件 ===================== */
const attachments = ref<{ images: Array<{ name: string; type: string; base64: string }>; files: Array<{ name: string; type: string; base64: string }> }>({
  images: [],
  files: []
})
const attachmentCount = computed(() => attachments.value.images.length + attachments.value.files.length)
const attachmentItems = computed(() => [...attachments.value.images, ...attachments.value.files])

const removeAttachment = (idx: number) => {
  const images = [...attachments.value.images]
  const files = [...attachments.value.files]
  if (idx < images.length) images.splice(idx, 1)
  else files.splice(idx - images.length, 1)
  attachments.value = { images, files }
}

/* ===================== 会话历史 ===================== */
const historyOpen = ref(false)
const sessions = ref<any[]>([])
const sessionsLoading = ref(false)
const sessionId = ref('')
/** 浮层根节点：只用来判「点的是不是浮层里面」（点外面关闭） */
const sessionPopoverRef = ref<HTMLElement | null>(null)

/**
 * 会话搜索关键词
 *
 * ⚠️ **只按标题**过滤，而且是纯客户端过滤（`sessions` 本来就是整份取回来的）。
 *    按消息正文搜会话做不到 —— 那需要后端提供「按内容搜会话」的检索接口，
 *    前端手里只有标题/时间/条数这几个字段。
 */
const sessionKeyword = ref('')

/**
 * 列表里显示的标题
 *
 * 没有标题的会话显示「新会话」，**搜索也用这同一句** —— 保证「搜到的就是看到的」：
 * 界面上写着「新会话」却搜不到它，用户只会以为搜索坏了。
 */
const sessionTitle = (s: any) => s?.title || '新会话'

const filteredSessions = computed(() => {
  const kw = sessionKeyword.value.trim().toLowerCase()
  if (!kw) return sessions.value
  return sessions.value.filter((s: any) => sessionTitle(s).toLowerCase().includes(kw))
})

/**
 * 数量文案
 *
 * 搜索时给「命中 / 共」两个数，不给单个数：只显示命中数会被读成
 * 「我的会话只剩这么几条了」—— 那是假话（总数并没有变）。
 */
const sessionCountText = computed(() =>
  sessionKeyword.value.trim()
    ? `命中 ${filteredSessions.value.length} / 共 ${sessions.value.length}`
    : `共 ${sessions.value.length} 条`
)

/** 开关浮层：打开时清掉上次的搜索词，否则下次点开看到的是个「被过滤过」的列表 */
const toggleHistory = () => {
  historyOpen.value = !historyOpen.value
  if (historyOpen.value) sessionKeyword.value = ''
}

/**
 * 点浮层外面关闭
 *
 * 挂在 document 的 `mousedown` 上（与 `AiAssistant` 的历史会话面板一致）；
 * 触发按钮上那个 `@mousedown.stop` 是配套的 —— 少了它就是「mousedown 先关掉、
 * click 又打开」，按钮永远关不掉。
 */
const onDocMousedown = (e: MouseEvent) => {
  if (!historyOpen.value) return
  const el = sessionPopoverRef.value
  if (el && !el.contains(e.target as Node)) historyOpen.value = false
}

const formatTime = (time: any) => {
  if (!time) return ''
  const d = new Date(time)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const loadSessions = async () => {
  if (!userId.value) return
  sessionsLoading.value = true
  try {
    const res: any = await listSessions(userId.value)
    if (res?.code === 200 && Array.isArray(res.data)) sessions.value = res.data
    else if (Array.isArray(res?.rows)) sessions.value = res.rows
  } catch (e) {
    console.warn('[agent] 加载会话列表失败', e)
  } finally {
    sessionsLoading.value = false
  }
}

/** 新对话：后端落一条空会话，首条消息后标题自动替换 */
const newSession = async () => {
  if (isGenerating.value) stop()
  reset()
  historyOpen.value = false
  try {
    const res: any = await createSession(userId.value)
    sessionId.value = res?.data?.sessionId || `asst_${Date.now()}`
  } catch {
    sessionId.value = `asst_${Date.now()}`
  }
  await loadSessions()
}

/**
 * 读回某个会话的历史
 *
 * 注意只能复原「提问 + 最终回复」—— 工具调用过程没有落库（它是瞬时的执行过程，
 * 存下来既没用又占地方），所以刷新后看到的是一问一答，不是完整时间线。
 */
const loadHistory = async (sid: string) => {
  if (!sid) return
  try {
    // 优先用「完整时间线快照」复原（含工具卡片）—— 否则刷新后只剩纯文本问答
    const tl: any = await getAgentTimeline(sid, userId.value)
    const tlMsgs = tl?.data?.messages
    if (Array.isArray(tlMsgs) && tlMsgs.length) {
      messages.value = tlMsgs
      return
    }
    const res: any = await getConversationHistory(sid, userId.value)
    if (res?.code === 200 && Array.isArray(res.data)) {
      messages.value = res.data.map((m: any) => ({
        role: m.role === 'assistant' ? 'assistant' : 'user',
        content: m.content || '',
        ...(m.attachments?.length ? { attachments: m.attachments } : {})
      }))
    }
  } catch (e) {
    console.warn('[agent] 加载会话消息失败', e)
  }
}

/** 切换历史会话 */
const switchSession = async (s: any) => {
  if (!s?.sessionId || s.sessionId === sessionId.value) return
  if (isGenerating.value) return
  reset()
  sessionId.value = s.sessionId
  historyOpen.value = false
  await loadHistory(s.sessionId)
}

const removeSession = async (s: any) => {
  try {
    await ElMessageBox.confirm(`确定删除「${s.title || '新会话'}」吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteSession(s.sessionId, userId.value)
    sessions.value = sessions.value.filter((x: any) => x.sessionId !== s.sessionId)
    if (s.sessionId === sessionId.value) await newSession()
  } catch (e) {
    ElMessage.error('删除失败')
    console.warn('[agent] 删除会话失败', e)
  }
}

/* ===================== 发送 ===================== */
const quickActions = [
  {
    icon: FolderOpened,
    label: '看看我的题库',
    desc: '列出全部题库与题量',
    text: '帮我看看我有哪些题库'
  },
  {
    icon: UploadFilled,
    label: '导入这份文档',
    desc: '上传文档后自动建库导题',
    text: '把这个文档的题目导入题库，没有就先创建'
  },
  {
    icon: Search,
    label: '查题库详情',
    desc: '题型分布、题目列表',
    text: '看看我第一个题库的题目分布'
  },
  {
    icon: QuestionFilled,
    label: '建一个题库',
    desc: '按名字创建并推断科目',
    text: '帮我创建一个题库'
  }
]

const handleSend = async ({ content }: { content: string }) => {
  if (isGenerating.value) return
  const text = (content || '').trim()
  const imgs = [...attachments.value.images]
  const docs = [...attachments.value.files]
  if (!text && !imgs.length && !docs.length) return

  if (!sessionId.value) {
    try {
      const res: any = await createSession(userId.value)
      sessionId.value = res?.data?.sessionId || `asst_${Date.now()}`
    } catch {
      sessionId.value = `asst_${Date.now()}`
    }
  }

  // 附件一次性快照，随后立刻清空输入区预览，避免重复发送
  attachments.value = { images: [], files: [] }

  // 附件元信息：先用「只有名字 / 类型」的占位立即入流，别让文档解析拖住发送；
  // 缩略图与文档预览块随后异步补齐（reactive 代理，补齐后气泡里的附件才能点开预览）。
  const metas = reactive<any[]>(
    [...imgs, ...docs].map(attachmentPlaceholder)
  )
  const metasReady = fillAttachmentMetas(metas, imgs, docs)

  const answer = await send({
    message: text,
    // 传对象而不是 .map(i => i.base64)：下游要靠 name 给 DS 的图片附件起名
    images: imgs,
    files: docs.map((d) => ({ name: d.name, type: d.type, base64: d.base64 })),
    // 只用于历史落库的元信息：原图/原件都不入库
    attachments: metas,
    model: model.value || undefined,
    sessionId: sessionId.value,
    userId: userId.value,
    autoConfirm: autoConfirm.value
  })

  // ds-free 链路后端不落库（扩展代发），这里补写「提问 + 最终回复」保证历史可读
  if (isDsFree.value && sessionId.value?.startsWith('asst_') && answer) {
    try {
      // 落库要拿到最终的预览块，不能写半截 —— 等补齐完再写
      await metasReady
      await saveConversationMessages(
        sessionId.value,
        {
          userMessage: text || (imgs.length ? '[图片]' : '[附件]'),
          assistantMessage: answer,
          attachments: metas.map((a) => ({ ...a }))
        },
        userId.value
      )
    } catch (e) {
      console.warn('[agent] ds-free 历史落库失败', e)
    }
  }

  // 新会话的第一轮之后，后端才把标题写进去 → 刷新列表
  loadSessions()
}

/* ===================== 生命周期 ===================== */
onMounted(async () => {
  // 历史会话浮层的「点外面关闭」（回调自己判 historyOpen，关着的时候是空转）
  document.addEventListener('mousedown', onDocMousedown)
  await loadSessions()
  if (sessions.value.length) {
    sessionId.value = sessions.value[0].sessionId
    await loadHistory(sessionId.value)
  } else {
    await newSession()
  }
})

/**
 * 本轮结束后把视图滚到底
 *
 * ⚠️ 这里**不**在 deactivated 时中断流：本页是 keep-alive 的，
 * 用户切去看题库再切回来，应该还能看到刚才那次执行跑完的结果。
 * 只有组件真正销毁（离开这个模块）才中断，避免后端白跑一轮。
 */
watch(isGenerating, (now, before) => {
  if (before && !now) chatRef.value?.scrollToBottom?.()
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocMousedown)
  if (isGenerating.value) stop()
})
</script>

<style scoped lang="scss">
.agent-page {
  height: 100%;
  display: flex;
  padding: 12px 0 0;
  box-sizing: border-box;
}

.agent-shell {
  position: relative;
  flex: 1;
  min-width: 0;
  display: flex;
  border-radius: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

/* ── 历史会话浮层 ── */
/*
 * 形态与观感对齐 os 助手的历史会话面板（`AiAssistant` 的 `.session-popover`）：
 * 白卡片 + 12px 圆角 + 描边 + 阴影，**覆盖**在消息区上、不占布局。
 *
 * 锚点：`bottom: calc(100% + 8px)` —— 以**输入卡片**为基准（`.chat-input-area` 是
 * `position: relative`），从卡片上边缘往上弹 8px；与卡片里已有的 `.mode-card-popup`
 * 是同一套路。好处是**一个手算偏移都不用**：卡片长高（多行文本 / 附件预览）、
 * 底部统计条 `.agent-foot` 出现时，浮层自动跟着走。
 *
 * ⚠️ `max-height` 不能写成百分比：百分比是相对**输入卡片**的高度解析的，卡片才 113px 高，
 * `max-height: 62%` 只剩 70px（os 助手那边是相对整个抽屉解析才够用）。
 * 这里给的 `min(46vh, 420px)` 同时保证任何窗口高度下都不会顶出 `.ai-chat-stream`
 * 上边缘被它裁掉（那条链上挂着 `overflow: hidden`）。
 *
 * ⚠️ 进场/退场**只动 transform + opacity**（见下面的 `.pop-fade-*`）：这两个是合成阶段属性，
 * 不触发布局。旧形态（左侧栏）用 `transition: all` 动 `width`，等于每帧给整个消息列表
 * 重排一次 —— 那正是用户报的「点历史会话按钮会卡一下」。
 */
.session-popover {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  z-index: 30;
  width: 268px;
  max-width: 100%;
  max-height: min(46vh, 420px);
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  overflow: hidden;
}

.session-popover-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  border-bottom: 1px solid #eef2f7;
}

.session-count {
  font-size: 12px;
  font-weight: 400;
  color: #9aa5b5;
}

.session-search {
  flex-shrink: 0;
  padding: 8px 8px 0;
}

.session-list {
  flex: 1;
  /* 列表空着时高度为 0 → `v-loading` 的转圈没地方显示，给个下限 */
  min-height: 56px;
  overflow-y: auto;
  padding: 6px 8px 8px;
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
    background: #eef4ff;
  }
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
  display: flex;
  gap: 10px;
  margin-top: 3px;
  font-size: 11px;
  color: #9aa5b5;
}

.session-delete {
  position: absolute;
  top: 8px;
  right: 6px;
  display: none;
  color: #9aa5b5;

  &:hover {
    color: #ef4444;
  }
}

.session-item:hover .session-delete {
  display: inline-flex;
}

.session-empty {
  padding: 18px 6px;
  text-align: center;
  font-size: 12.5px;
  line-height: 1.6;
  color: #9aa5b5;
  word-break: break-all;
}

/*
 * 浮层的进场/退场 —— **只动 transform + opacity**
 *
 * ⚠️ 不要退回 `transition: all` + 动 `width`/`height`：那是在动一个**布局属性**，
 *    每一帧都要同步重排整个 `.agent-shell` 子树（消息列表就在里面），就是「卡一下」的来源。
 *    另：这层浮层本来就不占布局，动宽度也没有任何视觉意义。
 */
.pop-fade-enter-active,
.pop-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.pop-fade-enter-from,
.pop-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* ── 主区 ── */
.agent-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/*
 * 底部工具栏里的小按钮（历史会话开关 / 新对话 …）
 * 与 `ChatInputArea` 的 `.toolbar-btn`、`KnowledgeBaseDrawer` 的 `.kb-entry`
 * 保持同一观感（28×28 / 圆角 8 / 透明底）—— 那两个类是各自组件的 scoped 样式，这里用不了。
 */
.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #6b7280;
  font-size: 15px;
  cursor: pointer;
  /* 只列真要变的三个属性：`all` 会把以后新增的任何属性（含布局属性）也一起动画化 */
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  flex-shrink: 0;

  &:hover,
  &.is-on {
    background: #fff;
    border-color: #e5e7eb;
    color: #2563eb;
  }
}

.mode-switch {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 2px;
}

.mode-text {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.meta-warn {
  margin: 8px 16px 0;
  padding: 5px 10px;
  font-size: 12px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 6px;
}

/* ── 空状态 hero ── */
.hero {
  max-width: 720px;
  margin: 0 auto;
  padding: 28px 20px 10px;
  text-align: center;
}

.hero-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, #eef4ff, #f3ecff);
  border: 1px solid #e2e8f7;
  color: #4f6ef7;
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.6px;
}

.hero-title {
  margin: 14px 0 8px;
  font-size: 22px;
  font-weight: 700;
  color: #1f2d3d;
  letter-spacing: -0.2px;
}

.hero-desc {
  margin: 0 auto;
  max-width: 560px;
  font-size: 13.5px;
  line-height: 1.85;
  color: #5c6b81;

  strong {
    color: #2563eb;
    font-weight: 600;
  }
}

.hero-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(232px, 1fr));
  gap: 10px;
  margin-top: 22px;
  text-align: left;
}

.hero-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid #e8edf5;
  border-radius: 11px;
  background: #fff;
  cursor: pointer;
  /* 列出 hover 里真正会变的四个属性（`all` 会把布局属性也卷进来，见 `.pop-fade-*` 的说明） */
  transition: border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;

  &:hover {
    border-color: #93b4f5;
    background: #f7faff;
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
  }
}

.hero-card-icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef4ff, #f3ecff);
  color: #4f6ef7;
  font-size: 15px;
}

.hero-card-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.hero-card-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #1f2d3d;
  line-height: 1.4;
}

.hero-card-desc {
  font-size: 12px;
  color: #9aa5b5;
  line-height: 1.5;
  margin-top: 1px;
}

/* ── 输入区补充 ── */
.footer-hint {
  font-size: 11.5px;
  color: #b6bdc9;
  margin-left: 8px;
  white-space: nowrap;
}

/* 「新对话」：底部工具栏右侧，观感压得比 el-button 默认更轻 */
.tb-new {
  font-size: 13px;
  color: #6b7280;

  &:hover {
    color: #2563eb;
    background: #f3f5f9;
  }
}

/* 窄屏：左侧工具行会挤（附件/知识库/历史/执行开关/工具弹层 + 这行提示）→ 提示先让位 */
@media (max-width: 1100px) {
  .footer-hint {
    display: none;
  }
}

/* ── 底部状态条（执行统计）── */
.agent-foot {
  display: flex;
  align-items: center;
  /* ⚠️ 水平居中（用户 2026-09-19 指定）：整条统计在面板里居中，不靠左 */
  justify-content: center;
  /* 组之间的 `|` 与组内 `·` 自己带间距，这里只留窄缝，避免居中后显得散 */
  gap: 10px;
  /*
   * 上下 7 → 6：配合上面 `.chat-input-area` 的 `margin-bottom: 3px`，
   * 让这行统计**紧贴**输入卡片底部（用户 2026-09-19 要求「两者贴合」）。
   * 左右仍是 16px —— 统计文字不跟着卡片的 12px 内缩走，窄屏横向滚动时两端才不贴边。
   */
  padding: 6px 16px;
  border-top: 1px solid #eef2f7;
  background: #fcfdff;
  font-size: 12px;
  color: #9aa5b5;
  /* 窄屏时统计比面板宽 → 允许横向滚，别把面板撑高或换行 */
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}

.foot-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* 组内分隔符：比正文更淡，避免与数字抢注意力 */
.foot-dot {
  color: #ccd3de;
}

/* 组间分隔符：比组内稍重，用来切分「三类信息」 */
.foot-bar {
  color: #dde3ec;
}

.foot-item.is-warn {
  color: #b45309;
}

.foot-item.is-error {
  color: #b91c1c;
}

/* AiChatStream 自带边框，容器已有边框 → 去掉内层重复描边 */
.agent-main :deep(.ai-chat-stream) {
  border: none;
  border-radius: 0;
}

/*
 * ── 输入区「悬浮吸底」──
 *
 * 结构上它**留在正常文档流里**（AiChatStream 里它本来就是消息列表的兄弟节点），
 * 靠两件事保证「永远看得见」：
 *   ① `.chat-messages { min-height: 0 }`（AiChatStream 里）→ 消息区自己被压住、内部滚动；
 *   ② `.chat-input-area { flex-shrink: 0 }`（ChatInputArea 里）→ 输入区不被消息挤压。
 *
 * ⚠️ 别退回 `position: absolute; bottom: 14px` 那套「贴纸式悬浮」（这里原来就是那么做的）：
 *   它要额外给消息区垫 `padding-bottom: 156px` 的魔法数字，输入框长高一行（多行文本、
 *   附件预览）那个数字就不够用，最后一条消息会被盖住，而且滚动容器的判定也跟着变形。
 * 「悬浮」只做在**视觉**上：白卡片 + 圆角 + 阴影 + 四周留边 —— 行为上仍是普通流式布局。
 */
.agent-main :deep(.chat-input-area) {
  /*
   * 底部 12px → 3px：卡片下方不再留一大块空白，让它紧贴下面的 `.agent-foot`
   * 统计条（用户 2026-09-19：「让输入框高度下降，和底部那条统计贴合」）。
   * ⚠️ 只缩小正间距，**不要**用负 margin 把统计条叠到卡片上（那会盖住卡片圆角/阴影）。
   */
  margin: 0 12px 3px;
  /* 卡片自身垂直留白 8/10 → 6/6 */
  padding: 6px 10px;
  border: 1px solid #e7ebf0;
  border-top: 1px solid #e7ebf0; /* 盖掉组件默认的 `border-top` 分隔线（卡片不需要） */
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 6px 22px rgba(15, 23, 42, 0.1);
}

/*
 * ── 把输入卡片压矮 ──
 *
 * 为什么全写在 `:deep()` 覆盖层里、不改 `ChatInputArea` 的默认样式：
 *   该组件是**聊天助手抽屉（`AiAssistant`）与智能体页共用**的，改默认值会连带改掉
 *   抽屉里的输入框观感。「压矮」只是智能体页这一层的局部覆盖。
 *
 * 高度账（静态估算，未在浏览器实测）：
 *   组件默认 ≈ 138px ＝ textarea 两行 50 ＋ 分隔线 7 ＋ 工具行 (4+36)
 *                     ＋ input-box 上下 padding 20 ＋ 卡片上下 padding 18 ＋ 描边 3
 *   压到 ≈ 113px      ＝ textarea 两行 47（行高 1.5 → 1.4）
 *                     ＋ 分隔线 5（上下 margin 4/2 → 2/2）
 *                     ＋ 工具行 (2+36)（margin-top 4 → 2）
 *                     ＋ input-box 上下 padding 8（10/10 → 4/4）
 *                     ＋ 卡片上下 padding 12（8/10 → 6/6）＋ 描边 3
 *
 * ⚠️ 工具行那 36px 是**附件上传按钮**（`ChatFileUploader` 的 `.upload-btn`，36×36）钉住的 ——
 *    `align-items: center` 取这一行里最高的那个，所以只把行内其它按钮改小**并不会**让整行变矮，
 *    只会得到一个 26/28/36 混排、高度却一点没变的工具栏。所以这里**不动按钮尺寸**。
 *    要再压这一行，得先统一附件按钮的尺寸（那是共用组件，改它会连带影响助手抽屉）。
 *
 * ⚠️ 压的都是**垂直方向**的（上下 padding / 行高 / 上下 margin），
 *    没动字号，也没把 textarea 压到低于两行 —— 「两行起步 + 自动增高」是从 sp3 搬来的
 *    明确行为（见 `ChatInputArea` 的 `rows="2"` 与 `TEXTAREA_MAX_HEIGHT`）。
 */

/* 卡片内再套一层灰底 + 描边会显脏 → 内层输入框融进卡片（顺带收掉它的上下 padding） */
.agent-main :deep(.chat-input-area .input-box) {
  border-color: transparent;
  background: transparent;
  padding: 4px 8px 4px 10px;
  min-height: 0; /* 组件默认的 66px 下限与「压矮」相冲，去掉以免它兜底撑高 */
}

.agent-main :deep(.chat-input-area .chat-textarea) {
  min-height: 32px;
  /* autoGrow 读的是 scrollHeight → 行高降下来，两行起步的高度也跟着降 */
  line-height: 1.4;
}

.agent-main :deep(.chat-input-area .input-divider) {
  margin: 2px 0;
}

.agent-main :deep(.chat-input-area .input-bottom) {
  margin-top: 2px;
  min-height: 32px;
}
</style>
