// composables/questionPracticeQuestionShape.ts
//
// 练习题的**形状**辅助（从 `useQuestionPractice.ts` 抽出）。
//
//   · `asUnansweredQuestion` —— 把一道处理好的题重置成「未作答」
//
// ⚠ 依赖方向单向：`useQuestionPractice.ts` → 本模块；本模块**零 import**，
//    不反向依赖它，因此不会形成循环依赖。
//
// ⚠ **练习状态机与作答流程一个字节都没动** —— 这里只把「重置成未作答」时
//    那四个字段的形状挪到了可独立读、可独立测的地方。
/**
 * 把一道处理好的题重置成「未作答」
 *
 * ⚠️ 这四个字段**必须一起重置** —— 只漏一个就会出现「题目没作答、却还显示着
 *    上次的答案 / 解析」的错位（用户报的「练完再进来答案还在」）。
 *
 * ⚠️ 这段形状原本在**两处**逐字相同（乱序出题 / 顺序出题）—— 现在收敛到一处，
 *    以后再加一个要重置的字段，不会漏掉其中一条路径。
 */
export function asUnansweredQuestion<T extends object>(processed: T) {
  return {
    ...processed,
    answered: false,
    correct: false,
    showAnalysis: false,
    userAnswer: null
  }
}
