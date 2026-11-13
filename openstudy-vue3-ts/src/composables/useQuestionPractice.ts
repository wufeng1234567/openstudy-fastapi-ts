import { ref, computed, nextTick } from 'vue'
import type { Ref, ComputedRef } from 'vue'
import {
  listQuestionMainAll,
  getQuestionMain,
  recordStudyTime,
  reportPractice,
  startPracticeSession,
  answerPracticeSession,
  submitPracticeSession
} from '@/api/questionMain/questionMain'
// 修改导入，添加新的API方法
import { listQuestionErrorAll, batchCheckError } from '@/api/questionError/questionError'
import { addFavoriteQuestion, deleteFavoriteQuestionByUserAndQuestion, batchCheckFavorite } from '@/api/favoriteQuestion/favoriteQuestion'
import { addQuestionMarked, deleteMarkedByUserAndQuestion, batchCheckMarked } from '@/api/questionMarked/questionMarked'
import useUserStore from '@/store/modules/user'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import type { TransformedQuestion } from '@/types'

/*
 * ── 抽离出去的**纯逻辑**模块（2026-11 可读性重构）────────────────────
 *
 * 本文件只留**练习状态机**（取题 → 转换 → 切片 → 作答 → 提交）与响应式状态；
 * 下列模块都是无副作用的纯函数，可以独立理解与复用：
 *   · `./questionPracticeTransform`  —— 原始题目 → `TransformedQuestion` 的转换规则
 *   · `./questionPracticeAnswer`     —— 判分写回 / 答案格式化 / 错因备注与标签
 *   · `./questionPracticeRandomPlan` —— 随机题单的持久化与「新题优先」算法
 *
 * ⚠️ 依赖方向单向（本文件 → 上面三个），它们**不反向依赖**本文件，
 *    因此不会形成循环依赖。
 */
import {
  toDisplayQuestions,
  transformQuestionForDisplay
} from './questionPracticeTransform'
import {
  applyServerGrade,
  generateErrorNote,
  generateErrorTags,
  hasAnswerValue,
  stringifyAnswerForLog
} from './questionPracticeAnswer'
import {
  buildRandomPlan,
  loadRandomPlan,
  clearRandomPlan as clearStoredRandomPlan
} from './questionPracticeRandomPlan'
import {
  computeSliceWindow,
  isAnswerCorrect,
  isCompositeAnswered,
  isCompositeType,
  toggleSelection
} from './questionPracticeRules'

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
   * 服务端练习会话（判分/成绩的权威来源）。
   * 每次题目批次变化时新建；同一批题反复作答不会重复建会话。
   */
  const practiceSessionId = ref<string>('')
  const practiceSessionSignature = ref<string>('')
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

  /**
   * 为当前页面的题目批次创建服务端会话。
   *
   * 为什么不把整库所有题都塞进一个会话：练习页按「每次 N 题 / 只刷错题」切片，
   * 若会话包含全库，交卷时未展示的题会被算成未答，成绩失真。
   * 因此以 `questions.value`（当前实际展示的题单）为准，题单变化即重建会话。
   */
  async function ensurePracticeSession(): Promise<boolean> {
    const ids = (questions.value || [])
      .map((q: any) => Number(q?.id))
      .filter((id) => Number.isFinite(id) && id > 0)
    if (!ids.length || !props.bankId) return false
    // 模拟考试会话由 PracticeComponent 带着分值快照创建，绝不能被这里的
    // 「顺序练习」默认会话覆盖（否则 _mockScore 丢失、交卷满分错误）。
    if (props.moduleType === 'mock' && practiceSessionId.value) return true
    const signature = `${props.bankId}:${ids.join(',')}`
    if (practiceSessionId.value && practiceSessionSignature.value === signature) return true
    try {
      const res: any = await startPracticeSession({
        bankId: Number(props.bankId),
        moduleType: props.moduleType || 'sequential',
        questionIds: ids
      })
      if (res?.code === 200 && res?.data?.sessionId) {
        practiceSessionId.value = String(res.data.sessionId)
        practiceSessionSignature.value = signature
        return true
      }
      console.warn('[practice] 创建服务端会话失败', res?.msg || res)
    } catch (e) {
      console.warn('[practice] 创建服务端会话异常', e)
    }
    return false
  }

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

  /**
   * 清掉随机题单（对外入口）
   *
   * ⚠️ 对外签名保持**零参数**：`PracticeComponent` 与 `usePracticeSubmitAction`
   *    按 `clearRandomPlan: () => void` 用，签名不能变。
   *    存储键的算法留在本文件（依赖 `userStore.id` / `props`），
   *    真正落盘的活儿在 `./questionPracticeRandomPlan`。
   */
  const clearRandomPlan = (): void => {
    clearStoredRandomPlan(randomPlanKey())
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
    // 判断是否需要打乱题目顺序：随机练习固定打乱，自定义练习根据 shuffleOptions 设置
    const moduleSettings = store.getModuleSettings(props.moduleType)
    /*
     * ⚠️⚠️ 模拟考试**必须**排除在这个分支之外（2026-10-22 修的 bug）。
     *
     * 现象（用户口径）：在考试配置页设了「单选 5 道 × 2 分」，
     * 开考后卷子里却是 2 道问答题 + 2 道填空题 + 1 道单选，满分显示 0。
     *
     * 根因：`mock` 原来和 `random` 共用这条分支，于是走进
     *   `loadRandomPlan(data, count)` —— 它会把**上一次随机练习留在
     *   localStorage 里的题单**按 id 还原出来，组卷方辛苦抽好的卷子被整份丢弃。
     *   而这张还原出来的题单里的题目是后端原始对象（没有 `_mockScore`），
     *   所以每道题分值都算成 0 → 满分 0 → `0 >= 0` 被判及格。
     *
     * 两者的"乱序"只是字面相似，语义完全不同：
     *   · 随机练习：题单要**跨会话稳定**（换页/刷新都还是这批题）；
     *   · 模拟考试：每次开考都是**一张新卷子**，绝不该复用上一场的题单。
     */
    const shouldShuffle = props.moduleType === 'random' ||
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
        const planned = loadRandomPlan(data, count, randomPlanKey())
        shuffled = planned || buildRandomPlan(data, count, randomPlanKey(), lastRoundKey())
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
      await ensurePracticeSession()
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
      await ensurePracticeSession()
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
      await ensurePracticeSession()
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
      if (isCompositeType(q.type)) {
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
    const win = computeSliceWindow(allQuestionsData.value.length, newCount, questionOffset.value)
    questionOffset.value = win.offset

    // 从 allQuestionsData 中重新切片
    const newData = allQuestionsData.value.slice(win.sliceStart, win.sliceEnd)

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
      if (isCompositeType(q.type)) {
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
      if (isCompositeType(q.type)) {
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

  // 新增：重置所有数据并重新加载题目（用于模式切换）
  // 保存当前答题状态到缓存
  // moduleType 参数可选，用于在模式切换时指定旧的 moduleType
  /**
   * 把当前作答状态写进会话内缓存
   *
   * @param moduleType 显式指定 key 里的模块名（不传则用 `props.moduleType`）
   * @param bankIdOverride 显式指定 key 里的题库 id（不传则用 `props.bankId`）
   *
   * ⚠️ `bankIdOverride` 是为**切换题库**这个场景加的（2026-10-22）：
   *    Vue 的 `watch(() => props.bankId, (newId, oldId) => ...)` 回调里，
   *    `props.bankId` **已经是新题库**了。此时若无脑调用本函数，
   *    就会把「旧题库的题目」写进「新题库的缓存 key」——
   *    下一次进新题库，`restoreAnswerState()` 会把旧题目恢复出来，
   *    等于把「切题库串题」这个 bug 换了个地方复现，而且更难查。
   *    所以调用方必须把 `oldId` 明传进来。
   */
  function saveCurrentAnswerState(moduleType?: string, bankIdOverride?: number | string): void {
    // 如果 moduleType 显式传入且为 undefined，说明是路由过渡，不保存
    if (moduleType === undefined) {
      // 路由过渡状态，跳过保存
      return
    }
    const type = moduleType || props.moduleType
    const bankId = bankIdOverride ?? props.bankId
    if (!bankId || !type || questions.value.length === 0) return

    const cacheKey = `${bankId}_${type}`
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
  /**
   * 保存旧状态 → 清空 → 尝试从缓存恢复 → 没有缓存就重新拉题
   *
   * @param oldModuleType 旧模块名（切换模块时传，用于把旧状态的 key 写对）
   * @param oldBankId 旧题库 id（**切换题库时必传**，理由见 `saveCurrentAnswerState` 的注释）
   */
  function resetAndFetchQuestions(oldModuleType?: string, oldBankId?: number | string): void {
    // 调试日志
    debugResetAndFetch(props.moduleType, props.bankId)

    // 先保存当前答题状态（使用旧的 moduleType / bankId 作为 key）
    if (oldBankId !== undefined) {
      saveCurrentAnswerState(oldModuleType, oldBankId)
    } else {
      saveCurrentAnswerState(oldModuleType)
    }

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
        status: "0",
        // 练习入口不拿答案/解析；判分与参考答析由服务端会话在作答后返回
        withAnswer: false
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

      await processQuestions(data)
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
        status: "0",
        withAnswer: false
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

      await processQuestions(data)
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
      if (isCompositeType(q.type)) {
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
    if (currentIndex !== index && currentQ && !isCompositeType(currentQ.type) && selectedAnswer.value !== null && answers.value[currentIndex] === null) {
      handleAnswerSubmission(currentIndex)
    }

    currentQuestionIndex.value = index
    const q = questions.value[index]
    const ans = answers.value[index]

    // 对于阅读理解或完形填空，重置 selectedAnswer 并同步子题答案
    if (isCompositeType(q?.type)) {
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
      let isCorrect = isAnswerCorrect(q.type, ans, q.correctAnswer)
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
      selectedAnswer.value = toggleSelection(arr, index)
    } else if (['single', 'truefalse'].includes(type)) {
      selectedAnswer.value = index
    }
  }

  function selectSubOption(subIndex: number, optionIndex: number): void {
    const currentQ = currentQuestion.value
    if (!currentQ || !isCompositeType(currentQ.type)) return
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
    if (!currentQ || !isCompositeType(currentQ.type)) {
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
    if (!currentQ || !isCompositeType(currentQ.type)) {
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
    if (!q || !isCompositeType(q.type)) return

    const allAnswered = isCompositeAnswered(q.subQuestions, ans)
    q.answered = allAnswered
  }

  // ✅ 修复：handleAnswerSubmission 函数 - 完整版
  /**
   * 作答提交：只把用户答案发给服务端，判分/参考答案/解析全部由服务端返回。
   *
   * 旧实现直接拿 `q.correctAnswer` 在前端比对，题目接口又明文下发答案，
   * 等于「答案在客户端、判分也在客户端」。现在答案不在初始题目里，
   * 只有本题作答后服务端才会返回 `correctAnswer/analysis`。
   */
  async function handleAnswerSubmission(qIndex: number): Promise<void> {
    if (submissionLock.value) return
    const q = questions.value[qIndex]
    if (!q) return

    const composite = isCompositeType(q.type)
    const answer = composite ? answers.value[qIndex] : (answers.value[qIndex] ?? selectedAnswer.value)
    if (!hasAnswerValue(answer)) return

    submissionLock.value = true
    try {
      if (!practiceSessionId.value) {
        const ok = await ensurePracticeSession()
        if (!ok) {
          proxy.$modal.msgError('练习会话创建失败，请刷新后重试')
          return
        }
      }
      const res: any = await answerPracticeSession(practiceSessionId.value, q.id, answer)
      if (res?.code !== 200) {
        proxy.$modal.msgError(res?.msg || '服务端判分失败，请重试')
        return
      }
      answers.value[qIndex] = answer
      applyServerGrade(q, res.data || {})
      if (!composite) selectedAnswer.value = answer
      if ((q as any).pending) {
        proxy.$modal.msgInfo('简答题已保存，参考答案待你自评')
      }
    } catch (e: any) {
      console.warn('[practice] 服务端判分异常', e)
      proxy.$modal.msgError('服务端判分失败，请检查网络后重试')
    } finally {
      setTimeout(() => { submissionLock.value = false }, 100)
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
    practiceSessionId.value = ''
    practiceSessionSignature.value = ''
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
  const gradedQuestions = computed(() =>
    questions.value.filter((q: any) => q.answered && !q.pending)
  )
  const correctCount = computed<number>(() => gradedQuestions.value.filter((q: any) => q.correct === true).length)
  const wrongCount = computed<number>(() => gradedQuestions.value.filter((q: any) => q.correct !== true).length)
  const pendingCount = computed<number>(() => questions.value.filter((q: any) => q.answered && q.pending).length)
  const accuracy = computed<number>(() =>
    gradedQuestions.value.length > 0
      ? Math.round((correctCount.value / gradedQuestions.value.length) * 100)
      : 0
  )

  /*
   * 选项乱序的实际实现在 `QuestionDisplay.vue`（2026-10-22）
   * ==========================================================================
   * ⚠️ 这里**刻意保持原样**（原样返回 options），不做打乱。原因：
   *
   *   真正渲染选项的组件是 `QuestionDisplay`，它有**自己的** `displayOptions`，
   *   并且用"显示下标"去判断选中态、发射 `select-option`。
   *   如果在这里先打乱，`QuestionDisplay` 会把它当成"原始顺序"再渲染一遍，
   *   于是下标与 `answers` 里存的原始下标错位 —— 选中态会跳到别的选项上。
   *
   *   正确的分工：
   *     · 本 composable 负责**答案**（存原始下标，永不因显示顺序变化而改）；
   *     · `QuestionDisplay` 负责**显示顺序**（打乱后用 `_origin` 映射回原始下标）。
   *   两边各管一件事，就不会错位。
   */
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
    // 服务端练习会话（结算时用它提交成绩）
    practiceSessionId,
    ensurePracticeSession,
    applyServerGrade,
    pendingCount,

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
