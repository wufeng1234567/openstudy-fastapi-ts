import { marked } from 'marked'
import DOMPurify from 'dompurify'

const ADD_TAGS = ['table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'pre']
const ADD_ATTR = ['colspan', 'rowspan', 'align', 'class']

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * 渲染结果缓存
 *
 * 症状：历史上下文很长时，悬浮助手「打开 / 拖拽边框」极卡。
 * 根因：模板里 `v-html="renderAgentMarkdown(msg.content)"` 是**内联调用**，
 *      每次重渲染（打开、resize、任意响应式变动）都会对**每一条**消息重跑
 *      `marked.parse + DOMPurify.sanitize`——几百条消息 × 每次都重解析，
 *      主线程被占满 → 掉帧。
 * 处理：按 `content` 缓存渲染结果。消息内容不变时命中缓存，重渲染几乎零成本。
 *      Map 插满后整体清空（简单够用；历史里重复内容很少，清空代价可接受）。
 */
const mdCache = new Map<string, string>()
const MD_CACHE_MAX = 800

export function renderAgentMarkdown(content: string): string {
  if (!content) return ''
  const cached = mdCache.get(content)
  if (cached !== undefined) return cached
  const html = _renderAgentMarkdownUncached(content)
  if (mdCache.size >= MD_CACHE_MAX) mdCache.clear()
  mdCache.set(content, html)
  return html
}

function _renderAgentMarkdownUncached(content: string): string {
  const toolJsonRegex = /([\s\S]*?)(tool_call|tool_result)[ \t]*\r?\n?\s*(\{[\s\S]*)/m
  const match = content.match(toolJsonRegex)

  if (match) {
    const textPart = match[1]
    const jsonPart = match[3]
    let html = ''
    if (textPart.trim()) {
      html += marked.parse(textPart) as string
    }
    html += `<div class="tool-json-block"><pre class="tool-json-content">${escapeHtml(jsonPart)}</pre></div>`
    return DOMPurify.sanitize(html, { ADD_TAGS, ADD_ATTR })
  }

  const html = marked.parse(content)
  return DOMPurify.sanitize(html as string, {
    ADD_TAGS: ['table', 'thead', 'tbody', 'tr', 'th', 'td'],
    ADD_ATTR: ['colspan', 'rowspan', 'align']
  })
}
