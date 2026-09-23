/**
 * 图片压缩 / 缩放工具（data URL 进、data URL 出）
 *
 * 为什么要做这件事：
 * DS 扩展链路把图片以 base64 data URL 的形式，经
 *   SDK(隔离域) → window.postMessage → bridge(内容脚本) → chrome.runtime.sendMessage
 *   → background → chrome.scripting.executeScript(args)
 * 送到 chat.deepseek.com 页面。这条链路每一跳都要做一次结构化克隆/JSON 序列化，
 * 一张 5MB 的截图 base64 后约 6.8MB，多张就会把 IPC 顶到上限并抛错
 * （表现为「无法连接到 DeepSeek 页面」，看起来像通信故障）。
 *
 * 所以在前端先把大图缩到合理尺寸再传，既稳又快；DS 官网本身也会再压缩一次，
 * 视觉上几乎没有差别（截图里的文字在 1600px 下依然清晰）。
 */

/** 缩放后长边上限（约等于主流手机屏幕宽度，够 DS 识别细节） */
const DEFAULT_MAX_DIM = 1600
/** JPEG 质量，逐档降级 */
const QUALITY_LADDER = [0.85, 0.72, 0.6]
/** 小于这个体积就不折腾了（约 800KB） */
const SOFT_LIMIT_BYTES = 800 * 1024
/** 压缩后仍不超过这个体积就接受（约 1.5MB） */
const HARD_LIMIT_BYTES = 1500 * 1024
/** 不做压缩的格式：GIF 会丢动画、SVG 可能污染 canvas */
const SKIP_TYPES = ['image/gif', 'image/svg+xml']

/** 粗略估算 data URL 的字节数（不解码，避免大字符串开销） */
export function dataUrlByteSize(dataUrl: string): number {
  const comma = dataUrl.indexOf(',')
  if (comma < 0) return dataUrl.length
  const b64 = dataUrl.slice(comma + 1)
  if (!dataUrl.slice(0, comma).includes('base64')) return b64.length
  const padding = b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0
  return Math.floor((b64.length * 3) / 4) - padding
}

/** 人类可读体积，用于提示文案 */
export function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 从 data URL 头里取 MIME */
export function mimeOfDataUrl(dataUrl: string): string {
  const m = /^data:([^;,]+)/i.exec(dataUrl)
  return m ? m[1].toLowerCase() : ''
}

/**
 * 图片解码超时（毫秒）。
 *
 * 极少见但真实存在：某些损坏 / 超大的 data URL，浏览器既不触发 onload
 * 也不触发 onerror，Promise 就永远挂着。调用方（历史落库、自动压缩）都在
 * await 它，一挂整条链路就静默卡死 —— 表现是「回复正常但历史一直存不上」。
 */
const DECODE_TIMEOUT_MS = 5000

const loadImage = (src: string, timeout = DECODE_TIMEOUT_MS): Promise<HTMLImageElement> =>
  new Promise((resolve, reject) => {
    const img = new Image()
    let settled = false
    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      img.src = ''
      reject(new Error('图片解码超时'))
    }, timeout)
    const done = (fn: () => void) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      fn()
    }
    img.onload = () => done(() => resolve(img))
    img.onerror = () => done(() => reject(new Error('图片解码失败')))
    img.src = src
  })

/** 历史记录里「点开查看」用图的长边上限（与发送给模型的压缩档一致） */
const PREVIEW_MAX_DIM = 1600
/** 查看用图的体积上限（约 900KB）——保证点开看得清，又不至于把历史表撑爆 */
const PREVIEW_TARGET_BYTES = 900 * 1024
/** 查看用图的质量阶梯（比列表缩略图更保真，逐档降级到体积达标） */
const PREVIEW_QUALITY_LADDER = [0.9, 0.8, 0.68, 0.55]

export interface ImageVariants {
  /** 列表 / 气泡里显示的小缩略图（长边 240） */
  thumb: string
  /** 点击放大后显示的查看图（长边 ≤1600） */
  preview: string
}

/**
 * 一次解码，同时产出**两种尺寸**：列表缩略图 + 点开查看图。
 *
 * 为什么需要两张：
 *   · 历史消息如果只存 240px 缩略图，刷新后点开就是「把 240px 拉满全屏」，
 *     字全都糊成一团（用户实测反馈「根本看不清」）；
 *   · 但列表也没必要每张都加载 1600px，图多时会明显变卡。
 * 所以列表用小图、查看器用大图，各取所需。
 *
 * 大图策略：原图（也就是已经压缩过、真正发给模型的那张）本来就够小就直接用，
 * 不做任何重编码；否则缩到 1600 并按质量阶梯压到目标体积。PNG 截图优先保留
 * 无损（文字更锐利），超标才退到 JPEG。
 *
 * 失败返回空串，调用方按「无图」处理即可（会回退到原图）。
 */
export async function makeImageVariants(
  dataUrl: string,
  opts: { thumbDim?: number; previewDim?: number; previewTarget?: number } = {}
): Promise<ImageVariants> {
  const empty: ImageVariants = { thumb: '', preview: '' }
  try {
    if (!dataUrl || !dataUrl.startsWith('data:image/')) return empty
    const srcMime = mimeOfDataUrl(dataUrl)
    if (SKIP_TYPES.includes(srcMime)) return empty

    const img = await loadImage(dataUrl)
    const w = img.naturalWidth || img.width
    const h = img.naturalHeight || img.height
    if (!w || !h) return empty

    const draw = (maxDim: number, quality: number, type = 'image/jpeg'): string => {
      const scale = Math.min(1, maxDim / Math.max(w, h))
      const tw = Math.max(1, Math.round(w * scale))
      const th = Math.max(1, Math.round(h * scale))
      const canvas = document.createElement('canvas')
      canvas.width = tw
      canvas.height = th
      const ctx = canvas.getContext('2d')
      if (!ctx) return ''
      // 透明底转 JPEG 会变黑，先铺白底
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, tw, th)
      ctx.drawImage(img, 0, 0, tw, th)
      return canvas.toDataURL(type, quality)
    }

    const thumb = draw(opts.thumbDim ?? 240, 0.7)
    const target = opts.previewTarget ?? PREVIEW_TARGET_BYTES
    const previewDim = opts.previewDim ?? PREVIEW_MAX_DIM

    let preview = ''
    if (dataUrlByteSize(dataUrl) <= target) {
      // 已经小到可以直接存，保留原样（无损）
      preview = dataUrl
    } else if (srcMime === 'image/png') {
      const png = draw(previewDim, 1, 'image/png')
      if (png && dataUrlByteSize(png) <= target) preview = png
    }
    if (!preview) {
      let best = ''
      for (const quality of PREVIEW_QUALITY_LADDER) {
        const out = draw(previewDim, quality)
        if (!out) continue
        best = out
        if (dataUrlByteSize(out) <= target) break
      }
      preview = best || dataUrl
    }

    return { thumb, preview }
  } catch (e) {
    console.warn('[image-compress] 生成图片尺寸变体失败:', e)
    return empty
  }
}

/**
 * 压缩图片 data URL。
 *
 * 失败时**原样返回**，绝不因为压缩失败而丢掉用户选的图。
 */
export async function compressImageDataUrl(
  dataUrl: string,
  opts: { maxDim?: number; softLimit?: number; hardLimit?: number } = {}
): Promise<string> {
  const maxDim = opts.maxDim ?? DEFAULT_MAX_DIM
  const softLimit = opts.softLimit ?? SOFT_LIMIT_BYTES
  const hardLimit = opts.hardLimit ?? HARD_LIMIT_BYTES

  try {
    if (!dataUrl.startsWith('data:image/')) return dataUrl
    if (SKIP_TYPES.includes(mimeOfDataUrl(dataUrl))) return dataUrl
    // 本来就不大，保持原样（不重编码，避免无谓的画质损失）
    if (dataUrlByteSize(dataUrl) <= softLimit) return dataUrl

    const img = await loadImage(dataUrl)
    const w = img.naturalWidth || img.width
    const h = img.naturalHeight || img.height
    if (!w || !h) return dataUrl

    const scale = Math.min(1, maxDim / Math.max(w, h))
    const tw = Math.max(1, Math.round(w * scale))
    const th = Math.max(1, Math.round(h * scale))

    const canvas = document.createElement('canvas')
    canvas.width = tw
    canvas.height = th
    const ctx = canvas.getContext('2d')
    if (!ctx) return dataUrl
    // 透明底转 JPEG 会变黑，先铺白底
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, tw, th)
    ctx.drawImage(img, 0, 0, tw, th)

    // 截图类（PNG）优先保留无损，文字更锐利；体积可接受就用 PNG
    const srcMime = mimeOfDataUrl(dataUrl)
    if (srcMime === 'image/png') {
      try {
        const png = canvas.toDataURL('image/png')
        if (dataUrlByteSize(png) <= hardLimit) return png
      } catch {
        /* 忽略，降级到 JPEG */
      }
    }

    let best = ''
    for (const quality of QUALITY_LADDER) {
      const out = canvas.toDataURL('image/jpeg', quality)
      best = out
      if (dataUrlByteSize(out) <= hardLimit) return out
    }
    // 全部档位都超标：返回最小的一档（比原图小就行）
    return best && dataUrlByteSize(best) < dataUrlByteSize(dataUrl) ? best : dataUrl
  } catch (e) {
    console.warn('[image-compress] 压缩失败，使用原图:', e)
    return dataUrl
  }
}
