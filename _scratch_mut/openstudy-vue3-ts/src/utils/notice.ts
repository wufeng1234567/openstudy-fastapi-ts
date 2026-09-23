/**
 * 通知分类工具
 *
 * 后端 `sys_notice` 表同时承载了两种来源的通知，通过 `remark` 字段的 JSON `type` 区分：
 * - 系统通知：管理员发布，通常没有 remark（或 remark 不含用户通知的 type）
 * - 用户通知：普通用户产生，remark.type ∈ { comment, reply, mention }
 *   - comment：有人评论了你的笔记
 *   - reply  ：有人回复了你的评论 / 留言
 *   - mention：有人在评论中 @ 了你
 *
 * 后端 `/system/notice/listAll` 已按 remark.toUserId 过滤（只下发系统公告 + 发给我的通知）。
 * 这里再在前端做一层兜底判断：即使后端返回了脏数据，也不会串到别的用户的页面/红点里。
 */
export const USER_NOTICE_TYPES = ['comment', 'reply', 'mention'] as const
export type UserNoticeType = (typeof USER_NOTICE_TYPES)[number]

export interface NoticeRemark {
  type?: string
  fromUserId?: number | string
  toUserId?: number | string
  noteId?: number | string
  commentId?: number | string
  [key: string]: unknown
}

/** 解析 remark（解析失败 / 非对象返回 null，不抛异常） */
export function parseNoticeRemark(remark?: string | null): NoticeRemark | null {
  if (!remark) return null
  try {
    const parsed = JSON.parse(remark)
    return parsed && typeof parsed === 'object' ? (parsed as NoticeRemark) : null
  } catch {
    return null
  }
}

/** 判断是否属于「用户通知」类型；不是则返回空字符串 */
export function getUserNoticeType(notice: any): UserNoticeType | '' {
  const type = parseNoticeRemark(notice?.remark)?.type
  return USER_NOTICE_TYPES.includes(type as UserNoticeType) ? (type as UserNoticeType) : ''
}

/** 系统通知：不是用户通知类型的一律归为系统通知（无 remark 的管理员公告、remark 解析失败等） */
export function isSystemNotice(notice: any): boolean {
  return !getUserNoticeType(notice)
}

/**
 * 是否是「发给当前用户」的用户通知。
 * remark 里没有 toUserId 时视为发给所有人（兼容旧数据）。
 */
export function isUserNoticeFor(notice: any, userId?: number | string | null): boolean {
  if (!getUserNoticeType(notice)) return false
  const toUserId = parseNoticeRemark(notice?.remark)?.toUserId
  if (toUserId === undefined || toUserId === null || toUserId === '') return true
  return String(toUserId) === String(userId)
}

/** 用户通知类型的中文短标签 */
export function getUserNoticeTypeLabel(notice: any): string {
  const map: Record<UserNoticeType, string> = {
    comment: '评论',
    reply: '回复',
    mention: '@我'
  }
  const type = getUserNoticeType(notice)
  return type ? map[type] : ''
}
