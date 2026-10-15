import request from '@/utils/request'
import type { QuestionBank, PageResult, ApiResult } from '@/types'

// 查询题库主列表
export function listQuestionBank(query: any): Promise<PageResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<QuestionBank>>
}

// 查询题库主列表不分页
export function listQuestionBankAll(query?: any): Promise<ApiResult<QuestionBank[]>> {
  return request({
    url: '/questionBank/questionBank/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<QuestionBank[]>>
}

// 获取当前用户的题库列表
export function listMyQuestionBank(): Promise<ApiResult<QuestionBank[]>> {
  return request({
    url: '/questionBank/questionBank/my',
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank[]>>
}

// 查询题库主详细
export function getQuestionBank(id: number | string): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/' + id,
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

// 新增题库主（原接口，返回影响行数）
export function addQuestionBank(data: Partial<QuestionBank>): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 创建题库并返回完整对象（供前台使用）
export function createQuestionBankWithReturn(data: Partial<QuestionBank>): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/createWithReturn',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

// 修改题库主
export function updateQuestionBank(data: Partial<QuestionBank>): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除题库主
export function delQuestionBank(id: number | string): Promise<ApiResult> {
  return request({
    url: '/questionBank/questionBank/' + id,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 复制题库为我的新题库（深拷贝题目与子题）
export function copyQuestionBank(id: number | string, data?: { bankName?: string }): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/copy/' + id,
    method: 'post',
    data: data || {}
  }) as unknown as Promise<ApiResult<QuestionBank>>
}
