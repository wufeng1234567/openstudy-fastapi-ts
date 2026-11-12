import { computed, ref } from 'vue'

/** 练习页题目流滚动、标记题和分波切换。 */
export function usePracticeStream(options: {
  questions: { value: any[] }
  markedQuestions: { value: number[] }
  backendMarkedSet: { value: Set<number> }
  highlightedIndex: { value: number }
  questionStreamRef: { value: HTMLElement | null }
  isOverviewActive: { value: boolean }
  forceOverview: { value: boolean }
  overviewMode: { value: boolean }
  hasSubmittedCurrentBatch: { value: boolean }
  showExamResult: { value: boolean }
  totalScore: { value: number }
  moduleSettings: { value: any }
  questionOffset: { value: number }
  store: any
  getModuleType: () => string | undefined
  loadBatchWithoutReset: () => void
  goToQuestion: (index: number) => void
}) {
  let scrollDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let scrollLock = false

  const markedQuestionsSet = computed(() => {
    const set = new Set<number>()
    options.backendMarkedSet.value.forEach((id) => set.add(Number(id)))
    options.markedQuestions.value.forEach((idx) => {
      const q = options.questions.value[idx]
      if (q && q.id != null) set.add(Number(q.id))
    })
    return set
  })

  const toggleOverview = () => {
    if (options.isOverviewActive.value) {
      options.store.saveModuleSettings(options.getModuleType(), { overviewScrollIndex: options.highlightedIndex.value })
    }
    const next = !options.isOverviewActive.value
    options.forceOverview.value = false
    options.overviewMode.value = next
  }

  const scrollToQuestion = (index: number) => {
    if (!options.questionStreamRef.value) return
    scrollLock = true
    options.highlightedIndex.value = index
    const children = options.questionStreamRef.value.children
    if (children && children[index]) {
      ;(children[index] as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    setTimeout(() => {
      scrollLock = false
    }, 600)
  }

  const onStreamScroll = () => {
    if (scrollLock) return
    if (scrollDebounceTimer) clearTimeout(scrollDebounceTimer)
    scrollDebounceTimer = setTimeout(() => {
      if (!options.questionStreamRef.value) return
      const scrollTop = options.questionStreamRef.value.scrollTop
      if (scrollTop !== undefined) {
        const idx = Math.round(scrollTop / 120)
        if (idx >= 0 && idx < options.questions.value.length) options.highlightedIndex.value = idx
      }
    }, 200)
  }

  const handleMarkedChange = (index: number) => {
    const q = options.questions.value[index]
    const qid = q && q.id != null ? Number(q.id) : null
    const set = new Set(options.markedQuestions.value)
    if (set.has(index)) {
      set.delete(index)
      if (qid != null) options.backendMarkedSet.value.delete(qid)
    } else {
      set.add(index)
      if (qid != null) options.backendMarkedSet.value.add(qid)
    }
    options.markedQuestions.value = [...set]
    options.store.saveModuleSettings(options.getModuleType(), { markedQuestions: options.markedQuestions.value })
  }

  const handlePrevBatch = () => {
    options.hasSubmittedCurrentBatch.value = false
    options.showExamResult.value = false
    options.totalScore.value = 0
    const count = options.moduleSettings.value.questionCount || 10
    options.questionOffset.value = Math.max(0, options.questionOffset.value - count)
    options.loadBatchWithoutReset()
    setTimeout(() => {
      if (options.isOverviewActive.value) {
        const firstCard = document.querySelector('.overview-question-card')
        if (firstCard) firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
      } else {
        options.goToQuestion(0)
      }
    }, 150)
  }

  return { markedQuestionsSet, toggleOverview, scrollToQuestion, onStreamScroll, handleMarkedChange, handlePrevBatch }
}
