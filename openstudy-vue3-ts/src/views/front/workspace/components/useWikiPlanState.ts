import { saveStudyPlanConfig, readStudyPlanConfig } from '@/utils/studyPlanState'

/**
 * 学习计划快照的读写（只存可重建状态，不把前端勾选当完成态）。
 *
 * 从 KnowledgeWikiPanel.vue 抽出。plan 的字段拼装与 kbId 读取逻辑原样保留，
 * 仅把 props / routeStrategy 改为 options 传入。
 */
export function useWikiPlanState(options: {
  props: any
  routeStrategy: any
}) {
  const { props, routeStrategy } = options

  /** 计划快照只存“可重建状态 + 当前视图”，不把前端勾选当完成态。 */
  function persistPlanState(plan: any) {
    if (!plan) return
    saveStudyPlanConfig({
      kbId: Number(props.activeKbId || 0),
      goal: plan.intent?.goal || routeStrategy.value,
      examDate: plan.intent?.examDate || '',
      horizonDays: Number(plan.window?.horizonDays || 7),
      dailyMinutes: Number(plan.window?.dailyMinutes || 40),
      restDays: Array.isArray(plan.window?.restDays) ? plan.window.restDays : [],
      bankIds: Array.isArray(plan.intent?.bankIds) ? plan.intent.bankIds : [],
      sinceMs: Number(plan.window?.sinceMs || 0),
      planId: String(plan.planId || '')
    })
  }

  function readPlanState(): any | null {
    return readStudyPlanConfig(props.activeKbId)
  }

  return { persistPlanState, readPlanState }
}
