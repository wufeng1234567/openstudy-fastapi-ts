/**
 * 类图导出功能 - 支持 SVG、PNG、JPG、Visio 四种格式
 */

import html2canvas from 'html2canvas'
import { saveAs } from 'file-saver'
import { generateVsdx } from '@/utils/vsdxGenerator'

/**
 * 导出为 SVG
 * 从 LogicFlow 画布中提取 SVG 并下载
 */
export function exportSvg(lf: any, filename: string = 'class-diagram.svg') {
  // 获取画布的 SVG 元素
  const container = lf.container
  const svgElement = container.querySelector('svg')
  if (!svgElement) return

  // 克隆 SVG 以避免修改原始元素
  const svgClone = svgElement.cloneNode(true) as SVGElement

  // 获取画布实际内容边界
  const graphData = lf.getGraphData()
  const nodes = graphData.nodes || []
  if (nodes.length === 0) return

  // 计算内容边界
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const node of nodes) {
    const x = node.x || 0
    const y = node.y || 0
    const w = node.width || 200
    const h = node.height || 150
    minX = Math.min(minX, x - w / 2)
    minY = Math.min(minY, y - h / 2)
    maxX = Math.max(maxX, x + w / 2)
    maxY = Math.max(maxY, y + h / 2)
  }

  const padding = 40
  const width = maxX - minX + padding * 2
  const height = maxY - minY + padding * 2

  svgClone.setAttribute('width', String(width))
  svgClone.setAttribute('height', String(height))
  svgClone.setAttribute('viewBox', `${minX - padding} ${minY - padding} ${width} ${height}`)

  // 添加白色背景
  const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  bgRect.setAttribute('x', String(minX - padding))
  bgRect.setAttribute('y', String(minY - padding))
  bgRect.setAttribute('width', String(width))
  bgRect.setAttribute('height', String(height))
  bgRect.setAttribute('fill', 'white')
  svgClone.insertBefore(bgRect, svgClone.firstChild)

  const svgString = new XMLSerializer().serializeToString(svgClone)
  const blob = new Blob([svgString], { type: 'image/svg+xml;charset=utf-8' })
  saveAs(blob, filename)
}

/**
 * 导出为 PNG（透明背景）
 */
export async function exportPng(container: HTMLElement, filename: string = 'class-diagram.png') {
  const canvas = await html2canvas(container, {
    backgroundColor: null,
    scale: 2,
    useCORS: true,
    logging: false
  })

  canvas.toBlob((blob) => {
    if (blob) saveAs(blob, filename)
  }, 'image/png')
}

/**
 * 导出为 JPG（白色背景，压缩）
 */
export async function exportJpg(container: HTMLElement, filename: string = 'class-diagram.jpg', quality: number = 0.9) {
  const canvas = await html2canvas(container, {
    backgroundColor: '#ffffff',
    scale: 2,
    useCORS: true,
    logging: false
  })

  canvas.toBlob((blob) => {
    if (blob) saveAs(blob, filename)
  }, 'image/jpeg', quality)
}

/**
 * 导出为 Visio (.vsdx)
 */
export async function exportVisx(classes: any[], relations: any[], filename: string = 'class-diagram.vsdx') {
  await generateVsdx(classes, relations, filename)
}

/**
 * 导出功能组合函数
 */
export function useDiagramExport() {
  return {
    exportSvg,
    exportPng,
    exportJpg,
    exportVisx
  }
}
