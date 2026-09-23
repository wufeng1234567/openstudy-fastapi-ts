import request from '@/utils/request'

// 查询敏感词管理列表
export function listSensitiveWord(query: any) {
  return request({
    url: '/sensitiveWord/sensitiveWord/list',
    method: 'get',
    params: query
  })
}

// 查询敏感词管理详细
export function getSensitiveWord(id: number | string) {
  return request({
    url: '/sensitiveWord/sensitiveWord/' + id,
    method: 'get'
  })
}

// 新增敏感词管理
export function addSensitiveWord(data: any) {
  return request({
    url: '/sensitiveWord/sensitiveWord',
    method: 'post',
    data: data
  })
}

// 修改敏感词管理
export function updateSensitiveWord(data: any) {
  return request({
    url: '/sensitiveWord/sensitiveWord',
    method: 'put',
    data: data
  })
}

// 删除敏感词管理
export function delSensitiveWord(id: number | string) {
  return request({
    url: '/sensitiveWord/sensitiveWord/' + id,
    method: 'delete'
  })
}

// AI生成敏感词
export function aiGenerateWords(data: any) {
  return request({
    url: '/sensitiveWord/sensitiveWord/aiGenerate',
    method: 'post',
    data: data
  })
}
