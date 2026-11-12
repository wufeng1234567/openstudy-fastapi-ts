import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  applyWorkspaceOrganize,
  deleteWorkspaceOrganizeRecord,
  getWorkspaceOrganizePlan,
  getWorkspaceOrganizeRecord,
  listWorkspaceOrganizePlans,
  previewWorkspaceOrganize,
  rollbackWorkspacePlan
} from '@/api/ai/workspace'
import { computeOrganizeReport, countOrganizePlans } from './organizeHelpers'

/** 单文档智能整理：预览、轮询、应用、回退和整理记录。 */
export function useWorkspaceOrganize(options: {
  activeKb: { value: any }
  load: () => Promise<void>
  uploadTip: { value: string }
  runReindex: (doc: any, statusText: string) => Promise<{ ok: boolean; message: string; chunkCount?: number }>
  showHealth: (doc: any) => void
}) {
  const organizeReportVisible = ref(false)
  const organizePlansLoading = ref(false)
  const organizePlans = ref<any[]>([])
  const organizeVisible = ref(false)
  const organizeMode = ref<'quick' | 'deep'>('deep')
  const organizeStatus = ref('starting')
  const organizeStage = ref('starting')
  const organizeProgress = ref(0)
  const organizeElapsed = ref(0)
  const organizeError = ref('')
  const organizeApplied = ref(false)
  const organizeRecordView = ref(false)
  const organizePlanId = ref<number | null>(null)
  const organizeChanges = ref<any[]>([])
  const organizeSuggestions = ref<any[]>([])
  const organizeDocTarget = ref<any>(null)
  const organizeTask = reactive({ active: false, docId: 0, fileName: '', statusText: '', percent: 0 })
  const deepOrganizeOptions = reactive({
    structure: true,
    imageLinking: true,
    duplicateDetection: true,
    cleanupSuggestions: true
  })

  let organizeClock: ReturnType<typeof setInterval> | null = null
  let organizePoll: ReturnType<typeof setTimeout> | null = null
  let organizeStartedAt = 0

  const organizeReport = computed(() => computeOrganizeReport(organizePlans.value))

  async function refreshOrganizePlans(silent = false) {
    if (!silent) organizePlansLoading.value = true
    try {
      const res: any = await listWorkspaceOrganizePlans(40)
      organizePlans.value = res.code === 200 ? (res.data || []) : []
    } catch (e: any) {
      if (!silent) ElMessage.error('读取整理记录失败：' + (e?.message || e))
    } finally {
      if (!silent) organizePlansLoading.value = false
    }
  }

  async function openOrganizeReport() {
    organizeReportVisible.value = true
    await refreshOrganizePlans()
  }

  async function deleteOrganizeRecord(plan: any) {
    try {
      await ElMessageBox.confirm(
        `删除「${plan.docName}」的这条整理记录？只删除记录，不会回退已经应用的文档变更。`,
        '删除整理记录',
        { confirmButtonText: '删除记录', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    try {
      const res: any = await deleteWorkspaceOrganizeRecord(Number(plan.planId))
      if (res.code !== 200) {
        ElMessage.error(res.msg || '删除失败')
        return
      }
      ElMessage.success('整理记录已删除')
      await openOrganizeReport()
    } catch (e: any) {
      ElMessage.error('删除失败：' + (e?.message || e))
    }
  }

  function organizePlanCount(status: string) {
    return countOrganizePlans(organizePlans.value, status)
  }

  async function openOrganizePlan(plan: any) {
    try {
      const res: any = plan.legacy
        ? await getWorkspaceOrganizeRecord(Number(plan.planId))
        : await getWorkspaceOrganizePlan(plan.planId)
      if (res.code !== 200) {
        ElMessage.error(res.msg || '读取整理计划失败')
        return
      }
      const data = res.data || {}
      organizeReportVisible.value = false
      organizeVisible.value = true
      organizeRecordView.value = true
      organizeMode.value = data.mode === 'deep' ? 'deep' : 'quick'
      organizeApplied.value = data.status === 'applied' && !plan.legacy
      organizeError.value = data.error || ''
      organizePlanId.value = data.planId || plan.planId
      organizeStatus.value = data.status || plan.status
      organizeStage.value = data.stage || plan.stage || 'done'
      organizeProgress.value = Number(data.progress || 100)
      let visibleChanges = data.changes || []
      let visibleSuggestions = data.suggestions || []
      if (data.status === 'applied' && Array.isArray(data.appliedChangeIds)) {
        const appliedIds = new Set(data.appliedChangeIds)
        visibleChanges = visibleChanges.filter((change: any) => appliedIds.has(change.id) || change.field === 'facets')
        const appliedExclusionIds = new Set(data.appliedExclusionIds || [])
        visibleSuggestions = visibleSuggestions.filter((suggestion: any) => appliedExclusionIds.has(suggestion.id))
      }
      organizeChanges.value = visibleChanges
      organizeSuggestions.value = visibleSuggestions
      organizeElapsed.value = 0
      organizeDocTarget.value =
        options.activeKb.value?.files.find((d: any) => Number(d.docId) === Number(data.docId)) || null
    } catch (e: any) {
      ElMessage.error('读取整理计划失败：' + (e?.message || e))
    }
  }

  function startOrganize(doc: any) {
    if (!doc?.docId) return
    ElMessageBox.confirm(
      `智能整理会分析「${doc.fileName}」的正文、章节和图片，生成预览方案。\n不会自动修改正文，只有你确认后才应用。`,
      '开始智能整理',
      { confirmButtonText: '开始分析', cancelButtonText: '取消', type: 'info' }
    )
      .then(() => {
        organizeDocTarget.value = doc
        organizeMode.value = 'deep'
        beginOrganize(doc, 'deep')
      })
      .catch(() => {})
  }

  function startOrganizeClock() {
    stopOrganizeClock()
    organizeStartedAt = Date.now()
    organizeElapsed.value = 0
    organizeClock = setInterval(() => {
      organizeElapsed.value = (Date.now() - organizeStartedAt) / 1000
    }, 300)
  }

  function stopOrganizeClock() {
    if (organizeClock) {
      clearInterval(organizeClock)
      organizeClock = null
    }
    if (organizePoll) {
      clearTimeout(organizePoll)
      organizePoll = null
    }
  }

  function applyPlanPayload(data: any) {
    organizePlanId.value = Number(data.planId || 0) || null
    organizeStatus.value = data.status || 'running'
    organizeStage.value = data.stage || 'starting'
    organizeProgress.value = Number(data.progress || 0)
    organizeChanges.value = data.changes || []
    organizeSuggestions.value = data.suggestions || []
    organizeError.value = data.error || ''
    if (organizeTask.active) {
      organizeTask.statusText = data.stage === 'failed' ? '整理失败' : '正在分析文档'
      organizeTask.percent = Math.max(4, Number(data.progress || organizeTask.percent || 4))
    }
  }

  async function beginOrganize(doc: any, mode: 'deep') {
    stopOrganizeClock()
    organizeVisible.value = true
    organizeMode.value = 'deep'
    organizeStatus.value = 'starting'
    organizeStage.value = 'starting'
    organizeProgress.value = 0
    organizeChanges.value = []
    organizeSuggestions.value = []
    organizeError.value = ''
    organizeApplied.value = false
    organizeRecordView.value = false
    organizePlanId.value = null
    organizeTask.active = true
    organizeTask.docId = doc.docId
    organizeTask.fileName = doc.fileName
    organizeTask.statusText = '正在提交整理任务…'
    organizeTask.percent = 4
    startOrganizeClock()
    try {
      const res: any = await previewWorkspaceOrganize({ docId: doc.docId, mode, options: { ...deepOrganizeOptions } })
      if (res.code !== 200) {
        organizeStatus.value = 'failed'
        organizeError.value = res.msg || '整理失败'
        organizeTask.active = false
        stopOrganizeClock()
        return
      }
      applyPlanPayload(res.data || {})
      if (organizeStatus.value === 'ready') {
        organizeTask.active = false
        stopOrganizeClock()
        return
      }
      pollOrganizePlan()
    } catch (e: any) {
      organizeStatus.value = 'failed'
      organizeError.value = e?.message || String(e)
      organizeTask.active = false
      stopOrganizeClock()
    }
  }

  async function pollOrganizePlan() {
    const planId = organizePlanId.value
    if (!planId) return
    try {
      const res: any = await getWorkspaceOrganizePlan(planId)
      if (res.code !== 200) {
        organizeStatus.value = 'failed'
        organizeError.value = res.msg || '读取整理计划失败'
        stopOrganizeClock()
        return
      }
      applyPlanPayload(res.data || {})
      if (organizeStatus.value === 'ready' || organizeStatus.value === 'failed') {
        organizeTask.active = false
        stopOrganizeClock()
        return
      }
      organizePoll = setTimeout(pollOrganizePlan, 600)
    } catch (e: any) {
      organizeStatus.value = 'failed'
      organizeError.value = e?.message || String(e)
      organizeTask.active = false
      stopOrganizeClock()
    }
  }

  async function applyOrganizePreview(changeIds: string[], exclusionIds: string[]) {
    if (!organizePlanId.value) return
    try {
      const res: any = await applyWorkspaceOrganize({ planId: organizePlanId.value, changeIds, exclusionIds })
      if (res.code !== 200) {
        ElMessage.error(res.msg || '应用整理失败')
        return
      }
      organizeApplied.value = true
      organizeStatus.value = 'applied'
      organizeTask.active = false
      options.uploadTip.value = ''
      await options.load()
      if (res.data?.needsReindex && organizeDocTarget.value?.docId) {
        const result = await options.runReindex(organizeDocTarget.value, '整理已应用，正在重新建立索引…')
        ElMessage.success(result.ok ? '整理已应用，索引已重建完成' : '整理已应用，但索引重建失败：' + result.message)
      } else {
        ElMessage.success('整理已应用')
      }
    } catch (e: any) {
      ElMessage.error('应用整理失败：' + (e?.message || e))
    }
  }

  function freshOrganizeDoc(): any {
    const target = organizeDocTarget.value
    if (!target?.docId) return null
    return options.activeKb.value?.files.find((d: any) => Number(d.docId) === Number(target.docId)) || target
  }

  function rerunOrganize() {
    const doc = freshOrganizeDoc()
    if (doc) beginOrganize(doc, 'deep')
  }

  function recheckOrganize() {
    const doc = freshOrganizeDoc()
    if (!doc?.docId) return
    organizeVisible.value = false
    options.showHealth(doc)
  }

  async function rollbackOrganizePreview() {
    if (!organizePlanId.value) return
    try {
      const res: any = await rollbackWorkspacePlan(organizePlanId.value)
      if (res.code !== 200) {
        ElMessage.error(res.msg || '回退失败')
        return
      }
      organizeApplied.value = false
      organizeStatus.value = 'rolled_back'
      options.uploadTip.value = ''
      await options.load()
      if (res.data?.needsReindex && organizeDocTarget.value?.docId) {
        const result = await options.runReindex(organizeDocTarget.value, '回退已生效，正在重新建立索引…')
        ElMessage.success(result.ok ? '已回退本次整理，索引已重建' : '已回退，但索引重建失败：' + result.message)
      } else {
        ElMessage.success('已回退本次整理')
      }
    } catch (e: any) {
      ElMessage.error('回退失败：' + (e?.message || e))
    }
  }

  return {
    organizeReportVisible,
    organizePlansLoading,
    organizePlans,
    organizeVisible,
    organizeMode,
    organizeStatus,
    organizeStage,
    organizeProgress,
    organizeElapsed,
    organizeError,
    organizeApplied,
    organizeRecordView,
    organizePlanId,
    organizeChanges,
    organizeSuggestions,
    organizeDocTarget,
    organizeTask,
    deepOrganizeOptions,
    organizeReport,
    refreshOrganizePlans,
    openOrganizeReport,
    deleteOrganizeRecord,
    organizePlanCount,
    openOrganizePlan,
    startOrganize,
    stopOrganizeClock,
    beginOrganize,
    pollOrganizePlan,
    applyOrganizePreview,
    freshOrganizeDoc,
    rerunOrganize,
    recheckOrganize,
    rollbackOrganizePreview
  }
}
