import request from '@/utils/request'
import type { ApiResult } from '@/types'

/** 我的定向站内通知列表 */
export function listMyNotifications(params?: { onlyUnread?: boolean; pageNum?: number; pageSize?: number }): Promise<ApiResult<{ total: number; rows: any[] }>> {
  return request({
    url: '/notification/notification/myList',
    method: 'get',
    params
  }) as unknown as Promise<ApiResult<{ total: number; rows: any[] }>>
}

/** 未读通知数 */
export function getNotificationUnreadCount(): Promise<ApiResult<number>> {
  return request({
    url: '/notification/notification/unreadCount',
    method: 'get'
  }) as unknown as Promise<ApiResult<number>>
}

/** 标记单条已读 */
export function markNotificationRead(id: number | string): Promise<ApiResult> {
  return request({
    url: '/notification/notification/markRead/' + id,
    method: 'post'
  }) as unknown as Promise<ApiResult>
}

/** 全部已读 */
export function markAllNotificationsRead(): Promise<ApiResult> {
  return request({
    url: '/notification/notification/markReadAll',
    method: 'post'
  }) as unknown as Promise<ApiResult>
}

/** 删除单条通知 */
export function deleteNotification(id: number | string): Promise<ApiResult> {
  return request({
    url: '/notification/notification/' + id,
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}

/** 清空通知 */
export function clearNotifications(): Promise<ApiResult> {
  return request({
    url: '/notification/notification/clear/all',
    method: 'delete'
  }) as unknown as Promise<ApiResult>
}
