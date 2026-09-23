import request from '@/utils/request'

// 查询笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记列表
export function listNoteCategory(query: any) {
  return request({
    url: '/noteCategory/noteCategory/list',
    method: 'get',
    params: query
  })
}

// 查询笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记详细
export function getNoteCategory(id: number | string) {
  return request({
    url: '/noteCategory/noteCategory/' + id,
    method: 'get'
  })
}

// 新增笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记
export function addNoteCategory(data: any) {
  return request({
    url: '/noteCategory/noteCategory',
    method: 'post',
    data: data
  })
}

// 修改笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记
export function updateNoteCategory(data: any) {
  return request({
    url: '/noteCategory/noteCategory',
    method: 'put',
    data: data
  })
}

// 删除笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记
export function delNoteCategory(id: number | string) {
  return request({
    url: '/noteCategory/noteCategory/' + id,
    method: 'delete'
  })
}


// 获取所有分类（不分页）
export function getAllNoteCategory(params?: any) {
  return request({
    url: '/noteCategory/noteCategory/all',
    method: 'get',
    params
  });
}
