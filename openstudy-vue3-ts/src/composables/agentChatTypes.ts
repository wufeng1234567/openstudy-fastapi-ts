// composables/agentChatTypes.ts
//
// Agent 对话**数据结构**的单一出处（从 `useAgentChat.ts` 抽出的纯类型模块）。
//
// 这里只放**类型声明**（编译后无运行时代码），不含任何逻辑：
//   · 消息流 / 专家工作组 / 进度步骤 / 运行选项 —— 界面与状态机共用的形状；
//   · 执行统计 —— 与后端 `loop.py` 的 `_metrics_event()` 逐字对齐；
//   · 回退结果与回退状态 —— **界面契约**（字段名一个字都不能改）。
//
// ⚠️ 为什么要独立成文件：`useAgentChat.ts` 是流式状态机，体量已经很大；
//    把「形状」与「行为」分开，界面组件也能只 import 类型、不牵进状态机。
//
// 本模块**不依赖**任何其它模块（除 `@/api/ai/agent` 的两个入参类型），
// 因此不会与 `useAgentChat.ts` 形成循环依赖。
import type { AgentRollbackItem, AgentImageInput } from '@/api/ai/agent'

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
  /**
   * `turn_end` 专用：**本轮耗时（毫秒）**（2026-10-27 新增）
   *
   * 用户要求「做一个记录，记录了本次对话共耗时多少时间，每轮聊天的底部都可以看到」。
   *
   * 用 `send()` 的 finally 里 `Date.now() - runStartedAt` 算出来落在这条标记上。
   * 它必须随 `turn_end` 一起**落库**（`slimTimeline` 白名单），
   * 否则刷新后历史轮次的耗时就丢了 —— 那正是用户说的"记录"要解决的问题。
   */
  durationMs?: number
  /**
   * `turn_end` 专用：**到这里为止的会话累计耗时（毫秒）**
   *
   * 单轮耗时只说明"这次等了多久"；用户更想要的是"这段对话一共花了多久"。
   * 累计值在轮末由前面的累计 + 本轮耗时得出，同样落库。
   */
  totalDurationMs?: number
  /** agent_note 的子类型（决定图标与配色） */
  noteKind?: 'correct' | 'warning' | 'error'
  /** tool_result 专用 */
  tool?: string
  action?: string
  status?: 'running' | 'ok' | 'fail'
  detail?: string
  /** 助手回答引用到的知识库片段（文档 chip + hover 切片） */
  references?: any[]
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
