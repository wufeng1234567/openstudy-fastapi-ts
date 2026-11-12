import { nextTick } from 'vue'
import { ElMessageBox } from 'element-plus'

/** 练习页「提交」入口：未答确认、清随机题单、进入结算。 */
export function usePracticeSubmitAction(options: {
  totalQuestions: { value: number }
  answeredCount: { value: number }
  hasSubmittedCurrentBatch: { value: boolean }
  forceOverview: { value: boolean }
  getModuleType: () => string | undefined
  clearRandomPlan: () => void
  handleSubmitExam: (submitOptions?: { skipConfirm?: boolean }) => void
}) {
  const handleSubmit = () => {
    const unanswered = options.totalQuestions.value - options.answeredCount.value
    const enterSettlement = () => {
      options.hasSubmittedCurrentBatch.value = true
      options.clearRandomPlan()
      options.forceOverview.value = true
      options.handleSubmitExam({ skipConfirm: true })
      nextTick(() => {
        setTimeout(() => {
          const firstCard = document.querySelector('.overview-question-card')
          if (firstCard) firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }, 120)
      })
    }

    if (options.getModuleType() === 'mock') {
      const message = unanswered > 0 ? `您还有 ${unanswered} 题未作答，确定要交卷吗？` : '确定要交卷吗？'
      ElMessageBox.confirm(message, '确认提交', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })
        .then(enterSettlement)
        .catch(() => {
          /* 用户取消 */
        })
      return
    }

    if (unanswered > 0) {
      ElMessageBox.confirm(`您还有 ${unanswered} 题未作答，是否提交并查看解析？`, '提示', {
        confirmButtonText: '提交并查看解析',
        cancelButtonText: '继续答题',
        type: 'warning'
      })
        .then(enterSettlement)
        .catch(() => {
          /* 继续答题 */
        })
      return
    }
    enterSettlement()
  }

  return { handleSubmit }
}
