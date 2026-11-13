// composables/agentChatTurns.ts
//
// 「**某一轮**」在消息流里的定位与摘除（从 `useAgentChat.ts` 抽出）。
//
//   · `locateTurnIn` —— 找出这一轮的消息在消息流里的范围（**只算、不改**）
//   · `sliceOutTurn` —— 算出「摘掉这一轮之后」的那份消息列表（**只算、不改**）
//
// ⚠️ 依赖方向单向：`useAgentChat.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠️ 这两个函数**都不许有副作用**：回退的顺序是「先算出 → 写进快照 → 写成了才动本地」，
//    顺序反过来的话本地会先被删掉（详见 `locateTurnIn` 的注释）。
import type { AgentChatMessage } from './agentChatTypes'

/** 某一轮在消息流里的范围 */
export interface TurnRange {
  /** 该轮**用户消息**的下标 */
  startIdx: number
  /** 该轮 `turn_end` 标记的下标 */
  endIdx: number
  /** 该轮用户提问的正文（回退后交给界面回填输入框） */
  userText: string
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
export function locateTurnIn(
  messages: AgentChatMessage[],
  tid: string
): TurnRange | null {
  const endIdx = messages.findIndex((m) => m.type === 'turn_end' && m.turnId === tid)
  if (endIdx < 0) return null
  for (let i = endIdx - 1; i >= 0; i--) {
    if (messages[i].role === 'user') {
      return { startIdx: i, endIdx, userText: messages[i].content || '' }
    }
  }
  return null
}

/**
 * 算出「摘掉这一轮之后」的那份消息列表（**不改 messages**）
 *
 * ⚠️ 定位不到（`plan` 为 `null`）时**原样返回**（一份拷贝）——
 *    此时一条都不能删（上层据此报「提问正文拿不到」），而不是猜一把删掉别人的轮次。
 */
export function sliceOutTurn(
  messages: AgentChatMessage[],
  plan: TurnRange | null
): AgentChatMessage[] {
  if (!plan) return [...messages]
  return [
    ...messages.slice(0, plan.startIdx),
    ...messages.slice(plan.endIdx + 1)
  ]
}
