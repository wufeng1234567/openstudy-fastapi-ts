import request from '@/utils/request'

/**
 * 单词 API
 *
 * ⚠️ 后端 `app/api/v1/words.py` 全部使用 **Query 参数**（不是 JSON body），
 *    而且字段名是 `bookId` / `word` / `translation`（不是 `wordBookId` / `english` / `chinese`）。
 *    这里统一按后端口径转发，页面只管传业务字段。
 *
 * ⚠️ 2026-10-23 修「系统接口 422 异常」：
 *    后端 `GET /words/words/list` 的签名是
 *        `pageSize: int = Query(50, ge=1, le=200)`
 *    —— `le=200` 是**硬上限**，传 1000 会被 FastAPI 直接拒成
 *        HTTP 422 `Input should be less than or equal to 200`
 *    （注意是 HTTP 422，不是仓库惯用的 `{code:500}` 信封，
 *      所以响应拦截器里 `code = res.data.code || 200` 都进不去，
 *      直接落到 `error` 分支被拼成「系统接口422异常」）。
 *
 *    页面要的是「这本词书的**全部**单词」，于是写了 `pageSize: 1000` —— 想法没错，
 *    但表达方式错了：应该**分页取完**，而不是一次要 1000 条。
 *    现在两件事一起做：
 *      ① `clampPageSize()` 兜底，任何调用方误传超限值都不会再 422；
 *      ② `listAllWords()` 内部翻页取全量，给「确实需要全部」的场景用。
 */

/** 与后端 `Query(50, ge=1, le=200)` 对齐 */
export const WORDS_MAX_PAGE_SIZE = 200
/** 词书不设上限的那一支：与后端 `Query(10, ge=1, le=100)` 对齐 */
export const WORD_BOOKS_MAX_PAGE_SIZE = 100
/** 防御性上限：即使后端 total 异常也不至于无限翻页 */
const ALL_PAGES_HARD_LIMIT = 5000

/** 把 pageSize 收进 [1, max]，避免把超限值发给后端触发 422 */
export function clampPageSize(size: any, max: number): number {
  const n = Number(size)
  if (!Number.isFinite(n) || n < 1) return max
  return Math.min(Math.floor(n), max)
}

/** 查询单词列表：`bookId` 是后端认的参数名（不是 wordBookId） */
export function listWords(query: any = {}) {
  return request({
    url: '/words/words/list',
    method: 'get',
    params: {
      ...query,
      pageSize: clampPageSize(query.pageSize, WORDS_MAX_PAGE_SIZE)
    }
  })
}

/**
 * 取「某本词书 / 某个筛选条件下的**全部**单词」
 *
 * 内部按 `WORDS_MAX_PAGE_SIZE` 翻页，直到取满 `total` 条。
 * 用于「详情页要看全部单词」「听写要练全部单词」这类真的不能截断的场景 ——
 * 直接传 `pageSize: 1000` 那种写法会被后端 422 拒掉。
 *
 * 返回结构与 `listWords` 一致（`code / total / rows`），`rows` 是合并后的全量。
 */
export async function listAllWords(query: any = {}) {
  const pageSize = WORDS_MAX_PAGE_SIZE
  const first: any = await listWords({ ...query, pageNum: 1, pageSize })
  if (!first || first.code !== 200) return first

  const rows: any[] = [...(first.rows || [])]
  const total = Number(first.total || 0)

  let pageNum = 2
  // `rows.length < total` 是正常终止条件；
  // `batch.length === 0` 用于后端 total 与实际不符时提前退出，避免死循环。
  while (rows.length < total && rows.length < ALL_PAGES_HARD_LIMIT) {
    const next: any = await listWords({ ...query, pageNum, pageSize })
    if (!next || next.code !== 200) break
    const batch = next.rows || []
    if (!batch.length) break
    rows.push(...batch)
    pageNum++
  }

  return { ...first, total: rows.length, rows }
}

/** 查询单词详细 */
export function getWords(id: number | string) {
  return request({
    url: '/words/words/' + id,
    method: 'get'
  })
}

/** 新增单词（后端是 Query 参数） */
export function addWords(data: any) {
  return request({
    url: '/words/words',
    method: 'post',
    params: {
      bookId: data.bookId,
      word: data.word,
      phonetic: data.phonetic || undefined,
      translation: data.translation || undefined,
      example: data.example || undefined,
      audioUrl: data.audioUrl || undefined,
      sortOrder: data.sortOrder ?? 0
    }
  })
}

/** 批量新增单词（后端同样要求 Query，且 `words` 是 JSON 字符串） */
export function batchAddWords(bookId: number | string, words: any[]) {
  return request({
    url: '/words/words/batch',
    method: 'post',
    params: { bookId, words: JSON.stringify(words) }
  })
}

/** 修改单词（后端是 Query 参数） */
export function updateWords(data: any) {
  return request({
    url: '/words/words',
    method: 'put',
    params: {
      wordId: data.wordId,
      word: data.word,
      phonetic: data.phonetic || undefined,
      translation: data.translation || undefined,
      example: data.example || undefined,
      audioUrl: data.audioUrl || undefined,
      sortOrder: data.sortOrder
    }
  })
}

/** 删除单词 */
export function delWords(id: number | string) {
  return request({
    url: '/words/words/' + id,
    method: 'delete'
  })
}

/* ============================================================================
 * 英语练习记录（2026-10-26）
 *
 * 为什么要有这层：听写 / 阅读原本练完即弃 —— 关掉页面就不知道上次练了什么、
 * 错了哪些词。这三个接口把结果留下来，页面才能接上"下次"，
 * 智能体的 `english_practice` 工具也才有数据可分析。
 * ========================================================================== */

/** 一次练习的提交体 */
export interface PracticeSubmitPayload {
  /** dictation=单词听写 / reading=阅读练习 / ocr=拍照识词 */
  mode: 'dictation' | 'reading' | 'ocr'
  bookId?: number | string
  title?: string
  total: number
  correct: number
  /** 用时（秒），不传按 0 算 */
  duration?: number
  /** 逐题明细 */
  detail?: Array<{ word?: string; input?: string; ok: boolean }>
}

/** 提交练习结果（⚠️ accuracy 由后端算，前端不要自己再算一遍） */
export function submitPractice(data: PracticeSubmitPayload) {
  return request({
    url: '/words/practice/submit',
    method: 'post',
    data
  })
}

/** 取最近一次练习（页面「继续上次」入口） */
export function getLastPractice(mode?: 'dictation' | 'reading' | 'ocr') {
  return request({
    url: '/words/practice/last',
    method: 'get',
    params: mode ? { mode } : {}
  })
}

/** 练习汇总（各模式正确率 / 7 天趋势 / 最常错词） */
export function getPracticeStats() {
  return request({
    url: '/words/practice/stats',
    method: 'get'
  })
}
