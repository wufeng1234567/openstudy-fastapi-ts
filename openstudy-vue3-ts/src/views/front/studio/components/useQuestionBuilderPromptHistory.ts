import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/** AI 提示词历史：localStorage 持久化、去重、回填和清空。 */
export function useQuestionBuilderPromptHistory(options: {
  aiForm: any
  userAiConfigs: any
  rawJsonContent: any
  parsedQuestionsForPreview: any
  editablePreviewData: any
}) {
  const { aiForm, userAiConfigs, rawJsonContent, parsedQuestionsForPreview, editablePreviewData } = options

// ==================== 提示词历史记录 ====================
const PROMPT_HISTORY_KEY = 'ai_prompt_history'
const MAX_HISTORY_COUNT = 10
const promptHistory = ref<any[]>([])

/**
 * 一条历史记录里「用户到底输入了什么」
 *
 * 2026-10-20 修：历史记录原来只认两种输入
 *   `knowledgePoint`（固定题型）和 `compositeRequirement`（组合题），
 *   新增的 `customRequirement`（自定义出题）**完全没被记录和回填** ——
 *   用户在自定义模式下点历史标签，输入框毫无反应。
 *
 * 这里把三种输入统一成一个取值函数，避免"每加一种模式就漏改三处"
 * （记录 / 去重 / 回填）。
 */
const historyContentOf = (src: any): string => {
  const t = String(src?.questionType || '').trim()
  if (t === 'custom') return String(src?.customRequirement || '')
  if (t === 'composite') return String(src?.compositeRequirement || '')
  return String(src?.knowledgePoint || '')
}

const loadPromptHistory = () => {
  try {
    const stored = localStorage.getItem(PROMPT_HISTORY_KEY)
    if (stored) promptHistory.value = JSON.parse(stored)
  } catch (e) { }
}

const savePromptToHistory = () => {
  const type = aiForm.value.questionType
  const isComposite = type === 'composite'
  const isCustom = type === 'custom'

  const record = {
    // 保存当前题型：用于判断"这条历史属于哪类输入"
    questionType: type,
    /*
     * 三种输入**各存各的字段**，不合并成一个 content 字符串。
     * 原因：回填时要写回**对应的输入框**，合并后就不知道该写哪儿了。
     */
    knowledgePoint: (isComposite || isCustom) ? '' : (aiForm.value.knowledgePoint || ''),
    compositeRequirement: isComposite ? (aiForm.value.compositeRequirement || '') : '',
    // ↓ 2026-10-20 新增：自定义出题的需求描述
    customRequirement: isCustom ? (aiForm.value.customRequirement || '') : '',
    // 保存其他配置
    count: isComposite ? 0 : (aiForm.value.count || 3),
    wordCount: isComposite ? (aiForm.value.wordCount || 200) : 0,
    subCount: isComposite ? (aiForm.value.subCount || 5) : 0,
    model: aiForm.value.model || '',
    timestamp: Date.now()
  }

  // 去重：按「实际内容 + 题型」判重（不同题型即使文字相同也算两条）
  const currentContent = historyContentOf(record)
  const exists = currentContent
    ? promptHistory.value.some(
        item => item.questionType === record.questionType && historyContentOf(item) === currentContent
      )
    : false

  if (!exists && currentContent) {
    promptHistory.value.unshift(record)
    if (promptHistory.value.length > MAX_HISTORY_COUNT) {
      promptHistory.value = promptHistory.value.slice(0, MAX_HISTORY_COUNT)
    }
    localStorage.setItem(PROMPT_HISTORY_KEY, JSON.stringify(promptHistory.value))
  }
}


// 删除单条历史记录
const deleteHistoryItem = (index) => {
  promptHistory.value.splice(index, 1)
  localStorage.setItem(PROMPT_HISTORY_KEY, JSON.stringify(promptHistory.value))
  ElMessage.success('已删除')
}


const applyHistoryPrompt = (item) => {
  if (!item) return

  const itemType = String(item.questionType || '').trim()
  // 跟随历史记录的题型（含 composite / custom / 各种固定题型）
  if (itemType && itemType !== aiForm.value.questionType) {
    aiForm.value.questionType = itemType
    // 只同步题型，**不清空**素材（素材是全局附加项，与题型无关）
    aiForm.value.knowledgePoint = ''
  }

  const isComposite = aiForm.value.questionType === 'composite'
  const isCustom = aiForm.value.questionType === 'custom'

  if (isCustom) {
    aiForm.value.customRequirement = item.customRequirement || ''
  } else if (isComposite) {
    aiForm.value.compositeRequirement = item.compositeRequirement || item.knowledgePoint || ''
    if (item.wordCount) aiForm.value.wordCount = item.wordCount
    if (item.subCount) aiForm.value.subCount = item.subCount
  } else {
    aiForm.value.knowledgePoint = item.knowledgePoint || ''
    if (item.count) aiForm.value.count = item.count
  }

  // 只在用户有该模型配置时才切换，避免删模型后历史记录导致报错
  if (item.model !== undefined && item.model !== null && item.model !== '') {
    const hasModel = userAiConfigs.value.some(config => config.isEnabled === 1 && config.model === item.model)
    if (hasModel) {
      aiForm.value.model = item.model
    }
  }
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
}

const clearPromptHistory = () => {
  promptHistory.value = []
  localStorage.removeItem(PROMPT_HISTORY_KEY)
  ElMessage.success('历史记录已清空')
}





  return {
    promptHistory,
    historyContentOf,
    loadPromptHistory,
    savePromptToHistory,
    deleteHistoryItem,
    applyHistoryPrompt,
    clearPromptHistory
  }
}
