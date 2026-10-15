import request from '@/utils/request'

export function listJobLog(query: any) {
  return request({
    url: '/monitor/jobLog/list',
    method: 'get',
    params: query
  })
}

export function delJobLog(jobLogId: number | string) {
  return request({
    url: '/monitor/jobLog/' + jobLogId,
    method: 'delete'
  })
}

export function cleanJobLog() {
  return request({
    url: '/monitor/jobLog/clean',
    method: 'delete'
  })
}
