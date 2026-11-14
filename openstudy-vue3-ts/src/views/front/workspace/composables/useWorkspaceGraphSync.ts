import { ref } from 'vue'
import { buildWikiIncremental } from '@/api/ai/workspace'

/**
 * 资料夹实体变更后的知识图谱增量同步。
 *
 * 上传/网页导入/题库关联/笔记导入都只负责“实体写入”，这里统一触发
 * `/rag/wiki/build/incremental`，避免每个入口各写一份同步逻辑。
 */
export function useWorkspaceGraphSync(options: {
  activeKbId: { value: number | null }
  wikiRefreshKey: { value: number }
}) {
  const graphSyncing = ref(false)
  let pendingTimer: ReturnType<typeof setTimeout> | null = null
  let refreshTimers: Array<ReturnType<typeof setTimeout>> = []
  let followupTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleGraphSync(delay = 600) {
    const kbId = Number(options.activeKbId.value || 0)
    if (!kbId) return
    if (pendingTimer) clearTimeout(pendingTimer)
    pendingTimer = setTimeout(() => {
      pendingTimer = null
      void runGraphSync()
    }, delay)
  }

  async function runGraphSync() {
    const kbId = Number(options.activeKbId.value || 0)
    if (!kbId || graphSyncing.value) return
    graphSyncing.value = true
    try {
      const res: any = await buildWikiIncremental({ kbId, limit: 30 })
      if (res.code !== 200) return
      // 任务在后台跑：先刷新一次让图谱显示新实体，再在任务完成后补刷。
      options.wikiRefreshKey.value += 1
      refreshTimers.forEach((timer) => clearTimeout(timer))
      refreshTimers = [2500, 8000].map((ms) =>
        setTimeout(() => {
          options.wikiRefreshKey.value += 1
        }, ms)
      )
      // 文档解析、图片描述是后台任务：稍后再扫一次来源状态，避免第一次扫描时内容还没就绪。
      if (followupTimer) clearTimeout(followupTimer)
      followupTimer = setTimeout(() => {
        followupTimer = null
        void runGraphSync()
      }, 12000)
    } catch (error) {
      console.warn('[workspace] 知识图谱增量同步失败', error)
    } finally {
      graphSyncing.value = false
    }
  }

  return { graphSyncing, scheduleGraphSync, runGraphSync }
}
