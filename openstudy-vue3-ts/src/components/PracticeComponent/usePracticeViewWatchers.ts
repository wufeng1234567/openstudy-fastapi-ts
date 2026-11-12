import { watch } from 'vue'

/** 练习页题目流、滚动锚点和模拟考试初始化监听。 */
export function usePracticeViewWatchers(options: {
  questions: { value: any[] }
  committedQuestions: { value: Record<number, boolean> }
  isOverviewActive: { value: boolean }
  currentQuestionIndex: { value: number }
  moduleTypeSafe: { value: string }
  getModuleType: () => string | undefined
  getBankId: () => number
  historyRecord: { value: any }
  currentExamRecord: { value: any }
  showExamResult: { value: boolean }
  totalScore: { value: number }
  mockPhase: { value: string }
  ensureScrollHost: () => void
  syncScrollState: () => void
  restoreMockSession: () => Promise<boolean>
  loadMockAvailability: () => Promise<void>
}) {
  watch(
    () => options.questions.value.map((q: any) => q?.id).join(','),
    () => {
      options.committedQuestions.value = {}
    }
  )

  watch(
    [() => options.isOverviewActive.value, () => options.questions.value.length],
    () => {
      options.ensureScrollHost()
      options.syncScrollState()
    },
    { flush: 'post' }
  )

  watch(
    () => options.currentQuestionIndex.value,
    () => {
      options.syncScrollState()
    },
    { flush: 'post' }
  )

  watch(
    () => [options.getModuleType(), options.getBankId()],
    async () => {
      if (options.moduleTypeSafe.value !== 'mock') return
      options.historyRecord.value = null
      options.currentExamRecord.value = null
      options.showExamResult.value = false
      options.totalScore.value = 0
      const restored = await options.restoreMockSession()
      if (!restored) options.mockPhase.value = 'setup'
      await options.loadMockAvailability()
    },
    { immediate: true }
  )
}
