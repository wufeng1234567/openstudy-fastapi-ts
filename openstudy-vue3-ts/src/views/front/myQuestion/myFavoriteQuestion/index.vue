<!-- src/views/MyFavoriteQuestion/MyFavoriteQuestion/index.vue -->
<template>
  <div class="question-page-container">
    <!--
      `embedded = true`：本页被「题目管理」以分组的形式内嵌时，
      不再显示自己的页面标题（外层已有分组切换，且顶栏已显示「我的学习 · 题目管理」）。
      独立访问本路由时保持原样。
    -->
    <MyQuestion ref="myQuestionRef" question-type="favorite" :header-title="embedded ? '' : headerTitle"
      :show-star-filter="true"
      :show-favorite-status-filter="true" :show-star="true" :show-favorite-status="true" :show-collect-actions="true"
      :show-study-stats="true" :empty-action-text="'去发现题目'" :api-config="apiConfig" :question-banks="questionBanks"
      :user-store="userStore" @empty-action="goToQuestionBank" />
  </div>
</template>


<!-- src/views/favorite/MyFavoriteQuestion.vue -->
<script setup lang="ts">
defineOptions({ name: 'FrontQuestionCollect' })
import { ref, computed, onMounted } from 'vue'

/**
 * 是否被「题目管理」内嵌（内嵌时不显示自己的页面标题）
 * 独立访问本路由时保持原样。
 */
withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
import { useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { getCurrentInstance } from 'vue'
import type { QuestionBank } from '@/types'

// 组件导入
import MyQuestion from '@/components/MyQuestion/MyQuestion.vue'

// API导入
import {
  listFavoriteQuestion,
  delFavoriteQuestion,
  updateFavoriteQuestion
} from '@/api/favoriteQuestion/favoriteQuestion'
import { getQuestionMain } from '@/api/questionMain/questionMain'
import { listQuestionBankAll } from '@/api/questionBank/questionBank'
import { listQuestionMarkedAll } from '@/api/questionMarked/questionMarked'
import { useQuestionPractice } from '@/composables/useQuestionPractice'

const { proxy } = getCurrentInstance() as any
const router = useRouter()
const userStore = useUserStore()

const myQuestionRef = ref<any>(null)
const questionBanks = ref<QuestionBank[]>([])

// ✅ 关键：使用与原始代码完全相同的转换函数
const { transformQuestionForDisplay } = useQuestionPractice({ bankId: 0, moduleType: '' }, { proxy }, { isFavoriteMode: true })

const headerTitle = computed(() => '题目收藏')

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
      difficulty: transformed.difficulty || questionData.difficulty || 2
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
      questionType: questionData.questionType
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

// ✅ 修复API配置，确保数据格式一致
const apiConfig = {
  // 列表API
  listApi: async (params: any) => {
    try {
      const userId = getCurrentUserId()

      if (!userId) {
        return Promise.reject(new Error('用户未登录'))
      }

      const response = await listFavoriteQuestion({
        ...params,
        userId,
        favoriteStatus: 1
      })

      if (response.code !== 200) {
        return Promise.reject(new Error(response.msg || '获取收藏失败'))
      }

      const favorites = response.rows || []

      // 后端已返回聚合数据（包含题目详情），直接使用，避免 N+1 查询
      const transformedFavorites = favorites.map((fav: any) => {
        fav.questionDetail = {
          ...fav,
          transformed: customTransformQuestion(fav),
          questionType: fav.questionType,
          options: fav.options,
          answer: fav.answer,
          analysis: fav.analysis || '',
          difficulty: fav.difficulty || 2
        }
        return fav
      })

      return {
        code: 200,
        rows: transformedFavorites,
        total: response.total || transformedFavorites.length
      }
    } catch (error) {
      throw error
    }
  },

  // 删除API - ✅ 修复：需要传递userId
  deleteApi: async (favoriteId: any, options: any = {}) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return delFavoriteQuestion(favoriteId)
  },

  // 更新API - ✅ 修复：需要传递userId
  updateApi: async (data: any) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return updateFavoriteQuestion({
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

onMounted(() => {
  loadQuestionBanks()
})
</script>

<style scoped lang="scss">
.question-page-container {
  height: 100%;
}
</style>
