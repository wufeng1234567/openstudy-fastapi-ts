import request from '@/utils/request'

export function getPublicSections() {
  return request({
    url: '/notes/note/publicSection/list',
    method: 'get'
  })
}
