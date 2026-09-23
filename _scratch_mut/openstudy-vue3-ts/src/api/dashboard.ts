import request from '@/utils/request'

// 获取统计数据
export function getDashboardStats() {
  return request({
    url: '/system/dashboard/stats',
    method: 'get'
  })
}

// 获取最近活动
export function getDashboardRecent() {
  return request({
    url: '/system/dashboard/recent',
    method: 'get'
  })
}
