import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getDocumentStatus, reprocessDocument } from '@/api/ai/rag'
import { delay } from '../utils/helpers'
import { reprocessPercent } from '../utils/helpers'

/** 文档重新解析/向量化的后台任务。 */
export function useWorkspaceReprocess(options: { load: () => Promise<void> }) {
  const reprocessTask = reactive({
    active: false,
    docId: 0,
    fileName: '',
    statusText: '',
    percent: 0,
    error: ''
  })
  const reprocessElapsed = ref(0)
  let reprocessTimer: ReturnType<typeof setInterval> | null = null

  function stopReprocessClock() {
    if (reprocessTimer) {
      clearInterval(reprocessTimer)
      reprocessTimer = null
    }
  }

  async function pollReprocess(docId: number): Promise<{ ok: boolean; message: string; chunkCount?: number }> {
    for (let i = 0; i < 150; i++) {
      await delay(1200)
      try {
        const res: any = await getDocumentStatus(docId)
        if (res.code !== 200 || !res.data) continue
        const data = res.data
        const status = Number(data.status || 1)
        reprocessTask.statusText = data.statusText || '整理中…'
        reprocessTask.percent = reprocessPercent(status)
        if (status === 5) return { ok: true, message: '已完成', chunkCount: Number(data.chunkCount || 0) }
        if (status === 4) return { ok: false, message: data.errorMsg || '解析或向量化失败' }
      } catch {
        // 单次轮询失败不打断，继续等下一个周期。
      }
    }
    return { ok: false, message: '等待超时，任务可能仍在后台运行，可稍后刷新查看' }
  }

  async function reprocess(doc: any) {
    if (reprocessTask.active) {
      if (reprocessTask.docId === doc.docId) ElMessage.info('这份资料正在重新解析，请稍候')
      else ElMessage.warning('还有一份资料正在重新解析，等它完成后再试')
      return
    }
    if (Number(doc.status) === 2) {
      ElMessage.info('这份资料正在解析/向量化中，请等状态变成「可检索」后再重新解析')
      return
    }
    try {
      const { ElMessageBox } = await import('element-plus')
      await ElMessageBox.confirm(
        `重新解析「${doc.fileName}」会重新切分并向量化这段资料，期间检索可能暂时不完整。`,
        '重新解析并向量化',
        { confirmButtonText: '开始重新解析', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    reprocessTask.active = true
    reprocessTask.docId = doc.docId
    reprocessTask.fileName = doc.fileName
    reprocessTask.statusText = '正在提交任务…'
    reprocessTask.percent = 4
    reprocessTask.error = ''
    reprocessElapsed.value = 0
    stopReprocessClock()
    reprocessTimer = setInterval(() => { reprocessElapsed.value += 1 }, 1000)
    try {
      const res: any = await reprocessDocument(doc.docId)
      if (res.code !== 200) {
        reprocessTask.active = false
        stopReprocessClock()
        ElMessage.error(res.msg || '重新处理失败')
        return
      }
      reprocessTask.statusText = res.data?.statusText || '已加入队列，等待解析…'
      reprocessTask.percent = 10
      await options.load()
      const result = await pollReprocess(doc.docId)
      reprocessTask.active = false
      stopReprocessClock()
      await options.load()
      if (result.ok) {
        ElMessage.success(`「${doc.fileName}」已重新解析并完成向量化${result.chunkCount ? `，共 ${result.chunkCount} 个分块` : ''}`)
      } else {
        ElMessage.error(`「${doc.fileName}」重新解析失败：${result.message}`)
      }
    } catch (e: any) {
      reprocessTask.active = false
      stopReprocessClock()
      ElMessage.error('重新处理失败：' + (e?.message || e))
    }
  }

  async function runReindex(doc: any, statusText: string): Promise<{ ok: boolean; message: string; chunkCount?: number }> {
    reprocessTask.active = true
    reprocessTask.docId = doc.docId
    reprocessTask.fileName = doc.fileName
    reprocessTask.statusText = statusText
    reprocessTask.percent = 10
    reprocessTask.error = ''
    reprocessElapsed.value = 0
    stopReprocessClock()
    reprocessTimer = setInterval(() => { reprocessElapsed.value += 1 }, 1000)
    await options.load()
    const result = await pollReprocess(doc.docId)
    reprocessTask.active = false
    stopReprocessClock()
    await options.load()
    return result
  }

  return {
    reprocessTask,
    reprocessElapsed,
    stopReprocessClock,
    pollReprocess,
    reprocess,
    runReindex
  }
}
