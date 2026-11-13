// composables/agentChatLifecycle.ts
//
// Agent **一轮的生命周期**的纯派生（从 `useAgentChat.ts` 抽出）。
//
//   · `elapsedSeconds` —— 思考块已经跑了多少秒（至少 1 秒）
//   · `turnDurationMs` —— 本轮耗时（毫秒）
//   · `sumTurnDurations` —— 到此为止**整段对话**的累计耗时
//   · `buildTurnEndMessage` —— 轮末标记（`turn_end`）
//   · `createRollbackOutcome` —— 回退结果的初值
//   · `toolResultStatus` / `expertDoneStatus` —— 状态映射（`'ok' / 'fail' / 'cancelled'`）
//   · `newLocalConfirmId` —— ds-free 前端确认卡的本地 id
//
// ⚠ 依赖方向单向：`useAgentChat.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠ **状态机与事件时序一个字节都没动** —— 这里只把「怎么算」挪到了可独立测的地方；
//    `messages.value.push(...)` 的位置与先后完全不变。
import type { AgentEvent } from '@/api/ai/agent'
import type { AgentChatMessage, TurnRollbackOutcome } from './agentChatTypes'

/**
 * 已经跑了多少秒（至少 1 秒）
 *
 * ⚠️ 秒级取整会把「0.4 秒」显示成 0，看着像坏了 —— 所以下限是 1。
 */
export function elapsedSeconds(sinceMs: number, now: number): number {
  return Math.max(1, Math.round((now - sinceMs) / 1000))
}

/**
 * 本轮耗时（毫秒）
 *
 * ⚠️ 没有开始时间（0）时算 0 —— 那一轮压根没跑起来。
 */
export function turnDurationMs(startedAt: number, now: number): number {
  return startedAt ? Math.max(0, now - startedAt) : 0
}

/**
 * 到此为止**整段对话**的累计耗时（毫秒）
 *
 * ⚠️ 累计值从已有的 `turn_end` 求和，而不是另存一个全局变量：
 *    刷新 / 切换会话后消息是从快照还原的，求和能自然复原；
 *    而全局变量一刷新就归零，累计算出来会比实际小。
 *
 * ⚠️ 求和必须**用单轮值相加**（`durationMs`），不能加 `totalDurationMs`：
 *    后者本身就是累计值，把它再加一遍等于平方级膨胀
 *    （两轮各 10s，第二轮会算成 10+20=30s 而不是 20s）。
 */
export function sumTurnDurations(messages: AgentChatMessage[]): number {
  return messages.reduce(
    (sum, m) => sum + (m.type === 'turn_end' ? (m.durationMs || 0) : 0),
    0
  )
}

/**
 * 轮末标记（`turn_end`）
 *
 * ⚠️ `content` 恒为空串 —— 它唯一的载荷是 `turnId` 与两个耗时；
 *    回退组件就挂在这一轮的末尾，所以消费者必须能**可靠地**知道「一轮到哪结束了」。
 */
export function buildTurnEndMessage(
  turnId: string,
  durationMs: number,
  totalDurationMs: number
): AgentChatMessage {
  return {
    role: 'assistant',
    type: 'turn_end',
    turnId,
    content: '',
    durationMs,
    totalDurationMs
  }
}

/**
 * 回退结果的**初值**
 *
 * ⚠️ 字段名是**界面契约**（`AgentTurnRollback` 逐条渲染「哪些没退成、为什么」）——
 *    改名字等于让组件渲染不出东西。
 */
export function createRollbackOutcome(): TurnRollbackOutcome {
  return {
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
}

/**
 * 工具结果的状态映射
 *
 * ⚠️ 「用户取消」单独一档（`cancelled`）—— 取消不是失败，
 *    渲染成红色失败卡片是 bug（用户 2026-10-16 报的）。
 */
export function toolResultStatus(event: AgentEvent): 'ok' | 'fail' | 'cancelled' {
  return event.success ? 'ok' : (event.cancelled ? 'cancelled' : 'fail')
}

/** 专家行的状态映射 */
export function expertDoneStatus(success: boolean): 'ok' | 'fail' {
  return success ? 'ok' : 'fail'
}

/**
 * ds-free 前端确认卡的本地 id
 *
 * ⚠️ 形状 `local_<毫秒>_<随机>` 与后端的 `t_<毫秒>_<随机>` 是同一套写法，刻意保持一致。
 */
export function newLocalConfirmId(): string {
  return `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}
