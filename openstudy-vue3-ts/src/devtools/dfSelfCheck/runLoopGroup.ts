/**
 * 自检 · 「协议/循环」组 —— 脚本化模型，跑**真** `agentDsFree.ts` 的循环
 *
 * 这一组**完全不碰 DS 页面**（模型回复是脚本喂进去的），所以：
 *   · 不需要扩展、不需要登录 DS，跑得飞快（毫秒级/条）；
 *   · 最安全，随便反复跑；
 *   · 覆盖的恰恰是历史上真出过 bug 的那些点 —— 协议解析跑偏、格式纠错与止损、
 *     压缩回灌要保留 `questionId`（Bug⑤）、Agent 模式要自动开深度思考（Bug⑥）。
 *
 * 与 Node 驱动（`tests/check_agent_dsfree.mjs` 的 `runLoopCases`）的关系：
 *   **同一批用例、同一套断言、同一份 ctx 形状**。区别只在「怎么把模型脚本化」：
 *     · Node  → Vite SSR 的 `resolveId` 把 `@/utils/ds-proxy` 换成桩模块
 *     · 浏览器 → `__withDSSeam()`（缝长在 `ds-proxy.ts` 里，见那边的注释）
 *   另外 Node 还要桩 `@/utils/auth` / `doc-parse` / `image-compress`（在 Node 里跑不了），
 *   浏览器里这几个模块是真的、能跑 —— 所以这里**不桩它们，反而更接近生产**。
 *
 * ⚠️ 两者结果必须逐条一致。任何一条对不上，先怀疑这里的驱动写错了。
 */
import {
  runDsFreeAgentStream,
  fetchAgentTools,
  resetAgentToolsCache,
  resetHistoryInjection
} from '@/api/ai/agentDsFree'
import { __withDSSeam } from '@/utils/ds-proxy'
import type { DfCase } from '../../../tests/df_cases.mjs'
import { evaluateCase, type Row, type AssertRow } from './evaluate'
import { append, progress, beginAbortGroup, groupAborted } from './store'

/**
 * 与后端注册表一致的最小工具能力清单（供 `needConfirm` 判定，DF-LOOP-14 依赖它）
 *
 * ⚠️⚠️ 这份 `actions` 与 Node 驱动（`tests/check_agent_dsfree.mjs` 的 `STUB_LOOP_ACTIONS`）
 *    **必须逐字一致**：两边同时被 `needConfirm` 与「服务端票据闸门」读，
 *    少一边或差一个 action，同一条用例在两个驱动下的结论就会分叉（双驱动同步是红线）。
 */
const STUB_TOOLS = {
  tools: [{ function: { name: 'bank_manage', description: 'Manage question banks' } }],
  actions: {
    bank_manage: { write: ['create', 'update'], destructive: ['delete', 'delete_many'] },
    question_manage: { write: ['create'], destructive: ['delete', 'delete_many'] },
    // 非破坏性写操作的样本（DF-LOOP-56/57/58）—— 「写操作 × autoConfirm=false」这一格
    // 只有非破坏性动作才判得出来（破坏性恒需确认，缺不缺 autoConfirm 结论一样）。
    note_manage: { write: ['create', 'update'], destructive: ['delete', 'delete_many'] }
  }
}

/**
 * 「这一次调用在**服务端**是否需要确认」—— 确认票据校验用的判据。
 *
 * ⚠️ 刻意在桩里**重算一遍**，不引用被测代码的 `needConfirm()`：引用它就成了
 *    「自己证明自己」，前端少弹一次卡片时两边一起错、用例照样绿。
 *    判据与后端 `loop.needs_user_confirmation` 同口径：破坏性恒需要；
 *    写操作只在 `autoConfirm === false` 时需要（`autoConfirm` 直接读请求体）。
 */
function stubNeedsConfirm(body: any): boolean {
  const meta = (STUB_TOOLS.actions as any)[body?.tool]
  if (!meta) return false
  const a = String(body?.params?.action || '')
  if ((meta.destructive || []).includes(a)) return true
  if ((meta.write || []).includes(a)) return body.autoConfirm === false
  return false
}

/** 每条用例的兜底超时（正常毫秒级就结束，这条只防死循环/挂住） */
const CASE_TIMEOUT_MS = 20000

const sleep0 = () => new Promise((r) => setTimeout(r, 0))

interface LoopScript {
  /** 每一轮「模型回复全文」；轮次越界则重复最后一条 */
  modelScript: string[]
  toolScript: any[]
  chunkSize: number
  throwOnce: boolean
  deepThinkResults: Array<{ ok: boolean; changed: boolean; was: boolean | null }>
  /**
   * 每轮的**推理文本**（深度思考内容），按**累积**形式回调给被测代码。
   *
   * ⚠️ 和 `deepThinkResults` 命名相近但不是一回事：那个是「深度思考开关」，这个是模型吐的思考正文。
   */
  reasoning: string[]
  answerConfirm: boolean
  /**
   * 运行时背景（长期记忆摘要 + 知识库清单）—— 桩掉 `GET /ai/agent/context` 的返回。
   *
   * 与 Node 驱动必须成对：少一边，DF-LOOP-24/25 在面板里就会去请求**真实后端**
   * （拿不到只剩空串），同一条用例两个驱动给出不同结论。
   */
  runtimeContext: string
  /**
   * 本会话的短期历史 —— 桩掉 `GET /ai/agent/context?sessionId=…` 的 `history` 字段。
   *
   * 与 Node 驱动必须成对：同 `runtimeContext`，少一边用例结论就会分叉。
   */
  history: string
  /**
   * 下发给链路的**轮次 id**（turnId）—— 一次用户提问一个，同一次提问里的所有请求复用它。
   *
   * 用例（DF-LOOP-60）拿它断言「`/ai/agent/execute` 的请求体里带着同一个 id」。
   * ⚠️ 与 Node 驱动（`tests/check_agent_dsfree.mjs` 的 `c.turnId`）**必须成对**：
   *    少一边，同一条用例就会一侧绿、一侧红（双驱动同步是红线）。
   */
  turnId?: string
  /**
   * 需要连着跑多次 `runDsFreeAgentStream` 时的 sessionId 序列（第 i 次用第 i 个）。
   *
   * 历史注入是**跨调用**的会话级行为（「换会话才重新注入」），单次调用里测不到 ——
   * 用这个把「同一 session 的第二轮」/「换 session」造出来。
   */
  sessionIds: string[]
  /**
   * `/ai/agent/preview`（确认卡片的 preview + 确认票据）的桩形态：
   *   · 不传 → 接口返回 `{ preview: {} }`，**发不发票据按服务端判据**（读请求体里的
   *     `autoConfirm`；见下面 `stubNeedsConfirm` 的说明）
   *   · `{ result: {...} }` → 返回 `{ preview: result, confirmTicket: … }`
   *   · `{ throws: true }` → 网络层抛错
   *   · `{ status: 500 }` → HTTP 非 2xx
   *   · `{ raw: {...} }` → **整个响应体原样返回**（200）：造「非本接口的形状」
   *     （catch_all 假成功 / `fail()` 信封）—— 见 DF-LOOP-39/40
   *   · `{ ticket: 'tk-x' }` → 钉死下发的票值
   *   · `{ ticket: '' }` → **不下发票据**（造「服务端没给票据」）
   *
   * ⚠️ 与 Node 驱动必须成对（同 `runtimeContext` / `history`：少一边用例结论就分叉）。
   */
  previewStub: { result?: any; throws?: boolean; status?: number; raw?: any; ticket?: string } | null
  /**
   * 第 1 / 2 / 3… 次 `GET /ai/agent/tools` 的状态码（超出数组长度一律 200）。
   *
   * 本来是 TOOLS 套件专用字段；**LOOP 组现在也用它**（DF-LOOP-52 造「工具元信息拉不到」→
   * `needConfirm` 必须 fail-closed）。所以浏览器驱动也必须实现它 ——
   * 面板会跑 LOOP 组，实现里少一边这条用例就会一侧红一侧绿。
   */
  toolsStatuses: number[]
}

/**
 * 跑「协议/循环」组。
 *
 * @param cases 要跑的用例（由面板做前缀筛选）
 * @param onRow 每跑完一条回调一次（面板用来增量渲染；store 里也有一份日志）
 */
export async function runLoopGroup(
  cases: DfCase[],
  onRow?: (row: Row) => void
): Promise<Row[]> {
  const rows: Row[] = []
  const groupSignal = beginAbortGroup()

  // 工具清单是模块级缓存，且**失败也会被缓存**（见 agentDsFree 里的注释）。
  // 开跑前清一次，保证本组拿到的一定是上面那份桩数据，而不是上一次的残留。
  resetAgentToolsCache()

  // 脚本状态：每跑一条用例就复位
  const script: LoopScript = {
    modelScript: [],
    toolScript: [],
    chunkSize: 0,
    throwOnce: false,
    deepThinkResults: [],
    reasoning: [],
    answerConfirm: true,
    runtimeContext: '',
    history: '',
    turnId: undefined,
    sessionIds: [],
    previewStub: null,
    toolsStatuses: []
  }

  for (const c of cases) {
    if (groupAborted()) {
      rows.push(abortedRow(c))
      progress.aborted += 1
      append('warn', '已中止，剩余用例未执行', { caseId: c.id, scope: 'runLoop' })
      continue
    }
    progress.current = c.id
    append('info', `${c.title}`, { caseId: c.id, scope: 'runLoop' })

    script.modelScript = c.model || []
    script.toolScript = c.tools || []
    script.chunkSize = c.chunkSize || 0
    script.throwOnce = !!c.throwOnce
    // 用例里的 `deepThink` 是「每次 ensureDeepThink 的返回值」脚本
    script.deepThinkResults = (c.deepThink as any) || []
    // `reasoning` 是每轮的**推理文本**（深度思考内容），与上一行的开关状态不是一回事
    script.reasoning = c.reasoning || []
    script.answerConfirm = c.answerConfirm !== false
    // 运行时背景：不桩的话 `fetchAgentContext()` 会打到真实后端，用例结论就随真实数据飘
    script.runtimeContext = c.runtimeContext || ''
    script.history = c.history || ''
    // 本轮 id（一次提问一个）：用例断言它原样进 `/ai/agent/execute` 的请求体（DF-LOOP-60）
    script.turnId = c.turnId
    script.sessionIds = c.sessionIds || []
    script.previewStub = c.previewStub || null
    // 「元信息拉不到」的现场（DF-LOOP-52）—— 与 Node 驱动同名同义
    script.toolsStatuses = c.agentToolsGetStatus || []
    // ⚠️ 必须清缓存：`fetchAgentTools` 是**模块级缓存**，而所有用例共用同一个模块实例。
    //    不清的话第一条用例拉到的清单会被后面所有用例复用（Node 驱动同样每例清一次）。
    resetAgentToolsCache()
    // ⚠️ 「已注入过历史的 sessionId」也是模块级状态：不清的话前一条用例留下的
    //    sessionId 会让后一条的「第一轮注入」静默失效（Node 驱动同样每例清一次）。
    resetHistoryInjection()

    // 用例内部产出的记录（相当于 Node 版的 globalThis.__DF_*）
    const fedToModel: string[] = []
    const sysPrompts: string[] = []
    const deepThinkCalls: boolean[] = []
    const toolCalls: string[] = []
    const events: any[] = []
    const confirms: any[] = []
    /** `/ai/agent/preview` 收到的请求体 —— 与 Node 驱动的 `ctx.previewCalls` 同义 */
    const previewCalls: any[] = []
    /** `/ai/agent/execute` 收到的请求体 —— 与 Node 驱动的 `ctx.execBodies` 同义 */
    const execBodies: any[] = []
    /**
     * 服务端**已下发的确认票据**与**已被用掉**的票据（每条用例复位）。
     *
     * 合同 v1：票据一次性 —— 用过的再传一次要被拒。桩里也照这个来，
     * 否则「前端把上一张票据拿去复用」这种错法在本地永远测不出来。
     */
    const issuedTickets = new Set<string>()
    const usedTickets = new Set<string>()
    let round = 0
    let toolIdx = 0
    let dtIdx = 0
    let toolsGet = 0

    const t0 = Date.now()

    // ---- fetch 桩：只拦工具那两个接口 ----
    // ⚠️ 与 Node 版的关键区别：Node 对**任何** URL 都回 `jsonRes({})`（它跑在独立进程里，
    //    污染不了别人）。浏览器里绝对不能照抄 —— 漏还原 / 误拦会把整页的网络请求搞坏。
    //    所以这里非目标 URL 一律**透传**给原生 fetch，并在 finally 里无条件还原。
    const realFetch = globalThis.fetch
    globalThis.fetch = (async (input: any, init?: any) => {
      const url = String(typeof input === 'string' ? input : input?.url || '')
      if (url.includes('/ai/agent/tools')) {
        // 「元信息拉不到」：状态码脚本化（DF-LOOP-52 用它造 `_toolsCache` 恒为 null 的现场）
        toolsGet += 1
        const status = script.toolsStatuses[toolsGet - 1] || 200
        if (status >= 400) return badRes(status)
        return jsonRes(STUB_TOOLS)
      }
      // 运行时背景 + 本会话历史：返回用例脚本里那两段（拿不到的用例传空串）
      if (url.includes('/ai/agent/context')) {
        return jsonRes({ context: script.runtimeContext, history: script.history })
      }
      if (url.includes('/ai/agent/execute')) {
        const body = JSON.parse(init?.body || '{}')
        toolCalls.push(`${body.tool}.${body.params?.action}`)
        // 请求体也留一份：断言「需要确认时带了票据 / 不需要时不带」
        execBodies.push(body)
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
        const r = script.toolScript[Math.min(toolIdx, script.toolScript.length - 1)]
        toolIdx += 1
        return jsonRes(r ?? { success: true })
      }
      // 写操作预演（确认卡片的 preview + 一次性确认票据）—— 与 Node 驱动同一套桩形态，
      // 见 LoopScript.previewStub
      if (url.includes('/ai/agent/preview')) {
        const body = JSON.parse(init?.body || '{}')
        previewCalls.push(body)
        const s = script.previewStub || {}
        if (s.throws) throw new Error('preview 接口网络异常（脚本注入）')
        if (s.status && s.status >= 400) return badRes(s.status)
        // `raw` = 整个响应体原样返回（200）：造**非本接口的形状**（catch_all 假成功 / fail 信封）
        if (s.raw !== undefined) {
          // 原样返回也要把票据收下（票据就在响应体里，契约如此）
          if (typeof s.raw?.confirmTicket === 'string' && s.raw.confirmTicket) {
            issuedTickets.add(s.raw.confirmTicket)
          }
          return jsonRes(s.raw)
        }
        // 票据：不传 = **按服务端判据**决定发不发；`ticket: ''` = **不下发票据**
        //（造「服务端没给」）；传字符串 = 钉死票值。
        //
        // ⚠️⚠️ `ticket` 不传时**不再是无条件发一张**：真服务端 `preview_agent_tool` 是
        //    `if needs_user_confirmation(tool, params, auto_confirm): result["confirmTicket"] = …`
        //    ——判据**读请求体里的 autoConfirm**（与执行侧同一个函数）。
        //    桩里必须演这一层，否则 DF-LOOP-56 那种「前端漏传 autoConfirm ⇒ 服务端按 true 判
        //    ⇒ 不发票据」的死锁在面板里**测不出来**（桩会慷慨地发一张，用例假绿）。
        //    判据复用 `stubNeedsConfirm`（同一个函数 ⇒「发不发票」与「要不要校验票」同源）。
        //    ⚠️ 与 Node 驱动（`check_agent_dsfree.mjs` 的 preview 桩）**必须逐字一致**。
        const ticket =
          s.ticket !== undefined
            ? s.ticket
            : stubNeedsConfirm(body)
              ? `tk-${previewCalls.length}`
              : ''
        if (ticket) issuedTickets.add(ticket)
        const out: any = { preview: s.result ?? {} }
        if (ticket) out.confirmTicket = ticket
        return jsonRes(out)
      }
      return realFetch(input, init)
    }) as typeof fetch

    const abort = linkAbort(CASE_TIMEOUT_MS, groupSignal)
    let answer = ''
    let thrown = ''

    // 捕获 `console.warn`：`fetchToolPreview` 的「响应缺 `preview` 键」警告**是新逻辑的一部分**
    //（它才是「路由改名 / 被 catch_all 兜成 200」的唯一信号），不抓就断言不到那条分支
    // —— 见 DF-LOOP-40。
    // ⚠️ 与 Node 驱动（`check_agent_dsfree.mjs` 的 `realWarn` 捕获）**必须成对**：
    //    ctx 少一边，同一条用例就会一侧绿、一侧红。
    const warns: string[] = []
    const realWarn = console.warn
    console.warn = (...a: any[]) => {
      warns.push(a.map((x) => String(x)).join(' '))
    }

    try {
      await __withDSSeam(
        {
          // 模型：按脚本逐字（或按 chunkSize 分帧）吐出来
          chat: async (o: any) => {
            const i = round
            round += 1
            fedToModel.push(o.userMessage || '')
            sysPrompts.push(o.systemPrompt || '')
            if (script.throwOnce && i === 0) throw new Error('扩展连接中断（脚本注入）')
            // 思考过程：真链路里 `chatWithDSAccumulated` 交给调用方的是**累积**全文
            // （见那边的归一化 + 节流逻辑），所以桩这里也按累积回调 ——
            // 「上游给累积、agentDsFree 自己 diff 成增量」这一步正是要测的东西。
            // ⚠️ 用 `script.reasoning` 而不是 `script.deepThink`：后者是「深度思考开关」。
            const reasoning =
              script.reasoning?.[Math.min(i, (script.reasoning?.length || 1) - 1)] || ''
            if (reasoning) {
              const rsize = Math.max(1, Math.ceil(reasoning.length / 3))
              for (let p = 0; p < reasoning.length; p += rsize) {
                o.onThinking?.(reasoning.slice(0, p + rsize))
                await sleep0()
              }
            }
            const full = script.modelScript[Math.min(i, script.modelScript.length - 1)] || ''
            const size =
              script.chunkSize > 0 ? script.chunkSize : Math.max(1, Math.ceil(full.length / 2))
            for (let p = 0; p < full.length; p += size) {
              o.onChunk?.(full.slice(0, p + size))
              await sleep0()
            }
            if (!full) o.onChunk?.('')
            return full
          },
          // 深度思考：记下**实参**（用例要断言「目标是开」，不是只看调用次数），再按脚本回状态
          ensureDeepThink: async (on: boolean) => {
            deepThinkCalls.push(on)
            const r = script.deepThinkResults[Math.min(dtIdx, script.deepThinkResults.length - 1)]
            dtIdx += 1
            return r || { ok: true, changed: false, was: true }
          }
        },
        async () => {
          // 缺省只跑一次、且不传 sessionId（老用例行为完全不变）。
          // 传了 `sessionIds` 就按顺序连着跑多次 —— 历史注入是**跨调用**的会话级行为，
          // 单次调用里测不到（见上面 LoopScript.sessionIds 的说明）。
          const sessionIds = script.sessionIds.length ? script.sessionIds : ['']
          let last = ''
          for (const sid of sessionIds) {
            last = await runDsFreeAgentStream(
              {
                message: c.prompt || '测试',
                model: 'deepseek-free',
                userId: 1,
                sessionId: sid || undefined,
                // 本轮 id —— 与 Node 驱动同名字段，少一边 DF-LOOP-60 就会一侧红一侧绿
                turnId: script.turnId,
                autoConfirm: c.opts?.autoConfirm !== false,
                maxLoops: c.opts?.maxLoops,
                signal: abort.signal
              },
              {
                onEvent: (e: any) => events.push(e),
                onConfirm: async (info: any) => {
                  confirms.push(info)
                  return script.answerConfirm
                }
              }
            )
          }
          return last
        }
      )
        .then((a) => {
          answer = a
        })
        .catch((e: any) => {
          thrown = String(e?.message || e)
        })
    } finally {
      globalThis.fetch = realFetch
      console.warn = realWarn
      abort.done()
    }

    const secs = Number(((Date.now() - t0) / 1000).toFixed(3))
    const ctx = {
      events,
      eventTypes: events.map((e: any) => e.type),
      answer: String(answer || ''),
      toolCalls,
      fedToModel,
      sysPrompts,
      deepThinkCalls,
      confirms,
      previewCalls,
      /** `/ai/agent/execute` 收到的请求体 —— 与 Node 驱动的 `ctx.execBodies` 同义 */
      execBodies,
      /** 本用例期间 `console.warn` 收到的文本 —— 与 Node 驱动的 `ctx.warnings` 同义（DF-LOOP-40） */
      warnings: warns,
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

    // 失败时把「实际是什么」写进日志 —— 只有断言标签没法排查
    const failed = asserts.filter((a) => !a.pass)
    append(aborted ? 'warn' : ok ? 'pass' : 'fail', c.title, {
      caseId: c.id,
      scope: 'runLoop',
      detail: failed.length
        ? failed.map((a) => `✗ ${a.label}${a.actual ? ` → ${a.actual}` : ''}`).join('\n')
        : undefined
    })
    // 原始轨迹放 debug 级别：平时不吵，要看协议怎么跑偏的时候勾上就全都有
    append('debug', `事件流：${ctx.eventTypes.join(' → ') || '(无事件)'}`, {
      caseId: c.id,
      scope: 'runLoop',
      detail: [
        `工具调用：${toolCalls.join('、') || '(无)'}`,
        `深度思考调用：${deepThinkCalls.length ? deepThinkCalls.map(String).join('、') : '(无)'}`,
        `确认卡片：${confirms.length} 次`,
        thrown ? `抛异常：${thrown}` : ''
      ]
        .filter(Boolean)
        .join('\n')
    })

    progress.done += 1
    if (aborted) progress.aborted += 1
    else ok ? (progress.passed += 1) : (progress.failed += 1)
    onRow?.(row)
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

/** 让 JSON 形状的桩响应看起来像 Response（`fetchAgentTools` 只用到 ok / json） */
function jsonRes(o: any) {
  return {
    ok: true,
    status: 200,
    async json() {
      return o
    },
    async text() {
      return JSON.stringify(o)
    }
  }
}

/** 非 2xx 的桩响应（测「HTTP 报错也要降级」时用；调用方只看 `ok` / `status`） */
function badRes(status: number) {
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

/**
 * 给一条用例挂超时，并跟随分组级 abort。
 *
 * 没用 `AbortSignal.any` / `AbortSignal.timeout`：前者要 Chrome 116+、后者要 124+，
 * 手写这十几行没有兼容性风险，也不会有「组合信号什么时候被回收」这种隐性坑。
 */
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

/**
 * 预热：只为了在开跑前把 `_toolsCache` 填好（顺便验证 fetch 桩链路通）。
 * 面板用它做「环境自检」，失败不影响后面 —— 真正的拉取在第一次用例里还会再做一次。
 */
export async function warmUpLoopGroup(): Promise<{ ok: boolean; message: string }> {
  try {
    resetAgentToolsCache()
    const realFetch = globalThis.fetch
    globalThis.fetch = (async (input: any, init?: any) => {
      const url = String(typeof input === 'string' ? input : input?.url || '')
      if (url.includes('/ai/agent/tools')) return jsonRes(STUB_TOOLS)
      return realFetch(input, init)
    }) as typeof fetch
    try {
      const tools = await fetchAgentTools()
      return {
        ok: tools.length > 0,
        message: tools.length ? `工具清单就绪（${tools.length} 个）` : '工具清单为空'
      }
    } finally {
      globalThis.fetch = realFetch
    }
  } catch (e: any) {
    return { ok: false, message: String(e?.message || e) }
  }
}
