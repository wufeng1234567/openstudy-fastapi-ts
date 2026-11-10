/**
 * 资料夹页面纯展示/轮询辅助函数。
 *
 * 从 `index.vue` 拆出，减少巨型 SFC；这些函数不依赖组件状态。
 */

export type WorkspaceView = 'list' | 'shelf' | 'gallery' | 'wiki'

export const WORKSPACE_VIEWS: WorkspaceView[] = ['list', 'shelf', 'gallery', 'wiki']

export function readWorkspaceView(fromQuery: string, storageKey: string): WorkspaceView {
  if ((WORKSPACE_VIEWS as readonly string[]).includes(fromQuery)) {
    return fromQuery as WorkspaceView
  }
  try {
    const saved = localStorage.getItem(storageKey) || ''
    if ((WORKSPACE_VIEWS as readonly string[]).includes(saved)) {
      return saved as WorkspaceView
    }
  } catch {
    // localStorage 不可用时退回默认资料夹
  }
  return 'list'
}

export function documentTypeKey(doc: any): string {
  const ext =
    String(doc?.fileType || doc?.fileName || '')
      .toLowerCase()
      .match(/\.([a-z0-9]+)$/)?.[1] || String(doc?.fileType || '').toLowerCase()
  if (['doc', 'docx'].includes(ext)) return 'word'
  if (['ppt', 'pptx'].includes(ext)) return 'ppt'
  if (['md', 'markdown', 'txt'].includes(ext)) return 'text'
  if (['pdf'].includes(ext)) return 'pdf'
  if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'].includes(ext)) return 'image'
  return 'other'
}

export function documentStatusKey(doc: any): string {
  if (Number(doc?.disabled) === 1) return 'blocked'
  if (Number(doc?.status) === 4) return 'failed'
  if (Number(doc?.status) === 5) return 'ready'
  return 'processing'
}

export function facetText(facets: any): string {
  if (!facets || typeof facets !== 'object') return '—'
  const parts = []
  if (facets.wordCount) parts.push(`${facets.wordCount} 字`)
  if (facets.formulaCount) parts.push(`${facets.formulaCount} 公式`)
  if (facets.imageCount) parts.push(`${facets.imageCount} 图片`)
  if (facets.tableCount) parts.push(`${facets.tableCount} 表格`)
  return parts.length ? parts.join(' / ') : '—'
}

export function reprocessPercent(status: number): number {
  if (status === 1) return 10
  if (status === 2) return 32
  if (status === 3) return 68
  if (status === 5) return 100
  return 0
}

export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
