import request from '@/utils/request'

export function listComments(noteId: number, pageNum: number, pageSize: number) {
  return request({
    url: '/notes/comment/list',
    method: 'get',
    params: { noteId, pageNum, pageSize }
  })
}

export function listReplies(commentId: number, pageNum: number, pageSize: number) {
  return request({
    url: '/notes/comment/replies',
    method: 'get',
    params: { parentId: commentId, pageNum, pageSize }
  })
}

export function getCommentThread(commentId: number) {
  return request({
    url: `/notes/comment/thread/${commentId}`,
    method: 'get'
  })
}

export function createComment(data: any) {
  return request({
    url: '/notes/comment/create',
    method: 'post',
    params: {
      noteId: data.noteId,
      content: data.content,
      parentId: data.parentId,
      replyToUserId: data.replyToUserId,
      replyToUserName: data.replyToUserName
    }
  })
}

export function deleteComment(id: number | string) {
  return request({
    url: `/notes/comment/delete/${id}`,
    method: 'delete'
  })
}
