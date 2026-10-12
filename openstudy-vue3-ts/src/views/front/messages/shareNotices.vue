<!-- ==================== 分享通知 ==================== -->
<!-- 题库分享相关的定向通知：有人领取了你的分享 / 你收藏的分享已失效 -->
<template>
  <div class="share-notice-page">
    <div class="page-header">
      <div class="page-title-wrap">
        <h3 class="page-title">分享通知</h3>
        <span class="page-desc">有人领取了你的分享，或你收藏的分享已失效</span>
      </div>
      <div class="header-actions">
        <el-button v-if="noticeList.length > 0" class="delete-all-btn" size="small" @click="handleClearAll">
          清空
        </el-button>
        <el-button v-if="unreadCount > 0" class="read-all-btn" size="small" @click="handleMarkAllRead">
          全部已读
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="notice-list">
      <div v-for="notice in noticeList" :key="notice.notificationId" class="notice-card"
        :class="{ unread: !notice.read }" @click="handleClick(notice)">
        <span v-if="!notice.read" class="unread-dot" />
        <div class="notice-body">
          <div class="notice-title">{{ notice.title }}</div>
          <div class="notice-content">{{ notice.content }}</div>
          <div class="notice-time">{{ relativeTime(notice.createTime) }}</div>
        </div>
        <div class="notice-actions" @click.stop>
          <el-button :icon="Delete" circle size="small" @click="handleDelete(notice)" />
        </div>
      </div>

      <el-empty v-if="!loading && noticeList.length === 0" description="暂无分享通知" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMessagesShareNotices' })
import { ref, inject, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import {
  listMyNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  deleteNotification,
  clearNotifications
} from '@/api/notification/notification'

const router = useRouter()
const refreshBadge = inject<(type: string, count: number) => void>('refreshBadge', () => { })

const loading = ref(false)
const noticeList = ref<any[]>([])
const unreadCount = ref(0)

const syncUnread = () => {
  unreadCount.value = noticeList.value.filter(n => !n.read).length
  refreshBadge('share', unreadCount.value)
}

const relativeTime = (timeStr?: string) => {
  if (!timeStr) return ''
  const target = new Date(timeStr).getTime()
  if (Number.isNaN(target)) return timeStr
  const diff = Date.now() - target
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (diff < minute) return '刚刚'
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`
  const d = new Date(target)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

const fetchNotices = async () => {
  loading.value = true
  try {
    const res: any = await listMyNotifications({ pageNum: 1, pageSize: 50 })
    if (res.code === 200) {
      noticeList.value = res.data?.rows || []
      syncUnread()
    }
  } catch (e) {
    // 静默失败，避免打断页面
  } finally {
    loading.value = false
  }
}

const handleClick = async (notice: any) => {
  if (!notice.read) {
    try {
      await markNotificationRead(notice.notificationId)
      notice.read = true
      syncUnread()
    } catch (e) { }
  }
  if (notice.link) {
    router.push(notice.link)
  }
}

const handleDelete = async (notice: any) => {
  try {
    await deleteNotification(notice.notificationId)
    noticeList.value = noticeList.value.filter(n => n.notificationId !== notice.notificationId)
    syncUnread()
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

const handleMarkAllRead = async () => {
  try {
    await markAllNotificationsRead()
    noticeList.value.forEach(n => { n.read = true })
    syncUnread()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

const handleClearAll = async () => {
  try {
    await clearNotifications()
    noticeList.value = []
    syncUnread()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

onMounted(fetchNotices)
</script>

<style scoped>
.share-notice-page {
  min-height: 300px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.page-title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.page-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.page-desc {
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.delete-all-btn {
  border-radius: 8px;
  font-weight: 500;
  padding: 5px 14px;
  color: #b45353;
  background: #fef2f2;
  border: 1px solid #e5d0d0;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.delete-all-btn:hover {
  border-color: #f56c6c;
  color: #f56c6c;
}

.read-all-btn {
  border-radius: 8px;
  font-weight: 500;
  padding: 5px 14px;
  color: #6b7280;
  background: #fff;
  border: 1px solid #e5e7eb;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.read-all-btn:hover {
  border-color: #409eff;
  color: #409eff;
}

.notice-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.notice-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.07);
}

.notice-card.unread {
  border-left: 3px solid #409EFF;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409EFF;
  flex-shrink: 0;
  margin-top: 6px;
}

.notice-body {
  flex: 1;
  min-width: 0;
}

.notice-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.notice-content {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.6;
  margin-bottom: 6px;
  word-break: break-all;
}

.notice-time {
  font-size: 12px;
  color: #9ca3af;
}

.notice-actions {
  flex-shrink: 0;
}
</style>
