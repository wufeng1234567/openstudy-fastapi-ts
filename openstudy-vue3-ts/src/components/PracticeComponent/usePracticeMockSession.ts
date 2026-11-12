import { saveMockSession } from '@/utils/mockExamSession'

/** 将当前进行中的模拟考试写入本地会话。 */
export function usePracticeMockSession(options: {
  isMockFlow: { value: boolean }
  mockPhase: { value: string }
  activeMockConfig: { value: any }
  questions: { value: any[] }
  answers: { value: any[] }
  subFillBlankAnswers: { value: Record<string, any> }
  subEssayAnswers: { value: Record<string, any> }
  currentQuestion: { value: any }
  practiceSessionId: { value: string | null }
  examStartAt: { value: number }
  getUserId: () => any
  getBankId: () => any
  getMockSessionEndAt: () => number
}) {
  function persistMockSession() {
    if (!options.isMockFlow.value || options.mockPhase.value !== 'running') return
    const cfg = options.activeMockConfig.value
    if (!cfg) return
    const list = options.questions.value || []
    if (!list.length) return

    const answersById: Record<string, any> = {}
    list.forEach((q: any, i: number) => {
      const qid = q?.id ?? q?.questionId
      if (qid === undefined || qid === null) return
      const ans = options.answers.value?.[i]
      if (ans === null || ans === undefined || ans === '') return
      if (Array.isArray(ans) && ans.length === 0) return
      if (typeof ans === 'object' && !Array.isArray(ans) && Object.keys(ans).length === 0) return
      answersById[String(qid)] = ans
    })

    const fillById: Record<string, Record<string, any>> = {}
    const essayById: Record<string, Record<string, any>> = {}
    Object.keys(options.subFillBlankAnswers.value || {}).forEach((k) => {
      const [qid, sub] = String(k).split('_')
      if (!qid || sub === undefined) return
      const v = (options.subFillBlankAnswers.value as any)[k]
      if (v === null || v === undefined || v === '') return
      ;(fillById[qid] ||= {})[sub] = v
    })
    Object.keys(options.subEssayAnswers.value || {}).forEach((k) => {
      const [qid, sub] = String(k).split('_')
      if (!qid || sub === undefined) return
      const v = (options.subEssayAnswers.value as any)[k]
      if (v === null || v === undefined || v === '') return
      ;(essayById[qid] ||= {})[sub] = v
    })

    const cur = options.currentQuestion.value
    const curId = cur ? cur.id ?? cur.questionId ?? null : null
    saveMockSession(options.getUserId(), {
      bankId: options.getBankId(),
      config: JSON.parse(JSON.stringify(cfg)),
      questionIds: list.map((q: any) => q?.id ?? q?.questionId),
      scores: list.map((q: any) => Number(q?._mockScore) || 0),
      types: list.map((q: any) => String(q?._mockType || q?.type || '')),
      answers: answersById,
      subFillBlank: fillById,
      subEssay: essayById,
      practiceSessionId: options.practiceSessionId.value || undefined,
      currentQuestionId: curId,
      startedAt: options.examStartAt.value || Date.now(),
      endAt: options.getMockSessionEndAt() || options.examStartAt.value + (Number(cfg.timeLimit) || 60) * 60000
    })
  }

  return { persistMockSession }
}
