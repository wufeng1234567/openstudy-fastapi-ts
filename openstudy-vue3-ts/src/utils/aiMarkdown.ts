/**
 * AI 解析内容渲染工具
 * 分段输出：按标题行（📋【考点分析】等）拆分为独立段落展示
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { renderLatexSafe } from './latex'

marked.setOptions({
  breaks: true,
  gfm: true
})

const ADD_TAGS = ['table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'pre']
const ADD_ATTR = ['colspan', 'rowspan', 'align', 'class']

// 标题行：emoji + 空格? + 【标题】（也兼容无 emoji 直接【标题】）
const SEGMENT_HEADER_RE = /^(?:[📋💡✅📌⭐🧠🎯📊🔑❌📎✏️📚🔍❗️⚠️❣️]+\s*)?【[^】]+】/u

export interface AiSegment {
  title: string | null
  body: string
}

/**
 * 将 AI 解析内容按标题拆分为段落数组
 * 流式过程中最后一个段落会持续累积，天然支持增量渲染
 */
export function splitAiSegments(content: string): AiSegment[] {
  if (!content) return []
  const segments: AiSegment[] = []
  let current: AiSegment | null = null

  for (const line of content.split('\n')) {
    const trimmed = line.trim()
    if (trimmed && SEGMENT_HEADER_RE.test(trimmed)) {
      current = { title: trimmed, body: '' }
      segments.push(current)
    } else {
      if (!current) {
        current = { title: null, body: '' }
        segments.push(current)
      }
      current.body += line + '\n'
    }
  }

  return segments.map(s => ({ title: s.title, body: s.body.trim() }))
}

/**
 * 将单个段落的 Markdown 渲染为安全的 HTML（含 LaTeX 支持）
 */
export function renderAiMarkdown(content: string): string {
  if (!content) return ''

  // 预处理：特殊分隔线统一为 markdown 的 ---
  let processed = content.replace(/^[━─]{3,}$/gm, '---')

  let html = ''
  try {
    html = marked.parse(processed) as string
  } catch (e) {
    html = processed
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }

  // 后处理：增强特殊符号样式
  html = html.replace(/([🧠🎯📌📊✅❌💡🔑])/gu, '<span class="emoji-icon">$1</span>')
  html = html.replace(/⭐/g, '<span class="star">⭐</span>')
  html = html.replace(/(^|[\s>])#([a-zA-Z\u4e00-\u9fa5][\w\u4e00-\u9fa5-]*)/g,
    (match, prefix, tag) => `${prefix}<span class="tag">#${tag}</span>`)

  // 渲染 LaTeX 公式并做 XSS 防护
  return DOMPurify.sanitize(renderLatexSafe(html), { ADD_TAGS, ADD_ATTR })
}
