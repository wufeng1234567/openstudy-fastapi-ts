import { ElMessageBox } from 'element-plus'

const IMAGE_UPLOAD_EXTS = new Set(['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'])

export function uploadFileExt(file: File): string {
  const dot = file.name.lastIndexOf('.')
  return dot < 0 ? '' : file.name.slice(dot + 1).toLowerCase()
}

export function isImageUploadFile(file: File): boolean {
  return file.type.startsWith('image/') || IMAGE_UPLOAD_EXTS.has(uploadFileExt(file))
}

/** 找出 Markdown 里引用、但当前选择中没有的本地图片文件名。 */
export async function missingMarkdownImageFiles(files: File[]): Promise<{ file: File; missing: string[] }[]> {
  const selectedImages = new Set(files.filter(isImageUploadFile).map((file) => file.name))
  const result: { file: File; missing: string[] }[] = []
  for (const file of files) {
    if (uploadFileExt(file) !== 'md' && uploadFileExt(file) !== 'markdown') continue
    let text = ''
    try {
      text = await file.text()
    } catch {
      continue
    }
    const refs = [...text.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)]
      .map((match) => String(match[1] || '').trim())
      .filter((url) => url && !/^(https?:|data:|\/\/)/i.test(url))
      .map((url) => url.split(/[?#]/)[0].replace(/\\/g, '/').split('/').pop() || '')
      .filter(Boolean)
    const missing = [...new Set(refs.filter((name) => !selectedImages.has(name)))]
    if (missing.length) result.push({ file, missing })
  }
  return result
}

/**
 * Markdown 里的图片是相对路径文本，浏览器上传时不会自动带同目录图片。
 * 批量上传前检查用户是否把被引用的图片也选进来了；漏选就明确提示，
 * 避免文档入库后才发现图片资产是 0。
 */
export async function ensureMarkdownImageFiles(files: File[]): Promise<boolean> {
  const missingGroups = await missingMarkdownImageFiles(files)
  if (!missingGroups.length) return true
  const lines = missingGroups.map(({ file, missing }) => `「${file.name}」缺少：${missing.join('、')}`)
  await ElMessageBox.alert(
    `${lines.join('\n')}\n\n请在文件选择窗口按住 Ctrl，把 Markdown 和这些图片一起选中后再上传。`,
    '图片没有一起选中',
    { confirmButtonText: '知道了', type: 'warning' }
  )
  return false
}

/**
 * 浏览器允许用户在「一次授权」后读取整个文档目录。这里只取缺失的图片，
 * 不会把整个目录当成资料上传；用于让「只选一个 .md」也尽量可用。
 */
export async function pickMissingImagesFromDirectory(names: string[]): Promise<File[]> {
  const picker = (window as any).showDirectoryPicker
  if (typeof picker !== 'function') return []
  const dir = await picker({ mode: 'read' })
  const wanted = new Set(names)
  const found: File[] = []

  const walk = async (handle: any) => {
    for await (const [, child] of handle.entries()) {
      if (child.kind === 'file') {
        const file = await child.getFile()
        if (wanted.has(file.name)) found.push(file)
      } else if (child.kind === 'directory') {
        await walk(child)
      }
    }
  }
  await walk(dir)
  return found
}
