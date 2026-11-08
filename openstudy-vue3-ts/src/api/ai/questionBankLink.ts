import request from '@/utils/request'

export interface KbQuestionBank {
  bankId: number
  bankName: string
  subject?: string
  description?: string
  questionCount?: number
  linked?: boolean
}

export function listKbQuestionBanks(kbId: number | string) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/question-banks`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: { linked: KbQuestionBank[]; available: KbQuestionBank[] } }>
}

export function linkKbQuestionBank(kbId: number | string, bankId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/question-banks`,
    method: 'post',
    data: { bankId }
  }) as unknown as Promise<{ code: number; msg?: string; data: KbQuestionBank }>
}

export function getKbQuestionBankKnowledge(kbId: number | string, bankId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/question-banks/${bankId}/knowledge`,
    method: 'get',
    timeout: 120000
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function unlinkKbQuestionBank(kbId: number | string, bankId: number) {
  return request({
    url: `/rag/workspace/kbs/${kbId}/question-banks/${bankId}`,
    method: 'delete'
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}
