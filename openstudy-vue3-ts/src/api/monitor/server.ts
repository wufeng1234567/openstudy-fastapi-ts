import request from '@/utils/request'

export function getServer() {
  return request({
    url: '/monitor/server',
    method: 'get'
  })
}
