import request from '@/utils/request'

/**
 * 单词 API
 *
 * ⚠️ 后端 `app/api/v1/words.py` 全部使用 **Query 参数**（不是 JSON body），
 *    而且字段名是 `bookId` / `word` / `translation`（不是 `wordBookId` / `english` / `chinese`）。
 *    这里统一按后端口径转发，页面只管传业务字段。
 */

/** 查询单词列表：`bookId` 是后端认的参数名（不是 wordBookId） */
export function listWords(query: any) {
  return request({
    url: '/words/words/list',
    method: 'get',
    params: query
  })
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
