import request from '@/utils/request'

/** 读取 RAG 向量化配置 + 本地/云端可用性检测 */
export function getRagConfig() {
  return request({
    url: '/rag/config',
    method: 'get'
  })
}

/** 更新 RAG 向量化配置（即时生效） */
export function updateRagConfig(data: Record<string, any>) {
  return request({
    url: '/rag/config',
    method: 'put',
    data
  })
}
