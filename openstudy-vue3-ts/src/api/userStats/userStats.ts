import request from '@/utils/request'
import type { ApiResult } from '@/types'

export interface OverviewStats {
  totalQuestions: number
  totalBanks: number
  totalErrors: number
  totalMarked: number
  totalMastered: number
  totalFavoriteNotes: number
  totalPracticeCount: number
  correctRate: number
  bankStudyCount: number
}

export interface SubjectStat {
  subject: string
  bankCount: number
  questionCount: number
  errorCount: number
  markedCount: number
}

export interface TrendItem {
  date: string
  /** 当天答错次数（同一题重复做错会累计） */
  errorCount: number
  /** 当天答对次数 */
  correctCount: number
  markedCount: number
  /** 当天作答总数（真实答题行为，已不再用"收藏记录数"充数） */
  practiceCount: number
}

export interface ErrorAnalysis {
  /** 全部错题记录数（含已掌握），作为掌握度分母 */
  totalErrors: number
  /** 仍活跃在错题本里的错题数 */
  activeErrors: number
  mastered: number
  masterRate: number
  byDifficulty: { difficulty: number; count: number }[]
  topErrors: { questionId: number; questionText: string; errorCount: number }[]
}

export interface GrowthRecord {
  joinDate: string
  studyDays: number
  /** 连续学习天数（从今天/昨天往前回溯），后端已返回，前端此前未使用 */
  consecutiveDays: number
  totalBanks: number
  totalQuestions: number
  totalNotes: number
  milestones: { type: string; count: number; title: string; achieved: boolean }[]
}

export function getOverview(): Promise<ApiResult<OverviewStats>> {
  return request({ url: '/userStats/overview', method: 'get' }) as unknown as Promise<ApiResult<OverviewStats>>
}

export function getBySubject(): Promise<ApiResult<SubjectStat[]>> {
  return request({ url: '/userStats/bySubject', method: 'get' }) as unknown as Promise<ApiResult<SubjectStat[]>>
}

export function getTrend(days: number = 7): Promise<ApiResult<TrendItem[]>> {
  return request({ url: '/userStats/trend', method: 'get', params: { days } }) as unknown as Promise<ApiResult<TrendItem[]>>
}

export function getErrorAnalysis(): Promise<ApiResult<ErrorAnalysis>> {
  return request({ url: '/userStats/errorAnalysis', method: 'get' }) as unknown as Promise<ApiResult<ErrorAnalysis>>
}

export function getGrowth(): Promise<ApiResult<GrowthRecord>> {
  return request({ url: '/userStats/growth', method: 'get' }) as unknown as Promise<ApiResult<GrowthRecord>>
}

/* ============================================================================
 * 逐题学情诊断（2026-10-26 v3 新增）
 * ----------------------------------------------------------------------------
 * 数据来自后端 `study_diagnosis_service.diagnose()`，是**算出来的、不是 LLM 生成的**。
 *
 * 在此之前它只挂在 AI 工具链上（要跟 AI 对话一句才看得到），而且默认产物是
 * 一份 PDF 下载。这个接口把它变成普通 REST，前端可以直接画成页内图表。
 *
 * 七档掌握度（按"该先处理谁"排序）：
 *   repeated_failure 反复做错 → 概念没通
 *   lapsing          曾经会、现在又错 → 记忆衰减
 *   overdue          过了复习窗口没练 → 该复习了
 *   due_soon         即将到期
 *   on_track         节奏正常
 *   mastered         已掌握
 *   fresh            新题，还没到复习期
 * ========================================================================== */

export type MasteryLevel =
  | 'repeated_failure'
  | 'lapsing'
  | 'overdue'
  | 'due_soon'
  | 'on_track'
  | 'mastered'
  | 'fresh'

export interface DiagnosisItem {
  questionId: number
  bankName: string
  subject: string
  questionText: string
  questionType: number
  difficulty: number
  attempts: number
  correctCount: number
  /** 0~1 */
  accuracy: number
  /** 连续答对次数 */
  streak: number
  level: MasteryLevel
  /** 中文档位名，如「反复失守」 */
  levelText: string
  /** 已过期天数（0=没过期） */
  overdueDays: number
  /** 距下次复习天数 */
  dueInDays: number
  recommendedIntervalDays: number
  lastPracticeTime?: string | null
  lastWrongTime?: string | null
  inErrorBook: boolean
  /** 累计做错次数（可能 > attempts，因为同一题多次错） */
  errorCount: number
  /** 后端算好的、可直接展示的建议句 */
  advice: string
}

export interface DiagnosisLevelInfo {
  count: number
  text: string
}

export interface DiagnosisSubjectRow {
  subject: string
  questions: number
  attempts: number
  /** 0~100 */
  accuracy: number
}

export interface DiagnosisDailyRow {
  date: string
  practiceCount: number
  correctCount: number
}

export interface DiagnosisActivity {
  daily: DiagnosisDailyRow[]
  windowDays: number
  activeDays: number
  peakDayCount: number
  /** 是否"突击式"学习（少数几天做了大部分题） */
  looksLikeBurst: boolean
  totalPractice: number
  averagePerActiveDay: number
}

export interface DiagnosisResult {
  hasData: boolean
  generatedAt: string
  summary: {
    questionsSeen: number
    totalAttempts: number
    overallAccuracy: number
    needsAttention: number
    canArchive: number
    overdueCount: number
  }
  items: DiagnosisItem[]
  byLevel: Record<string, DiagnosisLevelInfo>
  bySubject: DiagnosisSubjectRow[]
  activity: DiagnosisActivity
  headline: string
  suggestions: string[]
}

export function getDiagnose(limit: number = 30): Promise<ApiResult<DiagnosisResult>> {
  return request({ url: '/userStats/diagnose', method: 'get', params: { limit } }) as unknown as Promise<
    ApiResult<DiagnosisResult>
  >
}

/* ============================================================================
 * 学习闭环（2026-10-31）
 * 今日处方 / 知识体检 / 错题歼灭战共用一份逐题诊断结果。
 * ========================================================================== */

export interface LearningLoopTask {
  id: string
  type: 'question'
  questionId: number
  bankName: string
  subject: string
  questionText: string
  title: string
  reason: string
  advice: string
  level: string
  levelText: string
  estimatedMinutes: number
}

export interface LearningLoopWeakQuestion {
  questionId: number
  questionText: string
  level: string
  levelText: string
  accuracy: number
}

export interface LearningLoopHealthNode {
  subject: string
  accuracy: number
  questions: number
  weakCount: number
  status: 'strong' | 'watch' | 'weak'
  statusText: string
  color: string
  size: number
  weakQuestions?: LearningLoopWeakQuestion[]
}

export interface LearningLoopTarget {
  questionId: number
  bankName: string
  subject: string
  questionText: string
  level: string
  levelText: string
  errorCount: number
  streak: number
  stage: 'active' | 'observing'
  advice: string
}

export interface LearningLoopResult {
  hasData: boolean
  generatedAt: string
  headline: string
  todayPlan: LearningLoopTask[]
  healthMap: LearningLoopHealthNode[]
  errorBattle: {
    total: number
    mastered: number
    cleared: number
    observing: number
    active: number
    progress: number
    targets: LearningLoopTarget[]
  }
}

export function getLearningLoop(): Promise<ApiResult<LearningLoopResult>> {
  return request({ url: '/userStats/learning-loop', method: 'get' }) as unknown as Promise<
    ApiResult<LearningLoopResult>
  >
}

export interface PracticeProgressItem {
  questionId: number
  lastPracticeTime: string
  attempts: number
}

export interface PracticeProgressResult {
  since: string
  latest: PracticeProgressItem[]
}

export function getPracticeProgress(
  sinceMs: number,
  questionIds: number[]
): Promise<ApiResult<PracticeProgressResult>> {
  return request({
    url: '/userStats/practice-progress',
    method: 'get',
    params: {
      since_ms: sinceMs,
      question_ids: questionIds.length ? questionIds.join(',') : ''
    }
  }) as unknown as Promise<ApiResult<PracticeProgressResult>>
}

/* ============================================================================
 * 学习周报（2026-10-31）
 * 数据来自最近 7 天真实作答流水（若最近两周没学，则回退到最近一次学习的 7 天）。
 * ========================================================================== */

export interface WeeklyReportDaily {
  date: string
  weekday: string
  practiceCount: number
}

export interface WeeklyReportSubject {
  subject: string
  attempts: number
  accuracy: number
}

export interface WeeklyReportHighlight {
  type: string
  title: string
  detail: string
}

export interface WeeklyReportNext {
  title: string
  detail: string
}

export interface WeeklyReportResult {
  hasData: boolean
  generatedAt: string
  range: { start: string; end: string; label: string; isCurrent: boolean }
  headline: string
  stats: {
    practiceCount: number
    correctCount: number
    accuracy: number
    activeDays: number
    longestStreak: number
    markedCount: number
    deltaPractice: number | null
    deltaAccuracy: number | null
    prevPracticeCount: number
    prevAccuracy: number
  }
  daily: WeeklyReportDaily[]
  subjects: WeeklyReportSubject[]
  peakHour: number | null
  highlights: WeeklyReportHighlight[]
  nextWeek: WeeklyReportNext[]
}

export function getWeeklyReport(): Promise<ApiResult<WeeklyReportResult>> {
  return request({ url: '/userStats/weekly-report', method: 'get' }) as unknown as Promise<
    ApiResult<WeeklyReportResult>
  >
}

/* ============================================================================
 * 趋势图下钻：某一天做了什么（2026-10-31）
 * ========================================================================== */

export interface DayDetailItem {
  questionId: number
  questionText: string
  bankName: string
  subject: string
  isCorrect: boolean
  time: string
}

export interface DayDetailResult {
  date: string
  practiceCount: number
  correctCount: number
  errorCount: number
  markedCount: number
  unavailableCount: number
  items: DayDetailItem[]
}

export function getDayDetail(date: string): Promise<ApiResult<DayDetailResult>> {
  return request({
    url: '/userStats/day-detail',
    method: 'get',
    params: { date }
  }) as unknown as Promise<ApiResult<DayDetailResult>>
}

/* ============================================================================
 * 考前倒计时路线图（2026-10-31）
 * ========================================================================== */

export interface ExamPlanPhase {
  key: string
  title: string
  goal: string
  start: string
  end: string
  days: number
  color: string
}

export interface ExamPlanTask {
  type: string
  questionId: number
  subject: string
  title: string
  detail: string
  minutes: number
}

export interface ExamPlanDay {
  date: string
  phase: string
  theme: string
  tasks: ExamPlanTask[]
  minutes: number
}

export interface ExamPlanResult {
  hasData: boolean
  message?: string
  exam: {
    name: string
    date: string
    startDate: string
    daysLeft: number
    bankId?: number | null
    bankName?: string
    subjects: string[]
    restDays: number[]
    mode: 'balanced' | 'sprint'
    dailyMinutes: number
  }
  planProfile?: {
    key: 'maintenance' | 'micro' | 'standard' | 'intensive'
    label: string
    description: string
  }
  practiceBank?: {
    id: number
    name: string
  } | null
  overview?: {
    questionsSeen: number
    overallAccuracy: number
    needsAttention: number
    overdueCount: number
    repeatedFailure: number
  }
  phases: ExamPlanPhase[]
  days: ExamPlanDay[]
  advice: string[]
}

export interface ExamPlanQuery {
  examName: string
  examDate: string
  bankId?: number
  bankName?: string
  startDate?: string
  subjects?: string[]
  restDays?: number[]
  mode?: 'balanced' | 'sprint'
  dailyMinutes?: number
}

export interface ExamBankOption {
  bankId: number
  bankName: string
  subject: string
  questionCount: number
  attemptCount: number
  errorCount: number
  lastPracticeTime: string
}

export function getExamBanks(): Promise<ApiResult<ExamBankOption[]>> {
  return request({ url: '/userStats/exam-banks', method: 'get' }) as unknown as Promise<ApiResult<ExamBankOption[]>>
}

export function getExamPlan(query: ExamPlanQuery): Promise<ApiResult<ExamPlanResult>> {
  return request({
    url: '/userStats/exam-plan',
    method: 'get',
    params: {
      exam_name: query.examName,
      exam_date: query.examDate,
      bank_id: query.bankId || 0,
      bank_name: query.bankName || '',
      start_date: query.startDate || '',
      subjects: (query.subjects || []).join(','),
      rest_days: (query.restDays || []).join(','),
      mode: query.mode || 'balanced',
      daily_minutes: query.dailyMinutes ?? 40
    }
  }) as unknown as Promise<ApiResult<ExamPlanResult>>
}

/**
 * 生成「薄弱点复习卷」Word（2026-10-26 v3 新增）
 *
 * @param limit 最多收录多少道题（后端按诊断优先级取前 N）
 * @returns .docx 的二进制 Blob，调用方负责触发下载
 *
 * ── 为什么单独一个函数、刻意不走 `ApiResult` ──────────────────
 * 这个接口返回的是**文件流**，不是 `{code,msg,data}` 信封。
 * 若套用统一的 `request` + 拦截器，拦截器会尝试 `JSON.parse` 二进制内容
 * 从而报错（题库导出接口当初也踩过同样的坑）。
 *
 * `responseType: 'blob'` 告诉 axios 不要尝试解析，原样给回 Blob。
 * `timeout` 放宽到 120s：诊断要扫该用户的全部作答记录，
 * 数据量大的账号（实测 84 题 / 333 条记录）需要几秒，
 * 默认 10s 超时偶尔会掐断。
 */
export function buildReviewSheet(limit: number = 20): Promise<Blob> {
  return request({
    url: '/userStats/reviewSheet',
    method: 'get',
    params: { limit },
    responseType: 'blob',
    timeout: 120000
  }) as unknown as Promise<Blob>
}
