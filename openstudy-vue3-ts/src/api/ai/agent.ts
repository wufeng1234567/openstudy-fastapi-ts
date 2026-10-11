import { getToken } from '@/utils/auth'
import { mimeOfDataUrl } from '@/utils/image-compress'
import { extFromMime } from '@/utils/doc-parse'

/**
 * Agent 流式接口客户端（工具调用循环）
 *
 * 与 `ai.ts` 的 `assistantStream`（普通流式对话）不同：
 *   · 普通对话是**纯文本分片**，靠 `consumeAssistantStream` 解析；
 *   · Agent 是**换行分隔的 JSON 事件**（`{type:"tool_start",...}\n{type:"text",...}\n`），
 *     因为除了正文还要下发工具调用 / 自我纠正 / 警告等结构化信息。
 *
 * 事件契约以后端 `services/ai/agent/loop.py` 的模块 docstring 为准，改动要两边同步。
 *
 * 为什么单开一个文件而不是塞进 `ai.ts`：`ai.ts` 已经 1000+ 行且吃透了「纯文本流」
 * 的假设，把一套不同的解析规则混进去，后续谁改错一处都很难查。
 */

/** 事件类型 */
export type AgentEventType =
  | 'meta'
  | 'text'
  | 'thinking'
  | 'waiting'
  /**
   * **处理进度**（用户 2026-10-11）：文档解析等**耗时环节**的阶段进展，用于把"干等转圈"
   * 变成"有信息量的步骤清单"。与 `thinking`（推理正文，已不再展示）**无关**——这是
   * **进度/阶段提示**，非思维链。
   * 字段：`id`（步骤唯一 id，同 id 重复发=更新该步）、`message`（面向用户的中文文案）、
   * `state`（`running`|`done`|`failed`，缺省 `running`）、`icon`（可选 emoji）。
   */
  | 'progress'
  | 'tool_confirm'
  | 'tool_confirm_resolved'
  | 'tool_start'
  | 'tool_result'
  /**
   * **指挥家委派子代理**（多智能体协同）：指挥家把任务派给某子代理 / 子代理收工。
   * 子代理**不直接面向用户** —— 这两条事件只让执行时间线显示「调度到 <子代理>」「<子代理>完成」；
   * 子代理的实际产出由指挥家整合后以普通 `text` 事件下发。
   */
  | 'delegate_start'
  | 'delegate_done'
  | 'self_correct'
  | 'warning'
  | 'error'
  /**
   * 执行统计（底部状态条）。
   *
   * ⚠️ 只在这里「声明」是不够的 —— 消费方（`useAgentChat` 的 `case 'metrics'`）读的是
   * 下面那几个 `rounds` / `steps` / … 字段，契约见它们的注释。
   * 两条链路都会发：后端 `loop.py` 的 `_metrics_event()`、前端 `agentDsFree.ts` 的
   * `emitMetrics`（口径必须逐字一致，否则换个模型就看到两套数字）。
   */
  | 'metrics'
  /**
   * 撤掉当前正在流的 assistant 正文气泡。
   *
   * 只有 ds-free 链路会发：模型吐的是一段**没能解析成功**的工具调用协议文本
   *（DSML / 围栏 JSON / 裸 JSON），它已经随着 `text` 增量流进气泡了，
   * 但那不是回答 —— 发现后要把它从界面上抹掉，否则用户盯着一屏协议文本发呆。
   */
  | 'discard_text'
  | 'done'

/**
 * `meta` 事件里的工具条目 —— **本轮真正可用**的工具（已经剔掉被禁用的），只有名字与一句话描述。
 *
 * ⚠️ 「本轮可用」是后端在**发起这一轮时**算出来的（`ds-free` 那条链路由 `agentDsFree.ts`
 * 用 `fetchAgentTools()` 的生效清单发出来），所以它天然是过滤后的结果。
 * 界面上的**开关**不要用这份数据渲染 —— 那份要的是全量清单，
 * 见 `AgentToolDefinition` / `agentDsFree.fetchAgentToolsForUi()`。
 */
export interface AgentToolMeta {
  name: string
  description: string
}

/**
 * `GET /ai/agent/tools` 下发的单个工具条目（Function Calling schema + 用户开关）
 *
 * ⚠️ **与 `AgentToolMeta` 不是一回事**，别互相顶替：一个是「全量定义 + 开关状态」，
 * 一个是「本轮生效的那几个」。
 */
export interface AgentToolDefinition {
  type?: string
  /** Function Calling schema：工具名 / 描述 / 参数 */
  function: {
    name: string
    description?: string
    parameters?: Record<string, any>
  }
  /**
   * 用户是否禁用了该工具：`1` = 禁用，`0` / 缺省 = 启用。
   *
   * ⚠️ 后端下发的是 **0|1 整数**，不是布尔 —— 判据一律写 `disabled === 1`。
   * 写成 `!tool.disabled` 之类的取反，遇到 `0`（= 启用）就会读成禁用。
   */
  disabled?: 0 | 1
  /**
   * 界面显示用的**中文名**（`题库管理` / `笔记管理` …）。
   *
   * ⚠️ 它与 `function.description` 是**两条道**，别互相顶替：
   *   · `function.*` 是**模型侧**的（全英文，进提示词与 Function Calling），
   *     界面**不许**把它当文案渲染（那正是这次要修掉的缺陷）；
   *   · `label` / `descriptionZh` 是**界面侧**的，后端挂在 `function` **外面**，
   *     所以它永远进不了提示词。
   * 声明成可选只是为了「老后端还没这两个字段」时不至于渲染崩；面板的回落规则见
   * `AgentToolPopover`（`label` 缺失回落显示英文 `name`，说明字段缺失则**留空**）。
   */
  label?: string
  /** 界面显示用的**中文一句说明**（同上，只给界面） */
  descriptionZh?: string
}

/**
 * `/ai/agent/tools` 的响应体（GET 与 PUT **同一个形状**，不套 `{code,msg,data}` 信封）
 *
 * ⚠️⚠️ `tools` 永远是**全量**清单，被禁用的条目**也在里面**（各自带 `disabled: 1`）：
 * 界面上的开关就是照这份清单渲染的，在这里过滤掉等于让用户**再也打不开**某个工具。
 * 「生效清单」（能拼进提示词的那些）由 `agentDsFree.fetchAgentTools()` 负责过滤。
 */
export interface AgentToolsPayload {
  tools: AgentToolDefinition[]
  /** 每个工具的写 / 破坏性 action（ds-free 前端循环据此决定要不要弹二次确认卡片） */
  actions?: Record<string, { write?: string[]; destructive?: string[] }>
}

/** 一条 Agent 事件 */
export interface AgentEvent {
  type: AgentEventType
  /**
   * `text` / `thinking` 事件的正文**增量**
   *
   * `thinking` 是深度思考的**推理文本**（不是状态提示），两条链路都会发：
   * - ds-free：扩展读 chat.deepseek.com 的 reasoning 分片
   * - api 付费链路：`agent/loop.py` 从 `additional_kwargs.reasoning_content` 取
   *   （langchain-openai 默认会丢掉这个字段，靠 `langchain_reasoning_patch` 补回）
   *
   * 但**是否真的有**取决于上游模型 —— 不支持思考的 OpenAI 兼容接口整场都不会发。
   * 消费方必须容忍「没有 thinking 事件」。
   */
  content?: string
  /** 工具名（bank_manage / question_manage…） */
  tool?: string
  /** 工具 action（list / create / batch_import…） */
  action?: string
  /** 人类可读的一句话 */
  message?: string
  success?: boolean
  /** 工具返回的完整结构化结果 */
  data?: any
  /** 工具入参（长字段已被后端截断） */
  params?: Record<string, any>
  /** 写操作确认前展示的信息（题库名、题量…） */
  preview?: Record<string, any>
  /** 该工具调用是否需要用户确认 */
  needsConfirmation?: boolean
  /** 需要确认但被 autoConfirm=false 拦下 */
  needsConfirm?: boolean
  /** tool_confirm / tool_confirm_resolved：本次确认的 id */
  confirmId?: string
  /** tool_confirm_resolved：用户是否点了确认 */
  approved?: boolean
  /** tool_confirm：是否为破坏性操作（删除类） */
  destructive?: boolean
  /** 自我纠正的原因 */
  reason?: string
  attempt?: number
  /** done：累计自纠次数 */
  corrections?: number
  /** done：本轮累计错误 */
  errors?: string[]
  /** done：最终回复全文 */
  answer?: string

  // ---- `progress` 事件：处理进度（用户 2026-10-11，文档解析等耗时环节的步骤清单）----
  /** 步骤唯一 id：同 id 重复发 = 更新该步（如 running → done） */
  id?: string
  /** 步骤状态：`running` 进行中 / `done` 已完成 / `failed` 失败（缺省 running） */
  state?: 'running' | 'done' | 'failed'
  /** 步骤图标（可选 emoji，如 📄 🖼 🔍） */
  icon?: string

  // ---- `metrics` 事件：执行统计（底部状态条）----
  // ⚠️ 口径由两条链路共同约定（后端 `loop.py` 的 `_metrics_event()` / 前端 `agentDsFree.ts`）：
  //    每次发的都是**当前累计值**，不是增量 —— 消费方整组覆盖，别累加。
  /** 完成的 LLM 往返次数（「轮」） */
  rounds?: number
  /** 模型请求过的工具调用条目数（「步」，含没真正执行的） */
  steps?: number
  /** LLM 调用累计耗时（毫秒） */
  llmMs?: number
  /** 工具真正执行的累计耗时（毫秒） */
  toolMs?: number
  /** 各轮首 token 的平均毫秒；**没有样本时是 `null`**（UI 显示 `—`，不是 0） */
  firstTokenMs?: number | null
  /**
   * 上面那个平均值的**样本数**（真的收到过第一个内容 token 的轮数）
   *
   * 为什么需要它：状态条显示的是**会话累计**，前端要跨多次提问汇总首 token 平均，
   * 而**平均值不能直接相加** —— 必须拿「总和」与「样本数」才能正确加权。
   * ⚠️ 也别用 `rounds` 当权重：只吐 `tool_calls`、没有正文的轮不进样本。
   */
  firstTokenSamples?: number
  /** meta：**本轮生效**的可用工具清单（已剔掉被禁用的，见 `AgentToolMeta`） */
  tools?: AgentToolMeta[]
  /**
   * meta：**本轮由哪个智能体回答**（多智能体协同）。
   * `kind` = official（官方角色）/ user（用户自定义智能体）；`id` 是角色 key 或 `user:<id>`。
   */
  agent?: { id: string; name: string; kind: 'official' | 'user' }
  model?: string
  provider?: string
  /** meta：附件解析告警 */
  warnings?: string[]
  /** meta：成功落盘的图片数 */
  imageCount?: number
  /** 未知字段兜底 */
  [key: string]: any
}

export interface AgentFilePayload {
  name: string
  type: string
  base64: string
}

/**
 * 图片附件的两种写法：
 *   · `string`        —— 裸 data URL（老的调用方式，仍然兼容）
 *   · `{name,type,base64}` —— **推荐**，带原始文件名
 *
 * ⚠️ 为什么要带名字：图片会被送给两拨消费者，而它们要的形态不同 ——
 *   · 后端 `/ai/agent/stream` 的 `AgentRequest.images` 是 `List[str]`，只认 data URL 字符串；
 *   · 浏览器扩展的 `background.js` 读 `img.base64`，**只认对象**，传字符串会被整张丢弃。
 * 以前只传字符串，结果是「后端正常、图传不到 DS」；带名字的对象能同时满足两边
 *（`normalizeAgentImages` 负责拆成两种形态）。
 */
export type AgentImageInput = string | { name?: string; type?: string; base64: string }

/** 归一化后的图片附件（两种消费者都从这里派生） */
export interface AgentImageAttachment {
  name: string
  type: string
  base64: string
}

/**
 * 把 `AgentImageInput[]` 归一化成带名字的对象列表
 *
 * 裸字符串没有名字，按序号兜底成 `上传图片-1.png`；
 * 对象缺名字时同样兜底。没有 base64 的条目直接剔除（空图送过去只会白占位）。
 */
export function normalizeAgentImages(images?: AgentImageInput[]): AgentImageAttachment[] {
  return (images || [])
    .map((item, i) => {
      if (typeof item === 'string') {
        const mime = mimeOfDataUrl(item) || 'image/png'
        return { name: `上传图片-${i + 1}.${extFromMime(mime)}`, type: mime, base64: item }
      }
      const mime = item?.type || mimeOfDataUrl(item?.base64 || '') || 'image/png'
      return {
        name: item?.name || `上传图片-${i + 1}.${extFromMime(mime)}`,
        type: mime,
        base64: item?.base64 || ''
      }
    })
    .filter((att) => !!att.base64)
}

export interface AgentStreamOptions {
  message: string
  /** 图片附件（模型能直接看到这些图）。传对象可以保留原始文件名 */
  images?: AgentImageInput[]
  /** 文档附件，服务端抽正文 + 插图 */
  files?: AgentFilePayload[]
  /** 仅历史落库用的附件元信息 */
  attachments?: any[]
  model?: string
  provider?: string
  temperature?: number
  /** 会话 id；留空 = 不写聊天历史 */
  sessionId?: string
  /**
   * **本轮**（= 用户的一次提问）的轮次 id —— 由前端生成、随请求下发。
   *
   * 后端把它回显在 `meta` 事件里，并把**本轮产生的写操作**记在这个 id 下；
   * 用户点消息末尾那个「回退」组件时，前端拿同一个 id 调 `rollbackAgentTurn()`。
   *
   * ⚠️ 粒度是「**一次提问**」，不是「一次 LLM 往返」：同一次提问里 ds-free 会发**多次**
   *    `/ai/agent/execute`（每次工具调用一次），它们必须复用**同一个** id ——
   *    每调一次就换 id 等于把同一轮的操作记成好几轮，用户点一次回退只能撤掉其中一段。
   *    生成与下发见 `useAgentChat.send()`（一次 `send()` 一个 id）。
   * ⚠️ 可选字段，只为「老调用方（不传）」保持零改动：不传时请求体里是空串，
   *    后端按「没有轮次信息」处理（这一轮的操作就回退不了）。
   */
  turnId?: string
  userId?: string | number
  /** 写操作是否自动执行（默认 true） */
  autoConfirm?: boolean
  maxLoops?: number
  /**
   * **官方智能体角色 key**（多智能体协同）：「题库/笔记/知识库/记忆/统计/通用」之一，
   * 见 `GET /ai/agent/roles`。指定后用该角色的窄工具集与专属指令；留空则后端按消息
   * **规则路由**（零 LLM 成本），不确定会退 `general`（全工具）。
   */
  role?: string
  /**
   * **用户自定义智能体 id**（多智能体协同）：非空时**优先于** `role` ——
   * 用它的人设提示词 + 工具白名单（+ 可选绑定模型）。见 `/ai/agent/configs`。
   */
  agentId?: number
  signal?: AbortSignal
}

export interface AgentStreamHandlers {
  /** 每条事件回调（高频，尽量不要在这里做重活） */
  onEvent?: (event: AgentEvent) => void
  /** 流正常结束 */
  onDone?: (event: AgentEvent | null) => void
  /** 出错（网络 / 后端 error 事件 / 主动中止不算） */
  onError?: (message: string) => void
  /**
   * ds-free（前端循环）专用：写操作需要用户二次确认时回调
   *
   * 返回 Promise<boolean> —— resolve(true) 才执行该工具。api 付费链路不需要它
   *（后端 `run_agent_stream` 自己挂起并下发 `tool_confirm` 事件）。
   */
  onConfirm?: (info: {
    tool: string
    action?: string
    params?: Record<string, any>
    destructive?: boolean
    message?: string
    preview?: Record<string, any>
  }) => Promise<boolean>
}

function normalizeUserId(userId?: string | number): number | undefined {
  if (userId === undefined || userId === null || userId === '') return undefined
  const parsed = Number(userId)
  return Number.isFinite(parsed) ? parsed : undefined
}

/**
 * 写操作二次确认的应答（api 付费链路）
 *
 * 后端 `run_agent_stream` 遇到需要确认的写操作时会**挂起**并下发 `tool_confirm`
 * 事件；前端弹卡片，用户点击后调本接口唤醒它继续执行（或按取消跳过）。
 * ds-free 链路不需要它 —— 循环跑在前端，直接本地 resolve。
 */
export async function confirmAgentTool(confirmId: string, approved: boolean): Promise<boolean> {
  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/confirm`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ confirmId, approved })
    })
    const data = await response.json().catch(() => null)
    return Boolean((data && (data.data ? data.data.resolved : data.resolved)) ?? false)
  } catch (e) {
    console.warn('[agent] 确认应答失败', e)
    return false
  }
}

/**
 * 回退结果里的**一条**：`skipped`（没回退） / `failed`（回退报错） / `partial`（只退回一部分）共用。
 *
 * 字段都是可选的，因为三份清单的侧重不同：`skipped`/`partial` 讲的是 `reason`，
 * `failed` 讲的是 `error`。**别把它们合并成一句话**——UI 要按「工具 + 动作 + 原因」逐条渲染，
 * 用户看的就是「哪一条没退成、为什么」。
 */
export interface AgentRollbackItem {
  /** 工具名（`bank_manage` / `question_manage`…） */
  tool?: string
  /** 工具 action（`create` / `delete` / `update`…） */
  action?: string
  /** 没回退 / 只退回一部分的原因（人话，直接给用户看） */
  reason?: string
  /** 回退时报的错（`failed` 专用） */
  error?: string
  /** 未知字段兜底（服务端将来多给定位信息时不用改类型） */
  [key: string]: any
}

/**
 * `POST /ai/agent/rollback` 的返回 —— 调用方靠它区分「真的回退了」与「服务端 200 却什么都没发生」。
 *
 * ⚠️ 这五个字段名（`ok` / `reverted` / `skipped` / `failed` / `partial`）是**界面契约**：
 *    UI 直接按它们渲染结果与「不可回退原因」清单，改名等于让回退组件渲染不出东西。
 */
export interface AgentRollbackResult {
  /** 服务端确认的回退结果（判据见 `rollbackAgentTurn` 的注释：`code===200` + `data` 形状对） */
  ok: boolean
  /** `ok = false` 的原因（人话，直接给用户看；`ok = true` 时是空串） */
  reason: string
  /** 真正回退掉的写操作条数（可能是 0 —— 比如这一轮只有查询） */
  reverted: number
  /** 明确**没回退**的条目（工具不支持、已被删掉…） */
  skipped: AgentRollbackItem[]
  /** 回退**报错**的条目 */
  failed: AgentRollbackItem[]
  /** 只退回了一部分的条目（如批量导入只撤掉了一部分题） */
  partial: AgentRollbackItem[]
}

/**
 * 回退**某一轮**（一次用户提问）产生的所有写操作
 *
 * 语义（用户裁决）：**只回退最近一轮**、**增 / 删 / 改都回退**。真正干活的是服务端 ——
 * 它按 `turnId` 查本轮的写操作账本再逐条反向执行；前端只负责把 id 送上去并把结果端回来。
 *
 * ## 为什么 `ok` 不是 `res.ok`（与 `saveAgentToolPref` 同一条口径）
 * 「服务端拒了」和「回退成功」都可能拿到一个 **HTTP 200**：
 *   · 本仓 `catch_all` 把任何未匹配路径变成 `{code:200, msg:'操作成功', data:null}` 的**假成功**
 *     （`app/main.py` 最后注册，见 `.codebuddy/rules/backend-ai-chain.md`）；
 *   · 业务拒绝走的是 `{code:400|403, msg:'…', data:null}` 的信封，**HTTP 码同样是 200**。
 * 所以判据只能是「`code === 200` **且** `data` 是一份回退结果」，少任何一半都报 `ok=false`。
 *
 * ## 失败原因一律取服务端原话
 * `code !== 200` 时把 `msg` 连同 code 一起带出来（「该轮次不存在或不属于你」这类信息
 * 比一句「回退失败」有用得多）。⚠️ `code === 200` 时**不许**用 `msg`
 * —— 那是 `catch_all` 那句「操作成功」，把它当理由显示给用户等于把假成功写在界面上
 * （同 `saveAgentToolPref.serverReason` 的注释）。
 *
 * ## 成功也可能是「一条都没退成」
 * `reverted: 0` + `skipped`/`failed`/`partial` 有内容仍是**成功**（`ok: true`）：
 * 「哪些没退、为什么」是服务端的判断，UI 拿 `skipped` / `failed` / `partial` 直接渲染，
 * 前端**不替服务端兜底**（双链路同口径：回退语义只在服务端一处）。
 *
 * @param params.sessionId 会话 id（账本按会话 + 轮次定位）
 * @param params.turnId 轮次 id —— 就是本轮请求里下发的那个（`meta` 事件回显 / `turn_end` 标记里带着）
 */
export async function rollbackAgentTurn(params: {
  sessionId: string
  turnId: string
}): Promise<AgentRollbackResult> {
  /** 失败时的退化值：形状恒定（空数组而不是 undefined），UI 不用写判空分支 */
  const fail = (reason: string): AgentRollbackResult => ({
    ok: false,
    reason,
    reverted: 0,
    skipped: [],
    failed: [],
    partial: []
  })
  /**
   * 把服务端信封里那句失败原因翻出来。
   *
   * ⚠️ 只有 `code` 明确**不是 200** 才用它：被 `catch_all` 兜住时服务端回的是
   * `{code:200, msg:'操作成功'}` —— 那是假成功的话，不能拿来当理由。
   */
  const serverReason = (data: any): string => {
    const code = Number(data?.code)
    if (!Number.isFinite(code) || code === 200) return ''
    const msg = typeof data?.msg === 'string' ? data.msg.trim() : ''
    return msg ? `${msg}（服务端 code=${code}）` : ''
  }

  const turnId = String(params?.turnId || '')
  // 没有轮次 id 就无从定位账本 —— 这是**调用方**漏传 id，不是服务端能答的问题，
  // 所以在本地就说清楚（服务端只会回一句「参数缺失」，排查时看不出是哪一步丢的）。
  if (!turnId) return fail('缺少轮次 id（turnId），无法回退')

  try {
    const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/rollback`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      // 请求体**只有这两个键**（契约冻结）：不带 userId —— 归属由服务端从令牌里取
      // （见 `resolve_user_scope`，请求体里的 userId 不是权威）。
      body: JSON.stringify({ sessionId: String(params?.sessionId || ''), turnId })
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) return fail(serverReason(data) || `回退失败（HTTP ${res.status}）`)

    const code = Number((data as any)?.code)
    if (code !== 200) return fail(serverReason(data) || '回退被服务端拒绝')

    const d = (data as any)?.data
    // 判据落在「data 是一份回退结果」上：`reverted` 必然是数字（可能是 0）。
    // 少了这一步，路由没匹配上时那句 `{code:200,data:null}` 会被判成「回退成功」。
    if (!d || typeof d !== 'object' || typeof d.reverted !== 'number') {
      return fail('响应里没有回退结果（路由没匹配上？被 catch_all 兜成 200 假成功？）')
    }
    const list = (v: any) => (Array.isArray(v) ? v : [])
    return {
      ok: true,
      reason: '',
      reverted: Number(d.reverted),
      skipped: list(d.skipped),
      failed: list(d.failed),
      partial: list(d.partial)
    }
  } catch (e: any) {
    return fail(String(e?.message || e))
  }
}

/**
 * 发起一次 Agent 任务
 *
 * @returns 最终回复全文（失败或被中止时返回已累积的部分）
 */
export async function postAgentStream(
  opts: AgentStreamOptions,
  handlers: AgentStreamHandlers = {}
): Promise<string> {
  const { onEvent, onDone, onError } = handlers
  let answer = ''
  let doneEvent: AgentEvent | null = null
  let failed = false

  const emit = (event: AgentEvent) => {
    if (event.type === 'text' && typeof event.content === 'string') {
      answer += event.content
    }
    if (event.type === 'done') {
      doneEvent = event
      if (typeof event.answer === 'string' && event.answer) answer = event.answer
    }
    if (event.type === 'error') {
      failed = true
      onError?.(String(event.message || 'Agent 执行失败'))
    }
    onEvent?.(event)
  }

  try {
    const response = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/stream`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message: opts.message ?? '',
        // 后端只认 data URL 字符串；对象形态在 agentDsFree 那条链路上另有用途
        images: normalizeAgentImages(opts.images).map((att) => att.base64),
        files: opts.files || [],
        attachments: opts.attachments || [],
        provider: opts.provider,
        model: opts.model,
        temperature: opts.temperature,
        sessionId: opts.sessionId || '',
        // 本轮 id：后端据此把这一轮的**写操作账本**串起来（`rollbackAgentTurn` 靠它回退）。
        // 缺省空串 = 老调用方的行为一个字不变（那一轮的操作就没有账本、回退不了）。
        turnId: opts.turnId || '',
        userId: normalizeUserId(opts.userId),
        autoConfirm: opts.autoConfirm !== false,
        maxLoops: opts.maxLoops,
        // 多智能体协同：官方角色 key（空 = 后端规则路由）+ 用户自定义智能体 id（优先）。
        // `agentId` 用 `|| undefined` 去掉 0/空，避免被后端当成「指定了 0 号」。
        role: opts.role || '',
        agentId: opts.agentId || undefined
      }),
      signal: opts.signal
    })

    // 后端在「请求本身不合法 / 模型不可用」时可能直接返回 JSON 错误信封
    const contentType = response.headers.get('Content-Type') || ''
    if (contentType.includes('application/json')) {
      const payload = await response.json().catch(() => null)
      const msg = payload?.msg || payload?.message || payload?.detail || 'Agent 请求被拒绝'
      onError?.(String(msg))
      return answer
    }

    if (!response.ok) {
      onError?.(`Agent 请求失败（HTTP ${response.status}）`)
      return answer
    }
    if (!response.body) {
      onError?.('当前浏览器不支持流式读取响应体')
      return answer
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let finished = false

    /** 处理一行（一行 = 一条事件） */
    const handleLine = (raw: string) => {
      const line = raw.trim()
      if (!line || finished) return
      if (line === '[DONE]') {
        finished = true
        return
      }
      if (line.startsWith('{')) {
        try {
          emit(JSON.parse(line) as AgentEvent)
          return
        } catch {
          // 落到下面按纯文本处理（保底，不让一条坏行打断整轮）
        }
      }
      if (line.startsWith('Error: ')) {
        failed = true
        onError?.(line.slice('Error: '.length))
        return
      }
      // 兼容「后端某天改成纯文本分片」的情况
      emit({ type: 'text', content: line })
    }

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // JSON 事件里的换行都被 json.dumps 转义成 \n，所以按 \n 切分是安全的
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) handleLine(line)
    }
    if (buffer.trim()) handleLine(buffer)

    if (!failed) onDone?.(doneEvent)
    return answer
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      // 用户主动停止：不算错误，交回已累积的内容
      return answer
    }
    onError?.(error?.message || '网络异常，Agent 未启动')
    return answer
  }
}


/* ============================================================================
 * 多智能体协同（阶段 1 官方角色 + 阶段 2 用户自定义智能体）
 * ==========================================================================*/

/** 官方智能体角色（`GET /ai/agent/roles`） */
export interface AgentRoleMeta {
  key: string
  name: string
  description: string
  /** 角色白名单工具名；空数组 = 不限制（= general） */
  tools: string[]
}

/** 拉取官方角色清单（无需登录态）。失败返回空数组（界面对空清单要能降级）。 */
export async function listAgentRoles(): Promise<AgentRoleMeta[]> {
  try {
    const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/roles`, {
      headers: { Authorization: 'Bearer ' + getToken() }
    })
    if (!res.ok) return []
    const data = await res.json()
    return Array.isArray(data?.roles) ? data.roles : []
  } catch {
    return []
  }
}

/** 用户自定义智能体（`/ai/agent/configs`） */
export interface AgentConfig {
  agentId: number
  name: string
  description: string
  greeting: string
  personaPrompt: string
  tools: string[]
  model: string
  isEnabled: number
  createTime?: string | null
  updateTime?: string | null
}

/** 新建 / 更新用请求体（字段名与后端 `AgentConfigBody` 一一对应，`extra=forbid` 会拒未知字段） */
export interface AgentConfigInput {
  name?: string
  description?: string
  greeting?: string
  personaPrompt?: string
  tools?: string[]
  model?: string
  isEnabled?: number
}

function _authHeaders(): Record<string, string> {
  return { Authorization: 'Bearer ' + getToken(), 'Content-Type': 'application/json' }
}

/** 专家（官方角色）—— 用户可开关的「专家」清单项 */
export interface AgentExpert {
  key: string
  name: string
  description: string
  disabled: number
}

/**
 * 列出**专家清单**（含当前用户的开关状态）
 *
 * 与 `listAgentRoles()` 的区别：本接口**含用户数据**（每个人的开关不同），需登录态。
 * 供设置面板渲染「专家」开关（用户 2026-10-10：把「可用工具」改成「专家」）。
 * 失败返回空数组（界面需能降级）。
 */
export async function listAgentExperts(): Promise<AgentExpert[]> {
  try {
    const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/experts`, {
      headers: _authHeaders()
    })
    if (!res.ok) return []
    const data = await res.json()
    return Array.isArray(data?.experts) ? data.experts : []
  } catch {
    return []
  }
}

/**
 * 启用 / 关闭一个专家（`disabled`：1=关闭，0=启用）。返回最新专家清单（受控：显示值来自服务端）。
 * 失败抛错，供界面提示。
 */
export async function setAgentExpertPref(
  expert: string,
  disabled: 0 | 1
): Promise<AgentExpert[]> {
  const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/experts`, {
    method: 'PUT',
    headers: _authHeaders(),
    body: JSON.stringify({ expert, disabled })
  })
  const data = await res.json().catch(() => null)
  if (!res.ok || data?.code === 400) {
    throw new Error(data?.msg || data?.message || '保存失败')
  }
  return Array.isArray(data?.data?.experts) ? data.data.experts : []
}

/** 列出我的智能体（`includeDisabled=true` 含已暂停的） */
export async function listAgentConfigs(includeDisabled = false): Promise<AgentConfig[]> {
  try {
    const url = `${import.meta.env.VITE_APP_BASE_API}/ai/agent/configs?includeDisabled=${
      includeDisabled ? 'true' : 'false'
    }`
    const res = await fetch(url, { headers: _authHeaders() })
    if (!res.ok) return []
    const data = await res.json()
    return Array.isArray(data?.agents) ? data.agents : []
  } catch {
    return []
  }
}

/** 新建智能体；失败抛出后端 `msg`（供界面提示） */
export async function createAgentConfig(body: AgentConfigInput): Promise<AgentConfig> {
  const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/configs`, {
    method: 'POST',
    headers: _authHeaders(),
    body: JSON.stringify(body)
  })
  const data = await res.json().catch(() => null)
  if (!res.ok || data?.code === 400) {
    throw new Error(data?.msg || data?.message || '创建失败')
  }
  return data?.data ?? data
}

/** 更新智能体 */
export async function updateAgentConfig(agentId: number, body: AgentConfigInput): Promise<AgentConfig> {
  const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/configs/${agentId}`, {
    method: 'PUT',
    headers: _authHeaders(),
    body: JSON.stringify(body)
  })
  const data = await res.json().catch(() => null)
  if (!res.ok || data?.code === 400 || data?.code === 404) {
    throw new Error(data?.msg || data?.message || '更新失败')
  }
  return data?.data ?? data
}

/** 删除智能体（逻辑删除） */
export async function deleteAgentConfig(agentId: number): Promise<void> {
  const res = await fetch(`${import.meta.env.VITE_APP_BASE_API}/ai/agent/configs/${agentId}`, {
    method: 'DELETE',
    headers: _authHeaders()
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new Error(data?.msg || data?.message || '删除失败')
  }
}
