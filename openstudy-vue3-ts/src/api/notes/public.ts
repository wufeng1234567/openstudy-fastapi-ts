import request from '@/utils/request'

export function listPublicNotes(query: any) {
  return request({
    url: '/notes/note/public/list',
    method: 'get',
    params: query
  })
}

// 公开笔记的热门标签（学习分享页筛选用）
export function getPublicNoteTags(limit = 20) {
  return request({
    url: '/notes/note/public/tags',
    method: 'get',
    params: { limit }
  })
}

export function getPublicNote(id: number | string) {
  return request({
    url: `/notes/note/public/${id}`,
    method: 'get'
  })
}

export function recordClick(noteId: number | string) {
  return request({
    url: `/notes/note/public/click/${noteId}`,
    method: 'post',
    headers: {
      repeatSubmit: false
    }
  })
}

export function getRanking(type: string | number) {
  return request({
    url: '/notes/note/public/ranking',
    method: 'get',
    params: { type, limit: 10 }
  })
}
