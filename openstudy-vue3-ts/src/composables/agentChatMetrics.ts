// composables/agentChatMetrics.ts
//
// Agent 执行统计（`metrics` 事件）的**累加口径**（从 `useAgentChat.ts` 抽出的纯逻辑模块）。
//
// ⚠️⚠️ **口径由两条链路共同约定，改一处必须改另一处**：
//   · 后端：`app/services/ai/agent/loop.py` 的 `_metrics_event()`
//   · 前端：`src/api/ai/agentDsFree.ts`（ds-free 循环跑在前端）
//   `rounds` = 完成的 LLM 往返次数；`steps` = 模型请求过的工具调用条目数（含没真正执行的）；
//   `llmMs` / `toolMs` = 累计耗时（毫秒）。
//
// 这里放的是**与 Vue 无关的纯计算**：会话累加器 / 本轮快照的形状、投影、还原、增量计算。
// Vue 侧的 `ref` 与响应式仍由 `useAgentChat.ts` 持有。
//
// 依赖方向：本模块 → `./agentChatTypes`（只取 `AgentMetrics` 类型）；
// **不反向依赖 `useAgentChat.ts`**，因此不会形成循环依赖。
import type { AgentMetrics } from './agentChatTypes'

/**
 * 会话累计的**原始累加器**（比展示投影多存了 `ftSum` / `ftSamples`）
 *
 * ⚠️ `firstTokenMs` 是**平均值**，不能像其余四项那样直接相加 —— 所以累加器里存的是
 * **`ftSum`（总和）与 `ftSamples`（样本数）**，投影时才做除法。
 * 用 `rounds` 当权重是错的：只吐 `tool_calls`、没有正文的轮**不进样本**。
 *
 * ⚠️ 这里刻意用 **`type` 而不是 `interface`**：TS 只给「对象类型别名」隐式索引签名，
 *    `interface` 没有 —— 而 `saveAgentTimeline()` 的 `metrics` 形参是 `Record<string, number>`，
 *    用 `interface` 会让这个返回值**无法赋值**过去（隐式索引签名缺失的编译错误）。
 */
export type AgentMetricsAccumulator = {
  rounds: number
  steps: number
  llmMs: number
  toolMs: number
  ftSum: number
  ftSamples: number
}

/**
 * 后端 `metrics` 事件里**本轮（单次提问）**的累计值
 *
 * 事件里带的是**本轮累计值**，所以增量 = 本次值 − 上次值。每次 `send()` 必须归零，
 * 否则新一轮算出负增量、把会话总量往回拉。
 */
export interface AgentMetricsRoundValues {
  rounds: number
  steps: number
  llmMs: number
  toolMs: number
  ftSamples: number
}

/** 一个全零的累加器 / 本轮快照 */
export function createMetricsAccumulator(): AgentMetricsAccumulator {
  return { rounds: 0, steps: 0, llmMs: 0, toolMs: 0, ftSum: 0, ftSamples: 0 }
}

/**
 * 把会话累加器投影成**展示形状**（`AgentMetrics`）
 *
 * ⚠️ `firstTokenMs` 是**平均值**：没有样本时是 `null`（UI 显示 `—`），
 *    给 0 会被读成「瞬间返回」。
 */
export function projectMetrics(agg: AgentMetricsAccumulator): AgentMetrics {
  return {
    rounds: agg.rounds,
    steps: agg.steps,
    llmMs: agg.llmMs,
    toolMs: agg.toolMs,
    firstTokenMs: agg.ftSamples ? Math.round(agg.ftSum / agg.ftSamples) : null
  }
}

/**
 * 会话累计统计的**落库快照**（随 timeline 快照一起存）
 *
 * ⚠️ 存的是**原始累加器**（含 `ftSum`/`ftSamples`），不是展示投影 `metrics`：
 *    `firstTokenMs` 是平均值，跨会话恢复必须靠「总和 + 样本数」才能正确接着累加，
 *    直接存平均值会在下一次还原时算错（平均值不能相加）。
 */
export function metricsSnapshotOf(agg: AgentMetricsAccumulator): AgentMetricsAccumulator {
  return {
    rounds: agg.rounds,
    steps: agg.steps,
    llmMs: agg.llmMs,
    toolMs: agg.toolMs,
    ftSum: agg.ftSum,
    ftSamples: agg.ftSamples
  }
}

/**
 * 从落库快照**还原会话累计统计**（刷新 / 切换会话后调）
 *
 * 入参是 `metricsSnapshotOf()` 的产物（原始累加器形状）。缺字段按 0 处理；
 * 非法 / 缺失（老会话无统计）→ 全部归零（与升级前行为一致，不倒退）。
 */
export function restoreSessionAgg(snap?: Record<string, number> | null): AgentMetricsAccumulator {
  const n = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0)
  return {
    rounds: n(snap?.rounds),
    steps: n(snap?.steps),
    llmMs: n(snap?.llmMs),
    toolMs: n(snap?.toolMs),
    ftSum: n(snap?.ftSum),
    ftSamples: n(snap?.ftSamples)
  }
}

/**
 * 把「本轮累计值」的**增量**累进会话累加器，并返回**新的本轮快照**
 *
 * ⚠️ 事件里带的是**本轮累计值**（后端每次 `run_agent_stream` 都从 0 开始计数），
 *    而状态条要的是**会话累计** → 这里算增量再累加（整组覆盖会让每问一句就把旧账清掉）。
 * `curFtSum` = 本轮首 token 总和（后端只给平均值与样本数）：
 *    后端把平均值 `round()` 成整数，所以还原出的总和有几毫秒内的舍入误差，
 *    只影响显示、可忽略。
 *
 * @param agg 会话累加器（**原地**累加）
 * @param runSnapshot 上一份本轮快照（用于求增量）
 * @param cur 本轮累计值
 * @param curFtSum 本轮首 token 总和
 * @returns 新的本轮快照（调用方需替换掉旧的）
 */
export function applyMetricsDelta(
  agg: AgentMetricsAccumulator,
  runSnapshot: AgentMetricsAccumulator,
  cur: AgentMetricsRoundValues,
  curFtSum: number
): AgentMetricsAccumulator {
  agg.rounds += cur.rounds - runSnapshot.rounds
  agg.steps += cur.steps - runSnapshot.steps
  agg.llmMs += cur.llmMs - runSnapshot.llmMs
  agg.toolMs += cur.toolMs - runSnapshot.toolMs
  agg.ftSum += curFtSum - runSnapshot.ftSum
  agg.ftSamples += cur.ftSamples - runSnapshot.ftSamples
  return { ...cur, ftSum: curFtSum }
}
