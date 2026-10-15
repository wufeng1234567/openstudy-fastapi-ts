<template>
  <div class="comment-item"
    :class="{ 'has-replies': comment.replyCount > 0, 'target-highlight': comment._highlight }"
    @click="handleClickHighlight">
    <div class="comment-main">
      <UserAvatar :src="comment.avatar" :name="comment.userName || comment.name" :size="40"
        class="comment-avatar user-link" @click.stop="goToProfile(comment.userId)" />
      <div class="comment-body">
        <div class="comment-header">
          <span class="comment-username user-link" @click.stop="goToProfile(comment.userId)">{{ comment.userName ||
            comment.name }}</span>
          <span v-if="comment.replyToUserName" class="reply-to">
            <span class="reply-icon">→</span>
            <span class="reply-label user-link" @click.stop="goToProfile(comment.replyToUserId)">@{{
              comment.replyToUserName }}</span>
          </span>
        </div>
        <div class="comment-content" v-html="formattedContent" @click="handleContentClick"></div>
        <div class="comment-footer">
          <div class="footer-row">
            <span class="footer-time">{{ formatTime(comment.createTime) }}</span>
            <div class="footer-actions">
              <span class="action-link" @click="$emit('reply', comment)">回复</span>
              <span v-if="depth === 0 && !isPreview && !inThread" class="action-link"
                @click="$emit('viewThread', comment)">查看对话</span>
              <span v-if="comment.userId === currentUserId" class="action-link danger" @click="handleDelete">删除</span>
            </div>
          </div>
          <div v-if="replyCount && depth === 0 && !inThread" class="footer-reply-count"
            @click="$emit('viewThread', comment)">
            共 {{ replyCount }} 条回复，点击查看
          </div>
        </div>
      </div>
    </div>

    <!-- 子回复区域 -->
    <div v-if="replies && replies.length > 0 && depth < 3" class="replies-section" :class="{ 'no-indent': depth >= 1 }">
      <template v-for="(reply, idx) in visibleReplies" :key="reply.id">
        <CommentItem :comment="reply" :depth="depth + 1" :is-preview="isPreview" :expand-all="expandAll"
          :in-thread="inThread" @reply="(c) => $emit('reply', c)" @viewThread="(c) => $emit('viewThread', c)"
          @deleteComment="$emit('deleteComment', $event)" />
      </template>
      <el-button v-if="replies.length > 3 && !showAll && !expandAll && depth < 3" class="expand-replies-btn" text
        size="small" @click="showAll = true; cacheStore.toggleThread(props.comment.id)">
        展开剩余 {{ replies.length - 3 }} 条回复
      </el-button>
      <el-button v-if="showAll && replies.length > 3 && !expandAll && depth < 3" class="expand-replies-btn" text
        size="small" @click="showAll = false; cacheStore.toggleThread(props.comment.id)">
        收起
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import useUserStore from '@/store/modules/user'
import { useCommentCacheStore } from '@/store/modules/commentCache'
import { deleteComment } from '@/api/comment'
import { listUserFront } from '@/api/system/user'
import UserAvatar from '@/components/UserAvatar/index.vue'
import { renderMentionsHtml } from './mention'

const props = defineProps({
  comment: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  isPreview: { type: Boolean, default: false },
  expandAll: { type: Boolean, default: false },
  inThread: { type: Boolean, default: false }
})

const emit = defineEmits(['reply', 'viewThread', 'deleteComment'])

const router = useRouter()
const userStore = useUserStore()
const cacheStore = useCommentCacheStore()

const currentUserId = computed(() => userStore.id)

const handleClickHighlight = () => {
  if (props.comment._highlight) {
    props.comment._highlight = false
    props.comment._isNotificationTarget = false
  }
}

if (props.comment._highlight) {
  setTimeout(() => {
    props.comment._highlight = false
    props.comment._isNotificationTarget = false
  }, 5000)
}

const replies = computed(() => props.comment.children || [])
const replyCount = computed(() => props.comment.replyCount || props.comment.children?.length || 0)
const showAll = ref(false)

onMounted(() => {
  if (cacheStore.expandedThreads?.has?.(props.comment.id)) {
    showAll.value = true
  }
})

const visibleReplies = computed(() => {
  if (props.expandAll || showAll.value || props.isPreview) {
    return replies.value
  }
  return replies.value.slice(0, 3)
})

const goToProfile = (userId) => {
  if (!userId) return
  router.push(`/front/profile/${userId}`)
}

const handleDelete = async () => {
  try {
    await ElMessageBox.confirm('确定删除这条评论吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await deleteComment(props.comment.id)
    ElMessage.success('删除成功')
    emit('deleteComment', props.comment.id)
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const formatTime = (time) => {
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

const AT_SPAN_STYLE =
  'cursor:pointer;color:#409eff;background:#e8f4ff;border-radius:3px;padding:1px 4px;font-weight:500;'

/** 生成一个 @ 提及的 span（userId 为空表示老数据里只有昵称、没带 id） */
const atSpan = (userId: string | number, name: string) =>
  `<span class="at-mention" style="${AT_SPAN_STYLE}" data-userid="${userId}" data-username="${name}">@${name}</span>`

const formattedContent = computed(() => {
  // 解析规则集中在 ./mention.ts（评论正文与私信正文共用同一套，别在这里再写一份正则）。
  // 那里保证：`@{106} 演示用户2` → 蓝字 `@演示用户2`，且**永不会把 `{106}` 漏到界面上**。
  return renderMentionsHtml(props.comment.content || '', atSpan)
})

const handleContentClick = async (e) => {
  const target = e.target
  if (target.classList.contains('at-mention')) {
    const userId = target.getAttribute('data-userid')
    if (userId) {
      router.push(`/front/profile/${userId}`)
      return
    }
    const username = target.getAttribute('data-username')
    if (username) {
      try {
        const res = await listUserFront({ pageNum: 1, pageSize: 10 })
        const users = res.rows || []
        const matched = users.find(u => u.userName === username || u.nickName === username)
        if (matched) {
          router.push(`/front/profile/${matched.userId}`)
        } else {
          ElMessage.warning('未找到该用户')
        }
      } catch (e) {
        console.error('查询用户失败:', e)
        ElMessage.warning('未找到该用户')
      }
    }
  }
}
</script>

<style scoped lang="scss">
.comment-item {
  .comment-main {
    display: flex;
    gap: 10px;

    .comment-avatar {
      flex-shrink: 0;
    }

    .comment-body {
      flex: 1;
      min-width: 0;

      .comment-header {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 4px;

        .comment-username {
          font-weight: 600;
          font-size: 14px;
          color: #1f2937;
        }

        .reply-to {
          display: inline-flex;
          align-items: center;
          gap: 2px;

          .reply-icon {
            font-size: 12px;
            color: #9ca3af;
          }

          .reply-label {
            font-size: 12px;
            color: #409eff;
            font-weight: 500;
            background: #e8f4ff;
            border-radius: 4px;
            padding: 1px 6px;
          }
        }
      }

      .comment-content {
        font-size: 14px;
        line-height: 1.6;
        color: #374151;
        word-break: break-word;
        white-space: pre-wrap;

        :deep(.at-mention) {
          color: #409eff;
          background: #e8f4ff;
          border-radius: 3px;
          padding: 1px 4px;
          cursor: pointer;
          font-weight: 500;
          transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
          user-select: none;

          &:hover {
            background: #d0e8ff;
            color: #2d7dd2;
            transform: translateY(-1px);
            box-shadow: 0 1px 3px rgba(64, 158, 255, 0.15);
          }
        }
      }

      .comment-footer {
        margin-top: 8px;

        .footer-row {
          display: flex;
          justify-content: space-between;
          align-items: center;

          .footer-time {
            font-size: 12px;
            color: #9ca3af;
          }

          .footer-actions {
            display: flex;
            gap: 12px;

            .action-link {
              font-size: 12px;
              color: #9ca3af;
              cursor: pointer;
              transition: color 0.2s;
              user-select: none;

              &:hover {
                color: #409eff;
              }

              &.danger:hover {
                color: #f56c6c;
              }
            }
          }
        }

        .footer-reply-count {
          margin-top: 4px;
          font-size: 12px;
          color: #9ca3af;
          cursor: pointer;
          transition: color 0.2s;
          user-select: none;

          &:hover {
            color: #409eff;
          }
        }
      }
    }
  }

  .replies-section {
    margin-left: 20px;
    border-left: 2px solid #f3f4f6;

    &.no-indent {
      margin-left: 0;
      border-left: none;
    }

    .expand-replies-btn {
      font-size: 12px;
      padding: 4px 10px;
      color: #6b7280;
      background: #f3f4f6;
      border-radius: 4px;
      margin-top: 4px;

      &:hover {
        color: #409eff;
        background: #e8f4ff;
      }
    }
  }
}

.comment-item.has-replies {
  padding-bottom: 4px;
}

.user-link {
  cursor: pointer;
  transition: all 0.2s ease;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid transparent;
}

.user-link:hover {
  color: #409eff;
  border-bottom: 1px dashed #409eff;
}

.comment-avatar.user-link {
  border-bottom: none;
}

.comment-avatar.user-link:hover {
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.3);
}

.reply-label.user-link {
  border-bottom: none;
}

.comment-item.target-highlight {
  position: relative;
  background: #f9fafb;
  border-radius: 8px;
  transition: background 0.6s cubic-bezier(0.4, 0, 0.2, 1);

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    border-radius: 8px;
    background: linear-gradient(90deg,
        transparent 0%,
        rgba(0, 0, 0, 0.02) 30%,
        rgba(0, 0, 0, 0.04) 50%,
        rgba(0, 0, 0, 0.02) 70%,
        transparent 100%);
    pointer-events: none;
    animation: shimmerSweep 2s cubic-bezier(0.4, 0, 0.2, 1) 1 forwards;
    opacity: 0;
  }
}

@keyframes shimmerSweep {
  0% {
    opacity: 0;
    transform: translateX(-30%);
  }

  25% {
    opacity: 1;
  }

  75% {
    opacity: 1;
    transform: translateX(30%);
  }

  100% {
    opacity: 0;
    transform: translateX(30%);
  }
}



.reply-label.user-link:hover {
  color: #409eff;
}
</style>
