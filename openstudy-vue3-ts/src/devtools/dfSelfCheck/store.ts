/**
 * ds-free 自检面板 —— 状态与日志总线
 *
 * 刻意**放在模块级**（而不是面板组件的 setup 里）：
 *   · 关掉抽屉不中止运行、也不丢日志，重新打开还能看到全程；
 *   · `running` 要能当**全应用互斥锁**用（`useAgentChat.send` 也要读它），
 *     所以它不能是某个组件的局部状态。
 *
 * 这里不 import 任何 UI / Element Plus 的东西 —— 面板负责渲染，这里只负责攒数据。
 */
import { ref, reactive } from 'vue'
import type { Row } from './evaluate'

export type SelfCheckLevel = 'debug' | 'info' | 'pass' | 'fail' | 'warn' | 'error'

export interface SelfCheckLogEntry {
  /** 单调递增，用作 v-for 的 key */
  id: number
  ts: number
  level: SelfCheckLevel
  /** 来源，例如 'runLoop' / 'seed' / 'panel' */
  scope: string
  caseId?: string
  message: string
  /** 失败断言、原始事件流等需要缩进展示的多行内容 */
  detail?: string
}

/** 日志上限：超过就从头部丢。真链路一组几百行，够用；反复跑也不会吃满内存 */
const MAX_ENTRIES = 2000

export const entries = ref<SelfCheckLogEntry[]>([])
export const running = ref(false)

/**
 * 本次运行的结果行。
 *
 * 也放模块级：用户跑完真链路顺手把抽屉关了，重新打开还能看到结果、还能导出 ——
 * 结果存在组件里就会随卸载丢掉。
 */
export const rows = ref<Row[]>([])

export const progress = reactive({
  /** 当前分组名，空串表示没在跑 */
  group: '',
  total: 0,
  done: 0,
  passed: 0,
  failed: 0,
  /** 被用户中止（或超时中止）的条数 */
  aborted: 0,
  /** 正在跑哪条用例 */
  current: ''
})

/**
 * 分组级中止。
 *
 * 每条用例自己有超时，但「用户点了中止」得能**立刻**掐掉当前这条并停掉后续 ——
 * 真链路一组可能跑好几分钟，等当前用例超时是不可接受的。
 */
let _group: AbortController | null = null

/** 开跑时调一次，拿到分组级 signal 交给驱动 */
export function beginAbortGroup(): AbortSignal {
  _group = new AbortController()
  return _group.signal
}

export function abortGroup(): void {
  _group?.abort()
}

export function groupAborted(): boolean {
  return !!_group?.signal.aborted
}

/** 导出时写进文件头部的环境信息（由面板在开跑前填） */
export const runContext = reactive({
  group: '',
  startedAt: 0,
  env: {} as Record<string, string>
})

let _seq = 0

export function append(
  level: SelfCheckLevel,
  message: string,
  opt?: { caseId?: string; detail?: string; scope?: string }
): void {
  entries.value.push({
    id: ++_seq,
    ts: Date.now(),
    level,
    scope: opt?.scope || 'selfcheck',
    caseId: opt?.caseId,
    message,
    detail: opt?.detail
  })
  const over = entries.value.length - MAX_ENTRIES
  if (over > 0) entries.value.splice(0, over)
}

export function clear(): void {
  entries.value = []
  rows.value = []
}

export function beginRun(group: string, total: number, env?: Record<string, string>): void {
  running.value = true
  progress.group = group
  progress.total = total
  progress.done = 0
  progress.passed = 0
  progress.failed = 0
  progress.aborted = 0
  progress.current = ''
  runContext.group = group
  runContext.startedAt = Date.now()
  runContext.env = env || {}
  append('info', `开始运行「${group}」，共 ${total} 条`, { scope: 'run' })
}

export function endRun(): void {
  const s = ((Date.now() - runContext.startedAt) / 1000).toFixed(1)
  const tail = progress.aborted ? `，${progress.aborted} 中止` : ''
  append(
    progress.failed || progress.aborted ? 'fail' : 'pass',
    `「${progress.group}」结束：${progress.passed} 通过 / ${progress.failed} 失败${tail}，用时 ${s}s`,
    { scope: 'run' }
  )
  progress.group = ''
  progress.current = ''
  running.value = false
}

// =====================================================================
// 导出
// =====================================================================

/** `HH:mm:ss.SSS` */
function hms(ts: number): string {
  const d = new Date(ts)
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

/** 本地时间 `YYYY-MM-DD HH:mm:ss` */
function stamp(ts: number): string {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes()
  )}:${p(d.getSeconds())}`
}

/** 供文件名用：`2026-09-17T22-10-03`（不能带冒号，Windows 文件名不允许） */
export function fileStamp(): string {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
}

/** 人可读的过程日志（格式与 Node 驱动 `tests/logs/dsfree-check-*.log` 对齐，便于互相 diff） */
export function toText(): string {
  const head = [
    'ds-free OS 助手自检 —— 过程日志（浏览器面板）',
    `开始时间   ：${runContext.startedAt ? stamp(runContext.startedAt) : stamp(Date.now())}`,
    `分组       ：${runContext.group || '(未指定)'}`,
    `结果       ：${progress.passed} 通过 / ${progress.failed} 失败${
      progress.aborted ? ` / ${progress.aborted} 中止` : ''
    }`,
    ...Object.entries(runContext.env).map(([k, v]) => `${k.padEnd(10, '　')}：${v}`),
    '='.repeat(78),
    ''
  ].join('\n')

  const body = entries.value
    .map((e) => {
      const line = `[${hms(e.ts)}] [${e.level.padEnd(5)}] ${
        e.caseId ? `(${e.caseId}) ` : ''
      }${e.message}`
      return e.detail ? `${line}\n${indentDetail(e.detail)}` : line
    })
    .join('\n')

  return `${head}${body}\n`
}

/** detail 每行缩进，跟着日志行的层级走 */
function indentDetail(detail: string): string {
  return detail
    .split('\n')
    .map((l) => `                          ${l}`)
    .join('\n')
}

/** 结构化结果 —— 键名对齐 `tests/check_agent_dsfree_result.json`，方便两边对照 */
export function toJson(rows: Array<Record<string, any>>): string {
  return JSON.stringify(
    {
      when: new Date().toISOString(),
      group: runContext.group,
      elapsedSec: runContext.startedAt
        ? Number(((Date.now() - runContext.startedAt) / 1000).toFixed(1))
        : null,
      total: rows.length,
      passed: rows.filter((r) => r.status === '通过').length,
      failed: rows.filter((r) => r.status === '失败').length,
      aborted: rows.filter((r) => r.status === '中止').length,
      env: { ...runContext.env },
      rows,
      log: entries.value.map(({ id, ...rest }) => rest)
    },
    null,
    2
  )
}

/**
 * 触发浏览器下载。
 *
 * 刻意**不用 `file-saver`**：这个项目没装 `@types/file-saver`（`vue-tsc` 又是坏的，
 * 所以那 4 个已有调用点带着 TS7016 一直没被发现）。为一个日志下载再引一个新类型错误不值，
 * 原生 blob + `<a download>` 就够，仓库里也有先例（`views/front/tools/image.vue`）。
 */
export function downloadText(filename: string, text: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // 立刻 revoke 在部分浏览器上会打断下载，挪到下一个宏任务
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
