import request from '@/utils/request'

export function uploadImage(data: FormData) {
  return request({
    url: '/system/common/upload',
    method: 'post',
    data,
    headers: {
      'Content-Type': undefined
    }
  })
}
