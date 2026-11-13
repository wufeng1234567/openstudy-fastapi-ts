// composables/questionPracticeAnswer.ts
//
// 练习页**答案侧**的纯逻辑（从 `useQuestionPractice.ts` 抽出）。
//
//   · `applyServerGrade` —— 把服务端判分结果写回题目对象
//   · `stringifyAnswerForLog` —— 把各种形态的答案压成字符串写进流水
//   · `generateErrorNote` / `generateErrorTags` —— 答错时的错因备注与标签
//   · `hasAnswerValue` —— 判断答案是否**真的**填了（空白字符串不算）
//
// ⚠️ `applyServerGrade` 仍是 `useQuestionPractice()` 对外导出的一部分
//    （`PracticeComponent` / `usePracticeSubmission` 在用），
//    composable 侧原样转出，调用方无需改动。
import type { TransformedQuestion } from '@/types'

/** 把服务端判分结果写回题目对象，供解析区/答题卡/结算页共用 */
export function applyServerGrade(q: any, data: any): void {
  if (!q || !data) return
  if (data.correctAnswer !== undefined && data.correctAnswer !== null) {
    q.correctAnswer = data.correctAnswer
  }
  if (data.analysis !== undefined && data.analysis !== null) {
    q.analysis = data.analysis
  }
  if (Array.isArray(data.subResults) && data.subResults.length) {
    data.subResults.forEach((item: any) => {
      const sub = q.subQuestions?.[Number(item.subIndex)]
      if (!sub) return
      if (item.correctAnswer !== undefined && item.correctAnswer !== null) {
        sub.correctAnswer = item.correctAnswer
      }
      if (item.analysis !== undefined && item.analysis !== null) {
        sub.analysis = item.analysis
      }
    })
  }
  q.correct = data.isCorrect === true
  q.pending = data.pending === true
  q.answered = true
  q.showAnalysis = true
}

// 把各种形态的答案压成字符串写入流水（组合题传进来的是对象）
export function stringifyAnswerForLog(userAnswer: any): string {
  if (userAnswer === null || userAnswer === undefined) return ''
  if (Array.isArray(userAnswer)) return userAnswer.join(',')
  if (typeof userAnswer === 'object') {
    try {
      return JSON.stringify(userAnswer)
    } catch {
      return ''
    }
  }
  return String(userAnswer)
}
// ✅ 新增：生成错因备注
export function generateErrorNote(question: TransformedQuestion, userAnswer: any): string {
  const questionType = question.type
  const noteParts: string[] = []

  if (questionType === 'fillblank' || questionType === 'essay') {
    noteParts.push(`错误答案: "${userAnswer || '未填写'}"`)
    noteParts.push(`正确答案: "${question.correctAnswer}"`)
  } else if (questionType === 'single' || questionType === 'truefalse') {
    const userChoice = question.options && question.options[userAnswer] ? question.options[userAnswer] : '未选择'
    const correctChoice = question.options && question.options[question.correctAnswer] ? question.options[question.correctAnswer] : ''
    noteParts.push(`错误选项: ${userChoice}`)
    noteParts.push(`正确选项: ${correctChoice}`)
  } else if (questionType === 'multiple') {
    const userChoices = Array.isArray(userAnswer) && question.options
      ? userAnswer.map((idx: number) => question.options[idx] || `选项${idx}`).join(', ')
      : '未选择'
    const correctChoices = Array.isArray(question.correctAnswer) && question.options
      ? question.correctAnswer.map((idx: number) => question.options[idx] || `选项${idx}`).join(', ')
      : ''
    noteParts.push(`错误选项: ${userChoices}`)
    noteParts.push(`正确选项: ${correctChoices}`)
  }

  return noteParts.join(' | ')
}

// ✅ 新增：生成错题标签
export function generateErrorTags(questionType: string, userAnswer: any): string {
  const tags = ['自动记录']

  if (!userAnswer || (Array.isArray(userAnswer) && userAnswer.length === 0)) {
    tags.push('未作答')
  } else if (questionType === 'fillblank' || questionType === 'essay') {
    tags.push('主观题错误')
  } else {
    tags.push('选择题错误')
  }

  // 根据题目类型添加标签
  switch (questionType) {
    case 'single':
      tags.push('单选题')
      break
    case 'multiple':
      tags.push('多选题')
      break
    case 'truefalse':
      tags.push('判断题')
      break
    case 'fillblank':
      tags.push('填空题')
      break
    case 'essay':
      tags.push('问答题')
      break
  }

  return tags.join(',')
}

export function hasAnswerValue(value: any): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.length > 0
  if (typeof value === 'object') return Object.keys(value).some((k) => hasAnswerValue(value[k]))
  return true
}
