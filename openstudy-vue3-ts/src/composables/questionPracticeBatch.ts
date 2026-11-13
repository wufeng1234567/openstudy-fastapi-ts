// composables/questionPracticeBatch.ts
//
// 练习页「题单批次 / 初始答题态」的**纯派生**（从 `useQuestionPractice.ts` 抽出）。
//
// 这些函数只从入参算出结果，**不碰响应式状态**：
//   · `shuffleArray` —— Fisher–Yates 洗牌（返回**新数组**，不改入参）
//   · `isShuffledMode` —— 该模式是否要打乱（随机练习 / 模拟考试）
//   · `computeBatchSliceEnd` —— 一批题的切片末尾
//   · `buildInitialAnswers` —— 一批题的**初始答案**（组合题 `{}`、其余 `null`）
//   · `resetQuestionFlags` / `showAnalysisForAll` —— 作答标记归零 / 全部显示解析
//   · `answerStateCacheKey` —— 会话内答题态缓存的键
//
// ⚠ 依赖方向单向：`useQuestionPractice.ts` → 本模块 → `questionPracticeRules`；
//    这两个模块**都不反向依赖**本文件，因此不会形成循环依赖。
//
// ⚠ 练习状态机与事件时序一个字节都没动 —— 这里只把「怎么算」挪到了可独立读、
//    可独立测的地方；`questions` / `answers` 的赋值时机与先后完全不变。
import { isCompositeType } from './questionPracticeRules'

/**
 * Fisher–Yates 洗牌 —— 返回**新数组**，**不改入参**
 *
 * ⚠️ 与 `questionPracticeRandomPlan` 里的 `shuffleInPlace` 是两处**各自独立**的洗牌：
 *    那边就地洗（题单要保留同一份顺序），这边返回新数组（原数组不能动）。
 */
export function shuffleArray<T>(items: T[]): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

/** 该模式是否要打乱题目顺序（随机练习 / 模拟考试） */
export function isShuffledMode(moduleType: string): boolean {
  return moduleType === 'random' || moduleType === 'mock'
}

/**
 * 一批题的切片末尾（`loadBatchWithoutReset` 用）
 *
 * ⚠️ 与 `questionPracticeRules.computeSliceWindow` **刻意不同**：那个会先把 offset
 *    归到「每批的整数倍」，这里用的是**调用方给的原始 offset**。
 *    两处各按各的语义用，不要混用。
 */
export function computeBatchSliceEnd(total: number, count: number | string, offset: number): number {
  if (count === 'all') return total
  if (typeof count === 'number') return Math.min(offset + count, total)
  return Math.min(offset + 10, total)
}

/** 一批题的**初始答案**：组合题（阅读理解 / 完形填空）是 `{}`，其余是 `null` */
export function buildInitialAnswers(questions: any[]): any[] {
  return questions.map((q) => {
    if (isCompositeType(q.type)) {
      return {}
    }
    return null
  })
}

/** 把一批题的作答标记归零（换波 / 重新练习时用） */
export function resetQuestionFlags(questions: any[]): void {
  questions.forEach((q) => {
    q.answered = false
    q.correct = false
    q.showAnalysis = false
  })
}

/** 让一批题全部显示解析（「查看解析」） */
export function showAnalysisForAll(questions: any[]): void {
  questions.forEach((q) => {
    q.showAnalysis = true
  })
}

/**
 * 会话内答题态缓存的键（同一题库 + 同一模式互不影响）
 *
 * ⚠️ 键的**形状**是既有约定：缓存存在内存里、刷新即失效，但同一批改动里
 *    `saveCurrentAnswerState` / `restoreAnswerState` / `clearAnswerStateCache`
 *    三处必须算出**同一个**键 —— 统一从这里取，别各写一遍模板字符串。
 */
export function answerStateCacheKey(bankId: number | string, moduleType: string): string {
  return `${bankId}_${moduleType}`
}
