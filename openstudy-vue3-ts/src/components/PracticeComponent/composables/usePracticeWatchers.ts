import { watch } from 'vue'

/** 练习页会话持久化、草稿保存/恢复和设置变化监听。 */
export function usePracticeWatchers(options: {
  answers: { value: any[] }
  subFillBlankAnswers: { value: Record<string, any> }
  subEssayAnswers: { value: Record<string, any> }
  currentQuestionIndex: { value: number }
  questionOffset: { value: number }
  hasSubmittedCurrentBatch: { value: boolean }
  questions: { value: any[] }
  mockPhase: { value: string }
  showExamResult: { value: boolean }
  draftRestored: { value: boolean }
  moduleTypeSafe: { value: string }
  moduleSettings: { value: any }
  isResetting: { value: boolean }
  isOverviewActive: { value: boolean }
  questionStreamRef: { value: HTMLElement | null }
  highlightedIndex: { value: number }
  persistMockSession: () => void
  draftSaver: { schedule: () => void }
  restoreDraftIfAny: () => void
  updateQuestionCountAndSlice: (count: number) => void
  updateOnlyWrong: (value: boolean) => void
  fetchQuestions: () => void
}) {
  watch(
    [
      () => JSON.stringify(options.answers.value),
      () => JSON.stringify(options.subFillBlankAnswers.value),
      () => JSON.stringify(options.subEssayAnswers.value)
    ],
    () => {
      if (options.mockPhase.value !== 'running') return
      options.persistMockSession()
    }
  )

  watch(options.currentQuestionIndex, () => {
    if (options.mockPhase.value !== 'running') return
    options.persistMockSession()
  })

  watch(
    () => [
      JSON.stringify(options.answers.value),
      options.currentQuestionIndex.value,
      options.questionOffset.value,
      options.hasSubmittedCurrentBatch.value,
      JSON.stringify(options.subFillBlankAnswers.value),
      JSON.stringify(options.subEssayAnswers.value)
    ],
    () => {
      if (options.showExamResult.value) return
      if (!options.draftRestored.value) return
      if (options.moduleTypeSafe.value === 'mock') return
      options.draftSaver.schedule()
    }
  )

  watch(
    () => options.questions.value.length,
    (n, old) => {
      if (n > 0 && (!old || old === 0)) options.restoreDraftIfAny()
    }
  )

  watch(
    () => options.moduleSettings.value.questionCount,
    (value) => {
      if (options.isResetting.value) return
      options.updateQuestionCountAndSlice(value)
    }
  )

  watch(
    () => options.moduleSettings.value.onlyWrong,
    (value) => {
      if (options.isResetting.value) return
      options.updateOnlyWrong(value)
      options.fetchQuestions()
    }
  )

  watch(options.isOverviewActive, (value) => {
    if (!value) return
    const savedIndex = options.moduleSettings.value.overviewScrollIndex || 0
    if (savedIndex > 0 && options.questionStreamRef.value) {
      setTimeout(() => {
        if (!options.questionStreamRef.value) return
        const children = options.questionStreamRef.value.children
        if (children && children[savedIndex]) {
          ;(children[savedIndex] as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        options.highlightedIndex.value = savedIndex
      }, 100)
    }
  })
}
