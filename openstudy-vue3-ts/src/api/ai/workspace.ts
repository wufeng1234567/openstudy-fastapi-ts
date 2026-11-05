import request from '@/utils/request'
import { getToken } from '@/utils/auth'

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

/** 上传一个或多个文件到默认知识库（可带一句说明，帮 AI 以后认出这份资料） */
export function uploadToWorkspace(file: File | File[], note?: string, timeout = 600000) {
  const form = new FormData()
  const files = Array.isArray(file) ? file : [file]
  for (const item of files) {
    form.append('file', item, item.name)
  }
  return request({
    url: '/rag/workspace/upload',
    method: 'post',
    params: note ? { note } : undefined,
    data: form,
    timeout,
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/** 聊天中直接粘贴/上传的独立图片（我的资料图片墙用） */
export function listWorkspaceStandaloneImages(limit = 100) {
  return request({
    url: '/rag/workspace/standalone-images',
    method: 'get',
    params: { limit }
  })
}

/** 图片资产用途计数：{assetKey: count} */
export function getAssetUsageSummary() {
  return request({
    url: '/rag/assets/usage-summary',
    method: 'get'
  })
}

/* ============================================================================
 * 0.4.x 资料知识网络：画廊 / 引用 / 知识地图 / 版本对照
 * ========================================================================== */

export interface GalleryQuery {
  scope?: 'all' | 'current'
  kbId?: number | null
  source?: 'all' | 'document' | 'chat'
  status?: 'all' | 'pending' | 'processing' | 'done' | 'failed'
  q?: string
  limit?: number
}

/** 画廊列表：真实图片资产 + 描述状态 + 用途计数 */
export function listGalleryAssets(params: GalleryQuery = {}) {
  return request({
    url: '/rag/gallery',
    method: 'get',
    params: {
      scope: params.scope || 'all',
      kbId: params.kbId || undefined,
      source: params.source || 'all',
      status: params.status || 'all',
      q: params.q || undefined,
      limit: params.limit || 200
    }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

/** 单张图片详情（描述、OCR、来源章节、被引用记录） */
export function getGalleryAsset(assetKey: string) {
  return request({
    url: `/rag/gallery/${encodeURIComponent(assetKey)}`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

/** 批量补图片描述：传 docId 或 assetKeys */
export function describeGalleryAssets(data: { docId?: number; assetKeys?: string[]; limit?: number }) {
  return request({
    url: '/rag/gallery/describe',
    method: 'post',
    data,
    timeout: 300000
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

/** 资料知识地图 */
export function getKnowledgeMap(kbId?: number | null) {
  return request({
    url: '/rag/knowledge-map',
    method: 'get',
    params: kbId ? { kbId } : undefined
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export interface ContentReferencePayload {
  sourceType: 'document' | 'document_image' | 'chat_image' | 'note' | 'question'
  sourceId: number
  sourceSubId?: string
  targetType: 'document' | 'note' | 'question' | 'image'
  targetId: number
  quote?: string
  startOffset?: number
  endOffset?: number
}

export function createContentReference(data: ContentReferencePayload) {
  return request({
    url: '/rag/references',
    method: 'post',
    data
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

export function listContentReferences(params: {
  targetType?: string
  targetId?: number
  sourceType?: string
  sourceId?: number
  limit?: number
}) {
  return request({
    url: '/rag/references',
    method: 'get',
    params
  }) as unknown as Promise<{ code: number; msg?: string; data?: any[] }>
}

export function deleteContentReference(referenceId: number) {
  return request({
    url: `/rag/references/${referenceId}`,
    method: 'delete'
  })
}

/** 版本对照：from 历史版本 → 当前/另一个历史版本 */
export function diffDocumentVersions(docId: number, fromId: number, toId = 0) {
  return request({
    url: `/rag/document/versions/${docId}/diff`,
    method: 'get',
    params: { fromId, toId }
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

/** 单文档可检索开关 */
export function setDocumentSearchable(docId: number, disabled: boolean) {
  return request({
    url: `/rag/document/${docId}/searchable`,
    method: 'put',
    data: { disabled }
  })
}

/** 资料诊疗室 · 资料体检：四维评分 + 问题清单 + 章节覆盖热力（纯规则、可复现） */
export function getDocumentHealth(docId: number | string) {
  return request({
    url: `/rag/workspace/documents/${docId}/health`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}

export type StudyPackMode = 'review' | 'lecture' | 'outline'

export interface StudyPackStreamRequest {
  mode: StudyPackMode
  sectionIndexes: number[]
  instruction?: string
}

/**
 * 资料装配：把选中章节交给后端 LLM 重新组织，边生成边预览。
 *
 * 不能复用普通 `request`：它会把整个响应体等完才返回，长文档装配要等很久。
 * 这里的纯文本流契约与 `/ai/assistant/stream` 一致：正文增量 + `[DONE]` /
 * `Error: <原因>`。
 */
export interface StudyPrescriptionParams {
  days: number
  dailyMinutes: number
  goal: 'foundation' | 'exam' | 'weakness'
  sectionIndexes: number[]
  instruction?: string
}

/** 学习处方：由 LLM 根据体检结果和章节生成按天计划（结构化 JSON）。 */
export function generateStudyPrescription(docId: number | string, data: StudyPrescriptionParams) {
  return request({
    url: `/rag/workspace/documents/${docId}/prescription/generate`,
    method: 'post',
    data,
    timeout: 180000
  }) as unknown as Promise<{ code: number; msg?: string; data?: any }>
}

/** 导出学习处方：PDF / Word / Markdown / TXT */
export function exportStudyPrescription(
  docId: number | string,
  data: { format: 'pdf' | 'word' | 'docx' | 'md' | 'txt'; plan: any; meta?: any }
) {
  return request({
    url: `/rag/workspace/documents/${docId}/prescription/export`,
    method: 'post',
    data,
    responseType: 'blob',
    timeout: 120000
  })
}

export async function streamStudyPack(
  docId: number | string,
  data: StudyPackStreamRequest,
  onChunk?: (content: string) => void,
  onComplete?: (content: string) => void,
  onError?: (error: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const base = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  try {
    const response = await fetch(`${base}/rag/workspace/documents/${docId}/study-pack/stream`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + getToken(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        mode: data.mode,
        sectionIndexes: data.sectionIndexes,
        instruction: data.instruction || ''
      }),
      signal
    })

    if (!response.ok) {
      let detail = ''
      try {
        const raw = await response.text()
        if (raw) {
          try {
            const body = JSON.parse(raw)
            detail = body?.detail || body?.msg || body?.message || ''
          } catch {
            detail = raw.slice(0, 200)
          }
        }
      } catch {
        /* 读不出响应体时只保留 HTTP 状态 */
      }
      throw new Error(detail ? `装配失败 ${response.status}：${detail}` : `装配失败（HTTP ${response.status}）`)
    }

    const contentType = response.headers.get('content-type') || ''
    if (contentType.includes('application/json')) {
      let msg = '装配失败'
      try {
        const body = await response.json()
        msg = body?.msg || body?.message || msg
      } catch {
        /* 保留默认文案 */
      }
      throw new Error(msg)
    }
    if (!response.body) throw new Error('装配接口没有返回内容')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let full = ''
    let pending = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      let chunk = pending + decoder.decode(value, { stream: true })
      pending = ''
      // 兼容极端情况下上游把结束标记拆成两半。
      if (chunk.endsWith('[DO')) {
        pending = '[DO'
        chunk = chunk.slice(0, -3)
      }
      chunk = chunk.replace(/\[DONE\]/g, '')
      if (!chunk) continue
      if (chunk.indexOf('Error: ') === 0 && !full) {
        throw new Error(chunk.slice(7).trim())
      }
      full += chunk
      onChunk?.(full)
    }

    if (pending) full += pending.replace(/\[DONE\]/g, '')
    onComplete?.(full)
  } catch (error: any) {
    if (error?.name !== 'AbortError') onError?.(error)
  }
}

/** 智能整理：单文档预览（快速/深度） */
export function previewWorkspaceOrganize(data: {
  docId: number
  mode: 'deep'
  options?: Record<string, boolean>
}) {
  return request({
    url: '/rag/workspace/organize/preview',
    method: 'post',
    data
  })
}

/** 整理历史记录 */
export function listWorkspaceOrganizePlans(limit = 30) {
  return request({
    url: '/rag/workspace/organize/plans',
    method: 'get',
    params: { limit }
  })
}

/** 刷新整理计划状态 */
export function getWorkspaceOrganizePlan(planId: number) {
  return request({
    url: `/rag/workspace/organize/plans/${planId}`,
    method: 'get'
  })
}

/** 应用整理计划（只应用用户勾选的变更） */
export function applyWorkspaceOrganize(data: {
  planId: number
  changeIds?: string[]
  exclusionIds?: string[]
}) {
  return request({
    url: '/rag/workspace/organize/apply',
    method: 'post',
    data
  })
}

/** 读取一条整理记录；legacy 记录传负 planId */
export function getWorkspaceOrganizeRecord(recordId: number) {
  return request({
    url: `/rag/workspace/organize/records/${recordId}`,
    method: 'get'
  })
}

/** 删除一条整理记录；只删记录，不回退文档变更 */
export function deleteWorkspaceOrganizeRecord(recordId: number) {
  return request({
    url: `/rag/workspace/organize/records/${recordId}`,
    method: 'delete'
  })
}

/** 回退某次整理计划 */
export function rollbackWorkspacePlan(planId: number) {
  return request({
    url: `/rag/workspace/organize/plans/${planId}/rollback`,
    method: 'post'
  })
}

/** 兼容旧页面：整批回退智能整理 */
export function rollbackWorkspaceOrganize(batchId: string) {
  return request({
    url: '/rag/workspace/organize/rollback',
    method: 'post',
    data: { batchId }
  })
}

/** 记录一张图片资产被题目/笔记使用 */
export function recordAssetUsage(data: {
  assetKey: string
  assetUrl?: string
  targetType: 'question' | 'note' | 'document'
  targetId: number
}) {
  return request({
    url: '/rag/assets/usage',
    method: 'post',
    data
  })
}

/** 从默认知识库移除文件 */
export function deleteWorkspaceFile(docId: number | string) {
  return request({
    url: `/rag/workspace/file/${docId}`,
    method: 'delete'
  })
}

/* ============================================================================
 * 资料变微课（2026-10-31）
 * 后端按原文标题生成站点，不调用模型；前端负责展示与本地学习进度。
 * ========================================================================== */

export interface MicroCourseStation {
  id: string
  index: number
  title: string
  summary: string
  points: string[]
  minutes: number
  checkpoint: string
}

export interface MicroCourseBank {
  id: number
  name: string
  subject: string
  score: number
}

export interface MicroCourseResult {
  document: {
    id: number
    fileName: string
    subject: string
    materialType: string
    wordCount: number
    chunkCount: number
    hasOutline: boolean
    truncated: boolean
  }
  overview: {
    stationCount: number
    totalMinutes: number
    estimatedSessions: number
  }
  stations: MicroCourseStation[]
  relatedBanks: MicroCourseBank[]
}

export function getMicroCourse(docId: number | string) {
  return request({
    url: `/rag/document/micro-course/${docId}`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseResult }>
}

export interface MicroCourseHtmlResult {
  title?: string
  document: MicroCourseResult['document']
  overview: MicroCourseResult['overview']
  deck: {
    title: string
    subtitle: string
    slides: Array<{
      kind: string
      eyebrow?: string
      title: string
      subtitle?: string
      bullets?: string[]
      note?: string
    }>
  }
  html: string
  slides: number
  aiGenerated?: boolean
  recordId?: number
  version?: number
  changeSummary?: string
  createdAt?: string
  fromHistory?: boolean
  status?: 'generating' | 'ready' | 'failed'
  progress?: { current?: number; total?: number; phase?: string }
  errorMsg?: string
}

export interface MicroCourseHistoryItem {
  recordId: number
  docId: number
  version: number
  title: string
  changeSummary?: string
  slides: number
  aiGenerated: boolean
  createdAt: string
  fileName: string
}

/** 生成可在线演示的教学 HTML 课件（已有历史版本时直接读取） */
export function getMicroCourseHtml(docId: number | string, refresh = false, prompt = '', recordId?: number) {
  return request({
    url: `/rag/document/micro-course/${docId}/html`,
    method: 'get',
    params: {
      ...(refresh ? { refresh: true } : {}),
      ...(prompt ? { prompt } : {}),
      ...(recordId ? { recordId } : {})
    }
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult }>
}

/** 获取渐进式生成状态（包含当前已生成的 HTML） */
export function getMicroCourseStatus(docId: number | string) {
  return request({
    url: `/rag/document/micro-course/${docId}/status`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult | null }>
}

/** 导入外部 HTML 作为新版本 */
export function importMicroCourseHtml(docId: number | string, html: string, title?: string) {
  return request({
    url: `/rag/document/micro-course/${docId}/import`,
    method: 'post',
    data: { html, title: title || undefined }
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult }>
}

/** 微课历史版本列表 */
export function listMicroCourseHistory(docId: number | string) {
  return request({
    url: `/rag/document/micro-course/${docId}/history`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHistoryItem[] }>
}

/** 读取某个历史版本 */
export function getMicroCourseRecord(recordId: number | string) {
  return request({
    url: `/rag/document/micro-course/record/${recordId}`,
    method: 'get'
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult }>
}

/** 编辑单页 */
export function editMicroCourseSlide(recordId: number | string, slideIndex: number, patch: any) {
  return request({
    url: `/rag/document/micro-course/record/${recordId}/slide/${slideIndex}`,
    method: 'post',
    data: patch
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult & { before?: any; after?: any } }>
}

/** 调整页面顺序 */
export function reorderMicroCourseSlides(recordId: number | string, fromIndex: number, toIndex: number) {
  return request({
    url: `/rag/document/micro-course/record/${recordId}/reorder`,
    method: 'post',
    data: { fromIndex, toIndex }
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult }>
}

/** 重新生成单页 */
export function regenerateMicroCourseSlide(recordId: number | string, slideIndex: number, prompt = '') {
  return request({
    url: `/rag/document/micro-course/record/${recordId}/slides/${slideIndex}/regenerate`,
    method: 'post',
    data: { prompt }
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult & { before?: any; after?: any } }>
}

/** 插入新页面 */
export function insertMicroCourseSlide(recordId: number | string, index: number, slide: any) {
  return request({
    url: `/rag/document/micro-course/record/${recordId}/insert`,
    method: 'post',
    data: { index, slide }
  }) as unknown as Promise<{ code: number; msg?: string; data: MicroCourseHtmlResult }>
}

/** 把教学 HTML 转成 PPT（传 html 时按 HTML 的 slide 结构转换） */
export function downloadMicroCoursePptx(docId: number | string, html?: string, recordId?: number) {
  return request({
    url: `/rag/document/micro-course/${docId}/pptx`,
    method: 'post',
    data: { html: html || undefined, recordId: recordId || undefined },
    responseType: 'blob'
  })
}

/** 文档历史版本列表（编辑器内使用，不新增页面入口） */
export function listDocumentVersions(docId: number, limit = 30) {
  return request({
    url: `/rag/document/versions/${docId}`,
    method: 'get',
    params: { limit }
  })
}

/** 读取某个历史版本 */
export function getDocumentVersion(docId: number, versionId: number) {
  return request({
    url: `/rag/document/versions/${docId}/${versionId}`,
    method: 'get'
  })
}

/** 恢复历史版本（恢复前会自动保存当前版本） */
export function restoreDocumentVersion(docId: number, versionId: number) {
  return request({
    url: `/rag/document/versions/${docId}/${versionId}/restore`,
    method: 'post'
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

/** 跨资料夹级联搜索：资料夹名 + 内部文档名/备注/正文一起命中 */
export function searchWorkspaceCascade(query: string, folderLimit = 50, documentLimit = 20) {
  return request({
    url: '/rag/workspace/cascade-search',
    method: 'get',
    params: { q: query, folderLimit, documentLimit }
  }) as unknown as Promise<{ code: number; msg?: string; data: any }>
}
