import request from '@/utils/request'
import type { UserQuestionError, PageResult, ApiResult } from '@/types'

// 查询用户错题记录列表
export function listQuestionError(query: any): Promise<PageResult<UserQuestionError>> {
  return request({
    url: '/questionError/questionError/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<UserQuestionError>>
}

// 查询用户错题记录列表 不分页
export function listQuestionErrorAll(query: any): Promise<ApiResult<UserQuestionError[]>> {
  return request({
    url: '/questionError/questionError/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<UserQuestionError[]>>
}

// 查询用户错题记录详细
export function getQuestionError(errorId: number | string): Promise<ApiResult<UserQuestionError>> {
  return request({
    url: '/questionError/questionError/' + errorId,
    method: 'get'
  }) as unknown as Promise<ApiResult<UserQuestionError>>
}

// 新增用户错题记录
export function addQuestionError(data: Partial<UserQuestionError>): Promise<ApiResult> {
  return request({
    url: '/questionError/questionError',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 修改用户错题记录
export function updateQuestionError(data: Partial<UserQuestionError>): Promise<ApiResult> {
  return request({
    url: '/questionError/questionError',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除用户错题记录
export function delQuestionError(errorId: number | string): Promise<ApiResult> {
  return request({
    url: '/questionError/questionError/' + errorId,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 检查当前用户对某题的错题记录是否存在
export function checkUserErrorExists(questionId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: `/questionError/questionError/checkUserErrorExists/${questionId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 记录错题（智能方法）
// 参数使用 any：该接口接收动态错题载荷（含 number|string 混合 ID、reviewCount 等字段），
// 与 UserQuestionError 实体类型不完全一致，故放宽以避免调用端类型冲突。
export function recordOrUpdateError(data: any): Promise<ApiResult<boolean>> {
  return request({
    url: '/questionError/questionError/recordOrUpdateError',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult<boolean>>
}

// 批量检查用户错题记录是否存在
export function batchCheckError(questionIds: number[]): Promise<ApiResult<Record<string, boolean>>> {
  return request({
    url: '/questionError/questionError/batchCheck',
    method: 'post',
    data: { questionIds }
  }) as unknown as Promise<ApiResult<Record<string, boolean>>>
}

// 标记错题为已掌握
export function markErrorMastered(questionId: number): Promise<ApiResult> {
  return request({
    url: '/questionError/questionError/markMastered',
    method: 'post',
    data: { questionId }
  }) as unknown as Promise<ApiResult>
}
