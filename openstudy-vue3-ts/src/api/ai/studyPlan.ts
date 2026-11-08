import request from '@/utils/request'

export interface StudyMapParams {
  kbId?: number
  bankIds?: number[]
  sourceTypes?: string[]
  seedNodeId?: string
  depth?: number
  limit?: number
}

export function getStudyMap(params: StudyMapParams = {}) {
  const p = params || {}
  return request({
    url: '/rag/study-map',
    method: 'get',
    params: {
      kbId: p.kbId || 0,
      bankIds: p.bankIds?.length ? p.bankIds.join(',') : undefined,
      sourceTypes: p.sourceTypes?.length ? p.sourceTypes.join(',') : 'wiki,bank',
      seedNodeId: p.seedNodeId || undefined,
      depth: p.depth ?? 2,
      limit: p.limit ?? 80
    }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export interface StudyTraceParams {
  kbId?: number
  bankIds?: number[]
  sourceTypes?: string[]
  seedNodeId?: string
  goal?: string
  dailyMinutes?: number
  horizonDays?: number
  instruction?: string
}

export function prepareStudyTrace(params: StudyTraceParams) {
  return request({
    url: '/rag/study-plan/trace',
    method: 'post',
    data: {
      kbId: params.kbId || 0,
      bankIds: params.bankIds || [],
      sourceTypes: params.sourceTypes?.length ? params.sourceTypes : ['wiki', 'bank'],
      seedNodeId: params.seedNodeId || '',
      goal: params.goal || 'weakness',
      dailyMinutes: params.dailyMinutes ?? 30,
      horizonDays: params.horizonDays ?? 14,
      instruction: params.instruction || ''
    }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export interface StudyAdviceParams extends StudyTraceParams {
  traceId?: string
  parentSnapshotId?: number
  save?: boolean
  useLlm?: boolean
}

export function generateStudyAdvice(params: StudyAdviceParams) {
  return request({
    url: '/rag/study-plan/advice',
    method: 'post',
    data: {
      kbId: params.kbId || 0,
      bankIds: params.bankIds || [],
      sourceTypes: params.sourceTypes?.length ? params.sourceTypes : ['wiki', 'bank'],
      seedNodeId: params.seedNodeId || '',
      goal: params.goal || 'weakness',
      dailyMinutes: params.dailyMinutes ?? 30,
      horizonDays: params.horizonDays ?? 14,
      instruction: params.instruction || '',
      traceId: params.traceId || '',
      parentSnapshotId: params.parentSnapshotId || 0,
      save: params.save !== false,
      useLlm: params.useLlm !== false
    }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function listStudyPlanHistory(limit = 20, keyword = '') {
  return request({
    url: '/rag/study-plan/history',
    method: 'get',
    params: { limit, keyword: keyword || undefined }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function getStudyPlanHistory(snapshotId: number) {
  return request({
    url: `/rag/study-plan/history/${snapshotId}`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function createStudyPlanHistory(payload: Record<string, any>) {
  return request({
    url: '/rag/study-plan/history',
    method: 'post',
    data: payload
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function updateStudyPlanHistory(snapshotId: number, payload: { title?: string; pinned?: boolean }) {
  return request({
    url: `/rag/study-plan/history/${snapshotId}`,
    method: 'patch',
    data: payload
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export function deleteStudyPlanHistory(snapshotId: number) {
  return request({
    url: `/rag/study-plan/history/${snapshotId}`,
    method: 'delete'
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}
