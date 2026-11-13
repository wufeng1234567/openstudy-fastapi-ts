// composables/agentChatStatus.ts
//
// Agent 消息的**状态判定与收口**（从 `useAgentChat.ts` 抽出）。
//
//   · `findConfirmCard` —— 按 confirmId 找到那张「待确认」卡片
//   · `decisionStatus` —— 用户决定（确认 / 取消）落成卡片状态
//   · `closeRunningConfirms` —— 中止时把还「待确认」的卡片收口
//
// ⚠ 依赖方向单向：`useAgentChat.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠ **SSE 事件时序与消息顺序一个字节都没动** —— 这里只把「状态怎么算」挪到了
//    可独立读、可独立测的地方；`messages.value` 的读写位置与先后完全不变。
import type { AgentChatMessage } from './agentChatTypes'

/**
 * 按 `confirmId` 找到那张「待确认」卡片
 *
 * ⚠️ 「用户点确认」与「后端回传已确认」两个入口原本**各写一遍**同样的查找 ——
 *    现在收敛到一处，两边不可能再找错卡片。
 */
export function findConfirmCard(
  messages: AgentChatMessage[],
  confirmId: string
): AgentChatMessage | undefined {
  return messages.find(
    (m) => m.type === 'tool_confirm' && m.confirmId === confirmId
  )
}

/**
 * 用户决定落成卡片状态：确认 → `ok`，取消 → `fail`
 *
 * ⚠️ 取消用的是 `fail`（不是别的状态）—— 前端按 `status` 决定卡片配色，
 *    换字面量会让「取消」渲染成未知状态。
 */
export function decisionStatus(approved: boolean): 'ok' | 'fail' {
  return approved ? 'ok' : 'fail'
}

/**
 * 把还「待确认」（`running`）的确认卡收口成 `fail`
 *
 * ⚠️ 中止时必须做：否则本轮 finally 的快照会把 `running` 的确认卡存下去，
 *    刷新后又冒出一张能点、却没人应答的卡片（用户报的 bug）。
 */
export function closeRunningConfirms(messages: AgentChatMessage[]): void {
  for (const m of messages) {
    if (m.type === 'tool_confirm' && m.status === 'running') m.status = 'fail'
  }
}

/**
 * 自纠次数：取「当前值」与「本次尝试」的大者
 *
 * ⚠️ 用**大者**而不是覆盖：模型可能一次报多个不同的 attempt 号，
 *    覆盖会让计数变小（前端显示的「已自纠 N 次」忽大忽小）。
 */
export function nextCorrectionCount(current: number, attempt: unknown): number {
  return Math.max(current, Number(attempt) || 0)
}
