// composables/agentChatTimeline.ts
//
// Agent 时间线的**落库 / 复原**辅助（从 `useAgentChat.ts` 抽出的纯逻辑模块）。
//
// 这里放的都是**没有副作用的纯函数**：消息流瘦身、推理正文截断、快照复原时的
// 「未收口卡片」修正、轮次 id 生成。它们与流式状态机无关，可以独立理解与复用。
//
// 依赖方向：本模块 → `./agentChatTypes`（只取类型）；**不反向依赖 `useAgentChat.ts`**，
// 因此不会形成循环依赖。
import type { AgentChatMessage } from './agentChatTypes'

/** 单条消息里 `data` 的落库上限（超过就只留摘要），避免快照被题目数组撑爆 */
export const TIMELINE_DATA_LIMIT = 20000

/**
 * 思考块的落库上限
 *
 * 深度思考的推理动辄几千字，**不能像正文那样无上限地存** —— 快照被撑大会拖慢会话加载，
 * 而推理只是过程信息、不是用户要留的记录。超长就截断并注明。
 */
export const TIMELINE_REASONING_LIMIT = 4000

/**
 * 截断推理正文，但**不切断公式**
 *
 * ── 为什么不能直接 slice（2026-10-27）────────────────────────
 * 推理正文里常有 LaTeX（`$\lim_{x\to 0}\frac{\sin 3x}{x}$`）。
 * 直接 `slice(0, 4000)` 有可能正好切在 `$\frac{\sin 3x}` 中间，
 * 于是页面上出现半截公式 —— 要么原样露出反斜杠，要么 KaTeX 报错。
 *
 * 处理：若切断点落在某个成对定界符内部，就把切断点**后退到该公式的开头**。
 * 宁可少显示一个公式，也不要在末尾留一坨坏掉的 LaTeX。
 */
export function truncateReasoning(text: string, limit: number): string {
  const SUFFIX = '…（推理较长，已截断）'
  let cut = limit

  // 找出 [0, limit] 区间内最后一个未闭合的 `$`（或 `$$`）
  // 简单做法：从 limit 往前找最近的 `$`，看它前面有几个 `$`
  const head = text.slice(0, cut)
  const ddCount = head.split('$$').length - 1
  const singleCount = head.replace(/\$\$/g, '').split('$').length - 1

  // `$$` 必须是偶数对；奇数说明切在了块级公式内部
  if (ddCount % 2 === 1) {
    const i = head.lastIndexOf('$$')
    if (i > 0) cut = i
  } else if (singleCount % 2 === 1) {
    // 行内公式：同理，奇数说明切在公式内部
    const stripped = head.replace(/\$\$/g, '\u0000\u0000')
    const i = stripped.lastIndexOf('$')
    if (i > 0) cut = i
  }

  return text.slice(0, cut) + SUFFIX
}

/**
 * 落库前给消息流瘦身
 *
 * 只保留渲染需要的字段；`data`（工具原始返回，可能含整批题目）超过上限时
 * 退化成 `{message, _truncated}`，既留住「结果摘要」又不让快照无限膨胀。
 */
export function slimTimeline(msgs: AgentChatMessage[]): any[] {
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
        out.content = truncateReasoning(out.content, TIMELINE_REASONING_LIMIT)
      }
      if (m.secs != null) out.secs = m.secs
      return out
    }
    if (m.noteKind) out.noteKind = m.noteKind
    if (m.references?.length) out.references = m.references
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
    /*
     * 轮耗时（2026-10-27 新增，必须落库）
     *
     * 用户要的是「记录」—— 刷新页面后历史轮次的耗时还得在。
     * 白名单语义是"不在名单里的字段刷新后就没了"，所以这两行不能省。
     */
    if (m.durationMs != null) out.durationMs = m.durationMs
    if (m.totalDurationMs != null) out.totalDurationMs = m.totalDurationMs
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
 * 生成一个**轮次 id**
 *
 * 形状 `t_<毫秒>_<随机 6 位>`：
 *   · 毫秒时间戳 —— 日志 / 库里一眼看出先后，几个轮次之间能按时间排；
 *   · 随机后缀 —— 同一毫秒内连点两次发送也不会撞车（撞了就会把两轮的账本混在一起）。
 * 与 `requestConfirm` 里的 `local_<ms>_<rand>` 是同一套写法，刻意保持一致。
 */
export const newTurnId = () =>
  `t_${Date.now()}_${Math.random().toString(36).slice(2, 8).padEnd(6, '0')}`
