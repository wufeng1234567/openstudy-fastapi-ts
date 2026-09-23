/**
 * 刷题相关类型定义
 */

/** 练习模块类型 */
export type ModuleType = 'sequential' | 'random' | 'custom' | 'mock'

/** 练习/考试模式 */
export type PracticeMode = 'practice' | 'exam'

/** 题型（前端转换后的字符串形式） */
export type QuestionType =
  | 'single'
  | 'multiple'
  | 'truefalse'
  | 'fillblank'
  | 'essay'
  | 'readingComprehension'
  | 'cloze'
  | 'unknown'

/** 难度等级 1-4 */
export type DifficultyLevel = 1 | 2 | 3 | 4

// 注：QuestionOption 统一定义在 business.d.ts 中（含 isCorrect 字段），此处不再重复声明。

/** 单个模块的设置 */
export interface ModuleSettings {
  questionCount: number
  /** 是否打乱选项顺序 */
  shuffleOptions: boolean
  /** 答对后自动跳下一题 */
  autoNextOnCorrect: boolean
  /** 仅错题练习 */
  onlyWrong: boolean
  /** 练习 / 考试模式 */
  practiceMode: PracticeMode
  /** 整体浏览模式 */
  isOverviewMode: boolean
  /** 浏览模式下的滚动位置 */
  overviewScrollIndex?: number
  /** 自定义模式指定的题目 ID 列表 */
  markedQuestions?: number[]
  /** 考试模式时限（分钟） */
  examTimeLimit?: number
  [key: string]: any
}

/** 4 模块配置映射 */
export type PracticeModuleConfig = Record<ModuleType, ModuleSettings>

/** 刷题整体设置（持久化到 localStorage） */
export interface PracticeSettings {
  currentBankId: number | string | null
  currentBankName: string
  modules: PracticeModuleConfig
  [key: string]: any
}

/** 转换后的题目（用于显示/答题） */
export interface TransformedQuestion {
  id: number | string
  questionId?: number
  bankId?: number
  /** 题型（字符串形式） */
  type: QuestionType
  /** 后端原始题型 */
  questionType?: string | number
  /** 题干 */
  question?: string
  questionText?: string
  content?: string
  /** 选项（字符串数组或对象数组，转换后必定存在） */
  options: any[]
  /** 用户答案 */
  answer?: any
  /** 标准答案 */
  correctAnswer?: any
  analysis?: string
  difficulty?: number | DifficultyLevel
  score?: number
  sortOrder?: number
  /** 组合题主干内容 */
  mainContent?: string
  mainTitle?: string
  hasMainContent?: boolean
  /** 是否含子题 */
  hasSubQuestions?: boolean
  /** 子题列表（转换后必定存在，可能为空数组） */
  subQuestions: TransformedSubQuestion[]
  /** 答题状态 */
  answered?: boolean
  correct?: boolean
  showAnalysis?: boolean
  userAnswer?: any
  [key: string]: any
}

/** 转换后的子题 */
export interface TransformedSubQuestion {
  question?: string
  questionText?: string
  type: QuestionType
  options?: any[]
  analysis?: string
  correctAnswer?: any
  answered?: boolean
  correct?: boolean
  [key: string]: any
}

/** 答题状态 */
export interface AnswerState {
  selectedAnswer: string | string[] | number | number[] | null
  answers: Record<number, any>
  isCorrect: boolean | null
  [key: string]: any
}

/** 答题记录 */
export interface AnswerRecord {
  questionId: number | string
  userAnswer: any
  isCorrect: boolean
  timeSpent?: number
  [key: string]: any
}

/** 练习状态（composable 内部状态） */
export interface PracticeState {
  questions: TransformedQuestion[]
  allQuestionsData: TransformedQuestion[]
  currentQuestionIndex: number
  questionCount: number | string | null
  questionOffset: number
  isResetting: boolean
  [key: string]: any
}

/** 练习结果统计 */
export interface PracticeResult {
  totalQuestions: number
  answeredQuestions: number
  correctCount: number
  wrongCount: number
  accuracy: number
  totalTime: number
  wrongQuestionIds: (number | string)[]
  [key: string]: any
}
