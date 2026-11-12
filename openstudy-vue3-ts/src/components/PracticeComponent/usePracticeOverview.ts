import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

/** 练习页的整体浏览/逐题模式与空态动作。 */
export function usePracticeOverview(options: {
  moduleSettings: { value: any }
  store: any
  getModuleType: () => string | undefined
  noWrongQuestionsReason: { value: string }
  questions: { value: any[] }
  resetPractice: () => void
  clearAnswerStateCache: (moduleType: any) => void
  resetAndFetchQuestions: () => void
}) {
  const overviewMode = computed({
    get: () => options.moduleSettings.value.isOverviewMode || false,
    set: (value) => options.store.saveModuleSettings(options.getModuleType(), { isOverviewMode: value })
  })
  const forceOverview = ref(false)
  const isOverviewActive = computed(() => options.moduleSettings.value.isOverviewMode || forceOverview.value)
  const isEmptyState = computed(
    () => !!options.noWrongQuestionsReason.value && options.questions.value.length === 0
  )

  const handleEmptyRestart = () => {
    options.resetPractice()
    options.clearAnswerStateCache(options.getModuleType())
    forceOverview.value = false
    options.resetAndFetchQuestions()
  }

  const handleEmptyTurnOffOnlyWrong = () => {
    options.store.saveModuleSettings(options.getModuleType(), { onlyWrong: false })
    options.resetAndFetchQuestions()
    ElMessage.success('已关闭「只刷错题」，正在加载全部题目')
  }

  return {
    overviewMode,
    forceOverview,
    isOverviewActive,
    isEmptyState,
    handleEmptyRestart,
    handleEmptyTurnOffOnlyWrong
  }
}
