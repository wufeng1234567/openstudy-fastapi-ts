import { computed, ref } from 'vue'
import type { Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { searchWorkspaceCascade } from '@/api/ai/workspace'
import type { WorkspaceViewMode } from './useWorkspaceFilters'

/**
 * 资料空间的全库级联搜索。
 *
 * 从 `index.vue` 抽出；输入框只负责触发，搜索、清空和打开结果由这里维护。
 */
export function useWorkspaceCascade(options: {
  viewMode: Ref<WorkspaceViewMode>
  workspaceSearch: Ref<string>
  activeKbId: Ref<number | null>
  showAnatomy: (doc: any) => void
}) {
  const isCascadeMode = computed(
    () => (options.viewMode.value === 'list' || options.viewMode.value === 'shelf') && !!options.workspaceSearch.value.trim()
  )
  const cascadeLoading = ref(false)
  const cascadeResults = ref<any>({ query: '', totalFolders: 0, totalDocs: 0, folders: [] })
  let cascadeTimer: ReturnType<typeof setTimeout> | undefined

  function resetCascade() {
    cascadeResults.value = { query: '', totalFolders: 0, totalDocs: 0, folders: [] }
  }

  async function runCascade() {
    const query = options.workspaceSearch.value.trim()
    if (!query || !isCascadeMode.value) {
      resetCascade()
      return
    }
    cascadeLoading.value = true
    try {
      const res = await searchWorkspaceCascade(query, 50, 20)
      if (res.code === 200) {
        cascadeResults.value = res.data || { query, totalFolders: 0, totalDocs: 0, folders: [] }
      } else {
        ElMessage.error(res.msg || '搜索失败')
      }
    } catch (error: any) {
      ElMessage.error('搜索失败：' + (error?.message || error))
    } finally {
      cascadeLoading.value = false
    }
  }

  function scheduleCascade() {
    window.clearTimeout(cascadeTimer)
    if (!isCascadeMode.value) {
      resetCascade()
      return
    }
    cascadeTimer = window.setTimeout(runCascade, 240)
  }

  function openCascadeFolder(folder: any) {
    if (!folder?.kbId) return
    options.activeKbId.value = Number(folder.kbId)
    options.workspaceSearch.value = ''
    options.viewMode.value = 'list'
  }

  function openCascadeDocument(doc: any) {
    if (!doc?.docId) return
    options.showAnatomy({ docId: Number(doc.docId), fileName: doc.fileName || '未命名资料' })
  }

  return {
    isCascadeMode,
    cascadeLoading,
    cascadeResults,
    resetCascade,
    runCascade,
    scheduleCascade,
    openCascadeFolder,
    openCascadeDocument
  }
}
