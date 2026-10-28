/**
 * 变异检查：证明 `run-request-interceptors.mjs` 那套断言**不是摆设**
 * ============================================================================
 *
 * 做法：把 `src/utils/request.ts` 复制一份、把本次 4 处修复**逐条改回旧写法**，
 * 再用同一套断言跑它（REQ_TARGET 指向副本）—— 这些用例必须 FAIL。
 * 只要有一条没 FAIL，就说明对应断言在放着假绿。
 *
 * ⚠️ **失配即判失败**：锚点改不动了 = 这条保护已经失效，必须回来修脚本，
 *    不允许「跳过几条然后还宣称证明成立」。
 *
 * ⚠️ 请求拦截器 rejected handler 的那个 `return Promise.reject(error)`
 *    **没有可观测的调用方行为差异**（该分支在同步链路上是死路径），
 *    所以它不进变异集（变异了对用例也没影响），改由
 *    `tests/check_phase1_guards.mjs` 的 G5 做结构性保护；注释与报告里都不夸大它的作用。
 *
 * 用法： node tests/interceptors/run-mutation-check.mjs
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../..')
const SRC = path.join(ROOT, 'src/utils/request.ts')
const REL_TARGET = '/src/utils/__mut_request_for_test.ts'
const TMP = path.join(ROOT, 'src/utils/__mut_request_for_test.ts')

/**
 * 每段变异用「先定位锚点 → 在附近改一处」，而不是整段长字符串匹配
 * （注释/缩进稍有变化就失配，那种**假的成功**比失败更危险）。
 */
const MUTATIONS = [
  {
    name: '响应非 200 → 退回裸字符串 reject（应让 C1 FAIL）',
    apply(src) {
      const anchor = 'ElNotification.error({ title: msg })'
      const i = src.indexOf(anchor)
      if (i < 0) throw new Error(`找不到锚点：${anchor}`)
      const from = 'return Promise.reject(new Error(msg))'
      const j = src.indexOf(from, i)
      if (j < 0 || j - i > 400) throw new Error('锚点附近找不到 return Promise.reject(new Error(msg))')
      return src.slice(0, j) + "return Promise.reject('error')" + src.slice(j + from.length)
    }
  },
  {
    name: '401 常规分支 → 退回裸字符串 reject（应让 C2 FAIL）',
    apply(src) {
      const from = "Promise.reject(new Error('无效的会话，或者会话已过期，请重新登录。'))"
      if (!src.includes(from)) throw new Error('找不到 401 常规分支的 Error reject')
      return src.split(from).join("Promise.reject('无效的会话，或者会话已过期，请重新登录。')")
    }
  },
  {
    name: '401 静默分支 → 退回裸字符串 reject（应让 C3 FAIL）',
    apply(src) {
      const from = "Promise.reject(new Error('未登录'))"
      if (!src.includes(from)) throw new Error('找不到 401 静默分支的 Error reject')
      return src.split(from).join("Promise.reject('未登录')")
    }
  },
  {
    name: '响应 error handler → 退回类型不设防的解构（应让 C7/C8 FAIL）',
    apply(src) {
      const startTok = 'let message ='
      const endTok = "'请求失败，请稍后再试'"
      const i = src.indexOf(startTok)
      if (i < 0) throw new Error('找不到归一化后的 let message =')
      const j = src.indexOf(endTok, i)
      if (j < 0 || j - i > 400) throw new Error('找不到归一化表达式的收尾 token')
      return src.slice(0, i) + 'let { message } = error' + src.slice(j + endTok.length)
    }
  }
]

const MUST_FAIL = ['C1', 'C2', 'C3', 'C7', 'C8']

console.log('\n变异检查：把修复逐条改回旧写法，断言必须 FAIL\n')

let mutated = fs.readFileSync(SRC, 'utf8')
for (const m of MUTATIONS) {
  try {
    mutated = m.apply(mutated)
    console.log(`  · 已回退：${m.name}`)
  } catch (e) {
    console.log(`\n✗ 变异锚点失配（${m.name}）：${e.message}\n   请回来修本脚本，不要让它"跳过还宣称证明成立"\n`)
    process.exit(1)
  }
}
fs.writeFileSync(TMP, mutated, 'utf8')

let out = ''
let code = 0
try {
  const r = await promisify(execFile)(
    process.execPath,
    [path.join(__dirname, 'run-request-interceptors.mjs')],
    { cwd: ROOT, env: { ...process.env, REQ_TARGET: REL_TARGET } }
  )
  out = String(r.stdout) + String(r.stderr)
} catch (e) {
  out = String(e.stdout || '') + String(e.stderr || '')
  code = e.code ?? 1
} finally {
  fs.rmSync(TMP, { force: true })
}

// 断言 ligne 里带 ANSI 颜色码，解析前必须剥掉，否则 /FAIL (C\d+)/ 永远匹配不到
const plain = out.replace(/\[\d+m/g, '')
console.log(
  plain
    .split('\n')
    .filter((l) => l.includes('PASS') || l.includes('FAIL') || l.includes('通过 '))
    .join('\n')
)

const failedIds = [...plain.matchAll(/FAIL (C\d+)/g)].map((m) => m[1])
const missed = MUST_FAIL.filter((id) => !failedIds.includes(id))

console.log('')
if (code === 0) {
  console.log('✗ 变异版本竟然全绿 —— 断言无效，需要补强\n')
  process.exit(1)
}
if (missed.length) {
  console.log(`✗ 这些用例没抓到对应的回退：${missed.join(',')}（实际 FAIL：${failedIds.join(',') || '无'}）\n`)
  process.exit(1)
}
console.log(`✓ 变异版本按要求 FAIL：${failedIds.join(' | ')} —— 断言确实咬得住\n`)
process.exit(0)
