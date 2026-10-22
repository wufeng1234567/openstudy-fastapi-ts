import request from '@/utils/request'

/**
 * 知识库 API
 *
 * ⚠️ 命名说明（2026-10-22）：
 *   产品文案上「我的空间」已并入「知识库」，但这个文件的函数名保留 `Workspace`
 *   字样 —— 前端只改文案、不改标识，避免和 `api/ai/rag.ts` 里那套
 *   （对话页抽屉用的）混在一起时更难分辨。
 *   两者的后端接口是**同一套数据**：
 *     · 本文件 `/rag/workspace/*`  —— 默认库专用（不需要传 kbId）
 *     · `api/ai/rag.ts` 的 `/rag/knowledgeBase/*`、`/rag/document/*` —— 任意库
 */

/** 知识库总览：全部知识库 + 每个库的文档（新版知识库页用） */
export function getWorkspaceOverview() {
  return request({
    url: '/rag/workspace/overview',
    method: 'get'
  })
}

/** 默认知识库概况 + 文件列表（旧接口，兼容保留） */
export function getWorkspace() {
  return request({
    url: '/rag/workspace',
    method: 'get'
  })
}

/** 上传文件到默认知识库（可带一句说明，帮 AI 以后认出这份资料） */
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

/** 从默认知识库移除文件 */
export function deleteWorkspaceFile(docId: number | string) {
  return request({
    url: `/rag/workspace/file/${docId}`,
    method: 'delete'
  })
}

/**
 * 语义检索（RAG）
 *
 * ⚠️ 2026-10-22 重做：后端这个接口原先走的是**纯字符串匹配**且只搜默认库，
 * 现在已改为真正的混合检索（向量 + 全文 + RRF）。
 * `kbIds` 传了 = 只搜这些库；不传 = 搜该用户全部知识库。
 */
export function searchWorkspace(query: string, limit = 5, kbIds?: number[]) {
  return request({
    url: '/rag/workspace/search',
    method: 'post',
    data: { query, limit, kbIds: kbIds && kbIds.length ? kbIds : undefined },
    // 首次检索要现加载 embedding 模型（本地 bge-m3 约 15s），超时给足
    timeout: 120000
  })
}
