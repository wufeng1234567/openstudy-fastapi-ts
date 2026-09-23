/**
 * ds-free OS 助手 —— 端到端自检 / 压测
 *
 * 覆盖「用户输入 → 前端 Agent 循环 → 扩展 → DS 页面 → 工具 → 回灌 → 上屏」这条链路。
 * 用例表在 **`df_cases.mjs`**（加/改用例只动那个文件，本文件是驱动，一般不用碰）。
 *
 * ------------------------------------------------- 不想敲命令就双击这个
 *
 *   <仓库根>\scripts\run-dsfree-check.bat     ← 双击出菜单，选 1/2/3/4 即可
 *
 * ------------------------------------------------------------------ 用法
 *
 *   cd apps/fastapi-v2/openstudy-vue3-ts
 *
 *   node tests/check_agent_dsfree.mjs                  # 跑全部离线套件
 *   node tests/check_agent_dsfree.mjs --list           # 只看有哪些用例
 *   node tests/check_agent_dsfree.mjs --only DF-LOOP-  # 按 ID 前缀筛（可多次传）
 *   node tests/check_agent_dsfree.mjs --suite LOOP,PROXY
 *   node tests/check_agent_dsfree.mjs --repeat 20      # 反复压测（找偶发）
 *   node tests/check_agent_dsfree.mjs --suite LIVE     # 只看真浏览器套件（自带 --live）
 *   node tests/check_agent_dsfree.mjs --live --headless
 *   node tests/check_agent_dsfree.mjs --login-wait 0   # 前置不满足就直接结束，不留窗口
 *   node tests/check_agent_dsfree.mjs --clean          # 清掉 __df_test__ 前缀的数据
 *   node tests/check_agent_dsfree.mjs --no-color       # cmd 里颜色乱码时用这个
 *
 * ------------------------------------------------------- 七个套件怎么跑
 *
 *   LOOP / PROXY / RAG / TOOLS / UI / ROLLBACK  **离线**：把浏览器扩展和网络换掉，跑真源码。快、确定、能反复跑。
 *                            （RAG 更特殊：连扩展都不碰，只桩掉 `@/utils/request`，
 *                              验知识库 API 的请求形状与状态映射。
 *                              TOOLS 同样只桩 `/ai/agent/tools`，验「生效清单 vs 界面清单」
 *                              两个投影与开关写回。
 *                              ROLLBACK 只桩网络，验「本轮 turnId 有没有下发」与
 *                              回退接口的 `ok` 判据 —— 那两条都只在服务端留痕迹。）
 *   LIVE                     **在线**：起真 Chrome + 加载真扩展 + 连真 DS 页面。
 *
 * ------------------------------------------------------- LIVE 的前置条件
 *
 *   ① 前端 dev server 在 http://localhost:3167
 *   ② 那个浏览器 profile 里**已经登录 chat.deepseek.com**
 *   ③ 同一 profile 里已登录 OpenStudy（工具调用要鉴权）
 *
 *   ②③ 缺的时候脚本**不会把窗口一关走人** —— 带窗口时会留着窗口轮询等你登，
 *   登完自动接着跑（最多等 --login-wait 秒，默认 300）。无头模式下会直接报缺哪一条。
 *
 *   扩展是脚本用 CDP `Extensions.loadUnpacked` 动态装的，不需要你手动加载。
 *   ⚠️ 启动参数里**不能有** `--disable-extensions-except`（会把动态加载的扩展一起禁掉，
 *   而 loadUnpacked 照样返回 id，极具迷惑性）；`--load-extension` 在 Chrome 137+ 已失效。
 *
 * ------------------------------------------------------- 产物 & 清理
 *
 *   过程日志：tests/logs/dsfree-check-<时间戳>.log   ← 全程文本，ANSI 已剥掉，直接看/直接发
 *   结果 JSON：tests/check_agent_dsfree_result.json
 *   日志只留最近 20 份，更早的自动删；清理测试数据用 --clean（只认 df_cases.mjs 里的 PREFIX）
 *   删掉整套：rm -rf apps/fastapi-v2/openstudy-vue3-ts/tests
 */
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import readline from 'node:readline'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

import { LOOP_CASES, PROXY_CASES, RAG_CASES, TOOLS_CASES, UI_CASES, ROLLBACK_CASES, LIVE_CASES, PREFIX, AGENT_TOOLS } from './df_cases.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const VUE_ROOT = path.resolve(__dirname, '..')
// apps/fastapi-v2/openstudy-vue3-ts → 回退三级才是仓库根（少写一级会变成 apps/…）
const REPO_ROOT = path.resolve(VUE_ROOT, '../../..')
const EXT_DIR = path.join(REPO_ROOT, 'apps/deepseek-proxy/extension')
const OUT_JSON = path.join(__dirname, 'check_agent_dsfree_result.json')
const DEV_SERVER = process.env.DF_DEV_SERVER || 'http://localhost:3167'
const CHROME =
  process.env.DF_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const CDP_PORT = Number(process.env.DF_CDP_PORT || 9366)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
// 颜色：默认开。cmd 双击跑时若不显示颜色/出现 `←[2m` 乱码，用 --no-color 或设 NO_COLOR=1
const NO_COLOR = process.env.NO_COLOR != null || process.argv.includes('--no-color')
const paint = (code) => (s) => (NO_COLOR ? String(s) : `\x1b[${code}m${s}\x1b[0m`)
const C = {
  dim: paint(2),
  green: paint(32),
  red: paint(31),
  yellow: paint(33),
  cyan: paint(36),
  bold: paint(1)
}

// =====================================================================
// 过程日志：除了结果 JSON，再留一份**人能直接看**的全程文本日志
// =====================================================================
// 做法是给 console 挂个 tee —— 这样 Vite SSR、CDP、断言等所有输出
// （包括将来新加的）都会自动进日志，不用逐个调用点去改。
// 写进文件前把 ANSI 颜色码剥掉，否则记事本/VSCode 里全是乱码。
const LOG_DIR = process.env.DF_LOG_DIR || path.join(__dirname, 'logs')
/** 日志目录只留最近这么多份 —— 反复压测时不至于把磁盘堆满 */
const KEEP_LOGS = 20
const LOG_STAMP = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
const ANSI_RE = /\x1b\[[0-9;]*m/g

const fmtArg = (a) => {
  if (a instanceof Error) return a.stack || a.message
  if (typeof a === 'string') return a
  try {
    return JSON.stringify(a)
  } catch {
    return String(a)
  }
}

let LOG_FILE = ''
let LOG_READY = false
/** 初始化日志文件；失败也不影响主流程（只是没有日志而已） */
function initLog() {
  // 交互式菜单只是个转发器，真正的活是它 spawn 的子进程干的 —— 菜单本身不留日志，
  // 免得开几次菜单就把真正的运行日志挤出保留窗口（只留最近 20 份）
  if (process.argv.includes('--menu')) return
  try {
    fs.mkdirSync(LOG_DIR, { recursive: true })
    LOG_FILE = path.join(LOG_DIR, `dsfree-check-${LOG_STAMP}.log`)
    const head = [
      'ds-free OS 助手自检 —— 过程日志',
      `开始时间   ：${new Date().toLocaleString('zh-CN')}`,
      `命令行     ：node ${process.argv.slice(1).join(' ')}`,
      `工作目录   ：${process.cwd()}`,
      `Node       ：${process.version}  ${process.platform} ${process.arch}`,
      `Chrome     ：${CHROME}`,
      `dev server ：${DEV_SERVER}`,
      `Chrome 端口：${CDP_PORT}`,
      `扩展目录   ：${EXT_DIR}`,
      `用例表     ：${path.join(__dirname, 'df_cases.mjs')}`,
      `结果 JSON  ：${OUT_JSON}`,
      '='.repeat(78),
      ''
    ].join('\n')
    fs.writeFileSync(LOG_FILE, head, 'utf8')
    LOG_READY = true
  } catch (e) {
    LOG_READY = false
    // 这里不能走 console.log（会递归回 append），直接写 stderr
    process.stderr.write(`[log] 日志文件创建失败，本次不记录过程日志：${e?.message || e}\n`)
  }
}
function logAppend(prefix, args) {
  if (!LOG_READY) return
  const line = prefix + args.map(fmtArg).join(' ')
  try {
    fs.appendFileSync(LOG_FILE, line.replace(ANSI_RE, '') + '\n', 'utf8')
  } catch {
    /* 磁盘写不进去就算了，别把测试搞挂 */
  }
}
initLog()

const _log = console.log.bind(console)
const _err = console.error.bind(console)
console.log = (...a) => {
  _log(...a)
  logAppend('', a)
}
console.error = (...a) => {
  _err(...a)
  logAppend('[stderr] ', a)
}

// =====================================================================
// CLI
// =====================================================================
function parseArgs(argv) {
  const out = {
    only: [],
    suite: null,
    repeat: 1,
    live: false,
    clean: false,
    list: false,
    verbose: false,
    // LIVE 默认**带窗口**：首次要手动登录 chat.deepseek.com，无头没法登
    headed: true,
    // LIVE 带窗口时，前置条件没满足就留着窗口等用户登录，最多等这么久（秒；0 = 不等）
    loginWait: 300,
    // 交互式菜单（给双击 .bat 用；见文件末尾 runMenu 的注释说明为什么菜单在 Node 里）
    menu: false
  }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--only') out.only.push(argv[++i])
    else if (a.startsWith('--only=')) out.only.push(a.slice(7))
    else if (a === '--suite') {
      out.suite = (argv[++i] || '').split(',').map((s) => s.trim()).filter(Boolean)
      // `--suite LIVE` 本身就是「要跑真浏览器」的意思，省得再记一个 --live
      if (out.suite.includes('LIVE')) out.live = true
    }
    else if (a === '--repeat') out.repeat = Math.max(1, Number(argv[++i]) || 1)
    else if (a === '--live') out.live = true
    else if (a === '--headed') out.headed = true
    else if (a === '--headless') out.headed = false
    else if (a === '--login-wait') out.loginWait = Math.max(0, Number(argv[++i]) || 0)
    else if (a.startsWith('--login-wait=')) out.loginWait = Math.max(0, Number(a.slice(13)) || 0)
    else if (a === '--clean') out.clean = true
    else if (a === '--menu') out.menu = true
    else if (a === '--list') out.list = true
    else if (a === '--verbose' || a === '-v') out.verbose = true
    else if (a === '--help' || a === '-h') out.help = true
  }
  return out
}

const ARGS = parseArgs(process.argv.slice(2))

if (ARGS.help) {
  console.log(fs.readFileSync(fileURLToPath(import.meta.url), 'utf8').split('*/')[0])
  process.exit(0)
}

// =====================================================================
// 用例筛选
// =====================================================================
const ALL = [
  ...LOOP_CASES.map((c) => ({ ...c, suite: 'LOOP' })),
  ...PROXY_CASES.map((c) => ({ ...c, suite: 'PROXY' })),
  ...RAG_CASES.map((c) => ({ ...c, suite: 'RAG' })),
  ...UI_CASES.map((c) => ({ ...c, suite: 'UI' })),
  ...TOOLS_CASES.map((c) => ({ ...c, suite: 'TOOLS' })),
  ...ROLLBACK_CASES.map((c) => ({ ...c, suite: 'ROLLBACK' })),
  ...LIVE_CASES.map((c) => ({ ...c, suite: 'LIVE' }))
]

function selected() {
  let list = ALL
  if (!ARGS.live) list = list.filter((c) => c.suite !== 'LIVE')
  if (ARGS.suite?.length) list = list.filter((c) => ARGS.suite.includes(c.suite))
  if (ARGS.only.length) list = list.filter((c) => ARGS.only.some((p) => c.id.startsWith(p)))
  return list
}

if (ARGS.list) {
  const bySuite = {}
  for (const c of ALL) (bySuite[c.suite] ||= []).push(c)
  for (const [suite, cs] of Object.entries(bySuite)) {
    console.log(`\n${C.bold(suite)}  ${C.dim(`(${cs.length})`)}`)
    for (const c of cs) console.log(`  ${c.id.padEnd(14)} ${c.title}`)
  }
  console.log(`\n共 ${ALL.length} 条。筛选用 --only / --suite，跑真浏览器加 --live`)
  console.log(C.dim(`\n过程日志：${LOG_FILE || '(未写成功)'}\n`))
  pruneLogs()
  process.exit(0)
}

// =====================================================================
// 通用：Vite SSR 装载（带模块桩）
// =====================================================================
const STUB_PREFIX = '\0df-stub:'

/**
 * 起一个只用于 SSR 装载模块的 vite server。
 *
 * ⚠️ 桩必须用 `\0` 前缀 + 按**绝对路径后缀**匹配：vite.config 里的 alias 插件也是
 *    `enforce:'pre'` 且排在我们前面，等轮到我们时 id 已经被换成绝对路径了。
 */
async function makeLoader(stubs) {
  const keyOf = (id) => {
    const norm = String(id).replace(/\\/g, '/')
    for (const key of Object.keys(stubs)) {
      const rel = key.replace(/^@\//, '')
      if (norm === key || norm.endsWith(`/src/${rel}.ts`)) return key
    }
    return ''
  }
  const server = await createServer({
    root: VUE_ROOT,
    logLevel: 'error',
    // ⚠️ **必须用独立的 cacheDir**，否则会把你正在跑的 dev server 搞坏。
    //
    //    Vite 的默认 cacheDir 是 `node_modules/.vite` —— 和 `npm run dev` 的**同一个**。
    //    这个 loader 一样会跑依赖预构建、重写 `_metadata.json` / `deps/`，
    //    于是 dev server 里已加载模块引用的旧 hash 全部失效：
    //    症状是 dev server 开始对 `/node_modules/.vite/deps/*.js` 回
    //    **504 (Outdated Optimize Dep)**，页面上任何动态 import 都失败
    //    （`Failed to fetch dynamically imported module`），而且**不会自愈**。
    //    如果 loader 在预构建途中被结束（脚本跑完就 close），`deps/` 还可能被留成缺失状态。
    //    这个坑真踩过：跑了几次自检之后 dev server 就再也加载不出页面了，
    //    `/node_modules/.vite/deps/` 直接是空的。
    cacheDir: 'node_modules/.vite-dftest',
    server: { middlewareMode: true },
    appType: 'custom',
    plugins: [
      {
        name: 'df-stub',
        enforce: 'pre',
        resolveId(id) {
          const k = keyOf(id)
          if (k) return STUB_PREFIX + k
        },
        load(id) {
          if (id.startsWith(STUB_PREFIX)) return stubs[id.slice(STUB_PREFIX.length)]
        }
      }
    ]
  })
  return { server, load: (id) => server.ssrLoadModule(id) }
}

/** 与 DOM / 网络无关的几个工具模块，统一用这个桩 */
const SAFE_STUBS = {
  '@/utils/auth': `export function getToken(){ return 'df-test-token' }`,
  '@/utils/doc-parse': `
    export const DOC_UPLOAD_MAX_IMAGES = 8
    export function parseDocFile(){ return { text: '', images: [] } }
    export function dataUrlToFile(){ return null }
    export function extFromMime(){ return 'txt' }
    export async function parseFileToBlocks(){ return { blocks: [], images: [] } }
  `,
  '@/utils/image-compress': `
    export function compressImageDataUrl(_n, d){ return Promise.resolve(d) }
    export function mimeOfDataUrl(){ return 'image/png' }
    export function dataUrlByteSize(){ return 0 }
  `
}

const jsonRes = (o) => ({
  ok: true,
  status: 200,
  async json() { return o },
  async text() { return JSON.stringify(o) }
})

/**
 * LOOP 组桩的「写 / 破坏性 action 清单」（与浏览器驱动 `runLoopGroup.ts` 的 `STUB_TOOLS`
 * **必须逐字一致** —— 否则同一条用例两个驱动判定不同，这是红线）。
 *
 * 与后端 `ai.py:_agent_tools_payload` 同一形状：只列**有写 / 破坏性 action** 的工具
 * （`knowledge_search` / `memory_search` 这类只读工具本来就不在里面）。
 */
const STUB_LOOP_ACTIONS = {
  bank_manage: { write: ['create', 'update'], destructive: ['delete', 'delete_many'] },
  question_manage: { write: ['create'], destructive: ['delete', 'delete_many'] },
  // 非破坏性写操作的样本（DF-LOOP-56/57/58）—— 「写操作 × autoConfirm=false」这一格
  // 只有非破坏性动作才判得出来（破坏性恒需确认，缺不缺 autoConfirm 结论一样）。
  note_manage: { write: ['create', 'update'], destructive: ['delete', 'delete_many'] }
}

/**
 * 「这一次调用在**服务端**是否需要确认」—— 确认票据校验用的判据。
 *
 * ⚠️ 刻意在桩里**重算一遍**，不引用被测代码的 `needConfirm()`：引用它就成了
 *    「自己证明自己」，前端少弹一次卡片时两边一起错、用例照样绿。
 *    判据与后端 `loop.needs_user_confirmation` 同口径：破坏性恒需要；
 *    写操作只在 `autoConfirm === false` 时需要（`autoConfirm` 直接读请求体）。
 */
const stubNeedsConfirm = (body) => {
  const meta = STUB_LOOP_ACTIONS[body?.tool]
  if (!meta) return false
  const a = String(body?.params?.action || '')
  if (meta.destructive.includes(a)) return true
  if (meta.write.includes(a)) return body.autoConfirm === false
  return false
}

// =====================================================================
// 套件 1：LOOP —— 真 Agent 循环 + 脚本化模型
// =====================================================================
async function runLoopCases(cases) {
  const run = {
    modelScript: [],
    toolScript: [],
    chunkSize: 0,
    throwOnce: false,
    deepThinkResults: [],
    //: 每轮的**推理文本**（深度思考）。和 `deepThinkResults` 不是一回事 ——
    //: 那个是「开关状态」，这个是模型真正吐出来的思考内容。
    reasoning: [],
    answerConfirm: true,
    //: `/ai/agent/context` 的两段文本：`runtimeContext` 进系统提示词，`history` 进首轮用户消息
    runtimeContext: '',
    history: '',
    //: `/ai/agent/preview` 的桩形态（`{ result }` / `{ throws }` / `{ status }` / `{ ticket }`）
    //: ⚠️ `ticket` 不传 ≠ 无条件发一张：发不发票**按服务端口径**（读请求体里的 `autoConfirm`，
    //: 见下面 preview 分支里的 `stubNeedsConfirm`）。与浏览器驱动 `runLoopGroup.ts` 逐字一致。
    previewStub: null,
    //: 第 1 / 2 / 3… 次 `GET /ai/agent/tools` 的状态码（超出数组长度一律 200）—— 造「元信息拉不到」
    toolsStatuses: []
  }
  const rec = { round: 0, tool: 0, deepThink: 0, toolsGet: 0 }
  /**
   * 服务端**已下发的确认票据**（预演时记下来）与**已被用掉**的票据。
   *
   * 合同 v1：票据一次性 —— 用过的再传一次要被拒。桩里也照这个来，
   * 否则「前端把上一张票据拿去复用」这种错法在本地永远测不出来。
   */
  const issuedTickets = new Set()
  const usedTickets = new Set()

  const stubs = {
    ...SAFE_STUBS,
    '@/utils/ds-proxy': `
      export async function chatWithDSAccumulated(o) {
        return globalThis.__DF.chat(o)
      }
      export async function ensureDeepThink(on) { return globalThis.__DF.ensureDeepThink(on) }
      export async function getDeepThink() { return null }
      export async function setDeepThink() { return true }
    `
  }

  globalThis.__DF = {
    chat: async (o) => {
      const r = rec.round
      rec.round += 1
      globalThis.__DF_ROUNDS.push({ round: r, systemPrompt: o.systemPrompt || '', userMessage: o.userMessage || '' })
      if (run.throwOnce && r === 0) throw new Error('扩展连接中断（脚本注入）')
      // 思考过程：真链路里 `chatWithDSAccumulated` 交给调用方的是**累积**全文
      // （见那边的归一化 + 节流逻辑），所以桩这里也按累积回调 ——
      // 「上游给累积、agentDsFree 自己 diff 成增量」这一步正是要测的东西。
      const reasoning = run.reasoning[Math.min(r, run.reasoning.length - 1)] || ''
      if (reasoning) {
        const rsize = Math.max(1, Math.ceil(reasoning.length / 3))
        for (let i = 0; i < reasoning.length; i += rsize) {
          o.onThinking?.(reasoning.slice(0, i + rsize))
          await sleep(0)
        }
      }
      const full = run.modelScript[Math.min(r, run.modelScript.length - 1)] || ''
      const size = run.chunkSize > 0 ? run.chunkSize : Math.max(1, Math.ceil(full.length / 2))
      for (let i = 0; i < full.length; i += size) {
        o.onChunk?.(full.slice(0, i + size))
        await sleep(0)
      }
      if (!full) o.onChunk?.('')
      return full
    },
    ensureDeepThink: async (on) => {
      const i = rec.deepThink
      rec.deepThink += 1
      // 记下**实参**：用例要断言「目标是开」而不是只看调用次数
      globalThis.__DF_DT.push(on)
      return run.deepThinkResults[Math.min(i, run.deepThinkResults.length - 1)] || { ok: true, changed: false, was: true }
    }
  }

  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    const u = String(url)
    if (u.includes('/ai/agent/tools')) {
      // 「元信息拉不到」：状态码脚本化（DF-LOOP-52 用它造 `_toolsCache` 恒为 null 的现场）
      rec.toolsGet += 1
      const status = run.toolsStatuses[rec.toolsGet - 1] || 200
      if (status >= 400) return badRes(status)
      return jsonRes({
        tools: [{ function: { name: 'bank_manage', description: 'Manage question banks' } }],
        actions: STUB_LOOP_ACTIONS
      })
    }
    // 运行时背景（长期记忆摘要 + 知识库清单）—— 用例用 runtimeContext 指定，
    // 断言它被原样拼进系统提示词（两条链路上下文一致的红线）。
    // `history` 同理：短期会话历史，断言它只在本会话第一轮拼进用户消息。
    if (u.includes('/ai/agent/context')) {
      return jsonRes({ context: run.runtimeContext ?? '', history: run.history ?? '' })
    }
    if (u.includes('/ai/agent/execute')) {
      const body = JSON.parse(init?.body || '{}')
      const i = rec.tool
      rec.tool += 1
      globalThis.__DF_TOOLCALLS.push(`${body.tool}.${body.params?.action}`)
      // 请求体也留一份：断言「需要确认时带了票据 / 不需要时不带」
      globalThis.__DF_EXEC_BODIES.push(body)
      // ---- 服务端侧的确认票据闸门（契约 v1）----
      // 需要确认的调用**必须**带上「本次会话下发过、且还没用过」的票据，否则拒绝执行。
      // ⚠️ 与 api-core 的契约同源：票据一次性 / 绑定用户+工具+参数；这里只演「有没有、用过没」
      //    这一层（不演 TTL 与哈希绑定 —— 那是服务端单测的事）。
      if (stubNeedsConfirm(body)) {
        const tk = body.confirmTicket
        if (typeof tk !== 'string' || !tk || !issuedTickets.has(tk) || usedTickets.has(tk)) {
          return jsonRes({
            success: false,
            error: '确认票据缺失或已失效，已拒绝执行',
            hint: '请重新发起该操作并完成二次确认'
          })
        }
        usedTickets.add(tk)
      }
      const r = run.toolScript[Math.min(i, run.toolScript.length - 1)] ?? { success: true }
      return jsonRes(r)
    }
    // 写操作预演（确认卡片的 preview + 一次性确认票据）。桩形态见 df_cases.d.mts 的 `previewStub`：
    // 正常返回 / 网络层抛错 / HTTP 非 2xx —— 后两种都必须让前端降级成空值且照常弹卡片。
    // ⚠️ 放在 `/ai/agent/execute` 之后判：两个 URL 前缀不同，但保持「具体在前」的顺序更稳。
    if (u.includes('/ai/agent/preview')) {
      const body = JSON.parse(init?.body || '{}')
      globalThis.__DF_PREVIEWS.push(body)
      const s = run.previewStub || {}
      if (s.throws) throw new Error('preview 接口网络异常（脚本注入）')
      if (s.status && s.status >= 400) {
        return {
          ok: false,
          status: s.status,
          async json() {
            return {}
          },
          async text() {
            return ''
          }
        }
      }
      // `raw` = 把整个响应体原样返回（200）。用来造**非本接口的形状**：
      // catch_all 假成功 `{code,msg,data:null}` / `fail()` 信封 —— 见 DF-LOOP-39/40
      if (s.raw !== undefined) {
        // 原样返回也要把票据收下（票据就在响应体里，契约如此）
        if (typeof s.raw?.confirmTicket === 'string' && s.raw.confirmTicket) {
          issuedTickets.add(s.raw.confirmTicket)
        }
        return jsonRes(s.raw)
      }
      // 票据：不传 = **按服务端判据**决定发不发；`ticket: ''` = **不下发票据**（造「服务端没给」）；
      // 传字符串 = 钉死票值。
      //
      // ⚠️⚠️ `ticket` 不传时**不再是无条件发一张**：真服务端 `preview_agent_tool` 是
      //    `if needs_user_confirmation(tool, params, auto_confirm): result["confirmTicket"] = …`
      //    ——判据**读请求体里的 autoConfirm**（与执行侧同一个函数）。
      //    桩里必须演这一层，否则 DF-LOOP-56 那种「前端漏传 autoConfirm ⇒ 服务端按 true 判
      //    ⇒ 不发票据」的死锁在本地**测不出来**（桩会慷慨地发一张，用例假绿）。
      //    判据复用 `stubNeedsConfirm`（同一个函数，保证「发不发票」与「要不要校验票」同源）。
      //    既有用例用的都是破坏性动作（恒需确认）或显式传了 `ticket`，行为不变。
      const ticket =
        s.ticket !== undefined
          ? s.ticket
          : stubNeedsConfirm(body)
            ? `tk-${globalThis.__DF_PREVIEWS.length}`
            : ''
      if (ticket) issuedTickets.add(ticket)
      const out = { preview: s.result ?? {} }
      if (ticket) out.confirmTicket = ticket
      return jsonRes(out)
    }
    return jsonRes({})
  }

  const { server, load } = await makeLoader(stubs)
  const mod = await load('@/api/ai/agentDsFree')

  const results = []
  try {
    for (const c of cases) {
      // 复位
      run.modelScript = c.model || []
      run.toolScript = c.tools || []
      run.chunkSize = c.chunkSize || 0
      run.throwOnce = !!c.throwOnce
      run.deepThinkResults = c.deepThink || []
      run.reasoning = c.reasoning || []
      run.answerConfirm = c.answerConfirm !== false
      run.runtimeContext = c.runtimeContext || ''
      run.history = c.history || ''
      run.previewStub = c.previewStub || null
      run.toolsStatuses = c.agentToolsGetStatus || []
      rec.round = 0
      rec.tool = 0
      rec.deepThink = 0
      rec.toolsGet = 0
      issuedTickets.clear()
      usedTickets.clear()
      // ⚠️ 必须清缓存：`fetchAgentTools` / `fetchAgentContext` 都是**模块级缓存**，
      //    而所有用例共用同一个模块实例。不清的话，第一个用例拉到的运行时背景
      //    会被后面所有用例复用 —— 那些「注入为空」的用例就测不出东西了。
      mod.resetAgentToolsCache()
      // ⚠️ 「已注入过历史的 sessionId」同样是**模块级**状态：不清的话，前一条用例
      //    留下的 sessionId 会让后一条的「第一轮注入」静默失效（浏览器驱动同步要清）。
      mod.resetHistoryInjection()

      const events = []
      const confirms = []
      globalThis.__DF_ROUNDS = []
      globalThis.__DF_TOOLCALLS = []
      globalThis.__DF_DT = []
      globalThis.__DF_PREVIEWS = []
      globalThis.__DF_EXEC_BODIES = []

      // 缺省只跑一次、且不传 sessionId（老用例行为完全不变）。
      // 传了 `sessionIds` 就按顺序连着跑多次 —— 历史注入是**跨调用**的会话级行为，
      // 单次调用里测不到（见 df_cases.d.mts 里 `sessionIds` 的说明）。
      const sessionIds = c.sessionIds?.length ? c.sessionIds : ['']

      // 捕获 `console.warn`：`fetchToolPreview` 的「响应缺 `preview` 键」警告**是新逻辑的一部分**
      //（用来区分「合法业务答复」与「路由没对上」），不抓就断言不到那条分支 —— 见 DF-LOOP-39/40。
      const warns = []
      const realWarn = console.warn
      console.warn = (...a) => {
        warns.push(a.map((x) => String(x)).join(' '))
      }

      let answer = ''
      let thrown = ''
      try {
        for (const sid of sessionIds) {
          answer = await mod.runDsFreeAgentStream(
            {
              message: c.prompt || '测试',
              model: 'deepseek-free',
              userId: 1,
              sessionId: sid || undefined,
              // 本轮 id（一次提问一个）—— 用例用它断言「原样进 `/ai/agent/execute` 请求体」。
              // ⚠️ 浏览器驱动（`runLoopGroup.ts`）必须同样读这个字段（LOOP 组面板会跑）。
              turnId: c.turnId,
              autoConfirm: c.opts?.autoConfirm !== false,
              maxLoops: c.opts?.maxLoops
            },
            {
              onEvent: (e) => events.push(e),
              onConfirm: async (info) => {
                confirms.push(info)
                return run.answerConfirm
              }
            }
          )
        }
      } catch (e) {
        thrown = String(e?.message || e)
      } finally {
        console.warn = realWarn
      }

      const ctx = {
        events,
        eventTypes: events.map((e) => e.type),
        answer: String(answer || ''),
        toolCalls: [...globalThis.__DF_TOOLCALLS],
        fedToModel: globalThis.__DF_ROUNDS.map((r) => r.userMessage),
        sysPrompts: globalThis.__DF_ROUNDS.map((r) => r.systemPrompt),
        deepThinkCalls: [],
        confirms,
        //: `/ai/agent/preview` 收到的请求体（每条用例复位）—— 断言「弹卡片前调过、参数形状对」
        previewCalls: [...globalThis.__DF_PREVIEWS],
        //: `/ai/agent/execute` 收到的请求体（每条用例复位）—— 断言「需要确认时带了 confirmTicket」
        execBodies: [...globalThis.__DF_EXEC_BODIES],
        //: 本用例期间 `console.warn` 收到的文本 —— 断言那条「响应缺 preview 键」的告警有没有响
        warnings: warns,
        thrown
      }
      ctx.deepThinkCalls = [...globalThis.__DF_DT]
      results.push({ case: c, ctx })
    }
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
  return results
}

// =====================================================================
// 套件 2：PROXY —— 真 ds-proxy.ts + 假 window.DSProxy
// =====================================================================
async function runProxyCases(cases) {
  let impl = {}

  const stubs = { ...SAFE_STUBS, '@/utils/ds-proxy': '__REAL__' }
  const keyOf = (id) => {
    const norm = String(id).replace(/\\/g, '/')
    for (const key of Object.keys(stubs)) {
      const rel = key.replace(/^@\//, '')
      if (norm === key || norm.endsWith(`/src/${rel}.ts`)) return key
    }
    return ''
  }
  const server = await createServer({
    root: VUE_ROOT,
    logLevel: 'error',
    // 同上（makeLoader 那里有完整说明）：独立 cacheDir，别动 dev server 的 node_modules/.vite
    cacheDir: 'node_modules/.vite-dftest',
    server: { middlewareMode: true },
    appType: 'custom',
    plugins: [
      {
        name: 'df-proxy-stub',
        enforce: 'pre',
        resolveId(id) {
          const k = keyOf(id)
          // ds-proxy 走真代码，别桩
          if (k && k !== '@/utils/ds-proxy') return STUB_PREFIX + k
        },
        load(id) {
          if (id.startsWith(STUB_PREFIX)) return stubs[id.slice(STUB_PREFIX.length)]
        }
      }
    ]
  })

  // 假扩展：`window.DSProxy` 是个**构造函数**（真 SDK 就是这么挂的）
  globalThis.window = globalThis.window || {}
  globalThis.window.DSProxy = class {
    constructor() {
      const self = this
      for (const k of ['getStatus', 'getDeepThink', 'setDeepThink', 'sendMessageWithImages', 'sendMessage']) {
        this[k] = (...a) => impl[k]?.(...a)
      }
      void self
    }
  }

  const proxy = await server.ssrLoadModule('@/utils/ds-proxy')

  const results = []
  try {
    for (const c of cases) {
      impl = {}
      proxy.resetDSProxy()
      const ctx = {
        proxy,
        fakeDS: (o) => {
          impl = o
          proxy.resetDSProxy()
        }
      }
      let r
      let thrown = ''
      try {
        r = await c.run(ctx)
      } catch (e) {
        thrown = String(e?.message || e)
        r = { thrown }
      }
      results.push({ case: c, ctx: { ...r, thrown } })
    }
  } finally {
    await server.close()
  }
  return results
}

// =====================================================================
// 套件 3：RAG —— 知识库前端 API（桩掉 request，只验请求形状与状态映射）
// =====================================================================
async function runRagCases(cases) {
  const stubs = {
    ...SAFE_STUBS,
    // 桩掉 axios 封装：不真发请求，只把调用形状记下来给用例断言。
    // 录 `data` 必须**原样**留着（不能序列化）—— 上传用例要看它是不是 FormData、
    // 里面的 File 还带不带原始文件名，转成 JSON 就什么都验不出来了。
    '@/utils/request': `
      export default function request(config) {
        ;(globalThis.__RAG_CALLS ||= []).push({
          url: config.url,
          method: String(config.method || '').toLowerCase(),
          params: config.params || null,
          data: config.data || null,
          headers: config.headers || null
        })
        return Promise.resolve(globalThis.__RAG_RESPONSE)
      }
    `
  }

  globalThis.__RAG_CALLS = []
  globalThis.__RAG_RESPONSE = { code: 200, data: null }

  const { server, load } = await makeLoader(stubs)
  const mod = await load('@/api/ai/rag')

  const results = []
  try {
    for (const c of cases) {
      globalThis.__RAG_CALLS = []
      globalThis.__RAG_RESPONSE = c.response ?? { code: 200, data: null }

      let result = null
      let thrown = ''
      try {
        if (c.call) {
          const fn = mod[c.call]
          if (typeof fn !== 'function') throw new Error(`模块里没有导出函数 ${c.call}`)
          result = await fn(...(c.args || []))
        }
      } catch (e) {
        thrown = String(e?.message || e)
      }

      results.push({
        case: c,
        ctx: {
          calls: [...globalThis.__RAG_CALLS],
          call: globalThis.__RAG_CALLS[0] || null,
          result,
          thrown,
          /** 整个模块：纯函数类用例（类型判定 / 状态映射）直接调 */
          module: mod
        }
      })
    }
  } finally {
    await server.close()
  }
  return results
}

// =====================================================================
// 套件 4：UI —— 真 useAgentChat + 脚本化事件流
// =====================================================================
async function runUiCases(cases) {
  let script = []
  // 全局的 `__DF_*`：桩模块（跑在 vite SSR 里）与被测代码之间唯一的通道。
  // 每条用例复位，避免上一条的产物被下一条当成自己的。
  globalThis.__DF_EVENTS__ = []
  globalThis.__DF_SEND_OPTS = []
  globalThis.__DF_TIMELINES = []
  globalThis.__DF_ROLLBACK_CALLS = []
  globalThis.__DF_ROLLBACK_RESULT = { ok: true, reason: '', reverted: 0, skipped: [], failed: [], partial: [] }
  globalThis.__DF_STREAM_THROWS = []
  const stubs = {
    ...SAFE_STUBS,
    '@/api/ai/ai': `
      export function saveAgentTimeline(sid, tl){ globalThis.__DF_TIMELINES.push({ sid, tl }); return Promise.resolve({}) }
      export function getConversationHistory(){ return Promise.resolve({}) }
      export function attachmentPlaceholder(){ return {} }
      export function fillAttachmentMetas(){ return Promise.resolve() }
    `,
    '@/api/ai/agent': `
      export function postAgentStream(){ return Promise.resolve('') }
      export function confirmAgentTool(){ return Promise.resolve() }
      export function normalizeAgentImages(a){ return a || [] }
      // 回退接口的替身：把**实参**记下来（用例要断言「传的是这一轮的 id / send 用过的会话」），
      // 返回脚本化的结果（形状与真接口的成功/失败返回逐字一致）。
      export function rollbackAgentTurn(params){
        globalThis.__DF_ROLLBACK_CALLS.push(params)
        return Promise.resolve(globalThis.__DF_ROLLBACK_RESULT)
      }
    `,
    '@/api/ai/agentDsFree': `
      export async function runDsFreeAgentStream(o, h) {
        // 记下**实参**：断言「下发给链路的 turnId == 标记里的 turnId」
        globalThis.__DF_SEND_OPTS.push(o)
        const mode = globalThis.__DF_STREAM_MODE || ''
        if (mode) {
          globalThis.__DF_STREAM_THROWS.push(mode)
          const err = new Error(mode === 'abort' ? '已中止（脚本注入）' : '工具执行异常（脚本注入）')
          // ⚠️ 中止必须带 \`name === 'AbortError'\`：\`useAgentChat\` 靠它区分「用户主动停止」
          //    与「真的报错」（前者不插错误提示卡）。
          if (mode === 'abort') err.name = 'AbortError'
          throw err
        }
        for (const e of globalThis.__DF_EVENTS__) {
          h.onEvent?.(e)
          await new Promise((r) => setTimeout(r, 0))
        }
        return 'FINAL'
      }
      export function fetchAgentTools(){ return Promise.resolve([]) }
    `
  }
  globalThis.fetch = async () => jsonRes({})
  const { server, load } = await makeLoader(stubs)
  const { useAgentChat } = await load('@/composables/useAgentChat')

  const results = []
  try {
    for (const c of cases) {
      const chat = useAgentChat()
      let thrown = ''
      // 每条用例复位（上一轮的产物不许流到下一轮）
      globalThis.__DF_SEND_OPTS = []
      globalThis.__DF_TIMELINES = []
      globalThis.__DF_ROLLBACK_CALLS = []
      globalThis.__DF_STREAM_THROWS = []
      globalThis.__DF_STREAM_MODE = c.streamThrows || ''
      globalThis.__DF_ROLLBACK_RESULT =
        c.rollback?.result || { ok: true, reason: '', reverted: 0, skipped: [], failed: [], partial: [] }
      // `eventsRuns` = 连着跑**多次** `send()`（每次喂一组事件）—— 用来测**跨提问**的行为
      //（最典型的是「执行统计是会话累计，不是只显示最后一次提问」，见 DF-UI-07；
      //  以及「每轮各有一条 turn_end 标记」，见 DF-UI-11）。
      // 不传时行为与以前完全一样：只跑一次、用 `events`。
      const runs = c.eventsRuns?.length ? c.eventsRuns : [c.events || []]
      let rollbackReturn = null
      let rollbackBusy = ''
      try {
        for (const evs of runs) {
          globalThis.__DF_EVENTS__ = evs
          // `sessionId` 缺省仍是空串 = 不落库（老用例行为一字不变）
          await chat.send({ message: 'x', model: 'deepseek-free', sessionId: c.sessionId || '' })
        }
        // ---- 「回退本轮」：UI 侧唯一会调的那条路径（只传 turnId，会话由 composable 补）----
        if (c.rollback) {
          const marks = chat.messages.value.filter((m) => m.type === 'turn_end')
          const tid = c.rollback.turnId ?? marks[marks.length - 1]?.turnId
          const p = chat.rollbackTurn(tid)
          // 同步读一次：`rollbackTurn` 在第一个 await 之前就把状态置成 busy ——
          // 按钮就是靠它在这段时间里禁用的（连点会拿同一个账本回退两次）。
          rollbackBusy = chat.turnRollback.value.status
          rollbackReturn = await p
        }
      } catch (e) {
        thrown = String(e?.message || e)
      }
      const tl = globalThis.__DF_TIMELINES[globalThis.__DF_TIMELINES.length - 1]
      results.push({
        case: c,
        ctx: {
          messages: chat.messages.value,
          errors: chat.errors.value,
          corrections: chat.corrections.value,
          //: 执行统计（**会话累计**口径，不是单次提问）—— 见 DF-UI-07
          metrics: chat.metrics.value,
          //: 每次 `send()` 收到的请求选项（含 turnId）—— DF-UI-08/09/10/11 用它跟标记对账
          sentTurnIds: globalThis.__DF_SEND_OPTS.map((o) => o.turnId),
          //: 桩模块抛异常的形态（`error` / `abort`）—— 断言「现场真的成立了」，
          //: 否则那条用例其实在测正常路径
          streamThrows: [...globalThis.__DF_STREAM_THROWS],
          //: 最后一次 `saveAgentTimeline` 落库的那份快照（没有 sessionId 时是 undefined）
          timeline: tl?.tl,
          timelineSessionId: tl?.sid,
          //: `rollbackTurn` 的入参记录 / 返回 / 请求飞行期间的状态
          rollbackCalls: [...globalThis.__DF_ROLLBACK_CALLS],
          rollbackReturn,
          rollbackBusy,
          rollbackState: chat.turnRollback.value,
          currentTurnId: chat.currentTurnId.value,
          thrown
        }
      })
    }
  } finally {
    await server.close()
  }
  return results
}

// =====================================================================
// 套件 5：TOOLS —— 工具清单的两个投影 + 「可用工具」开关的写回
// =====================================================================
//
// 真 `agentDsFree.ts` + 桩掉的 `/ai/agent/tools`，跑真 `runDsFreeAgentStream`。
// 不碰扩展、不碰 DS 页面（模型回复由桩给定），所以是离线确定性的。
//
// ⚠️ 只有这一个驱动：浏览器面板只跑 LOOP / LIVE 组（`DfSelfCheckPanel` 的 pick 列表），
//    跑不到 TOOLS，与 RAG / UI 套件同理 —— 所以这里没有「两个驱动要同步」的负担。
//
// 桩的语义（与后端契约一致，见 df_cases.d.mts 的字段说明）：
//   · GET  `/ai/agent/tools` → 用例的 `agentTools`（缺省 `AGENT_TOOLS`）；
//     `agentToolsGetStatus` 可以按调用次序造失败；
//   · PUT  `/ai/agent/tools` → 缺省「照单生效」并把改后的**全量**清单回显；
//     `toolPrefPut` 可以改成「200 但没存」/ HTTP 非 2xx / 网络抛错。
async function runToolsCases(cases) {
  const st = { payload: null, getCount: 0, statuses: [], saveCalls: [], put: null, toolCalls: [] }
  const prompts = []
  globalThis.__TOOLS = {
    chat: async (o) => {
      prompts.push(o.systemPrompt || '')
      return '好的。'
    }
  }
  const stubs = {
    ...SAFE_STUBS,
    '@/utils/ds-proxy': `
      export async function chatWithDSAccumulated(o) { return globalThis.__TOOLS.chat(o) }
      export async function ensureDeepThink() { return { ok: true, changed: false, was: true } }
      export async function getDeepThink() { return null }
      export async function setDeepThink() { return true }
    `
  }

  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    const u = String(url)
    const method = String(init?.method || 'GET').toUpperCase()
    if (u.includes('/ai/agent/tools')) {
      const body = () => ({ tools: st.payload.tools, actions: st.payload.actions })
      if (method === 'PUT') {
        const sent = JSON.parse(init?.body || '{}')
        st.saveCalls.push(sent)
        const p = st.put || {}
        // `raw` = 整个响应体原样返回（200）。用来造**非本接口的形状**：
        // 服务端失败信封 `{code:400,msg,data:null}`、catch_all 的假成功 `{code:200,msg:'操作成功'}` —— 见 DF-TOOLS-08/09
        if (p.raw !== undefined) return jsonRes(p.raw)
        if (p.throws) throw new Error('保存接口网络异常（脚本注入）')
        if (p.status && p.status >= 400) return badRes(p.status)
        // 缺省「照单生效」：把请求里的开关应用到清单上，再回显**全量**清单。
        // `echo: 'unchanged'` 则是「HTTP 200 但清单没变」= 假成功。
        if (p.echo !== 'unchanged') {
          st.payload.tools = st.payload.tools.map((t) =>
            (t.function || t).name === sent.tool ? { ...t, disabled: sent.disabled } : t
          )
        }
        // `omitActions: true` = 响应里**没有** `actions` 字段（契约说是「同 GET 形状」，
        // 但实现走样少一个字段很常见）—— 这时前端不许把「写 / 破坏性」清单清掉
        return jsonRes(p.omitActions ? { tools: st.payload.tools } : body())
      }
      st.getCount += 1
      const status = st.statuses[st.getCount - 1] || 200
      if (status >= 400) return badRes(status)
      return jsonRes(body())
    }
    if (u.includes('/ai/agent/context')) return jsonRes({ context: '', history: '' })
    if (u.includes('/ai/agent/execute')) {
      const sent = JSON.parse(init?.body || '{}')
      st.toolCalls.push(`${sent.tool}.${sent.params?.action}`)
      return jsonRes({ success: true })
    }
    return jsonRes({})
  }

  const { server, load } = await makeLoader(stubs)
  const mod = await load('@/api/ai/agentDsFree')
  /** 有就调、没有就返回 null —— 少了导出时用例要**红得能看懂**，而不是崩成「用例执行时抛异常」 */
  const callIfExists = async (name, ...args) =>
    typeof mod[name] === 'function' ? mod[name](...args) : null

  const results = []
  try {
    for (const c of cases) {
      st.payload = JSON.parse(JSON.stringify(c.agentTools || AGENT_TOOLS))
      st.getCount = 0
      st.statuses = c.agentToolsGetStatus || []
      st.saveCalls = []
      st.put = c.toolPrefPut || null
      st.toolCalls = []
      prompts.length = 0
      mod.resetAgentToolsCache()

      const events = []
      let answer = ''
      let thrown = ''
      try {
        answer = await mod.runDsFreeAgentStream(
          {
            message: c.prompt || '我有哪些题库？',
            model: 'deepseek-free',
            userId: 1
          },
          { onEvent: (e) => events.push(e) }
        )
      } catch (e) {
        thrown = String(e?.message || e)
      }

      // 三个探针：生效清单 / 再读一次（验「失败没被缓存」）/ 界面清单
      const toolsEffective = await callIfExists('fetchAgentTools')
      const toolsAfterRetry = await callIfExists('fetchAgentTools')
      const toolsForUi = await callIfExists('fetchAgentToolsForUi')

      let saveResult = null
      let toolsAfterSave = null
      let toolsForUiAfterSave = null
      let systemPromptAfterSave = ''
      if (c.toolPrefSave) {
        saveResult = await callIfExists('saveAgentToolPref', c.toolPrefSave.tool, c.toolPrefSave.disabled)
        toolsAfterSave = await callIfExists('fetchAgentTools')
        toolsForUiAfterSave = await callIfExists('fetchAgentToolsForUi')
        // 再跑一轮：缓存没跟上服务端状态时，提示词里还会出现刚被禁用的工具
        await mod.runDsFreeAgentStream(
          { message: '再问一次', model: 'deepseek-free', userId: 1 },
          { onEvent: () => {} }
        )
        systemPromptAfterSave = prompts[prompts.length - 1] || ''
      }

      results.push({
        case: c,
        ctx: {
          events,
          eventTypes: events.map((e) => e.type),
          answer,
          toolCalls: [...st.toolCalls],
          /** 本轮真正发给模型的系统提示词 */
          systemPrompt: prompts[0] || '',
          /** 「保存之后再跑一轮」的那份提示词（没配 `toolPrefSave` 时是空串） */
          systemPromptAfterSave,
          toolsEffective,
          toolsAfterRetry,
          toolsForUi,
          saveResult,
          saveCalls: [...st.saveCalls],
          toolsAfterSave,
          /** 保存之后再读一次界面清单（配了 `toolPrefSave` 才有值） */
          toolsForUiAfterSave,
          thrown
        }
      })
    }
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
  return results
}

// =====================================================================
// 套件 6：ROLLBACK —— 轮次 id 的下发（api 链路）+ 回退接口的 `ok` 语义
// =====================================================================
//
// 真 `api/ai/agent.ts` + 桩掉的网络。两件事：
//   · `postAgentStream` 的**请求体**有没有带上本轮 `turnId`（DF-ROLLBACK-01）——
//     少带一个字段时前端一切正常、也不报错，只是后端没有账本可查；
//   · `rollbackAgentTurn` 的 `ok` **不是 HTTP 状态码**：本仓的 `catch_all` 会把
//     未匹配路径变成 `200 + {code:200,msg:'操作成功',data:null}` 的假成功，
//     业务拒绝也是 `200 + {code:400|403,…}`。判据只能是「`code===200` + `data` 形状对」
//     —— 与 `saveAgentToolPref` 同一条口径（那边的用例是 DF-TOOLS-08/09/10）。
//
// ⚠️ 只有这一个驱动：浏览器面板只跑 LOOP / LIVE 组，跑不到 ROLLBACK
//    （与 RAG / TOOLS / UI 套件同理），所以这里没有「两个驱动要同步」的负担。
async function runRollbackCases(cases) {
  const st = { streamBodies: [], rollbackBodies: [], response: {} }
  /**
   * 桩响应。**必须带 `headers.get`**：`postAgentStream` 先看 `Content-Type` 再决定
   * 「这是一份 JSON 错误信封」还是「这是流」—— 少了 `headers` 会直接 TypeError，
   * 而那样的红是驱动写错、不是产品错了。
   */
  const fakeRes = (body, { status = 200, contentType = 'application/json' } = {}) => ({
    ok: status < 400,
    status,
    headers: {
      get: (k) => (String(k).toLowerCase() === 'content-type' ? contentType : null)
    },
    async json() {
      return body
    },
    async text() {
      return typeof body === 'string' ? body : JSON.stringify(body)
    }
  })
  const originalFetch = globalThis.fetch
  globalThis.fetch = async (url, init) => {
    const u = String(url)
    const body = JSON.parse(init?.body || '{}')
    if (u.includes('/ai/agent/rollback')) {
      st.rollbackBodies.push(body)
      const r = st.response || {}
      if (r.throws) throw new Error('回退接口网络异常（脚本注入）')
      return fakeRes(r.raw !== undefined ? r.raw : {}, { status: r.status || 200 })
    }
    if (u.includes('/ai/agent/stream')) {
      // 请求体在**发出去那一刻**就已经记下了，所以这里只需要让 `postAgentStream`
      // 走它自己的「JSON 错误信封」出口（不必真去读流）。
      st.streamBodies.push(body)
      return fakeRes({ code: 400, msg: '（桩）到此为止', data: null })
    }
    return fakeRes({})
  }

  const { server, load } = await makeLoader({ ...SAFE_STUBS })
  const mod = await load('@/api/ai/agent')

  const results = []
  try {
    for (const c of cases) {
      st.streamBodies = []
      st.rollbackBodies = []
      st.response = c.rollbackResponse || {}
      let streamBody = null
      let rollback = null
      let thrown = ''
      try {
        if (c.streamOpts) {
          await mod.postAgentStream(c.streamOpts, {})
          streamBody = st.streamBodies[0] || null
        }
        if (c.rollbackParams) rollback = await mod.rollbackAgentTurn(c.rollbackParams)
      } catch (e) {
        thrown = String(e?.message || e)
      }
      results.push({
        case: c,
        ctx: {
          /** `/ai/agent/stream` 收到的请求体（DF-ROLLBACK-01） */
          streamBody,
          streamBodies: [...st.streamBodies],
          /** `/ai/agent/rollback` 收到的请求体 */
          rollbackBodies: [...st.rollbackBodies],
          /** `rollbackAgentTurn()` 的返回 */
          rollback,
          thrown
        }
      })
    }
  } finally {
    globalThis.fetch = originalFetch
    await server.close()
  }
  return results
}

/** 非 2xx 的桩响应（调用方只看 `ok` / `status` / `json()`） */
function badRes(status) {
  return {
    ok: false,
    status,
    async json() {
      return {}
    },
    async text() {
      return ''
    }
  }
}
// =====================================================================
// 套件 4：LIVE —— 真浏览器 + 真扩展 + 真 DS 页面
// =====================================================================
function httpJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let b = ''
      res.on('data', (c) => (b += c))
      res.on('end', () => {
        try {
          resolve(JSON.parse(b))
        } catch (e) {
          reject(e)
        }
      })
    }).on('error', reject)
  })
}

class CDP {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    // 收下所有主动推来的事件（Log.entryAdded / Runtime.consoleAPICalled …）——
    // 扩展注入失败时，`[DSPROXY_*]` 日志是唯一能定位原因的东西
    this.events = []
    ws.addEventListener('message', (ev) => {
      const m = JSON.parse(ev.data)
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id)
        this.pending.delete(m.id)
        m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
      } else if (m.method) {
        this.events.push(m)
        if (this.events.length > 2000) this.events.splice(0, 1000)
      }
    })
  }
  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error('CDP 超时: ' + method))
        }
      }, 30000)
    })
  }
  async evalJs(expression, awaitPromise = true) {
    const r = await this.send('Runtime.evaluate', {
      expression: `(async () => { ${expression} })()`,
      returnByValue: true,
      awaitPromise
    })
    if (r.exceptionDetails) {
      throw new Error(String(r.exceptionDetails.exception?.description || '').slice(0, 400))
    }
    return r.result.value
  }
}

/** 建立一条 CDP 连接 */
async function connect(url) {
  const ws = new WebSocket(url)
  await new Promise((res, rej) => {
    ws.addEventListener('open', res)
    ws.addEventListener('error', rej)
  })
  return new CDP(ws)
}

/**
 * 打开一个能加载**真扩展**的持久化 Chrome
 *
 * 扩展怎么加载 —— 这几条都是**对照实测**出来的，别凭印象改：
 *
 *   · `--load-extension` —— **Chrome 137 起被移除**，本机 153 上完全失效。
 *       实测：只带这个开关跑起来，`chrome-extension://` target 里只有 Chrome 自带的
 *       两个组件扩展（`nkeimhog…` / `fignfifo…`），我们的扩展压根没加载，
 *       `window.DSProxy` 10s 轮询全空 ⇒ 所以它**必须从参数里去掉**，留着只会误导。
 *   · `--disable-extensions-except` —— ⚠️ **绝对不能传**。它会把随后通过 CDP
 *       `Extensions.loadUnpacked` 动态加载的扩展一起禁掉：loadUnpacked 照样返回 id，
 *       但扩展进程根本不起来，症状是 `window.DSProxy` 死活不存在、
 *       控制台连一条 `[DSPROXY_WEB]` 日志都没有。
 *       （对照实测：不带 → 1.0s 注入成功；带上 → 12s 轮询全空）
 *   · `Extensions.loadUnpacked`（CDP，Chrome 126+）—— **唯一可用的现代做法**。
 *
 * 所以：启动参数里**一个扩展相关开关都不加**，扩展全靠 CDP 动态装载。
 * 别加「已经有了就跳过」这类守卫 —— Chrome 永远有自带的 `chrome-extension://` target，
 * 按 URL 前缀判断必然误判成「已加载」而跳过所有装载动作（踩过）。
 *
 * `headed`（默认 true）：**必须能看见窗口** —— 首次要手动登录 chat.deepseek.com，
 *   无头模式下用户没法登。登录信息存在持久化 profile 里，之后 `--headless` 也能跑。
 */
async function openBrowser({ headed = true } = {}) {
  const userDataDir = process.env.DF_PROFILE || path.join(os.tmpdir(), 'df-live-profile')
  if (!fs.existsSync(EXT_DIR)) throw new Error(`扩展目录不存在：${EXT_DIR}`)
  if (!fs.existsSync(CHROME)) throw new Error(`找不到 Chrome：${CHROME}（用 DF_CHROME=... 指定）`)

  const headless = !headed
  const child = spawn(
    CHROME,
    [
      ...(headless ? ['--headless=new'] : []),
      '--disable-gpu',
      '--no-sandbox',
      '--no-first-run',
      '--no-default-browser-check',
      `--remote-debugging-port=${CDP_PORT}`,
      `--user-data-dir=${userDataDir}`,
      // 这里**故意没有任何扩展开关** —— 见上方注释，多一个都会坏事
      '--window-size=1400,950',
      'about:blank'
    ],
    { stdio: 'ignore', detached: false }
  )

  const closeAll = (wsList) => {
    for (const w of wsList) {
      try {
        w.close()
      } catch {}
    }
    child.kill()
  }

  try {
    const ver = await waitPort(`http://127.0.0.1:${CDP_PORT}/json/version`)

    // ① 浏览器级连接：Extensions.loadUnpacked 只能发给 browser target
    let browserWs = null
    let extId = ''
    if (ver.webSocketDebuggerUrl) {
      const b = await connect(ver.webSocketDebuggerUrl)
      browserWs = b.ws
      try {
        const r = await b.send('Extensions.loadUnpacked', { path: EXT_DIR })
        extId = r?.id || ''
        console.log(C.dim(`  已加载扩展：${extId || '(无 id)'}`))
      } catch (e) {
        const msg = String(e?.message || e)
        console.log(C.yellow(`  Extensions.loadUnpacked 不可用：${msg.slice(0, 80)}`))
        console.log(C.dim('  · 该 CDP 域需要 Chrome 126+；太老的话改成手动加载扩展：'))
        console.log(C.dim(`    打开 chrome://extensions → 打开「开发者模式」→「加载已解压的扩展程序」→ 选 ${EXT_DIR}`))
        console.log(C.dim('    该操作会被持久化 profile 记住，之后再跑 --headless 也能用'))
      }
    }

    // ② 页面级连接：跑脚本用
    const list = await httpJson(`http://127.0.0.1:${CDP_PORT}/json/list`)
    const page = list.find((t) => t.type === 'page')
    const cdp = await connect(page.webSocketDebuggerUrl)
    await cdp.send('Page.enable')
    await cdp.send('Runtime.enable')
    // 把页面控制台收下来 —— 扩展注入失败时全靠这些日志定位
    await cdp.send('Log.enable').catch(() => {})

    return {
      cdp,
      extId,
      close: () => closeAll([cdp.ws, browserWs].filter(Boolean))
    }
  } catch (e) {
    child.kill()
    throw e
  }
}

/** 轮询等到 `fn()` 返回真值；超时返回 null（比固定 sleep 稳，网络/磁盘快慢都不怕） */
async function waitFor(fn, { timeout = 12000, step = 400, desc = '' } = {}) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    const v = await fn().catch(() => null)
    if (v) return v
    await sleep(step)
  }
  if (desc) console.log(C.dim(`  （等 ${desc} 超时 ${timeout}ms）`))
  return null
}

/** 从 CDP 事件里捞扩展/DSProxy 相关控制台日志，注入失败时打出来定位 */
function pickExtensionLogs(cdp, limit = 8) {
  return cdp.events
    .filter((e) => e.method === 'Runtime.consoleAPICalled' || e.method === 'Log.entryAdded')
    .map((e) =>
      e.method === 'Log.entryAdded'
        ? `[log:${e.params.entry.source}] ${e.params.entry.text}`
        : `[console] ${(e.params.args || []).map((a) => a.value || a.description || '').join(' ')}`
    )
    .filter((s) => /DSPROXY|DSProxy|extension|sdk/i.test(s))
    .slice(0, limit)
}

async function waitPort(url, timeout = 15000) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    try {
      return await httpJson(url)
    } catch {
      await sleep(300)
    }
  }
  throw new Error('CDP 未就绪: ' + url)
}

/** 前端 dev server 活着吗？—— LIVE 套件的硬前提，提前问一句比让它超时清楚得多 */
function pingDevServer(timeout = 3000) {
  return new Promise((resolve) => {
    const req = http.get(DEV_SERVER, (res) => {
      res.resume()
      resolve(res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(timeout, () => {
      req.destroy()
      resolve(false)
    })
  })
}

/** 在页面里跑一次真 Agent（真扩展 → 真 DS 页面） */
const PAGE_RUN = (prompt, userId) => `
  const events = []
  let formatErrorCount = 0
  const origPush = events.push.bind(events)
  events.push = (e) => { if (e && e.type === 'error') formatErrorCount++; return origPush(e) }
  const mod = await import('/src/api/ai/agentDsFree.ts')
  const answer = await mod.runDsFreeAgentStream(
    { message: ${JSON.stringify(prompt)}, model: 'deepseek-free', userId: ${userId}, autoConfirm: true },
    { onEvent: (e) => events.push(e), onConfirm: async () => true }
  )
  return { answer, events, formatErrorCount }
`

async function runLiveCases(cases) {
  const results = []
  let browser

  // 最先查 dev server：没起的话后面所有现象（扩展没注入 / 页面空白）都是假象，
  // 报「前端没起来」比报「window.DSProxy 不存在」有用得多
  if (!(await pingDevServer())) {
    const blockers = [
      `前端 dev server 没起来（${DEV_SERVER}）—— 先把它开起来：` +
        '双击 scripts\\start-fastAPI-Vue3.bat，或在 apps/fastapi-v2/openstudy-vue3-ts 下 npm run dev'
    ]
    console.log(C.yellow('\n  LIVE 套件被前置条件挡住，未执行：'))
    for (const b of blockers) console.log(C.yellow('    · ' + b))
    console.log('')
    return cases.map((c) => ({
      case: c,
      ctx: {
        blocked: true,
        blockers,
        eventTypes: [],
        toolCalls: [],
        answer: '',
        hadFormatError: false,
        formatErrorCount: -1
      }
    }))
  }

  try {
    browser = await openBrowser({ headed: ARGS.headed })
    const { cdp, close } = browser
    await cdp.send('Page.navigate', { url: DEV_SERVER })

    // 前置检查：扩展注入了吗？DS 登录了吗？OpenStudy 登录了吗？
    const probeEnv = () =>
      cdp.evalJs(`
      const ready = {
        hasProxy: typeof window.DSProxy !== 'undefined',
        url: location.href,
        hasToken: document.cookie.includes('Admin-Token')
      }
      if (ready.hasProxy) {
        try {
          const dsp = new window.DSProxy()
          const st = await dsp.getStatus()
          ready.dsTabOpen = !!st?.dsTabOpen
          // ⚠️ 别再读 st.loggedIn —— 扩展的 DSPROXY_GET_STATUS 压根不返回这个字段
          //    （background.js 的 getStatus() 只给 dsTabOpen / ready / tabCount），
          //    读出来恒为 undefined，于是「DS 未登录」这条前置永远挡着，
          //    哪怕 DS 页面明明开着也报未登录。踩过。
        } catch (e) { ready.statusError = String(e?.message || e) }
      }
      return ready
    `)

    const blockersOf = (env) => {
      const out = []
      if (!env.hasProxy) {
        out.push(
          '扩展没注入（window.DSProxy 不存在）—— 按顺序排查：' +
            '① 上面有没有打印「已加载扩展」；' +
            '② 有没有打印「Extensions.loadUnpacked 不可用」（这版 Chrome 太老）；' +
            `③ 都不行就手动把 ${EXT_DIR} 拖进 chrome://extensions（profile 会记住）。` +
            '⚠️ 常见坑：启动参数里带了 --disable-extensions-except，它会把 CDP 动态加载的扩展一起禁掉'
        )
      }
      if (!env.hasProxy || !env.dsTabOpen) {
        out.push(
          `${ARGS.headed ? '' : '先用 --headed 跑一次，然后'}新开一个标签页打开 https://chat.deepseek.com` +
            `（顺便确认已登录、能看到输入框；登录写进持久化 profile，之后 --headless 也能跑）`
        )
      }
      if (!env.hasToken) {
        out.push(
          `${ARGS.headed ? '' : '先用 --headed 跑一次，然后'}在 ${DEV_SERVER} 这个标签页里登录 OpenStudy（工具调用要鉴权）`
        )
      }
      return out
    }

    const profile = process.env.DF_PROFILE || path.join(os.tmpdir(), 'df-live-profile')
    // 扩展注入最多等 15s：冷启动/磁盘慢的时候真会超过 3s（实测 1~4s 都出现过）
    await waitFor(() => probeEnv().then((e) => e.hasProxy || null), {
      timeout: 15000,
      desc: 'window.DSProxy 注入'
    })

    let env = await probeEnv()
    let blockers = blockersOf(env)

    // 缺的是「登录」这种只能人来做的事 —— 带窗口时别把窗口关了走人，
    // 留着让用户登，轮询到齐了自动接着跑（--login-wait 0 可关掉这段等待）
    if (blockers.length && ARGS.headed && ARGS.loginWait > 0) {
      console.log(C.yellow('\n  LIVE 前置条件还差几条，浏览器窗口留给你操作：'))
      for (const b of blockers) console.log(C.yellow('    · ' + b))
      console.log(C.dim(`\n  补完会自动继续（最多等 ${ARGS.loginWait}s，--login-wait 0 可跳过等待）…`))
      const ok = await waitFor(
        async () => {
          env = await probeEnv().catch(() => env)
          blockers = blockersOf(env)
          return blockers.length === 0 ? true : null
        },
        { timeout: ARGS.loginWait * 1000, step: 3000 }
      )
      if (ok) console.log(C.green('  前置条件齐了，继续跑。'))
    }

    if (blockers.length) {
      console.log(C.yellow('\n  LIVE 套件被前置条件挡住，未执行：'))
      for (const b of blockers) console.log(C.yellow('    · ' + b))
      console.log(C.dim(`\n  profile：${profile}`))
      console.log(C.dim(`  模式：${ARGS.headed ? '带窗口' : '无头'}（--headed / --headless 切换）`))

      // 注入失败时，扩展自己的控制台日志是唯一线索 —— 别让它烂在事件队列里
      const extLogs = pickExtensionLogs(cdp)
      if (extLogs.length) {
        console.log(C.dim('\n  扩展/DSProxy 相关控制台日志：'))
        for (const l of extLogs) console.log(C.dim('    ' + l.slice(0, 150)))
      } else if (!env.hasProxy) {
        console.log(C.dim('\n  （控制台里连一条 DSPROXY/扩展日志都没有 —— content script 压根没跑起来）'))
      }
      console.log('')
      for (const c of cases) {
        results.push({
          case: c,
          ctx: { blocked: true, blockers, eventTypes: [], toolCalls: [], answer: '', hadFormatError: false, formatErrorCount: -1 }
        })
      }
      return results
    }

    const userId = await cdp.evalJs(
      `try { return Number(JSON.parse(localStorage.getItem('user') || '{}').id) || 1 } catch { return 1 }`
    )

    for (const c of cases) {
      let r = {}
      let thrown = ''
      const t0 = Date.now()
      try {
        r = await cdp.evalJs(PAGE_RUN(c.prompt, userId))
      } catch (e) {
        thrown = String(e?.message || e)
      }
      const secs = ((Date.now() - t0) / 1000).toFixed(1)
      const events = r.events || []
      const toolCalls = events
        .filter((e) => e.type === 'tool_result')
        .map((e) => `${e.tool}.${e.action}`)
      const selfCorrect = events.filter((e) => e.type === 'self_correct')

      // 过程轨迹要进日志 —— LIVE 跑一次很贵，出问题时「事件流长什么样」比断言更说明问题
      console.log(C.dim(`\n      ${c.id} 用时 ${secs}s｜提问：${String(c.prompt).slice(0, 60)}`))
      console.log(C.dim(`      事件流：${events.map((e) => e.type).join(' → ') || '(无事件)'}`))
      if (toolCalls.length) console.log(C.dim(`      工具调用：${toolCalls.join('、')}`))
      if (thrown) console.log(C.red(`      抛异常：${thrown.slice(0, 200)}`))

      results.push({
        case: c,
        ctx: {
          events,
          eventTypes: events.map((e) => e.type),
          answer: String(r.answer || ''),
          toolCalls,
          formatErrorCount: r.formatErrorCount ?? 0,
          // 「第一轮就格式错」= 没有工具成功过 + 出现过 self_correct
          hadFormatError: selfCorrect.length > 0 && toolCalls.length === 0,
          secs,
          thrown
        }
      })
    }
    void close
  } catch (e) {
    const reason = String(e?.message || e)
    console.log(C.red('\n  LIVE 环境起不来：') + reason)
    if (/找不到 Chrome/.test(reason)) {
      console.log(C.dim('    · 用 DF_CHROME="路径/chrome.exe" 指定'))
    }
    if (/扩展目录不存在/.test(reason)) {
      console.log(C.dim(`    · 期望位置：${EXT_DIR}`))
    }
    for (const c of cases) {
      results.push({
        case: c,
        ctx: {
          blocked: true,
          blockers: [reason],
          eventTypes: [],
          toolCalls: [],
          answer: '',
          formatErrorCount: -1
        }
      })
    }
  } finally {
    browser?.close()
  }
  return results
}

// =====================================================================
// --clean：清掉 __df_test__ 前缀的数据
// =====================================================================
async function cleanTestData() {
  console.log(C.cyan(`\n清理 ${PREFIX}* 前缀的数据…`))
  if (!(await pingDevServer())) {
    console.log(C.yellow(`  前端 dev server 没起来（${DEV_SERVER}）—— 清理要先把它开起来`))
    return
  }
  let browser
  try {
    browser = await openBrowser()
    const { cdp } = browser
    await cdp.send('Page.navigate', { url: DEV_SERVER })
    await sleep(2500)
    const r = await cdp.evalJs(`
      const token = document.cookie.split('; ').find(c => c.startsWith('Admin-Token='))
      if (!token) return { unauthenticated: true }
      const auth = { Authorization: 'Bearer ' + token.split('=')[1] }
      const post = async (url, body) => {
        const res = await fetch(url, {
          method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' }, body: JSON.stringify(body)
        })
        return { status: res.status, body: await res.json().catch(() => null) }
      }
      const listRes = await post('/ai/agent/execute', { tool: 'bank_manage', params: { action: 'list', bank_name: ${JSON.stringify(PREFIX)} }, userId: 1 })
      if (listRes.status !== 200) return { httpStatus: listRes.status, raw: listRes.body }
      const banks = listRes.body?.banks || []
      const deleted = []
      for (const b of banks) {
        if (!String(b.bankName || '').startsWith(${JSON.stringify(PREFIX)})) continue
        await post('/ai/agent/execute', { tool: 'bank_manage', params: { action: 'delete', bank_id: b.bankId }, userId: 1 })
        deleted.push(b.bankName)
      }
      return { found: banks.length, deleted }
    `)
    // 别把「没登进去所以查不到」说成「没有残留」—— 那是两回事
    if (r.unauthenticated) {
      console.log(C.yellow('  没登录，查不到 —— 先 --headed 在这个 profile 里登录 ' + DEV_SERVER))
      console.log(C.dim('  （别把「没查成」当成「没残留」）'))
    } else if (r.httpStatus) {
      console.log(C.yellow(`  查询失败 HTTP ${r.httpStatus}`) + C.dim(' ' + JSON.stringify(r.raw || {}).slice(0, 200)))
    } else {
      console.log(
        C.green(`  删掉 ${r.deleted.length} 个测试题库`) + C.dim(` ${r.deleted.join(', ') || '（没有残留）'}`)
      )
    }
  } catch (e) {
    console.log(C.yellow('  清理失败：' + String(e?.message || e)))
    console.log(C.dim('  （离线套件不落库，一般不需要清理；这条主要给 LIVE 用）'))
  } finally {
    browser?.close()
  }
}

// =====================================================================
// 交互式菜单（给双击 .bat 用）
// =====================================================================
// ⚠️ 菜单**必须**在 Node 里、不能写在 .bat 里 —— 踩过：
//    cmd.exe 是按「当前代码页」逐行解析 .bat 的。bat 存成 UTF-8 而 cmd 用 GBK 读时，
//    中文被当成多字节乱码，cmd 的**文件读取偏移量跟着错位**，于是从行中间开始解析，
//    报出一堆半截行碎片（`gs` / `o.` / `heck_agent_dsfree_result.json` 这种）。
//    `chcp 65001` 放第 2 行也救不了 —— 在它生效前偏移量就已经算歪了。
//    结论：`.bat` 里只留 ASCII，所有中文交给 Node（Windows 上 Node 走 WriteConsoleW，
//    不受控制台代码页影响）。所以 bat 只干一件事：`node ... --menu`。
const MENU_ITEMS = [
  {
    key: '1',
    label: '离线自检',
    desc: 'LOOP / PROXY / RAG / TOOLS / UI 五个套件。快、不联网、不写库，随便反复跑',
    args: []
  },
  {
    key: '2',
    label: '真浏览器端到端',
    desc: '起 Chrome + 真扩展 + 真 DS 页面。首次要在这个窗口里手动登录一次',
    args: ['--suite', 'LIVE', '--headed']
  },
  {
    key: '3',
    label: '反复压测',
    desc: '离线套件连跑 20 轮，专抓「偶尔才失败」的偶发问题',
    args: ['--repeat', '20']
  },
  {
    key: '4',
    label: '只列用例',
    desc: '不跑，只把全部用例的 ID / 标题打出来',
    args: ['--list']
  },
  {
    key: '5',
    label: '清理测试数据',
    desc: `删掉 ${PREFIX} 前缀的题库（不会碰真数据）`,
    args: ['--clean']
  }
]

async function runMenu() {
  if (!process.stdin.isTTY) {
    console.log(C.yellow('\n  当前不是交互式终端，菜单用不了。直接带参数跑，例如：'))
    console.log(C.dim('    node tests/check_agent_dsfree.mjs --list'))
    console.log(C.dim('    node tests/check_agent_dsfree.mjs --suite LOOP --repeat 20\n'))
    return
  }

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
  const ask = (q) => new Promise((r) => rl.question(q, r))
  let chosen = null

  for (;;) {
    console.log(C.bold('\n  ============ ds-free OS 助手自检 ============'))
    console.log(C.dim(`  用例表：tests/df_cases.mjs（共 ${ALL.length} 条）\n`))
    for (const m of MENU_ITEMS) {
      console.log(`  [${m.key}] ${C.bold(m.label)}`)
      console.log(C.dim(`        ${m.desc}`))
    }
    console.log('  [0] 退出\n')

    const pick = String(await ask('  输入序号后回车：')).trim()
    if (pick === '0') {
      rl.close()
      return
    }
    const hit = MENU_ITEMS.find((m) => m.key === pick)
    if (!hit) {
      console.log(C.yellow(`\n  没听懂「${pick}」，请输入 0 到 ${MENU_ITEMS.length} 之间的数字。`))
      continue
    }
    chosen = hit
    break
  }
  rl.close()

  // 真活儿交给子进程 —— stdio 全继承，用户看到的就是子进程原样输出
  console.log(C.dim(`\n  → node tests/check_agent_dsfree.mjs ${chosen.args.join(' ')}\n`))
  const res = spawnSync(process.execPath, [fileURLToPath(import.meta.url), ...chosen.args], {
    stdio: 'inherit',
    cwd: VUE_ROOT
  })
  const code = res.status ?? 1

  console.log(
    '\n  ' +
      (code === 0 ? C.green('结果：全部通过') : C.red(`结果：有失败（退出码 ${code}）`))
  )
  console.log(C.dim(`  过程日志目录：${LOG_DIR}`))
  console.log(C.dim('  要排查问题，把里面最新的那个 .log 整个发出来就行。'))
}

// =====================================================================
// 主流程
// =====================================================================
async function main() {
  const runStart = Date.now()

  if (ARGS.menu) {
    await runMenu()
    return
  }

  if (ARGS.clean) {
    await cleanTestData()
    return
  }

  const cases = selected()
  if (!cases.length) {
    console.log(C.yellow('\n没有匹配的用例。用 --list 看看有哪些。\n'))
    return
  }

  const bySuite = {}
  for (const c of cases) (bySuite[c.suite] ||= []).push(c)

  console.log(C.bold(`\n=== ds-free OS 助手自检 ===`))
  console.log(C.dim(`  用例 ${cases.length} 条 · 轮次 ${ARGS.repeat} · 套件 ${Object.keys(bySuite).join(', ')}`))
  console.log(C.dim(`  用例表：tests/df_cases.mjs`) + '\n')

  const rows = []
  let pass = 0
  let fail = 0

  for (const [suite, list] of Object.entries(bySuite)) {
    console.log(C.bold(`\n── ${suite} (${list.length}) ${'─'.repeat(Math.max(0, 50 - suite.length))}`))

    // 每个套件只起一次环境，轮次在内部复用（快）
    const drivers = {
      LOOP: runLoopCases,
      PROXY: runProxyCases,
      RAG: runRagCases,
      TOOLS: runToolsCases,
      UI: runUiCases,
      ROLLBACK: runRollbackCases,
      LIVE: runLiveCases
    }

    for (let round = 1; round <= ARGS.repeat; round++) {
      if (ARGS.repeat > 1) console.log(C.dim(`\n  第 ${round}/${ARGS.repeat} 轮`))
      const results = await drivers[suite](list)

      for (const { case: c, ctx } of results) {
        let asserts = []
        if (ctx.blocked) {
          // ⚠️ 原因必须**写在断言里**：只在上面打一行横幅的话，用 --only / 管道截断时
          //    很容易只剩「未满足（见上方提示）」而上方什么都没有，等于没说。
          asserts = [['前置条件未满足', false, (ctx.blockers || []).join(' / ') || '原因未知']]
        } else if (ctx.thrown && !c.expectThrows) {
          asserts = [['用例执行时抛异常', false], [String(ctx.thrown).slice(0, 120), false]]
        } else {
          try {
            asserts = c.expect(ctx) || []
          } catch (e) {
            asserts = [['断言函数自己抛了异常：' + String(e?.message || e), false]]
          }
        }
        const ok = asserts.length > 0 && asserts.every((a) => !!a[1])
        ok ? (pass += 1) : (fail += 1)

        const tag = ok ? C.green('PASS') : C.red('FAIL')
        console.log(`  [${tag}] ${C.bold(c.id)} ${c.title}`)
        for (const [label, good, actual] of asserts) {
          if (good && !ARGS.verbose) continue
          console.log(`         ${good ? C.dim('·') : C.red('✗')} ${label}${actual ? C.dim(` → ${actual}`) : ''}`)
        }
        rows.push({
          id: c.id,
          suite,
          round,
          title: c.title,
          status: ok ? '通过' : '失败',
          secs: ctx.secs ?? null,
          asserts: asserts.map(([label, good, actual]) => ({ label, pass: !!good, actual: actual ?? '' }))
        })
      }
    }
  }

  console.log(C.bold(`\n=== 结果 ===`))
  console.log(`  ${C.green(pass + ' 通过')} / ${fail ? C.red(fail + ' 失败') : '0 失败'}  （共 ${pass + fail} 条）`)
  console.log(C.dim(`  总耗时 ${((Date.now() - runStart) / 1000).toFixed(1)}s`))

  // 偶发检测：同一条用例在多次轮次里既有通过又有失败
  if (ARGS.repeat > 1) {
    const byId = {}
    for (const r of rows) (byId[r.id] ||= []).push(r.status)
    const flaky = Object.entries(byId).filter(
      ([, s]) => s.includes('通过') && s.includes('失败')
    )
    if (flaky.length) {
      console.log(C.yellow(`\n  ⚠️ 偶发（同一用例时好时坏）：${flaky.map(([id]) => id).join(', ')}`))
    } else {
      console.log(C.dim('\n  没有偶发用例（每轮结果一致）'))
    }
  }

  const summary = {
    total: rows.length,
    passed: pass,
    failed: fail,
    when: new Date().toISOString(),
    elapsedSec: Number(((Date.now() - runStart) / 1000).toFixed(1)),
    argv: process.argv.slice(2),
    logFile: LOG_FILE,
    rows
  }
  fs.writeFileSync(OUT_JSON, JSON.stringify(summary, null, 2), 'utf8')

  console.log(C.dim(`\n  结果 JSON：${OUT_JSON}`))
  console.log(C.dim(`  过程日志 ：${LOG_FILE || '(未写成功)'}`))
  console.log(C.dim(`  ⚠️ 日志文件只保留最近 ${KEEP_LOGS} 份，更早的已自动清掉`))
  console.log('')
  console.log(
    `结束时间：${new Date().toLocaleString('zh-CN')}  退出码：${fail ? 1 : 0}  （0=全通过）`
  )

  pruneLogs()
  process.exit(fail ? 1 : 0)
}

/** 日志目录只留最近 KEEP_LOGS 份 —— 反复跑不至于把磁盘堆满 */
function pruneLogs() {
  if (!LOG_READY) return
  try {
    const files = fs
      .readdirSync(LOG_DIR)
      .filter((f) => f.startsWith('dsfree-check-') && f.endsWith('.log'))
      .sort()
    for (const f of files.slice(0, Math.max(0, files.length - KEEP_LOGS))) {
      fs.unlinkSync(path.join(LOG_DIR, f))
    }
  } catch {
    /* 清理失败无所谓 */
  }
}

main().catch((e) => {
  console.error(C.red('\n脚本自身出错：'), e)
  process.exit(2)
})
