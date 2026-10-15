import request from '@/utils/request'

export function convertDocument(formData: FormData) {
  return request({
    url: '/document/convert',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    responseType: 'blob'
  })
}

export function getSupportedFormats() {
  return request({
    url: '/document/formats',
    method: 'get'
  })
}

export function checkConversionSupport(sourceFormat: string, targetFormat: string) {
  return request({
    url: '/document/check',
    method: 'get',
    params: { sourceFormat, targetFormat }
  })
}
