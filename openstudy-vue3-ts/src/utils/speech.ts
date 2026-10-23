/**
 * 浏览器语音合成（TTS）封装
 * ============================================================================
 * 2026-10-23 新增。项目里原本三处各自手写 `new SpeechSynthesisUtterance(...)`，
 * 每一处都踩了同样的坑，表现为「点了没声音 / 点了没反应」：
 *
 * ① **cancel() 后立刻 speak() 会被 Chrome 静默丢弃**
 *    这是 Chromium 的老问题：`speechSynthesis.cancel()` 紧接着 `speak()`，
 *    新说的话有概率根本不进入播放队列，且**不报错、不触发 onend**。
 *    而三处代码都在播放前先 cancel() —— 于是"第一次能响，之后点就哑了"。
 *    对策：cancel 之后等一小会儿（settleMs）再 speak。
 *
 * ② **onerror 被吞掉，用户永远不知道为什么没声音**
 *    原代码一律 `utterance.onerror = () => resolve()`。
 *    没装对应语言的语音、被浏览器策略拦下（not-allowed）、
 *    合成引擎不可用……全部静默。用户看到的就是"点了没反应"。
 *    对策：把错误码透出来，交给调用方提示。
 *
 * ③ **没有任何超时兜底**
 *    一旦引擎卡住（speaking 一直 true、onend 永不到来），
 *    调用方的 `isPlaying` 永远是 true —— 按钮如果是 `:loading="isPlaying"`，
 *    Element Plus 会把 loading 同时变成 disabled 并在 handleClick 里直接 return，
 *    于是按钮**永久点不动**。
 *    对策：startTimeoutMs 看门狗，没真正开始发声就判定失败并重试一次。
 *
 * 另外补充：
 *  · `getVoices()` 首次返回空数组是正常的（异步加载），需要等 voiceschanged；
 *  · 优先挑 `localService` 的本地语音，避免依赖网络；
 *  · speak 前 resume() 一次，绕开 Chrome "队列莫名 paused" 的问题。
 */

/** 失败原因 */
export type SpeakReason =
  | 'unsupported'   // 浏览器不支持语音合成
  | 'empty'         // 没有可读的文本
  | 'no-voice'      // 系统里没有对应语言的语音包
  | 'not-allowed'   // 被浏览器自动播放策略拦下（缺用户手势）
  | 'interrupted'   // 被新的播放打断 / 主动停止
  | 'canceled'      // 同上（旧浏览器用这个码）
  | 'failed'        // 其它失败（引擎卡住 / 合成不可用）

export interface SpeakResult {
  ok: boolean
  reason?: SpeakReason
  /** 原始错误对象，便于排查 */
  error?: unknown
}

export interface SpeakOptions {
  /** BCP-47，如 'en-US' / 'zh-CN' */
  lang?: string
  rate?: number
  pitch?: number
  volume?: number
  /** cancel 之后到 speak 之间的等待，规避 Chrome 丢帧。默认 80ms */
  settleMs?: number
  /** 超过这个时间还没真正开始发声，就判定失败。默认 1200ms */
  startTimeoutMs?: number
  /**
   * 浏览器 TTS 失败时，是否回退到服务端合成（`/tts/synthize`）。
   * 默认 true —— 部分环境下浏览器 TTS 完全不出声，兜底是唯一的出路。
   */
  fallbackToServer?: boolean
}

/** 每次播放自增，用于作废"上一轮还没结束的回调" */
let speakToken = 0

/**
 * 浏览器 TTS 是否被判定为「坏了」。
 *
 * 一旦某次失败原因是 `failed`（引擎拿到请求却不发声），就把这个标记置上，
 * 之后**直接走服务端合成**，不再让每个词都干等一次超时。
 * 刷新页面会重置（模块级变量）。
 */
let browserTtsBroken = false

/** 服务端合成结果的 URL 缓存：同一个词不用反复请求 */
const serverAudioCache = new Map<string, string>()

function synth(): SpeechSynthesis | undefined {
  if (typeof window === 'undefined') return undefined
  return window.speechSynthesis || undefined
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** 浏览器是否支持语音合成 */
export function isSpeechSupported(): boolean {
  return !!synth() && typeof window !== 'undefined' && typeof window.SpeechSynthesisUtterance === 'function'
}

/** 当前是否正在朗读 */
export function isSpeaking(): boolean {
  const s = synth()
  return !!s && (s.speaking || s.pending)
}

let voicesPromise: Promise<SpeechSynthesisVoice[]> | null = null
let voicesCache: SpeechSynthesisVoice[] = []

/**
 * 取可用语音列表。
 * 首次调用 `getVoices()` 常常是空数组（浏览器异步加载语音包），
 * 这里等到 `voiceschanged` 或超时，避免"第一次点没声音、第二次才有"。
 *
 * ⚠️ 只缓存**非空**结果：早期版本把空数组也缓存了，导致
 *    第一次探测超时后，即使语音包随后加载完成，也会永远返回空列表
 *    —— 表现为"刷新页面第一次不响，之后一直不响"。
 */
export function loadVoices(timeoutMs = 1500): Promise<SpeechSynthesisVoice[]> {
  const s = synth()
  if (!s || typeof s.getVoices !== 'function') return Promise.resolve([])

  const immediate = s.getVoices() || []
  if (immediate.length) {
    voicesCache = immediate
    return Promise.resolve(immediate)
  }
  if (voicesCache.length) return Promise.resolve(voicesCache)
  if (voicesPromise) return voicesPromise

  voicesPromise = new Promise<SpeechSynthesisVoice[]>((resolve) => {
    let done = false
    const finish = (list: SpeechSynthesisVoice[]) => {
      if (done) return
      done = true
      try { s.onvoiceschanged = null } catch { /* 忽略 */ }
      if (list.length) voicesCache = list
      voicesPromise = null
      resolve(list || [])
    }

    const timer = setTimeout(() => finish(s.getVoices() || []), timeoutMs)

    s.onvoiceschanged = () => {
      clearTimeout(timer)
      finish(s.getVoices() || [])
    }

    // 有些环境不会触发事件，但此时已经能取到
    const again = s.getVoices() || []
    if (again.length) {
      clearTimeout(timer)
      finish(again)
    }
  })

  return voicesPromise
}

/**
 * 预热语音列表。
 *
 * 应当在页面初始化时调用一次（onMounted），把 `getVoices()` 的结果提前放进
 * 同步缓存 —— 这样用户真正点"播放"时，`speak()` 里不需要为了拿语音列表
 * 而 `await`，从而保住用户手势上下文（见 `speak()` 顶部注释）。
 *
 * 不调用也能工作，只是首次点击时可能选不到最合适的 voice
 * （引擎会按 `lang` 自己挑，通常也能出声）。
 */
export function warmUpVoices(): void {
  const s = synth()
  if (!s || typeof s.getVoices !== 'function') return

  const fill = () => {
    const vs = s.getVoices() || []
    if (vs.length) voicesCache = vs
  }

  fill()
  if (!voicesCache.length) {
    // 首帧常为空；等一次 voiceschanged。这里**不阻塞**任何调用。
    try {
      const prev = s.onvoiceschanged
      s.onvoiceschanged = (ev: Event) => {
        fill()
        if (typeof prev === 'function') {
          try { (prev as any).call(s, ev) } catch { /* 忽略 */ }
        }
      }
    } catch { /* 忽略 */ }
    // 兜底轮询：有的环境不派发 voiceschanged
    let tries = 0
    const timer = setInterval(() => {
      fill()
      if (voicesCache.length || ++tries > 20) clearInterval(timer)
    }, 250)
  }
}

/** 按语言挑一个语音：先精确匹配，再按主语言前缀匹配，优先本地语音 */
export function pickVoice(voices: SpeechSynthesisVoice[], lang: string): SpeechSynthesisVoice | null {
  if (!voices.length) return null
  const want = String(lang || '').toLowerCase().replace('_', '-')
  const base = want.split('-')[0]

  const norm = (v: SpeechSynthesisVoice) => String(v.lang || '').toLowerCase().replace('_', '-')

  const exact = voices.filter((v) => norm(v) === want)
  const prefixed = voices.filter((v) => norm(v).startsWith(base + '-'))
  const candidates = exact.length ? exact : prefixed
  if (!candidates.length) return null

  // 本地语音不依赖网络，优先
  return candidates.find((v) => v.localService) || candidates[0]
}

/** 把浏览器的错误码归一化成我们自己的枚举 */
function normalizeReason(code: string | undefined): SpeakReason {
  switch (code) {
    case 'not-allowed':
      return 'not-allowed'
    case 'interrupted':
      return 'interrupted'
    case 'canceled':
    case 'cancelled':
      return 'canceled'
    case 'voice-unavailable':
    case 'language-unavailable':
      return 'no-voice'
    case 'synthesis-unavailable':
    case 'synthesis-failed':
    case 'audio-busy':
    case 'audio-hardware':
    default:
      return 'failed'
  }
}

function attemptOnce(
  content: string,
  opts: Required<Pick<SpeakOptions, 'lang' | 'rate' | 'pitch' | 'volume' | 'startTimeoutMs'>>,
  voice: SpeechSynthesisVoice | null,
  token: number
): Promise<SpeakResult> {
  const s = synth()
  if (!s) return Promise.resolve({ ok: false, reason: 'unsupported' })

  return new Promise<SpeakResult>((resolve) => {
    let settled = false
    let started = false
    let watchdog: ReturnType<typeof setTimeout> | null = null
    let hardStop: ReturnType<typeof setTimeout> | null = null

    const utterance = new window.SpeechSynthesisUtterance(content)
    utterance.lang = opts.lang
    utterance.rate = opts.rate
    utterance.pitch = opts.pitch
    utterance.volume = opts.volume
    if (voice) utterance.voice = voice

    const finish = (result: SpeakResult) => {
      if (settled) return
      settled = true
      if (watchdog) clearTimeout(watchdog)
      if (hardStop) clearTimeout(hardStop)
      utterance.onstart = null
      utterance.onend = null
      utterance.onerror = null
      resolve(result)
    }

    // 看门狗①：到点还没开始发声，就不再等了（否则 isPlaying 会永远卡住）
    watchdog = setTimeout(() => {
      if (started) return

      /*
       * ⚠️ 2026-10-23 修：这里原来写的是
       *      if (s.speaking || s.pending) { started = true; return }
       *    —— 只要队列里有东西就"认定已经开始发声"。这是**错的**。
       *
       *    实测本机 Chrome/Edge：`speak()` 之后 `speaking` 会一直是 true，
       *    但 `onstart` / `onend` 永远不触发、也完全没有声音。
       *    按老写法会一路走到 hardStop 并 report `ok:true` ——
       *    **用户什么都没听到，我们却报告播放成功**，比直接报错更糟。
       *
       *    正确的判据只有一个：`onstart` 有没有真的派发过。
       *    没派发就是没开始，如实报失败。
       */
      // 被更新的播放取代了，交给新的一轮去报告
      if (token !== speakToken) {
        finish({ ok: false, reason: 'interrupted' })
        return
      }
      finish({ ok: false, reason: 'failed' })
    }, opts.startTimeoutMs)

    // 看门狗②：`onstart` 已经确认声音真的出去了，但 `onend` 迟迟不来
    // （引擎卡死 / 事件丢失）。此时按「播放完成」收尾是合理的 ——
    // 关键是**必须**把 Promise 收掉，否则调用方的 isPlaying 永久为 true，按钮就废了。
    const maxMs = Math.min(60000, 3000 + content.length * 250)
    hardStop = setTimeout(() => finish({ ok: started, reason: started ? undefined : 'failed' }), maxMs)

    utterance.onstart = () => {
      started = true
    }

    utterance.onend = () => finish({ ok: true })

    utterance.onerror = (e: SpeechSynthesisErrorEvent) => {
      finish({ ok: false, reason: normalizeReason(e?.error), error: e })
    }

    /*
     * ⚠️ 这里是**同步**调用，调用栈必须仍然处于用户手势之中。
     *    千万不要在它前面插 await —— 见 `speak()` 顶部注释。
     */
    try {
      s.speak(utterance)
      // Chrome 有时队列会莫名停在 paused，resume 一下
      try { s.resume() } catch { /* 忽略 */ }
    } catch (e) {
      finish({ ok: false, reason: 'failed', error: e })
    }
  })
}

/**
 * 朗读一段文本。
 *
 * 成功 resolve `{ok:true}`；失败 resolve `{ok:false, reason}` ——
 * **不 reject**，调用方用 `if (!res.ok)` 判断即可，不必写 try/catch。
 *
 * ⚠️ 2026-10-23 重要修正：**`speak()` 必须在调用方的用户手势里同步发出。**
 *
 *    Chrome 的自动播放策略把 `speechSynthesis.speak()` 当作"发声"行为。
 *    如果它被推迟到某个 `await` 之后（哪怕只等 80ms），就已经脱离了
 *    用户手势的激活窗口，浏览器会直接以 `not-allowed` 拒绝 ——
 *    表现就是"点了按钮完全没声音，控制台也不报错"。
 *
 *    早期实现为了规避「cancel 后立刻 speak 被丢弃」，在 speak 前
 *    `await sleep(80)` + `await loadVoices()`（最多等 1.5s）。
 *    这**两件事都会破坏手势上下文**，等于用 A 问题换来了更致命的 B 问题。
 *
 *    现在的做法：
 *      · 语音列表用**同步缓存**（`getVoices()` 首帧常为空，但通常在
 *        页面加载后很快就会就绪，且 `loadVoices()` 已在别处预热）；
 *      · 不在 speak 前 await 任何东西，第一发**同步**打出去；
 *      · cancel 与 speak 之间不插 sleep —— 改由 attemptOnce 内部
 *        「第一发同步打、失败了再异步重试」来兼顾。
 */
export async function speak(text: string, options: SpeakOptions = {}): Promise<SpeakResult> {
  const content = String(text ?? '').trim()
  if (!content) return { ok: false, reason: 'empty' }

  const opts = {
    lang: options.lang ?? 'zh-CN',
    rate: options.rate ?? 0.9,
    pitch: options.pitch ?? 1,
    volume: options.volume ?? 1,
    startTimeoutMs: options.startTimeoutMs ?? 1200
  }
  const allowFallback = options.fallbackToServer !== false

  const token = ++speakToken

  /*
   * ⚠️ 浏览器 TTS 被判定为坏了之后（见 browserTtsBroken 注释），
   *    直接走服务端合成，不再让用户对着每个词干等 1.2 秒超时。
   */
  if (browserTtsBroken && allowFallback) {
    return speakViaServer(content, opts.lang, opts.rate, opts.volume, token)
  }

  if (!isSpeechSupported()) {
    if (allowFallback) {
      return speakViaServer(content, opts.lang, opts.rate, opts.volume, token)
    }
    return { ok: false, reason: 'unsupported' }
  }

  const s = synth()!

  /*
   * ⚠️ 同步取语音：这里**不能** await。
   *
   *    `getVoices()` 是同步 API，首帧可能返回空数组（语音包异步加载），
   *    空的时候交给引擎按 `lang` 自己挑即可 —— 不能为了"等语音包"而
   *    丢掉用户手势。
   *
   *    预热放在 `loadVoices()`，页面初始化时调用一次即可。
   */
  let voices = voicesCache
  if (!voices.length) {
    voices = (s.getVoices() || [])
    if (voices.length) voicesCache = voices
  }
  const voice = pickVoice(voices, opts.lang)
  const noVoiceHint = voices.length > 0 && !voice

  // —— 以下全部同步执行，保证仍在用户手势内 ——
  try { s.cancel() } catch { /* 忽略 */ }

  const first = await attemptOnce(content, opts, voice, token)
  if (first.ok) return first
  if (first.reason === 'interrupted') return first

  /*
   * ⚠️ 2026-10-23 修「点了半天没有任何提示」：
   *
   *    原来这里无条件重试一次，于是失败路径要等
   *      startTimeoutMs(1.5s) + 120ms + startTimeoutMs(1.5s) ≈ 3.1s
   *    才返回。而调用方还要再串行走几轮重复播放，用户实测**15.5 秒**
   *    才看到提示 —— 那时人早就以为"点了没反应"刷新页面了。
   *
   *    现在区分处理：
   *      · `failed`（引擎压根没开始发声）：重试基本没用，直接返回，
   *        让用户**立刻**看到原因；
   *      · 其它情况（如 not-allowed 之外的偶发）才重试一次。
   *
   *    宁可少重试一次，也不要让用户对着静音的按钮等三秒。
   */
  const worthRetry = first.reason !== 'failed' && first.reason !== 'no-voice'
  if (!worthRetry) {
    /*
     * `failed` = 引擎拿到了请求却不发声。这正是本机 Chromium 的症状
     * （见文件顶部注释）。标记下来，后续直接走服务端合成，不再逐个词超时。
     */
    if (first.reason === 'failed') {
      browserTtsBroken = true
      if (allowFallback) {
        const viaServer = await speakViaServer(content, opts.lang, opts.rate, opts.volume, token)
        if (viaServer.ok) return viaServer
        // 服务端也不行，把更有信息量的那个错误返回给调用方
        return viaServer.reason && viaServer.reason !== 'failed' ? viaServer : first
      }
    }
    if (noVoiceHint) return { ok: false, reason: 'no-voice', error: first.error }
    return first
  }

  await sleep(120)
  if (token !== speakToken) return { ok: false, reason: 'interrupted' }

  const second = await attemptOnce(content, opts, voice, token)
  if (second.ok) return second

  // 两次都没发出声音。如果本来就没匹配到对应语言的语音包，
  // 那么"缺语音包"比笼统的"播放失败"更能指导用户怎么办。
  if (noVoiceHint) return { ok: false, reason: 'no-voice', error: second.error }

  // 依旧是引擎不发声 → 标记 + 尝试服务端
  if (second.reason === 'failed') {
    browserTtsBroken = true
    if (allowFallback) {
      const viaServer = await speakViaServer(content, opts.lang, opts.rate, opts.volume, token)
      if (viaServer.ok) return viaServer
    }
  }

  return second
}

/** 停止当前朗读（并作废排队中的回调） */
export function stopSpeak(): void {
  speakToken++
  const s = synth()
  if (s) {
    try { s.cancel() } catch { /* 忽略 */ }
  }
  stopServerAudio()
}

/* ============================================================================
 * 服务端合成兜底
 * ============================================================================
 * 背景见 `app/api/v1/tts.py` 顶部注释：部分 Windows 环境下浏览器
 * `speechSynthesis` 会静默失效（有语音列表、speaking 变 true，但不出声）。
 * 这时改用后端 `/tts/synthize` 合成 mp3，再用 `Audio` 播放。
 *
 * 用 `Audio` 而不是 Web Audio：audio 元素自带播放控制与缓冲，
 * 且实测在本机 `Audio.play()` 正常。
 */

/** 当前正在播放的服务端音频 */
let serverAudio: HTMLAudioElement | null = null
/** 每次服务端播放自增，用于作废过期回调 */
let serverToken = 0

function stopServerAudio(): void {
  serverToken++
  if (serverAudio) {
    try {
      serverAudio.pause()
      serverAudio.src = ''
    } catch { /* 忽略 */ }
    serverAudio = null
  }
}

/** 服务端合成接口地址（带 /dev-api 前缀由环境变量决定） */
function ttsUrl(text: string, lang: string, rate: number): string {
  const base = (import.meta as any).env?.VITE_APP_BASE_API || ''
  const q = new URLSearchParams({
    text,
    lang,
    rate: String(Math.round((rate - 1) * 100))
  })
  return `${base}/tts/synthize?${q.toString()}`
}

/**
 * 用服务端合成的声音朗读。
 *
 * 音频带鉴权：后端接口要 token，而 `<audio src>` 无法带 Header，
 * 所以这里用 fetch 拿 blob 再喂给 Audio（顺带享受浏览器缓存）。
 */
async function speakViaServer(
  text: string,
  lang: string,
  rate: number,
  volume: number,
  token: number
): Promise<SpeakResult> {
  if (typeof window === 'undefined' || typeof window.Audio !== 'function') {
    return { ok: false, reason: 'unsupported' }
  }

  const url = ttsUrl(text, lang, rate)
  const cacheKey = url

  try {
    let objectUrl = serverAudioCache.get(cacheKey)

    if (!objectUrl) {
      const { getToken } = await import('@/utils/auth')
      const tk = getToken()
      const headers: Record<string, string> = {}
      if (tk) headers.Authorization = 'Bearer ' + tk

      const res = await fetch(url, { headers })
      const ct = res.headers.get('content-type') || ''

      if (!res.ok || ct.includes('application/json')) {
        // 后端返回的是 JSON 错误（edge-tts 未装 / 网络失败等）
        let msg = ''
        try {
          const j = await res.json()
          msg = j?.msg || ''
        } catch { /* 忽略 */ }
        return { ok: false, reason: 'failed', error: msg || `HTTP ${res.status}` }
      }

      const blob = await res.blob()
      if (!blob.size) return { ok: false, reason: 'failed', error: '音频为空' }

      objectUrl = URL.createObjectURL(blob)
      // 只在成功时缓存，且限制条目数，避免长词库无限增长
      if (serverAudioCache.size > 300) {
        const firstKey = serverAudioCache.keys().next().value
        if (firstKey) {
          const old = serverAudioCache.get(firstKey)
          if (old) URL.revokeObjectURL(old)
          serverAudioCache.delete(firstKey)
        }
      }
      serverAudioCache.set(cacheKey, objectUrl)
    }

    if (token !== speakToken) return { ok: false, reason: 'interrupted' }

    stopServerAudio()
    const myServerToken = ++serverToken

    return await new Promise<SpeakResult>((resolve) => {
      const audio = new window.Audio(objectUrl as string)
      audio.volume = Math.max(0, Math.min(1, volume))
      serverAudio = audio

      const cleanup = () => {
        if (serverAudio === audio) serverAudio = null
      }

      audio.onended = () => { cleanup(); resolve({ ok: true }) }
      audio.onerror = () => {
        cleanup()
        resolve({ ok: false, reason: 'failed', error: '音频解码失败' })
      }

      // 解码/缓冲卡住时的兜底，避免 Promise 永不 resolve
      const guard = setTimeout(() => {
        if (myServerToken === serverToken && audio.paused === false) {
          // 还在播（只是事件没来），视为正常收尾
          cleanup()
          resolve({ ok: true })
        }
      }, 20000)

      audio.play().then(() => {
        // 播放在正常进行；等 onended
      }).catch((e: any) => {
        clearTimeout(guard)
        cleanup()
        const name = e?.name || ''
        resolve({
          ok: false,
          reason: name === 'NotAllowedError' ? 'not-allowed' : 'failed',
          error: e?.message
        })
      })

      // 正常结束时清掉 guard
      const origEnd = audio.onended
      audio.onended = (ev) => {
        clearTimeout(guard)
        if (origEnd) (origEnd as any).call(audio, ev)
      }
      const origErr = audio.onerror
      audio.onerror = (ev) => {
        clearTimeout(guard)
        if (origErr) (origErr as any).call(audio, ev)
      }
    })
  } catch (e: any) {
    return { ok: false, reason: 'failed', error: e?.message || String(e) }
  }
}

/** 把失败原因转成给用户看的中文提示 */
export function speakReasonText(reason?: SpeakReason, lang?: string): string {
  switch (reason) {
    case 'unsupported':
      return '当前浏览器不支持语音朗读，换用 Chrome / Edge 试试'
    case 'empty':
      return '这条内容没有可朗读的文字'
    case 'no-voice': {
      // 区分中英文给出更具体的指引 —— 英文语音包缺失是最常见的情况
      const isZh = String(lang || '').toLowerCase().startsWith('zh')
      return isZh
        ? '系统里没有中文语音包，请在「设置 → 时间和语言 → 语音」里添加后重试'
        : '系统里没有英文语音包，请在「设置 → 时间和语言 → 语音 → 添加语音」里安装英文(美国)后重试'
    }
    case 'not-allowed':
      return '浏览器拦截了自动播放，请先点一下页面再播放'
    case 'interrupted':
    case 'canceled':
      return '播放已被打断'
    default:
      /*
       * 走到这里通常是「浏览器拿到了请求但语音引擎没真正发声」——
       * 实测在部分 Windows 环境下 Chromium 的 TTS 桥接会静默失效
       * （`getVoices()` 有语音、`speaking` 变 true，但 onstart 永不触发）。
       * 这种情况用户自己很难判断，所以提示里带上最可能的两条出路。
       */
      return '语音播放失败：浏览器没能调用系统语音。可尝试刷新页面，或改用 Edge/Chrome 最新版；若仍无声，请在系统设置里确认已安装对应语言的语音包'
  }
}
