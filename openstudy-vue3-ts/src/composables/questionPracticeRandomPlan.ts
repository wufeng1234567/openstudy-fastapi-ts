// composables/questionPracticeRandomPlan.ts
//
// 随机练习的**题单持久化**（从 `useQuestionPractice.ts` 抽出）。
//
// 模型：一次会话 = 一份固定题单，做完或主动「重新练习」才换
//     （完整口径见 composable 里 `processQuestions` 上方那段长注释）。
//
// 这里只放**存储与题单算法**；存储键（依赖 `userStore.id` / `props`）仍由 composable 算好
// 再显式传进来 —— 所以本模块**不持有任何状态**，也不碰 Vue。
//
// ⚠️ 存储格式是**裸数组** `[3044,3045,3046]`（见 `writeIdList`）：
//    读写必须同时改，改成对象会读不到 → 「随机只随机一次」立刻失效。
//    第一版这里写成 `plan.ids`（以为存的是 `{ids:[...]}` 对象），于是永远读不到，
//    探针实测「刷新 3 次题单变了 3 次」才抓到这个错。

export function readIdSet(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? new Set(arr.map(String)) : new Set()
  } catch {
    // 隐私模式 / 配额满 / 数据损坏 → 当成没有历史，不影响练习
    return new Set()
  }
}

export function writeIdList(key: string, ids: any[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(ids))
  } catch {
    // 存不下就退化成"每次重新随机"，仍然能练
  }
}

/**
 * 读取已持久化的随机题单
 *
 * 返回 `null` 表示"没有可用题单，需要重新生成"。校验条件：
 *   · 题单里的 id 必须**全部**能在当前题库数据里找到（否则题库改过了）
 *   · 题单长度必须与当前「每次练习数量」的预期一致（否则设置改过了）
 * 任一不满足就重建 —— 这是"题单失效"的唯一入口。
 *
 * ⚠️ 存储格式是**裸数组** `[3044,3045,3046]`（见 `writeIdList`）。
 *    第一版这里写成 `plan.ids`（以为存的是 `{ids:[...]}` 对象），
 *    于是永远读不到 → 每次加载都重建题单 → "随机只随机一次"完全没生效。
 *    探针实测：刷新 3 次题单变了 3 次，才抓到这个错。
 *    如果以后要加元数据（生成时间等）再改成对象，**读写必须同时改**。
 */
export function loadRandomPlan(data: any[], count: number | string, planKey: string): any[] | null {
  try {
    const raw = localStorage.getItem(planKey)
    if (!raw) return null
    const plan = JSON.parse(raw)
    const planIds: any[] = Array.isArray(plan) ? plan : (Array.isArray(plan?.ids) ? plan.ids : [])
    if (!planIds.length) return null

    // 题目增删 → 题单作废（避免用户点进去发现"少了一道题"）
    const byId = new Map<string, any>()
    data.forEach((q) => {
      const qid = q?.id ?? q?.questionId
      if (qid !== undefined && qid !== null) byId.set(String(qid), q)
    })
    const restored: any[] = []
    for (const id of planIds) {
      const q = byId.get(String(id))
      if (!q) return null   // 有题被删了 → 整体重建，不做部分拼接
      restored.push(q)
    }

    /*
     * 数量变了就重建。
     *
     * ⚠️ 这里比较的是**实际会用到的那一段**：`count='all'` 时要求题单覆盖全库，
     *    否则要求题单长度 === count。用户把"每次 10 题"改成"每次 20 题"时，
     *    旧题单只有 10 条 → 必须重建，否则页面上只有 10 道题却写着 20。
     */
    const want = count === 'all' ? data.length : Math.min(Number(count) || data.length, data.length)
    if (restored.length !== want) return null

    return restored
  } catch {
    return null
  }
}

/** 生成并持久化一份新的随机题单 */
export function buildRandomPlan(data: any[], count: number | string, planKey: string, lastRoundKey: string): any[] {
  const lastRound = readIdSet(lastRoundKey)

  // 分成「上一轮没练过」和「练过」两组，新题优先 —— 这是"更合理的随机"
  const fresh: any[] = []
  const done: any[] = []
  data.forEach((q) => {
    const qid = q?.id ?? q?.questionId
    if (qid !== undefined && qid !== null && lastRound.has(String(qid))) {
      done.push(q)
    } else {
      fresh.push(q)
    }
  })

  const shuffleInPlace = (arr: any[]) => {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]]
    }
    return arr
  }

  /*
   * 先打乱整体，再把「新题」稳定地提到前面。
   *
   * 为什么不是直接 [打乱(fresh), 打乱(done)]：
   *   那样会让"新题"永远占据最前面 N 个位置，一旦 count < fresh 数量，
   *   排在后面的 fresh 题在**连续几轮**里都轮不到 —— 覆盖面反而变窄。
   *   这里改为：整体随机后，把 fresh 集合内的题按随机顺序前置，
   *   done 的题填在后面。因为在 buildRandomPlan 里 fresh/done 是按
   *   "上一轮"划分的，每轮都会重算，所以不会有永久饿死的题。
   */
  const ordered = [...shuffleInPlace(fresh), ...shuffleInPlace(done)]

  const want = count === 'all' ? ordered.length : Math.min(Number(count) || ordered.length, ordered.length)
  const picked = ordered.slice(0, want)

  // 落盘：题单本身 + "这一轮将要练的题"（供下一轮生成时避开）
  writeIdList(planKey, picked.map((q) => q?.id ?? q?.questionId).filter((x) => x !== undefined && x !== null))
  writeIdList(lastRoundKey, picked.map((q) => q?.id ?? q?.questionId).filter((x) => x !== undefined && x !== null))

  /*
   * 返回的是**完整顺序**（picked 在前，其余在后）。
   *
   * 为什么末尾还要带没被抽中的题：
   *   `allQuestionsData` 是全库，`questions` 是它的前 count 条切片。
   *   如果这里只返回 picked，用户把「每次练习数量」调大时（比如 10 → 全部）
   *   就会没有题可取 —— 明明题库里有 100 道，页面却说总共 10 道。
   *   把剩余题接在后面，既保证题单稳定，也不丢题。
   */
  const pickedIds = new Set(picked.map((q) => String(q?.id ?? q?.questionId)))
  const rest = ordered.filter((q) => !pickedIds.has(String(q?.id ?? q?.questionId)))
  return [...picked, ...rest]
}

/**
 * 清掉随机题单（"重新练习" / 练完一轮时调用）
 *
 * ⚠️ 只清**题单**，不清 `lastRoundKey`（上一轮做过哪些题）——
 *    那份记录正是下一轮"新题优先"的依据，清掉就退化成纯随机了。
 */
export function clearRandomPlan(planKey: string): void {
  try {
    localStorage.removeItem(planKey)
  } catch {
    // 忽略：清不掉最多是沿用了旧题单，不影响功能
  }
}
