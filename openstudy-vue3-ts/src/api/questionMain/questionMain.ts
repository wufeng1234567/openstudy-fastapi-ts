import request from '@/utils/request'
import type { QuestionMain, PageResult, ApiResult } from '@/types'

// 查询一级题目列表
export function listQuestionMain(query: any): Promise<PageResult<QuestionMain>> {
  return request({
    url: '/questionMain/questionMain/list',
    method: 'get',
    params: { ...query, withAnswer: query?.withAnswer ?? false }
  }) as unknown as Promise<PageResult<QuestionMain>>
}

// 查询一级题目列表 不分页
export function listQuestionMainAll(query?: any): Promise<ApiResult<QuestionMain[]>> {
  return request({
    url: '/questionMain/questionMain/all',
    method: 'get',
    params: { ...(query || {}), withAnswer: query?.withAnswer ?? false }
  }) as unknown as Promise<ApiResult<QuestionMain[]>>
}

// 查询一级题目详细
export function getQuestionMain(id: number | string, withAnswer = true): Promise<ApiResult<QuestionMain>> {
  return request({
    url: '/questionMain/questionMain/' + id,
    method: 'get',
    params: { withAnswer }
  }) as unknown as Promise<ApiResult<QuestionMain>>
}

// 题目的原文依据（从资料生成时写入的 source anchor）
export function getQuestionSource(questionId: number | string): Promise<ApiResult<any>> {
  return request({
    url: `/questionMain/questionMain/${questionId}/source`,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

// 新增一级题目
export function addQuestionMain(data: Partial<QuestionMain>): Promise<ApiResult> {
  return request({
    url: '/questionMain/questionMain',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 修改一级题目
export function updateQuestionMain(data: Partial<QuestionMain>): Promise<ApiResult> {
  return request({
    url: '/questionMain/questionMain',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除一级题目
export function delQuestionMain(id: number | string): Promise<ApiResult> {
  return request({
    url: '/questionMain/questionMain/' + id,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 验证题目是否存在
export function checkQuestionExists(questionId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: '/questionMain/questionMain/checkExists/' + questionId,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 获取题目简单信息
export function getQuestionSimpleInfo(questionId: number | string): Promise<ApiResult<QuestionMain>> {
  return request({
    url: '/questionMain/questionMain/simpleInfo/' + questionId,
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionMain>>
}

// 搜索题目（用于选择器）
export function searchQuestions(params: any): Promise<ApiResult<QuestionMain[]>> {
  return request({
    url: '/questionMain/questionMain/search',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResult<QuestionMain[]>>
}

// 验证用户是否存在
export function checkUserExists(userId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: '/questionMain/questionMain/checkUserExists/' + userId,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 验证题目和用户是否存在
export function checkQuestionAndUser(questionId: number | string, userId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: `/questionMain/questionMain/checkQuestionAndUser/${questionId}/${userId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 记录刷题学习时间（覆盖所有练习模式）
export function recordStudyTime(data: { bankId: number; questionIds: number[] }): Promise<ApiResult> {
  return request({
    url: '/questionMain/questionMain/recordStudyTime',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// ========== 服务端练习会话 / 判分 ==========

export interface PracticeSessionStartPayload {
  bankId: number | string
  moduleType?: string
  questionIds?: Array<number | string>
  count?: number | null
  scores?: Record<string, number>
}

export function startPracticeSession(data: PracticeSessionStartPayload): Promise<ApiResult<any>> {
  return request({
    url: '/questionPractice/session/start',
    method: 'post',
    data
  }) as unknown as Promise<ApiResult<any>>
}

export function answerPracticeSession(
  sessionId: string,
  questionId: number | string,
  answer: any
): Promise<ApiResult<any>> {
  return request({
    url: `/questionPractice/session/${sessionId}/answer`,
    method: 'post',
    data: { questionId, answer }
  }) as unknown as Promise<ApiResult<any>>
}

export function submitPracticeSession(
  sessionId: string,
  durationSec?: number,
  answers?: Record<string, any>
): Promise<ApiResult<any>> {
  return request({
    url: `/questionPractice/session/${sessionId}/submit`,
    method: 'post',
    data: { durationSec: durationSec ?? null, answers: answers ?? null }
  }) as unknown as Promise<ApiResult<any>>
}

export function getPracticeSession(sessionId: string): Promise<ApiResult<any>> {
  return request({
    url: `/questionPractice/session/${sessionId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<any>>
}

export function listPracticeSessions(limit = 20): Promise<ApiResult<any>> {
  return request({
    url: '/questionPractice/sessions',
    method: 'get',
    params: { limit }
  }) as unknown as Promise<ApiResult<any>>
}

/**
 * 答题上报（答对 / 答错都要调用）
 *
 * 后端写一条答题流水 user_practice_log，并顺带同步：
 * - 已收藏题目的 correct_times / error_times
 * - 答错时 upsert 错题记录（已掌握的题目会重新回到错题本）
 *
 * 学习统计里的正确率、练习次数、学习趋势、连续学习天数全部基于这条流水。
 */
export function reportPractice(data: {
  questionId: number | string
  bankId?: number | string | null
  isCorrect: boolean
  answer?: string | null
  notes?: string | null
  tags?: string | null
  difficultyRating?: number | null
}): Promise<ApiResult> {
  return request({
    url: '/questionPractice/report',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}
