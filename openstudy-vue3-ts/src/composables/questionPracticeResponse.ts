// composables/questionPracticeResponse.ts
//
// 练习接口**返回结构**的兼容处理（从 `useQuestionPractice.ts` 抽出）。
//
//   · `pickArray` —— 从 `{ data: [] }` / `{ result: [] }` 两种返回结构里取出数组
//
// ⚠ 依赖方向单向：`useQuestionPractice.ts` → 本模块；本模块**零 import**，
//    不反向依赖它，因此不会形成循环依赖。
//
// ⚠ **练习状态机与事件时序一个字节都没动** —— 这里只把「后端返回可能是哪两种形状」
//    收敛到一处；调用点、拿数据的时机、后续处理顺序全部原样。

/**
 * 从响应里取出题目数组。
 *
 * ⚠️ 后端列表接口的返回结构有两种：`{ data: [] }` 与 `{ result: [] }` ——
 *    这里统一兼容；两种都不是数组时返回空数组。
 *
 * ⚠️ 刻意**不做**可选链（`response?.data`）：原来的写法在响应为空时会抛错、
 *    由调用方的 `try/catch` 兜住并提示「加载题目失败」—— 换成可选链会把这个
 *    错误静默掉，行为就变了。
 */
export function pickArray(response: any): any[] {
  if (Array.isArray(response.data)) return response.data
  if (Array.isArray(response.result)) return response.result
  return []
}
