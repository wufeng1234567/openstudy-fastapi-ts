/** 练习页逐题输入、选项同步和答对自动跳题。 */
export function usePracticeInput(options: {
  selectedAnswer: { value: any }
  currentQuestionIndex: { value: number }
  answers: { value: any[] }
  questions: { value: any[] }
  currentQuestion: { value: any }
  totalQuestions: { value: number }
  isExamMode: { value: boolean }
  committedQuestions: { value: Record<number, boolean> }
  isInstantJudgeType: (type: string | undefined) => boolean
  handleAnswerSubmission: (index: number) => void
  selectOption: (index: number) => void
  moduleSettings: { value: any }
  nextQuestion: () => void
}) {
  function handleUpdateAnswer(value: any) {
    options.selectedAnswer.value = value
    const qIndex = options.currentQuestionIndex.value
    if (qIndex >= 0 && qIndex < options.answers.value.length) options.answers.value[qIndex] = value
    if (!options.isExamMode.value && options.committedQuestions.value[qIndex]) {
      options.committedQuestions.value[qIndex] = false
      const q = options.questions.value[qIndex]
      if (q) {
        q.showAnalysis = false
        q.answered = false
        q.correct = false
      }
    }
  }

  function handleSelectOption(index: number) {
    options.selectOption(index)
    const qIndex = options.currentQuestionIndex.value
    if (qIndex >= 0 && qIndex < options.answers.value.length) {
      options.answers.value[qIndex] = options.selectedAnswer.value
    }
    if (options.isExamMode.value) return
    if (options.isInstantJudgeType(options.currentQuestion.value?.type)) {
      options.committedQuestions.value[qIndex] = true
      options.handleAnswerSubmission(qIndex)
    } else if (options.committedQuestions.value[qIndex]) {
      options.committedQuestions.value[qIndex] = false
      const q = options.questions.value[qIndex]
      if (q) {
        q.showAnalysis = false
        q.answered = false
        q.correct = false
      }
    }
    if (!options.moduleSettings.value.autoNextOnCorrect) return
    const q = options.currentQuestion.value
    if (!q) return
    if (q.type === 'single' || q.type === 'truefalse') {
      if (options.selectedAnswer.value === q.correctAnswer && options.currentQuestionIndex.value < options.totalQuestions.value - 1) {
        options.nextQuestion()
      }
    } else if (q.type === 'multiple') {
      const selected = Array.isArray(options.selectedAnswer.value) ? options.selectedAnswer.value : []
      const correct = Array.isArray(q.correctAnswer) ? q.correctAnswer : []
      if (selected.length === correct.length && selected.every((v: any) => correct.includes(v))) {
        if (options.currentQuestionIndex.value < options.totalQuestions.value - 1) options.nextQuestion()
      }
    }
  }

  return { handleUpdateAnswer, handleSelectOption }
}
