/**
 * 「新用例能红」的变异跑手（**只动镜像**，不碰真实工作树）
 *
 * 每条变异：断言前置状态 → 替换 → 跑子集套件 → 收集红集 → 整份写回 → 复核 md5。
 * 产物：每个变异一行 + 红集列表（用来判断「只红该红的那几条」）。
 */
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const MIRROR = path.join(path.dirname(fileURLToPath(import.meta.url)), 'openstudy-vue3-ts')
const md5 = (p) => crypto.createHash('md5').update(fs.readFileSync(p)).digest('hex')

const F = {
  useAgentChat: 'src/composables/useAgentChat.ts',
  agent: 'src/api/ai/agent.ts',
  agentDsFree: 'src/api/ai/agentDsFree.ts'
}

const MARKER = `      messages.value.push({ role: 'assistant', type: 'turn_end', turnId, content: '' })\n`

const MUTATIONS = [
  {
    name: 'M00 复原成「修复前」（四处回退相关代码全去掉）',
    edits: [
      [F.agentDsFree, `    turnId: opts.turnId || '',\n    autoConfirm: opts.autoConfirm !== false,`, `    autoConfirm: opts.autoConfirm !== false,`],
      [F.agent, `        turnId: opts.turnId || '',\n        userId: normalizeUserId(opts.userId),`, `        userId: normalizeUserId(opts.userId),`],
      [F.useAgentChat, MARKER, ''],
      [F.useAgentChat, `    if (m.turnId) out.turnId = m.turnId\n`, '']
    ]
  },
  {
    name: 'M01 ds-free：/ai/agent/execute 不带 turnId',
    edits: [
      [F.agentDsFree, `    turnId: opts.turnId || '',\n    autoConfirm: opts.autoConfirm !== false,`, `    autoConfirm: opts.autoConfirm !== false,`]
    ]
  },
  {
    name: 'M02 api 链路：/ai/agent/stream 不带 turnId',
    edits: [
      [F.agent, `        turnId: opts.turnId || '',\n        userId: normalizeUserId(opts.userId),`, `        userId: normalizeUserId(opts.userId),`]
    ]
  },
  {
    name: 'M03 回退：把 `data` 少剥一层信封（读成整份响应体）',
    edits: [[F.agent, `    const d = (data as any)?.data`, `    const d = data as any`]]
  },
  {
    name: 'M04 回退：只看 HTTP，不看 body 里的 code',
    edits: [[F.agent, `    if (code !== 200) return fail(serverReason(data) || '回退被服务端拒绝')\n`, '']]
  },
  {
    name: 'M05 回退：不校验 data 形状',
    edits: [
      [
        F.agent,
        `    if (!d || typeof d !== 'object' || typeof d.reverted !== 'number') {\n      return fail('响应里没有回退结果（路由没匹配上？被 catch_all 兜成 200 假成功？）')\n    }\n`,
        `    if (!d) {\n      return fail('响应里没有回退结果（路由没匹配上？被 catch_all 兜成 200 假成功？）')\n    }\n`
      ]
    ]
  },
  {
    name: 'M06 轮末标记整个去掉',
    edits: [[F.useAgentChat, MARKER, '']]
  },
  {
    name: 'M07 标记挪到落库**之后**（快照里没有它）',
    edits: [
      [F.useAgentChat, MARKER, ''],
      [
        F.useAgentChat,
        `          console.warn('[agent] 时间线落库失败', e)\n        }\n      }\n    }\n  }`,
        `          console.warn('[agent] 时间线落库失败', e)\n        }\n      }\n${MARKER}    }\n  }`
      ]
    ]
  },
  {
    name: 'M08 有错误提示就不加标记（报错那一轮无可回退）',
    edits: [
      [
        F.useAgentChat,
        MARKER,
        `      if (!messages.value.some((m) => m.type === 'agent_note' && m.noteKind === 'error')) {\n${MARKER}      }\n`
      ]
    ]
  },
  {
    name: 'M09 标记只加在**正常结束**的路径上（挂在 try 结尾）',
    edits: [
      [F.useAgentChat, MARKER, ''],
      [F.useAgentChat, `      return answer\n    } catch (e: any) {`, `${MARKER}      return answer\n    } catch (e: any) {`]
    ]
  },
  {
    name: 'M10 每轮 id 固定成常量（两轮撞同一个 id）',
    edits: [
      [
        F.useAgentChat,
        "  `t_${Date.now()}_${Math.random().toString(36).slice(2, 8).padEnd(6, '0')}`",
        "  't_1758530000000_aaaaaa'"
      ]
    ]
  },
  {
    name: 'M11 回退时不置 busy',
    edits: [[F.useAgentChat, `    turnRollback.value = { turnId: tid, status: 'busy', summary: null }\n`, '']]
  },
  {
    name: 'M12 回退结果里的 skipped 清单被吞掉',
    edits: [
      [
        F.useAgentChat,
        `    turnRollback.value = { turnId: tid, status: res.ok ? 'done' : 'fail', summary: res }`,
        `    turnRollback.value = { turnId: tid, status: res.ok ? 'done' : 'fail', summary: { ...res, skipped: [] } }`
      ]
    ]
  },
  {
    name: 'M13 回退失败也报 done（状态不看服务端的 ok）',
    edits: [[F.useAgentChat, `status: res.ok ? 'done' : 'fail'`, `status: 'done'`]]
  },
  {
    name: 'M14 落库白名单不留 turnId（刷新后拿不到最近一轮）',
    edits: [[F.useAgentChat, `    if (m.turnId) out.turnId = m.turnId\n`, '']]
  }
]

const SELECT = [
  '--only',
  'DF-LOOP-60',
  '--only',
  'DF-UI-0',
  '--only',
  'DF-UI-1',
  '--only',
  'DF-ROLLBACK-'
]

const results = []
for (const mut of MUTATIONS) {
  const backups = new Map()
  let pre = {}
  // ---- 前置断言：镜像必须是我预期的版本，否则拒绝开跑 ----
  const before = {}
  for (const [file] of mut.edits) {
    before[file] = md5(path.join(MIRROR, file))
    backups.set(file, fs.readFileSync(path.join(MIRROR, file), 'utf8'))
  }
  let applied = true
  for (const [file, find, repl] of mut.edits) {
    const p = path.join(MIRROR, file)
    let src = fs.readFileSync(p, 'utf8')
    const n = src.split(find).length - 1
    if (n !== 1) {
      applied = false
      results.push({ name: mut.name, error: `替换目标在 ${file} 里出现 ${n} 次（要求 1 次），未改动` })
      break
    }
    fs.writeFileSync(p, src.replace(find, repl), 'utf8')
  }
  if (!applied) continue

  const run = spawnSync(process.execPath, ['tests/check_agent_dsfree.mjs', '--no-color', ...SELECT], {
    cwd: MIRROR,
    encoding: 'utf8'
  })
  let redIds = []
  let greenIds = []
  let parseErr = ''
  try {
    const out = JSON.parse(fs.readFileSync(path.join(MIRROR, 'tests/check_agent_dsfree_result.json'), 'utf8'))
    redIds = out.rows.filter((r) => r.status !== '通过').map((r) => r.id)
    greenIds = out.rows.filter((r) => r.status === '通过').map((r) => r.id)
  } catch (e) {
    parseErr = String(e?.message || e)
  }

  // ---- 整份写回 + 复核 md5 ----
  for (const file of backups.keys()) fs.writeFileSync(path.join(MIRROR, file), backups.get(file), 'utf8')
  const after = {}
  let restored = true
  for (const file of backups.keys()) {
    after[file] = md5(path.join(MIRROR, file))
    if (after[file] !== before[file]) restored = false
  }

  results.push({
    name: mut.name,
    exit: run.status,
    redIds,
    greenIds,
    restored,
    before,
    after,
    parseErr,
    stderrTail: String(run.stderr || '').slice(-400)
  })
  console.log(`\n== ${mut.name}`)
  console.log(`   红(${redIds.length})：${redIds.join(', ') || '(无)'}`)
  console.log(`   绿(${greenIds.length})：${greenIds.join(', ')}`)
  console.log(`   md5 还原：${restored ? '✅ 一致' : '❌ 不一致'}`)
  if (parseErr) console.log(`   结果 JSON 解析失败：${parseErr}`)
  if (run.status !== 0 && run.status !== 1) console.log(`   ⚠️ 退出码 ${run.status}（≠0/1，可能是脚本自身出错）\n${run.stderrTail}`)
}

fs.writeFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), 'mutations_report.json'), JSON.stringify(results, null, 2), 'utf8')
console.log('\n报告：_scratch_mut/mutations_report.json')
