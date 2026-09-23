/**
 * DS Proxy 统一封装（v2 / TS 版）
 *
 * DS Proxy 是「DS Proxy」浏览器扩展通过 content script（bridge.js）注入到页面的 SDK，
 * 挂在 `window.DSProxy` 上。它经 postMessage 与 chat.deepseek.com 标签页通信：
 *   · 发送：在 DS 页做 DOM 自动化（填输入框、点深度思考、点发送）
 *   · 接收：由 MAIN world 的 interceptor.js 劫持页面自身的 SSE 流，分片回流
 *
 * 因为请求是 DS 页面自己发的，PoW / TLS 指纹 / 行为遥测天然满足，
 * 本方案不需要任何 token、cookie 维护，也没有账号风控风险。
 *
 * 相比 springboot3 版的改进：
 *   1. 单飞（single-flight）初始化：并发调用共享同一个 Promise，不会创建多个实例
 *   2. 首次检查 window.DSProxy 立即返回，扩展已就绪时不再空等
 *   3. 轮询定时器在成功/超时后一定清理，避免泄漏
 *   4. getStatus 结果做形状校验，扩展版本不一致时给出明确报错
 *   5. 移除已废弃的「专家 / 识图」模式切换（DS 官网已合并，默认支持上传图片）
 */

/**
 * 扩展 `DSPROXY_GET_STATUS` 的返回。
 *
 * ⚠️ 刻意**不声明 `loggedIn`**：扩展压根不返回它（见 `isDSReady` 的说明）。
 *    留着这个字段只会诱使别人再写出「`status.loggedIn` 恒 false」那种死条件。
 */
export interface DSProxyStatus {
  /** chat.deepseek.com 标签页开着 */
  dsTabOpen?: boolean
  /** 扩展视角的「就绪」 */
  ready?: boolean
  tabCount?: number
  [key: string]: unknown
}

export interface DSAttachment {
  name: string
  type: string
  /** 完整 data URL，例如 data:image/png;base64,xxxx */
  base64: string
}

export interface ChatWithDSOptions {
  /** 系统提示词。DS 网页版没有 system role，会自动拼接到用户消息前面 */
  systemPrompt?: string
  /** 用户消息正文 */
  userMessage: string
  /** 正式回复的流式回调，text 为累积全文 */
  onChunk?: (text: string) => void
  /** 深度思考过程的流式回调，text 为累积全文 */
  onThinking?: (text: string) => void
  /** 图片附件（DS 现已默认支持上传图片） */
  images?: DSAttachment[]
  /** 其它文件附件 */
  files?: DSAttachment[]
  /** 超时毫秒，默认 5 分钟 */
  timeout?: number
}

/** `chatWithDSAccumulated` 的入参（在 ChatWithDSOptions 之上多两个流式控制项） */
export interface ChatWithDSAccumulatedOptions extends ChatWithDSOptions {
  onChunk?: (full: string) => void
  thinkingThrottleMs?: number
}

/** 扩展注入 SDK 的等待超时（毫秒） */
const SDK_LOAD_TIMEOUT = 5000
/** 轮询间隔（毫秒） */
const POLL_INTERVAL = 100

let _instance: DSProxy | null = null
let _pending: Promise<DSProxy> | null = null

// =====================================================================
// 测试缝（仅开发环境生效）
// =====================================================================
/**
 * ds-free 的「协议/循环」自检要跑真源码，但必须把**模型回复脚本化** ——
 * 也就是把「和 DS 页面通信」这一层整个替换掉，且一个字节都不能真发给 DS。
 *
 * Node 版自检（`tests/check_agent_dsfree.mjs`）靠 Vite SSR 的 `resolveId` 把
 * `@/utils/ds-proxy` 换成桩模块；浏览器里没有这套机制，所以缝只能长在这里。
 *
 * 为什么缝在这一层，而不是给 `AgentStreamOptions` 加测试字段：
 *   · `AgentStreamOptions` 被 `runDsFreeAgentStream` 与 `postAgentStream` 共用，
 *     塞测试字段等于给所有读者加一条隐式约定；
 *   · 缝保持「整个 `chatWithDSAccumulated` / `ensureDeepThink` 被替换」这一粒度，
 *     `api/ai/agentDsFree.ts` 的循环本体才能**一行不改** —— 被测代码与生产逐字一致。
 *
 * ⚠️ 两个调用点都在 `api/ai/agentDsFree.ts`（`ensureDeepThink` / `chatWithDSAccumulated`），
 *    它们读的是本模块导出的函数，所以在这里判一下就够了，用不着改调用方。
 */
export interface DSSeam {
  chat?: (options: ChatWithDSAccumulatedOptions) => Promise<string>
  ensureDeepThink?: (on: boolean) => Promise<{ ok: boolean; changed: boolean; was: boolean | null }>
}

let _seam: DSSeam | null = null

/** 当前是否处于「模型被脚本化」状态（自检运行中应为 true） */
export function __dsSeamActive(): boolean {
  return _seam !== null
}

/**
 * 在缝内跑一段逻辑，结束后**自动还原**（异常 / 超时中止也还原）。
 *
 * 刻意做成作用域式而不是 `__setSeam` / `__clearSeam` 两个 API：
 * 后者调用方一旦忘了还原，整页的模型调用就一直是脚本化的 —— 用 `try/finally` 从结构上消掉这个可能。
 *
 * 生产里 `import.meta.env.DEV` 会被静态替换成 `false`，写入覆盖的那条路径是死代码，
 * 语义为零（`_seam` 永远是 null）。
 */
export async function __withDSSeam<T>(seam: DSSeam, fn: () => Promise<T>): Promise<T> {
  if (!import.meta.env.DEV) return fn()
  const prev = _seam
  _seam = seam
  try {
    return await fn()
  } finally {
    _seam = prev
  }
}

/** 是否检测到扩展注入的 SDK（不做等待，用于 UI 提前提示） */
export function hasDSProxy(): boolean {
  return typeof window !== 'undefined' && !!(window as any).DSProxy
}

/**
 * 获取 DS Proxy 实例（单例 + 单飞）
 *
 * 多个组件同时调用只会等同一个 Promise，不会重复构造实例。
 */
export function getDSProxy(timeout = SDK_LOAD_TIMEOUT): Promise<DSProxy> {
  if (_instance) return Promise.resolve(_instance)
  if (_pending) return _pending

  _pending = new Promise<DSProxy>((resolve, reject) => {
    let timer: ReturnType<typeof setTimeout> | null = null

    const done = () => {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
    }

    const check = () => {
      const Ctor = (window as any).DSProxy
      if (Ctor) {
        done()
        _instance = new Ctor()
        _pending = null
        resolve(_instance as DSProxy)
        return
      }
      timer = setTimeout(check, POLL_INTERVAL)
    }

    // 扩展已就绪时立即返回，不空等一个轮询周期
    if (hasDSProxy()) {
      check()
      return
    }

    timer = setTimeout(() => {
      done()
      _pending = null
      reject(new Error('未检测到 DS Proxy 扩展，请确认扩展已安装并启用'))
    }, timeout)

    check()
  })

  return _pending
}

/**
 * 检查 DS 通道是否就绪（扩展在 + chat.deepseek.com 标签页开着）
 *
 * ⚠️ **这里查不了「登录没登录」** —— 别再写成 `status.loggedIn`。
 *
 *    扩展的 `DSPROXY_GET_STATUS`（`extension/background.js` 的 `getStatus()`）返回的是
 *    `{ dsTabOpen, ready, tabCount }`，**根本没有 `loggedIn` 字段**；
 *    SDK 的 `getStatus()` 也只映射 `dsTabOpen` / `ready`。
 *    （登录态只在扩展向后端做健康上报时用 `detectLoginIssue()` 探一次，
 *      走的是 `getHealth()` 那条 REST 路径，不在这个通道里。）
 *
 *    所以 `!!status?.loggedIn` 恒为 `undefined` → 整个表达式恒 `false`。
 *    这个函数以前就这么写着，只是没有任何调用方，一直没暴露 ——
 *    直到 ds-free 自检前置检查用它，才出现「DS 页面明明开着却报检测不到」。
 *
 * 需要真正的登录态时用 `getHealth()`（走后端聚合，要求后端在跑、扩展上报过）。
 */
export async function isDSReady(): Promise<boolean> {
  try {
    const dsp = await getDSProxy()
    const status = await dsp.getStatus()
    return !!status?.dsTabOpen || !!status?.ready
  } catch {
    return false
  }
}

/**
 * 转成「可结构化克隆」的纯对象（JSON 深拷贝）。
 *
 * ⚠️ 传附件前**必须**做这一步：附件数组往往直接来自 Vue 的 ref/reactive，
 * 元素是响应式 Proxy；而扩展 SDK 用 `window.postMessage` 把消息送到 bridge，
 * 走的是结构化克隆 —— **Proxy 无法被克隆**，会直接抛：
 *   Failed to execute 'postMessage' on 'Window': #<Object> could not be cloned.
 * 症状极具迷惑性：纯文字聊天一切正常，一传图片/文件就「发送失败」。
 *
 * 这里把 base64 字符串也一并断开与响应式对象的引用，顺带减少 isReactive 追踪开销。
 */
function toPlain<T>(value: T): T {
  if (value === null || value === undefined) return value
  try {
    return JSON.parse(JSON.stringify(value)) as T
  } catch {
    return value
  }
}

/** 从 data URL 头部抠出 MIME（拿不到就给 image/png） */
function mimeOfDataUrl(dataUrl: string): string {
  return /^data:([^;,]*)/i.exec(dataUrl || '')?.[1] || 'image/png'
}

/**
 * 把图片列表归一化成扩展要求的 `{name, type, base64}` 对象
 *
 * ⚠️ 这是**必须的边界兜底**，不是多余的防御：
 *   扩展 `background.js` 读的是 `img.base64` ——
 *     `if (!img.base64) { log('IMG[i]: SKIP - no base64'); continue }`
 *   一旦调用方传了裸 data URL **字符串**，`img.base64` 就是 undefined，
 *   于是每一张图都被**静默丢掉**：文字正常、工具正常，就是图一张都到不了 DS。
 *   agent 链路历史上就这么翻过车，所以在这里再兜一层 —— 字符串自动包成对象，
 *   同时打一条 warning 把调用方揪出来。
 */
function normalizeImages(images: unknown): DSAttachment[] {
  if (!Array.isArray(images)) return []
  return images.map((item, i) => {
    if (typeof item === 'string') {
      if (item) {
        console.warn(
          `[ds-free] 第 ${i + 1} 张图片传的是裸 data URL 字符串，已自动包装成附件对象；` +
            '调用方应按 DSAttachment（{name,type,base64}）传，否则扩展会整张丢弃'
        )
      }
      const mime = mimeOfDataUrl(item)
      return { name: `image_${i + 1}.${mime.split('/')[1] || 'png'}`, type: mime, base64: item }
    }
    const att = (item || {}) as DSAttachment
    return {
      name: att.name || `image_${i + 1}.png`,
      type: att.type || mimeOfDataUrl(att.base64),
      base64: att.base64 || ''
    }
  })
}

/**
 * 通过 DS Proxy 对话（流式）
 *
 * @returns 完整回复文本
 */
export async function chatWithDS(options: ChatWithDSOptions): Promise<string> {
  const {
    systemPrompt = '',
    userMessage,
    onChunk,
    onThinking,
    images = [],
    files = [],
    timeout = 300000
  } = options

  const dsp = await getDSProxy()

  const status = await dsp.getStatus()
  if (!status || typeof status !== 'object') {
    throw new Error('扩展返回的状态异常，请更新扩展版本')
  }
  if (!status.dsTabOpen) {
    throw new Error('DeepSeek 页面未打开，请先打开 chat.deepseek.com 并登录')
  }

  // DS 网页版无 system role，把 system prompt 拼到用户消息前。
  // 纯附件消息（用户只传图/文件、不写文字）时 userMessage 为空，
  // 此时只发提示词，避免往输入框里塞一段空的「## 用户消息」段落。
  const content = userMessage
    ? systemPrompt
      ? `${systemPrompt}\n\n## 用户消息\n\n${userMessage}`
      : userMessage
    : systemPrompt

  return dsp.sendMessageWithImages(content, toPlain(normalizeImages(images)), {
    timeout,
    fileDataList: files.length > 0 ? toPlain(files) : null,
    onThinking: (text: string) => onThinking?.(text),
    onChunk: (text: string) => onChunk?.(text)
  })
}

/**
 * 适配 v2 后端约定的对话入口（onChunk 收「累积全文」）
 *
 * 扩展 SDK 的 onChunk 语义在不同版本间可能是「增量」也可能是「累积」，
 * 这里统一归一化后再回调，调用方拿到的始终是累积全文，
 * 与 api/ai/ai.ts 里 assistantStream 的契约保持一致。
 */
export async function chatWithDSAccumulated(
  options: ChatWithDSAccumulatedOptions
): Promise<string> {
  // 自检运行时模型是被脚本化的（见 __withDSSeam）—— 直接走缝，不碰 DS 页面
  if (_seam?.chat) return _seam.chat(options)

  let full = ''
  let thinking = ''
  let lastThinkingEmit = 0
  let pendingTimer: ReturnType<typeof setTimeout> | null = null
  // 思考过程节流：扩展每 50ms 推一次累积文本，若每次都整段替换 +
  // 重排 + 自动滚动，长思考文本下会把界面抖成幻灯片。
  const throttleMs = options.thinkingThrottleMs ?? 150

  const emitThinking = (force = false) => {
    const now = Date.now()
    if (!force && now - lastThinkingEmit < throttleMs) {
      // 落在节流窗口内：安排一次尾部补发，保证最后一段不丢
      if (pendingTimer === null) {
        pendingTimer = setTimeout(() => {
          pendingTimer = null
          lastThinkingEmit = Date.now()
          options.onThinking?.(thinking)
        }, throttleMs)
      }
      return
    }
    lastThinkingEmit = now
    options.onThinking?.(thinking)
  }

  /**
   * 把待发的思考**立刻**补出去（清掉节流定时器）。
   *
   * 没有待发内容时是 no-op，所以可以放心挂在每个 `onChunk` 上。
   */
  const flushThinking = () => {
    if (pendingTimer === null) return
    clearTimeout(pendingTimer)
    pendingTimer = null
    emitThinking(true)
  }

  const text = await chatWithDS({
    ...options,
    onChunk: (incoming: string) => {
      if (!incoming) return
      // ⚠️ 正文开始前，必须先把待发的思考刷出去。别删这一行 ——
      //    DS 页面切换相位时，**最后一个思考 delta 和答案几乎同时到**，
      //    而尾发是 `setTimeout(throttleMs)`：不刷这一帧，补发就会落在答案**之后**，
      //    UI 上表现为「残缺思考块（只有前几个字符）→ 答案 → 剩下的思考」，
      //    用户得把两块拼起来才看出是同一段推理（线上 2026-09-19 报过，见 DF-PROXY-11）。
      flushThinking()
      // 累积式：新值以当前全文为前缀 → 直接替换；否则视为增量 → 追加
      full = incoming.startsWith(full) ? incoming : full + incoming
      options.onChunk?.(full)
    },
    onThinking: (incoming: string) => {
      if (!incoming) return
      thinking = incoming.startsWith(thinking) ? incoming : thinking + incoming
      emitThinking()
    }
  })

  // 收尾：把待发的补出去；一次都没发过（thinking 非空但没有待发任务）时强制刷最后一帧
  if (pendingTimer !== null) flushThinking()
  else if (thinking) emitThinking(true)

  // 兜底：SDK 直接 resolve 了完整文本
  if (text && !full) {
    full = text
    options.onChunk?.(full)
  }
  return full
}

/** 读取 DS 网页版深度思考开关状态；null 表示读取失败 */
export async function getDeepThink(): Promise<boolean | null> {
  try {
    const dsp = await getDSProxy()
    return (await dsp.getDeepThink()) ?? null
  } catch {
    return null
  }
}

/**
 * 确保 DS 网页端的「深度思考」处于指定状态（已经是目标值就一个字节都不改）
 *
 * 为什么不是直接 `setDeepThink(on)`：
 *   · **要知道「到底改没改」**。Agent 模式会自动把它打开，得能对用户说一句
 *     「刚才是快速模式，已经帮你切成深度思考了」—— 否则用户只会觉得「响应怎么变慢了」，
 *     而不知道这正是修掉工具调用格式错误的关键。
 *   · 状态一致时省掉一次 postMessage → 标签页 → 回传的往返。
 *
 * ⚠️ 读不到状态（`was === null`：扩展没装 / DS 页面没开）时**直接返回失败，不要硬写**
 *    —— 写了也不知道成没成，只会多一次静默失败。
 *
 * @returns `ok` 表示当前确实处于目标状态；`changed` 表示这次调用真的翻动了开关
 */
export async function ensureDeepThink(
  on: boolean
): Promise<{ ok: boolean; changed: boolean; was: boolean | null }> {
  // 自检时深度思考状态也是脚本化的（见 __withDSSeam），不读 DS 页面
  if (_seam?.ensureDeepThink) return _seam.ensureDeepThink(on)

  const target = !!on
  const was = await getDeepThink()
  if (was === null) return { ok: false, changed: false, was: null }
  if (was === target) return { ok: true, changed: false, was }
  const ok = await setDeepThink(target)
  return { ok, changed: ok, was }
}

/** 设置 DS 网页版深度思考开关 */
export async function setDeepThink(on: boolean): Promise<boolean> {
  try {
    const dsp = await getDSProxy()
    const res: any = await dsp.setDeepThink(!!on)
    // 扩展侧会回传结构化结果 { ok, changed, deepThinkOn, error, candidates }。
    // 注意判据是 `ok !== true` 而不是 `ok === false`：
    // 消息投递失败时返回对象可能连 ok 字段都没有，用 === false 会漏掉这种情况。
    if (res && typeof res === 'object' && (res as any).ok !== true) {
      console.warn(
        '[ds-free] 设置 DS 页面「深度思考」未成功:',
        (res as any).error || JSON.stringify(res).slice(0, 300)
      )
      return false
    }
    return true
  } catch (e) {
    console.warn('[ds-free] 设置 DS 页面「深度思考」异常:', e)
    return false
  }
}

/** 重置实例缓存（切换账号、扩展重载后调用） */
export function resetDSProxy(): void {
  _instance = null
  _pending = null
}

/**
 * 扩展注入的 SDK 实例类型。
 * 只声明本项目实际用到的成员，其余保持宽松，便于兼容扩展的小版本升级。
 */
export interface DSProxy {
  getStatus(): Promise<DSProxyStatus>
  getDeepThink(): Promise<boolean>
  setDeepThink(on: boolean): Promise<void>
  sendMessageWithImages(
    content: string,
    images: DSAttachment[],
    options?: {
      timeout?: number
      fileDataList?: DSAttachment[] | null
      onThinking?: (text: string) => void
      onChunk?: (text: string) => void
    }
  ): Promise<string>
  /** 打开新会话（扩展支持时可用） */
  openNewChat?(): Promise<void>
  cancel?(requestId?: string): Promise<void>
}

declare global {
  interface Window {
    DSProxy?: new () => DSProxy
  }
}
