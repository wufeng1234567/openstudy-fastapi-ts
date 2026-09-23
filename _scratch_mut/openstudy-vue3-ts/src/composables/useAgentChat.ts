// composables/useAgentChat.ts
import { ref, computed } from 'vue'
import {
  postAgentStream,
  confirmAgentTool,
  rollbackAgentTurn,
  type AgentRollbackResult,
  type AgentEvent,
  type AgentImageInput
} from '@/api/ai/agent'
import { runDsFreeAgentStream } from '@/api/ai/agentDsFree'
import { saveAgentTimeline } from '@/api/ai/ai'
import { running as selfCheckRunning } from '@/devtools/dfSelfCheck/store'

/** ds-free（DeepSeek 网页版）走前端工具调用循环，与 api-paid 后端循环共用同一套事件流 */
export const isDsFreeModel = (model?: string) => model === 'deepseek-free'

/**
 * Agent 对话状态机（工具调用过程**内联**进消息流）
 *
 * 与聊天的区别：Agent 一轮里除了正文，还会有「调工具 → 拿结果 → 再调 → 最终回复」。
 * 这些过程不该藏在折叠面板里 —— 用户要看得到它建了哪个题库、导到第几题、哪里在自我纠正。
 * 所以这里把事件流**翻译成消息流**：
 *
 *   tool_start   → 插一条 `type:'tool_result'` 且 `status:'running'` 的消息（转圈）
 *   tool_result  → 回填同一条（改成 ok / fail），失败时带 errors
 *   self_correct → 插一条「自我纠正」气泡
 *   text         → 追加到当前**未闭合**的 assistant 正文气泡
 *
 * 产出直接喂给 `AiChatStream`（它的 `tool_result` 分支 / 插槽就是为此留的），
 * 所以大屏智能体页与 sp3 一样是「对话即过程」的形态，不需要额外的执行面板。
 */

/** 消息流里的一条（AiChatStream 认识 role / type / content） */
export interface AgentChatMessage {
  role: 'user' | 'assistant'
  /**
   * tool_result=工具卡片；agent_note=纠正/告警/错误提示；thinking=等待占位；
   * **reasoning=深度思考的推理块（可折叠）**；tool_confirm=写操作二次确认卡片；
   * **turn_end=轮末标记（一轮的最后一条，回退组件挂在这里）**；其余为普通正文
   *
   * ⚠️ 别把 `reasoning` 和 `thinking` 合并：`thinking` 是**等待占位**（三点抖动，
   * 见 `pendingPlaceholder`），它早就在用了，两者语义完全不同。
   *
   * ⚠️ `turn_end` 是**结构**、不是内容：`content` 恒为空串，它唯一的载荷是 `turnId`
   * （见 `send()` 的 finally —— 那是两条链路**都必然经过**的轮末点）。
   */
  type?: 'tool_result' | 'agent_note' | 'thinking' | 'reasoning' | 'tool_confirm' | 'turn_end'
  content: string
  /**
   * 这条消息属于**哪一轮**（一次用户提问）—— 目前只有 `turn_end` 标记用。
   *
   * 它是「回退」的**唯一凭据**：服务端按 `turnId` 查本轮的写操作账本，
   * 所以这个字段必须原样落库（`slimTimeline` 白名单）+ 原样传给 `rollbackTurn()`。
   */
  turnId?: string
  /** agent_note 的子类型（决定图标与配色） */
  noteKind?: 'correct' | 'warning' | 'error'
  /** tool_result 专用 */
  tool?: string
  action?: string
  status?: 'running' | 'ok' | 'fail'
  detail?: string
  errors?: string[]
  params?: Record<string, any>
  /** 工具返回的完整结构化结果（卡片里「查看详情」用；仅内存，不落库） */
  data?: Record<string, any>
  /** tool_confirm 专用：本次确认的 id（后端链路用于唤醒后端，前端链路用于本地 resolve） */
  confirmId?: string
  /** tool_confirm：是否为破坏性操作（删除类） */
  destructive?: boolean
  /** tool_confirm：确认前展示的信息（题库名 / 题量…） */
  preview?: Record<string, any>
  /** 自我纠正序号 */
  attempt?: number
  /**
   * `reasoning` 专用：这一段思考花了多少秒。
   * **`secs == null` 就表示它还在跑** —— 没有另设 `status` 字段，理由见 `closeReasoning()`。
   */
  secs?: number
  /** 已发送的附件（仅 user 消息） */
  attachments?: any[]
}

export interface AgentRunOptions {
  message: string
  /** 图片附件；传 `{name,type,base64}` 对象可以保留原始文件名 */
  images?: AgentImageInput[]
  files?: Array<{ name: string; type: string; base64: string }>
  attachments?: any[]
  model?: string
  provider?: string
  sessionId?: string
  userId?: string | number
  /** 写操作是否自动执行 */
  autoConfirm?: boolean
  maxLoops?: number
}

/** 单条消息里 `data` 的落库上限（超过就只留摘要），避免快照被题目数组撑爆 */
const TIMELINE_DATA_LIMIT = 20000

/**
 * 思考块的落库上限
 *
 * 深度思考的推理动辄几千字，**不能像正文那样无上限地存** —— 快照被撑大会拖慢会话加载，
 * 而推理只是过程信息、不是用户要留的记录。超长就截断并注明。
 */
const TIMELINE_REASONING_LIMIT = 4000

/**
 * 落库前给消息流瘦身
 *
 * 只保留渲染需要的字段；`data`（工具原始返回，可能含整批题目）超过上限时
 * 退化成 `{message, _truncated}`，既留住「结果摘要」又不让快照无限膨胀。
 */
function slimTimeline(msgs: AgentChatMessage[]): any[] {
  return msgs.map((m) => {
    const out: any = { role: m.role, content: m.content || '' }
    if (m.type) out.type = m.type
    // 轮次 id：`turn_end` 标记必须带上它 —— **刷新之后「最近一轮还能回退」全靠这一个字段**
    //（账本在后端库里，前端只要把 id 带回来）。白名单的语义是「不在名单里的字段刷新后就没了」，
    // 所以漏掉这一行 = 刷新一次回退按钮就成了摆设。
    // ⚠️ 放在 `reasoning` 的提前 return **之前**：那条分支同样受白名单约束。
    if (m.turnId) out.turnId = m.turnId
    // 思考块单独处理：内容截断，但 `secs` 照存（刷新后收起态还得显示「已思考 X 秒」）。
    // ⚠️ 截断要放在 `out.type` 赋值之后 —— 提前 return 会把 type 丢掉，
    //    刷新后这团文本就变成一条普通正文了。
    if (m.type === 'reasoning') {
      if (out.content.length > TIMELINE_REASONING_LIMIT) {
        out.content = out.content.slice(0, TIMELINE_REASONING_LIMIT) + '…（推理较长，已截断）'
      }
      if (m.secs != null) out.secs = m.secs
      return out
    }
    if (m.noteKind) out.noteKind = m.noteKind
    if (m.tool) out.tool = m.tool
    if (m.action) out.action = m.action
    if (m.status) out.status = m.status
    if (m.detail) out.detail = m.detail
    if (m.errors?.length) out.errors = m.errors
    if (m.params) out.params = m.params
    if (m.attempt != null) out.attempt = m.attempt
    if (m.attachments?.length) out.attachments = m.attachments
    if (m.data) {
      try {
        const s = JSON.stringify(m.data)
        out.data =
          s.length > TIMELINE_DATA_LIMIT
            ? { message: (m.data as any)?.message, _truncated: true, _bytes: s.length }
            : m.data
      } catch {
        // 循环引用等无法序列化 → 丢弃 data（卡片仍能显示标题与状态）
      }
    }
    return out
  })
}

/**
 * 执行统计（`metrics` 事件）
 *
 * 口径与后端 `loop.py` 的 `_metrics_event()` **逐字一致**（双链路同口径是红线）：
 *   · `rounds` = 完成的 LLM 往返次数
 *   · `steps`  = 模型请求过的工具调用条目数（含「工具不存在 / 参数校验不过」这些没执行的）
 *   · `llmMs` / `toolMs` = 累计耗时（毫秒）
 *   · `firstTokenMs` = 各轮「发起 LLM 调用 → 第一个非空可读内容」的平均毫秒；
 *     **没有样本时是 `null`**，UI 显示 `—`（给 0 会被读成「瞬间返回」）
 */
export interface AgentMetrics {
  rounds: number
  steps: number
  llmMs: number
  toolMs: number
  firstTokenMs: number | null
}

/**
 * 「回退本轮」的状态（UI 直接照 `status` + `summary` 渲染）
 *
 * `summary` 就是 `rollbackAgentTurn()` 的返回值，**字段名一个字都没改**
 * （`ok` / `reverted` / `skipped` / `failed` / `partial`）—— UI 要按它逐条渲染结果
 * 与「不可回退原因」清单，改名等于让组件渲染不出东西。
 */
export interface TurnRollbackState {
  /** 这次回退针对的轮次（`idle` 时是空串）—— UI 靠它判断「这个结果是不是我那一轮的」 */
  turnId: string
  /**
   * `idle` = 没点过；`busy` = 请求在飞（按钮要禁用，否则连点会打两次账本）；
   * `done` = 服务端回了回退结果；`fail` = 服务端拒了 / 网络挂了（看 `summary.reason`）
   */
  status: 'idle' | 'busy' | 'done' | 'fail'
  /** 回退结果（`busy` 时是 null，其余状态都有值） */
  summary: AgentRollbackResult | null
}

/**
 * 生成一个**轮次 id**
 *
 * 形状 `t_<毫秒>_<随机 6 位>`：
 *   · 毫秒时间戳 —— 日志 / 库里一眼看出先后，几个轮次之间能按时间排；
 *   · 随机后缀 —— 同一毫秒内连点两次发送也不会撞车（撞了就会把两轮的账本混在一起）。
 * 与 `requestConfirm` 里的 `local_<ms>_<rand>` 是同一套写法，刻意保持一致。
 */
const newTurnId = () =>
  `t_${Date.now()}_${Math.random().toString(36).slice(2, 8).padEnd(6, '0')}`

export function useAgentChat() {
  const messages = ref<AgentChatMessage[]>([])
  const isGenerating = ref(false)

  /**
   * 本轮的轮次 id（**发给后端的那个**）
   *
   * UI 要拿它调 `rollbackTurn()`；`turn_end` 标记里的 `turnId` 与它逐字相同。
   */
  const currentTurnId = ref('')
  /** 回退状态（见 `TurnRollbackState`） */
  const turnRollback = ref<TurnRollbackState>({ turnId: '', status: 'idle', summary: null })
  /**
   * 最近一次 `send()` 用过的会话 id
   *
   * 为什么记一份：UI 手上只有「这一轮的 `turnId`」（从 `turn_end` 标记里拿），
   * 而回退接口要的是 `{sessionId, turnId}`。记下来就能让 UI 一句
   * `rollbackTurn(turnId)` 走通，不必到处透传会话 id（页面上的 `sessionId`
   * 还可能在这一轮之后变过 —— 比如用户切了会话）。
   */
  const lastSessionId = ref('')

  /** meta 事件：可用工具 / 实际模型 / 附件告警 */
  const tools = ref<Array<{ name: string; description: string }>>([])
  const activeModel = ref('')
  const metaWarnings = ref<string[]>([])
  const imageCount = ref(0)
  const corrections = ref(0)
  const errors = ref<string[]>([])

  /**
   * 执行统计（`metrics` 事件）—— 底部状态条显示用
   *
   * ⚠️⚠️ **口径由两条链路共同约定，改一处必须改另一处**：
   *   · 后端：`app/services/ai/agent/loop.py` 的 `_metrics_event()`
   *   · 前端：`src/api/ai/agentDsFree.ts`（ds-free 循环跑在前端）
   *   `rounds` = 完成的 LLM 往返次数；`steps` = 模型请求过的工具调用条目数（含没真正执行的）；
   *   `llmMs` / `toolMs` = 累计耗时（毫秒）。
   *
   * ⚠️ **这里是「会话累计」，不是「上一句提问」**（用户 2026-09-19 报的 bug）：
   *   后端每次 `run_agent_stream` 都从 0 开始计数，所以事件里带的是**本轮**的量；
   *   如果直接整组覆盖，用户每问一句新问题，状态条就会被新账顶掉 ——
   *   而这条状态条长在整段对话下方、形态上就是「这次会话一共做了多少」。
   *   所以这里做成**跨提问累加，只在 `reset()`（新对话 / 切换会话）时清零**。
   */
  const metrics = ref<AgentMetrics>({
    rounds: 0,
    steps: 0,
    llmMs: 0,
    toolMs: 0,
    firstTokenMs: null
  })

  /** 会话累计的原始累加器（`metrics` 是它的展示投影） */
  const sessionAgg = { rounds: 0, steps: 0, llmMs: 0, toolMs: 0, ftSum: 0, ftSamples: 0 }

  /**
   * 本轮（单次提问）上一次收到的快照
   *
   * 事件里带的是**本轮累计值**，所以增量 = 本次值 − 上次值。每次 `send()` 必须归零，
   * 否则新一轮算出负增量、把会话总量往回拉。
   */
  let runSnapshot = { rounds: 0, steps: 0, llmMs: 0, toolMs: 0, ftSum: 0, ftSamples: 0 }

  /**
   * 把会话累加器投影到 `metrics`
   *
   * ⚠️ `firstTokenMs` 是**平均值**，不能像其余四项那样直接相加 —— 所以累加器里存的是
   * **`ftSum`（总和）与 `ftSamples`（样本数）**，这里才做除法。
   * 用 `rounds` 当权重是错的：只吐 `tool_calls`、没有正文的轮**不进样本**。
   */
  const syncMetrics = () => {
    metrics.value = {
      rounds: sessionAgg.rounds,
      steps: sessionAgg.steps,
      llmMs: sessionAgg.llmMs,
      toolMs: sessionAgg.toolMs,
      firstTokenMs: sessionAgg.ftSamples
        ? Math.round(sessionAgg.ftSum / sessionAgg.ftSamples)
        : null
    }
  }

  /** 当前「未闭合」的 assistant 正文气泡下标；-1 = 下一条 text 要新建气泡 */
  let openTextIndex = -1
  let controller: AbortController | null = null

  /** 一次运行里所有工具调用（含运行中）—— 供页面做统计/折叠用 */
  const toolCalls = computed(() =>
    messages.value.filter((m) => m.type === 'tool_result')
  )

  /** 是否有过任何执行过程（决定要不要显示「执行过程」入口） */
  const hasRun = computed(() => toolCalls.value.length > 0)

  const reset = () => {
    messages.value = []
    pendingPlaceholder = null
    // 还挂着的确认一律按「取消」处理，避免 ds-free 循环里的 Promise 永远悬着
    pendingConfirms.forEach((resolve) => resolve(false))
    pendingConfirms.clear()
    openTextIndex = -1
    // 直接置空而不是调 closeReasoning：整条消息流都要清掉，没必要再往旧对象上写状态
    openReasoning = null
    turnReasoning = null
    reasoningStartedAt = 0
    tools.value = []
    activeModel.value = ''
    metaWarnings.value = []
    imageCount.value = 0
    corrections.value = 0
    errors.value = []
    // 会话级复位：轮次凭据与回退状态都属于「上一个会话」，跟着清掉。
    // ⚠️ 不清的话，切到新会话后 `rollbackTurn(oldTurnId)` 会带着**新会话**的
    //    sessionId 去回退旧会话的轮次 —— 服务端只能回一句「该轮次不存在」，用户莫名其妙。
    currentTurnId.value = ''
    lastSessionId.value = ''
    turnRollback.value = { turnId: '', status: 'idle', summary: null }
    // 会话级复位：新对话 / 切换会话才清空统计（发新提问**不**清 —— 见 `send()` 里的说明）。
    // 直接重置累加器再投影，不要只写 `metrics.value`：那样累加器还留着旧值，
    // 下一次事件会把旧账又加回来。
    sessionAgg.rounds = 0
    sessionAgg.steps = 0
    sessionAgg.llmMs = 0
    sessionAgg.toolMs = 0
    sessionAgg.ftSum = 0
    sessionAgg.ftSamples = 0
    runSnapshot = { rounds: 0, steps: 0, llmMs: 0, toolMs: 0, ftSum: 0, ftSamples: 0 }
    syncMetrics()
  }

  /** 关闭当前正文气泡：下一次 text 会新开一条 */
  const closeText = () => {
    openTextIndex = -1
  }

  /**
   * 把当前正文气泡**整条删掉**（不是关闭）。
   *
   * 用于 `discard_text`：模型吐的是没解析成功的工具调用协议文本（DSML / JSON），
   * 它已经随 `text` 增量流进气泡了。不删的话，纠正重发之后气泡里会
   * 留着那一屏协议文本，用户以为那就是回答。
   */
  const discardText = () => {
    if (openTextIndex >= 0 && openTextIndex < messages.value.length) {
      messages.value.splice(openTextIndex, 1)
    }
    openTextIndex = -1
    // 等待占位是按**对象引用**找的（见 `clearPlaceholder`），不靠下标，所以不受影响
  }

  /**
   * 思考块（深度思考的推理文本）
   *
   * 和正文气泡一样是「未闭合」模型：`thinking` 事件每次给一段**增量**，
   * 先到的累加在同一个块里；一旦有正文 / 工具卡 / 提示 / 轮次结束就 `closeReasoning()`
   * 收口（记下耗时，UI 据此把块折起来）。
   *
   * 为什么另开一个盒子而不是复用 `openTextIndex`：正文要能被 `discardText` 整条撤掉
   * （协议文本误当回答），而思考块**不能**跟着撤 —— 它是真实发生过的推理，
   * 撤掉反而让「刚才发生了什么」变得不可解释。
   */
  let openReasoning: AgentChatMessage | null = null
  let reasoningStartedAt = 0
  /**
   * **本轮**（一次 `send`）的思考块 —— 收口后**不清空**，专门用来接「迟到的增量」。
   *
   * 为什么需要它：上游 reasoning 和 response 的相对顺序**没有保证** ——
   * 扩展侧的发送批次是一个共享槽位（`interceptor.js` 的 `_pendingChunk`），
   * reasoning 与 response 会互相覆盖；DS 的 fragments 本身也是 `THINK / RESPONSE` 交替的。
   * 于是「思考的最后一截」可能落在答案**之后**。
   *
   * 此时若新开一个思考块，界面就变成「残缺思考块 → 答案 → 剩下的思考」，
   * 用户得把两块拼起来才看得出是同一段推理（线上 2026-09-19 报过两次，见 DF-UI-06）。
   * 所以一轮里**只留一个块**，迟到的增量补回它（它排在答案之前）。
   */
  let turnReasoning: AgentChatMessage | null = null

  const appendReasoning = (delta: string) => {
    if (!delta) return
    // 有推理文字可看了就摘掉「等待中」占位 —— 转圈和文字同时出现是多余的
    clearPlaceholder()
    if (!openReasoning) {
      // 本轮已经有思考块（已收口）→ 补回去，**不新开块**
      if (turnReasoning) {
        turnReasoning.content += delta
        // 思考其实还在继续 → 顺延耗时，「已思考 X 秒」才诚实。
        // 刻意**不重新展开**：用户可能已经手动收起过，突然弹开会很打扰。
        turnReasoning.secs = Math.max(1, Math.round((Date.now() - reasoningStartedAt) / 1000))
        return
      }
      openReasoning = { role: 'assistant', type: 'reasoning', content: '' }
      turnReasoning = openReasoning
      reasoningStartedAt = Date.now()
      messages.value.push(openReasoning)
    }
    openReasoning.content += delta
  }

  /**
   * 收口当前思考块：记下耗时。
   *
   * 「还在跑」就靠 `secs == null` 判断（UI 侧同理），**不额外用 `status`** ——
   * `AgentChatMessage.status` 的联合类型是 `'running' | 'ok' | 'fail'`，
   * 那是工具卡片在用的；为一个推理块往里加 `'done'` 会让
   * `AgentToolResult.STATUS_WORDS` 之类的映射莫名多一个无文案的值。
   */
  const closeReasoning = () => {
    if (!openReasoning) return
    // 至少 1 秒：秒级取整会把「0.4 秒」显示成 0，看着像坏了
    openReasoning.secs = Math.max(1, Math.round((Date.now() - reasoningStartedAt) / 1000))
    openReasoning = null
  }

  /**
   * 「等待中」占位气泡
   *
   * ds-free 首轮要先「拉工具清单 → 扩展加载 → 模型思考」好几秒，这段时间一条消息都没有，
   * 左侧空白观感很差。所以发送时先压一条 `type:'thinking'`（AiChatStream 渲染成三点抖动），
   * 任何真实内容（正文 / 工具卡 / 提示）到来时再摘掉。
   */
  let pendingPlaceholder: AgentChatMessage | null = null
  const clearPlaceholder = () => {
    if (!pendingPlaceholder) return
    const i = messages.value.indexOf(pendingPlaceholder)
    if (i >= 0) messages.value.splice(i, 1)
    pendingPlaceholder = null
  }

  /**
   * 显示「等待中」占位（已有就只更新文案，不重复插入）
   *
   * 由 `waiting` 事件在**每一轮模型思考开始前**触发。只在发送时放一次是不够的 ——
   * 工具执行完之后、等模型下一轮回复的那段时间会一片空白（用户反馈的「中间没有等待效果」）。
   */
  const showPlaceholder = (label: string = '') => {
    if (pendingPlaceholder) {
      pendingPlaceholder.content = label
      return
    }
    pendingPlaceholder = { role: 'assistant', type: 'thinking', content: label }
    messages.value.push(pendingPlaceholder)
  }

  /** 待用户确认的写操作（ds-free 前端循环的等待者；后端链路由 confirmId 走 HTTP 唤醒） */
  const pendingConfirms = new Map<string, (approved: boolean) => void>()

  /** 请求用户确认（ds-free 前端循环调用）→ 返回用户的决定 */
  const requestConfirm = (info: {
    tool: string
    action?: string
    params?: Record<string, any>
    destructive?: boolean
    message?: string
    preview?: Record<string, any>
  }): Promise<boolean> => {
    closeText()
    clearPlaceholder()
    closeReasoning()
    const confirmId = `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    messages.value.push({
      role: 'assistant',
      type: 'tool_confirm',
      content: info.message || `即将执行 ${info.tool}`,
      tool: info.tool,
      action: info.action || '',
      params: info.params,
      preview: info.preview,
      destructive: info.destructive,
      status: 'running',
      confirmId
    })
    return new Promise<boolean>((resolve) => {
      pendingConfirms.set(confirmId, resolve)
    })
  }

  /**
   * 用户点了「确认」/「取消」（页面调用）
   *
   * - ds-free：前端循环在等 → 本地 resolve
   * - api 付费：后端循环在挂起 → POST `/ai/agent/confirm` 唤醒
   */
  const resolveConfirm = async (confirmId: string, approved: boolean) => {
    const msg = messages.value.find(
      (m) => m.type === 'tool_confirm' && m.confirmId === confirmId
    )
    if (msg) msg.status = approved ? 'ok' : 'fail'
    const local = pendingConfirms.get(confirmId)
    if (local) {
      pendingConfirms.delete(confirmId)
      local(approved)
      return
    }
    await confirmAgentTool(confirmId, approved)
  }

  const appendText = (chunk: string) => {
    if (!chunk) return
    // 正文开始了 ⇒ 这一轮的思考已经结束，把块收口（UI 会折起来，别让它继续长）
    closeReasoning()
    clearPlaceholder()
    if (openTextIndex < 0 || openTextIndex >= messages.value.length) {
      messages.value.push({ role: 'assistant', content: chunk })
      openTextIndex = messages.value.length - 1
      return
    }
    const target = messages.value[openTextIndex]
    target.content = (target.content || '') + chunk
  }

  const pushNote = (kind: 'correct' | 'warning' | 'error', text: string, attempt?: number) => {
    clearPlaceholder()
    closeText()
    closeReasoning()
    messages.value.push({
      role: 'assistant',
      type: 'agent_note',
      noteKind: kind,
      content: text,
      attempt
    })
  }

  const pushTool = (event: AgentEvent) => {
    clearPlaceholder()
    closeText()
    closeReasoning()
    messages.value.push({
      role: 'assistant',
      type: 'tool_result',
      tool: event.tool || '',
      action: event.action || event.params?.action || '',
      content: event.message || `正在执行 ${event.tool}…`,
      status: 'running',
      params: event.params
    })
  }

  /** 回填最后一条「同工具 + 运行中」的卡片 */
  const fillTool = (event: AgentEvent) => {
    const detail = String(event.data?.message || event.message || '')
    const errs = Array.isArray(event.data?.errors) ? event.data.errors : []
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.type === 'tool_result' && m.status === 'running' && m.tool === event.tool) {
        m.status = event.success ? 'ok' : 'fail'
        m.detail = detail
        m.errors = errs
        m.data = event.data
        m.content = detail || m.content
        return
      }
    }
    // 没找到对应卡片（事件丢了 / 顺序异常）：补一条，别让过程凭空消失
    messages.value.push({
      role: 'assistant',
      type: 'tool_result',
      tool: event.tool || '',
      action: event.action || '',
      content: detail || `已执行 ${event.tool}`,
      status: event.success ? 'ok' : 'fail',
      errors: errs,
      data: event.data
    })
  }

  /** 事件 → 消息流 */
  const handleEvent = (event: AgentEvent) => {
    switch (event.type) {
      case 'meta':
        tools.value = event.tools || []
        activeModel.value = event.model || ''
        metaWarnings.value = event.warnings || []
        imageCount.value = event.imageCount || 0
        break

      case 'text':
        appendText(event.content || '')
        break

      case 'waiting':
        // 每一轮「模型思考」开始时都会发（首轮 + 每次工具执行之后）→ 显示等待占位；
        // 真实内容（正文 / 工具卡 / 提示）一到就被 clearPlaceholder 摘掉。
        closeText()
        showPlaceholder(event.message || '')
        break

      case 'tool_confirm':
        // 后端（api 付费链路）遇到需要确认的写操作 → 下发本事件并挂起，等用户点卡片
        closeText()
        clearPlaceholder()
        messages.value.push({
          role: 'assistant',
          type: 'tool_confirm',
          content: event.message || `即将执行 ${event.tool}`,
          tool: event.tool || '',
          action: event.action || '',
          params: event.params,
          preview: event.preview,
          destructive: Boolean(event.destructive),
          status: 'running',
          confirmId: event.confirmId || ''
        })
        break

      case 'tool_confirm_resolved': {
        // 后端已收到用户决定 → 同步卡片状态
        const m = messages.value.find(
          (x) => x.type === 'tool_confirm' && x.confirmId === event.confirmId
        )
        if (m) m.status = event.approved ? 'ok' : 'fail'
        break
      }

      case 'thinking':
        // 深度思考的**推理文本**（增量）→ 累加到当前思考块。
        //
        // ⚠️ 旧实现把 `thinking` 当成「中间说明」，塞成一条黄色 agent_note ——
        //    那套语义**从来没人发过**（后端 loop.py / chat_engine.py 都不发 thinking 事件），
        //    是死代码。真正承担「中间说明」的是 `waiting`（走占位气泡）和
        //    `warning`（走 agent_note），所以这里改成推理块不会抢它们的位置。
        appendReasoning(event.content || '')
        break

      case 'tool_start':
        pushTool(event)
        break

      case 'tool_result':
        fillTool(event)
        break

      case 'self_correct':
        corrections.value = Math.max(corrections.value, Number(event.attempt) || 0)
        pushNote('correct', event.reason || '参数有误，正在重试', Number(event.attempt) || undefined)
        break

      case 'metrics': {
        // 后端发的是**本轮（单次提问）的累计值**，本状态条要的是**会话累计** →
        // 本处算增量并累进会话总量（整组覆盖会让每问一句就把旧账清掉）。
        const cur = {
          rounds: Number(event.rounds) || 0,
          steps: Number(event.steps) || 0,
          llmMs: Number(event.llmMs) || 0,
          toolMs: Number(event.toolMs) || 0,
          ftSamples: Number(event.firstTokenSamples) || 0
        }
        // 本轮首 token 总和 = 平均值 × 样本数（后端只给这两个）；
        // 后端把平均值 `round()` 成整数，所以这里还原出的总和有几毫秒内的舍入误差，
        // 只影响显示、可忽略。
        const curFtSum =
          typeof event.firstTokenMs === 'number' ? event.firstTokenMs * cur.ftSamples : 0
        sessionAgg.rounds += cur.rounds - runSnapshot.rounds
        sessionAgg.steps += cur.steps - runSnapshot.steps
        sessionAgg.llmMs += cur.llmMs - runSnapshot.llmMs
        sessionAgg.toolMs += cur.toolMs - runSnapshot.toolMs
        sessionAgg.ftSum += curFtSum - runSnapshot.ftSum
        sessionAgg.ftSamples += cur.ftSamples - runSnapshot.ftSamples
        runSnapshot = { ...cur, ftSum: curFtSum }
        syncMetrics()
        break
      }

      case 'warning':
        pushNote('warning', event.message || '')
        break

      case 'discard_text':
        // 上一轮吐的是没解析成功的工具调用协议文本，不是回答 —— 从气泡里撤掉
        discardText()
        break

      case 'error':
        errors.value.push(String(event.message || 'Agent 执行失败'))
        pushNote('error', event.message || 'Agent 执行失败')
        break

      case 'done':
        clearPlaceholder()
        if (typeof event.answer === 'string' && event.answer) {
          // done.answer 是最终全文：若正文气泡已有内容就整体替换，避免重复
          if (openTextIndex >= 0 && messages.value[openTextIndex]) {
            messages.value[openTextIndex].content = event.answer
          }
        }
        if (event.corrections) corrections.value = Number(event.corrections)
        if (Array.isArray(event.errors)) errors.value = event.errors
        closeText()
        break

      default:
        break
    }
  }

  /**
   * 执行一轮 Agent 任务
   *
   * @returns 最终回复全文
   */
  const send = async (opts: AgentRunOptions): Promise<string> => {
    if (isGenerating.value) return '';
    // ds-free 自检运行中禁止发消息。
    // 为什么拦在这里而不是各调用方：这是**唯一**通往后端循环 / 前端循环的入口，
    // 改一处就覆盖了所有 useAgentChat 消费者（OS 助手抽屉、大屏智能体页…），
    // 只改 AiAssistant 会漏掉别的页面 —— 那时两边会抢同一个 DS 标签页、
    // 或者用户的消息被喂给自检的脚本化模型。
    if (selfCheckRunning.value) {
      pushNote('warning', 'ds-free 自检正在运行，先等它结束（或去「自检」页点中止）')
      return ''
    }

    // ---- 用户消息入流（附件一次性快照）----
    const imgs = [...(opts.images || [])]
    const docs = [...(opts.files || [])]
    const atts = [...(opts.attachments || [])]
    /**
     * 本轮 id：**一次提问生成一个**，同一次提问里的所有请求复用它。
     *
     * 为什么在 `send()` 里生成（而不是每个请求各生成一个）：后端把「这一轮做了哪些写操作」
     * 记在 `turnId` 下，而 ds-free 一轮里会发**多次** `/ai/agent/execute`（每次工具调用一次）、
     * api 链路则发一次 `/ai/agent/stream` —— 它们属于**同一轮**，必须共用一个 id，
     * 否则用户点一次「回退」只能撤掉这一轮的一部分。
     */
    const turnId = newTurnId()
    currentTurnId.value = turnId
    // 回退接口要的是 `{sessionId, turnId}`，而 UI 手上只有 `turnId` —— 这里记一份，
    // 让 `rollbackTurn(turnId)` 一个参数就能用（见 `lastSessionId` 的注释）。
    lastSessionId.value = String(opts.sessionId || '')
    messages.value.push({
      role: 'user',
      content: (opts.message || '').trim() || (imgs.length ? '[图片]' : '[附件]'),
      ...(atts.length ? { attachments: atts } : {})
    })
    closeText()
    // 新一轮开始：上一个回合的思考块到此为止（迟到的增量只允许补进**本轮**那个块）
    turnReasoning = null
    reasoningStartedAt = 0

    isGenerating.value = true
    controller = new AbortController()
    // ⚠️ 新的一次提问：后端那边计数从 0 重新开始 → 本轮快照也必须归零。
    //    不归零的话，新一轮的增量会算成负数（本轮小值 − 上轮大值），
    //    把会话累计往回拉 —— 那正是「状态条被刷新掉」的另一种表现。
    //    注意：只归零**快照**，会话累加器 `sessionAgg` 不动（它要跨提问保留）。
    runSnapshot = { rounds: 0, steps: 0, llmMs: 0, toolMs: 0, ftSum: 0, ftSamples: 0 }
    // 立即放一个「等待中」占位（首轮模型思考前 ds-free 还要先拉工具清单 / 加载扩展）。
    // 之后每一轮由 `waiting` 事件重新显示，真实内容一到就摘掉。
    showPlaceholder('正在理解你的需求…')

    try {
      const streamOpts = {
        message: opts.message,
        images: imgs,
        files: docs,
        attachments: atts,
        model: opts.model || undefined,
        provider: opts.provider,
        sessionId: opts.sessionId,
        // 本轮 id 下发给两条链路（api 链路的 `/ai/agent/stream`、ds-free 链路的
        // `/ai/agent/execute` / `/ai/agent/preview`）—— 后端据此记本轮写操作账本。
        turnId,
        userId: opts.userId,
        autoConfirm: opts.autoConfirm !== false,
        maxLoops: opts.maxLoops,
        signal: controller.signal
      }
      // ds-free：前端工具调用循环（浏览器扩展代发，协议上挂不了原生 FC）
      const answer = isDsFreeModel(opts.model)
        ? await runDsFreeAgentStream(streamOpts, {
            onEvent: handleEvent,
            onError: (msg) => pushNote('error', msg),
            // ds-free 的前端循环自己做二次确认（api 付费那条是后端挂起 + 本页调 confirm 接口）
            onConfirm: requestConfirm
          })
        : await postAgentStream(streamOpts, {
            onEvent: handleEvent,
            onError: (msg) => pushNote('error', msg)
          })
      // 兜底：模型一个字都没给（例如只调了工具就停了）
      if (!messages.value.some((m) => m.role === 'assistant' && m.content && !m.type)) {
        pushNote('warning', '本次没有收到文字回复，请查看上方执行过程。')
      }
      return answer
    } catch (e: any) {
      if (e?.name !== 'AbortError') {
        pushNote('error', e?.message || 'Agent 执行异常')
      }
      return ''
    } finally {
      isGenerating.value = false
      controller = null
      clearPlaceholder()
      closeText()
      // 收口思考块：跑完（成功/报错/中断）它都该折起来，否则会一直停在「正在思考…」
      closeReasoning()
      // ---- 轮末标记（**每一轮恰好一条**）----
      //
      // 回退组件就挂在这一轮的末尾，所以消费者必须能**可靠地**知道「一轮到哪结束了」。
      // 为什么选这里（`send()` 的 finally）当轮末点：
      //   · `done` 事件**不是**可靠的轮末点 —— ds-free 被中止时根本不发它
      //     （见 `agentDsFree.ts` 的 aborted 分支），api 链路也只是「正常结束」才发；
      //   · 而 finally 是成功 / 报错 / 用户主动停止**都必然经过**的那一个点。
      //
      // ⚠️ 要求「每轮一条」而不是「成功才加」：报错 / 被中止的那一轮里**可能已经写进去过东西**
      //    （工具跑一半失败是常态），那种情况恰恰最需要回退 —— 没标记就等于没有可点的按钮。
      // ⚠️ 顺序：必须在下面 `saveAgentTimeline` **之前** push，否则落库的快照里没有它，
      //    刷新之后最近一轮就回退不了。
      messages.value.push({ role: 'assistant', type: 'turn_end', turnId, content: '' })
      // 持久化「完整时间线」（含工具卡片）—— 刷新后才能复原卡片视图。
      // 放在 finally：成功 / 报错 / 主动停止都会存下当前这一版（含已跑过的过程卡片）。
      if (opts.sessionId) {
        try {
          await saveAgentTimeline(opts.sessionId, slimTimeline(messages.value), opts.userId)
        } catch (e) {
          console.warn('[agent] 时间线落库失败', e)
        }
      }
    }
  }

  /**
   * 回退**某一轮**（一次用户提问）的所有写操作 —— 用户在消息末尾那个回退组件上点一下时调用
   *
   * @param turnId 要回退的轮次 id：就是该轮 `turn_end` 标记里的 `turnId`
   *              （刷新之后那条标记仍在，靠 `slimTimeline` 把它落了库）
   * @param sessionId 会话 id；不传就用**最近一次 `send()` 用过的那个**（`lastSessionId`）
   * @returns `rollbackAgentTurn()` 的原样返回（UI 也可以只读 `turnRollback.value.summary`）
   *
   * ## 前端在这里**只做搬运**
   * 「哪些没退成、为什么」全由服务端算：本函数把结果原样交给 `turnRollback.summary`，
   * 一条都不合并、一条都不改写 —— 双链路同口径（回退语义只在服务端一处）。
   * 前端唯一的判断是「叫 `done` 还是 `fail`」，而那也是服务端给的 `ok`。
   *
   * ## 为什么要有 `busy`
   * 账本回退是**不可逆**的写操作：连点两次会让第二次拿到「已经退过了」的答案，
   * 用户看到的样子却是「第一次没生效」。`busy` 就是给按钮「在这期间禁用」用的。
   */
  const rollbackTurn = async (turnId: string, sessionId?: string): Promise<AgentRollbackResult> => {
    const tid = String(turnId || '')
    turnRollback.value = { turnId: tid, status: 'busy', summary: null }
    const res = await rollbackAgentTurn({
      sessionId: String(sessionId ?? lastSessionId.value ?? ''),
      turnId: tid
    })
    turnRollback.value = { turnId: tid, status: res.ok ? 'done' : 'fail', summary: res }
    return res
  }

  const stop = () => {
    controller?.abort()
    controller = null
    isGenerating.value = false
    pendingConfirms.forEach((resolve) => resolve(false))
    pendingConfirms.clear()
    clearPlaceholder()
    closeText()
    // 主动停止时也要收口，否则思考块留在「正在思考…」状态上不动
    closeReasoning()
  }

  return {
    // 状态
    messages,
    isGenerating,
    tools,
    activeModel,
    metaWarnings,
    imageCount,
    corrections,
    errors,
    metrics,
    toolCalls,
    hasRun,
    /** 本轮的轮次 id（一次提问一个）—— 回退组件用它标识「哪一轮」 */
    currentTurnId,
    /** 回退状态：`{turnId, status, summary}`，UI 直接照 `summary` 渲染 */
    turnRollback,
    // 方法
    send,
    stop,
    reset,
    /** 用户点击确认卡片时调用（确认 / 取消） */
    resolveConfirm,
    /** 用户点击「回退本轮」时调用 → 回退这一轮的所有写操作（增 / 删 / 改） */
    rollbackTurn
  }
}
