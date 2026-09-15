import request from '@/utils/request'

export function listFavoriteNote(query: any) {
  return request({
    url: '/favoriteNote/favoriteNote/list',
    method: 'get',
    params: query
  })
}

export function getFavoriteNote(favoriteId: number | string) {
  return request({
    url: '/favoriteNote/favoriteNote/' + favoriteId,
    method: 'get'
  })
}

export function addFavoriteNote(data: any) {
  return request({
    url: '/favoriteNote/favoriteNote',
    method: 'post',
    params: { noteId: data.noteId }
  })
}

export function updateFavoriteNote(data: any) {
  return request({
    url: '/favoriteNote/favoriteNote',
    method: 'put',
    data: data
  })
}

export function delFavoriteNote(favoriteId: number | string) {
  return request({
    url: '/favoriteNote/favoriteNote/' + favoriteId,
    method: 'delete'
  })
}

export function checkNoteFavoriteExists(userId: number | string, noteId: number | string) {
  return request({
    url: `/favoriteNote/favoriteNote/checkFavorite/${userId}/${noteId}`,
    method: 'get'
  })
}

export function deleteFavoriteNoteByUserAndNote(userId: number | string, noteId: number | string) {
  return request({
    url: `/favoriteNote/favoriteNote/deleteByUserAndNote/${userId}/${noteId}`,
    method: 'delete'
  })
}

export function getFavoriteNoteDetails() {
  return request({
    url: '/favoriteNote/favoriteNote/details',
    method: 'get'
  })
}

export function checkNoteExists(noteId: number | string) {
  return request({
    url: '/favoriteNote/favoriteNote/checkNote/' + noteId,
    method: 'get'
  })
}
