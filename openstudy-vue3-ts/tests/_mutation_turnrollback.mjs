/**
 * 变异跑手（可重复运行）—— 证明 L16 / L69–L89 这一族「会红」，并给出**隔离**证据。
 * 其中 L86–L89 是 2026-09-23 用户报的线上 bug「回退以后刷新页面，刚刚回退的对话内容还是存在」
 * 那一族：会话 id 由页面显式传入 / 老数据如实说一句 / 失败不许装成成功 / 逻辑面不许拿
 * `historyMatched` 短路。它们断在**三个文件**上（两个消费方 + 结果栏 + 消息流 + 逻辑面），
 * 所以半变异必须按文件分开打（M86x 打 chat.vue / AiAssistant，M87x 打结果栏与消息流，
 * M89x 打逻辑面）—— 只打一处就宣称「这条判据能红」是不够的。
 *
 * 其后 L90–L91 是同一个线上 bug 的**第二半**（补写历史没带 `turnId` → 落库 `turn_id=''`
 * → 服务端一行都匹配不到）：那两个消费方各一条判据，半变异 M90x / M91a 分别只打一侧，
 * 用来证明「只摘 chat.vue 那处 → 只有 L90 红；只摘 AiAssistant 那处 → 只有 L91 红」。
 *
 * ⚠️ 绝不就地改共享树：跑手自建一份 `D:/OpenStudy/apps/fastapi-v2/_mirror_turnrollback_ui/`
 *    镜像副本（`src/` 拷贝 + 指向真 node_modules 的 **junction**），每个变异前从真仓库
 *    拷一份干净文件过去，跑完做**双侧 md5 复核**，最后把镜像删掉。
 *    （就地变异会被 ——reload 的后端拿去服务用户浏览器，本仓 2026-09-21 实测过；
 *      删镜像前必须**先 unlink 那个 junction**，否则递归删会跟着删进真实目录。）
 *
 * 用法：cd apps/fastapi-v2/openstudy-vue3-ts && node tests/_mutation_turnrollback.mjs
 *
 * 输出三段：
 *   0) **同版本闸门** —— 真仓库与镜像都必须全绿，且判据条数一致（镜像/判据不同版本直接拒跑）
 *   1) 每个变异：期望红的判据 / 实际红的判据 / 是否「只红它那一半」+ 变异后的 md5
 *   2) 收尾：真仓库与镜像的 md5 复核（任一漂移就明说「别信上面的结论」）
 *
 * 每条半变异只动「一条断言的一半」：多数的期望集只有一条。
 * 两个**粗变异**（M10 整个分支删掉 / M11 组件换成 div）必然连带多条，表里如实标注。
 */
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'

const REAL = 'D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts'
const MIRROR = 'D:/OpenStudy/apps/fastapi-v2/_mirror_turnrollback_ui'

const STREAM = 'src/components/AiChatStream/index.vue'
const RB = 'src/components/AgentTurnRollback/index.vue'
const NOTICE = 'src/components/AgentRollbackNotice/index.vue'
const CHAT = 'src/views/front/agent/chat.vue'
const ASSIST = 'src/components/AiAssistant/index.vue'
/** 判据脚本自己 —— L85 的落点在这里（`chatRuntime` 的手抄桩） */
const HARNESS = 'tests/check_frontend_static.mjs'
/** 2026-09-23 新进 `DEFAULT_TARGETS` 的两个文件（只动**镜像里**的副本，真文件一个字节都不碰） */
const USE_AGENT_CHAT = 'src/composables/useAgentChat.ts'
const API_AI = 'src/api/ai/ai.ts'

/**
 * ⚠️ 只有这些文件会被「每次变异前从真仓库拷一份干净副本」+「跑完复核 md5」。
 *    凡是被某个变异改过的文件都必须在里面，否则上一次变异会**残留**到下一次（结论直接作废）。
 */
const MIRROR_FILES = [STREAM, RB, NOTICE, CHAT, ASSIST, HARNESS, USE_AGENT_CHAT, API_AI]

const md5 = (p) => crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex')

/**
 * 变异跑手必须先把**当前**的判据脚本同步进镜像。
 *
 * ⚠️ 镜像里的 `tests/` 必须**够用**：`DEFAULT_TARGETS` 里有个文件（`src/devtools/dfSelfCheck/
 *    runLoopGroup.ts`）会 import `../../../tests/df_cases.mjs` —— 镜像里少了它就会以
 *    「文件级：import 解析不到」变红，而那**不是产品代码的问题**，是镜像不完整。
 *    （这就是「只收 L 号」的旧跑手会漏掉的那类红：它把 `FILE` 失败读成「一条都不红」。）
 *
 * ⚠️ 判据脚本自己也在 `MIRROR_FILES` 里，所以每次变异前都会被 `restore()` 重新拷一遍 ——
 *    这里只负责**第一次**把镜像的那个目录填够。
 */
const syncHarness = () => {
  for (const rel of ['check_frontend_static.mjs', 'df_cases.mjs', 'df_cases.d.mts']) {
    fs.copyFileSync(path.join(REAL, 'tests', rel), path.join(MIRROR, 'tests', rel))
  }
}

/**
 * 换行符归一：真文件可能是 CRLF（`\r\n`）、也可能是 LF；JS 模板字面量里的锚点是 LF。
 * 不归一的话多行锚点**一次都命中不了**，跑手会以「变异没落地」中止（M1 / M6b 实测过）。
 */
const withEol = (text, eol) => (eol === '\r\n' ? text.split('\n').join('\r\n') : text)

/**
 * 删镜像。
 * ⚠️ **先 unlink `node_modules` 那个 junction**：直接递归删会跟着删进**真实**的 node_modules
 *    （本仓踩过这种删法）。junction 在 `lstat` 里是 symlink，unlink 只摘掉这个 reparse point。
 * ⚠️ 顺序不能换：`fs.rmSync(recursive)` 只在**先摘掉联接之后**才能落在镜像自己身上。
 */
const cleanMirror = (quiet = false) => {
  const nm = path.join(MIRROR, 'node_modules')
  try {
    if (fs.existsSync(nm) && fs.lstatSync(nm).isSymbolicLink()) fs.unlinkSync(nm)
  } catch (e) {
    console.log(`  ✗ node_modules 联接没能 unlink：${e.message}（镜像留在盘上，请手工删）`)
    return false
  }
  fs.rmSync(MIRROR, { recursive: true, force: true })
  if (!quiet) console.log(`  ✓ 镜像已删除：${MIRROR}`)
  return true
}

/**
 * 准备镜像目录（**自建**，跑完自己删）：
 *   · `src/` —— 真仓库那一份**拷贝**（要改的就是它；绝不改真仓库）；
 *   · `tests/` —— 只有判据脚本（`syncHarness` 每次开跑前再同步一遍）；
 *   · `node_modules` —— 指向真仓库的 **junction**（别拷，几百 MB）。
 */
const ensureMirror = () => {
  cleanMirror(true)
  fs.mkdirSync(MIRROR, { recursive: true })
  fs.cpSync(path.join(REAL, 'src'), path.join(MIRROR, 'src'), { recursive: true })
  fs.mkdirSync(path.join(MIRROR, 'tests'), { recursive: true })
  fs.copyFileSync(path.join(REAL, 'package.json'), path.join(MIRROR, 'package.json'))
  fs.symlinkSync(path.join(REAL, 'node_modules'), path.join(MIRROR, 'node_modules'), 'junction')
}

/* =====================================================================
 * 变异体：[id, 说明, [[文件, from, to], …], 期望红的判据]
 * ===================================================================== */
const MUTATIONS = [
  // ---------- 负对照 ----------
  ['M0', '负对照：在结果栏里加一行 HTML 注释（不该影响任何判据）', [[NOTICE, '<template>', '<!-- 变异负对照 -->\n<template>']], []],
  [
    'M0b',
    '负对照（专治「断言被自己的注释判红」）：往消息流里塞一句同时提到 `:active` 和 lastTurnId 的注释 —— L71 用了 codeText 剥注释，仍应全绿',
    [
      [
        STREAM,
        'const inputContent = ref(\'\')',
        '// 已删除的旧口径：`:active="…"`（只有最近一轮可点）与 computed lastTurnId 都不许回来\nconst inputContent = ref(\'\')'
      ]
    ],
    []
  ],

  // ---------- L16 / L69：挂载点与分支顺序 ----------
  ['M9', 'v-for 的内层 div 上删掉 :key（L16 ② 既有半边）', [[STREAM, ' :key="idx" :class=', ' :class=']], ['L16']],
  [
    'M1',
    '把 turn_end 分支挪到 assistant 正文分支**之后**（复现空气泡）',
    [
      [
        STREAM,
        `        <div v-else-if="msg.type === 'turn_end'" class="turn-end-slot">\n          <AgentTurnRollback :turn-id="msg.turnId" :state="rollbackStates[msg.turnId] || null"\n            :answer-text="turnAnswerText(msg.turnId)" :disabled="isGenerating"\n            @rollback="$emit('rollback-turn', msg.turnId)" @copy="copyText($event)" />\n        </div>\n`,
        ''
      ],
      [
        STREAM,
        '        <!-- user 消息 -->',
        `        <div v-else-if="msg.type === 'turn_end'" class="turn-end-slot">\n          <AgentTurnRollback :turn-id="msg.turnId" :state="rollbackStates[msg.turnId] || null"\n            :answer-text="turnAnswerText(msg.turnId)" :disabled="isGenerating"\n            @rollback="$emit('rollback-turn', msg.turnId)" @copy="copyText($event)" />\n        </div>\n        <!-- user 消息 -->`
      ]
    ],
    ['L69']
  ],
  [
    'M10',
    '整条 turn_end 分支删掉（= 改动前的树：标记掉进正文分支渲染成空气泡）——**粗变异，预期连带**',
    [
      [
        STREAM,
        `        <div v-else-if="msg.type === 'turn_end'" class="turn-end-slot">\n          <AgentTurnRollback :turn-id="msg.turnId" :state="rollbackStates[msg.turnId] || null"\n            :answer-text="turnAnswerText(msg.turnId)" :disabled="isGenerating"\n            @rollback="$emit('rollback-turn', msg.turnId)" @copy="copyText($event)" />\n        </div>\n`,
        ''
      ]
    ],
    // ⚠️ 第一次跑时这条我预测漏了 L79（实际还红了它）：L79 用 `turn_end` 分支来**定位**那条
    //    消息类型链，分支没了它连链都找不到。这不是缺陷，是这条粗变异的连带面 —— 如实记下来。
    ['L16', 'L69', 'L70', 'L71', 'L79']
  ],
  ['M11', 'turn_end 分支里不渲染组件（换成普通 div）——**粗变异，预期连带**', [[STREAM, '<AgentTurnRollback :turn-id="msg.turnId"', '<div :turn-id="msg.turnId"']], ['L16', 'L70', 'L71']],

  // ---------- L70：传下去的四个 prop / 两个事件（每个只动一半） ----------
  ['M70a', ':turn-id 不传这一轮的 id（传空串）', [[STREAM, ':turn-id="msg.turnId"', `:turn-id="''"`]], ['L70']],
  ['M70b', ':state 退回「一份扁平状态」（不按 turnId 取）', [[STREAM, ':state="rollbackStates[msg.turnId] || null"', ':state="rollbackStates || null"']], ['L70']],
  ['M70c', ':answer-text 不传这一轮的正文（传空串）', [[STREAM, ':answer-text="turnAnswerText(msg.turnId)"', `:answer-text="''"`]], ['L70']],
  ['M70d', ':disabled 常假（生成中也允许点）', [[STREAM, ':disabled="isGenerating"\n            @rollback=', ':disabled="false"\n            @rollback=']], ['L70']],
  ['M70e', '组件上的 @rollback 不接（点了没人转发）', [[STREAM, ` @rollback="$emit('rollback-turn', msg.turnId)"`, '']], ['L70']],
  ['M70f', '组件上的 @copy 不接（复制按钮点了没反应）', [[STREAM, ' @copy="copyText($event)"', '']], ['L70']],

  // ---------- L71（反转判据）：旧口径不许回来 ----------
  ['M71a', '把 `:active`（只有最近一轮可点）加回来', [[STREAM, ':state="rollbackStates[msg.turnId] || null"', ':state="rollbackStates[msg.turnId] || null" :active="true"']], ['L71']],
  ['M71b', '把算「最后一条 turn_end」的 computed 加回来', [[STREAM, "const inputContent = ref('')", "const lastTurnId = computed(() => '')\n\nconst inputContent = ref('')"]], ['L71']],

  // ---------- L72：四个字段真的画出来（在**消息列表之外**的结果栏里） ----------
  [
    'M72a',
    '结果栏里删掉 failed 那一段',
    [
      [
        NOTICE,
        `        <div v-if="entry.outcome.failed.length" class="arn-block">\n          <div class="arn-block-title">回退失败</div>\n          <div v-for="(item, i) in entry.outcome.failed" :key="'failed-' + i" class="arn-item">\n            <span v-if="opOf(item)" class="arn-op">{{ opOf(item) }}</span>\n            <span class="arn-text">{{ errorOf(item) }}</span>\n          </div>\n        </div>\n`,
        ''
      ]
    ],
    ['L72']
  ],
  ['M72b', 'reverted 不再渲染（只剩一句「已回退若干项」）', [[NOTICE, '已回退 {{ entry.outcome.reverted }} 项操作', '已回退若干项操作']], ['L72']],

  // ---------- L73：接线（组件 → 消息流 → 两个消费方） ----------
  ['M73a', 'chat.vue 的 AiChatStream 不接 @rollback-turn', [[CHAT, ' @rollback-turn="onRollbackTurn"', '']], ['L73']],
  ['M73b', '组件里那个回退按钮删掉 @click ——**粗变异，预期连带 L76**', [[RB, ' :disabled="!canClick" @click="onRollback"', ' :disabled="!canClick"']], ['L73', 'L76']],
  ['M73c', '组件脚本里不再 emit rollback ——**粗变异，预期连带 L76**', [[RB, "emit('rollback', props.turnId)", 'void props.turnId']], ['L73', 'L76']],

  // ---------- L74（反转判据）：每一轮都渲染 ----------
  ['M74a', '组件根节点又挂上 v-if（有的轮整格不渲染）', [[RB, '<div class="agent-rollback" :class=', '<div v-if="!disabled" class="agent-rollback" :class=']], ['L74']],
  ['M74b', '消息流里那一格的外边距归零被删（空的一格撑出 16px）', [[STREAM, '.message.msg-turn_end {\n  margin-bottom: 0;\n}', '.message.msg-turn_end {\n  margin-bottom: 16px;\n}']], ['L74']],

  // ---------- L75：两个边界 ----------
  ['M75a', '「没有可回退的操作」不再看 partial', [[RB, ' && !s.partial.length', '']], ['L75']],
  ['M75b', '服务端 reason 被换成一句自己编的话', [[RB, '{{ outcome.reason }}', `{{ '回退失败' }}`]], ['L75']],

  // ---------- L76：两个按钮（结构） ----------
  [
    'M76a',
    '把「复制」按钮整块删掉（只剩一个按钮）',
    [
      [
        RB,
        `\n        <button type="button" class="atr-btn is-copy" :disabled="!canCopy" @click="onCopy">\n          <el-icon class="atr-icon">\n            <CopyDocument />\n          </el-icon>\n          <span>复制</span>\n        </button>\n`,
        '\n'
      ]
    ],
    ['L76']
  ],
  ['M76b', '复制按钮改成 emit rollback（两个按钮都成回退）', [[RB, "  emit('copy', props.answerText)", "  emit('rollback', props.turnId)"]], ['L76']],

  // ---------- L77：图标名必须真的存在 ----------
  [
    'M77a',
    '模板里把图标名写错（import 没改）—— 运行时静默渲染成空，只有这条判据抓得住',
    [[RB, '            <CopyDocument />\n          </el-icon>\n          <span>复制</span>', '            <CopyDocuments />\n          </el-icon>\n          <span>复制</span>']],
    ['L77']
  ],
  ['M77b', 'import 与模板**一起**写成不存在的图标名（专测「对着包的导出清单核名字」那一半）', [[RB, "import { CopyDocument, RefreshLeft } from '@element-plus/icons-vue'", "import { CopyDocuments, RefreshLeft } from '@element-plus/icons-vue'"]], ['L77']],
  ['M77c', '回退按钮里的 el-icon 删掉（按钮只剩文字）', [[RB, '          <el-icon class="atr-icon">\n            <RefreshLeft />\n          </el-icon>\n', '']], ['L77']],

  // ---------- L78：按钮区不许用 emoji ----------
  ['M78a', '轮末复制按钮的文案里塞一个 📋', [[RB, '<span>复制</span>', '<span>📋 复制</span>']], ['L78']],
  [
    'M78b',
    '用户消息复制按钮的文案里塞一个 📋（测消息流那一半的 nodeText 扫描）',
    [[STREAM, '            <span class="mc-label">复制</span>\n          </el-button>\n        </div>', '            <span class="mc-label">📋 复制</span>\n          </el-button>\n        </div>']],
    ['L78']
  ],

  // ---------- L79：复制的是哪段文本 ----------
  ['M79a', '用户那一格的复制按钮不复制本条 content（复制空串）', [[STREAM, `<el-button v-if="msg.content && msg.content.trim()" class="msg-copy-btn" size="small" text\n            @click="copyText(msg.content)">`, `<el-button v-if="msg.content && msg.content.trim()" class="msg-copy-btn" size="small" text\n            @click="copyText('')">`]], ['L79']],
  ['M79b', '轮末复制不再过滤 assistant（把用户提问和工具卡片也拼进去）', [[STREAM, "if (m && m.role === 'assistant' && !m.type && String(m.content || '').trim()) {", "if (m && !m.type && String(m.content || '').trim()) {"]], ['L79']],

  // ---------- L80：提问正文回填输入框 ----------
  ['M80a', 'defineExpose 不再暴露 setInputText（页面喊了没人应）', [[STREAM, 'defineExpose({ scrollToBottom, messagesRef, setInputText })', 'defineExpose({ scrollToBottom, messagesRef })']], ['L80']],
  ['M80b', 'chat.vue 不再回填输入框', [[CHAT, '  if (r.ok && r.dropped && r.userText) chatRef.value?.setInputText?.(r.userText)\n', '']], ['L80']],
  ['M80c', 'AiAssistant 不再回填输入框', [[ASSIST, '  if (r.ok && r.dropped && r.userText) chatRef.value?.setInputText?.(r.userText)\n', '']], ['L80']],
  ['M80d', 'chat.vue 回填前不判 dropped（消息还在也回填）', [[CHAT, 'if (r.ok && r.dropped && r.userText) chatRef.value?.setInputText?.(r.userText)', 'if (r.ok && r.userText) chatRef.value?.setInputText?.(r.userText)']], ['L80']],

  // ---------- L81：状态按轮，旧引用清零 ----------
  ['M81a', 'chat.vue 把 `:rollback-states` 写回单份的 `:rollback-state`', [[CHAT, ':rollback-states="rollbackStates"', ':rollback-state="rollbackStates"']], ['L81']],
  ['M81b', '消息流把按轮的 prop 改回单份名字 rollbackState', [[STREAM, 'rollbackStates: { type: Object, default: () => ({}) }', 'rollbackState: { type: Object, default: () => ({}) }']], ['L81']],

  // ---------- L82：结果区在列表外 + 可关闭 ----------
  [
    'M82a',
    '把结果栏挪进消息列表里（回退时它会跟着那一轮一起消失）',
    [
      [STREAM, `    <AgentRollbackNotice v-if="rollbackNotices.length && !noticeClosed" :entries="rollbackNotices"\n      @close="noticeClosed = true" />\n`, ''],
      [
        STREAM,
        '      </div>\n    </div>',
        `      </div>\n      <AgentRollbackNotice v-if="rollbackNotices.length && !noticeClosed" :entries="rollbackNotices"\n        @close="noticeClosed = true" />\n    </div>`
      ]
    ],
    ['L82']
  ],
  ['M82b', '消息流不接 @close（结果区关不掉）', [[STREAM, '\n      @close="noticeClosed = true" />', ' />']], ['L82']],
  ['M82c', '结果栏自己的关闭按钮删掉', [[NOTICE, `      <button type="button" class="arn-close" title="关闭" aria-label="关闭" @click="$emit('close')">\n        <el-icon>\n          <Close />\n        </el-icon>\n      </button>\n`, '']], ['L82']],

  // ---------- L83：结果区的高度账 ----------
  ['M83a', '结果栏允许被压缩（flex-shrink: 1）', [[NOTICE, '  flex-shrink: 0;\n  margin: 0 12px 6px;', '  flex-shrink: 1;\n  margin: 0 12px 6px;']], ['L83']],
  ['M83b', '结果栏没有 max-height（能一直长高，把消息区挤成 0）', [[NOTICE, '  max-height: min(32vh, 220px);\n', '']], ['L83']],
  ['M83c', '结果栏不自己滚（overflow-y: visible）', [[NOTICE, '  overflow-y: auto;\n  box-sizing: border-box;', '  overflow-y: visible;\n  box-sizing: border-box;']], ['L83']],

  // ---------- L84：成功要看得见 ----------
  ['M84a', 'chat.vue 的成功提示不带条数', [[CHAT, 'ElMessage.success(`已回退 ${r.reverted} 项操作`)', "ElMessage.success('已回退')"]], ['L84']],
  // ⚠️ M84b 的期望集 2026-09-23 从 `[L84]` 扩成 `[L84,L88]`：新增的 L88 也要
  //    断「两个消费方的成功提示存在且被 `r.ok` 把关」（失败不许装成成功），
  //    所以整句删掉时它**必然**一起红。这是断言族变大的连带，**不是**放宽了哪一条。
  ['M84b', 'AiAssistant 的成功提示整句删掉', [[ASSIST, '  if (r.ok) ElMessage.success(`已回退 ${r.reverted} 项操作`)\n', '']], ['L84', 'L88']],

  // ---------- L85：判据侧名单不许过期（`chatRuntime` 的手抄桩 vs chat.vue 的解构） ----------
  ['M85a', '把 `rollbackStates` 从 chatRuntime 的手抄桩里删掉（名单落在产品源码后面）', [[HARNESS, '    rollbackStates: refStub({}),\n', '']], ['L85']],
  ['M85b', '把旧的单份 `turnRollback` 写回桩里（桩比产品源码旧 —— 会把作废的口径传下去）', [[HARNESS, '    rollbackStates: refStub({}),', '    turnRollback: refStub({}),\n    rollbackStates: refStub({}),']], ['L85']],
  ['M85c', '把 `agentChatStubKeys` 从 chatRuntime 的返回里删掉（落点没了 → fail-closed 判红）', [[HARNESS, 'return { ok: true, api, agentChatStubKeys: Object.keys(agentChatStub) }', 'return { ok: true, api }']], ['L85']],

  // ---------- 新进 DEFAULT_TARGETS 的两个文件：**真的**被检查了吗 ----------
  // 只改**镜像里**的副本（真文件由 md5 复核兜着）。这类失败**没有 L 号**（文件级：语法 / import 路径），
  // 记成伪 id `FILE` —— 旧版跑手只收 L 号，会把这种红读成「一条都不红」（假绿）。
  ['M86', '把镜像里 `useAgentChat.ts` 的一条 import 路径改坏（证明它进了检查清单）', [[USE_AGENT_CHAT, "from '@/api/ai/ai'", "from '@/api/ai/aiMISSING'"]], ['FILE']],
  ['M86b', '把镜像里 `api/ai/ai.ts` 的一条 import 路径改坏（同上，证明它也被检查）', [[API_AI, "import request from '@/utils/request'", "import request from '@/utils/requestMISSING'"]], ['FILE']],

  // ---------- L86–L89：线上 bug「回退以后刷新，刚刚回退的对话内容还是存在」 ----------
  // 三层各一条：会话 id 由页面显式传入（L86）/ 老数据如实说一句（L87）/
  // 两条新失败路径不许装成成功（L88）/ 逻辑面不许拿 `historyMatched` 短路（L89）。
  ['M86c', 'chat.vue 不传第二个实参（会话 id 又变成「composable 内部那份」= 刷新后空串，线上 bug 的原形态）', [[CHAT, 'rollbackTurn(turnId, sessionId.value)', 'rollbackTurn(turnId)']], ['L86']],
  ['M86d', 'chat.vue 传空串当会话 id（服务端按空会话过滤 → 命中 0 行还回 200 = 假成功）', [[CHAT, 'rollbackTurn(turnId, sessionId.value)', "rollbackTurn(turnId, '')"]], ['L86']],
  ['M86e', 'chat.vue 传 ref 本身、漏了 `.value`（交给服务端的是一个对象，不是会话 id）', [[CHAT, 'rollbackTurn(turnId, sessionId.value)', 'rollbackTurn(turnId, sessionId)']], ['L86']],
  ['M86f', 'AiAssistant 不传第二个实参（第二个消费方漏接）', [[ASSIST, 'rollbackTurn(turnId, currentSessionId.value)', 'rollbackTurn(turnId)']], ['L86']],
  [
    'M87a',
    '消息流的入选条件不再认「老数据」那一轮 —— 它被过滤掉，结果栏里那句话**永远没机会渲染**',
    [[STREAM, 'const unmarked = o.ok === true && Number(o.historyMatched) === 0', 'const unmarked = false']],
    ['L87']
  ],
  [
    'M87b',
    '老数据判据少看一半（不再要求 `historyMatched === 0`）—— 幂等重试被说成「旧数据」',
    [[NOTICE, '  if (Number(o.historyMatched) !== 0) return false\n', '']],
    ['L87']
  ],
  [
    'M87c',
    '老数据判据判反（`=== 0` 才 return false）',
    [[NOTICE, 'if (Number(o.historyMatched) !== 0) return false', 'if (Number(o.historyMatched) === 0) return false']],
    ['L87']
  ],
  [
    'M87d',
    '结果栏里那一行提示整块删掉（这一轮进了结果栏，却一句话都不说）',
    [
      [
        NOTICE,
        '        <div v-if="historyUnmarked(entry.outcome)" class="arn-old">\n          已从界面移除；但服务端历史里这一轮没有轮次标记（旧数据），删不掉历史里那几行。\n        </div>\n',
        ''
      ]
    ],
    ['L87']
  ],
  ['M88a', 'chat.vue 的成功提示不再被 `r.ok` 把关（失败也报「已回退 N 项操作」）', [[CHAT, 'if (r.ok) ElMessage.success(', 'if (r) ElMessage.success(']], ['L88']],
  ['M88b', 'AiAssistant 的成功提示不再被 `r.ok` 把关', [[ASSIST, 'if (r.ok) ElMessage.success(', 'if (r) ElMessage.success(']], ['L88']],
  ['M88c', 'chat.vue 回填输入框时不再要求 `ok`（失败也把提问塞回输入框）', [[CHAT, 'if (r.ok && r.dropped && r.userText) chatRef', 'if (r.dropped && r.userText) chatRef']], ['L88']],
  [
    'M88d',
    '轮末那一格的失败原因被加上「必须有三份清单之一」—— 两条新失败路径都没有清单，原因整句看不到',
    [[RB, `v-if="status === 'fail' && outcome && outcome.reason"`, `v-if="status === 'fail' && outcome && outcome.reason && outcome.failed.length"`]],
    ['L88']
  ],
  [
    'M89a',
    '逻辑面 `rollbackTurn` 不再收第二个参数（页面传进来的会话 id 被静默丢掉）',
    [
      [
        USE_AGENT_CHAT,
        '  const rollbackTurn = async (\n    turnId: string,\n    sessionId?: string\n  ): Promise<TurnRollbackOutcome> => {',
        '  const rollbackTurn = async (\n    turnId: string\n  ): Promise<TurnRollbackOutcome> => {'
      ]
    ],
    ['L89']
  ],
  [
    'M89b',
    '逻辑面不再把 `historyMatched` 记进结果（界面永远读不到 → 那句说明永远不说）',
    [[USE_AGENT_CHAT, '      outcome.historyMatched = Number(dr.matched) || 0', '      void dr']],
    ['L89']
  ],
  [
    'M89c',
    '逻辑面在 `matched === 0` 上提前 return（老数据永远删不掉 —— team-lead 点名的反向判据）',
    [
      [
        USE_AGENT_CHAT,
        '      outcome.historyMatched = Number(dr.matched) || 0',
        '      outcome.historyMatched = Number(dr.matched) || 0\n      if (outcome.historyMatched === 0) return outcome'
      ]
    ],
    ['L89']
  ],
  [
    'M89d',
    '契约里把 `historyMatched` 改名（界面读的是一个类型上不存在的字段）',
    [[USE_AGENT_CHAT, '  historyMatched: number', '  historyMatchedRenamed: number']],
    ['L89']
  ],
  [
    'M0c',
    '负对照（专治「断言被自己的注释判红」）：三处都塞进**同时提到** `rollbackTurn(turnId)` / `historyMatched === 0` / `if (historyMatched === 0) return` 的注释 —— L86 / L87 / L89 只认代码，仍应全绿',
    [
      [
        CHAT,
        'const chatRef = ref<any>(null)',
        '// 反例说明：以前就是 `rollbackTurn(turnId)` 一个参数（会话 id 取自「最近一次 send」）\nconst chatRef = ref<any>(null)'
      ],
      [
        NOTICE,
        "defineEmits(['close'])",
        '// 反例说明：判据不许写成 `if (historyMatched === 0) return`（那是「老数据不许回退」的错口径）\ndefineEmits([\'close\'])'
      ],
      [
        USE_AGENT_CHAT,
        '  const rollbackTurn = async (',
        '// 反例说明：`if (historyMatched === 0) return outcome` 是**禁止**的写法\n  const rollbackTurn = async ('
      ]
    ],
    []
  ],

  /* ---------- L90–L91：补写历史要带上本轮的 `turnId`（线上 bug 的第二半） ----------
   * 两侧各三条半变异 + 一条负对照，**必须按侧隔离**（team-lead 的明确要求）：
   * 只摘 chat.vue 那处 → 只有 L90 红；只摘 AiAssistant 那处 → 只有 L91 红。 */
  ['M90a', 'chat.vue 补写历史的请求体里摘掉 `turnId`（落库 `turn_id` 又是空串）', [[CHAT, '          turnId: turnIdOfThisSend\n', '']], ['L90']],
  ['M91a', 'AiAssistant 补写历史的请求体里摘掉 `turnId`', [[ASSIST, '          turnId: turnIdOfThisSend\n', '']], ['L91']],
  [
    'M90f',
    '**两侧一起**摘掉 `turnId`（隔离性对照：一条半变异只该点亮它那一侧，两条一起摘就该两条都红）',
    [
      [CHAT, '          turnId: turnIdOfThisSend\n', ''],
      [ASSIST, '          turnId: turnIdOfThisSend\n', '']
    ],
    ['L90', 'L91']
  ],
  [
    'M91b',
    'AiAssistant 不再从 composable 解构 `currentTurnId`（抽屉那一侧的「解构」半边）',
    [[ASSIST, '  currentTurnId: agentCurrentTurnId,\n', '']],
    ['L91']
  ],
  [
    'M90b',
    'chat.vue 的 `turnId` 自己新生成一个（字段在、值与 `turn_end` 标记对不上 → 回退照样匹配不到）',
    [[CHAT, 'turnId: turnIdOfThisSend', 'turnId: String(Date.now())']],
    ['L90']
  ],
  [
    // ⚠️ 这条**不隔离**，如实记：摘掉 `currentTurnId` 的解构后，`chatRuntime` 那句
    //    `return { … currentTurnId … }` 先炸（判据侧返回名单点了产品已无的标识符），
    //    于是所有用 `chatRuntime()` 的判据一起红：L29–L32 / L85 / L86 / L88 都是**连带**，
    //    真正要证明的只有 L90（它自己的解构判据 + 运行期抛 ReferenceError）。
    //    报文已改成「这是判据侧名单过期，不是产品代码引用了未定义的变量」（见 chatRuntime 的 catch），
    //    所以连带红的那些人不会被误导到产品代码上去。
    'M90c',
    'chat.vue 不再从 composable 解构 `currentTurnId`（页面手上根本没有本轮的 id）——**粗变异，预期连带用 chatRuntime 的几条**',
    [[CHAT, '  // 本轮的轮次 id（`send()` 开头生成、`turn_end` 标记里那个）：补写历史时要带上它\n  currentTurnId,\n', '']],
    ['L90', 'L85', 'L29', 'L30', 'L31', 'L32', 'L86', 'L88']
  ],
  [
    'M90d',
    'chat.vue 把「抓本轮 id」挪到 `await metasReady` **之后**（那一窗里再发一次就会贴错轮次标记）',
    [
      [CHAT, "  const turnIdOfThisSend = String(currentTurnId.value || '')\n\n", ''],
      [
        CHAT,
        '      await metasReady\n',
        "      await metasReady\n      const turnIdOfThisSend = String(currentTurnId.value || '')\n"
      ]
    ],
    ['L90']
  ],
  [
    'M90e',
    'chat.vue 在请求体里**现读** `currentTurnId.value`（不在 await 之前先抓成局部量）',
    [[CHAT, 'turnId: turnIdOfThisSend', 'turnId: String(currentTurnId.value || \'\')']],
    ['L90']
  ],
  [
    'M0d',
    '负对照（补写历史那两处）：在 `handleSend` 上方各塞一整行注释，里面**照抄** `saveConversationMessages(sessionId.value, { userMessage, assistantMessage, turnId: currentTurnId.value })` —— L90 / L91 只认代码，仍应全绿',
    [
      [
        CHAT,
        'const handleSend = async ({ content }: { content: string }) => {',
        '// 反例说明（旧口径）：以前是 `saveConversationMessages(sessionId.value, { userMessage, assistantMessage }, userId.value)` —— 没有 turnId\nconst handleSend = async ({ content }: { content: string }) => {'
      ],
      [
        ASSIST,
        '  const answer = await agentSend({',
        '  // 反例说明（旧口径）：以前是 `saveConversationMessages(currentSessionId.value, { userMessage, assistantMessage }, userId.value)` —— 没有 turnId\n  const answer = await agentSend({'
      ]
    ],
    []
  ]
]

// ---------------------------------------------------------------------------
// 0) 记下真仓库的 md5（跑完复核：真仓库一个字节都不该动）
// ---------------------------------------------------------------------------
const pristine = {}
for (const rel of MIRROR_FILES) pristine[rel] = md5(path.join(REAL, rel))

const restore = () => {
  for (const rel of MIRROR_FILES) fs.copyFileSync(path.join(REAL, rel), path.join(MIRROR, rel))
}

/** 跑一遍某个目录里的检查器，返回红的判据 id 列表 */
const runChecker = (cwd) => {
  let out = ''
  let code = 0
  try {
    out = execFileSync(process.execPath, ['tests/check_frontend_static.mjs'], {
      cwd,
      encoding: 'utf8',
      maxBuffer: 64 * 1024 * 1024
    })
  } catch (e) {
    out = String(e.stdout || '')
    code = e.status ?? 1
  }
  const fails = [...out.matchAll(/\[FAIL\]\s+(\S+)\s+->\s+([^\n]*)/g)].map((m) => ({ file: m[1], msg: m[2] }))
  // 布局断言：`[FAIL] <file> -> L70 …`
  const reds = fails.map((f) => /^(L\d+)/.exec(f.msg)?.[1]).filter(Boolean)
  // ⚠️ 文件级（语法 / import 路径）的失败**没有 L 号**，只按 L 号收会**整片漏掉** ——
  //    那种失败在旧版跑手里会被读成「一条都不红」＝假绿。用伪 id `FILE` 记进表里。
  const fileFails = fails.filter((f) => !/^L\d+/.test(f.msg)).map((f) => `${f.file}: ${f.msg.slice(0, 60)}`)
  const line = /布局断言：(\d+)\/(\d+) 通过/.exec(out)
  // 「全绿」不能只看 L 号：还要看脚本自己那句话（`N 个问题` / `全部通过`）
  const clean = /全部通过/.test(out) && !/\d+ 个问题/.test(out)
  return {
    reds: [...reds, ...fileFails.map(() => 'FILE')],
    fileFails,
    clean,
    line: line ? line[0] : '(没跑到布局断言)',
    code,
    total: line ? Number(line[2]) : -1
  }
}

console.log('=== 0) 同版本闸门：真仓库与镜像必须都全绿，且判据条数一致 ===')
console.log('  · 重建镜像（src 拷贝 + node_modules junction）')
ensureMirror()
syncHarness()
restore()
const real = runChecker(REAL)
const control = runChecker(MIRROR)
console.log(`  真仓库：${real.line}   红的判据：[${real.reds.join(', ')}]   全绿=${real.clean}`)
console.log(`  镜  像：${control.line}   红的判据：[${control.reds.join(', ')}]   全绿=${control.clean}`)
if (real.fileFails.length || control.fileFails.length) {
  console.log('  文件级失败明细：')
  for (const f of [...real.fileFails, ...control.fileFails]) console.log(`    · ${f}`)
}
if (real.reds.length || control.reds.length || !real.clean || !control.clean) {
  console.log('  ✗ 有一侧本来就不绿（含文件级失败）—— 先修干净，别继续（变异结论会不可信）')
  process.exit(1)
}
if (real.total < 0 || real.total !== control.total) {
  console.log(`  ✗ 判据条数对不上（真=${real.total} 镜像=${control.total}）—— 镜像/判据不同版本，拒跑`)
  process.exit(1)
}

const rows = []
/**
 * 只跑名单里的变异（可选）：`node tests/_mutation_turnrollback.mjs M90a,M91b`
 *
 * 用途：整张表跑一轮约 8 分钟。**已经跑过整张表之后**再补一两条变异时，
 * 用过滤模式补跑那两条即可（闸门段照样跑 —— 它才是「这一轮测的是不是当前这棵树」的依据）。
 * ⚠️ 过滤模式**不能**代替整张表：`chat.vue` / `AiAssistant` 这类被测文件字节一变，
 *    旧的绿红就绑在旧 md5 上了，必须整张表重跑（见 `testing.md`）。
 */
const ONLY = (process.argv.slice(2).find((a) => !a.startsWith('--')) || '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean)
if (ONLY.length) {
  const known = new Set(MUTATIONS.map((m) => m[0]))
  const unknown = ONLY.filter((id) => !known.has(id))
  if (unknown.length) {
    console.log(`✗ --only 里有不存在的变异 id：${unknown.join('、')}（先确认是不是写错了，别当「跑过了」）`)
    process.exit(1)
  }
  console.log(`\n（过滤模式：只跑 ${ONLY.join('、')}；整张表共 ${MUTATIONS.length} 条）`)
}
for (const [id, desc, patches, expect] of MUTATIONS) {
  if (ONLY.length && !ONLY.includes(id)) continue
  restore()
  // 逐个替换；每个 from 必须**恰好**命中一次（否则变异没落地，结论无效）
  const problems = []
  for (const [rel, rawFrom, rawTo] of patches) {
    const p = path.join(MIRROR, rel)
    const src = fs.readFileSync(p, 'utf8')
    const eol = src.includes('\r\n') ? '\r\n' : '\n'
    const from = withEol(rawFrom, eol)
    const to = withEol(rawTo, eol)
    const n = src.split(from).length - 1
    if (n !== 1) {
      problems.push(`${rel} 的变异锚点命中 ${n} 次（要求 1 次）：${JSON.stringify(rawFrom.slice(0, 60))}`)
      continue
    }
    fs.writeFileSync(p, src.split(from).join(to))
  }
  if (problems.length) {
    rows.push({ id, desc, expect, reds: null, note: problems.join('；') })
    console.log(`\n=== ${id} ${desc}\n  ✗ 变异没落地：${problems.join('；')}`)
    continue
  }
  const mutatedMd5 = patches.map(([rel]) => `${rel}:${md5(path.join(MIRROR, rel))}`).join(' ')
  const res = runChecker(MIRROR)
  const expected = [...expect].sort().join(',')
  const actual = [...res.reds].sort().join(',')
  const isolated = actual === expected
  rows.push({ id, desc, expect, reds: res.reds, isolated })
  console.log(`\n=== ${id} ${desc}`)
  console.log(`  期望红：[${expected}]   实际红：[${actual}]   ${isolated ? '✓ 隔离' : '✗ 不隔离'}`)
  console.log(`  ${res.line}`)
  console.log(`  变异后 md5：${mutatedMd5}`)
}

// 恢复 + 双侧 md5 复核
restore()
console.log('\n=== 收尾：md5 复核 ===')
let drift = 0
for (const rel of MIRROR_FILES) {
  const realNow = md5(path.join(REAL, rel))
  const mirror = md5(path.join(MIRROR, rel))
  const same = realNow === pristine[rel] && mirror === pristine[rel]
  if (!same) drift++
  console.log(`  ${same ? 'OK  ' : 'DRIFT'} ${rel}  真=${realNow}  镜像=${mirror}`)
}
console.log(drift ? '\n✗ 有漂移，别信上面的结论' : '\n✓ 真仓库与镜像都与跑之前逐字相同')

console.log('\n=== 汇总表 ===')
for (const r of rows) {
  const want = [...r.expect].join(',') || '(不红)'
  const got = r.reds ? [...r.reds].join(',') || '(不红)' : '变异未落地'
  console.log(`  ${r.id}  期望=[${want}]  实际=[${got}]  ${r.isolated ? '' : '  <-- 不隔离'}`)
}

console.log('\n=== 收尾：删镜像 ===')
cleanMirror()
