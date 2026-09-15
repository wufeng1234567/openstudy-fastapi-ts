import request from '@/utils/request'

// 查询用户笔记主，每篇笔记必须归属于一个用户自定义的分类列表
export function listNote(query: any) {
  return request({
    url: '/notes/note/list',
    method: 'get',
    params: query
  })
}

// 查询用户笔记主，每篇笔记必须归属于一个用户自定义的分类详细
export function getNote(id: number | string) {
  return request({
    url: '/notes/note/' + id,
    method: 'get'
  })
}

// 新增用户笔记主，每篇笔记必须归属于一个用户自定义的分类
export function addNote(data: any) {
  return request({
    url: '/notes/note',
    method: 'post',
    data: data
  })
}

// 修改用户笔记主，每篇笔记必须归属于一个用户自定义的分类
export function updateNote(data: any) {
  return request({
    url: '/notes/note',
    method: 'put',
    data: data
  })
}

// 删除用户笔记主，每篇笔记必须归属于一个用户自定义的分类
export function delNote(id: number | string) {
  return request({
    url: '/notes/note/' + id,
    method: 'delete'
  })
}

// 批量删除笔记
export function batchDelNote(ids: (number | string)[]) {
  return request({
    url: '/notes/note/' + ids.join(','),
    method: 'delete'
  })
}
