import request from '@/utils/request'

export function list(query: any) {
  return request({
    url: '/monitor/logininfor/list',
    method: 'get',
    params: query
  })
}

export function delLogininfor(infoId: number | string) {
  return request({
    url: '/monitor/logininfor/' + infoId,
    method: 'delete'
  })
}

export function unlockLogininfor(userName: string) {
  return request({
    url: '/monitor/logininfor/unlock/' + userName,
    method: 'get'
  })
}

export function cleanLogininfor() {
  return request({
    url: '/monitor/logininfor/clean',
    method: 'delete'
  })
}
