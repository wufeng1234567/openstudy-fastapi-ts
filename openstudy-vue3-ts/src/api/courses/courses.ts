import request from '@/utils/request'

// 查询课程信息列表
export function listCourses(query: any) {
  return request({
    url: '/courses/courses/list',
    method: 'get',
    params: query
  })
}

// 查询课程信息详细
export function getCourses(courseId: number | string) {
  return request({
    url: '/courses/courses/' + courseId,
    method: 'get'
  })
}

// 新增课程信息
export function addCourses(data: any) {
  return request({
    url: '/courses/courses',
    method: 'post',
    data: data
  })
}

// 修改课程信息
export function updateCourses(data: any) {
  return request({
    url: '/courses/courses',
    method: 'put',
    data: data
  })
}

// 删除课程信息
export function delCourses(courseId: number | string) {
  return request({
    url: '/courses/courses/' + courseId,
    method: 'delete'
  })
}
