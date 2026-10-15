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

// —— 用户「笔记草稿」（写笔记页的临时草稿，用户维度、无 noteId、不进笔记列表）——
// 与 note 表里 status='draft' 的正式笔记不同：智能体 note_manage.save_draft 也写这里。

// 取当前用户的后端草稿（没有则 data=null）
export function getNoteDraft() {
  return request({
    url: '/notes/note/draft',
    method: 'get'
  })
}

// 保存/更新当前用户的后端草稿
export function saveNoteDraft(data: any) {
  return request({
    url: '/notes/note/draft',
    method: 'put',
    data: data
  })
}

// 清除当前用户的后端草稿（发布成功 / 丢弃草稿时）
export function clearNoteDraft() {
  return request({
    url: '/notes/note/draft',
    method: 'delete'
  })
}
