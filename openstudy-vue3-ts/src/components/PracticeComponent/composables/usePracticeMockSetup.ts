import { nextTick } from 'vue'
import { buildMockPaper, normalizeType } from '../utils/practiceQuestionUtils'
import { listQuestionMainAll, startPracticeSession } from '@/api/questionMain/questionMain'
import { EXAM_BANK_ID_KEY, EXAM_END_TIME_KEY } from './usePracticeExamTimer'

/** 模拟考试题量统计、配置组卷和开始考试。 */
export function usePracticeMockSetup(options: {
  mockAvailable: { value: Record<string, number> }
  activeMockConfig: { value: any }
  examStartAt: { value: number }
  mockPhase: { value: string }
  practiceSessionId: { value: string | number | null }
  store: any
  proxy: any
  getBankId: () => number
  updateQuestionOffset: (value: number) => void
  updateQuestionCount: (value: number) => void
  processQuestions: (list: any[]) => Promise<void> | void
  startExamTimer: () => void
  setMockSessionEndAt: (value: number) => void
}) {
  async function loadMockAvailability(): Promise<void> {
    try {
      const res: any = await listQuestionMainAll({ bankId: options.getBankId(), status: '0', withAnswer: false })
      const data: any[] = Array.isArray(res?.data) ? res.data : Array.isArray(res?.result) ? res.result : []
      const counter: Record<string, number> = {}
      for (const q of data) {
        const type = normalizeType(q.questionType ?? q.question_type)
        counter[type] = (counter[type] || 0) + 1
      }
      options.mockAvailable.value = counter
      const cfg = options.store.getMockExamConfig()
      let changed = false
      for (const row of cfg.typeRows) {
        const cap = counter[row.type] || 0
        if (row.count > cap) {
          row.count = cap
          changed = true
        }
      }
      if (changed) options.store.saveMockExamConfig(cfg)
    } catch (e) {
      console.warn('[mock] 读取题库题量失败', e)
      options.mockAvailable.value = {}
    }
  }

  async function handleMockStart(cfg: any) {
    options.activeMockConfig.value = JSON.parse(JSON.stringify(cfg))
    options.examStartAt.value = Date.now()
    const endAt = options.examStartAt.value + (Number(cfg.timeLimit) || 60) * 60000
    options.setMockSessionEndAt(endAt)
    localStorage.setItem(EXAM_END_TIME_KEY, String(endAt))
    localStorage.setItem(EXAM_BANK_ID_KEY, String(options.getBankId()))

    try {
      const res: any = await listQuestionMainAll({ bankId: options.getBankId(), status: '0', withAnswer: false })
      const pool: any[] = Array.isArray(res?.data) ? res.data : Array.isArray(res?.result) ? res.result : []
      if (!pool.length) {
        options.proxy.$modal.msgWarning('这个题库还没有题目，无法开始考试')
        options.mockPhase.value = 'setup'
        return
      }
      const paper = buildMockPaper(cfg, pool)
      if (!paper.length) {
        options.proxy.$modal.msgWarning('按当前配置没有抽到题目，请调整题型题数')
        options.mockPhase.value = 'setup'
        return
      }
      const sessionRes: any = await startPracticeSession({
        bankId: options.getBankId(),
        moduleType: 'mock',
        questionIds: paper.map((q: any) => q.id),
        scores: Object.fromEntries(paper.map((q: any) => [String(q.id), Number(q._mockScore) || 0]))
      })
      if (sessionRes?.code !== 200 || !sessionRes?.data?.sessionId) {
        options.proxy.$modal.msgError(sessionRes?.msg || '创建考试会话失败，请重试')
        options.mockPhase.value = 'setup'
        return
      }
      options.practiceSessionId.value = String(sessionRes.data.sessionId)
      options.updateQuestionOffset(0)
      options.updateQuestionCount(paper.length)
      await options.processQuestions(paper)
    } catch (e) {
      console.error('[mock] 组卷失败', e)
      options.proxy.$modal.msgError('组卷失败，请重试')
      options.mockPhase.value = 'setup'
      return
    }

    options.mockPhase.value = 'running'
    await nextTick()
    options.startExamTimer()
  }

  return { loadMockAvailability, handleMockStart }
}
