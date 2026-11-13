// composables/questionPracticeState.ts
//
// 练习链路的**状态派生**（从 `useQuestionPractice.ts` 抽出）。
//
//   · `buildAnswerStateSnapshot` —— 会话内答题态缓存的**快照形状**
//   · `markedIdsFromResponse` —— 收藏 / 斩题 / 错题标记接口返回的 id 集合
//
// ⚠ 依赖方向单向：`useQuestionPractice.ts` → 本模块；本模块**不反向依赖**它，
//    因此不会形成循环依赖。
//
// ⚠ 练习状态机与事件时序一个字节都没动 —— 这里只把「状态怎么算」挪到了
//    可独立读、可独立测的地方。

/** 会话内答题态快照的**内容形状**（`answerStateCache` 里存的就是它） */
export interface AnswerStateSnapshot {
  questions: any[]
  allQuestionsData: any[]
  answers: any[]
  currentQuestionIndex: number
  selectedAnswer: any
  subFillBlankAnswers: Record<string | number, any>
  subEssayAnswers: Record<string | number, any>
  questionOffset: number
  questionCount: number | string | null
}

/**
 * 造一份答题态快照
 *
 * ⚠️ 数组与子题答案都**复制一份**再存进缓存：缓存与页面状态共用同一批对象引用的话，
 *    用户在页面上继续作答会**顺手改掉缓存里的旧快照**，切回来时状态就串了。
 */
export function buildAnswerStateSnapshot(input: {
  questions: any[]
  allQuestionsData: any[]
  answers: any[]
  currentQuestionIndex: number
  selectedAnswer: any
  subFillBlankAnswers: Record<string | number, any>
  subEssayAnswers: Record<string | number, any>
  questionOffset: number
  questionCount: number | string | null
}): AnswerStateSnapshot {
  return {
    questions: [...input.questions],
    allQuestionsData: [...input.allQuestionsData],
    answers: [...input.answers],
    currentQuestionIndex: input.currentQuestionIndex,
    selectedAnswer: input.selectedAnswer,
    subFillBlankAnswers: { ...input.subFillBlankAnswers },
    subEssayAnswers: { ...input.subEssayAnswers },
    questionOffset: input.questionOffset,
    questionCount: input.questionCount
  }
}

/**
 * 从「收藏 / 斩题 / 错题」批量查询的返回里取出**打上标记的题目 id**
 *
 * ⚠️ 接口返回的是 `{ "<题目id>": 0|1 }` 这样的映射，值为真才算标记上了。
 *
 * ⚠️ 这段解析原本在 `loadQuestionStatus` 里**写了三遍**（收藏 / 斩题 / 错题各一遍），
 *    现在收敛到一份实现 —— 三处的口径不会再漂。
 */
export function markedIdsFromResponse(data: Record<string, any> | null | undefined): Set<number> {
  return new Set(
    Object.entries(data || {}).filter(([, v]) => v).map(([k]) => Number(k))
  )
}
