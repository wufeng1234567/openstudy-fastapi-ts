// views/front/agent/chatAgentHelpers.ts
//
// Agent 会话页的**纯逻辑 / 展示判定 / 格式化**（从 `chat.vue` 抽出）。
//
//   · `mapToolLabels`        —— 工具名 → 中文名对照表
//   · `countAttachments`     —— 附件总数
//   · `flattenAttachments`   —— 图片 + 文件合成一份列表
//   · `hasFiles`             —— 这次拖拽里有没有文件
//   · `normalizeOutlineOffset` —— 大纲滚动偏移的合法化
//   · `normalizeHeroSuggestions` —— 首页推荐问句的形状归一
//
// ⚠ 依赖方向单向：`chat.vue` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠ **模板、会话 / 流式事件时序一个字节都没动** —— 这里只把「显示成什么样」
//    的判定挪到了可独立读、可独立测的地方；请求的发起顺序、SSE 事件的处理
//    顺序、附件的增删时机全部原样。
import { UploadFilled } from '@element-plus/icons-vue'

/** 工具名 → 中文名（界面对照；无则回落到 name 本身） */
export function mapToolLabels(
  options: Array<{ name: string; label?: string }>
): Record<string, string> {
  const m: Record<string, string> = {}
  for (const t of options || []) m[t.name] = t.label || t.name
  return m
}

/** 附件总数（图片 + 文件） */
export function countAttachments(attachments: {
  images: any[]
  files: any[]
}): number {
  return attachments.images.length + attachments.files.length
}

/** 图片 + 文件合成一份列表（上传器与列表组件共用一份） */
export function flattenAttachments(attachments: {
  images: any[]
  files: any[]
}): any[] {
  return [...attachments.images, ...attachments.files]
}

/**
 * 这次拖拽里有没有文件（拖文字 / 链接时不接管）
 *
 * ⚠️ types 在某些浏览器里拖文件时是 `['Files']`，拖文字时是 `['text/plain']`
 */
export function hasFiles(e: DragEvent): boolean {
  const t = e.dataTransfer
  if (!t) return false
  return Array.from(t.types || []).includes('Files')
}

/** 大纲滚动偏移的合法化：非有限数 / 非正数一律归零 */
export function normalizeOutlineOffset(off: any): number {
  return Number.isFinite(off) && off > 0 ? off : 0
}

/**
 * 首页推荐问句的形状归一
 *
 * ⚠️ `icons` 由调用方给（页面里那一组图标组件）—— 本模块不持有组件，
 *    免得同一组图标在两个地方各存一份。
 */
export function normalizeHeroSuggestions(
  list: any[] = [],
  icons: any[] = []
): any[] {
  return list.map((item, index) => ({
    ...item,
    label: item.label || item.text,
    icon: item.action === 'upload' ? UploadFilled : icons[index % icons.length]
  }))
}
