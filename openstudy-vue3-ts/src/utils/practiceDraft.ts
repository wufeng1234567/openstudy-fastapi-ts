/**
 * 练习暂存（Practice Draft）
 * ============================================================================
 * ## 它和 keep-alive 页面缓存不是一回事
 *
 * | | keep-alive（`frontPageCache` + `<KeepAlive>`） | 本模块（暂存） |
 * | --- | --- | --- |
 * | 活多久 | **进程内**，刷新即失效、关标签即失效 | **localStorage**，刷新/重开浏览器仍在 |
 * | 存什么 | 组件实例与路由滚动状态 | **答题数据**（每题作答、对错、当前题号、分波位置） |
 * | 谁在用 | 路由层，用于"切到别的模块再切回来" | 练习页，用于"离开题库后再进来继续" |
 * | 失败影响 | 回来时重新加载、丢滚动位置 | 恢复不到上次进度 |
 *
 * 两者互补：keep-alive 只解决"同一会话内来回切"，本模块解决"关掉再回来"。
 *
 * ## 设计要点
 *
 * 1. **静默暂存**：用户每次作答（选选项 / 改填空 / 改简答 / 换题 / 换波）后
 *    自动写一次，不需要用户点任何按钮。写操作做了节流（默认 600ms），
 *    避免连续输入时每敲一个字就 JSON.stringify 整个题库。
 *
 * 2. **手动暂存**：答题卡面板上的「暂存」按钮走同一个 `flush()`，
 *    并回调状态（保存中 / 已暂存 / 暂存失败）给 UI 显示。
 *
 * 3. **按「用户 + 题库 + 模块」分区**：同一个题库的不同练习模式（顺序/随机/
 *    模拟考试）进度互不覆盖；不同用户在同一浏览器也不串。
 *
 * 4. **不碰后端数据**：答题上报（`/questionPractice/report` → `user_question_error`）
 *    是另一条链路，本模块**不写、不清、不覆盖**它。
 *    即使在暂存里判错过，也不会去改后端的错题记录。
 *
 * 5. **版本号**：结构变更时递增 `VERSION`，旧数据自动作废（宁可重做也不要
 *    用错结构复原出"看起来答过、实际是错的"状态）。
 */

/** 结构版本：改字段语义时 +1，旧数据会被忽略 */
const VERSION = 1

/** localStorage 键前缀（后面拼 userId_bankId_moduleType） */
const KEY_PREFIX = 'os_practice_draft'

/** 自动暂存的节流间隔（ms） */
const AUTO_SAVE_DELAY = 600

/** 一份暂存里到底存了什么（字段是"恢复所需的最小集"） */
export interface PracticeDraft {
  v: number
  /** 写入时间（毫秒时间戳），用于判断新旧 */
  savedAt: number
  /** 题库 id */
  bankId: number | string
  /** 练习模块（sequential / random / custom / mock），不同模块互不覆盖 */
  moduleType: string
  /** 题目 id 顺序快照（随机/自定义模式下位置会变，恢复时按 id 对齐，不按数组下标） */
  questionIds: Array<number | string>
  /** 每题作答：key = questionId，value = 该题的答案（字符串/数组/对象） */
  answers: Record<string, any>
  /** 每题是否已判分（刷题模式下答完即判；考试模式下提交后才判） */
  judged: Record<string, boolean>
  /** 每题是否正确（仅 judged 为 true 时有效） */
  correct: Record<string, boolean>
  /** 组合题子题：填空题答案 { qid: { subIndex: value } } */
  subFillBlank: Record<string, Record<string, any>>
  /** 组合题子题：简答题答案 { qid: { subIndex: value } } */
  subEssay: Record<string, Record<string, any>>
  /** 当前所在题目的 id（不是下标，避免题库重新排序后错位） */
  currentQuestionId?: number | string | null
  /** 当前波次序号（0 起）：分波刷题要能回到"我做到第几波" */
  batchIndex: number
  /** 每波题数（恢复时分波要一致，否则题号对不上） */
  batchSize: number
  /** 这一波里已经提交过吗（考试模式用：提交后不再重复判） */
  submittedBatches: number[]
  /** 会话累计统计（对/错/用时），可选 */
  stats?: { correct: number; wrong: number; elapsedMs: number }
}

/** 生成分区键（同一浏览器多用户、同用户多题库多模块都互不影响） */
function draftKey(userId: number | string | null | undefined, bankId: number | string, moduleType: string) {
  return `${KEY_PREFIX}_${userId || 0}_${bankId}_${moduleType}`
}

/**
 * 读取暂存
 *
 * 返回 `null` 表示"没有可用的暂存"（不存在 / 版本不对 / 结构损坏 / 题库不匹配）。
 * **任何异常都返回 null**，绝不抛错打断练习页的初始化。
 */
export function loadDraft(
  userId: number | string | null | undefined,
  bankId: number | string,
  moduleType: string
): PracticeDraft | null {
  try {
    const raw = localStorage.getItem(draftKey(userId, bankId, moduleType))
    if (!raw) return null
    const data = JSON.parse(raw) as PracticeDraft
    // 版本 / 归属校验：对不上就当没存过
    if (!data || data.v !== VERSION) return null
    if (String(data.bankId) !== String(bankId)) return null
    if (data.moduleType !== moduleType) return null
    if (!data.answers || typeof data.answers !== 'object') return null
    return data
  } catch {
    return null
  }
}

/** 覆盖写入（内部用；外部请走 `createDraftSaver` 以享受节流与状态回调） */
export function saveDraft(
  userId: number | string | null | undefined,
  draft: PracticeDraft
): boolean {
  try {
    localStorage.setItem(
      draftKey(userId, draft.bankId, draft.moduleType),
      JSON.stringify(draft)
    )
    return true
  } catch {
    // 配额满 / 隐私模式：返回 false，由调用方提示"暂存失败"
    return false
  }
}

/** 删除某个题库某模块的暂存（例如用户主动"重新练习"） */
export function clearDraft(
  userId: number | string | null | undefined,
  bankId: number | string,
  moduleType: string
): void {
  try {
    localStorage.removeItem(draftKey(userId, bankId, moduleType))
  } catch {
    /* 忽略 */
  }
}

/**
 * 列出该用户所有暂存（答题卡/题库列表可以据此显示"有未完成进度"）
 *
 * 只做只读扫描，不解析具体内容以外的副作用。
 */
export function listDrafts(userId: number | string | null | undefined): PracticeDraft[] {
  const out: PracticeDraft[] = []
  try {
    const prefix = `${KEY_PREFIX}_${userId || 0}_`
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (!k || !k.startsWith(prefix)) continue
      const raw = localStorage.getItem(k)
      if (!raw) continue
      try {
        const d = JSON.parse(raw) as PracticeDraft
        if (d && d.v === VERSION) out.push(d)
      } catch {
        /* 单条损坏不影响其他 */
      }
    }
  } catch {
    /* 忽略 */
  }
  return out
}

/** 暂存状态（给 UI 显示"保存中 / 已暂存 / 暂存失败"） */
export type DraftSaveState = 'idle' | 'saving' | 'saved' | 'failed'

export interface DraftSaverOptions {
  /** 取当前用户 id 的函数（登录态可能在初始化后才就绪） */
  getUserId: () => number | string | null | undefined
  /** 取题库 id */
  getBankId: () => number | string
  /** 取练习模块名 */
  getModuleType: () => string
  /** 组装当前快照（由练习页提供，因为它最清楚状态在哪） */
  buildSnapshot: () => Omit<PracticeDraft, 'v' | 'savedAt'>
  /** 状态变化回调（用于按钮文案与轻提示） */
  onStateChange?: (state: DraftSaveState, at?: number) => void
  /** 节流间隔，默认 AUTO_SAVE_DELAY */
  delay?: number
}

export interface DraftSaver {
  /** 安排一次自动暂存（节流；连续调用只会真正写最后一次） */
  schedule: () => void
  /** 立即写入（手动「暂存」按钮走这个），返回是否成功 */
  flush: () => boolean
  /** 取消尚未执行的自动暂存（组件卸载时调用） */
  cancel: () => void
  /** 清除本分区的暂存（"重新练习"用） */
  clear: () => void
}

/**
 * 创建暂存器
 *
 * 为什么做成工厂而不是模块级单例：
 *   练习页可能同时存在多个实例（悬浮练习窗口 + 全屏页），
 *   各自绑定自己的题库/模块，共享一个单例会互相覆盖。
 */
export function createDraftSaver(opts: DraftSaverOptions): DraftSaver {
  const delay = opts.delay ?? AUTO_SAVE_DELAY
  let timer: ReturnType<typeof setTimeout> | null = null
  let lastState: DraftSaveState = 'idle'

  const emit = (state: DraftSaveState, at?: number) => {
    lastState = state
    opts.onStateChange?.(state, at)
  }

  const doSave = (): boolean => {
    const userId = opts.getUserId()
    const bankId = opts.getBankId()
    // 题库还没确定（新建练习页早期）→ 不写，避免污染 "bankId undefined" 的分区
    if (bankId === undefined || bankId === null || bankId === '') return false

    emit('saving')
    const snap = opts.buildSnapshot()
    const draft: PracticeDraft = {
      ...snap,
      v: VERSION,
      savedAt: Date.now(),
      bankId: snap.bankId ?? bankId,
      moduleType: snap.moduleType || opts.getModuleType()
    }
    const ok = saveDraft(userId, draft)
    emit(ok ? 'saved' : 'failed', draft.savedAt)
    return ok
  }

  return {
    schedule() {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        timer = null
        doSave()
      }, delay)
    },
    flush() {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      return doSave()
    },
    cancel() {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
    },
    clear() {
      if (timer) {
        clearTimeout(timer)
        timer = null
      }
      clearDraft(opts.getUserId(), opts.getBankId(), opts.getModuleType())
      emit('idle')
    }
  }

  // 说明：lastState 目前只用于内部去重扩展，保留引用避免 lint 报未使用
  void lastState
}
