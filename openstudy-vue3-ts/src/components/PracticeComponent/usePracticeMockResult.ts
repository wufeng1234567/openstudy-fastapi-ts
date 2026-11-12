import type { MockExamItemDetail, MockExamRecord } from '@/types'
import { normalizeOptionList, normalizeType, fullStem } from './practiceQuestionUtils'
import { submitPracticeSession } from '@/api/questionMain/questionMain'
import { clearMockSession } from '@/utils/mockExamSession'

/** 模拟考试交卷：服务端判分、生成记录、切到总结页。 */
export function usePracticeMockResult(options: {
  activeMockConfig: { value: any }
  practiceSessionId: { value: string | number | null }
  examStartAt: { value: number }
  questions: { value: any[] }
  answers: { value: any[] }
  currentExamRecord: { value: MockExamRecord | null }
  totalScore: { value: number }
  showExamResult: { value: boolean }
  mockPhase: { value: string }
  getBankId: () => number
  getBankName: () => string
  store: any
  proxy: any
  getUserId: () => any
  stopExamTimer: () => void
  clearExamStorage: () => void
  setMockSessionEndAt: (value: number) => void
  showAllAnalysis: () => void
}) {
  async function handleMockSubmit() {
    const cfg = options.activeMockConfig.value
    if (!cfg) return
    if (!options.practiceSessionId.value) {
      options.proxy.$modal.msgError('考试会话不存在，无法交卷，请刷新后重试')
      return
    }
    const durationSec = options.examStartAt.value
      ? Math.max(0, Math.round((Date.now() - options.examStartAt.value) / 1000))
      : 0
    let serverData: any
    try {
      const localAnswers = Object.fromEntries(
        options.questions.value.map((q: any, i: number) => [String(q.id), options.answers.value[i]])
      )
      const res: any = await submitPracticeSession(options.practiceSessionId.value, durationSec, localAnswers)
      if (res?.code !== 200) {
        options.proxy.$modal.msgError(res?.msg || '交卷失败，请重试')
        return
      }
      serverData = res.data || {}
    } catch (e: any) {
      console.error('[mock] 服务端交卷失败', e)
      options.proxy.$modal.msgError('交卷失败，请检查网络后重试')
      return
    }

    const serverItems: any[] = Array.isArray(serverData.items) ? serverData.items : []
    const items: MockExamItemDetail[] = serverItems.map((item: any, i: number) => {
      const q = item.question || {}
      const type = normalizeType(q.questionType) as any
      const subResults: any[] = Array.isArray(item.subResults) ? item.subResults : []
      const detail: any = {
        questionId: item.questionId,
        index: i + 1,
        type,
        stem: fullStem(q),
        userAnswer: item.userAnswer,
        correctAnswer: item.correctAnswer,
        isCorrect: item.isCorrect === true,
        gotScore: Number(item.scoreAwarded) || 0,
        fullScore: Number(item.maxScore) || 0,
        analysis: String(item.analysis || '') || undefined
      }
      if (Array.isArray(q.options) && q.options.length) detail.options = normalizeOptionList(q.options)
      const subs = Array.isArray(q.subQuestions) ? q.subQuestions : []
      if (subs.length) {
        detail.subItems = subs.map((sq: any, si: number) => {
          const subResult = subResults.find((r: any) => Number(r.subIndex) === si)
          return {
            index: si + 1,
            type: normalizeType(sq.questionType) as any,
            question: String(sq.questionText || `问题 ${si + 1}`),
            options: Array.isArray(sq.options) && sq.options.length ? normalizeOptionList(sq.options) : undefined,
            userAnswer: undefined,
            correctAnswer: subResult?.correctAnswer
          }
        })
      }
      return detail as MockExamItemDetail
    })

    const gotScore = Number(serverData.score) || 0
    const fullScore = Number(serverData.totalScore) || 0
    const record: MockExamRecord = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      bankId: options.getBankId(),
      bankName: options.getBankName(),
      submittedAt: Date.now(),
      config: JSON.parse(JSON.stringify(cfg)),
      totalQuestions: items.length,
      correctCount: Number(serverData.correctCount) || 0,
      wrongCount: Number(serverData.wrongCount) || 0,
      gotScore: Math.round(gotScore * 10) / 10,
      fullScore,
      passed: fullScore > 0 && gotScore >= (Number(cfg.passScore) || 0),
      durationSec,
      items
    }

    options.currentExamRecord.value = record
    options.store.addMockExamRecord(record)
    options.stopExamTimer()
    options.clearExamStorage()
    clearMockSession(options.getUserId(), options.getBankId())
    options.setMockSessionEndAt(0)
    options.practiceSessionId.value = ''
    options.showAllAnalysis()
    options.totalScore.value = Math.round(record.gotScore)
    options.showExamResult.value = true
    options.mockPhase.value = 'summary'
    if (Number(serverData.pendingCount || 0) > 0) {
      options.proxy.$modal.msgInfo(`本场有 ${serverData.pendingCount} 道简答题待自评，不计入自动得分`)
    }
  }

  return { handleMockSubmit }
}
