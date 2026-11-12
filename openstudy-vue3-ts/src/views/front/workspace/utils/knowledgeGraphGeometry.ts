export function clusterOutline(points: any[], padding = 28) {
  if (!points.length) return ''
  const cx = points.reduce((sum, point) => sum + Number(point.x || 0), 0) / points.length
  const cy = points.reduce((sum, point) => sum + Number(point.y || 0), 0) / points.length
  const samples = 48
  const radial: { x: number; y: number }[] = []
  for (let index = 0; index < samples; index += 1) {
    const angle = (index * Math.PI * 2) / samples
    let distance = 0
    for (const point of points) {
      const dx = Number(point.x || 0) - cx
      const dy = Number(point.y || 0) - cy
      const projected = Math.cos(angle) * dx + Math.sin(angle) * dy
      const radius = Number(point.r || 0) + padding
      distance = Math.max(distance, projected + radius)
    }
    distance = Math.max(40, distance)
    radial.push({
      x: cx + Math.cos(angle) * distance,
      y: cy + Math.sin(angle) * distance
    })
  }
  const fmt = (point: any) => `${Math.round(point.x * 10) / 10},${Math.round(point.y * 10) / 10}`
  const at = (index: number) => radial[(index + radial.length) % radial.length]
  const parts = [`M${fmt(radial[0])}`]
  for (let index = 0; index < radial.length; index += 1) {
    const current = at(index)
    const next = at(index + 1)
    const previous = at(index - 1)
    const after = at(index + 2)
    const control1 = {
      x: current.x + (next.x - previous.x) / 6,
      y: current.y + (next.y - previous.y) / 6
    }
    const control2 = {
      x: next.x - (after.x - current.x) / 6,
      y: next.y - (after.y - current.y) / 6
    }
    parts.push(`C${fmt(control1)} ${fmt(control2)} ${fmt(next)}`)
  }
  return parts.join(' ') + ' Z'
}
