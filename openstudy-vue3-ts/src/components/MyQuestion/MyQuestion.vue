<!-- src/components/MyQuestion/MyQuestion.vue -->
<template>
  <div class="favorite-container">
    <!-- AI 解析弹框 -->
    <AiAnalysisDialog v-if="showAiAnalysis" :question="currentAiQuestion.text" :question-id="currentAiQuestion.id"
      :question-type="currentAiQuestion.type" :options="currentAiQuestion.options"
      :correct-answer="currentAiQuestion.answer" :cached-content="currentAiQuestion.cachedContent"
      :sub-questions="currentAiQuestion.subQuestions"
      @close="showAiAnalysis = false" @update-cache="updateAiCache" />

    <!-- 题目详情弹框 -->
    <QuestionDetailDialog v-model:visible="detailDialogVisible" :current-favorite-question="currentFavoriteQuestion"
      :current-question-detail="currentQuestionDetail" :current-question-index="currentQuestionIndex"
      :dialog-questions="dialogQuestions" :is-fullscreen="isFullscreen" :selected-answer="selectedAnswer"
      :sub-fill-blank-answers="subFillBlankAnswers" :sub-essay-answers="subEssayAnswers" :answers="answers"
      :question-type="questionType" @close="closeDetailDialog" @toggle-fullscreen="toggleFullscreen"
      @prev-question="prevQuestionInDialog" @next-question="nextQuestionInDialog" @select-option="selectOption"
      @update-answer="value => selectedAnswer = value" @select-sub-option="selectSubOption"
      @update-sub-fill-blank-answer="updateSubFillBlankAnswer" @update-sub-essay-answer="updateSubEssayAnswer"
      @mark="markQuestion" @add-note="addNote" @report="reportQuestion" @ai-analyze="openAiAnalysis" />

    <!-- 搜索和标题区域 -->
    <div ref="headerRef" class="header-wrapper">
      <QuestionHeader :title="headerTitle" :total="total" :search-keyword="searchQuery?.keyword || ''"
        :question-type="questionType" :show-filter="true" :filter-open="filterOpen" :filter-active="filterActive"
        @search="handleSearch" @clear-search="handleClearSearch" @toggle-filter="toggleFilterSidebar"
        @refresh="handleRefresh" />
    </div>

      <!-- 筛选下拉面板（触发按钮已内嵌到搜索框最左侧） -->
      <CommonFilterSidebar
        ref="filterSidebarRef"
        title="筛选"
        hide-trigger
        :filter-groups="filterGroups"
        :filter-form="filterForm"
        :default-filter="defaultFilter"
        :style="{ '--filter-top': headerHeight + 'px' }"
        @filter-change="handleFilterChange"
        @reset-filters="resetFilters"
        @collapse-change="handleFilterCollapseChange"
        @active-change="handleFilterActiveChange"
      />

      <!-- 右侧内容区域 -->
      <div class="content-main">
          <!-- 加载状态 -->
          <div v-if="loading" class="loading-container">
            <el-skeleton :rows="6" animated />
          </div>

          <!-- 空状态 -->
          <div v-else-if="!questions || questions.length === 0" class="empty-state">
            <el-empty :description="emptyText">
              <template #image>
                <el-icon size="80">
                  <Star />
                </el-icon>
              </template>
              <el-button type="primary" @click="handleEmptyAction">
                {{ emptyActionText }}
              </el-button>
            </el-empty>
          </div>

          <!-- 题目卡片列表 -->
          <div v-else class="question-list">
            <el-row :gutter="20">
              <el-col v-for="item in questions" :key="getItemKey(item)" :xs="24" :sm="12" :md="12" :lg="8"
                class="question-card-col" :data-qid="item.questionId">
                <QuestionCard :item="item" :question-type="questionType" :show-star="showStar"
                  :show-favorite-status="showFavoriteStatus" :show-collect-actions="showCollectActions"
                  :show-study-stats="showStudyStats" :uncollect-loading="uncollectLoading[getItemKey(item)]"
                  @view-detail="handleViewDetail" @toggle-star="toggleStar" @uncollect="handleUncollect" />
              </el-col>
            </el-row>

            <!-- 分页 -->
            <div class="pagination-section">
              <el-pagination v-model:current-page="searchQuery.pageNum" v-model:page-size="searchQuery.pageSize"
                :page-sizes="[12, 24, 48, 96]" layout="total, sizes, prev, pager, next, jumper" :total="total"
                @size-change="handleSizeChange" @current-change="handleCurrentChange" />
            </div>
          </div>
        </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MyQuestion' })
import { ref, reactive, onMounted, onUnmounted, onBeforeUnmount, onDeactivated, computed, watch, nextTick } from 'vue'
import { getCurrentInstance } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Star } from '@element-plus/icons-vue'

import QuestionDetailDialog from './QuestionDetailDialog.vue'
import QuestionHeader from './QuestionHeader.vue'
import CommonFilterSidebar from '@/components/CommonFilterSidebar/index.vue'
import QuestionCard from './QuestionCard.vue'
import AiAnalysisDialog from '@/components/AiAnalysisDialog/index.vue'

const { proxy } = getCurrentInstance()
const router = useRouter()
const route = useRoute()

const props = defineProps({
  questionType: {
    type: String,
    default: 'favorite',
    validator: (value) => ['favorite', 'wrong', 'marked'].includes(value)
  },
  headerTitle: {
    type: String,
    default: ''
  },
  showStarFilter: {
    type: Boolean,
    default: true
  },
  showFavoriteStatusFilter: {
    type: Boolean,
    default: true
  },
  showStar: {
    type: Boolean,
    default: true
  },
  showFavoriteStatus: {
    type: Boolean,
    default: true
  },
  showCollectActions: {
    type: Boolean,
    default: true
  },
  showStudyStats: {
    type: Boolean,
    default: true
  },
  emptyActionText: {
    type: String,
    default: '去发现题目'
  },
  apiConfig: {
    type: Object,
    default: () => ({})
  },
  questionBanks: {
    type: Array,
    default: () => []
  },
  userStore: {
    type: Object,
    default: null
  },
  /** 进入页面后要自动定位并打开的题目 id（供「学习统计 → 易错 TOP5」等外部跳转使用） */
  focusQuestionId: {
    type: [String, Number],
    default: null
  }
})

const questionTypes = [
  { value: 1, label: '单选题' },
  { value: 2, label: '多选题' },
  { value: 3, label: '判断题' },
  { value: 4, label: '填空题' },
  { value: 5, label: '简答题' },
  { value: 6, label: '组合题' }
]

const difficultyOptions = [
  { value: 1, label: '简单', class: 'difficulty-1' },
  { value: 2, label: '中等', class: 'difficulty-2' },
  { value: 3, label: '困难', class: 'difficulty-3' },
  { value: 4, label: '极难', class: 'difficulty-4' }
]

// 默认筛选值（单选项统一改成数组，支持多选）
const defaultFilter = computed(() => ({
  bankId: null,
  isStarred: [],
  favoriteStatus: props.questionType === 'favorite' ? [1] : [],
  difficulty: [],
  questionType: [],
  isMastered: props.questionType === 'wrong' ? [0] : [],
  markedType: [],
  createRange: null
}))

// 筛选配置
const filterGroups = computed(() => {
  const groups = []

  // 题库筛选
  if (props.questionBanks?.length > 0) {
    groups.push({
      key: 'bankId',
      label: '所属题库',
      type: 'select',
      options: props.questionBanks.map(b => ({ value: b.id, label: b.bankName }))
    })
  }

  // 题型筛选
  groups.push({
    key: 'questionType',
    label: '题型',
    type: 'checkbox',
    options: questionTypes
  })

  // 难度筛选
  groups.push({
    key: 'difficulty',
    label: '难度',
    type: 'checkbox',
    options: difficultyOptions
  })

  // 标星状态（多选）
  if (props.showStarFilter) {
    groups.push({
      key: 'isStarred',
      label: '标星状态',
      type: 'checkbox',
      options: [
        { value: 1, label: '已标星' },
        { value: 0, label: '未标星' }
      ]
    })
  }

  // 掌握状态（错题页面，多选）
  if (props.questionType === 'wrong') {
    groups.push({
      key: 'isMastered',
      label: '掌握状态',
      type: 'checkbox',
      options: [
        { value: 0, label: '未掌握' },
        { value: 1, label: '已掌握' }
      ]
    })
  }

  // 斩题类型（多选）
  if (props.questionType === 'marked') {
    groups.push({
      key: 'markedType',
      label: '斩题类型',
      type: 'checkbox',
      options: [
        { value: 1, label: '错题' },
        { value: 2, label: '难题' },
        { value: 3, label: '重点' },
        { value: 4, label: '易错' },
        { value: 5, label: '技巧' }
      ]
    })
  }

  // 时间筛选（题库模块同一套组件）
  groups.push({
    key: 'createRange',
    label: props.questionType === 'wrong' ? '错题时间' : (props.questionType === 'marked' ? '标记时间' : '收藏时间'),
    type: 'dateRange'
  })

  return groups
})

const loading = ref(true)
const total = ref(0)
const allQuestions = ref([])
const questions = ref([])
const detailDialogVisible = ref(false)
const isFullscreen = ref(false)
const uncollectLoading = ref({})
const filterSidebarRef = ref<any>(null)
const headerRef = ref(null)
const headerHeight = ref(0)
// 内嵌筛选按钮状态：面板是否展开 / 是否有生效的筛选条件
const filterOpen = ref(false)
const filterActive = ref(false)

const currentFavoriteQuestion = ref(null)
const currentQuestionDetail = ref(null)
const currentQuestionIndex = ref(0)
const dialogQuestions = ref([])

const selectedAnswer = ref('')
const subFillBlankAnswers = ref({})
const subEssayAnswers = ref({})
const answers = ref([])

const searchQuery = reactive({
  pageNum: 1,
  pageSize: 12,
  keyword: '',
  userId: null
})

const filterForm = reactive({
  bankId: null,
  isStarred: [],
  favoriteStatus: props.questionType === 'favorite' ? [1] : [],
  difficulty: [],
  questionType: [],
  isMastered: props.questionType === 'wrong' ? [0] : [],
  markedType: [],
  createRange: null
})

const hasAutoAppliedFilter = ref(false)

// AI 解析相关状态
const showAiAnalysis = ref(false)
const aiAnalysisCache = ref(new Map())
const currentAiQuestion = ref({
  id: null,
  text: '',
  type: '',
  options: '',
  answer: '',
  cachedContent: '',
  subQuestions: [] as any[]
})

const emit = defineEmits([
  'view-detail',
  'toggle-star',
  'uncollect',
  'refresh',
  'empty-action',
  'mark',
  'add-note',
  'report',
  /* 条数变化（首屏回来 / 搜索 / 筛选 / 删除后）——外层分组壳用它更新顶栏计数 */
  'total-change'
])

/*
 * 条数上报
 * ----------------------------------------------------------------------------
 * 用户 2026-10-19 两个连续反馈：
 *   ①「第一次点题目管理，默认进题目收藏，但上方标题没有题目数，必须点别的 tab 才出现」
 *   ②「xx 道题 会连续刷新两遍」
 *
 * ① 的根因：外层只在"切 tab"这个时机去读一次实例上的 total，
 *    首屏请求还没回来 —— 读到 0，之后再没有第二次机会。
 *    所以改成子页面主动上报。
 *
 * ② 的根因：加载过程中 total 会被改写很多次，而且不是单调的 ——
 *    三个分组并行拉数据，谁先回来谁先报；`applySearchAndFilter()` 中途还会把
 *    total 写回 0 再写回 N。实测一次进入页面总共上报 9 次：
 *
 *      "" → "" → "" → "" → "6 道题" → "6 道题" → "" → "6 道题" → "6 道题"
 *
 *    用户看到的就是数字「闪两下」。
 *
 * 所以这里上报的是**带加载态的结构**，而不是裸数字：
 *    { total, loading }
 * 外层据此区分「还不知道」和「确实是 0 条」，
 * 加载中只更新内部记录、不往顶栏推字，收敛后只推一次。
 */
watch(
  [total, loading],
  () => {
    emit('total-change', {
      total: Number(total.value) || 0,
      loading: loading.value
    })
  },
  { immediate: true }
)

const emptyText = computed(() => {
  const textMap = {
    favorite: '暂无收藏的题目',
    wrong: '暂无错题记录',
    marked: '暂无斩题记录'
  }
  return textMap[props.questionType] || '暂无数据'
})

const getCurrentUserId = () => {
  if (!props.userStore) {
    return null
  }
  const userId = props.userStore.id || props.userStore.userId || props.userStore.user?.userId
  if (!userId) {
    return null
  }
  return userId
}

const getItemKey = (item) => {
  if (props.questionType === 'wrong') {
    return item.errorId || item.bankId
  }
  return item.favoriteId || item.wrongId || item.markedId || item.bankId
}

// 测量 header 高度（与题库模块一致，只用 offsetHeight）
const updateHeaderHeight = () => {
  nextTick(() => {
    if (headerRef.value) {
      headerHeight.value = headerRef.value.offsetHeight
    }
  })
}

onMounted(() => {
  if (!props.questionBanks || props.questionBanks.length === 0) {
  }
  initData()
  updateHeaderHeight()
  window.addEventListener('resize', updateHeaderHeight)

  watch(
    () => route.query.bankId,
    (newBankId) => {
      hasAutoAppliedFilter.value = false
      if (newBankId) {
        setTimeout(() => {
          applyBankIdFilter(newBankId)
        }, 100)
      } else {
        filterForm.bankId = null
        hasAutoAppliedFilter.value = false
        handleFilterChange({ bankId: null })
      }
    },
    { immediate: true }
  )
})

onUnmounted(() => {
  window.removeEventListener('resize', updateHeaderHeight)
})

const initData = () => {
  loading.value = true
  if (props.questionType === 'favorite' && props.apiConfig.listApi) {
    initFavoriteData()
  } else if (props.questionType === 'wrong' && props.apiConfig.listApi) {
    initWrongData()
  } else if (props.questionType === 'marked' && props.apiConfig.listApi) {
    initMarkedData()
  } else {
    loading.value = false
  }
}

const initMarkedData = async () => {
  try {
    const userId = getCurrentUserId()
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      loading.value = false
      return
    }
    const response = await props.apiConfig.listApi({
      pageNum: 1,
      pageSize: 100,
      userId: userId,
      markedStatus: 1
    })
    if (response.code === 200) {
      allQuestions.value = response.rows || []
      total.value = allQuestions.value.length
      if (allQuestions.value.length > 0) {
        questions.value = [...allQuestions.value]
        applySearchAndFilter()
      }
    } else {
      proxy.$modal.msgError(response.msg || '获取斩题数据失败')
    }
  } catch (error) {
    proxy.$modal.msgError('加载斩题数据失败')
  } finally {
    loading.value = false
  }
}

const initFavoriteData = async () => {
  try {
    const userId = getCurrentUserId()
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      loading.value = false
      return
    }
    const response = await props.apiConfig.listApi({
      pageNum: 1,
      pageSize: 100,
      userId: userId,
      favoriteStatus: 1
    })
    if (response.code === 200) {
      allQuestions.value = response.rows || []
      total.value = allQuestions.value.length
      if (allQuestions.value.length > 0) {
        questions.value = [...allQuestions.value]
        applySearchAndFilter()
      }
    } else {
      proxy.$modal.msgError(response.msg || '获取数据失败')
    }
  } catch (error) {
    proxy.$modal.msgError('加载数据失败')
  } finally {
    loading.value = false
  }
}

const initWrongData = async () => {
  try {
    const userId = getCurrentUserId()
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      loading.value = false
      return
    }
    const response = await props.apiConfig.listApi({
      pageNum: 1,
      pageSize: 100,
      userId: userId,
      status: 1,
      // null 会被 axios 丢弃 → 服务端不做「是否已掌握」限制，交给前端多选筛选
      isMastered: null
    })
    if (response.code === 200) {
      allQuestions.value = response.rows || []
      total.value = allQuestions.value.length
      if (allQuestions.value.length > 0) {
        questions.value = [...allQuestions.value]
        applySearchAndFilter()
      }
    } else {
      proxy.$modal.msgError(response.msg || '获取错题数据失败')
    }
  } catch (error) {
    proxy.$modal.msgError('加载错题数据失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.questionBanks, (newBanks) => {
  if (route.query.bankId && newBanks.length > 0) {
    hasAutoAppliedFilter.value = false
    setTimeout(() => {
      applyBankIdFilter(route.query.bankId)
    }, 100)
  }
}, { immediate: true })

const applyBankIdFilter = async (bankId) => {
  if (!bankId) {
    return
  }
  const bankIdNum = Number(bankId)
  if (filterForm.bankId === bankIdNum) {
    return
  }
  hasAutoAppliedFilter.value = false
  filterForm.bankId = bankIdNum
  hasAutoAppliedFilter.value = true
  await nextTick()
  handleFilterChange({ bankId: bankIdNum })
  if (allQuestions.value && allQuestions.value.length > 0) {
    applySearchAndFilter()
  }
}

/** 按当前关键词 + 筛选条件计算出完整列表（不含分页） */
const buildFilteredList = () => {
  if (!allQuestions.value || allQuestions.value.length === 0) {
    return []
  }
  let filtered = [...allQuestions.value]
  if (searchQuery.keyword && searchQuery.keyword.trim()) {
    const keyword = searchQuery.keyword.toLowerCase().trim()
    filtered = filtered.filter(item => {
      const questionText = (item.questionDetail?.questionText || '').toLowerCase()
      const matches = questionText.includes(keyword)
      return matches
    })
  }
  if (filterForm.bankId) {
    filtered = filtered.filter(item => item.bankId === filterForm.bankId)
  }
  if (filterForm.isStarred?.length > 0 && props.questionType === 'favorite') {
    filtered = filtered.filter(item => filterForm.isStarred.includes(item.isStarred ? 1 : 0))
  }
  if (filterForm.favoriteStatus?.length > 0 && props.questionType === 'favorite') {
    filtered = filtered.filter(item => filterForm.favoriteStatus.includes(item.favoriteStatus ? 1 : 0))
  }
  if (filterForm.isMastered?.length > 0 && (props.questionType === 'wrong' || props.questionType === 'marked')) {
    filtered = filtered.filter(item => filterForm.isMastered.includes(item.isMastered ? 1 : 0))
  }
  if (filterForm.markedType?.length > 0 && props.questionType === 'marked') {
    filtered = filtered.filter(item => filterForm.markedType.includes(item.markedType))
  }
  if (filterForm.difficulty.length > 0) {
    filtered = filtered.filter(item => {
      const difficulty = item.questionDetail?.difficulty
      const matches = difficulty && filterForm.difficulty.includes(difficulty)
      return matches
    })
  }
  if (filterForm.questionType.length > 0) {
    filtered = filtered.filter(item => {
      const questionType = item.questionDetail?.questionType
      const matches = questionType && filterForm.questionType.includes(questionType)
      return matches
    })
  }
  // 时间范围：收藏时间 / 错题时间 / 标记时间
  if (filterForm.createRange?.length === 2) {
    const [start, end] = filterForm.createRange
    const startTs = new Date(`${start} 00:00:00`).getTime()
    const endTs = new Date(`${end} 23:59:59`).getTime()
    filtered = filtered.filter(item => {
      const time = props.questionType === 'wrong'
        ? (item.errorTime || item.lastErrorTime || item.createTime)
        : item.createTime
      if (!time) return false
      const ts = new Date(time).getTime()
      return ts >= startTs && ts <= endTs
    })
  }
  return filtered
}

const applySearchAndFilter = () => {
  const filtered = buildFilteredList()
  if (filtered.length === 0) {
    questions.value = []
    total.value = 0
    return
  }
  total.value = filtered.length
  const startIndex = (searchQuery.pageNum - 1) * searchQuery.pageSize
  const endIndex = startIndex + searchQuery.pageSize
  questions.value = filtered.slice(startIndex, endIndex)
}

const handleViewDetail = async (item) => {
  currentFavoriteQuestion.value = item
  currentQuestionIndex.value = 0
  dialogQuestions.value = [item]
  try {
    if (props.apiConfig.detailApi && item.questionId) {
      const response = await props.apiConfig.detailApi(item.questionId)
      if (response.code === 200) {
        let questionData = response.data
        if (questionData.transformed) {
          currentQuestionDetail.value = {
            ...questionData.transformed,
            showAnalysis: true,
            id: item.questionId,
            questionType: questionData.questionType || item.questionDetail?.questionType,
            bankName: item.bankDetail?.bankName,
            difficulty: item.questionDetail?.difficulty
          }
        } else if (props.apiConfig.transformQuestion) {
          const transformed = props.apiConfig.transformQuestion(questionData)
          currentQuestionDetail.value = {
            ...transformed,
            showAnalysis: true,
            id: item.questionId,
            questionType: questionData.questionType || item.questionDetail?.questionType,
            bankName: item.bankDetail?.bankName,
            difficulty: item.questionDetail?.difficulty
          }
        } else {
          currentQuestionDetail.value = {
            ...questionData,
            showAnalysis: true,
            id: item.questionId,
            bankName: item.bankDetail?.bankName,
            difficulty: item.questionDetail?.difficulty
          }
        }
        detailDialogVisible.value = true
        resetAnswerState()
      }
    } else {
      let questionData = item.questionDetail || {}
      if (questionData.transformed) {
        currentQuestionDetail.value = {
          ...questionData.transformed,
          showAnalysis: true,
          id: item.questionId,
          questionType: questionData.questionType,
          bankName: item.bankDetail?.bankName,
          difficulty: item.questionDetail?.difficulty
        }
      } else {
        if (props.apiConfig.transformQuestion) {
          const transformed = props.apiConfig.transformQuestion(questionData)
          currentQuestionDetail.value = {
            ...transformed,
            showAnalysis: true,
            id: item.questionId,
            questionType: questionData.questionType,
            bankName: item.bankDetail?.bankName,
            difficulty: item.questionDetail?.difficulty
          }
        } else {
          currentQuestionDetail.value = {
            ...questionData,
            showAnalysis: true,
            id: item.questionId,
            bankName: item.bankDetail?.bankName,
            difficulty: item.questionDetail?.difficulty
          }
        }
      }
      detailDialogVisible.value = true
      resetAnswerState()
    }
  } catch (error) {
    proxy.$modal.msgError('加载题目详情失败')
  }
  emit('view-detail', item)
}

const resetAnswerState = () => {
  selectedAnswer.value = ''
  subFillBlankAnswers.value = {}
  subEssayAnswers.value = {}
  answers.value = []
}

const handleSearch = (keyword) => {
  if (!searchQuery) {
    return
  }
  searchQuery.keyword = keyword
  searchQuery.pageNum = 1
  applySearchAndFilter()
}

const handleClearSearch = () => {
  if (!searchQuery) {
    return
  }
  searchQuery.keyword = ''
  searchQuery.pageNum = 1
  applySearchAndFilter()
}

const handleRefresh = () => {
  searchQuery.keyword = ''
  searchQuery.pageNum = 1
  filterForm.bankId = null
  filterForm.isStarred = []
  filterForm.favoriteStatus = props.questionType === 'favorite' ? [1] : []
  filterForm.difficulty = []
  filterForm.questionType = []
  filterForm.isMastered = props.questionType === 'wrong' ? [0] : []
  filterForm.markedType = []
  filterForm.createRange = null
  hasAutoAppliedFilter.value = false
  if (props.questionType === 'favorite' && props.apiConfig.listApi) {
    initFavoriteData()
  } else if (props.questionType === 'wrong' && props.apiConfig.listApi) {
    initWrongData()
  } else if (props.questionType === 'marked' && props.apiConfig.listApi) {
    initMarkedData()
  }
  emit('refresh')
}

const handleFilterChange = (newFilter) => {
  Object.assign(filterForm, newFilter)
  searchQuery.pageNum = 1
  applySearchAndFilter()
}

const resetFilters = () => {
  filterForm.bankId = null
  filterForm.isStarred = []
  filterForm.favoriteStatus = props.questionType === 'favorite' ? [1] : []
  filterForm.difficulty = []
  filterForm.questionType = []
  filterForm.isMastered = props.questionType === 'wrong' ? [0] : []
  filterForm.markedType = []
  filterForm.createRange = null
  hasAutoAppliedFilter.value = false
  searchQuery.keyword = ''
  searchQuery.pageNum = 1
  if (props.questionType === 'favorite' && props.apiConfig.listApi) {
    initFavoriteData()
  } else if (props.questionType === 'wrong' && props.apiConfig.listApi) {
    initWrongData()
  } else if (props.questionType === 'marked' && props.apiConfig.listApi) {
    initMarkedData()
  }
}

// 内嵌在搜索框里的筛选按钮：切换下方筛选面板
const toggleFilterSidebar = () => {
  filterSidebarRef.value?.toggleCollapse?.()
}

// 面板展开/收起同步到按钮态（事件值为「是否已收起」）
const handleFilterCollapseChange = (collapsed) => {
  filterOpen.value = !collapsed
}

// 是否有生效的筛选条件（按钮小圆点）
const handleFilterActiveChange = (active) => {
  filterActive.value = !!active
}

const closeDetailDialog = () => {
  detailDialogVisible.value = false
  isFullscreen.value = false
  currentQuestionDetail.value = null
  currentFavoriteQuestion.value = null
  dialogQuestions.value = []
  resetAnswerState()
}

// 关掉弹窗时，必须连同「Element Plus 的 body 滚动锁」一起放掉。
//
// ⚠️ 本页是 keep-alive 缓存的（见 views/front/myQuestion/index.vue 里的 <keep-alive>）。
//    带着**打开的详情弹窗**从浏览器回退到「学习统计」时，组件走的是 deactivated
//    而不是 unmounted —— detailDialogVisible 会原样保留成 true，el-dialog 的
//    useLockscreen 就永远等不到 visible 变 false，document.body 上的
//    `el-popup-parent--hidden`（theme-chalk 里是 overflow:hidden）因此一直挂着，
//    表现为回到上一页后整页滚不动。这里在失活 / 卸载时把弹窗收掉。
onDeactivated(() => {
  if (detailDialogVisible.value) closeDetailDialog()
})

// 卸载同样收一次：不依赖上面那条（比如页面被移出 keep-alive 缓存时）
onBeforeUnmount(() => {
  if (detailDialogVisible.value) closeDetailDialog()
})

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value
}

const prevQuestionInDialog = () => {
  if (currentQuestionIndex.value > 0) {
    currentQuestionIndex.value--
    loadQuestionForDialog(currentQuestionIndex.value)
  }
}

const nextQuestionInDialog = () => {
  if (currentQuestionIndex.value < dialogQuestions.value.length - 1) {
    currentQuestionIndex.value++
    loadQuestionForDialog(currentQuestionIndex.value)
  }
}

const loadQuestionForDialog = async (index) => {
  const item = dialogQuestions.value[index]
  if (item && props.apiConfig.detailApi) {
    try {
      const response = await props.apiConfig.detailApi(item.questionId)
      if (response.code === 200) {
        const data = response.data.transformed || response.data
        currentQuestionDetail.value = {
          ...data,
          bankName: item.bankDetail?.bankName,
          difficulty: item.questionDetail?.difficulty
        }
        resetAnswerState()
      }
    } catch (error) {
    }
  }
}

const toggleStar = async (item) => {
  if (props.questionType === 'wrong' || props.questionType === 'marked') {
    proxy.$modal.msgInfo(`${props.questionType === 'wrong' ? '错题' : '斩题'}暂不支持标星`)
    return
  }
  const userId = getCurrentUserId()
  if (!userId) {
    proxy.$modal.msgWarning('请先登录')
    return
  }
  if (props.apiConfig.updateApi) {
    try {
      const result = await props.apiConfig.updateApi({
        favoriteId: item.favoriteId,
        userId: userId,
        isStarred: item.isStarred ? 0 : 1
      })
      if (result.code === 200) {
        item.isStarred = !item.isStarred
        proxy.$modal.msgSuccess(item.isStarred ? '已标星' : '已取消标星')
        const index = allQuestions.value.findIndex(q => getItemKey(q) === getItemKey(item))
        if (index !== -1) {
          allQuestions.value[index].isStarred = item.isStarred
        }
      }
    } catch (error) {
      proxy.$modal.msgError('操作失败')
    }
  }
  emit('toggle-star', item)
}

const handleUncollect = (item) => {
  const userId = getCurrentUserId()
  if (!userId) {
    proxy.$modal.msgWarning('请先登录')
    return
  }
  uncollectLoading.value[getItemKey(item)] = true
  const confirmMessage = props.questionType === 'wrong'
    ? '确定要移除这道错题记录吗？移除后错误次数将被重置。'
    : props.questionType === 'marked'
      ? '确定要移除这道斩题记录吗？'
      : '确定要取消收藏这道题目吗？'
  const confirmTitle = props.questionType === 'wrong'
    ? '移除错题确认'
    : props.questionType === 'marked'
      ? '移除斩题确认'
      : '取消收藏确认'
  proxy.$modal.confirm(
    confirmMessage,
    confirmTitle,
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).then(() => {
    if (props.apiConfig.deleteApi) {
      let id
      if (props.questionType === 'wrong') {
        id = item.errorId
      } else if (props.questionType === 'marked') {
        id = item.markedId
      } else {
        id = item.favoriteId || item.bankId
      }
      return props.apiConfig.deleteApi(id, { userId })
    }
  }).then(result => {
    if (result.code === 200) {
      const successMessage = props.questionType === 'wrong'
        ? '已移除错题'
        : props.questionType === 'marked'
          ? '已移除斩题'
          : '已取消收藏'
      proxy.$modal.msgSuccess(successMessage)
      const index = allQuestions.value.findIndex(q => getItemKey(q) === getItemKey(item))
      if (index !== -1) {
        allQuestions.value.splice(index, 1)
      }
      applySearchAndFilter()
      if (questions.value.length === 0 && searchQuery.pageNum > 1) {
        searchQuery.pageNum = Math.max(1, searchQuery.pageNum - 1)
        applySearchAndFilter()
      }
    } else {
      proxy.$modal.msgError(result.msg || '操作失败')
    }
  }).catch(error => {
    if (error !== 'cancel') {
      proxy.$modal.msgError('操作失败')
    }
  }).finally(() => {
    uncollectLoading.value[getItemKey(item)] = false
  })
  emit('uncollect', item)
}

const handleEmptyAction = () => {
  emit('empty-action')
}

const handleSizeChange = (val) => {
  searchQuery.pageSize = val
  searchQuery.pageNum = 1
  applySearchAndFilter()
}

const handleCurrentChange = (val) => {
  searchQuery.pageNum = val
  applySearchAndFilter()
}

const selectOption = (index) => {
  selectedAnswer.value = index
}

const selectSubOption = (subIndex, optionIndex) => {
  if (!answers.value[currentQuestionIndex.value]) {
    answers.value[currentQuestionIndex.value] = {}
  }
  answers.value[currentQuestionIndex.value][subIndex] = optionIndex
}

const updateSubFillBlankAnswer = (subIndex, value) => {
  subFillBlankAnswers.value[subIndex] = value
}

const updateSubEssayAnswer = (subIndex, value) => {
  subEssayAnswers.value[subIndex] = value
}

const markQuestion = () => {
  proxy.$modal.msgInfo('斩题功能开发中')
  emit('mark')
}

const addNote = () => {
  proxy.$modal.msgInfo('笔记功能开发中')
  emit('add-note')
}

const reportQuestion = () => {
  proxy.$modal.msgInfo('举报功能开发中')
  emit('report')
}

// 从多个候选值里取第一个「有内容」的（undefined / null / 空串 / 空数组都跳过）
const firstNonEmpty = (...vals: any[]) => {
  for (const v of vals) {
    if (v === undefined || v === null) continue
    if (typeof v === 'string' && v.trim() === '') continue
    if (Array.isArray(v) && v.length === 0) continue
    return v
  }
  return ''
}

// AI 解析功能
//
// ⚠️ 题干字段名在两条链路上是**不一样**的，这里必须都认：
//   · 列表接口给的 item.questionDetail —— 字段名 questionText（原始题目表字段）；
//   · 详情接口经 transformQuestionForDisplay() 转出来的 currentQuestionDetail
//     —— 字段名 question（转换器里写的是 `question: q.questionText`），
//     答案也从 answer 变成了 correctAnswer。
// 旧实现只读 questionText / answer，于是从详情弹窗点「AI 解析」时题干恒为空串，
// 发给 ds-free（DeepSeek 网页版）的提示词里「## 题目」那一节整段是空的
// —— 就是「题干缺失」。
// 阅读理解 / 完形填空的正文在 mainContent 里（此时 question 是空串），一并兜住。
const openAiAnalysis = (questionDetail) => {
  const source = questionDetail || currentQuestionDetail.value
  if (!source) return

  const questionId = firstNonEmpty(source.id, currentQuestionDetail.value?.id)
  if (!questionId) {
    proxy.$modal.msgError('题目信息不完整，无法发起 AI 解析')
    return
  }

  // 题干：questionText / question_text / question 三种名字都试；都空则退回文章正文
  const stemRaw = firstNonEmpty(source.questionText, source.question_text, source.question)
  const stem = typeof stemRaw === 'string' ? stemRaw : String(stemRaw ?? '')
  const question = stem.trim() ? stem : String(firstNonEmpty(source.mainContent) ?? '')

  const questionType = getQuestionTypeName(
    firstNonEmpty(source.questionType, source.question_type, currentQuestionDetail.value?.questionType)
  )
  const options = firstNonEmpty(source.options, currentQuestionDetail.value?.options)
  const answer = firstNonEmpty(
    source.answer,
    source.correctAnswer,
    currentQuestionDetail.value?.answer,
    currentQuestionDetail.value?.correctAnswer
  )

  // 检查缓存
  let cachedContent = ''
  if (aiAnalysisCache.value.has(questionId)) {
    cachedContent = aiAnalysisCache.value.get(questionId)
  }

  // 设置当前题目信息
  currentAiQuestion.value = {
    id: questionId,
    text: question,
    type: questionType,
    options: typeof options === 'string' ? options : JSON.stringify(options),
    answer: answer as string,
    cachedContent: cachedContent,
    // 组合题小题（阅读理解/完形填空）：供 AI 解析时连同小题图一并发送
    subQuestions: normalizeAiSubQuestions(source)
  }

  showAiAnalysis.value = true
}

/**
 * 归一组合题小题为 AI 解析所需形状 `[{question, options, correctAnswer, type}]`。
 * 兼容两种来源：后端详情(subQuestions 里是 questionText/answer)
 * 与 transformQuestionForDisplay 产物(question/correctAnswer)。
 */
function normalizeAiSubQuestions(source: any): any[] {
  const subs = source?.subQuestions || source?.questionSubList || []
  if (!Array.isArray(subs)) return []
  return subs.map((sq: any) => ({
    question: sq.question || sq.questionText || sq.question_text || '',
    options: sq.options ?? [],
    correctAnswer: sq.correctAnswer ?? sq.answer,
    type: sq.type || sq.questionType || sq.question_type
  }))
}

// 获取题型名称（同时接受数字题型与转换器产出的字符串题型）
const getQuestionTypeName = (type) => {
  const typeMap = {
    1: '单选题',
    2: '多选题',
    3: '判断题',
    4: '填空题',
    5: '简答题',
    6: '组合题',
    7: '组合题'
  }
  const strMap = {
    single: '单选题',
    multiple: '多选题',
    truefalse: '判断题',
    fillblank: '填空题',
    essay: '简答题',
    readingComprehension: '组合题',
    cloze: '组合题'
  }
  const key = String(type ?? '')
  return typeMap[key] || strMap[key] || '未知题型'
}

// 更新 AI 缓存
const updateAiCache = ({ questionId, content }) => {
  aiAnalysisCache.value.set(questionId, content)
}

// ===== 外部跳转定位：滚动到指定题目卡片并打开详情 =====
/** 待定位的题目 id（数据加载完成后才执行） */
const pendingFocusId = ref(null)

/** 在列表中找到该题 → 翻到它所在页 → 滚动到卡片 → 打开详情弹窗 */
const focusOnQuestion = async (id) => {
  if (!id) return
  const key = String(id)

  const list = buildFilteredList()
  const item = list.find(it => String(it.questionId) === key)

  if (!item) {
    // 不在当前列表范围内（被筛选条件挡掉、或属于「已掌握」而列表默认只看未掌握）
    // → 交给后端按 questionId 精确取一条，能拿到就打开
    try {
      const res = await props.apiConfig.listApi?.({
        pageNum: 1,
        pageSize: 1,
        questionId: id,
        isMastered: null // null 会被 axios 丢弃 → 不限制是否已掌握
      })
      const hit = res?.rows?.[0]
      if (hit) {
        proxy.$modal.msgInfo('该题不在当前筛选范围内，已直接打开详情')
        await handleViewDetail(hit)
        return
      }
    } catch (e) {
      // 忽略，走下面的降级
    }
    await handleViewDetail({ questionId: id })
    proxy.$modal.msgInfo('该题不在当前列表中，已直接打开详情')
    return
  }

  const targetPage = Math.floor(list.indexOf(item) / searchQuery.pageSize) + 1
  if (searchQuery.pageNum !== targetPage) {
    searchQuery.pageNum = targetPage
    applySearchAndFilter()
  }

  await nextTick()
  const el = document.querySelector(`.question-list .question-card-col[data-qid="${key}"]`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('is-focused')
    setTimeout(() => el.classList.remove('is-focused'), 2400)
  }
  await handleViewDetail(item)
}

/** 数据加载完成且有待定位 id 时才执行（避免列表还没渲染就去找） */
const tryFocusPending = async () => {
  if (!pendingFocusId.value || loading.value) return
  const id = pendingFocusId.value
  pendingFocusId.value = null
  await nextTick()
  await focusOnQuestion(id)
}

watch(() => props.focusQuestionId, (v) => {
  if (v) {
    pendingFocusId.value = v
    tryFocusPending()
  }
}, { immediate: true })

// 列表加载结束时再尝试一次（外部跳转进入时通常先有 id、后有数据）
watch(loading, (v) => {
  if (!v) tryFocusPending()
})

defineExpose({
  refresh: handleRefresh,
  resetFilters,
  getQuestions: () => questions.value,
  focusQuestion: focusOnQuestion,
  /*
   * 当前列表条数。
   * 供外层（「题目管理」分组壳）把计数推到顶栏 —— 与「题库管理」做法一致：
   * 用户 2026-10-18 要求把内容区那行「xxx  N 个 xxx」合并进顶栏。
   */
  getTotal: () => total.value
})
</script>

<style scoped lang="scss">
.question-card-col {
  margin-bottom: 20px;
}

/* 外部跳转定位到某题时的高亮提示 */
.question-card-col.is-focused {
  :deep(.question-card) {
    border-color: #409eff;
    box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.16);
  }
}

.favorite-container {
  height: 100%;
  padding: 0 16px;  /* 与题库模块一致 */
  position: relative;
  min-height: 100%;
}

.header-wrapper {
  margin-bottom: 20px;

  /* 覆盖 PageHeader 内部的 margin-bottom，与题库模块一致 */
  :deep(.search-area) {
    margin-bottom: 20px;
  }
}

.content-main {
  min-height: 400px;
}

.loading-container {
  background: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.empty-state {
  background: #fff;
  padding: 40px 20px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.pagination-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #e4e7ed;
  display: flex;
  justify-content: center;
}
</style>
