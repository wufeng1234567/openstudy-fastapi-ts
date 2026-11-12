import { getPlainText } from '@/utils/questionUtils'

export function truncate(text: string, len: number): string {
  if (!text) return ''
  const str = String(text)
  return str.length > len ? `${str.slice(0, len)}...` : str
}

export function getQuestionText(q: any): string {
  if (!q) return ''
  return getPlainText(q.questionText || q.content || q.questionContent || '')
}

export function getBankName(bank: any): string {
  return bank.bankName || bank.name || `题库${bank.bankId || bank.bankId}`
}

export function getBankId(bank: any): any {
  return bank.questionBankId || bank.bankId || bank.bankId
}

export function formatTime(time: any): string {
  if (!time) return ''
  const date = new Date(time)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getTagList(tags: any): any {
  if (!tags) return []
  if (typeof tags === 'string') return tags.split(',').filter((t) => t.trim())
  return tags
}
