import { computed, ref } from 'vue'
import type { MockExamConfig, MockExamRecord } from '@/types'

type MockPhase = 'setup' | 'running' | 'history' | 'summary'

/** 模拟考试状态、展示分支判断和结果弹窗状态。 */
export function usePracticeMockState(options: {
  moduleTypeSafe: { value: string }
  moduleSettings: { value: any }
}) {
  const mockPhase = ref<MockPhase>('setup')
  const isMockFlow = computed(() => options.moduleTypeSafe.value === 'mock')
  const showMockSetupUI = computed(
    () => isMockFlow.value && (mockPhase.value === 'setup' || mockPhase.value === 'history')
  )
  const showMockSummaryUI = computed(() => isMockFlow.value && mockPhase.value === 'summary')
  const activeMockConfig = ref<MockExamConfig | null>(null)
  const effectiveShuffleOptions = computed(() => {
    if (isMockFlow.value) return !!activeMockConfig.value?.shuffleOptions
    return !!options.moduleSettings.value.shuffleOptions
  })
  const mockAvailable = ref<Record<string, number>>({})
  const currentExamRecord = ref<MockExamRecord | null>(null)
  const historyRecord = ref<MockExamRecord | null>(null)
  const examStartAt = ref(0)
  const showExamResult = ref(false)
  const totalScore = ref(0)
  const showAnalysisDialog = ref(false)
  const viewerVisible = ref(false)
  const viewerSrc = ref('')
  const hasSubmittedCurrentBatch = ref(false)
  const isFirstLoaded = ref(false)
  const examTimeLimit = computed(() => options.moduleSettings.value.examTimeLimit || 60)

  return {
    mockPhase,
    isMockFlow,
    showMockSetupUI,
    showMockSummaryUI,
    activeMockConfig,
    effectiveShuffleOptions,
    mockAvailable,
    currentExamRecord,
    historyRecord,
    examStartAt,
    showExamResult,
    totalScore,
    showAnalysisDialog,
    viewerVisible,
    viewerSrc,
    hasSubmittedCurrentBatch,
    isFirstLoaded,
    examTimeLimit
  }
}
