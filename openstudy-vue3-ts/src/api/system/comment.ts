import request from '@/utils/request'

export function listComment(query: any) {
  return request({
    url: '/system/comment/list',
    method: 'get',
    params: query
  })
}

export function getComment(commentId: number | string) {
  return request({
    url: '/system/comment/' + commentId,
    method: 'get'
  })
}

export function updateComment(data: any) {
  return request({
    url: '/system/comment',
    method: 'put',
    data: data
  })
}

export function delComment(commentId: number | string) {
  return request({
    url: '/system/comment/' + commentId,
    method: 'delete'
  })
}
