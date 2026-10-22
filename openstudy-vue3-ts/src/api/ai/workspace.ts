import request from '@/utils/request'

/** 工作空间概况 + 文件列表 */
export function getWorkspace() {
  return request({
    url: '/rag/workspace',
    method: 'get'
  })
}

/** 上传文件到工作空间（可带一句说明，帮 AI 以后认出这份资料） */
export function uploadToWorkspace(file: File, note?: string, timeout = 600000) {
  const form = new FormData()
  form.append('file', file, file.name)
  return request({
    url: '/rag/workspace/upload',
    method: 'post',
    params: note ? { note } : undefined,
    data: form,
    timeout,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/** 从工作空间移除文件 */
export function deleteWorkspaceFile(docId: number | string) {
  return request({
    url: `/rag/workspace/file/${docId}`,
    method: 'delete'
  })
}

/** 按自然语言找文件（页面上的「试试 AI 怎么找」用） */
export function searchWorkspace(query: string, limit = 5) {
  return request({
    url: '/rag/workspace/search',
    method: 'post',
    data: { query, limit }
  })
}
