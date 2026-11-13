/** QuestionBuilder AI 输出归一化（纯函数，不依赖组件状态）。 */

import { textToHtml } from '@/utils/questionUtils'

export const extractJsonFromAiResponse = (text: any) => {
  if (!text) { console.warn('【extractJson】text 为空'); return null }
  if (typeof text === 'object') return text

  try {
    const direct = JSON.parse(text)
    return direct
  } catch (e) {
  }

  let cleaned = text
    .replace(/```json\s*|\s*```/gi, '')
    .replace(/```\s*|\s*```/g, '')
    .replace(/[\u0000-\u001F\u007F-\u009F]/g, '')
    .trim()


  let start = cleaned.indexOf('[')
  let end = cleaned.lastIndexOf(']')

  if (start === -1) {
    start = cleaned.indexOf('{')
    end = cleaned.lastIndexOf('}')
  }


  if (start !== -1 && end !== -1 && end > start) {
    cleaned = cleaned.substring(start, end + 1)
  }

  cleaned = cleaned.replace(/([{,]\s*)([a-zA-Z_$][a-zA-Z0-9_$]*)\s*:/g, '$1"$2":')
  cleaned = cleaned.replace(/,(\s*[}\]])/g, '$1')

  try {
    const result = JSON.parse(cleaned)
    return result
  } catch (e: any) {
    console.warn('【extractJson】清理后解析失败:', e.message)
    const fallback = text.substring(
      text.indexOf('[') !== -1 ? text.indexOf('[') : text.indexOf('{'),
      text.lastIndexOf(']') !== -1 ? text.lastIndexOf(']') + 1 : text.lastIndexOf('}') + 1
    )
    try {
      return JSON.parse(fallback)
    } catch (e2: any) {
      console.error('【extractJson】JSON解析完全失败:', e2.message)
      console.error('【extractJson】最终尝试解析的内容前500字符:', fallback.substring(0, 500))
      return null
    }
  }
}

// 把 AI 返回的字段名统一成「美化预览 / 导入」需要的结构
// AI 通常返回 questionText / answer，而预览与导入使用 question / correctAnswer
export const toOptionIndex = (item: any, options: any) => {
  if (typeof item === 'number') return item
  const text = String(item ?? '').trim()
  if (text === '') return item
  // 1) 直接是选项文本（如 answer: "class"）
  const byText = options.findIndex((opt: any) => String(opt).trim().toLowerCase() === text.toLowerCase())
  if (byText >= 0) return byText
  // 2) A/B/C/D 形式
  const letter = text.replace(/[.、:：)\s]/g, '').toUpperCase()
  if (/^[A-Z]$/.test(letter)) {
    const idx = letter.charCodeAt(0) - 65
    if (idx >= 0 && idx < options.length) return idx
  }
  // 3) 数字下标
  if (/^\d+$/.test(text)) {
    const idx = Number(text)
    if (idx >= 0 && idx < options.length) return idx
  }
  return item
}

// 选择题答案归一化：支持 选项文本 / A-D / 数字下标 / 逗号分隔多选
export const normalizeAiAnswer = (answer: any, options: any, questionType: any) => {
  if (!Array.isArray(options) || options.length === 0) return answer
  const isMultiple = questionType === 'multiple' || questionType === 2
  const toArray = (val: any) => {
    if (Array.isArray(val)) return val.map(v => toOptionIndex(v, options)).filter(v => typeof v === 'number')
    if (typeof val === 'string' && /[,，]/.test(val)) {
      return val.split(/[,，]/).map(v => toOptionIndex(v.trim(), options)).filter(v => typeof v === 'number')
    }
    return null
  }
  if (isMultiple) {
    const arr = toArray(answer)
    if (arr) return arr
    const idx = toOptionIndex(answer, options)
    return typeof idx === 'number' ? [idx] : []
  }
  const arr = toArray(answer)
  if (arr) return arr.length ? arr[0] : answer
  return toOptionIndex(answer, options)
}

export const normalizeAiQuestion = (q: any, defaultScore = 5, questionType = '') => {
  if (!q || typeof q !== 'object') return q
  const normalized = { ...q }

  /*
   * ── 组合题要**递归归一化子题**（2026-10-20 方案 B）──────────────
   *
   * 混排出题时，模型返回的组合题里嵌着 questions[]（子题）。
   * 如果只归一化外层：
   *   · 子题的 `answer` 不会转成 `correctAnswer` → 预览里答案框是空的；
   *   · 子题的 `options` 若是 JSON 字符串，预览 v-for 遍历会报错。
   *
   * ⚠️ 只处理一层嵌套：组合题里再套组合题没有业务意义（编辑器也不支持），
   *    真出现了就让内层保持原样，由用户自己看原始 JSON 修。
   */
  const rawSubs = normalized.subQuestions || normalized.questions
  if (Array.isArray(rawSubs) && rawSubs.length > 0) {
    normalized.subQuestions = rawSubs.map((s: any) =>
      normalizeAiQuestion(s, 2, s?.type || s?.questionType || '')
    )
    // 材料字段统一成内部命名 `content`（编辑器认这个）
    if (!normalized.content) {
      normalized.content = normalized.passage || normalized.material || ''
    }
    if (normalized.score === undefined || normalized.score === null) {
      normalized.score = 10
    }
    return normalized
  }

  if (normalized.question === undefined || normalized.question === null || normalized.question === '') {
    normalized.question = normalized.questionText || normalized.title || normalized.questionContent || ''
  }
  if (normalized.correctAnswer === undefined || normalized.correctAnswer === null) {
    if (normalized.answer !== undefined && normalized.answer !== null) {
      normalized.correctAnswer = normalized.answer
    }
  }
  if (normalized.score === undefined || normalized.score === null) {
    normalized.score = defaultScore
  }
  // options 若是 JSON 字符串，转成数组，供预览 v-for 使用
  if (typeof normalized.options === 'string') {
    try {
      const parsedOptions = JSON.parse(normalized.options)
      if (Array.isArray(parsedOptions)) normalized.options = parsedOptions
    } catch (e) { /* 保持原样 */ }
  }
  // 答案归一化：把「选项文本 / A-D / 数字」统一成 option 下标
  if (Array.isArray(normalized.options) && normalized.correctAnswer !== undefined && normalized.correctAnswer !== null) {
    const type = questionType || normalized.type || normalized.questionType || ''
    normalized.correctAnswer = normalizeAiAnswer(normalized.correctAnswer, normalized.options, type)
  }
  return normalized
}

export const convertAiQuestionToInternal = (aiQuestion: any, questionType: any) => {
  const newId = Date.now() + Math.random() + Math.floor(Math.random() * 1000)
  /*
   * ⚠️ 题型取值优先级（2026-10-20 修）：
   *   ① `aiQuestion.type` —— AI 为**每道题**标注的题型
   *   ② 调用方传的 `questionType` —— 整批统一题型
   *   ③ 兜底 'single'
   *
   * 为什么必须让 ① 优先：
   *   自定义出题（custom）允许**一次生成多种题型**（3 道选择 + 2 道填空…），
   *   后端模板已要求模型为每题输出 `type`。若这里仍用"整批的 questionType"，
   *   custom 模式下会得到一个 `type: 'custom'` 的非法题目 ——
   *   编辑器不认识它，预览会渲染成空白。
   *
   *   而固定题型场景下 `aiQuestion.type` 通常不存在（或与批次一致），
   *   所以 ② 仍然是实际生效的那一个，行为不变。
   */
  const resolvedType = mapAiTypeToInternal(
    aiQuestion?.type || aiQuestion?.questionType || questionType
  )

  /*
   * ── 组合题（2026-10-20 方案 B）────────────────────────────────────
   *
   * 背景：自定义出题原来**只能出单一题型**，组合题走独立分支
   * （`generateCompositeStreamFull`，一次整批都是组合题）。
   * 用户要求「一批里混组合题」，于是打开了两条链路。
   *
   * ⚠️ 为什么要单独走这里、而不是复用 `aiForm.questionType === 'composite'`：
   *   那个判断是**整批级**的（`isCompositePreview` 看整份数据是否有
   *   passage + questions）。混排时一批里既有普通题又有组合题，
   *   整批级判断没法表达"第 7 道是组合题、第 8 道是单选题"。
   *
   * 复用 `convertCompositeFromAi`：它已经处理好了 passage → content、
   * 子题选项/答案归一化、sortOrder。再写一份是重复且容易走偏。
   */
  if (resolvedType === 'composite') {
    return convertCompositeFromAi({
      passage: aiQuestion.passage || aiQuestion.content || aiQuestion.material || '',
      // 兼容几种可能的字段名：模型有时用 subQuestions / questions / subs
      questions: aiQuestion.questions || aiQuestion.subQuestions || aiQuestion.subs || [],
      title: aiQuestion.title
    })
  }

  const base: any = {
    id: newId,
    type: resolvedType,
    title: textToHtml(aiQuestion.question || aiQuestion.questionText || aiQuestion.title || ''),
    analysis: aiQuestion.analysis || '',
    score: 5
  }
  if (resolvedType === 'single' || resolvedType === 'multiple') {
    let rawOptions = aiQuestion.options
    let options: any[] = []
    if (Array.isArray(rawOptions)) options = rawOptions.map(opt => String(opt).trim())
    else if (typeof rawOptions === 'string') {
      try { options = JSON.parse(rawOptions) } catch { options = rawOptions.split(',').map(s => s.trim().replace(/^["']|["']$/g, '')) }
    }
    options = options.filter((opt: any) => opt !== '')
    if (options.length === 0) options = ['选项A', '选项B']
    options = options.map((opt: any) => opt.replace(/^[A-Z][\.\:]\s*/, ''))
    base.options = options
    base.optionsJson = JSON.stringify(options)
    let ans = aiQuestion.correctAnswer ?? aiQuestion.answer
    if (resolvedType === 'single') {
      if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
      else if (typeof ans === 'number') ans = Math.min(ans, options.length - 1)
      else ans = 0
      base.answer = ans >= 0 && ans < options.length ? ans : 0
    } else {
      let arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map(s => s.trim()) : []
      base.answer = arr.map(item => {
        if (typeof item === 'string' && /[A-Za-z]/.test(item)) return item.toUpperCase().charCodeAt(0) - 65
        return typeof item === 'number' ? item : 0
      }).filter(idx => idx >= 0 && idx < options.length)
    }
  } else if (resolvedType === 'judge') {
    let ans = aiQuestion.correctAnswer ?? aiQuestion.answer
    if (typeof ans === 'boolean') base.answer = ans
    else if (typeof ans === 'string') base.answer = ['true', '正确', '对', 't'].includes(ans.toLowerCase())
    else base.answer = false
  } else {
    base.answer = aiQuestion.correctAnswer || aiQuestion.answer || ''
  }
  return base
}

export const convertCompositeFromAi = (aiData: any) => {
  const newId = Date.now() + Math.random()
  const composite = {
    id: newId,
    type: 'composite',
    title: textToHtml(aiData.title || '阅读理解'),
    content: textToHtml(aiData.passage || ''),
    analysis: '',
    score: 10,
    subQuestions: []
  }
  const questions = aiData.questions || []
  composite.subQuestions = questions.map((q: any, index: any) => {
    const subType = mapAiTypeToInternal(q.type)
    const sub: any = {
      id: Date.now() + Math.random() + index,
      type: subType,
      question: textToHtml(q.question || q.questionText || ''),
      score: q.score || 2,
      analysis: q.analysis || '',
      sortOrder: index
    }
    if (subType === 'single' || subType === 'multiple') {
      let opts = q.options || []
      if (typeof opts === 'string') { try { opts = JSON.parse(opts) } catch { opts = [] } }
      opts = opts.map((opt: any) => String(opt).trim()).filter((opt: any) => opt)
      if (opts.length === 0) opts = ['选项A', '选项B']
      sub.options = opts
      sub.optionsJson = JSON.stringify(opts)
      let ans = q.correctAnswer ?? q.answer
      if (subType === 'single') {
        if (typeof ans === 'string' && /[A-Za-z]/.test(ans)) ans = ans.toUpperCase().charCodeAt(0) - 65
        else if (typeof ans === 'number') ans = ans
        else ans = 0
        sub.answer = ans >= 0 && ans < opts.length ? ans : 0
      } else {
        let arr = Array.isArray(ans) ? ans : typeof ans === 'string' ? ans.split(',').map(s => s.trim()) : []
        sub.answer = arr.map(item => {
          if (typeof item === 'string' && /[A-Za-z]/.test(item)) return item.toUpperCase().charCodeAt(0) - 65
          return typeof item === 'number' ? item : 0
        }).filter(idx => idx >= 0 && idx < opts.length)
      }
    } else if (subType === 'judge') {
      let ans = q.correctAnswer ?? q.answer
      if (typeof ans === 'boolean') sub.answer = ans
      else if (typeof ans === 'string') sub.answer = ['true', '正确', '对'].includes(ans.toLowerCase())
      else sub.answer = false
    } else {
      sub.answer = q.correctAnswer || q.answer || ''
    }
    return sub
  })
  return composite
}

export const mapAiTypeToInternal = (typeStr: any) => {
  /*
   * ⚠️ `composite` 必须显式列出（2026-10-20 方案 B）。
   *
   * 原来映射表里没有它，AI 返回 `type: "composite"` 时会落到 `|| 'single'`
   * 兜底 —— 一道带材料的小题组题被静默降级成单选题，
   * passage 和子题全部丢失，用户只看到一道内容像材料的选择题。
   * 这种"悄悄改对成错"比报错更难发现。
   */
  const map: Record<string, string> = {
    single: 'single',
    multiple: 'multiple',
    judge: 'judge',
    fill: 'fill',
    essay: 'essay',
    composite: 'composite'
  }
  return map[typeStr] || 'single'
}
