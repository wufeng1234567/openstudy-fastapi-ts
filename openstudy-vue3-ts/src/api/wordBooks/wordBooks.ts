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
 *
 * ⚠️ 2026-10-23 再修「系统接口 422 异常」：
 *    后端 `GET /wordBooks/wordBooks/list` 的签名是
 *        `pageSize: int = Query(10, ge=1, le=100)`
 *    —— `le=100` 是**硬上限**。前端「我的词库」页写了 `pageSize: 200`
 *    （想一次拿全部词书），被 FastAPI 直接拒成
 *        HTTP 422 `Input should be less than or equal to 100`
 *    这正是「读取词库失败：Request failed with status code 422」的来源。
 *
 *    现在 `clampPageSize()` 统一兜底；需要全量时用 `listAllWordBooks()` 翻页取完。
 */

/** 与后端 `Query(10, ge=1, le=100)` 对齐 */
const MAX_PAGE_SIZE = 100
/** 防御性上限：即使后端 total 异常也不至于无限翻页 */
const ALL_PAGES_HARD_LIMIT = 2000

/** 把 pageSize 收进 [1, max]，避免把超限值发给后端触发 422 */
function clampPageSize(size: any, max: number = MAX_PAGE_SIZE): number {
  const n = Number(size)
  if (!Number.isFinite(n) || n < 1) return max
  return Math.min(Math.floor(n), max)
}

/** 我的词书 + 系统预置词书（分页） */
export function listWordBooks(query: any = {}) {
  return request({
    url: '/wordBooks/wordBooks/list',
    method: 'get',
    params: {
      ...query,
      pageSize: clampPageSize(query.pageSize)
    }
  })
}

/** 我的词书 + 系统预置（不分页，下拉框用） */
export function listAllWordBooks(query: any = {}) {
  return request({
    url: '/wordBooks/wordBooks/all',
    method: 'get',
    params: query
  })
}

/**
 * 取「我的 + 预置」全部词书（内部翻页）
 *
 * 返回结构与 `listWordBooks` 一致（`code / total / rows`）。
 * 给「需要全部词书、不能截断」的页面用 —— 直接传 `pageSize: 200/1000`
 * 会被后端 422 拒掉。
 *
 * @deprecated 旧名保留：原实现打的是不存在的 `/front/list`。
 *             现在改为真正翻页取全量，调用方无需改 import。
 */
export async function listFrontWordBooks(query: any = {}) {
  const pageSize = MAX_PAGE_SIZE
  const first: any = await listWordBooks({ ...query, pageNum: 1, pageSize })
  if (!first || first.code !== 200) return first

  const rows: any[] = [...(first.rows || [])]
  const total = Number(first.total || 0)

  let pageNum = 2
  while (rows.length < total && rows.length < ALL_PAGES_HARD_LIMIT) {
    const next: any = await listWordBooks({ ...query, pageNum, pageSize })
    if (!next || next.code !== 200) break
    const batch = next.rows || []
    if (!batch.length) break
    rows.push(...batch)
    pageNum++
  }

  return { ...first, total: rows.length, rows }
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
