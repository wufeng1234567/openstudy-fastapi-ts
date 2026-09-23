import request from '@/utils/request'

// 查询单词列表
export function listWords(query: any) {
  return request({
    url: '/words/words/list',
    method: 'get',
    params: query
  })
}

// 查询单词详细
export function getWords(id: number | string) {
  return request({
    url: '/words/words/' + id,
    method: 'get'
  })
}

// 新增单词
export function addWords(data: any) {
  return request({
    url: '/words/words',
    method: 'post',
    data: data
  })
}

// 批量新增单词
export function batchAddWords(data: any) {
  return request({
    url: '/words/words/batch',
    method: 'post',
    data: data
  })
}

// 修改单词
export function updateWords(data: any) {
  return request({
    url: '/words/words',
    method: 'put',
    data: data
  })
}

// 删除单词
export function delWords(id: number | string) {
  return request({
    url: '/words/words/' + id,
    method: 'delete'
  })
}
