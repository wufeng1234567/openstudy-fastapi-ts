/**
 * 阶段一修复的**结构性**守门检查（补 automated 兜底，不是行为测试）
 * ============================================================================
 *
 * 为什么不是行为测试：本仓库**没有组件测试设施**（无 vitest / jest / @vue/test-utils /
 * jsdom，node_modules 里也没有 playwright / puppeteer），离线装不了，所以这两处修复
 * **无法**做「真的卸载组件 → 看监听被摘掉 / 流被 abort」级别的验证。
 * 这里退一步做源码结构断言，并且明确标注：它只能防「又把代码改回去」，
 * **不能**证明运行时行为正确。真正的行为缺口见报告里的「未覆盖」。
 *
 * 用法： node tests/check_phase1_guards.mjs
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8')

/** 去掉 block 注释与整行 // 注释（key 的说明文字里常提到被删的那个 key 名） */
function codeText(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
}

let bad = 0
const check = (name, fn) => {
  try {
    fn()
    console.log(`  \x1b[32mPASS\x1b[0m ${name}`)
  } catch (e) {
    bad++
    console.log(`  \x1b[31mFAIL\x1b[0m ${name}\n       ${e.message}`)
  }
}
const assert = (cond, msg) => {
  if (!cond) throw new Error(msg)
}

console.log('\n阶段一修复的结构性守门检查\n')

/* ── ① OsIcon：图标表里不能有重复 key ───────────────────────────────── */
check('G1 OsIcon 图标表无重复 key（pen-line / folder 曾各重复一次）', () => {
  const src = codeText(read('src/components/OsIcon/index.vue'))
  const head = 'const ICONS: Record<string, string> = {'
  const start = src.indexOf(head)
  assert(start >= 0, '找不到 ICONS 对象字面量（改名/搬走后要同步更新这条检查）')
  // 从 `{` 起做括号配平，取出整张表（值里有 ';' 但没有未转义的大括号）
  const open = start + head.length - 1
  let depth = 0
  let end = -1
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) {
        end = i
        break
      }
    }
  }
  assert(end > 0, 'ICONS 对象字面量没闭合（配平失败）')
  const body = src.slice(open + 1, end)
  // 只认「行首 + key + 冒号 + 行尾/换行」这种真正的新键；值里的 `"http://"` 不会被算进来
  const keys = [...body.matchAll(/^[ \t]*['"]?([A-Za-z0-9_-]+)['"]?[ \t]*:(?=\s|$)/gm)].map((m) => m[1])
  assert(keys.length > 10, `只扫到 ${keys.length} 个 key —— 扫描口径坏了，别当成通过`)
  const dup = keys.filter((k, i) => keys.indexOf(k) !== i)
  assert(
    dup.length === 0,
    `图标表里有重复 key：${[...new Set(dup)].join('、')} —— 对象字面量里后写的会静默覆盖前一个`
  )
})

/* ── ② AiAssistant：document 级监听必须成对摘除 + 卸载要断流 ─────────── */
check('G2 AiAssistant：paste 监听在 onUnmounted 里成对摘除', () => {
  const src = codeText(read('src/components/AiAssistant/index.vue'))
  const adds = [...src.matchAll(/document\.addEventListener\(\s*'paste'\s*,\s*([^)\s]+)/g)].map((m) => m[1])
  const removes = [...src.matchAll(/document\.removeEventListener\(\s*'paste'\s*,\s*([^)\s]+)/g)].map((m) => m[1])
  assert(adds.length === 1, `应当只在 document 上注册 1 条 paste 监听，实际 ${adds.length} 条`)
  assert(removes.length === 1, `应当在 document 上摘除 1 条 paste 监听，实际 ${removes.length} 条`)
  assert(adds[0] === removes[0], `注册用的是 ${adds[0]}、摘除用的是 ${removes[0]} —— 不是同一个函数引用，removeEventListener 认不出来，等于没删`)
  assert(
    removes[0] === 'handlePaste',
    `摘除的句柄应当是 handlePaste，实际是 ${removes[0]}（换成箭头函数/匿名函数同样删不掉）`
  )
  // 摘除动作必须落在 onUnmounted 里（写在别处等于没由生命周期兜住）
  const i = src.indexOf('onUnmounted(() => {')
  assert(i >= 0, 'AiAssistant 没有 onUnmounted')
  const body = src.slice(i, src.indexOf('\n})', i))
  assert(body.includes("removeEventListener('paste', handlePaste)"), 'paste 的摘除不在 onUnmounted 里')
})

check('G3 AiAssistant：卸载时按状态 stop / abort 正在生成的流', () => {
  const src = codeText(read('src/components/AiAssistant/index.vue'))
  const i = src.indexOf('onUnmounted(() => {')
  assert(i >= 0, 'AiAssistant 没有 onUnmounted')
  const body = src.slice(i, src.indexOf('\n})', i))
  assert(/agentStop\(\)/.test(body), 'onUnmounted 里没有调用 agentStop()（Agent 链路）')
  assert(/stream\.abort\(\)/.test(body), 'onUnmounted 里没有调用 stream.abort()（问答链路）')
  assert(/agentGenerating\.value/.test(body), 'stop 没有先看 agentGenerating 状态位')
  assert(/stream\.isGenerating\.value/.test(body), 'abort 没有先看 stream.isGenerating 状态位')
})

/* ── ③ request.ts：拦截器 reject 的 reason 形状 ──────────────────────── */
check('G4 request.ts：不再有裸字符串 reject，error handler 做了类型归一化', () => {
  const src = codeText(read('src/utils/request.ts'))
  const bare = [
    /Promise\.reject\(\s*'error'\s*\)/,
    /Promise\.reject\(\s*'未登录'\s*\)/,
    /Promise\.reject\(\s*'无效的会话/
  ]
  const hit = bare.filter((re) => re.test(src))
  assert(
    hit.length === 0,
    '还有裸字符串 reject —— 调用方 `catch (e) { e?.message }` 拿不到真实文案（应 reject Error(msg)）'
  )
  assert(
    /typeof error === 'string'/.test(src),
    '响应 error handler 没有对 string/未知形状做归一化'
  )
  assert(!/let \{ message \} = error/.test(src), 'error handler 仍在直接解构 error.message')
})

/*
 * G5 —— 只做结构性保护，别把它当成"有行为差异"的证据：
 *
 * 请求侧 rejected handler 少了 `return`，会把 rejection 吞成 fulfilled(undefined)。
 * 但在 axios 0.27.2 当前的拦截器链里**没有请求侧 rejection 会走到那里**（整个环是
 * `Promise.resolve(config)` 起手的同步段），所以这一处修完**没有可观测的行为差异** ——
 * 它既没法用调用方断言证明，也不该被说成修好了某个用户可见问题。
 * 因此这里只锁住形状：将来真有人加异步请求拦截器，形状的坑已经先被堵上。
 */
check('G5 request.ts：请求拦截器 rejected handler 必须 return Promise.reject(error)', () => {
  // 边界与切片都用 codeText 后的 src，保证偏移一致
  const src = codeText(read('src/utils/request.ts'))
  const tail = src.indexOf('service.interceptors.response.use(')
  assert(tail > 0, '找不到 service.interceptors.response.use（改了注册方式就同步更新这条检查）')
  const requestPart = src.slice(0, tail)
  const i = requestPart.lastIndexOf(') => {') // 请求侧的 rejected handler
  assert(i >= 0 && /Promise\.reject\(error\)/.test(requestPart.slice(i)), '请求拦截器没有 rejected handler')
  const body = requestPart.slice(i)
  assert(
    /return Promise\.reject\(error\)/.test(body),
    '请求侧 rejected handler 没有 return Promise.reject(error) —— rejection 会被吞成 fulfilled(undefined)'
  )
  assert(
    !/^\s*Promise\.reject\(error\)/m.test(body),
    '请求侧存在"没 return 的 Promise.reject(error)"'
  )
})

console.log(`\n通过 ${5 - bad}/5\n`)
process.exit(bad ? 1 : 0)
