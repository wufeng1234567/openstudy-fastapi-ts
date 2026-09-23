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
