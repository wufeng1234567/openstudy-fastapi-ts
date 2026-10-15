import request from '@/utils/request'

// 查询单词本列表（后台管理用）
export function listWordBooks(query: any) {
  return request({
    url: '/wordBooks/wordBooks/list',
    method: 'get',
    params: query
  })
}

// 前台查询用户可见的单词本列表
export function listFrontWordBooks(query: any) {
  return request({
    url: '/wordBooks/wordBooks/front/list',
    method: 'get',
    params: query
  })
}

// 查询单词本详细
export function getWordBooks(id: number | string) {
  return request({
    url: '/wordBooks/wordBooks/' + id,
    method: 'get'
  })
}

// 新增单词本
export function addWordBooks(data: any) {
  return request({
    url: '/wordBooks/wordBooks',
    method: 'post',
    data: data
  })
}

// 修改单词本
export function updateWordBooks(data: any) {
  return request({
    url: '/wordBooks/wordBooks',
    method: 'put',
    data: data
  })
}

// 删除单词本
export function delWordBooks(id: number | string) {
  return request({
    url: '/wordBooks/wordBooks/' + id,
    method: 'delete'
  })
}
