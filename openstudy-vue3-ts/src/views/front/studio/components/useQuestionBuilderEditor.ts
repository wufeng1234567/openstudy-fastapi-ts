import type { Ref } from 'vue'

/** QuestionBuilder 的题型推导、题目计数与克隆选择。 */
export function useQuestionBuilderEditor(options: {
  questions: Ref<any[]>
  currentId: Ref<any>
  questionTypes: Ref<any[]>
  aiForm: Ref<any>
}) {
  const previewTypeOf = (q: any): string => {
    if (Array.isArray(q?.subQuestions) && q.subQuestions.length > 0) return 'composite'
    if (q?.content && Array.isArray(q?.questions) && q.questions.length > 0) return 'composite'
    const type = String(q?.type || q?.questionType || '').trim()
    if (type && type !== 'custom') return type
    const fallback = String(options.aiForm.value.questionType || '').trim()
    return fallback && fallback !== 'custom' ? fallback : 'single'
  }

  const getTypeCount = (type: string) => options.questions.value.filter((q: any) => q.type === type).length

  const cloneQuestion = (typeItem: any) => {
    const newId = Date.now() + Math.random()
    const base: any = { id: newId, type: typeItem.type, title: '', analysis: '', score: 5, content: '' }
    if (typeItem.type === 'composite') {
      base.subQuestions = []
      base.content = ''
    } else if (typeItem.type === 'single' || typeItem.type === 'multiple') {
      base.options = ['选项A', '选项B']
      base.optionsJson = JSON.stringify(base.options)
      base.answer = typeItem.type === 'single' ? 0 : []
    } else if (typeItem.type === 'judge') {
      base.answer = false
    } else {
      base.answer = ''
    }
    options.questions.value.push(base)
    options.currentId.value = newId
    return base
  }

  const selectQuestion = (id: any) => {
    options.currentId.value = id
  }

  return { previewTypeOf, getTypeCount, cloneQuestion, selectQuestion }
}
