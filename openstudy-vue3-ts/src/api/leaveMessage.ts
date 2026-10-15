import request from '@/utils/request'

export const getLeaveMessageList = () => {
  return request({
    url: '/leaveMessage/list',
    method: 'get'
  })
}

export const addLeaveMessage = (data: any) => {
  return request({
    url: '/leaveMessage/add',
    method: 'post',
    data: data
  })
}

export const listMessage = (userName: string, content: string) => {
  return request({
    url: '/leaveMessage/admin/list',
    method: 'get',
    params: { userName, content }
  })
}

export const delMessage = (id: number | string) => {
  return request({
    url: `/leaveMessage/${id}`,
    method: 'delete'
  })
}

export const updateMessage = (data: any) => {
  return request({
    url: '/leaveMessage',
    method: 'put',
    data: data
  })
}

export const addMessage = (data: any) => {
  return request({
    url: '/leaveMessage/admin/add',
    method: 'post',
    data: data
  })
}
