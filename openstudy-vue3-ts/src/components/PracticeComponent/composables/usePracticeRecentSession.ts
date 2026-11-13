import { ref } from 'vue'
import { getPracticeSession, listPracticeSessions } from '@/api/questionMain/questionMain'

/** 最近一次已交卷练习的读取与回看。 */
export function usePracticeRecentSession(options: {
  getBankId: () => number
  getModuleTypeSafe: () => string
  proxy: any
}) {
  const recentSession = ref<any>(null)

  async function loadRecentSession() {
    try {
      const res: any = await listPracticeSessions(10)
      const list: any[] = Array.isArray(res?.data) ? res.data : []
      recentSession.value =
        list.find(
          (s: any) =>
            String(s.bankId) === String(options.getBankId()) &&
            s.status === 'submitted' &&
            (options.getModuleTypeSafe() === 'mock' ? s.moduleType === 'mock' : s.moduleType !== 'mock')
        ) || null
    } catch {
      recentSession.value = null
    }
  }

  async function openRecentSession() {
    if (!recentSession.value?.sessionId) return
    try {
      const res: any = await getPracticeSession(recentSession.value.sessionId)
      if (res?.code !== 200) {
        options.proxy.$modal.msgError(res?.msg || '读取练习成绩失败')
        return
      }
      const d = res.data || {}
      const lines = (d.items || []).map((it: any, i: number) => {
        const label = it.isCorrect === true ? '正确' : it.pending ? '待自评' : it.answered ? '错误' : '未答'
        return `${i + 1}. ${label}（${Number(it.scoreAwarded || 0)}/${Number(it.maxScore || 0)} 分）`
      })
      options.proxy.$modal.alert(
        `上次练习成绩：${d.score}/${d.totalScore} 分（${d.percentage}%）\n` +
          `答对 ${d.correctCount} · 答错 ${d.wrongCount} · 待自评 ${d.pendingCount}\n\n${lines.join('\n')}`,
        '上次练习成绩'
      )
    } catch {
      options.proxy.$modal.msgError('读取练习成绩失败')
    }
  }

  return { recentSession, loadRecentSession, openRecentSession }
}
