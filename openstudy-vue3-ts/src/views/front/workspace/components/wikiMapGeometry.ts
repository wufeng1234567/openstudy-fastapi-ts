// views/front/workspace/components/wikiMapGeometry.ts
//
// 知识图谱的**几何与力学计算**（从 `KnowledgeWikiPanel.vue` 抽出）。
//
// 这里全是「给一组数据 → 算出坐标 / 力 / 选哪些」的**纯计算**：
//   · `buildMapEdge` —— 一条边的起止坐标（沿方向向量留出节点半径的间隙）
//   · `pickNonOverlappingLabelIds` —— 标签避让（挑出互不重叠的那些）
//   · `computeRepulsion` —— 节点之间的斥力
//   · `computeSpringForces` —— 边两端的引力
//   · `integrateNodes` —— 阻尼 / 限速 / 位置夹取
//   · `computeWheelZoom` —— 滚轮缩放（以指针为锚点）
//
// ⚠ 本模块**零 import** —— 不依赖 Vue、不依赖组件里的任何状态，
//    因此不可能形成循环依赖。
//
// ⚠ **时序不变**：调用顺序、每帧的迭代次数、阻尼与限速系数、坐标夹取范围
//    全部逐字照搬 —— 拖拽 / 缩放 / 力导向动画的手感不会因为这次搬家有任何变化。

/**
 * 一条边的起止坐标
 *
 * ⚠️ 起点沿「源 → 目标」方向**外推** `source.r + 5`，终点**内推** `target.r + 7`，
 *    这样线段不会插进节点圆里（两端的间隙不一样是原实现的口径，别改成一致）。
 */
export function buildMapEdge(
  source: any,
  target: any,
  sourceId: string,
  targetId: string,
  edge: any,
  isCross: (edge: any) => boolean
): any {
  const dx = target.x - source.x
  const dy = target.y - source.y
  const distance = Math.hypot(dx, dy) || 1
  const ux = dx / distance
  const uy = dy / distance
  const startPad = Number(source.r || 5) + 5
  const endPad = Number(target.r || 5) + 7
  return {
    key: `${sourceId}-${targetId}-${edge.type}`,
    source: sourceId,
    target: targetId,
    x1: source.x + ux * startPad,
    y1: source.y + uy * startPad,
    x2: target.x - ux * endPad,
    y2: target.y - uy * endPad,
    type: edge.type || 'related',
    label: edge.label || edge.type || '关系',
    cross: isCross(edge)
  }
}

/**
 * 标签避让：按顺序挑出**互不重叠**的那些节点的 id
 *
 * ⚠️ 判定用的是**屏幕坐标**（节点坐标 × 缩放 + 平移），不是图谱坐标 ——
 *    缩放得越小，屏幕上挤在一起的节点越多，能显示的标签就越少。
 */
export function pickNonOverlappingLabelIds(
  candidates: any[],
  getTitle: (node: any) => string,
  scale: number,
  viewX: number,
  viewY: number,
  maxLabels = Number.POSITIVE_INFINITY
): Set<string> {
  const result = new Set<string>()
  const occupied: Array<{ left: number; right: number; top: number; bottom: number }> = []
  const fontSize = Math.min(14, 11 / Math.max(0.8, Number(scale) || 1))
  for (const node of candidates) {
    if (result.size >= maxLabels) break
    const title = getTitle(node)
    if (!title) continue
    const screenX = Number(node.x) * Number(scale) + Number(viewX)
    const screenY = Number(node.y) * Number(scale) + Number(viewY) + Number(node.r) + 14
    // 中文按字号估算，额外留 8px 横向间隙；之前固定 11px 会低估放大后的标签宽度。
    const width = Math.max(34, title.length * fontSize + 8)
    const height = Math.max(16, fontSize * 1.3)
    const box = { left: screenX - width / 2, right: screenX + width / 2, top: screenY - height + 4, bottom: screenY + 4 }
    const overlaps = occupied.some((item) => !(box.right < item.left || box.left > item.right || box.bottom < item.top || box.top > item.bottom))
    if (overlaps) continue
    occupied.push(box)
    result.add(String(node.id))
  }
  return result
}

/** 节点之间的斥力（按距离平方衰减）—— 就地改 `vx` / `vy` */
export function computeRepulsion(nodes: any[], alpha: number): void {
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]!
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j]!
      const dx = b.x - a.x
      const dy = b.y - a.y
      const distance = Math.hypot(dx, dy) || 1
      const force = (12000 * alpha) / Math.max(distance * distance, 100)
      const fx = (dx / distance) * force
      const fy = (dy / distance) * force
      a.vx -= fx
      a.vy -= fy
      b.vx += fx
      b.vy += fy
    }
  }
}

/** 边两端的引力（按目标距离 140 收缩 / 拉开）—— 就地改 `vx` / `vy` */
export function computeSpringForces(edges: any[], byId: Map<string, any>, alpha: number): void {
  for (const edge of edges) {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) continue
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.hypot(dx, dy) || 1
    const degree = Math.max(1, Math.sqrt(Math.max(1, (source.degree || 0) + (target.degree || 0))))
    const force = ((distance - 140) * 0.003 * alpha) / degree
    const fx = (dx / distance) * force
    const fy = (dy / distance) * force
    source.vx += fx
    source.vy += fy
    target.vx -= fx
    target.vy -= fy
  }
}

/**
 * 积分一步：阻尼 → 限速 → 位置夹取 → 写回位置表
 *
 * ⚠️ 限速 20、夹取范围 x∈[40,960] / y∈[40,600] 都是原实现的口径，逐字照搬。
 */
export function integrateNodes(nodes: any[], positions: Record<string, any>): void {
  for (const node of nodes) {
    node.vx *= 0.6
    node.vy *= 0.6
    const speed = Math.hypot(node.vx, node.vy)
    if (speed > 20) {
      node.vx *= 20 / speed
      node.vy *= 20 / speed
    }
    node.x = Math.max(40, Math.min(960, node.x + node.vx))
    node.y = Math.max(40, Math.min(600, node.y + node.vy))
    positions[node.id] = { x: node.x, y: node.y }
  }
}

/**
 * 滚轮缩放：**以指针位置为锚点**（指针下的图谱内容保持在指针下）
 *
 * ⚠️ 缩放区间 [0.35, 3]、每格 1.12 倍是原实现的口径，逐字照搬。
 */
export function computeWheelZoom(
  current: { x: number; y: number; scale: number },
  px: number,
  py: number,
  deltaY: number
): { x: number; y: number; scale: number } {
  const old = current.scale
  const next = Math.max(0.35, Math.min(3, old * (deltaY < 0 ? 1.12 : 1 / 1.12)))
  const wx = (px - current.x) / old
  const wy = (py - current.y) / old
  return { x: px - wx * next, y: py - wy * next, scale: next }
}
