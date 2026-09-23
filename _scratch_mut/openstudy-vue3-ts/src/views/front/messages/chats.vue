<template>
  <div class="chat-container">
    <div class="chat-left">
      <div class="chat-conversations">
        <div class="conversations-header">
          <span>会话列表</span>
          <el-button text :icon="Plus" @click="showNewChatDialog = true" class="new-chat-btn" />
        </div>
        <div class="conversations-list">
          <div v-for="conv in conversations" :key="conv.userId" class="conversation-item"
            :class="{ active: selectedUserId === conv.userId }" @click="selectConversation(conv)">
            <UserAvatar :size="44" :src="conv.avatar" :name="conv.nickname" class="conv-avatar" />
            <div class="conv-info">
              <div class="conv-top">
                <span class="conv-name">{{ conv.nickname }}</span>
                <span class="conv-time">{{ formatTime(conv.lastMessageTime) }}</span>
              </div>
              <div class="conv-bottom">
                <span class="conv-preview">{{ conv.lastMessage }}</span>
                <el-badge v-if="conv.unreadCount > 0" :value="conv.unreadCount" :max="99" class="conv-badge" />
              </div>
            </div>
          </div>
          <el-empty v-if="conversations.length === 0" description="暂无会话" :image-size="60" />
        </div>
      </div>
    </div>

    <div class="chat-right">
      <template v-if="selectedUserId">
        <div class="chat-header">
          <div class="chat-user-info">
            <UserAvatar :size="36" :src="selectedUser.avatar" :name="selectedUser.nickname" class="chat-avatar" />
            <span class="chat-username">{{ selectedUser.nickname }}</span>
          </div>
          <el-dropdown trigger="click" @command="handleCommand">
            <el-button text :icon="MoreFilled" class="more-btn" />
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="deleteConversation">删除会话</el-dropdown-item>
                <el-dropdown-item command="clearHistory">清空聊天记录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="chat-messages" ref="messagesContainer">
          <div v-if="loadingHistory" class="loading-more">
            <el-icon class="is-loading">
              <Loading />
            </el-icon>
            加载中...
          </div>
          <div v-if="hasMoreHistory && !loadingHistory" class="load-more-btn" @click="loadMoreHistory">
            加载更多消息
          </div>
          <div v-for="msg in messages" :key="msg.id" class="message-item"
            :class="{ mine: msg.senderId === currentUserId }">
            <UserAvatar :size="36" :src="msg.senderId === currentUserId ? myAvatar : msg.senderAvatar"
              :name="msg.senderId === currentUserId ? myNickname : msg.senderNickname" class="msg-avatar" />
            <div class="message-content">
              <div class="message-bubble">
                <span>{{ msg.content }}</span>
                <el-button v-if="msg.senderId === currentUserId" text :icon="Delete" class="delete-msg-btn"
                  @click="deleteMessage(msg.id)" />
              </div>
              <div class="message-time">{{ formatTime(msg.createTime) }}</div>
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <div class="input-tools">
            <el-button text :icon="Picture" @click="handleSelectImage" title="发送图片" />
            <input type="file" ref="fileInput" accept="image/*" style="display:none" @change="handleImageChange" />
          </div>
          <div class="input-wrapper">
            <el-input v-model="inputMessage" type="textarea" :rows="3" placeholder="输入消息..." resize="none"
              @keydown.enter.exact.prevent @keydown.ctrl.enter="handleSend" />
          </div>
          <div class="input-actions">
            <span class="shortcut-hint">Ctrl+Enter 发送</span>
            <el-button type="primary" :disabled="!inputMessage.trim()" @click="handleSend">
              发送
            </el-button>
          </div>
        </div>
      </template>

      <el-empty v-else description="选择一位用户开始聊天" :image-size="80" />
    </div>

    <el-dialog v-model="showNewChatDialog" title="发起私信" width="400px">
      <div class="search-user-wrapper">
        <el-input v-model="searchKeyword" placeholder="搜索用户..." clearable @input="handleSearchUser">
          <template #prefix>
            <el-icon>
              <Search />
            </el-icon>
          </template>
        </el-input>
      </div>
      <div class="user-list">
        <div v-for="user in searchResults" :key="user.userId" class="user-item" @click="startNewChat(user)">
          <UserAvatar :size="36" :src="user.avatar" :name="user.nickname" />
          <div class="user-info">
            <div class="user-name">{{ user.nickname }}</div>
            <div class="user-account">@{{ user.username }}</div>
          </div>
        </div>
        <el-empty v-if="searchResults.length === 0 && searchKeyword" description="未找到用户" :image-size="40" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, MoreFilled, Picture, Loading, Plus, Search } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import UserAvatar from '@/components/UserAvatar/index.vue'
import {
  getConversations,
  getChatHistory,
  sendMessage,
  markRead,
  deleteMessage as deleteMessageApi,
  deleteConversation as deleteConversationApi,
  createConversation,
  clearChatHistory,
  getUnreadCount,
  searchUsers
} from '@/api/system/chat'

const userStore = useUserStore()
const refreshBadge = inject('refreshBadge')

const currentUserId = computed(() => userStore.id)
const myAvatar = computed(() => userStore.avatar)
const myNickname = computed(() => userStore.name)

const conversations = ref([])
const selectedUserId = ref(null)
const selectedUser = ref({})
const messages = ref([])
const inputMessage = ref('')
const messagesContainer = ref(null)
const fileInput = ref(null)
const page = ref(1)
const size = 20
const hasMoreHistory = ref(true)
const loadingHistory = ref(false)

const showNewChatDialog = ref(false)
const searchKeyword = ref('')
const searchResults = ref([])

const handleSearchUser = async () => {
  try {
    const res = await searchUsers(searchKeyword.value)
    searchResults.value = res.data || []
  } catch (e) {
    console.error('搜索用户失败', e)
  }
}

const startNewChat = async (user) => {
  showNewChatDialog.value = false
  searchKeyword.value = ''
  searchResults.value = []

  try {
    const res = await createConversation(user.userId)
    const convUser = res.data || user

    const conv = {
      userId: convUser.userId,
      nickname: convUser.nickname,
      avatar: convUser.avatar,
      lastMessage: '',
      lastMessageTime: null,
      unreadCount: 0
    }

    const exists = conversations.value.find(c => c.userId === convUser.userId)
    if (!exists) {
      conversations.value.unshift(conv)
    }

    await selectConversation(conv)
  } catch (e) {
    ElMessage.error('创建会话失败')
  }
}

const selectConversation = async (conv) => {
  if (selectedUserId.value === conv.userId) {
    scrollToBottom()
    return
  }

  selectedUserId.value = conv.userId
  selectedUser.value = {
    userId: conv.userId,
    nickname: conv.nickname,
    avatar: conv.avatar
  }
  page.value = 1
  messages.value = []
  hasMoreHistory.value = true
  loadingHidden.value = false

  clearConvUnread(conv.userId)
  saveLastChatUser(conv.userId)

  await loadHistory()
  await markAsRead()

  await nextTick()
  scrollToBottom()
}

const clearConvUnread = (userId) => {
  const conv = conversations.value.find(c => c.userId === userId)
  if (conv) {
    conv.unreadCount = 0
  }
}

const loadingHidden = ref(false)

const loadHistory = async (hidden = false) => {
  if (!selectedUserId.value) return
  loadingHistory.value = true
  try {
    const res = await getChatHistory(selectedUserId.value, page.value, size, hidden)
    const data = res.data || {}
    const newMessages = data.messages || []
    if (page.value === 1) {
      messages.value = newMessages
    } else {
      messages.value = [...newMessages, ...messages.value]
    }
    if (hidden) {
      hasMoreHistory.value = data.hasMore || false
    } else {
      hasMoreHistory.value = data.hasMore || false
      if (!hasMoreHistory.value && data.hasHidden) {
        hasMoreHistory.value = true
        loadingHidden.value = true
      }
    }
  } catch (e) {
    console.error('加载历史消息失败', e)
  } finally {
    loadingHistory.value = false
  }
}

const loadMoreHistory = async () => {
  if (loadingHidden.value) {
    page.value = 1
    loadingHidden.value = false
    await loadHistory(true)
  } else {
    page.value++
    await loadHistory(loadingHidden.value)
  }
}

const handleSend = async () => {
  const content = inputMessage.value.trim()
  if (!content || !selectedUserId.value) return

  try {
    const res = await sendMessage({
      receiverId: selectedUserId.value,
      content
    })
    if (res.code === 200) {
      messages.value.push(res.data)
      inputMessage.value = ''
      clearConvUnread(selectedUserId.value)
      await nextTick()
      scrollToBottom()
      await loadConversations()
    }
  } catch (e) {
    ElMessage.error('发送消息失败')
  }
}

const markAsRead = async () => {
  if (!selectedUserId.value) return
  try {
    await markRead(selectedUserId.value)
    await updateBadge()
  } catch (e) {
    console.error('标记已读失败', e)
  }
}

const deleteMessage = async (messageId) => {
  try {
    await ElMessageBox.confirm('确定删除该消息吗？', '提示', { type: 'warning' })
    await deleteMessageApi(messageId)
    messages.value = messages.value.filter(m => m.id !== messageId)
    ElMessage.success('删除成功')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

const handleCommand = async (command) => {
  if (command === 'deleteConversation') {
    try {
      await ElMessageBox.confirm('确定删除该会话吗？', '提示', { type: 'warning' })
      await deleteConversationApi(selectedUserId.value)
      selectedUserId.value = null
      selectedUser.value = {}
      messages.value = []
      await loadConversations()
      ElMessage.success('删除成功')
    } catch (e) {
      if (e !== 'cancel') ElMessage.error('删除失败')
    }
  } else if (command === 'clearHistory') {
    try {
      await ElMessageBox.confirm('确定清空与该用户的全部聊天记录吗？此操作仅影响您这边，对方仍可查看聊天记录。', '提示', { type: 'warning' })
      await clearChatHistory(selectedUserId.value)
      messages.value = []
      page.value = 1
      loadingHidden.value = true
      hasMoreHistory.value = true
      ElMessage.success('聊天记录已清空')
    } catch (e) {
      if (e !== 'cancel') {
        console.error('[clearHistory] 清空失败', e)
        ElMessage.error('清空失败')
      }
    }
  }
}

const handleSelectImage = () => {
  fileInput.value?.click()
}

const handleImageChange = (e) => {
  const file = e.target.files[0]
  if (file) {
    ElMessage.info('图片发送功能开发中')
  }
}

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const loadConversations = async () => {
  try {
    const res = await getConversations()
    conversations.value = res.data || []
  } catch (e) {
    console.error('加载会话列表失败', e)
  }
}

const LAST_CHAT_KEY = 'lastChatUserId'

const saveLastChatUser = (userId) => {
  if (userId) {
    localStorage.setItem(LAST_CHAT_KEY, userId)
  }
}

const loadLastChatUser = () => {
  return localStorage.getItem(LAST_CHAT_KEY)
}

const autoSelectLastChat = async () => {
  const lastUserId = loadLastChatUser()
  if (lastUserId && conversations.value.length > 0) {
    const conv = conversations.value.find(c => c.userId == lastUserId)
    if (conv) {
      clearConvUnread(conv.userId)
      await selectConversation(conv)
    }
  }
}

const updateBadge = async () => {
  try {
    const res = await getUnreadCount()
    if (typeof refreshBadge === 'function') {
      refreshBadge('chat', res.data || 0)
    }
  } catch (e) {
    // 静默处理，不影响功能
  }
}

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()
  const diff = now - date

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  if (diff < 604800000) return Math.floor(diff / 86400000) + '天前'

  return date.toLocaleDateString()
}

onMounted(async () => {
  await loadConversations()
  await updateBadge()
  await autoSelectLastChat()

  wsRetryCount = 0

  const userId = userStore.id || userStore.userId || userStore.user_id
  console.log('[WebSocket] onMounted userId:', userId, 'current ws:', ws, 'wsConnected:', wsConnected)
  if (userId) {
    initWebSocket()
  } else {
    const checkUserReady = setInterval(() => {
      const readyUserId = userStore.id || userStore.userId || userStore.user_id
      console.log('[WebSocket] waiting for userId, current:', readyUserId)
      if (readyUserId) {
        clearInterval(checkUserReady)
        initWebSocket()
      }
    }, 200)
  }
})

let ws = null
let wsConnected = false
let wsRetryCount = 0
const MAX_WS_RETRIES = 5

const initWebSocket = () => {
  const userId = userStore.id || userStore.userId || userStore.user_id
  console.log('[WebSocket] initWebSocket called, userId:', userId, 'current ws:', ws, 'wsConnected:', wsConnected)

  if (!userId) {
    console.warn('WebSocket 初始化失败: userId 不存在', userId)
    if (wsRetryCount < MAX_WS_RETRIES) {
      wsRetryCount++
      console.log(`WebSocket 重试 (${wsRetryCount}/${MAX_WS_RETRIES})`)
      setTimeout(initWebSocket, 1000)
    }
    return
  }

  if (ws && wsConnected) {
    console.log('[WebSocket] Already connected, skipping')
    return
  }

  if (ws) {
    console.log('[WebSocket] Closing existing ws before creating new one')
    ws.close()
    ws = null
    wsConnected = false
  }

  wsRetryCount = 0
  const wsUrl = `/ws/chat?userId=${userId}`

  console.log('正在连接 WebSocket:', wsUrl)
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    console.log('WebSocket 连接成功, userId:', userId)
    wsConnected = true
    wsRetryCount = 0
  }

  ws.onerror = (error) => {
    console.log('WebSocket 连接发生错误')
    console.error('WebSocket 错误', error)
    wsConnected = false
    ws = null
  }

  ws.onmessage = (event) => {
    console.log('[WebSocket] onmessage received, data:', event.data)
    try {
      const message = JSON.parse(event.data)
      console.log('[WebSocket] parsed message:', message)
      handleNewMessage(message)
    } catch (e) {
      console.error('解析 WebSocket 消息失败', e)
    }
  }

  ws.onclose = (event) => {
    console.log('WebSocket 连接关闭, code:', event.code, 'reason:', event.reason)
    wsConnected = false
    ws = null
  }
}

const handleNewMessage = (message) => {
  console.log('[WebSocket] handleNewMessage called:', message)
  if (message.senderId === selectedUserId.value) {
    console.log('[WebSocket] Message from selected user, adding to messages')
    messages.value.push(message)
    nextTick(() => scrollToBottom())
    markMessageAsRead(message.senderId)
  }

  const convIndex = conversations.value.findIndex(c => {
    const otherId = c.userId
    return otherId === message.senderId || otherId === message.receiverId
  })

  if (convIndex !== -1) {
    const conv = conversations.value[convIndex]
    conv.lastMessage = message.content
    conv.lastMessageTime = message.createTime
    if (message.senderId !== currentUserId.value) {
      if (message.senderId !== selectedUserId.value) {
        conv.unreadCount = (conv.unreadCount || 0) + 1
        updateBadge()
      }
    } else {
      conv.unreadCount = 0
    }
    conversations.value.splice(convIndex, 1)
    conversations.value.unshift(conv)
  } else {
    const otherUserId = message.senderId === currentUserId.value ? message.receiverId : message.senderId
    const otherNickname = message.senderId === currentUserId.value ? message.receiverNickname : message.senderNickname
    const otherAvatar = message.senderId === currentUserId.value ? message.receiverAvatar : message.senderAvatar

    const newConv = {
      userId: otherUserId,
      nickname: otherNickname,
      avatar: otherAvatar,
      lastMessage: message.content,
      lastMessageTime: message.createTime,
      unreadCount: message.senderId !== currentUserId.value ? 1 : 0
    }

    conversations.value.unshift(newConv)
    updateBadge()
  }
}

const markMessageAsRead = async (senderId) => {
  try {
    await markRead(senderId)
    updateBadge()
  } catch (e) {
    console.error('标记已读失败', e)
  }
}

onUnmounted(() => {
  console.log('[WebSocket] onUnmounted, closing ws:', ws)
  if (ws) {
    ws.close()
    ws = null
    wsConnected = false
  }
})
</script>

<style scoped lang="scss">
.chat-container {
  display: flex;
  height: calc(100vh - 85px);
  background: var(--el-bg-color);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.04);
}

.chat-left {
  overflow-y: auto;
}

.chat-right {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.chat-left {
  width: 280px;
  background: #ffffff;
  border: 1px solid var(--el-border-color-lighter);
  border-right: none;
  border-radius: 8px 0 0 8px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .chat-container {
    height: calc(100vh - 80px);
    border-radius: 0;
    border-left: none;
    border-right: none;
  }

  .chat-left {
    width: 180px;
  }
}

@media (max-width: 480px) {
  .chat-container {
    flex-direction: column;
  }

  .chat-left {
    width: 100%;
    height: auto;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid var(--el-border-color-lighter);
    border-radius: 8px 8px 0 0;
  }

  .chat-right {
    flex: 1;
    border-radius: 0 0 8px 8px;
  }

  .conversations-list {
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    overflow-y: hidden;

    &::-webkit-scrollbar {
      height: 0;
    }
  }

  .conversation-item {
    flex-shrink: 0;
    flex-direction: column;
    width: 80px;
    padding: 8px;
    text-align: center;
    border-bottom: none;
    border-right: 1px solid var(--el-border-color-lighter);

    &:last-child {
      border-right: none;
    }
  }

  .conv-avatar {
    margin-right: 0;
    margin-bottom: 4px;
  }

  .conv-info {
    width: 100%;
  }

  .conv-top {
    flex-direction: column;
    gap: 2px;
  }

  .conv-name {
    font-size: 11px;
  }

  .conv-time {
    display: none;
  }

  .conv-bottom {
    display: none;
  }

  .conv-badge {
    position: absolute;
    top: 2px;
    right: 2px;
  }

  .conversation-item {
    position: relative;
  }
}

.chat-conversations {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.conversations-header {
  padding: 16px;
  font-weight: 600;
  font-size: 15px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--el-text-color-primary);
}

.conversations-list {
  flex: 1;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--el-border-color-lighter);
    border-radius: 2px;
  }
}

.conversation-item {
  display: flex;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid var(--el-border-color-lighter);

  &:hover {
    background: var(--el-fill-color);
  }

  &.active {
    background: #f9fafb;
    border-left: 3px solid #6b7280;
    padding-left: 13px;
  }
}

.conv-avatar {
  flex-shrink: 0;
  margin-right: 12px;
}

.conv-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.conv-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.conv-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  margin-left: 8px;
}

.conv-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.conv-preview {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.conv-badge {
  flex-shrink: 0;
  margin-left: 8px;
}

.chat-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 0 8px 8px 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}

.chat-user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-avatar {
}

.chat-username {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.more-btn {
  font-size: 16px;
  color: var(--el-text-color-secondary);

  &:hover {
    color: #4b5563;
  }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: var(--el-fill-color-lighter);

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--el-border-color-lighter);
    border-radius: 2px;
  }
}

.loading-more,
.load-more-btn {
  text-align: center;
  padding: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s;

  &:hover {
    color: #4b5563;
  }
}

.load-more-btn {
  margin-bottom: 12px;
}

.message-item {
  display: flex;
  margin-bottom: 8px;
  align-items: flex-start;

  &.mine {
    flex-direction: row-reverse;

    .message-bubble {
      background: #f0f2f5;
      color: #1f2937;
      margin-right: 10px;
    }

    .message-time {
      text-align: right;
      margin-right: 10px;
    }
  }
}

.msg-avatar {
  flex-shrink: 0;
}

.message-content {
  max-width: 70%;
}

.message-bubble {
  display: inline-block;
  background: var(--el-bg-color);
  padding: 6px 12px;
  border-radius: 6px;
  word-break: break-word;
  line-height: 1.4;
  font-size: 14px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.delete-msg-btn {
  font-size: 12px;
  opacity: 0;
  padding: 4px;
  color: var(--el-text-color-secondary);
  transition: opacity 0.15s;

  &:hover {
    opacity: 1;
    color: var(--el-color-danger);
  }
}

.message-item:hover .delete-msg-btn {
  opacity: 0.5;
}

.message-time {
  font-size: 10px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  margin-left: 10px;
}

.chat-input-area {
  flex-shrink: 0;
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 10px 12px;
  background: var(--el-bg-color);
}

.input-tools {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.input-wrapper {
  margin-bottom: 8px;

  :deep(.el-textarea__inner) {
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 14px;
    line-height: 1.4;
  }
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 12px;
}

.shortcut-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.new-chat-btn {
  margin-left: auto;
  font-size: 18px;
  color: #6b7280;

  &:hover {
    background: #f9fafb;
  }
}

.search-user-wrapper {
  margin-bottom: 12px;
}

.user-list {
  max-height: 280px;
  overflow-y: auto;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.15s;

  &:hover {
    background: var(--el-fill-color);
  }
}

.user-info {
  flex: 1;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.user-account {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

@media (max-width: 1200px) {
  .chat-left {
    width: 240px;
  }

  .conversation-item {
    padding: 10px 12px;
  }

  .conv-avatar {
    margin-right: 10px;
  }

  .conv-name {
    font-size: 13px;
  }

  .conv-preview {
    font-size: 11px;
  }

  .message-item {
    margin-bottom: 8px;
  }

  .message-bubble {
    padding: 6px 10px;
    font-size: 13px;
  }

  .message-time {
    font-size: 10px;
  }
}

@media (max-width: 1024px) {
  .chat-left {
    width: 200px;
  }

  .conversations-header {
    padding: 12px;
    font-size: 14px;
  }

  .conversation-item {
    padding: 8px 10px;
  }

  .conv-avatar {
    margin-right: 8px;
  }

  .conv-info {
    min-width: 0;
  }

  .conv-top {
    margin-bottom: 2px;
  }

  .conv-name {
    font-size: 13px;
  }

  .conv-time {
    font-size: 10px;
    margin-left: 4px;
  }

  .conv-preview {
    font-size: 11px;
  }

  .chat-header {
    padding: 10px 12px;
  }

  .chat-username {
    font-size: 14px;
  }

  .chat-messages {
    padding: 10px;
  }

  .message-item {
    margin-bottom: 8px;
  }

  .message-bubble {
    padding: 6px 10px;
    font-size: 13px;
  }

  .message-time {
    font-size: 10px;
  }

  .chat-input-area {
    padding: 8px 10px;
  }

  .input-wrapper {
    margin-bottom: 6px;

    :deep(.el-textarea__inner) {
      padding: 6px 10px;
      font-size: 13px;
    }
  }
}

@media (max-width: 768px) {
  .chat-container {
    border-radius: 0;
    border-left: none;
    border-right: none;
  }

  .chat-left {
    width: 180px;
  }

  .conversations-header {
    padding: 10px;
    font-size: 13px;
  }

  .new-chat-btn {
    font-size: 16px;
  }

  .conversation-item {
    padding: 8px;
  }

  .conv-avatar {
    margin-right: 6px;
  }

  .conv-name {
    font-size: 12px;
  }

  .conv-time {
    font-size: 10px;
    margin-left: 2px;
  }

  .conv-preview {
    font-size: 10px;
  }

  .conv-badge {
    :deep(.el-badge__content) {
      font-size: 10px;
      min-width: 16px;
      height: 16px;
      line-height: 14px;
    }
  }

  .chat-right {
    border-radius: 0;
  }

  .chat-header {
    padding: 8px 10px;
  }

  .chat-avatar {
    width: 32px !important;
    height: 32px !important;
  }

  .chat-username {
    font-size: 13px;
  }

  .more-btn {
    font-size: 14px;
  }

  .chat-messages {
    padding: 8px;
  }

  .message-item {
    margin-bottom: 6px;
  }

  .msg-avatar {
    width: 32px !important;
    height: 32px !important;
  }

  .message-content {
    max-width: 80%;
  }

  .message-bubble {
    padding: 5px 8px;
    font-size: 13px;
    border-radius: 4px;
  }

  .message-time {
    font-size: 9px;
    margin-top: 1px;
  }

  .chat-input-area {
    padding: 8px;
  }

  .input-wrapper {
    margin-bottom: 6px;

    :deep(.el-textarea__inner) {
      padding: 6px 8px;
      font-size: 13px;
    }
  }

  .shortcut-hint {
    display: none;
  }
}

@media (max-width: 480px) {
  .chat-container {
    flex-direction: column;
  }

  .chat-left {
    width: 100%;
    height: auto;
    max-height: 200px;
    border-right: none;
    border-bottom: 1px solid var(--el-border-color-lighter);
    border-radius: 8px 8px 0 0;
  }

  .chat-right {
    flex: 1;
    border-radius: 0 0 8px 8px;
  }

  .conversations-list {
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    overflow-y: hidden;

    &::-webkit-scrollbar {
      height: 0;
    }
  }

  .conversation-item {
    flex-shrink: 0;
    flex-direction: column;
    width: 80px;
    padding: 8px;
    text-align: center;
    border-bottom: none;
    border-right: 1px solid var(--el-border-color-lighter);

    &:last-child {
      border-right: none;
    }
  }

  .conv-avatar {
    margin-right: 0;
    margin-bottom: 4px;
  }

  .conv-info {
    width: 100%;
  }

  .conv-top {
    flex-direction: column;
    gap: 2px;
  }

  .conv-name {
    font-size: 11px;
  }

  .conv-time {
    display: none;
  }

  .conv-bottom {
    display: none;
  }

  .conv-badge {
    position: absolute;
    top: 2px;
    right: 2px;
  }

  .conversation-item {
    position: relative;
  }
}
</style>
