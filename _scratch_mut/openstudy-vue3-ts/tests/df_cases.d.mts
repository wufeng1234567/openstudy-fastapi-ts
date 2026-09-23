/**
 * `df_cases.mjs`（用例表）的类型声明
 *
 * 为什么放在这里、而不是 `src/types/`：
 *   · 用例表本身是 `.mjs`（有 Node 驱动在用，不能改成 `.ts`），而 `tsconfig.include`
 *     只含 `src/**` —— 不声明的话，`src/` 里 import 它就是 TS7016「找不到声明文件」。
 *   · TypeScript 的约定是：import 以 `.mjs` 结尾时去找同名的 `.d.mts`。
 *     所以声明文件跟用例表**放一起**最不容易走丢，tsconfig 里补一行 include 即可。
 *
 * 这份声明只描述**浏览器自检面板会用到的那部分**：套件数组 + 素材常量。
 * Node 驱动是 `.mjs`，不受这里约束。
 */

/** `expect` 返回的断言三元组：`[说明, 是否通过, 实际值?]` */
export type DfAssertTuple = [label: string, pass: boolean, actual?: string]

/** 一条用例。字段按套件不同而不同，这里全列成可选，避免每加一条用例就要改类型 */
export interface DfCase {
  /** 形如 `DF-LOOP-01`，命名规范见 df_cases.mjs 头部 */
  id: string
  suite: 'LOOP' | 'PROXY' | 'RAG' | 'TOOLS' | 'UI' | 'ROLLBACK' | 'LIVE'
  title: string
  /**
   * 断言函数。返回 `[label, ok]` 列表，判据是 `every(a => !!a[1])`。
   * ctx 的形状由驱动决定，各套件不同（见 df_cases.mjs 头部说明）。
   */
  expect: (ctx: any) => DfAssertTuple[]
  /** 期望这轮抛异常（少数用例用） */
  expectThrows?: boolean

  // ---- LOOP 专用 ----
  /** 每一轮「模型回复全文」；轮次越界则重复最后一条 */
  model?: string[]
  /** 第 N 次工具调用的返回 */
  tools?: any[]
  /** >0 时按这个粒度把模型回复分帧（测流式边界） */
  chunkSize?: number
  /** 传给 runDsFreeAgentStream 的额外选项 */
  opts?: Record<string, any>
  /** 二次确认卡片的回答；默认 true，`false` = 用户在卡片上点了取消 */
  answerConfirm?: boolean
  /** 让第一次 chat 调用抛异常（测异常重试） */
  throwOnce?: boolean
  /** 脚本化的「深度思考当前状态」 */
  deepThink?: boolean
  /**
   * 每轮的**推理文本**（深度思考内容），按**累积**形式喂给被测代码。
   *
   * ⚠️ 与 `deepThink` 不是一回事：那个是「深度思考开关」，这个是模型吐的思考正文。
   * 驱动要负责按累积回调（真链路 `chatWithDSAccumulated` 的语义就是累积），
   * 由 `agentDsFree` 自己 diff 成增量 —— 那一步正是用例要覆盖的。
   */
  reasoning?: string[]

  /**
   * 运行时背景（长期记忆摘要 + 知识库清单）—— 桩掉 `GET /ai/agent/context` 的返回。
   *
   * ⚠️ **两个驱动都必须支持它**：Node 驱动桩 `fetch`，浏览器驱动也桩 `fetch`。
   * 少一边的话，DF-LOOP-24/25 在浏览器面板里会去请求**真实后端**
   * （拿不到就退化成空串，用例要么失败、要么随真实数据飘）——
   * 而这两条是 LOOP 套件，面板是**会**跑到的。
   */
  runtimeContext?: string

  /**
   * 本会话的短期历史 —— 桩掉 `GET /ai/agent/context?sessionId=…` 的 `history` 字段。
   *
   * 契约上这份文本已经带 `<conversation_history>` 标签（后端
   * `conversation_service.build_context_prompt(lang="en")` 的产物）——
   * **前端原样搬运，不 trim、不补标签、不重排**（动一个字符两条链路就分叉）。
   *
   * ⚠️ 同 `runtimeContext`：**两个驱动都必须支持它**，少一边用例结论就会分叉。
   */
  history?: string

  /**
   * 让同一条用例**连续跑多次** `runDsFreeAgentStream`，第 i 次用 `sessionIds[i]` 当
   * `sessionId`（缺省只跑一次、不传 sessionId）。
   *
   * 为什么需要：历史注入的判据是「**换会话**才重新注入」，那是**跨调用**的会话级行为 ——
   * 单次调用里测不到（一轮内的后续轮次走的是工具结果回灌，本来就不拼历史）。
   * 用例「同一 session 第二轮不再注入」= `['s1','s1']`；「换会话重新注入」= `['s1','s2']`。
   */
  sessionIds?: string[]

  /**
   * `/ai/agent/preview`（确认卡片的 `preview` + **确认票据**）的桩形态：
   *   · 不传 → 接口返回 `{ preview: {} }`；**发不发票据按服务端判据**决定 ——
   *     即 `needs_user_confirmation(tool, params, 请求体里的 autoConfirm)`：
   *     破坏性动作恒发；写操作只在 `autoConfirm === false` 时发。
   *     （与真 `preview_agent_tool` 同源。少了这一层，「前端漏传 autoConfirm ⇒ 服务端按
   *     true 判 ⇒ 不发票据」这种死锁测不出来，用例会假绿 —— 见 DF-LOOP-56。）
   *   · `{ result: {...} }` → 返回 `{ preview: result, confirmTicket: … }`
   *   · `{ throws: true }` → 网络层抛错
   *   · `{ status: 500 }` → HTTP 非 2xx
   *   · `{ raw: {...} }` → **整个响应体原样返回**（200），用来造「非本接口的形状」：
   *     `fail()` 信封（`{success:false,…}`）与 catch_all 的假成功
   *     `{code,msg,data:null}` —— 见 DF-LOOP-39/40
   *   · `{ ticket: 'tk-x' }` → 钉死下发的票值
   *   · `{ ticket: '' }` → **不下发票据**（造「服务端没给票据」→ 需要确认的执行必被拒，
   *     DF-LOOP-53 / 57）
   *
   * 后两种都必须让前端**降级成空值且照常弹卡片** —— 关系见 DF-LOOP-37/38。
   * ⚠️ 同 `runtimeContext` / `history`：**两个驱动都必须支持它**，少一边用例结论就会分叉。
   */
  previewStub?: {
    result?: any
    throws?: boolean
    status?: number
    raw?: any
    ticket?: string
  }

  /**
   * 下发给链路的**轮次 id**（turnId）—— 一次用户提问一个，同一次提问里的所有请求复用它。
   *
   * 驱动把它当 `opts.turnId` 交给 `runDsFreeAgentStream`，用例断言它**原样**出现在
   * `/ai/agent/execute` 的请求体里（DF-LOOP-60）。
   *
   * ⚠️ 同 `runtimeContext` / `history`：**两个驱动都必须支持它** ——
   *    LOOP 组是面板会跑的组，少一边这条用例就会一侧红一侧绿。
   */
  turnId?: string

  // ---- TOOLS 专用（**只有 Node 驱动**跑这个套件，浏览器面板只跑 LOOP / LIVE 组） ----
  //
  // 与 `runtimeContext` / `previewStub` 不同：这几个字段**不需要**浏览器驱动也实现一份
  // —— 面板根本不会跑到 TOOLS 套件（`DfSelfCheckPanel` 的 pick 列表里没有它），
  // 与 RAG / UI 套件同理，因此不存在「同一个桩字段两边不同步」的问题。
  //
  // ⚠️ **例外是 `agentToolsGetStatus`**：它现在也被 LOOP 组的 DF-LOOP-52 用
  //    （造「工具元信息拉不到」→ `needConfirm` 必须 fail-closed），
  //    所以**两个驱动都必须实现它** —— 面板会跑 LOOP 组。
  /** 桩掉 `GET /ai/agent/tools` 的响应体（不传用驱动里的缺省素材 `AGENT_TOOLS`） */
  agentTools?: any
  /**
   * 第 1 / 2 / 3… 次 GET `/ai/agent/tools` 返回的状态码（超出数组长度一律 200）。
   * 用来造「拉取失败」—— 失败**不许进缓存**（DF-TOOLS-06），
   * 以及「元信息不可用时 `needConfirm` fail-closed」（DF-LOOP-52）。
   */
  agentToolsGetStatus?: number[]
  /** 流跑完之后要执行的 `saveAgentToolPref()` 调用（DF-TOOLS-03/04/05） */
  toolPrefSave?: { tool: string; disabled: 0 | 1 }
  /**
   * 桩掉 `PUT /ai/agent/tools` 的响应：
   *   · 不传 → 「照单生效」并把改后的**全量**清单回显（正常保存）；
   *   · `{ echo: 'unchanged' }` → HTTP 200 但清单原样回显（**假成功**，服务端其实没存）；
   *   · `{ omitActions: true }` → 200 且回显新清单，但**不带 `actions` 字段**
   *     （契约是「同 GET 形状」，实现少个字段很常见）—— 前端不许因此把
   *     「写 / 破坏性」清单清掉（DF-TOOLS-07）；
   *   · `{ raw: {...} }` → **整个响应体原样返回**（HTTP 200），用来造非本接口的形状：
   *     后端失败信封 `{code:400,msg,data:null}`（DF-TOOLS-08）与 catch_all 的假成功
   *     `{code:200,msg:'操作成功',data:null}`（DF-TOOLS-09）。优先级最高。
   *   · `{ status: 400 }` → HTTP 非 2xx（被拒）；
   *   · `{ throws: true }` → 网络层抛错。
   */
  toolPrefPut?: {
    echo?: 'unchanged'
    omitActions?: boolean
    raw?: any
    status?: number
    throws?: boolean
  }

  // ---- ROLLBACK 专用（**只有 Node 驱动**跑这个套件，与 TOOLS / RAG / UI 同理） ----
  /** 交给 `postAgentStream` 的请求选项（DF-ROLLBACK-01 用它造 api 链路请求体） */
  streamOpts?: Record<string, any>
  /** 交给 `rollbackAgentTurn` 的入参 `{sessionId, turnId}` */
  rollbackParams?: { sessionId: string; turnId: string }
  /**
   * 桩掉 `POST /ai/agent/rollback` 的响应：
   *   · `{ raw: {...} }` → **整个响应体原样返回**（HTTP 200）。用来造
   *     成功形状、`fail()`/`error()` 信封（`{code:400|403,msg,data:null}`）与
   *     catch_all 的假成功 `{code:200,msg:'操作成功',data:null}` —— 判据见 DF-ROLLBACK-02/03/04；
   *   · `{ status: 500 }` → HTTP 非 2xx；
   *   · `{ throws: true }` → 网络层抛错。
   */
  rollbackResponse?: { raw?: any; status?: number; throws?: boolean }

  // ---- UI 专用：轮末标记与「回退本轮」（仅 Node 驱动，面板不跑 UI 组） ----
  /**
   * 这一轮 `send()` 用的 `sessionId`（不传 = 空串 = **不落库**）。
   *
   * DF-UI-12 用它验「快照保留 turnId」：时间线只在有 sessionId 时才存。
   */
  sessionId?: string
  /**
   * 让桩掉的 `runDsFreeAgentStream` 以异常收场，造「报错 / 用户中止的那一轮」：
   *   · `'error'` → 抛普通 Error（`send()` 会插一张错误提示卡）
   *   · `'abort'` → 抛 `name === 'AbortError'`（`send()` 当作用户主动停止，**不**报错）
   *
   * 要钉的是「轮末标记挂在 `finally` 上 ⇒ 这两种情况也必须有标记」。
   */
  streamThrows?: 'error' | 'abort'
  /**
   * 跑完 `send()` 之后再调一次 `chat.rollbackTurn(turnId)`（DF-UI-13/14）。
   *   · `turnId` 不传 = 用**最后一条 `turn_end` 标记**里的 id（也就是 UI 真会传的那个）
   *   · `result` = 桩掉 `rollbackAgentTurn` 的返回（形状 `{ok,reason,reverted,skipped,failed,partial}`）
   */
  rollback?: { turnId?: string; result?: any }

  // ---- LIVE 专用 ----
  /** 真实提问；可含 `__DF_BANK__` 占位符，由真链路驱动替换成 seed 出来的题库名（TOOLS 套件借用它当提问正文） */
  prompt?: string

  // ---- PROXY / UI 专用（浏览器面板不跑，仅保证类型完整） ----
  run?: (ctx: any) => Promise<any>
  events?: any[]
  /**
   * 连着跑**多次** `send()`，每次喂一组事件（第 i 次用 `eventsRuns[i]`）。
   *
   * 为什么需要：有些行为是**跨提问**的，单次调用里测不到 —— 最典型的是
   * 「执行统计是**会话累计**，不是只显示最后一句提问的账」（DF-UI-07）。
   * 不传时与只传 `events` 完全等价（跑一次）。
   *
   * ⚠️ 只有 Node 驱动（`check_agent_dsfree.mjs` 的 `runUiCases`）支持它 ——
   *    UI 套件在浏览器面板里不跑（面板只跑 LOOP 组），所以不存在双驱动同步问题。
   */
  eventsRuns?: any[][]
}

/** 落库数据统一前缀 —— 清理只认它 */
export const PREFIX: string

// ---- 模型回复素材（造各种「协议跑偏」场景） ----
export const CALL: (tool: string, params: Record<string, any>) => string
export const BAD_ARROW: string
export const BAD_DSML: string
export const BAD_FENCE: string
export const BAD_BARE: string
export const QUOTE_JSON: string
export const TWO_CALLS: string
/** 最终回复里**引用**了一段「工具调用长什么样」的 JSON（写在句子中间）—— DF-LOOP-45 用 */
export const QUOTE_CALL_INLINE: string
/** 最终回复里只是**提到** `tool_call` 这个词，没有任何标记 —— DF-LOOP-46 用 */
export const MENTION_PROTOCOL: string
/** 最终回复里只是**提到** `DSML` 这个词，没有 `<|DSML|>` 标记 —— DF-LOOP-47 用 */
export const MENTION_DSML: string

/**
 * 用例下发的**轮次 id**（turnId）样本，形状 `t_<毫秒>_<随机 6 位>`。
 * DF-LOOP-60 与 DF-ROLLBACK-01/02… 用它断言「原样下发、不被改写」。
 */
export const TURN_ID_SAMPLE: string

/**
 * 「回灌内容明显超过旧 6000 字符上限」的 `knowledge_search` 结果（DF-LOOP-35 用）。
 * 6 条 × 约 1190 字，每条正文尾部带 `__HIT_<i>_END__` 哨兵，最后一条 chunkId = 900006。
 */
export const BIG_SEARCH_RESULT: any

/** 破坏性写操作的预演返回（`/ai/agent/preview` 的 `preview`）—— DF-LOOP-36 用 */
export const PREVIEW_DELETE_BANKS: any

// ---- 常用工具返回 ----
export const TOOL_BANKS: any
export const TOOL_SEARCH_ONE: any
export const TOOL_LIST_34: any
export const TOOL_FAIL: any

// ---- 工具清单素材（TOOLS 套件用） ----
/** `GET /ai/agent/tools` 的响应体素材：两个工具，默认都启用（`disabled` 是 0|1 整数） */
export const AGENT_TOOLS: {
  tools: any[]
  actions: Record<string, { write: string[]; destructive: string[] }>
}
/** 在 `AGENT_TOOLS` 上改开关：`{ memory_search: 1 }` = 把 memory_search 关掉 */
export const agentToolsWith: (map: Record<string, 0 | 1>) => {
  tools: any[]
  actions: Record<string, { write: string[]; destructive: string[] }>
}

// ---- 套件 ----
export const LOOP_CASES: DfCase[]
export const PROXY_CASES: DfCase[]
export const RAG_CASES: DfCase[]
export const TOOLS_CASES: DfCase[]
export const UI_CASES: DfCase[]
/** 轮次 id 的下发 + 回退接口的 `ok` 语义（只有 Node 驱动跑） */
export const ROLLBACK_CASES: DfCase[]
export const LIVE_CASES: DfCase[]
/** 依赖 seed 数据的真链路用例（含 `__DF_BANK__` 占位符）——只有浏览器面板会跑 */
export const SELF_LIVE_CASES: DfCase[]
