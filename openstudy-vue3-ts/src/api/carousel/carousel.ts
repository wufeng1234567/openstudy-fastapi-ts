import request from '@/utils/request'

// 查询轮播图管理列表
export function listCarousel(query: any) {
  return request({
    url: '/carousel/carousel/list',
    method: 'get',
    params: query
  })
}

// 查询轮播图列表不分页
export function listCarouselAll(query?: any) {
  return request({
    url: '/carousel/carousel/all',
    method: 'get',
    params: query
  })
}

// 查询轮播图管理详细
export function getCarousel(id: number | string) {
  return request({
    url: '/carousel/carousel/' + id,
    method: 'get'
  })
}

// 新增轮播图管理
export function addCarousel(data: any) {
  return request({
    url: '/carousel/carousel',
    method: 'post',
    data: data
  })
}

// 修改轮播图管理
export function updateCarousel(data: any) {
  return request({
    url: '/carousel/carousel',
    method: 'put',
    data: data
  })
}

// 删除轮播图管理
export function delCarousel(id: number | string) {
  return request({
    url: '/carousel/carousel/' + id,
    method: 'delete'
  })
}
