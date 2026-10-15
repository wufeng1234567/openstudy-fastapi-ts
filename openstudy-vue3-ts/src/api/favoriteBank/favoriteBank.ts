import request from '@/utils/request'
import type { UserBankFavorite, QuestionBank, PageResult, ApiResult } from '@/types'

// 查询用户题库收藏列表
export function listFavoriteBank(query: any): Promise<PageResult<UserBankFavorite>> {
  return request({
    url: '/favoriteBank/favoriteBank/list',
    method: 'get',
    params: query
  }) as unknown as Promise<PageResult<UserBankFavorite>>
}

// 查询用户题库收藏列表 不分页
export function listFavoriteBankAll(query: any): Promise<ApiResult<UserBankFavorite[]>> {
  return request({
    url: '/favoriteBank/favoriteBank/all',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult<UserBankFavorite[]>>
}

// 查询用户题库收藏详细
export function getFavoriteBank(favoriteId: number | string): Promise<ApiResult<UserBankFavorite>> {
  return request({
    url: '/favoriteBank/favoriteBank/' + favoriteId,
    method: 'get'
  }) as unknown as Promise<ApiResult<UserBankFavorite>>
}

// 验证题库是否存在
export function checkBankExists(bankId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: '/favoriteBank/favoriteBank/check/' + bankId,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 查询所有题库列表（用于下拉选择）
export function listQuestionBankAll(): Promise<ApiResult<QuestionBank[]>> {
  return request({
    url: '/questionBank/questionBank/all',
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank[]>>
}

// 根据题库ID查询题库详情
export function getBankInfo(bankId: number | string): Promise<ApiResult<QuestionBank>> {
  return request({
    url: '/questionBank/questionBank/' + bankId,
    method: 'get'
  }) as unknown as Promise<ApiResult<QuestionBank>>
}

// 新增用户题库收藏
export function addFavoriteBank(data: Partial<UserBankFavorite>): Promise<ApiResult> {
  return request({
    url: '/favoriteBank/favoriteBank',
    method: 'post',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 修改用户题库收藏
export function updateFavoriteBank(data: Partial<UserBankFavorite>): Promise<ApiResult> {
  return request({
    url: '/favoriteBank/favoriteBank',
    method: 'put',
    data: data
  }) as unknown as Promise<ApiResult>
}

// 删除用户题库收藏
export function delFavoriteBank(favoriteId: number | string): Promise<ApiResult> {
  return request({
    url: '/favoriteBank/favoriteBank/' + favoriteId,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 导出用户题库收藏
export function exportFavoriteBank(query: any): Promise<ApiResult> {
  return request({
    url: '/favoriteBank/favoriteBank/export',
    method: 'get',
    params: query
  }) as unknown as Promise<ApiResult>
}

// 检查用户是否已收藏题库
export function checkBankFavoriteExists(userId: number | string, bankId: number | string): Promise<ApiResult<boolean>> {
  return request({
    url: `/favoriteBank/favoriteBank/checkFavorite/${userId}/${bankId}`,
    method: 'get'
  }) as unknown as Promise<ApiResult<boolean>>
}

// 根据用户ID和题库ID删除收藏
export function deleteFavoriteBankByUserAndBank(userId: number | string, bankId: number | string): Promise<ApiResult> {
  return request({
    url: `/favoriteBank/favoriteBank/deleteByUserAndBank/${userId}/${bankId}`,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

// 记录题库学习时间（进入题库时调用）
export function recordBankStudy(bankId: number | string): Promise<ApiResult> {
  return request({
    url: `/favoriteBank/favoriteBank/recordStudy/${bankId}`,
    method: 'post'
  }) as unknown as Promise<ApiResult>
}
