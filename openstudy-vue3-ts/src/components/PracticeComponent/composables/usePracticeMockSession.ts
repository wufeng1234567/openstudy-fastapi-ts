import { nextTick } from 'vue'
import {
  EXAM_BANK_ID_KEY,
  EXAM_END_TIME_KEY
} from './usePracticeExamTimer'
import { saveMockSession, loadMockSession, clearMockSession } from '@/utils/mockExamSession'
import { listQuestionMainAll, startPracticeSession, getPracticeSession } from '@/api/questionMain/questionMain'

/** 模拟考试本地会话的写入与恢复。 */
export function usePracticeMockSession(options: {
  isMockFlow: { value: boolean }
  mockPhase: { value: string }
  activeMockConfig: { value: any }
  questions: { value: any[] }
  answers: { value: any[] }
  subFillBlankAnswers: { value: Record<string, any> }
  subEssayAnswers: { value: Record<string, any> }
  currentQuestion: { value: any }
  currentQuestionIndex: { value: number }
  questionOffset: { value: number }
  practiceSessionId: { value: string | number | null }
  examStartAt: { value: number }
  getUserId: () => any
  getBankId: () => any
  getMockSessionEndAt: () => number
  setMockSessionEndAt: (value: number) => void
  updateQuestionOffset: (value: number) => void
  updateQuestionCount: (value: number) => void
  processQuestions: (list: any[]) => Promise<void> | void
  startExamTimer: () => void
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

  async function restoreMockSession(): Promise<boolean> {
    const session = loadMockSession(options.getUserId(), options.getBankId())
    if (!session) return false

    try {
      const res: any = await listQuestionMainAll({ bankId: options.getBankId(), status: '0', withAnswer: false })
      const pool: any[] = Array.isArray(res?.data) ? res.data : Array.isArray(res?.result) ? res.result : []
      const byId = new Map<string, any>()
      pool.forEach((q: any) => {
        const qid = q?.id ?? q?.questionId
        if (qid !== undefined && qid !== null) byId.set(String(qid), q)
      })

      const rebuilt: any[] = []
      session.questionIds.forEach((qid: any, idx: number) => {
        const q = byId.get(String(qid))
        if (!q) return
        rebuilt.push({
          ...q,
          _mockScore: Number(session.scores?.[idx]) || 0,
          _mockType: session.types?.[idx] || q.type
        })
      })

      if (!rebuilt.length) {
        clearMockSession(options.getUserId(), options.getBankId())
        return false
      }

      let restoredSessionId = ''
      if (session.practiceSessionId) {
        try {
          const oldSession: any = await getPracticeSession(session.practiceSessionId)
          if (oldSession?.code === 200 && oldSession.data?.status === 'ongoing') {
            restoredSessionId = String(session.practiceSessionId)
          }
        } catch {
          // 旧会话不可用 → 下面新建
        }
      }
      if (!restoredSessionId) {
        const sessionRes: any = await startPracticeSession({
          bankId: options.getBankId(),
          moduleType: 'mock',
          questionIds: rebuilt.map((q: any) => q.id),
          scores: Object.fromEntries(rebuilt.map((q: any) => [String(q.id), Number(q._mockScore) || 0]))
        })
        if (sessionRes?.code !== 200 || !sessionRes?.data?.sessionId) {
          throw new Error(sessionRes?.msg || '恢复考试会话失败')
        }
        restoredSessionId = String(sessionRes.data.sessionId)
      }
      options.practiceSessionId.value = restoredSessionId
      options.activeMockConfig.value = JSON.parse(JSON.stringify(session.config))
      options.setMockSessionEndAt(Number(session.endAt) || 0)
      options.examStartAt.value = Number(session.startedAt) || Date.now()
      localStorage.setItem(EXAM_END_TIME_KEY, String(options.getMockSessionEndAt()))
      localStorage.setItem(EXAM_BANK_ID_KEY, String(options.getBankId()))

      const prevOffset = options.questionOffset.value
      options.updateQuestionOffset(0)
      options.updateQuestionCount(rebuilt.length)
      await options.processQuestions(rebuilt)
      options.updateQuestionOffset(prevOffset)

      const idxById = new Map<string, number>()
      rebuilt.forEach((q: any, i: number) => {
        const qid = q?.id ?? q?.questionId
        if (qid !== undefined && qid !== null) idxById.set(String(qid), i)
      })

      const nextAnswers = [...options.answers.value]
      Object.keys(session.answers || {}).forEach((qid) => {
        const i = idxById.get(String(qid))
        if (i !== undefined) nextAnswers[i] = session.answers[qid]
      })
      options.answers.value = nextAnswers
      Object.keys(session.subFillBlank || {}).forEach((qid) => {
        const i = idxById.get(String(qid))
        if (i === undefined) return
        Object.keys(session.subFillBlank[qid] || {}).forEach((sub) => {
          ;(options.subFillBlankAnswers.value as any)[`${qid}_${sub}`] = session.subFillBlank[qid][sub]
        })
      })
      Object.keys(session.subEssay || {}).forEach((qid) => {
        const i = idxById.get(String(qid))
        if (i === undefined) return
        Object.keys(session.subEssay[qid] || {}).forEach((sub) => {
          ;(options.subEssayAnswers.value as any)[`${qid}_${sub}`] = session.subEssay[qid][sub]
        })
      })
      rebuilt.forEach((q: any, i: number) => {
        const ans = options.answers.value?.[i]
        if (ans === null || ans === undefined || ans === '') return
        if (Array.isArray(ans) && ans.length === 0) return
        if (typeof ans === 'object' && !Array.isArray(ans) && Object.keys(ans).length === 0) return
        q.answered = true
      })
      if (session.currentQuestionId !== undefined && session.currentQuestionId !== null) {
        const i = idxById.get(String(session.currentQuestionId))
        if (i !== undefined && i >= 0) options.currentQuestionIndex.value = i
      }
      options.mockPhase.value = 'running'
      await nextTick()
      options.startExamTimer()
      return true
    } catch (e) {
      console.error('[mock] 恢复考试会话失败', e)
      clearMockSession(options.getUserId(), options.getBankId())
      return false
    }
  }

  return { persistMockSession, restoreMockSession }
}
