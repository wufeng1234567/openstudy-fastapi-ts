/** 资料夹页面的画廊/图谱导航动作（从 index.vue 抽离）。 */

import { ElMessage } from 'element-plus'
import { nextTick } from 'vue'
import type { ComputedRef, Ref } from 'vue'
import type { Router } from 'vue-router'

export function useWorkspaceNavigation(options: {
  kbs: Ref<any[]>
  activeKb: ComputedRef<any>
  openQuestionPicker: (img: any) => void
  openNotePicker: (img: any) => void
  showAnatomy: (doc: any, opts?: any) => void
  showHealth: (doc: any) => void
  router: Router
  galleryStats: { total: number }
  mapStats: { total: number }
  viewMode: Ref<string>
  workspaceSearch: Ref<string>
  wikiSearchSubmitKey: Ref<number>
}) {
  function findDocRecord(docId: number) {
    for (const kb of options.kbs.value) {
      const found = (kb.files || []).find((doc: any) => Number(doc.docId) === Number(docId))
      if (found) return found
    }
    return (options.activeKb.value?.files || []).find((doc: any) => Number(doc.docId) === Number(docId)) || null
  }

  function onGalleryUseImage(img: any) {
    if (!img) return
    if (img.target === 'question') options.openQuestionPicker(img)
    else options.openNotePicker(img)
  }

  function onGalleryLocate(payload: { docId: number; offset: number; targetText?: string }) {
    const doc = findDocRecord(payload.docId)
    if (!doc) {
      ElMessage.warning('没有找到这张图对应的资料，可能已经被移动或删除')
      return
    }
    options.showAnatomy(doc, { offset: payload.offset, targetText: payload.targetText || '' })
  }

  function onMapOpenDoc(payload: { docId: number; offset?: number; targetText?: string }) {
    const doc = findDocRecord(payload.docId)
    if (!doc) {
      ElMessage.warning('没有找到这份资料，可能已经被移动或删除')
      return
    }
    if (payload.offset != null) {
      options.showAnatomy(doc, { offset: payload.offset, targetText: payload.targetText || '' })
    } else {
      options.showHealth(doc)
    }
  }

  function onGraphLocate(payload: { docId: number; chunkId?: number; chunkIndex?: number }) {
    const doc = findDocRecord(payload.docId)
    if (!doc) {
      ElMessage.warning('没有找到这条证据对应的资料，可能已经被移动或删除')
      return
    }
    options.showAnatomy(doc, {
      chunkId: payload.chunkId,
      chunkIndex: payload.chunkIndex,
      targetText: ''
    })
  }

  function onWikiAsk(prompt: string) {
    const text = String(prompt || '').trim()
    if (!text) return
    options.router.push({ path: '/front/agent/chat', state: { seedQuestion: text } })
  }

  function onGalleryStats(payload: { total?: number }) {
    options.galleryStats.total = Number(payload?.total || 0)
  }

  function onMapStats(payload: { total?: number }) {
    options.mapStats.total = Number(payload?.total || 0)
  }

  function onWorkspaceSearchEnter() {
    if (options.viewMode.value === 'wiki') options.wikiSearchSubmitKey.value += 1
  }

  function onWikiSearchSelected() {
    options.workspaceSearch.value = ''
    nextTick(() => {
      const input = document.querySelector<HTMLInputElement>('.kbp-global-search input')
      input?.blur()
    })
  }

  return {
    findDocRecord,
    onGalleryUseImage,
    onGalleryLocate,
    onMapOpenDoc,
    onGraphLocate,
    onWikiAsk,
    onGalleryStats,
    onMapStats,
    onWorkspaceSearchEnter,
    onWikiSearchSelected
  }
}
