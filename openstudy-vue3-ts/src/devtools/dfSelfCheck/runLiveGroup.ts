/**
 * 自检 · 「真链路端到端」组 —— 真扩展 + 真 DS 页面 + 真后端工具
 *
 * 这一组跑的就是**用户日常用的那条路**，一个桩都没有：
 *   前端 Agent 循环 → 浏览器扩展 → chat.deepseek.com 页面 → 后端工具 → 回灌 → 出结果
 *
 * 所以它只能在**已经登录好的浏览器里**跑 —— 这正是把自检搬进面板的意义：
 * 不用另起干净 Chrome，不用手动给测试实例鉴权。
 *
 * ⚠️ 已知限制：**DS 会话无法隔离**。
 *   扩展的 `getActiveDsTabId()`（`extension/background.js`）取的是「最早注册的页签」，
 *   而 `DSPROXY_OPEN_NEW_CHAT` 只是 `chrome.tabs.create` 开个新标签 ——
 *   发送目标切不过去。所以本组的提问会落进**用户当前那个 DS 对话**里。
 *   缓解：所有提问统一加 `[自检]` 前缀，事后一眼能认出来；面板开跑前会再提示一次。
 */
import { runDsFreeAgentStream } from '@/api/ai/agentDsFree'
import { hasDSProxy, isDSReady } from '@/utils/ds-proxy'
import { getToken } from '@/utils/auth'
import { PREFIX, type DfCase } from '../../../tests/df_cases.mjs'
import { evaluateCase, type Row, type AssertRow } from './evaluate'
import { append, progress, beginAbortGroup, groupAborted } from './store'

const BASE = import.meta.env.VITE_APP_BASE_API

/** 提问前缀：DS 会话里一眼认出哪些是自检留下的 */
const TAG = '[自检] '

/** 题库名占位符（`SELF_LIVE_CASES` 的 prompt 里用） */
export const BANK_PLACEHOLDER = '__DF_BANK__'

/** 单条用例兜底超时 —— DS 网页端偶尔很慢，给足；超了就当失败并继续下一条 */
const CASE_TIMEOUT_MS = 180000

/**
 * 用例之间的间隔。
 *
 * **不是可有可无的礼貌**：DS 网页端对连续消息有限流，而本组 6 条用例每条都要
 * 1~3 轮往返（一问一答一轮 = 给 DS 发一条消息），连着打十几条必然被挡下来 ——
 * 实测跑完最后一条时 DS 页面弹出「消息发送过于频繁，请稍后重试」。
 * 那个提示是 **DeepSeek 页面自己的**（我们前端 / 后端 / 扩展里都没有这句话），
 * 因为扩展是 DOM 自动化去操作真页面，所以 DS 的限流一样管得着我们。
 */
const CASE_GAP_MS = 5000

/** seed 的自检会话 id，方便在聊天历史里区分 */
const SESSION_ID = 'df_selfcheck'

// =====================================================================
// 后端工具调用（与 agentDsFree.executeTool 同一 URL / 同一鉴权口径）
// =====================================================================

export async function agentExecute(
  tool: string,
  params: Record<string, any>,
  extra?: { userId?: string | number }
): Promise<any> {
  const res = await fetch(`${BASE}/ai/agent/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + getToken()
    },
    body: JSON.stringify({
      tool,
      params,
      userId: extra?.userId || 0,
      sessionId: SESSION_ID,
      // seed / clean 是自检的基础设施操作，不是被测对象 —— 确认环节直接放行
      autoConfirm: true,
      confirmed: true
    })
  })
  // ⚠️ 不能直接 `res.json()`：后端没起 / 网关返回 HTML / 401 时，
  //    报出来的是「Unexpected end of JSON input」这种没法排查的错。
  //    这里把 HTTP 状态和响应体开头带上，一眼能看出是接口的问题还是数据的问题。
  const text = await res.text()
  if (!res.ok) {
    throw new Error(`${tool} 接口 HTTP ${res.status}：${text.slice(0, 120) || '(空响应)'}`)
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(`${tool} 接口返回的不是 JSON（HTTP ${res.status}）：${text.slice(0, 120)}`)
  }
}

// =====================================================================
// 前置检查
// =====================================================================

export interface PreflightItem {
  label: string
  ok: boolean
  hint: string
}

export async function preflight(): Promise<PreflightItem[]> {
  const items: PreflightItem[] = []

  const extOk = hasDSProxy()
  items.push({
    label: '扩展已注入',
    ok: extOk,
    hint: extOk
      ? ''
      : '页面上没有 window.DSProxy —— 确认 DeepSeek 代理扩展已安装并启用，然后刷新本页'
  })

  let dsOk = false
  if (extOk) {
    try {
      dsOk = await isDSReady()
    } catch {
      dsOk = false
    }
  }
  // 注意措辞：这里只能确认**标签页开着**，查不了登录态 ——
  // 扩展的 getStatus 不返回 loggedIn（详见 isDSReady 的注释）。
  // 写「已登录」会让用户以为这一条保证登录了；真没登录的话，
  // 后面的用例会失败并留下扩展报的错，那才是让人去查登录态的地方。
  items.push({
    label: 'DS 页面已打开',
    ok: dsOk,
    hint: dsOk
      ? ''
      : '扩展没看到 chat.deepseek.com 的标签页 —— 打开它（顺便确认已登录、能看到输入框），然后回来自检页重试'
  })

  const tokenOk = !!getToken()
  items.push({
    label: 'OpenStudy 已登录',
    ok: tokenOk,
    hint: tokenOk ? '' : '当前没拿到 Admin-Token，工具调用会 401'
  })

  return items
}

// =====================================================================
// 测试数据 seed / clean
// =====================================================================

function stamp(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
}

export interface SeedResult {
  ok: boolean
  bankName: string
  bankId: number | null
  imported: number
  detail: string
}

/**
 * 建一个 `__df_test__` 前缀的题库并塞 3 道题。
 *
 * 先 clean 再 create：`bank_manage.create` 对同名题库会**直接失败**（后端有重名校验），
 * 上一次崩在半路留下的残留会让这次一开跑就挂。
 */
export async function seedTestData(): Promise<SeedResult> {
  const bankName = `${PREFIX}自检-${stamp()}`

  try {
    await cleanTestData()

    const created = await agentExecute('bank_manage', {
      action: 'create',
      bank_name: bankName,
      subject: '自检'
    })
    if (created?.success === false) {
      return {
        ok: false,
        bankName,
        bankId: null,
        imported: 0,
        detail: `建题库失败：${created?.error || created?.message || JSON.stringify(created).slice(0, 200)}`
      }
    }
    // ⚠️ `create` 把题库嵌在 `bank` 里，bankId 不在顶层 —— 这个坑在 Node 驱动里踩过一次
    const bankId = created?.bank?.bankId ?? created?.bank?.bank_id ?? null
    if (!bankId) {
      return {
        ok: false,
        bankName,
        bankId: null,
        imported: 0,
        detail: `建题库返回里没找到 bankId：${JSON.stringify(created).slice(0, 200)}`
      }
    }

    // `questions` 按契约传 **JSON 字符串**（后端也容忍数组，但契约是字符串）
    const questions = JSON.stringify([
      {
        questionType: 4,
        questionText: '自检题目 1：事件 A、B、C 构成完备事件组，且 P(A)=0.5，则 P(C)=____。',
        answer: '0.5',
        analysis: '自检用占位解析',
        difficulty: 2
      },
      {
        questionType: 1,
        questionText: '自检题目 2：下列哪个是质数？',
        options: ['4', '6', '7', '9'],
        answer: '2',
        analysis: '自检用占位解析',
        difficulty: 1
      },
      {
        questionType: 3,
        questionText: '自检题目 3：真或假 —— 空集是任何集合的子集。',
        answer: '对',
        analysis: '自检用占位解析',
        difficulty: 2
      }
    ])

    const imported = await agentExecute('question_manage', {
      action: 'batch_import',
      bank_id: bankId,
      questions
    })

    const n = Number(imported?.imported ?? 0)
    const failed = Number(imported?.failed ?? 0)
    if (imported?.success === false || n === 0) {
      return {
        ok: false,
        bankName,
        bankId,
        imported: n,
        detail: `批量导入失败：${JSON.stringify(imported?.errors || imported).slice(0, 300)}`
      }
    }
    if (failed > 0) {
      // 部分失败也算前置不成立 —— 否则 DF-LIVE-05 会莫名其妙地失败，排查方向全错
      return {
        ok: false,
        bankName,
        bankId,
        imported: n,
        detail: `批量导入部分失败：${failed} 条，${JSON.stringify(imported?.errors || []).slice(0, 300)}`
      }
    }

    return {
      ok: true,
      bankName,
      bankId,
      imported: n,
      detail: `题库「${bankName}」已就绪，${n} 道题`
    }
  } catch (e: any) {
    // 也兜一层：面板调它时没有 try/catch，抛出去会让「前置不满足 → 写进结果行」这条路径断掉，
    // 用户只看到日志停在「准备测试数据…」然后就没了
    return {
      ok: false,
      bankName,
      bankId: null,
      imported: 0,
      detail: `准备测试数据出错：${e?.message || e}`
    }
  }
}

/**
 * 删掉所有 `__df_test__` 前缀的题库。
 *
 * ⚠️ 「没查成」和「没残留」必须分开说：
 *    没登录 / 接口报错时如果也说「没有残留」，用户会以为清干净了，实际上一堆垃圾还在库里。
 */
export async function cleanTestData(): Promise<{ ok: boolean; deleted: string[]; detail: string }> {
  if (!getToken()) {
    return { ok: false, deleted: [], detail: '没登录（拿不到 Admin-Token），查不到 —— 这不等于没有残留' }
  }

  let listed: any
  try {
    listed = await agentExecute('bank_manage', { action: 'list', bank_name: PREFIX })
  } catch (e: any) {
    return { ok: false, deleted: [], detail: `查询测试题库失败：${e?.message || e}` }
  }
  if (listed?.success === false) {
    return {
      ok: false,
      deleted: [],
      detail: `查询测试题库失败：${listed?.error || JSON.stringify(listed).slice(0, 200)}`
    }
  }

  const banks: any[] = listed?.banks || []
  const targets = banks.filter((b) => String(b.bankName || '').startsWith(PREFIX))
  const deleted: string[] = []
  const failed: string[] = []
  for (const b of targets) {
    try {
      const r = await agentExecute('bank_manage', { action: 'delete', bank_id: b.bankId })
      if (r?.success === false) failed.push(`${b.bankName}(${r?.error || '未知错误'})`)
      else deleted.push(String(b.bankName))
    } catch (e: any) {
      failed.push(`${b.bankName}(${e?.message || e})`)
    }
  }

  const detail = failed.length
    ? `删掉 ${deleted.length} 个，另有 ${failed.length} 个失败：${failed.join('、')}`
    : `删掉 ${deleted.length} 个测试题库`
  return { ok: failed.length === 0, deleted, detail }
}

// =====================================================================
// 跑真链路
// =====================================================================

export interface LiveRunOptions {
  /** seed 出来的题库名，用来替换 prompt 里的 `__DF_BANK__` */
  bankName?: string
  userId?: string | number
  /** 用例之间的间隔（毫秒）。默认 5000 —— 见 CASE_GAP_MS 的说明，别随手调小 */
  caseGapMs?: number
  onRow?: (row: Row) => void
}

export async function runLiveGroup(cases: DfCase[], opts: LiveRunOptions = {}): Promise<Row[]> {
  const rows: Row[] = []
  const groupSignal = beginAbortGroup()
  const gap = opts.caseGapMs ?? CASE_GAP_MS

  for (let i = 0; i < cases.length; i++) {
    const c = cases[i]
    if (groupAborted()) {
      rows.push(abortedRow(c))
      progress.aborted += 1
      append('warn', '已中止，剩余用例未执行', { caseId: c.id, scope: 'runLive' })
      continue
    }
    // 第一条不用等；之后每条之间垫一下，避免连着打爆 DS 的发送频率限制
    if (i > 0 && gap > 0) {
      append('debug', `等 ${(gap / 1000).toFixed(0)}s 再发下一条（DS 有发送频率限制）`, {
        scope: 'runLive'
      })
      await sleep(gap)
      if (groupAborted()) {
        rows.push(abortedRow(c))
        progress.aborted += 1
        continue
      }
    }
    progress.current = c.id

    // 提问加 `[自检]` 前缀并在 DS 会话里留痕（见文件头「DS 会话无法隔离」）
    const prompt = TAG + String(c.prompt || '测试').split(BANK_PLACEHOLDER).join(opts.bankName || '')
    append('info', `${c.title}`, { caseId: c.id, scope: 'runLive', detail: `提问：${prompt}` })

    const events: any[] = []
    const confirms: any[] = []
    let formatErrorCount = 0
    let answer = ''
    let thrown = ''
    const t0 = Date.now()

    const abort = linkAbort(CASE_TIMEOUT_MS, groupSignal)
    try {
      answer = await runDsFreeAgentStream(
        {
          message: prompt,
          model: 'deepseek-free',
          userId: opts.userId ?? 0,
          sessionId: SESSION_ID,
          autoConfirm: true,
          signal: abort.signal
        },
        {
          onEvent: (e: any) => {
            events.push(e)
            if (e?.type === 'error') formatErrorCount += 1
          },
          // 真链路自动放行确认（与 Node 驱动一致），但要**记下来**——
          // `DF-LIVE-06` 断言的就是「破坏性操作确实触发了确认」
          onConfirm: async (info: any) => {
            confirms.push(info)
            return true
          }
        }
      )
    } catch (e: any) {
      thrown = String(e?.message || e)
    } finally {
      abort.done()
    }

    const secs = Number(((Date.now() - t0) / 1000).toFixed(1))
    const toolCalls = events
      .filter((e) => e.type === 'tool_result')
      .map((e) => `${e.tool}.${e.action}`)
    const selfCorrect = events.filter((e) => e.type === 'self_correct')

    const ctx = {
      events,
      eventTypes: events.map((e) => e.type),
      answer: String(answer || ''),
      toolCalls,
      confirms,
      formatErrorCount,
      // 「第一轮就格式错」= 一次工具都没跑成 + 出现过 self_correct
      hadFormatError: selfCorrect.length > 0 && toolCalls.length === 0,
      thrown
    }

    const { ok, asserts } = evaluateCase(c, ctx)
    const aborted = groupAborted()
    const row: Row = {
      id: c.id,
      suite: c.suite,
      title: c.title,
      status: aborted ? '中止' : ok ? '通过' : '失败',
      secs,
      asserts: aborted ? [{ label: '用户中止', pass: false, actual: '' }, ...asserts] : asserts
    }
    rows.push(row)

    // 疑似被 DS 限流：这句提示是 DeepSeek 页面自己弹的，被扩展/模型回传进来。
    // 单独标出来，免得用户以为是自己代码坏了 —— 等几十秒再跑，或把间隔调大。
    const throttled = events.some((e) =>
      /频繁|稍后重试|too many requests|rate ?limit/i.test(String(e?.message || ''))
    )
    if (throttled) {
      append(
        'warn',
        '疑似被 DeepSeek 限流（页面提示「消息发送过于频繁」）—— 等一会儿再跑，别连续重跑真链路组',
        { caseId: c.id, scope: 'runLive' }
      )
    }

    const failed = asserts.filter((a) => !a.pass)
    append(aborted ? 'warn' : ok ? 'pass' : 'fail', c.title, {
      caseId: c.id,
      scope: 'runLive',
      detail: failed.length
        ? failed.map((a) => `✗ ${a.label}${a.actual ? ` → ${a.actual}` : ''}`).join('\n')
        : undefined
    })
    append('debug', `事件流：${ctx.eventTypes.join(' → ') || '(无事件)'}`, {
      caseId: c.id,
      scope: 'runLive',
      detail: [
        `工具调用：${toolCalls.join('、') || '(无)'}`,
        `确认卡片：${confirms.length} 次${confirms.length ? `（破坏性：${confirms.filter((x) => x?.destructive).length}）` : ''}`,
        `格式错误事件：${formatErrorCount}`,
        `用时：${secs}s`,
        `回复：${String(answer || '').slice(0, 200)}`,
        thrown ? `抛异常：${thrown}` : ''
      ]
        .filter(Boolean)
        .join('\n')
    })

    progress.done += 1
    if (aborted) progress.aborted += 1
    else ok ? (progress.passed += 1) : (progress.failed += 1)
    opts.onRow?.(row)
  }

  progress.current = ''
  return rows
}

/** 一条「没跑」的结果行（分组被中止时占位，让报告仍然完整） */
function abortedRow(c: DfCase): Row {
  return {
    id: c.id,
    suite: c.suite,
    title: c.title,
    status: '中止',
    secs: null,
    asserts: [{ label: '用户中止，未执行', pass: false, actual: '' }] as AssertRow[]
  }
}

/** 给一条用例挂超时（同 runLoopGroup，手写以避开 AbortSignal.any 的版本要求） */
function linkAbort(ms: number, parent?: AbortSignal | null) {
  const ac = new AbortController()
  const onParent = () => ac.abort()
  if (parent) {
    if (parent.aborted) ac.abort()
    else parent.addEventListener('abort', onParent, { once: true })
  }
  const timer = ms > 0 ? setTimeout(() => ac.abort(), ms) : null
  return {
    signal: ac.signal,
    done: () => {
      if (timer) clearTimeout(timer)
      parent?.removeEventListener('abort', onParent)
    }
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
