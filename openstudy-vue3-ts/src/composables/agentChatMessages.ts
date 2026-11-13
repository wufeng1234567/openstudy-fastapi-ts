// composables/agentChatMessages.ts
//
// Agent 消息流里各类消息的**形状构造**（从 `useAgentChat.ts` 抽出）。
//
// 这里只回答「这条消息长什么样」，**不碰状态、不发事件**：
//   · `buildAgentNote` —— 纠正 / 告警 / 错误提示气泡
//   · `buildToolResultMessage` —— 工具开始执行（转圈中的卡片）
//   · `buildToolResultFallback` —— 事件丢了 / 顺序异常时的兜底卡片
//   · `buildToolConfirmMessage` —— 写操作二次确认卡片
//   · `buildUserMessage` —— 用户提问气泡
//   · `buildAssistantTextMessage` —— 助手正文气泡
//
// ⚠ 依赖方向单向：`useAgentChat.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠ **事件时序与消息顺序一个字节都没动** —— 这里只是把「形状怎么算」挪到了
//    可以单独读、单独测的地方；`messages.value.push(...)` 的位置与先后完全不变。
import type { AgentEvent } from '@/api/ai/agent'
import type { AgentChatMessage } from './agentChatTypes'

/** 纠正 / 告警 / 错误提示气泡 */
export function buildAgentNote(
  kind: 'correct' | 'warning' | 'error',
  text: string,
  attempt?: number
): AgentChatMessage {
  return {
    role: 'assistant',
    type: 'agent_note',
    noteKind: kind,
    content: text,
    attempt
  }
}

/** 工具开始执行 —— 建一张「转圈中」的卡片 */
export function buildToolResultMessage(event: AgentEvent): AgentChatMessage {
  return {
    role: 'assistant',
    type: 'tool_result',
    tool: event.tool || '',
    action: event.action || event.params?.action || '',
    content: event.message || `正在执行 ${event.tool}…`,
    status: 'running',
    params: event.params
  }
}

/**
 * 没找到对应卡片（事件丢了 / 顺序异常）时的**兜底卡片**
 *
 * ⚠️ 用户取消（`cancelled`）**不走这里** —— 取消不是失败，不该在界面上多出一张
 *    红色的「批量删除失败」。确认卡片本身在 `tool_confirm_resolved` 时已经显示「已取消」。
 */
export function buildToolResultFallback(
  event: AgentEvent,
  detail: string,
  errs: string[]
): AgentChatMessage {
  return {
    role: 'assistant',
    type: 'tool_result',
    tool: event.tool || '',
    action: event.action || '',
    content: detail || `已执行 ${event.tool}`,
    status: event.success ? 'ok' : 'fail',
    errors: errs,
    data: event.data
  }
}

/** 写操作二次确认卡片（后端 api 付费链路下发） */
export function buildToolConfirmMessage(event: AgentEvent): AgentChatMessage {
  return {
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
  }
}

/**
 * 用户提问气泡
 *
 * ⚠️ 纯图片 / 纯附件的那一轮，`send()` 会把它落成 `[图片]` / `[附件]` ——
 *    回填输入框时也要跟用户当时看到的那条一致，所以这个兜底不能去掉。
 */
export function buildUserMessage(
  text: string,
  hasImages: boolean,
  attachments: any[]
): AgentChatMessage {
  return {
    role: 'user',
    content: String(text || '').trim() || (hasImages ? '[图片]' : '[附件]'),
    ...(attachments.length ? { attachments } : {})
  }
}

/** 助手正文气泡（`references` 非空时挂上来源引用） */
export function buildAssistantTextMessage(
  text: string,
  references: any[]
): AgentChatMessage {
  return {
    role: 'assistant',
    content: text,
    ...(references.length ? { references } : {})
  }
}
