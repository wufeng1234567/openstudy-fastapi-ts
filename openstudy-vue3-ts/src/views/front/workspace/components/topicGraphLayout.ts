/**
 * 知识主题关系布局。
 *
 * 首层图谱只展示 topic 节点，来源节点（资料 / 网页 / 图片 / 题库 / 笔记）
 * 收进节点详情。这里用一次静态力导向计算主题节点位置：
 * - 有真实主题关系的节点受弹簧力拉近；
 * - 所有节点之间保留最小间距，避免节点和连线挤在一起；
 * - 少量迭代后统一缩放，适配当前画布。
 *
 * 不在每帧运行，避免几百个主题时拖拽/缩放掉帧。
 */
import { normalizeEntityKind } from '../utils/knowledgeGraphMeta'

const IDEAL_EDGE_DISTANCE = 170
const MIN_NODE_DISTANCE = 64
const REPULSION_RADIUS = 280
const ITERATIONS = 80

export function layoutTopicGraph(
  nodes: any[],
  edges: any[],
  width = 1200,
  height = 760
): any[] {
  const topics = nodes.filter(
    (node) => normalizeEntityKind(node.kind || node.pageType) === 'topic'
  )
  if (!topics.length) return []

  const ids = new Set(topics.map((node) => String(node.id)))
  const byId = new Map(topics.map((node) => [String(node.id), node]))
  const degree = new Map<string, number>()
  const links: Array<{ source: string; target: string }> = []
  for (const edge of edges || []) {
    const source = String(edge.source || '')
    const target = String(edge.target || '')
    if (!ids.has(source) || !ids.has(target) || source === target) continue
    links.push({ source, target })
    degree.set(source, (degree.get(source) || 0) + 1)
    degree.set(target, (degree.get(target) || 0) + 1)
  }

  // 初始网格：给力导向一个稳定、不重叠的起点。
  const cols = Math.max(1, Math.ceil(Math.sqrt(topics.length)))
  const rows = Math.max(1, Math.ceil(topics.length / cols))
  const cellW = Math.max(120, width / cols)
  const cellH = Math.max(100, height / rows)
  const positions = new Map<string, { x: number; y: number; vx: number; vy: number }>()
  topics.forEach((node, index) => {
    const col = index % cols
    const row = Math.floor(index / cols)
    positions.set(String(node.id), {
      x: (col + 0.5) * cellW,
      y: (row + 0.5) * cellH,
      vx: 0,
      vy: 0
    })
  })

  const centerX = (cols * cellW) / 2
  const centerY = (rows * cellH) / 2
  for (let iteration = 0; iteration < ITERATIONS; iteration += 1) {
    const alpha = 1 - iteration / ITERATIONS
    const entries = [...positions.entries()]

    // 节点间斥力：距离越近推力越大，保证不会叠在一起。
    for (let i = 0; i < entries.length; i += 1) {
      const [, a] = entries[i]!
      for (let j = i + 1; j < entries.length; j += 1) {
        const [, b] = entries[j]!
        let dx = b.x - a.x
        let dy = b.y - a.y
        let distance = Math.hypot(dx, dy)
        if (distance < 0.01) {
          dx = ((i + 1) % 7) + 0.5
          dy = ((j + 1) % 5) + 0.5
          distance = Math.hypot(dx, dy)
        }
        if (distance >= REPULSION_RADIUS) continue
        const force = ((REPULSION_RADIUS - distance) / REPULSION_RADIUS) * 3.4 * alpha
        const fx = (dx / distance) * force
        const fy = (dy / distance) * force
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy
      }
    }

    // 关系弹簧：真实相关的主题保持舒适距离，不被斥力推散。
    for (const link of links) {
      const source = positions.get(link.source)
      const target = positions.get(link.target)
      if (!source || !target) continue
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.hypot(dx, dy) || 1
      if (distance < MIN_NODE_DISTANCE) continue
      const force = (distance - IDEAL_EDGE_DISTANCE) * 0.012 * alpha
      const fx = (dx / distance) * force
      const fy = (dy / distance) * force
      source.vx += fx
      source.vy += fy
      target.vx -= fx
      target.vy -= fy
    }

    // 轻微向中心收拢，避免孤立组件飘到画布外。
    for (const [, item] of entries) {
      item.vx += (centerX - item.x) * 0.0008 * alpha
      item.vy += (centerY - item.y) * 0.0008 * alpha
      item.vx *= 0.72
      item.vy *= 0.72
      item.x += Math.max(-18, Math.min(18, item.vx))
      item.y += Math.max(-18, Math.min(18, item.vy))
    }
  }

  // 最后做几轮硬碰撞消解：节点圆点之间始终保留可点击/可读的空白，
  // 避免力导向参数偏差时出现“两个节点叠在一起”的情况。
  const entries = [...positions.entries()]
  for (let pass = 0; pass < 18; pass += 1) {
    for (let i = 0; i < entries.length; i += 1) {
      const [idA, a] = entries[i]!
      const nodeA = byId.get(idA)!
      for (let j = i + 1; j < entries.length; j += 1) {
        const [idB, b] = entries[j]!
        const nodeB = byId.get(idB)!
        const minDistance =
          Math.max(10, Number(nodeA.r || 10)) +
          Math.max(10, Number(nodeB.r || 10)) +
          34
        let dx = b.x - a.x
        let dy = b.y - a.y
        let distance = Math.hypot(dx, dy)
        if (distance >= minDistance) continue
        if (distance < 0.01) {
          dx = 1
          dy = 0.35
          distance = Math.hypot(dx, dy)
        }
        const push = (minDistance - distance) / 2
        const ux = dx / distance
        const uy = dy / distance
        a.x -= ux * push
        a.y -= uy * push
        b.x += ux * push
        b.y += uy * push
      }
    }
  }

  // 统一缩放到画布安全区，保留边距；不改变相对距离。
  const list = topics.map((node) => {
    const point = positions.get(String(node.id))!
    return { ...node, x: point.x, y: point.y }
  })
  const minX = Math.min(...list.map((node) => node.x))
  const maxX = Math.max(...list.map((node) => node.x))
  const minY = Math.min(...list.map((node) => node.y))
  const maxY = Math.max(...list.map((node) => node.y))
  const contentW = Math.max(1, maxX - minX)
  const contentH = Math.max(1, maxY - minY)
  const pad = 72
  // 保留可读尺寸：节点数量多时允许图谱超出视口，由拖拽/缩放查看，
  // 不把整张图压成看不清的小点。
  const scale = Math.min(
    1,
    Math.max(0.55, Math.min((width - pad * 2) / contentW, (height - pad * 2) / contentH))
  )
  const offsetX = (width - contentW * scale) / 2 - minX * scale
  const offsetY = (height - contentH * scale) / 2 - minY * scale
  return list.map((node) => ({
    ...node,
    x: node.x * scale + offsetX,
    y: node.y * scale + offsetY
  }))
}
