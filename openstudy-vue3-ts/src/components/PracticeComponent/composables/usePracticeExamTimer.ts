import { computed, ref } from 'vue'
import type { ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'

export const EXAM_END_TIME_KEY = 'openstudy_exam_end_time'
export const EXAM_BANK_ID_KEY = 'openstudy_exam_bank_id'

/**
 * 练习/模拟考试的倒计时生命周期。
 *
 * 从 `PracticeComponent.vue` 抽出的第一块业务逻辑：它只依赖当前模块类型、
 * 题库 id、时间上限和交卷回调，不直接操作练习页的题目/答案状态。
 */
export function usePracticeExamTimer(options: {
  getModuleType: () => string | undefined
  getBankId: () => number | string | undefined
  examTimeLimit: ComputedRef<number>
  showExamResult: { value: boolean }
  onTimeUp: () => void
}) {
  const remainingTime = ref(0)
  const examTimer = ref<ReturnType<typeof setInterval> | null>(null)
  let isTimeUpDialogShowing = false
  let visibilityBound = false

  const formattedRemainingTime = computed(() => {
    const minutes = Math.floor(remainingTime.value / 60)
    const seconds = remainingTime.value % 60
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  const isTimeWarning = computed(() => remainingTime.value > 0 && remainingTime.value <= 300)
  const isTimeDanger = computed(() => remainingTime.value > 0 && remainingTime.value <= 60)

  function startExamTimer() {
    if (options.getModuleType() !== 'mock') return
    if (options.showExamResult.value) return

    stopExamTimer()

    const savedEndTime = localStorage.getItem(EXAM_END_TIME_KEY)
    const savedBankId = localStorage.getItem(EXAM_BANK_ID_KEY)
    const now = Date.now()

    if (savedEndTime && savedBankId === String(options.getBankId())) {
      const endTime = parseInt(savedEndTime)
      if (now < endTime) {
        remainingTime.value = Math.ceil((endTime - now) / 1000)
      } else {
        remainingTime.value = 0
        clearExamStorage()
        return
      }
    } else {
      const totalSeconds = options.examTimeLimit.value * 60
      const endTime = now + totalSeconds * 1000
      localStorage.setItem(EXAM_END_TIME_KEY, String(endTime))
      localStorage.setItem(EXAM_BANK_ID_KEY, String(options.getBankId()))
      remainingTime.value = totalSeconds
    }

    examTimer.value = setInterval(() => {
      const currentTime = Date.now()
      const endTime = parseInt(localStorage.getItem(EXAM_END_TIME_KEY) || '')

      if (!endTime || currentTime >= endTime) {
        stopExamTimer()
        clearExamStorage()
        remainingTime.value = 0
        if (!document.hidden && !isTimeUpDialogShowing) {
          handleTimeUp()
        }
      } else {
        remainingTime.value = Math.ceil((endTime - currentTime) / 1000)
      }
    }, 1000)
  }

  function stopExamTimer() {
    if (examTimer.value) {
      clearInterval(examTimer.value)
      examTimer.value = null
    }
  }

  function clearExamStorage() {
    localStorage.removeItem(EXAM_END_TIME_KEY)
    localStorage.removeItem(EXAM_BANK_ID_KEY)
  }

  function handleTimeUp() {
    if (isTimeUpDialogShowing || options.showExamResult.value) return
    isTimeUpDialogShowing = true
    ElMessageBox.alert('考试时间已到，系统将自动提交试卷！', '时间到', {
      confirmButtonText: '确定',
      type: 'warning',
      showClose: false,
      closeOnClickModal: false,
      closeOnPressEscape: false
    }).then(() => {
      isTimeUpDialogShowing = false
      options.onTimeUp()
    }).catch(() => {
      isTimeUpDialogShowing = false
      options.onTimeUp()
    })
  }

  function bindVisibility() {
    if (visibilityBound) return
    document.addEventListener('visibilitychange', handleVisibilityChange)
    visibilityBound = true
  }

  function unbindVisibility() {
    if (!visibilityBound) return
    document.removeEventListener('visibilitychange', handleVisibilityChange)
    visibilityBound = false
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      stopExamTimer()
    } else if (options.getModuleType() === 'mock' && !options.showExamResult.value) {
      startExamTimer()
    }
  }

  return {
    remainingTime,
    examTimer,
    formattedRemainingTime,
    isTimeWarning,
    isTimeDanger,
    startExamTimer,
    stopExamTimer,
    clearExamStorage,
    handleTimeUp,
    bindVisibility,
    unbindVisibility
  }
}
