import { ref, computed, nextTick } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import { listQuestionMainAll, getQuestionMain, recordStudyTime, reportPractice } from '@/api/questionMain/questionMain'
import { parseOptions } from '@/utils/questionUtils'
// 修改导入，添加新的API方法
import { listQuestionErrorAll, batchCheckError } from '@/api/questionError/questionError'
import { addFavoriteQuestion, deleteFavoriteQuestionByUserAndQuestion, batchCheckFavorite } from '@/api/favoriteQuestion/favoriteQuestion'
import { addQuestionMarked, deleteMarkedByUserAndQuestion, batchCheckMarked } from '@/api/questionMarked/questionMarked'
import useUserStore from '@/store/modules/user'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import type { TransformedQuestion, QuestionType } from '@/types'

// 调试日志工具
import {
  debugFetchStart,
  debugFetchComplete,
  debugProcessStart,
  debugCacheCheck,
  debugShuffle,
  debugCacheWrite,
  debugSetAllQuestionsData,
  debugSetQuestions,
  debugProcessComplete,
  debugResetAndFetch,
  debugFetchQuestions,
  debugStateSnapshot,
  debugCacheStatus
} from '@/utils/practiceDebug'

interface UseQuestionPracticeOptions {
  isFavoriteMode?: boolean
  singleQuestionId?: number | string | null
  onlyWrong?: boolean
  questionCount?: number | string | null
}

interface UseQuestionPracticeProps {
  bankId: number | string
  moduleType: string
}

export function useQuestionPractice(
  props: UseQuestionPracticeProps,
  { proxy }: { proxy: any },
  options: UseQuestionPracticeOptions = {}
) {
  const {
    isFavoriteMode = false,
    singleQuestionId = null
  } = options

  // 需要支持响应式更新
  const onlyWrong = ref<boolean>(options.onlyWrong ?? false)
  const questionCount = ref<number | string | null>(options.questionCount ?? null)
  const questionOffset = ref<number>(0)
  function updateOnlyWrong(val: boolean): void { onlyWrong.value = val }
  function updateQuestionCount(val: number | string): void { questionCount.value = val }
  function updateQuestionOffset(val: number): void { questionOffset.value = val }

  // 响应式数据
  const questions = ref<TransformedQuestion[]>([])
  // allQuestionsData 保存后端原始题目数据（未转换），故保留 any[]
  const allQuestionsData = ref<any[]>([])
  const currentQuestionIndex = ref<number>(0)
  // selectedAnswer 实际可能为 string | string[] | number | number[] | null，统一用 any 占位
  const selectedAnswer = ref<any>(null)
  const answers = ref<any[]>([])
  const loading = ref<boolean>(true)
  const submissionLock = ref<boolean>(false)
  /**
   * 「只刷错题」模式下、当前题库没有可练错题时的说明文案
   *
   * ⚠️ 为什么要单独一个状态（而不是只弹一次 `msgInfo`）：
   *   `ElMessage` 3 秒后自己消失，用户回头看就是一片空白页，
   *   分不清「加载失败」还是「本来就没题」。把它留在页面状态里，
   *   模板就能一直显示一句可执行的话（见 `PracticeComponent` 的空态）。
   *   空串 = 不是这种情况。
   */
  const noWrongQuestionsReason = ref<string>('')

  /**
   * 「没有题可练」的**类型**（2026-10-21）
   *
   * 空态区域是共用的一块，但两种情况该给**不同的动作**：
   *   · `'noWrong'`  —— 题库里没有你的错题 → 给「关闭只刷错题」「返回题库」
   *   · `'finished'` —— 本轮已经刷完 → 给「重新练习」「返回题库」
   * 放在同一个状态里（而不是两个布尔）是因为它们互斥，
   * 两个独立布尔迟早会同时为真，UI 就会两段文案叠在一起。
   */
  const noQuestionsKind = ref<'noWrong' | 'finished'>('noWrong')

  // 乱序结果缓存：key 为 `${bankId}_${moduleType}`，value 为打乱后的数据
  const shuffledCache = new Map<string, any[]>()
  // 答题状态缓存：key 为 `${bankId}_${moduleType}`，value 为答题状态
  const answerStateCache = new Map<string, any>()
  // 标志位：是否正在重置中（防止二次触发）
  const isResetting = ref<boolean>(false)

  // 获取用户store
  const userStore = useUserStore()
  // 获取刷题设置store
  const store = usePracticeSettingsStore()

  const subFillBlankAnswers = ref<Record<string | number, any>>({})
  const subEssayAnswers = ref<Record<string | number, any>>({})

  // 收藏状态
  const favoritedQuestions = ref<Set<number>>(new Set())
  // 斩题状态
  const markedQuestions = ref<Set<number>>(new Set())
  // 错题状态
  const errorQuestions = ref<Set<number>>(new Set())

  // ✅ 答题上报：答对 / 答错都要上报（学习统计的唯一数据源）
  // 说明：原先只在答错时上报，导致后端 user_question_favorite.correct_times / error_times
  // 从未被写入，「正确率」「练习次数」恒为 0；后端也没有任何"答对了"的行为记录。
  async function reportQuestionPractice(
    question: TransformedQuestion,
    userAnswer: any,
    isCorrect: boolean
  ): Promise<void> {
    try {
      await reportPractice({
        questionId: question.id,
        bankId: question.bankId || props.bankId,
        isCorrect,
        answer: stringifyAnswerForLog(userAnswer),
        // 错因备注 / 标签只在答错时有意义
        notes: isCorrect ? null : generateErrorNote(question, userAnswer),
        tags: isCorrect ? null : generateErrorTags(question.type, userAnswer),
        difficultyRating: question.difficulty || 3,
      })

      // 答错才把题目标记进"当前错题"集合；答对不改动（答对一次不等于已掌握）
      if (!isCorrect) {
        errorQuestions.value.add(Number(question.id))
      }
    } catch (error) {
      // 静默失败，不影响答题流程
    }
  }

  // 把各种形态的答案压成字符串写入流水（组合题传进来的是对象）
  function stringifyAnswerForLog(userAnswer: any): string {
    if (userAnswer === null || userAnswer === undefined) return ''
    if (Array.isArray(userAnswer)) return userAnswer.join(',')
    if (typeof userAnswer === 'object') {
      try {
        return JSON.stringify(userAnswer)
      } catch {
        return ''
      }
    }
    return String(userAnswer)
  }
  // ✅ 新增：生成错因备注
  function generateErrorNote(question: TransformedQuestion, userAnswer: any): string {
    const questionType = question.type
    const noteParts: string[] = []

    if (questionType === 'fillblank' || questionType === 'essay') {
      noteParts.push(`错误答案: "${userAnswer || '未填写'}"`)
      noteParts.push(`正确答案: "${question.correctAnswer}"`)
    } else if (questionType === 'single' || questionType === 'truefalse') {
      const userChoice = question.options && question.options[userAnswer] ? question.options[userAnswer] : '未选择'
      const correctChoice = question.options && question.options[question.correctAnswer] ? question.options[question.correctAnswer] : ''
      noteParts.push(`错误选项: ${userChoice}`)
      noteParts.push(`正确选项: ${correctChoice}`)
    } else if (questionType === 'multiple') {
      const userChoices = Array.isArray(userAnswer) && question.options
        ? userAnswer.map((idx: number) => question.options[idx] || `选项${idx}`).join(', ')
        : '未选择'
      const correctChoices = Array.isArray(question.correctAnswer) && question.options
        ? question.correctAnswer.map((idx: number) => question.options[idx] || `选项${idx}`).join(', ')
        : ''
      noteParts.push(`错误选项: ${userChoices}`)
      noteParts.push(`正确选项: ${correctChoices}`)
    }

    return noteParts.join(' | ')
  }

  // ✅ 新增：生成错题标签
  function generateErrorTags(questionType: string, userAnswer: any): string {
    const tags = ['自动记录']

    if (!userAnswer || (Array.isArray(userAnswer) && userAnswer.length === 0)) {
      tags.push('未作答')
    } else if (questionType === 'fillblank' || questionType === 'essay') {
      tags.push('主观题错误')
    } else {
      tags.push('选择题错误')
    }

    // 根据题目类型添加标签
    switch (questionType) {
      case 'single':
        tags.push('单选题')
        break
      case 'multiple':
        tags.push('多选题')
        break
      case 'truefalse':
        tags.push('判断题')
        break
      case 'fillblank':
        tags.push('填空题')
        break
      case 'essay':
        tags.push('问答题')
        break
    }

    return tags.join(',')
  }


  // 新增：处理单个题目（收藏页面用）
  function fetchSingleQuestion(questionId: number | string): void {
    loading.value = true

    getQuestionMain(questionId)
      .then((response: any) => {
        if (response.code === 200 && response.data) {
          // 处理单个题目
          const question = response.data
          processQuestions([question])
        } else {
          proxy.$modal.msgError('获取题目失败')
          loading.value = false
        }
      })
      .catch((err: any) => {
        proxy.$modal.msgError('加载题目失败')
        loading.value = false
      })
  }

  /**
   * 随机练习的「固定题单」—— 一次随机，之后一直用它
   * ==========================================================================
   * 用户口径（2026-10-20，两次反馈收敛到同一件事）：
   *   ① 「刷新页面一直都是这题 只是他的序号变了 可能是第一题 可能是第二题
   *      每次刷新题号不一样 但是题目一样」
   *   ② 「我的想法是 随机只随机一次 在用户没有提交结果刷完这个题库时
   *      永远也都是保留暂存结果」
   *
   * ★ 为什么采纳②而不是"每次刷新重新抽"★
   *   随机练习的语义是「我开始了一次练习」。这次练习应该有**固定的题单**：
   *   刷新、关掉再开、切到别的模块再回来，看到的都还是这一份，进度也还在。
   *   否则"随机"就变成了"每次刷新换一批题 + 暂存按 id 硬拽回某题"，
   *   两个机制互相打架 —— 上一版的"按快照重排"只是在事后补救，治标。
   *
   *   真实刷题产品（Anki / Duolingo / 各类题库 App）都是这个模型：
   *   一次会话 = 一份固定题单，做完或主动"重新练习"才换。
   *
   * ★ 题单什么时候失效（重新随机）★
   *   · 用户点「重新练习」（`resetPractice`）
   *   · 练完/提交结算后（`handleFinishExam` → 下一轮）
   *   · 题库题目有增删（题单里引用的 id 对不上时自动重建）
   *   · 每次练习数量 / 只刷错题等设置变了（题单的范围变了）
   *   除此之外**一律沿用**。
   *
   * ★ "更合理的随机"体现在哪★
   *   题单**第一次生成时**才做优化：
   *     优先排入上一轮没练过的题（跨轮覆盖更广），再补上一轮练过的；
   *   生成后写入 localStorage，之后完全稳定。
   *   这样既满足"固定的随机题单"，又让连续几轮练习的覆盖面自然扩大。
   */

  const RANDOM_PLAN_PREFIX = 'os_random_plan_'

  /** 题单存储键：同一用户 + 同一题库 + 同一模式，互不影响 */
  function randomPlanKey(): string {
    return `${RANDOM_PLAN_PREFIX}${userStore.id || 0}_${props.bankId}_${props.moduleType}`
  }

  /** 上一轮练过的题（用于新一轮生成时"新题优先"） */
  function lastRoundKey(): string {
    return `os_recent_practice_${userStore.id || 0}_${props.bankId}_${props.moduleType}`
  }

  function readIdSet(key: string): Set<string> {
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

  function writeIdList(key: string, ids: any[]): void {
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
  function loadRandomPlan(data: any[], count: number | string): any[] | null {
    try {
      const raw = localStorage.getItem(randomPlanKey())
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
  function buildRandomPlan(data: any[], count: number | string): any[] {
    const lastRound = readIdSet(lastRoundKey())

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
    writeIdList(randomPlanKey(), picked.map((q) => q?.id ?? q?.questionId).filter((x) => x !== undefined && x !== null))
    writeIdList(lastRoundKey(), picked.map((q) => q?.id ?? q?.questionId).filter((x) => x !== undefined && x !== null))

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
  function clearRandomPlan(): void {
    try {
      localStorage.removeItem(randomPlanKey())
    } catch {
      // 忽略：清不掉最多是沿用了旧题单，不影响功能
    }
  }

  // 通用题目处理函数 - 现在可被外部调用
  async function processQuestions(data: any[]): Promise<void> {
    /*
     * 一进来先清掉上一次的「没有题」标记。
     *
     * ⚠️ 位置很关键：必须在这里（有数据可用、马上要算出新结果的地方），
     *    而不是在 `fetchQuestions` 开头 —— 那里先清、随后又可能被
     *    `clearForNoQuestions` 写回，中间会闪一下"没有空态的有空态"。
     *    放在 `processQuestions` 入口，语义就是"我现在要重新算题了，
     *    算完是什么结果，下面各分支自己负责写"。见 `clearNoQuestionsState`。
     */
    clearNoQuestionsState()

    const count = questionCount.value
    // 判断是否需要打乱题目顺序：随机/模拟考试固定打乱，自定义练习根据 shuffleOptions 设置
    const moduleSettings = store.getModuleSettings(props.moduleType)
    const shouldShuffle = props.moduleType === 'random' || props.moduleType === 'mock' ||
                         (props.moduleType === 'custom' && moduleSettings.shuffleOptions)
    const offset = questionOffset.value

    // 调试日志：开始处理
    debugProcessStart(props.moduleType, data, { shouldShuffle, questionCount: count, offset })

    if (shouldShuffle) {
      /*
       * 「随机练习」= 一次随机，题单固定（2026-10-20 按用户方案重做）
       * =================================================================
       * 用户口径：
       *   ① 「刷新页面一直都是这题 只是他的序号变了 可能是第一题 可能是第二题
       *      每次刷新题号不一样 但是题目一样」        ← 报的现象
       *   ② 「随机只随机一次 在用户没有提交结果刷完这个题库时 永远也都是保留暂存结果」
       *                                              ← 给的方案，按它实现
       *
       * 旧实现的两个毛病：
       *   · `shuffledCache` 是模块级 Map，**刷新即失效** → 每次刷新重新洗牌；
       *   · 暂存里又按 `currentQuestionId` 把用户拽回同一道题 →
       *     "题号变、题目不变"。两个机制互相打架。
       *
       * 现在的做法：
       *   题单持久化在 localStorage（`loadRandomPlan`），刷新/重开浏览器都沿用同一份；
       *   只有「重新练习」「练完一轮」「题目增删」「练习数量变化」才重建
       *   （见 `buildRandomPlan` / `clearRandomPlan` 的注释）。
       *   既然顺序天然稳定，暂存里的 `currentQuestionId` 就能正确定位 ——
       *   两个机制不再冲突，而是互补。
       *
       * `shuffledCache` 仍然保留：它解决的是**同一会话内**重复调用
       * processQuestions（如切换设置后重进）时不要重排。跨会话的稳定性由 localStorage 保证。
       */
      const cacheKey = `${props.bankId}_${props.moduleType}`
      let shuffled: any[]

      const hasCache = shuffledCache.has(cacheKey)
      debugCacheCheck(props.moduleType, cacheKey, hasCache, hasCache ? shuffledCache.get(cacheKey) : null)

      if (hasCache) {
        // 同一会话内已经排过序 → 沿用，避免"翻着翻着顺序又变"
        shuffled = shuffledCache.get(cacheKey) as any[]
      } else {
        // 先看有没有持久化的题单；没有（或已失效）才生成新的
        const planned = loadRandomPlan(data, count)
        shuffled = planned || buildRandomPlan(data, count)
        debugShuffle(props.moduleType, [...data], shuffled)
        debugCacheWrite(props.moduleType, cacheKey, shuffled)
        shuffledCache.set(cacheKey, shuffled)
      }

      // 调试日志：设置 allQuestionsData
      debugSetAllQuestionsData(props.moduleType, shuffled, 'processQuestions(shuffle)')
      // 将打乱后的数组保存到 allQuestionsData，确保后续切片保持乱序
      allQuestionsData.value = shuffled

      const sliceEnd = count === 'all' ? shuffled.length : count as number
      const slicedData = shuffled.slice(0, sliceEnd)

      // ⚠️ 同顺序分支：只刷错题时**先过滤、后赋值 questions**，
      //    否则「0 条错题」的题库会先闪一屏全部题目（2026-10-20 修的 bug）。
      if (onlyWrong.value) {
        const ok = await filterOnlyWrongQuestions()
        if (!ok) {
          clearForNoWrongQuestions('这个题库里还没有你的错题')
          return
        }
        debugProcessComplete(props.moduleType, questions.value, allQuestionsData.value)
        return
      }

      // 调试日志：设置 questions
      debugSetQuestions(props.moduleType, slicedData, 'processQuestions(shuffle)')

      questions.value = slicedData.map((q) => {
        const processed = transformQuestionForDisplay(q)
        return {
          ...processed,
          answered: false,
          correct: false,
          showAnalysis: false,
          userAnswer: null
        }
      })

      // 调试日志：处理完成
      debugProcessComplete(props.moduleType, questions.value, allQuestionsData.value)

      resetAnswers()
      await loadQuestionStatus()
      loading.value = false
    } else {
      if (offset >= data.length) {
        /*
         * 「这一轮已经刷完」的兜底（2026-10-21 修：原来这里只弹一次瞬时提示，
         * 下面留一片空白 —— 用户口径「顺序练习模式下的只刷错题…没有兜底 UI 友好提示」）
         *
         * 原来的写法：
         *     proxy.$modal.msgInfo('已刷完所有题目')   ← 3 秒自动消失
         *     questions.value = []
         *     return                                  ← 页面永久空白
         *
         * 用户看到的是：点了「提交」→ 一条消息一闪而过 → 之后再回来就是空白页，
         * 分不清「刷完了」还是「坏了」，也没有任何回去/重来的入口。
         *
         * 修法与「没有错题」共用同一个空态区域，只是文案和动作不同 ——
         * 这样**所有"没有题可练"的情况都有说得清、可操作的兜底**，
         * 不再依赖会消失的 toast。
         */
        clearForNoQuestions('本轮题目已经刷完', 'finished')
        return
      }

      const sliceEnd = count === 'all' ? data.length : Math.min(offset + (count as number), data.length)
      const slicedData = data.slice(offset, sliceEnd)

      // 调试日志：设置 allQuestionsData（顺序模式）
      debugSetAllQuestionsData(props.moduleType, data, 'processQuestions(sequential)')
      allQuestionsData.value = data

      /*
       * ⚠️⚠️ 「只刷错题」必须在**赋值 questions 之前**过滤（2026-10-20 修的 bug）。
       *
       * 原来的顺序是：
       *     questions.value = slicedData.map(...)   ← 全部题目先渲染
       *     await filterOnlyWrongQuestions()        ← 一次网络往返之后才清空
       * 于是「0 条错题」的题库会**先闪一屏全部题目**，再提示失败/暂无错题。
       * 用户看到的就是「把所有题目获取过来，然后显示获取错题列表失败」。
       *
       * 现在：先过滤 allQuestionsData（本函数内部只动它），确认有可练的错题之后，
       * 才按过滤后的结果赋值 questions —— 一帧都不会闪。
       */
      if (onlyWrong.value) {
        // 让 filterOnlyWrongQuestions 自己去收敛 allQuestionsData 并调用 applyQuestionLimits
        const ok = await filterOnlyWrongQuestions()
        if (!ok) {
          clearForNoWrongQuestions('这个题库里还没有你的错题')
          return
        }
        debugProcessComplete(props.moduleType, questions.value, allQuestionsData.value)
        return
      }

      // 调试日志：设置 questions（顺序模式）
      debugSetQuestions(props.moduleType, slicedData, 'processQuestions(sequential)')

      questions.value = slicedData.map((q) => {
        const processed = transformQuestionForDisplay(q)
        return {
          ...processed,
          answered: false,
          correct: false,
          showAnalysis: false,
          userAnswer: null
        }
      })

      resetAnswers()
      await loadQuestionStatus()
      loading.value = false
    }
  }

  /**
   * 「只刷错题」：把题目过滤成本题库里**仍在错题本中**的那些
   *
   * ⚠️⚠️ 这个函数在 2026-10-20 修过一个用户可见的 bug，改之前先读完这段：
   *
   * **现象**：在「刷题设置」里勾上「只刷错题」，进入一个**没有错题**的题库，
   * 会先看到**整个题库的题目**闪一下，然后提示「获取错题列表失败」，最后空白。
   *
   * **根因**（两个叠在一起）：
   *   1. 调用方 `processQuestions` 是「先把全部题目写进 `questions` / `allQuestionsData`，
   *      再 `await` 本函数去过滤」——中间隔着**一次网络往返**，所以全部题目必然先渲染一帧；
   *   2. 本函数原来把「一次网络请求 + 数据过滤 + 状态加载」整段包在**一个 try** 里，
   *      `catch` 把**任何**异常的文案都替换成「获取错题列表失败」，并且**不打印原始异常**。
   *      于是「0 条错题」这种**完全正常**的业务情况，一旦中间某步抛错（例如
   *      `applyQuestionLimits()` 里 `msgInfo` 触发的渲染、或状态接口失败），
   *      用户看到的就是一句笼统的「获取错题列表失败」，而控制台一个字都没有。
   *
   * **修法**：
   *   · 由调用方**先过滤、再赋值**（见 `processQuestions` 里 `onlyWrong` 分支）；
   *   · 本函数只负责「取错题 id → 过滤 allQuestionsData → 交给 applyQuestionLimits」，
   *     且**把「没有错题」当成正常结果**提前返回，不走进 catch；
   *   · catch 里 `console.error` 打原始异常，提示文案带上真实原因（可诊断）。
   *
   * Returns:
   *   `true`  = 过滤已生效（`allQuestionsData` 已被收窄，调用方应据此决定是否赋值题目）
   *   `false` = 当前没有错题（调用方应把题目清空并给「暂无错题」的引导）
   */
  async function filterOnlyWrongQuestions(): Promise<boolean> {
    // ① 登录态：拿不到 userId 就不用发请求（这不是「失败」，是前提不满足）
    const userId = userStore.id || (userStore as any).userId
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      return false
    }

    // ② 取错题列表 —— 这一段单独 try，失败原因能精确到「请求本身」
    let errorList: any[] = []
    try {
      const res = await listQuestionErrorAll({ userId, bankId: props.bankId })
      if (res && res.code === 200) {
        errorList = Array.isArray(res.data) ? res.data : []
      } else {
        // 业务码非 200：把服务端原话带出来，不要笼统说「失败」
        const why = (res as any)?.msg || `业务码 ${(res as any)?.code}`
        console.error('[onlyWrong] 错题列表返回异常：', res)
        proxy.$modal.msgError(`获取错题列表失败：${why}`)
        return false
      }
    } catch (e: any) {
      console.error('[onlyWrong] 请求错题列表抛异常：', e)
      proxy.$modal.msgError(`获取错题列表失败：${e?.message || e || '网络错误'}`)
      return false
    }

    // ③ 0 条错题 = **正常业务结果**，不是错误。
    //    ⚠️ 这里必须提前 return，绝不能落进下面的 catch —— 那正是「0 条错题却提示
    //    『获取失败』」的来源。
    if (errorList.length === 0) {
      return false
    }

    // ④ 过滤 + 收敛题目（这之后才动 questions）
    try {
      const errorQuestionIds = new Set(errorList.map((e: any) => Number(e.questionId)))
      const filtered = allQuestionsData.value.filter((q) => errorQuestionIds.has(Number(q.id)))
      if (filtered.length === 0) {
        // 有错题记录，但都不在当前题库/当前这一页里 —— 也是「没有可练的错题」
        return false
      }
      allQuestionsData.value = filtered
      // ⚠️ resetOffset: true —— 数组已经从「全库」换成「错题集」，旧偏移量失效。
      //    不归零就是 bug1：offset 越界 → 被判成「已刷完所有题目」→ 空白页。
      applyQuestionLimits({ resetOffset: true })
      // 批量加载收藏/斩题状态（错题状态已通过 errorQuestionIds 确定）
      await loadQuestionStatus()
      return true
    } catch (e: any) {
      // 走到这里说明**数据本身**有问题（不是请求），原文打出来
      console.error('[onlyWrong] 过滤错题后渲染失败：', e)
      proxy.$modal.msgError(`错题练习初始化失败：${e?.message || e}`)
      questions.value = []
      allQuestionsData.value = []
      loading.value = false
      return false
    }
  }

  /**
   * 清空题目并给出**可执行的引导**（统一入口，2026-10-21 扩展）
   *
   * ⚠️ 为什么需要它：原来「没有题可练」的几种情况处理方式不一致 ——
   *   · 只刷错题 + 没有错题 → 有 `.practice-empty` 空态（2026-10-20 修的）
   *   · 顺序模式刷完了      → 只弹一次 `msgInfo('已刷完所有题目')`，**下面一片空白**
   * 用户口径：「顺序练习模式下的只刷错题的视图 没有错题 没有兜底 ui 友好提示
   *   用户 其他模式都有」—— 说的就是后者：其他模式有空态，顺序模式这条却只留空白。
   *
   * 现在统一走这里，**任何"没有题可练"都落在同一个空态区域**，
   * 并带 `kind` 让 UI 区分文案与动作：
   *   · `'noWrong'`   —— 题库里没有你的错题（可「关闭只刷错题」或「返回题库」）
   *   · `'finished'`  —— 本轮已刷完（可「重新练习」或「返回题库」）
   *
   * 为什么坚持**不用 toast 兜底**：`ElMessage` / `$modal.msgInfo` 都是瞬时的，
   * 3 秒后什么都不剩，用户回头再看只看到一个空白页 ——
   * 「刷完了」和「坏了」在视觉上完全一样。
   */
  function clearForNoQuestions(reason: string, kind: 'noWrong' | 'finished' = 'noWrong'): void {
    questions.value = []
    allQuestionsData.value = []
    currentQuestionIndex.value = 0
    resetAnswers()
    loading.value = false
    noWrongQuestionsReason.value = reason
    noQuestionsKind.value = kind
  }

  /** 兼容旧调用点：语义与 `clearForNoQuestions(reason, 'noWrong')` 相同 */
  function clearForNoWrongQuestions(reason: string): void {
    clearForNoQuestions(reason, 'noWrong')
  }

  /**
   * 清掉「没有题可练」的空态标记
   *
   * ⚠️ 必须有这一步（2026-10-21）：`noWrongQuestionsReason` 原来**只写不清**，
   * 一旦被置成非空，就再也不会回到空串。而组件的空态判据是
   * `noWrongQuestionsReason && questions.length === 0` ——
   * 平时靠"有题目"掩盖着，看不出问题；但用户点了空态里的
   * 「关闭只刷错题 / 重新练习」（会重拉题目）之后，只要某个瞬间
   * `questions` 被清空（重拉时先 `questions.value = []`），
   * 那个旧文案就会**再次闪出来**，显示的还是上一次的「没有错题」。
   *
   * 调用时机：**成功拿到题目**的地方（`processQuestions` 入口、`applyQuestionLimits`
   * 的非空分支）。失败/真的没有题时由 `clearForNoQuestions` 重新写回。
   */
  function clearNoQuestionsState(): void {
    noWrongQuestionsReason.value = ''
  }

  /**
   * 把「后端原始题目数组」转成组件能渲染的 `TransformedQuestion[]`
   *
   * ⚠️⚠️ **任何给 `questions.value` 赋值的地方都必须经过它**（2026-10-20 修的 bug）。
   *
   * 现象（用户口径）：「只刷错题 会变成题型无法识别 全部都一样」，截图里每一道题
   * 都显示「未知题型 / 暂不支持该题型」。
   *
   * 根因：`transformQuestionForDisplay()` 负责把 `questionType`(数字 1~7) 映射成
   * 组件认识的 `type`('single'/'multiple'/…) 并整理 options 等字段。
   * `processQuestions` 的分支是 `slicedData.map(transformQuestionForDisplay)`，
   * 但我在修 bug1 时让错题分支改走 `applyQuestionLimits()` —— 而那个函数里是
   * **裸赋值** `questions.value = shuffled / slice(...)`，
   * 于是 `questions` 里躺的是后端原始对象：没有 `type`、没有整理过的 options，
   * 组件拿不到题型 → 每道题都渲染成「未知题型」。
   *
   * 修法：把转换收进这一个函数，`applyQuestionLimits` 的四个赋值点全部改用它。
   * 这样「哪里赋值」不再重要 —— 只要都走这里，就不会再漏一次。
   */
  function toDisplayQuestions(raw: any[]): TransformedQuestion[] {
    return (raw || []).map((q) => {
      const processed = transformQuestionForDisplay(q)
      return {
        ...processed,
        // 每次都重置答题态：换波/换筛选之后，上一波的作答不能带过来
        answered: false,
        correct: false,
        showAnalysis: false,
        userAnswer: null
      } as TransformedQuestion
    })
  }

  function applyQuestionLimits(options: { resetOffset?: boolean } = {}): void {
    if (allQuestionsData.value.length === 0) {
      resetAnswers()
      loading.value = false
      return
    }
    /*
     * 走到这里说明**确实有题可练** —— 前面任何一次留下的"没有题"标记都该失效。
     * 不在这里清的话，「本轮刷完」→ 用户点「重新练习」→ 重新拉到题目后，
     * 空态文案还挂在状态里（虽然题目盖住了它），下次任何一次 questions 短暂
     * 为空的瞬间都会把它闪出来。见 `clearNoQuestionsState` 的注释。
     */
    clearNoQuestionsState()
    const count = questionCount.value
    const shouldShuffle = props.moduleType === 'random' || props.moduleType === 'mock'
    /*
     * ⚠️⚠️ 「只刷错题」时必须把偏移归零（2026-10-20 修的 bug1）。
     *
     * 现象（用户口径）：顺序/随机练习 + 勾上「只刷错题」→ 进去一片空白，
     * 兜底显示「什么都没有」。
     *
     * 根因：`questionOffset` 是**按全库题数**算出来的分波进度（例如刷到第 3 波 = offset 40）；
     * 而「只刷错题」会把 `allQuestionsData` 收窄成几十条里的一两条 ——
     * 于是下面 `offset >= allQuestionsData.length` 立刻成立，走进「已刷完所有题目」
     * 分支：清空 questions + 弹提示。用户看到的就是空页面。
     *
     * 为什么不能只改判断条件：偏移量的**语义**就是「在这个数组里从第几条开始」。
     * 数组换了（全库 → 错题集），旧偏移量没有意义，必须归零 ——
     * 否则即使不越界，也会从错题集中间开始刷，用户以为是漏题。
     *
     * 由调用方（`filterOnlyWrongQuestions`）显式传 `resetOffset: true`，
     * 而不是在这里无条件归零：正常的分波翻页**必须**保留偏移。
     */
    if (options.resetOffset) {
      questionOffset.value = 0
    }
    const offset = questionOffset.value

    if (shouldShuffle) {
      const shuffled = [...allQuestionsData.value]
      for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
      }
      // ⚠️ 必须 toDisplayQuestions，不能裸赋值（见该函数的注释）
      questions.value = toDisplayQuestions(
        count === 'all' ? shuffled : shuffled.slice(0, count as number)
      )
    } else if (offset >= allQuestionsData.value.length) {
      /*
       * 随机/错题模式下的「本轮刷完」—— 与上面顺序模式那条同因同修（2026-10-21）。
       * 原来同样是「弹一条瞬时提示 + 留下空白页」，用户回头看不到任何线索。
       */
      clearForNoQuestions('本轮题目已经刷完', 'finished')
      return
    } else if (count && count !== 'all' && typeof count === 'number' && count < allQuestionsData.value.length) {
      // ⚠️ 同上：必须转换
      questions.value = toDisplayQuestions(
        allQuestionsData.value.slice(offset, offset + count)
      )
    } else {
      // ⚠️ 同上：必须转换
      questions.value = toDisplayQuestions(allQuestionsData.value)
    }

    resetAnswers()
    loading.value = false
  }

  // 批量加载题目的收藏/斩题/错题状态
  async function loadQuestionStatus(): Promise<void> {
    if (questions.value.length === 0) return

    const questionIds = questions.value.map(q => Number(q.id))

    try {
      const [favRes, markedRes, errorRes] = await Promise.all([
        batchCheckFavorite(questionIds),
        batchCheckMarked(questionIds),
        batchCheckError(questionIds),
      ])

      if (favRes.code === 200 && favRes.data) {
        favoritedQuestions.value = new Set(
          Object.entries(favRes.data).filter(([, v]) => v).map(([k]) => Number(k))
        )
      }
      if (markedRes.code === 200 && markedRes.data) {
        markedQuestions.value = new Set(
          Object.entries(markedRes.data).filter(([, v]) => v).map(([k]) => Number(k))
        )
      }
      if (errorRes.code === 200 && errorRes.data) {
        errorQuestions.value = new Set(
          Object.entries(errorRes.data).filter(([, v]) => v).map(([k]) => Number(k))
        )
      }
    } catch (e) {
      // 静默失败，不影响刷题
      console.warn('加载题目状态失败', e)
    }
  }

  function loadBatchWithoutReset(): void {
    if (allQuestionsData.value.length === 0) {
      return
    }
    const count = questionCount.value
    const offset = questionOffset.value

    if (offset >= allQuestionsData.value.length) {
      questions.value = []
      answers.value = []
      return
    }

    let sliceEnd: number
    if (count === 'all') {
      sliceEnd = allQuestionsData.value.length
    } else if (typeof count === 'number') {
      sliceEnd = Math.min(offset + count, allQuestionsData.value.length)
    } else {
      sliceEnd = Math.min(offset + 10, allQuestionsData.value.length)
    }

    // 对切片后的数据调用 transformQuestionForDisplay 转换
    const slicedData = allQuestionsData.value.slice(offset, sliceEnd)
    questions.value = slicedData.map(q => {
      const processed = transformQuestionForDisplay(q)
      return {
        ...processed,
        answered: false,
        correct: false,
        showAnalysis: false,
        userAnswer: null
      }
    })

    answers.value = questions.value.map(q => {
      if (['readingComprehension', 'cloze'].includes(q.type)) {
        return {}
      }
      return null
    })

    currentQuestionIndex.value = 0
    selectedAnswer.value = null
    loading.value = false

    // 记录刷题学习时间（下一波题目）
    if (props.bankId && slicedData.length > 0) {
      const questionIds = slicedData.map((q: any) => q.id).filter(Boolean)
      console.log('[学习时间记录-下一波] 准备调用 API', { bankId: props.bankId, questionIdsCount: questionIds.length })
      recordStudyTime({ bankId: props.bankId, questionIds }).then((res: any) => {
        console.log('[学习时间记录-下一波] API 返回成功', res)
      }).catch((err: any) => {
        console.error('[学习时间记录-下一波] API 调用失败', err)
      })
    }
  }

  // 新增：更新题目数量并重新切片，保留已答题目的状态
  function updateQuestionCountAndSlice(newCount: number | string): void {
    questionCount.value = newCount

    // 如果 allQuestionsData 为空，不需要处理
    if (allQuestionsData.value.length === 0) {
      return
    }

    // 保存当前题目的答题状态（通过题目 ID 映射）
    const oldQuestionsMap = new Map<any, any>()
    questions.value.forEach((q, index) => {
      if (q && q.id) {
        oldQuestionsMap.set(q.id, {
          question: q,
          answer: answers.value[index],
          index: index
        })
      }
    })

    // 计算新的偏移量，保持在当前批次的起始位置
    let newOffset = 0
    if (newCount !== 'all' && typeof newCount === 'number') {
      newOffset = Math.floor(questionOffset.value / newCount) * newCount
    }
    questionOffset.value = Math.max(0, newOffset)

    // 从 allQuestionsData 中重新切片
    let sliceEnd: number
    if (newCount === 'all') {
      sliceEnd = allQuestionsData.value.length
    } else if (typeof newCount === 'number') {
      sliceEnd = Math.min(newOffset + newCount, allQuestionsData.value.length)
    } else {
      sliceEnd = Math.min(newOffset + 10, allQuestionsData.value.length)
    }

    const newData = allQuestionsData.value.slice(newOffset, sliceEnd)

    // 处理新数据，保留已答题目的状态
    questions.value = newData.map(q => {
      const processed = transformQuestionForDisplay(q)
      const existing = oldQuestionsMap.get(q.id)

      if (existing) {
        // 保留已答题目的状态
        return {
          ...processed,
          answered: existing.question.answered,
          correct: existing.question.correct,
          showAnalysis: existing.question.showAnalysis,
          userAnswer: existing.question.userAnswer
        }
      }

      return {
        ...processed,
        answered: false,
        correct: false,
        showAnalysis: false,
        userAnswer: null
      }
    })

    // 重新构建 answers 数组，保留已答题目的答案
    const newAnswers = questions.value.map(q => {
      const existing = oldQuestionsMap.get(q.id)
      if (existing && existing.answer !== undefined) {
        return existing.answer
      }
      if (['readingComprehension', 'cloze'].includes(q.type)) {
        return {}
      }
      return null
    })

    answers.value = newAnswers

    // 确保 currentQuestionIndex 在有效范围内
    if (currentQuestionIndex.value >= questions.value.length) {
      currentQuestionIndex.value = Math.max(0, questions.value.length - 1)
    }

    // 使用 goToQuestion 同步所有状态（包括 selectedAnswer、子题答案等）
    const targetIndex = currentQuestionIndex.value
    if (questions.value[targetIndex]) {
      currentQuestionIndex.value = targetIndex
      const q = questions.value[targetIndex]
      const ans = answers.value[targetIndex]

      // 对于阅读理解或完形填空，同步子题答案
      if (['readingComprehension', 'cloze'].includes(q.type)) {
        selectedAnswer.value = null
        if (ans && ans.fillblank) {
          subFillBlankAnswers.value = { ...ans.fillblank }
        } else {
          subFillBlankAnswers.value = {}
        }
        if (ans && ans.essay) {
          subEssayAnswers.value = { ...ans.essay }
        } else {
          subEssayAnswers.value = {}
        }
      } else {
        selectedAnswer.value = ans ?? null
      }
    } else {
      selectedAnswer.value = null
      subFillBlankAnswers.value = {}
      subEssayAnswers.value = {}
    }

    loading.value = false
  }

  /**
   * 取组合题的子题数组（**字段名兼容**）
   *
   * ⚠️ 这里踩过坑（用户 2026-10-18 bug3「组合题只有题干、看不到子题」）：
   *    前端原来只读 `q.questionSubList`，但后端 `format_question()` 返回的键叫
   *    `subQuestions`（见 `app/api/v1/questions.py`）——**永远取不到**，
   *    于是子题数组恒为空、`ReadingComprehensionDisplay` 的
   *    `v-if="subQuestions.length > 0"` 整块不渲染，界面上就只剩题干。
   *
   *    三个候选键都兼容：`subQuestions`（后端现用）/ `questionSubList`（早期约定，写入时用）/
   *    `question_sub_list`（蛇形接口）。取到第一个非空数组即返回。
   */
  function pickSubList(q: any): any[] {
    if (!q) return []
    const candidates = [q.subQuestions, q.questionSubList, q.question_sub_list]
    for (const c of candidates) {
      if (Array.isArray(c) && c.length > 0) return c
    }
    return []
  }
  // ✅ 关键：导出的通用转换函数 - 完整版
  function transformQuestionForDisplay(q: any): TransformedQuestion {
    let type: QuestionType = 'unknown'
    switch (q.questionType || q.question_type) {
      case 1:
        type = 'single'
        break
      case 2:
        type = 'multiple'
        break
      case 3:
        type = 'truefalse'
        break
      case 4:
        type = 'fillblank'
        break
      case 5:
        type = 'essay'
        break
      case 6:
        type = 'readingComprehension'
        break
      case 7:
        type = 'cloze'
        break
      default:
        type = 'unknown'
    }

    // 解析选项
    let options: any[] = []
    if (q.options) {
      try {
        // 优先使用 parseOptions 函数
        if (typeof parseOptions === 'function') {
          options = parseOptions(q.options, type)
        } else {
          // 备用方案：手动解析
          if (typeof q.options === 'string') {
            const trimmed = q.options.trim()
            if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
              options = JSON.parse(trimmed)
            } else if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
              const parsed = JSON.parse(trimmed)
              options = Object.values(parsed).filter((val: any) => val !== null && val !== undefined)
            } else {
              options = trimmed.split(',').map((opt: string) => opt.trim())
            }
          } else if (Array.isArray(q.options)) {
            options = q.options
          } else if (typeof q.options === 'object') {
            options = Object.values(q.options).filter((val: any) => val !== null && val !== undefined)
          }
        }
      } catch (e) {
        // 创建有意义的默认选项
        if (type === 'single' || type === 'multiple') {
          // 根据题目内容创建相关选项
          const baseOptions = ['has studied', 'studies', 'is studying', 'study']
          options = baseOptions
        } else if (type === 'truefalse') {
          options = ['正确', '错误']
        }
      }
    } else {
      // 创建有意义的默认选项
      if (type === 'single' || type === 'multiple') {
        // 根据题目内容创建相关选项
        if (q.questionText && q.questionText.includes('English')) {
          options = ['has studied', 'studies', 'is studying', 'study']
        } else if (q.questionText && q.questionText.includes('If I')) {
          options = ['am', 'was', 'were', 'be']
        } else {
          options = ['选项A', '选项B', '选项C', '选项D']
        }
      } else if (type === 'truefalse') {
        options = ['正确', '错误']
      }
    }

    // ✅ 改进：正确答案标准化
    let correctAnswer: any = q.answer

    if (type === 'truefalse') {
      const ans = String(q.answer).trim().toLowerCase()
      correctAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
    } else if (type === 'single') {
      if (typeof q.answer === 'string') {
        const ansStr = q.answer.trim()
        const letter = ansStr.toUpperCase()
        if (letter.length === 1 && letter >= 'A' && letter <= 'Z') {
          correctAnswer = letter.charCodeAt(0) - 65
        } else {
          const num = Number(ansStr)
          if (!isNaN(num)) {
            correctAnswer = num
          } else {
            correctAnswer = 0
          }
        }
      } else {
        correctAnswer = Number(q.answer) || 0
      }
    } else if (type === 'multiple') {
      if (typeof q.answer === 'string') {
        const ansStr = q.answer.trim()

        if (ansStr.startsWith('[') && ansStr.endsWith(']')) {
          try {
            const parsed = JSON.parse(ansStr)
            if (Array.isArray(parsed)) {
              if (parsed.every((item: any) => typeof item === 'number')) {
                correctAnswer = parsed
              }
              else if (parsed.every((item: any) => typeof item === 'string' && item.length === 1)) {
                correctAnswer = parsed
                  .map((s: string) => s.trim().toUpperCase())
                  .filter((s: string) => s >= 'A' && s <= 'Z')
                  .map((s: string) => s.charCodeAt(0) - 65)
              } else {
                correctAnswer = []
              }
            } else {
              correctAnswer = []
            }
          } catch (e) {
            correctAnswer = ansStr
              .split(/[,，]/)
              .map((s: string) => {
                s = s.trim().toUpperCase()
                if (s.length === 1 && s >= 'A' && s <= 'Z') {
                  return s.charCodeAt(0) - 65
                }
                const num = Number(s)
                return isNaN(num) ? null : num
              })
              .filter((n: number | null) => n !== null)
          }
        } else {
          correctAnswer = ansStr
            .split(/[,，]/)
            .map((s: string) => {
              s = s.trim().toUpperCase()
              if (s.length === 1 && s >= 'A' && s <= 'Z') {
                return s.charCodeAt(0) - 65
              }
              const num = Number(s)
              return isNaN(num) ? null : num
            })
            .filter((n: number | null) => n !== null)
        }
      } else if (Array.isArray(q.answer)) {
        correctAnswer = q.answer
          .map((item: any) => {
            if (typeof item === 'string') {
              const s = item.trim().toUpperCase()
              if (s.length === 1 && s >= 'A' && s <= 'Z') {
                return s.charCodeAt(0) - 65
              }
              const num = Number(s)
              return isNaN(num) ? null : num
            }
            return typeof item === 'number' ? item : null
          })
          .filter((n: number | null) => n !== null)
      } else {
        correctAnswer = []
      }

      if (!Array.isArray(correctAnswer)) {
        correctAnswer = []
      }
    } else if (type === 'fillblank' || type === 'essay') {
      // 填空题和问答题保持原始答案
      correctAnswer = q.answer
    }

    // 处理阅读理解 & 完形填空
    let subQuestions: any[] = []
    let hasMainContent = false
    let mainContent = ''
    let mainTitle = ''

    if (type === 'cloze') {
      mainContent = q.content || ''
      mainTitle = q.questionText || '完形填空'
      hasMainContent = true

      if (mainContent) {
        mainContent = mainContent.replace(/\[\[(\d+)\]\]/g, '___$1___')
      }

      if (pickSubList(q).length > 0) {
        subQuestions = pickSubList(q).map((sq: any, index: number) => {
          let sqType = 'single'
          switch (sq.questionType || sq.question_type) {
            case 1:
              sqType = 'single'
              break
            case 2:
              sqType = 'multiple'
              break
            case 3:
              sqType = 'truefalse'
              break
            case 4:
              sqType = 'fillblank'
              break
            case 5:
              sqType = 'essay'
              break
            default:
              sqType = 'single'
          }

          // 解析子题选项
          let sqOptions: any[] = []
          if (sq.options) {
            try {
              if (typeof sq.options === 'string') {
                const trimmed = sq.options.trim()
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                  sqOptions = JSON.parse(trimmed)
                } else {
                  sqOptions = trimmed.split(',').map((opt: string) => opt.trim())
                }
              } else if (Array.isArray(sq.options)) {
                sqOptions = sq.options
              }
            } catch (e) {
            }
          }

          // ✅ 改进：子题答案处理
          let sqCorrectAnswer: any = sq.answer
          if (sqType === 'truefalse') {
            const ans = String(sq.answer).trim().toLowerCase()
            sqCorrectAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
          } else if (sqType === 'single') {
            if (typeof sq.answer === 'string' && sq.answer.length === 1) {
              const letter = sq.answer.toUpperCase()
              if (letter >= 'A' && letter <= 'Z') {
                sqCorrectAnswer = letter.charCodeAt(0) - 65
              } else {
                sqCorrectAnswer = Number(sq.answer) || 0
              }
            } else {
              sqCorrectAnswer = Number(sq.answer) || 0
            }
          } else if (sqType === 'multiple') {
            // 使用相同的多选题答案处理逻辑
            if (typeof sq.answer === 'string') {
              sqCorrectAnswer = sq.answer
                .split(/[,，]/)
                .map((s: string) => {
                  s = s.trim().toUpperCase()
                  if (s.length === 1 && s >= 'A' && s <= 'Z') {
                    return s.charCodeAt(0) - 65
                  }
                  const num = Number(s)
                  return isNaN(num) ? null : num
                })
                .filter((n: number | null) => n !== null)
            } else if (Array.isArray(sq.answer)) {
              sqCorrectAnswer = sq.answer
            } else {
              sqCorrectAnswer = []
            }
          } else if (sqType === 'fillblank' || sqType === 'essay') {
            // ✅ 关键修复：填空题和问答题保持原始答案字符串
            sqCorrectAnswer = sq.answer
          }

          return {
            question: sq.questionText || sq.question_text || `第 ${index + 1} 空应填入：`,
            type: sqType,
            options: sqOptions,
            analysis: sq.analysis,
            correctAnswer: sqCorrectAnswer,
            answered: false,
            correct: false
          }
        })
      }
    }
    else if (type === 'readingComprehension') {
      mainContent = q.content || ''
      mainTitle = q.questionText || '阅读理解'
      hasMainContent = !!mainContent

      if (pickSubList(q).length > 0) {
        subQuestions = pickSubList(q).map((sq: any, index: number) => {
          let sqType = 'single'
          switch (sq.questionType || sq.question_type) {
            case 1:
              sqType = 'single'
              break
            case 2:
              sqType = 'multiple'
              break
            case 3:
              sqType = 'truefalse'
              break
            case 4:
              sqType = 'fillblank'
              break
            case 5:
              sqType = 'essay'
              break
            default:
              sqType = 'single'
          }

          // 解析子题选项
          let sqOptions: any[] = []
          if (sq.options) {
            try {
              if (typeof sq.options === 'string') {
                const trimmed = sq.options.trim()
                if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
                  sqOptions = JSON.parse(trimmed)
                } else {
                  sqOptions = trimmed.split(',').map((opt: string) => opt.trim())
                }
              } else if (Array.isArray(sq.options)) {
                sqOptions = sq.options
              }
            } catch (e) {
            }
          }

          // ✅ 改进：子题答案处理
          let sqCorrectAnswer: any = sq.answer
          if (sqType === 'truefalse') {
            const ans = String(sq.answer).trim().toLowerCase()
            sqCorrectAnswer = ans === 't' || ans === 'true' || ans === '1' ? 0 : 1
          } else if (sqType === 'single') {
            if (typeof sq.answer === 'string' && sq.answer.length === 1) {
              const letter = sq.answer.toUpperCase()
              if (letter >= 'A' && letter <= 'Z') {
                sqCorrectAnswer = letter.charCodeAt(0) - 65
              } else {
                sqCorrectAnswer = Number(sq.answer) || 0
              }
            } else {
              sqCorrectAnswer = Number(sq.answer) || 0
            }
          } else if (sqType === 'multiple') {
            if (typeof sq.answer === 'string') {
              sqCorrectAnswer = sq.answer
                .split(/[,，]/)
                .map((s: string) => {
                  s = s.trim().toUpperCase()
                  if (s.length === 1 && s >= 'A' && s <= 'Z') {
                    return s.charCodeAt(0) - 65
                  }
                  const num = Number(s)
                  return isNaN(num) ? null : num
                })
                .filter((n: number | null) => n !== null)
            } else if (Array.isArray(sq.answer)) {
              sqCorrectAnswer = sq.answer
            } else {
              sqCorrectAnswer = []
            }
          } else if (sqType === 'fillblank' || sqType === 'essay') {
            // ✅ 关键修复：填空题和问答题保持原始答案字符串
            sqCorrectAnswer = sq.answer
          }

          return {
            question: sq.questionText || sq.question_text || `问题 ${index + 1}`,
            type: sqType,
            options: sqOptions,
            analysis: sq.analysis,
            correctAnswer: sqCorrectAnswer,
            answered: false,
            correct: false
          }
        })
      }
    }

    if (!hasMainContent) {
      mainContent = ''
      mainTitle = ''
    }

    const questionObj = {
      id: q.id,
      bankId: q.bankId, // ✅ 添加 bankId 字段，用于错题记录
      difficulty: q.difficulty, // ✅ 添加难度字段
      question: (type === 'readingComprehension' || type === 'cloze') ? '' : (q.questionText || q.question_text),
      type,
      options,
      correctAnswer,
      analysis: q.analysis || '',
      mainContent,
      mainTitle,
      hasMainContent,
      subQuestions,
      answered: false,
      correct: false,
      showAnalysis: false,
      userAnswer: null,
      // 添加额外的元数据，方便调试
      _rawAnswer: q.answer,
      _rawOptions: q.options
    }

    return questionObj
  }

  // 新增：重置所有数据并重新加载题目（用于模式切换）
  // 保存当前答题状态到缓存
  // moduleType 参数可选，用于在模式切换时指定旧的 moduleType
  function saveCurrentAnswerState(moduleType?: string): void {
    // 如果 moduleType 显式传入且为 undefined，说明是路由过渡，不保存
    if (moduleType === undefined) {
      // 路由过渡状态，跳过保存
      return
    }
    const type = moduleType || props.moduleType
    if (!props.bankId || !type || questions.value.length === 0) return

    const cacheKey = `${props.bankId}_${type}`
    const state = {
      questions: [...questions.value],
      allQuestionsData: [...allQuestionsData.value],
      answers: [...answers.value],
      currentQuestionIndex: currentQuestionIndex.value,
      selectedAnswer: selectedAnswer.value,
      subFillBlankAnswers: { ...subFillBlankAnswers.value },
      subEssayAnswers: { ...subEssayAnswers.value },
      questionOffset: questionOffset.value,
      questionCount: questionCount.value
    }

    answerStateCache.set(cacheKey, state)
  }

  // 从缓存恢复答题状态
  function restoreAnswerState(): boolean {
    if (!props.bankId || !props.moduleType) return false

    const cacheKey = `${props.bankId}_${props.moduleType}`
    const state = answerStateCache.get(cacheKey)

    if (!state) {
      return false
    }

    /*
     * ⚠️ 缓存里是"空题目"时**不要恢复**（2026-10-21）。
     *
     * `resetAndFetchQuestions` 的流程是「先清空 → 再尝试从缓存恢复」。
     * 如果缓存恰好存着一份 `questions: []`（比如上一次就是在空态里存下的，
     * 或者保存时机赶上了清空的瞬间），恢复它就等于把 `questions` 又置回空，
     * 然后函数**直接 return，根本不会去调接口** ——
     * 用户点「重新练习」后页面依旧停在空态，且请求都没发出去，极难排查。
     *
     * 判据用 `allQuestionsData` 而不是 `questions`：真正能重新切出题目的是
     * 前者（`applyQuestionLimits` 从它切片）。前者非空才算"这份缓存有用"。
     */
    if (!Array.isArray(state.allQuestionsData) || state.allQuestionsData.length === 0) {
      answerStateCache.delete(cacheKey)
      return false
    }

    questions.value = state.questions
    allQuestionsData.value = state.allQuestionsData
    answers.value = state.answers
    currentQuestionIndex.value = state.currentQuestionIndex
    selectedAnswer.value = state.selectedAnswer
    subFillBlankAnswers.value = state.subFillBlankAnswers
    subEssayAnswers.value = state.subEssayAnswers
    questionOffset.value = state.questionOffset
    questionCount.value = state.questionCount
    loading.value = false

    return true
  }

  // 清除指定模块的答题状态缓存
  function clearAnswerStateCache(moduleType: string): void {
    if (!props.bankId || !moduleType) {
      return
    }
    const cacheKey = `${props.bankId}_${moduleType}`
    answerStateCache.delete(cacheKey)
  }

  // oldModuleType 参数可选，用于在模式切换时指定旧的 moduleType
  function resetAndFetchQuestions(oldModuleType?: string): void {
    // 调试日志
    debugResetAndFetch(props.moduleType, props.bankId)

    // 先保存当前答题状态（使用旧的 moduleType 作为 key）
    saveCurrentAnswerState(oldModuleType)

    // 同步最新的设置（模式切换后 moduleSettings 会变化）
    const settings = store.getModuleSettings(props.moduleType)
    questionCount.value = settings.questionCount
    onlyWrong.value = settings.onlyWrong || false

    isResetting.value = true

    /*
     * 「没有题可练」的空态标记必须在这里就清掉（2026-10-21）。
     *
     * 不清的后果：用户点空态里的「重新练习 / 关闭只刷错题」→ 本函数开始重拉 →
     * 但 `noWrongQuestionsReason` 还是上一次的值，而 `questions` 已经被清空
     * （下面第 6 行）→ `isEmptyState` 依旧为 true → 空态**原样留在屏幕上**，
     * 看起来就是"按钮点了没反应"。
     * 清掉之后，重拉期间显示的是 `loading` 遮罩，语义正确（正在加载）。
     */
    clearNoQuestionsState()

    questions.value = []
    allQuestionsData.value = []
    answers.value = []
    currentQuestionIndex.value = 0
    selectedAnswer.value = null
    subFillBlankAnswers.value = {}
    subEssayAnswers.value = {}
    questionOffset.value = 0
    loading.value = true

    // 尝试从缓存恢复，如果没有缓存则重新加载
    if (restoreAnswerState()) {
      isResetting.value = false
      return
    }

    // 重新加载题目
    fetchQuestionsInternal().finally(() => {
      // 延迟清除标志位，确保所有 watch 都已处理完毕
      setTimeout(() => {
        isResetting.value = false
      }, 100)
    })
  }

  // 内部函数：实际加载题目（跳过早期返回检查）
  async function fetchQuestionsInternal(): Promise<void> {
    // 调试日志
    debugFetchStart(props.moduleType, props.bankId)

    if (isFavoriteMode && singleQuestionId) {
      fetchSingleQuestion(singleQuestionId)
      return
    }

    if (!props.bankId || Number(props.bankId) <= 0) {
      loading.value = false
      return
    }

    loading.value = true

    try {
      // response 兼容 { data: [] } 与 { result: [] } 两种返回结构，故用 any
      const response: any = await listQuestionMainAll({
        bankId: props.bankId,
        status: "0"
      })
      let data: any[] = []
      if (Array.isArray(response.data)) {
        data = response.data
      } else if (Array.isArray(response.result)) {
        data = response.result
      }

      // 调试日志：API返回数据
      debugFetchComplete(props.moduleType, data)

      if (data.length === 0) {
        questions.value = []
        resetAnswers()
        loading.value = false
        return
      }

      processQuestions(data)
      subFillBlankAnswers.value = {}
      subEssayAnswers.value = {}
      await nextTick()
    } catch (err) {
      proxy.$modal.msgError('加载题目失败')
      loading.value = false
    }
  }

  // ✅ 修复：fetchQuestions 函数 - 确保初始化时重置子题答案
  async function fetchQuestions(): Promise<void> {
    // 调试日志
    debugFetchQuestions(props.moduleType, props.bankId, questions.value.length > 0)

    if (questions.value.length > 0) {
      loading.value = false
      return
    }

    if (isFavoriteMode && singleQuestionId) {
      fetchSingleQuestion(singleQuestionId)
      return
    }

    if (!props.bankId || Number(props.bankId) <= 0) {
      loading.value = false
      return
    }

    loading.value = true

    try {
      // response 兼容 { data: [] } 与 { result: [] } 两种返回结构，故用 any
      const response: any = await listQuestionMainAll({
        bankId: props.bankId,
        status: "0"
      })
      let data: any[] = []
      if (Array.isArray(response.data)) {
        data = response.data
      } else if (Array.isArray(response.result)) {
        data = response.result
      }

      if (data.length === 0) {
        questions.value = []
        resetAnswers()
        loading.value = false
        return
      }

      processQuestions(data)
      subFillBlankAnswers.value = {}
      subEssayAnswers.value = {}
      await nextTick()

      // 记录刷题学习时间（题库+题目）
      if (props.bankId && data.length > 0) {
        const questionIds = data.map((q: any) => q.id).filter(Boolean)
        console.log('[学习时间记录] 准备调用 API', { bankId: props.bankId, questionIdsCount: questionIds.length, questionIds })
        recordStudyTime({ bankId: props.bankId, questionIds }).then((res: any) => {
          console.log('[学习时间记录] API 返回成功', res)
        }).catch((err: any) => {
          console.error('[学习时间记录] API 调用失败', err)
        })
      } else {
        console.log('[学习时间记录] 跳过：bankId=' + props.bankId + ', data.length=' + data.length)
      }

      // 调试日志：状态快照
      debugStateSnapshot(props.moduleType, {
        questions: questions.value,
        allQuestionsData: allQuestionsData.value,
        currentQuestionIndex: currentQuestionIndex.value,
        questionCount: questionCount.value,
        questionOffset: questionOffset.value,
        isResetting: isResetting.value
      })
    } catch (err) {
      proxy.$modal.msgError('加载题目失败')
      loading.value = false
    }
  }

  // ✅ 修复：resetAnswers 函数 - 重置子题答案
  function resetAnswers(): void {
    currentQuestionIndex.value = 0
    selectedAnswer.value = null

    // ✅ 新增：重置子题答案显示数据
    subFillBlankAnswers.value = {}
    subEssayAnswers.value = {}

    answers.value = questions.value.map(q => {
      if (['readingComprehension', 'cloze'].includes(q.type)) {
        return {}
      }
      return null
    })

    questions.value.forEach((q) => {
      q.answered = false
      q.correct = false
      q.showAnalysis = false
    })
  }

  // ✅ 修复：goToQuestion 函数 - 添加子题答案同步逻辑
  function goToQuestion(index: number): void {
    const currentIndex = currentQuestionIndex.value
    const currentQ = questions.value[currentIndex]

    // 保存当前题目的答案
    if (currentIndex !== index && currentQ && !['readingComprehension', 'cloze'].includes(currentQ.type) && selectedAnswer.value !== null && answers.value[currentIndex] === null) {
      handleAnswerSubmission(currentIndex)
    }

    currentQuestionIndex.value = index
    const q = questions.value[index]
    const ans = answers.value[index]

    // 对于阅读理解或完形填空，重置 selectedAnswer 并同步子题答案
    if (['readingComprehension', 'cloze'].includes(q?.type)) {
      selectedAnswer.value = null

      // ✅ 新增：同步子题答案到显示数据
      if (ans && ans.fillblank) {
        subFillBlankAnswers.value = { ...ans.fillblank }
      } else {
        subFillBlankAnswers.value = {}
      }

      if (ans && ans.essay) {
        subEssayAnswers.value = { ...ans.essay }
      } else {
        subEssayAnswers.value = {}
      }

      return
    }

    selectedAnswer.value = ans ?? null

    // 设置解析显示状态
    if (ans !== null && q) {
      let isCorrect = false
      const ca = q.correctAnswer
      if (q.type === 'single' || q.type === 'truefalse') {
        isCorrect = ans === ca
      } else if (q.type === 'multiple') {
        isCorrect =
          Array.isArray(ans) &&
          Array.isArray(ca) &&
          ans.length === ca.length &&
          ans.every((v: any) => ca.includes(v))
      } else if (['fillblank', 'essay'].includes(q.type)) {
        isCorrect = String(ans).trim().toLowerCase() === String(ca).trim().toLowerCase()
      }
      q.showAnalysis = true
    }
  }
  function nextQuestion(): void {
    handleAnswerSubmission(currentQuestionIndex.value)

    if (currentQuestionIndex.value < totalQuestions.value - 1) {
      currentQuestionIndex.value++
      goToQuestion(currentQuestionIndex.value)
    }
  }

  function prevQuestion(): void {
    if (currentQuestionIndex.value > 0) {
      handleAnswerSubmission(currentQuestionIndex.value)
      currentQuestionIndex.value--
      goToQuestion(currentQuestionIndex.value)
    }
  }

  function selectOption(index: number): void {
    const type = currentQuestion.value?.type
    if (type === 'multiple') {
      const arr = Array.isArray(selectedAnswer.value) ? [...selectedAnswer.value] : []
      const i = arr.indexOf(index)
      if (i > -1) {
        arr.splice(i, 1)
      } else {
        arr.push(index)
      }
      selectedAnswer.value = arr
    } else if (['single', 'truefalse'].includes(type)) {
      selectedAnswer.value = index
    }
  }

  function selectSubOption(subIndex: number, optionIndex: number): void {
    const currentQ = currentQuestion.value
    if (!currentQ || !['readingComprehension', 'cloze'].includes(currentQ.type)) return
    if (!currentQ.subQuestions[subIndex]) return

    if (!answers.value[currentQuestionIndex.value]) {
      answers.value[currentQuestionIndex.value] = {}
    }

    const subQ = currentQ.subQuestions[subIndex]
    if (subQ.type === 'multiple') {
      if (!answers.value[currentQuestionIndex.value][subIndex]) {
        answers.value[currentQuestionIndex.value][subIndex] = []
      }
      const arr = [...answers.value[currentQuestionIndex.value][subIndex]]
      const i = arr.indexOf(optionIndex)
      if (i > -1) {
        arr.splice(i, 1)
      } else {
        arr.push(optionIndex)
      }
      answers.value[currentQuestionIndex.value][subIndex] = arr
    } else {
      answers.value[currentQuestionIndex.value][subIndex] = optionIndex
    }

    updateReadingOrClozeStatus()
    handleAnswerSubmission(currentQuestionIndex.value)
  }

  // ✅ 修复：updateSubFillBlankAnswer 函数 - 完整版
  function updateSubFillBlankAnswer(subIndex: number, value: string): void {
    const currentQ = currentQuestion.value
    if (!currentQ || !['readingComprehension', 'cloze'].includes(currentQ.type)) {
      return
    }

    // ✅ 关键修复：同时更新两个地方的答案数据
    // 1. 更新 answers 数组中的结构化答案（用于判题）
    if (!answers.value[currentQuestionIndex.value]) {
      answers.value[currentQuestionIndex.value] = {}
    }
    if (!answers.value[currentQuestionIndex.value].fillblank) {
      answers.value[currentQuestionIndex.value].fillblank = {}
    }
    answers.value[currentQuestionIndex.value].fillblank[subIndex] = value

    // 2. ✅ 新增：更新 subFillBlankAnswers（用于显示）
    // 确保是响应式更新
    subFillBlankAnswers.value = {
      ...subFillBlankAnswers.value,
      [subIndex]: value
    }

    updateReadingOrClozeStatus()
    handleAnswerSubmission(currentQuestionIndex.value)
  }

  // ✅ 修复：updateSubEssayAnswer 函数 - 完整版
  function updateSubEssayAnswer(subIndex: number, value: string): void {
    const currentQ = currentQuestion.value
    if (!currentQ || !['readingComprehension', 'cloze'].includes(currentQ.type)) {
      return
    }

    // ✅ 关键修复：同时更新两个地方的答案数据
    // 1. 更新 answers 数组中的结构化答案
    if (!answers.value[currentQuestionIndex.value]) {
      answers.value[currentQuestionIndex.value] = {}
    }
    if (!answers.value[currentQuestionIndex.value].essay) {
      answers.value[currentQuestionIndex.value].essay = {}
    }
    answers.value[currentQuestionIndex.value].essay[subIndex] = value

    // 2. ✅ 新增：更新 subEssayAnswers（用于显示）
    // 确保是响应式更新
    subEssayAnswers.value = {
      ...subEssayAnswers.value,
      [subIndex]: value
    }

    updateReadingOrClozeStatus()
    handleAnswerSubmission(currentQuestionIndex.value)
  }

  function updateReadingOrClozeStatus(): void {
    const currentIndex = currentQuestionIndex.value
    const q = questions.value[currentIndex]
    const ans = answers.value[currentIndex]
    if (!q || !['readingComprehension', 'cloze'].includes(q.type)) return

    const allAnswered = q.subQuestions.every((subQ: any, idx: number) => {
      if (subQ.type === 'fillblank') {
        return ans && ans.fillblank && ans.fillblank[idx] !== undefined && ans.fillblank[idx] !== ''
      } else if (subQ.type === 'essay') {
        return ans && ans.essay && ans.essay[idx] !== undefined && ans.essay[idx] !== ''
      } else {
        return ans && ans[idx] !== undefined
      }
    })
    q.answered = allAnswered
  }

  // ✅ 修复：handleAnswerSubmission 函数 - 完整版
  function handleAnswerSubmission(qIndex: number): void {
    if (submissionLock.value) return
    const q = questions.value[qIndex]
    if (!q) return

    submissionLock.value = true
    setTimeout(() => { submissionLock.value = false }, 100)

    let isCorrect = false
    let userAnswer: any = null

    if (['readingComprehension', 'cloze'].includes(q.type)) {
      // 阅读理解/完形填空处理逻辑
      const subAns = answers.value[qIndex] || {}

      // ✅ 修复：检查是否有填空题或问答题的答案
      const hasAnyAnswer = Object.keys(subAns).length > 0 &&
        (Object.keys(subAns).some(key => key !== 'fillblank' && key !== 'essay') ||
          (subAns.fillblank && Object.keys(subAns.fillblank).length > 0) ||
          (subAns.essay && Object.keys(subAns.essay).length > 0))

      if (hasAnyAnswer) {
        const allAnswered = q.subQuestions.every((subQ: any, i: number) => {
          if (subQ.type === 'fillblank') {
            const hasAnswer = subAns.fillblank && subAns.fillblank[i] !== undefined && subAns.fillblank[i] !== ''
            return hasAnswer
          } else if (subQ.type === 'essay') {
            const hasAnswer = subAns.essay && subAns.essay[i] !== undefined && subAns.essay[i] !== ''
            return hasAnswer
          } else {
            const hasAnswer = subAns[i] !== undefined
            return hasAnswer
          }
        })

        q.answered = allAnswered

        if (allAnswered) {
          let allCorrect = true
          for (let i = 0; i < q.subQuestions.length; i++) {
            const subQ = q.subQuestions[i]

            if (subQ.type === 'fillblank') {
              const userAns = subAns.fillblank && subAns.fillblank[i]

              if (!userAns || userAns.trim().toLowerCase() !== String(subQ.correctAnswer).trim().toLowerCase()) {
                allCorrect = false
                break
              }
            } else if (subQ.type === 'essay') {
              continue
            } else if (subQ.type === 'multiple') {
              const userAns = Array.isArray(subAns[i]) ? subAns[i].slice().sort() : []
              const correctAnswer = Array.isArray(subQ.correctAnswer) ? subQ.correctAnswer.slice().sort() : []
              if (JSON.stringify(userAns) !== JSON.stringify(correctAnswer)) {
                allCorrect = false
                break
              }
            } else {
              if (subAns[i] !== subQ.correctAnswer) {
                allCorrect = false
                break
              }
            }
          }

          q.correct = allAnswered && allCorrect
          q.showAnalysis = true

          const currentUserId = userStore.id || (userStore as any).userId
          if (currentUserId) {
            reportQuestionPractice(q, subAns, !!q.correct)
          }
        }
      }
      return
    }

    // 普通题目处理
    const ans = selectedAnswer.value
    if (ans !== null) {
      userAnswer = ans
      answers.value[qIndex] = ans
      q.answered = true

      const ca = q.correctAnswer

      if (q.type === 'single' || q.type === 'truefalse') {
        isCorrect = ans === ca
      } else if (q.type === 'multiple') {
        isCorrect = Array.isArray(ans) && Array.isArray(ca) &&
          ans.length === ca.length && ans.every((v: any) => ca.includes(v))
      } else if (['fillblank', 'essay'].includes(q.type)) {
        isCorrect = String(ans).trim().toLowerCase() === String(ca).trim().toLowerCase()
      }

      q.correct = isCorrect
      q.showAnalysis = true

      const currentUserId = userStore.id || (userStore as any).userId
      if (currentUserId) {
        reportQuestionPractice(q, userAnswer, isCorrect)
      }
    }
  }

  /**
   * 「重新练习」—— 这是随机题单**唯一该被丢弃**的用户入口
   *
   * ⚠️ 为什么必须在这里清题单（2026-10-20）：
   *   随机练习现在采用「一次随机、题单固定」的模型（见 `buildRandomPlan`）。
   *   如果"重新练习"不清题单，用户点它只会把答案清空，
   *   题目顺序还是老样子 —— 那就不是"重新练习"，而是"重做同一份卷子"。
   *   用户的诉求是"随机"，重新练习就应该换一批/换一个顺序。
   *
   * 注意只清**题单**，不清"上一轮做过哪些题"（`lastRoundKey`）：
   *   那份记录正是下一轮"新题优先"的依据，清掉就退化成纯随机了。
   */
  function resetPractice(): void {
    // 丢掉随机题单 + 会话内的乱序缓存，让下次加载重新生成
    clearRandomPlan()
    shuffledCache.delete(`${props.bankId}_${props.moduleType}`)
    questionOffset.value = 0
    resetAnswers()
    /*
     * 顺手清掉「没有题可练」的标记（2026-10-21）。
     *
     * 答题卡上的「重新练习」绑的就是本函数。它已经把所有进度归零了，
     * 那个空态标记再留着就自相矛盾（"重新练了"却还挂着"没有题"）。
     * 这里不清的话，`resetPractice()` 单独调用时（结算页/答题卡那条路径）
     * 空态会残留，只有走 `resetAndFetchQuestions` 才被清掉 —— 依赖调用方，
     * 太脆弱。函数自己保证"重置之后不再是空态"更可靠。
     */
    clearNoQuestionsState()
  }

  function showAllAnalysis(): void {
    questions.value.forEach(q => {
      q.showAnalysis = true
    })
  }

  function viewResult(): void {
    proxy.$modal.alert(
      `本次练习完成！\n答对 ${correctCount.value} 题，答错 ${wrongCount.value} 题，正确率 ${accuracy.value}%`
    )
  }

  async function collectQuestion(): Promise<void> {
    const question = currentQuestion.value
    if (!question) return

    const userId = userStore.id || (userStore as any).userId
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      return
    }

    try {
      const qid = Number(question.id)
      if (favoritedQuestions.value.has(qid)) {
        // 已收藏 → 取消收藏
        await deleteFavoriteQuestionByUserAndQuestion(userId, qid)
        favoritedQuestions.value.delete(qid)
        proxy.$modal.msgSuccess('已取消收藏')
      } else {
        // 未收藏 → 添加收藏
        await addFavoriteQuestion({
          questionId: qid,
          bankId: Number(question.bankId || props.bankId),
          userId,
        })
        favoritedQuestions.value.add(qid)
        proxy.$modal.msgSuccess('已收藏该题')
      }
    } catch (error) {
      proxy.$modal.msgError('操作失败')
    }
  }

  async function markQuestion(): Promise<void> {
    const question = currentQuestion.value
    if (!question) return

    const userId = userStore.id || (userStore as any).userId
    if (!userId) {
      proxy.$modal.msgWarning('请先登录')
      return
    }

    try {
      const qid = Number(question.id)
      if (markedQuestions.value.has(qid)) {
        // 已斩 → 取消斩题
        await deleteMarkedByUserAndQuestion(userId, qid)
        markedQuestions.value.delete(qid)
        proxy.$modal.msgSuccess('已取消斩题')
      } else {
        // 未斩 → 添加斩题
        await addQuestionMarked({
          questionId: qid,
          bankId: Number(question.bankId || props.bankId),
          userId,
        })
        markedQuestions.value.add(qid)
        proxy.$modal.msgSuccess('已标记为斩题')
      }
    } catch (error) {
      proxy.$modal.msgError('操作失败')
    }
  }

  function addNote(): void {
    proxy.$modal.msgInfo('请添加笔记')
  }

  function reportQuestion(): void {
    proxy.$modal.msgSuccess('已提交举报')
  }

  // 计算属性
  const currentQuestion = computed<TransformedQuestion>(() => questions.value[currentQuestionIndex.value])
  const totalQuestions = computed<number>(() => questions.value.length)
  const correctCount = computed<number>(() =>
    answers.value.filter((a, i) => {
      const q = questions.value[i]
      if (!q || a === null) return false
      if (['readingComprehension', 'cloze'].includes(q.type)) {
        const subAns = a
        if (!subAns || Object.keys(subAns).length === 0) return false
        return q.subQuestions.every((sq: any, idx: number) => {
          if (sq.type === 'fillblank') {
            const userAnswer = subAns.fillblank && subAns.fillblank[idx]
            return userAnswer !== undefined &&
              userAnswer.trim().toLowerCase() === String(sq.correctAnswer).trim().toLowerCase()
          } else if (sq.type === 'essay') {
            return true
          } else if (sq.type === 'multiple') {
            const userAnswer = Array.isArray(subAns[idx]) ? subAns[idx].slice().sort() : []
            const correctAnswer = Array.isArray(sq.correctAnswer) ? sq.correctAnswer.slice().sort() : []
            return JSON.stringify(userAnswer) === JSON.stringify(correctAnswer)
          } else {
            return subAns[idx] === sq.correctAnswer
          }
        })
      }
      if (q.type === 'multiple') {
        return Array.isArray(a) &&
          Array.isArray(q.correctAnswer) &&
          a.length === q.correctAnswer.length &&
          a.every((v: any) => q.correctAnswer.includes(v))
      }
      if (['fillblank', 'essay'].includes(q.type)) {
        return String(a).trim().toLowerCase() === String(q.correctAnswer).trim().toLowerCase()
      }
      return a === q.correctAnswer
    }).length
  )
  const wrongCount = computed<number>(() =>
    answers.value.filter((a, i) => {
      const q = questions.value[i]
      if (!q || a === null || !q.answered) return false

      if (['readingComprehension', 'cloze'].includes(q.type)) {
        const subAns = a
        if (!subAns || Object.keys(subAns).length === 0) return false
        return !q.subQuestions.every((sq: any, idx: number) => {
          if (sq.type === 'fillblank') {
            const userAnswer = subAns.fillblank && subAns.fillblank[idx]
            return userAnswer !== undefined &&
              userAnswer.trim().toLowerCase() === String(sq.correctAnswer).trim().toLowerCase()
          } else if (sq.type === 'essay') {
            return true
          } else if (sq.type === 'multiple') {
            const userAnswer = Array.isArray(subAns[idx]) ? subAns[idx].slice().sort() : []
            const correctAnswer = Array.isArray(sq.correctAnswer) ? sq.correctAnswer.slice().sort() : []
            return JSON.stringify(userAnswer) === JSON.stringify(correctAnswer)
          } else {
            return subAns[idx] === sq.correctAnswer
          }
        })
      }

      if (q.type === 'multiple') {
        return !(Array.isArray(a) &&
          Array.isArray(q.correctAnswer) &&
          a.length === q.correctAnswer.length &&
          a.every((v: any) => q.correctAnswer.includes(v)))
      }

      if (['fillblank', 'essay'].includes(q.type)) {
        return String(a).trim().toLowerCase() !== String(q.correctAnswer).trim().toLowerCase()
      }

      return a !== q.correctAnswer
    }).length
  )
  const accuracy = computed<number>(() =>
    totalQuestions.value > 0 ? Math.round((correctCount.value / totalQuestions.value) * 100) : 0
  )

  const displayOptions = computed<any[]>(() => {
    const opts = currentQuestion.value?.options
    return Array.isArray(opts) ? opts : []
  })

  return {
    // 响应式数据
    questions,
    currentQuestionIndex,
    selectedAnswer,
    answers,
    loading,
    // 「只刷错题」但没有可练错题时的说明（空串 = 不是这种情况）
    noWrongQuestionsReason,
    // 「没有题可练」的类型：noWrong（没错题）/ finished（本轮刷完）
    noQuestionsKind,
    // 清掉上面的空态标记（拿到题目时调用，见函数注释）
    clearNoQuestionsState,
    subFillBlankAnswers,
    subEssayAnswers,
    questionOffset,
    allQuestionsData,
    isResetting,
    favoritedQuestions,
    markedQuestions,
    errorQuestions,

    // 计算属性
    currentQuestion,
    totalQuestions,
    correctCount,
    wrongCount,
    accuracy,
    displayOptions,

    // 方法
    fetchQuestions,
    resetAndFetchQuestions,
    resetAnswers,
    goToQuestion,
    nextQuestion,
    prevQuestion,
    selectOption,
    selectSubOption,
    updateSubFillBlankAnswer,
    updateSubEssayAnswer,
    handleAnswerSubmission,
    resetPractice,
    // 「练完一轮」时清随机题单（下一轮重新随机）；由 PracticeComponent 在结算时调用
    clearRandomPlan,
    showAllAnalysis,
    viewResult,
    collectQuestion,
    markQuestion,
    addNote,
    reportQuestion,
    loadQuestionStatus,

    // ✅ 新增：导出的错题记录方法（可选）
    reportQuestionPractice,

    // 原有的导出函数
    transformQuestionForDisplay,
    processQuestions,
    applyQuestionLimits,
    loadBatchWithoutReset,
    fetchSingleQuestion,

    // 响应式更新方法
    updateOnlyWrong,
    updateQuestionCount,
    updateQuestionOffset,
    updateQuestionCountAndSlice,

    // 答题状态缓存方法
    saveCurrentAnswerState,
    restoreAnswerState,
    clearAnswerStateCache
  }
}
