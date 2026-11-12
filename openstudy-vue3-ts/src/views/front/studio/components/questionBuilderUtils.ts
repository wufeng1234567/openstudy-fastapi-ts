/** QuestionBuilder 展示层的小型纯函数，不依赖组件 ref。 */

export function truncateText(text: string, maxLength: number): string {
  if (!text) return ''
  return text.length > maxLength ? `${text.substring(0, maxLength)}...` : text
}

export function getSubTypeName(type: string): string {
  const map: Record<string, string> = {
    single: '单选题',
    multiple: '多选题',
    judge: '判断题',
    fill: '填空题',
    essay: '简答题'
  }
  return map[type] || type
}

export function getSubTypeTagType(type: string): string {
  const map: Record<string, string> = {
    single: 'primary',
    multiple: 'success',
    judge: 'warning',
    fill: 'info',
    essay: ''
  }
  return map[type] || 'info'
}

export function isSubOptionCorrect(sub: any, optIdx: number): boolean {
  if (sub.type === 'single') return sub.correctAnswer === optIdx
  if (sub.type === 'multiple') return Array.isArray(sub.correctAnswer) && sub.correctAnswer.includes(optIdx)
  return false
}

export function formatSubAnswer(sub: any): any {
  if (sub.type === 'judge') return sub.correctAnswer ? '正确' : '错误'
  return sub.correctAnswer
}
