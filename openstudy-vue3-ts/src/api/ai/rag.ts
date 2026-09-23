import request from '@/utils/request'

/**
 * RAG 知识库 API 客户端
 *
 * 后端 `app/api/v1/rag.py`。响应形状沿用仓库主流：HTTP 200 + `body.code`，
 * `request()` 已经把 `body` 解出来返回，所以调用方判 `res.code === 200` 再读 `res.data`。
 *
 * 与 `/ai/agent/*` 那几个族**刻意不同**（那边是 403 + fail 信封 / SSE，不要统一）——
 * 这里不要照抄 agent 的解析方式。
 */

/* ===================== 类型 ===================== */

export interface RagKnowledgeBase {
  kbId: number
  name: string
  description?: string | null
  /**
   * 是否被屏蔽：1 = 已屏蔽（智能体看不到这个库），0 = 正常
   *
   * ⚠️ 是整数 0/1，**不是布尔** —— 后端把库里 `disabled SMALLINT NOT NULL DEFAULT 0`
   * 的那个值原样返回，前端别自己转成 boolean 再转回去，那样写回时会对不上。
   */
  disabled: number
  docCount?: number
  chunkCount?: number
  createTime?: string | null
}

export interface RagDocument {
  docId: number
  kbId: number
  fileName: string
  fileType?: string | null
  fileSize?: number | null
  chunkCount?: number
  /** 1 待解析 / 2 解析中 / 3 已解析 / 4 处理失败 / 5 已向量化 */
  status: number
  /** 后端给的中文状态文案（与 `models/rag.py` 的 DOC_STATUS_TEXT 同一份） */
  statusText?: string
  errorMsg?: string | null
  createTime?: string | null
}

export interface RagChunk {
  chunkId: number
  chunkIndex: number
  content: string
  contentLength?: number
  /** 是否已经带上向量（没向量的分块检索不到） */
  vectorized?: boolean
}

export interface RagSearchHit {
  chunkId: number
  docId: number
  kbId?: number
  docName?: string | null
  chunkIndex: number
  content: string
  score?: number
  keywordScore?: number | null
  vectorScore?: number | null
  source?: string
}

/* ===================== 文档状态（给 UI 用） ===================== */

export const DOC_PENDING = 1
export const DOC_PARSING = 2
export const DOC_PARSED = 3
export const DOC_FAILED = 4
export const DOC_VECTORIZED = 5

/** 处理还没结束 —— 需要继续轮询 */
export function isDocumentProcessing(status: number): boolean {
  return status === DOC_PENDING || status === DOC_PARSING
}

/** 已经**可检索**（用户关心的是这个，而不是「有没有解析完」） */
export function isDocumentSearchable(status: number): boolean {
  return status === DOC_VECTORIZED
}

/**
 * 状态 → Element Plus tag 类型
 *
 * ⚠️ `DOC_PARSED(3)` 单独标成 info 而不是 success：它只是「解析出了文本」，
 * 分块还没向量化 —— 这时候去检索**什么都查不到**。以前不分这两个状态，
 * 界面上看着「已完成」，用户却搜不出东西，只会怀疑是搜索坏了。
 */
export function documentTagType(status: number): 'success' | 'info' | 'warning' | 'danger' {
  if (status === DOC_VECTORIZED) return 'success'
  if (status === DOC_FAILED) return 'danger'
  if (status === DOC_PARSING) return 'warning'
  return 'info'
}

/** 失败之外都还可以重试（重试 = 重跑解析 + 向量化） */
export function canReprocessDocument(status: number): boolean {
  return status !== DOC_PARSING
}

/* ===================== 上传 ===================== */

/** 可上传的扩展名（后端 `file_parser.parse_file` 支持的文本类格式） */
export const KB_FILE_EXTENSIONS = ['txt', 'md', 'pdf', 'docx', 'doc'] as const

/** `accept` 属性用 */
export const KB_FILE_ACCEPT = '.txt,.md,.pdf,.docx,.doc'

/**
 * 按扩展名判断能不能传
 *
 * 前端只挡明显不支持的（给即时反馈），真正的把关在后端 —— 解析失败会返回
 * 400 + 人话原因，那条路径也要能正常显示，不能只靠前端预检。
 */
export function isSupportedKbFile(fileName: string): boolean {
  const name = String(fileName || '')
  const dot = name.lastIndexOf('.')
  if (dot < 0 || dot === name.length - 1) return false
  const ext = name.slice(dot + 1).toLowerCase()
  return (KB_FILE_EXTENSIONS as readonly string[]).includes(ext)
}

/** 拼上传表单。`kbId` 走 **query**（后端是 `Query(..., alias="kbId")`），不是表单字段 */
export function buildUploadForm(file: File | Blob, fileName?: string): FormData {
  const form = new FormData()
  // 第三个参数是文件名 —— 不给的话浏览器会用 Blob 的默认名，后端拿到的 file_name 就是错的
  form.append('file', file, fileName || (file as File).name || '未命名文档')
  return form
}

/* ===================== 知识库 ===================== */

export function listKnowledgeBases() {
  return request({
    url: '/rag/knowledgeBase/list',
    method: 'get'
  })
}

export function createKnowledgeBase(data: { name: string; description?: string }) {
  return request({
    url: '/rag/knowledgeBase',
    method: 'post',
    data
  })
}

export function getKnowledgeBase(kbId: number) {
  return request({
    url: `/rag/knowledgeBase/${kbId}`,
    method: 'get'
  })
}

/**
 * 改知识库（改名 / 改描述 / 屏蔽开关都走这一个接口）
 *
 * ⚠️ 屏蔽**刻意复用这个 PUT**，没有单独开路由：`app/api/v1/catch_all.py` 会按路径关键词
 * 兜底分发，新路由一旦拼错就会返回**假的 200 + `data: null`**，比复用更难发现。
 * 所以 `disabled` 就是同一个 body 里的一个字段，`0` 启用 / `1` 已屏蔽。
 */
export function updateKnowledgeBase(
  kbId: number,
  data: { name?: string; description?: string; disabled?: 0 | 1 }
) {
  return request({
    url: `/rag/knowledgeBase/${kbId}`,
    method: 'put',
    data
  })
}

/**
 * 删除知识库
 *
 * ⚠️ 后端是**逻辑删**（`del_flag='2'`）但会**物理清掉**文档与分块 ——
 * 也就是「列表里没了、检索不到了，但库本身的行还在」。UI 按「已删除」呈现即可，
 * 别承诺「数据彻底抹掉」。
 */
export function deleteKnowledgeBase(kbId: number) {
  return request({
    url: `/rag/knowledgeBase/${kbId}`,
    method: 'delete'
  })
}

/* ===================== 文档 ===================== */

export function listDocuments(kbId: number) {
  return request({
    url: `/rag/document/list/${kbId}`,
    method: 'get'
  })
}

/** 上传文档（后端同步解析 + 后台向量化，返回后要轮询状态） */
export function uploadDocument(kbId: number, file: File, timeout = 600000) {
  return request({
    url: '/rag/document/upload',
    method: 'post',
    params: { kbId },
    data: buildUploadForm(file),
    timeout,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/** 直接导入纯文本（不经过文件解析） */
export function importDocumentText(kbId: number, content: string, fileName?: string) {
  return request({
    url: '/rag/document/uploadText',
    method: 'post',
    data: { kbId, content, fileName: fileName || '未命名文档.txt' }
  })
}

export function getDocumentContent(docId: number) {
  return request({
    url: `/rag/document/content/${docId}`,
    method: 'get'
  })
}

export function getDocumentChunks(docId: number, limit = 200) {
  return request({
    url: `/rag/document/chunks/${docId}`,
    method: 'get',
    params: { limit }
  })
}

/** 处理进度（上传后轮询这个，直到 `done`） */
export function getDocumentStatus(docId: number) {
  return request({
    url: `/rag/document/status/${docId}`,
    method: 'get'
  })
}

export function deleteDocument(docId: number) {
  return request({
    url: `/rag/document/${docId}`,
    method: 'delete'
  })
}

/** 失败重试（重跑解析 + 向量化） */
export function reprocessDocument(docId: number) {
  return request({
    url: `/rag/document/reprocess/${docId}`,
    method: 'post'
  })
}

/* ===================== 检索（预览用） ===================== */

/**
 * 只检索、不调模型
 *
 * 给「我传的资料到底有没有被检索到」这个疑问用 —— 问答本身走 Agent 的
 * `knowledge_search` 工具，不需要前端再接一遍 `/rag/ask`。
 */
export function searchKnowledge(query: string, kbIds?: number[], topK = 5) {
  return request({
    url: '/rag/search',
    method: 'post',
    data: { query, kbIds, topK }
  })
}
