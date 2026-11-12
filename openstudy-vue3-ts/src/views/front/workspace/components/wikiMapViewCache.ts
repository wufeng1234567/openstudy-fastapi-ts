/** 知识图谱视角缓存：按资料夹和画布尺寸恢复上次缩放/平移。 */
export function useWikiMapViewCache(options: {
  activeKbId: any
  mapSize: any
  mapGraph: any
  mapView: any
}) {
  const { activeKbId, mapSize, mapGraph, mapView } = options
  const MAP_VIEW_CACHE_PREFIX = 'openstudy_wiki_map_view:v3:'

function mapViewCacheKey() {
  return `${MAP_VIEW_CACHE_PREFIX}${Number(props.activeKbId || 0)}`
}

function readMapViewCache() {
  try {
    const raw = sessionStorage.getItem(mapViewCacheKey())
    if (!raw) return null
    const cached = JSON.parse(raw)
    if (
      Math.abs(Number(cached.width) - mapSize.width) > 1 ||
      Math.abs(Number(cached.height) - mapSize.height) > 1 ||
      Number(cached.nodes) !== Number(mapGraph.value.nodes?.length || 0)
    ) return null
    return cached
  } catch {
    return null
  }
}

function saveMapViewCache() {
  try {
    sessionStorage.setItem(mapViewCacheKey(), JSON.stringify({
      width: mapSize.width,
      height: mapSize.height,
      nodes: Number(mapGraph.value.nodes?.length || 0),
      x: Number(mapView.x),
      y: Number(mapView.y),
      scale: Number(mapView.scale)
    }))
  } catch {
    // sessionStorage 不可用时忽略，不影响图谱使用。
  }
}



  return { mapViewCacheKey, readMapViewCache, saveMapViewCache }
}
