<template>
  <div class="bank-card-list">
    <!-- 标题和搜索区域 -->
    <div class="search-area">
      <div class="title-section">
        <h2 class="page-title">{{ title }}</h2>
        <span class="total-count">共 {{ total }} 个题库</span>
      </div>

      <div class="search-section">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索题库名称"
          clearable
          @input="handleSearchInput"
          @keyup.enter="handleSearchEnter"
          class="search-input"
        >
          <template #prefix>
            <el-icon>
              <Search />
            </el-icon>
          </template>
        </el-input>

        <el-button @click="handleRefresh" class="refresh-btn">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- 空状态 -->
    <div v-else-if="bankList.length === 0" class="empty-state">
      <el-empty :description="emptyDescription">
        <template #image>
          <el-icon size="80">
            <component :is="emptyIcon" />
          </el-icon>
        </template>
        <el-button @click="handleEmptyAction" class="empty-action-btn">
          {{ emptyActionText }}
        </el-button>
      </el-empty>
    </div>

    <!-- 卡片列表 -->
    <div v-else class="bank-grid">
      <el-row :gutter="20">
        <el-col v-for="item in bankList" :key="item.id || item.favoriteId" :xs="24" :sm="12" :md="8" :lg="6" :xl="4"
          class="bank-card-col">
          <div class="bank-card">
            <!-- 可点击区域 -->
            <div class="clickable-area" @click="handleCardClick(item)">
              <!-- 题库封面 -->
              <div class="card-cover">
                <el-image :src="getImageUrl(item.coverImage || item.bank?.coverImage)" fit="cover" class="cover-image"
                  @error="handleImageError">
                  <template #error>
                    <div class="image-error">
                      <el-icon>
                        <Picture />
                      </el-icon>
                    </div>
                  </template>
                </el-image>

                <!-- 状态标签 -->
                <div v-if="mode === 'favorite'" class="favorite-status">
                  <el-tag type="warning" size="small">已收藏</el-tag>
                </div>

                <!-- 标星（仅收藏模式） -->
                <div v-if="mode === 'favorite' && item.isStarred" class="star-icon"
                  @click.stop="handleToggleStar(item)">
                  <el-icon color="#f4c542">
                    <StarFilled />
                  </el-icon>
                </div>
              </div>

              <!-- 题库信息 -->
              <div class="card-content">
                <div class="bank-name">
                  <h3>{{ getBankName(item) }}</h3>
                  <el-tag v-if="getBankSubject(item)" size="small" type="info">
                    {{ getBankSubject(item) }}
                  </el-tag>
                </div>

                <!-- 统计信息 -->
                <div class="bank-stats">
                  <div class="stat-item">
                    <el-icon>
                      <Document />
                    </el-icon>
                    <span>{{ getTotalQuestions(item) }} 题</span>
                  </div>
                  <div class="stat-item">
                    <el-icon>
                      <User />
                    </el-icon>
                    <span>{{ getTimeLabel(item) }}</span>
                  </div>
                </div>

                <!-- 描述 -->
                <div v-if="getBankDescription(item)" class="bank-description">
                  <div class="description-text">{{ getBankDescription(item) }}</div>
                </div>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="card-actions">
              <el-button size="small" @click.stop="handleViewDetail(item)" class="action-btn">
                <el-icon>
                  <View />
                </el-icon>
                查看详情
              </el-button>

              <el-button v-if="mode === 'my'" size="small" @click.stop="handleDelete(item)"
                :loading="deleteLoading[item.id]" class="action-btn action-btn--danger">
                <el-icon>
                  <Delete />
                </el-icon>
                删除
              </el-button>

              <el-button v-else-if="mode === 'favorite'" size="small"
                @click.stop="handleUncollect(item)" :loading="uncollectLoading[item.favoriteId]"
                class="action-btn action-btn--danger">
                <el-icon>
                  <Delete />
                </el-icon>
                取消收藏
              </el-button>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 分页 -->
      <div v-if="total > 0" class="pagination-section">
        <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :page-sizes="[12, 24, 48, 96]"
          layout="total, sizes, prev, pager, next, jumper" :total="total" @size-change="handleSizeChange"
          @current-change="handlePageChange" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'BankCardList' })
import { ref, watch, computed } from 'vue'
import { Search, Refresh, Picture, Document, User, View, Delete, StarFilled } from '@element-plus/icons-vue'

const props = defineProps({
  mode: {
    type: String,
    required: true,
    validator: (val) => ['my', 'favorite'].includes(val)
  },
  dataList: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },
  actionLoading: {
    type: Object,
    default: () => ({})
  },
  title: {
    type: String,
    default: '题库列表'
  },
  emptyDescription: {
    type: String,
    default: '暂无题库'
  },
  emptyIcon: {
    type: Object,
    default: () => Picture
  },
  emptyActionText: {
    type: String,
    default: '去创建题库'
  }
})

const emit = defineEmits([
  'search',
  'refresh',
  'card-click',
  'view-detail',
  'delete',
  'uncollect',
  'toggle-star',
  'empty-action',
  'page-change',
  'size-change'
])

const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(12)
let searchTimer = null

const filteredList = computed(() => {
  if (!searchKeyword.value) return props.dataList
  const keyword = searchKeyword.value.toLowerCase()
  return props.dataList.filter(item => {
    const name = (getBankName(item) || '').toLowerCase()
    return name.includes(keyword)
  })
})

const bankList = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredList.value.slice(start, end)
})

const total = computed(() => filteredList.value.length)

const getBankName = (item) => {
  return item.bankName || item.bank?.bankName || '未知题库'
}

const getBankSubject = (item) => {
  return item.subject || item.bank?.subject || ''
}

const getTotalQuestions = (item) => {
  return item.totalQuestions || item.bank?.totalQuestions || 0
}

const getBankDescription = (item) => {
  return item.description || item.bank?.description || item.notes || ''
}

const getTimeLabel = (item) => {
  if (props.mode === 'my') {
    return item.createTime ? `创建于 ${item.createTime}` : ''
  } else {
    return item.createTime ? `收藏于 ${item.createTime}` : ''
  }
}

const getImageUrl = (imagePath) => {
  if (!imagePath) return ''
  const baseApi = import.meta.env.VITE_APP_BASE_API || ''
  return imagePath.startsWith('http') ? imagePath : `${baseApi}${imagePath}`
}

const handleImageError = (e) => {
  console.log('图片加载失败')
}

const handleSearchInput = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    emit('search', searchKeyword.value)
  }, 300)
}

const handleSearchEnter = () => {
  if (searchTimer) clearTimeout(searchTimer)
  currentPage.value = 1
  emit('search', searchKeyword.value)
}

const handleSearchClear = () => {
  searchKeyword.value = ''
  currentPage.value = 1
  emit('search', '')
}

const handleRefresh = () => {
  searchKeyword.value = ''
  currentPage.value = 1
  emit('refresh')
}

const handleCardClick = (item) => {
  emit('card-click', item)
}

const handleViewDetail = (item) => {
  emit('view-detail', item)
}

const handleDelete = (item) => {
  emit('delete', item)
}

const handleUncollect = (item) => {
  emit('uncollect', item)
}

const handleToggleStar = (item) => {
  emit('toggle-star', item)
}

const handleEmptyAction = () => {
  emit('empty-action')
}

const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
  emit('size-change', val)
}

const handlePageChange = (val) => {
  currentPage.value = val
  emit('page-change', val)
}

defineExpose({
  resetSearch: () => {
    searchKeyword.value = ''
    currentPage.value = 1
  }
})

const deleteLoading = computed(() => props.mode === 'my' ? props.actionLoading : {})
const uncollectLoading = computed(() => props.mode === 'favorite' ? props.actionLoading : {})
</script>

<style scoped lang="scss">
.bank-card-list {
  .search-area {
    margin-bottom: 24px;
  }

  .title-section {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
  }

  .page-title {
    font-size: 20px;
    font-weight: 700;
    color: #1f2937;
    margin: 0;
  }

  .total-count {
    font-size: 14px;
    color: #6b7280;
  }

  .search-section {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .search-input {
    flex: 1;
    max-width: 400px;

    :deep(.el-input__wrapper) {
      border-radius: 8px;
      box-shadow: 0 0 0 1px #e5e7eb;
      background: #fff;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    :deep(.el-input__wrapper):hover {
      box-shadow: 0 0 0 1px #d1d5db;
    }

    :deep(.el-input__wrapper.is-focus) {
      box-shadow: 0 0 0 1px #b3b3b3;
    }
  }

  .refresh-btn {
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    padding: 8px 14px;
    height: auto;
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .refresh-btn:hover {
    transform: translateY(-2px);
    border-color: #d1d5db;
    color: #4b5563;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
  }

  .refresh-btn:active {
    transform: translateY(0);
  }

  .loading-container,
  .empty-state {
    padding: 40px 0;
    text-align: center;
  }

  .empty-action-btn {
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    padding: 8px 16px;
    height: auto;
    background: #fff;
    border: 1px solid #e5e7eb;
    color: #6b7280;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .empty-action-btn:hover {
    transform: translateY(-2px);
    border-color: #d1d5db;
    color: #4b5563;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
  }

  .bank-grid {
    margin-top: 20px;
  }

  .bank-card-col {
    margin-bottom: 24px;
  }

  .bank-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 16px;
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    height: 100%;
    display: flex;
    flex-direction: column;

    &:hover {
      transform: translateY(-4px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
      border-color: #d1d5db;
    }
  }

  .clickable-area {
    flex: 1;
    cursor: pointer;
    transition: background-color 0.2s ease;

    &:hover {
      background-color: #f8fafc;
    }
  }

  .card-cover {
    position: relative;
    height: 140px;
    overflow: hidden;
    background: #f5f7fa;

    .cover-image {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .image-error {
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: #ccc;
      font-size: 40px;
    }

    .favorite-status {
      position: absolute;
      top: 12px;
      left: 12px;
    }

    .star-icon {
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(255, 255, 255, 0.9);
      border-radius: 50%;
      width: 32px;
      height: 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s;
      z-index: 2;

      &:hover {
        background: #fff;
        transform: scale(1.1);
      }
    }
  }

  .card-content {
    padding: 16px;

    .bank-name {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;

      h3 {
        margin: 0;
        font-size: 16px;
        font-weight: 600;
        color: #1f2937;
        flex: 1;
        margin-right: 8px;
        overflow: hidden;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
      }
    }

    .bank-stats {
      display: flex;
      gap: 16px;
      margin-bottom: 12px;
      font-size: 13px;
      color: #6b7280;

      .stat-item {
        display: flex;
        align-items: center;
        gap: 4px;

        .el-icon {
          font-size: 14px;
          color: #9ca3af;
        }
      }
    }

    .bank-description {
      .description-text {
        font-size: 13px;
        color: #6b7280;
        line-height: 1.5;
        overflow: hidden;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
      }
    }
  }

  .card-actions {
    padding: 12px 16px;
    border-top: 1px solid #f3f4f6;
    display: flex;
    gap: 8px;

    .action-btn {
      flex: 1;
      border-radius: 8px;
      font-weight: 500;
      font-size: 13px;
      padding: 6px 8px;
      height: auto;
      background: #fff;
      border: 1px solid #e5e7eb;
      color: #6b7280;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .action-btn:hover {
      transform: translateY(-2px);
      border-color: #d1d5db;
      color: #4b5563;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
    }

    .action-btn:active {
      transform: translateY(0);
    }

    .action-btn--danger {
      background: #fef2f2;
      border-color: #e5d0d0;
      color: #b45353;
    }

    .action-btn--danger:hover {
      background: #fff;
      border-color: #b38080;
      color: #9b3a3a;
    }
  }

  .pagination-section {
    margin-top: 32px;
    display: flex;
    justify-content: center;
  }
}

@media (max-width: 768px) {
  .bank-card-list {
    .search-section {
      flex-direction: column;
      align-items: stretch;

      .search-input {
        max-width: 100%;
      }

      .search-btn,
      .refresh-btn {
        width: 100%;
      }
    }

    .card-cover {
      height: 120px;
    }
  }
}
</style>