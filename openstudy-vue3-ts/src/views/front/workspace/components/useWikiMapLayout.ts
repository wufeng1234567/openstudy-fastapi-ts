/** 知识图谱画布尺寸与视角适配。 */
export function useWikiMapLayout(options: {
  mapCanvasRef: any
  mapSize: any
  mapNodes: any
  mapView: any
  mapLayoutScale: any
  view: any
  mapReady: any
  saveMapViewCache: () => void
}) {
  const { mapCanvasRef, mapSize, mapNodes, mapView, mapLayoutScale, view, mapReady, saveMapViewCache } = options

function syncMapSize() {
  const element = mapCanvasRef.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  if (rect.width > 0) mapSize.width = Math.max(720, Math.round(rect.width))
  if (rect.height > 0) mapSize.height = Math.max(520, Math.round(rect.height))
}

function onMapResize() {
  if (view.value !== 'map' || !mapReady.value) return
  const element = mapCanvasRef.value
  if (!element) return
  const rect = element.getBoundingClientRect()
  if (rect.width <= 0 || rect.height <= 0) return
  // 浏览器显示/隐藏滚动条也会触发 window.resize，但不应改变图谱视角。
  // 只有窗口或侧栏发生真正的大幅变化时才重新布局并 fit。
  const widthChanged = Math.abs(rect.width - mapSize.width) >= 48
  const heightChanged = Math.abs(rect.height - mapSize.height) >= 48
  if (!widthChanged && !heightChanged) return
  syncMapSize()
  fitMapView()
}

watch(mapCanvasRef, (element) => {
  if (!element) return
  // 直接以图谱视图刷新时，组件首次渲染的 ref 可能比 onMounted 的 switchMap 更早出现；
  // 再等两帧量一次，确保默认 mapSize=1200×760 不会覆盖真实画布尺寸。
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (!mapCanvasRef.value) return
    syncMapSize()
    if (mapReady.value) fitMapView()
  }))
})

function fitMapView() {
  syncMapSize()
  const nodes = mapNodes.value
  if (!nodes.length) {
    mapView.x = 0
    mapView.y = 0
    mapView.scale = 1
    return
  }
  const xs = nodes.map((node: any) => Number(node.x))
  const ys = nodes.map((node: any) => Number(node.y))
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const padding = 64
  const panelReserve = Math.min(320, Math.max(220, mapSize.width * 0.12))
  const availableWidth = Math.max(640, mapSize.width - panelReserve)
  const maxFitScale = Math.max(1.1, Math.min(2.2, mapLayoutScale.value * 1.2))
  const scale = Math.min(
    maxFitScale,
    Math.max(
      // 组间距优先；空间不足时允许图谱略超出视口后拖拽/缩放，不把整张图缩成看不清的小点。
      0.75,
      Math.min(
        (availableWidth - padding * 2) / Math.max(180, maxX - minX + 120),
        (mapSize.height - padding * 2) / Math.max(180, maxY - minY + 120)
      )
    )
  )
  mapView.scale = scale
  mapView.x = availableWidth / 2 - ((minX + maxX) / 2) * scale
  mapView.y = mapSize.height / 2 - ((minY + maxY) / 2) * scale
  saveMapViewCache()
}



  return { syncMapSize, fitMapView, onMapResize }
}
