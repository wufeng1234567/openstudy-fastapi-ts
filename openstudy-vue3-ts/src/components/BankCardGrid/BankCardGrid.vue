<!-- components/BankCardGrid/BankCardGrid.vue -->
<template>
  <div class="bank-card-grid">
    <!-- 头部区域 -->
    <div ref="headerRef" class="header-section" v-if="showHeader">
      <div class="title-section">
        <h2 class="page-title">{{ title }}</h2>
        <span class="total-count" v-if="showTotalCount">共 {{ total }} 个题库</span>
      </div>

      <div class="search-section" v-if="showSearch">
        <!-- 搜索框内嵌筛选按钮（与「我的题库 / 学习分享」一致） -->
        <SearchFilterInput v-model="localSearchKeyword" placeholder="搜索题库名称" class="search-input"
          :show-filter="showFilter" :filter-open="filterOpen" :filter-active="filterActive" @input="handleDebouncedSearch"
          @enter="handleSearchEnter" @clear="handleSearchClear" @toggle-filter="toggleFilter" />

        <el-button @click="handleRefresh" class="refresh-btn" v-if="showRefresh">
          <el-icon>
            <Refresh />
          </el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 筛选下拉面板（与「我的题库」共用同一套配置：多选 + 时间范围） -->
    <CommonFilterSidebar v-if="showFilter && showSearch" ref="filterSidebarRef" title="题库筛选" hide-trigger
      :filter-groups="filterGroups" :filter-form="filterForm" :default-filter="defaultFilter"
      :style="{ '--filter-top': headerHeight + 'px', '--filter-left': '0px' }" @filter-change="handleFilterChange"
      @reset-filters="handleFilterReset" @collapse-change="handleFilterCollapseChange"
      @active-change="handleFilterActiveChange" />

    <!-- 内容区域 -->
    <div class="content-main">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-container">
        <el-skeleton :rows="6" animated />
      </div>

      <!-- 空状态 -->
      <div v-else-if="displayBanks.length === 0" class="empty-state">
        <slot name="empty" :keyword="localSearchKeyword">
          <el-empty :description="getEmptyDescription()">
            <template #image>
              <el-icon size="80">
                <component :is="emptyIcon" />
              </el-icon>
            </template>
            <slot name="empty-action">
              <el-button type="primary" @click="handleEmptyAction">
                去发现题库
              </el-button>
            </slot>
          </el-empty>
        </slot>
      </div>

      <!-- 题库卡片列表 -->
      <div v-else class="bank-list">
        <el-row :gutter="20">
          <el-col v-for="(item, index) in paginatedBanks" :key="getItemKey(item, index)" :xs="24" :sm="colSm"
            :md="colMd" :lg="colLg" :xl="colXl" class="bank-card-col">
            <!-- 不要使用自定义插槽，用默认卡片 -->
            <div class="bank-card">
              <!-- 可点击区域 -->
              <div class="clickable-area" :class="{ 'is-disabled': isEmptyBank(item) }"
                @click="handleCardClick(item)">
                <!-- 题库封面 -->
                <div class="card-cover">
                  <BankCover :cover-image="item.coverImage" :bank-name="item.bankName" :subject="item.subject"
                    class="cover-image" />

                  <!-- 收藏状态 -->
                  <div v-if="showFavoriteStatus && (item.isCollected || item.favoriteId)" class="favorite-status">
                    <el-tag type="warning" size="small" class="favorite-tag">
                      已收藏
                    </el-tag>
                  </div>

                  <!-- 标星 -->
                  <div v-if="showStar && (item.isStarred || item.starred)" class="star-icon"
                    @click.stop="handleStarClick(item)">
                    <el-icon color="#f4c542">
                      <StarFilled />
                    </el-icon>
                  </div>
                </div>

                <!-- 题库信息 -->
                <div class="card-content">
                  <div class="bank-name">
                    <h3>{{ item.bankName || `题库ID: ${item.id}` }}</h3>
                    <el-tag v-if="item.subject" size="small" type="info">
                      {{ item.subject }}
                    </el-tag>
                  </div>

                  <!-- 题库统计 -->
                  <div v-if="showStats" class="bank-stats">
                    <div class="stat-item">
                      <el-icon>
                        <Document />
                      </el-icon>
                      <span v-if="!isEmptyBank(item)">{{ item.totalQuestions || 0 }} 题</span>
                      <el-tag v-else size="small" type="info" effect="plain">暂无题目</el-tag>
                    </div>
                    <div v-if="item.chapterCount" class="stat-item">
                      <el-icon>
                        <Collection />
                      </el-icon>
                      <span>{{ item.chapterCount }} 章节</span>
                    </div>
                    <div v-if="showCollectCount && item.collectCount" class="stat-item">
                      <el-icon>
                        <User />
                      </el-icon>
                      <span>{{ item.collectCount }} 人收藏</span>
                    </div>
                  </div>

                  <!-- 创建时间 -->
                  <div v-if="showCreateTime && item.createTime" class="create-time">
                    <el-icon>
                      <Clock />
                    </el-icon>
                    <span>创建于 {{ formatTime(item.createTime) }}</span>
                  </div>

                  <!-- 收藏备注 -->
                  <div v-if="showNotes && item.notes" class="bank-notes">
                    <el-icon>
                      <Comment />
                    </el-icon>
                    <span class="notes-text">{{ item.notes }}</span>
                  </div>

                  <!-- 学习信息 -->
                  <div v-if="showStudyInfo && (item.studyCount || item.lastStudyTime)" class="study-info">
                    <el-icon>
                      <Reading />
                    </el-icon>
                    <span>学习 {{ item.studyCount || 0 }} 次</span>
                    <span v-if="item.lastStudyTime" class="last-study">
                      最后: {{ formatTime(item.lastStudyTime) }}
                    </span>
                  </div>

                  <!-- 描述 -->
                  <div v-if="showDescription && item.description" class="bank-description">
                    <div class="description-text" v-html="truncateText(item.description, 80)"></div>
                  </div>
                </div>
              </div>

              <!-- 卡片底部操作按钮 -->
              <div class="card-actions">
                <el-button type="primary" size="small" plain :disabled="isEmptyBank(item)" @click.stop="handleViewDetail(item)" class="action-btn">
                  <el-icon>
                    <View />
                  </el-icon>
                  查看详情
                </el-button>

                <el-button v-if="showUncollectAction && (item.isCollected || item.favoriteId)" type="danger"
                  size="small" plain @click.stop="handleUncollect(item)"
                  :loading="uncollectLoading[getFavoriteId(item)]" class="action-btn">
                  <el-icon>
                    <Delete />
                  </el-icon>
                  取消收藏
                </el-button>

                <FavoriteButton v-else-if="showFavoriteButton" :type="'bank'" :target-id="item.id"
                  :initial-collected="item.isCollected" size="small" @collect-success="handleCollectSuccess"
                  @uncollect-success="handleUncollectSuccess" class="action-btn" />
              </div>
            </div>
          </el-col>
        </el-row>

        <!-- 分页 -->
        <div v-if="showPagination" class="pagination-section">
          <el-pagination v-model:current-page="currentPage" v-model:page-size="pageSize" :page-sizes="[12, 24, 48, 96]"
            layout="total, sizes, prev, pager, next, jumper" :total="displayBanks.length"
            @size-change="handleSizeChange" @current-change="handleCurrentChange" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, toRefs, getCurrentInstance, nextTick, onMounted, onBeforeUnmount } from 'vue'
import type { PropType } from 'vue'
import { parseTime } from '@/utils/ruoyi'
import {
  Refresh, StarFilled, Document,
  User, Comment, Clock, View, Delete, Collection,
  Reading
} from '@element-plus/icons-vue'
import BankCover from '@/components/BankCover/index.vue'
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
import SearchFilterInput from '@/components/SearchFilterInput/index.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import type { QuestionBank } from '@/types'

const { proxy } = getCurrentInstance()

const props = defineProps({
  // 数据相关
  banks: {
    type: Array as PropType<QuestionBank[]>,
    default: () => []
  },
  loading: {
    type: Boolean,
    default: false
  },

  // 标题和描述
  title: {
    type: String,
    default: '题库列表'
  },
  emptyText: {
    type: String,
    default: '暂无题库'
  },
  emptyIcon: {
    type: [String, Object],
    default: 'Collection'
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
  // 是否在搜索框内嵌「筛选」入口（多选 + 时间范围）
  showFilter: {
    type: Boolean,
    default: true
  },
  showRefresh: {
    type: Boolean,
    default: true
  },
  showPagination: {
    type: Boolean,
    default: true
  },

  // 卡片内容控制
  showFavoriteStatus: {
    type: Boolean,
    default: true
  },
  showStar: {
    type: Boolean,
    default: true
  },
  showStats: {
    type: Boolean,
    default: true
  },
  showCollectCount: {
    type: Boolean,
    default: true
  },
  showCreateTime: {
    type: Boolean,
    default: false
  },
  showNotes: {
    type: Boolean,
    default: false
  },
  showStudyInfo: {
    type: Boolean,
    default: false
  },
  showDescription: {
    type: Boolean,
    default: true
  },
  showFavoriteButton: {
    type: Boolean,
    default: true
  },
  showUncollectAction: {
    type: Boolean,
    default: false
  },

  // 布局配置
  colSm: {
    type: Number,
    default: 12
  },
  colMd: {
    type: Number,
    default: 8
  },
  colLg: {
    type: Number,
    default: 6
  },
  colXl: {
    type: Number,
    default: 4
  },

  // 搜索关键词
  searchKeyword: {
    type: String,
    default: ''
  },

  // 是否使用完整数据搜索
  useFullDataSearch: {
    type: Boolean,
    default: true
  },

  // 是否启用卡片点击弹窗
  enableCardClickModal: {
    type: Boolean,
    default: true
  },

  // 自定义弹窗标题
  modalTitle: {
    type: String,
    default: '提示'
  },

  // 自定义弹窗确认按钮文本
  modalConfirmText: {
    type: String,
    default: '查看详情'
  },

  // 自定义弹窗取消按钮文本
  modalCancelText: {
    type: String,
    default: '取消'
  },

  // 自定义获取关键词函数
  getItemSearchText: {
    type: Function,
    default: (item) => item.bankName || ''
  },

  // 自定义获取收藏ID函数
  getItemFavoriteId: {
    type: Function,
    default: (item) => item.favoriteId
  },

  // 自定义获取Key函数
  getItemKey: {
    type: Function,
    default: (item, index) => item.id || index
  },
  // 是否自动过滤停用的题库
  autoFilterDisabledBanks: {
    type: Boolean,
    default: true
  },
  // 自定义获取状态字段函数
  getItemStatus: {
    type: Function,
    default: (item) => item.status || '0'
  }
})

const emit = defineEmits([
  'search',
  'refresh',
  'card-click',
  'card-click-confirm',
  'view-detail',
  'star-click',
  'uncollect',
  'collect-success',
  'uncollect-success',
  'empty-action',
  'page-change',
  'size-change'
])

// 响应式数据
const localSearchKeyword = ref(props.searchKeyword)
const currentPage = ref(1)
const pageSize = ref(12)
const uncollectLoading = ref<Record<string | number, boolean>>({})
const allBanks = ref<QuestionBank[]>([])
const displayBanks = ref<QuestionBank[]>([])
const searchDebounceTimer = ref<ReturnType<typeof setTimeout> | null>(null)

// 筛选（与「我的题库 / 学习分享」一致：多选 + 时间范围，组内 OR、组间 AND）
const headerRef = ref(null)
const headerHeight = ref(0)
const filterOpen = ref(false)
const filterActive = ref(false)
const filterSidebarRef = ref<any>(null)
const filterForm = reactive<{
  subjects: string[]
  questionCount: string[]
  createRange: string[] | null
}>({
  subjects: [],
  questionCount: [],
  createRange: null
})
const defaultFilter = { subjects: [], questionCount: [], createRange: null }

const filterGroups = computed(() => {
  const subjects = new Set<string>()
  allBanks.value.forEach((bank: QuestionBank) => {
    if (bank.subject) subjects.add(bank.subject)
  })

  return [
    {
      key: 'subjects',
      label: '科目分类',
      type: 'checkbox',
      options: Array.from(subjects).sort().map((s: string) => ({ value: s, label: s }))
    },
    {
      key: 'questionCount',
      label: '题目数量',
      type: 'checkbox',
      options: [
        { value: '0-10', label: '10题以下' },
        { value: '10-50', label: '10-50题' },
        { value: '50-100', label: '50-100题' },
        { value: '100+', label: '100题以上' }
      ]
    },
    {
      key: 'createRange',
      label: '创建时间',
      type: 'dateRange'
    }
  ]
})

const toggleFilter = () => {
  filterSidebarRef.value?.toggleCollapse?.()
}

const handleFilterCollapseChange = (collapsed: boolean) => {
  filterOpen.value = !collapsed
}

const handleFilterActiveChange = (active: boolean) => {
  filterActive.value = !!active
}

const handleFilterChange = (newFilter: any) => {
  Object.assign(filterForm, newFilter)
  if (props.useFullDataSearch) {
    applyFilters()
  } else {
    emit('search', localSearchKeyword.value)
  }
}

const handleFilterReset = () => {
  filterForm.subjects = []
  filterForm.questionCount = []
  filterForm.createRange = null
  if (props.useFullDataSearch) {
    applyFilters()
  }
}

const updateHeaderHeight = () => {
  nextTick(() => {
    if (headerRef.value) headerHeight.value = (headerRef.value as any).offsetHeight
  })
}

onMounted(() => {
  updateHeaderHeight()
  window.addEventListener('resize', updateHeaderHeight)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateHeaderHeight)
})

// 计算属性
const total = computed(() => displayBanks.value.length)

// 初始化数据
const initData = () => {
  allBanks.value = [...props.banks]
  displayBanks.value = [...props.banks]
  applyFilters() // 这里修改
  currentPage.value = 1
}

// 应用搜索和状态过滤
const applyFilters = () => {
  let filteredBanks = [...allBanks.value]

  // 如果启用自动过滤停用题库，则过滤掉 status === '1' 的题库
  if (props.autoFilterDisabledBanks) {
    filteredBanks = filteredBanks.filter(item => {
      const itemStatus = props.getItemStatus(item)
      return itemStatus !== '1' // 过滤掉停用的题库
    })
  }

  // 应用搜索过滤
  if (localSearchKeyword.value && localSearchKeyword.value.trim() !== '') {
    const searchKeyword = localSearchKeyword.value.toLowerCase().trim()
    filteredBanks = filteredBanks.filter(item => {
      // 使用自定义的搜索文本函数
      const searchText = props.getItemSearchText(item).toLowerCase()
      return searchText.includes(searchKeyword)
    })
  }

  // 科目分类（多选）
  if (filterForm.subjects?.length > 0) {
    filteredBanks = filteredBanks.filter(item => filterForm.subjects.includes(item.subject || ''))
  }

  // 题目数量（多选：命中任一档）
  if (filterForm.questionCount?.length > 0) {
    const ranges = filterForm.questionCount
    filteredBanks = filteredBanks.filter(item => {
      const count = item.totalQuestions || 0
      return ranges.some((range: string) => {
        if (range === '0-10') return count < 10
        if (range === '10-50') return count >= 10 && count < 50
        if (range === '50-100') return count >= 50 && count < 100
        if (range === '100+') return count >= 100
        return false
      })
    })
  }

  // 创建时间范围
  if (filterForm.createRange?.length === 2) {
    const [start, end] = filterForm.createRange
    const startTs = new Date(`${start} 00:00:00`).getTime()
    const endTs = new Date(`${end} 23:59:59`).getTime()
    filteredBanks = filteredBanks.filter(item => {
      if (!item.createTime) return false
      const ts = new Date(item.createTime).getTime()
      return ts >= startTs && ts <= endTs
    })
  }

  displayBanks.value = filteredBanks
  currentPage.value = 1
}

const paginatedBanks = computed(() => {
  if (!props.showPagination) {
    return displayBanks.value
  }

  const startIndex = (currentPage.value - 1) * pageSize.value
  const endIndex = startIndex + pageSize.value
  return displayBanks.value.slice(startIndex, endIndex)
})

// 监听外部数据变化
watch(() => props.banks, (newBanks) => {
  allBanks.value = [...newBanks]
  if (!props.useFullDataSearch) {
    // 如果不使用完整数据搜索，直接更新显示数据
    displayBanks.value = [...newBanks]
  } else {
    // 使用完整数据搜索，需要重新应用过滤
    applyFilters() // 这里修改
  }
  currentPage.value = 1
}, { immediate: true, deep: true })

watch(() => props.searchKeyword, (newVal) => {
  localSearchKeyword.value = newVal
  if (props.useFullDataSearch) {
    applyFilters() // 这里修改
  }
})

// 方法
const handleDebouncedSearch = () => {
  if (searchDebounceTimer.value) {
    clearTimeout(searchDebounceTimer.value)
  }
  searchDebounceTimer.value = setTimeout(() => {
    if (props.useFullDataSearch) {
      applyFilters()
    } else {
      emit('search', localSearchKeyword.value)
      currentPage.value = 1
    }
  }, 300)
}

const handleSearchClear = () => {
  localSearchKeyword.value = ''
  if (props.useFullDataSearch) {
    applyFilters()
  } else {
    handleDebouncedSearch()
  }
}

const handleSearchEnter = () => {
  if (searchDebounceTimer.value) clearTimeout(searchDebounceTimer.value)
  if (props.useFullDataSearch) {
    applyFilters()
  } else {
    emit('search', localSearchKeyword.value)
    currentPage.value = 1
  }
}

const handleRefresh = () => {
  localSearchKeyword.value = ''
  emit('refresh')
  currentPage.value = 1
  if (props.useFullDataSearch) {
    // 使用完整数据搜索，重新初始化数据
    initData() // 这里会自动调用 applyFilters
  }
}

// 卡片点击处理
const isEmptyBank = (item) => {
  return !item || !item.totalQuestions || Number(item.totalQuestions) === 0
}

const handleCardClick = (item) => {
  // 空题库不允许点击进入
  if (isEmptyBank(item)) {
    return
  }

  // 先触发 card-click 事件
  emit('card-click', item)

  // 如果启用了弹窗，则显示确认弹窗
  if (props.enableCardClickModal) {
    proxy.$modal.confirm(
      `是否查看题库 "${item.bankName || '未知题库'}" 的详细信息？`,
      props.modalTitle,
      {
        confirmButtonText: props.modalConfirmText,
        cancelButtonText: props.modalCancelText,
        type: 'info'
      }
    ).then(() => {
      // 用户确认，触发查看详情
      emit('card-click-confirm', item)
      handleViewDetail(item)
    }).catch(() => {
      // 用户取消
    })
  } else {
    // 不启用弹窗，直接触发查看详情
    handleViewDetail(item)
  }
}

const handleViewDetail = (item) => {
  emit('view-detail', item)
}

const handleStarClick = (item) => {
  emit('star-click', item)
}

const handleUncollect = async (item) => {
  try {
    const favoriteId = getFavoriteId(item)
    uncollectLoading.value[favoriteId] = true

    await proxy.$modal.confirm(
      `确定要取消收藏 "${item.bankName || '该题库'}" 吗？`,
      '取消收藏确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    emit('uncollect', item)

  } catch (error) {
    // 用户取消操作或其他错误
    if (error !== 'cancel') {
      proxy.$modal.msgError('操作失败')
    }
  } finally {
    const favoriteId = getFavoriteId(item)
    uncollectLoading.value[favoriteId] = false
  }
}

const handleCollectSuccess = (targetId, type) => {
  emit('collect-success', targetId, type)
}

const handleUncollectSuccess = (targetId, type) => {
  emit('uncollect-success', targetId, type)
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
const getEmptyDescription = () => {
  if (localSearchKeyword.value) {
    return `没有找到包含"${localSearchKeyword.value}"的题库`
  }
  return props.emptyText
}

const formatTime = (time) => {
  return parseTime(time, '{y}-{m}-{d}')
}

const truncateText = (text, length = 50) => {
  if (!text) return ''
  return text.length > length ? text.substring(0, length) + '...' : text
}
</script>

<style scoped lang="scss">
.bank-card-grid {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  /* 内嵌筛选面板的定位参考 */
  position: relative;

  .header-section {
    margin-bottom: 16px;

    .title-section {
      display: flex;
      align-items: baseline;
      gap: 10px;
      margin-bottom: 14px;

      .page-title {
        font-size: 16px;
        font-weight: 600;
        letter-spacing: -0.01em;
        color: var(--os-text);
        margin: 0;
      }

      .total-count {
        margin-left: 0;
        font-size: 13px;
        color: var(--os-text-3);
        background: transparent;
        padding: 0;
        border-radius: 0;
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

      .refresh-btn {
        border-radius: var(--os-radius-sm);
      }
    }
  }

  .content-main {
    flex: 1;

    .loading-container {
      padding: 40px;
      text-align: center;
    }

    .empty-state {
      padding: 60px 20px;
      text-align: center;
    }

    .bank-list {
      .bank-card-col {
        margin-bottom: 24px;
      }

      .bank-card {
        background: #fff;
        border: 1px solid var(--os-border-soft);
        border-radius: var(--os-radius);
        overflow: hidden;
        transition: border-color var(--ds-duration-base) var(--ds-ease-in-out),
          box-shadow var(--ds-duration-base) var(--ds-ease-in-out),
          transform var(--ds-duration-base) var(--ds-ease-in-out);
        height: 100%;
        display: flex;
        flex-direction: column;

        &:hover {
          transform: translateY(-1px);
          box-shadow: var(--os-shadow-2);
          border-color: var(--os-border-strong);

          .clickable-area {
            background-color: #fcfcfd;
          }
        }

        .clickable-area {
          flex: 1;
          cursor: pointer;
          transition: background-color 0.2s ease;

          &:hover {
            background-color: #fcfcfd;
          }

          &.is-disabled {
            cursor: not-allowed;

            &:hover {
              background-color: transparent;
            }
          }
        }

        .card-cover {
          position: relative;
          height: 144px;
          overflow: hidden;

          .cover-image {
            width: 100%;
            height: 100%;
            background-color: #f5f7fa;
            transition: transform 0.3s ease;
          }

          &:hover .cover-image {
            /* 轻微放大即可，不再做 1.05 那种"廉价"的缩放 */
            transform: scale(1.02);
          }

          .favorite-status {
            position: absolute;
            top: 12px;
            left: 12px;

            .favorite-tag {
              font-weight: 600;
              box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            }
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
              background: rgba(255, 255, 255, 1);
              transform: scale(1.1);
            }

            .el-icon {
              font-size: 18px;
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
              line-height: 1.4;
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
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 12px;
            font-size: 12px;
            color: #606266;

            .stat-item {
              display: flex;
              align-items: center;
              gap: 4px;

              .el-icon {
                font-size: 14px;
                color: #909399;
              }
            }
          }

          .create-time {
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

          .bank-notes {
            display: flex;
            align-items: flex-start;
            gap: 6px;
            margin-bottom: 12px;
            padding: 8px;
            background: #fdf6ec;
            border-radius: 4px;
            border-left: 3px solid #e6a23c;

            .el-icon {
              color: #e6a23c;
              flex-shrink: 0;
              margin-top: 2px;
            }

            .notes-text {
              font-size: 12px;
              color: #e6a23c;
              line-height: 1.4;
              overflow: hidden;
              text-overflow: ellipsis;
              display: -webkit-box;
              -webkit-line-clamp: 2;
              -webkit-box-orient: vertical;
            }
          }

          .study-info {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            font-size: 12px;
            color: #909399;

            .el-icon {
              font-size: 12px;
            }

            .last-study {
              font-size: 11px;
              color: #c0c4cc;
            }
          }

          .bank-description {
            .description-text {
              font-size: 13px;
              color: #666;
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
          border-top: 1px solid #f0f0f0;
          display: flex;
          gap: 8px;

          .el-button,
          .action-btn {
            flex: 1;
            border-radius: 8px;
            font-size: 12px;
            padding: 6px 12px;
            font-weight: 500;
          }

          .el-button--default {
            background: #f5f7fa;
            border-color: #e4e7ed;
            color: #606266;
          }

          .el-button--default:hover {
            background: #ecf5ff;
            border-color: #b3d8ff;
            color: #409eff;
          }

          .el-button--danger {
            background: #fef0f0;
            border-color: #fde2e2;
            color: #f56c6c;
          }

          .el-button--danger:hover {
            background: #f56c6c;
            border-color: #f56c6c;
            color: #fff;
          }
        }
      }

      .pagination-section {
        margin-top: 32px;
        display: flex;
        justify-content: center;
      }
    }
  }
}

// 响应式调整
@media (max-width: 768px) {
  .bank-card-grid {
    .header-section {
      .search-section {
        flex-direction: column;
        align-items: stretch;
      }

      .search-input {
        max-width: 100%;
      }
    }

    .bank-card {
      .card-cover {
        height: 124px;
      }

      .card-content {
        .bank-name h3 {
          font-size: 15px;
        }
      }
    }
  }
}
</style>
