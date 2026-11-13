import { watch } from 'vue'

/** 练习页路由参数变化：切换模块 / 切换题库时保存旧状态并重置。 */
export function usePracticeRouteWatches(options: {
  getModuleType: () => string | undefined
  getBankId: () => number
  showExamResult: { value: boolean }
  hasSubmittedCurrentBatch: { value: boolean }
  remainingTime: { value: number }
  saveCurrentAnswerState: (moduleType?: string) => void
  resetAndFetchQuestions: (moduleType?: string, oldBankId?: number) => void
  resetDraftRestored: () => void
  startExamTimer: () => void
  stopExamTimer: () => void
  clearExamStorage: () => void
  debugWatchTrigger: (name: string, value: string, newValue: any, oldValue: any) => void
  debugLeaveModule: (moduleType: string, bankId: number) => void
  debugEnterModule: (moduleType: string | undefined, bankId: number) => void
}) {
  watch(
    () => options.getModuleType(),
    (newType, oldType) => {
      options.debugWatchTrigger('moduleType', String(newType), newType, oldType)
      if (newType === undefined && oldType && oldType !== 'null') {
        options.saveCurrentAnswerState(oldType)
        return
      }
      if (newType === 'mock' && !options.showExamResult.value) {
        options.startExamTimer()
      } else {
        options.stopExamTimer()
        options.remainingTime.value = 0
        options.clearExamStorage()
      }
      if (newType && newType !== oldType && oldType !== null) {
        options.debugLeaveModule(oldType || 'unknown', options.getBankId())
        options.debugEnterModule(newType, options.getBankId())
        options.resetAndFetchQuestions(oldType)
      }
    }
  )

  watch(
    () => options.getBankId(),
    (newId, oldId) => {
      if (oldId === undefined || oldId === null) return
      if (!newId || Number(newId) <= 0) return
      if (Number(newId) === Number(oldId)) return
      options.debugWatchTrigger('bankId', String(newId), String(newId), String(oldId))
      options.stopExamTimer()
      options.remainingTime.value = 0
      options.clearExamStorage()
      options.showExamResult.value = false
      options.hasSubmittedCurrentBatch.value = false
      options.resetDraftRestored()
      options.resetAndFetchQuestions(options.getModuleType(), oldId)
    }
  )
}
