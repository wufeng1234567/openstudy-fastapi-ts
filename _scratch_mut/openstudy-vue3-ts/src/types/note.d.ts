/**
 * 笔记相关类型定义（从 business.d.ts 拆分，补充更多字段）
 */

/** 笔记 */
export interface Note {
  noteId: number
  userId: number
  userName?: string
  userAvatar?: string
  categoryId?: number
  categoryName?: string
  title: string
  content?: string
  coverImage?: string
  isPublic: string
  viewCount: number
  likeCount: number
  commentCount: number
  isLiked?: boolean
  isFavorited?: boolean
  status: string
  createTime?: string
  updateTime?: string
  [key: string]: any
}

/** 笔记分类 */
export interface NoteCategory {
  categoryId: number
  userId: number
  categoryName: string
  sortOrder: number
  noteCount?: number
  [key: string]: any
}

/** 笔记评论 */
export interface NoteComment {
  commentId?: number
  noteId: number
  userId: number
  userName?: string
  userAvatar?: string
  content: string
  parentId?: number
  replyUserId?: number
  replyUserName?: string
  children?: NoteComment[]
  createTime?: string
  [key: string]: any
}

/** 笔记图片 */
export interface NoteImage {
  imageId?: number
  noteId: number
  imageUrl: string
  thumbnailUrl?: string
  sortOrder?: number
  [key: string]: any
}

/** 笔记收藏 */
export interface NoteFavorite {
  favoriteId?: number
  userId: number
  noteId: number
  note?: Note
  createTime?: string
  [key: string]: any
}

/** 笔记公共区块 */
export interface NotePublicSection {
  sectionId?: number
  noteId: number
  sectionType: string
  content: string
  sortOrder?: number
  [key: string]: any
}
