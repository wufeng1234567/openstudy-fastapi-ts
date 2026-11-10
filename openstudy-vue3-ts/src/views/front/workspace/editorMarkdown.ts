/**
 * 资料编辑器：Tiptap HTML ↔ Markdown 转换。
 *
 * 保留【图N】标记与 LaTeX 原子节点；从 workspace/index.vue 拆出。
 */

import { marked } from 'marked'
import TurndownService from 'turndown'

export function createTurndownService(): TurndownService {
  const service = new TurndownService({
    headingStyle: 'atx',
    bulletListMarker: '-',
    codeBlockStyle: 'fenced'
  })
  service.addRule('os-image-marker', {
    filter: (node: any) => node.nodeName === 'IMG' && !!node.getAttribute('data-os-image'),
    replacement: (_content: string, node: any) => `【图${node.getAttribute('data-os-image')}】`
  })
  service.addRule('os-math', {
    filter: (node: any) => node.nodeName === 'SPAN' && !!node.getAttribute('data-os-math'),
    replacement: (_content: string, node: any) => {
      try {
        return decodeURIComponent(node.getAttribute('data-os-math') || '')
      } catch {
        return node.textContent || ''
      }
    }
  })
  service.addRule('markdown-table', {
    filter: (node: any) => node.nodeName === 'TABLE',
    replacement: (_content: string, node: any) => {
      const rows = [...node.querySelectorAll('tr')].map((row: any) =>
        [...row.querySelectorAll('th,td')].map((cell: any) =>
          String(cell.textContent || '').replace(/\|/g, '\\|').replace(/\n+/g, ' ').trim()
        )
      )
      if (!rows.length) return ''
      const width = Math.max(...rows.map((row: string[]) => row.length))
      const normalized = rows.map((row: string[]) => {
        const padded = [...row]
        while (padded.length < width) padded.push('')
        return padded
      })
      const header = normalized[0]
      const body = normalized.slice(1)
      const lines = [
        `| ${header.join(' | ')} |`,
        `| ${header.map(() => '---').join(' | ')} |`,
        ...body.map((row: string[]) => `| ${row.join(' | ')} |`)
      ]
      return `\n\n${lines.join('\n')}\n\n`
    }
  })
  return service
}

export function markdownToEditorHtml(
  markdown: string,
  imageMap: Record<string, string>,
  resolveImageUrl: (url: string) => string
): string {
  const protectedMath = String(markdown || '').replace(
    /\$\$[\s\S]*?\$\$|\$[^$\n]+?\$/g,
    (formula) => `<span data-os-math="${encodeURIComponent(formula)}"></span>`
  )
  const withImages = protectedMath
    .replace(/【图(\d+)】/g, (_m, n) => {
      const url = imageMap[String(n)]
      return url ? `<img data-os-image="${n}" src="${resolveImageUrl(url)}" />` : `【图${n}】`
    })
    .replace(
      /!\[([^\]]*)\]\(([^)\s]+)\)/g,
      (_all, alt, url) =>
        `<img src="${String(url).replace(/"/g, '&quot;')}" alt="${String(alt).replace(/"/g, '&quot;')}" />`
    )
  try {
    return marked.parse(withImages, { gfm: true, breaks: true }) as string
  } catch {
    return `<p>${withImages.replace(/</g, '&lt;')}</p>`
  }
}

export function htmlToEditorMarkdown(service: TurndownService, html: string): string {
  return service.turndown(html || '').trim()
}
