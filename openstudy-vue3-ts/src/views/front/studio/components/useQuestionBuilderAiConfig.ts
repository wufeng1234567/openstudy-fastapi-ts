import { nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getBankContextInfo, clearBankConversation } from '@/api/ai/ai'
import { listAiConfig } from '@/api/system/aiConfig'

/** 题库 AI 上下文与模型配置面板。 */
export function useQuestionBuilderAiConfig(options: { currentBankId: any }) {
  const { currentBankId } = options
  // 题库上下文信息
const bankContextInfo = ref({
  bankName: '',
  totalQuestions: 0
})
const historyCount = ref(0)
const clearingContext = ref(false)

// AI 模型配置相关
const userAiConfigs = ref<any[]>([])
const aiModelManagerVisible = ref(false)
const aiModelManagerRef = ref(null)

const loadUserAiConfigs = async () => {
  try {
    // available = 系统提供的官方模型 + 我自己添加的模型（用于校验用户选的模型是否可用）
    const res = await listAiConfig('available')
    if (res.code === 200 && res.rows) {
      userAiConfigs.value = res.rows
    }
  } catch (error) {
    console.error('加载用户AI配置失败:', error)
  }
}

const openAiModelManager = () => {
  aiModelManagerVisible.value = true
  nextTick(() => {
    if (aiModelManagerRef.value) {
      aiModelManagerRef.value.refresh()
    }
  })
}

// 加载题库上下文信息
const loadBankContextInfo = async () => {
  if (!currentBankId.value) return
  try {
    const res = await getBankContextInfo(currentBankId.value)
    if (res.code === 200 && res.data) {
      bankContextInfo.value = {
        bankName: res.data.bankName || '未知题库',
        totalQuestions: res.data.totalQuestions || 0
      }
      historyCount.value = res.data.historyCount || 0
    }
  } catch (error) {
    console.error('加载题库上下文失败:', error)
  }
}

// 清空上下文
const handleClearContext = async () => {
  if (!currentBankId.value) return
  try {
    await ElMessageBox.confirm('确定清空该题库的AI对话上下文吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    clearingContext.value = true
    const res = await clearBankConversation(currentBankId.value)
    if (res.code === 200) {
      ElMessage.success('上下文已清空')
      historyCount.value = 0
    } else {
      ElMessage.error(res.msg || '清空失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败')
    }
  } finally {
    clearingContext.value = false
  }
}




  return {
    bankContextInfo,
    historyCount,
    clearingContext,
    userAiConfigs,
    aiModelManagerVisible,
    aiModelManagerRef,
    loadUserAiConfigs,
    openAiModelManager,
    loadBankContextInfo,
    handleClearContext
  }
}
