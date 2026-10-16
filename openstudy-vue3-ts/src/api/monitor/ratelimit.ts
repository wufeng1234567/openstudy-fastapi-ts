import request from '@/utils/request'

export function getRateLimitConfig() {
  return request({
    url: '/monitor/ratelimit/config',
    method: 'get'
  })
}

export function updateRateLimitConfig(data: any) {
  return request({
    url: '/monitor/ratelimit/config',
    method: 'put',
    data: data
  })
}

export function listViolations(query: any) {
  return request({
    url: '/monitor/ratelimit/violations',
    method: 'get',
    params: query
  })
}

export function listCounters(query: any) {
  return request({
    url: '/monitor/ratelimit/counters',
    method: 'get',
    params: query
  })
}

export function clearCounters(data: any) {
  return request({
    url: '/monitor/ratelimit/counters',
    method: 'delete',
    data: data
  })
}

export function banUser(data: any) {
  return request({
    url: '/monitor/ratelimit/ban',
    method: 'post',
    data: data
  })
}

export function unbanUser(data: any) {
  return request({
    url: '/monitor/ratelimit/unban',
    method: 'post',
    data: data
  })
}
