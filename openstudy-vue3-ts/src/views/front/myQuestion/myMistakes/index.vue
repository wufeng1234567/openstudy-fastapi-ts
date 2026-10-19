<!-- src/views/MyMistakes/MyMistakes/index.vue -->
<template>
  <div class="question-page-container">
    <!-- `embedded`：被「题目管理」内嵌时隐藏自己的标题（外层有分组切换） -->
    <MyQuestion ref="myQuestionRef" question-type="wrong" :header-title="embedded ? '' : headerTitle"
      :show-star-filter="true"
      :show-favorite-status-filter="false" :show-star="true" :show-favorite-status="false" :show-collect-actions="true"
      :show-study-stats="true" :empty-action-text="'暂无错题，去练习'" :api-config="apiConfig" :question-banks="questionBanks"
      :user-store="userStore" :focus-question-id="focusQuestionId" @empty-action="goToQuestionBank"
      @total-change="onTotalChange" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontWrongQuestion' })
import { ref, computed, onMounted } from 'vue'

/** 是否被「题目管理」内嵌（内嵌时不显示自己的页面标题） */
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
import { useRoute, useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { getCurrentInstance } from 'vue'
import type { QuestionBank } from '@/types'

// 组件导入
import MyQuestion from '@/components/MyQuestion/MyQuestion.vue'

// API导入
import {
  listQuestionError,
  updateQuestionError,
  delQuestionError,
  checkUserErrorExists,
  recordOrUpdateError
} from '@/api/questionError/questionError'
import { getQuestionMain } from '@/api/questionMain/questionMain'
import { listQuestionBankAll } from '@/api/questionBank/questionBank'
import { listQuestionMarkedAll } from '@/api/questionMarked/questionMarked'
import { useQuestionPractice } from '@/composables/useQuestionPractice'

const { proxy } = getCurrentInstance() as any
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const myQuestionRef = ref<any>(null)
const questionBanks = ref<QuestionBank[]>([])

/** 外部跳转带进来的题目 id（如「学习统计 → 易错 TOP5」点击）
 *  响应式传给 MyQuestion，由它负责翻页 + 滚动到卡片 + 打开详情弹窗 */
const focusQuestionId = computed(() => route.query.questionId || null)

// ✅ 关键：使用与原始代码完全相同的转换函数
const { transformQuestionForDisplay } = useQuestionPractice({ bankId: 0, moduleType: '' }, { proxy }, { isFavoriteMode: false })

const headerTitle = computed(() => '我的错题')

// ✅ 优化获取用户ID的函数
const getCurrentUserId = (): string | number | null => {
  // user store 中只有 id 字段
  const userId = userStore.id

  if (!userId) {
    return null
  }

  return userId
}

// ✅ 创建与原始代码一致的转换函数
const customTransformQuestion = (questionData: any) => {
  try {
    // ✅ 使用与原始代码完全相同的转换函数
    const transformed = transformQuestionForDisplay(questionData)

    // ✅ 确保转换后的数据包含所有必要字段
    return {
      ...transformed,
      // 确保这些关键字段存在
      id: questionData.id || questionData.questionId,
      // 保留原始题型（数字）
      questionType: questionData.questionType,
      // 确保选项是数组格式
      options: transformed.options || [],
      // 确保有文本内容
      text: transformed.text || questionData.questionText || '',
      // 确保有解析
      analysis: transformed.analysis || questionData.analysis || '',
      // 确保有正确答案
      correctAnswer: transformed.correctAnswer || questionData.answer || '',
      // 确保显示解析
      showAnalysis: true,
      // 保留难度信息
      difficulty: transformed.difficulty || questionData.difficulty || 2,
      // 添加错题特有字段
      errorCount: questionData.errorCount || 1,
      lastErrorTime: questionData.lastErrorTime,
      isMastered: questionData.isMastered || 0
    }
  } catch (error) {
    // 转换失败时返回基本结构
    return {
      id: questionData.id || questionData.questionId,
      type: getQuestionType(questionData.questionType),
      text: questionData.questionText || '',
      options: parseOptions(questionData.options),
      correctAnswer: questionData.answer || '',
      analysis: questionData.analysis || '',
      difficulty: questionData.difficulty || 2,
      showAnalysis: true,
      questionType: questionData.questionType,
      errorCount: questionData.errorCount || 1,
      lastErrorTime: questionData.lastErrorTime,
      isMastered: questionData.isMastered || 0
    }
  }
}

// 解析选项
const parseOptions = (options: any) => {
  if (!options) return []
  try {
    if (typeof options === 'string') {
      return JSON.parse(options)
    } else if (Array.isArray(options)) {
      return options
    }
  } catch (e) {
  }
  return []
}

// 获取题型字符串
const getQuestionType = (type: any) => {
  const typeMap: Record<string, string> = {
    1: 'single',
    2: 'multiple',
    3: 'judge',
    4: 'fill',
    5: 'essay',
    6: 'composite'
  }
  return typeMap[type] || 'single'
}

// ✅ 错题API配置
const apiConfig = {
  // 列表API
  listApi: async (params: any) => {
    try {
      const userId = getCurrentUserId()

      if (!userId) {
        return Promise.reject(new Error('用户未登录'))
      }

      const response = await listQuestionError({
        ...params,
        userId,
        status: 1, // 只查询活跃状态的错题
        // 默认只看未掌握的错题；显式传 null 时不限制（供「定位某道题」的兜底查询使用）
        isMastered: params.isMastered === undefined ? 0 : params.isMastered
      })

      if (response.code !== 200) {
        return Promise.reject(new Error(response.msg || '获取错题失败'))
      }

      const errors = response.rows || []

      // 后端已返回聚合数据（包含题目详情），直接使用，避免 N+1 查询
      const transformedErrors = errors.map((error: any) => {
        error.questionDetail = {
          ...error,
          transformed: customTransformQuestion(error),
          questionType: error.questionType,
          options: error.options,
          answer: error.answer,
          analysis: error.analysis || '',
          difficulty: error.difficulty || 2
        }
        return error
      })

      return {
        code: 200,
        rows: transformedErrors,
        total: response.total || transformedErrors.length
      }
    } catch (error) {
      throw error
    }
  },

  // 删除API - 移除错题
  deleteApi: async (errorId: any, options: any = {}) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return delQuestionError(errorId)
  },

  // 更新API - 更新错题状态（如标记为已掌握）
  updateApi: async (data: any) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return updateQuestionError({
      ...data,
      userId: userId
    })
  },

  // 详情API - ✅ 关键：确保与原始代码的数据格式一致
  detailApi: async (questionId: any) => {
    try {
      const response = await getQuestionMain(questionId)
      if (response.code === 200) {
        const questionData = response.data

        // ✅ 使用与原始代码相同的转换函数
        const transformed = transformQuestionForDisplay(questionData)

        return {
          ...response,
          data: {
            // 保留原始数据
            ...questionData,
            // 添加转换后的数据（与原始代码保持一致）
            transformed: {
              ...transformed,
              // 确保有ID
              id: questionId,
              // 确保有题型（数字）
              questionType: questionData.questionType,
              // 确保显示解析
              showAnalysis: true,
              // 确保有难度
              difficulty: questionData.difficulty || 2,
              // 确保有解析内容
              analysis: questionData.analysis || ''
            }
          }
        }
      }
      return response
    } catch (error) {
      throw error
    }
  },

  // ✅ 关键：提供转换函数给MyQuestion组件使用
  transformQuestion: customTransformQuestion
}

// 加载题库列表
const loadQuestionBanks = async () => {
  try {
    const response = await listQuestionBankAll({})
    if (response.code === 200) {
      questionBanks.value = response.data || []
    }
  } catch (error) {
  }
}

const goToQuestionBank = () => {
  router.push('/front/questionPractice')
}

// 暴露方法
defineExpose({
  refresh: () => {
    if (myQuestionRef.value) {
      myQuestionRef.value.refresh()
    }
  },
  /* 供「题目管理」分组壳把条数推到顶栏 */
  getTotal: () => Number(myQuestionRef.value?.getTotal?.() ?? 0)
})

/**
 * 条数上报
 * ----------------------------------------------------------------------------
 * 用户 2026-10-19：首次进「题目管理」顶栏没有题目数，必须点别的 tab 才出现。
 * 根因是外层只在切 tab 时读一次 `getTotal()`，而首屏请求还没回来 —— 读到 0。
 *
 * 改成子页面主动上报：`MyQuestion` 的 total 一变就往上抛，
 * 外层（分组壳）据此更新顶栏，不依赖"某个时机去读实例"。
 */
const emitTotal = defineEmits<{ (e: 'total-change', payload: { total: number; loading: boolean }): void }>()

/**
 * 转发 `MyQuestion` 的条数上报
 * 带上 loading 是让外层能区分「还不知道」和「确实是 0 条」——
 * 裸数字会让顶栏在加载过程中闪出中间的 0（用户 2026-10-19 反馈"连续刷新两遍"）。
 */
function onTotalChange(payload: { total: number; loading: boolean }) {
  emitTotal('total-change', {
    total: Number(payload?.total) || 0,
    loading: !!payload?.loading
  })
}

onMounted(() => {
  loadQuestionBanks()
})
</script>

<style scoped lang="scss">
.question-page-container {
  height: 100%;
}
</style>
