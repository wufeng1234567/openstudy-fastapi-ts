export function displayUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
}

export function kindLabel(kind: string) {
  return (
    {
      photo: '照片',
      diagram: '示意图',
      table: '表格',
      formula: '公式',
      screenshot: '截图',
      image: '图片'
    } as Record<string, string>
  )[kind] || '图片'
}

export function statusLabel(status: string) {
  return (
    {
      done: '已描述',
      pending: '待描述',
      processing: '生成中',
      failed: '失败'
    } as Record<string, string>
  )[status] || '待描述'
}
