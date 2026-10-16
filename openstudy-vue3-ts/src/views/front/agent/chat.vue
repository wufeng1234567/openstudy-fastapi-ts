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
        ⚠️ 这里**没有常驻左侧历史栏**（2026-09-20 用户要求改形态）：
        原来它是 `.agent-shell` 里的 flex 兄弟（`.agent-sidebar`，固定 248px、常驻占位），
        改为**按需唤起的左侧抽屉**（2026-10-09：从「输入卡片上方的浮动面板」升级为
        公共组件 `ResizableDrawer`，可拖拽调宽、与知识库抽屉同款交互）。
        理由：历史会话是「偶尔看一眼就关」的东西，不该长期占掉一列对话宽度。
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
          :show-mode-switch="false" :rollback-states="rollbackStates" @send="handleSend" @stop="stop"
          @toggle-pause="stop" @rollback-turn="onRollbackTurn">
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
              @resolve="(payload) => onConfirmResolve(message, payload)" />
          </template>

          <!-- 输入框上方：待发送附件预览 -->
          <template #input-header>
            <ChatAttachmentList :items="attachmentItems" removable :disabled="isGenerating"
              @remove="removeAttachment" />
          </template>

          <!-- 输入框下方工具行（左半）：附件 / 知识库 / 历史会话 / 执行开关 -->
          <!--
            知识库 / 历史会话 / 设置三个入口**统一到同一个可拉伸抽屉**（内部 tab 切换）。
            方向原则（用户 2026-10-10 定）：**入口在哪侧、抽屉就从哪侧滑出** ——
            知识库/历史会话按钮在左 → 抽屉从左侧（ltr）；设置按钮在右 → 抽屉从右侧（rtl）。
            ⚠️ 方向**只在打开抽屉的那一下由入口侧决定一次、之后锁定**，同一抽屉内切 tab
               不再改变方向（否则：左侧点开知识库再点设置 tab，抽屉会甩到右侧，不合理）。
          -->
          <template #input-footer>
            <ChatFileUploader v-model="attachments" :disabled="isGenerating" />

            <!-- 知识库：资料是给「这次提问」用的，入口就该在发消息的地方 -->
            <button type="button" class="tb-btn" :class="{ 'is-on': panelOpen && panelTab === 'kb' }"
              title="知识库 —— 传资料、让智能体检索后回答" @click="openPanel('kb')">
              <el-icon>
                <FolderOpened />
              </el-icon>
            </button>

            <!-- 历史会话：入口在左 → 抽屉从左侧滑出 -->
            <button type="button" class="tb-btn" :class="{ 'is-on': panelOpen && panelTab === 'history' }"
              title="历史会话" @click="openPanel('history')">
              <el-icon>
                <Clock />
              </el-icon>
            </button>

            <!-- 模型下拉框：直接放输入框旁，省得每次进设置改（用户 2026-10-12 要求）。
                 与「设置 → 模型」绑的是同一个 `model`，两处天然同步。 -->
            <div class="tb-model">
              <AiModelSelector v-model="model" scene="agent" width="180px" :disabled="isGenerating" @select="onModelSelect" />
            </div>

            <!-- 「注入历史上下文」按钮：仅「DS 免费（无浏览器）」模型露出。
                 一次性操作：点击即把当前会话历史作为 .md 附件发给 DS 网页（并在正文里说明这是历史），
                 不是常驻开关。写操作默认自动执行、仅删除需确认，故不再有「自动模式」开关。 -->
            <button v-if="showInjectHistory" type="button" class="tb-btn tb-inject"
              :disabled="isGenerating || injectingHistory" @click="handleInjectHistory"
              title="把当前会话的历史上下文作为附件发送给 DS 网页（用于长上下文续聊）">
              <el-icon><UploadFilled /></el-icon>
              <span>{{ injectingHistory ? '注入中…' : '注入历史' }}</span>
            </button>
            <!-- 「调试」按钮：仅 DS 桥模型露出。点击打开当前登录态的 DS 浏览器窗口（有头），
                 便于直接看到卡在哪一步（附件上传 / 等回复）。 -->
            <button v-if="showInjectHistory" type="button" class="tb-btn tb-inject"
              :disabled="openingBridge" @click="handleOpenDsBridge"
              title="打开当前登录态的 DS 浏览器窗口（调试用）">
              <el-icon><View /></el-icon>
              <span>{{ openingBridge ? '打开中…' : '调试' }}</span>
            </button>
          </template>
          <!-- 输入框下方工具行（右半）：设置（智能体/模型/工具聚合）+ 新对话 + 发送按钮 -->
          <template #input-toolbar-right>
            <!-- 设置入口在右 → 抽屉从右侧滑出（见上方方向原则） -->
            <button type="button" class="tb-btn" :class="{ 'is-on': panelOpen && panelTab === 'settings' }"
              title="智能体设置（智能体 / 模型 / 可用工具）" :disabled="isGenerating" @click="openPanel('settings')">
              <el-icon>
                <Setting />
              </el-icon>
            </button>
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

      </div>
    </div>

    <!--
      智能体侧栏抽屉（统一容器）：知识库 / 历史会话 / 设置三个功能共用**同一个可拉伸抽屉**，
      内部用 tab 切换。方向按「入口在哪侧、抽屉就从哪侧滑出」动态给出：
        设置（右侧入口）→ rtl（右）；知识库/历史会话（左侧入口）→ ltr（左）。
      见 `panelDirection` 计算属性。
    -->
    <ResizableDrawer
      v-model="panelOpen"
      :direction="panelDirection"
      storage-key="openstudy_agent_panel_size"
      :default-width="380"
      :min="300"
      :max="720"
    >
      <div class="agent-panel">
        <!-- tab 头：与工具栏三个入口一一对应 -->
        <div class="agent-panel-tabs">
          <div :class="['aptab', { active: panelTab === 'settings' }]" @click="switchTab('settings')">
            <el-icon><Setting /></el-icon>
            <span>设置</span>
          </div>
          <div :class="['aptab', { active: panelTab === 'kb' }]" @click="switchTab('kb')">
            <el-icon><FolderOpened /></el-icon>
            <span>知识库</span>
          </div>
          <div :class="['aptab', { active: panelTab === 'history' }]" @click="switchTab('history')">
            <el-icon><Clock /></el-icon>
            <span>历史会话</span>
          </div>
        </div>

        <!-- ① 设置 -->
        <div v-show="panelTab === 'settings'" class="agent-panel-body settings-body">
          <!-- 我的智能体（用户自建角色）——官方"专家"已由下面的「专家」开关管理，
               故这里**不再**列官方角色（避免与专家开关重复、造成"两个地方管同一批东西"）。
               「选哪个对话」与「管理（增删改）」是同一件事的两个面，合并在同一区块，
               不再一个在顶、一个在底，避免割裂感。 -->
          <div class="settings-row">
            <div class="settings-label-row">
              <span class="settings-label">我的智能体</span>
              <el-button text type="primary" size="small" @click="openAgentManager">
                管理（新建 / 编辑 / 删除）
              </el-button>
            </div>
            <div class="settings-field">
              <el-select v-if="myAgents.length" v-model="selectedAgentKey" size="default"
                :disabled="isGenerating" style="width: 100%">
                <el-option label="自动（由主助手按需安排）" :value="AUTO_AGENT_KEY" />
                <el-option v-for="a in myAgents" :key="'a-' + a.agentId" :label="a.name" :value="'user:' + a.agentId" />
              </el-select>
              <div class="settings-hint" v-if="myAgents.length">
                「自动」= 由主助手按需安排；也可指定你创建的某个智能体来对话。
              </div>
              <div class="settings-hint" v-else>
                还没有自定义智能体。点上方「管理」新建一个（可设人设、限定工具、绑定模型）。
              </div>
            </div>
          </div>

          <div class="settings-row">
            <div class="settings-label">模型</div>
            <div class="settings-field">
              <AiModelSelector v-model="model" scene="agent" width="100%" :disabled="isGenerating" @select="onModelSelect" />
            </div>
          </div>

          <div class="settings-row">
            <div class="settings-label">专家</div>
            <div class="settings-field">
              <!-- 三种状态分开说：读取中 / 取不到（可重试）/ 有数据 -->
              <div v-if="expertLoading" class="settings-hint">正在读取专家…</div>
              <div v-else-if="expertLoadFailed" class="settings-tools-error">
                <span>专家列表没取到</span>
                <el-button text type="primary" size="small" @click="loadExperts">重试</el-button>
              </div>
              <div v-else class="settings-tools">
                <div v-for="e in experts" :key="e.key" class="settings-tool settings-expert">
                  <div class="settings-expert-main">
                    <span class="settings-tool-name">{{ e.name }}</span>
                    <span class="settings-expert-desc">{{ e.description }}</span>
                    <AiModelSelector
                      :model-value="e.model || ''"
                      scene="agent-expert"
                      width="100%"
                      :auto-default="false"
                      class="settings-expert-model"
                      @update:model-value="(v) => onExpertModelChange(e, v)"
                    />
                  </div>
                  <el-switch
                    :model-value="e.disabled !== 1"
                    size="small"
                    :loading="expertTogglingKey === e.key"
                    :disabled="isGenerating"
                    @update:model-value="toggleExpert(e, $event)"
                  />
                </div>
              </div>
              <div class="settings-hint">
                开启的专家，主助手会在需要时自动请它来帮忙；关掉就完全不用它。
              </div>
            </div>
          </div>
        </div>

        <!-- ② 知识库（与悬浮助手同一个面板组件） -->
        <div v-show="panelTab === 'kb'" class="agent-panel-body">
          <KnowledgeBasePanel ref="kbPanelRef" />
        </div>

        <!-- ③ 历史会话 -->
        <div v-show="panelTab === 'history'" class="agent-panel-body session-drawer">
          <div class="session-search">
            <el-input v-model="sessionKeyword" size="small" clearable placeholder="搜索会话标题"
              @keydown.esc="panelOpen = false">
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>
          <div class="session-count-line">{{ sessionCountText }}</div>
          <div class="session-list" v-loading="sessionsLoading">
            <div v-for="s in filteredSessions" :key="s.sessionId"
              :class="['session-item', { active: s.sessionId === sessionId }]" @click="switchSession(s)">
              <div class="session-title">{{ sessionTitle(s) }}</div>
              <div class="session-meta">
                <span>{{ formatTime(s.updatedAt) }}</span>
                <span>{{ s.messageCount || 0 }} 条</span>
              </div>
              <span class="session-delete" title="删除会话" @click.stop="removeSession(s)">
                <el-icon><Delete /></el-icon>
              </span>
            </div>
            <div v-if="!sessionsLoading && !sessions.length" class="session-empty">暂无历史会话</div>
            <div v-else-if="!sessionsLoading && !filteredSessions.length" class="session-empty">
              没有标题包含「{{ sessionKeyword.trim() }}」的会话
            </div>
          </div>
        </div>
      </div>
    </ResizableDrawer>

    <!-- 「我的智能体」管理弹窗 -->
    <el-dialog v-model="agentMgrVisible" title="我的智能体" width="600px" append-to-body>
      <div class="agent-mgr-list">
        <div v-if="!myAgents.length" class="agent-mgr-empty">
          还没有自定义智能体。点击下方「新建智能体」创建你自己的 AI 助手（可设人设、限定工具、绑定模型）。
        </div>
        <div v-for="a in myAgents" :key="a.agentId" class="agent-mgr-item">
          <div class="agent-mgr-main">
            <div class="agent-mgr-name">{{ a.name }}</div>
            <div class="agent-mgr-desc">{{ a.description || '（无简介）' }}</div>
            <div class="agent-mgr-tools">
              工具：{{ (a.tools && a.tools.length) ? a.tools.map(t => toolLabelMap[t] || t).join('、') : '全部' }}
              <span v-if="a.model"> ｜ 模型：{{ a.model }}</span>
            </div>
          </div>
          <div class="agent-mgr-ops">
            <el-button text size="small" @click="openEditAgent(a)">编辑</el-button>
            <el-button text size="small" type="danger" @click="removeAgent(a)">删除</el-button>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="openCreateAgent">新建智能体</el-button>
        <el-button type="primary" @click="agentMgrVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 智能体 新建 / 编辑 表单 -->
    <el-dialog
      v-model="agentFormVisible"
      :title="editingAgentId == null ? '新建智能体' : '编辑智能体'"
      width="560px"
      append-to-body
    >
      <div v-if="editingAgentId == null" class="agent-form-tip">
        💡 也可以直接在下面输入框里说「帮我建一个数学老师智能体」，由「智能体专家」按对话帮你创建。
      </div>
      <el-form label-width="90px" label-position="right">
        <el-form-item label="名称" required>
          <el-input v-model="agentForm.name" maxlength="64" show-word-limit placeholder="如：数学老师" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="agentForm.description" maxlength="255" placeholder="一句话说明它的用途" />
        </el-form-item>
        <el-form-item label="人设提示词">
          <el-input
            v-model="agentForm.personaPrompt"
            type="textarea"
            :rows="4"
            maxlength="4000"
            show-word-limit
            placeholder="用英文描述这个智能体的角色与行为（会作为系统指令）。留空则仅按工具集工作。"
          />
        </el-form-item>
        <el-form-item label="可用工具">
          <el-select v-model="agentForm.tools" multiple clearable placeholder="留空 = 不限（全部工具）" style="width: 100%">
            <el-option
              v-for="t in toolOptions"
              :key="t.name"
              :label="t.label || t.name"
              :value="t.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定模型">
          <AiModelSelector v-model="agentForm.model" scene="agent-form" width="100%" :auto-default="false" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="agentFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="agentSaving" @click="saveAgent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontAgentChat' })

import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Clock, Delete, Plus, Setting,
  FolderOpened, QuestionFilled, UploadFilled, Search, View
} from '@element-plus/icons-vue'
import AiChatStream from '@/components/AiChatStream/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AgentToolResult from '@/components/AgentToolResult/index.vue'
import AgentConfirmCard from '@/components/AgentConfirmCard/index.vue'
import ChatFileUploader from '@/components/ChatFileUploader/index.vue'
import ChatAttachmentList from '@/components/ChatAttachmentList/index.vue'
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel/index.vue'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
// 工具开关清单（设置 tab）：**静态 import**，不再用 `await import()` 动态加载 ——
// 动态 import 会把「模块何时就绪」变成变量，是「刷新后先点别的 tab 再进设置，工具列表
// 不加载」这类顺序敏感 bug 的温床（用户 2026-10-10 报）。静态 import 保证函数随时可用。
import { fetchAgentToolsForUi } from '@/api/ai/agentDsFree'
import { useAgentChat, normalizeRestoredMessages } from '@/composables/useAgentChat'
import { listSessions, createSession, deleteSession, getConversationHistory, saveConversationMessages, getAgentTimeline, attachmentPlaceholder, fillAttachmentMetas } from '@/api/ai/ai'
import {
  listAgentConfigs,
  createAgentConfig,
  updateAgentConfig,
  deleteAgentConfig,
  listAgentExperts,
  setAgentExpertPref,
  setAgentExpertModel,
  showDsBridge,
  type AgentConfig,
  type AgentConfigInput,
  type AgentExpert
} from '@/api/ai/agent'
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
  send, stop, reset, resolveConfirm, whenIdle,
  // 从落库快照复原「会话累计执行统计」（指标数据保留，底部状态条已按用户要求移除）
  restoreMetrics,
  // 本轮的轮次 id（`send()` 开头生成、`turn_end` 标记里那个）：补写历史时要带上它
  currentTurnId,
  // 轮末回退（**按轮**）：状态是 `rollbackStates[turnId]`，页面只把它转交给消息流
  rollbackStates, rollbackTurn
} = useAgentChat()

/**
 * 回退**某一轮**的全部写操作 —— 用户在轮末那格点一下「回退」时调用
 *
 * 只搬不判：哪些撤掉了 / 哪些不给撤 / 为什么，全由服务端按轮次账本算出来
 * （`rollbackTurn` 把结果交给 `rollbackStates[turnId].outcome`，
 * 轮末那格显示状态、清单汇总到消息列表外的结果栏）。
 * 每一轮都能点（用户 2026-09-23 裁决），页面不替消息流判「是不是最近一轮」。
 *
 * ## ⚠️ 会话 id 必须**由页面显式传进去**（第二个实参）
 * 这里传的是**页面正在显示的那个会话**（`sessionId` 这个 ref），**不是**「最近一次 `send()`
 * 用过的会话」。composable 内部那份「最近一次发送用过的会话 id」在**刷新之后是空串**
 * （消息是从会话快照复原的，没走 `send()`），拿它去回退就会两个请求都带 `sessionId:''`：
 * 服务端按空会话过滤 → 命中 0 行、还回 200 成功 → 本地消息被摘掉、服务端历史与快照都没动
 * → **刷新一下刚回退的那一轮又全回来了**（用户 2026-09-23 报的线上 bug，根因就在这一行）。
 * 会话 id 的事实来源是「当前显示的会话」，页面手上正好有它，所以由页面传。
 *
 * 回退成功后要做两件界面上的事，都在这里做（**两个消费方各写一份，别只做一个**）：
 *   ① 一句 toast 报条数 —— 消息整轮被摘掉时，这是「刚才那一下成了」的唯一反馈；
 *   ② 把这一轮的**提问正文**回填输入框（用户要接着改一改再问）。
 *      ⚠️ 图片 / 附件**不回填**：`outcome.userText` 里只有正文。
 * ⚠️ 失败（`ok === false`，含「不知道这一轮属于哪个会话」「快照没写成功」）**不在这里报**：
 *    人话在 `outcome.reason` 里，由**轮末那一格**就地显示（`AgentTurnRollback`）——
 *    这两种失败都不摘消息，那一格还在，所以看得见。
 */
const onRollbackTurn = async (turnId: string) => {
  const r = await rollbackTurn(turnId, sessionId.value)
  if (!r) return
  if (r.ok) ElMessage.success(`已回退 ${r.reverted} 项操作`)
  if (r.ok && r.dropped && r.userText) chatRef.value?.setInputText?.(r.userText)
}

/**
 * 确认卡片回调（确认 / 取消 / 让 AI 重新生成）
 *
 * `payload` 兼容老写法：布尔 = 确认 / 取消；对象 = 可编辑草稿卡片回的
 * `{ approved, edited }` 或 `{ approved:false, regenerate, opinion }`。
 *
 * 「重新生成」：先取消当前确认（服务端据此不导入），**等本轮收尾**再发一条带修改意见的
 * 追问 —— 不能立刻发，`send()` 开头有 `isGenerating` 闸门，本轮还在跑会被直接打回。
 */
const onConfirmResolve = async (message: any, payload: any) => {
  if (payload && payload.regenerate) {
    await resolveConfirm(message.confirmId, false)
    await whenIdle()
    const opinion = String(payload.opinion || '').trim()
    if (opinion) await handleSend({ content: `请根据以下修改意见重新生成题库草稿：\n${opinion}` })
    return
  }
  await resolveConfirm(message.confirmId, payload)
}

/** 模型（scene='agent'，与聊天助手的选择互不干扰） */
const model = ref('')
// 选中的 AI 配置 id（区分同名的系统/用户模型）；由 AiModelSelector 的 @select 提供
const selectedConfigId = ref(null)
const onModelSelect = (cfg) => { selectedConfigId.value = cfg?.configId ?? null }
/** 写操作**默认自动执行**（仅删除需确认）——用户 2026-10-12 定案：取消「自动模式」开关。 */
const autoConfirm = ref(true)
/** 「注入历史上下文」按钮状态：仅「DS 免费（无浏览器）」= ds-free-nb 模型露出。 */
const injectingHistory = ref(false)
const showInjectHistory = computed(() => (model.value || '').trim() === 'ds-free-nb')

/** 「调试」按钮状态：打开当前登录态的 DS 浏览器窗口（有头），便于排查卡在哪一步。 */
const openingBridge = ref(false)
const handleOpenDsBridge = async (): Promise<void> => {
  if (openingBridge.value) return
  openingBridge.value = true
  try {
    const r = await showDsBridge()
    if (r.ok) ElMessage.success('已打开 DS 浏览器窗口（保持登录态）')
    else ElMessage.error(r.message || '打开 DS 浏览器失败（桥未运行？）')
  } finally {
    openingBridge.value = false
  }
}

/* ===================== 多智能体协同 ===================== */
// 智能体选择：官方角色 + 我的自定义智能体。
// `selectedAgentKey` 编码规则：'auto'（自动路由）/ 'official:<key>' / 'user:<agentId>'。
// 自动路由 = 后端按消息关键词选官方角色（零成本，不确定退 general）。
//
// ⚠️ 「自动」用**非空哨兵值 `'auto'`**，不用空串 `''`：Element Plus 的 `el-select` 把
//    空串 value 当作「未选中」，会忽略该 option 的 label 转而显示 placeholder ——
//    结果「自动」这一项永远显示不出来（用户 2026-10-10 报：智能体框显示「请选择」）。
//    启用哨兵值后 `value="auto"` 能被正常选中并显示 label。
const AUTO_AGENT_KEY = 'auto'
const selectedAgentKey = ref(AUTO_AGENT_KEY)
const myAgents = ref<AgentConfig[]>([])

/** 交给 `send()` 的解析结果：官方角色 key 与用户智能体 id 二选一（'auto' → 两者皆空） */
const selectedRole = computed(() => {
  const k = selectedAgentKey.value
  return k.startsWith('official:') ? k.slice('official:'.length) : ''
})
const selectedAgentId = computed(() => {
  const k = selectedAgentKey.value
  return k.startsWith('user:') ? Number(k.slice('user:'.length)) || undefined : undefined
})

/**
 * 拉取「我的智能体」（用户自建角色）
 *
 * ⚠️ 不再拉官方角色：官方"专家"已由设置面板的「专家」开关管理，下拉里再列一次
 * 与开关重复（用户 2026-10-10 反馈"智能体下拉框明显多余"）。故只拉用户自定义的。
 */
async function loadAgents() {
  myAgents.value = await listAgentConfigs()
}

/* ---- 智能体侧栏抽屉（统一容器：设置 / 知识库 / 历史会话，内部 tab 切换）---- */
// 用户 2026-10-10 裁决：三个功能的容器形态各异（设置=el-dialog、知识库/历史=各自抽屉），
// 统一到一个可拉伸抽屉 + 内部 tab；点工具栏对应按钮 → 开抽屉 + 切到对应 tab。
// 方向原则：**入口在哪侧、抽屉就从哪侧滑出**（设置按钮在右 → rtl；知识库/历史在左 → ltr）。
//
// ⚠️ 方向**只在「本次打开抽屉」时由入口侧决定一次，之后锁定**——不能随 tab 变：
//    用户 2026-10-10 反馈「在左侧点开知识库，再点智能体设置 tab，抽屉会甩到右侧，不合理」。
//    同一个抽屉在会话期内来回横跳，破坏「同一个容器」的心智。故 `panelDirection` 是 **ref
//    而非 computed**：`openPanel` 仅在「原本处于关闭态」时按入口侧设一次；抽屉已开时，
//    无论是点内部 tab 头还是点工具栏另一个按钮，都**保持当前方向不变**（只切 tab 内容）。
const panelOpen = ref(false)
const panelTab = ref<'settings' | 'kb' | 'history'>('settings')
/** 抽屉滑出方向：由「打开它的那个入口」决定并锁定（打开期间不随 tab 变） */
const panelDirection = ref<'rtl' | 'ltr'>('ltr')
/** 知识库面板实例（切到知识库 tab 时调 activate 载入） */
const kbPanelRef = ref<InstanceType<typeof KnowledgeBasePanel> | null>(null)

/** 入口侧 → 抽屉方向：设置入口在右（rtl），知识库/历史入口在左（ltr） */
const dirOfTab = (tab: 'settings' | 'kb' | 'history'): 'rtl' | 'ltr' =>
  tab === 'settings' ? 'rtl' : 'ltr'

/**
 * 进入某个 tab 时要触发的加载。
 *
 * ⚠️ 必须集中在这里，且「工具栏入口」与「抽屉内 tab 头」**都**要走它。
 * 原来的坑：加载只写在 `openPanel()`（工具栏入口）里，而抽屉 tab 头是直接
 * `panelTab = 'kb'` 赋值的 —— 于是「刷新后先点设置/历史，再点知识库」时
 * `activate()` 从没被调用，知识库永远加载不出来（用户 2026-10-16 报）。
 * 同一原理，专家列表若先点别的 tab 再进设置也会空 —— 故一并收口。
 */
function enterTab(tab: 'settings' | 'kb' | 'history') {
  if (tab === 'settings') loadExperts()
  // 知识库面板是 v-show 常驻挂载，只有显式 activate 才会拉库列表；
  // 从抽屉 tab 头直接切进来也必须触发。
  if (tab === 'kb') nextTick(() => kbPanelRef.value?.activate?.())
  // 历史会话：清掉上次的搜索词（原 watch 里的逻辑，统一到这里）
  if (tab === 'history') sessionKeyword.value = ''
}

/** 抽屉内 tab 头点击：只切 tab + 触发该 tab 的加载（方向不重算，保持打开时锁定） */
function switchTab(tab: 'settings' | 'kb' | 'history') {
  panelTab.value = tab
  enterTab(tab)
}

function openPanel(tab: 'settings' | 'kb' | 'history') {
  // 仅在「抽屉原本关闭」时按入口侧设定方向；已打开时保持当前方向（不横跳）
  if (!panelOpen.value) panelDirection.value = dirOfTab(tab)
  panelTab.value = tab
  panelOpen.value = true
  enterTab(tab)
}

/* ---- 「我的智能体」管理弹窗 ---- */
const agentMgrVisible = ref(false)
const agentFormVisible = ref(false)
const agentSaving = ref(false)
/** 编辑中的目标 id；null = 新建 */
const editingAgentId = ref<number | null>(null)
const agentForm = reactive<AgentConfigInput>({
  name: '',
  description: '',
  greeting: '',
  personaPrompt: '',
  tools: [],
  model: ''
})
/** 工具项（全量，含中文 label 与启用状态），来自 `/ai/agent/tools` —— 「我的智能体」管理页的工具多选用 */
const toolOptions = ref<Array<{ name: string; label: string; disabled: number }>>([])
/** 正在读工具清单（含「重试」那一次） */
const toolLoading = ref(false)
/** 工具清单**没取到**（网络错 / 结构异常）—— 与「取到了但一条都没有」分开表达 */
const toolLoadFailed = ref(false)
/** 工具清单请求的飞行锁（同一时刻只发一次，见 loadToolOptions） */
let _toolLoadInFlight: Promise<void> | null = null

/* ---- 专家（设置面板可开关的「专家」）----
   用户 2026-10-10 裁决：把「可用工具」（工具粒度、技术味）改成「专家」（角色粒度、用户能懂）。
   关闭某专家 = 后端指挥家通讯录里不再出现它 → LLM 实时知道叫不到。 */
const experts = ref<AgentExpert[]>([])
const expertLoading = ref(false)
const expertLoadFailed = ref(false)
const expertTogglingKey = ref('')
let _expertLoadInFlight: Promise<void> | null = null

async function loadExperts() {
  // 与 loadToolOptions 同款：飞行锁 + 加载态 + 失败态 + 空结果不覆盖旧数据
  if (_expertLoadInFlight) return _expertLoadInFlight
  expertLoading.value = true
  expertLoadFailed.value = false
  _expertLoadInFlight = (async () => {
    try {
      const list = await listAgentExperts()
      if (list.length) {
        experts.value = list
        expertLoadFailed.value = false
      } else {
        expertLoadFailed.value = experts.value.length === 0
      }
    } catch (e) {
      console.warn('[agent] 读取专家列表失败', e)
      expertLoadFailed.value = experts.value.length === 0
    } finally {
      expertLoading.value = false
      _expertLoadInFlight = null
    }
  })()
  return _expertLoadInFlight
}

/** 拨动专家开关（受控式：显示值来自服务端回值） */
async function toggleExpert(e: AgentExpert, on: boolean) {
  const want: 0 | 1 = on ? 0 : 1
  if ((e.disabled === 1 ? 1 : 0) === want) return
  expertTogglingKey.value = e.key
  try {
    const list = await setAgentExpertPref(e.key, want)
    if (list.length) experts.value = list
    ElMessage.success(want === 1 ? `已关闭「${e.name}」` : `已开启「${e.name}」`)
  } catch (err: any) {
    ElMessage.error(err?.message || `「${e.name}」没保存成功`)
  } finally {
    expertTogglingKey.value = ''
  }
}

/** 给专家绑定模型（乐观更新：失败回滚；成功用服务端回值受控刷新） */
async function onExpertModelChange(e: AgentExpert, model: string) {
  const prev = e.model || ''
  e.model = model
  try {
    const list = await setAgentExpertModel(e.key, model)
    if (list.length) experts.value = list
    ElMessage.success(model ? `「${e.name}」已绑定 ${model}` : `「${e.name}」已恢复跟随默认模型`)
  } catch (err: any) {
    e.model = prev
    ElMessage.error(err?.message || `「${e.name}」模型没保存成功`)
  }
}

/** 工具名 → 中文名（界面对照；无则回落到 name 本身） */
const toolLabelMap = computed(() => {
  const m: Record<string, string> = {}
  for (const t of toolOptions.value) m[t.name] = t.label || t.name
  return m
})

async function loadToolOptions() {
  // ⚠️ 必须有加载态 + 失败态：原先无 try/catch，失败时 `toolOptions` 落成空数组，
  //    界面永远停在「正在读取工具清单…」（用户 2026-10-10 报的 bug：从知识库/历史
  //    切到设置后工具一直转圈）。参考 `AgentToolPopover` 的成熟口径——显式 loading +
  //    「取不到」单独表达 + 可重试，且「取到了但一条都没有」与「没取到」不能说成同一句话。
  //
  // ⚠️ 飞行锁（`_toolLoadInFlight`）：多个入口（onMounted 预取 / 点设置 / 点重试）可能
  //    同时触发。并发多次请求不仅浪费，返回顺序还可能让"后发先至"的空结果盖掉已有数据。
  //    共享同一个飞行中的 Promise，保证同一时刻只有一次请求。
  if (_toolLoadInFlight) return _toolLoadInFlight
  toolLoading.value = true
  toolLoadFailed.value = false
  _toolLoadInFlight = (async () => {
    try {
      // 静态 import（见顶部），不用动态 import —— 避免"模块就绪时机"变成顺序敏感变量
      const payload: any = await fetchAgentToolsForUi()
      const list = Array.isArray(payload?.tools) ? payload.tools : []
      const mapped = list
        .map((t: any) => ({
          name: t?.function?.name || t?.name || '',
          label: t?.label || t?.descriptionZh || t?.function?.name || t?.name || '',
          disabled: t?.disabled === 1 ? 1 : 0
        }))
        .filter((t: any) => t.name)
      if (mapped.length) {
        // 拿到数据才覆盖；空结果不覆盖已有列表（网络抖动不该把已显示的工具清空）
        toolOptions.value = mapped
        toolLoadFailed.value = false
      } else {
        // 后端注册表不可能为空 ⇒ 空数组即「没取到」；保留旧数据、标失败供重试
        toolLoadFailed.value = toolOptions.value.length === 0
      }
    } catch (e) {
      console.warn('[agent] 读取工具清单失败', e)
      // 失败**不清空**已有列表（保留上次成功结果），仅标失败供重试
      toolLoadFailed.value = toolOptions.value.length === 0
    } finally {
      toolLoading.value = false
      _toolLoadInFlight = null
    }
  })()
  return _toolLoadInFlight
}

function openAgentManager() {
  agentMgrVisible.value = true
  loadToolOptions()
}

function openCreateAgent() {
  editingAgentId.value = null
  Object.assign(agentForm, { name: '', description: '', greeting: '', personaPrompt: '', tools: [], model: '' })
  agentFormVisible.value = true
}

function openEditAgent(a: AgentConfig) {
  editingAgentId.value = a.agentId
  Object.assign(agentForm, {
    name: a.name,
    description: a.description || '',
    greeting: a.greeting || '',
    personaPrompt: a.personaPrompt || '',
    tools: [...(a.tools || [])],
    model: a.model || ''
  })
  agentFormVisible.value = true
}

async function saveAgent() {
  if (!agentForm.name || !agentForm.name.trim()) {
    ElMessage.warning('请填写智能体名称')
    return
  }
  agentSaving.value = true
  try {
    const body: AgentConfigInput = {
      name: agentForm.name.trim(),
      description: agentForm.description || '',
      greeting: agentForm.greeting || '',
      personaPrompt: agentForm.personaPrompt || '',
      // 空数组 = 不限制；显式传数组让后端按白名单处理
      tools: agentForm.tools || [],
      model: agentForm.model || ''
    }
    if (editingAgentId.value == null) {
      await createAgentConfig(body)
      ElMessage.success('智能体已创建')
    } else {
      await updateAgentConfig(editingAgentId.value, body)
      ElMessage.success('智能体已更新')
    }
    agentFormVisible.value = false
    await loadAgents()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    agentSaving.value = false
  }
}

async function removeAgent(a: AgentConfig) {
  try {
    await ElMessageBox.confirm(`确定删除智能体「${a.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAgentConfig(a.agentId)
    ElMessage.success('已删除')
    // 若删除的正是当前选中的，回落到「自动」
    if (selectedAgentKey.value === `user:${a.agentId}`) selectedAgentKey.value = AUTO_AGENT_KEY
    await loadAgents()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}


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
const sessions = ref<any[]>([])
const sessionsLoading = ref(false)
const sessionId = ref('')

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
  panelOpen.value = false
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
 * 优先用「完整时间线快照」（含工具卡片 + 会话执行统计）；没有快照的老会话退回
 * `ai_chat_message`（只能复原「提问 + 最终回复」两行）。
 */
const loadHistory = async (sid: string) => {
  if (!sid) return
  try {
    // 优先用「完整时间线快照」复原（含工具卡片 + 会话执行统计）—— 否则刷新后只剩纯文本问答
    const tl: any = await getAgentTimeline(sid, userId.value)
    const tlMsgs = tl?.data?.messages
    // 会话累计执行统计从快照复原（老会话无统计 → 归零，与升级前一致）
    restoreMetrics(tl?.data?.metrics ?? null)
    if (Array.isArray(tlMsgs) && tlMsgs.length) {
      // 快照里可能有「一轮没跑完」留下的悬空卡片（未收口的确认 / 转圈的工具卡）——
      // 复原前统一收口，否则刷新后会冒出一张能点却没人应答的确认卡。
      messages.value = normalizeRestoredMessages(tlMsgs)
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
  panelOpen.value = false
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

const handleSend = async ({ content, injectHistory = false }: { content: string; injectHistory?: boolean }) => {
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
    // configId：精确指定选中哪条配置（区分同名的系统/用户模型）
    configId: selectedConfigId.value || undefined,
    sessionId: sessionId.value,
    userId: userId.value,
    autoConfirm: autoConfirm.value,
    // 多智能体协同：选了「我的智能体」传 agentId（优先），选了官方角色传 role；
    // 都没选（'' = 自动）传空 → 后端按消息规则路由。
    role: selectedRole.value || undefined,
    agentId: selectedAgentId.value,
    // 仅 ds-free-nb：把当前会话历史作为附件投递给 DS 网页
    injectHistory,
  })

  /**
   * 本轮的轮次 id —— **必须在 `await send(...)` 返回后、在下面那个 `await metasReady` 之前**抓在手里。
   *
   * 为什么非传不可：`ai_chat_message.turn_id` 是 `POST /ai/conversation/drop-turn` 的**唯一命中键**
   * （服务端按 `(user_id, session_id, turn_id)` 删这一轮）。下面这条补写以前不带它 →
   * 落库的行 `turn_id` 是空串 → 用户点回退时服务端**一行都匹配不到**、还回 `code:200`
   * （`dropped: 0`），界面却把消息摘了、快照也重写 → 刷新一次这一轮又回来
   * （用户 2026-09-23 报的「回退以后刷新，刚刚回退的对话内容还是存在」的第二半）。
   * ⚠️ 必须是**这一轮**的 id，不许自己再生成一个：`send()` 开头就把 `currentTurnId`
   * 置成了本轮 id，`await send(...)` resolve 时它的 `finally`（push `turn_end` 标记）已经跑完，
   * 所以此刻取到的与轮末标记里的 `turnId` **逐字相同** —— 生成一个新的就与标记对不上，回退照样匹配不到。
   * ⚠️ 先抓成局部量再进 `await`：下面的补写是在 `await metasReady` 之后才发请求的，
   * 中间隔着一次 await，那时 `currentTurnId` 万一被下一次 `send()` 换掉了就传错轮次。
   */
  const turnIdOfThisSend = String(currentTurnId.value || '')

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
          attachments: metas.map((a) => ({ ...a })),
          // 这一轮的轮次标记：服务端靠它把「提问 + 回复」两行按轮找出来（见上面的说明）
          turnId: turnIdOfThisSend
        },
        userId.value
      )
    } catch (e) {
      console.warn('[agent] ds-free 历史落库失败', e)
    }
  }

  // 新会话的第一轮之后，后端才把标题写进去 → 刷新列表
  loadSessions()
  // 这一轮里「智能体专家」可能刚用 agent_manage 创建/改了智能体 →
  // 刷新「我的智能体」列表，否则新建的智能体要等重进页面才出现（用户 2026-10-12 报）。
  loadAgents()
}

/**
 * 「注入历史上下文」按钮（**一次性操作**，仅 ds-free-nb）：
 * 点击 → 把说明文字**自动填进输入框**，随即**自动发送**（走与手打完全相同的发送路径）。
 * 后端据 injectHistory=true 把当前会话历史拼进正文、并让桥把正文作为 .md 附件投递给 DS 网页。
 */
const INJECT_HISTORY_MSG =
  '以下附件是本会话的历史对话上下文。请阅读该附件，理解我们已经聊过的内容，然后等待我的下一条指令。'
const handleInjectHistory = async (): Promise<void> => {
  if (injectingHistory.value || isGenerating.value) return
  if (!sessionId.value || !messages.value.some((m) => m.role === 'user' || m.role === 'assistant')) {
    ElMessage.info('当前会话还没有历史内容可注入（先聊几句再注入）')
    return
  }
  injectingHistory.value = true
  try {
    // 1) 填进输入框（用户可见，与手打一致）
    chatRef.value?.setInputText?.(INJECT_HISTORY_MSG)
    await nextTick()
    // 2) 自动发送（走正常发送路径；带 injectHistory 标记）
    await handleSend({ content: INJECT_HISTORY_MSG, injectHistory: true })
    // 3) 清空输入框（正常发送后 ChatInputArea 会自清；这里直呼 handleSend 绕过了它，手动清）
    chatRef.value?.setInputText?.('')
    ElMessage.success('已把历史上下文作为附件注入给 DS 网页')
  } catch (e) {
    console.error('[inject-history] 失败', e)
    ElMessage.error('注入历史上下文失败')
  } finally {
    injectingHistory.value = false
  }
}

/* ===================== 生命周期 ===================== */
onMounted(async () => {
  // 智能体清单（官方角色 + 我的智能体）：不阻塞会话加载，失败静默降级
  loadAgents()
  // ⚡ 进页面即**预取**专家清单：不管用户先点哪个 tab（设置 / 知识库 / 历史），
  //   进设置时都已在手，彻底消除"刷新后先点别的 tab 再进设置，列表不加载"这类顺序敏感问题
  //   （用户 2026-10-10 报）。飞行锁保证与后续 openPanel 的调用不重复请求。
  loadExperts()
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
/* 智能体侧栏抽屉（统一容器）：tab 条 + 内容区铺满抽屉 */
.agent-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}

/* tab 条：与工具栏三个入口一一对应 */
.agent-panel-tabs {
  flex-shrink: 0;
  display: flex;
  gap: 4px;
  padding: 8px 10px;
  border-bottom: 1px solid #eef2f7;
}
.aptab {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  height: 32px;
  border-radius: 8px;
  font-size: 13px;
  color: #6b7280;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s ease, color 0.15s ease;

  &:hover {
    background: #f3f5f9;
  }
  &.active {
    background: #eef4ff;
    color: #2563eb;
    font-weight: 600;
  }
}

/* 各 tab 内容：铺满剩余高度、内部自管滚动 */
.agent-panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 历史会话 tab：搜索 + 计数 + 列表 纵向排列 */
.session-drawer {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.session-count-line {
  flex-shrink: 0;
  padding: 6px 12px 2px;
  font-size: 12px;
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

/* 输入框旁的模型下拉框：与工具行的图标按钮垂直居中对齐 */
.tb-model {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
}

/* 带**文字**的工具按钮（注入历史 / 调试）：不能沿用 `.tb-btn` 的固定 28px 方框
   —— 那会把它压成竖排单字（用户 2026-10-12 截图反馈）。这里改成自适应宽度、横向排列。 */
.tb-btn.tb-inject {
  width: auto;
  height: 28px;
  padding: 0 10px;
  gap: 4px;
  font-size: 12px;
  white-space: nowrap;

  /* 图标与文字都随 `currentColor`，hover 一起变色 */
  :deep(.el-icon) {
    font-size: 14px;
  }
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

/* 「新对话」：底部工具栏右侧，观感压得比 el-button 默认更轻 */
.tb-new {
  font-size: 13px;
  color: #6b7280;

  &:hover {
    color: #2563eb;
    background: #f3f5f9;
  }
}

/* ── 「设置」面板（合并：智能体 / 模型 / 可用工具）──
   用户 2026-10-09 裁决：底部工具栏过密（9 个控件），把配置类三件套收进本面板。
   用户 2026-10-10 反馈「输入框贴边框、空白多」→ 加内边距、限制单列最大宽度、收紧行距。 */
.settings-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  /* 与抽屉内壁留出呼吸感：原先内容直接贴边，输入框会顶到 tab 栏/滚动条 */
  padding: 18px 20px 24px;
  /* 面板较宽（可拉伸）时，表单不至于被拉得过散 */
  max-width: 560px;
}
.settings-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.settings-label {
  font-size: 13px;
  color: #606266;
  font-weight: 600;
}
/* 标签 + 右侧操作入口同一行：把「查看/选择」与「管理」收在一个区块里 */
.settings-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.settings-label-row .el-button {
  padding: 0;
  height: auto;
  font-weight: 400;
}
.settings-field {
  min-width: 0;
}
.settings-hint {
  font-size: 12px;
  color: #b0b6c0;
  margin-top: 6px;
  line-height: 1.6;
}
.settings-tools {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #eef0f4;
  border-radius: 8px;
  padding: 4px 12px;
}
.settings-tools-error {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #b45309;
  padding: 8px 10px;
  background: #fffaf0;
  border: 1px solid #f5e2c8;
  border-radius: 8px;
}
.agent-form-tip {
  margin-bottom: 12px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #4f46e5;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 8px;
}
.settings-tool {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f4f6f9;

  &:last-child {
    border-bottom: none;
  }
}
.settings-tool-name {
  font-size: 13px;
  color: #303133;
}
/* 专家项：名称 + 一句话说明两行，右侧开关顶对齐 */
.settings-expert {
  align-items: flex-start;
}
.settings-expert-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.settings-expert-desc {
  font-size: 12px;
  color: #9aa5b5;
  line-height: 1.5;
}
.settings-expert-model {
  margin-top: 6px;
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

/* ---- 我的智能体管理弹窗 ---- */
.agent-mgr-list {
  max-height: 380px;
  overflow-y: auto;
}
.agent-mgr-empty {
  color: #909399;
  font-size: 13px;
  line-height: 1.7;
  padding: 8px 0;
}
.agent-mgr-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #eef0f4;
  border-radius: 8px;
  margin-bottom: 8px;
}
.agent-mgr-name {
  font-weight: 600;
  color: #303133;
}
.agent-mgr-desc {
  font-size: 12.5px;
  color: #909399;
  margin-top: 2px;
}
.agent-mgr-tools {
  font-size: 12px;
  color: #b0b6c0;
  margin-top: 4px;
}
.agent-mgr-ops {
  flex-shrink: 0;
}
</style>
