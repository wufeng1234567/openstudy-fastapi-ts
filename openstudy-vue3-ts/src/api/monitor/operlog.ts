import request from '@/utils/request'

export function list(query: any) {
  return request({
    url: '/monitor/operlog/list',
    method: 'get',
    params: query
  })
}

export function delOperlog(operId: number | string) {
  return request({
    url: '/monitor/operlog/' + operId,
    method: 'delete'
  })
}

export function cleanOperlog() {
  return request({
    url: '/monitor/operlog/clean',
    method: 'delete'
  })
}
