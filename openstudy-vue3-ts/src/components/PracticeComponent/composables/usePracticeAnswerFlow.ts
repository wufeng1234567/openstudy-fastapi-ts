import { ref } from 'vue'
import { ElMessage } from 'element-plus'

/** 练习页的作答确认、选项变更和换波动作。 */
export function usePracticeAnswerFlow(options: {
  currentQuestion: any
  currentQuestionIndex: { value: number }
  questions: { value: any[] }
  answers: { value: any[] }
  selectedAnswer: { value: any }
  isExamMode: { value: boolean }
  isOverviewActive: { value: boolean }
  moduleSettings: { value: any }
  questionOffset: { value: number }
  hasSubmittedCurrentBatch: { value: boolean }
  showExamResult: { value: boolean }
  totalScore: { value: number }
  selectOption: (index: number) => void
  selectSubOption: (subIndex: number, optionIndex: number) => void
  updateSubFillBlankAnswer: (subIndex: number, value: any) => void
  updateSubEssayAnswer: (subIndex: number, value: any) => void
  handleAnswerSubmission: (index: number) => void
  loadBatchWithoutReset: () => void
  startExamTimer: () => void
  isMock: () => boolean
  goToQuestion: (index: number) => void
}) {
  const committedQuestions = ref<Record<number, boolean>>({})

  function isInstantJudgeType(type: string | undefined) {
    return type === 'single' || type === 'truefalse'
  }

  function needsSubmit(q: any): boolean {
    if (!q) return false
    if (isInstantJudgeType(q.type)) return false
    if (q.type === 'composite') return Array.isArray(q.subQuestions) && q.subQuestions.length > 0
    return true
  }

  function handleCommitAnswer(qIndex: number) {
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) options.currentQuestionIndex.value = qIndex
    const q = options.questions.value[qIndex]
    const val = options.answers.value[qIndex]
    const isEmpty =
      val === null || val === undefined || val === '' || (Array.isArray(val) && val.length === 0)
    if (isEmpty) {
      ElMessage.warning(q?.type === 'essay' ? '请先写下你的答案' : '请先作答再确认')
      return
    }
    committedQuestions.value[qIndex] = true
    options.handleAnswerSubmission(qIndex)
  }

  const handleOverviewSelect = (qIndex: number, optIdx: number) => {
    // 已交卷/浏览成绩时只读，不能再向会话提交答案。
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) {
      if (
        options.currentQuestion.value &&
        !['readingComprehension', 'cloze'].includes(options.currentQuestion.value.type) &&
        options.selectedAnswer.value !== null &&
        options.answers.value[options.currentQuestionIndex.value] === null
      ) {
        options.handleAnswerSubmission(options.currentQuestionIndex.value)
      }
      options.currentQuestionIndex.value = qIndex
    }
    options.selectedAnswer.value =
      options.answers.value[qIndex] ?? (options.questions.value[qIndex]?.type === 'multiple' ? [] : null)
    options.selectOption(optIdx)
    options.answers.value[qIndex] = options.selectedAnswer.value
    if (options.questions.value[qIndex]) options.questions.value[qIndex].answered = true
    if (!options.isExamMode.value && isInstantJudgeType(options.questions.value[qIndex]?.type)) {
      committedQuestions.value[qIndex] = true
      options.handleAnswerSubmission(qIndex)
    } else if (!options.isExamMode.value && committedQuestions.value[qIndex]) {
      committedQuestions.value[qIndex] = false
      const q = options.questions.value[qIndex]
      if (q) {
        q.showAnalysis = false
        q.answered = false
        q.correct = false
      }
    }
  }

  const handleOverviewUpdateAnswer = (qIndex: number, value: any) => {
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) options.currentQuestionIndex.value = qIndex
    options.selectedAnswer.value = value
    options.answers.value[qIndex] = value
    if (options.questions.value[qIndex]) options.questions.value[qIndex].answered = true
    if (!options.isExamMode.value && isInstantJudgeType(options.questions.value[qIndex]?.type)) {
      committedQuestions.value[qIndex] = true
      options.handleAnswerSubmission(qIndex)
    } else if (!options.isExamMode.value && committedQuestions.value[qIndex]) {
      committedQuestions.value[qIndex] = false
      const q = options.questions.value[qIndex]
      if (q) {
        q.showAnalysis = false
        q.answered = false
        q.correct = false
      }
    }
  }

  const handleOverviewSelectSubOption = (qIndex: number, subIndex: number, optIdx: number) => {
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) options.currentQuestionIndex.value = qIndex
    options.selectSubOption(subIndex, optIdx)
    options.answers.value = [...options.answers.value]
  }

  const handleOverviewUpdateSubFillBlank = (qIndex: number, subIndex: number, value: any) => {
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) options.currentQuestionIndex.value = qIndex
    options.updateSubFillBlankAnswer(subIndex, value)
  }

  const handleOverviewUpdateSubEssay = (qIndex: number, subIndex: number, value: any) => {
    if (options.showExamResult.value) return
    if (options.currentQuestionIndex.value !== qIndex) options.currentQuestionIndex.value = qIndex
    options.updateSubEssayAnswer(subIndex, value)
  }

  const jumpToNextBatch = () => {
    options.hasSubmittedCurrentBatch.value = false
    options.showExamResult.value = false
    options.totalScore.value = 0
    committedQuestions.value = {}
    const count = options.moduleSettings.value.questionCount || 10
    options.questionOffset.value = options.questionOffset.value + count
    options.loadBatchWithoutReset()
    if (options.isMock()) options.startExamTimer()
    setTimeout(() => {
      if (options.isOverviewActive.value) {
        const firstCard = document.querySelector('.overview-question-card')
        if (firstCard) firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
      } else {
        options.goToQuestion(0)
      }
    }, 150)
  }

  return {
    committedQuestions,
    isInstantJudgeType,
    needsSubmit,
    handleCommitAnswer,
    handleOverviewSelect,
    handleOverviewUpdateAnswer,
    handleOverviewSelectSubOption,
    handleOverviewUpdateSubFillBlank,
    handleOverviewUpdateSubEssay,
    jumpToNextBatch
  }
}
