// composables/agentChatEventShapes.ts
//
// Agent SSE 事件 → 消息流片段的**纯构造器**（从 `useAgentChat.ts` 抽出）。
//
// 这里放的全是「拿到事件 / 数据 → 算出一个片段」的无副作用函数：
//   · **进度步骤** —— `buildProgressStep` / `upsertStepById` / `closeRunningSteps`
//   · **子代理步骤** —— `buildSubagentStep` / `trimSubagentSteps` / `isUserVisibleProgressPhase`
//   · **专家工作组行** —— `buildExpertRow` / `buildExpertDoneRow` / `findExpertRow`
//   · **确认卡片消息** —— `buildConfirmMessage`
//
// ⚠️ 依赖方向单向：`useAgentChat.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠️ 本模块**只算形状、不碰状态**：`messages.value` 的读写、事件的收口时机
//    全部留在 composable 里 —— 事件顺序与 SSE 契约一个字节都没动。
import type { AgentEvent } from '@/api/ai/agent'
import type {
  AgentChatMessage,
  AgentExpertProgress,
  AgentProgressStep
} from './agentChatTypes'
import { stripMarkdown } from './agentChatText'

/**
 * 每个专家行最多保留的**子代理步骤**条数（`subagent_event` 累积）。
 *
 * 一个子代理一轮可能跑几十次工具往返，事件量远超用户在卡片上想看的量。留最近若干条
 * 就够表达「它现在做到哪、刚做完什么」，也让落库快照不至于被步骤撑大。
 */
export const SUBAGENT_STEPS_LIMIT = 20

/** 专家卡片的「一行」（子代理步骤）的类型 */
type ExpertStep = NonNullable<AgentExpertProgress['steps']>[number]

/**
 * 由 `progress` 事件算出进度步骤
 *
 * 返回 `null` = 这个事件没有 `id`，直接忽略（与原实现的口径一致）。
 */
export function buildProgressStep(event: AgentEvent): AgentProgressStep | null {
  const id = String(event.id || '')
  if (!id) return null
  const state: AgentProgressStep['state'] =
    event.state === 'done' ? 'done' : event.state === 'failed' ? 'failed' : 'running'
  return {
    id,
    message: String(event.message || ''),
    state,
    icon: event.icon
  }
}

/** 同 `id` 就更新、否则追加（进度清单的更新口径） */
export function upsertStepById(steps: AgentProgressStep[], step: AgentProgressStep): void {
  const i = steps.findIndex((s) => s.id === step.id)
  if (i >= 0) steps[i] = step
  else steps.push(step)
}

/**
 * 把仍在 `running` 的步骤标成 `done`
 *
 * 轮末收口用：避免最后一步永远停在转圈。
 */
export function closeRunningSteps(steps: AgentProgressStep[] | undefined): void {
  for (const s of steps || []) {
    if (s.state === 'running') s.state = 'done'
  }
}

/** 由 `subagent_event` 算出子代理的阶段步骤 */
export function buildSubagentStep(event: AgentEvent): ExpertStep {
  return {
    phase: String(event.phase || ''),
    message: String(event.message || ''),
    tool: event.tool ? String(event.tool) : undefined,
    success: typeof event.success === 'boolean' ? event.success : null,
    round: Number(event.round) || 0
  }
}

/** 只留最近 N 条：长任务会有几十步，全留既费内存又没人看 */
export function trimSubagentSteps(steps: ExpertStep[]): void {
  if (steps.length > SUBAGENT_STEPS_LIMIT) {
    steps.splice(0, steps.length - SUBAGENT_STEPS_LIMIT)
  }
}

/**
 * 任务行显示的进展文案**只认工具类**事件（`正在调用 XX…` / 工具结果）——
 * `round`（「第 N 轮思考」）与 `start`（「开始处理任务」）是内部噪声，不该占据那一行
 * （用户 2026-10-16 报「信息太多、看不懂」）。
 */
export function isUserVisibleProgressPhase(phase: string): boolean {
  return ['tool_call', 'tool_result', 'error'].includes(phase)
}

/** 由 `delegate_start` 算出「专家开工中」那一行 */
export function buildExpertRow(event: AgentEvent): AgentExpertProgress {
  const ag = event.agent || {}
  return {
    index: Number(event.index ?? 0) || 0,
    key: String(ag.id || ''),
    name: String(ag.name || ag.id || '专家'),
    status: 'running',
    task: stripMarkdown(String(event.task || ''))
  }
}

/** 卡片丢了（异常）时补的那一行（已带结论） */
export function buildExpertDoneRow(event: AgentEvent): AgentExpertProgress {
  const ag = event.agent || {}
  const idx = Number(event.index ?? -1)
  return {
    index: idx >= 0 ? idx : 0,
    key: String(ag.id || ''),
    name: String(ag.name || ag.id || '专家'),
    status: event.success ? 'ok' : 'fail',
    summary: stripMarkdown(String(event.summary || ''))
  }
}

/**
 * 按 **index → key → index** 三级回退找到专家卡片里对应的那一行
 *
 * ⚠️ 第一级**要求该行仍在 `running`**：后端已把 index 改成「整轮全局唯一」，
 *   正常不会撞号；这里再挡一道，避免异常情况下把已完成的行重复回填、让真正的那行留在转圈。
 */
export function findExpertRow(
  experts: AgentExpertProgress[],
  index: number,
  key: string
): AgentExpertProgress | undefined {
  let row = index >= 0 ? experts.find((e) => e.index === index && e.status === 'running') : undefined
  if (!row) {
    // index 缺失 / 越界 / 已回填过 → 回退到「按 key 找最近一个 running 行」
    row = [...experts].reverse().find((e) => e.key === key && e.status === 'running')
  }
  if (!row && index >= 0) {
    // 仍找不到：index 对应行已存在（已回填）时，直接按 index 取回来补（幂等，避免漏状态）
    row = experts.find((e) => e.index === index)
  }
  return row
}

/**
 * 确认卡片的消息体（`requestConfirm` 用）
 *
 * 形状与旧实现完全一致（前端 `AgentToolResult` / 确认卡片按这些字段渲染）。
 */
export function buildConfirmMessage(
  info: {
    tool: string
    action?: string
    params?: Record<string, any>
    destructive?: boolean
    message?: string
    preview?: Record<string, any>
  },
  confirmId: string
): AgentChatMessage {
  return {
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
  }
}
