/**
 * 文档附件的**结构化解析**（在线预览 + 抽取文档内嵌图片）
 *
 * 后端接口：`POST /ai/question-bank/parse-files-blocks`
 *   → 走 `app/services/file_parser.py`，返回
 *     `{ fileName, textContent, blocks, images, totalTextLength, error? }`
 *   · `blocks` 是**有序**的图文块列表（`type: 'text' | 'image'`），
 *     docx 里的图片会按原文位置插进文字之间；公式已转成 LaTeX、表格转成 `|` 分隔文本。
 *   · `images` 是文档内嵌图片的原始 data URL（未压缩）。
 *
 * 「AI 搭建题库」的富预览用的就是这个接口；聊天助手的附件预览现在也走同一套，
 * 于是「Word 里的插图」既能被看见（上传时一并送给模型 / DS），也能被点开预览。
 *
 * ⚠️ 本模块**不 import `@/api/ai/ai`**，避免和 `ai.ts` 形成循环依赖；
 * `ai.ts` 反过来从这里 re-export `parseFileBlocks`（保持旧调用方签名不变）。
 */

import request from '@/utils/request'
import { compressImageDataUrl, mimeOfDataUrl } from '@/utils/image-compress'

/** 有序内容块（与后端 `file_parser` 的 blocks 结构一致） */
export interface DocBlock {
  type: 'text' | 'image'
  /** 文本块正文 */
  content?: string
  /** 图片块的 data URL */
  imageUrl?: string
  orderIndex: number
  imageName?: string
}

export interface DocParse {
  fileName: string
  textContent: string
  blocks: DocBlock[]
  images: { orderIndex: number; imageUrl: string; imageName?: string }[]
  totalTextLength: number
  error?: string
}

/** 在线预览里最多保留几张文档插图 */
export const PREVIEW_MAX_IMAGES = 4
/** 在线预览插图的长边与体积上限（要落库，必须压到足够小） */
const PREVIEW_IMAGE_DIM = 1000
const PREVIEW_IMAGE_TARGET = 180 * 1024
/** 在线预览正文的字符上限（超长文档只留前 6 万字） */
export const PREVIEW_MAX_CHARS = 60000
/** 一并送给模型 / DS 的文档插图上限（张） */
export const DOC_UPLOAD_MAX_IMAGES = 8

/** 后端 `POST /ai/question-bank/parse-files-blocks`：多文件 → 单文件直接返回对象，多文件返回数组 */
export function parseFileBlocks(files: File[]) {
  const formData = new FormData()
  files.forEach((file) => {
    formData.append('files', file)
  })
  return request({
    url: '/ai/question-bank/parse-files-blocks',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    timeout: 120000
  })
}

/** 把 `data:...;base64,...` 还原成 File（用于把内存里的附件再次交给解析接口） */
export function dataUrlToFile(dataUrl: string, name: string, type = ''): File | null {
  try {
    const s = (dataUrl || '').trim()
    const comma = s.indexOf(',')
    if (!s.startsWith('data:') || comma < 0) return null
    const head = s.slice(0, comma)
    const body = s.slice(comma + 1)
    const mime = /data:([^;,]*)/i.exec(head)?.[1] || type || 'application/octet-stream'

    let bytes: Uint8Array
    if (/;base64/i.test(head)) {
      const bin = atob(body)
      bytes = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    } else {
      bytes = new TextEncoder().encode(decodeURIComponent(body))
    }
    return new File([bytes], name || 'file', { type: mime })
  } catch (e) {
    console.warn('[doc-parse] data URL 转 File 失败:', e)
    return null
  }
}

/** 解析单个文档（失败返回 null，调用方按「无预览」处理） */
export async function parseDocFile(file: File): Promise<DocParse | null> {
  try {
    const res: any = await parseFileBlocks([file])
    if (res?.code !== 200) {
      console.warn('[doc-parse] 解析失败:', res?.msg)
      return null
    }
    return res.data as DocParse
  } catch (e) {
    console.warn('[doc-parse] 解析异常:', e)
    return null
  }
}

/**
 * 把解析结果压成「适合落库 + 适合预览」的形态：
 *   · 文本总量截到 `PREVIEW_MAX_CHARS`
 *   · 插图最多 `PREVIEW_MAX_IMAGES` 张，并缩到长边 1000 / ≤180KB
 * 返回 null 表示这个文档没有可预览的内容。
 */
export async function buildDocPreview(
  doc: DocParse | null | undefined
): Promise<{ blocks: DocBlock[]; text: string; error?: string } | null> {
  if (!doc) return null
  const out: DocBlock[] = []
  let chars = 0
  let usedImages = 0

  for (const b of doc.blocks || []) {
    // 文本额度用完 + 插图额度也用完 → 后面的内容没必要再看
    if (chars >= PREVIEW_MAX_CHARS && usedImages >= PREVIEW_MAX_IMAGES) break
    if (b.type === 'image') {
      if (!b.imageUrl || usedImages >= PREVIEW_MAX_IMAGES) continue
      const small = await compressImageDataUrl(b.imageUrl, {
        maxDim: PREVIEW_IMAGE_DIM,
        softLimit: PREVIEW_IMAGE_TARGET,
        hardLimit: PREVIEW_IMAGE_TARGET
      })
      if (!small) continue
      usedImages += 1
      out.push({ type: 'image', content: '', imageUrl: small, orderIndex: out.length })
      continue
    }
    const text = (b.content || '').trim()
    if (!text) continue
    // ⚠️ 文本额度用完后**只能跳过文本，不能 break** —— 否则「前面的正文很长、
    //    插图在后半段」的 Word 会一张图都预览不到（实测踩到过）。
    if (chars >= PREVIEW_MAX_CHARS) continue
    const remain = PREVIEW_MAX_CHARS - chars
    const piece =
      text.length > remain ? `${text.slice(0, remain)}\n…（内容过长，仅预览前 ${PREVIEW_MAX_CHARS} 字）` : text
    chars += piece.length
    out.push({ type: 'text', content: piece, orderIndex: out.length })
  }

  // 一个块都没有：降级用 textContent（老格式或解析器没给 blocks）
  if (!out.length && doc.textContent) {
    out.push({
      type: 'text',
      content: doc.textContent.slice(0, PREVIEW_MAX_CHARS),
      orderIndex: 0
    })
  }
  if (!out.length) return { blocks: [], text: '', error: doc.error || '' }
  return { blocks: out, text: (doc.textContent || '').slice(0, PREVIEW_MAX_CHARS), error: doc.error }
}

/**
 * 抽取文档内嵌的插图（**压缩后**的 data URL），用于把它们当成图片一起上传。
 *
 * 为什么需要：Word 里的图表 / 公式截图对 AI 理解内容很关键。
 * 官方 API 链路后端会自己抽（`chat_engine.extract_attachments`）；
 * 但 **ds-free 链路是把文件直接丢给 DS 网页端的，DS 只读文字、看不到插图**，
 * 所以前端要把插图抽出来，作为图片附件一起送过去。
 *
 * 必须压缩：docx 里的原图动辄几 MB，直传会撑爆扩展的 IPC 通道
 * （表现为「无法连接到 DeepSeek 页面」，详见 utils/image-compress.ts）。
 */
export async function collectDocImages(
  docs: (DocParse | null | undefined)[],
  limit = DOC_UPLOAD_MAX_IMAGES
): Promise<{ name: string; type: string; base64: string }[]> {
  const out: { name: string; type: string; base64: string }[] = []
  const seen = new Set<string>()
  for (const doc of docs) {
    for (const img of doc?.images || []) {
      if (out.length >= limit) return out
      const url = img?.imageUrl
      if (!url || seen.has(url)) continue
      seen.add(url)
      const base64 = await compressImageDataUrl(url)
      const mime = mimeOfDataUrl(base64) || 'image/png'
      // 名字带上「来源文档名 + 序号」，扩展名按**真实 MIME** 给（原图是 jpeg 就不能写成 .png）
      const docBase = (doc?.fileName || '文档').replace(/\.[^.]+$/, '') || '文档'
      out.push({
        name: `${docBase}-插图${out.length + 1}.${extFromMime(mime)}`,
        type: mime,
        base64
      })
    }
  }
  return out
}

/** 文档类附件的扩展名（这些才值得去调解析接口） */
const DOC_EXTS = ['docx', 'doc', 'pdf', 'txt', 'md', 'markdown']

export function isDocFile(name: string, type = ''): boolean {
  if (type && type.startsWith('image/')) return false
  const ext = (name || '').split('.').pop()?.toLowerCase() || ''
  return DOC_EXTS.includes(ext)
}

/* ============================================================
 * 附件命名
 * 原则：**有自带命名的一律用自带的**（就是用户在系统里看到的名字，含扩展名），
 *      只有「没有名字」或「名字是 image.png 这种浏览器的通用占位」时才兜底生成，
 *      而且兜底名也要可读（不是单纯一个后缀缩写）。
 * ============================================================ */

/** 浏览器给剪贴板图片 / 无名文件时的通用占位名，这些名字没有任何信息量 */
const GENERIC_NAMES = [
  'image',
  'image.png',
  'image.jpg',
  'image.jpeg',
  'blob',
  'file',
  'untitled',
  'screenshot',
  '未命名'
]

/** 常见 MIME → 扩展名（兜底命名时用，避免一律写成 .png / .txt） */
const MIME_EXT: Record<string, string> = {
  'image/jpeg': 'jpg',
  'image/svg+xml': 'svg',
  'image/x-icon': 'ico',
  'image/bmp': 'bmp',
  'image/webp': 'webp',
  'application/pdf': 'pdf',
  'application/msword': 'doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'application/vnd.ms-excel': 'xls',
  'application/vnd.ms-powerpoint': 'ppt',
  'application/zip': 'zip',
  'application/json': 'json',
  'application/xml': 'xml',
  'text/plain': 'txt',
  'text/markdown': 'md',
  'text/csv': 'csv',
  'text/html': 'html'
}

/** MIME → 扩展名；认不出来就给 bin（不给一长串没意义的"扩展名"） */
export function extFromMime(mime = ''): string {
  const m = (mime || '').toLowerCase().trim()
  if (!m) return 'bin'
  if (MIME_EXT[m]) return MIME_EXT[m]
  const sub = (m.split('/')[1] || '').split('+')[0].replace(/[^a-z0-9]/g, '')
  return sub && sub.length <= 8 ? sub : 'bin'
}

/** 这个名字是不是「没有信息量的通用占位名」 */
export function isGenericFileName(name: string): boolean {
  const base = (name || '').trim().toLowerCase()
  if (!base) return true
  const stem = base.replace(/\.[^.]+$/, '')
  return GENERIC_NAMES.includes(base) || GENERIC_NAMES.includes(stem)
}

/** 本地时间戳 YYYYMMDD-HHmmss */
function stamp(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  )
}

/**
 * 生成一个**可读且不重复**的兜底文件名，例如 `粘贴图片-20260916-114530-1.png`。
 *
 * 只在文件本身没有名字（剪贴板图片、程序生成的 data URL）时才用；
 * 有自带命名的一律优先用自带的 —— 那才是用户认得出来的名字。
 */
export function makeFallbackFileName(
  opts: { mime?: string; label?: string; index?: number } = {}
): string {
  const label = (opts.label || '附件').trim() || '附件'
  const ext = extFromMime(opts.mime || '')
  const seq = (opts.index ?? 0) > 0 ? `-${(opts.index as number) + 1}` : ''
  return `${label}-${stamp()}${seq}.${ext}`
}

/** 选一个「合理的附件名」：自带命名优先，通用占位名才兜底生成 */
export function resolveFileName(
  name: string | undefined,
  opts: { mime?: string; label?: string; index?: number } = {}
): string {
  const given = (name || '').trim()
  if (given && !isGenericFileName(given)) return given
  return makeFallbackFileName({ ...opts, mime: opts.mime || '' })
}
