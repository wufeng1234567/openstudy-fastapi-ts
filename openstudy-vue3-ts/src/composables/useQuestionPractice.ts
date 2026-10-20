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

  // 通用题目处理函数 - 现在可被外部调用
  async function processQuestions(data: any[]): Promise<void> {
    const count = questionCount.value
    // 判断是否需要打乱题目顺序：随机/模拟考试固定打乱，自定义练习根据 shuffleOptions 设置
    const moduleSettings = store.getModuleSettings(props.moduleType)
    const shouldShuffle = props.moduleType === 'random' || props.moduleType === 'mock' ||
                         (props.moduleType === 'custom' && moduleSettings.shuffleOptions)
    const offset = questionOffset.value

    // 调试日志：开始处理
    debugProcessStart(props.moduleType, data, { shouldShuffle, questionCount: count, offset })

    if (shouldShuffle) {
      // 检查缓存：如果已有乱序结果，直接使用
      const cacheKey = `${props.bankId}_${props.moduleType}`
      let shuffled: any[]

      const hasCache = shuffledCache.has(cacheKey)
      debugCacheCheck(props.moduleType, cacheKey, hasCache, hasCache ? shuffledCache.get(cacheKey) : null)

      if (hasCache) {
        // 使用缓存的乱序结果
        shuffled = shuffledCache.get(cacheKey) as any[]
      } else {
        // 首次进入，生成乱序并缓存
        shuffled = [...data]
        const beforeShuffle = [...shuffled]
        for (let i = shuffled.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
        }

        // 调试日志：打乱前后对比
        debugShuffle(props.moduleType, beforeShuffle, shuffled)
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
        proxy.$modal.msgInfo('已刷完所有题目')
        questions.value = []
        resetAnswers()
        loading.value = false
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
   * 「只刷错题」时把题目清空并给出**可执行的引导**
   *
   * ⚠️ 为什么需要它：没有错题时，原来只弹一条 `msgInfo` 然后留一个空白页面 ——
   * 用户不知道「是加载失败了」还是「本来就没题」。这里同时清状态 + 给文案，
   * 让「空」这件事是**说得清的**。
   */
  function clearForNoWrongQuestions(reason: string): void {
    questions.value = []
    allQuestionsData.value = []
    currentQuestionIndex.value = 0
    resetAnswers()
    loading.value = false
    noWrongQuestionsReason.value = reason
  }

  function applyQuestionLimits(options: { resetOffset?: boolean } = {}): void {
    if (allQuestionsData.value.length === 0) {
      resetAnswers()
      loading.value = false
      return
    }
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
      if (count === 'all') {
        questions.value = shuffled
      } else {
        questions.value = shuffled.slice(0, count as number)
      }
    } else if (offset >= allQuestionsData.value.length) {
      questions.value = []
      proxy.$modal.msgInfo('已刷完所有题目')
      resetAnswers()
      loading.value = false
      return
    } else if (count && count !== 'all' && typeof count === 'number' && count < allQuestionsData.value.length) {
      questions.value = allQuestionsData.value.slice(offset, offset + count)
    } else {
      questions.value = allQuestionsData.value
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

  function resetPractice(): void {
    questionOffset.value = 0
    resetAnswers()
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
