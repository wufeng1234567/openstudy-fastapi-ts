import request from '@/utils/request'

// 查询公告列表
export function listNotice(query: any) {
  return request({
    url: '/system/notice/list',
    method: 'get',
    params: query
  })
}

// 查询公告详细
export function getNotice(noticeId: number | string) {
  return request({
    url: '/system/notice/' + noticeId,
    method: 'get'
  })
}

// 新增公告
export function addNotice(data: any) {
  return request({
    url: '/system/notice',
    method: 'post',
    data: data
  })
}

// 修改公告
export function updateNotice(data: any) {
  return request({
    url: '/system/notice',
    method: 'put',
    data: data
  })
}

// 删除公告
export function delNotice(noticeId: number | string) {
  return request({
    url: '/system/notice/' + noticeId,
    method: 'delete'
  })
}

// 获取顶部公告列表（带已读标记和未读总数，最多5条）
export function listTopNotice() {
  return request({ url: '/system/notice/listTop', method: 'get' })
}

// 获取公告列表（带已读标记）；传 pageNum/pageSize 时分页，不传保持旧全量行为
export function listAllNotice(query?: { pageNum?: number; pageSize?: number; scope?: 'system' | 'user' }) {
  return request({ url: '/system/notice/listAll', method: 'get', params: query })
}

// 标记单条已读
export function markRead(noticeId: number | string) {
  return request({
    url: '/system/notice/markRead',
    method: 'post',
    params: { noticeId },
    headers: { repeatSubmit: false }
  })
}

// 全部标记已读
export function markReadAll(ids: (number | string)[]) {
  return request({
    url: '/system/notice/markReadAll',
    method: 'post',
    params: { ids },
    headers: { repeatSubmit: false }
  })
}

// 获取未读总数
export function unreadCount() {
  return request({ url: '/system/notice/unreadCount', method: 'get' })
}

// 顶栏红点：系统/用户通知 + 定向分享通知的聚合未读数
export function totalUnread() {
  return request({ url: '/system/notice/totalUnread', method: 'get' })
}

// 消息中心左侧红点：system / user / share 一次返回，替代拉全量列表自己数
export function unreadSummary() {
  return request({ url: '/system/notice/unreadSummary', method: 'get' })
}

// 前台删除单条通知
export function deleteFrontNotice(noticeId: number | string) {
  return request({ url: '/system/notice/front/' + noticeId, method: 'delete' })
}

// 前台批量删除通知
export function deleteFrontNoticeBatch(noticeIds: (number | string)[]) {
  return request({ url: '/system/notice/front/batch/' + noticeIds.join(','), method: 'delete' })
}
