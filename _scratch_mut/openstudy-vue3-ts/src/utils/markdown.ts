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
 * Agent 专用 markdown 渲染
 * 检测 tool_call / tool_result 原始 JSON 块，用流式输出容器渲染
 */
export function renderAgentMarkdown(content: string): string {
  if (!content) return ''

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
