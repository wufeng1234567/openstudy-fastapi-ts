<!-- src/components/FavoriteButton/FavoriteButton.vue -->
<template>
  <el-button
    :class="['favorite-btn', { 'is-collected': isCollected }]"
    :size="size"
    @click="handleCollect"
    :loading="isLoading"
    :disabled="disabled"
    :plain="plain"
  >
    <el-icon><Star /></el-icon>
    {{ buttonText }}
  </el-button>
</template>

<script setup lang="ts">
import { ref, computed, watch, defineProps, defineEmits, onMounted } from 'vue'
import { getCurrentInstance } from 'vue'
import useUserStore from '@/store/modules/user'
import { ensureLogin } from '@/utils/loginGuard'
import { Star } from '@element-plus/icons-vue'

const { proxy } = getCurrentInstance()

// API 根据类型动态导入
import {
  checkBankFavoriteExists,
  addFavoriteBank,
  deleteFavoriteBankByUserAndBank
} from '@/api/favoriteBank/favoriteBank'
import {
  checkQuestionFavoriteExists,
  addFavoriteQuestion,
  deleteFavoriteQuestionByUserAndQuestion
} from '@/api/favoriteQuestion/favoriteQuestion'
import {
  checkNoteFavoriteExists,
  addFavoriteNote,
  deleteFavoriteNoteByUserAndNote
} from '@/api/favoriteNote/favoriteNote'

const props = defineProps({
  // 必需属性
  type: {
    type: String,
    required: true,
    validator: (value) => ['bank', 'question', 'note'].includes(value)
  },
  targetId: {
    type: [Number, String],
    required: true
  },
  
  // 可选属性
  size: {
    type: String,
    default: 'default',
    validator: (value) => ['large', 'default', 'small'].includes(value)
  },
  disabled: {
    type: Boolean,
    default: false
  },
  plain: {
    type: Boolean,
    default: false
  },
  round: {
    type: Boolean,
    default: false
  },
  // 初始收藏状态（可选，如果不传会自动检测）
  initialCollected: {
    type: Boolean,
    default: null
  },
  // 按钮类型配置
  collectedButtonType: {
    type: String,
    default: 'warning'
  },
  uncollectedButtonType: {
    type: String,
    default: 'info'
  }
})

const emit = defineEmits(['update:collected', 'collect-success', 'collect-error', 'uncollect-success'])

// 响应式数据
const isCollected = ref(props.initialCollected || false)
const isLoading = ref(false)
const favoriteId = ref(null)
const userStore = useUserStore()

const buttonText = computed(() => {
  return isCollected.value ? '已收藏' : '收藏'
})

// 获取当前用户ID
const getCurrentUserId = () => {
  return userStore.id || userStore.userId
}

// 检查登录状态（游客 / 未登录会提示去登录）
const checkLogin = async () => {
  return await ensureLogin('收藏')
}

// 检查收藏状态
const checkFavoriteStatus = () => {
  // 未登录 / 游客不请求收藏状态
  if (!userStore.token || userStore.isGuest) {
    isCollected.value = false
    return
  }

  // 如果没有 targetId，不检查
  if (!props.targetId) {
    return
  }

  // 如果父组件提供了初始状态（true/false），使用父组件的状态
  if (props.initialCollected === true || props.initialCollected === false) {
    isCollected.value = props.initialCollected
    return
  }

  // 否则通过 API 检查收藏状态
  const userId = getCurrentUserId()
  if (!userId) return

  let checkApi
  if (props.type === 'bank') {
    checkApi = checkBankFavoriteExists
  } else if (props.type === 'question') {
    checkApi = checkQuestionFavoriteExists
  } else if (props.type === 'note') {
    checkApi = checkNoteFavoriteExists
  }

  checkApi(userId, props.targetId).then(response => {
    if (response.code === 200) {
      // API 契约：{ data: boolean }
      isCollected.value = !!response.data
    }
  }).catch(error => {
    console.error('检查收藏状态失败:', error)
    // 如果检查失败，默认设为未收藏
    isCollected.value = false
  })
}

// 处理收藏/取消收藏 - 乐观更新
const handleCollect = async () => {
  if (!(await checkLogin())) return

  isLoading.value = true
  const userId = getCurrentUserId()

  // 保存当前状态用于回滚
  const previousState = isCollected.value

  // 乐观更新：立即切换状态
  isCollected.value = !isCollected.value

  try {
    if (previousState) {
      // 之前是已收藏，现在要取消收藏
      let deleteApi
      if (props.type === 'bank') {
        deleteApi = deleteFavoriteBankByUserAndBank
      } else if (props.type === 'question') {
        deleteApi = deleteFavoriteQuestionByUserAndQuestion
      } else if (props.type === 'note') {
        deleteApi = deleteFavoriteNoteByUserAndNote
      }
      await deleteApi(userId, props.targetId)
      favoriteId.value = null
      emit('update:collected', false)
      emit('uncollect-success', props.targetId, props.type)
    } else {
      // 之前是未收藏，现在要收藏
      const data = { userId }
      if (props.type === 'bank') {
        data.bankId = props.targetId
      } else if (props.type === 'question') {
        data.questionId = props.targetId
      } else if (props.type === 'note') {
        data.noteId = props.targetId
      }

      let addApi
      if (props.type === 'bank') {
        addApi = addFavoriteBank
      } else if (props.type === 'question') {
        addApi = addFavoriteQuestion
      } else if (props.type === 'note') {
        addApi = addFavoriteNote
      }
      await addApi(data)
      emit('update:collected', true)
      emit('collect-success', props.targetId, props.type)
    }
  } catch (error: any) {
    // 出错时回滚状态
    isCollected.value = previousState
    console.error('收藏操作失败:', error)
    emit('collect-error', error, props.targetId, props.type)
  } finally {
    isLoading.value = false
  }
}

// 监听 targetId 变化
watch(() => props.targetId, (newVal) => {
  if (newVal) {
    checkFavoriteStatus()
  }
})

// 监听 initialCollected 变化
watch(() => props.initialCollected, (newVal) => {
  if (newVal === true || newVal === false) {
    isCollected.value = newVal
  }
})

// 组件挂载时检查收藏状态
onMounted(() => {
  checkFavoriteStatus()
})

// 暴露方法供父组件调用
defineExpose({
  checkStatus: checkFavoriteStatus,
  refresh: checkFavoriteStatus
})
</script>

<style scoped>
.favorite-btn {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  border-radius: 8px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 8px 16px;
  height: auto;
  font-weight: 500;
}

.favorite-btn:hover {
  transform: translateY(-2px);
  border-color: var(--el-border-color-hover);
  color: var(--el-text-color-primary);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.favorite-btn.is-collected {
  background: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning);
  color: var(--el-color-warning);
}

.favorite-btn.is-collected:hover {
  border-color: var(--el-color-warning-dark-2);
  color: var(--el-color-warning-dark-2);
  background: var(--el-color-warning-light-8);
}

.favorite-btn .el-icon {
  margin-right: 4px;
}

.favorite-btn.is-loading {
  opacity: 0.7;
}
</style>