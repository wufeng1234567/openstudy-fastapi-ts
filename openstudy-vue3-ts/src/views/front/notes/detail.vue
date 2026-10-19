<template>
  <div class="notes-detail-container">
    <div class="header">
      <div class="header-left">
        <el-button @click="goBack" :icon="ArrowLeft" text class="back-btn">
          返回列表
        </el-button>
      </div>
      <h2 class="header-title">{{ noteData.title || '笔记详情' }}</h2>
      <div class="header-right">
        <FavoriteButton type="note" :target-id="noteData.noteId" :initial-collected="noteData.isFavorited" size="small" plain />
        <el-button v-if="noteData.userId === userStore.id" class="edit-btn" :icon="Edit" size="small"
          @click="goEditor(noteData.noteId)">
          编辑
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="content-wrapper">
      <div v-if="error" class="error-container">
        <el-empty description="笔记加载失败" />
        <el-button type="primary" @click="goBack" style="margin-top: 16px;">
          返回列表
        </el-button>
      </div>
      <div v-else-if="noteData.noteId" class="content-card">
        <div class="meta-info">
          <span class="author user-link" @click.stop="goToProfile(noteData.userId)">{{ noteData.authorName || '匿名用户'
            }}</span>
          <span class="separator">·</span>
          <span class="time">{{ formatTime(noteData.createTime) }}</span>
          <template v-if="noteData.tags">
            <span class="separator">·</span>
            <el-tag v-for="(tag, index) in getTagList(noteData.tags)" :key="index" size="small" class="tag-item">
              {{ tag }}
            </el-tag>
          </template>
          <!-- 关联题库：只露前几个，其余收进「+N」弹层 ——
               关联十几个库时，平铺会把整行元信息挤爆 -->
          <template v-if="canManageLinks && linkedBanks.length > 0">
            <span class="separator">·</span>
            <el-tag v-for="bank in visibleBanks" :key="getBankId(bank)" size="small" class="bank-chip"
              :closable="canManageLinks" @close="unlinkBank(getBankId(bank))" @click="goToBank(getBankId(bank))">
              {{ getBankName(bank) }}
            </el-tag>
            <el-popover v-if="hiddenBanks.length > 0" placement="bottom" :width="220" trigger="click">
              <template #reference>
                <el-tag size="small" class="bank-chip bank-chip-more">+{{ hiddenBanks.length }}</el-tag>
              </template>
              <div class="more-banks">
                <div class="more-banks-title">其余 {{ hiddenBanks.length }} 个关联题库</div>
                <div v-for="bank in hiddenBanks" :key="getBankId(bank)" class="more-bank-item"
                  @click="goToBank(getBankId(bank))">
                  <el-icon><Collection /></el-icon>
                  <span class="more-bank-name">{{ getBankName(bank) }}</span>
                  <el-icon class="more-bank-remove" @click.stop="unlinkBank(getBankId(bank))"><Close /></el-icon>
                </div>
              </div>
            </el-popover>
          </template>
          <!-- 关联题目按钮 + popover -->
          <el-popover v-if="canManageLinks && linkedQuestions.length > 0" placement="bottom" :width="440" trigger="click">
            <template #reference>
              <el-button text size="small" class="linked-questions-btn">
                Linked {{ linkedQuestions.length }} questions
              </el-button>
            </template>
            <div class="questions-popover">
              <div class="popover-title">关联题目（{{ linkedQuestions.length }}）</div>
              <div v-for="q in linkedQuestions" :key="q.id || q.questionId" class="question-item">
                <div class="question-info-row">
                  <span class="q-type">{{ getQuestionTypeText(q.questionType) }}</span>
                  <span class="q-text">{{ truncate(getQuestionText(q), 60) }}</span>
                </div>
                <el-button v-if="canManageLinks" text size="small" class="unlink-q-btn"
                  @click="unlinkQuestion(q.id || q.questionId)">
                  取消关联
                </el-button>
              </div>
            </div>
          </el-popover>
          <!-- 复制 / 导出：从顶栏移到此处（右对齐），顶栏留给收藏与编辑 -->
          <div v-if="noteData.noteId" class="title-actions">
            <el-tooltip content="复制全文" placement="top" :show-after="300">
              <el-button class="icon-action-btn" :icon="DocumentCopy" circle @click="copyNote" />
            </el-tooltip>
            <el-tooltip content="导出 Markdown" placement="top" :show-after="300">
              <el-button class="icon-action-btn" :icon="Download" circle @click="exportNote" />
            </el-tooltip>
          </div>
        </div>
        <div class="markdown-content">
          <div class="rendered-content">
            <TiptapEditor v-model="noteHtmlContent" :hideToolbar="true" :disabled="true" placeholder=""
              @preview-image="openImageViewer" />
          </div>
        </div>

        <!-- 图片预览模态框 -->
        <ImageViewer v-model:visible="imageViewerVisible" :src="imageViewerSrc" />

        <!-- 评论区 -->
        <CommentSection v-if="noteData.noteId" :note-id="noteData.noteId" />

        <!-- 上一篇/下一篇导航 -->
        <div class="navigation">
          <el-button v-if="prevNote.noteId" @click="goToNote(prevNote.noteId)" type="text" :icon="ArrowLeft" class="nav-btn">
            上一篇：{{ prevNote.title }}
          </el-button>
          <el-button v-if="nextNote.noteId" @click="goToNote(nextNote.noteId)" type="text" :icon="ArrowRight"
            class="nav-btn next">
            下一篇：{{ nextNote.title }}
          </el-button>
        </div>
      </div>
    </div>

    <!-- 滚动按钮 -->
    <ScrollButton :bottom="40" :right="20" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontNotesDetail' })
import { ref, computed, onMounted, onActivated, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElIcon } from 'element-plus'
import { ArrowLeft, ArrowRight, ArrowUp, Close, Collection, Edit, Download, DocumentCopy } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { getPublicNote, listPublicNotes, recordClick } from '@/api/notes/public'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import useUserStore from '@/store/modules/user'
import { getNoteQuestionBanksByNoteId, removeNoteQuestionBank } from '@/api/noteQuestionBank/noteQuestionBank'
import { getNoteQuestionsByNoteId, deleteNoteQuestion } from '@/api/noteQuestion/noteQuestion'
import { getPlainText, getQuestionTypeText } from '@/utils/questionUtils'
import CommentSection from '@/components/CommentSection/CommentSection.vue'
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'

const cacheStore = useFrontPageCacheStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const loading = ref(false)
const noteData = ref({})
const error = ref(false)
const prevNote = ref({ noteId: '', title: '' })
const nextNote = ref({ noteId: '', title: '' })
const imageViewerVisible = ref(false)
const imageViewerSrc = ref('')
const isFetching = ref(false)  // 防重复请求锁

// 导入知识库功能已移除
let lastClickedNoteId = null

const noteHtmlContent = ref('')

// 关联题库与题目
const linkedBanks = ref<any[]>([])
const linkedQuestions = ref<any[]>([])

// 当前用户是否为笔记作者
const isAuthor = computed(() => {
  return noteData.value && noteData.value.userId && noteData.value.userId === userStore.id
})

/**
 * 谁能维护「笔记-题库/题目」关联：**只有作者本人**。
 *
 * ⚠️ 这里曾经写成 `isAuthor || noteData.isFavorited`，理由是「关联按 user_id 隔离，
 *    收藏者维护自己那一套」。但后端(2026-10 加水平越权防护时)只允许作者读写关联
 *    （`_deny_not_note_owner` → 403「无权操作他人笔记的关联」），前端这套判断就成了
 *    空头支票：收藏者看到可点的题库 chip 和按钮，一进详情页就 403。
 *
 *    用户 2026-10-19 报的「演示用户1 进 user2 的公开笔记 → 加载关联题库失败 → 当前操作没有权限」
 *    正是这条链路。现在让前端与后端同口径：非作者直接不请求、不渲染。
 *    若将来真要放开「收藏者可维护自己那套关联」，得先在后端把 user_id 维度的查询补齐，
 *    前端再跟着放开 —— 不能只改一边。
 */
const canManageLinks = computed(() => !!isAuthor.value)

// 关联题库一多（十几个）就会把元信息行挤爆：默认只露出前几个，其余收进「+N」弹层
const MAX_VISIBLE_BANKS = 3
const visibleBanks = computed(() => linkedBanks.value.slice(0, MAX_VISIBLE_BANKS))
const hiddenBanks = computed(() => linkedBanks.value.slice(MAX_VISIBLE_BANKS))

// 截断文本
const truncate = (text: string, len: number) => {
  if (!text) return ''
  const str = String(text)
  return str.length > len ? str.slice(0, len) + '...' : str
}

// 获取题目展示文本（兼容多种字段名）
const getQuestionText = (q: any) => {
  if (!q) return ''
  const raw = q.questionText || q.content || q.questionContent || ''
  return getPlainText(raw)
}

// 加载关联题库
const loadLinkedBanks = async (noteId: any) => {
  if (!noteId) {
    linkedBanks.value = []
    return
  }
  try {
    const res = await getNoteQuestionBanksByNoteId(noteId)
    if (res.code === 200 && Array.isArray(res.data)) {
      linkedBanks.value = res.data
    } else {
      linkedBanks.value = []
    }
  } catch (e) {
    console.error('加载关联题库失败:', e)
    linkedBanks.value = []
  }
}

// 加载关联题目
const loadLinkedQuestions = async (noteId: any) => {
  if (!noteId) {
    linkedQuestions.value = []
    return
  }
  try {
    const res = await getNoteQuestionsByNoteId(noteId)
    if (res.code === 200 && Array.isArray(res.data)) {
      linkedQuestions.value = res.data
    } else {
      linkedQuestions.value = []
    }
  } catch (e) {
    console.error('加载关联题目失败:', e)
    linkedQuestions.value = []
  }
}

// 取消关联题库（仅作者）
const unlinkBank = async (bankId: any) => {
  if (!canManageLinks.value || !noteData.value.noteId) return
  try {
    const res = await removeNoteQuestionBank(noteData.value.noteId, bankId)
    if (res.code === 200) {
      linkedBanks.value = linkedBanks.value.filter(b => b.questionBankId !== bankId && b.id !== bankId)
      ElMessage.success('已取消关联题库')
    } else {
      ElMessage.error(res.msg || '取消关联失败')
    }
  } catch (e) {
    console.error('取消关联题库失败:', e)
    ElMessage.error('取消关联失败')
  }
}

// 取消关联题目（仅作者）
const unlinkQuestion = async (questionId: any) => {
  if (!canManageLinks.value || !noteData.value.noteId) return
  try {
    const res = await deleteNoteQuestion(noteData.value.noteId, questionId)
    if (res.code === 200) {
      linkedQuestions.value = linkedQuestions.value.filter(q => q.id !== questionId && q.questionId !== questionId)
      ElMessage.success('已取消关联题目')
    } else {
      ElMessage.error(res.msg || '取消关联失败')
    }
  } catch (e) {
    console.error('取消关联题目失败:', e)
    ElMessage.error('取消关联失败')
  }
}

// 跳转到题库
const goToBank = (bankId: any) => {
  if (!bankId) return
  router.push({ path: '/front/studio/create', query: { bankId } })
}

// 获取题库名称（兼容字段）
const getBankName = (bank: any) => {
  return bank.bankName || bank.name || `题库${bank.bankId || bank.bankId}`
}

// 获取题库 ID（兼容字段）
const getBankId = (bank: any) => {
  return bank.questionBankId || bank.bankId || bank.bankId
}

watch(() => noteData.value.markdownContent, (newMd) => {
  noteHtmlContent.value = newMd ? marked.parse(newMd) : ''
}, { immediate: true })

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getTagList = (tags) => {
  if (!tags) return []
  if (typeof tags === 'string') {
    return tags.split(',').filter(t => t.trim())
  }
  return tags
}

const exportNote = () => {
  const title = noteData.value.title || '笔记'
  const mdContent = noteData.value.markdownContent || ''
  const content = `# ${title}\n\n${mdContent}`
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.md`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ElMessage.success('笔记已导出为 Markdown 文件')
}

const copyNote = async () => {
  const title = noteData.value.title || '笔记'
  const mdContent = noteData.value.markdownContent || ''
  const content = `# ${title}\n\n${mdContent}`
  try {
    await navigator.clipboard.writeText(content)
    ElMessage.success('全文已复制到剪贴板')
  } catch (err) {
    ElMessage.error('复制失败，请手动复制')
  }
}

// 图片预览
const openImageViewer = (src: string) => {
  imageViewerSrc.value = src
  imageViewerVisible.value = true
}

const fetchNoteDetail = async () => {
  if (isFetching.value) return
  isFetching.value = true

  const id = route.params.id
  if (!id) {
    error.value = true
    isFetching.value = false
    return
  }

  // 如果数据已经是最新的ID，跳过
  if (noteData.value.noteId === Number(id)) {
    isFetching.value = false
    return
  }

  loading.value = true
  error.value = false
  // 重置关联数据
  linkedBanks.value = []
  linkedQuestions.value = []
  try {
    const res = await getPublicNote(id)
    noteData.value = res.data || {}
    if (!noteData.value.noteId) {
      error.value = true
    } else {
      await fetchNavigationNotes(id)
      // 关联题库 / 题目属于作者的私人整理信息，仅作者本人加载
      if (canManageLinks.value) {
        await Promise.all([
          loadLinkedBanks(id),
          loadLinkedQuestions(id)
        ])
      }
    }
  } catch (err) {
    console.error(err)
    error.value = true
  } finally {
    loading.value = false
    isFetching.value = false
  }
}

const fetchNavigationNotes = async (currentId) => {
  try {
    const res = await listPublicNotes({ pageSize: 100 })
    const notes = res.rows || []
    const numericId = Number(currentId)
    const currentIndex = notes.findIndex(note => Number(note.noteId) === numericId)

    if (currentIndex > 0) {
      prevNote.value = notes[currentIndex - 1]
    } else {
      prevNote.value = { noteId: '', title: '' }
    }
    if (currentIndex < notes.length - 1) {
      nextNote.value = notes[currentIndex + 1]
    } else {
      nextNote.value = { noteId: '', title: '' }
    }
  } catch (error) {
    console.error('获取导航笔记失败:', error)
  }
}

const goBack = () => {
  router.push('/front/notes/list')
}

const goToProfile = (userId) => {
  if (!userId) return
  router.push(`/front/profile/${userId}`)
}

const goEditor = (id) => {
  cacheStore.setLastVisited('notes', `editor?id=${id}`)
  router.push(`/front/notes/editor?id=${id}`)
}

const goToNote = (id) => {
  cacheStore.setLastVisited('notes', `detail/${id}`)
  router.push(`/front/notes/detail/${id}`)
}

const onMountedNoteId = ref(null)

onMounted(async () => {
  const noteId = route.params.id
  onMountedNoteId.value = noteId
  lastClickedNoteId = noteId
  // 游客不需要记录点击次数
  if (!userStore.isGuest) {
    recordClick(noteId).catch(() => { })
  }
  await fetchNoteDetail()
})

// 监听路由参数变化，记录点击
watch(() => route.params.id, (newId, oldId) => {
  // 游客不需要记录点击次数
  if (!userStore.isGuest && newId && newId !== oldId) {
    lastClickedNoteId = newId
    recordClick(newId).catch(() => { })
  }
})

onActivated(async () => {
  if (!route.path.startsWith('/front/notes')) return

  const newId = route.params.id
  if (!newId) return
  if (isFetching.value) return

  if (noteData.value.noteId !== Number(newId)) {
    prevNote.value = { id: '', title: '' }
    nextNote.value = { id: '', title: '' }
    await fetchNoteDetail()
    // 游客不需要记录点击次数
    if (!userStore.isGuest && lastClickedNoteId !== newId) {
      lastClickedNoteId = newId
      recordClick(newId).catch(() => { })
    }
  } else if (!userStore.isGuest && lastClickedNoteId !== newId) {
    lastClickedNoteId = newId
    recordClick(newId).catch(() => { })
  }
})
</script>

<style lang="scss">
.notes-detail-container {
  padding: 24px;

  .header {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    align-items: center;
    margin-bottom: 24px;
  }

  .header-left {
    justify-self: start;
  }

  .back-btn {
    width: fit-content;
    border-radius: 8px;
    font-weight: 500;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover {
      color: #4b5563;
      background: #f3f4f6;
    }
  }

  .header-title {
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    color: #1f2937;
    text-align: center;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .header-right {
    justify-self: end;
    display: flex;
    gap: 8px;

    .export-btn,
    .copy-btn,
    .import-btn,
    .edit-btn {
      border-radius: 8px;
      font-weight: 500;
      padding: 7px 16px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        background: #fff;
        border-color: #d1d5db;
        color: #4b5563;
        transform: translateY(-2px);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      }

      &:active {
        transform: translateY(0);
      }
    }
  }

  .content-wrapper {
    min-height: 400px;

    .error-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 400px;

      .el-button {
        border-radius: 8px;
        font-weight: 500;
        padding: 8px 20px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        background: #fff;
        border: 1px solid #e5e7eb;
        color: #6b7280;

        &:hover {
          border-color: #409eff;
          color: #409eff;
          transform: translateY(-2px);
        }

        &:active {
          transform: translateY(0);
        }
      }
    }
  }

  .content-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    padding: 24px;

    .meta-info {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      padding-bottom: 16px;
      margin-bottom: 16px;
      border-bottom: 1px solid #f3f4f6;
      font-size: 13px;
      color: #6b7280;

      /* 复制 / 导出图标：推到元信息行最右侧，与左侧文字拉开距离 */
      .title-actions {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-left: auto;
        flex-shrink: 0;
      }

      .icon-action-btn {
        width: 28px;
        height: 28px;
        border: 1px solid #e5e7eb;
        background: #fff;
        color: #9ca3af;
        transition: all 0.2s ease;

        &:hover {
          color: #4b5563;
          border-color: #d1d5db;
          background: #f9fafb;
        }

        &:active {
          transform: scale(0.96);
        }
      }

      .separator {
        color: #d1d5db;
      }

      .author {
        font-weight: 500;
      }

      .tag-item {
        border-radius: 4px;
        background: #fefce8;
        border-color: #e5e0c0;
        color: #947a4a;
      }

      .bank-chip {
        border-radius: 4px;
        background: #fefce8;
        border-color: #e5e0c0;
        color: #947a4a;
        cursor: pointer;
        transition: all 0.2s ease;

        &:hover {
          background: #fef9c3;
          border-color: #ca8a04;
          color: #854d0e;
        }
      }

      /* 「+N」折叠标签：与题库 chip 同色系，但用虚线和略深的字重暗示「这只是入口」 */
      .bank-chip-more {
        border-style: dashed;
        font-weight: 600;
      }

      .more-banks {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }

      .more-banks-title {
        font-size: 12px;
        color: #9ca3af;
        padding: 2px 4px 6px;
      }

      .more-bank-item {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 8px;
        border-radius: 6px;
        font-size: 13px;
        color: #4b5563;
        cursor: pointer;
        transition: background 0.15s ease;

        &:hover {
          background: #f3f4f6;
        }
      }

      .more-bank-name {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .more-bank-remove {
        flex-shrink: 0;
        color: #c0c4cc;
        font-size: 13px;

        &:hover {
          color: #f56c6c;
        }
      }

      .linked-questions-btn {
        color: #2563eb;
        padding: 2px 8px;
        font-size: 13px;
        border: 1px solid #bfdbfe;
        border-radius: 6px;
        background: #eff6ff;
        transition: all 0.2s ease;

        &:hover {
          background: #dbeafe;
          border-color: #60a5fa;
          color: #1d4ed8;
        }
      }
    }

    .markdown-content {
      line-height: 1.7;
    }

    .rendered-content {
      :deep(.editor-toolbar) {
        display: none;
      }
    }

    .navigation {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 32px;
      padding-top: 24px;
      border-top: 1px solid #f3f4f6;

      .nav-btn {
        color: #6b7280;
        font-size: 14px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        max-width: 45%;
        text-align: left;

        &:hover {
          color: #409eff;
          background: #f3f4f6;
        }

        &.next {
          text-align: right;
        }
      }
    }
  }

  .back-to-top {
    .el-button {
      border-radius: 50%;
      width: 40px;
      height: 40px;
      padding: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #fff;
      border: 1px solid #e5e7eb;
      color: #6b7280;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);

      &:hover {
        border-color: #409eff;
        color: #409eff;
        transform: translateY(-2px);
      }
    }
  }
}

.el-tag--info {
  background: #f3f4f6;
  border-color: #e5e7eb;
  color: #6b7280;
}

.kb-dialog-body {
  min-height: 200px;
}

.kb-desc {
  color: #6b7280;
  font-size: 13px;
}

.kb-table {
  border-radius: 8px;
  overflow: hidden;

  .el-table__header th {
    background: #f8f9fa;
    color: #6b7280;
    font-weight: 500;
    border-bottom: 1px solid #e5e7eb;
  }

  .el-table__body td {
    color: #1f2937;
    border-bottom: 1px solid #f3f4f6;
  }

  .el-table__row:hover>td {
    background: #fafafa;
  }
}

.kb-select-btn {
  border-radius: 6px;
  font-weight: 500;
  padding: 5px 12px;
  color: #6b7280;
  background: #fff;
  border: 1px solid #e5e7eb;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: #fff;
    border-color: #409eff;
    color: #409eff;
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
}

.kb-create-btn {
  border-radius: 8px;
  font-weight: 500;
  padding: 8px 20px;
  color: #6b7280;
  background: #fff;
  border: 1px solid #e5e7eb;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: #fff;
    border-color: #409eff;
    color: #409eff;
    transform: translateY(-2px);
  }

  &:active {
    transform: translateY(0);
  }
}

.kb-list-container {
  .kb-list-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 12px;

    .kb-new-btn {
      border-radius: 6px;
      font-weight: 500;
      padding: 6px 12px;
      color: #6b7280;
      background: #fff;
      border: 1px solid #e5e7eb;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        background: #fff;
        border-color: #409eff;
        color: #409eff;
        transform: translateY(-1px);
      }

      &:active {
        transform: translateY(0);
      }

      .el-icon {
        margin-right: 4px;
      }
    }
  }
}

.kb-create-form {
  padding: 8px 0;

  .form-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;

    .form-title {
      font-size: 16px;
      font-weight: 600;
      color: #1f2937;
    }

    .form-close-btn {
      color: #9ca3af;
      padding: 4px;
      transition: color 0.3s;

      &:hover {
        color: #6b7280;
      }
    }
  }

  .kb-form {
    :deep(.el-form-item) {
      margin-bottom: 16px;
    }

    :deep(.el-form-item__label) {
      color: #6b7280;
      font-weight: 500;
      padding-bottom: 4px;
    }

    :deep(.el-input__wrapper),
    :deep(.el-textarea__inner) {
      border-radius: 8px;
      box-shadow: none;
      border: 1px solid #e5e7eb;
      transition: border-color 0.3s;

      &:hover,
      &:focus {
        border-color: #409eff;
      }
    }

    .form-actions {
      margin-top: 24px;
      margin-bottom: 0;
      display: flex;
      justify-content: flex-end;
      gap: 12px;

      .kb-cancel-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 8px 20px;
        color: #6b7280;
        background: #fff;
        border: 1px solid #e5e7eb;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          background: #fff;
          border-color: #409eff;
          color: #409eff;
          transform: translateY(-2px);
        }
      }

      .kb-confirm-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 8px 20px;
        color: #6b7280;
        background: #fff;
        border: 1px solid #e5e7eb;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

        &:hover {
          background: #fff;
          border-color: #409eff;
          color: #409eff;
          transform: translateY(-2px);
        }
      }
    }
  }
}

.el-tag--success {
  background: #f0f9eb;
  border-color: #e1f3d8;
  color: #67c23a;
}

.el-tag--warning {
  background: #fefce8;
  border-color: #e5e0c0;
  color: #947a4a;
}

.el-tag--danger {
  background: #fef2f2;
  border-color: #e5d0d0;
  color: #b45353;
}

.user-link {
  cursor: pointer;
  transition: all 0.2s ease;
  color: inherit;
  text-decoration: none;
  border-bottom: 1px solid transparent;

  &:hover {
    color: #409eff;
    border-bottom: 1px dashed #409eff;
  }
}

.questions-popover {
  max-height: 360px;
  overflow-y: auto;

  .popover-title {
    font-size: 14px;
    font-weight: 600;
    color: #1f2937;
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid #f3f4f6;
  }

  .question-item {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 0;
    border-bottom: 1px dashed #f3f4f6;

    &:last-child {
      border-bottom: none;
    }

    .question-info-row {
      flex: 1;
      min-width: 0;
      display: flex;
      align-items: flex-start;
      gap: 6px;

      .q-type {
        flex-shrink: 0;
        font-size: 12px;
        color: #6b7280;
        background: #f3f4f6;
        padding: 1px 6px;
        border-radius: 4px;
        white-space: nowrap;
      }

      .q-text {
        font-size: 13px;
        color: #303133;
        line-height: 1.5;
        word-break: break-word;
      }
    }

    .unlink-q-btn {
      flex-shrink: 0;
      color: #b45353;
      padding: 2px 6px;

      &:hover {
        color: #991b1b;
      }
    }
  }
}
</style>
