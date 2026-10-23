import request from '@/utils/request'

/**
 * 词书 API
 *
 * ⚠️ 2026-10-23 修：这里原本有 `listFrontWordBooks` 指向
 *    `/wordBooks/wordBooks/front/list` —— **后端根本没有这个路由**。
 *    请求会落到 `catch_all` 兜底，返回一个假的 `200 + 空 rows`，
 *    前端于是永远显示「还没有词库」，看起来像"功能没做"，
 *    实际是"请求打到了一个不存在的地方"。
 *
 *    另外后端全部用 **Query 参数**（不是 JSON body），字段名是
 *    `bookId` / `bookName` / `bookDescription`。这里统一按后端口径转发。
 */

/** 我的词书 + 系统预置词书（分页） */
export function listWordBooks(query: any = {}) {
  return request({
    url: '/wordBooks/wordBooks/list',
    method: 'get',
    params: query
  })
}

/**
 * 我的词书 + 系统预置（不分页，下拉框用）
 *
 * @deprecated 旧名保留：原实现打的是不存在的 `/front/list`。
 *             现在直接复用 `/all`，调用方无需改 import。
 */
export function listFrontWordBooks(query: any = {}) {
  return request({
    url: '/wordBooks/wordBooks/all',
    method: 'get',
    params: query
  })
}

/** 查询词书详情 */
export function getWordBooks(id: number | string) {
  return request({
    url: '/wordBooks/wordBooks/' + id,
    method: 'get'
  })
}

/** 新建词书（后端是 Query 参数；归属自动取当前登录用户） */
export function addWordBooks(data: any) {
  return request({
    url: '/wordBooks/wordBooks',
    method: 'post',
    params: {
      bookName: data.bookName ?? data.name,
      bookDescription: data.bookDescription ?? data.description ?? undefined,
      coverImage: data.coverImage || undefined
    }
  })
}

/** 修改词书 */
export function updateWordBooks(data: any) {
  return request({
    url: '/wordBooks/wordBooks',
    method: 'put',
    params: {
      bookId: data.bookId,
      bookName: data.bookName,
      bookDescription: data.bookDescription ?? undefined,
      coverImage: data.coverImage || undefined,
      status: data.status
    }
  })
}

/** 删除词书 */
export function delWordBooks(id: number | string) {
  return request({
    url: '/wordBooks/wordBooks/' + id,
    method: 'delete'
  })
}
