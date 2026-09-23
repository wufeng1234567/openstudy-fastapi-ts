<template>
  <div class="mentions-page">
    <div class="page-header">
      <div class="page-title-wrap">
        <h3 class="page-title">回复与@</h3>
        <span class="page-desc">汇总了用户对你笔记的评论、对你留言的回复，以及 @ 你的消息</span>
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
          <div class="notice-title">
            <span v-if="getTypeLabel(notice)" class="notice-type-tag" :class="`is-${getNoticeType(notice)}`">
              {{ getTypeLabel(notice) }}
            </span>
            <!-- 谁 + 做了什么：发起人昵称由后端在列表行上补（notice.fromNickName），
                 拿不到时退回原来那句笼统标题，避免出现「undefined 评论了你的笔记」 -->
            <span v-if="getActor(notice)" class="notice-title-text">
              <span class="notice-actor">{{ getActor(notice) }}</span>
              {{ getActionText(notice) }}
            </span>
            <span v-else class="notice-title-text">{{ notice.noticeTitle || notice.title }}</span>
          </div>
          <div class="notice-summary">{{ plainMentions(notice.noticeContent || notice.content) }}</div>
          <div class="notice-time">{{ relativeTime(notice.createTime) }}</div>
        </div>
        <div class="notice-actions" @click.stop>
          <el-button class="delete-btn" :icon="Delete" circle @click="handleDelete(notice)" />
        </div>
      </div>
      <el-empty v-if="!loading && noticeList.length === 0" description="暂无回复与@消息" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import { listAllNotice, markRead, markReadAll, deleteFrontNotice, deleteFrontNoticeBatch } from '@/api/system/notice'
import { isUserNoticeFor, getUserNoticeType, getUserNoticeTypeLabel, parseNoticeRemark } from '@/utils/notice'
import { plainMentions } from '@/components/CommentSection/mention'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const noticeList = ref([])
const unreadCount = ref(0)

const refreshBadge = inject('refreshBadge', () => { })

// 通知类型标签：评论 / 回复 / @我
const getNoticeType = (notice) => getUserNoticeType(notice)
const getTypeLabel = (notice) => getUserNoticeTypeLabel(notice)

/**
 * 「谁在回复你 / 谁在 @ 你」。
 * remark 里只存了数字 fromUserId，昵称是后端在列表行上补的 fromNickName（只读增强，见 notices.py）。
 * 后端拿不到时**不加这个键**，这里就是空串 → 模板退回显示 notice_title（不显示空名字）。
 */
const getActor = (notice) => notice.fromNickName || ''

/**
 * 三类动作文案（用户点名定的口径，别乱改）：
 * - comment 一级留言  → 「演示用户1 评论了你的笔记」
 * - reply   子留言     → 「演示用户1 回复了你」
 * - mention 被 @       → 「演示用户1 @了你」
 */
const ACTION_TEXT: Record<string, string> = {
  comment: '评论了你的笔记',
  reply: '回复了你',
  mention: '@了你'
}
const getActionText = (notice) =>
  ACTION_TEXT[getNoticeType(notice)] || notice.noticeTitle || notice.title || ''

// 「回复与@」= 发给当前用户的全部用户通知（评论 + 回复 + @我）
const fetchUserNotices = async () => {
  loading.value = true
  try {
    const res = await listAllNotice()
    const all = res.data || []
    const myId = userStore.id
    const mine = all.filter(n => isUserNoticeFor(n, myId))
    noticeList.value = mine
    unreadCount.value = mine.filter(n => !n.read).length
  } catch (e) {
    ElMessage.error('获取「回复与@」消息失败')
  } finally {
    loading.value = false
  }
}

const handleClick = (notice) => {
  const id = notice.noticeId || notice.id

  if (id && !notice.read) {
    // 标记为已读
    notice.read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    refreshBadge('user', unreadCount.value)
    markRead(id).catch(() => { })
  }

  // 跳转到对应笔记 / 评论
  const remark = parseNoticeRemark(notice.remark)
  if (remark?.noteId) {
    let path = `/front/notes/detail/${remark.noteId}`
    if (remark.commentId) {
      path += `?focusComment=${remark.commentId}`
    }
    router.replace(path)
  }
}

const handleReadAll = () => {
  const ids = noticeList.value
    .map(n => n.noticeId || n.id)
    .filter(Boolean)
    .join(',')
  if (!ids) return
  unreadCount.value = 0
  refreshBadge('user', 0)
  ElMessage.success('已全部标记为已读')
  markReadAll(ids).catch(() => { })
}

const handleDelete = async (notice) => {
  const id = notice.noticeId || notice.id
  try {
    await ElMessageBox.confirm('确定要删除这条消息吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteFrontNotice(id)
    noticeList.value = noticeList.value.filter(n => (n.noticeId || n.id) !== id)
    if (!notice.read) {
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      refreshBadge('user', unreadCount.value)
    }
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
    await ElMessageBox.confirm('确定要清空全部「回复与@」消息吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    const ids = noticeList.value
      .map(n => n.noticeId || n.id)
      .filter(Boolean)
    await deleteFrontNoticeBatch(ids)
    noticeList.value = []
    unreadCount.value = 0
    refreshBadge('user', 0)
    ElMessage.success('清空成功')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
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
  fetchUserNotices()
})
</script>

<style scoped lang="scss">
.mentions-page {
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
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 15px;
          color: #1f2937;
          margin-bottom: 6px;
          font-weight: 500;
        }

        .notice-title-text {
          min-width: 0;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        /* 发起人：整行里最该被一眼看到的东西 */
        .notice-actor {
          font-weight: 600;
          color: #111827;
        }

        .notice-type-tag {
          flex-shrink: 0;
          padding: 3px 8px;
          font-size: 11px;
          line-height: 1;
          font-weight: 500;
          border-radius: 4px;
          border: 1px solid transparent;

          /* 三种类型用色相拉开距离：评论=蓝、回复=绿、@我=紫 */
          &.is-comment {
            background: #eff6ff;
            border-color: #bfdbfe;
            color: #2563eb;
          }

          &.is-reply {
            background: #f0fdf4;
            border-color: #bbf7d0;
            color: #16a34a;
          }

          &.is-mention {
            background: #f5f3ff;
            border-color: #ddd6fe;
            color: #7c3aed;
          }
        }

        .notice-summary {
          font-size: 14px;
          line-height: 1.6;
          color: #6b7280;
          word-break: break-word;
          white-space: pre-wrap;
          margin-bottom: 4px;
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