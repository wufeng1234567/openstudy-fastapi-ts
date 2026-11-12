import { ref } from 'vue'

/** 练习页 AI 解析弹窗的状态、缓存和题目文本格式化。 */
export function usePracticeAnalysis(options: {
  currentQuestion: { value: any }
  showAnalysisDialog: { value: boolean }
}) {
  const analysisCache = ref(new Map<any, string>())
  const currentAnalysisContent = ref('')
  const isAnalysisGenerating = ref(false)
  const analysisTargetQuestion = ref<any>(null)

  function openQuestion(question: any) {
    const questionId = question?.id
    if (!questionId) return
    analysisTargetQuestion.value = question
    currentAnalysisContent.value = analysisCache.value.has(questionId)
      ? (analysisCache.value.get(questionId) as string)
      : ''
    options.showAnalysisDialog.value = true
  }

  function openAiAnalysis() {
    openQuestion(options.currentQuestion.value)
  }

  function openAiAnalysisForQuestion(question: any) {
    openQuestion(question)
  }

  function getQuestionTypeName(type: string) {
    const typeMap: Record<string, string> = {
      single: '单选题',
      multiple: '多选题',
      truefalse: '判断题',
      fillblank: '填空题',
      essay: '简答题',
      readingComprehension: '组合题',
      cloze: '组合题'
    }
    return typeMap[type] || type
  }

  function formatOptionsForAnalysis(question: any) {
    if (!question || !question.options) return ''
    return Array.isArray(question.options) ? JSON.stringify(question.options) : question.options
  }

  function getAnalysisQuestionText(question: any) {
    if (!question) return ''
    if (question.type === 'readingComprehension' || question.type === 'cloze') {
      const parts: string[] = []
      if (question.mainTitle) parts.push(question.mainTitle)
      if (question.mainContent) parts.push(question.mainContent)
      if (parts.length > 0) return parts.join('\n\n')
    }
    return question.question || question.questionText || question.title || ''
  }

  function updateAnalysisCache(questionId: any, content: string) {
    analysisCache.value.set(questionId, content)
  }

  function setAnalysisGenerating(generating: boolean) {
    isAnalysisGenerating.value = generating
  }

  function handleAnalysisClose() {
    options.showAnalysisDialog.value = false
    isAnalysisGenerating.value = false
  }

  return {
    analysisCache,
    currentAnalysisContent,
    isAnalysisGenerating,
    analysisTargetQuestion,
    openAiAnalysis,
    openAiAnalysisForQuestion,
    getQuestionTypeName,
    formatOptionsForAnalysis,
    getAnalysisQuestionText,
    updateAnalysisCache,
    setAnalysisGenerating,
    handleAnalysisClose
  }
}
