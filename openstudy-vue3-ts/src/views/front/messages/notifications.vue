<template>
  <div class="notifications-page">
    <div class="page-header">
      <div class="page-title-wrap">
        <h3 class="page-title">系统通知</h3>
        <span class="page-desc">管理员发布的系统公告</span>
      </div>
      <div class="header-actions">
        <el-button v-if="noticeList.length > 0" class="delete-all-btn" size="small" @click="handleDeleteAll">
          清空全部
        </el-button>
        <el-button v-if="unreadCount > 0" class="read-all-btn" size="small" @click="handleReadAll">
          全部已读
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="notice-list">
      <div v-for="notice in noticeList" :key="notice.noticeId || notice.id" class="notice-card"
        :class="{ unread: !notice.read }" @click="handleClick(notice)">
        <div class="notice-left">
          <span v-if="!notice.read" class="unread-dot" />
        </div>
        <div class="notice-body">
          <div class="notice-title">{{ notice.noticeTitle || notice.title }}</div>
          <div class="notice-summary">
            {{ displayContent(notice) }}
          </div>
          <div v-if="needsExpand(notice.noticeContent || notice.content || '')" class="notice-expand-btn"
            @click.stop="toggleExpand(notice)">
            {{ expandedId === (notice.noticeId || notice.id) ? '收起' : '展开全文' }}
          </div>
          <div class="notice-time">{{ relativeTime(notice.createTime) }}</div>
        </div>
        <div class="notice-actions" @click.stop>
          <el-button class="delete-btn" :icon="Delete" circle @click="handleDelete(notice)" />
        </div>
      </div>
      <el-empty v-if="!loading && noticeList.length === 0" description="暂无系统通知" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { listAllNotice, markRead, markReadAll, deleteFrontNotice, deleteFrontNoticeBatch } from '@/api/system/notice'
import { isSystemNotice, parseNoticeRemark } from '@/utils/notice'

const router = useRouter()

const loading = ref(false)
const noticeList = ref([])
const unreadCount = ref(0)
const expandedId = ref(null)

const refreshBadge = inject('refreshBadge', () => { })

const fetchNotices = async () => {
  loading.value = true
  try {
    const res = await listAllNotice()
    const all = res.data || []
    // 系统通知只保留管理员发布的公告；
    // 评论 / 回复 / @我 属于用户通知，统一由「回复与@」页面管理
    noticeList.value = all.filter(isSystemNotice)
    unreadCount.value = noticeList.value.filter(n => !n.read).length
  } catch (e) {
    ElMessage.error('获取系统通知失败')
  } finally {
    loading.value = false
  }
}

const handleClick = (notice) => {
  const id = notice.noticeId || notice.id

  if (id && !notice.read) {
    notice.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    refreshBadge('sys', unreadCount.value)
    markRead(id).catch(() => { })
  }

  // 兼容历史数据：若系统通知带 remark.noteId，则跳转到对应笔记
  const remark = parseNoticeRemark(notice.remark)
  if (remark?.noteId) {
    let path = `/front/notes/detail/${remark.noteId}`
    if (remark.commentId) {
      path += `?focusComment=${remark.commentId}`
    }
    router.replace(path)
  }
}

const toggleExpand = (notice) => {
  const id = notice.noticeId || notice.id
  if (expandedId.value === id) {
    expandedId.value = null
  } else {
    expandedId.value = id
  }
}

/** 去掉 HTML 标签 + 解码常见实体，转成纯文本（通知内容是富文本 HTML） */
const stripHtml = (html) => {
  if (!html) return ''
  const s = String(html)
  // 无尖括号的纯文本直接返回（避免误删）
  if (!s.includes('<')) return s
  let text = s.replace(/<[^>]*>/g, ' ')
  text = text
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
  return text.replace(/\s+/g, ' ').trim()
}

const displayContent = (notice) => {
  const content = stripHtml(notice.noticeContent || notice.content || '')
  if (needsExpand(content) && expandedId.value !== (notice.noticeId || notice.id)) {
    return content.substring(0, 50) + '...'
  }
  return content
}

const handleReadAll = () => {
  const ids = noticeList.value
    .map(n => n.noticeId || n.id)
    .filter(Boolean)
    .join(',')
  if (!ids) return
  unreadCount.value = 0
  refreshBadge('sys', 0)
  ElMessage.success('已全部标记为已读')
  markReadAll(ids).catch(() => { })
}

const handleDelete = async (notice) => {
  const id = notice.noticeId || notice.id
  try {
    await ElMessageBox.confirm('确定要删除这条通知吗？（仅从你的列表移除，不影响其他用户）', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteFrontNotice(id)
    // 以服务端为准重新拉取，避免本地状态与服务端不一致（刷新后回弹）
    await fetchNotices()
    ElMessage.success('删除成功')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleDeleteAll = async () => {
  if (noticeList.value.length === 0) return
  try {
    await ElMessageBox.confirm('确定要清空全部通知吗？（仅从你的列表移除，不影响其他用户）', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const ids = noticeList.value
      .map(n => n.noticeId || n.id)
      .filter(Boolean)
    await deleteFrontNoticeBatch(ids)
    // 以服务端为准重新拉取，避免本地状态与服务端不一致（刷新后回弹）
    await fetchNotices()
    refreshBadge('sys', unreadCount.value)
    ElMessage.success('清空成功')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
}

const CONTENT_THRESHOLD = 50

const hasMoreContent = (content) => {
  if (!content) return false
  return content.length > CONTENT_THRESHOLD
}

const needsExpand = (content) => {
  return hasMoreContent(content)
}

const relativeTime = (time) => {
  if (!time) return ''
  const now = Date.now()
  const diff = now - new Date(time).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  const date = new Date(time)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

onMounted(() => {
  fetchNotices()
})
</script>

<style scoped lang="scss">
.notifications-page {
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 16px;

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

      &:hover {
        border-color: #f56c6c;
        color: #f56c6c;
      }
    }

    .read-all-btn {
      border-radius: 8px;
      font-weight: 500;
      padding: 5px 14px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        border-color: #409eff;
        color: #409eff;
      }
    }
  }

  .notice-list {
    .notice-card {
      display: flex;
      gap: 12px;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 12px;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

        .notice-actions {
          opacity: 1;
        }
      }

      .notice-left {
        width: 12px;
        flex-shrink: 0;
        padding-top: 6px;

        .unread-dot {
          display: block;
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #409eff;
        }
      }

      &.unread .notice-title {
        font-weight: 600;
      }

      .notice-body {
        flex: 1;
        min-width: 0;

        .notice-title {
          font-size: 15px;
          color: #1f2937;
          margin-bottom: 6px;
          font-weight: 500;
        }

        .notice-summary {
          font-size: 14px;
          line-height: 1.6;
          color: #6b7280;
          word-break: break-word;
          white-space: pre-wrap;
          margin-bottom: 4px;

          &.expanded {
            white-space: normal;
          }
        }

        .notice-expand-btn {
          font-size: 12px;
          color: #409eff;
          margin-bottom: 8px;
          cursor: pointer;
          user-select: none;

          &:hover {
            color: #66b1ff;
          }
        }

        .notice-time {
          font-size: 12px;
          color: #9ca3af;
        }
      }

      .notice-actions {
        display: flex;
        align-items: flex-start;
        opacity: 0;
        transition: opacity 0.2s;

        .delete-btn {
          padding: 4px;
          color: #9ca3af;
          background: transparent;
          border: none;
          transition: all 0.2s;

          &:hover {
            color: #b45353;
            background: #fef2f2;
          }
        }
      }
    }
  }
}
</style>
