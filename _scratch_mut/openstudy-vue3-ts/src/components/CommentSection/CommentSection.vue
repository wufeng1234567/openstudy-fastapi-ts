<template>
  <div class="comment-section">
    <div class="preview-area" v-if="!initialLoading">
      <div v-if="previewComments.length > 0" class="preview-comments">
        <div v-for="comment in previewComments" :key="comment.id" class="preview-card">
          <CommentItem :comment="comment" :depth="0" :is-preview="true" @reply="onReplyFromPreview"
            @viewThread="openPreviewThread" />
        </div>
      </div>

      <div class="comment-actions-bar">
        <div class="write-comment" @click="focusWriteInput">
          <span class="write-placeholder">📝 写评论...</span>
        </div>
        <CommentInput v-if="showWriteInput" ref="writeInputRef" :reply-target="null" placeholder="写下你的评论..."
          @submit="handleSubmitComment" />
        <el-button v-if="totalComments > 0" class="view-all-btn" size="small" @click="openModal">
          查看全部 {{ totalComments }} 条评论
        </el-button>
      </div>
    </div>

    <CommentModal ref="modalRef" :note-id="noteId" :visible="showModal" @close="showModal = false"
      @commentAdded="onCommentAdded" />

    <!-- 预览区查看对话弹窗 -->
    <el-dialog v-model="previewThreadVisible" title="查看对话" width="560px" :close-on-click-modal="false"
      class="thread-dialog" append-to-body>
      <div v-loading="previewThreadLoading" class="preview-thread-body">
        <CommentItem v-if="previewThreadComment"
          :key="'preview-thread-' + previewThreadComment.id + '-' + (previewThreadComment.children?.length || 0)"
          :comment="previewThreadComment" :depth="0" :is-preview="false" :expand-all="true" :in-thread="true"
          @reply="handleThreadReply" />
        <el-empty v-if="!previewThreadLoading && !previewThreadComment" description="暂无回复数据" />
      </div>
      <template #footer>
        <CommentInput ref="threadInputRef" :reply-target="threadReplyTarget"
          :placeholder="'回复 @' + (threadReplyTarget?.userName || '') + '...'" submit-text="回复"
          @submit="handleThreadSubmit" @cancelReply="handleThreadCancelReply" />
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onDeactivated, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listComments, createComment, getCommentThread } from '@/api/comment'
import { ensureLogin } from '@/utils/loginGuard'
import { useCommentCacheStore } from '@/store/modules/commentCache'
import CommentItem from './CommentItem.vue'
import CommentInput from './CommentInput.vue'
import CommentModal from './CommentModal.vue'

const props = defineProps({
  noteId: { type: [Number, String], required: true },
})

const route = useRoute()
const modalRef = ref(null)
const focusLocked = ref(false)
const cacheStore = useCommentCacheStore()

const noteId = computed(() => Number(props.noteId))

const previewComments = ref([])
const totalComments = ref(0)
const initialLoading = ref(false)
const showWriteInput = ref(false)
const showModal = ref(false)
const writeInputRef = ref(null)

const previewThreadVisible = ref(false)
const previewThreadLoading = ref(false)
const previewThreadComment = ref(null)
const threadReplyTarget = ref(null)
const threadInputRef = ref(null)

/**
 * keep-alive 会把本组件的弹窗状态一起缓存下来：离开页面 / 换一篇笔记时若不主动关，
 * 下次再进「学习分享」的笔记页，上一次通知跳转打开的「查看对话」会原样重现。
 */
const closeOverlays = () => {
  showModal.value = false
  previewThreadVisible.value = false
  threadReplyTarget.value = null
  focusLocked.value = false
}

// ⚠️ 这里**不要**去 router.replace 摘掉 ?focusComment=。
//    父级 views/front/notes/index.vue:10 是用 :key="route.fullPath" 渲染本页的，
//    改 query 就等于换 key → detail.vue + 本组件当场 UNMOUNT + MOUNT（已用真实 router
//    实测：after replace: ["Detail UNMOUNT","Detail MOUNT"]），
//    而 handleFocusFromRoute 正处在 await 中间 → 弹窗会随实例一起被拆掉，点通知将不再弹。
//    一次性参数的重放问题在源头解决：lastVisited 不再记录 focusComment。

const onReplyFromPreview = async (comment) => {
  if (!(await ensureLogin('回复评论'))) return
  threadReplyTarget.value = { id: comment.id, userId: comment.userId, userName: comment.userName || comment.name }
  openPreviewThread(comment)
}

const openPreviewThread = async (comment) => {
  previewThreadVisible.value = true
  previewThreadLoading.value = true
  previewThreadComment.value = null
  if (!threadReplyTarget.value) {
    threadReplyTarget.value = { id: comment.id, userId: comment.userId, userName: comment.userName || comment.name }
  }
  try {
    const res = await getCommentThread(comment.id)
    previewThreadComment.value = res.data || res
  } catch (e) {
    ElMessage.error('获取回复数据失败')
  } finally {
    previewThreadLoading.value = false
  }
}

const handleThreadReply = (comment) => {
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
    id: previewThreadComment.value?.id,
    userId: previewThreadComment.value?.userId,
    userName: previewThreadComment.value?.userName
  }
  if (!target.id) return
  const params = { noteId: noteId.value, content, parentId: target.id, replyToUserId: target.userId, replyToUserName: target.userName }
  try {
    await createComment(params)
    ElMessage.success('回复成功')
    threadInputRef.value?.clear()
    if (previewThreadComment.value?.id) {
      const threadRes = await getCommentThread(previewThreadComment.value.id)
      previewThreadComment.value = JSON.parse(JSON.stringify(threadRes.data || threadRes))
    }
  } catch (e) {
    ElMessage.error('回复失败')
  }
}

const fetchPreview = async () => {
  if (!props.noteId) return
  initialLoading.value = true
  try {
    const res = await listComments(noteId.value, 1, 3)
    const data = res.data || res
    previewComments.value = [...(data.list || [])]
    totalComments.value = data.total || 0
  } catch (e) {
  } finally {
    initialLoading.value = false
  }
}

watch(() => props.noteId, () => { closeOverlays(); fetchPreview() }, { immediate: true })

onMounted(() => { fetchPreview() })

const focusWriteInput = async () => {
  if (!(await ensureLogin('发表评论'))) return
  showWriteInput.value = true
}

const handleSubmitComment = async (content) => {
  if (!(await ensureLogin('发表评论'))) return
  try {
    await createComment({ noteId: noteId.value, content })
    ElMessage.success('评论成功')
    showWriteInput.value = false
    await fetchPreview()
    writeInputRef.value?.clear()
  } catch (e) {
    writeInputRef.value?.clear()
    ElMessage.error('评论失败')
  }
}

const openModal = () => {
  cacheStore.setNoteId(noteId.value)
  showModal.value = true
}

const onCommentAdded = () => { fetchPreview() }

// 核心：子组件自己读路由参数，预加载数据后显示弹窗
const handleFocusFromRoute = async (newVal) => {
  console.log(`[CommentSection] handleFocusFromRoute=${newVal}, focusLocked=${focusLocked.value}, modalRef=${modalRef.value ? '有' : '无'}`)
  if (!newVal || focusLocked.value) return
  focusLocked.value = true
  try {
    // 先预加载评论数据，避免弹窗显示"暂无评论"闪烁
    if (modalRef.value) {
      console.log(`[CommentSection] 预加载评论数据...`)
      await modalRef.value.prepare()
      console.log(`[CommentSection] 数据加载完成`)
    }
    console.log(`[CommentSection] 打开弹窗`)
    showModal.value = true
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 300))
    console.log(`[CommentSection] 调用 modalRef.focusOnComment(${newVal})`)
    modalRef.value?.focusOnComment(Number(newVal))
  } catch (e) {
    console.error('[CommentSection] 自动聚焦评论失败:', e)
  } finally {
    setTimeout(() => { focusLocked.value = false }, 3000)
  }
}

onMounted(() => {
  fetchPreview()
  const focusId = route.query.focusComment
  console.log(`[CommentSection] onMounted focusId=${focusId}, modalRef=${modalRef.value ? '有' : '无'}`)
  if (focusId) {
    handleFocusFromRoute(focusId)
  }
})

// 被 keep-alive 缓存：离开页面时收掉所有弹窗，回来时不该看见上一次的弹窗
onDeactivated(() => { closeOverlays() })

// 监听路由变化（非首次加载）
watch(() => route.query.focusComment, (newVal, oldVal) => {
  console.log(`[CommentSection] watch路由变化: ${oldVal} → ${newVal}`)
  if (newVal && newVal !== oldVal) {
    handleFocusFromRoute(newVal)
  }
})

defineExpose({
  refresh: fetchPreview,
  resetFocus: () => { focusLocked.value = false },
  focusOnComment: (commentId) => {
    if (!commentId || focusLocked.value) return
    focusLocked.value = true
    showModal.value = true
    nextTick().then(async () => {
      await new Promise(resolve => setTimeout(resolve, 600))
      modalRef.value?.focusOnComment(commentId)
      setTimeout(() => { focusLocked.value = false }, 3000)
    })
  }
})
</script>

<style scoped lang="scss">
.comment-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e5e7eb;
  .preview-area .preview-comments .preview-card {
    background: #fff;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
    padding: 12px 16px;
    margin-bottom: 10px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    &:hover { box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04); }
  }
}
.comment-actions-bar {
  margin-top: 12px;
  .write-comment {
    padding: 10px 14px;
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.3s;
    &:hover { border-color: #d1d5db; }
    .write-placeholder { font-size: 14px; color: #9ca3af; }
  }
  .view-all-btn {
    margin-top: 10px;
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    border-radius: 8px;
    font-weight: 500;
    padding: 6px 16px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    &:hover { border-color: #409eff; color: #409eff; transform: translateY(-2px); }
    &:active { transform: translateY(0); }
  }
}
.preview-thread-body { min-height: 200px; max-height: 50vh; overflow-y: auto; }
</style>
