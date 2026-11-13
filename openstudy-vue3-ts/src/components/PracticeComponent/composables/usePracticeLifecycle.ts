import { onActivated, onDeactivated, onMounted, onUnmounted, watch } from 'vue'

/** 练习页生命周期：首次加载、离开落盘、keep-alive 离场/回场。 */
export function usePracticeLifecycle(options: {
  getModuleType: () => string | undefined
  getBankId: () => number
  isFirstLoaded: { value: boolean }
  showExamResult: { value: boolean }
  setTimeUpDialogShowing: (value: boolean) => void
  fetchQuestions: () => Promise<any> | any
  restoreDraftIfAny: () => void
  loadRecentSession: () => void
  startExamTimer: () => void
  stopExamTimer: () => void
  draftSaver: { flush: () => void; cancel: () => void }
  saveCurrentAnswerState: () => void
  bindVisibility: () => void
  unbindVisibility: () => void
  bindPracticeScrollHost: () => void
  scheduleScrollHostBinding: () => void
  unbindPracticeScrollHost: (clearTimers?: boolean) => void
  debugEnterModule: (moduleType: string | undefined, bankId: number) => void
  debugLeaveModule: (moduleType: string | undefined, bankId: number) => void
}) {
  let hasBeenDeactivated = false

  watch(options.showExamResult, (value) => {
    if (value) {
      options.stopExamTimer()
      options.setTimeUpDialogShowing(false)
    } else if (options.getModuleType() === 'mock') {
      options.setTimeUpDialogShowing(false)
      options.startExamTimer()
    }
  })

  onMounted(() => {
    options.debugEnterModule(options.getModuleType(), options.getBankId())
    if (!options.isFirstLoaded.value && options.getBankId() && options.getBankId() > 0) {
      options.isFirstLoaded.value = true
      options.fetchQuestions().then(() => {
        try {
          options.restoreDraftIfAny()
        } catch (e) {
          console.warn('[practice] 恢复暂存失败', e)
        }
      })
    }
    if (options.getModuleType() === 'mock' && !options.showExamResult.value) {
      options.startExamTimer()
    }
    options.loadRecentSession()
    options.bindVisibility()
    options.scheduleScrollHostBinding()
  })

  onUnmounted(() => {
    options.debugLeaveModule(options.getModuleType(), options.getBankId())
    options.saveCurrentAnswerState()
    try {
      options.draftSaver.flush()
    } catch {
      /* 暂存失败不该影响离开页面 */
    }
    options.draftSaver.cancel()
    options.stopExamTimer()
    options.unbindVisibility()
    options.unbindPracticeScrollHost(true)
  })

  onDeactivated(() => {
    options.debugLeaveModule(options.getModuleType(), options.getBankId())
    try {
      options.draftSaver.flush()
    } catch {
      /* 暂存失败不该影响离开页面 */
    }
    options.draftSaver.cancel()
    options.stopExamTimer()
    options.unbindVisibility()
    options.unbindPracticeScrollHost(true)
    hasBeenDeactivated = true
  })

  onActivated(() => {
    const isReentry = hasBeenDeactivated
    hasBeenDeactivated = false
    options.debugEnterModule(options.getModuleType(), options.getBankId())
    options.bindVisibility()
    options.bindPracticeScrollHost()
    if (isReentry && options.getModuleType() === 'mock' && !options.showExamResult.value) {
      options.startExamTimer()
    }
  })
}
