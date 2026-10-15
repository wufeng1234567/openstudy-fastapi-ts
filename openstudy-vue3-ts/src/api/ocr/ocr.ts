import request from '@/utils/request'

export function ocrRecognize(data: any) {
  return request({
    url: '/ocr/recognize',
    method: 'post',
    data: data,
    timeout: 600000
  })
}
