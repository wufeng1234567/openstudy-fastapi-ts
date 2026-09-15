<template>
  <div class="my-notes-page">
    <PageHeader title="我的笔记" :total="total" unit="篇" itemName="笔记" placeholder="搜索笔记..." v-model="searchKeyword"
      @search="handleSearch" @refresh="handleRefresh">
      <template #extra>
        <el-button v-if="notesList.length > 0" class="delete-all-btn" @click="handleDeleteAll">
          <el-icon>
            <Delete />
          </el-icon>
          删除全部
        </el-button>
        <el-button class="write-btn" @click="goEditor()">
          <el-icon>
            <Edit />
          </el-icon>
          写笔记
        </el-button>
      </template>
    </PageHeader>

    <div v-if="currentBankName" class="bank-filter-tag">
      <el-tag type="warning" closable @close="clearBankFilter">
        来自题库：{{ currentBankName }}
      </el-tag>
    </div>

    <div class="filter-bar">
      <div class="filter-row">
        <span class="filter-label">分类：</span>
        <div class="category-chips">
          <el-tag v-for="cat in categoryList" :key="cat.id" :type="selectedCategoryId === cat.id ? 'primary' : 'info'"
            class="category-chip" @click="selectCategory(cat.id)">
            {{ cat.name }}
          </el-tag>
          <el-tag :type="selectedCategoryId === null ? 'primary' : 'info'" class="category-chip"
            @click="selectCategory(null)">
            全部
          </el-tag>
        </div>
      </div>
      <div class="filter-row">
        <span class="filter-label">题库：</span>
        <el-select v-model="selectedBankId" placeholder="全部题库" clearable class="bank-select" @change="handleBankChange">
          <el-option v-for="bank in questionBankList" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
        </el-select>
      </div>
    </div>

    <div v-loading="loading" class="notes-list">
      <div v-if="notesList.length === 0 && !loading" class="empty-state">
        <el-empty description="暂无笔记" />
      </div>
      <div v-for="note in notesList" :key="note.noteId" class="note-card" @click="goDetail(note.noteId)">
        <div class="note-card-header">
          <h3 class="note-title">{{ note.title }}</h3>
          <el-tag v-if="note.isPublic === 0" type="info" size="small">私有</el-tag>
          <el-tag v-else type="success" size="small">公开</el-tag>
        </div>
        <p class="note-summary">{{ getSummary(note.markdownContent) }}</p>
        <div class="note-meta">
          <span class="meta-item">
            <el-icon>
              <Calendar />
            </el-icon>
            {{ formatTime(note.createTime) }}
          </span>
          <span class="meta-item" v-if="note.wordCount">
            <el-icon>
              <Document />
            </el-icon>
            {{ note.wordCount }} 字
          </span>
        </div>
        <div v-if="note.tags" class="note-tags">
          <el-tag v-for="tag in getTagList(note.tags).slice(0, 3)" :key="tag" size="small" class="tag-item">
            {{ tag }}
          </el-tag>
        </div>
        <div class="note-actions" @click.stop>
          <el-button text size="small" @click="goEditor(note.noteId)">
            <el-icon>
              <Edit />
            </el-icon>
            编辑
          </el-button>
          <el-button text size="small" class="delete-btn" @click="handleDelete(note.noteId, note.title)">
            <el-icon>
              <Delete />
            </el-icon>
            删除
          </el-button>
        </div>
      </div>
    </div>

    <div v-if="total > 0" class="pagination">
      <el-pagination v-model:current-page="pageNum" :page-size="pageSize" :total="total" layout="prev, pager, next"
        @current-change="handlePageChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyNotes' })
import { ref, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Calendar, Document, Delete } from '@element-plus/icons-vue'
import PageHeader from '@/components/PageHeader/index.vue'
import { listNote } from '@/api/notes/note'
import { delNote, batchDelNote } from '@/api/notes/note'
import { getAllNoteCategory } from '@/api/noteCategory/noteCategory'
import { getNoteQuestionBanksByBankId } from '@/api/noteQuestionBank/noteQuestionBank'
import { getQuestionBank } from '@/api/questionBank/questionBank'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import useUserStore from '@/store/modules/user'

interface NoteItem {
  id: number | string
  title: string
  markdownContent?: string
  isPublic?: number
  createTime?: string
  wordCount?: number
  tags?: string | string[]
  [key: string]: any
}

interface CategoryItem {
  id: number | string
  name: string
  [key: string]: any
}

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const loading = ref(false)
const notesList = ref<NoteItem[]>([])
const categoryList = ref<CategoryItem[]>([])
const questionBankList = ref<any[]>([])
const selectedCategoryId = ref<number | string | null>(null)
const selectedBankId = ref<number | string | null>(null)
const searchKeyword = ref('')
const pageNum = ref(1)
const pageSize = ref(12)
const total = ref(0)
const currentBankName = ref('')
const bankFilteredNoteIds = ref<(number | string)[]>([])

const fetchNotes = async () => {
  loading.value = true
  try {
    if (selectedBankId.value && bankFilteredNoteIds.value.length > 0) {
      const query: any = {
        userId: userStore.id,
        pageNum: 1,
        pageSize: 1000
      }

      if (selectedCategoryId.value) {
        query.categoryId = selectedCategoryId.value
      }

      if (searchKeyword.value.trim()) {
        query.title = searchKeyword.value.trim()
      }

      const res: any = await listNote(query)
      if (res.code === 200) {
        let notes: NoteItem[] = res.rows || []
        notes = notes.filter((n: NoteItem) => bankFilteredNoteIds.value.includes(n.id))
        total.value = notes.length
        notesList.value = notes
      }
    } else {
      const query: any = {
        userId: userStore.id,
        pageNum: pageNum.value,
        pageSize: pageSize.value
      }

      if (selectedCategoryId.value) {
        query.categoryId = selectedCategoryId.value
      }

      if (searchKeyword.value.trim()) {
        query.title = searchKeyword.value.trim()
      }

      const res: any = await listNote(query)
      if (res.code === 200) {
        let notes: NoteItem[] = res.rows || []
        total.value = res.total || 0
        notesList.value = notes
      }
    }
  } catch (error) {
    ElMessage.error('获取笔记失败')
  } finally {
    loading.value = false
  }
}

const fetchCategories = async () => {
  try {
    const res: any = await getAllNoteCategory({ userId: userStore.id })
    if (res.code === 200) {
      categoryList.value = res.data || []
    }
  } catch (error) {
  }
}

const fetchQuestionBanks = async () => {
  try {
    const res: any = await listMyQuestionBank()
    if (res.code === 200) {
      questionBankList.value = res.data || []
    }
  } catch (error) {
  }
}

const fetchBankNotes = async (bankId: number | string) => {
  try {
    const res: any = await getNoteQuestionBanksByBankId(bankId)
    if (res.code === 200 && res.data) {
      bankFilteredNoteIds.value = res.data.map((item: any) => item.noteId) || []
    } else {
      bankFilteredNoteIds.value = []
    }
  } catch (error) {
    bankFilteredNoteIds.value = []
  }
}

const fetchBankName = async (bankId: number | string) => {
  try {
    const res: any = await getQuestionBank(bankId)
    if (res.code === 200 && res.data) {
      currentBankName.value = res.data.bankName || ''
    }
  } catch (error) {
  }
}

const selectCategory = (categoryId: number | string | null) => {
  selectedCategoryId.value = categoryId
  pageNum.value = 1
  fetchNotes()
}

const handleBankChange = async (bankId: number | string | null) => {
  selectedBankId.value = bankId
  pageNum.value = 1
  if (bankId) {
    await fetchBankNotes(bankId)
  } else {
    bankFilteredNoteIds.value = []
  }
  fetchNotes()
}

const clearBankFilter = () => {
  router.replace({ path: '/front/myQuestion/myNotes' })
  selectedBankId.value = null
  currentBankName.value = ''
  bankFilteredNoteIds.value = []
  fetchNotes()
}

const handleSearch = () => {
  pageNum.value = 1
  fetchNotes()
}

const handleRefresh = () => {
  searchKeyword.value = ''
  selectedCategoryId.value = null
  selectedBankId.value = null
  currentBankName.value = ''
  bankFilteredNoteIds.value = []
  pageNum.value = 1
  fetchNotes()
}

const handlePageChange = () => {
  fetchNotes()
}

const getSummary = (content?: string) => {
  if (!content) return ''
  return content.replace(/[#*`\[\]]/g, '').substring(0, 100) + '...'
}

const getTagList = (tags: string | string[]) => {
  if (!tags) return []
  if (typeof tags === 'string') {
    return tags.split(',').filter((t: string) => t.trim())
  }
  return tags
}

const formatTime = (time?: string) => {
  if (!time) return ''
  const date = new Date(time)
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

const goEditor = (noteId?: number | string) => {
  if (noteId) {
    router.push({ path: '/front/notes/editor', query: { id: noteId } })
  } else {
    const bankId = selectedBankId.value || route.query.bankId
    router.push({ path: '/front/notes/editor', query: bankId ? { bankId } : {} })
  }
}

const goDetail = (noteId: number | string) => {
  router.push({ path: '/front/notes/detail/' + noteId })
}

const handleDelete = (noteId: number | string, title: string) => {
  ElMessageBox.confirm(`确定删除笔记「${title}」吗？删除后无法恢复。`, '确认删除', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      const res: any = await delNote(noteId)
      if (res.code === 200) {
        ElMessage.success('删除成功')
        fetchNotes()
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => { })
}

const handleDeleteAll = () => {
  if (notesList.value.length === 0) return
  ElMessageBox.confirm(`确定删除全部 ${total.value} 篇笔记吗？删除后无法恢复。`, '删除全部笔记', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      const allIds = notesList.value.map((n: NoteItem) => n.id)
      const res: any = await batchDelNote(allIds)
      if (res.code === 200) {
        ElMessage.success(`成功删除 ${allIds.length} 篇笔记`)
        pageNum.value = 1
        fetchNotes()
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (error) {
      ElMessage.error('删除全部失败')
    }
  }).catch(() => { })
}

onMounted(async () => {
  fetchCategories()
  fetchQuestionBanks()
  if (route.query.bankId) {
    selectedBankId.value = Number(route.query.bankId)
    await fetchBankNotes(route.query.bankId as string)
    await fetchBankName(route.query.bankId as string)
  }
  fetchNotes()
})

watch(() => route.query.bankId, async (newBankId) => {
  if (newBankId) {
    selectedBankId.value = Number(newBankId)
    await fetchBankNotes(newBankId as string)
    await fetchBankName(newBankId as string)
  } else {
    selectedBankId.value = null
    currentBankName.value = ''
    bankFilteredNoteIds.value = []
  }
  fetchNotes()
})
</script>

<style scoped lang="scss">
.my-notes-page {
  .bank-filter-tag {
    margin-bottom: 16px;
  }

  .filter-bar {
    background: #f9fafb;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 20px;

    .filter-row {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;

      &:not(:last-child) {
        margin-bottom: 12px;
      }

      .filter-label {
        font-size: 14px;
        color: #6b7280;
        font-weight: 500;
      }

      .category-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;

        .category-chip {
          cursor: pointer;
          transition: all 0.2s;

          &:hover {
            transform: translateY(-1px);
          }
        }
      }

      .bank-select {
        width: 180px;

        :deep(.el-input__wrapper) {
          border-radius: 8px;
          box-shadow: 0 0 0 1px #e5e7eb;

          &:hover {
            box-shadow: 0 0 0 1px #d1d5db;
          }
        }
      }
    }
  }

  .notes-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    min-height: 200px;
  }

  .empty-state {
    grid-column: 1 / -1;
    padding: 60px 0;
  }

  .note-card {
    background: white;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    &:hover {
      border-color: #d1d5db;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      transform: translateY(-2px);
    }

    .note-card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;

      .note-title {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
        color: #1f2937;
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .note-summary {
      margin: 0 0 12px 0;
      font-size: 13px;
      color: #6b7280;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .note-meta {
      display: flex;
      gap: 16px;
      margin-bottom: 12px;

      .meta-item {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: #9ca3af;

        .el-icon {
          font-size: 14px;
        }
      }
    }

    .note-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 12px;

      .tag-item {
        font-size: 12px;
      }
    }

    .note-actions {
      border-top: 1px solid #f3f4f6;
      padding-top: 12px;
      margin-top: auto;
      display: flex;
      gap: 8px;

      .delete-btn {
        color: #b45353;

        &:hover {
          color: #9b3a3a;
        }
      }
    }
  }
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

:deep(.delete-all-btn) {
  margin-left: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 500;
  color: #b45353;
  background: #fef2f2;
  border: 1px solid #e5d0d0;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: #fff;
    border-color: #b38080;
    color: #9b3a3a;
    transform: translateY(-2px);
  }

  .el-icon {
    margin-right: 4px;
  }
}

:deep(.write-btn) {
  margin-left: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    border-color: #d1d5db;
    color: #4b5563;
    transform: translateY(-2px);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
  }

  .el-icon {
    margin-right: 4px;
  }
}

@media (max-width: 768px) {
  .my-notes-page {
    .notes-list {
      grid-template-columns: 1fr;
    }
  }
}
</style>
