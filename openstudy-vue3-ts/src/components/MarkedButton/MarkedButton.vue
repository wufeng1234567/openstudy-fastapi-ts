<!-- src/components/MarkedButton/MarkedButton.vue -->
<template>
  <div class="marked-button-wrapper">
    <!-- 已斩题状态 -->
    <el-button v-if="markedStatus" :type="markedButtonType" :size="size" :plain="plain" :loading="loading"
      @click="handleUnmark" class="marked-button marked-status">
      <el-icon :size="iconSize">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
          <path fill="currentColor"
            d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448s448-200.6 448-448S759.4 64 512 64m0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372s372 166.6 372 372s-166.6 372-372 372m125.2-465.7l-178 246a7.95 7.95 0 0 1-12.9 0l-85.6-118.9a7.96 7.96 0 0 1 1.7-11.2c4.5-3.2 10.7-2 13.8 2.6l73.7 102.4l150.9-208.6c3-4.2 9-5.2 13.1-2.3c4.1 2.9 5.2 8.9 2.3 13.1z" />
        </svg>
      </el-icon>
      <span class="button-text">{{ markedText }}</span>
    </el-button>

    <!-- 未斩题状态 -->
    <el-button v-else :type="unmarkedButtonType" :size="size" :plain="plain" :loading="loading" @click="handleMark"
      class="marked-button unmarked-status">
      <el-icon :size="iconSize">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
          <path fill="currentColor"
            d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448s448-200.6 448-448S759.4 64 512 64m0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372s372 166.6 372 372s-166.6 372-372 372" />
        </svg>
      </el-icon>
      <span class="button-text">{{ unmarkedText }}</span>
    </el-button>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MarkedButton' })
import { ref, computed, watch, onMounted } from 'vue'
import { getCurrentInstance } from 'vue'
import useUserStore from '@/store/modules/user'
import { ensureLogin } from '@/utils/loginGuard'

// API导入
import {
  addQuestionMarked,
  updateQuestionMarked,
  delQuestionMarked,
  deleteMarkedByUserAndQuestion
} from '@/api/questionMarked/questionMarked'
import { checkMarkedExists } from '@/api/questionMarked/questionMarked'

const { proxy } = getCurrentInstance()
const userStore = useUserStore()

// Props
const props = defineProps({
  // 题目ID
  questionId: {
    type: [Number, String],
    required: true
  },

  // 题库ID
  bankId: {
    type: [Number, String],
    default: null
  },

  // 按钮大小
  size: {
    type: String,
    default: 'default',
    validator: (val) => ['large', 'default', 'small', ''].includes(val)
  },

  // 是否显示为朴素按钮
  plain: {
    type: Boolean,
    default: true
  },

  // 已斩题按钮类型
  markedButtonType: {
    type: String,
    default: 'primary'
  },

  // 未斩题按钮类型
  unmarkedButtonType: {
    type: String,
    default: 'default'
  },

  // 已斩题按钮文字
  markedText: {
    type: String,
    default: '已斩题'
  },

  // 未斩题按钮文字
  unmarkedText: {
    type: String,
    default: '斩题'
  },

  // 是否自动检查斩题状态
  autoCheck: {
    type: Boolean,
    default: true
  },

  // 斩题成功后是否显示提示
  showSuccessMessage: {
    type: Boolean,
    default: true
  },

  // 默认斩题类型
  defaultMarkedType: {
    type: Number,
    default: 2 // 默认难题
  },

  // 默认难度等级
  defaultDifficulty: {
    type: Number,
    default: 2 // 默认中等
  }
})

// Emits
const emit = defineEmits([
  'change',          // 斩题状态变化时触发
  'marked',          // 斩题成功时触发
  'unmarked',        // 取消斩题成功时触发
  'error',           // 操作失败时触发
  'update:marked'    // 支持v-model
])

// 响应式数据
const loading = ref(false)
const markedStatus = ref(false)
const currentMarkedId = ref(null)

// 计算属性
const iconSize = computed(() => {
  const sizeMap = {
    large: 16,
    default: 14,
    small: 12,
    '': 14
  }
  return sizeMap[props.size] || 14
})

// 获取用户ID
const getCurrentUserId = () => {
  const userId = userStore.id || userStore.userId || userStore.user_id

  if (!userId) {
    console.error('无法获取用户ID，store内容:', userStore)
    return null
  }

  return userId
}

// 检查斩题状态 - 添加调试
const checkMarkedStatus = async () => {
  if (!props.autoCheck || !props.questionId) return
  if (!userStore.token || userStore.isGuest) return

  const userId = getCurrentUserId()
  if (!userId) return

  try {
    const response = await checkMarkedExists({
      userId: userId,
      questionId: props.questionId
    })

    if (response.code === 200) {
      // API 契约：{ data: boolean }
      markedStatus.value = !!response.data
      // 触发更新事件
      emit('update:marked', markedStatus.value)
    }
  } catch (error) {
    console.error('检查斩题状态失败:', error)
    console.error('错误详情:', error.response)
  }
}

// 直接斩题（跳过对话框，使用默认值）
const handleMark = async () => {
  if (!(await ensureLogin('斩题'))) return

  const userId = getCurrentUserId()
  if (!userId) {
    proxy.$modal.msgWarning('请先登录')
    return
  }

  loading.value = true

  try {
    const markData: Record<string, any> = {
      userId: userId,
      questionId: props.questionId,
      bankId: props.bankId,
      markedType: props.defaultMarkedType,
      difficultyLevel: props.defaultDifficulty,
      notes: '',
      errorTimesBeforeMark: 0,
      correctTimesBeforeMark: 0,
      reviewCount: 0,
      isMastered: 1,
      markedStatus: 1
    }

    const response = await addQuestionMarked(markData)

    if (response.code === 200) {
      markedStatus.value = true

      if (response.data) {
        currentMarkedId.value = response.data.markedId ||
          response.data.id ||
          response.data.result ||
          null
      }

      if (props.showSuccessMessage) {
        proxy.$modal.msgSuccess('斩题成功')
      }

      emit('change', true)
      emit('marked', {
        markedId: currentMarkedId.value,
        ...markData
      })
      emit('update:marked', true)
    } else {
      proxy.$modal.msgError(response.msg || '斩题失败')
      emit('error', new Error(response.msg || '斩题失败'))
    }
  } catch (error) {
    proxy.$modal.msgError(error.msg || '斩题失败，请稍后重试')
    emit('error', error)
  } finally {
    loading.value = false
  }
}

// 取消斩题
const handleUnmark = async () => {
  if (!(await ensureLogin('取消斩题'))) return

  const userId = getCurrentUserId()
  if (!userId) {
    proxy.$modal.msgWarning('请先登录')
    return
  }

  loading.value = true

  try {
    // 使用 deleteByUserAndQuestion 接口（无需 markedId）
    const response = await deleteMarkedByUserAndQuestion(userId, props.questionId)

    if (response.code === 200) {
      markedStatus.value = false
      currentMarkedId.value = null

      if (props.showSuccessMessage) {
        proxy.$modal.msgSuccess('已取消斩题')
      }

      // 触发事件
      emit('change', false)
      emit('unmarked', null)
      emit('update:marked', false)
    } else {
      proxy.$modal.msgError(response.msg || '取消斩题失败')
      emit('error', new Error(response.msg || '取消斩题失败'))
    }
  } catch (error) {
    console.error('取消斩题失败:', error)
    proxy.$modal.msgError(error.msg || '取消斩题失败，请稍后重试')
    emit('error', error)
  } finally {
    loading.value = false
  }
}

// 手动设置斩题状态（供外部调用）
const setMarkedStatus = (status, markedId = null) => {
  markedStatus.value = !!status
  if (markedId) {
    currentMarkedId.value = markedId
  }
  emit('update:marked', markedStatus.value)
}

// 手动刷新斩题状态
const refreshStatus = () => {
  checkMarkedStatus()
}

// 监听questionId变化
watch(() => props.questionId, () => {
  if (props.autoCheck) {
    checkMarkedStatus()
  }
})

// 组件挂载时检查状态
onMounted(() => {
  if (props.autoCheck) {
    checkMarkedStatus()
  }
})

// 暴露方法供外部调用
defineExpose({
  checkMarkedStatus,
  setMarkedStatus,
  refreshStatus,
  mark: handleMark,
  unmark: handleUnmark
})
</script>

<style scoped lang="scss">
.marked-button-wrapper {
  display: inline-block;

  .marked-button {
    display: flex;
    align-items: center;
    gap: 6px;

    .button-text {
      margin-left: 2px;
    }

    &.marked-status {
      :deep(.el-icon) {
        color: inherit;
      }
    }

    &.unmarked-status {
      :deep(.el-icon) {
        color: #c0c4cc;
      }

      &:hover {
        :deep(.el-icon) {
          color: var(--el-button-hover-text-color);
        }
      }
    }
  }
}
</style>