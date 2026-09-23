/**
 * 业务类型定义
 */

/** 题库 */
export interface QuestionBank {
  id: number
  bankName: string
  description?: string
  userId: number
  userName?: string
  coverImage?: string
  subject?: string
  totalQuestions: number
  status: string
  createTime?: string
  [key: string]: any
}

/** 题目 */
export interface QuestionMain {
  id: number
  bankId: number
  questionType: number
  questionText: string
  content?: string
  answer?: string
  analysis?: string
  difficulty: number
  score: number
  status: string
  options?: string
  createTime?: string
  [key: string]: any
}

/** 题目选项 */
export interface QuestionOption {
  label: string
  content: string
  /** 是否为正确选项（前端转换后可选） */
  isCorrect?: boolean
  sortOrder?: number
  [key: string]: any
}

/** 子题（组合题 / 阅读理解 / 完形填空中的子题目） */
export interface QuestionSub {
  /** 子题主键 */
  id?: number
  subId?: number
  /** 所属主题 ID（兼容 mainId / parentId） */
  mainId?: number
  parentId?: number
  questionId?: number
  /** 子题题干（兼容 questionText / content） */
  questionText?: string
  content?: string
  subContent?: string
  /** 子题题型（数字或文本） */
  questionType?: string | number
  subType?: string
  /** 选项（字符串 / 数组 / QuestionOption[]） */
  options?: string | any[] | QuestionOption[]
  subOptions?: string
  /** 答案 */
  answer?: any
  subAnswer?: string
  /** 解析 */
  analysis?: string
  subAnalysis?: string
  /** 排序与分值 */
  sortOrder?: number
  score?: number
  [key: string]: any
}

/** 用户错题 */
export interface UserQuestionError {
  errorId?: number
  userId: number
  questionId: number
  bankId?: number
  /** 首次出错时间 */
  errorTime?: string
  /** 最近出错时间 */
  lastErrorTime?: string
  errorCount: number
  /** 错因备注 */
  notes?: string
  /** 错题标签（逗号分隔） */
  tags?: string
  /** 难度评级 1-4 */
  difficultyRating?: number
  reviewCount?: number
  /** 是否已掌握（0/1） */
  isMastered?: number | boolean
  /** 状态（1 正常） */
  status?: number
  question?: QuestionMain
  [key: string]: any
}

/** 用户收藏题目 */
export interface UserQuestionFavorite {
  favoriteId?: number
  userId: number
  questionId: number
  bankId?: number
  notes?: string
  tags?: string
  /** 是否加星 */
  isStarred?: number | boolean
  /** 收藏状态 */
  favoriteStatus?: string
  createTime?: string
  question?: QuestionMain
  [key: string]: any
}

/** 用户斩题（已掌握） */
export interface UserQuestionMarked {
  markedId?: number
  userId: number
  questionId: number
  bankId?: number
  /** 斩题类型 */
  markedType?: string
  /** 难度等级 1-4 */
  difficultyLevel?: number
  /** 是否已掌握 */
  isMastered?: number | boolean
  createTime?: string
  question?: QuestionMain
  [key: string]: any
}

/** 用户收藏题库 */
export interface UserBankFavorite {
  favoriteId?: number
  userId: number
  bankId: number
  createTime?: string
  bank?: QuestionBank
  [key: string]: any
}

/** 题目笔记 */
export interface NoteQuestion {
  noteId?: number
  userId: number
  questionId: number
  bankId?: number
  content: string
  createTime?: string
  updateTime?: string
  [key: string]: any
}

// 注：Note / NoteCategory / NoteComment / NoteImage 的完整定义位于 note.d.ts，
// 此处不再重复声明以避免类型冲突。

/** 课程 */
export interface Course {
  courseId: number
  courseName: string
  courseDescription?: string
  coverImage?: string
  userId?: number
  category?: string
  status: string
  createTime?: string
  [key: string]: any
}

/** 词书 */
export interface WordBook {
  bookId: number
  bookName: string
  bookDescription?: string
  wordCount: number
  coverImage?: string
  status: string
  [key: string]: any
}

/** 单词 */
export interface Word {
  wordId: number
  bookId: number
  word: string
  phonetic?: string
  translation?: string
  example?: string
  audioUrl?: string
  [key: string]: any
}

/** 轮播图 */
export interface Carousel {
  carouselId?: number
  title: string
  imageUrl: string
  linkUrl?: string
  description?: string
  sortOrder?: number
  status: string
  [key: string]: any
}

/** 留言 */
export interface LeaveMessage {
  messageId?: number
  userId: number
  userName?: string
  content: string
  replyContent?: string
  status: string
  createTime?: string
  [key: string]: any
}

/** 评论 */
export interface Comment {
  commentId?: number
  userId: number
  userName?: string
  userAvatar?: string
  targetType: string
  targetId: number
  content: string
  parentId?: number
  replyUserId?: number
  replyUserName?: string
  createTime?: string
  [key: string]: any
}

/** 敏感词 */
export interface SensitiveWord {
  wordId?: number
  word: string
  category?: string
  status: string
  createTime?: string
  [key: string]: any
}
