// composables/useAgentChat.ts
import { ref, computed, watch } from 'vue'
import {
  postAgentStream,
  confirmAgentTool,
  rollbackAgentTurn,
  type AgentRollbackItem,
  type AgentEvent,
  type AgentImageInput
} from '@/api/ai/agent'
import { runDsFreeAgentStream } from '@/api/ai/agentDsFree'
import { saveAgentTimeline, dropAgentTurn } from '@/api/ai/ai'
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

/**
 * 指挥家「派发专家」的元工具名。
 *
 * ⚠️ 它的 `tool_start`/`tool_result` **不建工具卡片**——那是对用户隐藏的内部机制
 * （用户 2026-10-11：单个专家应表现为"当前助手自己完成"，不该看到"派发专家"这类痕迹）。
 * 专家进度统一由 `experts` 协作卡片表达（且仅多专家时展示）。与后端
 * `roles.DELEGATE_TOOL_NAME` 逐字一致。
 */
const DELEGATE_TOOL_NAME = 'delegate_task'

/** 专家工作组里的**一行**（一个专家的一次派活） */
export interface AgentExpertProgress {
  /** 后端 `delegate_start`/`delegate_done` 的 `index`（本轮第 N 个委派）——用它定位行 */
  index: number
  /** 专家 key（bank/note/kb/stats 或 user:<id>） */
  key: string
  /** 专家显示名（后端已给中文名，如「题库专家」） */
  name: string
  /** 进行中 / 完成 / 失败 */
  status: 'running' | 'ok' | 'fail'
  /** 派给它的任务摘要（后端截断到 200 字） */
  task?: string
  /** 完成后的结论摘要 */
  summary?: string
  /**
   * 进行中的**最近一行**进展文案（`subagent_event` 的 `message`）—— 进行中时优先于 `task`
   * 显示，让用户看到它「现在」在干嘛，而不是只看到派给它的原始任务。
   */
  progress?: string
  /**
   * 子代理的阶段步骤（`subagent_event` 累积）。**只留最近若干条**（见
   * `SUBAGENT_STEPS_LIMIT`）：一轮子代理可能有几十次工具往返，全留会让快照与界面都膨胀。
   */
  steps?: Array<{
    /** 阶段：`start` / `round` / `tool_call` / `tool_result` / `wrapup` / `error` */
    phase: string
    /** 面向用户的一句话 */
    message: string
    /** 该步涉及的工具（`tool_call` / `tool_result` 有） */
    tool?: string
    /** 结果：`null` = 进行中 / `true` 成功 / `false` 失败 */
    success?: boolean | null
    /** 第几轮思考 */
    round?: number
  }>
}

/**
 * 一条**处理进度步骤**（用户 2026-10-11 方案 C：文档解析等的"干等转圈"→"步骤清单"）。
 *
 * ⚠️ 与 `thinking`（推理正文，已不再展示）**不是一回事**：这是**进度/阶段提示**，
 *    面向用户展示"后台在处理什么"，不含任何思维链内容。
 * 由后端 `progress` 事件驱动：同 `id` 重复发 = 更新该步（running → done/failed）。
 */
export interface AgentProgressStep {
  /** 步骤唯一 id（后端给，如 `doc_parse` / `save_images`） */
  id: string
  /** 面向用户的文案（中文） */
  message: string
  /** 进行中 / 完成 / 失败 */
  state: 'running' | 'done' | 'failed'
  /** 可选 emoji 图标 */
  icon?: string
}

/**
 * 去掉子代理产出里的 Markdown 标记（用户 2026-10-11：专家结论不该露 `*` `#` 之类符号）。
 *
 * 专家的结论走**纯文本插值**渲染（`AiChatStream` 的 `{{ ex.summary }}`），不是 md 渲染器
 * ——若后端把 `**加粗**`、`- 列表`、`# 标题`、`` `代码` `` 原样带过来，用户看到的就是一堆
 * 标记符号。这里做**保守剥离**（只去标记、不动正文），让结论读起来是干净的句子。
 *
 * 只处理常见行内/行首标记；不做完整 md 解析（专家结论多为短句，过度解析反而危险）。
 */
export function stripMarkdown(text: string): string {
  if (!text) return ''
  return (
    text
      // 行首：标题 #、引用 >、无序列表 -/*/+ 、有序列表 1.
      .replace(/^[ \t]*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/gm, '')
      // 围栏代码块标记 ``` / ~~~（保留里面的内容）
      .replace(/^[ \t]*(?:```|~~~).*$/gm, '')
      // 行内代码 `x` → x
      .replace(/`([^`]*)`/g, '$1')
      // 加粗 / 斜体：**x** __x__ *x* _x_ → x
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/__([^_]+)__/g, '$1')
      .replace(/\*([^*\n]+)\*/g, '$1')
      .replace(/_([^_\n]+)_/g, '$1')
      // 删除线 ~~x~~ → x
      .replace(/~~([^~]+)~~/g, '$1')
      // 链接 [文字](url) → 文字 ；图片 ![alt](url) → alt
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      // Markdown 表格 → 可读行（| 指标 | 数值 | 行转成「指标：数值」，分隔行删除）
      .replace(/[\s\S]*/, (s) => stripMarkdownTables(s))
      // 收尾：合并多余空行
      .replace(/\n{3,}/g, '\n\n')
      .trim()
  )
}

/**
 * 把 **Markdown 表格**转成「可读的行」（用户 2026-10-11：子代理结论里会出现
 * `| 指标 | 数值 |` / `|---|---|` 这类表格语法，纯文本插值下就是把竖线和横线糊在脸上）。
 *
 * 处理规则（**保守**，只认"标准表格形态"，别误伤正常的 `|`）：
 *   1. **分隔行**（只由 `|`、`-`、`:` 和空白组成的行，如 `|---|---|`）→ 整行删除；
 *   2. **表头行 + 数据行**：形如 `| a | b | c |`（或首尾竖线可省）的连续行 → 去首尾 `|`，
 *      单元格 trim 后：两列用 `：` 连（`指标：数值`），三列及以上用 ` · ` 连（`a · b · c`）。
 *
 * ⚠️ 只在**真出现分隔行**或**该行首尾有 `|`** 时才当表格处理 —— 避免把正文里偶尔出现的
 *    单个 `|`（如 "TCP | UDP 的区别"）误转。
 */
function stripMarkdownTables(text: string): string {
  const lines = text.split('\n')
  const isSeparator = (s: string) => /^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$/.test(s)
  const isTableRow = (s: string) => {
    const t = s.trim()
    // 首尾都有 `|`，或中间有 >=2 个 `|`（≥3 单元格）才算表格行；单个 `|` 不算
    return (t.startsWith('|') && t.endsWith('|') && t.length > 1) || (t.match(/\|/g) || []).length >= 2
  }
  const renderRow = (s: string) => {
    const cells = s
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((c) => c.trim())
      .filter((c) => c.length > 0)
    if (cells.length === 0) return ''
    if (cells.length === 2) return `${cells[0]}：${cells[1]}`
    return cells.join(' · ')
  }
  const out: string[] = []
  for (const line of lines) {
    if (isSeparator(line) && line.includes('-')) continue // 分隔行：丢弃
    if (isTableRow(line)) {
      const r = renderRow(line)
      if (r) out.push(r)
      continue
    }
    out.push(line)
  }
  return out.join('\n')
}

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
   *
   * ⚠️ **`experts` = 专家工作组卡片**（多专家并行干活的进度条）：一行一个专家，
   *    `content` 恒空、载荷在 `experts` 数组。指挥家同一轮并发派多个专家时产出。
   */
  type?: 'tool_result' | 'agent_note' | 'thinking' | 'reasoning' | 'tool_confirm' | 'turn_end' | 'experts' | 'progress'
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
   * `experts` 专用：专家工作组的各行（一行一个专家）。
   * 由 `delegate_start` 建行（status='running'）、`delegate_done` 回填（status='ok'|'fail'）。
   */
  experts?: AgentExpertProgress[]
  /**
   * `progress` 专用：处理步骤清单（**文档解析等耗时环节的进度**，用户 2026-10-11 方案 C）。
   *
   * 一条 `progress` 消息承载**整份步骤列表**；每次收到 `progress` 事件按 `id` 更新
   * 对应步骤（不存在则追加）。**非思维链**——只是"正在解析文档 / 已提取 X 字 Y 图"这类进度提示。
   * 该消息在**本轮结束**（`turn_end`）时若还有 running 步骤，应收口（见 `closeProgress`）。
   */
  steps?: AgentProgressStep[]
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
  /** 官方智能体角色 key（多智能体协同）；空 = 后端规则路由 */
  role?: string
  /** 用户自定义智能体 id（优先于 role） */
  agentId?: number
  /** 「注入历史记忆」开关（仅 ds-free-nb 有意义）：历史作为附件投递给 DS 网页 */
  injectHistory?: boolean
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
 * 每个专家行最多保留的**子代理步骤**条数（`subagent_event` 累积）。
 *
 * 一个子代理一轮可能跑几十次工具往返，事件量远超用户在卡片上想看的量。留最近若干条
 * 就够表达「它现在做到哪、刚做完什么」，也让落库快照不至于被步骤撑大。
 */
const SUBAGENT_STEPS_LIMIT = 20

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
    // 二次确认卡片的三件套：漏了哪个刷新后卡片都会走样 ——
    //   · `confirmId` 是身份（本地 resolve / 后端唤醒都靠它）；
    //   · `destructive` 决定标题与配色（漏了「批量删除」会显示成普通确认）；
    //   · `preview` 是「将影响什么」的清单（漏了用户不知道自己在确认什么）。
    if (m.confirmId) out.confirmId = m.confirmId
    if (m.destructive != null) out.destructive = m.destructive
    if (m.preview) out.preview = m.preview
    if (m.attempt != null) out.attempt = m.attempt
    if (m.attachments?.length) out.attachments = m.attachments
    // 专家工作组卡片：整条 `experts` 数组落库，刷新后仍能看到「这轮请了哪些专家、结果如何」。
    // （行内容短、行数=专家数，无需像 data 那样截断。）
    if (m.type === 'experts' && Array.isArray(m.experts)) {
      out.experts = m.experts
    }
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
 * 复原落库快照时**修正「没有收口」的卡片**（刷新后不该看到永远转圈 / 永远待确认的卡片）。
 *
 * 快照可能是在**一轮没跑完**时写下的（用户点了「停止」、或取消了确认后又立刻刷新）：
 *   · `tool_confirm` 仍是 `running` → 刷新后冒出一张**还能点**的确认卡，点下去却没人应答
 *     （后端那一轮早就不在了）；
 *   · `tool_result` 仍是 `running` → 永远转圈的工具卡片。
 * 这两类在快照里都**不可信**，复原时统一收口成 `fail`（与 `stop()` 的口径一致，文案中性）。
 *
 * ⚠️ 只修正「running」这一个状态：已 `ok` / `fail` / `cancelled` 的都是用户或后端**明确
 * 给出过**的结论，不许覆盖。
 */
export function normalizeRestoredMessages(msgs: any[]): any[] {
  if (!Array.isArray(msgs)) return []
  return msgs.map((m) => {
    if (!m || typeof m !== 'object' || m.status !== 'running') return m
    if (m.type === 'tool_confirm') {
      return { ...m, status: 'fail', content: '已取消 / 已中断' }
    }
    if (m.type === 'tool_result') {
      return { ...m, status: 'fail' }
    }
    return m
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
 * 一次「回退」的**结果**（UI 直接照它渲染）
 *
 * 前面五个字段就是 `rollbackAgentTurn()` 的返回值，**字段名一个字都没改**
 * （`ok` / `reason` / `reverted` / `skipped` / `failed` / `partial`）—— UI 要按它逐条渲染
 * 「哪些没退成、为什么」，改名等于让组件渲染不出东西。
 *
 * 后两个字段是「回退」这次要做的**另外两件事**的结果：
 *   · `userText` —— 这一轮用户提问的正文（消息已被摘掉，界面拿它回填输入框）；
 *   · `dropped` —— 这一轮的**对话**是否真的从「本地消息流 + 落库快照」里移除了。
 */
export interface TurnRollbackOutcome {
  /** 后端**写操作**回退成功（判据见 `rollbackAgentTurn`：`code===200` 且 `data` 形状对） */
  ok: boolean
  /** `ok = false` 时的原因（服务端原话，前端不编文案；`ok = true` 时是空串） */
  reason: string
  /** 真正回退掉的写操作条数（可能是 0 —— 比如这一轮只有查询） */
  reverted: number
  /** 明确**没回退**的条目（工具不支持、已被删掉…） */
  skipped: AgentRollbackItem[]
  /** 回退**报错**的条目 */
  failed: AgentRollbackItem[]
  /** 只退回了一部分的条目（如批量导入只撤掉了一部分题） */
  partial: AgentRollbackItem[]
  /**
   * 这一轮用户提问的正文（消息被移除后交给界面回填输入框；没找到则空串）
   *
   * ⚠️ 取的是**被摘掉的那条 user 消息的 `content`**（不是 `send()` 的入参）：
   * 纯图片 / 纯附件的那一轮，`send()` 会把它落成 `[图片]` / `[附件]`，
   * 回填输入框时也要跟用户当时看到的那条一致。
   */
  userText: string
  /**
   * 这一轮的对话是否真的从「本地消息流 + 落库快照」里移除了
   *
   * 判据是**服务端那半步成了没有**（`dropAgentTurn().ok`），不是「删掉了几行」——
   * 接口是幂等的，重试时服务端回 `dropped: 0` 同样是成功。
   *
   * ⚠️ 它与 `ok` **不是一回事**：`dropped=true` 只说明服务端的历史行删掉了，
   * 而整次回退还可能因为「时间线快照没写成功」被判成 `ok=false`（那时**本地消息一条不动**，
   * 见 `rollbackTurn` 的顺序说明）。界面要分开读这两个字段。
   */
  dropped: boolean
  /**
   * 服务端「按 `(user_id, session_id, turn_id)` 命中的行数」——**不考虑 `del_flag`**
   *
   * 它回答的是一个 `dropped` 回答不了的问题：**这一轮在服务端历史里到底有没有轮次标记**。
   *   · `historyMatched === 0` → 那一轮的行 `turn_id` 是空串（历史数据，ds-free 补写
   *     历史时前端还没带 `turnId`）→ 服务端**一行都匹配不到**；
   *   · `historyMatched > 0` + 服务端回的行数 `0` → **已经删过了**（接口幂等，重试的正常回执）。
   *
   * ⚠️⚠️ 上面那句里的「行数」是 **`AgentDropTurnResult.dropped`**（`api/ai/ai.ts`，
   *    那是**数字**），**不是**本接口上的 `outcome.dropped` —— 本接口的 `dropped` 是
   *    **布尔**（见上一条字段说明：只表示「服务端那半步成了」）。两者的名字撞了，
   *    把 `outcome.dropped === 0` 当行数写会永远读成「一行都没删」（布尔 `false` 也不是 0）。
   *    本接口**没有**把行数透出去 —— 界面要区分「删掉了」与「已经删过了」时先说一声。
   *
   * ⚠️ 界面**不许**因为它是 0 就以为「没什么可删的」而跳过本地移除 ——
   *    旧数据在服务端删不动，本地消息照样要从消息流与快照里摘掉（否则用户点了没反应）。
   * 服务端没给这个字段（老后端）时归 0，形状恒定，UI 不用写判空分支。
   */
  historyMatched: number
}

/**
 * **某一轮**的回退状态（UI 直接照 `status` + `outcome` 渲染）
 *
 * ⚠️ 这里**只有两个字段**：轮次 id 是**外层记录的键**（`rollbackStates[turnId]`）。
 * 旧版是一份「最近一次回退」的扁平状态（`{turnId, status, summary}`），
 * 那**存不下两轮的结果** —— 用户先回退第 1 轮、再回退第 2 轮，第一轮的结果就被覆盖了，
 * 而界面上两个回退组件都还在、各自显示同一份（后一次）结果。
 */
export interface TurnRollbackState {
  /**
   * `idle` = 没点过；`busy` = 请求在飞（按钮要禁用，否则连点会打两次账本）；
   * `done` = 两件事都成了；`fail` = 被服务端拒了 / 网络挂了 / 只成了一半（看 `outcome.reason`）
   */
  status: 'idle' | 'busy' | 'done' | 'fail'
  /** 回退结果（`busy` 时是 null，其余状态都有值） */
  outcome: TurnRollbackOutcome | null
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
  /**
   * **按轮**存的回退状态（键 = `turnId`，值见 `TurnRollbackState`）
   *
   * 为什么不是一份「最近一次回退」：用户 2026-09-22 的裁决是**每一轮都能点回退**，
   * 界面上会同时挂着好几个回退组件。单份状态会被后一次覆盖 —— 第 1 轮的结果会显示在
   * 第 2 轮的组件下面（两边读的是同一份），用户根本看不出那是哪一轮的。
   */
  const rollbackStates = ref<Record<string, TurnRollbackState>>({})
  /**
   * 写某一轮的状态（**整对象替换**而不是 `rollbackStates.value[tid] = …`）
   *
   * 替换整份对象是为了让「新键」也一定能被 Vue 的依赖收集看到：
   * `ref({})` 装的是 `reactive` 代理，直接加键在 Vue 3 里本来也能追踪，
   * 但 UI 若把某个组件的结果**解构**出去用（`const s = rollbackStates.value[id]`），
   * 只有替换整份对象才能保证既有的解构引用被重新求值。
   */
  const setRollbackState = (
    tid: string,
    status: TurnRollbackState['status'],
    outcome: TurnRollbackOutcome | null
  ) => {
    rollbackStates.value = { ...rollbackStates.value, [tid]: { status, outcome } }
  }
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

  /**
   * 会话累计统计的**落库快照**（随 timeline 快照一起存）
   *
   * ⚠️ 存的是**原始累加器**（含 `ftSum`/`ftSamples`），不是展示投影 `metrics`：
   *    `firstTokenMs` 是平均值，跨会话恢复必须靠「总和 + 样本数」才能正确接着累加，
   *    直接存平均值会在下一次还原时算错（平均值不能相加）。
   */
  const metricsSnapshot = () => ({
    rounds: sessionAgg.rounds,
    steps: sessionAgg.steps,
    llmMs: sessionAgg.llmMs,
    toolMs: sessionAgg.toolMs,
    ftSum: sessionAgg.ftSum,
    ftSamples: sessionAgg.ftSamples
  })

  /**
   * 从落库快照**还原会话累计统计**（刷新 / 切换会话后调）
   *
   * 入参是 `metricsSnapshot()` 的产物（原始累加器形状）。缺字段按 0 处理；
   * 非法 / 缺失（老会话无统计）→ 全部归零（与升级前行为一致，不倒退）。
   */
  const restoreMetrics = (snap?: Record<string, number> | null) => {
    const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0)
    sessionAgg.rounds = n(snap?.rounds)
    sessionAgg.steps = n(snap?.steps)
    sessionAgg.llmMs = n(snap?.llmMs)
    sessionAgg.toolMs = n(snap?.toolMs)
    sessionAgg.ftSum = n(snap?.ftSum)
    sessionAgg.ftSamples = n(snap?.ftSamples)
    // 还原后本轮快照也归零 —— 下一轮 `send` 的增量从「已还原的会话量」起算，才不会被顶掉
    runSnapshot = {
      rounds: sessionAgg.rounds,
      steps: sessionAgg.steps,
      llmMs: sessionAgg.llmMs,
      toolMs: sessionAgg.toolMs,
      ftSum: sessionAgg.ftSum,
      ftSamples: sessionAgg.ftSamples
    }
    syncMetrics()
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
    rollbackStates.value = {}
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
    // ⚠️ 用户 2026-10-11（二次定案，回退"不暴露"）：**重新累加推理正文**（content 恢复有值），
    //    以便 `AgentReasoning` 能把思维链**实时逐字展示**给用户（"深度思考思维链暴露出来给用户看"）。
    // 有推理发生就摘掉「等待中」占位。
    clearPlaceholder()
    if (!openReasoning) {
      // 本轮已有思考块（已收口）→ 迟到增量：折回来继续追加内容 + 顺延耗时，不新开块
      if (turnReasoning) {
        // ⚠️ **必须操作 `messages.value` 里的响应式代理**（见下方长注释），不能改闭包里的 raw 对象
        const i = messages.value.indexOf(turnReasoning)
        if (i >= 0) {
          messages.value[i].content = (messages.value[i].content || '') + delta
          messages.value[i].secs = Math.max(1, Math.round((Date.now() - reasoningStartedAt) / 1000))
        } else {
          turnReasoning.content += delta
          turnReasoning.secs = Math.max(1, Math.round((Date.now() - reasoningStartedAt) / 1000))
        }
        return
      }
      openReasoning = { role: 'assistant', type: 'reasoning', content: '' }
      turnReasoning = openReasoning
      reasoningStartedAt = Date.now()
      messages.value.push(openReasoning)
    }
    /*
     * ⚠️⚠️ 卡死真凶（用户 2026-10-11 报「卡在 The 后不动、最后才整段出现」）：
     *   `messages` 是 `ref([])`，Vue 3 的数组元素**只有通过代理读出来**才带依赖追踪。
     *   闭包变量 `openReasoning` 指向的是**push 进去的那个 raw 对象**，直接 `openReasoning.content += delta`
     *   改的是 **raw 对象**（无代理 setter）→ **不触发 Vue 重渲染** → 界面停住；直到后续某次
     *   （如正文/工具/轮末）触发了整数组的响应式刷新，才把累计的内容"一次性刷出"。
     *   正文之所以没这问题：`appendText` 用的是 `messages.value[openTextIndex]`（**代理对象**）。
     *   故此处必须同样**从 `messages.value` 取回该消息的代理**再改。
     */
    const idx = messages.value.indexOf(openReasoning)
    if (idx >= 0) {
      messages.value[idx].content = (messages.value[idx].content || '') + delta
    } else {
      // 兜底：找不到（理论上不会）→ 退回改 raw，至少不丢内容
      openReasoning.content += delta
    }
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
    const secs = Math.max(1, Math.round((Date.now() - reasoningStartedAt) / 1000))
    // ⚠️ 改**数组里的代理消息**（`openReasoning` 是 raw 引用，直接改不触发更新）
    const i = messages.value.indexOf(openReasoning)
    if (i >= 0) messages.value[i].secs = secs
    else openReasoning.secs = secs
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
      // ⚠️ 必须改**数组里的代理对象**（`pendingPlaceholder` 是 push 进去的 raw 引用，直接改不触发更新，
      //    与 `appendReasoning` 卡死同因）
      const i = messages.value.indexOf(pendingPlaceholder)
      if (i >= 0) messages.value[i].content = label
      else pendingPlaceholder.content = label
      return
    }
    pendingPlaceholder = { role: 'assistant', type: 'thinking', content: label }
    messages.value.push(pendingPlaceholder)
  }

  /**
   * **处理进度步骤清单**（用户 2026-10-11 方案 C）——`progress` 事件驱动。
   *
   * 一条用户提问里所有 `progress` 事件都汇总到**同一条** `type:'progress'` 消息的 `steps` 数组：
   * 按 `id` 更新对应步骤（不存在则追加），于是前端渲染成一个**逐步推进的清单**
   * （进行中的转圈、完成的打勾、失败的红叉），把"干等转圈"变成"看得见的处理流程"。
   *
   * 与 `waiting` 占位（转圈气泡）的关系：进度清单**优先**呈现——收到 progress 时先摘掉转圈占位，
   * 避免两个等待 UI 同时出现。
   */
  let pendingProgress: AgentChatMessage | null = null
  const upsertProgressStep = (event: AgentEvent) => {
    const id = String(event.id || '')
    if (!id) return
    // 有进度了 → 摘掉那个抽象转圈占位（进度清单本身就是更信息化的等待态）
    clearPlaceholder()
    if (!pendingProgress) {
      pendingProgress = { role: 'assistant', type: 'progress', content: '', steps: [] }
      messages.value.push(pendingProgress)
    }
    // ⚠️ 必须改**数组里的代理消息**的 `steps`（`pendingProgress` 是 push 进去的 raw 引用，
    //    直接改它的属性不触发 Vue 更新 —— 与 `appendReasoning` 同因）
    const mi = messages.value.indexOf(pendingProgress)
    const target = mi >= 0 ? messages.value[mi] : pendingProgress
    if (!target.steps) target.steps = []
    const steps = target.steps as AgentProgressStep[]
    const state: AgentProgressStep['state'] =
      event.state === 'done' ? 'done' : event.state === 'failed' ? 'failed' : 'running'
    const step: AgentProgressStep = {
      id,
      message: String(event.message || ''),
      state,
      icon: event.icon
    }
    const i = steps.findIndex((s) => s.id === id)
    if (i >= 0) steps[i] = step
    else steps.push(step)
  }

  /**
   * 收口进度清单：把仍未完成的步骤标为已完成（本轮结束/生成正文时调）。
   * 避免最后一步永远停在 `running` 转圈。
   */
  const closeProgress = () => {
    if (!pendingProgress) return
    const mi = messages.value.indexOf(pendingProgress)
    const target = mi >= 0 ? messages.value[mi] : pendingProgress
    for (const s of (target.steps as AgentProgressStep[]) || []) {
      if (s.state === 'running') s.state = 'done'
    }
    pendingProgress = null
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
   * 把当前时间线**尽快**补写落库（best-effort）—— 确认卡片状态一变就调。
   *
   * 为什么需要：快照原先**只在轮末**（`send()` 的 finally）与回退时写。用户取消（或确认）
   * 一张确认卡后、本轮收尾之前若刷新页面，磁盘上仍是「待确认」的那一版 → 刷新后卡片又
   * 变回可点的样子（用户报的 bug）。所以在确认状态一变就补写一次。
   *
   * 用 0ms 去抖合并同一拍里的多次调用（`resolveConfirm` 与紧随的 `tool_confirm_resolved`
   * 是同一件事的两半）；`fire-and-forget`，失败只记 console —— 落库失败不能挡住本地状态。
   */
  let timelineSaveTimer: ReturnType<typeof setTimeout> | null = null
  const persistTimelineSoon = () => {
    const sid = lastSessionId.value
    if (!sid) return
    if (timelineSaveTimer) clearTimeout(timelineSaveTimer)
    timelineSaveTimer = setTimeout(() => {
      timelineSaveTimer = null
      saveAgentTimeline(sid, slimTimeline(messages.value), undefined, metricsSnapshot()).catch(
        (e) => {
          console.warn('[agent] 确认状态落库失败', e)
        }
      )
    }, 0)
  }

  /**
   * 用户点了「确认」/「取消」（页面调用）
   *
   * - ds-free：前端循环在等 → 本地 resolve
   * - api 付费：后端循环在挂起 → POST `/ai/agent/confirm` 唤醒
   *
   * `decision` 兼容两种形状：
   *   · `boolean` —— 老调用方「确认 / 取消」，行为一个字不变；
   *   · `{ approved, edited }` —— 可编辑草稿卡片回传的改动（`edited` 只对
   *     `question_manage.batch_import` 有意义，见 `confirmAgentTool`）。ds-free 本地循环
   *     只吃 `approved`（前端不落库、暂不支持改动），`edited` 仅随 api 链路送服务端。
   */
  const resolveConfirm = async (
    confirmId: string,
    decision: boolean | { approved?: boolean; edited?: Record<string, any> | null }
  ) => {
    const approved = typeof decision === 'boolean' ? decision : decision?.approved === true
    const edited = typeof decision === 'object' && decision ? decision.edited : undefined
    const msg = messages.value.find(
      (m) => m.type === 'tool_confirm' && m.confirmId === confirmId
    )
    if (msg) {
      msg.status = approved ? 'ok' : 'fail'
      // 状态一变就补写快照 —— 否则用户取消后、轮末之前刷新，磁盘上还是「待确认」那一版
      persistTimelineSoon()
    }
    const local = pendingConfirms.get(confirmId)
    if (local) {
      pendingConfirms.delete(confirmId)
      local(approved)
      return
    }
    await confirmAgentTool(confirmId, approved, edited)
  }

  /**
   * 等本轮生成收尾（`isGenerating` 归 false）—— 供「让 AI 重新生成」用。
   *
   * 「重新生成」= 先取消当前确认卡片，**必须等本轮完全收尾**才能发起下一轮：
   * `send()` 开头有 `if (isGenerating.value) return` 的闸门，本轮没结束时再调会直接被打回。
   */
  const whenIdle = (): Promise<void> => {
    if (!isGenerating.value) return Promise.resolve()
    return new Promise<void>((resolve) => {
      const stopWatch = watch(isGenerating, (v) => {
        if (!v) {
          stopWatch()
          resolve()
        }
      })
    })
  }

  const appendText = (chunk: string) => {
    if (!chunk) return
    // 正文开始了 ⇒ 这一轮的思考已经结束，把块收口（UI 会折起来，别让它继续长）
    closeReasoning()
    // 正文开始 ⇒ 文档处理阶段结束 → 进度清单收口（未完成步骤标 done），别让最后一步一直转圈
    closeProgress()
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
    // ⚠️ 工具调用标志「本轮模型的这段思考已结束」，下一轮模型（工具执行完之后）
    //    会重新思考 —— 必须清空 turnReasoning，否则下一轮的思考会被**追加进第一块**
    //    （表现为：多轮深度思考全挤在同一张卡片里，用户只看到一个越滚越长的思考块）。
    //    ds-free 那条「迟到增量」路径（纯文本、无工具）不受影响：它不会经过 pushTool。
    turnReasoning = null
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
        m.status = event.success ? 'ok' : (event.cancelled ? 'cancelled' : 'fail')
        m.detail = detail
        m.errors = errs
        m.data = event.data
        m.content = detail || m.content
        return
      }
    }
    // ⚠️ 用户取消（`cancelled`）**不补卡片**：取消不是失败，不该在界面上多出一张红色的
    //    「批量删除失败」。确认卡片本身在 `tool_confirm_resolved` 时已经显示「已取消」，
    //    再补一条失败卡就是重复且错误的信息（用户 2026-10-16 报的就是这个）。
    if (event.cancelled) return
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

  /**
   * 找到「**本轮**的专家工作组卡片」（本轮没有则返回 undefined）
   *
   * ⚠️ 必须按**轮边界**（`turn_end` 标记）限定，否则会误取**上一轮**的卡片 ——
   * 新专家的行会被追加到历史那轮的卡片里，用户看到的是「上一轮突然多了一行」。
   * 做法：从末尾往前，先遇到 `experts` 就取它；先遇到 `turn_end`（本轮起点）则本轮还没有卡片。
   */
  const findExpertCard = () => {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.type === 'experts') return m
      if (m.type === 'turn_end') return undefined
    }
    return undefined
  }

  /** `delegate_start` → 建/追加一行「专家开工中」 */
  const pushExpertStart = (event: AgentEvent) => {
    clearPlaceholder()
    closeText()
    closeReasoning()
    // 同 pushTool：专家开工标志着「本轮思考结束」，下一轮思考需新建块（勿并入第一块）
    turnReasoning = null
    const ag = event.agent || {}
    const row: AgentExpertProgress = {
      index: Number(event.index ?? 0) || 0,
      key: String(ag.id || ''),
      name: String(ag.name || ag.id || '专家'),
      status: 'running',
      task: stripMarkdown(String(event.task || ''))
    }
    const card = findExpertCard()
    if (card && Array.isArray(card.experts)) {
      card.experts.push(row)
    } else {
      messages.value.push({
        role: 'assistant',
        type: 'experts',
        content: '',
        experts: [row]
      })
    }
  }

  /** `delegate_done` → 按 `index` 回填该行的状态与结论 */
  const fillExpertDone = (event: AgentEvent) => {
    const idx = Number(event.index ?? -1)
    const ag = event.agent || {}
    const card = findExpertCard()
    if (card && Array.isArray(card.experts)) {
      // 优先按 index 精确回填——**且要求该行仍在 running**：后端已改 index 为「整轮全局唯一」，
      // 正常不会撞号；这里再挡一道，避免异常情况下把已完成的行重复回填、让真正的那行留在转圈。
      let row = idx >= 0 ? card.experts.find((e) => e.index === idx && e.status === 'running') : undefined
      if (!row) {
        // index 缺失/越界/已回填过 → 回退到「按 key 找最近一个 running 行」
        const key = String(ag.id || '')
        row = [...card.experts].reverse().find((e) => e.key === key && e.status === 'running')
      }
      if (!row && idx >= 0) {
        // 仍找不到：index 对应行已存在（已回填）时，直接按 index 取回来补（幂等，避免漏状态）
        row = card.experts.find((e) => e.index === idx)
      }
      if (row) {
        row.status = event.success ? 'ok' : 'fail'
        row.summary = stripMarkdown(String(event.summary || ''))
        return
      }
    }
    // 卡片丢了（异常）：补一张只含该行的卡片，别让专家凭空消失
    messages.value.push({
      role: 'assistant',
      type: 'experts',
      content: '',
      experts: [
        {
          index: idx >= 0 ? idx : 0,
          key: String(ag.id || ''),
          name: String(ag.name || ag.id || '专家'),
          status: event.success ? 'ok' : 'fail',
          summary: stripMarkdown(String(event.summary || ''))
        }
      ]
    })
  }

  /**
   * `subagent_event` → 把子代理的阶段进展挂到专家卡片对应那一行（进行中时展示）。
   *
   * 观测是**旁路**：行找不到就**什么都不做** —— 绝不像 `delegate_start` 那样补建卡片。
   * 补建出来的行没有任务摘要、还可能把「单个专家」变成「多专家协同」，凭空改变产品形态。
   * 正常序列是 `delegate_start`（建行）先到、`subagent_event` 随后，行一定在。
   */
  const pushSubagentEvent = (event: AgentEvent) => {
    const idx = Number(event.index ?? -1)
    const ag = event.agent || {}
    const card = findExpertCard()
    if (!card || !Array.isArray(card.experts)) return
    // 优先按 index 定位（后端保证与 delegate_start 同源）；index 缺失时退回「按 key 找最近一行」。
    let row = idx >= 0 ? card.experts.find((e) => e.index === idx) : undefined
    if (!row) {
      const key = String(ag.id || '')
      row = [...card.experts].reverse().find((e) => e.key === key)
    }
    if (!row) return
    // 已完成的行不再接受进展（迟到的事件）：别让「对勾」后面又冒出「第 2 轮思考」。
    if (row.status !== 'running') return
    if (!Array.isArray(row.steps)) row.steps = []
    row.steps.push({
      phase: String(event.phase || ''),
      message: String(event.message || ''),
      tool: event.tool ? String(event.tool) : undefined,
      success: typeof event.success === 'boolean' ? event.success : null,
      round: Number(event.round) || 0
    })
    // 只留最近 N 条：长任务会有几十步，全留既费内存又没人看
    if (row.steps.length > SUBAGENT_STEPS_LIMIT) {
      row.steps.splice(0, row.steps.length - SUBAGENT_STEPS_LIMIT)
    }
    if (event.message) row.progress = String(event.message)
  }

  /**
   * 轮末清理：**只有一位专家时，不显示「专家协同」卡片**。
   *
   * 产品口径（用户 2026-10-11）：单个专家被派活时，对用户就当是**主助手自己完成的**
   * ——不暴露"我们内部有专家协同"这层；只有**真的多个专家并行**（一行一个）时才值得
   * 展示那张协同卡片。故在轮末（`turn_end` 前）检查：本轮 experts 卡片若只有 1 行，
   * 直接移除（专家名/结论对用户无意义，主助手正文已整合了结果）。
   */
  const dropSoloExpertCard = () => {
    const card = findExpertCard()
    if (card && Array.isArray(card.experts) && card.experts.length <= 1) {
      const i = messages.value.indexOf(card)
      if (i >= 0) messages.value.splice(i, 1)
    }
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

      case 'progress':
        // 处理进度（文档解析等耗时环节）→ 汇总进"步骤清单"消息（用户 2026-10-11 方案 C）
        upsertProgressStep(event)
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
        if (m) {
          m.status = event.approved ? 'ok' : 'fail'
          persistTimelineSoon()
        }
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
        // `delegate_task` 是内部机制，不建工具卡片（见 DELEGATE_TOOL_NAME 注释）
        if ((event.tool || '') !== DELEGATE_TOOL_NAME) pushTool(event)
        break

      case 'tool_result':
        if ((event.tool || '') !== DELEGATE_TOOL_NAME) fillTool(event)
        break

      // 指挥家并发派活 → 专家工作组卡片（一行一个专家）。
      // `delegate_start` 建行（转圈），`delegate_done` 按 `index` 回填状态与结论。
      case 'delegate_start':
        pushExpertStart(event)
        break

      case 'delegate_done':
        fillExpertDone(event)
        break

      // 子代理中间过程（观测旁路）→ 挂到专家卡片那一行的进度上。
      case 'subagent_event':
        pushSubagentEvent(event)
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
        // 多智能体协同：官方角色 / 用户自定义智能体（后者优先）。透传给两条链路。
        role: opts.role,
        agentId: opts.agentId,
        // 仅 ds-free-nb 有意义：注入历史并作为附件投递（后端按 provider 收口）
        injectHistory: opts.injectHistory === true,
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
      // 单专家「专家协同」卡片在轮末丢弃（只有多专家并行才展示协同 UI，见函数注释）——
      // 必须在 push `turn_end` **之前**做（`findExpertCard` 以 `turn_end` 为轮边界）。
      dropSoloExpertCard()
      // 进度清单收口：轮末若还有 running 步骤（如解析中途报错），标记完成，别让它一直转圈
      closeProgress()
      messages.value.push({ role: 'assistant', type: 'turn_end', turnId, content: '' })
      // 持久化「完整时间线」（含工具卡片）—— 刷新后才能复原卡片视图。
      // 放在 finally：成功 / 报错 / 主动停止都会存下当前这一版（含已跑过的过程卡片）。
      if (opts.sessionId) {
        try {
          await saveAgentTimeline(
            opts.sessionId,
            slimTimeline(messages.value),
            opts.userId,
            // 会话累计统计随快照一起落库 —— 刷新后才能复原底部状态条（否则归零）
            metricsSnapshot()
          )
        } catch (e) {
          console.warn('[agent] 时间线落库失败', e)
        }
      }
    }
  }

  /**
   * 定位**某一轮**的消息在本地消息流里的范围（**不改 messages**）
   *
   * ## 一轮的范围怎么定（判据是 `turnId`，不是下标）
   * 「这一轮」= 该轮的**用户消息** + 它之后的**一切**（工具卡 / 思考块 / 正文 / 提示），
   * 直到那条 `type:'turn_end'` 标记为止 —— 标记是 `turnId` 唯一的落点，所以：
   *   ① 先用 `type==='turn_end' && turnId===tid` 找到这一轮的**末尾**；
   *   ② 再往回找最近的一条 `role==='user'` 当**开头**（`send()` 里先 push 用户消息，
   *      所以一轮之内不会再出现第二条 user 消息）。
   * ⚠️ 绝不能用「最后 N 条」之类的下标口径：用户回退的可能是**中间**那一轮
   *   （每一轮都能点回退），按下标删会把别的轮次一起带走。
   *
   * ## 找不到标记时返回 `null`（**什么都不删**）
   * 只有 `turn_end` 标记带 `turnId`；标记不在（老快照 / 被人手改过）就没有任何凭据
   * 能证明哪些消息属于这一轮 —— 此时如实返回 `null`（上层据此报「提问正文拿不到」）、
   * 一条不动，而不是猜一把删掉别人的轮次。
   *
   * ## 为什么是「先定位、后摘除」两个动作
   * `rollbackTurn` 必须先算出「摘掉之后的那份列表」并**把它写进快照**，写成了才动本地
   * （顺序反转：服务端 + 快照都成了，才轮到界面）。所以定位这一步**不许有副作用** ——
   * 否则「快照没写成功」时本地已经被删了，用户看到消息没了、刷新又回来。
   */
  const locateTurn = (tid: string): { startIdx: number; endIdx: number; userText: string } | null => {
    const endIdx = messages.value.findIndex((m) => m.type === 'turn_end' && m.turnId === tid)
    if (endIdx < 0) return null
    for (let i = endIdx - 1; i >= 0; i--) {
      if (messages.value[i].role === 'user') {
        return { startIdx: i, endIdx, userText: messages.value[i].content || '' }
      }
    }
    return null
  }

  /**
   * 回退**某一轮**（一次用户提问）—— 用户在消息末尾那个回退组件上点一下时调用
   *
   * 一次点击要**做完三件事**（用户 2026-09-22 的原话：「点回退后 llm 本次的回答自动消失、
   * 用户 A 的提问也自动消失，并且提问内容自动回到用户的输入框里」）：
   *   ① 撤销这一轮的**写操作** → `POST /ai/agent/rollback`（账本在后端，前端只搬运）；
   *   ② 把这一轮的**对话**从历史里抹掉 → `POST /ai/conversation/drop-turn`
   *      （逻辑删库里的消息行）+ 从本地 `messages` 里摘掉这一轮的那些消息；
   *   ③ 把用户提问的正文交给界面回填输入框 → `outcome.userText`。
   *
   * 最后还要**重新覆盖写一次时间线快照**：刷新后前端是拿快照复原消息流的，
   * 不重写的话被删的那一轮会**在刷新之后回来**（磁盘上还是旧的整会话快照）。
   *
   * ## 会话 id 从哪来（**两个来源，显式入参优先**）
   * `sessionId` 实参 > `lastSessionId`（最近一次 `send()` 用过的那个）。为什么要有实参：
   * `lastSessionId` **只有 `send()` 会写**，而用户**刷新页面**之后消息是从快照复原的、
   * 根本没走 `send()` —— 那时它是空串。于是两个请求都带 `sessionId:''`：服务端按空会话
   * 过滤命中 0 行、还回 `code:200` 假成功，前端却把本地消息摘了、快照也没重写 →
   * **刷新一次刚回退的那一轮又全回来了**（用户 2026-09-23 报的线上 bug）。
   * 页面手上正好有「正在显示的那个会话」，所以由它显式传进来；`lastSessionId` 留着兜底
   * （同一次提问之后立刻回退仍然只要一个 `turnId` 就能走通）。
   *
   * ## 执行顺序与失败语义（都是刻意的）
   * 0. **两个来源都拿不到会话 id → 一个请求都不发**，如实报
   *    `reason='不知道这一轮属于哪个会话，无法回退'`、`status='fail'`，**本地一条消息都不删**
   *    （编一个空会话 id 发出去只会拿到「假成功」，那才是这次 bug 的形态）；
   * 1. 先调 `rollback`：**写操作**是这一轮真正落到库里的东西，它没撤成就**什么都不许删**
   *    （对话留着，用户还能看到自己问过什么、也能重试）；
   * 2. `rollback.ok=false`（例如 403 / 该轮不存在）→ 消息留着、`status='fail'`、
   *    `reason` 原样带回（服务端原话，前端不编）；
   * 3. `rollback.ok=true` 才去调 `drop-turn`。这一步没成（`dropAgentTurn.ok=false`）时
   *    **本地消息也留着**，并如实报 `ok=false` + 服务端原话 —— 那就是「写操作撤了、
   *    对话没删」的半成状态，界面必须能让用户看见（而不是装作全成了）；
   * 4. **先把「摘掉这一轮之后的那份快照」写进库，写成了才动本地 `messages`**。
   *    顺序反过来的话（先摘本地、再 PUT 快照），PUT 失败时磁盘上还是旧的整会话快照，
   *    用户看到「消息没了」→ 一刷新这一轮又回来了，而且 `outcome.ok` 还是 `true`，
   *    界面报成功、失败只进 console —— 那正是这次线上 bug 的第二半。
   *    重试是安全的：两个接口幂等、快照是覆盖写。
   * 5. 快照写成了 → 摘掉这一轮的消息、把提问正文放进 `userText`、`status='done'`。
   *
   * ## 前端在这里**只做搬运**（与 `agentDsFree` 的双链路同口径）
   * 「哪些没退成、为什么」全由服务端算，一条都不合并、一条都不改写；
   * 前端唯一的判断是「叫 `done` 还是 `fail`」，而那也是服务端给的 `ok`。
   *
   * ## `historyMatched === 0` **不改变任何一步**
   * 它是「这一轮在服务端历史里没有轮次标记」（旧数据）的凭据，只是**信息**：
   * `drop` 那一步照调（实测这一档服务端回 `{dropped: 0, matched: 0}`）、快照照重写、
   * 本地消息照摘 —— 界面据此说得出「历史里没有这一轮」，但**不许**拿它短路任何一步。
   * （要区分「删掉了」与「已经删过了」还差服务端的**行数** —— 本接口没透出去，
   *   见 `historyMatched` 字段说明那条 ⚠️。）
   *
   * ## 为什么要有 `busy`（而且是**按轮**存的）
   * 账本回退是**不可逆**的写操作：连点两次第二次会拿到「已经退过了」的答案，
   * 用户看到的样子却是「第一次没生效」。`busy` 就是给按钮「在这期间禁用」用的；
   * 按轮存是因为每一轮都有一个自己的回退组件（见 `rollbackStates` 的注释）。
   *
   * ## `status` 不会永久卡在 `busy`
   * 全程 `try/finally`：两个接口各自都吞掉自己的异常（都返回结果对象），
   * 所以能走到 `catch` 的只有本地逻辑出错 —— 那种情况也要把异常文本如实当理由带出去。
   *
   * @param turnId 要回退的轮次 id：就是该轮 `turn_end` 标记里的 `turnId`
   *              （刷新之后那条标记仍在，靠 `slimTimeline` 把它落了库）
   * @param sessionId 这一轮属于哪个会话（**页面显式传**：就是它正在显示的那个会话）。
   *                  不传时退回「最近一次 `send()` 用过的会话」；两个都拿不到就一个请求都不发。
   * @returns 这一轮的回退结果（UI 也可以只读 `rollbackStates.value[turnId].outcome`）
   */
  const rollbackTurn = async (
    turnId: string,
    sessionId?: string
  ): Promise<TurnRollbackOutcome> => {
    const tid = String(turnId || '')
    // 显式入参优先（页面手上就有），兜底才是「最近一次 `send()` 用过的那个」
    // （见 `lastSessionId` / 本函数头部注释里那段线上 bug 的说明）。
    const sid = String(sessionId || lastSessionId.value || '')
    const outcome: TurnRollbackOutcome = {
      ok: false,
      reason: '',
      reverted: 0,
      skipped: [],
      failed: [],
      partial: [],
      userText: '',
      dropped: false,
      historyMatched: 0
    }

    // ---- ⓪ 不知道这一轮属于哪个会话：**一个请求都不发** ----
    // 空会话 id 发出去服务端只会回一句 `code:200` 的假成功（按 `session_id=''` 过滤命中 0 行），
    // 于是界面把本地消息摘了、库里与快照都没动 —— 那正是「刷新后这一轮又回来」的成因。
    // 所以这里就地失败：消息一条不动，人话写进 `reason`（轮末那一格会显示它）。
    if (!sid) {
      outcome.reason = '不知道这一轮属于哪个会话，无法回退'
      setRollbackState(tid, 'fail', outcome)
      return outcome
    }

    setRollbackState(tid, 'busy', null)

    try {
      // ---- ① 撤销这一轮的写操作（第一步没成，后面一步都不做）----
      const rb = await rollbackAgentTurn({ sessionId: sid, turnId: tid })
      outcome.ok = rb.ok
      outcome.reason = rb.reason
      outcome.reverted = rb.reverted
      outcome.skipped = rb.skipped
      outcome.failed = rb.failed
      outcome.partial = rb.partial
      if (!rb.ok) {
        // 整体失败：**一条消息都不删**（用户还得看得见自己问过什么）
        setRollbackState(tid, 'fail', outcome)
        return outcome
      }

      // ---- ② 把这一轮的对话从会话历史里逻辑删掉 ----
      const dr = await dropAgentTurn({ sessionId: sid, turnId: tid })
      if (!dr.ok) {
        // 「写操作撤了、对话没删」—— 半成状态也按失败如实报（理由取服务端原话）
        outcome.ok = false
        outcome.reason = dr.reason
        setRollbackState(tid, 'fail', outcome)
        return outcome
      }
      outcome.dropped = true
      // 服务端「按 (user_id, session_id, turn_id) 命中了几行」（不看 del_flag）。
      // 只是**信息**：0 说明那一轮在服务端历史里没有轮次标记（旧数据），
      // **不改变任何一步**（见函数头部注释）。
      outcome.historyMatched = Number(dr.matched) || 0

      // ---- ③ 先算出「摘掉这一轮之后的消息列表」（**这一步不改 `messages`**）----
      // 定位与摘除拆开，是因为下面那一步（写快照）失败时本地必须原封不动。
      const plan = locateTurn(tid)
      outcome.userText = plan ? plan.userText : ''
      const afterTurn = plan
        ? [
            ...messages.value.slice(0, plan.startIdx),
            ...messages.value.slice(plan.endIdx + 1)
          ]
        : [...messages.value]

      // ---- ④ 先把快照写进库（**写成了才动本地**）----
      // 与 `send()` 的 finally 同一个接口、同一份 `slimTimeline` 产物：落库的是
      // 「摘掉这一轮之后的那一版消息流」，所以刷新后复原出来的消息流里没有它。
      // ⚠️ 不带 userId —— 与 `rollbackAgentTurn` 同口径，归属由服务端从令牌里取。
      // ⚠️ `saveAgentTimeline` 走 `request()`，`code !== 200` 会 `reject('error')` ——
      //    这个 reject **必须在这一步被接住并转成 `ok=false`**，不许吞进 console：
      //    吞了就成了「界面报成功、刷新后这一轮又回来」。
      try {
        await saveAgentTimeline(sid, slimTimeline(afterTurn), undefined, metricsSnapshot())
      } catch (e: any) {
        outcome.ok = false
        outcome.reason =
          '回退没完成：时间线快照没写成功，刷新后这一轮仍会回来（可以再点一次重试）'
        console.warn('[agent] 回退后时间线落库失败（本地消息保持不动）', e)
        setRollbackState(tid, 'fail', outcome)
        return outcome
      }

      // ---- ⑤ 快照写成了 → 现在才把这一轮从本地消息流里摘掉 ----
      // 悬挂的「未闭合气泡」指针不用管：`openTextIndex` / `pendingPlaceholder` /
      // `openReasoning` 只在一次 `send()` 期间有效，而那期间 UI 的回退按钮是禁用的
      // （`isGenerating`），轮末（`finally`）已把它们全部复位。
      if (plan) messages.value.splice(plan.startIdx, plan.endIdx - plan.startIdx + 1)
      setRollbackState(tid, 'done', outcome)
      return outcome
    } catch (e: any) {
      outcome.ok = false
      outcome.reason = String(e?.message || e)
      setRollbackState(tid, 'fail', outcome)
      return outcome
    } finally {
      // 兜底：任何一步意外跳出都不许把按钮永久留在禁用态
      if (rollbackStates.value[tid]?.status === 'busy') {
        setRollbackState(tid, outcome.ok ? 'done' : 'fail', outcome)
      }
    }
  }

  const stop = () => {
    controller?.abort()
    controller = null
    isGenerating.value = false
    // 中止时把还「待确认」的卡片收口成「已取消」：否则本轮 finally 的快照会把 running 的
    // 确认卡存下去，刷新后又冒出一张能点、却没人应答的卡片（用户报的 bug）。
    for (const m of messages.value) {
      if (m.type === 'tool_confirm' && m.status === 'running') m.status = 'fail'
    }
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
    /** 从落库快照还原会话累计统计（刷新 / 切换会话后由页面调用） */
    restoreMetrics,
    toolCalls,
    hasRun,
    /** 本轮的轮次 id（一次提问一个）—— 回退组件用它标识「哪一轮」 */
    currentTurnId,
    /**
     * 按轮存的回退状态：`rollbackStates[turnId] = { status, outcome }`。
     * 每一轮都能点回退，所以**每个组件读自己那一轮的键**（`rollbackStates[msg.turnId]`），
     * 别读「最后一份」—— 那会让先回退的那一轮显示成后一轮的结果。
     */
    rollbackStates,
    // 方法
    send,
    stop,
    reset,
    /** 用户点击确认卡片时调用（确认 / 取消） */
    resolveConfirm,
    /** 等本轮生成收尾（`isGenerating` 归 false）—— 「让 AI 重新生成」用 */
    whenIdle,
    /** 用户点击「回退本轮」时调用 → 撤写操作 + 删掉这一轮的对话 + 交回提问正文（见其注释） */
    rollbackTurn
  }
}
