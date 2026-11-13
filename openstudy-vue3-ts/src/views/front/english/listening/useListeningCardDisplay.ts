import { computed, ref } from 'vue'

/**
 * 听写卡片显示规则 / 练习结果展示状态（从 index.vue 原样抽出的纯状态辅助）。
 * 仅依赖调用方传入的 4 个 ref，不含 API、音频、定时器、路由等副作用。
 */
export function useListeningCardDisplay(options: {
  practiceWords: any
  currentIndex: any
  practiceMode: any
  audioContent: any
}) {
  const { practiceWords, currentIndex, practiceMode, audioContent } = options

    /** 本次练习用时（秒）—— 从点「开始听写」起算 */
    const practiceStartedAt = ref(0)
    const practiceElapsedSeconds = computed(() =>
        practiceStartedAt.value ? Math.max(0, Math.round((Date.now() - practiceStartedAt.value) / 1000)) : 0
    )

    /** 当前词书名（提交记录时带上，列表里能看出练的哪本） */
    const currentBookName = ref('')

    // 计算属性
    // ⚠️ `masteredCount` / `unmasteredCount` 已删除（2026-10-23）：
    //    `words` 表没有掌握状态列，这两个数只能是 0 和"全部"，属于假指标。

    const currentWord = computed(() => {
        return practiceWords.value[currentIndex.value] || null
    })

    const progressPercent = computed(() => {
        if (practiceWords.value.length === 0) return 0
        return Math.round(((currentIndex.value) / practiceWords.value.length) * 100)
    })

    /* ============================================================================
     * 屏幕显示规则（2026-10-26，跟随「播放内容」）
     *
     * 核心原则：**页面上不能出现用户要靠听才能得到的信息**，否则等于给答案。
     *
     *   播放内容   卡片显示                      为什么
     *   ─────────────────────────────────────────────────────────────────────
     *   zh（中文）  中文释义 + 音标               听中文写英文，题面就是那条中文
     *   en（英文）  **什么都不显示**（只一个 ?）   听英文拼写，中文和拼写都不能给
     *   both       中文释义                      先中文自测，英文靠听
     *
     * 另外：`listen`（纯听力）模式一律不显示 —— 用户是纸笔听写，
     * 任何提示都会削弱练习。
     * ========================================================================== */

    /** 卡片上是否显示中文释义 */
    const showChineseOnCard = computed(() => {
        if (practiceMode.value === 'listen') return false
        return audioContent.value !== 'en'
    })

    /**
     * 卡片上是否显示英文拼写
     *
     * ⚠️ 永远不显示。这是听写练习 —— 英文拼写就是要写出来的答案。
     *    这里显式写成一个恒 false 的变量而不是直接不写，
     *    是为了让"为什么没有英文"这个决定在代码里是可见的，
     *    以后想改成「答完再显示」时知道该动这里。
     */
    const showEnglishOnCard = computed(() => false)

    /** 卡片上是否显示音标 —— 只在播中文时给（音标能反推出拼写，播英文时不能给） */
    const showPhoneticOnCard = computed(() => {
        if (practiceMode.value === 'listen') return false
        return audioContent.value === 'zh'
    })

    /** 纯听力模式 / 播英文时的占位文案 */
    const cardPlaceholderHint = computed(() => {
        if (audioContent.value === 'en') return '听发音，写出这个单词'
        return '听发音，写出这个单词'
    })

  return {
    practiceStartedAt, practiceElapsedSeconds, currentBookName, currentWord, progressPercent,
    showChineseOnCard, showEnglishOnCard, showPhoneticOnCard, cardPlaceholderHint,
  }
}
