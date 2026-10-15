/**
 * 题库分享工具
 */

/**
 * 由分享令牌构建分享落地页地址
 *
 * ⚠️ 本项目路由是 history 模式（createWebHistory），地址里**没有** `#`。
 * 之前拼成 `...#/front/share/xxx`，对方打开会落到首页而看不到领取页 —— 已修正。
 *
 * @param token 分享令牌
 * @returns 形如 http://host/front/share/<token> 的完整地址
 */
export function buildBankShareUrl(token: string): string {
  if (!token) return ''
  // BASE_URL 默认为 '/'，部署在子路径下也能正确拼接
  const base = import.meta.env.BASE_URL || '/'
  const prefix = base.endsWith('/') ? base : `${base}/`
  return `${window.location.origin}${prefix}front/share/${encodeURIComponent(token)}`
}

/** 复制文本到剪贴板 */
export function copyToClipboard(text: string): Promise<void> {
  if (!text) return Promise.reject(new Error('empty'))
  return navigator.clipboard.writeText(text)
}

/**
 * 解析用户粘贴/输入的「分享链接」或「分享码」，二者都支持
 *
 * - 完整链接：http://host/front/share/<token>
 * - 旧 hash 链接：http://host/#/front/share/<token>
 * - 纯分享码：ABC123
 *
 * @returns { token } 或 { code }；无法识别时返回 {}
 */
export function parseShareInput(raw: string): { token?: string; code?: string } {
  const text = (raw || '').trim()
  if (!text) return {}

  // 先尝试从链接里抠出 token（兼容 #/ 与不带 # 两种形式）
  const matched = text.match(/share\/([A-Za-z0-9_-]+)/)
  if (matched && matched[1]) {
    return { token: matched[1] }
  }

  // 是个 URL 但里面没有 share/<token>，说明不是有效的分享链接
  if (/^https?:\/\//i.test(text) || text.includes('/')) {
    return {}
  }

  // 否则按分享码处理（分享码为大写字母+数字）
  const code = text.toUpperCase()
  if (!/^[A-Z0-9]{4,12}$/.test(code)) {
    return {}
  }
  return { code }
}

/** 格式化时间（YYYY-MM-DD HH:mm） */
export function formatDateTime(timeStr?: string | null): string {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  if (Number.isNaN(d.getTime())) return timeStr
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
