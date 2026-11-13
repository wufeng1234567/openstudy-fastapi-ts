import { nextTick } from 'vue'

/**
 * 图谱视图开关与重置：节点偏移重置、实体类型显隐、隐藏孤立点、箭头、视角复位。
 *
 * 从 KnowledgeWikiPanel.vue 抽出。依赖以 ref / reactive / 函数形式从 options 传入，
 * 返回的 5 个函数保持原签名与名称，模板与脚本调用点无需改动。
 */
export function useWikiMapViewControls(options: {
  mapNodeOffsets: any
  mapSimPositions: any
  mapLearningPath: any
  mapTypeVisible: any
  mapHideUnlinked: any
  mapShowArrows: any
  mapImageExpanded: any
  stopMapAnimation: () => void
  startMapAnimation: () => void
  syncMapSize: () => void
  fitMapView: () => void
}) {
  const {
    mapNodeOffsets, mapSimPositions, mapLearningPath, mapTypeVisible,
    mapHideUnlinked, mapShowArrows, mapImageExpanded,
    stopMapAnimation, startMapAnimation, syncMapSize, fitMapView
  } = options

  function resetMapNodeOffsets() {
    Object.keys(mapNodeOffsets).forEach((key) => delete mapNodeOffsets[key])
    Object.keys(mapSimPositions).forEach((key) => delete mapSimPositions[key])
    mapLearningPath.value = []
    stopMapAnimation()
  }

  function toggleMapType(type: string) {
    mapTypeVisible[type] = mapTypeVisible[type] === false
    resetMapNodeOffsets()
    nextTick(startMapAnimation)
  }

  function toggleHideUnlinked() {
    mapHideUnlinked.value = !mapHideUnlinked.value
    resetMapNodeOffsets()
    nextTick(startMapAnimation)
  }

  function toggleMapArrows() {
    mapShowArrows.value = !mapShowArrows.value
  }

  function resetGraphView() {
    resetMapNodeOffsets()
    mapImageExpanded.value = false
    nextTick(() => {
      syncMapSize()
      fitMapView()
    })
  }

  return {
    resetMapNodeOffsets,
    toggleMapType,
    toggleHideUnlinked,
    toggleMapArrows,
    resetGraphView
  }
}
