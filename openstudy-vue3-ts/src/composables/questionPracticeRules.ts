// composables/questionPracticeRules.ts
//
// 练习页的**判定与派生规则**（从 `useQuestionPractice.ts` 抽出）。
//
// 这些函数只回答「**是什么 / 算出来是多少**」，不碰响应式状态、不发请求：
//   · `COMPOSITE_TYPES` / `isCompositeType` —— 组合题（阅读理解 / 完形填空）的题型
//   · `isAnswerCorrect` —— 前端口径的判对错
//   · `isCompositeAnswered` —— 组合题的子题是否**全部**填完
//   · `toggleSelection` —— 多选题的选中态切换
//   · `computeSliceWindow` —— 题单的切片窗口（offset + 末尾）
//
// ⚠️ 本模块**零 import**：不依赖 Vue、不依赖任何服务层，因此不可能形成循环依赖。
//
// ⚠️ 这里只是把「口径」搬到可独立读、可独立测的地方 ——
//    练习状态机（取题 → 切片 → 作答 → 提交）与事件时序一行未动。
//
// ⚠️ `isAnswerCorrect` 只是**前端回显**用的口径；权威判分在服务端
//    （`handleAnswerSubmission` 拿服务端返回的 `correct` 落库）。
/** 组合题（阅读理解 / 完形填空）的题型 —— 它们的答案结构与普通题不同 */
export const COMPOSITE_TYPES = ['readingComprehension', 'cloze'] as const

/** 是不是组合题（阅读理解 / 完形填空） */
export function isCompositeType(type: any): boolean {
  return (COMPOSITE_TYPES as readonly string[]).includes(type)
}

/**
 * 前端口径的判对错
 *
 * · 单选 / 判断 —— 直接比相等
 * · 多选 —— 长度相同且**每一个**都在标准答案里（不看顺序）
 * · 填空 / 问答 —— 去空格后忽略大小写比字符串
 * · 其余题型 —— 一律算错（前端只回显，不做别的判定）
 */
export function isAnswerCorrect(type: any, userAnswer: any, correctAnswer: any): boolean {
  if (type === 'single' || type === 'truefalse') {
    return userAnswer === correctAnswer
  }
  if (type === 'multiple') {
    return (
      Array.isArray(userAnswer) &&
      Array.isArray(correctAnswer) &&
      userAnswer.length === correctAnswer.length &&
      userAnswer.every((v: any) => correctAnswer.includes(v))
    )
  }
  if (type === 'fillblank' || type === 'essay') {
    return String(userAnswer).trim().toLowerCase() === String(correctAnswer).trim().toLowerCase()
  }
  return false
}

/**
 * 组合题的子题是否**全部**填完
 *
 * 填空 / 问答题看 `ans.fillblank[idx]` / `ans.essay[idx]`；其余子题看 `ans[idx]`。
 */
export function isCompositeAnswered(subQuestions: any, ans: any): boolean {
  return subQuestions.every((subQ: any, idx: number) => {
    if (subQ.type === 'fillblank') {
      return ans && ans.fillblank && ans.fillblank[idx] !== undefined && ans.fillblank[idx] !== ''
    } else if (subQ.type === 'essay') {
      return ans && ans.essay && ans.essay[idx] !== undefined && ans.essay[idx] !== ''
    } else {
      return ans && ans[idx] !== undefined
    }
  })
}

/** 多选题的选中态切换：已选 → 取消；未选 → 选中 */
export function toggleSelection(list: number[], index: number): number[] {
  const i = list.indexOf(index)
  if (i > -1) list.splice(i, 1)
  else list.push(index)
  return list
}

/**
 * 题单的切片窗口
 *
 * · `offset` —— 存回 `questionOffset` 的值（归零后不小于 0）
 * · `sliceStart` / `sliceEnd` —— 真正用来切片的起止（`sliceEnd` 取不到就截到全库长度）
 *
 * ⚠️ `sliceStart` 与 `offset` 分开给：原实现里「存回状态的值」与「切片的起点」
 *    取的是同一个 `newOffset`，但一个是 `Math.max(0, …)` 过的、一个没有 ——
 *    分开返回是为了**逐字保持**原来的口径，不顺手「修正」任何边界。
 */
export function computeSliceWindow(
  total: number,
  count: number | string,
  offset: number
): { offset: number; sliceStart: number; sliceEnd: number } {
  let newOffset = 0
  if (count !== 'all' && typeof count === 'number') {
    newOffset = Math.floor(offset / count) * count
  }

  let sliceEnd: number
  if (count === 'all') {
    sliceEnd = total
  } else if (typeof count === 'number') {
    sliceEnd = Math.min(newOffset + count, total)
  } else {
    sliceEnd = Math.min(newOffset + 10, total)
  }

  return { offset: Math.max(0, newOffset), sliceStart: newOffset, sliceEnd }
}
