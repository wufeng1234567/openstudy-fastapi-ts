import { ElMessage } from 'element-plus'
import {
  convertAiQuestionToInternal,
  convertCompositeFromAi,
  extractJsonFromAiResponse,
  mapAiTypeToInternal,
  normalizeAiQuestion
} from './questionBuilderAi'
import { textToHtml } from '@/utils/questionUtils'

/** AI 生成结果解析、预览和导入。 */
export function useQuestionBuilderAiResult(options: {
  aiForm: any
  parsedQuestionsForPreview: any
  editablePreviewData: any
  pendingImportData: any
  rawJsonContent: any
  generatedCount: any
  viewMode: any
  aiGenerating: any
  questions: any
  currentId: any
  savePromptToHistory: () => void
}) {
  const finishAiGenerate = (rawData: any, isComposite: boolean) => {
    let actualData = rawData
    if (rawData && typeof rawData === 'object' && rawData.msg !== undefined) actualData = rawData.msg

    let parsed = actualData
    if (typeof actualData === 'string') {
      options.rawJsonContent.value = actualData
      parsed = extractJsonFromAiResponse(actualData)
    } else {
      options.rawJsonContent.value = JSON.stringify(actualData, null, 2)
    }
    if (!parsed) {
      ElMessage.error('AI 返回数据解析失败，请查看原始 JSON')
      options.aiGenerating.value = false
      return
    }
    if (isComposite) {
      if (!parsed.passage || !parsed.questions || !Array.isArray(parsed.questions)) {
        ElMessage.error('AI 返回的组合题数据格式不正确')
        options.aiGenerating.value = false
        return
      }
    } else if (!Array.isArray(parsed)) {
      if (parsed && typeof parsed === 'object' && (parsed.question || parsed.questionText)) parsed = [parsed]
      else {
        ElMessage.error('AI 返回的题目数据格式不正确')
        options.aiGenerating.value = false
        return
      }
    }

    if (isComposite) {
      parsed.questions = (parsed.questions || []).map((q: any) => normalizeAiQuestion(q, 2, q.type || q.questionType))
    } else {
      const fallbackType = options.aiForm.value.questionType
      parsed = Array.isArray(parsed)
        ? parsed.map((q: any) => normalizeAiQuestion(q, 5, q.type || q.questionType || fallbackType))
        : normalizeAiQuestion(parsed, 5, parsed.type || parsed.questionType || fallbackType)
    }

    options.generatedCount.value = isComposite ? parsed.questions?.length || 0 : Array.isArray(parsed) ? parsed.length : 1
    options.editablePreviewData.value = JSON.parse(JSON.stringify(parsed))
    options.parsedQuestionsForPreview.value = parsed
    options.pendingImportData.value = { isComposite, parsed: options.editablePreviewData.value, questionType: options.aiForm.value.questionType }
    options.viewMode.value = 'pretty'
    options.savePromptToHistory()
    ElMessage.success(`成功生成 ${options.generatedCount.value} 道题目，请确认后导入`)
    options.aiGenerating.value = false
  }

  const processParsedData = (isComposite: boolean, parsed: any) => {
    if (isComposite) {
      let composite: any = null
      if (parsed.passage && parsed.questions) composite = convertCompositeFromAi(parsed)
      else if (typeof parsed.passage === 'string' && !Array.isArray(parsed)) {
        composite = convertCompositeFromAi({ passage: parsed.passage, questions: parsed.questions || [] })
      } else if (Array.isArray(parsed)) {
        ElMessage.warning('AI 未返回文章内容，将仅导入子题')
        composite = { id: Date.now() + Math.random(), type: 'composite', title: '组合题（请手动填写材料）', content: '', analysis: '', score: 10, subQuestions: [] }
        parsed.forEach((q: any, idx: number) => {
          const subType = mapAiTypeToInternal(q.type || 'single')
          const sub: any = { id: Date.now() + Math.random() + idx, type: subType, question: textToHtml(q.question || q.questionText || ''), score: 2, analysis: q.analysis || '', sortOrder: idx }
          if (subType === 'single' || subType === 'multiple') {
            let opts = q.options || []
            if (typeof opts === 'string') try { opts = JSON.parse(opts) } catch { opts = [] }
            opts = opts.map((opt: any) => String(opt).trim()).filter((opt: any) => opt)
            if (opts.length === 0) opts = ['选项A', '选项B']
            sub.options = opts
            sub.optionsJson = JSON.stringify(opts)
            let ans = q.correctAnswer ?? q.answer
            if (subType === 'single') {
              if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
              else if (typeof ans !== 'number') ans = 0
              sub.answer = ans >= 0 && ans < opts.length ? ans : 0
            } else {
              const arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map((s: string) => s.trim()) : []
              sub.answer = arr.map((item: any) => typeof item === 'string' && /[A-Za-z]/.test(item) ? item.toUpperCase().charCodeAt(0) - 65 : typeof item === 'number' ? item : 0).filter((idx: number) => idx >= 0 && idx < opts.length)
            }
          } else if (subType === 'judge') {
            const ans = q.correctAnswer ?? q.answer
            sub.answer = typeof ans === 'boolean' ? ans : ['true', '正确', '对'].includes(String(ans).toLowerCase())
          } else {
            sub.answer = q.correctAnswer || q.answer || ''
          }
          composite.subQuestions.push(sub)
        })
      } else {
        ElMessage.error('组合题格式不正确')
        return
      }
      if (composite) {
        options.questions.value.push(composite)
        options.currentId.value = composite.id
        ElMessage.success('成功生成 1 道组合题')
      }
    } else {
      const questionArray = Array.isArray(parsed) ? parsed : [parsed]
      let addedCount = 0
      for (const q of questionArray) {
        try {
          options.questions.value.push(convertAiQuestionToInternal(q, options.aiForm.value.questionType))
          addedCount++
        } catch {
          console.warn('转换单题失败')
        }
      }
      if (addedCount > 0 && options.questions.value.length > 0) options.currentId.value = options.questions.value[options.questions.value.length - 1]?.id
      else if (!addedCount) ElMessage.warning('没有成功添加任何题目')
    }
  }

  const importGeneratedQuestions = () => {
    if (!options.pendingImportData.value) {
      ElMessage.warning('没有可导入的题目')
      return
    }
    const { isComposite, parsed, questionType } = options.pendingImportData.value
    const originalType = options.aiForm.value.questionType
    options.aiForm.value.questionType = questionType
    processParsedData(isComposite, parsed)
    options.aiForm.value.questionType = originalType
    ElMessage.success(`成功导入 ${options.generatedCount.value} 道题目`)
    options.pendingImportData.value = null
    options.parsedQuestionsForPreview.value = null
    options.editablePreviewData.value = null
    options.rawJsonContent.value = ''
  }

  const discardGeneratedQuestions = () => {
    options.parsedQuestionsForPreview.value = null
    options.editablePreviewData.value = null
    options.pendingImportData.value = null
    options.rawJsonContent.value = ''
    ElMessage.info('已丢弃生成的题目')
  }

  return { finishAiGenerate, processParsedData, importGeneratedQuestions, discardGeneratedQuestions }
}
