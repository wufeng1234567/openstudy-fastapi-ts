import request from '@/utils/request'

/**
 * 文档编排 API 客户端
 *
 * 后端 `app/api/v1/doc_compose.py`。响应形状沿用仓库主流：
 * HTTP 200 + `body.code`，`request()` 已经把 body 解出来返回，
 * 所以调用方判 `res.code === 200` 再读 `res.data`。
 *
 * 与 `/ai/agent/*` 刻意不同（那边是 SSE / 确认信封），不要混用解析方式。
 */

/* ===================== 类型 ===================== */

/** 主题（后端 `THEMES` 生成） */
export interface DocComposeTheme {
  value: string
  label: string
  bodyFont?: string
  headFont?: string
  bodySizePt?: number
  lineSpacing?: number
  firstLineIndentEm?: number
  headColor?: string
  tableHeaderFill?: string
}

/** 产物文件 */
export interface DocComposeFile {
  /**
   * 相对上传目录的路径，如 `export/2026/10/27/xxx_文档.docx`
   *
   * ⚠️ 这是给**落库 / 二次处理**用的，不是能直接 fetch 的地址。
   *    前端要预览或下载请用 `url`。
   */
  path: string
  /**
   * 可直接 fetch 的地址，形如 `/profile/export/2026/10/27/xxx_文档.docx`
   *
   * ⚠️ 静态文件挂在 `/profile`（见后端 main.py 的 app.mount），
   *    用 `path` 直接拼 `/dev-api/` 会 404（实测拿到 45 字节的错误页）。
   */
  url: string
  name: string
  type: 'docx' | 'pdf'
  size: number
}

/** 解析诊断信息 */
export interface DocComposeAnalysis {
  issues?: string[]
  issueCount?: number
  blocks?: number
  blockTypeCounts?: Record<string, number>
  headingLevels?: number[]
  charCount?: number
  detectedTitle?: string
}

/** 渲染结果 */
export interface DocComposeResult {
  files: DocComposeFile[]
  /** docx 的 url */
  url: string
  /** pdf 的 url（没生成时为空） */
  pdfUrl: string
  /** PDF 失败原因（不致命，docx 仍可用） */
  pdfError?: string | null
  spec: Record<string, any>
  blockCount: number
  theme: string
  themeLabel: string
  analysis: DocComposeAnalysis
}

/** 渲染请求 */
export interface DocComposeRenderParams {
  markdown?: string
  spec?: Record<string, any>
  title?: string
  subtitle?: string
  author?: string
  theme?: string
  cover?: boolean
  toc?: boolean
  header?: string
  footer?: string
  wantPdf?: boolean
  filename?: string
}

/* ===================== 接口 ===================== */

/** 渲染成 docx（可选 pdf），返回可访问 URL */
export function renderDocCompose(data: DocComposeRenderParams) {
  return request({
    url: '/ai/docCompose/render',
    method: 'post',
    data,
    // PDF 走 LibreOffice，冷启动可能 5~10 秒
    timeout: 120000,
  })
}

/**
 * 预览（只出 docx，不产 PDF）
 *
 * 与 render 分开是因为语义不同：预览要快，下载要完整。
 * 后端在这条路径上不出 PDF、默认不出封面目录。
 */
export function previewDocCompose(data: DocComposeRenderParams) {
  return request({
    url: '/ai/docCompose/preview',
    method: 'post',
    data,
    timeout: 60000,
  })
}

/** 主题清单 */
export function getDocComposeTemplates() {
  return request({
    url: '/ai/docCompose/templates',
    method: 'get',
  })
}

/**
 * AI 优化内容结构
 *
 * ⚠️ 后端承诺只调结构、不改事实。前端仍保留调用前快照以便撤销 ——
 *    模型不总是守规矩，而用户不一定会逐句复核。
 */
export function polishDocCompose(data: { markdown: string; instruction?: string; theme?: string }) {
  return request({
    url: '/ai/docCompose/polish',
    method: 'post',
    data,
    timeout: 180000,
  })
}
