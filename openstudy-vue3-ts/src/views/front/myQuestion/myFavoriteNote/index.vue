<template>
  <div class="note-favorite-container">
    <div v-if="loading" class="loading-container">
      <el-icon class="is-loading">
        <Loading />
      </el-icon>
      <span>加载中...</span>
    </div>

    <div v-else-if="notes.length === 0" class="empty-container">
      <el-empty description="暂无收藏笔记" />
      <el-button class="go-discover-btn" @click="goToNotes">去发现笔记</el-button>
    </div>

    <div v-else class="notes-list">
      <div v-for="note in notes" :key="note.noteId" class="note-card" @click="goToDetail(note.noteId)">
        <div class="note-header">
          <h3 class="note-title">{{ note.title }}</h3>
          <el-tag size="small" type="info">{{ note.categoryName || '未分类' }}</el-tag>
        </div>
        <div class="note-content" v-html="getPlainText(note.markdownContent)"></div>
        <div class="note-footer">
          <div class="note-meta">
            <span class="author">{{ note.authorName || '匿名用户' }}</span>
            <span class="separator">·</span>
            <span class="time">{{ formatTime(note.createTime) }}</span>
          </div>
          <el-button class="unfavorite-btn" size="small" @click.stop="handleUnfavorite(note.noteId)">取消收藏</el-button>
        </div>
      </div>
    </div>

    <div v-if="total > pageSize" class="pagination-container">
      <el-pagination v-model:current-page="currentPage" :page-size="pageSize" :total="total" layout="prev, pager, next"
        @current-change="handlePageChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMyFavoriteNote' })
import { ref, computed, watch, onMounted } from 'vue'

/** 条数变化时通知外层（供「笔记管理」把计数推到顶栏） */
const emitTotal = defineEmits<{ (e: 'total-change', n: number): void }>()

import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import useUserStore from '@/store/modules/user'
import { listFavoriteNote, deleteFavoriteNoteByUserAndNote } from '@/api/favoriteNote/favoriteNote'

interface FavoriteNoteItem {
  id: number | string
  title: string
  categoryName?: string
  markdownContent?: string
  authorName?: string
  createTime?: string
  [key: string]: any
}

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const notes = ref<FavoriteNoteItem[]>([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

// 条数变化 → 通知外层（「笔记管理」据此更新顶栏计数）
watch(total, (n) => emitTotal('total-change', Number(n) || 0), { immediate: true })

const loadNotes = async () => {
  loading.value = true
  try {
    const response: any = await listFavoriteNote({
      pageNum: currentPage.value,
      pageSize: pageSize.value
    })
    if (response.code === 200) {
      notes.value = response.rows || []
      total.value = response.total || 0
    } else {
      ElMessage.error(response.msg || '获取收藏笔记失败')
    }
  } catch (error) {
    ElMessage.error('获取收藏笔记失败')
  } finally {
    loading.value = false
  }
}

const handleUnfavorite = async (noteId: number | string) => {
  try {
    const userId = userStore.id
    if (!userId) {
      ElMessage.error('用户未登录')
      return
    }
    const response: any = await deleteFavoriteNoteByUserAndNote(userId, noteId)
    if (response.code === 200) {
      ElMessage.success('已取消收藏')
      loadNotes()
    } else {
      ElMessage.error(response.msg || '取消收藏失败')
    }
  } catch (error) {
    ElMessage.error('取消收藏失败')
  }
}

const goToDetail = (noteId: number | string) => {
  router.push(`/front/notes/detail/${noteId}`)
}

const goToNotes = () => {
  router.push('/front/notes/list')
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  loadNotes()
}

const formatTime = (time?: string) => {
  if (!time) return ''
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const getPlainText = (html?: string) => {
  if (!html) return ''
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || ''
}

onMounted(() => {
  loadNotes()
})
</script>

<style scoped lang="scss">
.note-favorite-container {
  padding: 16px;
  min-height: 100%;
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  color: #6b7280;

  .el-icon {
    font-size: 24px;
    margin-bottom: 8px;
  }
}

.empty-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;

  .go-discover-btn {
    margin-top: 16px;
    padding: 8px 20px;
    height: auto;
    min-height: 34px;
    font-size: 14px;
    font-weight: 500;
    color: #6b7280;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-sizing: border-box;

    &:hover {
      border-color: #d1d5db;
      color: #4b5563;
      transform: translateY(-2px);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    }

    &:active {
      transform: translateY(0);
      box-shadow: none;
    }
  }
}

.notes-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.note-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    border-color: #d1d5db;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);
  }

  .note-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;

    .note-title {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: #1f2937;
    }
  }

  .note-content {
    font-size: 14px;
    color: #6b7280;
    line-height: 1.6;
    margin-bottom: 12px;
    max-height: 80px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
  }

  .note-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .note-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: #9ca3af;

      .separator {
        color: #d1d5db;
      }
    }

    .unfavorite-btn {
      padding: 4px 10px;
      height: auto;
      font-size: 12px;
      color: #9ca3af;
      background: transparent;
      border: none;
      border-radius: 4px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        color: #b45353;
        background: #fef2f2;
      }
    }
  }
}

.pagination-container {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
