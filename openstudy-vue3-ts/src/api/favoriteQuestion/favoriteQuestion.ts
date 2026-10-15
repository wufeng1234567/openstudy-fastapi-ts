import request from '@/utils/request'
import type { UserQuestionFavorite, PageResult, ApiResult } from '@/types'

// 查询用户题目收藏列表
export function listFavoriteQuestion(query: any): Promise<PageResult<UserQuestionFavorite>> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<UserQuestionFavorite>>
}

// 验证题目是否存在
export function checkQuestionExists(questionId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/check/' + questionId,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 查询用户题目收藏详细
export function getFavoriteQuestion(favoriteId: number | string): Promise<ApiResult<UserQuestionFavorite>> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/' + favoriteId,
    method: 'get'
  }) as unknown as Promise<ApiResult<UserQuestionFavorite>>
}

// 新增用户题目收藏
export function addFavoriteQuestion(data: Partial<UserQuestionFavorite>): Promise<ApiResult> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 修改用户题目收藏
export function updateFavoriteQuestion(data: Partial<UserQuestionFavorite>): Promise<ApiResult> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除用户题目收藏
export function delFavoriteQuestion(favoriteId: number | string): Promise<ApiResult> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/' + favoriteId,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 检查用户是否已收藏题目
export function checkQuestionFavoriteExists(userId: number | string, questionId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: `/favoriteQuestion/favoriteQuestion/checkFavorite/${userId}/${questionId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 根据用户ID和题目ID删除收藏
export function deleteFavoriteQuestionByUserAndQuestion(userId: number | string, questionId: number | string): Promise<ApiResult> {
  return request({
    url: `/favoriteQuestion/favoriteQuestion/deleteByUserAndQuestion/${userId}/${questionId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 查询用户题目收藏列表（不分页）
export function listFavoriteQuestionAll(query: any): Promise<ApiResult<UserQuestionFavorite[]>> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<UserQuestionFavorite[]>>
}

// 为了兼容之前的调用，添加别名方法
export const listUserQuestionFavorite = listFavoriteQuestionAll

// 批量检查用户是否已收藏题目
export function batchCheckFavorite(questionIds: number[]): Promise<ApiResult<Record<string, boolean>>> {
  return request({
    url: '/favoriteQuestion/favoriteQuestion/batchCheck',
    method: 'post',
    data: { questionIds }
  }) as unknown as Promise<ApiResult<Record<string, boolean>>>
}
