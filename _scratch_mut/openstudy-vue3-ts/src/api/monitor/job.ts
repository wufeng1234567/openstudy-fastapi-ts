import request from '@/utils/request'

export function listJob(query: any) {
  return request({
    url: '/monitor/job/list',
    method: 'get',
    params: query
  })
}

export function getJob(jobId: number | string) {
  return request({
    url: '/monitor/job/' + jobId,
    method: 'get'
  })
}

export function addJob(data: any) {
  return request({
    url: '/monitor/job',
    method: 'post',
    data: data
  })
}

export function updateJob(data: any) {
  return request({
    url: '/monitor/job',
    method: 'put',
    data: data
  })
}

export function delJob(jobId: number | string) {
  return request({
    url: '/monitor/job/' + jobId,
    method: 'delete'
  })
}

export function changeJobStatus(jobId: number | string, status: string) {
  const data = {
    jobId,
    status
  }
  return request({
    url: '/monitor/job/changeStatus',
    method: 'put',
    data: data
  })
}

export function runJob(jobId: number | string, jobGroup: string) {
  const data = {
    jobId,
    jobGroup
  }
  return request({
    url: '/monitor/job/run',
    method: 'put',
    data: data
  })
}
