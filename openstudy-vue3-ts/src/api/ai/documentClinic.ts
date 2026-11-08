import request from '@/utils/request'

export function generateSmartReport(docId: number, options: { instruction?: string; useLlm?: boolean } = {}) {
  return request({
    url: `/rag/workspace/documents/${docId}/smart-report/generate`,
    method: 'post',
    data: {
      instruction: options.instruction || '',
      useLlm: options.useLlm !== false
    },
    timeout: 120000
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}
