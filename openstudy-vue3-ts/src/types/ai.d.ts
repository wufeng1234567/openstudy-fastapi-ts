/**
 * AI 相关类型定义
 */

/** AI 对话消息 */
export interface AiMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

/** AI 聊天请求 */
export interface AiChatRequest {
  messages: AiMessage[]
  model?: string
  provider?: string
  temperature?: number
  max_tokens?: number
  stream?: boolean
}

/** AI 出题请求 */
export interface AiGenerateRequest {
  topic: string
  question_type?: string
  count?: number
  difficulty?: number
  bank_id?: number
  model?: string
  provider?: string
}

/** 流式响应数据块 */
export interface StreamChunk {
  content?: string
  delta?: string
  done?: boolean
  error?: string
  [key: string]: any
}

/** 文档转换块 */
export interface DocumentBlock {
  type: 'text' | 'image' | 'table' | 'code' | 'heading' | 'list'
  content: string
  level?: number
  items?: string[]
  [key: string]: any
}

/** AI 模型配置 */
export interface AiModelConfig {
  modelId?: number
  modelName: string
  provider: string
  apiKey?: string
  apiUrl?: string
  isDefault?: boolean
  status: string
  [key: string]: any
}

/** AI 聊天会话 */
export interface AiChatSession {
  sessionId?: number
  userId: number
  title: string
  model?: string
  provider?: string
  messageCount?: number
  createTime?: string
  updateTime?: string
  [key: string]: any
}

/** AI 聊天记录 */
export interface AiChatRecord {
  recordId?: number
  sessionId: number
  role: string
  content: string
  tokens?: number
  createTime?: string
  [key: string]: any
}
