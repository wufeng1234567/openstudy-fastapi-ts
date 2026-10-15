/**
 * 变异跑手（临时，用完即删）—— 证明 DF-UI-20..25 / DF-ROLLBACK-12..15 这几条**会红**。
 *
 * ⚠️ 绝不就地改共享树：跑手自建一份 `D:/OpenStudy/apps/fastapi-v2/_mirror_dsfree_persist/`
 *    镜像（整棵前端目录**拷贝** + 指向真 node_modules 的 **junction**），每个变异前从真仓库
 *    拷回干净文件，跑完做**双侧 md5 复核**，最后先 unlink junction 再删镜像
 *    （直接递归删会跟着删进真实 node_modules）。
 *
 * 跑的是 `tests/check_agent_dsfree.mjs`（行版套件），判据读它自己写的
 * `tests/check_agent_dsfree_result.json` —— 不解析终端输出（管道会毁掉中文）。
 *
 * 用法：cd apps/fastapi-v2/openstudy-vue3-ts && node tests/_mutation_dsfree_persist.mjs
 *
 * ⚠️ 跑手运行期间**不许**再改它管的这 5 个文件：收尾的 md5 复核是拿「开跑那一刻」的哈希比的，
 *    中途编辑会以 `DRIFT` 报警（那是「编辑晚于记录点」，不是变异残留）。真仓库两侧哈希都
 *    对得上才算数。
 */
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'

const REAL = 'D:/OpenStudy/apps/fastapi-v2/openstudy-vue3-ts'
const MIRROR = 'D:/OpenStudy/apps/fastapi-v2/_mirror_dsfree_persist'

/** 会被变异 / 必须逐字还原的文件（真仓库的 md5 在跑之前记下，跑完复核） */
const PRODUCT_FILES = ['src/composables/useAgentChat.ts', 'src/api/ai/ai.ts']
/** 判据侧（只读；镜像里必须与真仓库逐字相同，否则两侧判据不是一个版本） */
const HARNESS_FILES = [
  'tests/check_agent_dsfree.mjs',
  'tests/df_cases.mjs',
  'tests/df_cases.d.mts'
]
const ALL_FILES = [...PRODUCT_FILES, ...HARNESS_FILES]

/** 拷贝镜像时要跳过的顶层条目（node_modules 用 junction；其余是构建产物 / 别人的镜像） */
const SKIP = new Set([
  'node_modules',
  'dist',
  'tests',
  '_mirror_turnrollback_ui',
  '_mirror_dsfree_persist',
  '_scratch_mut',
  '.git'
])

const md5 = (p) => crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex')
const withEol = (text, eol) => (eol === '\r\n' ? text.split('\n').join('\r\n') : text)

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

const ensureMirror = () => {
  cleanMirror(true)
  fs.mkdirSync(MIRROR, { recursive: true })
  // 顶层逐个拷（跳过 node_modules / dist / 别人的镜像），再把 tests 拷进来
  for (const name of fs.readdirSync(REAL)) {
    if (SKIP.has(name)) continue
    fs.cpSync(path.join(REAL, name), path.join(MIRROR, name), { recursive: true })
  }
  fs.cpSync(path.join(REAL, 'tests'), path.join(MIRROR, 'tests'), { recursive: true })
  fs.symlinkSync(path.join(REAL, 'node_modules'), path.join(MIRROR, 'node_modules'), 'junction')
}

/**
 * 跑一遍行版套件，红的用例 id 从**产物 JSON** 里读。
 * ⚠️ 跑之前先把产物删掉：不然「脚本没跑成」会被读成「上一次的结果」（假绿/假红都可能）。
 */
const runSuite = (cwd, label) => {
  const out = path.join(cwd, 'tests', 'check_agent_dsfree_result.json')
  fs.rmSync(out, { force: true })
  let code = 0
  try {
    execFileSync(process.execPath, ['tests/check_agent_dsfree.mjs'], {
      cwd,
      stdio: 'ignore',
      timeout: 10 * 60 * 1000
    })
  } catch (e) {
    code = e.status ?? 1
  }
  if (!fs.existsSync(out)) {
    return { ran: false, code, reds: [], total: -1, note: `${label} 没有写出产物 JSON（没跑成）` }
  }
  const d = JSON.parse(fs.readFileSync(out, 'utf8'))
  const reds = d.rows.filter((r) => r.status !== '通过')
  return {
    ran: true,
    code,
    total: d.total,
    passed: d.passed,
    failed: d.failed,
    reds: reds.map((r) => r.id),
    detail: reds.map((r) => ({
      id: r.id,
      asserts: r.asserts.filter((a) => !a.pass).map((a) => a.label)
    }))
  }
}

/* =====================================================================
 * 变异体：[id, 说明, [[文件, from, to], …], 期望红的用例 id 列表]
 * ===================================================================== */
const MUTATIONS = [
  [
    'MN0',
    '负对照：产品文件里只加一行注释（不该让任何用例变红）',
    [
      [
        PRODUCT_FILES[1],
        'function newPersistTurnId(): string {',
        '// 变异负对照：这一行只是注释\nfunction newPersistTurnId(): string {'
      ]
    ],
    []
  ],

  // ---------- DF-UI-20：拿不到会话 id 就一个请求都不发 ----------
  [
    'MU20',
    '把「不知道属于哪个会话」那道闸门整块删掉（= 改动前：带着空会话 id 照发，拿到假成功）',
    [
      [
        PRODUCT_FILES[0],
        `    if (!sid) {
      outcome.reason = '不知道这一轮属于哪个会话，无法回退'
      setRollbackState(tid, 'fail', outcome)
      return outcome
    }

`,
        ''
      ]
    ],
    ['DF-UI-20']
  ],

  // ---------- DF-UI-21：快照写不进去不许装成成功 ----------
  [
    'MU21',
    '快照 PUT 的失败被吞成一句 console.warn（ok 仍是 true、消息照摘）',
    [
      [
        PRODUCT_FILES[0],
        `      } catch (e: any) {
        outcome.ok = false
        outcome.reason =
          '回退没完成：时间线快照没写成功，刷新后这一轮仍会回来（可以再点一次重试）'
        console.warn('[agent] 回退后时间线落库失败（本地消息保持不动）', e)
        setRollbackState(tid, 'fail', outcome)
        return outcome
      }`,
        `      } catch (e: any) {
        console.warn('[agent] 回退后时间线落库失败（本地消息保持不动）', e)
      }`
      ]
    ],
    ['DF-UI-21']
  ],

  // ---------- DF-UI-22：顺序（PUT 在摘本地之前）+ PUT 写的是摘掉之后那份 ----------
  [
    'MU22a',
    'PUT 写的是**没摘掉这一轮**的那份消息流（刷新后它照样回来）',
    [[PRODUCT_FILES[0], 'slimTimeline(afterTurn)', 'slimTimeline(messages.value)']],
    // ⚠️ 第一次跑时我预测只有 DF-UI-22，实测还红了 DF-UI-17 / DF-UI-25 —— 那两条各自也有
    //    「最后一次快照里不许有这一轮」的判据，它们守的是**同一条不变量**（写进库的那份必须是
    //    摘掉之后的）。不是判据越界，是我的预测漏了它们，如实记在这里。
    ['DF-UI-17', 'DF-UI-22', 'DF-UI-25']
  ],
  [
    'MU22b',
    '顺序反过来（先摘本地消息、再 PUT 快照）——**粗变异**：PUT 失败时本地已经删了，DF-UI-21 也会红',
    [
      [
        PRODUCT_FILES[0],
        `      const plan = locateTurn(tid)
      outcome.userText = plan ? plan.userText : ''
`,
        `      const plan = locateTurn(tid)
      outcome.userText = plan ? plan.userText : ''
      if (plan) messages.value.splice(plan.startIdx, plan.endIdx - plan.startIdx + 1)
`
      ],
      [
        PRODUCT_FILES[0],
        `      if (plan) messages.value.splice(plan.startIdx, plan.endIdx - plan.startIdx + 1)
      setRollbackState(tid, 'done', outcome)`,
        `      setRollbackState(tid, 'done', outcome)`
      ]
    ],
    // ⚠️ 实测还红了 DF-UI-17（同 MU22a 的理由：它也有「最后一次快照里不许有这一轮」）。
    ['DF-UI-17', 'DF-UI-21', 'DF-UI-22']
  ],

  // ---------- DF-UI-23：显式入参优先 ----------
  [
    'MU23',
    '会话 id 的来源反过来（过期的「最近一次 send」赢过页面显式传的那个）',
    [
      [
        PRODUCT_FILES[0],
        'const sid = String(sessionId || lastSessionId.value || \'\')',
        'const sid = String(lastSessionId.value || sessionId || \'\')'
      ]
    ],
    ['DF-UI-23']
  ],

  // ---------- DF-UI-24 / 25：historyMatched 透出 + 不许拿它短路 ----------
  [
    'MU24',
    '`historyMatched` 不再记进结果（界面永远读不到 → 老数据那句话永远不说）',
    [[PRODUCT_FILES[0], '      outcome.historyMatched = Number(dr.matched) || 0', '      void dr']],
    ['DF-UI-24']
  ],
  [
    'MU25',
    '在 `historyMatched === 0` 上提前 return（老数据永远删不掉 —— 反向判据）',
    [
      [
        PRODUCT_FILES[0],
        '      outcome.historyMatched = Number(dr.matched) || 0',
        `      outcome.historyMatched = Number(dr.matched) || 0
      if (outcome.historyMatched === 0) {
        outcome.dropped = false
        setRollbackState(tid, 'fail', outcome)
        return outcome
      }`
      ]
    ],
    ['DF-UI-25']
  ],

  // ---------- DF-ROLLBACK-12 / 13：`matched` 是加法字段 ----------
  [
    'MR12',
    '`matched` 一律归 0（不去读服务端的值）',
    [
      [
        PRODUCT_FILES[1],
        '    const matched = typeof d.matched === \'number\' && Number.isFinite(d.matched) ? Number(d.matched) : 0',
        '    const matched = 0'
      ]
    ],
    ['DF-ROLLBACK-12']
  ],
  [
    'MR13',
    '把 `matched` 变成**必填**（老后端没有它就判失败）——**粗变异**：DF-ROLLBACK-09 那条「最小成功形状」也会红',
    [
      [
        PRODUCT_FILES[1],
        'if (!d || typeof d !== \'object\' || typeof d.dropped !== \'number\') {',
        'if (!d || typeof d !== \'object\' || typeof d.dropped !== \'number\' || typeof d.matched !== \'number\') {'
      ]
    ],
    ['DF-ROLLBACK-09', 'DF-ROLLBACK-13']
  ],

  // ---------- DF-ROLLBACK-14 / 15：补写历史那两趟的 turnId ----------
  [
    'MR14',
    '补写历史不再用调用方给的 id（自己另生成一个 —— 前端的 id 与库里的对不上）',
    [
      [
        PRODUCT_FILES[1],
        "    const persistTurnId = String(extras?.turnId || '') || newPersistTurnId()",
        '    const persistTurnId = newPersistTurnId()'
      ]
    ],
    ['DF-ROLLBACK-14']
  ],
  [
    'MR15',
    '调用方没给 id 时不再生成（两趟都落空串 = 服务端一行都匹配不到）',
    [
      [
        PRODUCT_FILES[1],
        "    const persistTurnId = String(extras?.turnId || '') || newPersistTurnId()",
        "    const persistTurnId = String(extras?.turnId || '')"
      ]
    ],
    ['DF-ROLLBACK-15']
  ],
  [
    'MR15b',
    '补写回复那一趟换成**另一个**新 id（两趟对不上 = 回退只能删掉一行）——**粗变异**：14 / 15 都会红',
    [
      [
        PRODUCT_FILES[1],
        `            aborted: signal?.aborted === true,
            // 与先写提问那一次同一个 id（这一行漏了，回退就只能删掉提问行）
            turnId: persistTurnId`,
        `            aborted: signal?.aborted === true,
            turnId: newPersistTurnId()`
      ]
    ],
    ['DF-ROLLBACK-14', 'DF-ROLLBACK-15']
  ]
]

/* =====================================================================
 * 0) 同版本闸门 + 前置状态
 * ===================================================================== */
const pristine = {}
for (const rel of ALL_FILES) pristine[rel] = md5(path.join(REAL, rel))

const restore = () => {
  for (const rel of ALL_FILES) fs.copyFileSync(path.join(REAL, rel), path.join(MIRROR, rel))
}

console.log('=== 0) 重建镜像（整棵前端目录拷贝 + node_modules junction） ===')
ensureMirror()
restore()

console.log('\n=== 1) 同版本闸门：真仓库与镜像都必须全绿，且条数一致 ===')
const real = runSuite(REAL, '真仓库')
const mirror0 = runSuite(MIRROR, '镜像')
console.log(
  `  真仓库：total=${real.total} passed=${real.passed} failed=${real.failed} reds=[${real.reds.join(', ')}]`
)
console.log(
  `  镜  像：total=${mirror0.total} passed=${mirror0.passed} failed=${mirror0.failed} reds=[${mirror0.reds.join(', ')}]`
)
if (!real.ran || !mirror0.ran || real.failed !== 0 || mirror0.failed !== 0) {
  console.log('  ✗ 有一侧本来就不绿 / 没跑成 —— 先修干净，别继续（变异结论会不可信）')
  for (const d of real.detail || []) console.log('    真仓库红：', d.id, JSON.stringify(d.asserts))
  for (const d of mirror0.detail || []) console.log('    镜  像红：', d.id, JSON.stringify(d.asserts))
  process.exit(1)
}
if (real.total !== mirror0.total) {
  console.log(`  ✗ 判据条数对不上（真=${real.total} 镜像=${mirror0.total}）—— 拒跑`)
  process.exit(1)
}
for (const rel of HARNESS_FILES) {
  const a = md5(path.join(REAL, rel))
  const b = md5(path.join(MIRROR, rel))
  if (a !== b) {
    console.log(`  ✗ 判据文件两侧不一致：${rel}（真=${a} 镜像=${b}）—— 拒跑`)
    process.exit(1)
  }
}

/* =====================================================================
 * 2) 逐个变异
 * ===================================================================== */
const rows = []
for (const [id, desc, patches, expect] of MUTATIONS) {
  restore()
  const problems = []
  for (const [rel, rawFrom, rawTo] of patches) {
    const p = path.join(MIRROR, rel)
    const src = fs.readFileSync(p, 'utf8')
    const eol = src.includes('\r\n') ? '\r\n' : '\n'
    const from = withEol(rawFrom, eol)
    const to = withEol(rawTo, eol)
    const n = src.split(from).length - 1
    if (n !== 1) {
      problems.push(`${rel} 的锚点命中 ${n} 次（要求 1 次）：${JSON.stringify(rawFrom.slice(0, 70))}`)
      continue
    }
    fs.writeFileSync(p, src.split(from).join(to))
  }
  if (problems.length) {
    console.log(`\n=== ${id} ${desc}\n  ✗ 变异没落地：${problems.join('；')}`)
    rows.push({ id, desc, expect, actual: null, ok: false, note: '变异没落地' })
    continue
  }
  const mutated = patches.map(([rel]) => `${rel}:${md5(path.join(MIRROR, rel))}`).join(' ')
  const res = runSuite(MIRROR, id)
  const want = [...expect].sort().join(',')
  const got = [...res.reds].sort().join(',')
  const ok = res.ran && want === got
  console.log(`\n=== ${id} ${desc}`)
  console.log(`  期望红：[${want}]   实际红：[${got}]   ${ok ? '✓' : '✗'}`)
  console.log(`  total=${res.total} failed=${res.failed}  变异后 md5：${mutated}`)
  for (const d of res.detail || []) console.log(`    · ${d.id} 红的判据：${JSON.stringify(d.asserts)}`)
  rows.push({ id, desc, expect, actual: res.reds, ok, note: res.ran ? '' : res.note })
}

/* =====================================================================
 * 3) 收尾：还原 + 双侧 md5 复核 + 删镜像
 * ===================================================================== */
restore()
console.log('\n=== 3) md5 复核（真仓库一个字节都不该动；镜像也应与真仓库逐字相同） ===')
let drift = 0
for (const rel of ALL_FILES) {
  const realNow = md5(path.join(REAL, rel))
  const mirror = md5(path.join(MIRROR, rel))
  const same = realNow === pristine[rel] && mirror === pristine[rel]
  if (!same) drift++
  console.log(`  ${same ? 'OK  ' : 'DRIFT'} ${rel}  真=${realNow} 镜像=${mirror}`)
}
console.log(drift ? '\n✗ 有漂移，别信上面的结论' : '\n✓ 真仓库与镜像都与跑之前逐字相同')

console.log('\n=== 汇总 ===')
for (const r of rows) {
  const want = r.expect.join(',') || '(不红)'
  const got = r.actual ? r.actual.join(',') || '(不红)' : '变异未落地'
  console.log(`  ${r.id}  期望=[${want}]  实际=[${got}]  ${r.ok ? '' : '  <-- 不符'}${r.note ? '  ' + r.note : ''}`)
}

console.log('\n=== 4) 删镜像 ===')
cleanMirror()
