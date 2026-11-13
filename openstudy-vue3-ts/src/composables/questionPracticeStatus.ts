// composables/questionPracticeStatus.ts
//
// 练习链路的**纯派生**：会话签名、上报载荷、结算文案（从 `useQuestionPractice.ts` 抽出）。
//
//   · `practiceSessionSignature` —— 服务端练习会话的签名（题单变了就换会话）
//   · `buildPracticeReportPayload` —— 答题上报的载荷（答对 / 答错都要上报）
//   · `buildPracticeResultText` —— 「本次练习完成」的结算文案
//
// ⚠ 依赖方向单向：`useQuestionPractice.ts` → 本模块 → `questionPracticeAnswer`
//    （只取答案格式化与错因备注的现成函数）；**不反向依赖** composable，
//    因此不会形成循环依赖。
//
// ⚠ 练习状态机与事件时序一个字节都没动 —— 这里只把「怎么算」挪到了可独立测的地方。
import type { TransformedQuestion } from '@/types'
import {
  generateErrorNote,
  generateErrorTags,
  stringifyAnswerForLog
} from './questionPracticeAnswer'

/**
 * 服务端练习会话的**签名**
 *
 * ⚠️ 题单一变（题目增删、顺序变）签名就变 → 服务端重建会话 → 成绩口径才准。
 *    只按「题库 id」签名会把上一轮的题目算进这一轮。
 */
export function practiceSessionSignature(bankId: number | string, ids: number[]): string {
  return `${bankId}:${ids.join(',')}`
}

/**
 * 答题上报的载荷
 *
 * ⚠️ **答对 / 答错都要上报** —— 后端 `user_question_favorite.correct_times / error_times`
 *    的唯一来源就是这里；原先只在答错时上报，正确率恒为 0（用户报的 bug）。
 *
 * ⚠️ 错因备注 / 标签只在**答错**时有意义（答对了写备注没意义）。
 */
export function buildPracticeReportPayload(
  question: TransformedQuestion,
  userAnswer: any,
  isCorrect: boolean,
  fallbackBankId: number | string
): {
  questionId: number | string
  bankId: number | string
  isCorrect: boolean
  answer: string
  notes: string | null
  tags: string | null
  difficultyRating: any
} {
  return {
    questionId: question.id,
    bankId: question.bankId || fallbackBankId,
    isCorrect,
    answer: stringifyAnswerForLog(userAnswer),
    notes: isCorrect ? null : generateErrorNote(question, userAnswer),
    tags: isCorrect ? null : generateErrorTags(question.type, userAnswer),
    difficultyRating: question.difficulty || 3
  }
}

/** 「本次练习完成」的结算文案 */
export function buildPracticeResultText(
  correct: number,
  wrong: number,
  accuracy: number
): string {
  return `本次练习完成！\n答对 ${correct} 题，答错 ${wrong} 题，正确率 ${accuracy}%`
}
