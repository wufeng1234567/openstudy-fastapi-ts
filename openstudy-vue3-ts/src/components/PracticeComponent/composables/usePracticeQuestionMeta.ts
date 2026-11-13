import { computed } from 'vue'

/** 练习页的题型分组与作答统计。 */
export function usePracticeQuestionMeta(options: {
  questions: { value: any[] }
  answers: { value: any[] }
  totalQuestions: { value: number }
}) {
  const typeLabelMap: Record<string, string> = {
    single: '单选题',
    multiple: '多选题',
    truefalse: '判断题',
    fillblank: '填空题',
    essay: '问答题',
    readingComprehension: '组合题',
    cloze: '完形填空'
  }

  const questionGroups = computed(() => {
    const groupMap: Record<string, any> = {}
    options.questions.value.forEach((q: any, i: number) => {
      const label = typeLabelMap[q.type] || '其他'
      if (!groupMap[label]) {
        groupMap[label] = { typeLabel: label, typeName: q.type, startIndex: i, endIndex: i, items: [] }
      }
      groupMap[label].endIndex = i
      groupMap[label].items.push({ ...q, index: i })
    })
    return Object.values(groupMap)
  })

  const answeredCount = computed(
    () =>
      options.answers.value.filter((a: any) => {
        if (a === null || a === undefined) return false
        if (typeof a === 'string') return a.trim().length > 0
        if (Array.isArray(a)) return a.length > 0
        if (typeof a === 'object') return Object.keys(a).length > 0
        return true
      }).length
  )
  const remainingCount = computed(() => options.totalQuestions.value - answeredCount.value)

  return { typeLabelMap, questionGroups, answeredCount, remainingCount }
}
