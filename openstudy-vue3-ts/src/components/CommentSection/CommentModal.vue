<template>
  <div v-if="visible" class="comment-modal-overlay" @click.self="handleClose">
    <div class="comment-modal-container">
      <div class="modal-toolbar">
        <div class="toolbar-title">
          💬 全部评论
          <span v-if="total" class="comment-count">({{ total }})</span>
        </div>
        <el-button class="close-btn" size="small" circle @click="handleClose">
          <el-icon>
            <Close />
          </el-icon>
        </el-button>
      </div>

      <div v-loading="loading" class="modal-body">
        <div v-if="commentList.length > 0" class="comment-list">
          <div v-for="comment in commentList" :key="comment.id" class="comment-card">
            <CommentItem :comment="comment" :depth="0" :is-preview="false" @reply="handleReply"
              @viewThread="openThreadDialog" @deleteComment="handleDeleteComment" />
          </div>
        </div>
        <el-empty v-if="!loading && commentList.length === 0" description="暂无评论" />
      </div>

      <div v-if="total > pageSize" class="modal-pagination">
        <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total"
          layout="prev, pager, next" small @current-change="handlePageChange" />
      </div>

      <CommentInput ref="inputRef" :reply-target="replyTarget" placeholder="写下你的评论..." @submit="handleSubmit"
        @cancelReply="handleCancelReply" />
    </div>

    <!-- 查看对话弹窗 -->
    <el-dialog v-model="threadVisible" title="查看对话" width="600px" :close-on-click-modal="false" class="thread-dialog"
      append-to-body>
      <div v-loading="threadLoading" class="thread-body">
        <CommentItem v-if="threadComment"
          :key="'thread-' + threadComment.id + '-' + (threadComment.children?.length || 0)" :comment="threadComment"
          :depth="0" :is-preview="false" :expand-all="true" :in-thread="true" @reply="handleThreadReply"
          @deleteComment="handleThreadDeleteComment" @click="clearThreadHighlight" />
        <el-empty v-if="!threadLoading && !threadComment" description="暂无对话数据" />
      </div>
      <template #footer>
        <CommentInput ref="threadInputRef" :reply-target="threadReplyTarget" placeholder="回复这条评论..." submit-text="回复"
          @submit="handleThreadSubmit" @cancelReply="handleThreadCancelReply" />
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { listComments, createComment, getCommentThread } from '@/api/comment'
import { ensureLogin } from '@/utils/loginGuard'
import { useCommentCacheStore } from '@/store/modules/commentCache'
import CommentItem from './CommentItem.vue'
import CommentInput from './CommentInput.vue'

const props = defineProps({
  noteId: { type: [Number, String], required: true },
  visible: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'commentAdded'])

const cacheStore = useCommentCacheStore()

const noteId = computed(() => Number(props.noteId))

const loading = ref(false)
const commentList = ref([])
const total = ref(0)
const pageSize = 10
const currentPage = ref(1)
const inputRef = ref(null)

const replyTarget = computed(() => cacheStore.replyTarget)

// 查看对话弹窗
const threadVisible = ref(false)
const threadLoading = ref(false)
const threadComment = ref(null)
const threadReplyTarget = ref(null)
const threadInputRef = ref(null)
const focusLocked = ref(false)

// 预加载评论数据（弹窗显示前调用，避免出现"暂无评论"闪烁）
const prepare = async () => {
  if (!noteId.value) return
  cacheStore.setNoteId(noteId.value)
  currentPage.value = cacheStore.currentPage
  loading.value = true
  try {
    const res = await listComments(noteId.value, currentPage.value, pageSize)
    const data = res.data || res
    commentList.value = [...(data.list || [])]
    total.value = data.total || 0
  } catch (e) {
    ElMessage.error('获取评论失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    if (commentList.value.length === 0) {
      prepare()
    }
  }
})

watch(() => props.noteId, () => {
  if (props.visible) {
    cacheStore.setNoteId(noteId.value)
    currentPage.value = 1
    cacheStore.setPage(1)
    prepare()
  }
})

const handlePageChange = (page) => {
  currentPage.value = page
  cacheStore.setPage(page)
  prepare()
}

const handleReply = async (comment) => {
  if (!(await ensureLogin('回复评论'))) return
  cacheStore.setReplyTarget({ id: comment.id, userId: comment.userId, userName: comment.userName || comment.name })
  nextTick(() => {
    inputRef.value?.$el?.querySelector('textarea')?.focus()
  })
}

const handleCancelReply = () => {
  cacheStore.clearReplyTarget()
}

const openThreadDialog = async (comment) => {
  threadVisible.value = true
  threadLoading.value = true
  threadComment.value = null
  threadReplyTarget.value = null
  try {
    const res = await getCommentThread(comment.id)
    threadComment.value = res.data || res
  } catch (e) {
    ElMessage.error('获取对话失败')
  } finally {
    threadLoading.value = false
  }
}

const handleThreadReply = async (comment) => {
  if (!(await ensureLogin('回复评论'))) return
  threadReplyTarget.value = { id: comment.id, userId: comment.userId, userName: comment.userName || comment.name }
  nextTick(() => {
    threadInputRef.value?.$el?.querySelector('textarea')?.focus()
  })
}

const handleThreadCancelReply = () => {
  threadReplyTarget.value = null
}


const handleThreadSubmit = async (content) => {
  if (!(await ensureLogin('回复评论'))) return
  const target = threadReplyTarget.value || {
    id: threadComment.value?.id,
    userId: threadComment.value?.userId,
    userName: threadComment.value?.userName
  }

  if (!target.id) return

  const params = {
    noteId: noteId.value,
    content,
    parentId: target.id,
    replyToUserId: target.userId,
    replyToUserName: target.userName
  }

  try {
    await createComment(params)
    ElMessage.success('回复成功')

    threadInputRef.value?.clear()

    if (threadComment.value?.id) {
      const threadRes = await getCommentThread(threadComment.value.id)
      threadComment.value = JSON.parse(JSON.stringify(threadRes.data || threadRes))
    }

    emit('commentAdded')
  } catch (e) {
    ElMessage.error('回复失败')
  }
}

const handleThreadDeleteComment = async () => {
  threadVisible.value = false
  await prepare()
  emit('commentAdded')
}

const handleSubmit = async (content) => {
  if (!(await ensureLogin('发表评论'))) return
  const params = { noteId: noteId.value, content }

  if (replyTarget.value) {
    params.parentId = replyTarget.value.id
    params.replyToUserId = replyTarget.value.userId
    params.replyToUserName = replyTarget.value.userName
  }

  try {
    await createComment(params)
    ElMessage.success('发表成功')

    if (replyTarget.value) cacheStore.clearReplyTarget()

    await prepare()
    inputRef.value?.clear()
    emit('commentAdded')
  } catch (e) {
    inputRef.value?.clear()
    ElMessage.error('发表失败')
  }
}

const handleDeleteComment = async () => {
  await prepare()
}

const handleClose = () => {
  emit('close')
}

async function focusOnComment(commentId) {
  if (focusLocked.value) {
    console.log(`[CommentModal] focusOnComment(${commentId}) 被锁定，跳过`)
    return
  }
  focusLocked.value = true
  console.log(`[CommentModal] focusOnComment(${commentId}) 开始, commentList长度=${commentList.value.length}`)

  try {
    console.log(`[CommentModal] 调用 getCommentThread(${commentId})...`)
    const threadRes = await getCommentThread(commentId)
    console.log(`[CommentModal] getCommentThread返回:`, threadRes)
    let threadData = JSON.parse(JSON.stringify(threadRes.data || threadRes))
    console.log(`[CommentModal] 获取评论线程成功:`, threadData.id, 'parentId:', threadData.parentId, '数据:', threadData)

    if (!threadData || !threadData.id) {
      console.log(`[CommentModal] threadData为空或没有id`)
      ElMessage.warning('未找到对应评论')
      return
    }

    const findInTree = (tree, targetId) => {
      if (!tree) return false
      if (tree.id === targetId) return true
      if (tree.children) {
        return tree.children.some(child => findInTree(child, targetId))
      }
      return false
    }

    const markHighlight = (comment, targetId) => {
      if (comment.id === targetId) {
        comment._highlight = true
        comment._isNotificationTarget = true
        return true
      }
      if (comment.children) {
        for (const child of comment.children) {
          if (markHighlight(child, targetId)) return true
        }
      }
      return false
    }

    if (threadData.parentId !== null) {
      if (commentList.value.length === 0) {
        await prepare()
      }

      let foundRoot = null
      for (const comment of commentList.value) {
        if (!comment.children || comment.children.length === 0) {
          try {
            const res = await getCommentThread(comment.id)
            const data = res.data || res
            if (data && data.children) {
              comment.children = data.children
            }
          } catch (e) {
          }
        }
        if (findInTree(comment, commentId)) {
          foundRoot = comment
          break
        }
      }

      if (!foundRoot) {
        ElMessage.warning('未找到对应评论')
        return
      }

      const fullRes = await getCommentThread(foundRoot.id)
      threadData = JSON.parse(JSON.stringify(fullRes.data || fullRes))
      markHighlight(threadData, commentId)

      threadVisible.value = true
      threadLoading.value = true
      threadComment.value = null
      threadReplyTarget.value = null
      threadComment.value = threadData
      threadLoading.value = false
      console.log(`[CommentModal] 查看对话弹窗已打开, 评论ID: ${commentId}`)

      await nextTick()
      setTimeout(() => {
        const el = document.querySelector('.comment-item.target-highlight')
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          console.log(`[CommentModal] 已滚动到评论: ${commentId}`)
        }
      }, 300)
    } else {
      // 一级评论：在评论列表中定位
      console.log(`[CommentModal] 一级评论，查找对应页码...`)
      const targetPage = await findCommentPage(commentId)
      console.log(`[CommentModal] 目标页码=${targetPage}`)
      if (targetPage) {
        currentPage.value = targetPage
        cacheStore.setPage(targetPage)
      }
      await prepare()
      console.log(`[CommentModal] 加载评论列表, 数量=${commentList.value.length}`)

      let found = null
      for (const comment of commentList.value) {
        if (comment.id === commentId) {
          found = comment
          break
        }
        if (comment.children && findInTree(comment, commentId)) {
          found = comment
          break
        }
      }

      if (!found) {
        console.log(`[CommentModal] 当前页未找到，重新获取评论数据...`)
        const res = await getCommentThread(commentId)
        const data = res.data || res
        if (data) {
          found = data
          const idx = commentList.value.findIndex(c => c.id === found.id)
          if (idx >= 0) {
            commentList.value[idx] = found
          } else {
            commentList.value.unshift(found)
          }
        }
      }

      console.log(`[CommentModal] found=${found ? '有' : '无'}`)
      if (found) {
        markHighlight(found, commentId)
      }

      await nextTick()
      setTimeout(() => {
        const el = document.querySelector('.comment-item.target-highlight')
        console.log(`[CommentModal] 查找高亮元素: ${el ? '找到' : '未找到'}`)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' })
          console.log(`[CommentModal] 已滚动到评论: ${commentId}`)
        }
      }, 300)
    }
  } catch (e) {
    console.error('[CommentModal] 定位评论失败:', e)
    ElMessage.error('定位评论失败')
  } finally {
    setTimeout(() => { focusLocked.value = false }, 2000)
  }
}

async function findCommentPage(commentId) {
  try {
    const totalCountRes = await listComments(noteId.value, 1, pageSize)
    const totalCount = totalCountRes.data?.total || totalCountRes.total || 0
    const totalPages = Math.ceil(totalCount / pageSize)

    for (let page = 1; page <= totalPages; page++) {
      const res = await listComments(noteId.value, page, pageSize)
      const data = res.data || res
      const list = data.list || []
      if (list.some(c => c.id === commentId)) {
        return page
      }
    }
  } catch (e) {
    console.error('查找评论页码失败:', e)
  }
  return 1
}

defineExpose({ focusOnComment, prepare })

const clearThreadHighlight = () => {
  if (threadComment.value?._highlight) {
    threadComment.value._highlight = false
  }
  const clearChildren = (comment) => {
    if (comment.children) {
      comment.children.forEach(child => {
        child._highlight = false
        clearChildren(child)
      })
    }
  }
  clearChildren(threadComment.value)
}
</script>

<style scoped lang="scss">
.comment-modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  justify-content: center;
  padding-top: 40px;
}

.comment-modal-container {
  width: 1000px;
  max-width: 95vw;
  height: calc(100vh - 80px);
  background: #fff;
  border-radius: 16px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
  overflow: hidden;
}

.modal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;

  .toolbar-title {
    font-size: 18px;
    font-weight: 600;
    color: #1f2937;

    .comment-count {
      font-weight: 400;
      color: #6b7280;
      font-size: 16px;
    }
  }

  .close-btn {
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover {
      border-color: #d1d5db;
      color: #4b5563;
    }
  }
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;

  .comment-list {
    .comment-card {
      background: #fff;
      border-radius: 16px;
      border: 1px solid #e5e7eb;
      padding: 16px;
      margin-bottom: 12px;
      transition: box-shadow 0.3s;

      &:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
      }
    }
  }
}

.modal-pagination {
  display: flex;
  justify-content: center;
  padding: 12px 0;
  border-top: 1px solid #f3f4f6;
  flex-shrink: 0;
}

.thread-body {
  min-height: 200px;
  max-height: 50vh;
  overflow-y: auto;
}
</style>
