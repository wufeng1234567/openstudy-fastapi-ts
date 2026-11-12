import { ElMessageBox } from 'element-plus'
import { submitPracticeSession } from '@/api/questionMain/questionMain'

/** 练习/模拟考试的交卷与结束考试流程。 */
export function usePracticeSubmission(options: {
  isMockFlow: { value: boolean }
  activeMockConfig: { value: any }
  practiceSessionId: { value: string | number | null }
  questions: { value: any[] }
  answers: { value: any[] }
  totalQuestions: { value: number }
  answeredCount: { value: number }
  totalScore: { value: number }
  showExamResult: { value: boolean }
  hasSubmittedCurrentBatch: { value: boolean }
  forceOverview: { value: boolean }
  proxy: any
  emit: (event: 'close') => void
  ensurePracticeSession: () => Promise<void> | void
  handleMockSubmit: () => Promise<void> | void
  applyServerGrade: (question: any, item: any) => void
  showAllAnalysis: () => void
  loadRecentSession: () => void
  clearExamStorage: () => void
  stopExamTimer: () => void
  clearAnswerStateCache: (moduleType: string) => void
}) {
  const handleSubmitExam = (submitOptions: { skipConfirm?: boolean } = {}) => {
    const doSubmit = async () => {
      if (options.isMockFlow.value && options.activeMockConfig.value) {
        await options.handleMockSubmit()
        return
      }
      try {
        if (!options.practiceSessionId.value) await options.ensurePracticeSession()
        if (!options.practiceSessionId.value) {
          options.proxy.$modal.msgError('练习会话不存在，无法交卷，请刷新后重试')
          return
        }
        const localAnswers = Object.fromEntries(
          options.questions.value.map((q: any, i: number) => [String(q.id), options.answers.value[i]])
        )
        const res: any = await submitPracticeSession(options.practiceSessionId.value, undefined, localAnswers)
        if (res?.code !== 200) {
          options.proxy.$modal.msgError(res?.msg || '交卷失败，请重试')
          return
        }
        const items: any[] = Array.isArray(res.data?.items) ? res.data.items : []
        const byId = new Map<string, any>(options.questions.value.map((q: any) => [String(q.id), q]))
        items.forEach((item: any) => {
          const question = byId.get(String(item.questionId))
          if (question) options.applyServerGrade(question, item)
        })
        options.totalScore.value = Math.round(Number(res.data?.percentage ?? 0))
        options.showAllAnalysis()
        options.showExamResult.value = true
        options.loadRecentSession()
        options.clearExamStorage()
        options.stopExamTimer()
        if (Number(res.data?.pendingCount || 0) > 0) {
          options.proxy.$modal.msgInfo(`本次有 ${res.data.pendingCount} 道简答题待自评，不计入自动正确率`)
        }
      } catch (e: any) {
        console.error('[practice] 交卷失败', e)
        options.proxy.$modal.msgError('交卷失败，请检查网络后重试')
      }
    }

    if (submitOptions.skipConfirm) {
      doSubmit()
      return
    }
    const unanswered = Math.max(0, options.totalQuestions.value - options.answeredCount.value)
    const tip =
      unanswered > 0
        ? `还有 ${unanswered} 道题没有作答。\n交卷后不能修改答案，确定现在交卷吗？`
        : '所有题目都已作答。\n交卷后不能修改答案，确定交卷吗？'
    ElMessageBox.confirm(tip, '确认交卷', {
      confirmButtonText: '确认交卷',
      cancelButtonText: '继续答题',
      type: unanswered > 0 ? 'warning' : 'info',
      closeOnClickModal: false
    })
      .then(() => doSubmit())
      .catch(() => {
        /* 用户选择继续答题 */
      })
  }

  const handleFinishExam = () => {
    options.showExamResult.value = false
    options.totalScore.value = 0
    options.hasSubmittedCurrentBatch.value = false
    options.forceOverview.value = false
    options.clearAnswerStateCache('mock')
    options.emit('close')
  }

  return { handleSubmitExam, handleFinishExam }
}
