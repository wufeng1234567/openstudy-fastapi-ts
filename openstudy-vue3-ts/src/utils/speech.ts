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
  /** 超过这个时间还没真正开始发声，就判定失败。默认 1500ms */
  startTimeoutMs?: number
}

/** 每次播放自增，用于作废"上一轮还没结束的回调" */
let speakToken = 0

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
  voice: SpeechSynthesisVoice | null
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
      // 队列里确实有东西在播，只是 onstart 没派发 —— 认作已开始
      if (s.speaking || s.pending) {
        started = true
        return
      }
      finish({ ok: false, reason: 'failed' })
    }, opts.startTimeoutMs)

    // 看门狗②：已开始发声、但 onend 永远不来（引擎卡死 / 事件丢失）。
    // 这种情况按「播放完成」处理 —— onstart 已经确认声音确实出去了，
    // 报失败反而会让用户以为没播。关键是**必须**把 Promise 收掉，
    // 否则调用方的 isPlaying 永久为 true，按钮就废了。
    const maxMs = Math.min(60000, 3000 + content.length * 250)
    hardStop = setTimeout(() => finish({ ok: true }), maxMs)

    utterance.onstart = () => {
      started = true
    }

    utterance.onend = () => finish({ ok: true })

    utterance.onerror = (e: SpeechSynthesisErrorEvent) => {
      finish({ ok: false, reason: normalizeReason(e?.error), error: e })
    }

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
 */
export async function speak(text: string, options: SpeakOptions = {}): Promise<SpeakResult> {
  if (!isSpeechSupported()) return { ok: false, reason: 'unsupported' }

  const content = String(text ?? '').trim()
  if (!content) return { ok: false, reason: 'empty' }

  const s = synth()!
  const opts = {
    lang: options.lang ?? 'zh-CN',
    rate: options.rate ?? 0.9,
    pitch: options.pitch ?? 1,
    volume: options.volume ?? 1,
    startTimeoutMs: options.startTimeoutMs ?? 1500
  }
  const settleMs = options.settleMs ?? 80

  const token = ++speakToken

  // 先打断上一次，并留出间隔（Chrome：cancel 后立即 speak 可能被丢弃）
  try { s.cancel() } catch { /* 忽略 */ }
  await sleep(settleMs)
  if (token !== speakToken) return { ok: false, reason: 'interrupted' }

  const voices = await loadVoices()
  if (token !== speakToken) return { ok: false, reason: 'interrupted' }

  const voice = pickVoice(voices, opts.lang)

  /*
   * ⚠️ 这里**不**因为「找不到对应语言的语音」就直接返回失败。
   *
   *    实际情况比"有/没有语音包"复杂得多：
   *    · 有的系统 getVoices() 只暴露部分语音，但引擎仍能按 `lang` 自行挑选；
   *    · 有的环境（如部分 Linux / 旧版 Android）语音列表为空但照样能发声；
   *    · 强行判定 no-voice 会把**本来能响**的机器判成错误。
   *
   *    所以策略是：能挑到就显式指定（更可控），挑不到就交给引擎按 `lang` 决定，
   *    只有**真的没能发出声音**（attemptOnce 失败）时，才归因为缺语音包。
   */
  const noVoiceHint = voices.length > 0 && !voice

  const first = await attemptOnce(content, opts, voice)
  if (first.ok) return first
  // 被新播放打断 / 主动停止，不需要重试
  if (first.reason === 'interrupted' || first.reason === 'canceled') return first
  if (token !== speakToken) return { ok: false, reason: 'interrupted' }

  // 引擎偶尔吞掉第一发，再给一次机会
  await sleep(80)
  if (token !== speakToken) return { ok: false, reason: 'interrupted' }

  const second = await attemptOnce(content, opts, voice)
  if (second.ok) return second

  // 两次都没发出声音。如果本来就没匹配到对应语言的语音包，
  // 那么"缺语音包"比笼统的"播放失败"更能指导用户怎么办。
  if (noVoiceHint) return { ok: false, reason: 'no-voice', error: second.error }

  return second
}

/** 停止当前朗读（并作废排队中的回调） */
export function stopSpeak(): void {
  speakToken++
  const s = synth()
  if (!s) return
  try { s.cancel() } catch { /* 忽略 */ }
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
      return '播放失败，请检查系统音量和语音引擎'
  }
}
