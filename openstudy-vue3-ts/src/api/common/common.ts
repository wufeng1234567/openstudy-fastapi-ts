import request from '@/utils/request'

export function uploadImage(data: FormData) {
  return request({
    url: '/common/upload',
    method: 'post',
    data,
    headers: {
      'Content-Type': undefined
    }
  }).then((res: any) => ({
    ...res,
    // 后端 common/upload 返回 fileName，老组件读取 url；这里同时兼容两种字段。
    url: res?.url || res?.fileName || res?.data?.url || res?.data?.fileName || ''
  }))
}
