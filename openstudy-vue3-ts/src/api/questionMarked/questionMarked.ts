import request from '@/utils/request'
import type { UserQuestionMarked, PageResult, ApiResult } from '@/types'

// 查询用户斩题列表
export function listQuestionMarked(query: any): Promise<PageResult<UserQuestionMarked>> {
  return request({
    url: '/questionMarked/questionMarked/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<UserQuestionMarked>>
}

// 查询用户斩题列表 不分页
export function listQuestionMarkedAll(query: any): Promise<ApiResult<UserQuestionMarked[]>> {
  return request({
    url: '/questionMarked/questionMarked/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<UserQuestionMarked[]>>
}

// 查询用户斩题详细
export function getQuestionMarked(markedId: number | string): Promise<ApiResult<UserQuestionMarked>> {
  return request({
    url: '/questionMarked/questionMarked/' + markedId,
    method: 'get'
  }) as unknown as Promise<ApiResult<UserQuestionMarked>>
}

// 新增用户斩题
export function addQuestionMarked(data: Partial<UserQuestionMarked>): Promise<ApiResult> {
  return request({
    url: '/questionMarked/questionMarked',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 修改用户斩题
export function updateQuestionMarked(data: Partial<UserQuestionMarked>): Promise<ApiResult> {
  return request({
    url: '/questionMarked/questionMarked',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除用户斩题
export function delQuestionMarked(markedId: number | string): Promise<ApiResult> {
  return request({
    url: '/questionMarked/questionMarked/' + markedId,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 检查用户是否已斩题
export function checkMarkedExists(params: any): Promise<ApiResult<boolean>> {
  return request({
    url: '/questionMarked/questionMarked/check',
    method: 'get',
    params: params
  }) as unknown as Promise<ApiResult<boolean>>
}

// 根据用户ID和题目ID删除斩题记录
export function deleteMarkedByUserAndQuestion(userId: number | string, questionId: number | string): Promise<ApiResult> {
  return request({
    url: `/questionMarked/questionMarked/deleteByUserAndQuestion/${userId}/${questionId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 批量检查用户是否已斩题
export function batchCheckMarked(questionIds: number[]): Promise<ApiResult<Record<string, boolean>>> {
  return request({
    url: '/questionMarked/questionMarked/batchCheck',
    method: 'post',
    data: { questionIds }
  }) as unknown as Promise<ApiResult<Record<string, boolean>>>
}
