/**
 * 学习计划的跨页面可重建状态。
 *
 * 只保存“参数 + sinceMs”，不保存完成态；完成状态始终由后端按真实答题/阅读流水重算。
 * 这样知识图谱、学习统计、Agent 看到的是同一份计划，而不是三份快照。
 */
export interface StudyPlanConfig {
  kbId: number
  goal: 'weakness' | 'foundation' | 'explore' | 'exam' | 'today' | 'sections'
  examDate: string
  horizonDays: number
  dailyMinutes: number
  restDays: number[]
  bankIds: number[]
  sinceMs: number
  savedAt: number
  planId?: string
}

// 兼容旧键名：不新建第二个计划状态键，只在原键上做加性字段扩展。
const CURRENT_KEY = 'openstudy.workspace.studyPlanState'
const V2_KEY = 'openstudy.studyPlan.config.v2'
const LEGACY_EXAM_PREFIX = 'os_exam_plan_v1_'

function safeParse(raw: string | null): any {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function startOfTodayMs(now = new Date()): number {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
}

function normalizeConfig(value: any): StudyPlanConfig | null {
  if (!value || typeof value !== 'object') return null
  const kbId = Number(value.kbId || 0)
  const sinceMs = Number(value.sinceMs || 0)
  if (!sinceMs) return null
  return {
    kbId: Number.isFinite(kbId) ? kbId : 0,
    goal: ['weakness', 'foundation', 'explore', 'exam', 'today', 'sections'].includes(value.goal)
      ? value.goal
      : 'weakness',
    examDate: String(value.examDate || ''),
    horizonDays: Math.max(1, Math.min(Number(value.horizonDays || 7), 30)),
    dailyMinutes: Math.max(10, Math.min(Number(value.dailyMinutes || 40), 240)),
    restDays: Array.isArray(value.restDays)
      ? value.restDays.map(Number).filter((n: number) => n >= 1 && n <= 7)
      : [],
    bankIds: Array.isArray(value.bankIds)
      ? [...new Set(value.bankIds.map(Number).filter((n: number) => n > 0))]
      : [],
    sinceMs,
    savedAt: Number(value.savedAt || Date.now()),
    planId: value.planId ? String(value.planId) : undefined
  }
}

export function readStudyPlanConfig(kbId?: number | null): StudyPlanConfig | null {
  if (typeof localStorage === 'undefined') return null
  const raw = safeParse(localStorage.getItem(CURRENT_KEY))
  const current = normalizeConfig(raw)
  if (current) {
    if (kbId && Number(kbId) !== current.kbId) return null
    return current
  }

  // 兼容旧 workspace 快照：只取可重建参数，丢弃 plan 本体。
  if (raw?.plan) {
    const plan = raw.plan || {}
    const migrated = normalizeConfig({
      kbId: raw.kbId || plan.intent?.kbId || 0,
      goal: plan.intent?.goal || raw.strategy || 'weakness',
      examDate: plan.intent?.examDate || '',
      horizonDays: plan.window?.horizonDays || 7,
      dailyMinutes: plan.window?.dailyMinutes || 40,
      restDays: plan.window?.restDays || [],
      bankIds: plan.intent?.bankIds || [],
      sinceMs: raw.sinceMs || plan.window?.sinceMs || 0,
      savedAt: Date.now(),
      planId: plan.planId
    })
    if (migrated && (!kbId || Number(kbId) === migrated.kbId)) return migrated
  }

  // 只作为本次开发期间的向后兼容，不参与正式持久化。
  const v2 = normalizeConfig(safeParse(localStorage.getItem(V2_KEY)))
  if (v2 && (!kbId || Number(kbId) === v2.kbId)) return v2
  return null
}

export function saveStudyPlanConfig(config: Omit<StudyPlanConfig, 'savedAt'> & { savedAt?: number }): void {
  if (typeof localStorage === 'undefined') return
  const payload: StudyPlanConfig = {
    ...config,
    savedAt: Number(config.savedAt || Date.now())
  }
  try {
    localStorage.setItem(CURRENT_KEY, JSON.stringify(payload))
  } catch {
    // 存储不可用不应阻塞当前页面
  }
}

export function clearStudyPlanConfig(): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.removeItem(CURRENT_KEY)
    localStorage.removeItem(V2_KEY)
  } catch {
    // ignore
  }
}

export interface LegacyExamConfig {
  examDate: string
  dailyMinutes: number
  restDays: number[]
  bankId: number
}

export function readLegacyExamConfig(userId?: number | string): LegacyExamConfig | null {
  if (typeof localStorage === 'undefined') return null
  const saved = safeParse(localStorage.getItem(`${LEGACY_EXAM_PREFIX}${userId || 'anon'}`))
  const form = saved?.form
  if (!form) return null
  return {
    examDate: String(form.examDate || ''),
    dailyMinutes: Math.max(10, Math.min(Number(form.dailyMinutes || 40), 240)),
    restDays: Array.isArray(form.restDays)
      ? form.restDays.map(Number).filter((n: number) => n >= 1 && n <= 7)
      : [],
    bankId: Number(form.bankId || 0)
  }
}
