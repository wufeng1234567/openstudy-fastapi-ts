/**
 * WebSocket 类型定义
 */

/** WebSocket 消息基类 */
export interface WsMessage {
  type: string
}

/** 聊天消息 */
export interface ChatMessage extends WsMessage {
  type: 'chat'
  senderId: number
  senderName?: string
  targetUserId: number
  content: string
  timestamp?: number
}

/** 心跳 */
export interface HeartbeatMessage extends WsMessage {
  type: 'heartbeat'
}

/** 用户状态 */
export interface UserStatusMessage extends WsMessage {
  type: 'user_online' | 'user_offline'
  userId: number
  userName?: string
}

/** 私信通知 */
export interface NoticeMessage extends WsMessage {
  type: 'notice'
  noticeId: number
  noticeTitle: string
  noticeContent?: string
}
