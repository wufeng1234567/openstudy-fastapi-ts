<!-- src/views/MyMarked/MyMarked/index.vue -->
<template>
  <div class="question-page-container">
    <MyQuestion ref="myQuestionRef" question-type="marked" :header-title="headerTitle" :show-star-filter="false"
      :show-favorite-status-filter="false" :show-star="false" :show-favorite-status="false" :show-collect-actions="true"
      :show-study-stats="true" :empty-action-text="'暂无斩题，去练习'" :api-config="apiConfig" :question-banks="questionBanks"
      :user-store="userStore" @empty-action="goToQuestionBank" />
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontMasteredQuestion' })
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import useUserStore from '@/store/modules/user'
import { getCurrentInstance } from 'vue'
import type { QuestionBank } from '@/types'

// 组件导入
import MyQuestion from '@/components/MyQuestion/MyQuestion.vue'

// API导入
import {
  listQuestionMarked,
  updateQuestionMarked,
  delQuestionMarked
} from '@/api/questionMarked/questionMarked'
import { getQuestionMain } from '@/api/questionMain/questionMain'
import { listQuestionBankAll } from '@/api/questionBank/questionBank'
import { useQuestionPractice } from '@/composables/useQuestionPractice'

const { proxy } = getCurrentInstance() as any
const router = useRouter()
const userStore = useUserStore()

const myQuestionRef = ref<any>(null)
const questionBanks = ref<QuestionBank[]>([])

// 使用转换函数
const { transformQuestionForDisplay } = useQuestionPractice({ bankId: 0, moduleType: '' }, { proxy }, { isFavoriteMode: false })

const headerTitle = computed(() => '我的斩题')

// 获取用户ID
const getCurrentUserId = (): string | number | null => {
  // user store 中只有 id 字段
  const userId = userStore.id

  if (!userId) {
    return null
  }

  return userId
}

// 创建斩题转换函数
const customTransformQuestion = (questionData: any) => {
  try {
    const transformed = transformQuestionForDisplay(questionData)

    return {
      ...transformed,
      id: questionData.id || questionData.questionId,
      questionType: questionData.questionType,
      options: transformed.options || [],
      text: transformed.text || questionData.questionText || '',
      analysis: transformed.analysis || questionData.analysis || '',
      correctAnswer: transformed.correctAnswer || questionData.answer || '',
      showAnalysis: true,
      difficulty: transformed.difficulty || questionData.difficulty || 2,
      // 斩题特有字段
      markedType: questionData.markedType || 2, // 默认难题
      markedStatus: questionData.markedStatus || 1
    }
  } catch (error) {
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
      markedType: questionData.markedType || 2,
      markedStatus: questionData.markedStatus || 1
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

// 获取斩题类型文本
const getMarkedTypeText = (markedType: any) => {
  const typeMap: Record<string, string> = {
    1: '错题',
    2: '难题',
    3: '重点',
    4: '易错',
    5: '技巧'
  }
  return typeMap[markedType] || '斩题'
}

// 斩题API配置
const apiConfig = {
  // 列表API
  listApi: async (params: any) => {
    try {
      const userId = getCurrentUserId()

      if (!userId) {
        return Promise.reject(new Error('用户未登录'))
      }

      const response = await listQuestionMarked({
        ...params,
        userId,
        markedStatus: 1 // 只查询活跃状态的斩题
      })

      if (response.code !== 200) {
        return Promise.reject(new Error(response.msg || '获取斩题失败'))
      }

      const marks = response.rows || []

      // 后端已返回聚合数据（包含题目详情），直接使用，避免 N+1 查询
      const transformedMarks = marks.map((mark: any) => {
        mark.questionDetail = {
          ...mark,
          transformed: customTransformQuestion(mark),
          questionType: mark.questionType,
          options: mark.options,
          answer: mark.answer,
          analysis: mark.analysis || '',
          difficulty: mark.difficulty || 2
        }
        // 添加斩题类型文本
        mark.markedTypeText = getMarkedTypeText(mark.markedType)
        return mark
      })

      return {
        code: 200,
        rows: transformedMarks,
        total: response.total || transformedMarks.length
      }
    } catch (error) {
      throw error
    }
  },

  // 删除API - 移除斩题
  deleteApi: async (markedId: any, options: any = {}) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return delQuestionMarked(markedId)
  },

  // 更新API - 更新斩题状态（如标记为已掌握）
  updateApi: async (data: any) => {
    const userId = getCurrentUserId()
    if (!userId) {
      return Promise.reject(new Error('用户未登录'))
    }

    return updateQuestionMarked({
      ...data,
      userId: userId
    })
  },

  // 详情API
  detailApi: async (questionId: any) => {
    try {
      const response = await getQuestionMain(questionId)
      if (response.code === 200) {
        const questionData = response.data

        const transformed = transformQuestionForDisplay(questionData)

        return {
          ...response,
          data: {
            ...questionData,
            transformed: {
              ...transformed,
              id: questionId,
              questionType: questionData.questionType,
              showAnalysis: true,
              difficulty: questionData.difficulty || 2,
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

  // 提供转换函数给MyQuestion组件使用
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
  }
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