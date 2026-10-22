/**
 * 刷题相关类型定义
 */

/** 练习模块类型 */
export type ModuleType = 'sequential' | 'random' | 'custom' | 'mock'

/** 练习/考试模式 */
export type PracticeMode = 'practice' | 'exam'

/**
 * 模拟考试的「按题型」组卷配置（2026-10-22）
 *
 * 为什么要按题型而不是只给一个总题数：
 *   真实考试里各题型的题量与分值本来就不同（单选 70×1 + 多选 20×1 + 判断 10×1）。
 *   只让用户填"共多少题"，要么系统替他平均分，要么全用同一种题型 —— 都不符合
 *   "自己设计一场考试"的预期。所以这里做成 per-type 的 {题数, 每题分值}。
 *
 * ⚠️ key 用的是前端归一后的题型（`QuestionType`），不是后端原始 `questionType` 数字。
 *    组卷时按归一后的类型分桶，见 `MockExamConfig.typeRows`。
 */
export interface MockExamTypeRow {
  /** 题型（前端归一值） */
  type: QuestionType
  /** 本次考试该题型抽多少道 */
  count: number
  /** 每道多少分 */
  score: number
}

/**
 * 模拟考试配置
 *
 * 与 `ModuleSettings` 的关系：本结构是 mock 模块的**考试专属**配置，
 * 挂在 `ModuleSettings.mockExam` 下（不强塞进 ModuleSettings 顶层，避免其他三个
 * 刷题入口也带着一堆用不上的考试字段）。
 */
export interface MockExamConfig {
  /** 各题型题数与分值 */
  typeRows: MockExamTypeRow[]
  /** 考试时长（分钟） */
  timeLimit: number
  /** 及格分（总分制） */
  passScore: number
  /** 选项乱序（仅考试页可配；答题卡面板不出现这个开关） */
  shuffleOptions: boolean
  /** 多选题得分模式 */
  multipleMode: 'strict' | 'partial'
  /** 漏选按比例得分时的比例（0~1），仅 `multipleMode === 'partial'` 时有意义 */
  partialRatio: number
}

/** 单题在某场考试里的判分明细（历史记录与总结页共用） */
export interface MockExamItemDetail {
  questionId: number | string
  /** 序号（从 1 开始，进考场时的顺序） */
  index: number
  type: QuestionType
  /** 题干纯文本片段（用于列表展示） */
  stem: string
  userAnswer: any
  correctAnswer: any
  isCorrect: boolean
  /** 该题实得分 */
  gotScore: number
  /** 该题满分 */
  fullScore: number
  analysis?: string
}

/**
 * 一场已完成考试的历史记录
 *
 * ⚠️ 存 localStorage 而不是后端：当前还没有"考试记录"表，
 *    而这次改造的目标是"用户能回看自己的每次考试"，本地存已能满足；
 *    将来要跨设备同步时，这份结构可以直接当后端表结构的蓝本。
 */
export interface MockExamRecord {
  /** 记录 id（时间戳 + 随机后缀，避免同毫秒重复） */
  id: string
  bankId: number | string
  bankName: string
  /** 交卷时间（毫秒时间戳） */
  submittedAt: number
  /** 本次配置快照（历史回看时不受用户后来改设置影响） */
  config: MockExamConfig
  /** 统计 */
  totalQuestions: number
  correctCount: number
  wrongCount: number
  /** 得分（含多选部分分，保留 1 位小数） */
  gotScore: number
  /** 满分 */
  fullScore: number
  passed: boolean
  /** 实际用时（秒） */
  durationSec: number
  /** 逐题明细 */
  items: MockExamItemDetail[]
}


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
  /**
   * 模拟考试的专属配置（仅 mock 模块使用，2026-10-22）
   *
   * 不塞到顶层的原因：其他三个刷题入口用不到按题型组卷、及格分、多选题得分模式，
   * 平铺上去会让 `ModuleSettings` 变成一个什么都装的袋子，也容易让设置面板
   * 误把考试字段渲染到刷题模式下。
   */
  mockExam?: MockExamConfig
  [key: string]: any
}

/** 4 模块配置映射 */
export type PracticeModuleConfig = Record<ModuleType, ModuleSettings>

/** 刷题整体设置（持久化到 localStorage） */
export interface PracticeSettings {
  currentBankId: number | string | null
  currentBankName: string
  modules: PracticeModuleConfig
  /**
   * 模拟考试历史记录（按时间倒序，最新的在前）
   *
   * 放在顶层而不是 modules.mock 下：历史属于「用户数据」，
   * 而 modules 是「模块偏好」——`resetModuleSettings('mock')` 会重置偏好，
   * 不该顺手把用户的历史考卷删掉。
   */
  mockExamHistory?: MockExamRecord[]
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
