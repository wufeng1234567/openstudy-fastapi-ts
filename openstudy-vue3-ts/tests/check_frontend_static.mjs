/**
 * 前端静态检查：SFC 编译 + TS 语法 + import 路径解析
 *
 * 为什么需要它（两个本机环境的坑，都不是代码问题）：
 *   · `vue-tsc` 在 Node 22 下直接崩：
 *     `Search string not found: "/supportedTSExtensions = .*(?=;)/"`
 *   · vite 的 SSR 链路也跑不通：`sass` 预处理器加载失败
 *     （`Cannot read properties of undefined (reading 'pop')`），
 *     而 `chat.vue` 一路 import 到 `src/router` 还需要 window/navigator 垫片
 *
 * 所以这里绕开构建工具，只做**确定性的静态检查**：
 *   1. `@vue/compiler-sfc` 解析 SFC          → 抓模板/脚本结构错
 *   2. `compileScript` + `compileTemplate`   → 抓 `<script setup>` / 模板语法错
 *   3. typescript 转译 script 块              → 抓 TS 语法错
 *   4. 手写 import 路径解析                    → 抓「路径写错 / 文件不存在」
 *   5. 布局结构断言（见文件末尾「布局结构断言」一节）
 *                                            → 抓「输入框吸底 / 顶部标题栏」这类**布局回归**
 *
 * 第 4 条是最有价值的一条：import 路径写错**不会**在启动时报，只有真正走到
 * 那个分支才炸 —— 平时摸不到的分支（错误处理、冷门入口）最容易带着这种错上线。
 *
 * 用法：
 *   cd apps/fastapi-v2/openstudy-vue3-ts
 *   node tests/check_frontend_static.mjs                  # 默认清单
 *   node tests/check_frontend_static.mjs src/foo.ts ...    # 指定文件（相对仓库根）
 *   node tests/check_frontend_static.mjs --no-layout       # 只跑语法/import，跳过布局断言
 *
 * 新增/改动前端文件后，把它加进 `DEFAULT_TARGETS`（或作为参数传进来）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
// ⚠️ 这里**只许用显式声明**的依赖。`typescript` 是 devDependencies 里的（`^5.3.3`）✅。
//    **不要**换成「只是别的包的传递依赖」的转译器/打包器（本文件原先用的那个就是这种）——
//    顶层 `node_modules` 里一旦没有它（pnpm 的严格布局 / `npm i --install-strategy=nested` /
//    vite 6+ 改走 rolldown），本脚本会**启动即崩**（`Cannot find module`），把「文件级 + 布局断言」
//    **全部**一起带走 —— 而它是所有人的验收入口。
import ts from 'typescript'

const ROOT = process.cwd()

/** 默认检查清单：改动频繁 / 风险高的入口文件 */
const DEFAULT_TARGETS = [
  'src/api/ai/rag.ts',
  // Agent 事件 / 工具类型的**两侧共用**契约（`AgentEvent` / `AgentToolDefinition` / `AgentToolsPayload`）。
  // 两条链路都依赖它，改动又频繁，而检查器此前**从没编译过它** —— 一个 import 路径写错
  // 只有真正走到那个分支才炸，正好是平时摸不到的分支最容易带着错上线。
  'src/api/ai/agent.ts',
  'src/api/ai/agentDsFree.ts',
  // `@/api/ai/ai` —— 会话列表 / 历史 / 时间线快照 / 附件占位那一整套接口。
  // ⚠️ 2026-09-23 补进清单（`drop-turn-fe-logic` 报的）：它和上面三个 ai 接口文件是同一类地基，
  //    却一直不在清单里 —— 「回退 + 删本轮对话」这条链正是靠它落库 / 读快照的。
  'src/api/ai/ai.ts',
  // `useAgentChat` —— 两条链路共用的引擎（消息流 / 回退状态 / 指标 / 时间线都在里面）。
  // ⚠️ 同一个理由补进来：它的 import 路径写错时，只有真正走到那一条（例如点了回退）才炸。
  'src/composables/useAgentChat.ts',
  'src/components/KnowledgeBaseDrawer/index.vue',
  // 抽屉的**内容**（2026-09-21 拆分后的新家：外壳只剩入口按钮 + el-drawer）。
  // L18–L26 的内容类判据全断在这个文件上 —— 一个 import 路径写错只有真走到那条分支才炸，
  // 而「上传失败 / 检索失败」这类分支平时根本摸不到。
  'src/components/KnowledgeBasePanel/index.vue',
  'src/components/ChatInputArea/index.vue',
  'src/components/AgentToolPopover/index.vue',
  // L17 的被测对象：它由「离线执行 script setup」检查，但也该进语法 / import 路径清单
  'src/components/AgentConfirmCard/index.vue',
  // 工具调用卡片的第二 / 第三层：`TOOL_LABELS` / `ACTION_LABELS`（前者）与
  // `FIELD_LABELS` / `ENUM_LABELS` / `REDUNDANT_KEYS`（后者）。L46–L53 拿它们当判据，
  // 但它们此前**根本不在本清单里** —— 一个 import 路径写错只有真正展开详情才炸。
  'src/components/AgentToolResult/index.vue',
  'src/components/AgentToolDetail/index.vue',
  // 消息流模板本身（`turn_end` 分支 / 轮末动作条的挂载点）。它此前**不在**清单里 ——
  // 一个 import 路径写错时，只有消息流真的渲染到那一支才炸，而它正是被 L69–L71 断的对象。
  'src/components/AiChatStream/index.vue',
  // 轮末动作条（`type:'turn_end'` 那一格）。L70 / L74 / L75 / L76 / L77 断它的模板、按钮与图标，
  // 而它 import 了 `@/api/ai/agent` 的类型与 `@element-plus/icons-vue` 的图标 ——
  // 路径/名字写错同样只有点开那一轮才会炸。
  'src/components/AgentTurnRollback/index.vue',
  // 回退结果栏（消息列表**之外**那一块）。L72 / L77 / L82 / L83 断它 ——
  // 它 import 了图标与 `@/api/ai/agent` 的类型；而且它是**新文件**，不进清单就没人管它的 import 路径。
  'src/components/AgentRollbackNotice/index.vue',
  // 右侧悬浮助手抽屉 —— `AiChatStream` 的**第二个消费方**。L73 / L80 / L81 / L84 都要在它身上
  // 再断一遍（「两个消费方都要接上」是本仓最常见的一种「功能做了一半」）。
  // ⚠️ 它此前**不在**清单里：这次的改动落在它身上（回退按轮 + 回填输入框 + toast），
  //    一个 import 路径写错在静态上完全看不出来，只有真正走到那条分支才炸。
  'src/components/AiAssistant/index.vue',
  'src/views/front/agent/chat.vue',
  'src/views/front/agent/index.vue',
  'src/devtools/dfSelfCheck/runLoopGroup.ts',
  // @ 提及整条链：`@{id} 昵称` 是**写入侧的线上契约**（后端靠它发 @ 通知），
  // 而 `mention.ts` 是**读取侧唯一一份解析规则**（评论正文 + 私信正文共用）。
  // 这条链的错法都很安静：正则漏一个分支，界面上就冒出 `{106}` 这种实现细节。
  'src/components/CommentSection/mention.ts',
  'src/components/CommentSection/CommentInput.vue',
  'src/components/CommentSection/CommentItem.vue',
  'src/views/front/messages/mentions.vue'
]

const ARGV = process.argv.slice(2)
/** `--no-layout`：只跑语法/import 检查（布局断言在文件末尾） */
const SKIP_LAYOUT = ARGV.includes('--no-layout')
const targets = ARGV.filter((a) => !a.startsWith('--')).length
  ? ARGV.filter((a) => !a.startsWith('--'))
  : DEFAULT_TARGETS

/** 允许的路径别名：`@/x` → `src/x` */
const ALIASES = [
  ['@/', 'src/'],
  ['~/', 'src/']
]

const EXT_CANDIDATES = ['', '.ts', '.tsx', '.js', '.mjs', '.vue', '/index.ts', '/index.vue', '/index.js']

/**
 * 把一条 import 说明符解析成磁盘上的真实文件。
 * 返回 文件路径 / `false`（有别名但找不到 → 路径写错了）/ `null`（bare 包名，不归这里管）
 */
function resolveSpec(spec, fromFile) {
  let base = null
  if (spec.startsWith('.')) {
    base = path.resolve(path.dirname(fromFile), spec)
  } else {
    for (const [alias, dir] of ALIASES) {
      if (spec.startsWith(alias)) {
        base = path.join(ROOT, dir, spec.slice(alias.length))
        break
      }
    }
  }
  if (!base) return null

  for (const ext of EXT_CANDIDATES) {
    const p = base + ext
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return p
  }
  return false
}

/**
 * TS/JS 文本 → JS 文本（只擦类型注解，**不做类型检查**）。
 *
 * ⚠️ 从旧的转译器换成 `ts.transpileModule` 时，有一个**必须自己补上**的语义差异：
 *    旧的是遇到 TS 语法错就**抛异常**，而 `ts.transpileModule` 是**把诊断塞进 `diagnostics` 返回、不抛** ——
 *    所以这里显式读诊断、由调用方报成问题；否则「抓 TS 语法错」这一项会**静默失效**
 *    （全绿，但其实什么都没查）。
 */
const TS_OPTS = {
  module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2020,
  jsx: ts.JsxEmit.Preserve
}

/** 返回 `{ code, errors }`；`errors` 是字符串化的语法错（空数组 = 没语法错） */
function transpileTs(code, fileName) {
  const out = ts.transpileModule(code, {
    compilerOptions: TS_OPTS,
    fileName,
    reportDiagnostics: true
  })
  const errors = (out.diagnostics || [])
    .filter((d) => d.category === ts.DiagnosticCategory.Error)
    .map((d) => ts.flattenDiagnosticMessageText(d.messageText, ' '))
  return { code: out.outputText, errors }
}

const IMPORT_RE = /(?:import|export)[\s\S]*?from\s*['"]([^'"]+)['"]|import\s*\(\s*['"]([^'"]+)['"]\s*\)/g
const CSS_URL_RE = /@import\s+['"]([^'"]+)['"]/g

let bad = 0
const fail = (f, msg) => {
  bad++
  console.log(`  [FAIL] ${f} -> ${msg}`)
}
const ok = (f, msg) => console.log(`  [OK]   ${f}${msg ? '  ' + msg : ''}`)

for (const rel of targets) {
  const file = path.join(ROOT, rel)
  if (!fs.existsSync(file)) {
    fail(rel, '文件不存在')
    continue
  }
  const source = fs.readFileSync(file, 'utf8')
  const problems = []
  // TS 转译器只能看 JS/TS —— .vue 要先取出 <script> 块，整份丢进去必然报「<template> 不合法」
  let scriptForTs = source

  if (file.endsWith('.vue')) {
    const { descriptor, errors } = parse(source, { filename: file })
    if (errors.length) problems.push('SFC 解析: ' + errors[0].message)

    scriptForTs = descriptor.scriptSetup?.content || descriptor.script?.content || ''

    try {
      if (descriptor.scriptSetup || descriptor.script) {
        compileScript(descriptor, { id: 'static-check' })
      }
    } catch (e) {
      problems.push('script setup: ' + String(e.message).split('\n')[0])
    }

    if (descriptor.template) {
      const r = compileTemplate({
        source: descriptor.template.content,
        filename: file,
        id: 'static-check'
      })
      if (r.errors.length) {
        const e = r.errors[0]
        problems.push('template: ' + (typeof e === 'string' ? e : e.message))
      }
    }
  }

  // TS 语法错：诊断在返回值里（不抛），必须显式报出来
  const tsResult = transpileTs(scriptForTs, file + '.script.ts')
  if (tsResult.errors.length) {
    problems.push('typescript: ' + tsResult.errors.slice(0, 3).join(' | '))
  }

  const seen = new Set()
  for (const m of source.matchAll(IMPORT_RE)) {
    const spec = m[1] || m[2]
    if (!spec || seen.has(spec)) continue
    seen.add(spec)
    if (resolveSpec(spec, file) === false) problems.push(`import 路径解析不到: ${spec}`)
  }
  for (const m of source.matchAll(CSS_URL_RE)) {
    if (resolveSpec(m[1], file) === false) problems.push(`@import 解析不到: ${m[1]}`)
  }

  if (problems.length) problems.forEach((p) => fail(rel, p))
  else ok(rel, `(${source.split('\n').length} 行, ${seen.size} 个外部 import)`)
}

// =====================================================================
// 布局结构断言 —— 智能体页「输入框吸底」+「顶部标题栏并进底部工具栏」
// =====================================================================
//
// 为什么断言**结构**而不是像素：像素要开浏览器量，而**智能体禁止操作浏览器**
// （见 `.codebuddy/rules/no-browser-automation.md`）。布局 bug 的根因全在结构里 ——
// 高度链有没有确定高度、滚动容器有没有 `min-height: 0`、输入区是不是滚动容器的兄弟节点、
// 有没有人把「贴纸式悬浮」加回来 —— 这些都能在源码上确定性断言，而且真的会红。

/** 取一份源码（找不到就当空串，由调用方判空） */
function readSource(rel) {
  const file = path.join(ROOT, rel)
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : ''
}

/** 只要 `<style>` 里的内容 */
function styleText(source) {
  return [...source.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map((m) => m[1]).join('\n')
}

/**
 * 去注释后的样式文本
 *
 * ⚠️ 必须先剥掉注释再断言：这些规则旁边就写着「**不要**改成 `position: fixed/absolute`」
 * 这种反例说明，不剥的话断言会被自己的注释判红（真踩过）。
 */
function cssOf(rel) {
  return styleText(readSource(rel)).replace(/\/\*[\s\S]*?\*\//g, '')
}

/** 去掉块注释（CSS/JS 的 `/* *​/` 与 HTML 的 `<!-- -->`）—— 注释里常写反例说明 */
function stripBlockComments(s) {
  return s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '')
}

/**
 * 一份源码的**代码文本**：块注释 + HTML 注释 + **整行** `//` 注释全部去掉。
 *
 * ⚠️ **删除类断言必须用它**（`L41` 就是）：某个东西被删掉之后，代码旁边往往会留一句
 *    「别再把它加回来」的说明 —— 那句话里**必然**写着刚被删掉的名字，不剥注释的话
 *    断言会被**自己的说明文字**判红（本文件 `cssOf` 的注释里记着这条已经真踩过）。
 *    剥完注释再 `includes(...)`，断的就是「**代码里**还有没有这个标识」。
 *
 * ⚠️ 只剥**整行**的 `//`（行首可带空白），不是「任何 `//` 之后都剥」：后者会把
 *    字符串里的 `https://…` 从中间切断，把一个只去掉注释的辅助函数变成一个破坏源码的东西。
 */
function codeText(rel) {
  return stripBlockComments(readSource(rel)).replace(/^[ \t]*\/\/.*$/gm, '')
}

/**
 * 取某个选择器的声明块（括号配平，够 SCSS 嵌套用）。
 * 选择器必须**紧跟着** `{`（中间只有空白）—— 否则 `.a` 会误配 `.a .b { }`。
 */
function cssRule(css, selector) {
  let from = 0
  for (;;) {
    const i = css.indexOf(selector, from)
    if (i < 0) return null
    const rest = css.slice(i + selector.length)
    const m = /^\s*\{/.exec(rest)
    if (m) {
      const start = i + selector.length + m[0].length - 1
      let depth = 0
      for (let j = start; j < css.length; j++) {
        if (css[j] === '{') depth++
        else if (css[j] === '}') {
          depth--
          if (depth === 0) return css.slice(start + 1, j)
        }
      }
      return null
    }
    from = i + selector.length
  }
}

/** 取 `<template #name>…</template>` 之间的源码（标签配平） */
function slotBlock(source, name) {
  const i = source.indexOf('#' + name)
  if (i < 0) return null
  const open = source.indexOf('>', i)
  if (open < 0) return null
  let depth = 1
  const re = /<\/?template\b/g
  re.lastIndex = open + 1
  let m
  while ((m = re.exec(source))) {
    if (m[0] === '<template') depth++
    else {
      depth--
      if (depth === 0) return source.slice(open + 1, m.index)
    }
  }
  return null
}

/** 模板 AST（compileTemplate 已经跑完 transform，`tag` 保留组件原大小写） */
function templateAst(rel) {
  const source = readSource(rel)
  if (!source) return null
  const { descriptor } = parse(source, { filename: rel })
  if (!descriptor.template) return null
  return compileTemplate({ source: descriptor.template.content, filename: rel, id: 'static-check' }).ast
}

/**
 * 把某个 SFC 的 `<script setup>` **在 Node 里真的跑一遍**，拿它的 computed 结果。
 *
 * 为什么需要：`AgentConfirmCard` 的「总数走 count、不走数组长度」那条分支
 * （`k === 'sample' && typeof p.count === 'number'`）**运行时从没被走到过** ——
 * 实测过的 preview 里 count 要么等于 sample 长度、要么根本不带 sample 键。
 * 光断言「某串字面量还在源码里」既弱（改成等价写法就假过）又会被注释骗过；
 * 这里直接喂 preview、看它算出什么标题，断的是**行为**。
 *
 * 做法（全程离线，**不碰浏览器**，也不加载 vue 运行时）：
 *   剥掉 import → `typescript` 把 TS 转成 JS → `new Function` 注入 `computed` / `defineProps` / `defineEmits` 三个桩。
 *   `defineProps` 桩忽略参数、直接返回调用方要喂的 preview（脚本里只读 `props.xxx`）。
 *
 * 返回 `{ ok: true, hasSample, lists, rows }` 或 `{ ok: false, why }`。
 *
 * ⚠️ `ok: false` 时**调用方必须判 FAIL**（fail-closed，绝不能当通过）—— 好消息是它**不会假绿**，
 *    退化的只是覆盖面。`why` 带着可诊断的原因，别把它压成一句「执行失败」。
 *
 * ⚠️ 这个 harness **只桩了三个 vue API，执行的是产品源码原样**（没有内联复制一份业务逻辑）。
 *    因此组件 `<script setup>` 里**新引入**一个 vue API（例如 `ref(0)`）时，这里会以
 *    `xxx is not defined` 失败 —— 那是**正确**的信号；修法只有一条：
 *    **把那个 API 加进下面的注入参数**（以及 `new Function` 的形参列表），
 *    **不要**因为「L17 红了」就反过来削弱 L17 的断言。
 *    也**不要**给这里加「合法 API 白名单」——那种名单本身会过期，是同一个坑。
 */
function runConfirmCard(preview) {
  const source = readSource(CONFIRM)
  if (!source) return { ok: false, why: `读不到 ${CONFIRM}` }
  const { descriptor } = parse(source, { filename: CONFIRM })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) return { ok: false, why: `${CONFIRM} 里没有 <script setup>` }
  // `new Function` 里没有模块作用域，import 必须先剥干净（剥不干净就判失败，别硬跑）
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  if (/\bimport\b/.test(noImport)) {
    return { ok: false, why: 'import 没剥干净（脚本里出现了新的 import 写法，剥 import 的正则需要同步更新）' }
  }
  const { code, errors } = transpileTs(noImport, CONFIRM + '.script.ts')
  if (errors.length) {
    return { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }
  }
  const computed = (fn) => ({ get value() { return fn() } })
  const defineProps = () => ({ preview })
  const defineEmits = () => () => {}
  try {
    const factory = new Function(
      'computed',
      'defineProps',
      'defineEmits',
      code + '\n;return { previewLists: previewLists, previewRows: previewRows, hasSample: hasSample }'
    )
    const out = factory(computed, defineProps, defineEmits)
    return {
      ok: true,
      hasSample: out.hasSample.value,
      lists: out.previewLists.value,
      rows: out.previewRows.value
    }
  } catch (e) {
    // 典型：脚本里用了没桩的 vue API → `xxx is not defined`（实测给 script setup 加 `ref(0)` 就是这个）
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    return {
      ok: false,
      why: m
        ? `script setup 用到了 \`${m[1]}\`，但它不在注入列表里（目前只注入 computed / defineProps / defineEmits）`
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

/**
 * 把 `AgentToolDetail` 的 `<script setup>` **在 Node 里真的跑一遍**，拿它的
 * `titleOf` / `restOf` / `rows`。
 *
 * 为什么必须真跑：这条 bug 的两个半边（标题被选成题库名 / 题干被整表摘掉）都长在
 * `titleOf` + `restOf` 这一层，而且**只有连起来才看得见** —— 断言「源码里还有没有
 * `TITLE_KEYS` 这个标识符」既弱（换个等价写法就假过）又会被注释骗过。
 *
 * 做法与 `runConfirmCard` 一致（全程离线，**不碰浏览器**，也不加载 vue 运行时）：
 *   剥 import → `typescript` 转译 → `new Function` 注入桩。
 *
 * ⚠️ 本组件用到的 vue API 与 `AgentConfirmCard` **不同**（多了 `ref` / `watch` /
 *    `withDefaults` / `defineOptions`），所以桩的清单也不一样。组件脚本里**新引入**一个
 *    没桩的 API 时会以 `xxx is not defined` 失败 —— 那是**正确**的信号，
 *    修法是把那个 API 加进下面的注入列表，**不要**因此削弱断言。
 * ⚠️ `defineProps` 桩返回 `{ data }`：`rows`（以及它依赖的 `visibleEntries`）读的是
 *    `props.data`，所以「这条 data 会渲染成哪些键值行」**必须按同一份 data 实例化一次**
 *    才算得出来 —— 这也是 `runToolDetail` 缓存工厂、按 data 新建实例的原因。
 *
 * 返回 `{ ok: true, titleOf, restOf, rowsOf }` 或 `{ ok: false, why }`。
 * ⚠️ `ok: false` 时调用方**必须判 FAIL**（fail-closed），`why` 带可诊断的原因。
 */
let __toolDetailFactory = null
function toolDetailFactory() {
  if (__toolDetailFactory) return __toolDetailFactory
  const source = readSource(TOOL_DETAIL)
  if (!source) {
    __toolDetailFactory = { ok: false, why: `读不到 ${TOOL_DETAIL}` }
    return __toolDetailFactory
  }
  const { descriptor } = parse(source, { filename: TOOL_DETAIL })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) {
    __toolDetailFactory = { ok: false, why: `${TOOL_DETAIL} 里没有 <script setup>` }
    return __toolDetailFactory
  }
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  if (/\bimport\b/.test(noImport)) {
    __toolDetailFactory = {
      ok: false,
      why: 'import 没剥干净（脚本里出现了新的 import 写法，剥 import 的正则需要同步更新）'
    }
    return __toolDetailFactory
  }
  const { code, errors } = transpileTs(noImport, TOOL_DETAIL + '.script.ts')
  if (errors.length) {
    __toolDetailFactory = { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }
    return __toolDetailFactory
  }
  try {
    const factory = new Function(
      'computed',
      'ref',
      'watch',
      'defineProps',
      'withDefaults',
      'defineOptions',
      code + '\n;return { titleOf: titleOf, restOf: restOf, rows: rows }'
    )
    __toolDetailFactory = { ok: true, factory }
  } catch (e) {
    __toolDetailFactory = { ok: false, why: `构造注入脚本失败：${String(e?.message || e)}` }
  }
  return __toolDetailFactory
}

/** 见 `toolDetailFactory` 的注释。`data` 就是「这一层要渲染的那个对象 / 数组」 */
function runToolDetail(data) {
  const f = toolDetailFactory()
  if (!f.ok) return f
  const computed = (fn) => ({ get value() { return fn() } })
  const ref = (v) => ({ value: v })
  const watch = () => {}
  const withDefaults = (p, d) => Object.assign({}, d, p)
  const defineOptions = () => {}
  const make = (d) => f.factory(computed, ref, watch, () => ({ data: d }), withDefaults, defineOptions)
  try {
    const api = make(data)
    return {
      ok: true,
      titleOf: (item) => api.titleOf(item),
      restOf: (item) => api.restOf(item),
      /** 某个对象会被渲染成哪些键值行（走产品源码的 `rows` + `visibleEntries`） */
      rowsOf: (d) => make(d).rows.value
    }
  } catch (e) {
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    return {
      ok: false,
      why: m
        ? `script setup 用到了 \`${m[1]}\`，但它不在注入列表里（目前只注入 computed / ref / watch / defineProps / withDefaults / defineOptions）`
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

/**
 * 遍历模板 AST。
 *
 * ⚠️ 只走 `children` 会**漏掉 `v-if` 分支**：`v-if` 的元素不在 children 上，
 * 而是被包进 `branches[].children`（NodeTypes.IF / IF_BRANCH）——
 * 漏了它，「删掉的节点又回来」这类断言会被一个 v-if 轻松绕过。
 */
function walkAst(node, cb) {
  cb(node)
  for (const branch of node.branches || []) walkAst(branch, cb)
  for (const child of node.children || []) walkAst(child, cb)
}

/**
 * 取某个指令的**表达式原文**（`:disabled` / `v-model` / `@click` 都走这个）；没有就给 null
 *
 * ⚠️ 复合表达式（例如 `!textImportContent.trim()`）在 AST 里是 `astType=8`，
 *    `exp.content` 是 **undefined** —— 只有 `loc.source` 存着原文。实测踩过：
 *    只看 `.content` 会把「有绑定」误判成「没绑定」。
 */
function expSource(directive) {
  const e = directive?.exp
  if (!e) return null
  const s = e.loc?.source ?? e.content
  return s == null ? null : String(s).trim()
}

/** 元素上某个 `v-bind:xxx`（含简写）的表达式原文 */
function boundExp(node, prop) {
  const d = (node?.props || []).find(
    (p) => p.type === 7 && p.name === 'bind' && p.arg && !Array.isArray(p.arg.content) && p.arg.content === prop
  )
  return expSource(d)
}

/** 元素上 `v-model` 的表达式原文（编译后是指令 `name=model`，不是 `modelValue` 的 bind） */
function modelExp(node) {
  return expSource((node?.props || []).find((p) => p.type === 7 && p.name === 'model'))
}

/** `node` 是否落在某个 `v-if` 节点里；命中就返回它的条件原文（拿不到给 null） */
function ifConditionOf(ast, target) {
  let hit = null
  walkAst(ast, (n) => {
    if (hit || n.type !== 9) return
    for (const b of n.branches || []) {
      walkAst(b, (x) => {
        if (x === target && !hit) hit = b.condition ?? n.codegenNode?.test ?? null
      })
    }
  })
  if (!hit) return null
  return String(hit.loc?.source ?? hit.content ?? '').trim() || null
}

/**
 * **直接**包住 `target` 的那个 `v-if` 的条件原文（拿不到给 null）。
 *
 * ⚠️ 与 `ifConditionOf` 的区别很关键，用错了会读到**外层**的条件：
 *   · `ifConditionOf` 找的是「任何一个把它包在里面的 v-if」—— 目标在**任何一层**
 *     条件分支里都算命中，所以它是「有没有被谁挡着」的判据；
 *   · 本函数只认「条件分支的**直接**子节点就是它」那一层 —— 目标自己那条 `v-if`。
 *
 * 为什么必须分开（实测踩过）：`.atp-item-blocked` 外面还套着清单那个
 * `v-if="!loading && rows.length"`，用 `ifConditionOf` 读回来的是**清单那句**，
 * 于是「这个标记只由 `t.disabled === 1` 决定」这条断言会读到错的表达式 —— 红了以后
 * 去改产品代码，就会把一句本来正确的 `v-if` 改坏。**别用外层条件去判内层节点。**
 *
 * ⚠️ 编译后元素上**不保留** `v-if` 指令（`transformIf` 会把它换成 IF 节点，元素本身
 *    进了 `branches[].children`），所以只能从 IF 节点这一侧读 —— 实测确认过。
 */
function ownConditionOf(ast, target) {
  let hit = null
  walkAst(ast, (n) => {
    if (hit || n.type !== 9) return
    for (const b of n.branches || []) {
      if ((b.children || []).some((c) => c === target)) {
        hit = b.condition ?? null
        return
      }
    }
  })
  if (hit == null) return null
  return String(hit.loc?.source ?? hit.content ?? '').trim() || null
}

/**
 * 把某个知识库组件的 `<script setup>` **在 Node 里真的跑一遍**（跑哪一个由 `file` 决定）。
 *
 * ⚠️ 2026-09-21 的刻意重构之后，这里**必须支持两个文件**：`KnowledgeBaseDrawer` 已被拆成
 *    **外壳**（入口按钮 + el-drawer，123 行），真正的内容全搬进了 `KnowledgeBasePanel`
 *    （悬浮助手的「我的知识库」tab 用的是同一个面板，两处只有一份实现）。
 *    判据于是跟着内容走：内容类（粘贴导入 / 屏蔽开关 / 搜索 / 取数失败）断 `KB_PANEL`，
 *    外壳类（挂载取徽标数字、打开抽屉时激活面板）断 `KB_SHELL`。
 *    改这里之前先读 `kbApiNames`：它把「harness 里的名字 → 组件里的名字」逐条列出来，
 *    并且**按文件分开** —— 两个组件的状态名不一样（面板里那个搜索词叫 `query`，
 *    抽屉里根本没有它），合成一份名单必然有一边是错的。
 *
 * 断的是**行为**，不是「源码里还有没有那串字面量」：
 *   · 挂载期到底有没有只调 `listKnowledgeBases`（而不是连锁 `listDocuments` + 轮询）；
 *   · 粘贴导入在**空正文**时到底发不发请求、正常正文发的参数对不对、后端拒绝后弹窗关不关。
 *
 * 为什么必须真跑：这几条都属于「点开才知道」的路径 —— 空正文那条正是**后端会兜底**
 * （`code 400 内容不能为空`）的那条，所以「前端没拦」在静态上看不出任何异常，只有跑起来
 * 数一数请求次数才分得清。
 *
 * 做法与 `runConfirmCard` 一致（全程离线，**不碰浏览器**，也不加载 vue 运行时）：
 *   剥 import → `typescript` 转译 → `new Function` 注入桩 → 调用并读结果。
 *
 * 桩分两类，别混：
 *   · 框架/浏览器（`ref` / `computed` / `onMounted` / `window` / `ElMessage`）—— 只为了让它跑起来；
 *   · `@/api/ai/rag` 的接口 —— 桩成**记账本**（`calls`），断言就断在「谁被调了几次、参数是什么」。
 *
 * ⚠️ `ok: false` 时调用方**必须判 FAIL**（fail-closed，不能当通过）。`why` 带的是可诊断的原因。
 * ⚠️ 这个 harness 执行的是**产品源码原样**。组件脚本里**新引入**一个没桩的全局
 *   （例如 `watch`）时，这里会以 `xxx is not defined` 失败 —— 那是**正确**的信号，
 *   修法是把那个 API 加进 `stubs`，**不要**因为断言红了就把它写松。
 *   **反过来**：名字在判据自己的名单里（`kbApiNames` / `stubs`）时，报出来的话必须指对方向 ——
 *   那是判据过期或桩缺失，不是「产品代码引用了未定义的标识符」（见 `kbApiNames` 上方那段）。
 */
function kbRuntime(file, cfg = {}) {
  const source = readSource(file)
  if (!source) return { ok: false, why: `读不到 ${file}` }
  const { descriptor } = parse(source, { filename: file })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) return { ok: false, why: `${file} 里没有 <script setup>` }
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  if (/\bimport\b/.test(noImport)) {
    return { ok: false, why: 'import 没剥干净（脚本里出现了新的 import 写法，剥 import 的正则需要同步更新）' }
  }
  const { code, errors } = transpileTs(noImport, file + '.script.ts')
  if (errors.length) return { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }

  const kbsResult = cfg.kbsResult ?? { code: 200, data: cfg.kbs || [] }
  const docsResult = cfg.docsResult ?? { code: 200, data: cfg.docs || [] }
  const importResult = cfg.importResult ?? { code: 200, data: { docId: 4242, fileName: '粘贴的笔记.txt', status: 1 } }
  const updateResult = cfg.updateResult ?? { code: 200 }

  const calls = {
    listKnowledgeBases: 0,
    listDocuments: 0,
    uploadDocument: 0,
    setTimeout: 0,
    importDocumentText: [],
    /** 「谁被拨了、发了什么载荷」—— 屏蔽开关的键名判据就断在这里 */
    updateKnowledgeBase: []
  }
  const msgs = { error: [], success: [], warning: [], warn: [] }
  const mounted = []

  const stubs = {
    // ---- 框架 / 编译宏 / 浏览器 ----
    ref: (v) => ({ value: v }),
    computed: (fn) => ({
      get value() {
        return fn()
      }
    }),
    onMounted: (fn) => mounted.push(fn),
    onBeforeUnmount: () => {},
    // 抽屉的 `onOpen` 里 `await nextTick()` —— 它是**产品代码**要的 vue API，
    // 离线跑时给它一个立刻 resolve 的空实现（不桩的话 onOpen 整条路走不进去，
    // 报出来的却是「产品代码用了未定义的标识符」，方向是反的）。
    nextTick: async () => {},
    // `KnowledgeBasePanel` 的 `<script setup>` 里有 `<script setup>` 级的编译宏调用
    // （`withDefaults(defineProps<…>(), …)` / `defineEmits<…>()`）—— 真编译时它们被
    // `compileScript` 改写掉，但这里是**把源码原样丢进 `new Function`**，
    // 所以这三个宏必须自己桩上，否则面板一进来就 `withDefaults is not defined`。
    defineProps: () => ({ closable: false }),
    withDefaults: (props) => props,
    defineEmits: () => () => {},
    defineOptions: () => {},
    defineExpose: () => {},
    window: {
      setTimeout: () => {
        calls.setTimeout += 1
        return 0
      },
      clearTimeout: () => {}
    },
    ElMessage: {
      error: (m) => msgs.error.push(String(m)),
      success: (m) => msgs.success.push(String(m)),
      warning: (m) => msgs.warning.push(String(m))
    },
    ElMessageBox: { prompt: async () => ({ value: '' }), confirm: async () => {} },
    // 产品代码的 `console.warn` 是**诊断**，不是判据 —— 收进 `msgs.warn` 而不是打到 stdout：
    // 不然「故意喂坏响应」的用例（L26）会在全绿的运行里刷出一串堆栈，看起来像失败。
    // 收着也不丢信息：需要的断言可以读 `msgs.warn`。
    console: {
      warn: (...a) => msgs.warn.push(a.map((x) => String(x?.message || x)).join(' ')),
      error: (...a) => msgs.warn.push(a.map((x) => String(x?.message || x)).join(' '))
    },
    // ---- @/api/ai/rag：常量取真值（都是数字），接口桩成记账本 ----
    DOC_FAILED: 4,
    DOC_PARSED: 3,
    KB_FILE_ACCEPT: '.txt,.md,.pdf,.docx,.doc',
    KB_FILE_EXTENSIONS: ['txt', 'md', 'pdf', 'docx', 'doc'],
    canReprocessDocument: () => false,
    createKnowledgeBase: async () => ({ code: 200 }),
    deleteDocument: async () => ({ code: 200 }),
    deleteKnowledgeBase: async () => ({ code: 200 }),
    documentTagType: () => 'info',
    getDocumentChunks: async () => ({ code: 200, data: [] }),
    getDocumentStatus: async () => ({ code: 200, data: { done: true, ok: true } }),
    importDocumentText: async (...args) => {
      calls.importDocumentText.push(args)
      return importResult
    },
    isDocumentProcessing: () => false,
    isDocumentSearchable: () => false,
    isSupportedKbFile: () => true,
    listDocuments: async () => {
      calls.listDocuments += 1
      return docsResult
    },
    listKnowledgeBases: async () => {
      calls.listKnowledgeBases += 1
      if (cfg.kbsThrows) throw new Error('列表请求炸了')
      // `kbsResult` 可以是一个**函数**：按第几次请求给不同响应。
      // 「写成功之后重取列表、服务端回值已经翻转」这类断言需要它
      // （固定一份响应就只能测出「假成功」那一面）。
      return typeof kbsResult === 'function' ? kbsResult(calls.listKnowledgeBases) : kbsResult
    },
    reprocessDocument: async () => ({ code: 200 }),
    searchKnowledge: async () => ({ code: 200, data: { hits: [] } }),
    updateKnowledgeBase: async (...args) => {
      calls.updateKnowledgeBase.push(args)
      if (cfg.updateThrows) throw new Error('写请求炸了')
      return updateResult
    },
    uploadDocument: async () => {
      calls.uploadDocument += 1
      return { code: 200, data: { docId: 1 } }
    }
  }

  const names = Object.keys(stubs)
  const pairs = kbApiNames(file)
  if (!pairs.length) {
    // 判据侧没为这个文件登记名字 → 立刻失败（**fail-closed**）。不能退化成「探不到任何名字、
    // 于是断言读到一堆 undefined、看着是绿的」—— 那是本文件最怕的假绿。
    return { ok: false, why: `kbRuntime 的判据名单（kbApiNames）里没有 ${file} —— 先给它登记 API 名单` }
  }
  // 逐个名字用 `typeof` 取：`typeof` 对**根本没有这个名字**的情况不抛（给 `undefined`），
  // 而直接写 `return { kbCount, busy, … }` 会在**第一个不存在的名字**上整句抛掉 ——
  // 那样连「哪些名字还在」都拿不到，只能猜是哪一边的错（八条假红就是这么来的）。
  const probe = code +
    `
;return {
  __api: { ${pairs.map(([api, expr]) => `${JSON.stringify(api)}: (typeof ${expr} === 'undefined' ? undefined : ${expr})`).join(', ')} },
  __present: { ${pairs.map(([api, expr]) => `${JSON.stringify(api)}: (typeof ${expr} !== 'undefined')`).join(', ')} }
}`
  try {
    const factory = new Function(...names, probe)
    const { __api: api, __present: present } = factory(...names.map((n) => stubs[n]))
    const goneFromComponent = pairs.filter(([api]) => !present[api])
    if (goneFromComponent.length) {
      return {
        ok: false,
        why:
          `${file} 的判据名单（kbApiNames）里有 ` +
          goneFromComponent.map(([api, expr]) => '`' + api + '`' + (api === expr ? '' : `（读组件的 \`${expr}\`）`)).join('、') +
          '，但组件**已经不再定义它了** —— 这是**判据这一侧的名单过期**（组件那侧根本没这个名字），' +
          '不是「组件用了未定义的标识符」。组件真的删掉这个状态、且没有断言再用它时，' +
          '把它们从 kbApiNames 里去掉；若断言还得读它，那是组件改错了，别改判据。' +
          '⚠️ 名字**也可能只是搬去了另一个组件**（2026-09-21 知识库抽屉拆成「外壳 + 面板」）：' +
          '那就要把这个文件换成它现在所在的那一个，而不是把名字删掉了事。'
      }
    }
    return {
      ok: true,
      api,
      calls,
      msgs,
      /**
       * 跑「进页面」这条路径：执行脚本里注册的 `onMounted` 回调，再**排空几轮宏任务**。
       *
       * ⚠️ 光 `await fn()` 不够：`onMounted(() => { loadKbs(false) })` 这个箭头函数**没有 return**，
       * 所以 await 回调本身等不到请求回来。所有桩都是纯 async（不碰定时器/IO），
       * 它们的链路全在微任务里跑完 —— 一个 `setImmediate` 就够，这里排 3 轮留余量。
       */
      runMount: async () => {
        if (!mounted.length) {
          return { ok: false, why: `${file} 没有注册 onMounted —— 进页面时不会去取知识库列表，徽标数字还是空的` }
        }
        for (const f of mounted) await f()
        for (let i = 0; i < 3; i++) await new Promise((r) => setImmediate(r))
        return { ok: true }
      }
    }
  } catch (e) {
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    // 走到这里说明**脚本自己**在执行时炸了。名字若是判据点名要的（kbApiNames 的两侧 + stubs），
    // 先把话说清是哪一边；不在这三份名单里的，才是组件侧的问题（新 import 没剥干净、变量名写错）。
    const namedByHarness = m && (pairs.some(([a, x]) => a === m[1] || x === m[1]) || names.includes(m[1]))
    return {
      ok: false,
      why: m
        ? namedByHarness
          ? `注进去的脚本执行时用到了 \`${m[1]}\`，这个名字在**判据的名单**里（kbApiNames / stubs 都有它）—— ` +
            '先看组件是不是把它删了 / 改了名：若组件确实删了它（例如随某块 UI 一起删、或搬去了另一个组件），' +
            '那是**判据名单过期**，把名字从 kbApiNames 去掉（搬走了就把 `file` 换成它现在所在的那个）；' +
            '若组件没删却仍报未定义，那是 `stubs` 少了一项，把它加进 stubs。'
          : `组件自己的 <script setup> 里用到了**没有定义**的 \`${m[1]}\` —— 这是**产品代码**的问题` +
            '（新加的 import 没被剥 import 的正则剥掉、或变量名写错），不是判据的问题，别改断言。'
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

/**
 * 「模板引用的标识符必须都能在 `<script setup>` 里找到」——**对任意 SFC 都成立**的守门判据。
 *
 * 为什么需要（真事故）：知识库入口按钮**点了没反应**。模板里 4 个标识符
 * （`kbFilter` / `filteredKbs` / `togglingKbId` / `toggleKbDisabled`）在脚本里零定义，
 * 编译成 `_ctx.X`，渲染时 `!filteredKbs.length` 抛 TypeError，**整个组件挂载失败** ——
 * 而语法 / import 检查**全绿**（这也是本文件「静态检查的两个洞」里的那个洞）。
 *
 * 2026-09-21 抽屉拆成「外壳 + 面板」之后，这条判据**两个文件都要跑**：
 * 面板现在有 1900 行、模板里 69 个 `_ctx.` 引用，而它的 `activate()` 由宿主在
 * 「显示它的那一刻」调用 —— 挂载失败的症状是「点开抽屉是一片空白」，比入口按钮不亮更难查。
 *
 * ⚠️ 这里**故意不传** `bindingMetadata`。传了之后已声明的标识符会编译成 `$setup.x`，
 *    模板里的 `_ctx.` 引用集实测会变成**空集**（探针输出 `WITHMETA _ctx refs: []`）
 *    ⇒ 断言退化成「永远通过」。不传时模板里**每一个**标识符都以 `_ctx.x` 出现，
 *    减掉脚本绑定剩下的正是「模板要用、脚本里没有」的那些。
 */
function templateIdentifierProblems(file) {
  const problems = []
  const source = readSource(file)
  if (!source) return `读不到 ${file}`
  const { descriptor } = parse(source, { filename: file })
  if (!descriptor.template) return `${file} 没有模板`

  let bindings = new Set()
  try {
    bindings = new Set(Object.keys(compileScript(descriptor, { id: 'static-check' }).bindings || {}))
  } catch (e) {
    return 'compileScript 失败，拿不到绑定表：' + String(e?.message || e).split('\n')[0]
  }

  const compiled = compileTemplate({
    source: descriptor.template.content,
    filename: file,
    id: 'static-check'
  })
  if (compiled.errors?.length) {
    const e0 = compiled.errors[0]
    problems.push('模板编译报错：' + (typeof e0 === 'string' ? e0 : e0.message))
  }
  const refs = [...new Set([...compiled.code.matchAll(/_ctx\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]))]
  // 实例内建（`$slots` / `$emit` …）不是 `<script setup>` 的绑定，白名单放行
  const INSTANCE = new Set([
    '$slots', '$attrs', '$emit', '$props', '$refs', '$el', '$options',
    '$forceUpdate', '$nextTick', '$watch', '$parent', '$root', '$data',
    '$set', '$delete', '$isServer', '$ssrContext'
  ])
  const missing = refs.filter((r) => !INSTANCE.has(r) && !bindings.has(r))
  if (missing.length) {
    problems.push(
      '模板引用了 ' +
        missing.length +
        ' 个脚本里没有定义的标识符：' +
        missing.join('、') +
        ' —— 渲染时它们解析成 undefined，`!x.length` 这类表达式当场抛 TypeError，' +
        '**整个组件挂载失败**（入口按钮点了没反应 / 点开面板一片空白就是这个症状）'
    )
  }
  // 反向对照：一条 `_ctx.` 都扫不到说明是**扫描口径**坏了，不能当通过
  if (!refs.length) {
    problems.push('模板里一个 `_ctx.` 引用都没扫到 —— 这条断言的扫描口径坏了（别当成通过）')
  }
  return problems.length ? problems.join('；') : null
}

/**
 * `el-switch` 在 **setup 期**会不会自己 emit 一次？会的话 emit 的是什么值？
 *
 * 照抄已安装的 `element-plus@2.14.5` 的真实语义（读的是
 * `node_modules/element-plus/es/components/switch/src/switch.vue_vue_type_script_setup_true_lang.mjs`）：
 *
 * ```js
 * const isControlled = ref(props.modelValue !== false);                       // :45
 * const actualValue = computed(() => isControlled.value ? props.modelValue : false); // :67-69
 * const checked = computed(() => actualValue.value === props.activeValue);    // :70
 * if (![props.activeValue, props.inactiveValue].includes(actualValue.value)) {// :71
 *   emit(UPDATE_MODEL_EVENT, props.inactiveValue);                            // :73
 * }
 * ```
 *
 * ⇒ 本组件**不写** `:active-value` / `:inactive-value`，所以取值域就是 `[true, false]`，
 *   而 emit 出去的值**恒是 `props.inactiveValue` = `false`**（**不是**「当前值的取反」）。
 *   ⚠️ 关键在 `:45` 那个 `!== false`：绑定值只要**不是 `false`**（`0` / `1` / `undefined` 都算），
 *      `isControlled` 就是 `true`、`actualValue` 就是那个原始值，于是命中 `:71` 的域检查、emit 一次。
 *      绑定值恒为 `true`/`false` 时，两条路都落在域里 —— **不可能 emit**。这就是本组件
 *      `toolEnabled` 必须返回布尔的机械理由（`:model-value` 绑 `t.disabled` 的 0|1 就会踩）。
 *
 * 返回 `null` = 不会 emit；否则返回会被 emit 出去的那个值（交给 `@update:model-value` 处理）。
 */
function elSwitchMountEmit(modelValue) {
  const ACTIVE = true
  const INACTIVE = false
  const isControlled = modelValue !== INACTIVE // :45
  const actual = isControlled ? modelValue : INACTIVE // :67-69
  if ([ACTIVE, INACTIVE].includes(actual)) return null // :71 落在取值域里 → 不 emit
  return INACTIVE // :73 emit(UPDATE_MODEL_EVENT, props.inactiveValue)
}

/**
 * 造一条 `/ai/agent/tools` 的条目：**Function Calling schema + 开关状态**。
 *
 * 形状必须与后端一致（`{ type, function: { name, description }, disabled }`）——
 * 组件只认**这一种**形状（读 `entry.function`，L44 守着那一格）：
 * `meta` 事件那种**拍平**的 `{ name, description }` 从来没进过清单那条路，
 * 组件里也**没有**为它兜底（早先那条兜底连一个调用点都没有，已删）。
 * 用错形状造数据，测出来的就是「组件不认它」而不是真要测的东西。
 *
 * `disabled` 不传就**不带这个键**（缺省 = 启用），与后端「这一列还没下发」的旧数据一致。
 */
const agentTool = (name, disabled, zh) => ({
  type: 'function',
  function: { name, description: `${name} 的说明` },
  // 界面侧中文层（**在 `function` 外面**）：真实后端一定会下发，fixture 也必须带上 ——
  // 否则「面板显示中文」这类断言是在一个**不可能出现的形状**上跑的。
  // ⚠️ 两层用**一眼能分辨**的值（英文描述 vs 中文名），读错层时断言才会红而不是静默通过。
  label: zh?.label ?? `${name}·中文名`,
  descriptionZh: zh?.descZh ?? `${name} 的中文说明`,
  ...(disabled === undefined ? {} : { disabled })
})

// ⚠️ 这里原来有**第二个** fixture `metaTool()`（`meta` 事件那种拍平的条目形状）。
//    它唯一的用户是 L41 里那块脚注（「本次运行下发 N 个工具」）的三态断言 —— 脚注已按
//    用户裁决整块删除（2026-09-21），`tools` prop 也没了，所以它**一个消费者都不剩**。
//    没人用的 fixture 留着只会让下一个人以为「清单还有第二种形状」，一并删掉。

/**
 * 一个会**记住改动**的服务端桩：`payload` 交给 `toolPopoverRuntime`，`save` 当
 * `saveAgentToolPref` 的返回 —— 每次写先记下改动，再回显**当前**的全量清单。
 *
 * ⚠️ 回显必须基于**当前**状态，不能基于一开始那份冻结的清单：拿冻结那份回显的话，
 *    第二次写会把第一次的改动悄悄「回滚」掉，断言读到的「当前状态」就是错的。
 *    （L36 的第一版就是这么写的，红了以后去改产品代码就会把对的改坏 —— 桩错了，不是实现错了。）
 */
const toolsServer = (list) => {
  let cur = list.map((t) => ({ ...t }))
  return {
    payload: () => ({ tools: cur }),
    save: (tool, disabled) => {
      cur = cur.map((t) => ((t.function || t).name === tool ? { ...t, disabled } : t))
      return { ok: true, reason: '', payload: { tools: cur } }
    },
    /**
     * 批量写（面板上的「全选」）—— 与后端 `set_all_tools_disabled` **同语义**：
     * 一次改全部，回显改完之后的**当前**全量清单（不是一开始那份冻结的）。
     */
    saveAll: (disabled) => {
      cur = cur.map((t) => ({ ...t, disabled }))
      return { ok: true, reason: '', payload: { tools: cur } }
    }
  }
}

/**
 * 把 `AgentToolPopover` 的 `<script setup>` **在 Node 里真的跑一遍**。
 *
 * 断的是**行为**，不是「源码里还有没有那串字面量」：
 *   · 挂载期到底取了几次清单（不是点开才取、也不是每次点击都取）；
 *   · 拨开关时**发出去的载荷**是什么（工具名 + `disabled` 是 **0|1 整数**）；
 *   · 服务端回 `ok: false`（假成功）时开关有没有被本地翻过去。
 *
 * 为什么必须真跑：这三条都属于「点开才知道」的路径。前端静态检查**不做类型检查**
 * （`ts.transpileModule` 只擦类型注解），所以「第二个参数传了布尔」「键名写成 blocked」
 * 「用本地翻转冒充保存成功」在源码上都「看起来没问题」，只有跑起来数一数才分得清。
 *
 * 做法与 `kbRuntime` / `runConfirmCard` 一致（全程离线，**不碰浏览器**，也不加载 vue 运行时）：
 *   剥 import → `typescript` 转译 → `new Function` 注入桩 → 调函数 / 读 computed。
 *
 * ⚠️ `ok: false` 时调用方**必须判 FAIL**（fail-closed，绝不能当通过）。
 * ⚠️ 这里执行的是**产品源码原样**。组件脚本里**新引入**一个没桩的名字时，
 *    这里会以 `xxx is not defined` 失败 —— 那是**正确**的信号，修法是把那个名字加进 `stubs`，
 *    **不要**因为断言红了就把断言写松。
 * ⚠️ 反过来，**判据这一侧**（`API_NAMES` / `stubs`）跟组件对不上时，报出来的话必须指对方向 ——
 *    组件删掉一个状态、而这里还点名要它，症状长得像「产品代码用了未定义标识符」，其实是
 *    **判据过期**（2026-09-21 八条假红就是这么来的，详见 `API_NAMES` 上方那段）。
 *
 * cfg:
 *   · `props`        —— 喂给组件 props（**当前只有 `{ model }`**；`tools` / `runModel` 已随脚注删除）
 *   · `payload`      —— `fetchAgentToolsForUi()` 的返回；可以传函数，按第几次请求给不同响应
 *   · `save`         —— `saveAgentToolPref()` 的返回；可以传函数（拿得到它收到的参数）
 *   · `fetchThrows`  —— 让取清单抛异常
 */
function toolPopoverRuntime(cfg = {}) {
  const source = readSource(POPOVER)
  if (!source) return { ok: false, why: `读不到 ${POPOVER}` }
  const { descriptor } = parse(source, { filename: POPOVER })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) return { ok: false, why: `${POPOVER} 里没有 <script setup>` }
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  if (/\bimport\b/.test(noImport)) {
    return { ok: false, why: 'import 没剥干净（脚本里出现了新的 import 写法，剥 import 的正则需要同步更新）' }
  }
  const { code, errors } = transpileTs(noImport, POPOVER + '.script.ts')
  if (errors.length) return { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }

  const propsArg = cfg.props || {}
  const calls = { fetchAgentToolsForUi: 0, saveAgentToolPref: [], saveAllToolPrefs: [] }
  const msgs = { error: [], success: [], warning: [], warn: [] }
  const mounted = []

  const stubs = {
    // ---- 框架 / 编译宏 ----
    ref: (v) => ({ value: v }),
    computed: (fn) => ({
      get value() {
        return fn()
      }
    }),
    onMounted: (fn) => mounted.push(fn),
    // ⚠️ 组件当前**只声明了一个 prop**（`model`），桩里就只回这一个：
    //    多留着 `tools` / `runModel` 会让「那个 prop 还在不在」在断言里失真 ——
    //    它们已随整块脚注按用户裁决删除（2026-09-21），连一个消费者都没有了。
    defineProps: () => ({
      model: propsArg.model || ''
    }),
    // ---- Element Plus / 图标 ----
    ElMessage: {
      error: (m) => msgs.error.push(String(m)),
      success: (m) => msgs.success.push(String(m)),
      warning: (m) => msgs.warning.push(String(m))
    },
    Tools: {},
    // 产品代码的 `console.warn` 是**诊断**，不是判据（「取清单抛异常」那条用例会走到它）——
    // 收进 `msgs.warn` 而不是打到 stdout，否则全绿的运行里会刷出一段看起来像失败的堆栈。
    console: {
      warn: (...a) => msgs.warn.push(a.map((x) => String(x?.message || x)).join(' ')),
      error: (...a) => msgs.warn.push(a.map((x) => String(x?.message || x)).join(' '))
    },
    // ---- @/api/ai/agentDsFree：桩成**记账本**，断言断在「谁被调了几次、参数是什么」----
    fetchAgentToolsForUi: async () => {
      calls.fetchAgentToolsForUi += 1
      if (cfg.fetchThrows) throw new Error('清单请求炸了')
      const p = cfg.payload
      if (typeof p === 'function') return p(calls.fetchAgentToolsForUi)
      return p || { tools: [] }
    },
    saveAgentToolPref: async (...args) => {
      calls.saveAgentToolPref.push(args)
      if (cfg.saveThrows) throw new Error('写请求炸了')
      const s = cfg.save
      if (typeof s === 'function') return s(...args)
      return s || { ok: true, payload: null, reason: '' }
    },
    /**
     * 批量写（「全选」）—— 与 `saveAgentToolPref` **同一套桩口径**。
     * ⚠️ 单独一个记账本（`calls.saveAllToolPrefs`）：挂载期零写入那条断言要分别数
     *    「逐行写」与「批量写」，合成一个计数器就分不清是哪条路漏写了。
     */
    saveAllToolPrefs: async (...args) => {
      calls.saveAllToolPrefs.push(args)
      if (cfg.saveAllThrows) throw new Error('批量写请求炸了')
      const s = cfg.saveAll
      if (typeof s === 'function') return s(...args)
      return s || { ok: true, payload: null, reason: '' }
    }
  }

  const names = Object.keys(stubs)
  /**
   * harness 要从组件里**取出来**的名字（断言读的就是它们）。
   *
   * ⚠️ 这是**判据这一侧**的清单，它必须跟着组件一起改。原来这句 `return` 是写死的，
   *    组件删掉一个 `const`（2026-09-21：脚注按用户裁决删除，`showRunToolCount` 随之消失）
   *    而名单没跟着改时，`new Function` 里那句 `return { … }` 会在**第一个不存在的名字**上
   *    整句抛掉，报出来的是：
   *      「script setup 用到了 `showRunToolCount`，但它不在 toolPopoverRuntime 的桩列表里」
   *    —— **这句话指错了方向**：它读起来像「产品代码引用了没定义的标识符」，
   *    真相是**判据的名单过期了**。于是 L34–L39 / L42 / L44 八条齐刷刷红在同一句上，
   *    每一条都在冤枉组件（八条假红）。判据工具的覆盖面不足会**伪装成「实现有问题」**，
   *    所以下面改成：先用 `typeof` **逐个探存在性**，再决定报哪一边的错。
   *
   * ⚠️ 加/删这个名字清单时**两边一起看**：这里少一个 → 断言读不到它（`TypeError` 或 false 绿）；
   *    这里多一个 → 立刻以「名单过期」红给你看（就是要它响）。
   */
  const API_NAMES = [
    'rows', 'loading', 'badgeCount', 'enabledCount', 'toolEnabled',
    'toggleTool', 'load', 'togglingName', 'entryTitle', 'headSub', 'toRow',
    // 2026-09-22 新增：中文层（`label` / `descZh` 走 `toRow`）、搜索（`keyword` / `matchedRows`）、
    // 「全选」（`allEnabled` / `bulkBusy` / `busy` / `toggleAll`）
    'keyword', 'matchedRows', 'allEnabled', 'bulkBusy', 'busy', 'toggleAll'
  ]
  // 逐个名字用 `typeof` 取：`typeof` 对**根本没有这个名字**的情况不抛（给 `undefined`），
  // 而直接写 `return { rows, … }` 会在第一个不存在的名字上整句抛掉 ——
  // 那样连「哪些名字还在」都拿不到，只能猜是哪一边的错。
  const probe = code +
    `
;return {
  __api: { ${API_NAMES.map((n) => `${JSON.stringify(n)}: (typeof ${n} === 'undefined' ? undefined : ${n})`).join(', ')} },
  __present: { ${API_NAMES.map((n) => `${JSON.stringify(n)}: (typeof ${n} !== 'undefined')`).join(', ')} }
}`
  try {
    const factory = new Function(...names, probe)
    const { __api: api, __present: present } = factory(...names.map((n) => stubs[n]))
    const goneFromComponent = API_NAMES.filter((n) => !present[n])
    if (goneFromComponent.length) {
      return {
        ok: false,
        why:
          `toolPopoverRuntime 的 API 名单里有 ${goneFromComponent.map((n) => '`' + n + '`').join('、')}，` +
          '但组件**已经不再定义它了** —— 这是**判据这一侧的名单过期**（组件那侧根本没这个名字），' +
          '不是「组件用了未定义的标识符」。组件真的删掉这个状态、且没有断言再用它时，' +
          `把它们从 API_NAMES 里去掉；若断言还得读它，那是组件改错了，别改判据。`
      }
    }
    return {
      ok: true,
      api,
      calls,
      msgs,
      /** 有没有注册 `onMounted`（「点开才取清单」就没有它） */
      mountedCount: mounted.length,
      /**
       * 跑「进页面」这条路径：执行脚本里注册的 `onMounted` 回调，再**排空几轮宏任务**。
       *
       * ⚠️ 光 `await fn()` 不够：`onMounted(load)` 里那个 `load` 是 async 的、但
       * `onMounted` 的回调**没有 return**，所以 await 它本身等不到请求回来。
       * 所有桩都是纯 async（不碰定时器 / IO），链路全在微任务里跑完 —— 一个
       * `setImmediate` 就够，这里排 3 轮留余量。
       */
      runMount: async () => {
        if (!mounted.length) {
          return {
            ok: false,
            why: '组件没有注册 onMounted —— 清单要等用户点开弹层才请求，点开时会先看到一个转圈'
          }
        }
        for (const f of mounted) await f()
        for (let i = 0; i < 3; i++) await new Promise((r) => setImmediate(r))
        return { ok: true }
      }
    }
  } catch (e) {
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    // 走到这里说明**脚本自己**在执行时炸了。名字若是判据点名要的（API_NAMES / stubs），
    // 先把话说清是哪一边；不在这两份名单里的，才是组件侧的问题（新 import 没剥干净、变量名写错）。
    const namedByHarness = m && (API_NAMES.includes(m[1]) || names.includes(m[1]))
    return {
      ok: false,
      why: m
        ? namedByHarness
          ? `注进去的脚本执行时用到了 \`${m[1]}\`，这个名字在**判据的名单**里（API_NAMES / stubs 都有它）—— ` +
            '先看组件是不是把它删了 / 改了名：若组件确实删了它（例如随某块 UI 一起删），那是**判据名单过期**，' +
            '把名字从 API_NAMES 去掉；若组件没删却仍报未定义，那是 `stubs` 少了一项，把它加进 stubs。'
          : `组件自己的 <script setup> 里用到了**没有定义**的 \`${m[1]}\` —— 这是**产品代码**的问题` +
            '（新加的 import 没被剥 import 的正则剥掉、或变量名写错），不是判据的问题，别改断言。'
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

/**
 * 一个节点的**直接子元素**（按模板顺序），会**穿透 `v-if`**。
 *
 * ⚠️ 带 `v-if` 的元素在**编译后**的 AST 里被包成 `NodeTypes.IF`(9)：元素本身不在
 * 父节点的 `children` 上，而是躲在 `branches[0].children` 里。所以
 * `children.filter(c => c.type === 1)` **会把它整个漏掉** —— 症状是「节点明明在，
 * 断言却说找不到」（L14 就踩过：`.agent-foot` 有 `v-if="hasRun"`）。
 */
const directElements = (parent) =>
  (parent.children || []).flatMap((c) => {
    if (c.type === 1) return [c]
    if (c.type === 9 && c.branches?.length) {
      return c.branches[0].children.filter((x) => x.type === 1)
    }
    return []
  })

/** 一个节点上的 class 列表 */
const nodeClasses = (node) =>
  (node.props || [])
    .filter((p) => p.type === 6 && p.name === 'class')
    .flatMap((p) => String(p.value?.content || '').split(/\s+/))
    .filter(Boolean)

/** 按遍历顺序取第一个满足条件的节点（没找到给 null） */
function firstNode(ast, pred) {
  let found = null
  walkAst(ast, (n) => {
    if (!found && pred(n)) found = n
  })
  return found
}

/**
 * 一个节点子树里**看得见的文案**（TEXT + 插值表达式的**原文**）
 *
 * ⚠️ 插值的原文在 `content.loc.source`，**不是** `content.content`：
 *    复合表达式（`kbFilter.trim()`）在 AST 里是 `astType=8`，`content.content` 是
 *    **undefined**（实测探针输出就是 `null`）—— 只看 `.content` 会把
 *    "文案里有用户输入的词" 误判成 "没有"。这条坑与 `expSource` 是同一个。
 */
function nodeText(node) {
  const out = []
  walkAst(node, (x) => {
    if (x.type === 2) out.push(String(x.content))
    else if (x.type === 5) out.push(String(x.content?.loc?.source ?? ''))
    // 12 = NodeTypes.TEXT_CALL：**静态文本**在「父元素里同时还放着元素子节点」时会被编译成它
    // （`createTextVNode("…")` 的 hoisted call），原文在 `loc.source` 里。
    // ⚠️ 漏掉它会**静默少读半句话**（实测 `.atp-foot-row`：`本次运行下发 N 个工具` 只读回
    //    「tools.length 个工具」），于是「文案里必须有某句话」的断言会以「文案其实是 Y」红掉，
    //    而产品代码本来是对的 —— 与 `ifConditionOf` 读错层那次是同一类坑：
    //    **判据工具自己的覆盖面不足，会伪装成实现有问题**。凡是要断「看得见的文案」，都得带上这一支。
    else if (x.type === 12) out.push(String(x.loc?.source ?? ''))
  })
  return out.join('')
}

/**
 * 取声明块里某个属性的第一个值。
 *
 * 前缀 `(?:^|[;{\s])` 是必需的：没有它，找 `margin` 会把 `margin-top` 也匹配进来
 * （反过来 `height` 会把 `min-height` 匹配进来），断言就会读到别的属性的值。
 */
function declValue(body, prop) {
  if (!body) return null
  const m = new RegExp(`(?:^|[;{\\s])${prop}\\s*:\\s*([^;}]+)`, 'm').exec(body)
  return m ? m[1].trim() : null
}

/** `padding` / `margin` 简写 → `[top, right, bottom, left]`（px 数值；解析不出来给 null） */
function boxEdges(value) {
  if (!value) return null
  const nums = value.split(/\s+/).filter(Boolean).map((v) => parseFloat(v))
  if (!nums.length || nums.some((n) => !Number.isFinite(n))) return null
  if (nums.length === 1) return [nums[0], nums[0], nums[0], nums[0]]
  if (nums.length === 2) return [nums[0], nums[1], nums[0], nums[1]]
  if (nums.length === 3) return [nums[0], nums[1], nums[2], nums[1]]
  return [nums[0], nums[1], nums[2], nums[3]]
}

/** 垂直方向留白合计（上下之和），读不到给 null */
function verticalPad(body, prop = 'padding') {
  const e = boxEdges(declValue(body, prop))
  return e ? e[0] + e[2] : null
}

/** 单值属性 → 数值（读不到 / 不是数字给 null） */
function pxValue(body, prop) {
  const v = declValue(body, prop)
  if (v == null) return null
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

/**
 * 在某个子树里找那条 `v-if / v-else-if / v-else` 链，取出条件里含 `kw` 的那一支。
 *
 * 返回 `{ branch, cond, index, all }`：
 *   · `branch` = 那一支（`children` 就是它的元素）；
 *   · `cond`   = 它的条件原文（`v-else` 那一支是空串）；
 *   · `index`  = 它在链里的**位置**（0 起）——「谁排在谁前面」这类判据就落在它上；
 *   · `all`    = 整条链的条件原文（报错信息里能一眼看出当前顺序）。
 *
 * ⚠️ 为什么必须按**链里的位置**判顺序，而不是按 `walkAst` 的遍历顺序：`transformIf` 把
 *    相邻的 `v-if/v-else-if` 合成**一个** IF 节点，`branches` 的顺序**就是**运行时求值顺序 ——
 *    这正是「空气泡」那条 bug 的判据（`turn_end` 掉到 assistant 正文分支后面去）。
 */
function ifBranchOf(root, kw) {
  let hit = null
  walkAst(root, (n) => {
    if (hit || n.type !== 9) return
    const all = n.branches || []
    for (let i = 0; i < all.length; i++) {
      const b = all[i]
      const cond = String(b.condition?.loc?.source ?? b.condition?.content ?? '')
      if (cond.includes(kw)) {
        hit = { branch: b, cond, index: i, all: all.map((x) => String(x.condition?.loc?.source ?? '(else)')) }
        return
      }
    }
  })
  return hit
}

/**
 * 从源码里抠出名为 `name` 的那个函数 / 箭头常量的**函数体**（大括号配平），拿不到给 null。
 *
 * 与 L68 里那个局部 `bodyOf` 同一做法，区别是**只看声明的位置**：从 `function name(` /
 * `const name =` 往后找**第一个** `{` 再配平 —— 所以它只适合体是块的那种
 * （`const x = computed(() => { … })` ✅；`const x = computed(() => a ? b : c)` ❌ 返回 null，
 *  调用方要按「拿不到 = 判 FAIL」处理，别当通过）。
 */
function jsBodyOf(src, name) {
  const m = new RegExp(`(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=)`).exec(src)
  if (!m) return null
  const open = src.indexOf('{', m.index + m[0].length - 1)
  if (open < 0) return null
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}') {
      depth--
      if (depth === 0) return src.slice(open, i + 1)
    }
  }
  return null
}

/**
 * 一个 SFC **模板里所有表达式的原文**（插值 + `v-if/v-else-if` 条件 + `v-for` 源 + 各种绑定）。
 *
 * 为什么要收成一份、而不是 `includes` 整个模板文本：**类名会污染子串断言** ——
 * `class="atr-skipped"` 里那个 `skipped` 满足 `\bskipped\b`（`-` 是非词字符，正好是个边界），
 * 于是「模板真的渲染了 skipped 这个字段」这条会被一个**只有样式钩子、根本没读数据**的类名判绿。
 * 表达式是按 AST 取的：只有「模板真的拿这个值去渲染/判断」才会进这份名单。
 */
function templateExprs(rel) {
  const ast = templateAst(rel)
  if (!ast) return null
  const out = []
  walkAst(ast, (n) => {
    if (n.type === 5) out.push(String(n.content?.loc?.source ?? n.content?.content ?? ''))
    else if (n.type === 11) out.push(String(n.source?.loc?.source ?? n.source?.content ?? ''))
    else if (n.type === 9) {
      for (const b of n.branches || []) {
        if (b.condition) out.push(String(b.condition.loc?.source ?? b.condition.content ?? ''))
      }
    }
    for (const p of n.props || []) {
      if (p.type === 7 && p.exp) {
        const s = expSource(p)
        if (s) out.push(s)
      }
    }
  })
  return out
}

/**
 * `node` 的 `v-if` / `v-else-if` 条件链，**从最外层到最内层**；命中不了给 `[]`。
 *
 * ⚠️ 为什么不能直接复用 `ifConditionOf`：它返回的是**最外层**那个 IF 分支的条件
 *    （`walkAst` 从根往下走，先撞上外层）。历史会话浮层整块挂在 `v-if="historyOpen"` 下面，
 *    于是浮层里那两个空态元素用 `ifConditionOf` 取到的**都是** `historyOpen` ——
 *    两条分支的判据看起来一模一样，断言就假过了（实测探针输出如此）。
 */
function ifChainOf(ast, target) {
  let hit = []
  const walk = (node, chain) => {
    if (node.type === 9) {
      for (const b of node.branches || []) {
        const c = b.condition
        const cond = c ? String(c.loc?.source ?? c.content ?? '').trim() : '(else)'
        walk(b, chain.concat(cond))
      }
      return
    }
    if (node === target) {
      if (!hit.length) hit = chain
      return
    }
    for (const child of node.children || []) walk(child, chain)
  }
  walk(ast, [])
  return hit
}

/** 时间/缓动函数字面量：在 `transition` 简写里出现，就说明这一项**没写属性名**（= all） */
const TRANSITION_TIME_RE = /^[\d.]+m?s$/
const TRANSITION_EASE_RE = /^(ease|ease-in|ease-out|ease-in-out|linear|step-start|step-end)$/

/** 按**顶层逗号**切分（`cubic-bezier(0.4, 0, 0.2, 1)` 括号里的逗号不能切） */
function splitTopLevelCommas(raw) {
  const out = []
  let depth = 0
  let buf = ''
  for (const ch of String(raw || '')) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    if (ch === ',' && depth === 0) {
      out.push(buf)
      buf = ''
    } else buf += ch
  }
  out.push(buf)
  return out.map((s) => s.trim()).filter(Boolean)
}

/**
 * 样式里所有 `transition` / `transition-property` 声明 → `[{ prop, raw, props, selector }]`
 *
 * `props` = 「这一段过渡在动哪些属性」：
 *   · `transition: background .2s ease, transform .2s` → `['background','transform']`；
 *   · **没写属性名**（`transition: all .2s` / `transition: .2s` / `transition: ease .2s`）
 *     → 记成 `['all']` —— 这正是要抓的写法（`all` 会把布局属性一起卷进来）。
 * `selector` = 它所在规则的选择器链，用来在失败信息里定位「是哪个文件的哪条规则」。
 *
 * 实现是个**逐字符的小扫描器**（不是正则），因为要同时拿到「所在规则」和「括号里的逗号」：
 * 实测 `cubic-bezier(0.4, 0, 0.2, 1)` 被简单 `split(',')` 切碎后，第二个属性名会被吞掉 → 守卫漏判。
 * 前提：样式里只用 `/* … *​/` 注释（被测的两个样式表都是；`cssOf` 也正是只剥这种）。
 */
function transitionDecls(css) {
  const out = []
  const stack = []
  let start = 0
  const pushDecl = (end) => {
    const m = /^\s*(transition(?:-property)?)\s*:\s*([\s\S]+?)\s*$/.exec(css.slice(start, end))
    if (!m) return
    const raw = m[2].replace(/\s+/g, ' ').trim()
    const props = splitTopLevelCommas(raw)
      .map((item) => {
        const first = (item.split(/\s+/).filter(Boolean)[0] || '').trim()
        if (!first) return null
        if (first === 'none') return null // `transition: none` 不动任何属性
        if (TRANSITION_TIME_RE.test(first) || TRANSITION_EASE_RE.test(first) || /^(steps|cubic-bezier)\(/.test(first)) {
          return 'all'
        }
        return first
      })
      .filter(Boolean)
    out.push({ prop: m[1], raw, props, selector: stack.join(' > ') })
  }
  for (let i = 0; i < css.length; i++) {
    const ch = css[i]
    if (ch === '{') {
      stack.push(css.slice(start, i).trim().replace(/\s+/g, ' '))
      start = i + 1
    } else if (ch === '}') {
      pushDecl(i) // 最后一条声明可能没写分号
      stack.pop()
      start = i + 1
    } else if (ch === ';') {
      pushDecl(i)
      start = i + 1
    }
  }
  return out
}

/**
 * 过渡里**一律不许出现**的属性：动它们就要重新排版（layout），而过渡是**逐帧**的 ——
 * 一帧一次重排，就是用户报的「点一下会卡一下」。`all` 更糟：它把这些属性全卷进来。
 *
 * 反过来说，`background` / `color` / `box-shadow` / `border-color` 这类只走绘制阶段的
 * 属性**不在此列**（它们不触发布局，文件里原有的 hover 过渡就是这类，不必改成 opacity/transform）。
 */
const LAYOUT_ANIM_PROPS = new Set([
  'all',
  'width', 'height', 'min-width', 'min-height', 'max-width', 'max-height',
  'margin', 'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'padding', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'top', 'right', 'bottom', 'left', 'inset', 'inset-block', 'inset-inline',
  'flex', 'flex-basis', 'flex-grow', 'flex-shrink', 'order',
  'font-size', 'line-height', 'gap', 'row-gap', 'column-gap',
  'border-width', 'border-radius', 'display', 'position'
])

/** 一个声明块里**顶层**出现过的属性名（够平铺规则用；不展开嵌套块） */
function declaredPropNames(body) {
  const noComment = String(body || '').replace(/\/\*[\s\S]*?\*\//g, '')
  return [...noComment.matchAll(/(?:^|[;{\s])([a-zA-Z-]+)\s*:/g)].map((m) => m[1])
}

/**
 * 取「**选择器列表里**含 `selector`」那条规则的声明块。
 *
 * ⚠️ 为什么不能直接用 `cssRule`：它要求选择器**紧跟着** `{`，而过渡这类规则普遍写成
 *    `.pop-fade-enter-active,\n.pop-fade-leave-active { … }` 这种**多选择器共享一个块**，
 *    `cssRule` 一条都取不到（实测；旧 `.slide-left-*` 也是这么写的）。
 *    这里要求：selector 前面是 `}`/`{`/`;`/`,`/行首（即它自己是一个独立选择器），
 *    且到下一个 `{` 之间没有 `;`/`{`/`}` —— 不足以解析任意 SCSS，够用即可。
 */
function ruleBodyWith(css, selector) {
  let from = 0
  for (;;) {
    const i = css.indexOf(selector, from)
    if (i < 0) return null
    const prev = css.slice(0, i).replace(/\s+$/, '').slice(-1)
    const brace = css.indexOf('{', i + selector.length)
    const between = brace < 0 ? null : css.slice(i + selector.length, brace)
    if (brace > 0 && ['', '}', '{', ';', ','].includes(prev) && !/[;{}]/.test(between)) {
      let depth = 0
      for (let j = brace; j < css.length; j++) {
        if (css[j] === '{') depth++
        else if (css[j] === '}') {
          depth--
          if (depth === 0) return css.slice(brace + 1, j)
        }
      }
      return null
    }
    from = i + selector.length
  }
}

/**
 * 把智能体页 `chat.vue` 的 `<script setup>` **在 Node 里真的跑一遍**（只跑 setup，不挂载、不开浏览器）。
 *
 * 断的是**行为**，不是「源码里还有没有那串字面量」：
 *   · 会话标题搜索的过滤结果（首尾空格 / 大小写 / 「新会话」兜底 / 匹配不上时不篡改原数组）；
 *   · 数量文案在搜索态下是否同时给出「命中数 + 总数」；
 *   · 点浮层外面关闭、点浮层里面不关。
 * 这些全是「点开才知道」的路径：把 `includes` 换成 `indexOf`、把 `trim()` 删掉，
 * 源码里照样能 grep 到「有个搜索」，只有真跑一遍才分得出对错。
 *
 * 做法与 `runConfirmCard` / `kbRuntime` 一致（离线、不加载 vue 运行时）：
 *   剥 import → `typescript` 转译 → `new Function` 注入桩 → 读 computed / 调函数。
 *
 * ⚠️ `ok: false` 时调用方**必须判 FAIL**（fail-closed，绝不能当通过）。
 * ⚠️ 这里执行的是**产品源码原样**：`chat.vue` 的 `<script setup>` 里新引入一个没桩的名字
 *    （新的 vue API / 新的 api 函数 / 新组件）时，会以 `xxx is not defined` 失败 ——
 *    那是**正确**的信号，修法是把那个名字加进 `stubs`，**不要**把断言写松。
 */
function chatRuntime() {
  const source = readSource(CHAT)
  if (!source) return { ok: false, why: `读不到 ${CHAT}` }
  const { descriptor } = parse(source, { filename: CHAT })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) return { ok: false, why: `${CHAT} 里没有 <script setup>` }
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  // ⚠️ 按**行首**判残留：`import` 这个词在注释里也会出现（`noticeRuntime` 那边实测踩过 ——
  //    结果栏的 JSDoc 里写着「不从…… import」，用 `\bimport\b` 会把注释算成没剥干净，
  //    报出来却像产品代码的问题）。`import` 语句必然在行首（允许缩进），行首判就够，也不放过真残留。
  if (/^\s*import\b/m.test(noImport)) {
    return { ok: false, why: 'import 没剥干净（脚本里出现了新的 import 写法，剥 import 的正则需要同步更新）' }
  }
  const { code, errors } = transpileTs(noImport, CHAT + '.script.ts')
  if (errors.length) return { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }

  const noop = () => {}
  const refStub = (v) => ({ value: v })
  /**
   * `rollbackTurn` 的桩：**记下实参**、结果由测试逐例给。
   *
   * 为什么要「记实参 + 可控返回」而不是一个固定 stub：
   * L86 / L87 / L88 断的是 `onRollbackTurn` 这一层的**行为**，而它只有两件事会变：
   *   · 把哪些参数交给了 `rollbackTurn`（会话 id 传对了没有 —— 那正是线上那条 bug 的根因）；
   *   · 拿到一个 `ok=false` / `historyMatched=0` 的结果之后，界面做了什么（toast / 回填）。
   * 这两件事**都只有真跑一遍才分得出对错**：`rollbackTurn(turnId)` 与
   * `rollbackTurn(turnId, sessionId.value)` 在源码里都「调了接口」，字符串断言分不出来。
   */
  const rollbackCalls = []
  /**
   * 逐例要交出去的 `TurnRollbackOutcome`（`{ value }` 这个壳是为了让测试能换掉它）。
   * 默认值 = **失败**：谁忘了设就得到「失败」这条路，逼着用例显式写清自己在测哪一条。
   */
  const rollbackOutcome = {
    value: {
      ok: false, reason: '（用例没有设置 rollbackOutcome）', reverted: 0,
      skipped: [], failed: [], partial: [], userText: '', dropped: false, historyMatched: 0
    }
  }
  /** `ElMessage.success` 收到的文案（`ok=false` 时**一条都不该有** —— 见 L88） */
  const successMsgs = []
  /** 交给 `setInputText` 的提问正文（`ok=false` 时也一条都不该有） */
  const inputTexts = []
  /**
   * 交给 `saveConversationMessages(...)` 的实参（每次补写历史一条）。
   *
   * L90 / L91 断的就是它：「补写历史时有没有把**本轮**的 `turnId` 带上」——
   * `ai_chat_message.turn_id` 是服务端 `drop-turn` 的唯一命中键，漏了它那一轮就永远删不掉
   * （用户报的「回退后刷新又回来」的第二半）。这条只有**真跑一遍 `handleSend`** 才测得出来：
   * 源码里「对象里有个 `turnId`」和「这个 `turnId` 是本轮的」是两件事。
   */
  const saveConvCalls = []
  /**
   * `useAgentChat()` 的桩 —— **手抄**的 composable 形状。
   *
   * ⚠️ 它必须跟着产品源码走：`chat.vue` 从 composable 里解构出来的**每个名字**都要在这儿有字段。
   *    缺一个**不会立刻炸**（解构不存在的键只是拿到 `undefined`），但只要哪条判据真去读它，
   *    报错会是 `Cannot read properties of undefined` —— 那个报错**指错边**：坏的是这份名单，
   *    不是产品代码。L85 专门守这条（少一个字段就红，并明说是判据这一侧的名单过期）。
   */
  const agentChatStub = {
    messages: refStub([]), isGenerating: refStub(false), tools: refStub([]), activeModel: refStub(''),
    metaWarnings: refStub([]), imageCount: refStub(0), corrections: refStub(0), errors: refStub([]),
    metrics: refStub({}), hasRun: refStub(false), send: async () => 'harness-answer', stop: noop, reset: noop,
    resolveConfirm: noop,
    // 本轮的轮次 id（`send()` 开头生成、`turn_end` 标记里那个）—— 补写历史时要带上它，
    // L90 / L91 会把它设成一个认得出的标记值，再去读 `saveConversationMessages` 的请求体。
    currentTurnId: refStub(''),
    // 轮末回退（2026-09-23 起是**按轮**的）：`rollbackStates[turnId] = { status, outcome }`，
    // `rollbackTurn(turnId, sessionId)` 返回 `TurnRollbackOutcome`。
    // ⚠️ 旧的单份 `turnRollback` 已被逻辑面删掉，桩里**不许**再留它 ——
    //    留着就等于给「旧口径回来」留了一条不报错的路（产品源码里已经没有这个名字了）。
    rollbackStates: refStub({}),
    rollbackTurn: async (...args) => {
      rollbackCalls.push(args)
      return rollbackOutcome.value
    }
  }
  const stubs = {
    // ---- 框架 / 编译宏 ----
    ref: refStub,
    reactive: (v) => v,
    computed: (fn) => ({
      get value() {
        return fn()
      }
    }),
    watch: noop,
    onMounted: noop,
    onBeforeUnmount: noop,
    defineOptions: noop,
    // ---- Element Plus ----
    // ⚠️ `success` 要**记下来**：L88 的判据是「失败的那一轮一条成功提示都不许有」，
    //    一个不记事的 `noop` 会让这条断言恒真（它测的就是「有没有弹过」）。
    ElMessage: { error: noop, success: (m) => successMsgs.push(String(m)), warning: noop },
    ElMessageBox: { confirm: async () => {} },
    // ---- 图标：脚本里只是常量 ----
    Clock: {}, Delete: {}, Plus: {}, FolderOpened: {}, QuestionFilled: {}, UploadFilled: {}, Search: {},
    // ---- 子组件：脚本里只是 import ----
    AiChatStream: {}, AiModelSelector: {}, AgentToolPopover: {}, AgentToolResult: {}, AgentConfirmCard: {},
    ChatFileUploader: {}, ChatAttachmentList: {}, KnowledgeBaseDrawer: {},
    // ---- composable / store：只要 setup 期真正用到的那几个返回值 ----
    useAgentChat: () => agentChatStub,
    useUserStore: () => ({ id: 1, userId: 1 }),
    // ---- @/api/ai/ai：本 harness 只问「本地过滤/关闭逻辑」与「补写历史的请求体」，请求全桩成空实现 ----
    listSessions: async () => ({ code: 200, data: [] }),
    createSession: async () => ({ code: 200, data: { sessionId: 'asst_stub' } }),
    deleteSession: async () => ({ code: 200 }),
    getConversationHistory: async () => ({ code: 200, data: [] }),
    saveConversationMessages: async (...args) => {
      saveConvCalls.push(args)
      return { code: 200 }
    },
    getAgentTimeline: async () => ({ code: 200, data: { messages: [] } }),
    attachmentPlaceholder: (a) => ({ name: a?.name || '', type: a?.type || '' }),
    fillAttachmentMetas: async () => {}
  }
  const names = Object.keys(stubs)
  /**
   * ⚠️ 这里交出去的**不只是状态，还有「记事本」**：L86–L88 断的是 `onRollbackTurn` 这一层的
   *    **行为**（交上去的实参、失败时有没有装作成功），而行为只能靠「跑一遍 + 看记事本」来判。
   *
   * ⚠️ 它们必须走**参数**注入，不能靠闭包：`new Function(...)` 造出来的函数在**全局作用域**里，
   *    看不到 `chatRuntime()` 的局部量（照闭包写会在取 `rollbackCalls` 时抛
   *    `rollbackCalls is not defined`，然后被下面那句「是桩列表的问题」**指错边**）。
   *    名字也都是 chat.vue 里没有的标识符 —— 同名参数与脚本里的 `const` 会撞成
   *    「Identifier has already been declared」。
   */
  const extra = { rollbackCalls, rollbackOutcome, successMsgs, inputTexts, saveConvCalls }
  try {
    const factory = new Function(
      ...names,
      ...Object.keys(extra),
      code +
        `
;return { sessions, sessionKeyword, filteredSessions, sessionCountText, sessionTitle,
  historyOpen, sessionPopoverRef, toggleHistory, onDocMousedown,
  sessionId, chatRef, onRollbackTurn, rollbackCalls, rollbackOutcome, successMsgs, inputTexts,
  handleSend, model, attachments, currentTurnId, saveConvCalls }`
    )
    const api = factory(...names.map((n) => stubs[n]), ...Object.keys(extra).map((n) => extra[n]))
    /**
     * `agentChatStubKeys` 是给 **L85** 用的：它拿这份键表去和 `chat.vue` 的解构名单对账，
     * 少一个字段就判红并明说「是判据这一侧的名单过期」。别删（删了 L85 没有落点，会 fail-closed 判红）。
     */
    return { ok: true, api, agentChatStubKeys: Object.keys(agentChatStub) }
  } catch (e) {
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    /**
     * ⚠️ 这里要把两种「`xxx is not defined`」分开说，否则报错**指错边**：
     *   · 那个名字**在桩里**、但产品源码里已经没有这个标识符了 → 是**判据侧返回名单过期**
     *     （实测：把 `currentTurnId` 的解构删掉时，本函数那句 `return { … currentTurnId … }`
     *      会先炸，于是 L29–L32/L85/L86/L88/L90 **一起红在同一句上**，而它们全在冤枉产品代码）；
     *   · 那个名字**不在桩里** → 产品真的引入了新东西，去补 stubs（这才是「加进桩列表」那条）。
     */
    const inStub = m ? Object.prototype.hasOwnProperty.call(agentChatStub, m[1]) : false
    return {
      ok: false,
      why: m
        ? inStub
          ? `chatRuntime 的返回名单里点了 \`${m[1]}\`，但产品源码里已经没有这个标识符了 —— ` +
            '**这是判据侧（chatRuntime 的 `return { … }` 名单）过期，不是产品代码引用了未定义的变量**：' +
            '产品真的删了它，就把名字从返回名单里去掉；不然先确认是不是产品漏了声明。'
          : `script setup 用到了 \`${m[1]}\`，但它不在 chatRuntime 的桩列表里（把它加进 stubs）`
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

const CHAT = 'src/views/front/agent/chat.vue'
const STREAM = 'src/components/AiChatStream/index.vue'
const INPUT = 'src/components/ChatInputArea/index.vue'
const FRONT = 'src/layout/front.vue'
const POPOVER = 'src/components/AgentToolPopover/index.vue'
const CONFIRM = 'src/components/AgentConfirmCard/index.vue'
/**
 * 抽屉的**外壳**（入口按钮 + el-drawer + 打开时激活面板）。
 *
 * ⚠️ 名字从 `KB_DRAWER` 改成 `KB_SHELL` 是 2026-09-21 拆分之后的事：这个名字现在必须
 *    **明确指「外壳」**——内容已经搬去 `KB_PANEL` 了，再叫 `KB_DRAWER` 会被读成
 *    「整个知识库功能」，下一个人很容易把内容类判据又钉在这个只剩 123 行的文件上
 *    （八条假红就是这么来的）。
 */
const KB_SHELL = 'src/components/KnowledgeBaseDrawer/index.vue'
/**
 * 抽屉的**内容**都在这里（2026-09-21 的刻意重构）：
 * `KnowledgeBaseDrawer` 只剩外壳（入口按钮 + el-drawer），真正的内容搬进了这个面板，
 * 悬浮助手的「我的知识库」tab 用的是同一个面板 —— 两处只有一份实现。
 * ⚠️ 所以「文档头部 / 粘贴导入 / 屏蔽开关 / 搜索 / 列表取数失败」这些判据的**家在这里**，
 *    只有外壳类判据（入口徽标数字、打开抽屉时激活面板）才断 `KB_SHELL`。
 */
const KB_PANEL = 'src/components/KnowledgeBasePanel/index.vue'
const NOTES_LIST = 'src/views/front/notes/list.vue'
/** 工具清单 / 开关这两个函数的实现文件（见 L40：组件依赖的是**具名导出**，不是整个模块） */
const API_DSFREE = 'src/api/ai/agentDsFree.ts'
const TOOL_DETAIL = 'src/components/AgentToolDetail/index.vue'
const TOOL_RESULT = 'src/components/AgentToolResult/index.vue'
/**
 * 轮末动作条（`type:'turn_end'` 那一格）：**回退 + 复制**两个按钮。
 *
 * ⚠️ 分工（2026-09-23 起）：
 *   · 「挂在哪、每轮都渲染、两个按钮、图标」断在这个文件上（L70 / L74 / L76 / L77）；
 *   · 逐条清单（`skipped` / `partial` / `failed`）**不在这个文件里画了** ——
 *     回退成功时这一格连同消息一起被摘掉，所以清单搬到了 `NOTICE`（L72）；
 *   · `reason` 原话 / 「没有可回退的操作」仍在这个文件（L75）。
 */
const TURN_ROLLBACK = 'src/components/AgentTurnRollback/index.vue'
/**
 * 回退结果栏 —— 逐条清单（没退成 / 只退一部分 / 报错）的**唯一落点**，可关闭。
 *
 * ⚠️ 它必须长在**消息列表之外**（`AiChatStream` 里 `.chat-messages` 的兄弟节点）：
 *    回退成功时那一轮的消息整轮被摘掉，挂在轮末的组件跟着下线 ——
 *    清单画在那一格上等于没画。L72 / L82 / L83 就断在这个位置上。
 */
const NOTICE = 'src/components/AgentRollbackNotice/index.vue'
/**
 * 右侧悬浮助手抽屉 —— `AiChatStream` 的**第二个消费方**（智能体模式下与大屏页共用同一套引擎）。
 *
 * ⚠️ 它存在的意义是 L73：任何「接线」类判据都必须在**两个**消费方上都断一遍 ——
 *    只在一个页面上接好、另一个漏接，是本仓最常见的一种「功能做了一半」。
 */
const ASSISTANT = 'src/components/AiAssistant/index.vue'

/**
 * `kbRuntime` 要**取出来**的名字（断言读的就是它们），按文件分开：
 * 每项是 `[harness 里的名字, 组件里的名字]`。
 *
 * ⚠️ 这是**判据这一侧**的清单，它必须跟着组件一起改，而且**两个文件不能共用一份** ——
 *    两个组件暴露的状态名本来就不同：面板里那个搜索词叫 `query`、有 `busy`，
 *    抽屉里只有 `kbCount` / `open` / `onOpen` / `panelRef`。
 *
 * ⚠️ 现状的由来（2026-09-21，八条假红）：这份名单**原来写死在 `kbRuntime` 的
 *    `return { … }` 里**（点着 `busy` / `kbs` / `filteredKbs` …），而组件已经拆成了两半 ——
 *    于是外壳那侧一个名字都不存在，`new Function` 里那句 `return` 在**第一个**缺失的名字上
 *    整句抛掉，报出来的却是「script setup 用到了 `busy`，但它不在桩列表里」——
 *    **读起来像产品代码引用了未定义的标识符，真相是判据的名单过期了**。
 *    判据工具的覆盖面不足会**伪装成「实现有问题」**，所以：名单放这里、按文件分开、
 *    取的时候逐个 `typeof` 探（见 `kbRuntime`）。
 *
 * ⚠️ 加/删名字时**两边一起看**：这里少一个 → 断言读不到它（`TypeError` 或 false 绿）；
 *    这里多一个 → 立刻以「判据名单过期」红给你看（就是要它响）。
 */
const KB_API_NAMES = {
  // 外壳：入口徽标 + 打开抽屉时把面板激活（`activate` 真的要调到，见 L20④）
  [KB_SHELL]: [
    ['kbCount', 'kbCount'],
    ['open', 'open'],
    ['visible', 'visible'],
    ['onOpen', 'onOpen'],
    ['panelRef', 'panelRef']
  ],
  // 内容：粘贴导入 / 屏蔽开关 / 搜索 / 列表取数失败
  [KB_PANEL]: [
    ['kbCount', 'kbCount'],
    ['busy', 'busy'],
    ['uploading', 'uploading'],
    ['importing', 'importing'],
    ['activeKbId', 'activeKbId'],
    ['uploadTip', 'uploadTip'],
    ['loadKbs', 'loadKbs'],
    ['activate', 'activate'],
    ['getKbCount', 'getKbCount'],
    ['importVisible', 'textImportVisible'],
    ['importContent', 'textImportContent'],
    ['importFileName', 'textImportFileName'],
    ['openTextImport', 'openTextImport'],
    ['submitTextImport', 'submitTextImport'],
    ['onFilesPicked', 'onFilesPicked'],
    ['kbs', 'kbs'],
    ['kbLoadFailed', 'kbLoadFailed'],
    // 面板里这个搜索词叫 `query`（一个框同时承担「筛库名」与「回车检索」两件事，见面板注释）。
    // 判据侧仍叫它 `kbFilter` —— 断言语义是「那个搜索词」，名字跟着语义走。
    ['kbFilter', 'query'],
    ['filteredKbs', 'filteredKbs'],
    ['kbEnabled', 'kbEnabled'],
    ['togglingKbId', 'togglingKbId'],
    ['toggleKbDisabled', 'toggleKbDisabled']
  ]
}

/** 见上方 `KB_API_NAMES`。写成函数是为了**惰性**读那两个 const（它们在下面才声明）。 */
function kbApiNames(file) {
  return KB_API_NAMES[file] || []
}

/* =====================================================================
 * 「认不出的键 → 原样显示」这件兜底，怎么才能变红（L46–L53）
 * =====================================================================
 * 三个渲染组件（`AgentToolResult` / `AgentConfirmCard` / `AgentToolDetail`）的映射表
 * 都是「映射不中就把键名/值原样打出来」—— 兜底本身是对的（总比空白强），
 * 代价是：**新增一个工具、动作、字段而忘了补标签，用户看到的就是英文标识符**：
 * `question_flag_manage · master`、`flagType: error`、`memoryTypes`。
 *
 * 下面几条把「忘了补」变成立刻能红的静态判据。判据来源分两种，每条注里标明：
 *   ① **后端注册表**（`../openstudy-fastapi/app/services/ai/agent/tools/*.py`，**只读**）——
 *      工具名读 4 空格缩进的 `name = "…"`，动作读 schema 里 `"action"` 的 `"enum"` 字面量。
 *      这是**唯一**能自动发现「后端新增了一个工具 / 一个动作」的口径；
 *      金标清单做不到这件事（它只会跟着前端一起过期）。
 *   ② **金标清单**（本文件里手抄，注里写明出处）—— 用于 preview()/回执里的**字段名**：
 *      那些键由业务逻辑拼出来，静态抽不出来，只能抄一份并写明出处行号。
 *
 * ⚠️ 判据是「值里含中日韩字符」而不是「值不等于键」：`delete: 'delete'` 这种
 *    「补了个假标签」必须也能红。
 */
const TOOLS_DIR = path.resolve(ROOT, '../openstudy-fastapi/app/services/ai/agent/tools')
const HAS_CJK = /[\u4e00-\u9fff]/

/** 后端注册表：`{ tools: [{name, file, actions}] }`，读不到时 `{ why }` */
function backendToolRegistry() {
  let files
  try {
    files = fs
      .readdirSync(TOOLS_DIR)
      .filter((f) => f.endsWith('.py') && f !== '__init__.py')
      .sort()
  } catch (e) {
    return { why: `读不到工具注册表 ${TOOLS_DIR}（${String(e?.message || e)}）` }
  }
  if (!files.length) return { why: `${TOOLS_DIR} 里一个 .py 都没有` }
  const tools = []
  for (const file of files) {
    const src = fs.readFileSync(path.join(TOOLS_DIR, file), 'utf8')
    const name = /^ {4}name = "([a-z_][a-z0-9_]*)"/m.exec(src)
    if (!name) return { why: `${file} 里找不到 4 空格缩进的 \`name = "…"\`` }
    tools.push({ name: name[1], file, actions: actionEnumOf(src) })
  }
  return { tools }
}

/**
 * 抽某个工具 schema 里 `"action"` 的 `"enum"`。
 *
 * 三种结果要分开（**别把「抽不到」和「没有 action」混成一个**）：
 *   · `string[]`     —— 抽到了字面量枚举
 *   · `null`         —— 这个工具根本没有 `"action"` 参数（如 `knowledge_search`，它没有 action）
 *   · `{why}`        —— 有 `"action"` 但枚举不是字面量（如 `list(_CLEAR_TYPES)`）→ **未验证**
 */
function actionEnumOf(src) {
  const at = src.indexOf('"action": {')
  if (at < 0) return null
  // 取紧跟在 `"action"` 后面的第一个 `"enum"` —— 它就是这个属性的枚举
  //（同一个 schema 里后面还会有别的 `"enum"`，例如 knowledge_base_manage 的 `disabled`）
  const enumAt = src.indexOf('"enum"', at)
  if (enumAt < 0) return { why: '"action" 后面找不到 "enum"' }
  const open = src.indexOf('[', enumAt)
  // ⚠️ `"enum"` 与 `[` 之间必须只有空白和冒号 —— 即**枚举就是那个数组字面量**。
  //    不查这一步的话，`"enum": sorted(_X)` 会一路 `indexOf` 到**后面别的**数组上，
  //    把不相干的代码当成动作名抽出来（实测：变体跑出过一个叫 `Math\` 的动作），
  //    虽然它仍然会因「没有标签」而报红，但报的是**假原因**。
  if (open < 0 || !/^[\s:]*$/.test(src.slice(enumAt + '"enum"'.length, open))) {
    return { why: '"enum" 不是字面量数组（抽不到取值，按未验证算）' }
  }
  const close = src.indexOf(']', open)
  if (open < 0 || close < 0) return { why: '"enum" 不是 [...] 形式' }
  const items = [...src.slice(open + 1, close).matchAll(/"([^"]+)"/g)].map((m) => m[1])
  if (!items.length) return { why: '"enum" 不是字面量（抽不到取值，按未验证算）' }
  return items
}

/**
 * 从一个 SFC 的 `<script setup>` 里读出一张常量表（`{ … }` 或 `[ … ]` 都可以）。
 *
 * 用 `codeText`（去注释）而不是原文：这几张表旁边就有反例说明的注释，
 * 注释里写着 `flagType` / `isPublic` 这些名字，不剥注释等于让断言被自己的说明满足。
 *
 * ⚠️ 不能简单地取「`const X` 之后的第一个 `=`」：类型注解里就有 `=`（`(obj: any) => boolean`），
 *    那样会读到注解中间去。判据是「**赋值号右边紧跟的**是 `{` 或 `[`」——
 *    `=>` 后面跟的是 ` boolean`，会被跳过（`REDUNDANT_KEYS` 这种数组字面量也就能读到了）。
 */
function objectLiteralBody(code, constName) {
  const at = code.indexOf(`const ${constName}`)
  if (at < 0) return null
  let from = at
  for (;;) {
    const eq = code.indexOf('=', from)
    if (eq < 0) return null
    // ⚠️ 末尾**不要**再写 `\s*`：那会把 `{` 后面的换行并进 `m[0]`，
    //    于是按 `m[0].length - 1` 算出来的下标落在空白上（实测踩过）。
    const m = /^[\s\r\n]*([[{])/.exec(code.slice(eq + 1))
    if (m) return balancedBlock(code, eq + 1 + m[0].length - 1)
    from = eq + 1
  }
}

/**
 * 从 `openIdx`（必须指向 `{` / `[` / `(`）配平到对应的闭合括号，返回**括号内部**文本。
 *
 * ⚠️ 用小括号栈而不是只数字符：类型注解与箭头函数里到处都是 `(` `)` `>`，
 *    只数花括号会在读到第一个 `)` 时就被带偏。
 */
function balancedBlock(code, openIdx) {
  const PAIR = { '{': '}', '[': ']', '(': ')' }
  const stack = [PAIR[code[openIdx]]]
  if (!stack[0]) return null
  for (let i = openIdx + 1; i < code.length; i++) {
    const ch = code[i]
    if (ch === "'" || ch === '"' || ch === '`') {
      // 跳过字符串，免得值里的括号把配平带偏
      i += 1
      while (i < code.length && code[i] !== ch) i += code[i] === '\\' ? 2 : 1
      continue
    }
    if (PAIR[ch]) stack.push(PAIR[ch])
    else if (ch === stack[stack.length - 1]) {
      stack.pop()
      if (!stack.length) return code.slice(openIdx + 1, i)
    }
  }
  return null
}

/** `KEY_LABELS` 那种 `{ 键: '中文' }` 的表 → `Map<键, 值>`；表不存在返回 null */
function labelTable(rel, constName) {
  const body = objectLiteralBody(codeText(rel), constName)
  if (body === null) return null
  const out = new Map()
  for (const m of body.matchAll(/(?:^|[{,\s])'?([A-Za-z_$][\w$]*)'?\s*:\s*'([^']*)'/g)) {
    out.set(m[1], m[2])
  }
  return out
}

/** `ENUM_LABELS` 里某个键的**内层**映射体（`markedType: { … }`）→ 文本；没有该键返回 null */
function nestedEnumBody(rel, constName, key) {
  const body = objectLiteralBody(codeText(rel), constName)
  if (body === null) return null
  const at = new RegExp(`(?:^|[{,\\s])'?${key}'?\\s*:`).exec(body)
  if (!at) return null
  const brace = body.indexOf('{', at.index)
  // 内层必须是 `{ … }` 字面量 —— 写成 `KEY: SOME_MAP`（外部常量）时抽不到，按未验证算
  if (brace < 0 || !/^[\s]*$/.test(body.slice(at.index + at[0].length, brace))) return null
  return balancedBlock(body, brace)
}

/** `new Set([ 'a', 'b' ])` 里的字符串项 */
function stringSetItems(rel, constName) {
  const code = codeText(rel)
  const at = code.indexOf(`const ${constName}`)
  if (at < 0) return null
  const open = code.indexOf('[', at)
  const close = code.indexOf(']', open)
  if (open < 0 || close < 0) return null
  return [...code.slice(open + 1, close).matchAll(/'([^']*)'/g)].map((m) => m[1])
}

/** `REDUNDANT_KEYS` 里有没有「键 + 那个人话字段」的一对 */
function redundantPair(rel, key, textField) {
  const body = objectLiteralBody(codeText(rel), 'REDUNDANT_KEYS')
  if (body === null) return false
  return new RegExp(`'${key}'\\s*,[^\\]]*${textField}`).test(body)
}

/**
 * 每个新工具 preview() 会输出、而原先**没有**标签的键。
 * 出处：`question_mark_manage.py:293-335`（`_preview_record` / `_preview_question`）、
 *       `memory_manage.py:131-169`（`_preview_forget` / `_preview_clear`）、
 *       `knowledge_base_manage.py:183-249`（`_preview_create/update/delete/delete_document` + `_load_doc`）、
 *       `bank_share_manage.py:193-275`（`_preview_share/revoke/receive/copy`）。
 */
const PREVIEW_KEYS_REQUIRED = [
  'flagType',
  'flagTypeText',
  'recordId',
  'preview',
  'questionId',
  'memoryId',
  'memoryType',
  'memoryTypeText',
  'content',
  'kbId',
  'name',
  'description',
  'disabledText',
  'documents',
  'chunks',
  'docId',
  'fileName',
  'shareId',
  'expireText',
  'expireTime',
  'receiveCount',
  'invalidatedReceivers',
  'ownerName',
  'permission',
  'received',
  'newBankName',
  'allowFork',
  'shareMessage'
]

/**
 * 每个新工具**回执/preview** 里会输出、而原先没有标签的字段名。
 * 出处：`question_record_service.brief_of`（`errorId/favoriteId/markedId` + 各表专有列）、
 *       `question_mark_manage.py:398-570`（list/add/master/remove 的回执）、
 *       `memory_manage.py:212-273`、`api/v1/user_stats.py:130-139 / 286-290 / 401-414 / 502-518`、
 *       `rag_write_service._kb_brief / _doc_brief`、`bank_share_service.format_share / share_info / receive_share`。
 *
 * ⚠️ 最后一行那 5 个（`name` / `title` / `type` / `embeddingModel` / …）是**实测多出来的**：
 *    它们不在最初的清单里，但确实会出现在结果里（`name` 连 `FIELD_LABELS` 都没有，
 *    所以 `knowledge_base_manage.update` 的回执里一直是裸 `name`）。
 */
const FIELD_KEYS_REQUIRED = {
  question_flag_manage: [
    'flagType', 'flagTypeText', 'recordId', 'errorId', 'favoriteId', 'markedId',
    'errors', 'favorites', 'markedQuestions', 'created', 'isMastered', 'errorCount',
    'status', 'lastErrorTime', 'favoriteStatus', 'correctTimes', 'errorTimes',
    'reviewCount', 'isStarred', 'markedStatus', 'markedType', 'markedTypeText',
    'difficultyLevel'
  ],
  memory_manage: ['memoryId', 'memoryType', 'memoryTypeText', 'memoryTypes'],
  learning_stats: [
    'totalBanks', 'totalErrors', 'totalMarked', 'totalMastered', 'totalFavoriteNotes',
    'totalPracticeCount', 'correctRate', 'bankStudyCount', 'byQuestionType', 'bankCount',
    'markedCount', 'date', 'practiceCount', 'correctCount', 'byDifficulty', 'activeErrors',
    'mastered', 'masterRate', 'bySubject', 'topErrors', 'joinDate', 'studyDays',
    'consecutiveDays', 'totalNotes', 'milestones', 'trend', 'days'
  ],
  knowledge_base_manage: [
    'kbId', 'docCount', 'chunkCount', 'disabled', 'disabledText', 'documents', 'docId',
    'fileName', 'chunks', 'knowledgeBases',
    // 实测补充：`_kb_brief` / `_doc_brief` 里有、清单里没有的列
    'embeddingModel', 'chunkSize', 'chunkOverlap', 'fileType', 'fileSize', 'errorMsg'
  ],
  bank_share_manage: [
    'shareId', 'shareCode', 'expireTime', 'expireText', 'effective', 'receiveCount',
    'shareMessage', 'ownerName', 'permission', 'received', 'resultStatus', 'resultStatusText',
    'invalidatedReceivers', 'revoked', 'newBankName', 'allowFork', 'sourceBankId',
    'sourceBankName', 'shares',
    // 实测补充：`format_share` / `share_info` / `receive_share` 里还有这些
    'shareToken', 'ownerId', 'ownerNickName', 'isOwner', 'alreadyReceived', 'coverImage'
  ]
}

/** 「值是 0/1 的列」必须有人话，否则用户看到裸数字 —— 键 → 期望的映射表 */
const ZERO_ONE_ENUM_KEYS = ['isMastered', 'favoriteStatus', 'markedStatus', 'markedType', 'disabled']
/** 同上，但走「是/否」那一套（后端给 bool 或 int 都可能） */
const YES_NO_KEYS_REQUIRED = ['isStarred', 'created', 'allowFork', 'revoked']

/* =====================================================================
 * L86–L89：「回退打在哪个会话上」这条链的三层判据工具
 * =====================================================================
 * 用户在 2026-09-23 报的线上 bug：「回退以后刷新页面，刚刚回退的对话内容还是存在」。
 * 根因是**会话 id 的来源错了**：`rollbackTurn` 只用 composable 内部那份
 * 「最近一次 `send()` 用过的会话 id」，而刷新之后消息是从**快照**复原的、根本没走 `send()`
 * —— 那份 id 是空串 → 两个请求都带 `sessionId:''` → 服务端按空会话过滤命中 0 行、还回 200 成功
 * → 本地消息被摘掉、服务端历史与快照都没动 → 刷新又全回来了。
 *
 * 这条链有三层，三层都得有落点（缺一层用户看到的还是「回退没生效」）：
 *   ① **页面**这一层：把「当前正在显示的那个会话」的 id 显式交给 `rollbackTurn`（L86）；
 *   ② **结果栏**这一层：服务端历史里没有这一轮标记（老数据）时如实说一句，且不把它排除（L87）；
 *   ③ **逻辑面**这一层：`matched === 0` 不许拦「把这一轮从界面上移除」（L89）。
 * ②③ 断在别人家的文件上也要断 —— 它们是同一条链，只断一半等于没断。
 */

/**
 * 取源码里**所有** `name(...)` 调用的实参清单（每个调用一个数组，按顶层逗号切）。
 *
 * ⚠️ 为什么不能用 `/name\(([^)]*)\)/`：实参里完全可能有括号（`f(a.b(c))` 这类），
 *    一刀切会在第一个 `)` 上截断，读到的参数个数就是错的 —— 而这条判据**正是在数参数个数**。
 *    所以按括号配平扫，并跳过引号里的括号（`'('` 这种字面量不算结构）。
 * ⚠️ 括号没配平（源码被截断）时**不返回**这一处，调用方按「读不到」处理 ——
 *    宁可让 `calls.length` 少一处，也不要拿半截实参去判「传了几个」。
 */
function callArgLists(src, name) {
  const out = []
  const re = new RegExp(`\\b${name}\\s*\\(`, 'g')
  let m
  while ((m = re.exec(src))) {
    let i = m.index + m[0].length
    const start = i
    let depth = 1
    let quote = ''
    for (; i < src.length && depth > 0; i++) {
      const c = src[i]
      if (quote) {
        if (c === '\\') i++
        else if (c === quote) quote = ''
        continue
      }
      if (c === '"' || c === "'" || c === '`') {
        quote = c
        continue
      }
      if (c === '(') depth++
      else if (c === ')') depth--
    }
    if (depth !== 0) continue
    out.push(splitTopLevel(src.slice(start, i - 1)))
  }
  return out
}

/** 按**顶层**逗号切实参（跳过括号 / 引号里的逗号）；空清单给 `[]`（= 零个实参） */
function splitTopLevel(s) {
  if (!String(s || '').trim()) return []
  const out = []
  let depth = 0
  let quote = ''
  let cur = ''
  for (let i = 0; i < s.length; i++) {
    const c = s[i]
    if (quote) {
      cur += c
      if (c === '\\') {
        cur += s[++i] ?? ''
        continue
      }
      if (c === quote) quote = ''
      continue
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c
      cur += c
      continue
    }
    if (c === '(' || c === '[' || c === '{') depth++
    else if (c === ')' || c === ']' || c === '}') depth--
    if (c === ',' && depth === 0) {
      out.push(cur.trim())
      cur = ''
      continue
    }
    cur += c
  }
  out.push(cur.trim())
  return out.filter(Boolean)
}

/**
 * 文件里**接收会话 id 的那个 ref**：被赋值为某个会话对象的 `.sessionId`。
 *
 * 判据落在「赋值来源」上、不落在名字上 —— 两个消费方的名字本来就不一样
 * （大屏页 `sessionId`、抽屉 `currentSessionId`），而这条判据要问的是
 * 「**页面自己**知不知道当前会话是谁」，不是「它叫不叫 sessionId」。
 * 还要求它**声明成 `ref(`**：不然 `page.sessionId` 这种点号路径也会被算进来。
 */
function sessionIdRefs(rel) {
  const src = readSource(rel) || ''
  const ids = new Set()
  const re = /([A-Za-z_$][\w$]*)\s*\.value\s*=[^\n]*\.sessionId\b/g
  let m
  while ((m = re.exec(src))) ids.add(m[1])
  return new Set([...ids].filter((n) => new RegExp(`const\\s+${n}\\s*=\\s*ref\\(`).test(src)))
}

/**
 * 文件里**用来载入「当前显示的那段对话」**的会话 ref。
 *
 * 这一层正是这次 bug 的关键：会话 id 的事实来源必须是「页面显示的那个会话」——
 * 也就是取历史 / 取时间线快照时用的那个值。三种写法都认：
 *   · 抽屉：`getConversationHistory(currentSessionId.value, …)`；
 *   · 大屏页：`loadHistory(sessionId.value)`（真正的取数在它里面，参数就是会话 id）。
 */
function displayedSessionRefs(rel) {
  const src = readSource(rel) || ''
  const ids = new Set()
  for (const re of [
    /getConversationHistory\(\s*([A-Za-z_$][\w$]*)\s*\.value/g,
    /getAgentTimeline\(\s*([A-Za-z_$][\w$]*)\s*\.value/g,
    /loadHistory\(\s*([A-Za-z_$][\w$]*)\s*\.value/g
  ]) {
    let m
    while ((m = re.exec(src))) ids.add(m[1])
  }
  return ids
}

/**
 * 把回退结果栏 `AgentRollbackNotice` 的 `<script setup>` 在 Node 里**真的跑一遍**，
 * 交出 `historyUnmarked`（「服务端历史里没有这一轮标记」那个判据函数本身）。
 *
 * 为什么要真跑而不是 grep 源码：这条判据是**几个条件一起看**（`ok` + `historyMatched === 0`
 * + 「一行都没删」），而「本来就是老数据」和「上次已经删过了（幂等）」在源码上长得几乎一样 ——
 * 少看一个条件时字符串断言照样绿，只有把用例喂进去才分得出对错：
 *   · 老数据（`matched === 0`）→ **要**说；
 *   · 幂等重试（`matched > 0`）→ **不许**说（那是正常成功）；
 *   · 失败（`ok === false`）→ 不许说（它的原因在轮末那一格，见 L88）；
 *   · 字段读不到（逻辑面还没上这个字段）→ 不许说（宁可不提，也不能编）。
 *
 * ⚠️ `ok: false` 时调用方**必须判 FAIL**（fail-closed：跑不起来 ≠ 通过）。
 */
function noticeRuntime() {
  const source = readSource(NOTICE)
  if (!source) return { ok: false, why: `读不到 ${NOTICE}` }
  const { descriptor } = parse(source, { filename: NOTICE })
  const raw = descriptor.scriptSetup?.content || ''
  if (!raw) return { ok: false, why: `${NOTICE} 里没有 <script setup>` }
  const noImport = raw
    .replace(/^\s*import\s[\s\S]*?from\s*['"][^'"]+['"]\s*$/gm, '')
    .replace(/^\s*import\s*['"][^'"]+['"]\s*$/gm, '')
  /**
   * ⚠️ 残留检查只能按**行首**判：`import` 这个词在注释里也会出现（本组件的 JSDoc 里就写着
   *    「展示层不依赖业务 composable，不从…… import」），用 `\bimport\b` 会把**注释**
   *    算成「没剥干净」—— 那是判据自己的口径问题，报出来却像产品代码的问题。
   *    `import` 语句必然在行首（允许缩进），所以行首判就够，也不放过任何真残留。
   */
  if (/^\s*import\b/m.test(noImport)) {
    return { ok: false, why: 'import 没剥干净（剥 import 的正则需要同步更新）' }
  }
  const { code, errors } = transpileTs(noImport, NOTICE + '.script.ts')
  if (errors.length) return { ok: false, why: 'TS 转译报错：' + errors.slice(0, 2).join(' | ') }

  const noop = () => {}
  const stubs = {
    // 编译宏：脚本里只是调用一下、结果丢弃（组件靠 props 拿 entries）
    defineProps: () => ({ entries: [] }),
    defineEmits: () => noop,
    // 图标：脚本里只是 import，模板里才用（剥 import 后留个值，防止脚本真去引用它时抛错）
    Close: {}
  }
  const names = Object.keys(stubs)
  try {
    const factory = new Function(...names, code + '\n;return { historyUnmarked }')
    return { ok: true, api: factory(...names.map((n) => stubs[n])) }
  } catch (e) {
    const msg = String(e?.message || e)
    const m = /^(\w+) is not defined$/.exec(msg)
    return {
      ok: false,
      why: m
        ? `script setup 用到了 \`${m[1]}\`，但它不在 noticeRuntime 的桩列表里（把它加进 stubs）`
        : `执行注入后的脚本抛错：${msg}`
    }
  }
}

/**
 * 「补写历史时带上了**本轮**的 `turnId`」—— 判据的**结构半边**，按文件跑一遍。
 *
 * 为什么这条不能只看「对象里有没有 `turnId`」：
 *   · `ai_chat_message.turn_id` 是 `POST /ai/conversation/drop-turn` 的**唯一命中键**
 *     （服务端按 `(user_id, session_id, turn_id)` 删这一轮）；空串就是「一行都匹配不到、
 *     还回 `code:200`」，界面却把消息摘了 → **刷新之后那一轮又回来**
 *     （用户 2026-09-23 那条线上 bug 的**第二半**：库里有 32 行真实数据 `turn_id` 全是空串）。
 *   · 所以要求两条：**请求体里有 `turnId`**，且它**取自 `useAgentChat()` 的 `currentTurnId`**
 *     （`send()` 开头生成、`turn_end` 标记里那个）。自己再生成一个 `t_<ms>` 会让行与标记对不上，
 *     回退**照样匹配不到** —— 断「有 `turnId`」是断不出这一种的。
 *   · 允许经**一层局部常量**转手（`const x = String(currentTurnId.value || '')`）：那是刻意的写法
 *     （补写发生在 `await metasReady` 之后，必须先抓在手里），不是需要断言去管的形状。
 *
 * ⚠️ 走 `codeText(rel)`（剥注释）：这两个调用点周围全是解释性注释，里面必然写着 `turnId`。
 */
function turnIdPersistProblems(rel) {
  const problems = []
  const code = codeText(rel)
  if (!readSource(rel)) return [`读不到 ${rel}`]
  // ① 解构里要有 `currentTurnId`（允许按本文件约定改别名，如 `currentTurnId: agentCurrentTurnId`）
  const m = /const\s*\{([\s\S]*?)\}\s*=\s*useAgentChat\s*\(/.exec(code)
  if (!m) {
    return [`${rel} 里读不到 \`const { … } = useAgentChat()\` —— 解构的写法变了，这条判据要跟着改`]
  }
  let bound = ''
  for (const piece of m[1].split(',')) {
    const [k, v] = piece.split(':').map((x) => (x || '').trim())
    if (k === 'currentTurnId') bound = v || 'currentTurnId'
  }
  if (!bound) {
    problems.push(
      `${rel} 没有从 \`useAgentChat()\` 解构出 \`currentTurnId\` —— ` +
        '页面手上就没有「本轮的轮次 id」这个东西，补写历史时只能落一个空串'
    )
  }

  // ② 补写历史的请求体里要有 `turnId`，且取值来自它
  const calls = callArgLists(code, 'saveConversationMessages')
  if (!calls.length) {
    problems.push(`${rel} 里没有调 \`saveConversationMessages(\` —— 补写历史那一段不见了？这条判据没有落点`)
    return problems
  }
  calls.forEach((args, i) => {
    const where = `${rel} 第 ${i + 1} 处 \`saveConversationMessages(\``
    const body = args[1] || ''
    if (!/^\s*\{/.test(body)) {
      problems.push(`${where} 的第二个实参不是对象字面量（读到 \`${body.slice(0, 40)}\`）—— 判据要读它的 body`)
      return
    }
    const tm = /(?:^|[{,\s])turnId\s*:\s*([^,}]+)/.exec(body)
    if (!tm) {
      problems.push(
        `${where} 的请求体里没有 \`turnId\` —— 落库时 \`turn_id\` 会是空串：` +
          '服务端 `drop-turn` 按 `(user_id, session_id, turn_id)` 一行都匹配不到、还回 `code:200`（dropped:0），' +
          '而界面已经把消息摘了 → **刷新之后刚回退的那一轮又回来了**'
      )
      return
    }
    if (!bound) return
    const value = tm[1].trim()
    const direct = new RegExp(`\\b${bound}\\b`).test(value)
    let viaAlias = null
    for (const id of [...value.matchAll(/[A-Za-z_$][\w$]*/g)].map((x) => x[0])) {
      const decl = new RegExp(`(?:const|let|var)\\s+${id}\\s*=[^\\n]*\\b${bound}\\b`).exec(code)
      if (decl) {
        viaAlias = { id, at: decl.index }
        break
      }
    }
    if (!direct && !viaAlias) {
      problems.push(
        `${where} 的 \`turnId\` 取的是 \`${value}\` —— 它不来自 \`${bound}\`（本轮的轮次 id）：` +
          '自己再生成一个 id 会与这一轮 `turn_end` 标记上的 `turnId` 对不上，回退**照样**匹配不到'
      )
      return
    }
    if (direct) {
      problems.push(
        `${where} 的 \`turnId\` 直接读了 \`${bound}\`（\`${value}\`）—— ` +
          '要在请求发出**之前**先抓成局部量：补写是在 `await metasReady`（文档解析，可能好几秒）之后才发请求的，' +
          '那一窗里用户再发一次，`currentTurnId` 就变成**下一轮**的 id 了 —— 这一轮的提问行会被贴上下一次的轮次标记'
      )
      return
    }
    /**
     * 时序：抓 id 的那一行必须在 `await metasReady` **之前**（理由同上：那次 await 里 id 可能被下一轮换掉）。
     * ⚠️ 这里锚的是**本地变量名 `metasReady`**：产品里改了名字这条判据要跟着改
     *    （报出来的话会明说「落点过期」，不是产品代码有问题）。
     */
    const awaitAt = code.indexOf('await metasReady')
    if (awaitAt < 0) {
      problems.push(
        `${rel} 里找不到 \`await metasReady\` —— **这是判据侧的落点过期**（补写前的那个 await 改名 / 挪走了）：` +
          '先把本判据的锚点改成新的写法，别去改产品代码迁就它'
      )
    } else if (viaAlias.at > awaitAt) {
      problems.push(
        `${where} 的 \`turnId\` 是在 \`await metasReady\` **之后**才抓的（\`const ${viaAlias.id} = …\` 排在它后面）—— ` +
          '那一窗里用户再发一次，`currentTurnId` 就变成下一轮的 id 了，这一轮的提问行会被贴上下一次的轮次标记'
      )
    }
  })
  return problems
}

const LAYOUT_CHECKS = [
  {
    id: 'L1',
    file: FRONT,
    label: 'agent-mode 容器有确定高度（height: 100vh + overflow: hidden）',
    // 根因就在这条：只给 `min-height` 时容器高度仍由内容决定，
    // 子级 `.agent-page{height:100%}` 退化成 auto，整条高度链跟着内容长高。
    fn: () => {
      const body = cssRule(cssOf(FRONT), '.front-layout.agent-mode')
      if (!body) return '找不到 .front-layout.agent-mode 规则'
      if (!/height:\s*100vh/.test(body)) return '.front-layout.agent-mode 缺 `height: 100vh`（只有 min-height 挡不住内容撑高）'
      if (!/overflow:\s*hidden/.test(body)) return '.front-layout.agent-mode 缺 `overflow: hidden`'
      return null
    }
  },
  {
    id: 'L2',
    file: STREAM,
    label: '消息列表能自己滚（overflow-y: auto + min-height: 0）',
    fn: () => {
      const body = cssRule(cssOf(STREAM), '.chat-messages')
      if (!body) return '找不到 .chat-messages 规则'
      if (!/overflow-y:\s*auto/.test(body)) return '.chat-messages 缺 `overflow-y: auto`'
      if (!/min-height:\s*0/.test(body))
        return '⚠️ .chat-messages 缺 `min-height: 0` —— flex item 默认 min-height:auto，`flex: 1` 会形同虚设、内部滚动条永不出现（「输入框被挤出视线」就是这个）'
      return null
    }
  },
  {
    id: 'L3',
    file: STREAM,
    label: '输入区在滚动容器之外（与 .chat-messages 是兄弟节点）',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到模板 AST'
      let messages = null
      let inside = false
      let sibling = false
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('chat-messages')) {
          messages = n
          walkAst(n, (d) => {
            if (d.type === 1 && d.tag === 'ChatInputArea') inside = true
          })
        }
      })
      if (!messages) return '模板里找不到 .chat-messages'
      if (inside) return 'ChatInputArea 被放进了 .chat-messages 里面（它会跟着消息一起滚走）'
      const parent = ast.children?.find((c) => c.type === 1 && nodeClasses(c).includes('ai-chat-stream'))
      sibling = !!parent?.children?.some((c) => c.type === 1 && c.tag === 'ChatInputArea')
      if (!sibling) return 'ChatInputArea 不是 .chat-messages 的兄弟节点（应同属 .ai-chat-stream）'
      return null
    }
  },
  {
    id: 'L4',
    file: INPUT,
    label: '输入区不被挤压（flex-shrink: 0）+ 不是 fixed/absolute',
    fn: () => {
      const body = cssRule(cssOf(INPUT), '.chat-input-area')
      if (!body) return '找不到 .chat-input-area 规则'
      if (!/flex-shrink:\s*0/.test(body)) return '.chat-input-area 缺 `flex-shrink: 0`（消息一多它会被压缩 → 输入框变矮）'
      if (/position:\s*(fixed|absolute)/.test(body))
        return '.chat-input-area 用了 fixed/absolute —— 「吸底」必须留在文档流里（手算偏移会在侧栏折叠/窄屏/顶栏高度变化时错位）'
      return null
    }
  },
  {
    id: 'L5',
    file: CHAT,
    label: '顶部标题栏已删（无 .agent-head / .head-name / .tool-bar 常驻横条）',
    fn: () => {
      const ast = templateAst(CHAT)
      if (!ast) return '拿不到模板 AST'
      const classes = new Set()
      walkAst(ast, (n) => {
        if (n.type === 1) nodeClasses(n).forEach((c) => classes.add(c))
      })
      const gone = ['agent-head', 'head-name', 'head-sub', 'head-toggle', 'head-right', 'tool-bar', 'tool-chip', 'tool-bar-model']
      const back = gone.filter((c) => classes.has(c))
      if (back.length) return `已删掉的节点又回来了：${back.join('、')}`
      return null
    }
  },
  {
    id: 'L6',
    file: CHAT,
    label: '输入区是文档流里的「悬浮卡片」（无 absolute 贴纸 + 无魔法预留高度）',
    fn: () => {
      const source = readSource(CHAT)
      const body = cssRule(cssOf(CHAT), ':deep(.chat-input-area)')
      if (!body) return '找不到 `:deep(.chat-input-area)` 覆盖规则'
      if (/position:\s*(absolute|fixed)/.test(body))
        return '输入区又变成 `position: absolute` 贴纸了 —— 那要靠 `padding-bottom` 魔法数字给消息区垫位，输入框长一行就盖住最后一条消息'
      if (!/border-radius/.test(body) || !/box-shadow/.test(body))
        return '悬浮卡片观感丢了（缺 border-radius / box-shadow）'
      if (/FLOAT_INPUT_H|FLOAT_INPUT_GAP|SCROLL_BTN_BOTTOM/.test(stripBlockComments(readSource(CHAT))))
        return '又把「手算输入卡片高度」的常量加回来了（FLOAT_INPUT_*）'
      if (/padding-bottom:\s*1[0-9][0-9]px/.test(cssOf(CHAT)))
        return '消息区又出现了 100px 以上的 `padding-bottom` 预留（贴纸式悬浮的补丁）'
      return null
    }
  },
  {
    id: 'L7',
    file: CHAT,
    label: '顶部那些控件没丢：都进了底部工具栏左槽',
    fn: () => {
      const block = slotBlock(readSource(CHAT), 'input-footer')
      if (!block) return '找不到 `#input-footer` 插槽'
      // 去注释：注释里提一句组件名不该算「控件还在」
      const code = stripBlockComments(block)
      const need = [
        ['ChatFileUploader', '附件上传'],
        ['KnowledgeBaseDrawer', '知识库'],
        ['historyOpen', '历史会话入口'],
        ['autoConfirm', '自动执行开关'],
        ['AgentToolPopover', '可用工具弹层']
      ]
      const miss = need.filter(([k]) => !code.includes(k)).map(([, cn]) => cn)
      if (miss.length) return `#input-footer 里少了：${miss.join('、')}`
      if (!code.includes('class="footer-hint"')) return '#input-footer 少了附件类型提示'
      return null
    }
  },
  {
    id: 'L8',
    file: CHAT,
    label: '底部工具栏右槽：模型选择器（常驻）+ 新对话',
    fn: () => {
      const block = slotBlock(readSource(CHAT), 'input-toolbar-right')
      if (!block) return '找不到 `#input-toolbar-right` 插槽'
      const code = stripBlockComments(block)
      const miss = []
      if (!code.includes('AiModelSelector')) miss.push('模型选择器')
      if (!code.includes('newSession')) miss.push('新对话')
      if (miss.length) return `#input-toolbar-right 里少了：${miss.join('、')}`
      return null
    }
  },
  {
    id: 'L9',
    file: CHAT,
    label: '模型选择器收窄但常驻（width < 150px，且不藏在弹层里）',
    fn: () => {
      const ast = templateAst(CHAT)
      if (!ast) return '拿不到模板 AST'
      let w = null
      let inPopover = false
      walkAst(ast, (n) => {
        if (n.type === 1 && n.tag === 'AiModelSelector') {
          const p = (n.props || []).find((x) => x.type === 6 && x.name === 'width')
          w = p ? String(p.value?.content || '') : null
        }
      })
      const popoverBlock = slotBlock(readSource(POPOVER), 'reference') || ''
      inPopover = /AiModelSelector/.test(popoverBlock)
      if (w === null) return 'AiModelSelector 没有显式 width（默认 220px 太宽）'
      const num = parseInt(w, 10)
      if (!Number.isFinite(num) || num <= 0) return `width 解析不出来：${w}`
      if (num >= 150) return `width 仍偏宽：${w}（要求 < 150px）`
      if (inPopover) return '模型选择器被藏进弹层了 —— 用户要求「收窄但常驻」'
      return null
    }
  },
  {
    id: 'L10',
    file: POPOVER,
    label: '可用工具走弹层组件（el-popover + 命名 popper-class）',
    fn: () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '组件文件不存在 / 拿不到模板 AST'
      let pop = null
      walkAst(ast, (n) => {
        if (n.type === 1 && n.tag === 'el-popover') pop = n
      })
      if (!pop) return '没有用 el-popover（工具清单要求「点开才显示」）'
      const p = (pop.props || []).find((x) => x.type === 6 && x.name === 'popper-class')
      if (!p || String(p.value?.content || '') !== 'agent-tool-popover')
        return '缺 popper-class="agent-tool-popover"（弹层被 teleport 到 body，样式要靠它挂靠）'
      return null
    }
  },
  {
    id: 'L11',
    file: CHAT,
    label: '底部状态条 .agent-foot 保留',
    fn: () => {
      const ast = templateAst(CHAT)
      if (!ast) return '拿不到模板 AST'
      let found = false
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('agent-foot')) found = true
      })
      return found ? null : '`.agent-foot` 状态条不见了（工具调用/自我纠正/图片落盘那些统计）'
    }
  },
  {
    id: 'L12',
    file: CHAT,
    label: '状态条水平居中 + 三组统计都接上了数据',
    fn: () => {
      // ① 版式：居中是用户明确要求的（原来是靠左）
      const body = cssRule(cssOf(CHAT), '.agent-foot')
      if (!body) return '找不到 .agent-foot 规则'
      if (!/justify-content:\s*center/.test(body)) {
        return '`.agent-foot` 没有 `justify-content: center` —— 用户要求这行统计水平居中'
      }
      // ② 数据接线：三个组缺任何一组都要能红（光有版式没有数是空壳）
      const src = readSource(CHAT)
      const missing = [
        'metrics.rounds', // 轮
        'metrics.steps', // 步
        'metrics.llmMs', // LLM 耗时
        'metrics.toolMs', // 工具调用耗时
        'metrics.firstTokenMs' // 首 token 平均
      ].filter((k) => !src.includes(k))
      if (missing.length) return `状态条没接上这些指标：${missing.join(' / ')}`
      // ③ 「没有样本」不能显示成 0 —— 0 读作「瞬间返回」，与「还没测到」相反
      if (!/firstTokenMs[^\n]*\?\?|== null \? '—'|= null \? '—'|== null\s*\?\s*'—'/.test(src)) {
        return '首 token 的 null 分支没处理 —— 没有样本时必须显示 `—`，不能落进 formatMs 变成 `0毫秒`'
      }
      return null
    }
  },
  {
    id: 'L13',
    file: CHAT,
    label: '智能体页把输入卡片压矮（覆盖层的垂直留白低于共用组件默认值）',
    fn: () => {
      const shared = cssOf(INPUT)
      const agent = cssOf(CHAT)

      // ① 共用组件（聊天助手抽屉也用它）的默认观感**不能**被顺手改掉 ——
      //    「压矮」必须只发生在智能体页这一层的 `:deep()` 覆盖里。
      const sharedArea = cssRule(shared, '.chat-input-area')
      const sharedBox = cssRule(shared, '.input-box')
      if (!sharedArea || !sharedBox) {
        return '找不到共用组件 ChatInputArea 的 `.chat-input-area` / `.input-box` 规则'
      }
      if (verticalPad(sharedArea) !== 24) {
        return `共用组件 .chat-input-area 的垂直 padding 变成 ${verticalPad(sharedArea)}px（原 24px）—— 它同时服务聊天助手抽屉，压矮要写在智能体页的 :deep 覆盖层里，别改共用默认值`
      }
      if (verticalPad(sharedBox) !== 20) {
        return `共用组件 .input-box 的垂直 padding 变成 ${verticalPad(sharedBox)}px（原 20px）—— 同上，别改共用默认值`
      }

      // ② 覆盖层里这几处必须真的压到**预算**以内。
      //    预算是「比共用组件默认值更紧」的上限 —— 把任何一处改回旧值 / 组件默认值都会越限。
      //    ⚠️ 只断言「比共用默认更小」是不够的：旧的智能体页本来就覆盖了一条
      //       `padding: 8px 12px 10px`（上下 18px < 默认 24px），只比大小它照样绿
      //       （变异测试 M2 就是这么漏过去的），所以这里必须给出明确上限。
      const areaAgent = cssRule(agent, ':deep(.chat-input-area)')
      const boxAgent = cssRule(agent, ':deep(.chat-input-area .input-box)')
      const dividerAgent = cssRule(agent, ':deep(.chat-input-area .input-divider)')
      const bottomAgent = cssRule(agent, ':deep(.chat-input-area .input-bottom)')
      const taAgent = cssRule(agent, ':deep(.chat-input-area .chat-textarea)')

      const budget = [
        ['卡片自身上下 padding', () => verticalPad(areaAgent), 12, '组件默认 24px（压矮前的智能体页是 18px）'],
        ['内层输入框上下 padding', () => verticalPad(boxAgent), 10, '组件默认 20px'],
        ['分隔线上下 margin', () => verticalPad(dividerAgent, 'margin'), 4, '组件默认 6px'],
        ['工具行 min-height', () => pxValue(bottomAgent, 'min-height'), 32, '组件默认 36px'],
        ['textarea 起点 min-height', () => pxValue(taAgent, 'min-height'), 32, '组件默认 42px'],
        ['textarea 行高', () => pxValue(taAgent, 'line-height'), 1.45, '组件默认 1.5']
      ]
      const miss = []
      for (const [name, read, ceil, base] of budget) {
        const got = read()
        if (got == null) {
          miss.push(`${name}没在覆盖层里下调（缺规则 / 缺该属性）`)
          continue
        }
        if (got > ceil) miss.push(`${name}是 ${got}，超出预算 ${ceil}（${base}）—— 输入卡片又变高了`)
      }
      if (miss.length) return miss.join('；')
      return null
    }
  },
  {
    id: 'L14',
    file: CHAT,
    label: '状态条 .agent-foot 与输入卡片贴合（卡片底部留白收窄 + 统计条紧跟在消息区之后）',
    fn: () => {
      const agent = cssOf(CHAT)

      // ① 版式：输入卡片的下方留白必须收窄，否则和统计条之间会空出一条
      const area = cssRule(agent, ':deep(.chat-input-area)')
      if (!area) return '找不到 `:deep(.chat-input-area)` 覆盖规则'
      // ⚠️ `margin-bottom` 长写会**盖掉** `margin` 简写的最后一位 —— 只看简写就会漏掉
      //    「简写写对了、后面又补一条 `margin-bottom: -6px`」（变异测试 M9 就漏过一次）。
      const shorthand = boxEdges(declValue(area, 'margin'))
      const longhand = pxValue(area, 'margin-bottom')
      const bottom = longhand != null ? longhand : shorthand ? shorthand[2] : null
      if (bottom == null) {
        return '覆盖层里读不到卡片的 `margin` / `margin-bottom` —— 卡片会退回默认的下方留白，与统计条脱开'
      }
      if (bottom < 0) return `输入卡片的下方 margin 是负值（${bottom}px）—— 那是把统计条叠到卡片上，会压住圆角与阴影`
      if (bottom > 4) return `输入卡片下方仍留 ${bottom}px（要求 ≤ 4px）—— 卡片与统计条之间会明显脱开`

      // ② 统计条自身别把间距撑回来
      const foot = cssRule(agent, '.agent-foot')
      if (!foot) return '找不到 .agent-foot 规则'
      const footPad = verticalPad(foot)
      if (footPad == null) return '.agent-foot 没写 `padding`'
      if (footPad > 12) return `.agent-foot 上下 padding 合计 ${footPad}px 偏大（要求 ≤ 12px）—— 统计条自己又把两行拉开了`

      // ③ 结构：统计条必须是 `.agent-main` 的直接子节点、且**紧跟在 AiChatStream 之后**
      //    （中间塞任何占位节点都会重新拉开距离 —— 这正是「贴合」在结构上的定义）
      const ast = templateAst(CHAT)
      if (!ast) return '拿不到模板 AST'
      let main = null
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('agent-main')) main = n
      })
      if (!main) return '模板里找不到 .agent-main'
      const kids = directElements(main)
      const idxStream = kids.findIndex((c) => c.tag === 'AiChatStream')
      const idxFoot = kids.findIndex((c) => nodeClasses(c).includes('agent-foot'))
      if (idxStream < 0) return '.agent-main 里找不到 AiChatStream'
      if (idxFoot < 0) return '.agent-foot 不是 .agent-main 的直接子节点（它应紧跟在消息区下方）'
      if (idxFoot !== idxStream + 1) {
        return `.agent-foot 与 AiChatStream 之间夹了 ${idxFoot - idxStream - 1} 个节点 —— 统计条不再紧贴输入卡片`
      }
      return null
    }
  },
  {
    id: 'L15',
    file: CHAT,
    label: '工具弹层的「当前模型」跟随选择器（不能只绑 activeModel）',
    fn: () => {
      const src = readSource(CHAT)
      const m = src.match(/<AgentToolPopover[^>]*\s:model="([^"]+)"/)
      if (!m) return '找不到 AgentToolPopover 的 `:model` 绑定'
      const expr = m[1]
      // `activeModel` 是后端 `meta` 事件回报的「**上次**实际跑用的模型」，只在一次请求
      // 跑完之后才更新。只绑它 → 用户在下拉里换完模型、还没发消息时，弹层里显示的仍是
      // 上一次的模型（用户 2026-09-19 报的就是这个）。选择器当前值 `model` 才是
      // 「下一次请求真正会用的模型」，所以表达式必须回落到它。
      if (!expr.includes('||') || !/\bmodel\b/.test(expr)) {
        return `:model 绑的是 \`${expr}\` —— 少了选择器的当前值：切换模型后不发消息，弹层不会更新`
      }
      return null
    }
  },
  {
    id: 'L16',
    file: STREAM,
    label:
      '轮末那一格挂的是轮末回退组件（2026-09-23 用户授权反转：原「禁止 after-message 死插槽」不再当第一条），且 :key 仍挂在 v-for 的那个 div 上',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到模板 AST'
      let deadSlot = false
      let forNode = null
      walkAst(ast, (n) => {
        // `<slot name="…">` 在 AST 里是 tag='slot' 的元素，`name` 是静态属性
        if (n.type === 1 && n.tag === 'slot') {
          const p = (n.props || []).find((x) => x.type === 6 && x.name === 'name')
          if (String(p?.value?.content || '') === 'after-message') deadSlot = true
        }
        // NodeTypes.FOR = 11：`v-for` 编译后被包成 FOR 节点，元素挂在它的 children 上
        if (n.type === 11) forNode = n
      })

      // ① 「轮末那一格」现在**必须有消费者**：`turn_end` 分支渲染轮末回退组件。
      //
      //    ⚠️ 2026-09-23 **用户授权反转**（原因：新增了「每轮末尾回退组件」需求，位置就是同一个轮末）。
      //    这条判据原先是**禁止** `<slot name="after-message">`，理由写着「那个插槽是上一个
      //    『每轮末尾分割线』需求的脚手架，**该需求已被用户撤销**」—— 那条理由只对「分割线」成立，
      //    对「轮末」这个位置本身不成立。所以这里改成**守这个组件**：轮末有消费者是**新需求**，
      //    不是旧需求复活；后来人看到这一段时别以为是谁偷偷把脚手架加回来了。
      //    （旧插槽本身仍不许回来 —— 见下面 ③：它是**没人用的空插槽**，与「这一格的唯一消费者」
      //      是两回事。这条护栏没有随反转一起作废。）
      if (!forNode) return '消息列表的 `v-for` 不见了'
      const loopEl = (forNode.children || []).find((c) => c.type === 1)
      if (!loopEl) return '`v-for` 里找不到元素节点'
      const turnBranch = ifBranchOf(loopEl, "'turn_end'")
      if (!turnBranch) {
        return (
          '消息列表里没有 `msg.type === \'turn_end\'` 分支 —— 轮末回退组件没有挂载点' +
          '（`turn_end` 的 role 也是 assistant，没有这一支它就会掉进正文分支变成空气泡）'
        )
      }
      if (!firstNode(turnBranch.branch, (n) => n.type === 1 && n.tag === 'AgentTurnRollback')) {
        return '`turn_end` 分支里没有渲染 `AgentTurnRollback` —— 轮末那一格空了，整条回退入口没了'
      }

      // ② `:key` 必须挂在这个 v-for 的**内层 div** 上。
      //    挂到外层 `<template v-for>` 上时，FOR 的元素子节点（div + slot）都没有 key，
      //    这条就会红 —— 正是要防的「还原成 div v-for 时把 key 忘了」。
      const el = (forNode.children || []).find((c) => c.type === 1)
      if (!el) return '`v-for` 里找不到元素节点'
      const hasKey = (el.props || []).some(
        (p) => p.type === 7 && p.name === 'bind' && String(p.arg?.content) === 'key'
      )
      if (!hasKey) {
        return `\`v-for\` 的元素（tag=${el.tag}）上没有 \`:key\` —— key 挂错层会让消息节点复用/错位`
      }

      // ③ 旧插槽仍不许回来：它服务的是「每轮末尾分割线」，那个需求确实被撤销了，
      //    而且**它从来没有调用方**（全仓 grep 只有它自己）—— 与 ① 的组件不是一回事。
      if (deadSlot) {
        return '`#after-message` 死插槽又回来了 —— 它服务的「每轮末尾分割线」需求已被撤销，别再恢复这段脚手架'
      }
      return null
    }
  },
  {
    id: 'L17',
    file: CONFIRM,
    label: '确认卡片：有 sample 时「共 N 条」必须还在（总数走 count，不走数组长度）',
    fn: () => {
      const src = stripBlockComments(readSource(CONFIRM))
      const problems = []

      // ① 耦合关系（另半边 `:182` 由 ③ 用**真实执行**验证）：
      //    确认卡片的 preview 来自后端的 `tool_confirm` / `/agent/preview`，`sample` 只是「前 N 条样例」，
      //    真值条数在 `count` 里。而 `:182` 让 count 在「有 sample」时**不单独成行** ——
      //    于是 `count` **只剩标题这一个出口**。
      //    所以标题必须由 `total` 渲染，且 `total` 对 `p.count` 必须带数值判定。
      //    ⚠️ 先 `stripBlockComments`：否则下面那串字面量会被旁边一句注释满足（本文件其余断言同样先剥注释）。
      if (!/\$\{total\}/.test(src)) {
        problems.push(
          '标题不再由 total 渲染 —— 「共 N 条」在整张卡片上没有出口：用户只看到「样例（5 条）」，会以为只影响 5 条（实际 10 条），且**零报错**'
        )
      }
      // ⚠️ 这个守卫的**真实语义**（实测出来的，免得后人顺手删掉）——
      //    它是**类型守卫**，不是**数值健全性检查**（这两件事差别很大，别被名字骗）：
      //      · `Infinity` / `NaN` 都是 `typeof 'number'`，**过得去**：喂 `count: Infinity`
      //        原码直接渲染「样例（共 Infinity 条，显示前 5 条）」；
      //      · 而完全正常的字符串数字 `'10'` 反倒被拦下。
      //    实测（固定 `sample` 5 条，只换 `count`，3 种写法对比）：
      //      · `10`     → 原码「共 10 条，显示前 5 条」；砍掉类型守卫**输出完全相同**；
      //      · `'10'`   → 原码退化成「样例（5 条）」；砍掉守卫反而显示「共 10 条，显示前 5 条」；
      //      · `'abc'` / `NaN` / `true` / `null` / `undefined` / 缺失 → 三种写法输出**都是**「样例（5 条）」
      //        （`total > items.length` 在 NaN 比较下为 false，所以「共 NaN 条」**进不了界面**）；
      //      · `Infinity` → 三种写法**都是**「共 Infinity 条」（它过了类型守卫）。
      //    ⇒ sample 场景里，这半边守卫**唯一能观察到的效果就是 `'10'` 那一种，而且是把显示弄差**。
      //      所以**别**把它写成「保护显示」的机制；真正的承重件是**键守卫 `k === 'sample'`**
      //      （它挡住非 sample 数组吃标量 count —— 去掉它，`bank_names` 只有 2 条也会显示
      //      「共 10 条，显示前 2 条」；④ 守的正是这条）。
      //    ⚠️ 那为何**仍然不要删**这半边？它的作用更接近**接口严格性**：把「后端必须发 JSON number」
      //      这个契约**显式化**，类型不符时 **fail-closed**（静默退回「不显示总数」），
      //      而不是让一个来路不明的类型悄悄流进比较与文案。
      //      ⚠️ 但它**保证不了显示出来的数是对的**（`Infinity` 就是活证据）——
      //      「count 是合理整数」这半**必须由后端用例来守**，别指望这个守卫。
      //      （严重度注：`Infinity`/`NaN` 都过不了 `JSON.parse`，实践中传不过来 —— 这是**类型层面**的反例，
      //        不是现网风险；它的价值在于说明这个守卫的语义，别把它当护身符。）
      //    真要支持字符串 count 或挡掉 `Infinity`，正路是**显式转换 + Number.isFinite**
      //    （`const n = Number(p.count)`，再用 `Number.isFinite(n) ? n : items.length`），
      //    并**同步更新 L17** —— 不是把守卫删掉。
      if (!/typeof\s+p\.count\s*===\s*'number'|Number\.isFinite\s*\(\s*p\.count\s*\)|Number\.isInteger\s*\(\s*p\.count\s*\)/.test(src)) {
        problems.push(
          '对 p.count 的数值判定没了 —— count 不再被限定为数字（等价的 Number.isFinite/Number.isInteger 也算过；若你确实换了写法，请同步更新 L17）'
        )
      }

      // ②④⑤ 三次离线真实执行。**先集中跑完再判断**：harness 自身没跑起来时只报**一条**诊断 ——
      // 否则同一个根因会被这里报 3 次，3 行噪音正好盖住真信息（fe-1 实测：加个 `ref(0)` 就会触发）。
      const probed = {
        '②': runConfirmCard({
          action: 'batch_import',
          count: 10,
          sample: ['第1题', '第2题', '第3题', '第4题', '第5题']
        }),
        '④': runConfirmCard({ count: 10, bank_names: ['甲库', '乙库'] }),
        '⑤': runConfirmCard({ action: 'batch_import', count: 5, sample: ['a', 'b', 'c', 'd', 'e'] })
      }
      const harnessFail = Object.entries(probed).find(([, r]) => !r.ok)
      if (harnessFail) {
        return [
          `离线执行 ${CONFIRM} 的 script setup 失败（${harnessFail[0]} 这一跑）：${harnessFail[1].why}`,
          '受影响的 ②③④⑤ 四项**未验证，不是通过**（① 的两条已独立判过）',
          '唯一的修法：把它需要的 API 加进 `runConfirmCard` 的注入参数（见该函数注释），**不要**因此削弱 L17 的断言'
        ].join('；')
      }

      // ② 真实执行（离线）：`:205-206`「count > len(sample)」这条分支此前**零运行时证据**。
      {
        const list = probed['②'].lists.find((l) => l.key === 'sample')
        if (!list) problems.push('previewLists 里没有 sample 条目')
        else {
          if (!list.heading.includes('共 10 条')) {
            problems.push(`sample 标题丢了总条数：「${list.heading}」应含「共 10 条」，否则用户以为只影响 5 条`)
          }
          if (!list.heading.includes('显示前 5 条')) {
            problems.push(`sample 标题没写清只显示了前几条：「${list.heading}」应含「显示前 5 条」`)
          }
          if (list.items.length !== 5) {
            problems.push(`逐条样例变成 ${list.items.length} 条（应 5 条）`)
          }
        }
        // ③ `:182` 那半边：有 sample 时 count 不单独成行。和 ② 是同一条链 ——
        //    「行被抑制」+「标题承载总数」必须同时在，缺一个总数就在卡片上消失。
        if (probed['②'].rows.some((r) => r.key === 'count')) {
          problems.push('有 sample 时 count 又单独成行了（和标题的「共 N 条」重复）—— `:182` 的抑制被删了')
        }
      }

      // ④ 非 sample 数组不许吃 count：count 是标量总数，不是任意数组的长度
      //    （把守卫弱化成裸 `p.count` 就会在这里红：bank_names 只有 2 条却显示「共 10 条」）
      {
        const names = probed['④'].lists.find((l) => l.key === 'bank_names')
        if (!names) problems.push('previewLists 里没有 bank_names 条目')
        else if (names.heading !== '题库名称（2 条）') {
          problems.push(
            `bank_names 标题成了「${names.heading}」—— 非 sample 数组不该拿 count 当长度（正确：「题库名称（2 条）」）`
          )
        }
      }

      // ⑤ count 与样例条数相等时不许写成「共 5 条，显示前 5 条」（把 `>` 写成 `>=` 就会）
      {
        const eq = probed['⑤'].lists.find((l) => l.key === 'sample')
        if (!eq) problems.push('previewLists 里没有 sample 条目（⑤ 的用例）')
        else if (eq.heading !== '样例（5 条）') {
          problems.push(`count 等于样例条数时标题成了「${eq.heading}」—— 应退化成「样例（5 条）」`)
        }
      }

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L18',
    file: KB_PANEL,
    label: '「粘贴文本」与「上传文档」是文档头部的同级入口，且共用同一个忙标记',
    fn: () => {
      const problems = []
      const ast = templateAst(KB_PANEL)
      if (!ast) return `读不到 ${KB_PANEL} 的模板`
      let head = null
      walkAst(ast, (n) => {
        if (!head && nodeClasses(n).includes('kb-docs-head')) head = n
      })
      if (!head) return '找不到 .kb-docs-head 容器'
      const kids = directElements(head)
      const upload = kids.find((k) => nodeClasses(k).includes('kb-upload-btn'))
      const imp = kids.find((k) => nodeClasses(k).includes('kb-import-btn'))
      if (!upload) problems.push('.kb-docs-head 的直接子元素里没有 .kb-upload-btn')
      if (!imp) {
        problems.push('.kb-docs-head 的直接子元素里没有 .kb-import-btn —— 「粘贴文本」必须和「上传文档」并排摆在文档头部')
      }
      if (upload && imp) {
        // 嵌进 <label> 的话，点「粘贴文本」会连带弹出文件选择框
        let nested = false
        walkAst(upload, (n) => {
          if (n !== upload && nodeClasses(n).includes('kb-import-btn')) nested = true
        })
        if (nested) problems.push('「粘贴文本」被塞进了「上传文档」的 <label> 里 —— 点它会连带弹出文件选择框')
      }
      if (imp && !boundExp(imp, 'disabled')) {
        problems.push('「粘贴文本」按钮没有 :disabled 绑定 —— 忙的时候还能点开弹窗')
      }
      // 两个入口必须由**同一个**忙标记驱动：各看各的 ref = 能同时开两次导入，
      // 两次导入的 uploadTip / 轮询会互相覆盖（见组件里 busy 的注释）
      const src = stripBlockComments(readSource(KB_PANEL))
      const def = /const\s+busy\s*=\s*computed\(\(\)\s*=>\s*([^\n]+)\)/.exec(src)
      if (!def) problems.push('找不到共用的忙标记 `const busy = computed(...)`')
      else {
        const exp = def[1]
        if (!/\|\|/.test(exp)) problems.push(`busy 不是「或」关系（${exp.trim()}）—— 两个入口没有真正互斥`)
        if (!/uploading\.value/.test(exp)) problems.push('busy 里没有 uploading.value —— 「上传文档」跑着时还能再开一次粘贴导入')
        if (!/importing\.value/.test(exp)) problems.push('busy 里没有 importing.value —— 「粘贴导入」跑着时还能再选文件')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L19',
    file: KB_PANEL,
    label: '粘贴导入：空正文不发请求 / 正常正文按 trim 后调一次 / 被拒后弹窗不关、正文不清',
    fn: async () => {
      const problems = []

      // ① 空（纯空白）正文：一个请求都不许发。
      //    后端对空内容是 `code 400 内容不能为空` —— 那是**兜底**，不该是唯一防线：
      //    靠它的话用户看到的是「导入失败」而不是「按钮点不动」。
      const blank = kbRuntime(KB_PANEL, {})
      if (!blank.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${blank.why}`
      blank.api.activeKbId.value = 7
      blank.api.importContent.value = '   \n\t  '
      blank.api.importFileName.value = ''
      blank.api.openTextImport()
      await blank.api.submitTextImport()
      if (blank.calls.importDocumentText.length !== 0) {
        problems.push(`空白正文也发了 ${blank.calls.importDocumentText.length} 次 importDocumentText（应 0 次）`)
      }

      // ② 正常正文：调一次，传的是 trim 后的正文与文件名
      const good = kbRuntime(KB_PANEL, {})
      if (!good.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${good.why}`
      good.api.activeKbId.value = 7
      good.api.importContent.value = '  数据结构笔记\n第一行  '
      good.api.importFileName.value = '  期末复习  '
      good.api.openTextImport()
      await good.api.submitTextImport()
      if (good.calls.importDocumentText.length !== 1) {
        problems.push(`正常正文调了 ${good.calls.importDocumentText.length} 次 importDocumentText（应 1 次）`)
      } else {
        const [kbId, content, fileName] = good.calls.importDocumentText[0]
        if (kbId !== 7) problems.push(`importDocumentText 的 kbId 是 ${JSON.stringify(kbId)}（应 7）`)
        if (content !== '数据结构笔记\n第一行') problems.push(`正文没按 trim 后的内容发：${JSON.stringify(content)}`)
        if (fileName !== '期末复习') problems.push(`文件名没 trim：${JSON.stringify(fileName)}（应「期末复习」）`)
      }
      if (good.api.importVisible.value !== false) problems.push('导入成功后弹窗没关掉')
      if (good.api.uploadTip.value === '') problems.push('导入成功后没有进度提示（uploadTip 空着）—— 用户不知道正在向量化')

      // ③ 文件名留空：不由视图自己编名字，交给 api 层默认（`rag.ts` 的 `未命名文档.txt`）
      const noName = kbRuntime(KB_PANEL, {})
      if (!noName.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${noName.why}`
      noName.api.activeKbId.value = 7
      noName.api.importContent.value = '正文'
      noName.api.importFileName.value = '   '
      noName.api.openTextImport()
      await noName.api.submitTextImport()
      if (noName.calls.importDocumentText.length !== 1) {
        problems.push(`文件名留空时调了 ${noName.calls.importDocumentText.length} 次（应 1 次）`)
      } else if (noName.calls.importDocumentText[0][2] !== undefined) {
        problems.push(
          `文件名留空时传了 ${JSON.stringify(noName.calls.importDocumentText[0][2])} —— 应传 undefined，只留 api 层的默认值这一个出处`
        )
      }

      // ④ 后端拒绝：弹窗必须留着、正文必须还在（刚粘的几千字不能因为一次失败就没了）
      const refused = kbRuntime(KB_PANEL, { importResult: { code: 400, msg: '内容不能为空' } })
      if (!refused.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${refused.why}`
      refused.api.activeKbId.value = 7
      refused.api.importContent.value = '很长的一段正文…'
      refused.api.openTextImport()
      await refused.api.submitTextImport()
      if (refused.api.importVisible.value !== true) problems.push('后端拒绝后弹窗被关掉了 —— 用户刚粘的正文没了')
      if (refused.api.importContent.value !== '很长的一段正文…') problems.push('后端拒绝后正文被清空了')
      if (!refused.msgs.error.length) problems.push('后端拒绝后没有 ElMessage.error —— 用户看不到为什么失败')

      // ⑤ 另一个导入在跑时不许再发一次（两个入口往同一个库写文档）
      const busyCase = kbRuntime(KB_PANEL, {})
      if (!busyCase.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${busyCase.why}`
      busyCase.api.activeKbId.value = 7
      busyCase.api.importContent.value = '正文'
      busyCase.api.uploading.value = true
      await busyCase.api.submitTextImport()
      if (busyCase.calls.importDocumentText.length !== 0) {
        problems.push('「上传文档」跑着的时候还能再提交一次粘贴导入 —— 两次导入的进度提示/轮询会互相覆盖')
      }

      // ⑥ 按钮本身也要挡：正文空着时「导入」应该是点不动的。
      //    （这条是**源码级**代理判据：真正的行为判据是 ①；按钮的 disabled 渲染出来什么样要开浏览器，
      //     而 agents 不许开浏览器 —— 所以这里只断「它由正文决定」这个绑定关系。）
      //    按钮靠 `@click="submitTextImport"` 认（el-button 的文案在编译后是 TEXT_CALL，按文案找不稳）。
      const ast = templateAst(KB_PANEL)
      if (!ast) problems.push(`读不到 ${KB_PANEL} 的模板`)
      else {
        let dialog = null
        walkAst(ast, (n) => {
          if (!dialog && n.type === 1 && String(n.tag) === 'el-dialog' && modelExp(n) === 'textImportVisible') dialog = n
        })
        if (!dialog) problems.push('找不到 v-model 绑 textImportVisible 的 el-dialog（粘贴文本弹窗）')
        else {
          let btn = null
          walkAst(dialog, (n) => {
            if (btn || n.type !== 1 || String(n.tag) !== 'el-button') return
            const click = (n.props || []).find((p) => p.type === 7 && p.name === 'on' && p.arg?.content === 'click')
            if (expSource(click) === 'submitTextImport') btn = n
          })
          if (!btn) problems.push('粘贴文本弹窗里找不到 @click 绑 submitTextImport 的 el-button')
          else {
            const exp = boundExp(btn, 'disabled')
            if (!exp) problems.push('「导入」按钮没有 :disabled 绑定 —— 正文空着也能点')
            else if (!/!\s*[\w.]*textImportContent/.test(exp) || !/trim\(\)/.test(exp)) {
              problems.push(`「导入」按钮的 :disabled 是「${exp}」—— 它必须由「正文 trim 后是否为空」决定`)
            }
          }
        }
      }

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L20',
    file: KB_SHELL,
    label: '外壳（入口按钮 + 抽屉）：进页面就把知识库数量取回来（只调 listKnowledgeBases，不拉文档、不起轮询），打开抽屉时真的把面板激活',
    fn: async () => {
      const problems = []

      // ① 挂载期只许取列表。autoSelect 一旦漏掉，就会连锁成
      //    `selectKb → loadDocs → pollDocument` —— 用户没打开过抽屉也被挂上一串
      //    后台轮询，而那些定时器只在抽屉 @closed 时才清。
      //
      //    ⚠️ 这一条断的是**外壳**（入口徽标那条路）：外壳自己 `listKnowledgeBases()` 一次、
      //       顺手把库数喂给徽标，**不碰**面板（面板是懒挂载的，见 `KnowledgeBasePanel` 的
      //       `activate()`）。面板打开那条路在 L60 上断 —— 同一件事分散在两处，
      //       就在两处分别钉住，别只留一边（原来两边都写在这一条里，判据过期时无法分辨）。
      const two = kbRuntime(KB_SHELL, { kbs: [{ kbId: 1, name: '甲' }, { kbId: 2, name: '乙' }] })
      if (!two.ok) return `离线执行 ${KB_SHELL} 的 script setup 失败：${two.why}`
      const m = await two.runMount()
      if (!m.ok) problems.push(m.why)
      if (two.calls.listKnowledgeBases !== 1) {
        problems.push(`挂载期 listKnowledgeBases 调了 ${two.calls.listKnowledgeBases} 次（应 1 次）`)
      }
      if (two.calls.listDocuments !== 0) {
        problems.push(
          `挂载期调了 listDocuments ${two.calls.listDocuments} 次 —— 抽屉没打开也会连锁 loadDocs，给处理中的文档起后台轮询`
        )
      }
      if (two.calls.setTimeout !== 0) problems.push(`挂载期起了 ${two.calls.setTimeout} 个定时器（轮询）`)
      if (two.api.kbCount.value !== 2) {
        problems.push(`kbCount 算成了 ${two.api.kbCount.value}（应 2）—— 徽标数字不对`)
      }

      // ② 没有知识库时数量必须是 0（徽标由 v-if="kbCount" 藏掉，见 ③）
      const none = kbRuntime(KB_SHELL, { kbs: [] })
      if (!none.ok) return `离线执行 ${KB_SHELL} 的 script setup 失败：${none.why}`
      await none.runMount()
      if (none.api.kbCount.value !== 0) {
        problems.push(`空列表时 kbCount 是 ${none.api.kbCount.value}（应 0）—— 用户没有任何知识库却会看到数字`)
      }

      // ③ 模板：徽标就得由 kbCount 控制（0 不渲染）。
      //    ⚠️ `v-if` 的表达式**不在**徽标元素的 props 上（实测：元素上只剩 class），
      //    它在包住它的 IF 节点的 branch.condition 上 —— 所以要走 ifConditionOf。
      const ast = templateAst(KB_SHELL)
      if (!ast) problems.push(`读不到 ${KB_SHELL} 的模板`)
      else {
        let badge = null
        walkAst(ast, (n) => {
          if (!badge && nodeClasses(n).includes('kb-entry-badge')) badge = n
        })
        if (!badge) problems.push('找不到 .kb-entry-badge 徽标节点')
        else {
          const cond = ifConditionOf(ast, badge)
          if (cond !== 'kbCount') {
            problems.push(`.kb-entry-badge 的 v-if 是「${cond || '(没有 v-if)'}」—— 徽标必须由 kbCount 控制（0 就不渲染）`)
          }
        }
      }

      // ④ **拆分之后的接口**：外壳打开时必须真的去激活面板，而且徽标要取面板报的库数。
      //    这是「抽屉里还有内容」的**唯一**机械判据 —— 面板是懒挂载的，
      //    外壳那句 `await panelRef.value?.activate()` 一旦被删掉（或 `activate` 改了名），
      //    用户点开抽屉看到的是一个**空面板**，而所有内容类判据（L19/L22–L26）**照样全绿**。
      //    做法：把 `panelRef.value` 换成一个记名桩 —— `activate` 记账、`getKbCount` 回一个
      //    与列表长度不同的数（3），这样「徽标是外壳自己算的」也能分辨出来。
      const openRt = kbRuntime(KB_SHELL, { kbs: [{ kbId: 1, name: '甲' }, { kbId: 2, name: '乙' }] })
      if (!openRt.ok) return `离线执行 ${KB_SHELL} 的 script setup 失败：${openRt.why}`
      let activated = 0
      openRt.api.panelRef.value = {
        activate: async () => {
          activated += 1
        },
        getKbCount: () => 3
      }
      await openRt.api.onOpen()
      if (activated !== 1) {
        problems.push(
          `打开抽屉时 panelRef.activate() 调了 ${activated} 次（应 1 次）—— 抽屉里会是一个空面板：` +
            '外壳只剩 el-drawer，内容全在 KnowledgeBasePanel 里，不激活它谁也不去取数'
        )
      }
      if (openRt.api.kbCount.value !== 3) {
        problems.push(
          `打开抽屉后徽标是 ${JSON.stringify(openRt.api.kbCount.value)}（应取面板报的 3）—— ` +
            '外壳自己拿挂载期那份数在算，面板里的增删改不会反映到徽标上'
        )
      }

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L21',
    file: KB_SHELL,
    label: '外壳模板引用的标识符必须都能在 <script setup> 里找到（防「模板写了、脚本没写」→ 渲染期 TypeError → 整个组件挂载失败）',
    fn: () => templateIdentifierProblems(KB_SHELL)
  },
  {
    id: 'L22',
    file: KB_PANEL,
    label: '屏蔽开关常驻可见（不在 hover 才显形的 .kb-item-ops 里）+ 行上有常驻的「已屏蔽」状态',
    fn: () => {
      const problems = []
      const ast = templateAst(KB_PANEL)
      if (!ast) return `读不到 ${KB_PANEL} 的模板`

      const ops = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-item-ops'))
      const block = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-block'))
      const sw = firstNode(ast, (n) => n.type === 1 && String(n.tag) === 'el-switch')

      if (!ops) problems.push('找不到 .kb-item-ops')
      if (!block) problems.push('找不到 .kb-block —— 屏蔽开关没有自己的常驻容器')
      if (!sw) problems.push('模板里找不到 el-switch —— 屏蔽功能没有任何入口')

      // ① 开关**不能**在 .kb-item-ops 里：那条规则是 `opacity: 0`，`:hover` 才变 1。
      //    放进去的话用户看不出「哪些库被屏蔽了」—— 而那正是他拨这个开关的目的。
      if (ops && sw) {
        let nested = false
        walkAst(ops, (n) => {
          if (n === sw) nested = true
        })
        if (nested) {
          problems.push(
            '屏蔽开关被放进了 .kb-item-ops —— 那条规则是 `opacity: 0`（`:hover` 才显形）：' +
              '用户看不出哪些库被屏蔽了，只能一个个去悬停猜'
          )
        }
      }
      // ② 开关必须落在自己的常驻容器里
      if (block && sw) {
        let inside = false
        walkAst(block, (n) => {
          if (n === sw) inside = true
        })
        if (!inside) problems.push('el-switch 不在 .kb-block 里 —— 常驻容器与开关对不上')
      }
      // ③ 这条判据的**前提**也得钉住：`.kb-item-ops` 仍是 `opacity: 0`。
      //    哪天有人把它改成常驻可见，「不能放进去」的理由就没了 —— 那时要重新判断并同步这条断言。
      const opsBody = cssRule(cssOf(KB_PANEL), '.kb-item-ops')
      if (!opsBody) problems.push('找不到 .kb-item-ops 规则')
      else if (!/opacity:\s*0/.test(opsBody)) {
        problems.push(
          '.kb-item-ops 不再是 `opacity: 0`（悬停才显形）了 —— 这条断言「开关不能放进去」的前提变了，请重新判断后同步这条断言'
        )
      }

      // ④ 行上必须有**常驻**的「已屏蔽」状态（不能只藏在 el-switch 的 title 里）
      //
      //    ⚠️ 这里必须用 `ownConditionOf`（**直接**包住它的那条 v-if），不能用 `ifConditionOf`：
      //       面板里这枚标记的外层还套着 `v-else`（列表区）与 `v-if="resultsMode"`（结果视图），
      //       `ifConditionOf` 返回的是**最外层**那个条件（实测探针输出 `resultsMode`），
      //       于是这条断言会读到一句与「已屏蔽」毫无关系的表达式 —— 红了以后去改产品代码，
      //       就会把一句本来正确的 v-if 改坏。判据落结构，别用外层条件去判内层节点。
      const mark = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-item-blocked'))
      if (!mark) {
        problems.push('找不到常驻的「已屏蔽」标记（.kb-item-blocked）—— 用户没法一眼看出哪些库被屏蔽')
      } else {
        const cond = (ownConditionOf(ast, mark) || '').replace(/\s+/g, '')
        if (cond !== 'kb.disabled===1') {
          problems.push(
            '「已屏蔽」标记的 v-if 是「' +
              (cond || '(没有 v-if)') +
              '」—— 必须**只**由 `kb.disabled === 1` 决定（写成 `=== 0` 会把每个现存知识库都画成已屏蔽）'
          )
        }
      }
      // ⑤ 整行视觉压暗也要挂在同一个判据上
      const item = firstNode(
        ast,
        (n) => n.type === 1 && /kb-item/.test(boundExp(n, 'class') || '')
      )
      if (!item) problems.push('找不到带 :class 的知识库行节点（.kb-item）')
      else {
        const cls = (boundExp(item, 'class') || '').replace(/\s+/g, '')
        if (!/blocked:kb\.disabled===1/.test(cls)) {
          problems.push('行上的 :class 里没有 `blocked: kb.disabled === 1`（实际：' + cls + '）')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L23',
    file: KB_PANEL,
    label: '屏蔽开关是受控式：写 { disabled: 0|1 } 且只有 code 200 才重取列表；假 200 不伪造「已屏蔽」，被拒不留本地改动',
    fn: async () => {
      const problems = []

      // ① 「光打开列表」不许写任何东西 —— 挂载期那次程序化 emit 一旦落到写接口上，
      //    十几行的列表就是十几个 PUT
      const idle = kbRuntime(KB_PANEL, { kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 0 }] } })
      if (!idle.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${idle.why}`
      await idle.api.loadKbs()
      if (idle.calls.updateKnowledgeBase.length !== 0) {
        problems.push('光打开列表就调了 updateKnowledgeBase —— 开关的程序化 emit 没被挡住')
      }

      // ② 用户拨到「已屏蔽」：载荷的**键名必须恰好是 disabled**（值 0/1），kbId 是被拨的那一行。
      //    这是唯一能在不开浏览器、不连后端的情况下抓住「字段名前后端不一致」的机械判据 ——
      //    前端静态检查不做类型检查（`ts.transpileModule` 只擦类型），
      //    后端 pydantic 的 extra='ignore' 也曾把多余键静默丢掉。
      const off = kbRuntime(KB_PANEL, { kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 0 }] } })
      if (!off.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${off.why}`
      await off.api.loadKbs()
      await off.api.toggleKbDisabled(off.api.kbs.value[0], false)
      if (off.calls.updateKnowledgeBase.length !== 1) {
        problems.push(`拨一次开关调了 ${off.calls.updateKnowledgeBase.length} 次 updateKnowledgeBase（应 1 次）`)
      } else {
        const [kbId, payload] = off.calls.updateKnowledgeBase[0]
        if (kbId !== 5) problems.push(`updateKnowledgeBase 的 kbId 是 ${JSON.stringify(kbId)}（应 5 —— 被拨的那一行）`)
        const keys = Object.keys(payload || {})
        if (keys.length !== 1 || keys[0] !== 'disabled') {
          problems.push(
            `载荷的键是 ${JSON.stringify(keys)} —— 必须**恰好**是 { disabled: 0|1 }。` +
              '写成 blocked / enabled / is_disabled 之类，后端（extra=forbid 之前）会静默丢掉、照样回 200，' +
              '服务端什么都没存而 UI 看起来成功了'
          )
        }
        if (payload?.disabled !== 1) {
          problems.push(`拨到「已屏蔽」时发的 disabled 是 ${JSON.stringify(payload?.disabled)}（应整数 1，不是布尔/字符串）`)
        }
      }
      // ③ 写成功后必须**重取列表**（显示值只认服务端回值）
      const before = off.calls.listKnowledgeBases
      await off.api.toggleKbDisabled({ kbId: 5, name: '甲', disabled: 1 }, true) // 取消屏蔽
      if (off.calls.listKnowledgeBases <= before) {
        problems.push('写成功后没有重取列表 —— 显示值只能是本地猜的（乐观式）')
      }
      if (off.calls.updateKnowledgeBase[1]?.[1]?.disabled !== 0) {
        problems.push(`取消屏蔽时发的 disabled 是 ${JSON.stringify(off.calls.updateKnowledgeBase[1]?.[1]?.disabled)}（应整数 0）`)
      }

      // ④ **假成功**：后端回 code 200 但服务端根本没改（重取回来这一行仍是 disabled:0）。
      //    后端的 catch-all 会把「路由被挪走 / 字段名不一致」变成 `code 200 + data:null` 这种信封 ——
      //    乐观式在这里会把开关留在「已屏蔽」上：用户以为被屏蔽了，下一次提问照样整库喂给模型。
      const fake = kbRuntime(KB_PANEL, {
        updateResult: { code: 200 },
        kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 0 }] }
      })
      if (!fake.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${fake.why}`
      await fake.api.loadKbs()
      await fake.api.toggleKbDisabled(fake.api.kbs.value[0], false)
      if (fake.api.kbEnabled(fake.api.kbs.value[0]) !== true) {
        problems.push('假 200（服务端没改）时开关被本地翻成了「已屏蔽」—— UI 在骗用户，模型下一次照样看得到这个库')
      }

      // ⑤ 服务端**真的**改了：显示值必须跟着服务端回值走
      let round = 0
      const real = kbRuntime(KB_PANEL, {
        kbsResult: () => {
          round += 1
          return { code: 200, data: [{ kbId: 5, name: '甲', disabled: round === 1 ? 0 : 1 }] }
        }
      })
      if (!real.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${real.why}`
      await real.api.loadKbs()
      if (real.api.kbEnabled(real.api.kbs.value[0]) !== true) problems.push('预置：服务端第一轮回的是 disabled:0，开关却不是「正常」')
      await real.api.toggleKbDisabled(real.api.kbs.value[0], false)
      if (real.api.kbEnabled(real.api.kbs.value[0]) !== false) {
        problems.push('服务端回值已经翻转成 disabled:1，开关却还显示「正常」—— 显示值没跟服务端走')
      }

      // ⑥ 被拒（code !== 200）：不许留下本地改动、要弹错、也不该去重取列表
      const rejected = kbRuntime(KB_PANEL, {
        updateResult: { code: 403, msg: '不许改' },
        kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 0 }] }
      })
      if (!rejected.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${rejected.why}`
      await rejected.api.loadKbs()
      const beforeReject = rejected.calls.listKnowledgeBases
      const row = rejected.api.kbs.value[0]
      await rejected.api.toggleKbDisabled(row, false)
      if (row.disabled !== 0) problems.push(`被拒后本地的 disabled 被改成了 ${JSON.stringify(row.disabled)}（应保持 0）`)
      if (rejected.api.kbEnabled(row) !== true) problems.push('被拒后开关没有保持原位')
      if (rejected.calls.listKnowledgeBases !== beforeReject) problems.push('被拒后还去重取了列表')
      if (!rejected.msgs.error.length) problems.push('被拒后没有 ElMessage.error —— 用户不知道没改成')

      // ⑦ 写请求抛异常：同样不许留下本地改动
      const threw = kbRuntime(KB_PANEL, {
        updateThrows: true,
        kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 0 }] }
      })
      if (!threw.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${threw.why}`
      await threw.api.loadKbs()
      const tRow = threw.api.kbs.value[0]
      await threw.api.toggleKbDisabled(tRow, false)
      if (threw.api.kbEnabled(tRow) !== true) problems.push('写请求抛异常后开关没有保持原位')
      if (!threw.msgs.error.length) problems.push('写请求抛异常后没有 ElMessage.error')

      // ⑧ 开关报的就是**当前**状态 → 一次写都不许发（程序化 emit / 重复点击的守卫）
      const noop = kbRuntime(KB_PANEL, { kbsResult: { code: 200, data: [{ kbId: 5, name: '甲', disabled: 1 }] } })
      if (!noop.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${noop.why}`
      await noop.api.loadKbs()
      await noop.api.toggleKbDisabled(noop.api.kbs.value[0], false) // 已经是「已屏蔽」，又要「已屏蔽」
      if (noop.calls.updateKnowledgeBase.length !== 0) {
        problems.push('开关报的正是当前状态时也发了写请求 —— 那次无用户操作的程序化 emit / 重复点击没被挡住')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L24',
    file: KB_PANEL,
    label: '屏蔽开关的绑定值恒为布尔（el-switch 挂载期那次无用户操作的 emit 不可能发生）+ 只有 disabled===1 才算屏蔽',
    fn: async () => {
      const problems = []
      const rt = kbRuntime(KB_PANEL, {})
      if (!rt.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${rt.why}`
      if (typeof rt.api.kbEnabled !== 'function') {
        return '组件里找不到 kbEnabled —— 开关的显示判据没有单一出处（判据散在模板里就没人能测它）'
      }

      // ① 取值域：开关的绑定值必须**恒为布尔**。
      //    el-switch（已安装的 element-plus@2.14.5，
      //    `es/components/switch/src/switch.vue_vue_type_script_setup_true_lang.mjs:71-76`）
      //    在 setup 期有一句裸 `if (![activeValue, inactiveValue].includes(actualValue))`，
      //    命中就**在没有用户操作的情况下** emit 一次 `update:modelValue` / `change` / `input`
      //    （默认取值域是 [true, false]）。所以「绑定值恒为布尔」＝「那次 emit 不可能发生」。
      //    绑原始 `kb.disabled`：`undefined`（后端这一列还没上线）与字符串 `'1'`（类型不匹配，
      //    那边是严格 `===`）都会命中 ⇒ 列表里每一行各 emit 一次 ⇒ 打开抽屉就是十几个 PUT。
      const domain = [undefined, null, 0, 1, 2, -1, '0', '1', true, false, '', 'x']
      for (const v of domain) {
        const got = rt.api.kbEnabled({ kbId: 1, name: '甲', disabled: v })
        if (typeof got !== 'boolean') {
          problems.push(
            `disabled=${JSON.stringify(v)} 时开关的绑定值是 ${JSON.stringify(got)}（${typeof got}）—— ` +
              '不在 [true, false] 取值域里，el-switch 会在挂载期无用户操作地 emit 一次，' +
              '那一行的开关就会被程序化地"拨"一下'
          )
        }
      }

      // ② 判据只能是 `=== 1`。`disabled` 是后加的列：在这一版后端上线前，
      //    每一行的运行时值都是 `undefined` —— 写成「`=== 0` 才算正常」会把
      //    **每一个现存知识库**都画成「已屏蔽」，用户会以为自己的资料全被屏蔽了。
      const cases = [
        [undefined, true, '后端还没下发这一列（真实现场，最容易写反的一格）'],
        [null, true, 'null 同上'],
        [0, true, '正常'],
        [1, false, '已屏蔽'],
        [2, true, '只有 === 1 才算屏蔽，不是「非 0 即屏蔽」'],
        ['1', true, '字符串 "1" 不算屏蔽（后端若哪天发字符串，判据不该跟着飘）'],
        ['0', true, '字符串 "0" 不算屏蔽']
      ]
      for (const [v, want, why] of cases) {
        const got = rt.api.kbEnabled({ kbId: 1, name: '甲', disabled: v })
        if (got !== want) {
          problems.push(`disabled=${JSON.stringify(v)} 时 kbEnabled 是 ${JSON.stringify(got)}（应 ${want}）—— ${why}`)
        }
      }

      // ③ 模板侧：`:model-value` 必须绑那个布尔表达式，不能绑原始字段；
      //    也不能写 :active-value / :inactive-value 把取值域改掉；更不能退回 v-model（乐观式）
      const ast = templateAst(KB_PANEL)
      if (!ast) return problems.length ? problems.join('；') : `读不到 ${KB_PANEL} 的模板`
      const sw = firstNode(ast, (n) => n.type === 1 && String(n.tag) === 'el-switch')
      if (!sw) problems.push('模板里找不到 el-switch（屏蔽开关）')
      else {
        const exp = boundExp(sw, 'model-value')
        if (!exp) {
          problems.push('屏蔽开关没有 :model-value 绑定 —— 它不会反映服务端的 disabled')
        } else if (/^[\w.$]+$/.test(exp)) {
          problems.push(
            `屏蔽开关的 :model-value 绑的是原始字段「${exp}」—— 值可能是 undefined / 字符串，` +
              '不在 [true, false] 里，会触发挂载期那次 emit（见 ①）'
          )
        } else if (!exp.includes('kbEnabled(')) {
          problems.push(`屏蔽开关的 :model-value 是「${exp}」—— 判据必须走 kbEnabled(kb) 这唯一出处`)
        }
        for (const prop of ['active-value', 'inactive-value']) {
          const v = boundExp(sw, prop)
          if (v !== null && v !== 'true' && v !== 'false') {
            problems.push(
              `屏蔽开关写了 :${prop}="${v}" —— 取值域不再是布尔，:model-value 的布尔表达式就白写了（且重新打开了那次 emit 的门）`
            )
          }
        }
        if (modelExp(sw)) {
          problems.push('屏蔽开关用了 v-model —— 那会重新引入「本地改值」的乐观式写法（显示值必须只来自服务端）')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L25',
    file: KB_PANEL,
    label: '知识库搜索：filteredKbs 按名字不区分大小写过滤、「搜索没命中」与「一个库都没有」文案分开、徽标仍数全部库、列表自己可滚、搜索框真的接上了（回车 / 作用域提示）',
    fn: async () => {
      const problems = []
      // ⚠️ `rt.api.kbFilter` 是**判据侧的名字**（语义：那个搜索词）；面板里它叫 `query`
      //    （一个框同时承担「筛库名」与「回车检索」两件事）。映射见 `KB_API_NAMES`。
      const rt = kbRuntime(KB_PANEL, {
        kbs: [
          { kbId: 1, name: '数据结构期末复习', disabled: 0 },
          { kbId: 2, name: '操作系统', disabled: 0 },
          { kbId: 3, name: 'Data Structure 笔记', disabled: 1 }
        ]
      })
      if (!rt.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${rt.why}`
      await rt.api.loadKbs()
      if (!('filteredKbs' in rt.api)) return '组件里找不到 filteredKbs —— 列表没有可测的过滤出处'

      // ① 没有搜索词 → **原样返回 kbs**（不新建数组），而且**包含被屏蔽的库**：
      //    后端故意把它们留在管理列表里，筛掉用户就没法取消屏蔽了
      if (rt.api.filteredKbs.value.length !== 3) {
        problems.push(`无搜索词时列表是 ${rt.api.filteredKbs.value.length} 条（应 3 条，含被屏蔽的那个）`)
      }
      if (rt.api.filteredKbs.value !== rt.api.kbs.value) {
        problems.push('无搜索词时新建了数组 —— 应原样返回 kbs（省一次无谓重渲染）')
      }

      // ② 中文子串命中
      rt.api.kbFilter.value = '数据'
      if (rt.api.filteredKbs.value.length !== 1 || rt.api.filteredKbs.value[0].kbId !== 1) {
        problems.push(`搜「数据」命中 ${JSON.stringify(rt.api.filteredKbs.value.map((k) => k.kbId))}（应 [1]）`)
      }
      // ③ 大小写不敏感 + 首尾空白不影响
      rt.api.kbFilter.value = '  DATA  '
      if (rt.api.filteredKbs.value.length !== 1 || rt.api.filteredKbs.value[0].kbId !== 3) {
        problems.push(
          `搜「  DATA  」命中 ${JSON.stringify(rt.api.filteredKbs.value.map((k) => k.kbId))}（应 [3]）—— 要 trim 且不区分大小写`
        )
      }
      // ④ 搜不到 → 空
      rt.api.kbFilter.value = '不存在的关键词'
      if (rt.api.filteredKbs.value.length !== 0) {
        problems.push(`搜不存在的关键词命中 ${rt.api.filteredKbs.value.length} 条（应 0）`)
      }
      // ⑤ 行的 name 缺失/非字符串不许把整条路径炸掉（后端字段缺失时的真实现场）
      const odd = kbRuntime(KB_PANEL, { kbs: [{ kbId: 9 }, { kbId: 10, name: null }, { kbId: 11, name: '有名字' }] })
      if (!odd.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${odd.why}`
      await odd.api.loadKbs()
      odd.api.kbFilter.value = '有名字'
      if (odd.api.filteredKbs.value.length !== 1) problems.push('列表里有 name 缺失的行时，过滤把它整条路径炸了或算错了')

      // ⑥ 徽标仍数**全部**库（与 L20 的外壳徽标耦合在这里显式钉住：徽标回答的是「我有几个库」，
      //    不是「这次搜到几个」—— 所以它不能被搜索词影响）
      rt.api.kbFilter.value = '数据'
      if (rt.api.kbCount.value !== 3) {
        problems.push(`筛选后 kbCount 变成 ${rt.api.kbCount.value}（应仍是 3）—— 徽标回答的是「我有几个库」，不是「搜到几个」`)
      }
      rt.api.kbFilter.value = ''

      // ⑦ 搜索框必须真的接上（不是摆设）。
      //
      //    ⚠️ 这条**原来是**「知识库列表的 v-for 数据源必须是 filteredKbs」—— 老抽屉的搜索框
      //       是「按名字筛列表」。重构后的面板换了设计：列表**不再**按名字筛
      //       （`v-for="kb in kbs"`：被屏蔽的库也要留在列表里，否则用户没法取消屏蔽 ——
      //       与上面的注释一致），搜索词改走两条出口：回车跨库语义检索（结果视图）
      //       ＋ 列表模式下的作用域提示（`.kb-scope`，把「在全部 N 个知识库里搜」写在用户眼前）。
      //       所以判据跟着改成**「搜索框必须有可见出口」** —— 这是同一件防护的另一种落地
      //       （原意就是「别让搜索框白摆着」），不是把断言删掉：出口全没了才算红。
      //
      //    ⚠️ 现状里 `filteredKbs` 这个 computed **一个消费者都没有**（全文件只有它自己那一处
      //       定义），而它的注释还写着「列表模式会渲染这份过滤结果」—— 注释与模板自相矛盾。
      //       这属于**产品侧要决定的事**（要么把名字过滤接回列表，要么把这个 computed 删掉），
      //       已上报；断言不替它选一边，所以这里只钉「搜索框有出口」。
      const ast = templateAst(KB_PANEL)
      if (!ast) return problems.length ? problems.join('；') : `读不到 ${KB_PANEL} 的模板`
      const kbFor = firstNode(ast, (n) => n.type === 11 && String(n.valueAlias?.loc?.source || '') === 'kb')
      const listSrc = kbFor ? String(kbFor.source?.loc?.source || '').trim() : null
      const scope = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-scope'))
      const scopeCond = scope ? ownConditionOf(ast, scope) || '' : ''
      if (!listSrc) problems.push('找不到 `v-for="kb in …"` 的列表节点 —— 知识库列表整个没了')
      if (listSrc !== 'filteredKbs' && !/query/.test(scopeCond)) {
        problems.push(
          `搜索框没有任何可见出口：列表不按它筛（v-for 走 ${JSON.stringify(listSrc)}），` +
            `也没有由它驱动的作用域提示（.kb-scope 的 v-if 是「${scopeCond || '(没有 v-if)'}」）—— 输入框成了摆设`
        )
      }
      const searchInput = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-search-input'))
      if (!searchInput) problems.push('找不到 .kb-search-input 搜索输入框')
      else {
        const bind = modelExp(searchInput) || boundExp(searchInput, 'value') || ''
        if (!/query/.test(bind)) {
          problems.push(`搜索框的输入绑定是「${bind || '(没有绑定)'}」—— 用户打进去的字没人接（应绑 query）`)
        }
        const enter = (searchInput.props || []).find(
          (p) => p.type === 7 && p.name === 'on' && p.arg && p.arg.content === 'keydown'
        )
        const enterExp = expSource(enter) || ''
        const enterMods = (enter?.modifiers || []).map((m) => (m && m.content) || m)
        if (!/runSearch/.test(enterExp) || !enterMods.includes('enter')) {
          problems.push(
            `搜索框的回车没接上检索（@keydown${enterMods.length ? '.' + enterMods.join('.') : ''}="${
              enterExp || '(没接)'
            }"）—— 面板的占位文案写着「回车检索」，按下却什么都不发生`
          )
        }
      }

      // ⑧ 两种空态：一个「一个知识库都没有」，一个「搜索没命中」—— 文案必须不同。
      //    共用「还没有知识库」那句会让用户以为自己的库被清空了。
      //
      //    ⚠️ 两个空态**按结构分辨**（各看自己那条 v-if 的判据），不靠文案猜：
      //       结果视图那个由 `searchHits` 决定，列表那个由 `kbs.length` 决定。
      //    ⚠️ 这里也必须用 `ownConditionOf` —— 两个节点都还套在别人的 v-if / v-else 里，
      //       `ifConditionOf` 读回来的是**最外层**那句（实测两个都返回 `resultsMode`），
      //       于是「搜索没命中」会被认成任意一个，判据整个失效。
      const empties = []
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('kb-empty')) empties.push(n)
      })
      if (empties.length !== 2) {
        problems.push(`.kb-empty 节点有 ${empties.length} 个（应 2 个：一个「没有知识库」、一个「搜索没命中」）`)
      } else {
        const info = empties.map((n) => ({ cond: ownConditionOf(ast, n) || '', text: nodeText(n) }))
        const noMatch = info.find((i) => /searchHits/.test(i.cond))
        const noKb = info.find((i) => /kbs\.length/.test(i.cond))
        if (!noMatch) problems.push('没有一条 .kb-empty 的条件由 `searchHits` 决定 —— 「搜索没命中」没有独立文案')
        if (!noKb) problems.push('没有一条 .kb-empty 的条件由 `kbs.length` 决定 —— 「一个知识库都没有」的引导文案没了')
        if (noMatch && noKb && noMatch.text === noKb.text) {
          problems.push('两种空态的文案一模一样 —— 搜索没命中时用户会以为自己一个知识库都没有（假信息）')
        }
        if (noMatch && /还没有知识库/.test(noMatch.text)) {
          problems.push('「搜索没命中」仍然用了「还没有知识库」那句引导文案 —— 那是假信息')
        }
        if (noMatch && !/searchedQuery|query/.test(noMatch.text)) {
          problems.push('「搜索没命中」的文案没有回显用户输入的关键词（query / searchedQuery）—— 用户不知道自己在筛什么')
        }
      }

      // ⑨ 列表要能自己滚：库多了（十几个）不许把文档区与「试检索」输入框整个推出视口
      const body = cssRule(cssOf(KB_PANEL), '.kb-list-wrap')
      if (!body) problems.push('找不到 .kb-list-wrap 规则')
      else {
        if (!/max-height\s*:/.test(body)) {
          problems.push('.kb-list-wrap 没有 max-height —— 十几个知识库时列表会把文档区和「试检索」输入框推出视口')
        }
        if (!/overflow-y\s*:\s*auto/.test(body)) {
          problems.push('.kb-list-wrap 没有 overflow-y: auto —— 只有 max-height 会把内容裁掉，而不是可以滚')
        }
      }
      // ⑩ 名字被省略号截断时要能看出全名（`.kb-doc-name` 早有 :title，列表这边漏了）
      const name = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-item-name'))
      if (!name) problems.push('找不到 .kb-item-name')
      else if (boundExp(name, 'title') !== 'kb.name') {
        problems.push(`.kb-item-name 的 :title 是 ${JSON.stringify(boundExp(name, 'title'))}（应绑 kb.name）—— 名字被截断后看不出全名`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L26',
    file: KB_PANEL,
    label: '列表「没取到」不静默通过：非数组响应要立 kbLoadFailed、且不出现「还没有知识库」那套引导文案',
    fn: async () => {
      const problems = []

      // ① code 200 但 `data` 不是数组 —— 后端 catch-all 按路径关键字分流，
      //    返回的正是 `{code:200,total:0,rows:[]}`（**没有 data 键**）这种信封。
      //    原先 `if (code === 200 && Array.isArray(data))` 会整块跳过：没有 else、没有报错。
      const odd = kbRuntime(KB_PANEL, { kbsResult: { code: 200, total: 0, rows: [] } })
      if (!odd.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${odd.why}`
      await odd.api.loadKbs()
      if (odd.api.kbLoadFailed?.value !== true) {
        problems.push(
          '响应是 `{code:200,total:0,rows:[]}`（没有 data 数组）时 kbLoadFailed 没立起来 —— ' +
            '「没取到列表」被静默当成了「零个知识库」'
        )
      }
      if (odd.api.kbCount.value !== 0) {
        problems.push(`取不到列表时 kbCount 是 ${odd.api.kbCount.value}（应 0 —— 拿不到数字就别显示数字）`)
      }

      // ② 请求抛错同样要立起来（首次打开 + 后端没起：最容易被当成「用户没有库」的那一格）
      const boom = kbRuntime(KB_PANEL, { kbsThrows: true })
      if (!boom.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${boom.why}`
      await boom.api.loadKbs()
      if (boom.api.kbLoadFailed?.value !== true) {
        problems.push('列表请求抛异常时 kbLoadFailed 没立起来 —— 用户会看到「还没有知识库」')
      }

      // ③ 下一次取到正常列表要清掉（否则提示会长期挂着）
      const recover = kbRuntime(KB_PANEL, {
        kbsResult: (n) => (n === 1 ? { code: 200, total: 0, rows: [] } : { code: 200, data: [{ kbId: 1, name: '甲', disabled: 0 }] })
      })
      if (!recover.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${recover.why}`
      await recover.api.loadKbs()
      const afterFirst = recover.api.kbLoadFailed?.value
      await recover.api.loadKbs()
      if (afterFirst !== true) problems.push('预置：第一次非数组响应没有立起 kbLoadFailed')
      if (recover.api.kbLoadFailed?.value !== false) problems.push('恢复正常响应后 kbLoadFailed 没清掉 —— 提示会一直挂着')

      // ④ 模板：**有十几个库的用户不得被告知「还没有知识库」**。
      //    空态引导文案必须被 kbLoadFailed 挡住，并且另有一条看得见的提示。
      //    ⚠️ 条件一律读 `ownConditionOf`（目标**自己**那条 v-if）：面板里这两个节点
      //       还套在别人的 v-if / v-else 里，`ifConditionOf` 会返回最外层那句
      //       （实测返回 `resultsMode`），那样「有没有被 kbLoadFailed 挡住」就成了
      //       在断言一个与本题无关的表达式 —— 假红，然后去改坏正确的产品代码。
      const ast = templateAst(KB_PANEL)
      if (!ast) return problems.length ? problems.join('；') : `读不到 ${KB_PANEL} 的模板`
      const empties = []
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('kb-empty')) empties.push(n)
      })
      const onboarding = empties.find((n) => /还没有知识库/.test(nodeText(n)))
      if (!onboarding) problems.push('找不到「还没有知识库」那条空态引导节点')
      else {
        const cond = ownConditionOf(ast, onboarding) || ''
        if (!/kbLoadFailed/.test(cond)) {
          problems.push(
            `「还没有知识库」空态的 v-if 是「${cond}」—— 它必须被 kbLoadFailed 挡住：` +
              '取不到列表时它是一句假话（真实情况是请求没成功，不是用户没有库）'
          )
        }
      }
      const banner = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('kb-load-failed'))
      if (!banner) problems.push('找不到「列表没取到」的提示节点（.kb-load-failed）—— 那就只剩一句假话给用户看')
      else {
        const bc = ownConditionOf(ast, banner) || ''
        if (!/kbLoadFailed/.test(bc)) {
          problems.push(`.kb-load-failed 的 v-if 是「${bc}」—— 它必须由 kbLoadFailed 控制`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L27',
    file: CHAT,
    label: '历史会话是**覆盖层**浮层（absolute + 锚在输入卡片上方），旧左侧栏形态不许回来',
    fn: () => {
      const problems = []
      const body = cssRule(cssOf(CHAT), '.session-popover')
      if (!body) {
        problems.push('找不到 .session-popover 规则 —— 历史会话的浮层形态没了')
      } else {
        if (!/position:\s*absolute/.test(body)) {
          problems.push(
            '.session-popover 不是 position: absolute —— 浮层必须脱离布局流：' +
              '留在流里就会像旧左侧栏（.agent-sidebar）那样把消息区挤窄'
          )
        }
        const z = pxValue(body, 'z-index')
        if (z == null || z <= 0) {
          problems.push(
            `.session-popover 的 z-index 是「${declValue(body, 'z-index') || '(没写)'}」—— 覆盖层要明确压住消息区`
          )
        }
        const bottom = declValue(body, 'bottom')
        if (!bottom || !bottom.includes('100%')) {
          problems.push(
            `.session-popover 的 bottom 是「${bottom || '(没写)'}」—— 要写成 calc(100% + Npx)：` +
              '以**输入卡片**为基准往上弹，卡片长高 / 底部统计条出现时才不用手算偏移'
          )
        }
        const maxH = declValue(body, 'max-height')
        if (!maxH) {
          problems.push('.session-popover 没有 max-height —— 会话多的时候会顶出 .ai-chat-stream 上沿被裁掉')
        } else if (maxH.includes('%')) {
          problems.push(
            `.session-popover 的 max-height 是「${maxH}」—— 百分比是相对**输入卡片**（约 113px 高）解析的，` +
              '会小到只剩几十像素，要用 vh/px'
          )
        }
      }

      // 浮层的定位基准：`.chat-input-area` 必须是 position: relative（含块），
      // 否则 `bottom: calc(100% + 8px)` 会去认更外层的祖先，锚点整条失效。
      const inputCard = cssRule(cssOf(INPUT), '.chat-input-area')
      if (!inputCard) problems.push(`读不到 ${INPUT} 的 .chat-input-area 规则`)
      else if (!/position:\s*relative/.test(inputCard)) {
        problems.push(
          `${INPUT} 的 .chat-input-area 不是 position: relative —— ` +
            '它是会话浮层的定位基准（浮层写在 #input-footer 槽里），少了它锚点就挂到更外层去了'
        )
      }

      // 旧形态的模板痕迹：`<aside>` 不只是「过时的写法」——
      // 全局样式 `aside { padding: 16px 24px; margin-bottom: 20px; border-radius: 12px; border: 1px solid … }`
      // （src/assets/styles/index.scss:104）会**悄悄**给任何一个 aside 补上内边距/外边距/圆角，
      // 那正是这一版要改掉的「不对齐」。浮层用 `<div>`。
      const ast = templateAst(CHAT)
      if (!ast) problems.push('拿不到模板 AST')
      else {
        const classes = new Set()
        let asideCount = 0
        walkAst(ast, (n) => {
          if (n.type !== 1) return
          if (String(n.tag) === 'aside') asideCount += 1
          nodeClasses(n).forEach((c) => classes.add(c))
        })
        if (asideCount) {
          problems.push(
            `模板里还有 ${asideCount} 个 <aside> —— 历史会话已改成浮层；` +
              '全局样式里的 aside{…} 会给它补上 padding/margin/圆角/描边'
          )
        }
        const back = ['agent-sidebar', 'side-head', 'side-list', 'side-item', 'side-empty', 'side-close'].filter((c) =>
          classes.has(c)
        )
        if (back.length) problems.push(`已删掉的左侧栏节点又回来了：${back.join('、')}`)
      }
      if (/\.slide-left-/.test(cssOf(CHAT))) {
        problems.push('.slide-left-* 的过渡定义还在 —— 那是旧左侧栏「动 width」的动画，已随形态一起删除')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L28',
    file: CHAT,
    label: '过渡只动合成/绘制属性：不许 all、不许 width/height（chat.vue + ChatInputArea 一起守）',
    fn: () => {
      const problems = []
      // 为什么连 ChatInputArea 一起守：`transition: all` 今天可能只 hover 到颜色（不是缺陷），
      // 但它是「将来谁往状态里加一个 padding/width 就静默变成逐帧重排」的机制 —— 守卫要堵的是这个机制。
      for (const rel of [CHAT, INPUT]) {
        const decls = transitionDecls(cssOf(rel))
        if (!decls.length) {
          problems.push(`${rel} 里一条 transition 都没了 —— 浮层/输入区总得有个进场或 hover 过渡（只动 opacity/transform/颜色就够了）`)
        }
        for (const d of decls) {
          const bad = d.props.filter((p) => LAYOUT_ANIM_PROPS.has(p))
          if (bad.length) {
            problems.push(
              `${rel} 的 ${d.selector} { ${d.prop}: ${d.raw} } —— 动到了布局属性 ${bad.join('、')}：` +
                '过渡是**逐帧**的，每帧都要重新排版整个子树（消息列表 / 输入区就在里面），这就是「点一下卡一下」的来源'
            )
          }
        }
      }
      // 起手态（进场第一帧 / 退场最后一帧）只允许 opacity/transform：
      // 旧形态正是在这里写 `width: 0`，而宽度是布局属性。
      const css = cssOf(CHAT)
      for (const sel of ['.pop-fade-enter-from', '.pop-fade-leave-to']) {
        const b = ruleBodyWith(css, sel)
        if (!b) {
          problems.push(`找不到 ${sel} 规则 —— 浮层要用 transform/opacity 起手，不许动 width/height`)
          continue
        }
        const bad = declaredPropNames(b).filter((p) => !['opacity', 'transform'].includes(p))
        if (bad.length) {
          problems.push(
            `${sel} 里除了 opacity/transform 还改了 ${bad.join('、')} —— ` +
              '起手态一旦动了布局属性，动画每一帧都要重排'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L29',
    file: CHAT,
    label: '会话搜索按标题过滤：忽略首尾空格、不区分大小写、「新会话」兜底能搜到、匹配不上时不篡改原数组',
    fn: () => {
      const rt = chatRuntime()
      if (!rt.ok) return `离线执行 ${CHAT} 的 script setup 失败：${rt.why}`
      const problems = []
      const seed = [
        { sessionId: 'a', title: '数据结构错题整理' },
        { sessionId: 'b', title: 'Agent Debug 记录' },
        { sessionId: 'c', title: '' }
      ]
      rt.api.sessions.value = seed
      const check = (kw, expect, why) => {
        rt.api.sessionKeyword.value = kw
        const got = rt.api.filteredSessions.value.map((s) => s.sessionId)
        if (got.join(',') !== expect.join(',')) {
          problems.push(`关键词 ${JSON.stringify(kw)} ${why}：命中 [${got.join(',')}]（应是 [${expect.join(',')}]）`)
        }
      }
      check('', ['a', 'b', 'c'], '（不搜时）应原样给出全部会话，且保持原顺序')
      check('  结构  ', ['a'], '应忽略首尾空格后再按标题匹配')
      check('agent', ['b'], '应不区分大小写')
      check('新会话', ['c'], '没有标题的会话在列表里显示「新会话」，搜「新会话」也要能搜到它（搜到的就是看到的）')
      check('不存在的词', [], '匹配不上时应给空列表')
      if (rt.api.sessions.value.length !== seed.length) {
        problems.push(
          `过滤把原数组改掉了：sessions 从 ${seed.length} 条变成 ${rt.api.sessions.value.length} 条 —— ` +
            '清空关键词后用户会少看到会话'
        )
      }
      rt.api.sessionKeyword.value = ''
      if (rt.api.filteredSessions.value.length !== seed.length) {
        problems.push('清空关键词后没有恢复成全部会话')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L30',
    file: CHAT,
    label: '两种空态分开说：一条会话都没有 ≠ 搜索没命中（文案不同，且没命中那句带上关键词）',
    fn: () => {
      const problems = []
      const ast = templateAst(CHAT)
      if (!ast) return '拿不到模板 AST'
      const empties = []
      walkAst(ast, (n) => {
        if (n.type === 1 && nodeClasses(n).includes('session-empty')) empties.push(n)
      })
      if (empties.length !== 2) {
        return `模板里 .session-empty 有 ${empties.length} 个（应 2 个：一条会话都没有 / 搜索没命中）—— 合成一句就是拿同一句话对两种处境说谎`
      }
      const texts = empties.map((n) => nodeText(n).replace(/\s+/g, ' ').trim())
      const conds = empties.map((n) => {
        const chain = ifChainOf(ast, n)
        return chain.length ? chain[chain.length - 1] : ''
      })
      if (texts.some((t) => !t)) problems.push('有空态节点是空的（没有任何文案）')
      if (texts[0] === texts[1]) {
        problems.push(`两条空态的文案一模一样（都是「${texts[0]}」）—— 搜索没命中时会被告知「没有历史会话」`)
      }
      if (!conds[0]) problems.push('第一条空态拿不到 v-if 条件')
      else if (!/sessions\.length/.test(conds[0]) || /filteredSessions/.test(conds[0])) {
        problems.push(`第一条空态的 v-if 是「${conds[0]}」—— 「一条会话都没有」必须由**全部会话**（sessions）决定`)
      }
      if (!conds[1]) problems.push('第二条空态拿不到 v-if 条件')
      else if (!/filteredSessions/.test(conds[1])) {
        problems.push(`第二条空态的 v-if 是「${conds[1]}」—— 「搜索没命中」必须由**过滤后**的列表（filteredSessions）决定`)
      }
      if (conds[0] && conds[0] === conds[1]) {
        problems.push(`两条空态用的是同一个条件「${conds[0]}」—— 那两句文案永远只会出现一句`)
      }
      if (!/sessionKeyword/.test(texts[1])) {
        problems.push(
          `「搜索没命中」那句文案是「${texts[1]}」—— 它要把用户输入的词带出来，否则用户不知道该改什么`
        )
      }

      // 运行时再钉一下：有会话但没命中时，两个条件必须一真一假（第一句不许抢答）
      const rt = chatRuntime()
      if (!rt.ok) problems.push(`离线执行 ${CHAT} 的 script setup 失败：${rt.why}`)
      else {
        rt.api.sessions.value = [{ sessionId: 'a', title: '数据结构' }, { sessionId: 'b', title: '英语语法' }]
        rt.api.sessionKeyword.value = '不存在的词'
        if (rt.api.filteredSessions.value.length !== 0) {
          problems.push('没有命中时 filteredSessions 不为空 —— 过滤条件没生效')
        }
        if (rt.api.sessions.value.length !== 2) {
          problems.push('过滤把原数组改掉了 —— 两条空态的判据会跟着错')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L31',
    file: CHAT,
    label: '数量不骗人：搜索时同时给出「命中数 + 总数」，没搜索时不给「命中」框架',
    fn: () => {
      const rt = chatRuntime()
      if (!rt.ok) return `离线执行 ${CHAT} 的 script setup 失败：${rt.why}`
      const problems = []
      rt.api.sessions.value = [
        { sessionId: 'a', title: '数据结构错题整理' },
        { sessionId: 'b', title: '英语语法' },
        { sessionId: 'c', title: '操作系统' }
      ]
      const plain = (rt.api.sessionCountText.value || '').trim()
      if (!plain.includes('3')) {
        problems.push(`没搜索时的数量文案是「${plain}」—— 至少要给出总数 3`)
      }
      if (/命中/.test(plain)) {
        problems.push(`没搜索时的数量文案是「${plain}」—— 没有搜索就不该出现「命中」这种说法`)
      }
      rt.api.sessionKeyword.value = '数据结构'
      const hits = (rt.api.sessionCountText.value || '').trim()
      const nums = (hits.match(/\d+/g) || []).map((n) => Number(n))
      if (!nums.includes(1) || !nums.includes(3)) {
        problems.push(`搜索时的数量文案是「${hits}」—— 命中数 1 与总数 3 都要给：只给一个会被读成「会话就剩这些了」`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L32',
    file: CHAT,
    label: '浮层能关掉：点外面关、点里面不关，且触发按钮带 @mousedown.stop（否则按钮永远关不掉）',
    fn: () => {
      const problems = []
      const rt = chatRuntime()
      if (!rt.ok) return `离线执行 ${CHAT} 的 script setup 失败：${rt.why}`
      const inside = { id: 'inside' }
      const outside = { id: 'outside' }

      rt.api.sessionPopoverRef.value = { contains: (t) => t === inside }
      rt.api.historyOpen.value = true
      rt.api.onDocMousedown({ target: outside })
      if (rt.api.historyOpen.value !== false) problems.push('点浮层外面没有关掉 —— 浮层会一直挡着消息区')

      rt.api.historyOpen.value = true
      rt.api.onDocMousedown({ target: inside })
      if (rt.api.historyOpen.value !== true) {
        problems.push('点浮层里面也被关掉了 —— 选会话 / 输搜索词时浮层会在手底下消失')
      }

      // 浮层还没渲染（ref 是 null）时点了外面：不许崩，也不许把状态改乱
      rt.api.sessionPopoverRef.value = null
      rt.api.historyOpen.value = true
      try {
        rt.api.onDocMousedown({ target: outside })
      } catch (e) {
        problems.push(`浮层没渲染时点外面抛错了：${String(e?.message || e)}`)
      }
      if (rt.api.historyOpen.value !== true) {
        problems.push('浮层没渲染时点外面把它关掉了（ref 为 null 时不该改状态）')
      }

      // 按钮上的 `@mousedown.stop`：mousedown 会先冒泡到 document 的关闭处理，
      // 不拦住就是「mousedown 关掉、click 又打开」→ 按钮看起来永远关不掉。
      const ast = templateAst(CHAT)
      if (!ast) problems.push('拿不到模板 AST')
      else {
        const btn = firstNode(ast, (n) => n.type === 1 && String(n.tag) === 'button' && nodeClasses(n).includes('tb-btn'))
        if (!btn) problems.push('找不到底部工具栏的历史会话按钮（button.tb-btn）')
        else {
          const on = (btn.props || []).filter((p) => p.type === 7 && p.name === 'on')
          const click = on.find((p) => p.arg?.content === 'click')
          if (!click) problems.push('历史会话按钮没有 @click —— 浮层打不开')
          const mousedown = on.find((p) => p.arg?.content === 'mousedown')
          if (!mousedown) {
            problems.push('历史会话按钮缺 `@mousedown.stop` —— mousedown 会先被「点外面关闭」吃掉，紧接着 click 又打开，按钮点不着关')
          } else if (!(mousedown.modifiers || []).includes('stop')) {
            problems.push(`历史会话按钮的 @mousedown 修饰符是 ${JSON.stringify(mousedown.modifiers || [])}（要 stop）`)
          }
          if (!/historyOpen/.test(boundExp(btn, 'class') || '')) {
            problems.push('历史会话按钮的 :class 没绑 historyOpen —— 浮层打开时按钮的 is-on 态不会亮')
          }
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L33',
    file: POPOVER,
    label: '入口按钮**无条件**渲染（切 / 新建会话之后不许消失）',
    fn: () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'
      const problems = []

      // ⚠️ 这条守的是用户报的第 ③ 条：清单以前由 `meta` 事件填进 `:tools`，而
      //    `reset()`（切会话 / 新建会话）会把它清成 `[]`，模板上又写着
      //    `v-if="tools && tools.length"` ⇒ **入口按钮整个消失**。
      //    现在清单由组件自己拉，入口按钮必须常驻 —— 所以**任何**以工具列表为条件的
      //    `v-if` 都不许挂到弹层或按钮上（再挂回来，这条就会红）。
      const pop = firstNode(ast, (n) => n.type === 1 && String(n.tag) === 'el-popover')
      if (!pop) return '模板里找不到 el-popover（弹层没了）'
      const popCond = ifConditionOf(ast, pop)
      if (popCond) {
        problems.push(
          `el-popover 上还挂着 v-if「${popCond}」—— 入口按钮会跟着它一起被藏掉（用户报的第 ③ 条正是这个）`
        )
      }

      const btn = firstNode(
        ast,
        (n) => n.type === 1 && String(n.tag) === 'button' && nodeClasses(n).includes('tool-entry')
      )
      if (!btn) problems.push('模板里找不到入口按钮 button.tool-entry')
      else {
        const btnCond = ifConditionOf(ast, btn)
        if (btnCond) {
          problems.push(`入口按钮被包在 v-if「${btnCond}」里 —— 用户要求它「无论什么时候都要正常出现」`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L34',
    file: POPOVER,
    label: '三种状态分得开：加载中 / 没取到（带重试）/ 取到了但全被屏蔽；「没取到」不许写成「一个工具都没有」',
    fn: async () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'
      const problems = []
      const byClass = (c) => firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes(c))

      const loadingNode = byClass('atp-loading')
      const failed = byClass('atp-failed')
      const allOff = byClass('atp-all-off')
      if (!loadingNode) problems.push('找不到加载态节点（.atp-loading）—— 读清单这段时间界面是一片空白')
      if (!failed) problems.push('找不到「清单没取到」的节点（.atp-failed）—— 取不到就只能拿一句假话交代')
      if (!allOff) problems.push('找不到「清单在、但每条都被屏蔽」的节点（.atp-all-off）')

      // ① 失败态的判据必须是「加载已结束 + 清单为空」：少 `!loading` 会在加载期间先闪一下错误提示。
      if (failed) {
        const c = (ownConditionOf(ast, failed) || '').replace(/\s+/g, '')
        if (!/!loading/.test(c)) {
          problems.push(`「没取到」的 v-if 是「${c}」—— 条件里要有 \`!loading\`，否则加载期间就闪错误提示`)
        }
        if (!/!rows\.length/.test(c)) {
          problems.push(`「没取到」的 v-if 是「${c}」—— 必须由**空清单**（!rows.length）决定`)
        }
      }

      // ② 重试出口：失败态里必须有个真去重新取清单的控件
      const retry = byClass('atp-retry')
      if (!retry) problems.push('找不到「重试」控件（.atp-retry）—— 一次网络抖动之后用户只能刷新整页')
      else {
        let callsLoad = false
        for (const p of retry.props || []) {
          if (p.type === 7 && p.name === 'on' && p.arg?.content === 'click' && /\bload\s*\(/.test(expSource(p) || '')) {
            callsLoad = true
          }
        }
        if (!callsLoad) problems.push('「重试」控件的 @click 没有调 load() —— 点了不会重新取清单')
      }

      // ③ 两条文案必须分得开，而且都不许把「零条」说成「没有工具」
      const failedText = failed ? nodeText(failed).replace(/\s+/g, '') : ''
      const allOffText = allOff ? nodeText(allOff).replace(/\s+/g, '') : ''
      if (failedText && allOffText && failedText === allOffText) {
        problems.push('失败态与「全部被屏蔽」共用一句话 —— 两种处境被说成了同一件事')
      }
      // ⚠️ 这里**不能**写成「文案里不许出现『一个工具都没有』」那种子串判据：
      //    它分不清**主张**与**引述并否认** —— 诚实的那句正是
      //    「取不到是这次请求失败了，**不是**『一个工具都没有』」，一刀切的子串检查会把
      //    **写对的那句**判红（本断言的第一版就是这么错的，实测踩到，已改成下面的正向要求）。
      //    判据落成**正向要求**：失败态必须明说「没取到 / 请求失败」——
      //    改成一句「一个工具都没有」的假话，这里就找不到那个字，照样会红。
      if (failedText && !/没取到|取不到|请求失败|加载失败/.test(failedText)) {
        problems.push(
          `「没取到」那条的文案是「${failedText}」—— 它必须说明是**这次没取到**（` +
            '只说「一个工具都没有」是假话：后端注册表不可能为空，零条 = 这次请求失败了）'
        )
      }
      if (allOffText && !/屏蔽/.test(allOffText)) {
        problems.push(`「每条都被屏蔽」那条的文案是「${allOffText}」—— 它要说清这是用户自己关的（与请求失败是两件事）`)
      }

      // ④ 徽标只在清单**加载完成**时出数字（加载中 / 取不到时给 null → 不渲染）
      const badge = byClass('tool-entry-count')
      if (!badge) problems.push('找不到入口徽标 .tool-entry-count')
      else {
        const c = ownConditionOf(ast, badge)
        if (!c || !/badgeCount/.test(c)) {
          problems.push(
            `徽标的 v-if 是「${c || '(没有 v-if)'}」—— 必须由 badgeCount 控制：` +
              '加载中 / 取不到时出的那个 `0` 会被读成「我一个工具都没有」'
          )
        }
      }

      // ⑤ 四个状态各跑一遍（离线真实执行）：徽标只在该出数字的时候出
      const loadingRt = toolPopoverRuntime({ payload: { tools: [] } })
      if (!loadingRt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${loadingRt.why}`
      if (loadingRt.api.loading.value !== true) {
        problems.push('组件刚创建时 loading 不是 true —— 第一帧会画出「没取到」')
      }
      if (loadingRt.api.badgeCount.value !== null) {
        problems.push(`清单还没回来时徽标是 ${JSON.stringify(loadingRt.api.badgeCount.value)}（应 null → 不渲染）`)
      }
      await loadingRt.runMount()
      if (loadingRt.api.loading.value !== false) problems.push('取完清单之后 loading 没落回 false')
      if (loadingRt.api.rows.value.length !== 0) problems.push('预置错误：空清单应当是 rows 为空')
      if (loadingRt.api.badgeCount.value !== null) {
        problems.push(
          `清单**没取到**时徽标是 ${JSON.stringify(loadingRt.api.badgeCount.value)}（应 null；` +
            '这里给 0，按钮上就挂着一个「我没有工具」的假数字）'
        )
      }

      // 请求抛异常：同样落到「没取到」，不能崩、也不能给 0
      const throwRt = toolPopoverRuntime({ fetchThrows: true })
      if (!throwRt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${throwRt.why}`
      const tm = await throwRt.runMount()
      if (!tm.ok) return tm.why
      if (throwRt.api.loading.value !== false || throwRt.api.rows.value.length !== 0) {
        problems.push('取清单抛异常时没有落到「空清单 + 加载结束」的状态（弹层会一直转圈）')
      }
      if (throwRt.api.badgeCount.value !== null) {
        problems.push(`取清单抛异常时徽标是 ${JSON.stringify(throwRt.api.badgeCount.value)}（应 null）`)
      }

      // 全被屏蔽：清单**在**（每条都列出来），徽标 0 是**真话**
      const offRt = toolPopoverRuntime({
        payload: { tools: [agentTool('bank_manage', 1), agentTool('question_manage', 1)] }
      })
      if (!offRt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${offRt.why}`
      await offRt.runMount()
      if (offRt.api.rows.value.length !== 2) {
        problems.push(`全部被屏蔽时清单里只剩 ${offRt.api.rows.value.length} 条（应 2 条 —— 整份清单照常列出）`)
      }
      if (offRt.api.enabledCount.value !== 0 || offRt.api.badgeCount.value !== 0) {
        problems.push(
          `全部被屏蔽时 enabledCount=${offRt.api.enabledCount.value}、徽标=${JSON.stringify(offRt.api.badgeCount.value)}（应都是 0）`
        )
      }

      // 正常：3 条里 2 条可用 → 徽标 2
      const okRt = toolPopoverRuntime({
        payload: { tools: [agentTool('bank_manage', 0), agentTool('question_manage'), agentTool('memory_search', 1)] }
      })
      if (!okRt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${okRt.why}`
      await okRt.runMount()
      if (okRt.api.badgeCount.value !== 2) {
        problems.push(`3 条里 2 条可用时徽标是 ${JSON.stringify(okRt.api.badgeCount.value)}（应 2 —— 徽标数的是**可用**的个数）`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L35',
    file: POPOVER,
    label: '屏蔽开关是受控式：绑定值恒为布尔（无 active-value/inactive-value、不裸绑 t.disabled）',
    fn: () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'
      const problems = []
      /**
       * 模板里现在有**两个** el-switch（逐行开关 + 「全选」），按 `@update:model-value`
       * 的处理器把它们分开 —— 那是它们唯一的语义差别。
       * ⚠️ **不要**用 `firstNode` 取「第一个 el-switch」：靠顺序选，下次有人在工具条上
       *    再加一个开关，这条断言就会**悄悄改测对象**（它当初正是这么被「全选」撞红的）。
       */
      const switches = []
      walkAst(ast, (n) => {
        if (n.type === 1 && String(n.tag) === 'el-switch') switches.push(n)
      })
      const handlerOf = (node) => {
        const upd = (node.props || []).find(
          (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'update:model-value'
        )
        return { upd, src: String(expSource(upd) || '') }
      }
      const rowSwitches = switches.filter((s) => /toggleTool\(/.test(handlerOf(s).src))
      const bulkSwitches = switches.filter((s) => /toggleAll\(/.test(handlerOf(s).src))
      const unclassified = switches.filter(
        (s) => !rowSwitches.includes(s) && !bulkSwitches.includes(s)
      )
      const sw = rowSwitches[0]
      if (!sw) return '模板里没有走 toggleTool 的逐行开关 —— 用户只能看工具，不能屏蔽工具（用户报的第 ① 条）'

      const mv = boundExp(sw, 'model-value')
      if (!mv) problems.push('逐行开关没有 :model-value 绑定 —— 开关没有显示值')
      else {
        if (/^t\.disabled$/.test(mv.replace(/\s+/g, ''))) {
          problems.push(
            `逐行开关的 :model-value 裸绑了 \`${mv}\`（后端的 0|1 整数）—— 它不在 el-switch 的取值域里，` +
              '挂载期会**无用户操作地** emit 一次 ⇒ 打开一次清单就对每一行各发一次 PUT'
          )
        }
        if (!/toolEnabled\(/.test(mv)) {
          problems.push(`逐行开关的 :model-value 是「${mv}」—— 显示值必须来自唯一的判据函数 toolEnabled（别在模板里另写一份判据）`)
        }
      }

      // 「全选」是本次新增的**第二个** el-switch，同一条取值域规则照样适用
      if (!bulkSwitches.length) {
        problems.push('找不到走 toggleAll 的「全选」开关 —— 用户没法一键改全部')
      }
      for (const bs of bulkSwitches) {
        const raw = boundExp(bs, 'model-value')
        const norm = String(raw || '').replace(/\s+/g, '')
        if (!raw) {
          problems.push('「全选」开关没有 :model-value —— 它的显示值必须由服务端数据推导（不许本地翻转）')
        } else if (norm !== 'allEnabled') {
          problems.push(
            `「全选」开关的 :model-value 是「${raw}」—— 判据只认 \`allEnabled\`：它恒为**布尔**，` +
              '天然落在 el-switch 的默认取值域里；换成别的表达式就得重新论证它恒为布尔，' +
              '否则挂载期那次 emit 会回来（打开一次弹层就把全部工具写一遍）'
          )
        }
      }
      if (unclassified.length) {
        problems.push(
          `有 ${unclassified.length} 个 el-switch 的 @update:model-value 既不走 toggleTool 也不走 toggleAll` +
            `（「${handlerOf(unclassified[0]).src || '(根本没有 @update:model-value)'}」）—— ` +
            '新加的开关必须落进这两类之一，否则「受控式」这条就漏了一个口子'
        )
      }
      for (const node of switches) {
        if (boundExp(node, 'active-value') || boundExp(node, 'inactive-value')) {
          problems.push(
            'el-switch 上出现了 :active-value / :inactive-value —— 那把取值域改成了 0|1，' +
              '而 0|1 恰好是**渲染值**的形态，挂载期那次 emit 就再也躲不掉了（本组件刻意不用）'
          )
          break
        }
      }
      const upd = (sw.props || []).find(
        (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'update:model-value'
      )
      if (!upd) problems.push('el-switch 没有 @update:model-value —— 拨了开关不会写回服务端')
      else if (!/toggleTool\(/.test(expSource(upd) || '')) {
        problems.push(`@update:model-value 是「${expSource(upd)}」—— 它必须走 toggleTool（那里才有受控式的那套判定）`)
      }

      // 取值域：`toolEnabled` 在 undefined / 0 / 1 上都必须返回**布尔**，而且判据只能是 `!== 1`
      const rt = toolPopoverRuntime({})
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      if (typeof rt.api.toolEnabled !== 'function') {
        return '组件里找不到 toolEnabled —— 开关的显示判据没有单一出处（判据散在模板里就没人能测它）'
      }
      const domain = [
        [undefined, true, '缺省 = 启用（默认全部工具开启，后端还没下发这一列时不能画成已屏蔽）'],
        [0, true, '0 = 启用'],
        [1, false, '1 = 屏蔽']
      ]
      for (const [d, expect, why] of domain) {
        const v = rt.api.toolEnabled({ name: 'x', disabled: d })
        if (typeof v !== 'boolean') {
          problems.push(`toolEnabled({ disabled: ${JSON.stringify(d)} }) 返回 ${JSON.stringify(v)}（${typeof v}）—— 必须是布尔，否则 el-switch 挂载期会 emit`)
        } else if (v !== expect) {
          problems.push(`toolEnabled({ disabled: ${JSON.stringify(d)} }) 是 ${v}（应 ${expect}：${why}）`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L36',
    file: POPOVER,
    label: '拨开关发出的载荷：saveAgentToolPref(被拨那一行的工具名, 整数 0|1)',
    fn: async () => {
      const base = [agentTool('bank_manage', 0), agentTool('question_manage', 1)]
      const srv = toolsServer(base)
      const rt = toolPopoverRuntime({ payload: srv.payload, save: srv.save })
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      const m = await rt.runMount()
      if (!m.ok) return m.why
      const problems = []

      // ① 拨到「已屏蔽」：参数必须是 **被拨那一行的名字** + **整数 1**
      //    这是唯一能在不开浏览器、不连后端的情况下抓住「字段名 / 类型前后端不一致」的机械判据：
      //    静态检查不做类型检查（`ts.transpileModule` 只擦类型），传布尔 / 字符串都能「编译通过」。
      const row = rt.api.rows.value.find((r) => r.name === 'bank_manage')
      if (!row) return '预置错误：清单里找不到 bank_manage'
      await rt.api.toggleTool(row, false)
      const c1 = rt.calls.saveAgentToolPref[0]
      if (!c1) problems.push('拨开关没有调 saveAgentToolPref —— 界面看起来改了，服务端什么都不知道')
      else {
        if (c1[0] !== 'bank_manage') {
          problems.push(`第一个参数是 ${JSON.stringify(c1[0])}（应是被拨那一行的工具名 bank_manage）`)
        }
        if (c1[1] !== 1) problems.push(`拨到「已屏蔽」时第二个参数是 ${JSON.stringify(c1[1])}（应整数 1）`)
        if (typeof c1[1] !== 'number') {
          problems.push(`第二个参数的类型是 ${typeof c1[1]}（必须是 number —— 传布尔/字符串后端读到的不是 0|1）`)
        }
      }

      // ② 拨回「可用」：整数 0
      const row2 = rt.api.rows.value.find((r) => r.name === 'question_manage')
      if (!row2) problems.push('预置错误：清单里找不到 question_manage（被屏蔽的那条被筛掉了？）')
      else {
        await rt.api.toggleTool(row2, true)
        const c2 = rt.calls.saveAgentToolPref[1]
        if (!c2) problems.push('把被屏蔽的行拨回「可用」时没有调 saveAgentToolPref')
        else {
          if (c2[0] !== 'question_manage') {
            problems.push(`第二个参数那次的工具名是 ${JSON.stringify(c2[0])}（应是 question_manage）`)
          }
          if (c2[1] !== 0 || typeof c2[1] !== 'number') {
            problems.push(`拨回「可用」时第二个参数是 ${JSON.stringify(c2[1])}（应整数 0）`)
          }
        }
      }

      // ③ 反面对照：开关报的就是它当前的状态 → 一次写都不许发
      //    （挡的是重复点击，以及「上一次 PUT 还在飞、用户又点一下」）
      // ⚠️ 这一行必须挑**状态已经被改过**的那一行：① 之后 bank_manage 是 `disabled: 1`，
      //    所以「再拨到已屏蔽」才是真正的 no-op。（第一版挑的是刚被打开的那一行，
      //    它当前是可用 → 拨到已屏蔽是**真改动**，那次的红是断言写错了，不是实现有问题。）
      const before = rt.calls.saveAgentToolPref.length
      const noopRow = rt.api.rows.value.find((r) => r.name === 'bank_manage')
      if (!noopRow || noopRow.disabled !== 1) {
        problems.push(`预置错误：bank_manage 现在应是 disabled:1，实际是 ${JSON.stringify(noopRow?.disabled)}`)
      } else {
        await rt.api.toggleTool(noopRow, false) // 已经是「已屏蔽」，又要「已屏蔽」
        if (rt.calls.saveAgentToolPref.length !== before) {
          problems.push('开关报的正是它当前的状态时也发了写请求 —— 重复点击没有被挡住')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L37',
    file: POPOVER,
    label: '假成功（ok:false）不许翻开关：显示值保持不变、把服务端给的 reason 说出来；真成功才翻',
    fn: async () => {
      const base = [agentTool('bank_manage', 0)]
      const problems = []

      // ① 服务端回 `ok: false`（假 200 / 回显没变）：**不翻开关**，如实报原因。
      //    这一格就是「后端 catch-all 把路由/字段名问题变成 200 假成功」时的防线 ——
      //    乐观式会让 UI 显示「已屏蔽」，而模型下一次照样拿到这个工具。
      const fake = toolPopoverRuntime({
        payload: { tools: base },
        save: () => ({ ok: false, payload: null, reason: 'bank_manage 的开关没变（服务端仍是 0）' })
      })
      if (!fake.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${fake.why}`
      const fm = await fake.runMount()
      if (!fm.ok) return fm.why
      const fRow = fake.api.rows.value[0]
      if (fake.api.toolEnabled(fRow) !== true) return '预置错误：这一行本来是「可用」'
      await fake.api.toggleTool(fRow, false)
      if (fake.api.toolEnabled(fake.api.rows.value[0]) !== true) {
        problems.push('服务端回 ok:false 之后开关仍被本地翻成了「已屏蔽」—— UI 在骗用户，模型下一次照样拿到这个工具')
      }
      if (fake.api.rows.value[0].disabled !== 0) {
        problems.push(`ok:false 之后本地的 disabled 被改成了 ${JSON.stringify(fake.api.rows.value[0].disabled)}（应保持 0）`)
      }
      if (!fake.msgs.error.length) {
        problems.push('ok:false 之后没有 ElMessage.error —— 用户不知道没保存上（开关看着还弹回去了，只会更迷糊）')
      } else if (!fake.msgs.error.some((m) => m.includes('开关没变'))) {
        problems.push(`错误提示里没有服务端给的原因（实际提示：${JSON.stringify(fake.msgs.error)}）`)
      }
      if (fake.api.togglingName.value) {
        problems.push(`ok:false 之后 togglingName 没清掉（还是 ${JSON.stringify(fake.api.togglingName.value)}）—— 所有开关会一直锁着`)
      }

      // ② 写请求抛异常：同样不许留下本地改动
      const threw = toolPopoverRuntime({ payload: { tools: base }, saveThrows: true })
      if (!threw.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${threw.why}`
      await threw.runMount()
      const tRow = threw.api.rows.value[0]
      await threw.api.toggleTool(tRow, false)
      if (threw.api.toolEnabled(threw.api.rows.value[0]) !== true) {
        problems.push('写请求抛异常之后开关没有保持原位')
      }
      if (!threw.msgs.error.length) problems.push('写请求抛异常之后没有 ElMessage.error')
      if (threw.api.togglingName.value) problems.push('写请求抛异常之后 togglingName 没清掉 —— 开关会一直锁着')

      // ③ **反面对照**：服务端确认（ok:true）时开关必须真的翻过去 ——
      //    没有这一条，把 toggleTool 整个改成空函数也能让 ①② 全绿（「什么都不做」不是受控式）。
      const srv = toolsServer(base)
      const good = toolPopoverRuntime({ payload: srv.payload, save: srv.save })
      if (!good.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${good.why}`
      await good.runMount()
      await good.api.toggleTool(good.api.rows.value[0], false)
      if (good.api.toolEnabled(good.api.rows.value[0]) !== false) {
        problems.push('服务端确认（ok:true）之后开关却没翻过去 —— 显示值没跟着服务端回传的清单走')
      }
      if (!good.msgs.success.length) problems.push('保存成功之后没有成功提示')
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L38',
    file: POPOVER,
    label: '被屏蔽的工具仍留在清单里（v-for 不筛掉它）且能再被打开 + 行上有常驻「已屏蔽」标记',
    fn: async () => {
      const problems = []
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'

      // ① 结构：清单的 v-for 必须遍历**整份**清单
      const forNode = firstNode(ast, (n) => n.type === 11)
      if (!forNode) problems.push('清单里找不到 v-for')
      else {
        const src = String(forNode.source?.loc?.source ?? '').replace(/\s+/g, '')
        if (/(filter|slice|splice)/.test(src)) {
          problems.push(
            `清单 v-for 的源是「${src}」—— 它把被屏蔽的条目筛掉了：` +
              '用户关掉一个工具之后就再也找不到那个开关、没法把它打开（知识库「屏蔽」那次踩过同一个坑）'
          )
        }
      }
      // ② 结构：行上要有**常驻**的「已屏蔽」标记，且只由 `disabled === 1` 决定
      const mark = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes('atp-item-blocked'))
      if (!mark) {
        problems.push('找不到常驻的「已屏蔽」标记（.atp-item-blocked）—— 用户没法一眼看出哪些工具被屏蔽')
      } else {
        // ⚠️ 必须用 `ownConditionOf`（直接包住它的那条 v-if）：外面还套着清单那句
        //    `v-if="!loading && rows.length"`，用 `ifConditionOf` 读回来的是**清单的条件**，
        //    于是这句会红、而产品代码本来是对的。
        const cond = (ownConditionOf(ast, mark) || '').replace(/\s+/g, '')
        if (cond !== 't.disabled===1') {
          problems.push(`「已屏蔽」标记的 v-if 是「${cond || '(没有 v-if)'}」—— 必须**只**由 \`t.disabled === 1\` 决定`)
        }
      }

      // ③ 运行时：全量清单（含 1 条被屏蔽）进来，两条都要在
      const base = [agentTool('bank_manage', 0), agentTool('question_manage', 1)]
      const srv = toolsServer(base)
      const rt = toolPopoverRuntime({ payload: srv.payload, save: srv.save })
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      const m = await rt.runMount()
      if (!m.ok) return m.why
      if (rt.api.rows.value.length !== 2) {
        problems.push(
          `后端下发 2 条（含 1 条 disabled:1），界面上只剩 ${rt.api.rows.value.length} 条 —— ` +
            '被屏蔽的条目被筛掉了，那个开关再也点不到'
        )
      }
      const off = rt.api.rows.value.find((r) => r.name === 'question_manage')
      if (!off) problems.push('被屏蔽的 question_manage 不在清单里')
      else if (rt.api.toolEnabled(off) !== false) problems.push('被屏蔽的条目显示成了「可用」')

      // ④ 能再被打开：拨回「可用」→ 发 disabled:0，显示值跟着服务端回值翻回去
      if (off) {
        await rt.api.toggleTool(off, true)
        const back = rt.api.rows.value.find((r) => r.name === 'question_manage')
        if (rt.calls.saveAgentToolPref[0]?.[1] !== 0) {
          problems.push(`把被屏蔽的工具拨回来时发的 disabled 是 ${JSON.stringify(rt.calls.saveAgentToolPref[0]?.[1])}（应整数 0）`)
        }
        if (rt.api.toolEnabled(back) !== true) {
          problems.push('被屏蔽的工具拨回来之后仍然显示「已屏蔽」—— 用户没法把它恢复')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L39',
    file: POPOVER,
    label: '清单在**挂载期**就取回来（恰好一次）：不是点开才取，也不是每次点击都取',
    fn: async () => {
      const problems = []
      const rt = toolPopoverRuntime({ payload: { tools: [agentTool('bank_manage', 0)] } })
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      if (!rt.mountedCount) {
        return '组件没有注册 onMounted —— 清单要等用户点开弹层才请求，点开时会先看到一个转圈（用户点开是要立刻看到清单）'
      }
      if (rt.calls.fetchAgentToolsForUi !== 0) {
        problems.push('组件还没挂载就发了取清单的请求')
      }
      const m = await rt.runMount()
      if (!m.ok) return m.why
      if (rt.calls.fetchAgentToolsForUi !== 1) {
        problems.push(`挂载期取了 ${rt.calls.fetchAgentToolsForUi} 次清单（应恰好 1 次 —— 一次点击一个 GET 是白烧请求）`)
      }

      // 「重试」再取一次（唯一的第二个出口）
      await rt.api.load()
      if (rt.calls.fetchAgentToolsForUi !== 2) {
        problems.push(`重试之后再取清单的次数是 ${rt.calls.fetchAgentToolsForUi}（应 2）`)
      }

      // 结构上：模板里会去取清单的地方**只有**失败态那个重试控件
      //（再挂一个 @click 到入口按钮上，就变成「每次点开都拉一次」）
      const ast = templateAst(POPOVER)
      if (!ast) problems.push('拿不到模板 AST')
      else {
        let loadClicks = 0
        walkAst(ast, (n) => {
          for (const p of n.props || []) {
            if (p.type === 7 && p.name === 'on' && p.arg?.content === 'click' && /\bload\s*\(/.test(expSource(p) || '')) {
              loadClicks += 1
            }
          }
        })
        if (loadClicks !== 1) {
          problems.push(
            `模板里点一下就会去取清单的地方有 ${loadClicks} 处（应 1 处：失败态的重试控件）—— ` +
              '把入口按钮也接上去，就等于「每次点开都拉一次」'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L40',
    file: POPOVER,
    label: '组件依赖的**两个具名导出**与实现对账（fetchAgentToolsForUi / saveAgentToolPref 真的 export 了）',
    fn: () => {
      const src = readSource(POPOVER)
      const impl = readSource(API_DSFREE)
      if (!impl) return `读不到 ${API_DSFREE}（组件读写工具清单的实现文件）`
      const problems = []

      // 为什么要有这条：文件级检查只核 **import 路径存不存在**，**不核具名导出**。
      // 组件现在靠 `fetchAgentToolsForUi()` / `saveAgentToolPref()` 两个**具名导出**工作，
      // 那边一旦改名（或换成默认导出），这边要等到**运行期**才炸 —— 而且症状极具迷惑性：
      // 弹层永远是「清单没取到」，开关点了没反应，看起来像后端挂了。
      // 这正是「import 路径对、名字不对」那一类错，静态检查的既有覆盖面里恰好吃不到。
      //
      // ⚠️⚠️ 这条判据是**源码文本**层面的（`readSource` + 正则），**刻意不去 import 模块再取属性**：
      //    `agentDsFree.ts` 的 `SaveAgentToolPrefResult` / `AgentContextBundle` 与 `agent.ts` 的
      //    `AgentToolDefinition` / `AgentToolsPayload` 都是 `interface` —— **编译后运行时不存在**。
      //    若改成「解析模块再查属性」，往名单里加任何一个**类型**导出都会**必然假红**
      //    （看起来像「导出被改名」，其实是类型被抹掉了）。要加只加**值导出**（函数 / const）。
      //    （`API_DSFREE` 的值导出名单由 tool-gate-fe-api 维护，其 2026-09-21 口径：
      //      `resetAgentToolsCache` / `fetchAgentTools` / `fetchAgentToolsForUi` / `saveAgentToolPref` /
      //      `fetchAgentContext` / `resetHistoryInjection` / `runDsFreeAgentStream`。）
      const need = [
        ['fetchAgentToolsForUi', '读全量清单（入口按钮的清单与徽标都靠它）'],
        ['saveAgentToolPref', '写回某个工具的开 / 关（逐行开关的唯一出口）'],
        ['saveAllToolPrefs', '写回**全部**工具的开 / 关（工具条上「全选」的唯一出口）']
      ]
      for (const [name, why] of need) {
        if (!new RegExp(`\\b${name}\\s*\\(`).test(src)) {
          problems.push(`组件里没有调用 ${name}() —— ${why}：这条链路的口径变了？`)
        }
        const exported = new RegExp(
          `export\\s+(?:async\\s+)?function\\s+${name}\\b|export\\s+const\\s+${name}\\b|export\\s*\\{[^}]*\\b${name}\\b`
        ).test(impl)
        if (!exported) {
          problems.push(
            `${API_DSFREE} 里没有具名导出 ${name} —— 组件调的是一个**不存在的名字**：` +
              '静态检查只核 import 路径、不核具名导出，所以这错要等运行期才炸（表现为「清单永远没取到」）'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L41',
    file: POPOVER,
    label:
      '脚注整块已删（守门：不许加回来）—— 组件源码里不存在 atp-foot / 本次运行下发 / runModel / showRunToolCount；用户点名保留的 headSub 那一行仍在',
    fn: () => {
      // 用户裁决原话：「保留 可用工具 3/5 个可用 · 由后端按当前配置下发 这一行 即可；
      // 下面的 本次运行下发 x 个工具（那一次运行后端实际给了这些；上面那份是当前配置）这段话去除」，
      // 追问后明确「本次运行模型：xxx」那一行也一起去掉 —— **整个脚注块删掉，两行都不要**。
      //
      // 这条断言的作用是**防复活**：一块 UI 被删掉之后，唯一还能"回来"的方式就是有人又写回去。
      // ⚠️ 删除类断言必须断**源码文本层面不存在该标识**，**不要**写成「模板里找不到某个节点」——
      //    找不到的真正原因可能只是选择器 / AST 遍历写错了，那会让断言**恒真**（什么也不防）。
      //    这里就是一行 `includes`：写回去必然红。
      // ⚠️ 先用 `codeText` 剥掉注释再查：删除之后旁边留的说明文字里**必然会写到被删掉的名字**
      //    （本组件里就有一句），不剥的话断言会被**自己的注释**判红（`cssOf` 的注释记着这条踩过）。
      const code = codeText(POPOVER)
      const gone = ['atp-foot', '本次运行下发', 'runModel', 'showRunToolCount']
      const back = gone.filter((k) => code.includes(k))
      if (back.length) {
        return (
          '脚注已被用户裁决**整块删除**（「本次运行模型」+「本次运行下发 N 个工具」两行），' +
          `但组件源码里又出现了 ${back.map((k) => '`' + k + '`').join('、')} —— 别加回来`
        )
      }

      // 反面：用户点名**保留**的那一行得还在（`.atp-head > .atp-sub` 里的 `headSub`）。
      // ⚠️ 没有这条，「保留这一行」那半句裁决就**没有任何机器防线** —— 把它删掉会全绿。
      //    只钉**那一行的表达式**（口径 = 可用数 / 全量数 + 那句说明），不钉样式：观感归用户。
      const sub = code.match(/const headSub = computed\(\(\) => \{[\s\S]*?\n\}\)/)
      if (!sub) {
        return '找不到 `headSub` computed —— 用户点名要保留的那行「N/M 个可用 · 由后端按当前配置下发」就靠它'
      }
      if (!sub[0].includes('个可用 · 由后端按当前配置下发')) {
        return '`headSub` 里「…个可用 · 由后端按当前配置下发」这句话变了 —— 用户裁决保留的就是这一行（改文案要连裁决一起改）'
      }
      if (!/\$\{enabledCount\.value\}\/\$\{rows\.value\.length\}/.test(sub[0])) {
        return (
          '`headSub` 的条数不再是「可用数 / 全量数」（`enabledCount.value` / `rows.value.length`）—— ' +
          '保留的那行要的就是这个口径，别换成「本次运行」那种快照的数'
        )
      }
      return null
    }
  },
  {
    id: 'L42',
    file: POPOVER,
    label: '挂载期零写入：没有任何用户操作时，每一行的开关都不许发出写请求（el-switch 挂载期 emit 的机械防线）',
    fn: async () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'
      // ⚠️ 模板里有两个 el-switch（逐行 + 「全选」）。这里要的是**逐行**那个 ——
      //    按 `@update:model-value` 走 toggleTool 认，不要用 `firstNode` 取「第一个」
      //    （「全选」在工具条里、排在前面，靠顺序取会取错对象）。
      const allSwitches = []
      walkAst(ast, (n) => {
        if (n.type === 1 && String(n.tag) === 'el-switch') allSwitches.push(n)
      })
      const updSrc = (node) =>
        String(
          expSource(
            (node.props || []).find(
              (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'update:model-value'
            )
          ) || ''
        )
      const sw = allSwitches.find((s) => /toggleTool\(/.test(updSrc(s)))
      if (!sw) return '模板里没有走 toggleTool 的逐行开关（那这条就没得测）'
      const bulkSw = allSwitches.find((s) => /toggleAll\(/.test(updSrc(s)))
      const mv = boundExp(sw, 'model-value')
      if (!mv) return 'el-switch 没有 :model-value 绑定 —— 求不出挂载期那个值'
      const forNode = firstNode(ast, (n) => n.type === 11)
      const alias = String(forNode?.valueAlias?.loc?.source || 't')

      const base = [agentTool('bank_manage', 0), agentTool('question_manage', 1), agentTool('memory_search', 0)]
      const srv = toolsServer(base)
      const rt = toolPopoverRuntime({ payload: srv.payload, save: srv.save })
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      const m = await rt.runMount()
      if (!m.ok) return m.why
      if (rt.api.rows.value.length !== 3) return `预置错误：清单应有 3 条，实际 ${rt.api.rows.value.length} 条`
      const problems = []

      // ① 组件自己「光挂载」写了没有（**两个写口分别数**：逐行 + 批量）
      if (rt.calls.saveAgentToolPref.length !== 0) {
        problems.push(
          `挂载期就发了 ${rt.calls.saveAgentToolPref.length} 次**逐行**写请求（应 0）：` +
            JSON.stringify(rt.calls.saveAgentToolPref)
        )
      }
      if (rt.calls.saveAllToolPrefs.length !== 0) {
        problems.push(
          `挂载期就发了 ${rt.calls.saveAllToolPrefs.length} 次**批量**写请求（应 0）：` +
            JSON.stringify(rt.calls.saveAllToolPrefs)
        )
      }

      // ② 把 el-switch **挂载期那次 emit** 也补进模型：离线 harness 不渲染模板，
      //    所以那一格得按真实源码手工补（见 `elSwitchMountEmit` 的注释，逐行对着源码）。
      //    emit 出来的值会走 `@update:model-value` → `toggleTool`，与用户拨一下**同一条路**。
      let emitCount = 0
      for (const row of rt.api.rows.value) {
        let v
        try {
          v = new Function(alias, 'toolEnabled', 'rows', 'enabledCount', `return ( ${mv} )`)(
            row,
            rt.api.toolEnabled,
            rt.api.rows.value,
            rt.api.enabledCount.value
          )
        } catch (e) {
          return `求值 :model-value（\`${mv}\`）失败：${String(e?.message || e)} —— 这一条**没跑成**，按未验证算，不要当成通过`
        }
        const emitted = elSwitchMountEmit(v)
        if (emitted === null) continue
        emitCount += 1
        await rt.api.toggleTool(row, emitted)
      }
      if (emitCount !== 0) {
        problems.push(
          `:model-value（\`${mv}\`）有 ${emitCount} 行的值不在 el-switch 的取值域 [true,false] 里 —— ` +
            '挂载期每行各 emit 一次（值恒为 inactiveValue=false），用户什么都没拨就会写服务端'
        )
      }
      if (rt.calls.saveAgentToolPref.length !== 0) {
        problems.push(
          `算上 el-switch 挂载期那次 emit，一次页面加载共发了 ${rt.calls.saveAgentToolPref.length} 次写请求（应 0）：` +
            JSON.stringify(rt.calls.saveAgentToolPref)
        )
      }

      // ③ 「全选」那个开关也一样要过这一关：它的显示值必须**恒为布尔**，
      //    否则挂载期 emit 的坑会在它身上重演 —— 而且后果更重：一次弹层打开就把**全部**工具写一遍。
      //    （取值域本身由 L64 枚举；这里只确认「挂载那一刻它落在 [true,false] 里」。）
      if (bulkSw) {
        const bmv = boundExp(bulkSw, 'model-value')
        const bnorm = String(bmv || '').replace(/\s+/g, '')
        if (bnorm && bnorm !== 'allEnabled') {
          problems.push(
            `「全选」开关的 :model-value 是「${bmv}」—— 这条只在它绑 \`allEnabled\` 时才求得出布尔值，` +
              '换成别的表达式必须重新论证「挂载期它一定落在 [true,false] 里」'
          )
        } else if (bnorm) {
          let bv
          try {
            bv = new Function('allEnabled', `return ( ${bmv} )`)(rt.api.allEnabled.value)
          } catch (e) {
            return `求值「全选」的 :model-value（\`${bmv}\`）失败：${String(e?.message || e)} —— 这一条**没跑成**，按未验证算，不要当成通过`
          }
          if (elSwitchMountEmit(bv) !== null) {
            problems.push(
              `「全选」开关的值（\`${bmv}\`）是 ${JSON.stringify(bv)}，不在 el-switch 的取值域 [true,false] 里 —— ` +
                '挂载期它会 emit 一次（值恒为 inactiveValue），打开一次弹层就把**全部**工具写一遍'
            )
          }
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L43',
    file: CHAT,
    label:
      '传给 <AgentToolPopover> 的只有 `:model`（守门：脚注那两个 prop `:run-model` / `:tools` 不许加回来）',
    fn: () => {
      // 用户裁决原话：「保留 可用工具 3/5 个可用 · 由后端按当前配置下发 这一行 即可；
      // 下面的 本次运行下发 x 个工具（那一次运行后端实际给了这些；上面那份是当前配置）这段话去除」——
      // 整块脚注删掉之后，`chat.vue` 这边**一个 prop 都不该留**：脚注那两行就是靠 `:run-model` /
      // `:tools` 传进组件的，而组件里**已经没有**这两个 prop 了（L41 守着组件那侧），
      // 留着就是「传了但没人接」的死绑定 —— 还会让下一个读代码的人以为脚注还在。
      //
      // ⚠️ 判据落在这个**标签自己的属性表**上（源码文本层面把 `<AgentToolPopover …>` 抠出来），
      //    **不是**「模板里找不到某个节点」：后者选择器 / AST 写错就**恒真**，什么也不防。
      // ⚠️ 也**不能**全文 `includes(':run-model')`：旁边那句「`:tools` / `:run-model` 曾为脚注而传」
      //    的说明注释里**必然**写着这两个名字，全文匹配会被**自己的注释**判红。
      const src = readSource(CHAT)
      const tag = src.match(/<AgentToolPopover\b[\s\S]*?>/)
      if (!tag) {
        return '找不到 <AgentToolPopover …> 标签 —— 这条断言**没生效**（按未验证算，不要当成通过）'
      }
      // 先把属性**值**清空再数属性名：否则 `:model="model || activeModel"` 里那个
      // `activeModel`（前面有空格）会被当成一个属性名。
      const stripped = tag[0].replace(/"[^"]*"/g, '""').replace(/'[^']*'/g, "''")
      const tokens = [...stripped.matchAll(/\s(:|v-bind:|@|v-on:)?([A-Za-z][\w-]*)(?=[\s=/>])/g)]
      const boundProps = tokens.filter((m) => m[1] === ':' || m[1] === 'v-bind:').map((m) => m[2])
      const allAttrs = tokens.map((m) => m[2])

      // ① 守门：脚注那两个 prop 不许加回来（组件那边已经不存在，加回来必然是死绑定）
      const back = allAttrs.filter((n) => n === 'run-model' || n === 'tools')
      if (back.length) {
        return (
          `<AgentToolPopover> 上又出现了 ${back.map((n) => '`' + n + '`').join('、')} —— ` +
          '整块脚注已按用户裁决删除、组件里也没有这两个 prop 了（L41 守着组件那侧），别加回来'
        )
      }

      const problems = []
      // ② `:model` 还在。⚠️ 如实记一笔：组件那侧的 `model` prop 现在**没有消费者**（脚注那行模型名已删）；
      //    留不留它是**另一处决定**（L15 也在守它的表达式），不在这一轮里顺手删。
      if (!boundProps.includes('model')) {
        problems.push(
          '`<AgentToolPopover>` 上找不到 `:model` 绑定 —— 它是 2026-09-19「切换模型后弹层不更新」那个修复的接线' +
            '（L15 断的是它的**表达式**）。组件那侧暂时没有消费者，但删它要连 L15 一起动，别在这一轮顺手删'
        )
      }
      // ③ 「只有 `:model`」：多传别的 **prop**（`:x` / `v-bind:x`）说明这轮删减没删干净。
      //    ⚠️ 只数**绑定进 props 的**属性；`class` / `ref` / `v-if` 这类不是 prop，不该被这条拦。
      const extra = boundProps.filter((n) => n !== 'model')
      if (extra.length) {
        problems.push(
          `<AgentToolPopover> 上除了 \`:model\` 还传了 ${extra.map((n) => ':`' + n + '`').join('、')} —— ` +
            '按用户裁决这里只该有 `:model`；确有新功能要加 prop 时，请连着这条断言一起说明，别默默加'
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L44',
    file: POPOVER,
    label: '清单行的归一化：名字读 `entry.function.name`、界面文案读**顶层** `label`/`descriptionZh`（模型侧英文不许进界面）',
    fn: () => {
      const rt = toolPopoverRuntime({})
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      if (typeof rt.api.toRow !== 'function') {
        return '组件里找不到 toRow —— 清单行的归一化没有单一出处（判据散在模板里就没人能测它）'
      }
      const problems = []
      // ⚠️ 这条守的是**两层不许读错**：
      //    ① 名字在 `entry.function` **里面**（条目本身没有 `.name`）—— 读错层**不会报错**，
      //       只会让每一行都是空名字（`:key` 全一样、开关错位），界面像「工具一个都没有名字」；
      //    ② 界面文案在**顶层**（`entry.label` / `entry.descriptionZh`），而**模型侧的
      //       `entry.function.description` 永远不许进界面** —— 那是「给 ai 发的英文」，
      //       摆给用户看正是这次要修掉的缺陷。
      //    fixture 刻意让两层的值一眼能分辨：读错层时下面的断言必然红，而不是静默画出一行空文案。
      const EN = 'MODEL-SIDE-EN-DESCRIPTION'
      const fixture = {
        type: 'function',
        function: { name: 'bank_manage', description: EN },
        label: '题库管理',
        descriptionZh: '题库的中文说明',
        disabled: 0
      }
      const row = rt.api.toRow(fixture)
      if (row?.name !== 'bank_manage') {
        problems.push(
          `schema 条目归一出来 name 是 ${JSON.stringify(row?.name)}（应 bank_manage）—— ` +
            '读错层了（名字在 `entry.function` 里，条目本身没有 `.name`）'
        )
      }
      if (row?.label !== '题库管理') {
        problems.push(
          `label 归一出来是 ${JSON.stringify(row?.label)}（应「题库管理」）—— ` +
            '它在**顶层** `entry.label`，不在 `entry.function` 里'
        )
      }
      if (row?.descZh !== '题库的中文说明') {
        problems.push(
          `descZh 归一出来是 ${JSON.stringify(row?.descZh)}（应「题库的中文说明」）—— ` +
            '它在**顶层** `entry.descriptionZh`'
        )
      }
      if (JSON.stringify(row).includes(EN)) {
        problems.push(
          '归一后的行里出现了**模型侧**的英文描述 —— 界面文案只许来自 `label` / `descriptionZh`：' +
            '把面向模型的文本摆给用户看是本次要修掉的缺陷'
        )
      }
      if (row?.disabled !== 0) {
        problems.push(`disabled:0 归一成了 ${JSON.stringify(row?.disabled)}（应 0 —— 别把 0 读成「已屏蔽」）`)
      }
      const off = rt.api.toRow(agentTool('memory_search', 1))
      if (off?.disabled !== 1) problems.push(`disabled:1 归一成了 ${JSON.stringify(off?.disabled)}（应 1）`)
      // 缺省（后端还没下发这一列）→ 0 = 可用，与 toolEnabled 的 `!== 1` 同口径
      const bare = rt.api.toRow(agentTool('note_manage'))
      if (bare?.disabled !== 0) {
        problems.push(`缺省 disabled 归一成了 ${JSON.stringify(bare?.disabled)}（应 0 = 可用，与 toolEnabled 同口径）`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L45',
    file: NOTES_LIST,
    label: '学习分享列表卡片上显示评论数 `💬 N`，取的是后端已算好的 commentCount（**含子留言**）',
    fn: () => {
      // 用户要求（2026-09-21）：「在笔记列表那边显示每条笔记评论数量」。
      // 口径是**含子留言**：后端 `note.comment_count` 建评论时（不分是否子留言）就 +1、
      // 删评论 / 删笔记时一起扣（`delete_comment` 那条扣减是本功能一起补上的），
      // 所以前端直接用列表接口已经下发的 `commentCount` 就对了 ——
      // 谁要是把它改成「只数一级评论」，卡片上的数字就会比自己点进去看到的少。
      //
      // ⚠️ 断的是**模板里那行标记**（先 `codeText` 剥注释），不是「AST 里找节点」：
      //    旁边那句说明注释里写着 `note.comment_count`，不剥注释的话断言可能被自己的注释满足。
      //    也不能只断「文件里存在 commentCount」—— `hotTip()` 里本来就有一个 `item.commentCount`，
      //    那样断会**恒真**，而这个节点删掉了也不报红。
      const code = codeText(NOTES_LIST)
      const hit = /class="comments"\s*>\s*💬\s*\{\{\s*note\.commentCount\s*(\|\|\s*0\s*)?\}\}/.exec(code)
      if (!hit) {
        return (
          '列表卡片的 meta 行里找不到「💬 + note.commentCount」这个节点 —— ' +
          '用户点名要的「每条笔记的评论数」没了（只剩这条断言在守它）'
        )
      }
      return null
    }
  },
  {
    id: 'L46',
    file: TOOL_RESULT,
    label: '工具名有人话，且**覆盖后端注册表里的每一个工具**（读 tools/*.py 的 `name = "…"` 自动比对）',
    fn: () => {
      // ⚠️ 判据来源是**后端注册表**，不是本文件里的一份金标名单：
      //    金标名单只能发现「标签被删」，发现不了「后端新增了一个工具」—— 而后者
      //    恰恰是这个缺陷的起源（本轮就是「新加了 5 个工具、前端不知道」）。
      //    只读后端文件，不写（前端角色对后端一行都不许改）。
      const reg = backendToolRegistry()
      if (reg.why) {
        return `${reg.why} —— 这条**没生效**（按未验证算，不要当成通过）`
      }
      const table = labelTable(TOOL_RESULT, 'TOOL_LABELS')
      if (!table?.size) return `读不出 ${TOOL_RESULT} 的 TOOL_LABELS —— 抽取逻辑/表名过期了（按未验证算）`
      const problems = []
      for (const t of reg.tools) {
        const label = table.get(t.name)
        if (label === undefined) {
          problems.push(`${t.name}（${t.file}）没有标签 → 卡片第二层就是英文标识符`)
        } else if (!HAS_CJK.test(label)) {
          problems.push(`${t.name} 的标签是 ${JSON.stringify(label)}，不含中文（等于没补）`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L47',
    file: CONFIRM,
    label: '确认卡片的 TOOL_LABELS 与「执行结果卡片」的**是同一份清单**（键集完全相同 + 覆盖注册表）',
    fn: () => {
      const reg = backendToolRegistry()
      if (reg.why) return `${reg.why} —— 这条**没生效**（按未验证算，不要当成通过）`
      const result = labelTable(TOOL_RESULT, 'TOOL_LABELS')
      const confirm = labelTable(CONFIRM, 'TOOL_LABELS')
      if (!result?.size || !confirm?.size) return '两张 TOOL_LABELS 里有一张读不出来（按未验证算）'
      const problems = []
      for (const t of reg.tools) {
        const label = confirm.get(t.name)
        if (label === undefined) problems.push(`${CONFIRM} 少了 ${t.name}`)
        else if (!HAS_CJK.test(label)) problems.push(`${CONFIRM} 的 ${t.name} 标签是 ${JSON.stringify(label)}，不含中文`)
      }
      // 「只补了一边」是这个仓库真发生过的事（同一个名字两处维护就必然漂）
      const onlyResult = [...result.keys()].filter((k) => !confirm.has(k))
      const onlyConfirm = [...confirm.keys()].filter((k) => !result.has(k))
      if (onlyResult.length) problems.push(`只有 ${TOOL_RESULT} 有：${onlyResult.join('、')}`)
      if (onlyConfirm.length) problems.push(`只有 ${CONFIRM} 有：${onlyConfirm.join('、')}`)
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L48',
    file: TOOL_RESULT,
    label: 'action 有人话，且覆盖每个工具 schema 里 `"action"` 的 enum（两张表键集相同）',
    fn: () => {
      const reg = backendToolRegistry()
      if (reg.why) return `${reg.why} —— 这条**没生效**（按未验证算，不要当成通过）`
      const result = labelTable(TOOL_RESULT, 'ACTION_LABELS')
      const confirm = labelTable(CONFIRM, 'ACTION_LABELS')
      if (!result?.size || !confirm?.size) return '两张 ACTION_LABELS 里有一张读不出来（按未验证算）'
      const problems = []
      const unverified = []
      for (const t of reg.tools) {
        if (t.actions === null) continue // 这个工具没有 action 参数（只读检索类）
        if (!Array.isArray(t.actions)) {
          unverified.push(`${t.file}：${t.actions.why}`)
          continue
        }
        for (const act of t.actions) {
          for (const [who, table] of [
            [TOOL_RESULT, result],
            [CONFIRM, confirm]
          ]) {
            const label = table.get(act)
            if (label === undefined) problems.push(`${who} 的 ACTION_LABELS 少了「${act}」（${t.name}）`)
            else if (!HAS_CJK.test(label)) problems.push(`${who} 的「${act}」标签是 ${JSON.stringify(label)}，不含中文`)
          }
        }
      }
      const onlyResult = [...result.keys()].filter((k) => !confirm.has(k))
      const onlyConfirm = [...confirm.keys()].filter((k) => !result.has(k))
      if (onlyResult.length) problems.push(`只有 ${TOOL_RESULT} 有：${onlyResult.join('、')}`)
      if (onlyConfirm.length) problems.push(`只有 ${CONFIRM} 有：${onlyConfirm.join('、')}`)
      // 「抽不到」必须显式说出来，不能默认当成通过
      if (unverified.length) problems.push('这条路没验到（枚举不是字面量）：' + unverified.join('；'))
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L49',
    file: CONFIRM,
    label: '确认卡片 PREVIEW_LABELS 覆盖 5 个新工具 preview() 输出的键（判定标准：值含中文）',
    fn: () => {
      const table = labelTable(CONFIRM, 'PREVIEW_LABELS')
      if (!table?.size) return `读不出 ${CONFIRM} 的 PREVIEW_LABELS（按未验证算）`
      const miss = []
      const fake = []
      for (const key of PREVIEW_KEYS_REQUIRED) {
        const label = table.get(key)
        if (label === undefined) miss.push(key)
        else if (!HAS_CJK.test(label)) fake.push(`${key}=${JSON.stringify(label)}`)
      }
      const problems = []
      if (miss.length) problems.push(`没有标签（确认卡片上就是英文键名）：${miss.join('、')}`)
      if (fake.length) problems.push(`标签不含中文（等于没补）：${fake.join('、')}`)
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L50',
    file: TOOL_DETAIL,
    label: 'FIELD_LABELS 覆盖 5 个新工具回执里的字段名（判定标准：值含中文）',
    fn: () => {
      const table = labelTable(TOOL_DETAIL, 'FIELD_LABELS')
      if (!table?.size) return `读不出 ${TOOL_DETAIL} 的 FIELD_LABELS（按未验证算）`
      const problems = []
      for (const [tool, keys] of Object.entries(FIELD_KEYS_REQUIRED)) {
        const miss = keys.filter((k) => table.get(k) === undefined)
        const fake = keys.filter((k) => table.has(k) && !HAS_CJK.test(table.get(k)))
        if (miss.length) problems.push(`${tool}：没有标签 ${miss.join('、')}`)
        if (fake.length) problems.push(`${tool}：标签不含中文 ${fake.join('、')}`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L51',
    file: TOOL_DETAIL,
    label: '0/1 语义的列不许显示裸数字（ENUM_LABELS 覆盖 5 个键 + YES_NO_KEYS 覆盖 4 个键）',
    fn: () => {
      const problems = []
      for (const key of ZERO_ONE_ENUM_KEYS) {
        const body = nestedEnumBody(TOOL_DETAIL, 'ENUM_LABELS', key)
        if (body === null) {
          problems.push(`ENUM_LABELS 里没有 ${key} 的映射 → 用户看到的是裸 0/1`)
          continue
        }
        const pairs = [...body.matchAll(/'([^']*)'\s*:\s*'([^']*)'/g)].map((m) => [m[1], m[2]])
        if (pairs.length < 2) problems.push(`ENUM_LABELS.${key} 只有 ${pairs.length} 个取值（0/1 两个都要有）`)
        const bad = pairs.filter(([, v]) => !HAS_CJK.test(v)).map(([k, v]) => `${k}→${JSON.stringify(v)}`)
        if (bad.length) problems.push(`ENUM_LABELS.${key} 的值不是人话：${bad.join('、')}`)
      }
      const yesNo = stringSetItems(TOOL_DETAIL, 'YES_NO_KEYS')
      if (!yesNo) problems.push('读不出 YES_NO_KEYS（按未验证算）')
      else {
        const miss = YES_NO_KEYS_REQUIRED.filter((k) => !yesNo.includes(k))
        if (miss.length) {
          problems.push(
            `YES_NO_KEYS 少了 ${miss.join('、')} —— 后端对这几个列给的是 **int 0/1**，` +
              '`scalarText` 只在值本来就是 boolean 时才翻，所以会原样显示成「0」'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L52',
    file: TOOL_DETAIL,
    label: '机器标识符 + 人话两个都给时只显示人话（REDUNDANT_KEYS 的 flagType/memoryType/markedType/status）',
    fn: () => {
      // ⚠️ 这是**源码级**判据（断的是 REDUNDANT_KEYS 那张表本身），不是行为级：
      //    `question_flag_manage` 的回执两个字段都给，谁都看得懂 `题目标签: 错题本`，
      //    但并排再显示一个 `标记类型: error` 就是纯噪声 —— 这条守的就是那个「隐掉」。
      const pairs = [
        ['flagType', 'flagTypeText'],
        ['memoryType', 'memoryTypeText'],
        ['markedType', 'markedTypeText'],
        ['status', 'effective']
      ]
      const miss = pairs.filter(([k, twin]) => !redundantPair(TOOL_DETAIL, k, twin)).map(([k, twin]) => `${k}←${twin}`)
      return miss.length
        ? `REDUNDANT_KEYS 里没有这几对「有人话就隐掉原键」：${miss.join('、')}`
        : null
    }
  },
  {
    id: 'L53',
    file: TOOL_DETAIL,
    label: '守门：`status` 不进全局枚举表（两个语义相反）+ 库表反向的 `is_public` 仍是 0=公开',
    fn: () => {
      const problems = []
      // ⚠️ 错题记录的 status 是 1=活跃、分享的是 '0'=有效 —— 语义相反，**不能**共用一张
      //    全局枚举（同一类坑参照 `is_public`：题库 0=公开、笔记 1=公开）。
      //    真要给错题本显示「活跃/已掌握」，正确做法是后端像 note_brief 那样直接给中文列。
      if (nestedEnumBody(TOOL_DETAIL, 'ENUM_LABELS', 'status') !== null) {
        problems.push(
          'ENUM_LABELS 里出现了 `status` —— 错题记录的 status(1=活跃) 与分享的 status(\'0\'=有效) ' +
            '语义相反，一张全局表必然给其中一个显示反；请让后端给 `statusText` 而不是在前端合并'
        )
      }
      for (const key of ['isPublic', 'is_public']) {
        const body = nestedEnumBody(TOOL_DETAIL, 'ENUM_LABELS', key)
        if (body === null) {
          problems.push(`ENUM_LABELS 少了 ${key}（题库的可见性）`)
          continue
        }
        if (!/'0'\s*:\s*'公开'/.test(body)) {
          problems.push(
            `ENUM_LABELS.${key} 的 0 不是「公开」—— 库里 is_public 是**反向**的` +
              '（题库 0=公开，questions.py「公开题库广场：只认 is_public == 0」），改反了用户看到的就正好相反'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L54',
    file: CONFIRM,
    label: 'preview 里「有人话就隐掉机器码」（flagType/disabled/memoryType）+ 没有人话的键不受影响',
    fn: () => {
      // 后端本来就是成对给的（flagType/flagTypeText、disabled/disabledText、memoryType/memoryTypeText），
      // 所以这条能盖住大半「机器码打在确认卡片上」。行为级判据：**喂 preview，看它算出哪些行**。
      const cases = [
        [{ flagType: 'error', flagTypeText: '错题本', recordId: 7, preview: '题干' }, 'flagType', 'flagTypeText'],
        [{ disabled: 0, disabledText: '启用中', kbId: 3, name: '资料' }, 'disabled', 'disabledText'],
        [{ memoryType: 'episodic', memoryTypeText: '操作记录', memoryId: 9 }, 'memoryType', 'memoryTypeText']
      ]
      const problems = []
      for (const [preview, rawKey, textKey] of cases) {
        const rt = runConfirmCard(preview)
        if (!rt.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${rt.why}`
        const keys = rt.rows.map((r) => r.key)
        if (keys.includes(rawKey)) {
          problems.push(`${JSON.stringify(preview)} → 仍然摆了一行机器码 \`${rawKey}\``)
        }
        if (!keys.includes(textKey)) {
          problems.push(`${JSON.stringify(preview)} → 人话字段 \`${textKey}\` 被一起隐掉了（那就什么都不显示了）`)
        }
      }
      // 负对照：既没有人话、也不在是/否名单里的键**必须原样保留**——
      // 这条防的是「为了隐机器码把整张表都吃掉」
      const keep = runConfirmCard({ recordId: 7, bankName: '甲库' })
      if (!keep.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${keep.why}`
      const kept = keep.rows.find((r) => r.key === 'recordId')
      if (!kept || kept.text !== '7') {
        problems.push(`负对照：recordId 应原样显示 7，实际 ${kept ? JSON.stringify(kept.text) : '这一行没了'}`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L55',
    file: CONFIRM,
    label: 'preview 的值翻译：bool/int 0-1 → 是/否、核实过的枚举 → 人话，其余原样',
    fn: () => {
      // ⚠️ 只断**核实过取值域**的键（见组件里 `YES_NO_KEYS` / `VALUE_ENUMS` 的注释与出处）。
      //    核实不到的键**故意没有映射**，那些键的正确行为就是「原样显示」。
      const cases = [
        [{ allowFork: 1 }, 'allowFork', '是'],
        [{ allowFork: 0 }, 'allowFork', '否'],
        [{ received: true }, 'received', '是'],
        [{ received: false }, 'received', '否'],
        // 没有 `disabledText` 时必须自己翻（有的话走 L54 那条「隐机器码」）
        [{ disabled: 0 }, 'disabled', '启用'],
        [{ disabled: 1 }, 'disabled', '已屏蔽'],
        [{ permission: 'read' }, 'permission', '只读'],
        // 负对照：不在任何名单里的键不许被「顺手翻译」
        [{ shareId: 12 }, 'shareId', '12']
      ]
      const problems = []
      for (const [preview, key, want] of cases) {
        const rt = runConfirmCard(preview)
        if (!rt.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${rt.why}`
        const row = rt.rows.find((r) => r.key === key)
        if (!row) {
          problems.push(`${JSON.stringify(preview)} → \`${key}\` 这一行都没了`)
        } else if (row.text !== want) {
          problems.push(`${JSON.stringify(preview)} → \`${key}\` 显示成 ${JSON.stringify(row.text)}（应 ${JSON.stringify(want)}）`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L56',
    file: CONFIRM,
    label: 'preview 里的长值单独成块（标签一行、值一块、保留换行、不截断），短值仍同行',
    fn: () => {
      // 为什么需要这条：`previewRows` 原先对**所有**标量都用同一个「60px 标签 + 同行值」模板，
      // 而 `memory_manage.forget` 的预演会回 `content`（记忆正文，可达数百字）——
      // 正文被挤在 60px 标签右边，读不成句。
      //
      // ⚠️ 判据落在**结构**上，不是「源码里还有没有某个字面量」——四条链断任意一条就红：
      //    ① computed 必须给这行算出「长值」标记（离线真跑 script setup，喂 preview 看它算出什么）；
      //    ② 模板必须真的用那个标记（标记留着、模板不认 → 长正文照样挤一行，是最容易发生的假修）；
      //    ③ 样式必须真的 `pre-wrap`（否则多行正文的换行被吃掉，等价于没修）。
      //    负对照盖住「一律拆块」那种偷懒写法。
      const problems = []

      // ── ① 记忆正文（`content`：多行 + 超长）→ 走块渲染，且内容一字不少、换行保留 ──
      const longText = '第一行：今天复习了操作系统\n第二行：进程与线程的区别我总记混\n' + '记'.repeat(60)
      const rt = runConfirmCard({ content: longText, memoryId: 9 })
      if (!rt.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${rt.why}`
      const row = rt.rows.find((r) => r.key === 'content')
      if (!row) {
        problems.push('`content`（记忆正文）这一行都没了')
      } else {
        if (row.block !== true) {
          problems.push(
            `长 content 没走块渲染（block=${JSON.stringify(row.block)}）—— 又和 60px 宽的标签挤在同一行`
          )
        }
        if (row.text !== longText) {
          problems.push(
            `长 content 被截断/改写了：实得 ${String(row.text).length} 字 ≠ 原文 ${longText.length} 字`
          )
        } else if (!row.text.includes('\n')) {
          problems.push('长 content 的换行没保留（正文被压成一行）')
        }
      }

      // ── ② 负对照：短值**不许**拆块 ──
      //    防的是「一律拆块」：那会把卡片撑成一屏，短值也各占两行。
      const shortRt = runConfirmCard({ title: '甲' })
      if (!shortRt.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${shortRt.why}`
      const shortRow = shortRt.rows.find((r) => r.key === 'title')
      if (!shortRow) problems.push('负对照：短值 `title` 这一行没了')
      else if (shortRow.block) {
        problems.push('负对照：1 个字的 `title` 也被拆成块了 —— 「一律拆块」会把卡片撑松')
      }

      // ── ③ 模板侧：`row.block` 必须真的驱动块类名 ──
      const ast = templateAst(CONFIRM)
      if (!ast) return `读不到 ${CONFIRM} 的模板`
      const blockCls = [
        ['ac-preview-row', 'ac-preview-row--block'],
        ['ac-preview-val', 'ac-preview-val--block']
      ]
      for (const [sel, want] of blockCls) {
        const node = firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes(sel))
        if (!node) {
          problems.push(`模板里找不到 .${sel} 节点`)
          continue
        }
        const cls = boundExp(node, 'class') || ''
        // 两个条件都要：类名在（模板认这个标记）+ 条件是 `row.block`（不是写死的 `true`）
        if (!cls.includes(want) || !/\.\s*block\b/.test(cls)) {
          problems.push(
            `.${sel} 上没有「按 row.block 加 .${want}」的 :class 绑定（实测读到 ${JSON.stringify(cls)}）` +
              ' —— 标记算出来了但模板不认，长正文照样挤一行'
          )
        }
      }

      // ── ④ 样式侧：块类名真的保留换行，且没有被塞进截断类声明 ──
      const blockCss = cssRule(cssOf(CONFIRM), '.ac-preview-val--block')
      if (!blockCss) {
        problems.push('样式里没有 .ac-preview-val--block 规则（长值是块元素却没有块样式）')
      } else {
        const ws = declValue(blockCss, 'white-space')
        if (ws !== 'pre-wrap') {
          problems.push(
            `.ac-preview-val--block 的 white-space 是 ${JSON.stringify(ws)}（应 pre-wrap，否则正文里的换行被吃掉）`
          )
        }
        if (/\boverflow\s*:\s*hidden|text-overflow\s*:|line-clamp/.test(blockCss)) {
          problems.push(
            '.ac-preview-val--block 里出现了截断类声明（overflow: hidden / text-overflow / line-clamp）—— 长正文会被切掉'
          )
        }
      }

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L57',
    file: TOOL_DETAIL,
    label: '错题/收藏/斩题小卡的标题取题干（brief_of 形状：有 bankName、有 preview、无 questionText），且题库名仍留在键值行',
    fn: () => {
      // 为什么需要：`question_flag_manage.list` 的 items 是
      // `question_record_service.brief_of` 的产物 —— **有 `bankName`、有 `preview`(80 字题干)、
      // 没有 `questionText`**。旧实现里 `TITLE_KEYS` 把 `bankName` 排在 `preview` 前，
      // 标题被选成题库名；而 `restOf` 又按**整张表**跳过，题干 `preview` 也被一起摘掉
      // ⇒ 用户点开详情看到一排 ID 和状态，**唯独不知道是哪道题**。
      //
      // ⚠️ 判据落在**行为**上（离线真跑 `titleOf`/`restOf`/`rows`），不是读源码字面量。
      const STEM = '简述进程与线程的区别，并说明线程私有与共享的资源各有哪些'
      const item = {
        errorId: 12,
        questionId: 34,
        bankId: 5,
        bankName: '操作系统题库',
        questionType: 5,
        questionTypeText: '简答题',
        difficulty: 2,
        preview: STEM,
        notes: '第一轮复习',
        tags: ['进程'],
        createTime: '2026-09-20 10:00:00'
      }
      const rt = runToolDetail(item)
      if (!rt.ok) return `离线执行 ${TOOL_DETAIL} 的 script setup 失败：${rt.why}`
      const problems = []
      const title = rt.titleOf(item)
      const rest = rt.restOf(item)
      const rows = rt.rowsOf(rest)
      if (!title.includes(STEM)) {
        problems.push(`小卡标题成了 ${JSON.stringify(title)}，不是题干 —— 用户看不出这是哪道题`)
      }
      // 「题干在这条小卡上看得见」= 标题里有，或键值行里还有它（两者都没有就是真信息丢失）
      const stemInRows = rows.some((r) => typeof r.text === 'string' && r.text.includes(STEM))
      if (!title.includes(STEM) && !stemInRows) {
        problems.push('题干在这条小卡上**任何位置都没有出现**（标题不是它、键值行里也没有）')
      }
      // 负对照：题库名必须**仍以键值行出现** —— 防「用丢掉题库名换题干」那种一行改法
      if (!rows.some((r) => r.key === 'bankName')) {
        problems.push(
          `负对照：题库名被挤掉了（键值行里只剩 ${rows.map((r) => r.key).join('/') || '（空）'}）—— 那是拿一个字段换另一个字段`
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L58',
    file: TOOL_DETAIL,
    label: '题干同义对只显示一次：有 questionText 时标题取 questionText（不是题库名），preview 不再重复出现',
    fn: () => {
      // `question_manage.list` 的元素（`question_write_service.question_brief`）**同时**给
      // `questionText`（全文）与 `preview`（80 字截断）—— 同一份内容的两种长度，
      // 必须只出现一次：选中的那个当标题，同组的一起从键值行去掉。
      const FULL = '简述进程与线程的区别，并说明线程私有与共享的资源各有哪些'
      const CUT = '简述进程与线程的区别，并说明线程私有与共享的资源…'
      const item = {
        questionId: 34,
        bankId: 5,
        bankName: '操作系统题库',
        questionText: FULL,
        preview: CUT,
        difficulty: 2
      }
      const rt = runToolDetail(item)
      if (!rt.ok) return `离线执行 ${TOOL_DETAIL} 的 script setup 失败：${rt.why}`
      const problems = []
      const title = rt.titleOf(item)
      if (!title.includes(FULL)) problems.push(`标题成了 ${JSON.stringify(title)}（应取 questionText 全文）`)
      if (title.includes('操作系统题库')) {
        problems.push('标题变成了题库名 —— 偏好顺序里 bankName 又跑到了题干前面')
      }
      // 结构判据（不靠子串）：`preview` 整个键都不该留在键值行里
      const rest = rt.restOf(item)
      if ('preview' in rest) problems.push('`preview` 仍留在键值行里 —— 题干会以「全文 + 截断版」显示两遍')
      const rows = rt.rowsOf(rest)
      if (rows.some((r) => r.key === 'preview')) problems.push('渲染结果里仍有 `preview` 那一行')
      if (rows.some((r) => r.text === CUT)) problems.push('渲染结果里仍能看到截断版题干 —— 同一份内容显示了两遍')
      // 负对照：题库名仍要在（这条同时守住「没把题库名挤没」）
      if (!rows.some((r) => r.key === 'bankName')) {
        problems.push(
          `负对照：题库名被挤掉了（键值行里只剩 ${rows.map((r) => r.key).join('/') || '（空）'}）`
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L59',
    file: CONFIRM,
    label: 'L56 的边界：60 字不成块、61 字成块（守 `> LONG_TEXT_MIN` 不被写成 `>=`）',
    fn: () => {
      // 用**非 `content`** 的键，把「键名命中」那一条排除掉，单独钉住长度判据。
      const problems = []
      const a = runConfirmCard({ shareMessage: '记'.repeat(60) })
      if (!a.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${a.why}`
      const ra = a.rows.find((r) => r.key === 'shareMessage')
      if (!ra) problems.push('60 字的 shareMessage 这一行没了')
      else if (ra.block) problems.push('60 字就成块了 —— 判据是 `> 60`，边界应当**不成块**')

      const b = runConfirmCard({ shareMessage: '记'.repeat(61) })
      if (!b.ok) return `离线执行 ${CONFIRM} 的 script setup 失败：${b.why}`
      const rb = b.rows.find((r) => r.key === 'shareMessage')
      if (!rb) problems.push('61 字的 shareMessage 这一行没了')
      else if (!rb.block) problems.push('61 字仍不成块 —— 判据是 `> 60`，边界应当**成块**')
      return problems.length ? problems.join('；') : null
    }
  },
  /* =====================================================================
   * L60 / L61：2026-09-21「知识库抽屉拆成 外壳 + 面板」之后**新加**的两条
   * =====================================================================
   * 老判据（L18–L26）是「把锚点搬到内容的新家」，不是新增覆盖面；
   * 这两条补的是**拆分本身**新产生的缝隙 —— 缝隙里出问题的话，老判据**全都还是绿的**：
   *   · L60：外壳打开抽屉 = `activate()` → 面板 `loadKbs()`（默认 autoSelect）→ 选第一个库 + 拉文档。
   *          这条链断掉时，用户点开抽屉看到的是「一个库都没选中、没有文档区」；
   *   · L61：面板 1900 行、模板里 69 个引用，而它是**懒挂载**的 —— 模板引用了脚本里没有的
   *          标识符时整个组件挂载失败，症状是「点开抽屉一片空白」（与 L21 是同一个洞，两个文件各钉一次）。
   * ⚠️ id 只在末尾追加（不复用、不插队）：历史记录里的 `L<n>` 必须永远指向同一条判据。
   */
  {
    id: 'L60',
    file: KB_PANEL,
    label: '面板被激活（抽屉打开）时选第一个库 + 拉文档；`loadKbs(false)`（只喂徽标）不选库、不拉文档',
    fn: async () => {
      const problems = []

      // ① 抽屉打开那条路：`activate()` → `loadKbs()`（不带参数，autoSelect 默认 true）
      //    → `selectKb(kbs[0])` → `loadDocs`。别为了「挂载期不起轮询」把 autoSelect 的默认值
      //    翻成 false —— 那样抽屉打开后没有选中的库、也没有文档列表，比徽标不亮严重得多。
      //    （判据从老的 L20④ 搬过来，对象换成面板：这条链现在全在面板里。）
      const openPath = kbRuntime(KB_PANEL, { kbs: [{ kbId: 11, name: '丙' }] })
      if (!openPath.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${openPath.why}`
      await openPath.api.activate()
      if (openPath.api.activeKbId.value !== 11) {
        problems.push(
          `面板被激活时没有选中第一个库（activeKbId=${JSON.stringify(openPath.api.activeKbId.value)}）—— autoSelect 的默认值被改掉了`
        )
      }
      if (openPath.calls.listDocuments === 0) {
        problems.push('面板被激活时没有拉文档列表 —— autoSelect 的默认值被改掉了，用户看到的是空文档区')
      }

      // ② 反面（同一个函数的另一条路）：`loadKbs(false)` 只把列表取回来 ——
      //    宿主（悬浮助手的 tab / 入口徽标）只想知道「有几个库」时，不该顺带选中库、
      //    拉文档、起轮询。这条与 ① 成对：**只有两条路都对**才说明 autoSelect 这个开关还在。
      const badgeOnly = kbRuntime(KB_PANEL, { kbs: [{ kbId: 11, name: '丙' }] })
      if (!badgeOnly.ok) return `离线执行 ${KB_PANEL} 的 script setup 失败：${badgeOnly.why}`
      await badgeOnly.api.loadKbs(false)
      if (badgeOnly.api.activeKbId.value !== null) {
        problems.push(`loadKbs(false) 也选中了库（activeKbId=${JSON.stringify(badgeOnly.api.activeKbId.value)}）—— 只喂徽标的那条路串到了选库`)
      }
      if (badgeOnly.calls.listDocuments !== 0) {
        problems.push(`loadKbs(false) 拉了 ${badgeOnly.calls.listDocuments} 次文档 —— 只喂徽标的那条路白打请求`)
      }
      if (badgeOnly.calls.setTimeout !== 0) {
        problems.push(`loadKbs(false) 起了 ${badgeOnly.calls.setTimeout} 个定时器（轮询）—— 只喂徽标的那条路不该起后台轮询`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L61',
    file: KB_PANEL,
    label: '面板模板引用的标识符必须都能在 <script setup> 里找到（与 L21 同一条判据，对象换成新家：面板是懒挂载的，挂载失败 = 点开抽屉一片空白）',
    fn: () => templateIdentifierProblems(KB_PANEL)
  },
  /**
   * =====================================================================
   * L62–L65：工具弹层的「英汉双份 + 全选 + 搜索」（用户 2026-09-22 的新需求）
   * =====================================================================
   * 用户原话：「可用工具需要进行优化 首先要有英汉双份 给用户展示中文 给ai发送英文
   * 然后工具要有一键全选功能 然后还要有搜索功能」，细节裁决：
   *   · 全选：**只做一个控件**，且「有一个工具没选上就自动显示关闭」；
   *   · 英文工具名：中文为主 + **小字英文名**；
   *   · 搜索：按 **中文名 + 中文说明 + 英文名** 匹配。
   * 这四条补的是**新增覆盖面**（不是搬锚点）—— 它们坏掉时，L33–L44 全都还是绿的。
   * ⚠️ id 只在末尾追加（不复用、不插队）：历史记录里的 `L<n>` 必须永远指向同一条判据。
   */
  {
    id: 'L62',
    file: POPOVER,
    label:
      '中文层：主标题绑 `label`（缺失才回落 `name`）、副标题绑 `name`、说明绑 `descriptionZh` 且**空就不显示**（绝不回落模型侧英文）',
    fn: () => {
      const ast = templateAst(POPOVER)
      if (!ast) return '拿不到模板 AST'
      const problems = []
      const byClass = (cls) => firstNode(ast, (n) => n.type === 1 && nodeClasses(n).includes(cls))
      const textOf = (n) => String(nodeText(n) || '').replace(/\s+/g, '')

      // ① 主标题：中文名优先、缺失回落英文工具名
      const nameNode = byClass('atp-name')
      if (!nameNode) problems.push('找不到主标题节点（.atp-name）')
      else {
        const txt = textOf(nameNode)
        if (!/\blabel\b/.test(txt)) {
          problems.push(`主标题的文案是「${txt}」—— 它必须优先显示中文名 \`label\``)
        }
        if (!/\bname\b/.test(txt)) {
          problems.push(`主标题的文案是「${txt}」—— \`label\` 缺失时要有回落，回落成英文工具名 \`name\``)
        }
      }

      // ② 副标题：英文工具名（用户点名要「中文为主 + 小字英文名」，报 bug / 查日志都要靠它）
      const keyNode = byClass('atp-key')
      if (!keyNode) {
        problems.push('找不到英文工具名的小字节点（.atp-key）—— 用户点名要「中文为主 + 小字英文名」')
      } else if (textOf(keyNode) !== 't.name') {
        problems.push(`副标题的文案是「${textOf(keyNode)}」—— 应为 \`t.name\``)
      }

      // ③ 说明：只有 `descriptionZh` 非空才渲染 —— **这一格就是「不许把模型侧英文摆给用户看」**
      const descNode = byClass('atp-desc')
      if (!descNode) problems.push('找不到说明节点（.atp-desc）')
      else {
        const cond = String(ownConditionOf(ast, descNode) || '').replace(/\s+/g, '')
        if (cond !== 't.descZh') {
          problems.push(
            `说明节点的 v-if 是「${cond || '(没有 v-if)'}」—— 必须是 \`t.descZh\`：` +
              '中文说明缺失时**留空**，**绝不许**回落显示模型侧的英文 `function.description`'
          )
        }
        if (textOf(descNode) !== 't.descZh') {
          problems.push(`说明节点的文案是「${textOf(descNode)}」—— 应为 \`t.descZh\``)
        }
      }

      // ④ 端到端：中文说明为空的那一行，归一化结果里也不许冒出模型侧英文
      const rt = toolPopoverRuntime({})
      if (!rt.ok) {
        problems.push(`离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`)
        return problems.join('；')
      }
      const blank = rt.api.toRow({
        type: 'function',
        function: { name: 'bank_manage', description: 'MODEL-SIDE-EN' },
        label: '题库管理',
        descriptionZh: ''
      })
      if (blank?.descZh) {
        problems.push(`descriptionZh 为空时归一出了 ${JSON.stringify(blank.descZh)}（应空 —— 不许回落到英文描述）`)
      }
      if (JSON.stringify(blank).includes('MODEL-SIDE-EN')) {
        problems.push('descriptionZh 为空时行里出现了模型侧英文描述 —— 说明节点会把它显示给用户')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L63',
    file: POPOVER,
    label:
      '搜索：按「中文名 + 中文说明 + 英文名」匹配（trim / 不区分大小写）；搜不到时结果为空但**不篡改原数组**',
    fn: async () => {
      const base = [
        agentTool('bank_manage', 0, { label: '题库管理', descZh: '建库、改库、删库' }),
        agentTool('memory_search', 1, { label: '记忆检索', descZh: '翻以前聊过的事' }),
        agentTool('note_manage', 0, { label: '笔记管理', descZh: '记笔记、列分类' })
      ]
      const srv = toolsServer(base)
      const rt = toolPopoverRuntime({
        payload: srv.payload,
        save: srv.save,
        saveAll: srv.saveAll
      })
      if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
      const m = await rt.runMount()
      if (!m.ok) return m.why
      if (typeof rt.api.matchedRows === 'undefined') return '组件里找不到 matchedRows —— 搜索的过滤没有单一出处'
      const problems = []
      const namesOf = () => rt.api.matchedRows.value.map((r) => r.name)

      if (namesOf().length !== 3) {
        problems.push(`没输关键词时应列出全部 3 条，实际 ${JSON.stringify(namesOf())}`)
      }

      const cases = [
        ['题库', ['bank_manage'], '中文名'],
        ['删库', ['bank_manage'], '中文说明'],
        ['MEMORY', ['memory_search'], '英文名，且不区分大小写'],
        ['  笔记  ', ['note_manage'], '首尾空格要忽略'],
        ['管理', ['bank_manage', 'note_manage'], '两条的中文名都带「管理」']
      ]
      for (const [kw, want, why] of cases) {
        rt.api.keyword.value = kw
        const got = namesOf()
        if (JSON.stringify(got) !== JSON.stringify(want)) {
          problems.push(`搜「${kw}」（${why}）应命中 ${JSON.stringify(want)}，实际 ${JSON.stringify(got)}`)
        }
      }

      // 搜不到 → 空结果，且**原清单一个字都不许动**（过滤只影响渲染结果）
      const before = rt.api.rows.value.map((r) => r.name)
      rt.api.keyword.value = 'zzz-不可能命中-zzz'
      if (namesOf().length !== 0) problems.push('搜不到时结果应为空')
      const after = rt.api.rows.value.map((r) => r.name)
      if (JSON.stringify(before) !== JSON.stringify(after)) {
        problems.push(
          `搜索改动了原清单（${JSON.stringify(before)} → ${JSON.stringify(after)}）—— 过滤只许影响渲染结果`
        )
      }
      rt.api.keyword.value = ''
      if (namesOf().length !== 3) problems.push('清空关键词后应回到全部 3 条')
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L64',
    file: POPOVER,
    label:
      '「全选」：只有**每一个**工具都可用才显示为开（有一个关着就显示关）；两个方向都能走；假成功不翻、真成功用回传清单重画',
    fn: async () => {
      const problems = []
      const mk = async (flags) => {
        const base = flags.map((d, i) => agentTool(`t${i}`, d))
        const srv = toolsServer(base)
        const rt = toolPopoverRuntime({
          payload: srv.payload,
          save: srv.save,
          saveAll: srv.saveAll
        })
        if (!rt.ok) return { err: `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}` }
        const m = await rt.runMount()
        if (!m.ok) return { err: m.why }
        return { rt, srv }
      }

      // ① 取值域：用户点名的规则 ——「当检测到有一个工具没选上，全选按钮也要自动显示关闭」
      const domain = [
        [[0, 0, 0], true, '全部启用 → 开'],
        [[0, 1, 0], false, '只有一个是 1 → 关（用户明确要求的就是这一格）'],
        [[1, 1, 0], false, '混合 → 关'],
        [[1, 1, 1], false, '全部屏蔽 → 关']
      ]
      for (const [flags, want, why] of domain) {
        const r = await mk(flags)
        if (r.err) return r.err
        const got = r.rt.api.allEnabled.value
        if (got !== want) {
          problems.push(`allEnabled(${JSON.stringify(flags)}) = ${JSON.stringify(got)}（应 ${want}）—— ${why}`)
        }
      }
      // 空清单也要是 false：「拿不准」不许画成「已全选」（模板上它压根不渲染，这里钉住计算值）
      const empty = await mk([])
      if (empty.err) return empty.err
      if (empty.rt.api.allEnabled.value !== false) {
        problems.push('清单为空时 allEnabled 应为 false（不是 true）—— 拿不准不许画成「已全选」')
      }

      // ② 两个方向：不是全开 → 全部启用（写 0）；已是全开 → 全部屏蔽（写 1）
      const partial = await mk([0, 1])
      if (partial.err) return partial.err
      await partial.rt.api.toggleAll(true)
      if (JSON.stringify(partial.rt.calls.saveAllToolPrefs) !== JSON.stringify([[0]])) {
        problems.push(
          `不是全开时点全选，发出的载荷是 ${JSON.stringify(partial.rt.calls.saveAllToolPrefs)}（应 [[0]] = 全部启用）`
        )
      }
      if (!partial.rt.api.rows.value.every((t) => t.disabled === 0)) {
        problems.push('全部启用之后清单里还有 disabled=1 的行')
      }
      await partial.rt.api.toggleAll(false)
      if (JSON.stringify(partial.rt.calls.saveAllToolPrefs) !== JSON.stringify([[0], [1]])) {
        problems.push(
          `已是全开时再点一下，发出的载荷是 ${JSON.stringify(partial.rt.calls.saveAllToolPrefs)}` +
            '（应再来一次 [[1]] = 全部屏蔽：只做单向的话，全开之后这个控件就再也按不动了）'
        )
      }
      if (!partial.rt.api.rows.value.every((t) => t.disabled === 1)) {
        problems.push('全部屏蔽之后清单里还有 disabled=0 的行')
      }

      // ③ 假成功（ok:false）**不许翻**，且要把服务端原话带出来（游客那条真实的 403）
      {
        const base = [agentTool('t0', 0), agentTool('t1', 1)]
        const reason = '游客仅可浏览，登录后才能进行该操作（服务端 code=403）'
        const rt = toolPopoverRuntime({
          payload: () => ({ tools: base }),
          saveAll: () => ({ ok: false, payload: null, reason })
        })
        if (!rt.ok) return `离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`
        const m = await rt.runMount()
        if (!m.ok) return m.why
        const before = rt.api.rows.value.map((t) => t.disabled)
        await rt.api.toggleAll(true)
        const after = rt.api.rows.value.map((t) => t.disabled)
        if (JSON.stringify(before) !== JSON.stringify(after)) {
          problems.push(
            `批量写返回 ok:false，清单却被改成了 ${JSON.stringify(after)}（应保持 ${JSON.stringify(before)}）` +
              '—— 受控式的全部意义就在这一格：假成功绝不许伪造状态'
          )
        }
        if (!rt.msgs.error.some((s) => s.includes('游客仅可浏览'))) {
          problems.push(`批量写失败时没有把服务端原话显示出来（收到的 error 是 ${JSON.stringify(rt.msgs.error)}）`)
        }
        if (rt.api.allEnabled.value !== false) {
          problems.push('批量写失败之后 allEnabled 变了 —— 显示值只能来自服务端数据')
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L65',
    file: POPOVER,
    label: '搜索过滤**不看** `disabled`：被屏蔽的工具只要名字/说明命中就仍在结果里（把 L38 那条保证补回来）',
    fn: async () => {
      const problems = []
      // L38 断的是「清单的 v-for 源不带 filter/slice/splice」。搜索上线后 v-for 的源变成了
      // `matchedRows` —— L38 照旧绿，但**保证换了位置**：真正要守的不再是「v-for 直读 rows」，
      // 而是「过滤谓词只看关键词、不看 `disabled`」。这条把它钉回来，否则
      // 「搜一下就把被屏蔽的工具藏起来」会悄悄回归 —— 用户再也找不到那个开关去打开它
      // （知识库「屏蔽」那次踩过完全一样的坑）。
      const src = readSource(POPOVER)
      const start = src.indexOf('const matchedRows')
      if (start < 0) {
        return '找不到 matchedRows 的定义 —— 搜索的过滤谓词必须有单一出处，否则这条判据没处落'
      }
      const open = src.indexOf('computed(', start)
      // 有界窗口：从 `computed(` 到第一个 `})`（就是那个 computed 的收尾），不扫全文件
      const end = src.indexOf('})', open)
      const body = src.slice(open, end < 0 ? open + 400 : end)
      if (/disabled/.test(body)) {
        problems.push(
          'matchedRows 的过滤谓词里出现了 `disabled` —— 过滤只许看关键词：' +
            '被屏蔽的工具必须仍然列出来，否则用户没法把它打开回来'
        )
      }
      // 运行时确认：被屏蔽的那条在命中时确实还在
      const base = [
        agentTool('bank_manage', 1, { label: '题库管理', descZh: '建库改库删库' }),
        agentTool('note_manage', 0, { label: '笔记管理', descZh: '记笔记' })
      ]
      const srv = toolsServer(base)
      const rt = toolPopoverRuntime({
        payload: srv.payload,
        save: srv.save,
        saveAll: srv.saveAll
      })
      if (!rt.ok) {
        problems.push(`离线执行 ${POPOVER} 的 script setup 失败：${rt.why}`)
        return problems.join('；')
      }
      const m = await rt.runMount()
      if (!m.ok) return m.why
      rt.api.keyword.value = '题库'
      const hit = rt.api.matchedRows.value.map((r) => r.name)
      if (JSON.stringify(hit) !== JSON.stringify(['bank_manage'])) {
        problems.push(
          `搜「题库」应命中被屏蔽的 bank_manage，实际 ${JSON.stringify(hit)}（被屏蔽的工具不许被搜索藏起来）`
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L66',
    file: API_DSFREE,
    label:
      'ds-free 自己拼提示词的那一段**不许读中文层**（`label` / `descriptionZh`）—— 「给 ai 发送英文」的前端半边',
    fn: () => {
      // 用户需求是**两半**：「给用户展示中文」+「给 ai 发送英文」。L62–L65 守前半，
      // 后半的机械保证在两处：
      //   · 后端 `tests/_toolpref_probe.py` 的 P11c/P11d（载荷里 `function` 的键恰好
      //     {name, description, parameters}、模型侧不出现中文层内容）；
      //   · 这里 —— ds-free 的提示词是**前端自己拼**的，它必须只读 `function.*`。
      // 后端把中文放在 `function` **外面**，所以只要前端这段不伸手去拿，就进不了提示词。
      // 一旦有人「顺手」把中文名塞进提示词（比如想让模型看到更好懂的名字），
      // 模型侧的语言约定就此破掉，而且不会有任何报错 —— 只有这条能拦住它。
      const src = readSource(API_DSFREE)
      if (!src) return `读不到 ${API_DSFREE}`
      const start = src.indexOf('const toolText = tools')
      if (start < 0) {
        return '找不到 `const toolText = tools` —— 把工具清单变成提示词文本的那一段改名了？这条判据要有落点'
      }
      const end = src.indexOf(".join('\\n\\n')", start)
      if (end < 0) {
        return '找不到 toolText 那段 mapping 的收尾（`.join(...)`）—— 判据的窗口要不出来了'
      }
      const body = src.slice(start, end)
      const problems = []
      for (const key of ['label', 'descriptionZh']) {
        if (body.includes(key)) {
          problems.push(
            `拼提示词那一段里出现了 \`${key}\` —— 那是**界面字段**（中文），` +
              '模型侧只许用 `function.name` / `function.description` / `function.parameters`；' +
              '中文进提示词会让模型面对两套语言约定，而且不会有任何报错'
          )
        }
      }
      // 正面：这一段必须仍然读 `function.name` / `function.description`（别把工具名也弄丢了）
      if (!/fn\.name/.test(body)) problems.push('拼提示词那一段不再读 `fn.name` —— 工具清单没有名字了')
      if (!/fn\.description/.test(body)) {
        problems.push('拼提示词那一段不再读 `fn.description` —— 模型看不到工具用途了')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  /**
   * =====================================================================
   * L67：进页面 / 切会话时落到「最新一条」
   * =====================================================================
   * 用户报告（原话）：「智能体页面 每次进入 都会默认在最上方 不会自动滚动到下方
   * 用户最新的聊天会话那边」。
   *
   * 根因不是「忘了滚」，而是**滚了但被钳成 0**：挂载当刻父级 flex 还没算出
   * `.chat-messages` 的 `clientHeight`，`scrollHeight ≈ clientHeight`，
   * `scrollTop = scrollHeight` 落到 0，而且**不触发 scroll 事件** ——
   * 于是 `isNearBottom` 一直是 `true`（看起来在底部），后面也不会自我纠正。
   * 第二个坑：进入时视口就在最上面，`autoScrollIfNearBottom` 的
   * `if (!isNearBottom) return` 恰好不成立 → 一次都不滚。
   *
   * 所以这条判的是**三件缺一不可的事**：① 有一个**不看 `isNearBottom`** 的落底函数；
   * ② 它落底前等了**一帧**（不是只等 nextTick）；③ 它被**接进**「首次拿到非空清单」
   * 与「挂载时已有历史」两条路。
   */
  {
    id: 'L67',
    file: STREAM,
    label:
      '进页面 / 切会话时**无条件**落到最新一条，且落底前先等一帧布局（挂载当刻滚会被钳成 0 且不触发 scroll 事件）',
    fn: () => {
      const src = readSource(STREAM)
      if (!src) return `读不到 ${STREAM}`
      const problems = []

      /** 按大括号配平抠出一个具名函数/箭头常量的函数体 */
      const bodyOf = (name) => {
        const re = new RegExp(
          `(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=\\s*(?:async\\s*)?\\()`
        )
        const m = re.exec(src)
        if (!m) return null
        const open = src.indexOf('{', m.index)
        if (open < 0) return null
        let depth = 0
        for (let i = open; i < src.length; i++) {
          if (src[i] === '{') depth++
          else if (src[i] === '}') {
            depth--
            if (depth === 0) return src.slice(open, i + 1)
          }
        }
        return null
      }

      // 候选：函数体里写了 `scrollTop = ...scrollHeight`，且**没有** `if (!isNearBottom) return`
      const candidates = []
      const names = new Set()
      for (const m of src.matchAll(/(?:async\s+)?function\s+(\w+)\s*\(/g)) names.add(m[1])
      for (const m of src.matchAll(/const\s+(\w+)\s*=\s*(?:async\s*)?\(/g)) names.add(m[1])
      for (const n of names) {
        const b = bodyOf(n)
        if (!b) continue
        if (!/scrollTop\s*=\s*[\w.]*scrollHeight/.test(b)) continue
        if (/if\s*\(\s*!isNearBottom/.test(b) || /isNearBottom\.value\s*\)\s*\{?\s*return/.test(b)) {
          continue
        }
        candidates.push([n, b])
      }

      // `props.messages.length` 的 watch 里调了谁 —— 那就是「落底」这一步的入口
      const w = /watch\(\s*\(\)\s*=>\s*props\.messages\.length[\s\S]*?\n\}\)/.exec(src)
      if (!w) return '找不到 `props.messages.length` 的 watch —— 这条判据要有落点'
      const wb = w[0]
      const pin = candidates.find(([n]) => new RegExp(`${n}\\s*\\(`).test(wb))
      if (!pin) {
        problems.push(
          candidates.length
            ? `\`props.messages.length\` 的 watch 里没有调用任何一个「无条件落底」的函数` +
              `（候选：${candidates.map(([n]) => n).join('、')}）—— 首次拿到历史那一次必须**无条件**落底，` +
              '只走「在底部附近才跟随」的话，进入时视口在最上面 → 条件不成立 → 一次都不滚（用户报的就是这条）'
            : '组件里找不到「无条件落底」的函数 —— 每个写 `scrollTop = scrollHeight` 的地方都挂着 ' +
              '`if (!isNearBottom) return`：进入页面时（视口在最上面）一次都不会滚'
        )
        return problems.join('；')
      }
      const [pinName, pinBody] = pin

      /**
       * 取一个声明的**那一段**（到空行为止）。
       * ⚠️ 给**表达式体的箭头函数**用 —— `const nextFrame = () => new Promise(...)` 根本没有
       *    大括号块，`bodyOf`（配平大括号）抓不到它，只能按段落取。
       */
      const defRegion = (name) => {
        const m = new RegExp(`(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=)`).exec(src)
        if (!m) return ''
        const rest = src.slice(m.index)
        const blank = rest.search(/\n\s*\n/)
        return blank < 0 ? rest.slice(0, 500) : rest.slice(0, blank)
      }

      // ① 落底前必须等**一帧**（只等 nextTick 不够：clientHeight 还没算出来）
      //    ⚠️ 允许走一层间接：`await nextFrame()` 这种把「等一帧」抽成小助手的写法一样算数 ——
      //    判据要认的是**行为**（真的等了 rAF），不是「这个词必须出现在这个函数体里」。
      const awaited = [...pinBody.matchAll(/await\s+(\w+)\s*\(/g)].map((m) => m[1])
      const waitsAFrame =
        /requestAnimationFrame/.test(pinBody) ||
        awaited.some((fn) => /requestAnimationFrame/.test(defRegion(fn)))
      if (!/nextTick/.test(pinBody)) problems.push(`\`${pinName}\` 落底前没有 await nextTick()`)
      if (!waitsAFrame) {
        problems.push(
          `\`${pinName}\` 只等了 nextTick、没有等一帧（requestAnimationFrame，直接写或经 ${awaited
            .map((x) => '`await ' + x + '()`')
            .join(' / ') || '一个等帧的小助手'} 间接都行）—— ` +
            '挂载当刻父级 flex 还没算出 clientHeight，scrollTop = scrollHeight 会被**钳成 0**，' +
            '而且**不触发 scroll 事件**（isNearBottom 一直 true，之后也不会自我纠正）'
        )
      }
      // ② 落底之后跟随状态要回到「跟随中」，否则流式内容来了不跟
      if (!/isNearBottom\.value\s*=\s*true/.test(pinBody)) {
        problems.push(`\`${pinName}\` 落底后没有把 isNearBottom 置回 true —— 之后的流式内容不会继续跟随`)
      }
      // ③ 清单被清空（新对话 / 切会话的 reset()）要复位，下一次加载才会重新落底
      if (!/n\s*===\s*0|length\s*===\s*0/.test(wb)) {
        problems.push(
          'watch 里没有处理「清单被清空」那一格 —— 新对话 / 切会话之后不会重新落底（用户会停在最上面）'
        )
      }
      // ④ 挂载时**已经**有历史也要落底：父级在更早的生命周期里填好 `messages` 时，
      //    `length` 的 watch 根本不会触发（没有「变化」）
      const om = /onMounted\(\(\)\s*=>\s*\{[\s\S]*?\n\}\)/.exec(src)
      if (!om) problems.push('找不到 onMounted —— 这条判据要有落点')
      else if (!/props\.messages\.length/.test(om[0]) || !new RegExp(`${pinName}\\s*\\(`).test(om[0])) {
        problems.push(
          `onMounted 里没有「已经有历史就直接落底」那一格（应判 \`props.messages.length\` 并调 \`${pinName}()\`）—— ` +
            '父级在更早的生命周期里（setup / 更早的 onMounted）就填好了 messages 时，length 的 watch 不会触发'
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  /**
   * =====================================================================
   * L68：keep-alive 收起 / 还原时**保留离开时的滚动位置**
   * =====================================================================
   * 用户报告（原话）：「第一次进入智能体页面 可以保持底部效果 但是如果此时不刷新页面的
   * 情况下 前往其他页面 然后再切换回智能体页面 就会发现滚动位置被破坏了 自动跑到最上方了
   * 应该要记录离开智能体页面前的滚动位置 只要不刷新下次进入依然是保留上次离开时的滚动位置」。
   *
   * 这条守的是**配对的两件事**（少一半都不算修好）：
   *   ① 离开时（`onDeactivated`）把现场记下来 —— 而且**必须是滚动事件里实时记的值**。
   *      依据（Vue 3 `KeepAlive` 源码，`node_modules/@vue/runtime-core` 的
   *      `sharedContext.deactivate`）：`move(vnode, storageContainer, ...)` 在**前**、
   *      `invokeArrayFns(instance.da)` 在**后** —— 回调 `deactivated` 时 DOM 已经被摘出文档，
   *      此时读 `scrollTop` 得到 **0**，拿它当现场，切回来必然停在最上面（正是用户报的 bug）。
   *   ② 回来时（`onActivated`）在**等一帧之后**把像素写回去：`onActivated` 跑的当刻 DOM 刚被
   *      塞回文档、高度还没算出来，当刻写 `scrollTop` 会被**钳成 0**（与 L67 同一个坑）。
   *      并且**首次挂载那一次不能还原** —— `activated` 在挂载时也会跟着 `onMounted` 跑一次
   *      （`runtime-core` 里挂载路径的 `instance.a && queuePostRenderEffect(instance.a)`），
   *      那时还没有现场，无守卫地去「还原」= 首屏被拽到最上面，正是 L67 刚修掉的那条。
   *      另外「贴底离开」要**继续贴底**：离开期间可能有新内容追加，硬还原旧像素等于停在旧消息上。
   */
  {
    id: 'L68',
    file: STREAM,
    label:
      'keep-alive 离开/回来时保留滚动位置：离开只搬内存里实时记的值（不读已被摘出文档的 DOM）、回来等一帧再写回、首次挂载不还原、贴底离开继续贴底',
    fn: () => {
      const src = readSource(STREAM)
      if (!src) return `读不到 ${STREAM}`
      const problems = []

      /** 按大括号配平抠出一个具名函数/箭头常量的函数体 */
      const bodyOf = (name) => {
        const re = new RegExp(
          `(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=\\s*(?:async\\s*)?\\()`
        )
        const m = re.exec(src)
        if (!m) return null
        const open = src.indexOf('{', m.index)
        if (open < 0) return null
        let depth = 0
        for (let i = open; i < src.length; i++) {
          if (src[i] === '{') depth++
          else if (src[i] === '}') {
            depth--
            if (depth === 0) return src.slice(open, i + 1)
          }
        }
        return null
      }

      /**
       * 取一个声明的**那一段**（到空行为止）—— 给表达式体的箭头函数用
       * （`const nextFrame = () => new Promise(...)` 没有大括号块，`bodyOf` 抓不到）
       */
      const defRegion = (name) => {
        const m = new RegExp(`(?:function\\s+${name}\\s*\\(|const\\s+${name}\\s*=)`).exec(src)
        if (!m) return ''
        const rest = src.slice(m.index)
        const blank = rest.search(/\n\s*\n/)
        return blank < 0 ? rest.slice(0, 500) : rest.slice(0, blank)
      }

      // ① 落点：容器 ref 与 scroll 处理器 —— 都从「注册监听」那行取，**不写死名字**
      const reg = /(\w+)(?:\.value)?\.addEventListener\(\s*'scroll'\s*,\s*(\w+)/.exec(src)
      if (!reg) return '找不到「注册 scroll 监听」那一行 —— 这条判据要有落点'
      const elRef = reg[1]
      const onScroll = reg[2]
      const scrollBody = bodyOf(onScroll)
      if (!scrollBody) return `读不到 \`${onScroll}\` 的函数体`

      // ② 滚动事件里**实时**记下当前位置（这是唯一可用的现场来源，见 ① 的依据）
      const posM = /(\w+)(?:\.value)?\s*=\s*scrollTop\b/.exec(scrollBody)
      if (!posM) {
        return (
          `\`${onScroll}\`（scroll 处理器）里没有把滚动位置记下来（应有一句 \`<某个 ref> = scrollTop\`）—— ` +
          '离开那一刻读不到 DOM 的 scrollTop（keep-alive 先摘 DOM 再回调 deactivated），' +
          '位置只能在**还能滚的时候**顺手记；不记就无从还原'
        )
      }
      const posRef = posM[1]

      // ③ 同一个处理器里维护「是否贴底」（回来靠它分「还原像素」和「继续贴底」）
      const nearM = /(\w+)(?:\.value)?\s*=[^\n]*scrollHeight[^\n]*scrollTop/.exec(scrollBody)
      if (!nearM) {
        return (
          `\`${onScroll}\` 里没有算出「是否贴底」（应有一句 \`<某个 ref> = ...scrollHeight...scrollTop...\`）—— ` +
          '离开期间可能有新内容追加，贴底离开的人被还原到旧像素 = 切回来不在底部'
        )
      }
      const nearRef = nearM[1]

      // ④ 离开：onDeactivated 记现场，且**只能搬内存里的值**
      const da = /onDeactivated\(\(\)\s*=>\s*\{[\s\S]*?\n\}\)/.exec(src)
      const stashNames = []
      if (!da) {
        problems.push(
          '没有注册 `onDeactivated` —— 本页在 keep-alive 的 `:include` 名单里（front.vue / AppMain 的 ' +
            '<keep-alive>），离开时得把滚动现场记下来'
        )
      } else {
        const b = da[0]
        for (const m of b.matchAll(/(?:^|[;{\s])(\w+)(?:\.value)?\s*=(?!=)/g)) stashNames.push(m[1])
        if (!new RegExp(`\\b${posRef}\\b`).test(b)) {
          problems.push(`\`onDeactivated\` 里没用到 \`${posRef}\`（实时记下的位置）—— 现场没记，回来没得还原`)
        }
        if (!new RegExp(`\\b${nearRef}\\b`).test(b)) {
          problems.push(
            `\`onDeactivated\` 里没用到 \`${nearRef}\`（是否贴底）—— 回来分不清「贴底离开」和「还在读旧消息」`
          )
        }
        if (new RegExp(`\\b${elRef}\\b`).test(b)) {
          problems.push(
            `\`onDeactivated\` 里读了 \`${elRef}\`（DOM）—— Vue 的 KeepAlive 是**先把 DOM 摘出文档**` +
              '（`move(vnode, storageContainer, ...)`）**再**回调 `deactivated`：那时读 `scrollTop` 得到 0，' +
              '存下来的「现场」就是最上面，切回来正好复现用户报的 bug'
          )
        }
      }

      // ⑤ 回来：onActivated
      const ac = /onActivated\(\(\)\s*=>\s*\{[\s\S]*?\n\}\)/.exec(src)
      if (!ac) {
        problems.push('没有注册 `onActivated` —— 只「记下来」没人「还原」等于没做')
        return problems.join('；')
      }
      const acBody = ac[0]

      // ⑤-a 还原那一格：某个被调用的函数把**存下来的像素**写回去（写的是变量，不是 scrollHeight）
      const called = [...acBody.matchAll(/\b(\w+)\s*\(/g)].map((m) => m[1])
      const restoreFns = called
        .map((n) => [n, bodyOf(n)])
        .filter(([, b]) => b && /\.scrollTop\s*=\s*\w/.test(b) && !/scrollHeight/.test(b))

      // ⑤-b 「贴底离开 → 回来继续贴底」那一格：调无条件落底的函数，或在里面直接写 scrollTop = ...scrollHeight
      const pinNames = new Set()
      for (const m of src.matchAll(/(?:async\s+)?function\s+(\w+)\s*\(/g)) pinNames.add(m[1])
      for (const m of src.matchAll(/const\s+(\w+)\s*=\s*(?:async\s*)?\(/g)) pinNames.add(m[1])
      const pinCands = []
      for (const n of pinNames) {
        const b = bodyOf(n)
        if (!b) continue
        if (!/scrollTop\s*=\s*[\w.]*scrollHeight/.test(b)) continue
        if (/if\s*\(\s*!isNearBottom/.test(b) || /isNearBottom\.value\s*\)\s*\{?\s*return/.test(b)) continue
        pinCands.push([n, b])
      }
      const pinsInActivated =
        pinCands.some(([n]) => new RegExp(`\\b${n}\\s*\\(`).test(acBody)) ||
        /scrollTop\s*=\s*[\w.]*scrollHeight/.test(acBody)

      // ⑤-c 首次挂载不准还原：还原调用**之前**要有一次「有没有现场」的判断
      const restoreIdx = restoreFns.length
        ? acBody.search(new RegExp(`\\b${restoreFns[0][0]}\\s*\\(`))
        : -1
      const stashName = stashNames[0] || null
      const condIdx = stashName
        ? acBody.search(new RegExp(`if\\s*\\([^)]*\\b${stashName}\\b[^)]*\\)`))
        : -1

      if (!restoreFns.length) {
        problems.push(
          '`onActivated` 里没有「把存下来的位置写回去」那一格（一个把 `scrollTop` 设成**变量**、' +
            '而不是设成 `scrollHeight` 的函数）—— 只记不还原，切回来还是停在最上面'
        )
      }
      if (!pinsInActivated) {
        problems.push(
          '`onActivated` 里没有「贴底离开 → 回来继续贴底」那一格（调无条件落底的函数，或在里面直接写 ' +
            '`scrollTop = ...scrollHeight`）—— 离开期间追加的新内容会让旧像素落在半空中，' +
            '在底部聊天的人切回来就看不到最新一条'
        )
      }
      if (!stashName) {
        problems.push('读不出「现场」存在哪个 ref 上 —— 上面 `onDeactivated` 那条判据也要一起看')
      } else if (condIdx < 0) {
        problems.push(
          `\`onActivated\` 里没有「还没有现场就直接返回」的守卫（形如 \`if (!${stashName}.value) return\`）—— ` +
            '`activated` 在**首次挂载**时也会跟着 `onMounted` 跑一次（`runtime-core` 挂载路径里的 ' +
            '`instance.a && queuePostRenderEffect(instance.a)`），那时现场是空的，' +
            '无守卫地去还原 = 首屏被拽到最上面（L67 刚修掉的那条 bug）'
        )
      } else if (restoreIdx >= 0 && condIdx > restoreIdx) {
        problems.push(
          `\`onActivated\` 里「有没有现场」的判定排在还原调用**之后** —— 首次挂载那一次照样会去还原`
        )
      }

      // ⑤-d 还原前必须等一帧（同一个「当刻写被钳成 0」的坑），还原后跟随状态要对齐真实位置
      if (restoreFns.length) {
        const [rName, rBody] = restoreFns[0]
        const awaited = [...rBody.matchAll(/await\s+(\w+)\s*\(/g)].map((m) => m[1])
        const waitsAFrame =
          /requestAnimationFrame/.test(rBody) ||
          awaited.some((fn) => /requestAnimationFrame/.test(defRegion(fn)))
        if (!/nextTick/.test(rBody) || !waitsAFrame) {
          problems.push(
            `\`${rName}\` 还原前没有先等一帧（要 \`nextTick\`，还要 \`requestAnimationFrame\`` +
              `，直接写或经 ${awaited.map((x) => '`await ' + x + '()`').join(' / ') || '一个等帧的小助手'} ` +
              '间接都行）—— `onActivated` 跑的当刻 DOM 刚被塞回文档、高度还没算出来，' +
              '当刻写 `scrollTop` 会被**钳成 0**（与 L67 同一个坑）'
          )
        }
        if (!new RegExp(`\\b${onScroll}\\s*\\(`).test(rBody)) {
          problems.push(
            `\`${rName}\` 还原之后没有重新判一次「是否贴底」（调 \`${onScroll}\`）—— ` +
              '跟随状态跟真实位置对不上时，之后的流式内容会乱跟（该跟的不跟 / 在读旧消息却被拽走）'
          )
        }
      }

      return problems.length ? problems.join('；') : null
    }
  },
  /* =====================================================================
   * 轮末动作条 + 回退结果栏（L69–L84）
   * =====================================================================
   * 需求（2026-09-23 用户裁决，当天**更新**过一次）：「每轮聊天结束的末尾添加一个回退
   * 组件，用户点击后自动撤销本次的所有操作」+「每轮 LLM 对话的底部提供两个按钮：
   * 一个回退、一个一键复制；用户那边也要有复制按钮；回退后提问正文自动回到输入框」。
   *
   * ⚠️ **当天有两次裁决，方向相反，别按旧的那条改回来**：
   *   · 先：「语义是**只回退最近一轮**」；
   *   · 后：「**每一轮都能点回退**」（同一天稍晚，用户明确覆盖了前一条）。
   *   本族判据已按**后一条**写：L71 是「旧口径不许再出现」的反向判据，
   *   L74 是「每一轮都渲染」的正向判据。看到 `:active` / `lastTurnId` 回来就是回退了。
   *
   * 前端在这条链上**只做搬运**：账本和「哪些撤了 / 哪些不给撤」全在服务端
   * （`app/services/ai/agent/rollback_service.py`），前端把 `turnId` 送上去、把结果画出来。
   * 判据分工：**挂在哪 / 两个按钮 / 复制什么**断 `AiChatStream`（L69–L71 / L79），
   * **这一轮自己的状态**断 `AgentTurnRollback`（L74 / L75 / L76 / L77），
   * **逐条清单**断 `NOTICE`（L72 / L82 / L83，它必须在消息列表**之外** ——
   * 回退那一轮的消息会被整轮摘掉，清单留在那一格上等于没画），**接没接上**断两个消费方（L73 / L80 / L81 / L84）。
   *
   * ⚠️ 这一族里最要紧的一条是 L69 的顺序：`turn_end` 标记的 `role` 也是 `assistant`，
   *    分支一旦排到正文分支后面，整条标记就会渲染成一个**空气泡**（每轮多一个「Agent」空白卡片）——
   *    这是逻辑面改动带进树的真实瑕疵，不是假想。
   */
  {
    id: 'L69',
    file: STREAM,
    label:
      '`turn_end` 分支存在，且排在 assistant 正文分支**之前**（排到后面就是每轮多一个空气泡）',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到模板 AST'
      const forNode = firstNode(ast, (n) => n.type === 11)
      if (!forNode) return '消息列表的 `v-for` 不见了'
      const loopEl = (forNode.children || []).find((c) => c.type === 1)
      if (!loopEl) return '`v-for` 里找不到元素节点'

      // 一条 `v-if/v-else-if/v-else` 链就是一个 IF 节点，`branches` 的顺序**就是运行时求值顺序**
      const turn = ifBranchOf(loopEl, "'turn_end'")
      if (!turn) {
        return (
          '找不到 `msg.type === \'turn_end\'` 分支 —— 每轮那条轮末标记没有分支可落，' +
          '它会掉进 `msg.role === \'assistant\'` 的正文分支，渲染成一个**空白的 Agent 气泡**'
        )
      }
      const body = ifBranchOf(loopEl, "role === 'assistant'")
      if (!body) return '找不到 `msg.role === \'assistant\'` 的正文分支（判据要有落点：顺序是相对它说的）'

      if (turn.index > body.index) {
        return (
          `\`turn_end\` 分支排在第 ${turn.index} 支、正文分支在第 ${body.index} 支 —— **排到后面去了**：` +
          `\`turn_end\` 的 role 也是 assistant，正文分支会先命中，标记只能渲染成空气泡` +
          `（当前链：${turn.all.join(' | ')}）`
        )
      }
      if (turn.index === body.index) {
        return '`turn_end` 与正文分支读到了同一支 —— 这两条判据的落点混了，先确认两条分支各写了一次'
      }
      return null
    }
  },
  {
    id: 'L70',
    file: STREAM,
    label:
      '`turn_end` 分支渲染轮末动作条，并把这一轮的 turnId / **按轮的**回退状态 / 复制的正文 / 生成中禁用都传下去',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到模板 AST'
      const forNode = firstNode(ast, (n) => n.type === 11)
      const loopEl = (forNode?.children || []).find((c) => c.type === 1)
      if (!loopEl) return '`v-for` 里找不到元素节点'
      const turn = ifBranchOf(loopEl, "'turn_end'")
      if (!turn) return '找不到 `turn_end` 分支（先看 L69）'

      const comp = firstNode(turn.branch, (n) => n.type === 1 && n.tag === 'AgentTurnRollback')
      if (!comp) {
        return (
          '`turn_end` 分支里没有渲染 `AgentTurnRollback` —— 轮末那一格是空的：' +
          '两个动作按钮（回退 / 复制）都长在这个组件里'
        )
      }

      const problems = []
      const turnIdExp = boundExp(comp, 'turn-id')
      if (!turnIdExp || !/msg\.turnId/.test(turnIdExp)) {
        problems.push(
          `\`:turn-id\` 绑的是 \`${turnIdExp}\` —— 必须把**这一条标记自己的** \`msg.turnId\` 传下去，` +
            '否则组件不知道自己是哪一轮（回退请求要靠它定位账本）'
        )
      }
      // ⚠️ 2026-09-23 **反转**：`:active`（「只有最近一轮可点」）**不再要求**，
      //    而且不许回来 —— 用户当天的后一次裁决是「每一轮都能点回退」。
      //    反向判据在 L71（`:active` / `lastTurnId` 不许再出现），正向在 L74。
      const stateExp = boundExp(comp, 'state')
      if (!stateExp) {
        problems.push('没有 `:state` —— 组件拿不到回退状态，点完之后结果不会出现在界面上')
      } else if (!/rollbackStates\s*\[\s*msg\.turnId\s*\]/.test(stateExp)) {
        problems.push(
          `\`:state\` 绑的是 \`${stateExp}\` —— 必须**按轮取**（\`rollbackStates[msg.turnId]\`）：` +
            '一份「最近一次回退」的扁平状态存不下两轮的结果 —— 用户先撤第 1 轮、再撤第 2 轮，' +
            '第 1 轮那格会跟着显示第 2 轮的结果，而它自己的消息早就不在了'
        )
      }
      const answerExp = boundExp(comp, 'answer-text')
      if (!answerExp || !/msg\.turnId/.test(answerExp)) {
        problems.push(
          `\`:answer-text\` 绑的是 \`${answerExp}\` —— 「复制」要的是**这一轮**的回复正文，` +
            '必须按这一轮的 `turnId` 回溯（不能传空、也不能传整份消息列表）'
        )
      }
      const disabledExp = boundExp(comp, 'disabled')
      if (!disabledExp || !/isGenerating/.test(disabledExp)) {
        problems.push(
          `\`:disabled\` 绑的是 \`${disabledExp}\` —— 生成中必须禁用` +
            '（这一轮还在写库，这时撤账本会与它交叉）'
        )
      }
      const listener = (comp.props || []).find(
        (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'rollback'
      )
      if (!listener) problems.push('组件上的 `@rollback` 没接 —— 点了按钮没人转发，页面收不到')
      else if (!/rollback-turn/.test(expSource(listener) || '')) {
        problems.push(`\`@rollback\` 转发的是 \`${expSource(listener)}\` —— 没有抛成 \`rollback-turn\` 事件`)
      }
      const copyListener = (comp.props || []).find(
        (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'copy'
      )
      if (!copyListener) {
        problems.push('组件上的 `@copy` 没接 —— 复制按钮点了不会有任何反应（剪贴板与提示在消息流这一侧）')
      } else if (!/copyText\s*\(/.test(expSource(copyListener) || '')) {
        problems.push(
          `\`@copy\` 转发的是 \`${expSource(copyListener)}\` —— 没有走消息流那份 \`copyText()\`：` +
            '剪贴板 + 成功/失败提示全站只有那一份实现，另起一套必然有一侧不一致'
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L71',
    file: STREAM,
    label:
      '**反转判据**：旧口径「只有最近一轮可点」不许再出现（没有 `:active`、也没有算「最后一条 turn_end」的 `lastTurnId`）',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到模板 AST'
      /**
       * ⚠️ 2026-09-23 **判据反转**（同一天里的第二次裁决，方向与上午那次相反）：
       *    · 上午：「语义是**只回退最近一轮**」→ 当时这条断的是「`:active` 绑到从末尾往前扫出的
       *      最后一条 `turn_end`」，那是**正向**判据；
       *    · 稍晚：用户改成「**每一轮都能点回退**」→ 那个开关整体作废。
       *      所以这条**必须**一起反转：留着它就会把「每轮都能点」判成红的。
       *
       * ⚠️ 这不是「把断言放松」：它从「要求某个开关存在」变成「**要求旧口径不许回来**」，
       *    照样能红（把 `:active` 或 `lastTurnId` 任一个加回来就红，见变异表 M2b / M3 / M3b）。
       *    后来人看到这一段时：这是用户当天的裁决反转，**不是**有人为了过测试放宽了守则。
       *
       * ⚠️ 用 `codeText`（剥掉块注释 / HTML 注释 / 整行 `//`）而不是 `readSource`：
       *    这个文件的注释里**必须**能写「`:active` / `lastTurnId` 已删除、别再按旧口径改回来」，
       *    不剥注释的话断言会被自己那句说明文字判红（本仓踩过，见 `codeText` 的注释）。
       */
      const src = codeText(STREAM)
      const problems = []

      // 反向对照（fail-closed）：连组件名都读不到，说明扫描口径坏了 —— 别当成通过
      if (!/AgentTurnRollback/.test(src)) {
        return `扫描口径坏了：剥注释后的 ${STREAM} 里连 \`AgentTurnRollback\` 都找不到（别当成通过）`
      }

      // ① 模板这一侧：轮末组件上不许再有 `:active`
      const comp = firstNode(ast, (n) => n.type === 1 && n.tag === 'AgentTurnRollback')
      if (!comp) return '模板里找不到 AgentTurnRollback'
      const activeExp = boundExp(comp, 'active')
      if (activeExp) {
        problems.push(
          `轮末组件上又出现了 \`:active="${activeExp}"\` —— 那是「只有最近一轮可点」的开关：` +
            '用户 2026-09-23 裁决**每一轮都能点回退**（当天稍晚覆盖了更早的「只回退最近一轮」）。' +
            '它一旦回来，更早那些轮的回退入口就又被整格藏掉了'
        )
      }

      // ② 脚本这一侧：算「最近一轮」的那个 computed 不许回来（它只服务旧口径，没有别的用处）
      if (/\blastTurnId\b/.test(src)) {
        problems.push(
          '脚本里又出现了 `lastTurnId` —— 那是旧口径「只有最近一轮可点」的判据（从末尾往前扫最后一条 ' +
            '`turn_end`）。现在每一轮都渲染自己的动作条，`:state` 直接按轮取 ' +
            '`rollbackStates[msg.turnId]`，这个 computed 没有存在的理由；' +
            '留着它只会诱导后来人把 `:active` 一起加回来'
        )
      }

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L72',
    file: NOTICE,
    label:
      '结果直接吃服务端四个字段：模板里真的渲染 reverted / skipped / partial / failed（不是只画一句摘要）—— 落点 2026-09-23 从轮末那一格搬到**消息列表之外**的结果栏',
    fn: () => {
      const exprs = templateExprs(NOTICE)
      if (!exprs) return `拿不到 ${NOTICE} 的模板 AST`
      const joined = exprs.join('\n')
      /**
       * ⚠️ 落点在 2026-09-23 换过一次文件（`TURN_ROLLBACK` → `NOTICE`），**不是放松**：
       *    回退成功时那一轮的消息会被整轮摘掉（`outcome.dropped`），挂在轮末的组件跟着下线 ——
       *    逐条清单画在那一格上等于没画。所以清单搬到了消息列表**之外**的结果栏，
       *    判据跟着内容走（断的还是同一件事：四个字段都真的被渲染出来）。
       *    ⚠️ 轮末那一格仍要显示 `reverted` 与整轮被拒的 `reason`（各是 L75 的一半）。
       *
       * 判据落在**模板表达式**上（不是整份模板文本）：类名会污染子串 ——
       * `class="arn-skipped"` 里那个 `skipped` 就满足 `\bskipped\b`（`-` 是非词字符、正好构成边界），
       * 一个只有样式钩子、根本没读数据的类名会把这条判绿。
       */
      const missing = []
      for (const [field, why] of [
        ['reverted', '真正回退掉的条数'],
        ['skipped', '明确**没回退**的条目（工具不支持 / 影响到了别人 / 已被物理删除…）'],
        ['partial', '只退回一部分的条目（撤了，但没撤干净）'],
        ['failed', '回退**报错**的条目（要能重试）']
      ]) {
        if (!new RegExp(`\\b${field}\\b`).test(joined)) {
          missing.push(`\`${field}\`（${why}）`)
        }
      }
      if (missing.length) {
        return (
          `模板里没有渲染 ${missing.join('、')} —— ` +
          '这几个字段是界面契约（`AgentRollbackResult`）：只画一句「回退完成」等于把服务端算出来的' +
          '「哪一条为什么没退成」整份丢掉，用户看到的是「点了没反应」'
        )
      }
      return null
    }
  },
  {
    id: 'L73',
    file: TURN_ROLLBACK,
    label: '回退入口真的接上了：组件里按钮 → emit、消息流转发 rollback-turn、两个消费方都调 rollbackTurn()',
    fn: () => {
      const problems = []

      // ① 组件这一侧：按钮上要有点击处理，且那个处理真的 emit（否则页面收不到任何东西）
      const expr = templateExprs(TURN_ROLLBACK)
      if (!expr) return `拿不到 ${TURN_ROLLBACK} 的模板 AST`
      const ast = templateAst(TURN_ROLLBACK)
      const btn = firstNode(ast, (n) => n.type === 1 && n.tag === 'button')
      if (!btn) problems.push('组件里没有 `button` —— 用户没有可点的地方')
      else if (!(btn.props || []).some((p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'click')) {
        problems.push('那个 `button` 上没有 `@click` —— 点了不会有任何事发生')
      }
      const script = readSource(TURN_ROLLBACK)
      if (!/emit\(\s*'rollback'/.test(script)) {
        problems.push("组件脚本里没有 `emit('rollback'` —— 点击没有抛出去，页面无从调接口")
      }

      // ② 两个消费方：模板接了 `@rollback-turn`，脚本里真的调了 `rollbackTurn(`
      const listenerOf = (rel, event) => {
        const a = templateAst(rel)
        if (!a) return null
        const el = firstNode(a, (n) => n.type === 1 && n.tag === 'AiChatStream')
        if (!el) return null
        const l = (el.props || []).find(
          (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === event
        )
        return l ? expSource(l) : null
      }
      for (const rel of [CHAT, ASSISTANT]) {
        const src = readSource(rel)
        if (!src) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        if (!listenerOf(rel, 'rollback-turn')) {
          problems.push(
            `${rel} 的 AiChatStream 上没有 \`@rollback-turn\` —— 消息流抛出来的事件没人接`
          )
        }
        if (!/rollbackTurn\s*\(/.test(src)) {
          problems.push(
            `${rel} 里没有调 \`rollbackTurn(\` —— 事件接了却没调服务端入口：` +
              '按钮点下去只会在界面上转一圈，账本一条都不会回退'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L74',
    file: TURN_ROLLBACK,
    label:
      '**反转判据**：每一轮都渲染（根节点上**没有** v-if 开关），且消息流仍把那一格的外边距归零',
    fn: () => {
      const ast = templateAst(TURN_ROLLBACK)
      if (!ast) return `拿不到 ${TURN_ROLLBACK} 的模板 AST`
      const rootEl = firstNode(ast, (n) => n.type === 1)
      if (!rootEl) return '组件模板里找不到根元素'

      /**
       * ① 口径 **2026-09-23 反转**（同一天里的第二次裁决）：
       *    · 上午：「非最近一轮整格不渲染」（根节点 `v-if="active"`）—— 用户当时裁决「只回退最近一轮」；
       *    · 稍晚：用户改成「**每一轮都能点回退**」→ 每一轮末尾那一格都必须**渲染出**两个按钮。
       *    所以这条从「根节点必须有 `v-if`」反转为「根节点上**不许**有 `v-if` 开关」，
       *    并举一个：`AgentTurnRollback` 的根节点一旦挂上条件，就又变成「有的轮没有回退入口」。
       *
       * ⚠️ 这是用户当天的裁决反转，**不是**有人为了过测试放宽守则 —— L71 那半边
       *    （`:active` / `lastTurnId` 不许回来）是配套的反向判据，两条一起看才是完整口径。
       */
      const cond = ownConditionOf(ast, rootEl)
      if (cond) {
        return (
          `组件根节点上又有 \`v-if="${cond}"\` —— 那是「非最近一轮整格不渲染」的旧口径：` +
          '用户 2026-09-23 裁决**每一轮都能点回退**（当天稍晚覆盖了更早的「只回退最近一轮」）。' +
          '挂上条件就会让更早那些轮末尾整格消失，用户连按钮都看不到'
        )
      }

      // ② 那一格不能自己带高度/间距：「轮末」是**结构节点**，不是一条消息 ——
      //    消息流已把它的下方留白归零，间距全部由组件自己带；
      //    这条与 ① 无关，**反转时照样保留**（两边都缺一不可：留白归零、间距由组件带）。
      const rule = cssRule(cssOf(STREAM), '.message.msg-turn_end')
      if (!rule) {
        return (
          '找不到 `.message.msg-turn_end` 规则 —— `turn_end` 那一格会继承 `.message` 的 16px 下方留白：' +
          '它本身不是一条消息，于是**每一轮末尾**凭空多出一段空隙（消息间距 16px 变 32px）'
        )
      }
      const mb = pxValue(rule, 'margin-bottom')
      if (mb !== 0) {
        return `\`.message.msg-turn_end\` 的 margin-bottom 是 ${mb}（要求 0）—— 空的那一格会把间距撑回来`
      }
      return null
    }
  },
  {
    id: 'L75',
    file: TURN_ROLLBACK,
    label:
      '两个边界：「这一轮没有可回退的操作」要四个字段一起判（不是失败态）；整轮被拒时渲染的是服务端 reason **本身**',
    fn: () => {
      const src = readSource(TURN_ROLLBACK)
      const exprs = templateExprs(TURN_ROLLBACK)
      if (!exprs) return `拿不到 ${TURN_ROLLBACK} 的模板 AST`
      const problems = []

      // ① 「没有可回退的操作」= `ok` + `reverted === 0` + **三份清单都空**（四个一起看）。
      //    只判 `reverted === 0` 会把「0 条退成、3 条不给退」也说成「没有可回退的操作」——
      //    那是替服务端下了个它没下的结论，还把它列出来的清单吞掉。
      const body = jsBodyOf(src, 'nothingToRollback')
      if (!body) return '读不到 `nothingToRollback` 的函数体 —— 这条判据要有落点（函数体写成一行的表达式时也读不到）'
      for (const f of ['reverted', 'skipped', 'failed', 'partial']) {
        if (!new RegExp(`\\b${f}\\b`).test(body)) {
          problems.push(
            `\`nothingToRollback\` 没看 \`${f}\` —— 「这一轮没有可回退的操作」的判据少了这一半，` +
              '会把「0 条退成 + 有清单」也报成「没有可回退的操作」'
          )
        }
      }

      // ② 整轮被拒（`ok === false`）时显示服务端**原话**：模板里插值的就是 `outcome.reason` 本身
      //    （不加前缀、不换成「回退失败」）。服务端那句话是唯一说得清原因的
      //    （如「缺少轮次 id（turnId），无法回退」/「该轮次不存在或不属于你」）。
      //    ⚠️ 这种情况下**消息不会被摘掉**（`dropped=false`），所以「就地显示」是对的 ——
      //       逐条清单那一侧在 `AgentRollbackNotice`（`skipped` / `failed` 非空时才有）。
      //    ⚠️ 字段名跟着冻结后的契约走：结果对象在 `rollbackStates[turnId]` 里叫 `outcome`
      //       （旧版叫 `summary`）。改名**不是**放松判据：断的仍是「原样渲染服务端那个字段」。
      if (!exprs.some((e) => e.trim() === 'outcome.reason')) {
        problems.push(
          '模板里没有一处**原样**渲染 `outcome.reason` —— 整轮被拒时用户看不到服务端给的原因，' +
            '只能看到一句自己编的「回退失败」'
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  /* =====================================================================
   * L76–L84：两个按钮 / 图标 / 复制什么 / 结果区的位置 / 接线
   * =====================================================================
   * 需求（2026-09-23 用户裁决）：「每轮 LLM 对话的底部提供两个按钮，一个回退按钮、
   * 一个一键复制按钮；不要用 📝 这种图标，要用更合理的正经 icon；复制按钮 LLM 底部要有、
   * 用户那边也要有；回退后 LLM 的回答和用户的提问一起消失，提问内容自动回到输入框」。
   *
   * 这一族按「用户能看见的那件事」分条，每条只钉一个机制（变异表里一个半变异就能让它单独红）：
   *   L76 两个按钮（结构）… L77 图标名必须真的存在（写错名字会静默渲染成空）
   *   L78 按钮区不许用 emoji / 符号字符 … L79 复制按钮复制的是哪段文本
   *   L80 提问正文回填输入框（两个消费方）… L81 状态按轮 … L82 结果区在列表外且可关闭
   *   L83 结果区的高度账（不许把输入框挤出视线）… L84 成功要看得见
   */
  {
    id: 'L76',
    file: TURN_ROLLBACK,
    label:
      '轮末那一格有**两个**按钮：一个回退（emit rollback）一个复制（emit copy）—— 落结构，不断言渲染文案',
    fn: () => {
      const ast = templateAst(TURN_ROLLBACK)
      if (!ast) return `拿不到 ${TURN_ROLLBACK} 的模板 AST`
      const src = readSource(TURN_ROLLBACK)
      const buttons = []
      walkAst(ast, (n) => {
        if (n.type === 1 && n.tag === 'button') buttons.push(n)
      })
      if (buttons.length < 2) {
        return `轮末那一格里只有 ${buttons.length} 个 <button>（要 2 个：回退 + 复制，并排给用户点）`
      }

      /**
       * 按钮的 `@click` 处理体：具名处理函数读它的函数体，内联表达式直接用原文。
       * 读不到给 `null`（调用方按「这条判据没有落点」处理，别当成通过）。
       */
      const clickBodyOf = (b) => {
        const click = (b.props || []).find(
          (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'click'
        )
        if (!click) return null
        const exp = (expSource(click) || '').trim()
        if (/^[A-Za-z_$][\w$]*$/.test(exp)) return jsBodyOf(src, exp)
        return exp
      }
      const findEmit = (kw) =>
        buttons.find((b) => {
          const body = clickBodyOf(b)
          return !!body && new RegExp(`emit\\(\\s*['"]${kw}['"]`).test(body)
        })

      const problems = []
      const rb = findEmit('rollback')
      const cb = findEmit('copy')
      if (!rb) problems.push("没有一个按钮 emit `'rollback'` —— 回退这个动作没接上")
      if (!cb) problems.push("没有一个按钮 emit `'copy'` —— 复制这个动作没接上（用户要求 LLM 底部要有复制按钮）")
      if (rb && cb && rb === cb) {
        problems.push('回退与复制挂在**同一个**按钮上 —— 两个动作必须各有一个按钮（用户点哪个是明确的）')
      } else if (rb && cb && buttons.indexOf(rb) > buttons.indexOf(cb)) {
        problems.push('复制按钮排在了回退按钮前面 —— 主操作（回退）在前、次操作（复制）在后（用户列的顺序）')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L77',
    file: TURN_ROLLBACK,
    label:
      '按钮的图标：名字**真的在** `@element-plus/icons-vue` 的导出里，且在按钮里作为组件渲染（写一个不存在的名字会静默渲染成空）',
    fn: () => {
      /**
       * 包里导出的图标名（**不 import 这个包**：它是 vue 组件库，import 会拉起 vue 运行时；
       * 语法检查器只许用显式声明的依赖，读它的产物文件是纯文本操作）。
       * 导出清单长这样（`dist/index.js` 末尾一处）：`export { add_location_default as AddLocation, … }`
       */
      const iconExports = () => {
        const p = path.join(ROOT, 'node_modules/@element-plus/icons-vue/dist/index.js')
        if (!fs.existsSync(p)) return null
        const m = /^export\s*\{([\s\S]*?)^\};/m.exec(fs.readFileSync(p, 'utf8'))
        if (!m) return null
        const names = [...m[1].matchAll(/\bas\s+([A-Za-z_$][\w$]*)/g)].map((x) => x[1])
        return names.length ? new Set(names) : null
      }
      /** 某个文件里从图标包 import 进来的名字 */
      const iconImports = (rel) => {
        const out = []
        const re = /import\s*\{([^}]*)\}\s*from\s*['"]@element-plus\/icons-vue['"]/g
        let m
        while ((m = re.exec(readSource(rel)))) {
          for (const piece of m[1].split(',')) {
            const name = piece.trim().split(/\s+as\s+/).pop().trim()
            if (name) out.push(name)
          }
        }
        return out
      }

      const exports = iconExports()
      if (!exports) {
        return '读不到 `@element-plus/icons-vue` 的导出清单 —— 这条判据没有落点（别当成通过）'
      }
      const problems = []
      for (const rel of [TURN_ROLLBACK, NOTICE, STREAM]) {
        const imported = iconImports(rel)
        if (!imported.length) continue
        const missing = imported.filter((n) => !exports.has(n))
        if (missing.length) {
          problems.push(
            `${rel} 从 \`@element-plus/icons-vue\` import 了**不存在**的图标：${missing.join('、')} —— ` +
              '模板里写一个不存在的组件名**不会报错**，只会渲染成一片空白（静态检查也抓不到），' +
              '所以名字必须对着包的导出清单核一遍'
          )
        }
      }

      // ① 模板里用到的图标名必须是**本文件 import 过的**（否则渲染期解析不到 → 空白）
      for (const rel of [TURN_ROLLBACK, NOTICE]) {
        const ast = templateAst(rel)
        if (!ast) {
          problems.push(`拿不到 ${rel} 的模板 AST`)
          continue
        }
        const imported = new Set(iconImports(rel))
        const used = []
        walkAst(ast, (n) => {
          if (n.type === 1 && /^[A-Z]/.test(n.tag)) used.push(n.tag)
        })
        const unknown = used.filter((t) => !imported.has(t))
        if (unknown.length) {
          problems.push(
            `${rel} 的模板里用了没 import 的组件：${unknown.join('、')} —— ` +
              '**图标写错名字的典型症状就是它**：模板照样编译通过，运行时解析不到就渲染成空，' +
              '用户看到的是「两个按钮上一个图标都没有」（组件没挂上，也不报错）'
          )
        }
      }

      // ② 两个按钮里**真的**各自渲染了一个图标（不是只有文字）
      const ast = templateAst(TURN_ROLLBACK)
      if (!ast) return problems.length ? problems.join('；') : '拿不到模板 AST'
      const imported = new Set(iconImports(TURN_ROLLBACK))
      const buttons = []
      walkAst(ast, (n) => {
        if (n.type === 1 && n.tag === 'button') buttons.push(n)
      })
      if (!buttons.length) return problems.length ? problems.join('；') : '模板里找不到 <button>'
      buttons.forEach((b, i) => {
        const iconTag = firstNode({ children: b.children || [] }, (n) => n.type === 1 && n.tag === 'el-icon')
        if (!iconTag) {
          problems.push(`第 ${i + 1} 个按钮里没有 \`el-icon\` —— 用户要求用正经图标，不是纯文字按钮`)
          return
        }
        const inner = firstNode(iconTag, (n) => n.type === 1 && n !== iconTag)
        if (!inner || !imported.has(inner.tag)) {
          problems.push(
            `第 ${i + 1} 个按钮的图标读不到一个**已 import 的图标组件**（读到的是 \`${inner ? inner.tag : '(空)'}\`）—— ` +
              '`<el-icon>` 里没有子组件时它什么都画不出来'
          )
        }
      })
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L78',
    file: TURN_ROLLBACK,
    label:
      '按钮区**不许**用 emoji 或符号字符当图标（📝 / ↩ / ↻ / ⚠ 这类码点一个都不许出现在按钮的可见文案里）',
    fn: () => {
      /**
       * 判据范围：`AgentTurnRollback`（整份模板，轮末那一格就是按钮区）+
       * 消息流里每个 `<button>` / `<el-button>` 的**可见文案**（`nodeText`，含 TEXT 与插值原文）。
       *
       * ⚠️ 只扫按钮的文案、不扫整个文件：
       *   · `AiChatStream` 的 `noteIcon()` 用的是 `↻` / `✕`（历史遗留，属于「过程提示」那一块，
       *     不在本次需求范围内）—— 整份文件扫描会把它算成违规，那不是这次的缺陷；
       *   · 注释里**必须**能写「不许用 📝 / ↩」这种反例说明 → 所以用 `stripBlockComments` 剥掉注释。
       */
      const EMOJI =
        /[\u{1F000}-\u{1FAFF}\u{2190}-\u{21FF}\u{2300}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{20E3}]/u
      const problems = []
      const scan = (label, text) => {
        const hit = EMOJI.exec(text)
        if (hit) {
          problems.push(
            `${label} 里出现了 emoji / 符号字符 \`${hit[0]}\` —— 用户 2026-09-23 明确要求` +
              '「不要使用 📝 这种图标，要使用别的更合理的正经 icon」：按钮的图标一律用 ' +
              '`<el-icon>` + `@element-plus/icons-vue` 的组件'
          )
        }
      }

      const cellTpl = stripBlockComments(readSource(TURN_ROLLBACK))
      scan(`${TURN_ROLLBACK} 的模板`, cellTpl)

      const ast = templateAst(STREAM)
      if (!ast) return problems.length ? problems.join('；') : '拿不到消息流的模板 AST'
      const buttons = []
      walkAst(ast, (n) => {
        if (n.type === 1 && (n.tag === 'button' || n.tag === 'el-button')) buttons.push(n)
      })
      // 反向对照：一个按钮都没扫到 = 扫描口径坏了，别当成通过
      if (!buttons.length) return '消息流模板里一个按钮都没扫到 —— 扫描口径坏了（别当成通过）'
      buttons.forEach((b, i) => scan(`${STREAM} 第 ${i + 1} 个按钮的文案`, nodeText(b)))

      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L79',
    file: STREAM,
    label:
      '「复制」复制的是哪段文本：用户消息那一格复制本条 `msg.content`，轮末那一格复制**这一轮 assistant 正文的拼接**',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到消息流的模板 AST'
      const src = readSource(STREAM)
      const forNode = firstNode(ast, (n) => n.type === 11)
      const loopEl = (forNode?.children || []).find((c) => c.type === 1)
      if (!loopEl) return '`v-for` 里找不到元素节点'

      const problems = []

      /* ① 用户消息那一格：链尾那个 `v-else` 分支里要有复制按钮，且复制的是本条 `msg.content` */
      let chain = null
      walkAst(loopEl, (n) => {
        if (chain || n.type !== 9) return
        const conds = (n.branches || []).map((b) =>
          String(b.condition?.loc?.source ?? b.condition?.content ?? '')
        )
        if (conds.some((c) => c.includes("'turn_end'"))) chain = n
      })
      if (!chain) return '找不到消息类型那条 `v-if / v-else-if` 链（先看 L69）'
      const last = chain.branches[chain.branches.length - 1]
      const lastCond = String(last.condition?.loc?.source ?? last.condition?.content ?? '')
      if (lastCond.trim()) {
        return '消息类型链的最后一条分支不是 `v-else` —— 这条判据要拿它当「用户消息那一格」，落点没了'
      }
      const copyBtn = firstNode(
        { children: last.children || [] },
        (n) => n.type === 1 && nodeClasses(n).includes('msg-copy-btn')
      )
      if (!copyBtn) {
        problems.push(
          '用户消息那一格没有复制按钮（`.msg-copy-btn`）—— 用户 2026-09-23 明确要求' +
            '「复制按钮 llm 底部要有，用户那边也要有」'
        )
      } else {
        const click = (copyBtn.props || []).find(
          (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'click'
        )
        const exp = expSource(click) || ''
        if (!/copyText\s*\(\s*msg\.content\s*\)/.test(exp)) {
          problems.push(
            `用户那一格的复制按钮复制的是 \`${exp}\` —— 要复制**这一条用户消息的** \`msg.content\`：` +
              '复制整轮（把 LLM 的回答也带走）或复制空值，用户都拿不到自己想要的那句话'
          )
        }
      }

      /* ② 轮末那一格：复制的是「这一轮 assistant 正文」的拼接 */
      const body = jsBodyOf(src, 'turnAnswerText')
      if (!body) {
        return problems.length
          ? problems.join('；')
          : '读不到 `turnAnswerText`（轮末复制按钮取正文的函数）的函数体 —— 这条判据没有落点'
      }
      if (!/props\.messages/.test(body)) {
        problems.push('`turnAnswerText` 没有从 `props.messages` 回溯 —— 它拿不到这一轮的消息')
      }
      if (!/['"]turn_end['"]/.test(body)) {
        problems.push(
          '`turnAnswerText` 没有认轮末标记 —— 划不出「这一轮」的边界：会把**上一轮**的回答也拼进来'
        )
      }
      if (!/role\s*===\s*['"]assistant['"]/.test(body)) {
        problems.push("`turnAnswerText` 没有按 `role === 'assistant'` 过滤 —— 会把用户自己的提问也复制进去")
      }
      if (!/!\s*[\w?.$]*\.type\b/.test(body)) {
        problems.push(
          '`turnAnswerText` 没有排除「非正文」的 assistant 消息（要写成 `!m.type` 这样的取反）—— ' +
            '工具卡片 / 过程提示 / 思考块会一起进剪贴板：用户要的是回答，不是一份执行日志'
        )
      }
      if (!/\.join\(/.test(body)) {
        problems.push('`turnAnswerText` 没有 join —— 一轮里有多条正文时只会复制到最后一条')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L80',
    file: STREAM,
    label:
      '回退后提问正文回到输入框：消息流 `defineExpose({ setInputText })` 且真的会写输入框；**两个**消费方都调它、都只喂服务端的 `userText`、且只在 `dropped` 时回填',
    fn: () => {
      const problems = []
      const src = readSource(STREAM)

      /* ① 暴露出来，而且真的会写那一个 ref */
      const expose = /defineExpose\(\{([^}]*)\}/.exec(src)
      if (!expose) {
        return '消息流里找不到 `defineExpose({...})` —— 页面没有任何办法把提问正文塞回输入框'
      }
      if (!/\bsetInputText\b/.test(expose[1])) {
        problems.push(
          '`defineExpose` 里没有 `setInputText` —— 页面拿不到这个方法（调用会被静默忽略，' +
            '表现为「回退后输入框还是空的」，且没有任何报错）'
        )
      }
      const body = jsBodyOf(src, 'setInputText')
      if (!body) {
        problems.push('读不到 `setInputText` 的函数体 —— 这条判据要有落点')
      } else if (!/inputContent\.value\s*=/.test(body)) {
        problems.push(
          '`setInputText` 没有写 `inputContent` —— 输入框不会变：`ChatInputArea` 的 `text` 就是它的 ' +
            '`modelValue`（写别的变量等于往一个没人看的地方赋值）'
        )
      }

      /* ② 两个消费方都接上（少接一处，那个入口就是哑的） */
      for (const rel of [CHAT, ASSISTANT]) {
        const s = readSource(rel)
        if (!s) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        // `?.` 也要认：页面里是 `streamRef.value?.setInputText?.(…)`
        if (!/setInputText\s*(?:\?\.)?\s*\(/.test(s)) {
          problems.push(`${rel} 没有调 \`setInputText(\` —— 这一侧「回退后提问自动回到输入框」是哑的`)
          continue
        }
        if (!/setInputText\s*(?:\?\.)?\s*\(\s*[^)]*userText/.test(s)) {
          problems.push(
            `${rel} 喂给 \`setInputText\` 的不是服务端给的 \`userText\` —— ` +
              '「这一轮问了什么」只有服务端从被摘掉的那条 user 消息里取得回来'
          )
        }
        if (!/if\s*\([^)]*dropped[^)]*\)[^\n]*setInputText/.test(s)) {
          problems.push(
            `${rel} 没有判 \`dropped\` 就回填 —— 只有「这一轮的对话**真的**被摘掉了」时才该回填：` +
              '否则消息还在，回填等于凭空多出一份提问'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L81',
    file: STREAM,
    label:
      '回退状态**按轮**：消息流只认 `rollbackStates[turnId]`，旧的单份 `turnRollback` / `rollbackState` 引用清零（两个消费方一起守）',
    fn: () => {
      const problems = []
      const src = readSource(STREAM)
      if (!/rollbackStates\s*:\s*\{\s*type:\s*Object/.test(src)) {
        problems.push('消息流没有 `rollbackStates` 这个 Object prop —— 按轮的状态进不来')
      }
      // ⚠️ 剥注释再查旧名字：注释里**必须**能写「旧版是一份扁平状态」这类说明
      if (/\brollbackState\b/.test(codeText(STREAM))) {
        problems.push(
          '消息流里还有旧的单份 prop `rollbackState` —— 每一轮都能点回退时它存不下两轮的结果' +
            '（判定落点见 L70 的 `:state` 半边）'
        )
      }

      for (const rel of [CHAT, ASSISTANT]) {
        const raw = readSource(rel)
        if (!raw) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        const s = codeText(rel)
        if (/\bturnRollback\b/.test(s)) {
          problems.push(
            `${rel} 还在用旧的单份状态 \`turnRollback\` —— 它只知道「最近一次回退是哪一轮的」：` +
              '两个回退动作连在一起时，前一轮的组件会显示后一轮的结果'
          )
        }
        if (!/\brollbackStates\b/.test(s)) {
          problems.push(`${rel} 没有从 composable 里取 \`rollbackStates\`（按轮的那份状态）`)
        }
        if (!/:\s*rollback-states\s*=/.test(raw)) {
          problems.push(`${rel} 的 \`AiChatStream\` 上没有 \`:rollback-states\` —— 消息流拿不到按轮的状态`)
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L82',
    file: STREAM,
    label:
      '回退结果区在**消息列表之外**（消息区与输入区之间的兄弟节点，不在 `.chat-messages` 里）且**可关闭**',
    fn: () => {
      const ast = templateAst(STREAM)
      if (!ast) return '拿不到消息流的模板 AST'
      let rootEl = null
      walkAst(ast, (n) => {
        if (!rootEl && n.type === 1 && nodeClasses(n).includes('ai-chat-stream')) rootEl = n
      })
      if (!rootEl) return '找不到 `.ai-chat-stream` 根节点'

      const kids = directElements(rootEl)
      const iMsgs = kids.findIndex((c) => nodeClasses(c).includes('chat-messages'))
      const iNotice = kids.findIndex((c) => c.tag === 'AgentRollbackNotice')
      const iInput = kids.findIndex((c) => c.tag === 'ChatInputArea')
      if (iMsgs < 0) return '找不到 `.chat-messages`（判据要有落点）'
      if (iNotice < 0) return '模板里没有渲染 `AgentRollbackNotice` —— 逐条清单没有任何落点'
      if (iInput < 0) return '找不到 `ChatInputArea`（判据要有落点）'

      const problems = []

      // ① **不在**消息列表里：回退成功时那一轮的消息会被整轮摘掉，
      //    挂在列表里的东西会跟着消失 / 挪位 —— 结果必须活在列表外面
      const inside = firstNode(
        { children: [kids[iMsgs]] },
        (n) => n.type === 1 && n.tag === 'AgentRollbackNotice'
      )
      if (inside) {
        problems.push(
          '结果区被渲染在 `.chat-messages` **里面** —— 回退时那一轮的消息会被整轮摘掉，' +
            '挂在列表里的结果会跟着它一起消失（用户只看到「消息少了一段」，不知道哪条没退成）'
        )
      }

      // ② 位置：消息区之后、输入区之前（贴着输入区，用户不用往回翻）
      if (!(iMsgs < iNotice && iNotice < iInput)) {
        problems.push(
          `结果区的位置不对（.chat-messages 第 ${iMsgs}、结果区第 ${iNotice}、输入区第 ${iInput} 个直接子节点）` +
            ' —— 要求：在消息区**之后**、输入区**之前**'
        )
      }

      // ③ 可关闭：组件里要有按钮抛 `close`，消息流要接上 `@close`
      const nAst = templateAst(NOTICE)
      if (!nAst) {
        problems.push(`拿不到 ${NOTICE} 的模板 AST`)
      } else {
        const nSrc = readSource(NOTICE)
        if (!/defineEmits\(\s*\[[^\]]*['"]close['"]/.test(nSrc)) {
          problems.push(`${NOTICE} 没有声明 \`close\` 事件 —— 结果区关不掉`)
        }
        const closeBtn = firstNode(nAst, (n) => {
          if (n.type !== 1 || n.tag !== 'button') return false
          const click = (n.props || []).find(
            (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'click'
          )
          const exp = expSource(click) || ''
          return /['"]close['"]/.test(exp) || /^\s*close\b/.test(exp)
        })
        if (!closeBtn) {
          problems.push(
            `${NOTICE} 里没有一个按钮抛 \`close\` —— 用户看完清单却关不掉它；` +
              '「必须有一个看得见且可关闭的地方」是这条需求的原文'
          )
        }
      }
      const noticeEl = kids[iNotice]
      const onClose = (noticeEl.props || []).find(
        (p) => p.type === 7 && p.name === 'on' && String(p.arg?.content) === 'close'
      )
      if (!onClose) {
        problems.push('消息流没有接 `@close` —— 结果区的关闭按钮点了没反应')
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L83',
    file: NOTICE,
    label:
      '结果区自己的高度账：`flex-shrink: 0` + `max-height` + `overflow-y: auto`（条目多时自己滚，不许把输入区挤出视线）',
    fn: () => {
      const rule = cssRule(cssOf(NOTICE), '.arn-panel')
      if (!rule) return `找不到 ${NOTICE} 里的 \`.arn-panel\` 规则 —— 结果区没有自己的高度约束`
      const problems = []

      const shrink = declValue(rule, 'flex-shrink')
      if (shrink !== '0') {
        problems.push(
          `\`.arn-panel\` 的 \`flex-shrink\` 是 ${shrink == null ? '(没写)' : shrink}（要求 0）—— ` +
            '它是消息区（`flex: 1`）与输入区（`flex-shrink: 0`）之间的**第三个** flex item：' +
            '允许被压缩时里面的文字会重叠'
        )
      }
      if (!declValue(rule, 'max-height')) {
        problems.push(
          '`.arn-panel` 没有 `max-height` —— 条目一多它就一直长高，把消息区挤成 0 高' +
            '（`.chat-messages` 是 `min-height: 0`，会被压没）'
        )
      }
      const oy = (declValue(rule, 'overflow-y') || '').trim()
      if (!/^(auto|scroll)$/.test(oy)) {
        problems.push(`\`.arn-panel\` 的 \`overflow-y\` 是 ${oy || '(没写)'} —— 条目多时要自己滚（auto/scroll）`)
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L84',
    file: CHAT,
    label:
      '回退成功要**看得见**：两个消费方都给她一句带条数的 toast（消息整轮被摘掉时这是唯一的反馈）',
    fn: () => {
      const problems = []
      for (const rel of [CHAT, ASSISTANT]) {
        const s = readSource(rel)
        if (!s) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        if (!/ElMessage\.success\(\s*`[^`]*reverted[^`]*`\s*\)/.test(s)) {
          problems.push(
            `${rel} 里没有一句**带条数**的成功提示（要 ` +
              '`ElMessage.success(...${...reverted}...)` 这样把服务端给的条数报出来）—— ' +
              '回退成功时那一轮的消息会被整轮摘掉，没有 toast 用户只知道「消息莫名少了一段」，' +
              '不知道是回退成功了还是出了问题'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L85',
    file: CHAT,
    label:
      '判据侧名单不许过期：`chat.vue` 从 `useAgentChat()` 解构出来的每个名字，`chatRuntime` 的手抄桩里都要有（少一个就红，且明说问题在判据这一侧）',
    fn: () => {
      const problems = []

      // ① 产品源码那一侧：解构出来的名字（`{ a, b: c }` 取的是**键** `a`）
      const src = readSource(CHAT)
      const m = /const\s*\{([\s\S]*?)\}\s*=\s*useAgentChat\s*\(/.exec(src)
      if (!m) {
        return '读不到 `const { … } = useAgentChat()` —— 解构的写法变了这条判据就得跟着改（先确认它还在不在）'
      }
      /**
       * ⚠️ 必须先剥注释再切分：解构块里**本来就带着一行注释**
       *    （`// 轮末回退（**按轮**）：…`，与 `rollbackStates` 同属一个逗号段）。
       *    不剥的话那一段会读成一串中文、被下面那句「读不出标识符」的守卫判红 ——
       *    **而这正是第一次跑变异时踩到的坑**：当时的写法是「读不出就默默丢弃」，
       *    于是 `rollbackStates` 从来没进过对账名单，M85a（把它从桩里删掉）**判绿** ——
       *    断言看着在守，实际上守不到。所以这里既剥注释、也把读不出的段**判红而不是丢掉**。
       */
      const block = m[1].replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
      const wanted = []
      const unreadable = []
      for (const piece of block.split(',')) {
        const name = piece.split(':')[0].trim()
        if (!name) continue
        if (/^[A-Za-z_$][\w$]*$/.test(name)) wanted.push(name)
        else unreadable.push(name.replace(/\s+/g, ' ').slice(0, 40))
      }
      if (unreadable.length) {
        return (
          `解构名单里有 ${unreadable.length} 段读不出标识符（${unreadable.join(' | ')}）—— ` +
          '这是**判据自己的扫描口径**问题（解构里出现了别名/注释之外的新写法），先修这条判据，别去改产品源码'
        )
      }
      if (!wanted.length) return '解构名单里一个名字都没读出来 —— 扫描口径坏了（别当成通过）'

      // ② 判据这一侧的手抄桩（由 `chatRuntime()` 执行后交出键表，别在这儿重新解析源码）
      const rt = chatRuntime()
      if (!rt.ok) return `chatRuntime 跑不起来（${rt.why}）—— 这条对账没有落点`
      if (!Array.isArray(rt.agentChatStubKeys) || !rt.agentChatStubKeys.length) {
        return 'chatRuntime 没有交出 `agentChatStubKeys` —— 那是这条判据的落点（补回去，别把这条断言写松）'
      }
      const stubbed = new Set(rt.agentChatStubKeys)
      const missing = wanted.filter((n) => !stubbed.has(n))
      if (missing.length) {
        problems.push(
          `\`chat.vue\` 从 \`useAgentChat()\` 里解构了 ${missing.length} 个名字，但 \`chatRuntime\` 的手抄桩里没有：` +
            `${missing.join('、')} —— **这是判据这一侧的名单过期，不是产品代码的问题**。` +
            '缺字段不会立刻炸（解构一个不存在的键只拿到 `undefined`），但只要哪条判据真去读它，' +
            '报错会是 `Cannot read properties of undefined` —— **那个报错指错边**。' +
            '修法是把名字补进 `chatRuntime` 的 `agentChatStub`，不要去改产品源码来迁就这份桩。'
        )
      }

      // ③ 反向半边：桩里不许留**产品源码已经没有的**旧名字。
      //    它比「缺字段」更阴：下一个人会以为「照桩写就行」，把已经作废的口径抄回产品里
      //    （单份的 `turnRollback` 就是这样 —— 逻辑面已经改成按轮的 `rollbackStates`）。
      if (stubbed.has('turnRollback')) {
        problems.push(
          '`chatRuntime` 的桩里还留着 `turnRollback`（单份回退状态）—— 产品源码里已经没有这个名字了' +
            '（2026-09-23 起是按轮的 `rollbackStates`）：桩比产品旧，会把旧口径当成「还能用的形状」传下去'
        )
      }
      return problems.length ? problems.join('；') : null
    }
  },
  /* =====================================================================
   * L86–L89：用户 2026-09-23 报的线上 bug「回退以后刷新页面，刚刚回退的对话内容还是存在」
   * =====================================================================
   * 根因：`rollbackTurn` 的会话 id 只来自 composable 内部那份「最近一次 `send()` 用过的」
   * 会话 id，而刷新之后消息是从**快照**复原的、根本没走 `send()` → 它是空串 →
   * 两个请求都带 `sessionId:''` → 服务端按空会话过滤命中 0 行、还回 200 成功 →
   * 本地消息被摘掉、服务端历史与快照没动 → 刷新又回来了。
   *
   * 修复分三层，每层一条判据（都是「真跑一遍」或「落结构」的判据，不是文案断言）：
   *   L86 页面把**当前显示的会话**的 id 交给 `rollbackTurn`（两个消费方都断）
   *   L87 老数据（服务端历史里没有这一轮标记）如实说一句，且照样进结果栏
   *   L88 两条新失败路径不许装成成功（界面这一侧）
   *   L89 逻辑面：`matched === 0` 不许拦「把这一轮从界面上移除」（跨面，见该条注释）
   */
  {
    id: 'L86',
    file: CHAT,
    label:
      '回退带上**当前显示的那个会话**的 id：两个消费方都把它作为第二个实参交给 `rollbackTurn`（刷新后 composable 内部那份「最近一次 send 的会话」是空串 —— 线上 bug 的根因）',
    fn: async () => {
      const problems = []

      /* ① 行为：真跑一遍 `chat.vue` 的 `onRollbackTurn`，看它到底交了几个实参、交的是哪个值。
       *    ⚠️ `rollbackTurn(turnId)` 与 `rollbackTurn(turnId, sessionId.value)` 在源码里
       *    都是「调了接口」—— 字符串断言分不出来，而这条正是这个 bug 的根因所在。 */
      const rt = chatRuntime()
      if (!rt.ok) {
        return `chatRuntime 跑不起来（${rt.why}）—— 这条判据没有落点（fail-closed，别当通过）`
      }
      const api = rt.api
      if (!Array.isArray(api.rollbackCalls) || typeof api.onRollbackTurn !== 'function') {
        return (
          'chatRuntime 没有交出 `rollbackCalls` / `onRollbackTurn` —— 这条判据的落点没了' +
          '（把记事本与 onRollbackTurn 补回 chatRuntime 的 return，别把断言写松）'
        )
      }
      // 会话 id 设成一个**认得出**的值：它必须原样出现在第二个实参上
      const marker = 'sess_judge_marker_L86'
      api.sessionId.value = marker
      await api.onRollbackTurn('t_judge_L86')
      const call = api.rollbackCalls[0]
      if (!call) {
        problems.push('`onRollbackTurn` 一次都没调 `rollbackTurn` —— 点了回退什么都不会发生')
      } else {
        if (String(call[0]) !== 't_judge_L86') {
          problems.push(`第一个实参应该是这一轮的 turnId（读到的是 \`${call[0]}\`）`)
        }
        if (call.length < 2) {
          problems.push(
            '`chat.vue` 调 `rollbackTurn` 时只传了 1 个实参（第二个 = 会话 id **没传**）—— ' +
              '刷新页面后 composable 内部那份「最近一次 send() 用过的会话 id」是**空串**' +
              '（消息是从快照复原的，没走 send），两个请求会带着 `sessionId:""` 发出去：' +
              '服务端按空会话过滤命中 0 行、还回 HTTP 200 成功 → 本地消息被摘掉、服务端历史与快照都没动 ' +
              '→ **刷新一下刚回退的那一轮又全回来了**（用户 2026-09-23 报的线上 bug）'
          )
        } else if (String(call[1]) !== marker) {
          problems.push(
            `第二个实参是 \`${call[1]}\`，而当时 \`sessionId.value\` 是 \`${marker}\` —— ` +
              '必须传**当前正在显示的那个会话**的 id（否则回退会打到别的会话、或空会话上）'
          )
        }
      }

      /* ② 结构：两个消费方交上去的第二个实参，都必须是「页面自己那个会话 ref」。
       *    签名的两条一起看（名字两个文件本来就不同：大屏页 `sessionId`、抽屉 `currentSessionId`）：
       *      · 它被赋值为某个会话对象的 `.sessionId`（页面知道「当前会话是谁」的唯一来源）；
       *      · 它被用来**载入当前显示的那段对话**（`loadHistory(...)` / `getConversationHistory(...)`）。
       *    ⚠️ 只断「有两个实参」远远不够：传 `''`、传别的会话、传 composable 里那份 `lastSessionId`
       *       都能满足「两个实参」，而那正是这个 bug 的几种错法。 */
      for (const rel of [CHAT, ASSISTANT]) {
        const src = readSource(rel)
        if (!src) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        /**
         * ⚠️ 扫描走 `codeText(rel)`（剥掉块注释 / HTML 注释 / 整行 `//` 注释）：
         *    注释里**必然**会出现 `rollbackTurn(turnId)` 这种反例说明（这两个文件的注释里
         *    正在讲这次 bug 的成因），用原始源码扫会把注释当成一处「只传了一个实参的调用」
         *    —— 那是判据自己的口径问题，报出来却像产品代码少传了参数。
         */
        const code = codeText(rel)
        const calls = callArgLists(code, 'rollbackTurn')
        if (!calls.length) {
          problems.push(`${rel} 里没有调 \`rollbackTurn(\` —— 这一侧的回退入口是哑的`)
          continue
        }
        const assigned = sessionIdRefs(rel)
        const displayed = displayedSessionRefs(rel)
        calls.forEach((args, i) => {
          const where = `${rel} 第 ${i + 1} 处 \`rollbackTurn(\``
          if (args.length < 2) {
            problems.push(`${where} 只传了 ${args.length} 个实参 —— 缺**第二个**（当前会话 id）`)
            return
          }
          const m = /^([A-Za-z_$][\w$]*)\s*\.value$/.exec(args[1])
          if (!m) {
            problems.push(
              `${where} 的第二个实参是 \`${args[1]}\` —— 要传页面自己那个持会话 id 的 ref（写法形如 \`<ref>.value\`）`
            )
            return
          }
          const name = m[1]
          if (!assigned.has(name)) {
            problems.push(
              `${where} 传的是 \`${name}\`，但它**不是**「被赋值为某个会话对象的 \`.sessionId\`」的那个 ref —— ` +
                '它不掌握「当前显示的是哪个会话」'
            )
          }
          if (!displayed.has(name)) {
            problems.push(
              `${where} 传的是 \`${name}\`，但页面**载入当前那段对话**用的不是它 —— ` +
                '会话 id 必须来自「正在显示的那个会话」，否则回退会打到别的会话上'
            )
          }
        })
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L87',
    file: NOTICE,
    label:
      '老数据（服务端历史里没有这一轮的轮次标记）如实说一句，且**照样进结果栏**：`historyUnmarked` 只对「老数据」为真（幂等重试 / 失败 / 字段缺失都不许说），结果栏里有一行专说这件事，消息流的入选条件也认它',
    fn: () => {
      const problems = []

      /* ① 判据函数本身：把用例喂进去，四种情况要分得出来。
       *    为什么必须真跑：`matched === 0` 与 `matched > 0` 两种分支在源码上都是几个 `&&`，
       *    「少看一个条件」「把 >0 写成 >=0」这类错法 grep 分不出来，喂用例才分得出。 */
      const rt = noticeRuntime()
      if (!rt.ok) {
        return `noticeRuntime 跑不起来（${rt.why}）—— 这条判据没有落点（fail-closed，别当通过）`
      }
      const f = rt.api.historyUnmarked
      if (typeof f !== 'function') {
        return (
          '结果栏脚本里找不到 `historyUnmarked` —— 「这一轮在服务端历史里没有轮次标记」这条判据' +
          '没有落点（提示那一行必须由它决定说不说）'
        )
      }
      /**
       * `dropped` 给两种形状各一份：服务端交出来的可能只是 boolean（「这一轮有没有从界面移除」），
       * 也可能是**行数**（`AgentDropTurnResult.dropped`）。判据只问「说不说这句话」，
       * 所以两种形状下期望值相同 —— 这也是这条判据敢于同时钉两种形状的理由。
       */
      const cases = [
        ['老数据：命中 0 行（`dropped` 是行数）', { ok: true, historyMatched: 0, dropped: 0 }, true],
        ['老数据：命中 0 行（`dropped` 是布尔）', { ok: true, historyMatched: 0, dropped: true }, true],
        ['幂等重试：上次已删过（命中 > 0）', { ok: true, historyMatched: 2, dropped: 0 }, false],
        ['失败（`ok === false`）', { ok: false, reason: '拿不到会话 id', historyMatched: 0, dropped: 0 }, false],
        ['字段读不到（逻辑面还没上 `historyMatched`）', { ok: true, dropped: 0 }, false]
      ]
      for (const [label, outcome, want] of cases) {
        let got
        try {
          got = !!f(outcome)
        } catch (e) {
          problems.push(`\`historyUnmarked\` 在「${label}」上抛错：${String(e?.message || e)}`)
          continue
        }
        if (got !== want) {
          problems.push(
            `\`historyUnmarked\` 在「${label}」上判成了 ${got}（要求 ${want}）—— ` +
              '「本来就是老数据」与「上次已经删过了」是两个相反的结论，判错会让用户看到的说明是假话'
          )
        }
      }

      /* ② 结果栏里**真有一行**专说这件事：一个带自己样式钩子的节点，条件是 `historyUnmarked(...)`，
       *    而且它渲染出了非空文案（不能只挂个 class 不画字）。
       *    ⚠️ 不锁死文案本身（文案会改），锁「这个分支存在 + 有独立落点 + 有话说」。 */
      const ast = templateAst(NOTICE)
      if (!ast) {
        problems.push(`拿不到 ${NOTICE} 的模板 AST`)
      } else {
        const nodes = []
        walkAst(ast, (n) => {
          if (n.type === 1 && ownConditionOf(ast, n)?.includes('historyUnmarked')) nodes.push(n)
        })
        if (!nodes.length) {
          problems.push(
            `${NOTICE} 的模板里没有一个节点按 \`historyUnmarked(...)\` 决定渲染 —— ` +
              '老数据那一轮进了结果栏却一句话都不说，用户只看到「已回退 0 项操作」，' +
              '读不出「历史那侧没删掉」这层意思'
          )
        }
        for (const n of nodes) {
          if (!nodeClasses(n).length) {
            problems.push(
              `${NOTICE} 里那个「旧数据」提示节点没有自己的 class —— 界面上要能单独认出这一行` +
                '（同一格里还画着 skipped / partial / failed 三张表）'
            )
          }
          if (!nodeText(n).trim()) {
            problems.push(`${NOTICE} 里那个「旧数据」提示节点是**空**的 —— 用户看不到任何字`)
          }
        }
      }

      /* ③ 消息流这一侧：老数据那一轮**要进结果栏**。
       *    ⚠️ 这是本条的**反向半边**：入选条件是「有清单**或**是老数据」，
       *       少写后半句时那一轮会被过滤掉 → 结果栏根本不会出现 → 上面那一行永远没机会渲染
       *       （字符串断言完全看不出来：`historyMatched` 在文件里照样有）。 */
      const streamSrc = readSource(STREAM)
      if (!streamSrc) {
        problems.push(`读不到 ${STREAM}`)
      } else {
        const body = jsBodyOf(streamSrc, 'rollbackNotices')
        if (!body) {
          problems.push('读不到 `rollbackNotices` 的函数体 —— 这条判据没有落点（别当成通过）')
        } else {
          const guard = body
            .split('\n')
            .filter((l) => /\bcontinue\b/.test(l))
            .join('\n')
          /**
           * 入选条件里要认「老数据」这一半。两种写法都算数（都很自然）：
           *   · 条件里直接写 `historyMatched`；
           *   · 条件里用一个**由 `historyMatched` 推出来的**局部量（如
           *     `const unmarked = o.ok === true && Number(o.historyMatched) === 0`）。
           * 只断「文件里出现过 historyMatched」是不够的 —— 那个字段完全可能只被读出来
           * 却没进入选条件（改一半的典型半成品），结果栏照样把这一轮过滤掉。
           */
          const names = [...guard.matchAll(/[A-Za-z_$][\w$]*/g)].map((x) => x[0])
          const hit =
            /\bhistoryMatched\b/.test(guard) ||
            names.some((n) =>
              new RegExp(`(?:const|let|var)\\s+${n}\\s*=[^\\n]*\\bhistoryMatched\\b`).test(body)
            )
          if (!guard.trim()) {
            problems.push(
              '`rollbackNotices` 里没有 `continue` —— 入选条件是别的写法？这条判据的落点没了（先确认）'
            )
          } else if (!hit) {
            problems.push(
              '`rollbackNotices` 的入选条件里没有 `historyMatched` —— ' +
                '「服务端历史里没有这一轮标记」的那一轮会被过滤掉，结果栏里那一行' +
                '**永远没有机会渲染**（用户以为回退没生效）'
            )
          }
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L88',
    file: TURN_ROLLBACK,
    label:
      '两条新失败路径（「不知道这一轮属于哪个会话」「快照没写成功」）不许装成成功：失败时不弹成功提示、不回填输入框（两个消费方 + 真跑 chat.vue），且轮末那一格的失败原因不受清单是否为空影响',
    fn: async () => {
      const problems = []

      /* ① 行为：真跑一遍 `chat.vue` 的 `onRollbackTurn`，喂两条失败结果。
       *    判据是**路径无关**的（只看 `ok === false`），所以给两种 reason 各跑一遍 ——
       *    逻辑面把新的失败路径加在哪一条上都落在这里，不用改这条判据。
       *    ⚠️ 下面是**代表性的**原因文本（真实文案由服务端/逻辑面给），判据不认这几句话，
       *       只认「失败不许走成功那条路」。 */
      const rt = chatRuntime()
      if (!rt.ok) {
        return `chatRuntime 跑不起来（${rt.why}）—— 这条判据没有落点（fail-closed，别当通过）`
      }
      const api = rt.api
      const paths = [
        ['不知道这一轮属于哪个会话', '拿不到会话 id，无法判断这一轮回退的是哪段对话'],
        ['写操作撤了、快照没写成功', '写操作已回退，但时间线快照没写成功（刷新后这一轮可能回来）']
      ]
      for (const [name, reason] of paths) {
        api.successMsgs.length = 0
        api.inputTexts.length = 0
        api.chatRef.value = { setInputText: (t) => api.inputTexts.push(String(t)) }
        api.rollbackOutcome.value = {
          ok: false, reason, reverted: 0,
          skipped: [], failed: [], partial: [],
          // 提问正文**有值**：这正是「失败却回填了输入框」那种错法能被抓住的原因
          userText: '这一轮的提问正文', dropped: true, historyMatched: 0
        }
        await api.onRollbackTurn('t_fail')
        if (api.successMsgs.length) {
          problems.push(
            `「${name}」这一条失败路径上弹了成功提示（\`${api.successMsgs.join(' / ')}\`）—— ` +
              '`ok === false` 时界面必须如实报失败：弹一句「已回退 N 项操作」会让用户以为成了，' +
              '而消息还在原地、服务端也可能只做了一半'
          )
        }
        if (api.inputTexts.length) {
          problems.push(
            `「${name}」这一条失败路径上把提问正文回填进了输入框 —— ` +
              '回填的前提是「这一轮**真的**从界面上移除了」，失败时消息还在，回填等于凭空多出一份提问'
          )
        }
      }

      /* ② 两个消费方（结构）：成功提示必须被 `r.ok` 把关 —— 少这一半，逻辑面把哪条路径
       *    报成 `ok === false` 都没用，界面照样报成功。 */
      for (const rel of [CHAT, ASSISTANT]) {
        const s = readSource(rel)
        if (!s) {
          problems.push(`读不到 ${rel}`)
          continue
        }
        if (!/if\s*\(\s*r\.ok\s*\)\s*ElMessage\.success\(/.test(s)) {
          problems.push(
            `${rel} 的成功提示没有被 \`r.ok\` 把关（要写成 \`if (r.ok) ElMessage.success(...)\`）—— ` +
              '失败的结果会被报成成功'
          )
        }
      }

      /* ③ 轮末那一格的失败原因：条件是 `status === 'fail'` + `outcome.reason`，
       *    **不许**再要求三份清单非空 —— 两条新失败路径（拿不到会话 id / 快照没写成功）
       *    都不带清单，加上去就等于让这两条路径在界面上**没有原因可看**
       *    （消息没被摘掉、那一格还在，所以这是它们唯一的落点）。 */
      const ast = templateAst(TURN_ROLLBACK)
      if (!ast) {
        problems.push(`拿不到 ${TURN_ROLLBACK} 的模板 AST`)
      } else {
        let reasonNode = null
        walkAst(ast, (n) => {
          if (reasonNode || n.type !== 1) return
          if (nodeClasses(n).includes('atr-reason')) reasonNode = n
        })
        if (!reasonNode) {
          problems.push(
            `${TURN_ROLLBACK} 里找不到失败原因那一行（\`.atr-reason\`）—— ` +
              '整轮失败时用户看不到服务端/逻辑面给的原因'
          )
        } else {
          const cond = ownConditionOf(ast, reasonNode) || ''
          if (!cond) {
            problems.push('失败原因那一行没有 `v-if` —— 没失败时它也会挂着（空行）')
          } else {
            if (!/status\s*===\s*'fail'/.test(cond)) {
              problems.push(`失败原因那一行的条件是 \`${cond}\` —— 少了 \`status === 'fail'\` 这一半`)
            }
            if (!/\breason\b/.test(cond)) {
              problems.push(`失败原因那一行的条件是 \`${cond}\` —— 没有要求 \`reason\` 有值`)
            }
            for (const k of ['failed', 'skipped', 'partial', 'reverted']) {
              if (new RegExp(`\\b${k}\\b`).test(cond)) {
                problems.push(
                  `失败原因那一行的条件里出现了 \`${k}\` —— 「不知道这一轮属于哪个会话」` +
                    '「快照没写成功」这两条新失败路径**都不带清单**，`' + cond + '` 会把它们' +
                    '的原因整句吞掉：用户只看到「回退」按钮变回可点，不知道发生了什么'
                )
              }
            }
          }
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L89',
    file: 'src/composables/useAgentChat.ts',
    label:
      '逻辑面（跨面判据）：`rollbackTurn` 收下页面给的会话 id，并且 `historyMatched === 0`（老数据）**不许**拦「把这一轮从界面上移除」',
    fn: () => {
      /**
       * ⚠️ 这条判据断的是**逻辑面**的文件（`fix-drop-fe-logic` 面的）。
       *    放在这里是因为它就是这次修复的另一半：页面把会话 id 传进来了（L86）、
       *    界面也会如实说话（L87），但逻辑面若在 `matched === 0` 上提前 `return`，
       *    老数据那一轮就**永远删不掉** —— 用户看到的还是「回退没生效」。
       *    判据红了先看是不是这里说的情况，别改 UI 去迁就。
       */
      const rel = 'src/composables/useAgentChat.ts'
      const src = readSource(rel)
      if (!src) return `读不到 ${rel} —— 这条判据没有落点（fail-closed，别当通过）`
      /**
       * ⚠️ 下面所有扫描都走 `codeText(rel)`（剥掉块注释 / HTML 注释 / 整行 `//` 注释）：
       *    这个文件的注释里**本来就在讨论** `historyMatched === 0`，将来还会有人写
       *    「不许写成 `if (historyMatched === 0) return`」这种反例说明 —— 不剥注释的话，
       *    那条判据会被**它自己的说明文字**判红（本仓 `codeText` 的注释里记着这个真踩过的坑）。
       */
      const code = codeText(rel)
      const problems = []

      /* ① 签名必须收第二个参数（页面按 L86 传的就是它） */
      if (!/rollbackTurn\s*=\s*async\s*\([^)]*\bsessionId\b/.test(code)) {
        problems.push(
          '`rollbackTurn` 的签名里没有 `sessionId` 这第二个参数 —— ' +
            '页面按「当前显示的会话」传进来的 id 会被**静默丢掉**（多传的实参 JS 不报错），' +
            '于是又回到「用 composable 内部那份（刷新后是空串）的会话 id」'
        )
      }

      /* ② 契约里要**声明成 number**（界面按它说那一句）。
       *    ⚠️ 不能只在整份文件里找 `historyMatched:`：改名的半成品会让结果对象里那个
       *    `historyMatched:` 仍然命中，判据判绿 —— 界面读的却是一个类型上不存在的字段。 */
      const ifaceAt = code.indexOf('interface TurnRollbackOutcome')
      let iface = ''
      if (ifaceAt >= 0) {
        const open = code.indexOf('{', ifaceAt)
        let depth = 0
        for (let i = open; i >= 0 && i < code.length; i++) {
          if (code[i] === '{') depth++
          else if (code[i] === '}') {
            depth--
            if (depth === 0) {
              iface = code.slice(open, i + 1)
              break
            }
          }
        }
      }
      if (!iface) {
        problems.push('找不到 `TurnRollbackOutcome` 的接口声明 —— 这条判据没有落点（别无声明就跳过）')
      } else if (!/historyMatched\s*:\s*number/.test(iface)) {
        problems.push(
          '`TurnRollbackOutcome` 里没有 `historyMatched: number` —— ' +
            '界面（L87）按它判断「服务端历史里有没有这一轮标记」，读不到就永远不说那句话：' +
            '用户看到「消息没了、历史里还在」只会以为回退没生效'
        )
      }

      /* ③ **反向判据**：`matched === 0` 不许拦任何一步。
       *    这一条正是 team-lead 点名的「不许出现 matched 为 0 就提前 return」。
       *    ⚠️ 判据落在「`historyMatched` **不出现在任何 `if` 的条件里**」，而**不**落在
       *    「`removeTurnMessages(` 之后才有 `historyMatched`」这种位置关系上：逻辑面刚把
       *    「摘本地消息」从 `removeTurnMessages(tid)` 改成 `locateTurn(tid)` + `messages.splice(...)`
       *    （先算后摘，为的是快照写失败时本地原封不动），位置类判据一次重构就失效，
       *    而「它是一个只读信息、不参与控制流」这个口径不随重构变。 */
      const body = jsBodyOf(code, 'rollbackTurn')
      if (!body) {
        problems.push('读不到 `rollbackTurn` 的函数体 —— 这条判据没有落点（别当成通过）')
      } else {
        if (!/outcome\.historyMatched\s*=/.test(body)) {
          problems.push(
            '`rollbackTurn` 没有把服务端给的命中行数记进结果（`outcome.historyMatched = …`）—— ' +
              '界面（L87）读不到它，就永远说不出「这一轮在服务端历史里没有标记」那句话'
          )
        }
        // 多行条件也认（`if (\n  …historyMatched…\n) {`）：`[^)]*` 配 `s` 标可以跨行
        const guard = /if\s*\([^)]*historyMatched/s.exec(body)
        if (guard) {
          problems.push(
            '`rollbackTurn` 拿 `historyMatched` 当了 `if` 的条件（`' +
              guard[0].replace(/\s+/g, ' ').slice(0, 60) +
              '`）—— 它是「这一轮在服务端历史里有没有轮次标记」的**信息**，不是「要不要回退」的判据：' +
              '旧数据在服务端删不动、本地照样要从消息流与快照里摘掉，拿它短路用户就只能一遍遍重点回退'
          )
        }
      }
      return problems.length ? problems.join('；') : null
    }
  },
  /* =====================================================================
   * L90–L91：线上 bug 的**第二半** —— 补写历史时必须带上本轮的 `turnId`
   * =====================================================================
   * `ai_chat_message.turn_id` 是服务端 `drop-turn` 的**唯一命中键**。两个消费方补写历史
   * （ds-free 链路后端不落库，前端在 `await send(...)` 之后自己写「提问 + 回复」两行）时
   * 没带它 → 落库的行 `turn_id=''`（真库实测：用户那条会话 32 行全是空串）→
   * 服务端按 `(user_id, session_id, turn_id)` 一行都匹配不到、还回 `code:200`（`dropped:0`）
   * → 界面把消息摘了、快照也重写了 → **刷新一次这一轮又回来**。
   *
   * 为什么拆成两条（而不是像 L86 那样在一个循环里断两个文件）：team-lead 要求
   * 「只摘 chat.vue 那处 → 只有 chat.vue 那半边红；只摘 AiAssistant 那处 → 只有它红」——
   * 一个 id 覆盖两侧时，红出来分不清是哪一侧漏了（半变异的隔离性就是为这个）。
   *   L90 = 大屏页：**真跑一遍** `handleSend`（读它交给服务端的请求体）+ 结构
   *   L91 = 抽屉：结构（该文件没有离线 harness，行为那半由 L90 在同一套 composable 上覆盖）
   */
  {
    id: 'L90',
    file: CHAT,
    label:
      '补写历史带上**本轮**的 `turnId`（大屏页）：真跑 `handleSend` 看请求体里的 `turnId` 是不是这一轮的 id，且解构里有 `currentTurnId`',
    fn: async () => {
      const problems = []

      /* ① 行为：真跑一遍 `handleSend`，读它交给 `saveConversationMessages` 的请求体。
       *    ⚠️ 只有真跑才分得出「body 里有个 turnId」与「那个 turnId 是**本轮**的」——
       *    自己 `newTurnId()` 生成一个同样的字段名，源码上长得一模一样，但服务端匹配不到
       *    （与 `turn_end` 标记上的 id 不是一个值）。 */
      const rt = chatRuntime()
      if (!rt.ok) {
        return `chatRuntime 跑不起来（${rt.why}）—— 这条判据没有落点（fail-closed，别当通过）`
      }
      const api = rt.api
      if (!Array.isArray(api.saveConvCalls) || typeof api.handleSend !== 'function') {
        return (
          'chatRuntime 没有交出 `saveConvCalls` / `handleSend` —— 这条判据的落点没了' +
          '（把记事本与 handleSend 补回 chatRuntime 的 return，别把断言写松）'
        )
      }
      const marker = 't_judge_L90'
      api.currentTurnId.value = marker
      // 造「走补写历史那一段」的前提：只有 ds-free + `asst_` 会话才补写
      api.model.value = 'deepseek-free'
      api.sessionId.value = 'asst_harness_L90'
      api.saveConvCalls.length = 0
      await api.handleSend({ content: '判据用提问' })
      const call = api.saveConvCalls[0]
      if (!call) {
        problems.push(
          '跑一遍 `handleSend` 之后一条 `saveConversationMessages` 都没发 —— ' +
            '补写历史那一段没走到（**先看是不是判据侧的前提没造对**：ds-free 模型名 / `asst_` 会话 id / ' +
            '桩里的 `send` 有没有返回非空 answer），再怀疑产品代码把这一段删了'
        )
      } else {
        const body = call[1] && typeof call[1] === 'object' ? call[1] : {}
        const got = String(body.turnId || '')
        if (got !== marker) {
          problems.push(
            `补写历史的请求体里 \`turnId\` 是 \`${got || '(没有这个字段)'}\`，而这一轮的 \`currentTurnId\` 是 \`${marker}\` —— ` +
              '落库的 `turn_id` 必须与服务端 `drop-turn` 的命中键逐字相同：空串 / 自己新生成的 id 都会让' +
              '那一轮**永远匹配不到**（界面却已经把它摘掉了，刷新一次就全回来）'
          )
        }
      }

      /* ② 结构半边（与 L91 同一套判据函数） */
      const struct = turnIdPersistProblems(CHAT)
      if (struct.length) problems.push(...struct)
      return problems.length ? problems.join('；') : null
    }
  },
  {
    id: 'L91',
    file: ASSISTANT,
    label:
      '补写历史带上**本轮**的 `turnId`（右侧抽屉）：解构里有 `currentTurnId`，且 `saveConversationMessages` 的请求体里那个 `turnId` 取自它',
    fn: () => {
      /**
       * ⚠️ 这条只断**结构**：`AiAssistant` 没有离线 harness（组件太大、依赖太多），
       *    而行为那半（「交上去的是不是本轮那个 id」）已在 L90 上对**同一套 composable**
       *    的同一个写法真跑过一遍。两侧共用一个判据函数 `turnIdPersistProblems`，
       *    所以两边不会出现「一边守得严、一边守得松」。
       *    ⚠️ 它的价值在**独立可红**：只摘这一处 `turnId`（或只删这里的 `currentTurnId` 解构）
       *    时，只有本条红 —— 这正是 team-lead 要求的「两个消费方各一半」。
       */
      const problems = turnIdPersistProblems(ASSISTANT)
      return problems.length ? problems.join('；') : null
    }
  }
]

if (!SKIP_LAYOUT) {
  console.log('\n布局结构断言（智能体页输入框吸底 + 工具栏合并）：')
  let layoutOk = 0
  for (const c of LAYOUT_CHECKS) {
    let msg = null
    try {
      // ⚠️ 这里必须 `await`：断言可以是 async 的 —— 有的判据要**真的跑一遍**产品源码里的
      //    异步函数（例如挂载期的取列表、粘贴导入的提交路径），光 await 同步返回的字符串没影响。
      //    本文件是 ESM，顶层 await 可用。
      msg = await c.fn()
    } catch (e) {
      msg = '断言自身出错：' + String(e?.message || e)
    }
    if (msg) fail(c.file, `${c.id} ${c.label} —— ${msg}`)
    else {
      layoutOk += 1
      ok(c.file, `${c.id} ${c.label}`)
    }
  }
  console.log(`布局断言：${layoutOk}/${LAYOUT_CHECKS.length} 通过`)
}

console.log(bad ? `\n${bad} 个问题` : '\n全部通过')
process.exit(bad ? 1 : 0)
