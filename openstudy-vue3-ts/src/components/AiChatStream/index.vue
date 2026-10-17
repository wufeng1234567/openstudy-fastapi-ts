<template>
  <div class="ai-chat-stream">
    <!-- 消息列表 -->
    <div class="chat-messages" ref="messagesRef">
      <!-- 空状态插槽 -->
      <slot name="empty" v-if="messages.length === 0 && !isGenerating"></slot>

      <!-- 更早的历史（默认不渲染，点按钮逐段回溯，避免超长历史把 DOM 撑爆导致卡顿） -->
      <div v-if="hasEarlier" class="load-earlier">
        <button type="button" class="load-earlier-btn" @click="loadEarlier">
          加载更早的消息（还有 {{ messages.length - visibleMessages.length }} 条）
        </button>
      </div>

      <!--
        `data-msg-idx` 是「提问目录」（AgentOutline）的锚点：
        右侧导航按序号定位到某条消息，滚动时也靠它反查当前在第几条。
        用绝对序号（windowOffset + idx），与可见窗口无关，回溯加载后依然对得上。
      -->
      <div
        v-for="(msg, idx) in visibleMessages"
        :key="windowOffset + idx"
        :data-msg-idx="windowOffset + idx"
        :class="['message', msg.role, msg.type ? 'msg-' + msg.type : '']"
      >
        <!-- 工具确认卡片 -->
        <div v-if="msg.type === 'tool_confirm'" class="message-content">
          <slot name="tool-confirm" :message="msg" :index="idx">
            <div class="message-text">{{ msg.content }}</div>
          </slot>
        </div>
        <!-- 工具执行结果 -->
        <div v-else-if="msg.type === 'tool_result'" class="message-content">
          <slot name="tool-result" :message="msg" :index="idx">
            <div class="message-text">{{ msg.content }}</div>
          </slot>
        </div>
        <!--
          思考态（深度思考）—— **不暴露推理正文**，只渲染一个等待动画。
          用户 2026-10-11：「深度思考的思维链不再暴露，改成更好的等待动画效果」。
          api 付费链路（LangChain 补丁）与 ds-free 链路都可能产出 `type:'reasoning'`；
          其 `content` 现在恒为空（`useAgentChat` 不再累积），只靠 `secs` 区分「跑/收口」。
          ⚠️ 2026-10-17：不再挂 `AGENT` 角色标签 —— 整条消息流只保留内容本身（DSH 的简洁形态）。
        -->
        <div v-else-if="msg.type === 'reasoning'" class="message-content">
          <AgentReasoning :content="msg.content" :secs="msg.secs" />
        </div>
        <!--
          「等待中」占位（三点抖动）
          ⚠️ 这是 `type:'thinking'`，和上面的 `reasoning` **不是一回事**：
             · thinking  = 还没有内容时的占位，`content` 是一句状态文案（「正在理解你的需求…」）
             · reasoning = 深度思考的**推理正文**，可折叠
             两者都由 `useAgentChat` 维护，别合并。
        -->
        <!--
          处理进度清单（`type:'progress'`）——**全站唯一的等待态**。
          用户 2026-10-17：原来「思考中」和「正在处理工具结果」两个提示同时出现、语义重复，
          现在只保留这一条：一行灰点 + 当前步骤文案；多步骤时显示为清单。
          （`type:'thinking'` 不再由 useAgentChat 生成，见那边注释；这里仍保留兜底渲染，
           万一老快照里存着 thinking 消息也不会白屏。）
        -->
        <div v-else-if="msg.type === 'progress' || msg.type === 'thinking'" class="message-content is-plain wait-row">
          <div class="agent-thinking">
            <span class="agent-thinking__dots" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="agent-thinking__text">{{ progressHeadline(msg) }}</span>
          </div>
          <ul v-if="msg.steps && msg.steps.length > 1" class="progress-steps">
            <li
              v-for="step in msg.steps"
              :key="step.id"
              :class="['progress-step', 'step-' + step.state]"
            >
              <span class="step-icon">
                <span v-if="step.state === 'running'" class="step-spinner" aria-hidden="true"></span>
                <span v-else-if="step.state === 'done'" class="step-check">✓</span>
                <span v-else class="step-fail">✕</span>
              </span>
              <span class="step-text">{{ step.message }}</span>
            </li>
          </ul>
        </div>
        <!--
          Agent 过程提示（自我纠正 / 警告 / 错误）
          只有智能体链路会产出 type='agent_note'，别的调用方不会走到这个分支。
        -->
        <div v-else-if="msg.type === 'agent_note'" class="message-content">
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
        <!--
          轮末动作条（`type:'turn_end'`）—— 每一轮的最后一条，回退 / 复制两个按钮就挂在这一格
          （用户裁决：回退组件的位置是「轮末」，即消息列表里那一轮的最后一条消息下面）。

          ⚠️ 这个分支**必须排在下面 `msg.role === 'assistant'` 那个正文分支之前**。
             `turn_end` 的 `role` 也是 assistant（`useAgentChat` 每轮 push 的那条标记），
             排在正文分支后面就永远轮不到它 —— 整条标记会掉进正文分支里渲染成一个
             **空白的「Agent」气泡**，每轮多一个。L69 守的就是这个顺序。
          ⚠️ 这一格**不带 `.message-content`**：里面只有一条轻量的动作行，
             带上气泡类名就等于给每一轮末尾加一张空白卡片（高度与间距见
             `.message.msg-turn_end` 与 `AgentTurnRollback` 自己的样式）。
          ⚠️ `:state` 必须**按轮**取（`rollbackStates[msg.turnId]`）：每一轮都能点回退，
             一份「最近一次回退」的扁平状态存不下两轮的结果（前一轮的结果会被后一轮覆盖，
             而两格的组件都还在）。L81 断的就是这个。
        -->
        <div v-else-if="msg.type === 'turn_end'" class="turn-end-slot">
          <AgentTurnRollback :turn-id="msg.turnId" :state="rollbackStates[msg.turnId] || null"
            :answer-text="turnAnswerText(msg.turnId)" :disabled="isGenerating"
            @rollback="$emit('rollback-turn', msg.turnId)" @copy="copyText($event)" />
        </div>
        <!--
          专家工作组（多专家并行干活）：一行一个专家。
          · 进行中=转圈、完成/失败=对勾/叉；**默认只显专家名 + 任务摘要（截断）**，保持干净；
          · 点某行**展开看该专家的结论详情**（默认收起，符合"思维链默认不显示、想看可点开"）；
          · 用户始终只看到这一张卡，专家不直接对用户发言（结果由主助手整合后另出正文）。
        -->
        <div v-else-if="msg.type === 'experts'" class="message-content">
          <div class="expert-group">
            <div class="expert-group-title">
              <el-icon class="eg-icon"><Connection /></el-icon>
              <span>{{ expertGroupTitle(msg.experts) }}</span>
            </div>
            <div v-for="(ex, ei) in (msg.experts || [])" :key="ei"
              :class="['expert-row', 'ex-' + ex.status]">
              <div class="expert-row-head" @click="toggleExpert(msg, ei)">
                <span class="expert-state">
                  <span v-if="ex.status === 'running'" class="expert-spin"></span>
                  <el-icon v-else-if="ex.status === 'ok'" class="expert-ok"><Select /></el-icon>
                  <el-icon v-else class="expert-fail"><CloseBold /></el-icon>
                </span>
                <span class="expert-name">{{ ex.name }}</span>
                <!--
                  收起态也要"看得见内容"：原来没有 summary 时这里显示「已完成」，
                  用户完全看不出专家答了什么（2026-10-17 报「专家的输出看不见」）。
                  现在：优先显示结论摘要，真的没结论才说「已完成（无结论）」，把异常显性化。
                -->
                <span class="expert-task">
                  <template v-if="ex.status === 'running'">{{ ex.progress || '正在处理…' }}</template>
                  <template v-else>{{ expertHeadline(ex) }}</template>
                </span>
                <el-icon class="expert-caret" :class="{ open: isExpertOpen(msg, ei) }"><ArrowDown /></el-icon>
              </div>
              <!--
                ⚠️ 进行中**默认收起**（用户 2026-10-16 报「自动展开占地太大、视觉差」）：
                默认只显示「正在调用 XX…」这一句最关键的信息（`ex.progress` 已在上面任务行），
                步骤明细要点一下 caret 才展开。展开后也只保留**工具类**步骤，把「第 N 轮思考」
                这类内部噪声滤掉 —— 用户看不懂、也不需要看。
              -->
              <div v-if="isExpertOpen(msg, ei) && ex.status === 'running' && visibleSteps(ex).length" class="expert-steps">
                <div v-for="(st, si) in visibleSteps(ex)" :key="si" class="expert-step">
                  <span :class="['expert-step-dot', 'sd-' + stepState(st)]"></span>
                  <span class="expert-step-text">{{ st.message }}</span>
                </div>
              </div>
              <div v-if="isExpertOpen(msg, ei)" class="expert-detail">
                <div v-if="ex.task" class="expert-detail-block">
                  <div class="ed-label">交给它的任务</div>
                  <div class="ed-text">{{ ex.task }}</div>
                </div>
                <div class="expert-detail-block">
                  <div class="ed-label">它的结论</div>
                  <div class="ed-text">{{ ex.status === 'running' ? '正在处理…' : (ex.summary || '（无输出）') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <!-- 普通 assistant 消息 -->
        <div class="message-content is-plain" v-else-if="msg.role === 'assistant'">
          <!--
            ⚠️ 正文**不要**绑点击复制：回答里点一下（想看链接、想选中一段、误触）
            就会把整段复制走 + 弹「复制成功」，很打扰。复制只走下面这个按钮。
          -->
          <div class="message-text rendered-md" v-html="renderAgentMarkdown(msg.content)">
          </div>
          <!--
            ⚠️ 2026-10-17：正文末尾那个「思考中…」呼吸提示已删除。
            它和进度行的"正在处理…"是**同一件事的两个 UI**，叠在一起就是用户看到的
            "两个等待提示"。现在全站只有一条等待态（见上面 type:'progress' 分支）。
          -->
          <el-button class="msg-copy-btn" size="small" text @click="copyText(msg.content)"
            v-if="msg.content && msg.content.trim()">
            <el-icon>
              <CopyDocument />
            </el-icon>
            <span class="mc-label">复制</span>
          </el-button>
          <div v-if="isGenerating && (!msg.content || msg.content.trim() === '') && isLastAssistantEmpty(idx)" class="ai-loading-inline">
            <LoadingDots size="small" :label="loadingText" />
          </div>
        </div>
        <!-- user 消息 -->
        <div class="message-content" v-else>
          <!-- 已发送的附件（图片可点击放大，文档显示扩展名） -->
          <ChatAttachmentList v-if="msg.attachments && msg.attachments.length" :items="msg.attachments" compact />
          <div v-if="msg.content" class="message-text">{{ msg.content }}</div>
          <!--
            用户消息的复制按钮（用户 2026-09-23 要求：LLM 那边和用户那边都要有复制按钮）。
            复制的是**这一条用户消息的 `content`**（不是整轮、也不是附件）；
            样式与 LLM 那侧共用 `.msg-copy-btn`（同一个观感，不留第二套）。
          -->
          <el-button v-if="msg.content && msg.content.trim()" class="msg-copy-btn" size="small" text
            @click="copyText(msg.content)">
            <el-icon>
              <CopyDocument />
            </el-icon>
            <span class="mc-label">复制</span>
          </el-button>
        </div>
      </div>
    </div>

    <!--
      回退结果栏 —— **在消息列表之外**（`.chat-messages` 的兄弟节点，见下面那段注释）。
      `rollbackStates` 里任何一轮带清单（没退成 / 只退一部分 / 报错）、或是「服务端历史里
      没有这一轮标记」的老数据时出现，可关闭；下一条新结果进来时自动重新出现
      （`noticeSignature`）。
    -->
    <AgentRollbackNotice v-if="rollbackNotices.length && !noticeClosed" :entries="rollbackNotices"
      @close="noticeClosed = true" />

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
import { CopyDocument, Connection, Select, CloseBold, ArrowDown } from '@element-plus/icons-vue'
import { renderAgentMarkdown } from '@/utils/markdown'
import LoadingDots from '@/components/LoadingDots/index.vue'
import AgentReasoning from '@/components/AgentReasoning/index.vue'
import AgentTurnRollback from '@/components/AgentTurnRollback/index.vue'
import AgentRollbackNotice from '@/components/AgentRollbackNotice/index.vue'
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
  scrollButtonBottom: { type: Number, default: 16 },
  /**
   * **按轮**的回退状态（`useAgentChat` 的 `rollbackStates`）：`{ [turnId]: { status, outcome } }`。
   *
   * ⚠️ 必须是按轮的**记录**，不是一份「最近一次回退」的扁平状态（旧版就是那样）：
   *    每一轮都能点回退，扁平状态存不下两轮的结果 —— 用户先撤第 1 轮、再撤第 2 轮，
   *    第 1 轮的组件会跟着显示第 2 轮的结果，而它自己那格的消息早就不在了。
   *
   * 本组件只把它**转交**给轮末那格的 `AgentTurnRollback`，自己不解析、不兜底 ——
   * 触发回退走 `rollback-turn` 事件，由调用方用**同一个 composable** 的 `rollbackTurn` 调接口
   * （回退语义只在服务端一处，见 `src/api/ai/agent.ts` 的 `rollbackAgentTurn`）；
   * 逐条清单则汇总到消息列表**之外**的 `AgentRollbackNotice`（见下方注释）。
   */
  rollbackStates: { type: Object, default: () => ({}) }
})

// 等待文案：深度思考时显示「深度思考中」（配合共用的三点抖动组件）
const loadingText = computed(() => (props.thinking ? '深度思考中' : 'AI 思考中'))

/**
 * 等待行的主文案（全站唯一的等待态）
 * ---------------------------------
 * 优先级：进行中的步骤 > 最后一条步骤 > 通用文案。
 * 目标：用户一眼看到"它现在在做什么"，而不是一句抽象的"思考中"。
 */
function progressHeadline(msg: any): string {
  const steps: any[] = Array.isArray(msg?.steps) ? msg.steps : []
  if (steps.length) {
    const running = steps.find((s) => s.state === 'running')
    if (running?.message) return String(running.message)
    const last = steps[steps.length - 1]
    if (last?.message) return String(last.message)
  }
  return msg?.content || '正在处理…'
}

/**
 * 专家工作组各行的**展开态**（默认收起 → 符合"专家思维链默认不显示、想看可点开"）。
 *
 * key = `${消息下标}:${行下标}`：消息只 append、下标稳定，用它做 key 足够；
 * 刷新后消息整份重建 → 展开态重置（收起），符合"默认不看"的预期。
 */
const expertOpen = ref<Set<string>>(new Set())
const expertKey = (msg: any, rowIdx: number) => {
  const mi = (props.messages as any[]).indexOf(msg)
  return `${mi}:${rowIdx}`
}

/**
 * 专家行是否展开
 * --------------
 * 默认策略（2026-10-17 调整）：
 *   · **进行中** → 收起。只显示「正在调用 XX…」，避免多个专家同时展开占满屏幕
 *     （用户 2026-10-16 明确反馈过"自动展开占地太大"）；
 *   · **已完成且有结论** → **自动展开**。用户看专家卡的目的就是看结论；
 *     以前一律收起，结论只藏在折叠区里，用户会以为"专家的输出不见了"。
 *   · 用户手动点过的，以用户的操作为准（下面 `expertUserToggled` 记录）。
 */
const expertUserToggled = ref<Set<string>>(new Set())

/**
 * 专家行收起时那行摘要
 * --------------------
 * 以前是 `ex.summary || '已完成'`：没结论时显示「已完成」，等于什么都没说，
 * 用户会以为"专家没输出"。现在把三种情况分开：
 *   · 有结论   → 结论首段（单行省略，hover 可看全文）
 *   · 失败     → 「执行失败」+ 原因首句
 *   · 成功但空 → 「已完成（没有返回结论）」—— 让异常一眼可见，而不是伪装成正常
 */
const expertHeadline = (ex: any) => {
  const s = String(ex?.summary || '').replace(/\s+/g, ' ').trim()
  if (ex?.status === 'fail') return s ? `执行失败：${s}` : '执行失败'
  if (s) return s
  return ex?.status === 'ok' ? '已完成（没有返回结论）' : '已完成'
}

const isExpertOpen = (msg: any, rowIdx: number) => {
  const k = expertKey(msg, rowIdx)
  if (expertUserToggled.value.has(k)) return expertOpen.value.has(k)
  const ex = (msg?.experts || [])[rowIdx]
  const done = ex && ex.status && ex.status !== 'running'
  return !!(done && String(ex.summary || '').trim())
}

const toggleExpert = (msg: any, rowIdx: number) => {
  const k = expertKey(msg, rowIdx)
  const s = new Set(expertOpen.value)
  // 首次点击：从"当前实际可见状态"取反，避免默认展开时点一下变成"又展开"
  const nowOpen = isExpertOpen(msg, rowIdx)
  if (nowOpen) s.delete(k)
  else s.add(k)
  expertOpen.value = s
  const t = new Set(expertUserToggled.value)
  t.add(k)
  expertUserToggled.value = t
}

/**
 * 展开时展示的步骤：只留**工具类**（`tool_call` / `tool_result` / `error`），滤掉
 * `round`（「第 N 轮思考」）与 `start`（「开始处理任务」）这类内部噪声 ——
 * 用户只关心「它在调什么工具、成没成」，不关心子代理内部思考了几轮。
 */
const visibleSteps = (ex: any) => {
  const all = Array.isArray(ex?.steps) ? ex.steps : []
  const kept = all.filter((st: any) => ['tool_call', 'tool_result', 'error'].includes(String(st?.phase || '')))
  const src = kept.length ? kept : all
  return src.slice(-4)
}

/** 步骤状态 → 圆点配色：`error` 或 `success:false` 记失败，`success:true` 记完成，其余进行中 */
const stepState = (st: any) => {
  if (st?.phase === 'error' || st?.success === false) return 'fail'
  if (st?.success === true) return 'ok'
  return 'running'
}

/**
 * 工作组标题：还在跑 → 「专家协同中（N 位）」；全部结束 → 「专家协同完成（N 位）」。
 * 避免专家已全做完、标题却还挂着「协同中」自相矛盾。
 */
const expertGroupTitle = (experts: any) => {
  const list = Array.isArray(experts) ? experts : []
  const n = list.length
  const running = list.some((e: any) => e?.status === 'running')
  return running ? `专家协同中（${n} 位）` : `专家协同完成（${n} 位）`
}

const emit = defineEmits([
  'update:messages',
  'send',
  'stop',
  'toggle-pause',
  'update:mode',
  'new-session',
  /** 点「回退」时抛给调用方（载荷 = 那一轮的 `turnId`），由页面调 `rollbackTurn()` */
  'rollback-turn'
])

/**
 * 这一轮 LLM 的回复正文（轮末「复制」按钮复制的内容）
 *
 * 组成：该轮 `turn_end` 标记**之前**、上一条 `turn_end` 标记**之后**的那些
 * assistant **正文**消息的 `content` 拼起来（用空行分隔）。
 *   · 工具卡片（`tool_confirm` / `tool_result`）、过程提示（`agent_note`）、思考块
 *     （`reasoning`）、等待占位（`thinking`）都**不是正文**，不参与 —— 用户要的是
 *     「这一轮 LLM 的回复」，把执行过程一起塞进剪贴板等于给了一份谁都不想读的日志。
 *   · 一轮里可能有多条正文（模型先答一句、调完工具再补一段）→ 全部按顺序收进来。
 *
 * ⚠️ 判据落在 `props.messages` 上（而不是某一轮的局部缓存）：刷新 / 切会话后消息是
 *    整份重新填进来的，只有从这份清单回溯才拿得到同一轮的正文。
 */
const turnAnswerText = (turnId: string | number | undefined) => {
  const list: any[] = props.messages as any[]
  let end = -1
  for (let i = list.length - 1; i >= 0; i--) {
    const m = list[i]
    if (m && m.type === 'turn_end' && String(m.turnId) === String(turnId)) {
      end = i
      break
    }
  }
  if (end < 0) return ''
  const parts: string[] = []
  for (let i = end - 1; i >= 0; i--) {
    const m = list[i]
    // 上一条轮末标记 = 上一轮的边界（到这儿就停，别把上一轮的回答也算进来）
    if (m && m.type === 'turn_end') break
    if (m && m.role === 'assistant' && !m.type && String(m.content || '').trim()) {
      parts.unshift(String(m.content))
    }
  }
  return parts.join('\n\n')
}

/**
 * 回退结果栏的内容：`rollbackStates` 里**带清单**的那些轮，外加「老数据」那一轮
 *
 * 为什么这一栏长在消息列表**之外**：回退成功时 `useAgentChat` 会把那一轮的消息整轮摘掉，
 * 挂在轮末的组件跟着一起下线 —— 结果画在那一格上等于没画（用户只看到消息少了一段，
 * 「哪一条没退成、为什么」全丢了）。所以逐条清单一律汇总到列表外面的
 * `AgentRollbackNotice`（可关闭、不会被删）。
 *
 * 没有可展示的东西（没退成 / 只退一部分 / 报错）时这一栏整块不出现 ——
 * 「一切顺利」有一句 toast 就够了，不必常驻一块「没有异常」的牌子。
 *
 * ⚠️ **但「老数据」不是「一切顺利」**：服务端历史里这一轮没有轮次标记时
 *    （`historyMatched === 0`：按 `(user_id, session_id, turn_id)` **不看 `del_flag`** 命中 0 行），
 *    历史那侧删不掉、界面上却已经移除了 —— 用户看到「消息没了、历史里还在」只会以为回退没生效。
 *    所以这一轮**也要进结果栏**（提示那一行画在 `AgentRollbackNotice` 里）。
 *    ⚠️ 这里只判**核心那一条**（`ok === true && historyMatched === 0`），必须与
 *       `AgentRollbackNotice.historyUnmarked` 的这一步**一致** —— 改一处必须改另一处。
 *       那个函数在此之上还核了「一行都没删（`dropped` 是行数时）」，只是防止说假话的
 *       sanity check；两边**不能**出现「一边判进、另一边判不进」的分叉。
 */
const rollbackNotices = computed(() => {
  const map: any = props.rollbackStates || {}
  const out: Array<{ turnId: string; outcome: any }> = []
  for (const [turnId, st] of Object.entries<any>(map)) {
    const o = st && st.outcome
    if (!o) continue
    // 「老数据」：服务端历史里没有这一轮的轮次标记（理由见上面那段注释）
    const unmarked = o.ok === true && Number(o.historyMatched) === 0
    if (!(o.skipped?.length || o.failed?.length || o.partial?.length || unmarked)) continue
    out.push({ turnId, outcome: o })
  }
  return out
})

/**
 * 结果栏的「身份」：内容变了（又撤了一轮 / 同一轮重试出了新清单 / 老数据那一句出现或消失）
 * 就重新出现
 *
 * 用户点掉结果栏（`noticeClosed`）之后，下一条**新的**结果不该被他上一次的关闭动作吞掉 ——
 * 关闭状态靠这个签名复位，而不是永久静音。
 * ⚠️ 签名里要带上 `historyMatched`：它是「这一轮要不要说那句旧数据」的那一位，
 *    不带它时「先失败、重试后成了老数据」这一幕的签名可能不变 → 结果栏不再弹出来。
 */
const noticeSignature = computed(() =>
  rollbackNotices.value
    .map(
      (e) =>
        `${e.turnId}:${e.outcome.reverted}:${e.outcome.skipped.length}:${e.outcome.failed.length}:${e.outcome.partial.length}:${e.outcome.historyMatched}`
    )
    .join('|')
)

/** 结果栏是否被用户关掉了（新结果进来时由下面的 watch 复位） */
const noticeClosed = ref(false)

watch(noticeSignature, () => {
  noticeClosed.value = false
})

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
    // ⚠️ `experts`（专家工作组卡片）同样是过程信息、content 恒空，须一并排除 ——
    //    否则它会被当成"一条 assistant 正文"，干扰 loading 动画的判定。
    if (
      props.messages[i].role === 'assistant' &&
      t !== 'tool_confirm' &&
      t !== 'tool_result' &&
      t !== 'agent_note' &&
      t !== 'experts'
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
 * 把一段文本回填进输入框（**回退**成功后由页面调用）
 *
 * 场景：用户点了某一轮的「回退」，那一轮的消息（含他的提问）被服务端摘掉了 ——
 * 提问正文由 `rollbackTurn()` 从被摘掉的那条 user 消息里取出来，页面拿它调这里。
 * 输入框内容在**本组件**手里（`inputContent`，`ChatInputArea` 是它的纯展示层），
 * 所以这条通道只能在本组件上开，页面拿到 `streamRef` 后调 `setInputText(text)`。
 *
 * ⚠️ **只回填正文，图片 / 附件不回填**：`outcome.userText` 里只有正文
 *    （附件是二进制、而且已经发出去过一轮），前端手里也没有原件，
 *    回填一个「只有文字」的输入框比不回填更容易让人以为附件还在。
 * ⚠️ 只写 `inputContent` 这个 ref，不碰 textarea 的 DOM：`ChatInputArea` 的 `text`
 *    是 `modelValue` 的 computed，它自己 watch 这个值并 autoGrow（高度会跟着长）。
 */
const setInputText = (text) => {
  inputContent.value = String(text || '')
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
 * 只渲染最近 N 条消息（「加载更早」可加量）
 *
 * 症状：历史上下文一多，悬浮助手「打开 / 拖边框」就卡。
 * 根因：模板 `v-for` 把**整段历史**的 DOM 全渲染出来，条目成千上万时，
 *      任何一次重排（打开、resize）都要重排全部节点 → 掉帧。
 * 处理：默认只渲染最近 `RENDER_CHUNK` 条，向上「加载更早」每次再加一段。
 *      绝大多数场景用户只看最近几条，因此几乎无感。
 */
const RENDER_CHUNK = 40
const renderLimit = ref(RENDER_CHUNK)
/** 是否还有更早的消息没渲染出来 */
const hasEarlier = computed(() => props.messages.length > renderLimit.value)
/** 实际参与渲染的消息子集（最近 renderLimit 条） */
const visibleMessages = computed(() => {
  const all = props.messages
  if (all.length <= renderLimit.value) return all
  return all.slice(all.length - renderLimit.value)
})
/** 窗口起点在完整数组里的绝对下标（`:key` 用它保证条目身份稳定，避免复用错位） */
const windowOffset = computed(() => Math.max(0, props.messages.length - renderLimit.value))
/** 点「加载更早」：多渲染一段；保持滚动位置不跳（在一次 nextTick 内补偿高度差） */
const loadEarlier = async () => {
  const el = messagesRef.value as HTMLElement | null
  const beforeH = el ? el.scrollHeight : 0
  const beforeTop = el ? el.scrollTop : 0
  renderLimit.value += RENDER_CHUNK
  await nextTick()
  const e2 = messagesRef.value as HTMLElement | null
  if (e2) e2.scrollTop = e2.scrollHeight - beforeH + beforeTop
}
/** 清单变化（切会话 / 清空）：把窗口复位，避免一直带着上一条会话的渲染量 */
watch(() => props.messages.length, (n) => {
  if (n === 0 || n <= RENDER_CHUNK) renderLimit.value = RENDER_CHUNK
})

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

/**
 * 新出现「待确认」卡片时 → **强制滚到它**
 *
 * 为什么可以打破"用户上滑就别打扰"的规则（2026-10-17 用户报的 bug）：
 *   确认卡是**阻塞式**的 —— 用户不点，后端的 Agent 循环就停在那里，整轮任务不动。
 *   而它只是时间线里的一条消息，用户若是上滑在看历史、或卡片被后来的内容顶出视口，
 *   就完全不知道有东西在等他确认，界面看起来就是"傻愣着"。
 *   所以这里必须无条件滚过去。只在**数量增加**时触发，不会在用户点完确认（状态变
 *   resolved）后再把视口拽走。
 */
watch(
  () => props.messages.filter((m: any) => m?.type === 'tool_confirm').length,
  (n, prev) => {
    if (n > (prev || 0)) {
      pinnedToLatest.value = true
      nextTick(() => pinToLatest())
    }
  }
)

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

/**
 * 对外暴露：滚动落底 / 滚动容器 / **回填输入框**
 *
 * `setInputText` 是给「回退」用的（页面在 `rollbackTurn` 成功后把这一轮的提问正文塞回来），
 * 见它自己的注释。两个消费方（大屏智能体页 + 右侧助手抽屉）都必须接上 ——
 * 少接一个，那一侧的「回退后提问自动回到输入框」就是哑的。
 */
defineExpose({ scrollToBottom, messagesRef, setInputText })
</script>

<style scoped lang="scss">
.ai-chat-stream {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border-radius: 0;
  border: none;
  position: relative;
  background: #fff;
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
  padding: 24px 20px 8px;
  background-color: #fff;
  position: relative;
  overflow-x: hidden;
  /* 用 flex 列承载消息：空状态（hero）可以靠 `margin: auto` 在可视区垂直居中 */
  display: flex;
  flex-direction: column;
}

/* 消息不参与压缩：内容超出时只让这一层滚动，而不是把每条消息压扁 */
.chat-messages > * {
  flex: 0 0 auto;
}

/* 消息列：与 DSH 一致，正文收在 820px 的阅读宽度里，居中 */
.message {
  width: 100%;
  max-width: 820px;
  margin: 0 auto 18px;
  display: flex;
}

/* 「加载更早的消息」：贴顶居中，样式低调，不抢正文 */
.load-earlier {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
}

.load-earlier-btn {
  border: 1px solid #dcdfe6;
  background: #fff;
  color: #606266;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: #409eff;
    color: #409eff;
  }
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

/*
 * 「轮末」标记（`type:'turn_end'`）**不是一条消息** —— 它这一格只承载两个动作按钮。
 *
 * ⚠️ 必须把 `.message` 自带的下方留白归零：这一格本身没有气泡、也不是一条消息，
 *    留着那 16px 就会让**每一轮末尾**凭空多出一段空隙（消息间距从 16px 变成 32px）。
 *    这一格真正的间距与高度由 `AgentTurnRollback` 自己带。
 */
.message.msg-turn_end {
  margin-bottom: 0;
}

.message-content {
  max-width: 100%;
  padding: 0;
  border-radius: 0;
  background-color: transparent;
  box-shadow: none;
  border: none;
  position: relative;
  min-width: 0;
}

/*
 * 普通回答：不套卡片、不描边 —— 只有正文（DSH 的对话就是"文字流"，
 * 每条回答一个白卡片会让页面变成一堆盒子，反而显得粗糙）。
 */
.message-content.is-plain {
  width: 100%;
}

/*
 * 工具卡 / 过程提示 / 专家卡：**也不套白框**（用户 2026-10-17：
 * "Agent 的输出不需要那些白色边框容器包裹，想要 DSH 那种简洁效果"）。
 *
 * 现在整条消息流只有两种视觉元素：
 *   · 用户气泡（淡蓝底）
 *   · 其余内容（正文 / 工具结果 / 进度 / 通知）—— 直接在流里，靠图标与缩进分层
 * 工具自己的状态与「查看详情」仍由 AgentToolResult 表达，不再需要外层容器强调。
 */
.message.msg-tool_result .message-content,
.message.msg-tool_confirm .message-content,
.message.msg-agent_note .message-content,
.message.msg-progress .message-content,
.message.msg-experts .message-content,
.message.msg-reasoning .message-content {
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.message.user .message-content {
  /* 用户气泡：DSH 用极淡的蓝底（--dsw-specific-bubble），不用灰底或深色块 */
  background-color: var(--dsw-specific-bubble);
  color: var(--os-text);
  border: none;
  box-shadow: none;
  border-radius: 14px;
  padding: 10px 14px;
  /*
   * ⚠️ 用户消息内容极短时（如只发「1」）气泡会被内容撑到只有一两个字符宽，
   *    而右下角的复制按钮是绝对定位、宽度固定（图标 + 「复制」两个字 ≈ 60px）——
   *    气泡比按钮还窄时按钮就**溢出到气泡外**（用户 2026-10-11 报）。
   *    给一个能容下复制按钮的最小宽度，短消息也不会把按钮挤出去。
   */
  min-width: 96px;
  max-width: 78%;
}

/* 工具卡片 / 过程提示属于「结构化内容」，比正文更需要横向空间 */
.message.msg-tool_result .message-content,
.message.msg-agent_note .message-content {
  max-width: 100%;
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
  max-width: 100%;
}

.message-role {
  font-size: 11px;
  margin-bottom: 7px;
  opacity: 1;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.agent-role {
  color: var(--os-text-4);
  font-weight: 500;
  font-size: 11px;
}

.message-text {
  line-height: 1.75;
  font-size: 14.5px;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

.msg-copy-btn {
  position: absolute;
  bottom: 2px;
  right: 0;
  border-radius: 6px;
  padding: 3px 7px;
  font-size: 12px;
  z-index: 10;
  color: var(--os-text-4);
  background: transparent;
  border: none;
  /* 只列 hover 里真正会变的两个颜色属性（本仓禁 `transition: all`：它会把以后新增的任何属性
     —— 含 padding/width 这类布局属性 —— 一起卷进逐帧重排） */
  transition: background-color 0.2s ease, color 0.2s ease;
  opacity: 0;
}

/* 复制按钮平时隐身，指针进入这条消息或键盘聚焦时才出现（不干扰阅读） */
.message:hover .msg-copy-btn,
.message:focus-within .msg-copy-btn {
  opacity: 1;
}

.msg-copy-btn:hover {
  background: var(--os-bg-hover);
  color: var(--os-text-2);
}

/* 图标与「复制」两个字的间距（el-button 只给插槽套一层 span，不会自己加 gap） */
.mc-label {
  margin-left: 3px;
}

/*
 * 用户气泡也给右下角的复制按钮留位（LLM 那侧由 `.rendered-md` 的 `padding-bottom` 留）：
 * 不留的话，消息只有一两行时按钮会压在最后一行文字上。
 */
.message.user .message-text {
  padding-bottom: 18px;
}

/* AI 加载动画（内联在消息内） */
.ai-loading-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

/* ==================== 统一等待行（DSH 式） ====================
   一行：三个呼吸灰点 + 当前状态文案。没有卡片、没有边框、没有"AGENT"标签。
   多步骤时才展开下面的清单（作为补充信息，不再是主视觉）。 */
.agent-thinking {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--os-text-3);
  user-select: none;
}

.agent-thinking__dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;

  i {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: currentColor;
    opacity: 0.35;
    animation: agent-think 1.25s ease-in-out infinite;

    &:nth-child(2) {
      animation-delay: 0.16s;
    }

    &:nth-child(3) {
      animation-delay: 0.32s;
    }
  }
}

@keyframes agent-think {
  0%,
  70%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }

  35% {
    opacity: 1;
    transform: translateY(-1px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .agent-thinking__dots i {
    animation: none;
    opacity: 0.5;
  }
}

/* 多步骤清单：去卡片，改成缩进的一列细字 */
.progress-steps {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  max-width: 100%;
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--os-text-3);
  word-break: break-word;
}

.progress-step.step-running {
  color: var(--os-text-2);
}

.progress-step.step-done {
  color: var(--os-text-3);
}

.progress-step.step-failed {
  color: var(--os-danger);
}

.step-icon {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* 进行中：小转圈 */
.step-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #c7d2fe;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: progress-spin 0.8s linear infinite;
}

.step-check {
  color: #16a34a;
  font-weight: 700;
}

.step-fail {
  color: #dc2626;
  font-weight: 700;
}

.step-emoji {
  flex-shrink: 0;
}

.step-text {
  flex: 1;
}

@keyframes progress-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .step-spinner {
    animation: none;
  }

  /* 「还在输出」提示：关掉呼吸闪烁但**保留可见**（不能直接隐藏，否则就失去"没停"的信号） */
  .stream-hint {
    animation: none;
    opacity: 0.7;
  }

  .stream-hint-dots i {
    animation: none;
    opacity: 0.6;
  }
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
  line-height: 1.75;
  font-size: 14.5px;
  color: var(--os-text);
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
    color: var(--os-text);
    font-weight: 600;
    line-height: 1.35;
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
    padding: 8px 14px;
    border-left: 2px solid var(--os-border-strong);
    color: var(--os-text-2);
    background: var(--dsw-static-neutral-bluish-50);
    border-radius: 0 8px 8px 0;
  }

  pre {
    background: var(--dsw-alias-markdown-code-block);
    color: var(--os-text);
    padding: 14px 16px;
    border: 1px solid var(--os-border-soft);
    border-radius: var(--os-radius-sm);
    margin: 0.6em 0;
    overflow-x: auto;
    overflow-y: auto;
    max-height: 300px;
    font-size: 13px;
    line-height: 1.7;
    max-width: 100%;
    white-space: pre-wrap;
    word-break: break-word;
    font-family: var(--os-font-code);

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
    background: var(--dsw-alias-markdown-inline-code);
    color: var(--os-text);
    border: 1px solid var(--os-border-soft);
    padding: 1px 5px;
    border-radius: 5px;
    font-size: 0.9em;
    font-family: var(--os-font-code);
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
    border: 1px solid var(--os-border-soft);
    padding: 8px 12px;
    text-align: left;
    white-space: nowrap;
    min-width: 60px;
  }

  th {
    background: var(--dsw-static-neutral-bluish-50);
    font-weight: 600;
  }

  tr:nth-child(even) {
    background: #fcfcfd;
  }

  hr {
    border: none;
    border-top: 1px solid var(--os-border-soft);
    margin: 1em 0;
  }

  img {
    max-width: 100%;
    border-radius: 8px;
  }

  a {
    color: var(--os-accent);
    text-decoration: none;
    word-break: break-word;
  }

  a:hover {
    text-decoration: underline;
  }
}

/* ── 专家工作组卡片（多专家并行干活）─────────────────────────────────────
   一行一个专家：状态图标 + 名字 + 一行摘要 + 展开箭头；点行展开看详情。
   默认只显一行（干净），细节收起 —— 对应"专家思维链默认不显示、想看可点开"。 */
.expert-group {
  border: 1px solid #e6ebf3;
  border-radius: 12px;
  background: #fbfcfe;
  overflow: hidden;
}

.expert-group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 12px;
  font-size: 12.5px;
  color: #64748b;
  background: #f4f7fc;
  border-bottom: 1px solid #e6ebf3;
}

.eg-icon {
  color: #4f6ef7;
}

.expert-row {
  border-bottom: 1px solid #eef2f7;
}

.expert-row:last-child {
  border-bottom: none;
}

.expert-row-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.expert-row-head:hover {
  background: #f2f6fd;
}

.expert-state {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
}

.expert-ok {
  color: #16a34a;
}

.expert-fail {
  color: #dc2626;
}

/* 进行中：旋转小圈（用纯 CSS，避免再引一个 loading 组件） */
.expert-spin {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid #dbe3ef;
  border-top-color: #4f6ef7;
  border-radius: 50%;
  animation: expert-rotate 0.8s linear infinite;
}

@keyframes expert-rotate {
  to {
    transform: rotate(360deg);
  }
}

.expert-name {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.expert-task {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 进行中展开的最近步骤（弱化小字）—— 只表达「它现在做到哪一步」 */
.expert-steps {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0 12px 8px 36px;
}

.expert-step {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
}

.expert-step-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
}

.expert-step-dot.sd-running {
  background: #93b4f5;
}

.expert-step-dot.sd-ok {
  background: #22c55e;
}

.expert-step-dot.sd-fail {
  background: #ef4444;
}

.expert-step-text {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.expert-caret {
  flex-shrink: 0;
  color: #b6bdc9;
  transition: transform 0.15s ease;
}

.expert-caret.open {
  transform: rotate(180deg);
}

.expert-detail {
  padding: 2px 12px 12px 36px;
}

.expert-detail-block + .expert-detail-block {
  margin-top: 8px;
}

.ed-label {
  font-size: 11.5px;
  color: #a0aab8;
  margin-bottom: 3px;
}

.ed-text {
  font-size: 13px;
  color: #475569;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
