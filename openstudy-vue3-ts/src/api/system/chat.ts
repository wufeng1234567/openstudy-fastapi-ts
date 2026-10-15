import request from '@/utils/request'

export function getConversations() {
  return request({
    url: '/system/chat/conversations',
    method: 'get'
  })
}

export function getChatHistory(otherUserId: number | string, page: number = 1, size: number = 20, hidden: boolean = false) {
  return request({
    url: '/system/chat/history/' + otherUserId,
    method: 'get',
    params: { page, size, hidden }
  })
}

export function sendMessage(data: any) {
  return request({
    url: '/system/chat/send',
    method: 'post',
    params: {
      receiverId: data.receiverId,
      content: data.content
    }
  })
}

export function markRead(senderId: number | string) {
  return request({
    url: '/system/chat/markRead/' + senderId,
    method: 'post'
  })
}

export function deleteMessage(messageId: number | string) {
  return request({
    url: '/system/chat/message/' + messageId,
    method: 'delete'
  })
}

export function deleteConversation(otherUserId: number | string) {
  return request({
    url: '/system/chat/conversation/' + otherUserId,
    method: 'delete'
  })
}

export function createConversation(otherUserId: number | string) {
  return request({
    url: '/system/chat/conversation/' + otherUserId,
    method: 'post'
  })
}

export function clearChatHistory(otherUserId: number | string) {
  return request({
    url: '/system/chat/history/clear/' + otherUserId,
    method: 'post'
  })
}

export function getUnreadCount() {
  return request({
    url: '/system/chat/unreadCount',
    method: 'get'
  })
}

export function syncChatToDatabase() {
  return request({
    url: '/system/chat/sync',
    method: 'post'
  })
}

export function searchUsers(keyword: string = '') {
  return request({
    url: '/system/chat/users',
    method: 'get',
    params: { keyword }
  })
}
