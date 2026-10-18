<!-- components/QuestionCardGrid/QuestionCardGrid.vue -->
<template>
  <div class="question-card-grid">
    <!-- 搜索和标题区域 -->
    <div class="header-section" v-if="showHeader">
      <div class="title-section">
        <h2 class="page-title">{{ title }}</h2>
        <span class="total-count" v-if="showTotalCount">共 {{ total }} 道题目</span>
      </div>

      <div class="search-section" v-if="showSearch">
        <el-input v-model="localSearchKeyword" placeholder="搜索题目内容" clearable @keyup.enter="handleSearch"
          @clear="handleSearchClear" class="search-input">
          <template #prefix>
            <el-icon>
              <Search />
            </el-icon>
          </template>
        </el-input>

        <el-button type="primary" @click="handleSearch" class="search-btn">
          搜索
        </el-button>

        <el-button @click="handleRefresh" class="refresh-btn" v-if="showRefresh">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 筛选侧边栏 -->
    <div class="filter-sidebar" v-if="showFilter">
      <div class="filter-section">
        <h3 class="filter-title">筛选</h3>

        <!-- 题型筛选 -->
        <div class="filter-group" v-if="showQuestionTypeFilter">
          <div class="filter-label">题型</div>
          <div class="filter-options">
            <el-checkbox-group v-model="localFilters.questionType" @change="handleFilterChange">
              <el-checkbox v-for="type in questionTypes" :key="type.value" :value="type.value" class="filter-checkbox">
                {{ type.label }}
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </div>

        <!-- 难度筛选 -->
        <div class="filter-group" v-if="showDifficultyFilter">
          <div class="filter-label">难度</div>
          <div class="filter-options">
            <el-checkbox-group v-model="localFilters.difficulty" @change="handleFilterChange">
              <el-checkbox v-for="diff in difficultyOptions" :key="diff.value" :value="diff.value"
                class="filter-checkbox">
                <span :class="`difficulty-${diff.value}`">{{ diff.label }}</span>
              </el-checkbox>
            </el-checkbox-group>
          </div>
        </div>

        <!-- 是否标星 -->
        <div class="filter-group" v-if="showStarFilter">
          <div class="filter-label">标星状态</div>
          <div class="filter-options">
            <el-radio-group v-model="localFilters.isStarred" @change="handleFilterChange">
              <el-radio :value="null">全部</el-radio>
              <el-radio :value="1">已标星</el-radio>
              <el-radio :value="0">未标星</el-radio>
            </el-radio-group>
          </div>
        </div>

        <!-- 收藏状态 -->
        <div class="filter-group" v-if="showFavoriteStatusFilter">
          <div class="filter-label">收藏状态</div>
          <div class="filter-options">
            <el-radio-group v-model="localFilters.favoriteStatus" @change="handleFilterChange">
              <el-radio :value="1">正常收藏</el-radio>
              <el-radio :value="2">已掌握</el-radio>
              <el-radio :value="3">待复习</el-radio>
            </el-radio-group>
          </div>
        </div>

        <!-- 题库筛选 -->
        <div class="filter-group" v-if="showBankFilter && questionBanks.length > 0">
          <div class="filter-label">所属题库</div>
          <div class="filter-options">
            <el-select v-model="localFilters.bankId" placeholder="选择题库" clearable @change="handleFilterChange"
              class="bank-select">
              <el-option v-for="bank in questionBanks" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
            </el-select>
          </div>
        </div>

        <!-- 清空筛选按钮 -->
        <div class="filter-actions" v-if="showFilterActions">
          <el-button type="default" size="small" @click="resetFilters" plain>
            清空筛选
          </el-button>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="content-main" :class="{ 'with-filter': showFilter }">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-container">
        <el-skeleton :rows="6" animated />
      </div>

      <!-- 空状态 -->
      <div v-else-if="filteredQuestions.length === 0" class="empty-state">
        <slot name="empty" :keyword="localSearchKeyword">
          <el-empty :description="emptyText">
            <template #image>
              <el-icon size="80">
                <component :is="emptyIcon" />
              </el-icon>
            </template>
            <slot name="empty-action">
              <el-button type="primary" @click="handleEmptyAction">
                去发现题目
              </el-button>
            </slot>
          </el-empty>
        </slot>
      </div>

      <!-- 题目卡片列表 -->
      <div v-else class="question-list">
        <el-row :gutter="20">
          <el-col v-for="(item, index) in paginatedQuestions" :key="getItemKey(item, index)" :xs="24" :sm="colSm"
            :md="colMd" :lg="colLg" class="question-card-col">
            <slot name="card" :item="item" :index="index">
              <!-- 默认卡片样式 -->
              <div class="question-card" @click="handleCardClick(item)">
                <!-- 卡片头部 -->
                <div class="card-header">
                  <div class="question-type-badge" :class="getQuestionTypeClass(item.questionDetail?.questionType)">
                    {{ getQuestionTypeText(item.questionDetail?.questionType) }}
                  </div>

                  <div class="header-actions">
                    <!-- 标星按钮 -->
                    <el-icon v-if="showStarAction" :class="['star-icon', { 'starred': item.isStarred }]"
                      @click.stop="handleStarClick(item)">
                      <StarFilled v-if="item.isStarred" />
                      <Star v-else />
                    </el-icon>

                    <!-- 收藏状态标签 -->
                    <el-tag v-if="showFavoriteStatus && item.favoriteStatus"
                      :type="getFavoriteStatusType(item.favoriteStatus)" size="small" class="status-tag">
                      {{ getFavoriteStatusText(item.favoriteStatus) }}
                    </el-tag>
                  </div>
                </div>

                <!-- 卡片内容 -->
                <div class="card-content">
                  <div class="question-text" v-html="formatQuestionText(item.questionDetail?.questionText)"></div>

                  <!-- 选择题选项预览 -->
                  <div v-if="[1, 2].includes(item.questionDetail?.questionType) && item.questionDetail?.options"
                    class="options-preview">
                    <div v-for="(option, optIndex) in getPreviewOptions(item.questionDetail.options)" :key="optIndex"
                      class="option-preview">
                      <span class="option-letter">{{ getOptionLabel(optIndex) }}.</span>
                      <span class="option-text">{{ option }}</span>
                    </div>
                  </div>

                  <!-- 填空题/简答题预览 -->
                  <div v-else-if="[4, 5].includes(item.questionDetail?.questionType)" class="answer-preview">
                    <div class="preview-label">答案预览：</div>
                    <div class="preview-text">{{ truncateText(item.questionDetail?.answer, 60) }}</div>
                  </div>

                  <!-- 难度标签 -->
                  <div v-if="showDifficulty && item.questionDetail?.difficulty" class="difficulty-tag">
                    <el-tag size="small" :type="getDifficultyType(item.questionDetail.difficulty)">
                      {{ getDifficultyText(item.questionDetail.difficulty) }}
                    </el-tag>
                  </div>

                  <!-- 题库信息 -->
                  <div v-if="showBankInfo && item.bankDetail" class="bank-info">
                    <el-icon>
                      <Collection />
                    </el-icon>
                    <span>{{ item.bankDetail.bankName }}</span>
                  </div>

                  <!-- 学习统计 -->
                  <div v-if="showStudyStats" class="study-stats">
                    <div class="stat-item">
                      <el-icon>
                        <Check />
                      </el-icon>
                      <span>正确: {{ item.correctTimes || 0 }}</span>
                    </div>
                    <div class="stat-item">
                      <el-icon>
                        <Close />
                      </el-icon>
                      <span>错误: {{ item.errorTimes || 0 }}</span>
                    </div>
                    <div class="stat-item">
                      <el-icon>
                        <RefreshRight />
                      </el-icon>
                      <span>复习: {{ item.reviewCount || 0 }}</span>
                    </div>
                  </div>

                  <!-- 收藏备注和标签 -->
                  <div v-if="showMetaInfo && (item.notes || item.tags)" class="meta-info">
                    <div v-if="item.notes" class="notes">
                      <el-icon>
                        <Comment />
                      </el-icon>
                      <span class="notes-text">{{ item.notes }}</span>
                    </div>
                    <div v-if="item.tags" class="tags">
                      <el-icon>
                        <PriceTag />
                      </el-icon>
                      <span class="tags-text">{{ item.tags }}</span>
                    </div>
                  </div>

                  <!-- 收藏时间 -->
                  <div v-if="showFavoriteTime && item.createTime" class="favorite-time">
                    <el-icon>
                      <Clock />
                    </el-icon>
                    <span>收藏于 {{ formatTime(item.createTime) }}</span>
                  </div>
                </div>

                <!-- 卡片底部操作按钮 -->
                <div class="card-footer">
                  <slot name="actions" :item="item" :index="index">
                    <el-button type="primary" size="small" plain @click.stop="handleViewDetail(item)">
                      <el-icon>
                        <View />
                      </el-icon>
                      查看详情
                    </el-button>

                    <el-button v-if="showUncollectAction" type="danger" size="small" plain
                      @click.stop="handleUncollect(item)" :loading="uncollectLoading[getFavoriteId(item)]">
                      <el-icon>
                        <Delete />
                      </el-icon>
                      取消收藏
                    </el-button>
                  </slot>
                </div>
              </div>
            </slot>
          </el-col>
        </el-row>

        <!-- 分页 -->
        <div v-if="showPagination" class="pagination-section">
          <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :page-sizes="[12, 24, 48, 96]"
            layout="total, sizes, prev, pager, next, jumper" :total="filteredQuestions.length"
            @size-change="handleSizeChange" @current-change="handleCurrentChange" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, toRefs } from 'vue'
import { parseTime } from '@/utils/ruoyi'
import {
  Search, Refresh, Star, StarFilled, View, Delete,
  Collection, Check, Close, RefreshRight, Clock,
  Comment, PriceTag, Document, FolderOpened
} from '@element-plus/icons-vue'

const props = defineProps({
  // 数据相关
  questions: {
    type: Array,
    default: () => []
  },
  questionBanks: {
    type: Array,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },

  // 标题和描述
  title: {
    type: String,
    default: '题目列表'
  },
  emptyText: {
    type: String,
    default: '暂无数据'
  },
  emptyIcon: {
    type: [String, Object],
    default: 'Document'
  },

  // 显示控制
  showHeader: {
    type: Boolean,
    default: true
  },
  showTotalCount: {
    type: Boolean,
    default: true
  },
  showSearch: {
    type: Boolean,
    default: true
  },
  showRefresh: {
    type: Boolean,
    default: true
  },
  showFilter: {
    type: Boolean,
    default: true
  },
  showPagination: {
    type: Boolean,
    default: true
  },

  // 筛选功能控制
  showQuestionTypeFilter: {
    type: Boolean,
    default: true
  },
  showDifficultyFilter: {
    type: Boolean,
    default: true
  },
  showStarFilter: {
    type: Boolean,
    default: true
  },
  showFavoriteStatusFilter: {
    type: Boolean,
    default: true
  },
  showBankFilter: {
    type: Boolean,
    default: true
  },
  showFilterActions: {
    type: Boolean,
    default: true
  },

  // 卡片内容控制
  showStarAction: {
    type: Boolean,
    default: true
  },
  showFavoriteStatus: {
    type: Boolean,
    default: true
  },
  showDifficulty: {
    type: Boolean,
    default: true
  },
  showBankInfo: {
    type: Boolean,
    default: true
  },
  showStudyStats: {
    type: Boolean,
    default: true
  },
  showMetaInfo: {
    type: Boolean,
    default: true
  },
  showFavoriteTime: {
    type: Boolean,
    default: true
  },
  showUncollectAction: {
    type: Boolean,
    default: true
  },

  // 布局配置
  colSm: {
    type: Number,
    default: 12
  },
  colMd: {
    type: Number,
    default: 12
  },
  colLg: {
    type: Number,
    default: 8
  },

  // 初始筛选值
  initialFilters: {
    type: Object,
    default: () => ({
      bankId: null,
      isStarred: null,
      favoriteStatus: 1,
      difficulty: [],
      questionType: []
    })
  },

  // 搜索关键词
  searchKeyword: {
    type: String,
    default: ''
  },

  // 自定义获取关键词函数
  getItemSearchText: {
    type: Function,
    default: (item) => item.questionDetail?.questionText || ''
  },

  // 自定义获取ID函数（用于取消收藏等操作）
  getItemFavoriteId: {
    type: Function,
    default: (item) => item.favoriteId
  },

  // 自定义获取题库ID函数
  getItemBankId: {
    type: Function,
    default: (item) => item.bankId
  },

  // 自定义获取Key函数
  getItemKey: {
    type: Function,
    default: (item, index) => item.id || item.questionId || index
  }
})

const emit = defineEmits([
  'search',
  'refresh',
  'filter-change',
  'card-click',
  'view-detail',
  'star-click',
  'uncollect',
  'empty-action',
  'page-change',
  'size-change'
])

// 响应式数据
const localSearchKeyword = ref(props.searchKeyword)
const currentPage = ref(1)
const pageSize = ref(12)
const localFilters = reactive({ ...props.initialFilters })
const uncollectLoading = ref({})

// 常量定义
const questionTypes = [
  { value: 1, label: '单选题' },
  { value: 2, label: '多选题' },
  { value: 3, label: '判断题' },
  { value: 4, label: '填空题' },
  { value: 5, label: '简答题' },
  { value: 6, label: '组合题' },
  { value: 7, label: '组合题' }
]

const difficultyOptions = [
  { value: 1, label: '简单' },
  { value: 2, label: '中等' },
  { value: 3, label: '困难' },
  { value: 4, label: '极难' }
]

const favoriteStatusMap = {
  1: { text: '正常收藏', type: 'primary' },
  2: { text: '已掌握', type: 'success' },
  3: { text: '待复习', type: 'warning' },
  0: { text: '已取消', type: 'info' }
}

// 计算属性
const total = computed(() => props.questions.length)

const filteredQuestions = computed(() => {
  let filtered = [...props.questions]

  // 关键词搜索
  if (localSearchKeyword.value && localSearchKeyword.value.trim()) {
    const keyword = localSearchKeyword.value.toLowerCase().trim()
    filtered = filtered.filter(item => {
      const searchText = props.getItemSearchText(item).toLowerCase()
      return searchText.includes(keyword)
    })
  }

  // 题库筛选
  if (localFilters.bankId) {
    filtered = filtered.filter(item => props.getItemBankId(item) === localFilters.bankId)
  }

  // 标星筛选
  if (localFilters.isStarred !== null) {
    filtered = filtered.filter(item => item.isStarred === localFilters.isStarred)
  }

  // 收藏状态筛选
  if (localFilters.favoriteStatus !== null) {
    filtered = filtered.filter(item => item.favoriteStatus === localFilters.favoriteStatus)
  }

  // 难度筛选
  if (localFilters.difficulty.length > 0) {
    filtered = filtered.filter(item => {
      const difficulty = item.questionDetail?.difficulty
      return difficulty && localFilters.difficulty.includes(difficulty)
    })
  }

  // 题型筛选
  if (localFilters.questionType.length > 0) {
    filtered = filtered.filter(item => {
      const questionType = item.questionDetail?.questionType
      return questionType && localFilters.questionType.includes(questionType)
    })
  }

  return filtered
})

const paginatedQuestions = computed(() => {
  if (!props.showPagination) {
    return filteredQuestions.value
  }

  const startIndex = (currentPage.value - 1) * pageSize.value
  const endIndex = startIndex + pageSize.value
  return filteredQuestions.value.slice(startIndex, endIndex)
})

// 监听外部数据变化
watch(() => props.searchKeyword, (newVal) => {
  localSearchKeyword.value = newVal
})

watch(() => props.initialFilters, (newVal) => {
  Object.assign(localFilters, newVal)
}, { deep: true })

// 方法
const handleSearch = () => {
  emit('search', localSearchKeyword.value)
  currentPage.value = 1
}

const handleSearchClear = () => {
  localSearchKeyword.value = ''
  handleSearch()
}

const handleRefresh = () => {
  emit('refresh')
  currentPage.value = 1
  resetFilters()
}

const handleFilterChange = () => {
  emit('filter-change', { ...localFilters })
  currentPage.value = 1
}

const resetFilters = () => {
  Object.assign(localFilters, props.initialFilters)
  handleFilterChange()
}

const handleCardClick = (item) => {
  emit('card-click', item)
}

const handleViewDetail = (item) => {
  emit('view-detail', item)
}

const handleStarClick = (item) => {
  emit('star-click', item)
}

const handleUncollect = (item) => {
  emit('uncollect', item)
}

const handleEmptyAction = () => {
  emit('empty-action')
}

const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
  emit('size-change', val)
}

const handleCurrentChange = (val) => {
  currentPage.value = val
  emit('page-change', val)
}

const getFavoriteId = (item) => {
  return props.getItemFavoriteId(item)
}

// 工具方法
const formatTime = (time) => {
  return parseTime(time, '{y}-{m}-{d}')
}

const getQuestionTypeText = (type) => {
  const typeMap = {
    1: '单选题',
    2: '多选题',
    3: '判断题',
    4: '填空题',
    5: '简答题',
    6: '组合题',
    7: '组合题'
  }
  return typeMap[type] || '未知题型'
}

const getQuestionTypeClass = (type) => {
  const classMap = {
    1: 'type-single',
    2: 'type-multiple',
    3: 'type-truefalse',
    4: 'type-fillblank',
    5: 'type-essay',
    6: 'type-reading',
    7: 'type-cloze'
  }
  return classMap[type] || ''
}

const getDifficultyText = (difficulty) => {
  const diffMap = {
    1: '简单',
    2: '中等',
    3: '困难',
    4: '极难'
  }
  return diffMap[difficulty] || '未知'
}

const getDifficultyType = (difficulty) => {
  const typeMap = {
    1: 'success',
    2: 'info',
    3: 'warning',
    4: 'danger'
  }
  return typeMap[difficulty] || ''
}

const getFavoriteStatusText = (status) => {
  return favoriteStatusMap[status]?.text || '未知'
}

const getFavoriteStatusType = (status) => {
  return favoriteStatusMap[status]?.type || 'info'
}

const formatQuestionText = (text) => {
  if (!text) return ''
  return text.replace(/\n/g, '<br>').substring(0, 200) + (text.length > 200 ? '...' : '')
}

const truncateText = (text, length = 50) => {
  if (!text) return ''
  return text.length > length ? text.substring(0, length) + '...' : text
}

const getOptionLabel = (index) => {
  return String.fromCharCode(65 + index)
}

const getPreviewOptions = (options) => {
  if (!options) return []
  try {
    const opts = typeof options === 'string' ? JSON.parse(options) : options
    return Array.isArray(opts) ? opts.slice(0, 2) : []
  } catch (e) {
    return []
  }
}
</script>

<style scoped lang="scss">
.question-card-grid {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;

  .header-section {
    margin-bottom: 20px;

    .title-section {
      display: flex;
      align-items: center;
      margin-bottom: 20px;

      .page-title {
        font-size: 20px;
        font-weight: 700;
        color: #1f2937;
        margin: 0;
      }

      .total-count {
        margin-left: 15px;
        font-size: 14px;
        color: #6b7280;
        background: #f3f4f6;
        padding: 4px 12px;
        border-radius: 12px;
      }
    }

    .search-section {
      display: flex;
      gap: 10px;
      align-items: center;

      .search-input {
        flex: 1;
        max-width: 400px;
      }
    }
  }

  .content-wrapper {
    display: flex;
    flex: 1;
    gap: 20px;

    .filter-sidebar {
      width: 240px;
      flex-shrink: 0;

      .filter-section {
        background: #fff;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);

        .filter-title {
          font-size: 16px;
          font-weight: 600;
          margin-bottom: 20px;
          color: #303133;
        }

        .filter-group {
          margin-bottom: 20px;

          .filter-label {
            font-size: 14px;
            color: #606266;
            margin-bottom: 10px;
            font-weight: 500;
          }

          .filter-options {
            .filter-checkbox {
              display: block;
              margin-bottom: 8px;
            }
          }
        }

        .filter-actions {
          margin-top: 20px;
        }
      }
    }

    .content-main {
      flex: 1;

      &.with-filter {
        margin-left: 0;
      }

      .loading-container {
        padding: 40px;
        text-align: center;
      }

      .empty-state {
        padding: 60px 20px;
        text-align: center;
      }

      .question-list {
        .question-card-col {
          margin-bottom: 20px;
        }

        .question-card {
          background: #fff;
          border-radius: 16px;
          border: 1px solid #e5e7eb;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
          overflow: hidden;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          cursor: pointer;
          height: 100%;
          display: flex;
          flex-direction: column;

          &:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
            border-color: #d1d5db;
          }

          .card-header {
            padding: 16px 16px 12px;
            border-bottom: 1px solid #e5e7eb;
            display: flex;
            justify-content: space-between;
            align-items: center;

            .question-type-badge {
              padding: 4px 12px;
              border-radius: 4px;
              font-size: 12px;
              font-weight: 500;
              color: #fff;

              &.type-single {
                background: #409EFF;
              }

              &.type-multiple {
                background: #67C23A;
              }

              &.type-truefalse {
                background: #E6A23C;
              }

              &.type-fillblank {
                background: #F56C6C;
              }

              &.type-essay {
                background: #909399;
              }

              &.type-reading {
                background: #8E44AD;
              }

              &.type-cloze {
                background: #16A085;
              }
            }

            .header-actions {
              display: flex;
              align-items: center;
              gap: 8px;

              .star-icon {
                cursor: pointer;
                font-size: 18px;
                color: #DCDFE6;
                transition: color 0.3s;

                &:hover {
                  color: #E6A23C;
                }

                &.starred {
                  color: #E6A23C;
                }
              }
            }
          }

          .card-content {
            padding: 16px;
            flex: 1;

            .question-text {
              margin-bottom: 16px;
              line-height: 1.6;
              color: #1f2937;
              font-size: 14px;

              :deep(br) {
                content: '';
                display: block;
                margin-bottom: 4px;
              }

              :deep(img) {
                max-width: 100% !important;
                max-height: 120px !important;
                width: auto !important;
                height: auto !important;
                object-fit: contain !important;
                border-radius: 4px;
                margin: 4px 0;
                vertical-align: middle;
              }
            }

            .options-preview {
              margin-bottom: 16px;

              .option-preview {
                margin-bottom: 8px;
                display: flex;
                align-items: flex-start;

                .option-letter {
                  color: #409EFF;
                  font-weight: 500;
                  margin-right: 8px;
                  flex-shrink: 0;
                }

                .option-text {
                  color: #606266;
                  font-size: 13px;
                  line-height: 1.5;

                  :deep(img) {
                    max-width: 80px !important;
                    max-height: 40px !important;
                    object-fit: contain !important;
                    border-radius: 2px;
                    vertical-align: middle;
                  }
                }
              }
            }

            .answer-preview {
              margin-bottom: 16px;
              padding: 12px;
              background: #f8f9fa;
              border-radius: 4px;

              .preview-label {
                font-size: 12px;
                color: #909399;
                margin-bottom: 4px;
              }

              .preview-text {
                font-size: 13px;
                color: #606266;
                line-height: 1.5;
                overflow: hidden;

                :deep(img) {
                  max-width: 100% !important;
                  max-height: 60px !important;
                  object-fit: contain !important;
                  border-radius: 2px;
                  vertical-align: middle;
                }
              }
            }

            .difficulty-tag {
              margin-bottom: 12px;
            }

            .bank-info {
              display: flex;
              align-items: center;
              gap: 6px;
              margin-bottom: 12px;
              font-size: 12px;
              color: #909399;

              .el-icon {
                font-size: 14px;
              }
            }

            .study-stats {
              display: flex;
              gap: 16px;
              margin-bottom: 12px;

              .stat-item {
                display: flex;
                align-items: center;
                gap: 4px;
                font-size: 12px;
                color: #606266;

                .el-icon {
                  font-size: 14px;
                }

                &:first-child .el-icon {
                  color: #67C23A;
                }

                &:nth-child(2) .el-icon {
                  color: #F56C6C;
                }

                &:last-child .el-icon {
                  color: #409EFF;
                }
              }
            }

            .meta-info {
              margin-bottom: 12px;

              .notes,
              .tags {
                display: flex;
                align-items: flex-start;
                gap: 6px;
                font-size: 12px;
                color: #606266;
                margin-bottom: 6px;

                .el-icon {
                  font-size: 14px;
                  color: #909399;
                  flex-shrink: 0;
                  margin-top: 2px;
                }

                .notes-text,
                .tags-text {
                  line-height: 1.4;
                }
              }
            }

            .favorite-time {
              display: flex;
              align-items: center;
              gap: 6px;
              font-size: 12px;
              color: #909399;

              .el-icon {
                font-size: 14px;
              }
            }
          }

          .card-footer {
            padding: 12px 16px;
            border-top: 1px solid #f0f0f0;
            display: flex;
            gap: 8px;
            justify-content: flex-end;
          }
        }

        .pagination-section {
          margin-top: 30px;
          display: flex;
          justify-content: center;
        }
      }
    }
  }
}

// 响应式调整
@media (max-width: 768px) {
  .question-card-grid {
    .content-wrapper {
      flex-direction: column;

      .filter-sidebar {
        width: 100%;
      }

      .content-main.with-filter {
        margin-left: 0;
      }
    }
  }
}
</style>