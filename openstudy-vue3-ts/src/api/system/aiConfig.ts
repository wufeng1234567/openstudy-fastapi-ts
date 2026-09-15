import request from '@/utils/request'

export function listAiConfig() {
  return request({
    url: '/system/ai/config/list',
    method: 'get'
  })
}

export function getAiConfig(configId: number | string) {
  return request({
    url: `/system/ai/config/${configId}`,
    method: 'get'
  })
}

export function getEffectiveConfig() {
  return request({
    url: '/system/ai/config/effective',
    method: 'get'
  })
}

export function getCurrentModel() {
  return request({
    url: '/system/ai/config/current',
    method: 'get'
  })
}

export function addAiConfig(data: any) {
  return request({
    url: '/system/ai/config',
    method: 'post',
    data
  })
}

export function updateAiConfig(data: any) {
  return request({
    url: '/system/ai/config',
    method: 'put',
    data
  })
}

export function deleteAiConfig(configIds: number | string) {
  return request({
    url: `/system/ai/config/${configIds}`,
    method: 'delete'
  })
}

export function setDefaultConfig(configId: number | string) {
  return request({
    url: `/system/ai/config/default/${configId}`,
    method: 'put'
  })
}

export function testAiConnection(data: any) {
  return request({
    url: '/system/ai/config/test',
    method: 'post',
    data
  })
}
