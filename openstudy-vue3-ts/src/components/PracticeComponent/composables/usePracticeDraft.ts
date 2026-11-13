import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createDraftSaver, loadDraft, type DraftSaveState } from '@/utils/practiceDraft'

/** 练习草稿的自动保存状态和快照构建器。 */
export function usePracticeDraft(options: {
  getUserId: () => any
  getBankId: () => any
  getModuleType: () => any
  getQuestions: () => any[]
  getAnswers: () => any[]
  getSubFillBlank: () => Record<string, any>
  getSubEssay: () => Record<string, any>
  getCurrentQuestion: () => any
  getQuestionOffset: () => number
  getQuestionCount: () => number
  getHasSubmittedCurrentBatch: () => boolean
  getCorrectCount: () => number
  getWrongCount: () => number
  getModuleTypeSafe: () => string
  getAllQuestionsData: () => any[]
  isPracticeMode: () => boolean
  loadBatchWithoutReset: () => void
  goToQuestion: (index: number) => void
  setQuestionOffset: (value: number) => void
}) {
  const draftState = ref<DraftSaveState>('idle')
  const draftSavedAt = ref(0)
  const draftRestored = ref(false)
  let draftRestoredOnce = false

  function buildDraftSnapshot() {
    const ids: Array<number | string> = []
    const answersById: Record<string, any> = {}
    const judgedById: Record<string, boolean> = {}
    const correctById: Record<string, boolean> = {}
    const fillById: Record<string, Record<string, any>> = {}
    const essayById: Record<string, Record<string, any>> = {}
    const answers = options.getAnswers()
    const list = options.getQuestions() || []

    list.forEach((q: any, idx: number) => {
      if (!q) return
      const qid = q.id ?? q.questionId ?? idx
      ids.push(qid)
      const ans = answers?.[idx]
      const hasAnswer =
        ans === null || ans === undefined
          ? false
          : typeof ans === 'object'
            ? Array.isArray(ans)
              ? ans.length > 0
              : Object.keys(ans).length > 0
            : ans !== ''
      if (hasAnswer) answersById[String(qid)] = ans
      if (q.answered) judgedById[String(qid)] = true
      if (q.correct === true || q.correct === false) correctById[String(qid)] = !!q.correct
    })

    Object.keys(options.getSubFillBlank() || {}).forEach((k) => {
      const [qid, sub] = String(k).split('_')
      if (!qid || sub === undefined) return
      const value = (options.getSubFillBlank() as any)[k]
      if (value === null || value === undefined || value === '') return
      ;(fillById[qid] ||= {})[sub] = value
    })
    Object.keys(options.getSubEssay() || {}).forEach((k) => {
      const [qid, sub] = String(k).split('_')
      if (!qid || sub === undefined) return
      const value = (options.getSubEssay() as any)[k]
      if (value === null || value === undefined || value === '') return
      ;(essayById[qid] ||= {})[sub] = value
    })

    const cur = options.getCurrentQuestion()
    const curId = cur ? cur.id ?? cur.questionId ?? null : null
    return {
      bankId: options.getBankId(),
      moduleType: options.getModuleType(),
      questionIds: ids,
      answers: answersById,
      judged: judgedById,
      correct: correctById,
      subFillBlank: fillById,
      subEssay: essayById,
      currentQuestionId: curId,
      batchIndex: Math.floor((options.getQuestionOffset() || 0) / Math.max(1, options.getQuestionCount() || 10)),
      batchSize: options.getQuestionCount() || 10,
      submittedBatches: options.getHasSubmittedCurrentBatch() ? [options.getQuestionOffset() || 0] : [],
      stats: { correct: options.getCorrectCount() || 0, wrong: options.getWrongCount() || 0, elapsedMs: 0 }
    }
  }

  function handleDraftStateChange(state: DraftSaveState, at?: number) {
    draftState.value = state
    if (state === 'saved' && at) draftSavedAt.value = at
    if (state === 'failed') ElMessage.warning('进度自动保存失败：浏览器存储不可用或空间不足')
  }

  const draftSaver = createDraftSaver({
    getUserId: options.getUserId,
    getBankId: options.getBankId,
    getModuleType: options.getModuleType,
    buildSnapshot: buildDraftSnapshot as any,
    onStateChange: handleDraftStateChange
  })

  function resetDraftRestored() {
    draftRestoredOnce = false
    draftRestored.value = false
  }

  function restoreDraftIfAny(retry = 0) {
    if (draftRestoredOnce) return
    if (options.getModuleTypeSafe() === 'mock') {
      draftRestoredOnce = true
      draftRestored.value = true
      return
    }
    const draft = loadDraft(options.getUserId(), options.getBankId(), options.getModuleType())
    if (!draft) {
      draftRestoredOnce = true
      draftRestored.value = true
      return
    }

    const batchSize = Math.max(1, Number(draft.batchSize) || options.getQuestionCount() || 10)
    const wantOffset = Math.max(0, Number(draft.batchIndex || 0) * batchSize)
    if (wantOffset !== (options.getQuestionOffset() || 0) && options.getAllQuestionsData().length > wantOffset) {
      options.setQuestionOffset(wantOffset)
      options.loadBatchWithoutReset()
    }

    const list = options.getQuestions() || []
    if (!list.length) {
      if (retry < 20) setTimeout(() => restoreDraftIfAny(retry + 1), 150)
      return
    }

    const idxById = new Map<string, number>()
    list.forEach((q: any, i: number) => {
      const qid = q?.id ?? q?.questionId ?? i
      idxById.set(String(qid), i)
    })

    let restoredCount = 0
    Object.keys(draft.answers || {}).forEach((qid) => {
      const i = idxById.get(String(qid))
      if (i === undefined) return
      const cur = options.getAnswers()?.[i]
      if (cur !== null && cur !== undefined && cur !== '') return
      options.getAnswers()[i] = draft.answers[qid]
      restoredCount += 1
    })
    Object.keys(draft.judged || {}).forEach((qid) => {
      const i = idxById.get(String(qid))
      if (i === undefined) return
      const q = list[i]
      if (!q) return
      q.answered = true
      if (draft.correct && typeof draft.correct[qid] === 'boolean') q.correct = draft.correct[qid]
      if (options.isPracticeMode()) q.showAnalysis = true
    })
    Object.keys(draft.subFillBlank || {}).forEach((qid) => {
      const subs = draft.subFillBlank[qid] || {}
      Object.keys(subs).forEach((sub) => {
        const k = `${qid}_${sub}`
        if (!(k in (options.getSubFillBlank() || {}))) (options.getSubFillBlank() as any)[k] = subs[sub]
      })
    })
    Object.keys(draft.subEssay || {}).forEach((qid) => {
      const subs = draft.subEssay[qid] || {}
      Object.keys(subs).forEach((sub) => {
        const k = `${qid}_${sub}`
        if (!(k in (options.getSubEssay() || {}))) (options.getSubEssay() as any)[k] = subs[sub]
      })
    })
    if (draft.currentQuestionId !== undefined && draft.currentQuestionId !== null) {
      const i = idxById.get(String(draft.currentQuestionId))
      if (i !== undefined) options.goToQuestion(i)
    }
    draftRestoredOnce = true
    draftRestored.value = true
    if (restoredCount > 0) {
      draftState.value = 'saved'
      draftSavedAt.value = draft.savedAt
    }
  }

  return { draftState, draftSavedAt, buildDraftSnapshot, draftSaver, draftRestored, resetDraftRestored, restoreDraftIfAny }
}
