/**
 * 模拟考试的「进行中会话」（Mock Exam Session）
 * ============================================================================
 * ## 解决什么问题
 *
 * 用户 2026-10-22 报的 bug：模拟考试进行中刷新页面，下次进来**卷子没了**，
 * 直接回到「考试配置页」。
 *
 * 根因两处，缺一不可：
 *   ① `mockPhase` 是组件内 ref，刷新即回到初始值 `'setup'`；
 *      更糟的是进入 mock 模块的 watch 里**无条件**把它重置成 `'setup'`。
 *   ② 试卷本身（题目、答案、配置）从来没有持久化过 ——
 *      只有倒计时用了 localStorage（`openstudy_exam_end_time`）。
 *
 * 所以刷新后是"计时器还记得，卷子已经没了"的分裂状态。
 *
 * ## 设计要点
 *
 * 1. **按「用户 + 题库」分区**，与 `practiceDraft` 一致：
 *       os_mock_session_{userId}_{bankId}
 *     A 题库考到一半去 B 题库，两份会话互不影响。
 *
 * 2. **存"题目 id 序列"而不是整份题目对象**：
 *    题目正文以题库为准（用户可能刚在后台改过题干），
 *    会话里只记"这场考的是哪几道、什么顺序、各自什么分值"。
 *    恢复时按 id 回题库取最新题目，用 `_mockScore` / `_mockType` 覆盖分值类型。
 *    这样既省配额，也不会让用户看到过期的题干。
 *
 * 3. **必须带 `endAt`（绝对时间戳）**：
 *    恢复时要判断"是否还在考试时间内"。存 `remaining`（剩余秒数）是错的 ——
 *    用户在别的页面待了 20 分钟再刷新，剩余时间要按真实流逝算，不能冻结。
 *
 * 4. **过期会话一律视为无效并清掉**，绝不恢复出一张已经超时的卷子：
 *    那会让用户以为"还有时间"，实际交卷时被判 0 分。
 *
 * 5. **交卷 / 主动离开考试 → 立刻清除会话**：
 *    会话只描述"正在进行中"的考试，已完成的不该留在这儿（历史记录另有存储）。
 */

/** 结构版本：改字段语义时 +1，旧数据自动作废 */
const VERSION = 1

/** localStorage 键前缀（后面拼 userId_bankId） */
const KEY_PREFIX = 'os_mock_session'

/**
 * 一份进行中的考试会话
 *
 * ⚠️ 这里**不存题目正文**，只存 id 与分值（见文件头「设计要点 2」）。
 */
export interface MockExamSession {
  v: number
  /** 写入时间（毫秒），用于排障与"多久没动过"的判断 */
  savedAt: number
  bankId: number | string
  /** 考试配置快照（判分要用同一个 passScore / multipleMode） */
  config: any
  /** 卷面构成：按考试顺序的题目 id */
  questionIds: Array<number | string>
  /** 每题满分（与 questionIds 同序；组合题按整题算） */
  scores: number[]
  /** 每题在考试里的题型（前端归一值，与 questionIds 同序） */
  types: string[]
  /** 作答：key = 题目 id，value = 该题答案（下标 / 下标数组 / 字符串 / 组合题对象） */
  answers: Record<string, any>
  /** 组合题子题填空答案：{ qid: { subIndex: value } } */
  subFillBlank: Record<string, Record<string, any>>
  /** 组合题子题简答答案 */
  subEssay: Record<string, Record<string, any>>
  /** 当前题目 id（恢复时定位到"我刚才在做的那道"） */
  currentQuestionId?: number | string | null
  /** 考试开始时间（算用时用） */
  startedAt: number
  /**
   * 考试**结束**的绝对时间戳（毫秒）
   *
   * 与 `startedAt + timeLimit*60000` 等价，但单独存下来更稳：
   * 用户中途改配置不影响本场（配置已冻结在 `config` 里）。
   */
  endAt: number
}

/** 生成分区键 */
function sessionKey(userId: number | string | null | undefined, bankId: number | string) {
  return `${KEY_PREFIX}_${userId || 0}_${bankId}`
}

/**
 * 读取会话
 *
 * 返回 `null` 的四种情况（都当"没有可恢复的考试"，绝不抛错打断页面初始化）：
 *   · 不存在；
 *   · 版本不符（结构升级过）；
 *   · 题库不匹配（防串库）；
 *   · **已过期**（`now >= endAt`）—— 顺手清掉，避免它一直躺在 localStorage 里。
 */
export function loadMockSession(
  userId: number | string | null | undefined,
  bankId: number | string,
  now = Date.now()
): MockExamSession | null {
  try {
    const key = sessionKey(userId, bankId)
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const data = JSON.parse(raw) as MockExamSession
    if (!data || data.v !== VERSION) {
      localStorage.removeItem(key)
      return null
    }
    if (String(data.bankId) !== String(bankId)) return null
    if (!Array.isArray(data.questionIds) || !data.questionIds.length) {
      localStorage.removeItem(key)
      return null
    }
    // 过期会话：不能恢复，否则用户会拿着"已超时"的卷子继续答题
    if (!(Number(data.endAt) > now)) {
      localStorage.removeItem(key)
      return null
    }
    return data
  } catch {
    return null
  }
}

/** 写入（覆盖）会话 */
export function saveMockSession(
  userId: number | string | null | undefined,
  session: Omit<MockExamSession, 'v' | 'savedAt'>
): boolean {
  try {
    const full: MockExamSession = { ...session, v: VERSION, savedAt: Date.now() }
    localStorage.setItem(sessionKey(userId, session.bankId), JSON.stringify(full))
    return true
  } catch {
    // 配额满 / 隐私模式：静默失败。考试仍可继续，只是刷新后无法恢复
    return false
  }
}

/** 清除会话（交卷 / 主动离开 / 过期） */
export function clearMockSession(
  userId: number | string | null | undefined,
  bankId: number | string
): void {
  try {
    localStorage.removeItem(sessionKey(userId, bankId))
  } catch {
    /* 忽略 */
  }
}
