import { ref, watch } from 'vue'

/**
 * AI 出题的流式输出状态、深度思考跟随与等待计时。
 *
 * 从 QuestionBuilder.vue 抽出。返回的 ref / 函数仍以原名暴露给模板与其它 composable：
 * aiGenerating / aiThinking / aiThinkingOpen / thinkBoxRef / thinkAutoFollow /
 * onThinkScroll / aiWaitSeconds / restartWaitTimer / streamBoxRef /
 * generatedCount / pendingImportData / currentGeneratingType。
 */
export function useQuestionBuilderAiStream() {
  // AI 生成相关状态
  const aiGenerating = ref(false)
  /**
   * 深度思考的**实时正文**（2026-10-20）
   *
   * 来源是后端 `\x1e@@THINK@@…\x1e` 标记里的增量（见 `chat_engine.THINK_OPEN`），
   * 经 `generateQuestionsStreamFull` 的 `onThinking` 回调送达。
   *
   * ⚠️ 它**不是**题目内容，绝不能拼进 `rawJsonContent` ——
   *    那样 JSON 前面会多出一大段推理，解析必失败。
   */
  const aiThinking = ref('')
  /** 思考卡片是否展开：默认展开（用户要看"在动"），一旦出现正文就自动收起 */
  const aiThinkingOpen = ref(true)
  /** 思考内容容器：用于**自动滚到底**，否则用户只能看到最早那一屏 */
  const thinkBoxRef = ref<HTMLElement | null>(null)
  /**
   * 是否「自动跟随」思考流（2026-10-20）
   *
   * 用户口径：「滚动条会不断自动往下面压 用户鼠标无法自由控制滚动…
   *   要既可以让用户自由控制滚动条 又要保证用户滚动到底部可以一直看到最新输出」
   *
   * `true`  —— 新内容到达时自动滚到底（默认；首次开始思考时就是这种）
   * `false` —— 用户已经往上翻去看历史了，**绝不打扰他**，视图停在原处
   *
   * 状态由 `onThinkScroll` 根据"是否贴底"自动切换，用户不需要点任何按钮：
   * 滚到底 → 恢复跟随；往上翻 → 停止跟随。
   */
  const thinkAutoFollow = ref(true)
  /** 判定"贴底"的容差（px）：留 24px 是因为小数像素/行高取整会有 1-2px 误差，
   *  卡得太死会让"明明滚到底了却不跟随"的 bug 反复出现 */
  const THINK_STICKY_THRESHOLD = 24

  /**
   * 用户手动滚动思考区时的处理
   *
   * ⚠️ 这个函数是"自由控制"与"自动跟随"不打架的关键：
   *   只有它在用户手势后更新 `thinkAutoFollow`，
   *   程序性的 `scrollTop` 赋值也会触发 scroll 事件 —— 但那时算出来
   *   仍然是"贴底"，因此 `thinkAutoFollow` 保持 true，不会误判成"用户想停下"。
   */
  const onThinkScroll = () => {
    const el = thinkBoxRef.value
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    thinkAutoFollow.value = distanceToBottom <= THINK_STICKY_THRESHOLD
  }
  /**
   * 已等待秒数（2026-10-20）
   *
   * 模型推理启动约 2.5s（实测，本地也躲不掉 —— 是模型侧耗时，不是代理）。
   * 原来这段时间界面只有一行静态文字，用户无法判断"在等"还是"卡死"。
   * 显示秒数把"不确定的等待"变成"看得见的进度"。
   */
  const aiWaitSeconds = ref(0)
  let aiWaitTimer: ReturnType<typeof setInterval> | null = null

  /*
   * 等待计时器的收尾（2026-10-20）
   *
   * ⚠️ 用 watch 而不是在每个结束路径里手动 clearInterval：
   *    `aiGenerating.value = false` 在文件里有 **9 处**
   *    （成功 / 解析失败 / 格式错误 / onError / 外层 catch…），
   *    逐处加一行必然漏改 —— 漏掉的那条路径会让计时器永远在跑，
   *    下次打开弹窗秒数从上次的数值继续涨，看着像"卡了几百秒"。
   *
   *    监听状态本身，无论从哪条路结束都能收尾 —— 一处覆盖全部。
   *
   * ⚠️ 必须放在 `aiGenerating` 声明**之后**：
   *    watch 在 setup 阶段立即求值，放在声明前会命中 TDZ
   *    直接抛 ReferenceError 白屏，而 `vite build` **抓不到这类错误**。
   */
  watch(aiGenerating, (running) => {
    if (!running && aiWaitTimer) {
      clearInterval(aiWaitTimer)
      aiWaitTimer = null
    }
  })

  // 启动等待计时（原 SFC 里以内联闭包传给 useQuestionBuilderAiGenerate，逻辑原样搬到这里）
  const restartWaitTimer = () => {
    aiWaitSeconds.value = 0
    if (aiWaitTimer) clearInterval(aiWaitTimer)
    aiWaitTimer = setInterval(() => { aiWaitSeconds.value += 1 }, 1000)
  }

  const streamBoxRef = ref(null)
  const generatedCount = ref(0)
  const pendingImportData = ref<any>(null) // 暂存待导入的数据
  const currentGeneratingType = ref({ isComposite: false, questionType: 'single' })

  return {
    aiGenerating,
    aiThinking,
    aiThinkingOpen,
    thinkBoxRef,
    thinkAutoFollow,
    onThinkScroll,
    aiWaitSeconds,
    restartWaitTimer,
    streamBoxRef,
    generatedCount,
    pendingImportData,
    currentGeneratingType
  }
}
