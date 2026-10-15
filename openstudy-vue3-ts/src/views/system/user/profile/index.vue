<template>
  <div class="profile-page">
    <div class="profile-layout">
      <!-- 左侧用户信息卡片 -->
      <div class="left-sidebar">
        <div class="user-card">
          <!-- 用户信息区域 -->
          <div class="user-info-section">
            <div class="user-avatar">
              <userAvatar :avatar="state.user.avatar" :user-name="state.user.nickName" :is-self="isSelf" />
            </div>
            <h2 class="user-nickname">{{ state.user.nickName || '未设置昵称' }}</h2>
            <div class="user-meta">
              <span>{{ state.user.userName }}</span>
              <span class="separator">·</span>
              <span>{{ state.user.email || '未设置邮箱' }}</span>
            </div>
          </div>

          <!-- 操作按钮区域 -->
          <div v-if="isSelf" class="user-actions">
            <el-button class="action-btn" size="small" @click="editDialogVisible = true">编辑资料</el-button>
            <el-button class="action-btn" size="small" @click="pwdDialogVisible = true">修改密码</el-button>
          </div>

          <!-- 路由导航区域 -->
          <div v-if="isSelf" class="nav-section">
            <div class="nav-divider"></div>
            <div class="nav-item" :class="{ active: activeTab === 'notes' }" @click="handleNavClick('notes')">
              <el-icon>
                <Document />
              </el-icon>
              <span>我的笔记</span>
            </div>
            <div class="nav-item" :class="{ active: activeTab === 'favorites' }" @click="handleNavClick('favorites')">
              <el-icon>
                <Star />
              </el-icon>
              <span>我的收藏</span>
            </div>
            <div class="nav-item" :class="{ active: activeTab === 'models' }" @click="handleNavClick('models')">
              <el-icon>
                <Setting />
              </el-icon>
              <span>我的模型</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧内容区域 -->
      <div class="right-content">
        <!-- 我的笔记 -->
        <div v-show="activeTab === 'notes'" class="content-section">
          <div class="section-header">
            <h3 class="section-title">{{ isSelf ? '我的笔记' : 'TA 的笔记' }}</h3>
            <div class="section-header-right">
              <el-button v-if="isSelf && selectedNoteIds.length > 0" class="batch-delete-btn" size="small"
                @click="handleBatchDelete">
                批量删除
              </el-button>
              <el-button v-if="isSelf" class="create-btn" @click="goEditor()">+ 写笔记</el-button>
            </div>
          </div>

          <div class="category-tags">
            <div class="category-tags-left">
              <el-tag class="tag-item" :class="{ active: selectedCategoryId === null }"
                @click="filterByCategory(null)">全部</el-tag>
              <el-tag v-for="cat in categoryList" :key="cat.id" class="tag-item"
                :class="{ active: selectedCategoryId === cat.id }" @click="filterByCategory(cat.id)">{{ cat.name
                }}</el-tag>
            </div>
            <div class="select-all-row" v-if="isSelf && paginatedNotes.length > 0">
              <el-checkbox :model-value="isAllSelected" @change="handleSelectAll" />
              <span class="select-all-text">全选</span>
            </div>
          </div>

          <div v-loading="loadingNotes" class="note-list">
            <div v-for="note in paginatedNotes" :key="note.noteId" class="note-item">
              <div class="note-check">
                <el-checkbox v-if="isSelf" v-model="selectedNoteIds" :label="note.noteId" class="note-checkbox"
                  @click.stop>
                  <template #default />
                </el-checkbox>
              </div>
              <div class="note-main">
                <div class="note-title" @click="goToDetail(note.noteId)">{{ note.title }}</div>
                <div class="note-meta">
                  <el-tag :type="note.isPublic === 1 ? 'success' : 'info'" size="small" class="visibility-tag">
                    {{ note.isPublic === 1 ? '公开' : '私有' }}
                  </el-tag>
                  <span class="note-time">{{ formatTime(note.createTime) }}</span>
                  <span class="note-actions">
                    <el-button v-if="isSelf" class="edit-btn" :icon="Edit" size="small"
                      @click.stop="goEditor(note.noteId)">编辑</el-button>
                    <el-button v-if="isSelf" class="delete-btn" size="small"
                      @click.stop="handleDeleteNote(note.noteId, note.title)">
                      <el-icon>
                        <Delete />
                      </el-icon>
                    </el-button>
                  </span>
                </div>
              </div>
            </div>
            <el-empty v-if="!loadingNotes && paginatedNotes.length === 0" description="还没有笔记" />
          </div>

          <div v-if="total > 0" class="pagination">
            <el-pagination v-model:current-page="pageNum" :page-size="pageSize" :total="total"
              layout="prev, pager, next" @current-change="handlePageChange" />
          </div>
        </div>

        <!-- 我的收藏 -->
        <div v-show="activeTab === 'favorites'" class="content-section">
          <MyFavoriteNote />
        </div>

        <!-- 我的模型 -->
        <div v-show="activeTab === 'models'" class="content-section">
          <aiModelManager />
        </div>
      </div>
    </div>

    <el-dialog v-model="editDialogVisible" title="编辑资料" width="500px" :close-on-click-modal="false">
      <userInfo :user="state.user" @close="editDialogVisible = false" @saved="editDialogVisible = false; fetchUser()" />
    </el-dialog>

    <el-dialog v-model="pwdDialogVisible" title="修改密码" width="500px" :close-on-click-modal="false">
      <resetPwd @close="pwdDialogVisible = false" @saved="pwdDialogVisible = false" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontProfile' })
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Setting, Document, Star, Delete } from '@element-plus/icons-vue'
import userAvatar from './userAvatar'
import userInfo from './userInfo'
import resetPwd from './resetPwd'
import aiModelManager from '@/components/AiModelManager/index.vue'
import MyFavoriteNote from '@/views/front/myQuestion/myFavoriteNote/index.vue'
import { getUserProfile, getFrontUserInfo } from '@/api/system/user'
import { getAllNoteCategory } from '@/api/noteCategory/noteCategory'
import { listNote } from '@/api/notes/note'
import { batchDelNote } from '@/api/notes/note'
import useUserStore from '@/store/modules/user'
import { listPublicNotes } from '@/api/notes/public'


const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const state = reactive({
  user: {}
})

const isSelf = computed(() => {
  return !route.params.userId || Number(route.params.userId) === userStore.id
})

const editDialogVisible = ref(false)
const pwdDialogVisible = ref(false)
const activeTab = ref('notes')

const categoryList = ref([])
const selectedCategoryId = ref(null)
const notesList = ref([])
const loadingNotes = ref(false)
const pageNum = ref(1)
const pageSize = ref(10)
const total = ref(0)
const selectedNoteIds = ref([])

const isAllSelected = computed(() => {
  const pageIds = paginatedNotes.value.map(n => n.id)
  return pageIds.length > 0 && pageIds.every(id => selectedNoteIds.value.includes(id))
})

const handleSelectAll = (checked) => {
  const pageIds = paginatedNotes.value.map(n => n.id)
  if (checked) {
    const existing = new Set(selectedNoteIds.value)
    pageIds.forEach(id => existing.add(id))
    selectedNoteIds.value = Array.from(existing)
  } else {
    const exclude = new Set(pageIds)
    selectedNoteIds.value = selectedNoteIds.value.filter(id => !exclude.has(id))
  }
}

const filteredNotes = computed(() => {
  if (selectedCategoryId.value === null) return notesList.value
  return notesList.value.filter(note => note.categoryId === selectedCategoryId.value)
})

const paginatedNotes = computed(() => {
  const start = (pageNum.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredNotes.value.slice(start, end)
})

const formatTime = (time) => {
  if (!time) return ''
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const handleNavClick = (tab) => {
  activeTab.value = tab
}

const goEditor = (id) => {
  if (id) {
    router.push(`/front/notes/editor?id=${id}`)
  } else {
    router.push('/front/notes/editor')
  }
}

const goToDetail = (id) => {
  router.push(`/front/notes/detail/${id}`)
}

const filterByCategory = (id) => {
  selectedCategoryId.value = id
  pageNum.value = 1
}

const handlePageChange = (page) => {
  pageNum.value = page
}

const fetchCategories = async () => {
  try {
    const res = await getAllNoteCategory({ userId: state.user.id || userStore.id })
    if (res.code === 200) {
      categoryList.value = res.data || []
    }
  } catch (error) {
    console.error('获取分类失败:', error)
  }
}

const fetchNotes = async () => {
  loadingNotes.value = true
  try {
    const userId = route.params.userId

    if (userId && !isSelf.value) {
      const res = await listPublicNotes({
        userId: Number(userId),
        pageNum: 1,
        pageSize: 999
      })
      if (res.code === 200) {
        notesList.value = res.rows || []
        total.value = res.total || 0
      }
    } else {
      const res = await listNote({
        userId: state.user.id || userStore.id,
        pageNum: 1,
        pageSize: 999
      })
      if (res.code === 200) {
        notesList.value = res.rows || []
        total.value = res.total || 0
      }
    }
  } catch (error) {
    ElMessage.error('获取笔记列表失败')
    console.error(error)
  } finally {
    loadingNotes.value = false
  }
}

const handleDeleteNote = (noteId, title) => {
  ElMessageBox.confirm(`确定删除笔记「${title}」吗？删除后无法恢复。`, '确认删除', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      const res = await batchDelNote([noteId])
      if (res.code === 200) {
        ElMessage.success('删除成功')
        selectedNoteIds.value = selectedNoteIds.value.filter(id => id !== noteId)
        fetchNotes()
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => { })
}

const handleBatchDelete = () => {
  if (selectedNoteIds.value.length === 0) return
  ElMessageBox.confirm(`确定删除选中的 ${selectedNoteIds.value.length} 篇笔记吗？删除后无法恢复。`, '批量删除', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      const res = await batchDelNote(selectedNoteIds.value)
      if (res.code === 200) {
        ElMessage.success(`成功删除 ${selectedNoteIds.value.length} 篇笔记`)
        selectedNoteIds.value = []
        fetchNotes()
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (error) {
      ElMessage.error('批量删除失败')
    }
  }).catch(() => { })
}

const fetchUser = () => {
  const userId = route.params.userId
  const promise = userId
    ? getFrontUserInfo(Number(userId))
    : getUserProfile()

  promise.then(response => {
    state.user = response.data?.user || response.data || {}
    fetchCategories()
    fetchNotes()
  }).catch(() => {
    ElMessage.error('获取用户信息失败')
  })
}

onMounted(() => {
  fetchUser()
})

watch(() => route.params.userId, () => {
  fetchUser()
})
</script>

<style lang="scss">
.profile-page {
  padding: 0;
}

.profile-layout {
  display: flex;
  gap: 20px;
  min-height: 100%;
}

.left-sidebar {
  width: 280px;
  flex-shrink: 0;
}

.user-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
  position: sticky;
  top: 16px;
}

.user-info-section {
  text-align: center;
  width: 100%;
  max-width: 200px;
  margin: 0 auto;

  .user-avatar {
    display: block;
    margin-bottom: 16px;
    text-align: center;
  }

  .user-nickname {
    margin: 0 0 8px;
    font-size: 18px;
    font-weight: 600;
    color: #1f2937;
  }

  .user-meta {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: 4px;
    font-size: 12px;
    color: #9ca3af;
    margin-bottom: 16px;

    .separator {
      color: #d1d5db;
    }
  }
}

.user-actions {
  display: flex;
  flex-direction: row;
  justify-content: center;
  gap: 12px;
  width: 100%;
  box-sizing: border-box;
  margin-bottom: 16px;

  .action-btn {
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 500;
    font-size: 14px;
    color: #6b7280;
    background: #fff;
    border: 1px solid #e5e7eb;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    height: auto;
    min-height: 34px;
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

.nav-section {
  margin-top: 16px;

  .nav-divider {
    height: 1px;
    background: #e5e7eb;
    margin-bottom: 16px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    color: #6b7280;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    margin-bottom: 4px;

    &:hover {
      color: #374151;
      background: #f9fafb;
    }

    &.active {
      color: #1f2937;
      background: #f3f4f6;
      font-weight: 600;
    }

    .el-icon {
      font-size: 16px;
    }
  }
}

.right-content {
  flex: 1;
  min-width: 0;
}

.content-section {
  background: #fff;
  border-top: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;

  .section-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: #1f2937;
  }

  .create-btn {
    // 往右边移动
    border-radius: 8px;
    font-weight: 500;
    padding: 7px 16px;

    height: auto;
    min-height: 34px;
    letter-spacing: 0.01em;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;

    &:hover {
      background: #fff;
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

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.batch-delete-btn {
  border-radius: 8px;
  font-weight: 500;
  padding: 5px 12px;
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

  &:active {
    transform: translateY(0);
  }
}

.category-tags {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f3f4f6;

  .category-tags-left {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .select-all-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    font-size: 14px;

    .select-all-text {
      font-size: 14px;
      color: #6b7280;
      white-space: nowrap;
    }
  }

  .tag-item {
    cursor: pointer;
    border-radius: 6px;
    padding: 0 12px;
    height: 30px;
    line-height: 30px;
    font-size: 13px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: #f3f4f6;
    border-color: #e5e7eb;
    color: #6b7280;

    &:hover {
      background: #e5e7eb;
      border-color: #d1d5db;
    }

    &.active {
      background: #e5e7eb;
      border-color: #d1d5db;
      color: #1f2937;
      font-weight: 600;
    }
  }
}

.note-list {
  min-height: 120px;

  .note-item {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 16px 4px;
    border-bottom: 1px solid #f3f4f6;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    cursor: pointer;

    &:hover {
      background: #f9fafb;
    }

    &:last-child {
      border-bottom: none;
    }

    .note-check {
      width: 28px;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding-left: 4px;
      margin-top: 2px;
    }

    /* 标题 + 「信息 / 操作」两行布局，避免时间与编辑按钮互相挤压 */
    .note-main {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .note-title {
      width: 100%;
      min-width: 0;
      font-size: 15px;
      font-weight: 500;
      color: #1f2937;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .note-meta {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px 10px;
      min-width: 0;

      .visibility-tag {
        border-radius: 4px;
      }

      .note-time {
        font-size: 13px;
        color: #9ca3af;
        white-space: nowrap;
      }

      .note-actions {
        margin-left: auto;
        display: flex;
        align-items: center;
        gap: 6px;
        flex-shrink: 0;
      }

      .edit-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 5px 12px;
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
          box-shadow: none;
        }
      }

      .delete-btn {
        border-radius: 8px;
        font-weight: 500;
        padding: 5px 8px;
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

        &:active {
          transform: translateY(0);
        }
      }
    }
  }
}

.pagination {
  display: flex;
  justify-content: center;
  margin-top: 20px;
  padding-top: 16px;

  .el-pager li {
    border-radius: 6px;

    &.is-active {
      background: #f3f4f6;
      color: #1f2937;
    }
  }
}

.el-overlay-dialog {
  .el-dialog {
    border-radius: 16px;

    .el-dialog__header {
      padding: 24px 24px 0;
      margin-right: 0;

      .el-dialog__title {
        font-size: 18px;
        font-weight: 600;
        color: #1f2937;
      }
    }

    .el-dialog__body {
      padding: 24px;

      .el-form {
        .el-form-item {
          margin-bottom: 20px;

          &:last-child {
            margin-bottom: 0;
          }

          .el-form-item__label {
            color: #6b7280;
            font-weight: 500;
          }

          .el-input__wrapper {
            border-radius: 8px;
            box-shadow: 0 0 0 1px #e5e7eb;

            &:hover {
              box-shadow: 0 0 0 1px #d1d5db;
            }

            &.is-focus {
              box-shadow: 0 0 0 1px #b3b3b3;
            }
          }
        }

        .el-button {
          border-radius: 8px !important;
          font-weight: 500;
          padding: 8px 20px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          background: #fff !important;
          border: 1px solid #e5e7eb !important;
          color: #6b7280 !important;

          &:hover {
            transform: translateY(-2px);
            border-color: #b3b3b3 !important;
            color: #4b5563 !important;
          }

          &:active {
            transform: translateY(0);
          }

          &.el-button--primary {
            background: #fff !important;
            border: 1px solid #e5e7eb !important;
            color: #1f2937 !important;

            &:hover {
              border-color: #9ca3af !important;
              color: #1f2937 !important;
              transform: translateY(-2px);
              box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
            }
          }

          &.el-button--danger {
            background: #fef2f2 !important;
            border: 1px solid #e5d0d0 !important;
            color: #b45353 !important;

            &:hover {
              background: #fff !important;
              border-color: #b38080 !important;
              color: #9b3a3a !important;
              transform: translateY(-2px);
              box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
            }
          }
        }
      }
    }
  }
}

@media (max-width: 768px) {
  .profile-layout {
    flex-direction: column;
  }

  .left-sidebar {
    width: 100%;
  }

  .user-card {
    position: static;
  }
}
</style>
