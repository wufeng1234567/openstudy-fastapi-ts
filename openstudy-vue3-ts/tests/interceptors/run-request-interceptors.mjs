/**
 * request.ts 拦截器链 —— 真实链路行为测试
 * ============================================================================
 *
 * 为什么要这么写（而不是直接 `promise.then(f, r)` 口头推断）：
 *
 *   axios 0.27.2 的拦截器链是 `promise = promise.then(chain.shift(), chain.shift())`
 *   两两配对消费（`node_modules/axios/lib/core/Axios.js:82-90`），一句配对的
 *   rejected handler **只接上游的 rejection**，接不住兄弟 fulfilled 返回的 rejection。
 *   也就是说「响应拦截器 fulfilled reject 出去的东西 → **原样直达调用方**」，
 *   而「请求拦截器 reject 的东西 → 会落到响应 rejected handler」。
 *   这两条谁也别靠嘴说：脚本用**真实 axios 实例 + 真实 http adapter + 真实 TCP 后端**，
 *   断言全部写在「最终调用方 catch 到的 reason」上。
 *
 * 运行： node tests/interceptors/run-request-interceptors.mjs
 */
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'
import { createServer } from 'vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '../..')
const STUB = path.join(__dirname, 'stub-')

const require = createRequire(pathToFileURL(path.join(ROOT, 'index.html')).href)

/* ---------- 断言小工具 ---------- */
const results = []
function check(name, fn) {
  return Promise.resolve()
    .then(fn)
    .then(() => {
      results.push({ name, ok: true })
      console.log(`  \x1b[32mPASS\x1b[0m ${name}`)
    })
    .catch((e) => {
      results.push({ name, ok: false, err: e })
      console.log(`  \x1b[31mFAIL\x1b[0m ${name}\n       ${e?.stack || e}`)
    })
}
function eq(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label || '值'} 不符：期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`)
}
function ok(cond, label) {
  if (!cond) throw new Error(label || '断言不成立')
}

/* ---------- 真实后端 ---------- */
const seen = []
const backend = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1')
  seen.push(`${req.method} ${u.pathname}`)
  res.setHeader('Content-Type', 'application/json')
  const send = (obj, status = 200) => res.end(JSON.stringify(obj))
  switch (u.pathname) {
    case '/ai/bank/list':
      return send({ code: 200, msg: 'ok', data: { rows: [{ bankId: 1 }] } })
    case '/ai/bank/detail':
      // 业务错误码：既不是 401 也不是 500/601 —— 走 `code !== 200` 分支
      return send({ code: 400, msg: '题库不存在' })
    case '/auth/expired':
      return send({ code: 401, msg: '登录状态已过期' })
    case '/boom':
      return send({ code: 500, msg: '服务端炸了' })
    case '/soft-warn':
      return send({ code: 601, msg: '该内容暂不可用' })
    case '/note/draft':
      return send({ code: 200, msg: 'ok', data: { saved: true } })
    default:
      return send({ code: 200, msg: 'ok', data: { path: u.pathname } })
  }
})
const PORT = await new Promise((resolve) => backend.listen(0, '127.0.0.1', () => resolve(backend.address().port)))
const BASE = `http://127.0.0.1:${PORT}`

/* ---------- 真实 axios http adapter ---------- */
let httpAdapter
try {
  httpAdapter = require('axios/lib/adapters/http')
} catch (e) {
  httpAdapter = (await import('axios/lib/adapters/http')).default
}
if (typeof httpAdapter !== 'function') throw new Error('拿不到 axios 的真实 http adapter')

/* ---------- 加载被测模块（浏览器边界替换） ---------- */
globalThis.__REQ_TEST_STATE__ = {
  token: 'dev-token',
  userToken: 'dev-token',
  isGuest: false,
  prompts: [],
  messages: [],
  notifications: [],
  box: [],
  sessionStore: new Map(),
  localStore: new Map()
}
const STATE = globalThis.__REQ_TEST_STATE__

const server = await createServer({
  root: ROOT,
  configFile: path.join(ROOT, 'vite.config.ts'),
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'warn',
  plugins: [],
  resolve: {
    alias: [
      { find: 'element-plus', replacement: STUB + 'element-plus.mjs' },
      { find: 'file-saver', replacement: STUB + 'file-saver.mjs' },
      { find: '@/utils/auth', replacement: STUB + 'auth.mjs' },
      { find: '@/plugins/cache', replacement: STUB + 'cache.mjs' },
      { find: '@/store/modules/user', replacement: STUB + 'user-store.mjs' },
      { find: '@/utils/loginGuard', replacement: STUB + 'login-guard.mjs' },
      { find: /^@\//, replacement: path.join(ROOT, 'src') + '/' }
    ]
  },
  /*
   * ⚠️ `ssr.noExternal` 必须有 element-plus：
   *    SSR 默认把 package.json 里的依赖**外置**（走 Node require），
   *    那样 `resolve.alias` 的替换件根本不会被加载，产品模块拿到的是**真的**
   *    element-plus，UI 副作用（ElMessage / ElNotification / ElMessageBox）
   *    既不会被记录、也让断言变成"假绿"。
   *    加进 noExternal 之后，这些裸依赖才会进 Vite 的 SSR 管线，alias 才生效。
   *    （只影响测试加载方式，不动产品代码。）
   */
  ssr: { noExternal: ['element-plus', 'file-saver'] },
  optimizeDeps: { noDiscovery: true, include: [] }
})

/**
 * 被测模块入口：默认就是产品文件；`REQ_TARGET` 给变异检查用
 * （把「改回旧写法」的副本喂给同一套断言，必须 FAIL，否则说明断言是摆设）。
 */
const TARGET = process.env.REQ_TARGET || '/src/utils/request.ts'

const mod = await server.ssrLoadModule(TARGET)
const service = mod.default
if (typeof service?.request !== 'function') throw new Error('ssrLoadModule 拿到的不是 axios 实例')

service.defaults.baseURL = BASE
service.defaults.adapter = httpAdapter

/** 调用方视角：包一层 catch，把 reason 原样交回断言 */
async function caller(method, url, data, extra = {}) {
  try {
    const res = await service.request({ method, url, data, ...extra })
    return { resolved: true, value: res }
  } catch (e) {
    return { resolved: false, reason: e }
  }
}

const resetSideEffects = () => {
  STATE.prompts = []
  STATE.messages = []
  STATE.notifications = []
  STATE.box = []
}

console.log(`\nrequest.ts 拦截器真实链路测试（backend ${BASE}，被测模块 ${TARGET}）\n`)

/* ---------- 用例 ---------- */
await check('C0 基线：200 正常返回 body.data', async () => {
  const r = await caller('get', '/ai/bank/list')
  ok(r.resolved, `不应该 reject：${JSON.stringify(r)}`)
  eq(r.value.code, 200, 'res.code')
  eq(Array.isArray(r.value.data.rows), true, 'res.data.rows')
})

await check('C1 业务错误码（400）→ 调用方拿到 Error 且 message 是真实业务文案', async () => {
  resetSideEffects()
  const r = await caller('get', '/ai/bank/detail')
  eq(r.resolved, false, '应当 reject')
  const e = r.reason
  ok(e instanceof Error, `reason 应当是 Error，实际 ${Object.prototype.toString.call(e)} = ${String(e)}`)
  eq(e.message, '题库不存在', 'Error.message')
  ok(!String(e.message).includes('includes'), '不得是 TypeError 之类的 JS 报错')
  ok(
    STATE.notifications.some((n) => n.title === '题库不存在'),
    `应给过一次 ElNotification：${JSON.stringify(STATE.notifications)}`
  )
})

await check('C2 401（非静默分支）→ Error 而非裸字符串，且不产生 TypeError', async () => {
  resetSideEffects()
  STATE.token = 'dev-token'
  STATE.userToken = 'dev-token'
  const r = await caller('get', '/auth/expired')
  eq(r.resolved, false, '应当 reject')
  const e = r.reason
  ok(e instanceof Error, `reason 应当是 Error，实际 ${Object.prototype.toString.call(e)} = ${String(e)}`)
  ok(String(e.message).includes('登录'), `文案应带业务含义：${e.message}`)
  eq(STATE.box.length, 1, '应弹过一次「去重新登录」确认框')
})

await check('C3 401（登出中/无 token 的静默分支）→ Error("未登录")，不弹框', async () => {
  resetSideEffects()
  STATE.token = '' // getToken() 为空 → 静默分支
  const r = await caller('get', '/auth/expired')
  STATE.token = 'dev-token'
  eq(r.resolved, false, '应当 reject')
  ok(r.reason instanceof Error, `reason 应当是 Error，实际 ${Object.prototype.toString.call(r.reason)}`)
  eq(r.reason.message, '未登录', '静默分支文案')
  eq(STATE.box.length, 0, '静默分支不该弹框')
})

await check('C4 500 / 601 → 仍是带真实文案的 Error（回归保护）', async () => {
  for (const [p, msg] of [['/boom', '服务端炸了'], ['/soft-warn', '该内容暂不可用']]) {
    resetSideEffects()
    const r = await caller('get', p)
    eq(r.resolved, false, `${p} 应当 reject`)
    ok(r.reason instanceof Error, `${p} reason 应是 Error`)
    eq(r.reason.message, msg, `${p} 文案`)
  }
})

await check('C5 游客写操作 → reason 保持 __needLogin（对象形状不被吞掉）', async () => {
  resetSideEffects()
  STATE.token = ''
  STATE.userToken = ''
  STATE.isGuest = true
  const r = await caller('post', '/note/draft', { title: 'x' })
  STATE.token = 'dev-token'
  STATE.userToken = 'dev-token'
  STATE.isGuest = false
  eq(r.resolved, false, '应当 reject')
  const e = r.reason
  ok(e && e.__needLogin === true, `reason 必须带 __needLogin：${JSON.stringify(e)}`)
  eq(e.message, '需要登录', '原始 reason 的 message 必须保留')
  eq(STATE.prompts.length, 1, '应当只提示过一次去登录')
  eq(STATE.messages.length, 0, '该分支不该再弹 ElMessage 报错')
  eq(seen.some((s) => s.startsWith('POST /note/draft')), false, '请求不该真的发出去')
})

await check('C6 高频重复提交 → reason 保持 __repeatSubmit，且静默无提示', async () => {
  resetSideEffects()
  const body = { unique: 'repeat-' + Date.now() }
  const first = await caller('post', '/note/draft', body)
  const second = await caller('post', '/note/draft', body)
  ok(first.resolved, `第一次应当放行：${JSON.stringify(first)}`)
  eq(second.resolved, false, '第二次应被节流拦下')
  ok(
    second.reason && second.reason.__repeatSubmit === true,
    `reason 必须带 __repeatSubmit：${JSON.stringify(second.reason)}`
  )
  eq(second.reason.message, '重复提交已拦截', '原始 message 保留')
  eq(STATE.messages.length, 0, '节流拦下必须静默')
  eq(STATE.notifications.length, 0, '节流拦下必须静默')
})

await check('C7 adapter reject 字符串 → 归一化后不再 TypeError，reject 原样透出', async () => {
  resetSideEffects()
  const prevAdapter = service.defaults.adapter
  service.defaults.adapter = () => Promise.reject('boom-string')
  try {
    const r = await caller('get', '/anything')
    eq(r.resolved, false, '应当 reject')
    ok(
      !(r.reason instanceof TypeError),
      `不得把字符串错误放大成 TypeError：${String(r.reason)}`
    )
    ok(
      STATE.messages.some((m) => String(m.message).includes('boom-string')),
      `应给出可读文案：${JSON.stringify(STATE.messages)}`
    )
  } finally {
    service.defaults.adapter = prevAdapter
  }
})

await check('C8 adapter reject undefined → 有兜底文案，仍不抛 TypeError', async () => {
  resetSideEffects()
  const prevAdapter = service.defaults.adapter
  service.defaults.adapter = () => Promise.reject(undefined)
  try {
    const r = await caller('get', '/anything')
    eq(r.resolved, false, '应当 reject')
    ok(!(r.reason instanceof TypeError), `不得抛 TypeError：${String(r.reason)}`)
    eq(STATE.messages.length, 1, '应提示一次')
    ok(String(STATE.messages[0].message).length > 0, '提示文案不得为空/undefined')
  } finally {
    service.defaults.adapter = prevAdapter
  }
})

await check('C9 真实网络错误（连到未监听端口）→ Error 透出且文案可读', async () => {
  resetSideEffects()
  const prevBase = service.defaults.baseURL
  service.defaults.baseURL = 'http://127.0.0.1:1' // 基本不会有人在听的端口
  try {
    const r = await caller('get', '/nope')
    eq(r.resolved, false, '应当 reject')
    ok(r.reason instanceof Error, `网络错误应是 Error：${Object.prototype.toString.call(r.reason)}`)
    ok(!String(r.reason.message).includes('includes'), '不得是 TypeError')
    eq(STATE.messages.length, 1, '应提示一次')
  } finally {
    service.defaults.baseURL = prevBase
  }
})

await server.close()
await new Promise((resolve) => backend.close(resolve))

const failed = results.filter((r) => !r.ok)
console.log(`\n通过 ${results.length - failed.length}/${results.length}`)
if (failed.length) {
  console.log('失败用例：' + failed.map((f) => f.name).join(' | '))
  process.exit(1)
}
console.log('全部通过\n')
process.exit(0)
