/**
 * 自检的断言求值 —— 与 Node 驱动 `tests/check_agent_dsfree.mjs` 的 `main()` 同一套判据。
 *
 * 刻意独立成一个纯函数模块：它不碰 DOM、不碰状态、不碰日志，
 * 这样「有多少断言通过」这件事只有一处实现，浏览器面板与 Node 驱动不会各算各的。
 */
import type { DfCase, DfAssertTuple } from '../../../tests/df_cases.mjs'

export interface AssertRow {
  label: string
  pass: boolean
  actual: string
}

export interface Row {
  id: string
  suite: string
  title: string
  /**
   * 三态而不是两态：`中止`（用户点了中止 / 超时）必须与「断言失败」分开。
   * 把中止混成 FAIL 会让人以为代码坏了，实际只是没跑完。
   */
  status: '通过' | '失败' | '中止'
  /** 用时（秒）；协议/循环组是毫秒级，会带小数 */
  secs: number | null
  asserts: AssertRow[]
}

/** 把 `expect` 的返回值归一成结构化行 */
function toRows(tuples: DfAssertTuple[]): AssertRow[] {
  return tuples.map(([label, pass, actual]) => ({
    label: String(label ?? ''),
    pass: !!pass,
    actual: actual === undefined || actual === null ? '' : String(actual)
  }))
}

/**
 * 跑一条用例的断言。
 *
 * ⚠️ 判据必须是 `asserts.length > 0 && every(pass)` —— 空断言**算失败**。
 * 否则一条 `expect` 写崩了、返回 `[]` 的用例会被静默判成通过，那是最坏的一种假绿。
 */
export function evaluateCase(c: DfCase, ctx: any): { ok: boolean; asserts: AssertRow[] } {
  let asserts: AssertRow[]
  try {
    asserts = toRows(c.expect(ctx) || [])
  } catch (e: any) {
    // 断言函数自己抛了 —— 这是测试代码的 bug，不能吞掉，直接判失败并把原因写出来
    asserts = [
      { label: '断言函数自己抛了异常', pass: false, actual: String(e?.message || e).slice(0, 300) }
    ]
  }
  return { ok: asserts.length > 0 && asserts.every((a) => a.pass), asserts }
}
