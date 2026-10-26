<template>
    <div class="listening-page">
        <!--
          2026-10-26：整行「< 返回」导航栏已删除。
          顶栏已经显示 `英语学习 · 单词听写`，页面层级清晰，
          再来一行返回栏只是重复占位（用户反馈「第二行多余了」）。
          练习中的「结束练习」按钮仍可退出，返回逻辑保留在 `goBack()` 里备用。
        -->
        <!--
          练习结果面板（2026-10-26 闭环）
          --------------------------------
          改前：练完弹一个 ElMessageBox（只有 4 个数字），点「返回」就丢光了。
          改后：结果留在页面里，能看到**具体写错了哪些词**，并给出三个出口。
        -->
        <div class="result-panel" v-if="hasResult && !isPracticing">
            <div class="result-panel__head">
                <div class="result-panel__score">
                    <span class="result-panel__pct">{{ resultSummary.accuracy }}<i>%</i></span>
                    <span class="result-panel__label">本次正确率</span>
                </div>
                <div class="result-panel__nums">
                    <span>共 {{ resultSummary.total }} 题</span>
                    <span class="is-ok">对 {{ resultSummary.correct }}</span>
                    <span class="is-bad">错 {{ resultSummary.total - resultSummary.correct }}</span>
                </div>
            </div>

            <div class="result-panel__wrong" v-if="resultWrongWords.length">
                <div class="result-panel__wrong-title">
                    写错的 {{ resultWrongWords.length }} 个词
                </div>
                <div class="wrong-list">
                    <div v-for="(w, i) in resultWrongWords" :key="i" class="wrong-item">
                        <span class="wrong-item__word">{{ w.word }}</span>
                        <span class="wrong-item__trans">{{ w.translation }}</span>
                        <span class="wrong-item__mine">你写的是：{{ w.userAnswer || '（空）' }}</span>
                    </div>
                </div>
            </div>
            <div class="result-panel__allok" v-else>
                <el-icon :size="20"><CircleCheck /></el-icon>
                <span>全部写对了，这本词库掌握得不错</span>
            </div>

            <div class="result-panel__actions">
                <el-button
                    v-if="resultWrongWords.length"
                    type="primary"
                    size="large"
                    @click="retryWrongWords"
                >
                    再练一遍错词（{{ resultWrongWords.length }}）
                </el-button>
                <el-button size="large" @click="backToBookSelect">换一本词库</el-button>
                <el-button size="large" text @click="router.push('/front/english/vocabulary')">
                    去我的词库
                </el-button>
            </div>

            <!--
              把这次练习交给智能体分析：跳过去时把问题带在 route state 里，
              智能体的 `english_practice` 工具能读到刚提交的这条记录，
              于是"页面练完 → 聊天里复盘"也接上了。
            -->
            <p class="result-panel__ai">
                想让 AI 帮你看看这次练习？
                <a class="result-panel__link" @click="askAiForAnalysis">交给智能体分析</a>
            </p>
        </div>

        <!-- 词库选择（未开始时显示） -->
        <div class="book-select-section" v-if="!isPracticing && !hasResult">
            <div class="select-label">选择词库</div>
            <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" style="width: 100%"
                @change="onBookChange">
                <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName" :value="book.bookId" />
            </el-select>

            <!--
              2026-10-26 新增：未选词库时的空状态。
              改前这里什么都没有 —— 整页只有一个下拉框，下方全空，
              用户不知道下一步该干什么。现在给出明确指引。
            -->
            <div class="start-empty" v-if="!selectedBookId">
                <div class="start-empty__icon">
                    <el-icon :size="26">
                        <Headset />
                    </el-icon>
                </div>
                <p class="start-empty__title">先选一本词库</p>
                <span class="start-empty__desc">
                    选好后点「开始听写」，系统会念中文释义，你拼出对应的英文单词
                </span>
            </div>

            <div class="start-empty" v-else-if="wordList.length === 0 && !loadingWords">
                <div class="start-empty__icon">
                    <el-icon :size="26">
                        <Collection />
                    </el-icon>
                </div>
                <p class="start-empty__title">这本词库还是空的</p>
                <span class="start-empty__desc">先去「我的词库」往里加几个单词，再回来听写</span>
                <el-button class="start-empty__btn" size="small" @click="router.push('/front/english/vocabulary')">
                    去添加单词
                </el-button>
            </div>

            <!-- 词库统计 -->
            <!--
              只说「总单词」。
              原来还有「已掌握 / 未掌握」两项，但 `words` 表根本没有掌握状态列
              （word_id / book_id / word / phonetic / translation / example /
                audio_url / sort_order / create_time），那两个数字永远是
              0 和全部 —— 等于给用户看两个假指标。2026-10-23 去掉。
            -->
            <div class="book-stats" v-if="selectedBookId && wordList.length > 0">
                <div class="stat-item">
                    <span class="stat-value">{{ wordList.length }}</span>
                    <span class="stat-label">总单词</span>
                </div>
            </div>

            <!--
              练习设置（2026-10-26 重排）
              -----------------------------------------------------------------
              改前两处结构/排版问题（截图实测）：
                ① 「练习模式」的 `.setting-item` 被**错误嵌套在「播放顺序」里面** ——
                   「播放顺序」是 flex 行，于是「练习模式」这个标签和两个单选框
                   直接压到「随机」右边，和它重叠在一起；
                ② 「播放间隔」一行塞了 2 个滑块 + 1 个标签 + 1 句提示，
                   宽度不够时全部挤成一团。

              改后：
                · 修正嵌套，每个设置项独立成行；
                · 统一「左标签 96px + 右控件」的两列网格，各行左边缘对齐；
                · 滑块行拆成「标签 / 滑块 / 提示」三栏，提示换到滑块下方；
                · 「自动下一题间隔」只在听写模式下才有意义，顺手也用同一个网格。
            -->
            <div class="practice-settings" v-if="selectedBookId && wordList.length > 0">
                <div class="setting-item">
                    <span class="setting-label">练习范围</span>
                    <el-radio-group v-model="practiceRange">
                        <el-radio value="all">全部单词</el-radio>
                    </el-radio-group>
                </div>

                <div class="setting-item">
                    <span class="setting-label">播放顺序</span>
                    <el-radio-group v-model="playOrder">
                        <el-radio value="sequential">顺序</el-radio>
                        <el-radio value="random">随机</el-radio>
                    </el-radio-group>
                </div>

                <div class="setting-item">
                    <span class="setting-label">练习模式</span>
                    <el-radio-group v-model="practiceMode">
                        <el-radio value="input">输入模式</el-radio>
                        <el-radio value="dictation">听写模式</el-radio>
                    </el-radio-group>
                </div>

                <div class="setting-item">
                    <span class="setting-label">播放次数</span>
                    <el-radio-group v-model="repeatCount">
                        <el-radio :value="1">1次</el-radio>
                        <el-radio :value="2">2次</el-radio>
                        <el-radio :value="3">3次</el-radio>
                    </el-radio-group>
                </div>

                <!-- 以下两项只在「听写模式」下出现 -->
                <div class="setting-item setting-item--slider" v-if="practiceMode === 'dictation'">
                    <span class="setting-label">播放间隔</span>
                    <div class="setting-control">
                        <el-slider v-model="playInterval" :min="1" :max="5" :step="0.5" show-stops
                            :format-tooltip="(val) => val + '秒'" />
                    </div>
                </div>

                <div class="setting-item setting-item--slider" v-if="practiceMode === 'dictation'">
                    <span class="setting-label">自动下一题</span>
                    <div class="setting-control">
                        <el-slider v-model="autoNextInterval" :min="1" :max="10" :step="0.5" show-stops
                            :format-tooltip="(val) => val + '秒'" />
                        <span class="setting-hint">播放完成后等待此时间自动进入下一题</span>
                    </div>
                </div>
            </div>

            <!-- 开始按钮 -->
            <div class="start-section" v-if="selectedBookId && wordList.length > 0">
                <el-button type="primary" size="large" @click="startPractice" :loading="loadingWords">
                    <el-icon>
                        <VideoPlay />
                    </el-icon>
                    开始听写
                </el-button>
            </div>

            <!-- 空状态 -->
            <el-empty v-else-if="selectedBookId && wordList.length === 0 && !loadingWords"
                description="该词库还没有单词，请先添加单词" />
        </div>

        <!--
          练习界面
          ⚠️ 2026-10-26：加上 `!hasResult`。
          原来这里是裸 `v-else`，接在 `book-select-section`（`!isPracticing && !hasResult`）
          后面，所以当 `isPracticing=false` 且 `hasResult=true` 时，
          它仍然成立 —— 结果面板和题目卡会同时渲染（截图实测叠在一起）。
        -->
        <div class="practice-section" v-else-if="!hasResult">
            <!-- 进度条 -->
            <div class="progress-bar">
                <div class="progress-text">{{ currentIndex + 1 }} / {{ practiceWords.length }}</div>
                <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
            </div>

            <!-- 当前单词卡片 -->
            <div class="word-card">
                <!-- ⚠️ 后端字段是 `translation` / `word`，不是 `chinese` / `english`（2026-10-23 修） -->
                <div class="word-chinese">{{ currentWord?.translation || '' }}</div>
                <div class="word-phonetic" v-if="currentWord?.phonetic">{{ currentWord.phonetic }}</div>

                <!-- 播放按钮 -->
                <!--
                  ⚠️ 2026-10-23 修：原来是 `:loading="isPlaying"`。
                      Element Plus 的 button 在 loading 时会**同时置 disabled**，
                      并且 `handleClick` 里 `if (props.loading) { evt.stopPropagation(); return }`
                      —— 也就是说只要 `isPlaying` 卡在 true，这个按钮就永久点不动，
                      表现正是「点击没反应」。
                      现在去掉 loading，只用图标在 播放/暂停 之间切换：
                      按钮始终可点，用户可以随时重播或打断。
                -->
                <div class="play-section">
                    <el-button type="primary" circle size="large"
                        @click="practiceMode === 'dictation' ? startDictationRound() : playCurrentWord()"
                        class="play-btn" :disabled="isWaitingAutoNext">
                        <el-icon :size="28">
                            <VideoPlay v-if="!isPlaying" />
                            <VideoPause v-else />
                        </el-icon>
                    </el-button>
                    <span class="play-hint" v-if="practiceMode === 'input'">点击播放中文发音</span>
                    <span class="play-hint" v-else>
                        <span v-if="isPlaying">
                            正在播放第 {{ currentPlayCount }}/{{ repeatCount }} 遍...
                        </span>
                        <span v-else-if="isWaitingAutoNext">
                            ⏳ {{ autoNextCountdown }}秒后自动下一题 <!-- ✅ 已经是整数 -->
                        </span>
                        <span v-else>
                            点击重新播放
                        </span>
                    </span>
                </div>

                <!-- 输入区域 -->
                <div class="input-section">
                    <el-input ref="inputRef" v-model="userAnswer" placeholder="请输入英文单词..." size="large" clearable
                        @keyup.enter="submitAnswer" :disabled="isCorrect || isWrong">
                        <template #suffix>
                            <el-button type="primary" @click="submitAnswer"
                                :disabled="!userAnswer.trim() || isCorrect || isWrong">
                                提交
                            </el-button>
                        </template>
                    </el-input>
                </div>

                <!-- 结果反馈 -->
                <div class="feedback-section" v-if="showFeedback">
                    <div :class="['feedback-card', isCorrect ? 'correct' : 'wrong']">
                        <div class="feedback-icon">
                            <el-icon :size="32">
                                <CircleCheck v-if="isCorrect" />
                                <CircleClose v-else />
                            </el-icon>
                        </div>
                        <div class="feedback-content">
                            <div class="correct-answer">
                                <span class="label">正确答案：</span>
                                <span class="value">{{ currentWord.word }}</span>
                            </div>
                            <div class="your-answer" v-if="!isCorrect">
                                <span class="label">你的答案：</span>
                                <span class="value">{{ userAnswer }}</span>
                            </div>
                            <div class="word-meaning">
                                <span class="label">释义：</span>
                                <span class="value">{{ currentWord.translation }}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 操作按钮 -->
            <div class="action-buttons">
                <el-button v-if="practiceMode === 'input' && showFeedback" type="primary" size="large"
                    @click="nextWord">
                    下一题
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </el-button>
                <el-button v-if="practiceMode === 'dictation' && !isWaitingAutoNext" type="primary" size="large"
                    @click="autoNextWord">
                    下一题
                    <el-icon>
                        <ArrowRight />
                    </el-icon>
                </el-button>
                <el-button v-if="practiceMode === 'input' && !showFeedback" type="info" size="large" @click="skipWord">
                    跳过
                </el-button>
                <el-button type="danger" plain size="large" @click="stopPractice">
                    结束练习
                </el-button>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontEnglishListening' })
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
    ArrowLeft, VideoPlay, VideoPause, ArrowRight,
    CircleCheck, CircleClose, Headset, Collection
} from '@element-plus/icons-vue'
import { listFrontWordBooks } from '@/api/wordBooks/wordBooks'
import { listAllWords, submitPractice } from '@/api/words/words'
import { ElMessage, ElMessageBox } from 'element-plus'
import { speak, stopSpeak, speakReasonText, warmUpVoices, unlockAudio } from '@/utils/speech'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const cacheStore = useFrontPageCacheStore()

// 状态
const isPracticing = ref(false)
const loadingWords = ref(false)

// 练习模式：input-输入模式，dictation-听写模式
const practiceMode = ref('input')
// 自动下一题间隔（秒）
const autoNextInterval = ref(3)
// 自动下一题定时器
let autoNextTimer = null
// 是否正在等待自动下一题
const isWaitingAutoNext = ref(false)
// 当前播放进度（第几次播放）
const currentPlayCount = ref(0)

// 词库相关
const bookOptions = ref([])
const selectedBookId = ref(null)
const wordList = ref([])

// 练习设置
const practiceRange = ref('all')
const playOrder = ref('random')
const repeatCount = ref(2)
const playInterval = ref(2)

// 练习状态
const practiceWords = ref([])
const currentIndex = ref(0)
const userAnswer = ref('')
const showFeedback = ref(false)
const isCorrect = ref(false)
const isWrong = ref(false)
const isPlaying = ref(false)




// 输入框引用
const inputRef = ref(null)

// ==================== 语音合成（Web Speech API） ====================
// 2026-10-23 改：原来这一页自己手写 `speechSynthesis.speak()`，踩了三个坑，
// 表现就是「点了没声音 / 点了没反应」。现在统一走 @/utils/speech：
//
//   ① `cancel()` 后立刻 `speak()` 会被 Chrome 静默丢弃（不报错、不触发 onend）
//      —— 原代码每次播放前都 cancel()，于是「第一次能响，之后点就哑了」。
//   ② `onerror` 一律 `() => resolve()`，缺语音包 / 被策略拦下全被吞掉，
//      用户永远不知道为什么没声音。
//   ③ 没有任何超时。引擎卡住时 `isPlaying` 永远是 true，而播放按钮是
//      `:loading="isPlaying"`，Element Plus 的 loading 会同时变成 disabled
//      并在 handleClick 里直接 return —— 按钮就**永久点不动**了。
//
// 具体细节见 `src/utils/speech.ts` 顶部注释。

// 统计
const practiceResults = ref([])

/* ============================================================================
 * 练习结果面板状态（2026-10-26 闭环）
 *
 * 改前练完只弹一个 ElMessageBox，关掉就什么都不剩。
 * 现在结果留在页面里，用户可以：
 *   · 看到本次写错的具体单词（不是只给个数字）
 *   · 点「再练一遍错词」只练这几个
 *   · 去词库 / 让 AI 分析这次练习
 * ========================================================================== */
const hasResult = ref(false)
const resultSummary = ref({ total: 0, correct: 0, accuracy: 0 })
const resultWrongWords = ref<Array<{ word: string; translation: string; userAnswer: string }>>([])

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

// 加载词库选项
const loadBookOptions = async () => {
    try {
        // ⚠️ 2026-10-23 修「加词库 422」：
        //    原来传 `pageSize: 100` 给 `/wordBooks/wordBooks/list` —— 那个接口上限就是 100，
        //    刚好卡在边界上没问题；但换个写法（>100）立刻 422。
        //    这里统一用 `listFrontWordBooks`（内部按 100 翻页取全量），不再依赖调用方算上限。
        //    另外 `userId` 后端不收（归属由登录态决定），传了也会被忽略，已去掉。
        const response = await listFrontWordBooks()
        if (response.code === 200) {
            bookOptions.value = response.rows || []
        } else {
            ElMessage.error(response.msg || '加载词库失败')
        }
    } catch (error) {
        console.error('加载词库失败:', error)
        ElMessage.error('加载词库失败')
    }
}

// 词库切换
const onBookChange = async (bookId) => {
    if (!bookId) return
    loadingWords.value = true
    // 记住书名：提交练习记录时要带上，列表里才看得出练的哪本
    currentBookName.value =
        String(bookOptions.value.find((b) => b.bookId === bookId)?.bookName || '')
    try {
        // ⚠️ 后端参数名是 `bookId`
        //
        // ⚠️ 2026-10-23 修「加载单词 422」：
        //    原来 `pageSize: 1000`，后端 `le=200` 是硬上限 → FastAPI 直接 HTTP 422，
        //    单词永远加载不出来（页面只会显示"该词库还没有单词"）。
        //    听写要练的就是**整本书**，所以用 listAllWords（内部翻页取完）。
        const response = await listAllWords({ bookId: bookId })
        if (response.code === 200) {
            wordList.value = response.rows || []
        } else {
            ElMessage.error(response.msg || '加载单词失败')
        }
    } catch (error) {
        console.error('加载单词失败:', error)
        ElMessage.error('加载单词失败')
    } finally {
        loadingWords.value = false
    }
}

// 开始练习
const startPractice = () => {
    // ⚠️ `words` 表没有 isMastered 列，原先按「未掌握」筛选永远为空。
    //    现在不做这个筛选：练的就是这本词库里的全部单词。
    let words = [...wordList.value]

    if (words.length === 0) {
        ElMessage.warning('没有可练习的单词')
        return
    }

    // 随机打乱
    if (playOrder.value === 'random') {
        words = shuffleArray(words)
    }

    practiceWords.value = words
    currentIndex.value = 0
    isPracticing.value = true
    practiceResults.value = []
    userAnswer.value = ''
    showFeedback.value = false
    isCorrect.value = false
    isWrong.value = false
    isWaitingAutoNext.value = false
    currentPlayCount.value = 0

    // 2026-10-26：清掉上一轮的结果面板，开始计时（提交记录时要报用时）
    hasResult.value = false
    resultWrongWords.value = []
    resultSummary.value = { total: 0, correct: 0, accuracy: 0 }
    practiceSubmitted.value = false
    practiceStartedAt.value = Date.now()

    // 清除之前的定时器
    clearAutoNextTimer()

    // 自动播放第一个单词
    nextTick(() => {
        if (practiceMode.value === 'dictation') {
            // 听写模式：自动开始播放
            startDictationRound()
        } else {
            // 输入模式：手动点击播放
            playCurrentWord()
        }
    })
}

// ==================== 听写模式播放 ====================
/**
 * 开始一轮听写播放
 * 听写模式下：播放 N 遍中文发音，每遍间隔 playInterval 秒
 * 播放完成后启动自动下一题倒计时
 *
 * 2026-10-23 改：
 *  · 失败时会提示原因，而不是「看着转圈、没有声音、然后自动跳到下一题」；
 *  · `isPlaying` 由 try/finally 兜底，异常不会把播放按钮永久锁死；
 *  · 播放失败**不再**自动进入下一题 —— 那样用户会眼睁睁看着题目一题题跳过，
 *    却不知道为什么每个都没声音。
 */
const startDictationRound = async () => {
    if (!currentWord.value) return

    // 清除之前的定时器
    clearAutoNextTimer()
    isWaitingAutoNext.value = false

    const word = currentWord.value
    const chinese = word.translation

    if (!chinese) {
        ElMessage.warning('该单词没有中文释义')
        autoNextWord()
        return
    }

    // 标记为已练习
    if (!word.practiced) {
        word.practiced = true
    }

    // 播放中文
    isPlaying.value = true
    currentPlayCount.value = 0

    try {
        for (let i = 0; i < repeatCount.value; i++) {
            currentPlayCount.value = i + 1
            const res = await speakChinesePromise(chinese)
            if (res && res.ok === false) {
                if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
                    ElMessage.warning(speakReasonText(res.reason, 'zh-CN'))
                }
                return
            }
            if (i < repeatCount.value - 1) {
                await sleep(playInterval.value * 1000)
            }
        }

        // 播放完成后，等待自动下一题
        startAutoNextCountdown()
    } finally {
        isPlaying.value = false
        currentPlayCount.value = 0
    }
}


// 倒计时显示
const autoNextCountdown = ref(0)
let countdownInterval = null

// 开始自动下一题倒计时
// 开始自动下一题倒计时（带显示）
const startAutoNextCountdown = () => {
    isWaitingAutoNext.value = true
    autoNextCountdown.value = Math.ceil(autoNextInterval.value)  // ✅ 向上取整

    // 每秒更新倒计时显示
    countdownInterval = setInterval(() => {
        if (autoNextCountdown.value > 0) {
            autoNextCountdown.value--
        }
        if (autoNextCountdown.value <= 0) {
            clearInterval(countdownInterval)
            countdownInterval = null
        }
    }, 1000)  // ✅ 改为每秒更新

    autoNextTimer = setTimeout(() => {
        clearInterval(countdownInterval)
        countdownInterval = null
        isWaitingAutoNext.value = false
        autoNextWord()
    }, autoNextInterval.value * 1000)
}




// 自动进入下一题
const autoNextWord = () => {
    clearAutoNextTimer()

    // 记录当前单词为已完成（跳过，因为没输入答案）
    if (practiceMode.value === 'dictation') {
        practiceResults.value.push({
            wordId: currentWord.value.wordId,
            word: currentWord.value,
            userAnswer: '',
            isCorrect: false,
            skipped: true,
            mode: 'dictation'
        })
    }

    if (currentIndex.value < practiceWords.value.length - 1) {
        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false
        isWaitingAutoNext.value = false

        nextTick(() => {
            startDictationRound()
        })
    } else {
        // 练习完成
        isPracticing.value = false
        showPracticeResult()
    }
}




// 清除定时器
const clearAutoNextTimer = () => {
    if (autoNextTimer) {
        clearTimeout(autoNextTimer)
        autoNextTimer = null
    }
    if (countdownInterval) {
        clearInterval(countdownInterval)
        countdownInterval = null
    }
    isWaitingAutoNext.value = false
    autoNextCountdown.value = 0  // ✅ 重置为 0
}
/**
 * 中文语音播放（Promise 版本）
 *
 * 走统一的 `speak()`：内部已处理 cancel→speak 的间隔、语音包选择、
 * 错误码透出和看门狗超时。返回 `{ok, reason}`，不再无声吞掉失败。
 */
const speakChinesePromise = (text) => {
    return speak(text, { lang: 'zh-CN', rate: 0.9 })
}

// 数组随机打乱
const shuffleArray = (array) => {
    const newArray = [...array]
    for (let i = newArray.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
            ;[newArray[i], newArray[j]] = [newArray[j], newArray[i]]
    }
    return newArray
}

/**
 * 播放当前单词的中文发音（输入模式）
 * 根据 repeatCount 设置播放 1~3 遍，每遍间隔 playInterval 秒
 *
 * 2026-10-23 改：
 *  · 原来用 `speakChinese()` + `waitForSpeechEnd()` 轮询 speaking。
 *    一旦浏览器吞掉发声（cancel 后立刻 speak），`speaking` 一直是 false，
 *    轮询立刻 resolve，循环空转完就结束了 —— **有间隔、没声音**。
 *    现在直接 `await speak()`，成功了才算播完。
 *  · 失败要说话。原来是静默的，用户只看到按钮转了一圈。
 *  · `isPlaying` 用 try/finally 兜底，任何异常都不会把按钮永久卡在 loading。
 */
const playCurrentWord = async () => {
    if (!currentWord.value) return

    // 停止当前播放
    stopSpeaking()

    const chinese = currentWord.value.translation
    if (!chinese) {
        ElMessage.warning('该单词没有中文释义')
        return
    }

    isPlaying.value = true
    try {
        // 根据设置播放多次
        for (let i = 0; i < repeatCount.value; i++) {
            if (i > 0) {
                await sleep(playInterval.value * 1000)
            }
            const res = await speakChinese(chinese)
            if (res && res.ok === false) {
                /*
                 * ⚠️ 失败必须**立刻**提示并退出循环。
                 *    原来只有 `return`，没有提示，而且外层还会继续下一轮 ——
                 *    用户实测要等 15.5 秒才看到一行提示，期间毫无反应。
                 *    现在第一发失败就报原因并停下，不做无意义的重播。
                 */
                if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
                    ElMessage.warning(speakReasonText(res.reason, 'zh-CN'))
                }
                return
            }
        }
    } finally {
        isPlaying.value = false
    }
}

/**
 * 播放中文语音（内部方法）
 *
 * 2026-10-23 改：原实现自己 new SpeechSynthesisUtterance 并直接 speak，
 * 失败时 `onerror = () => resolve()` 把错误吞掉。现在交给统一的 speak()。
 */
const speakChinese = (text) => {
    return speak(text, { lang: 'zh-CN', rate: 0.9 })
}

/**
 * 停止当前语音播放
 *
 * 2026-10-23 改：原实现只在 `speechSynthesis.speaking` 为 true 时才 cancel()。
 * 但 Chrome 里队列可能处于「pending 却没进入 speaking」的卡住状态，
 * 此时不 cancel 就永远解锁不了。现在无条件 cancel()，并把排队回调作废。
 */
const stopSpeaking = () => {
    stopSpeak()
}

// 延时函数
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// 提交答案
const submitAnswer = () => {
    if (!userAnswer.value.trim()) {
        ElMessage.warning('请输入答案')
        return
    }

    if (!currentWord.value) return

    const correctEnglish = String(currentWord.value.word || '').toLowerCase().trim()
    const userEnglish = userAnswer.value.toLowerCase().trim()

    // 判断是否正确（忽略大小写和前后空格）
    isCorrect.value = correctEnglish === userEnglish
    isWrong.value = !isCorrect.value
    showFeedback.value = true

    // 记录结果
    practiceResults.value.push({
        wordId: currentWord.value.wordId,
        word: currentWord.value,
        userAnswer: userAnswer.value,
        isCorrect: isCorrect.value
    })

    // 聚焦到下一题按钮
    nextTick(() => {
        inputRef.value?.blur()
    })
}

/*
 * 原 `markAsMastered()` 已删除（2026-10-23）
 * ----------------------------------------
 * 它写的是 `updateWords({ id, isMastered: 1 })`，但：
 *   · `words` 表**没有 isMastered 列**，后端不认这个字段；
 *   · 参数名也错（要 `wordId`，不是 `id`）。
 * 也就是说这个函数从来没成功过，只是把错误吞进了 catch。
 * 与其留一个假装存在的"掌握"概念，不如去掉 —— 见 `practiceRange` 的说明。
 */

// 下一题
const nextWord = () => {
    if (currentIndex.value < practiceWords.value.length - 1) {
        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false

        nextTick(() => {
            inputRef.value?.focus()
            playCurrentWord()
        })
    } else {
        // 练习完成
        showPracticeResult()
    }
}

// 跳过当前单词
const skipWord = () => {
    if (currentIndex.value < practiceWords.value.length - 1) {
        practiceResults.value.push({
            wordId: currentWord.value.wordId,
            word: currentWord.value,
            userAnswer: '',
            isCorrect: false,
            skipped: true
        })

        currentIndex.value++
        userAnswer.value = ''
        showFeedback.value = false
        isCorrect.value = false
        isWrong.value = false

        nextTick(() => {
            playCurrentWord()
        })
    } else {
        showPracticeResult()
    }
}

// 显示练习结果
/*
 * 2026-10-26 闭环改造
 * ---------------------------------------------------------------------------
 * 改前：练完只弹一个 ElMessageBox（总题数/正确/错误/正确率），点「返回」
 *       就把 `practiceResults` 丢掉 —— 关掉页面什么都不剩。
 *       下次进来重头开始，也不知道上次哪些词写错了。
 *
 * 改后：
 *   ① 把结果 POST 到 `/words/practice/submit` 落库；
 *   ② 结果面板里列出**本次写错的词**（不是只给个数字）；
 *   ③ 点「再练一遍错词」直接只练这几个词；
 *   ④ 「去词库」/「让 AI 帮我分析」两个出口。
 *      后者跳到智能体并带上问题，智能体的 `english_practice` 工具
 *      能读到刚才这次练习 —— 页面与对话就此闭环。
 */
/**
 * 本次练习是否已经提交过记录
 *
 * ⚠️ 2026-10-26 修「一次练习存了 3 条记录」：
 *    `showPracticeResult()` 有**三个**触发点 ——
 *      · 答完最后一题的 `nextWord()`
 *      · `skipWord()` 跳过最后一题
 *      · 「结束练习」按钮
 *    用户点「结束练习」时如果刚好已经答完，这三条路径会各调一次，
 *    于是同一次练习在库里躺了 3 条（实测：id 2/3/4 完全相同的数据）。
 *
 *    用这个标记做幂等：提交过一次就不再提交，
 *    新一轮练习开始时（`startPractice` / `retryWrongWords`）重置为 false。
 */
const practiceSubmitted = ref(false)

const submitPracticeRecord = async () => {
    if (!practiceResults.value.length) return
    // 幂等：同一次练习只落库一条
    if (practiceSubmitted.value) return
    practiceSubmitted.value = true

    const total = practiceResults.value.length
    const correct = practiceResults.value.filter(r => r.isCorrect).length
    try {
        await submitPractice({
            mode: 'dictation',
            bookId: selectedBookId.value || undefined,
            title: currentBookName.value || undefined,
            total,
            correct,
            duration: practiceElapsedSeconds.value,
            detail: practiceResults.value.map(r => ({
                word: String(r.word?.word || ''),
                input: String(r.userAnswer || ''),
                ok: !!r.isCorrect
            }))
        })
    } catch (e) {
        // 记录失败不该打断用户看结果，静默即可。
        // 但要把幂等标记放开，让用户还能重试。
        practiceSubmitted.value = false
        console.warn('[listening] 练习记录保存失败', e)
    }
}

// 显示练习结果
const showPracticeResult = async () => {
    stopSpeaking()

    const total = practiceResults.value.length
    const correct = practiceResults.value.filter(r => r.isCorrect).length
    const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0
    const wrongList = practiceResults.value.filter(r => !r.isCorrect)

    // 先落库，再展示（顺序反了会在用户点得太快时丢记录）
    await submitPracticeRecord()

    /*
     * ⚠️ 必须把 `isPracticing` 置 false：结果面板的显示条件是
     *    `hasResult && !isPracticing`，而练习区（题目卡片）的条件是
     *    `isPracticing`。不清掉的话两块钱同时渲染 ——
     *    截图实测：结果面板和题目卡叠在一起，页面很长很乱。
     */
    isPracticing.value = false
    clearAutoNextTimer()

    hasResult.value = true
    resultSummary.value = { total, correct, accuracy }
    resultWrongWords.value = wrongList.map(r => ({
        word: String(r.word?.word || ''),
        translation: String(r.word?.translation || ''),
        userAnswer: String(r.userAnswer || '')
    }))
}


// 结束练习
const stopPractice = () => {
    ElMessageBox.confirm('确定要结束本次练习吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(async () => {
        stopSpeaking()
        clearAutoNextTimer()

        // 已经做了一些题 → 落到结果面板（会先提交记录）
        if (practiceResults.value.length > 0) {
            isPracticing.value = false
            await showPracticeResult()
            return
        }

        isPracticing.value = false
        if (selectedBookId.value) {
            onBookChange(selectedBookId.value)
        }
    }).catch(() => { })
}

/* ============================================================================
 * 结果面板的三个出口（2026-10-26 闭环）
 * ========================================================================== */

/** 只练刚才写错的那几个词 */
function retryWrongWords() {
    const wanted = new Set(resultWrongWords.value.map((w) => w.word))
    const subset = wordList.value.filter((w: any) => wanted.has(String(w.word || '')))
    if (!subset.length) {
        ElMessage.warning('错词已经不在当前词库里了')
        return
    }
    hasResult.value = false
    practiceWords.value = subset
    currentIndex.value = 0
    isPracticing.value = true
    practiceResults.value = []
    userAnswer.value = ''
    showFeedback.value = false
    isCorrect.value = false
    isWrong.value = false
    isWaitingAutoNext.value = false
    currentPlayCount.value = 0
    practiceSubmitted.value = false
    practiceStartedAt.value = Date.now()
    nextTick(() => {
        if (practiceMode.value === 'dictation') {
            playCurrentWord()
        }
    })
}

/** 回到词库选择态 */
function backToBookSelect() {
    hasResult.value = false
    resultWrongWords.value = []
    if (selectedBookId.value) {
        onBookChange(selectedBookId.value)
    }
}

/**
 * 交给智能体分析
 *
 * 跳过去时把问题带在 route state 里 —— 智能体那边的 `english_practice`
 * 工具刚读到这次提交的记录，于是「页面练完 → 聊天里复盘」这条线也接通了。
 */
function askAiForAnalysis() {
    router.push({
        path: '/front/agent/chat',
        state: {
            seedQuestion: '我刚练完一次英语听写，帮我分析一下这次练习，我该重点复习哪些词？'
        } as any
    })
}

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
        clearAutoNextTimer()  // ✅ 清除定时器
    }
})
/*
 * 原 `goBack()` 已删除（2026-10-26）
 * ---------------------------------
 * 返回栏从模板移除后它没有调用方了。练习中退出用「结束练习」按钮，
 * 它内部会弹确认框并回到词库选择态，覆盖了唯一的退出需求。
 */

// 组件挂载：预热语音 + 加载词库
onMounted(() => {
    // 预热语音列表，让用户点播放时不必 await（保住用户手势上下文，
    // 否则 Chrome 会以 not-allowed 拒绝发声）。
    warmUpVoices()
    loadBookOptions()

    /*
     * 第一次交互时解锁 Web Audio 通道。
     * 服务端合成的声音走 Web Audio 播放（`<audio>` 在本环境会卡在
     * readyState 0，见 utils/speech.ts 顶部注释），而 AudioContext
     * 必须在用户手势里 resume 才不会一直被挂起。
     */
    const unlock = () => {
        unlockAudio()
        window.removeEventListener('pointerdown', unlock)
        window.removeEventListener('keydown', unlock)
    }
    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
})

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
    }
})
</script>

<style scoped lang="scss">
.listening-page {
    /*
     * 2026-10-26：原来 `min-height: 100vh` 会让页面比可视区高一点
     * （顶栏已占掉 52px），出现不必要的滚动条。改成 100%。
     *
     * ⚠️ 这里**不要**写 `align-items: center`：子元素已用
     *    `max-width + margin: 0 auto` 水平居中，再叠一层 center
     *    会因为 `width: 100%` 与 flex 收缩规则打架，实测整体偏右。
     */
    min-height: 100%;
    display: flex;
    flex-direction: column;

    .setting-hint {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 4px;
        display: block;
    }

    .page-header {
        display: grid;
        grid-template-columns: 1fr 1fr 1fr;
        align-items: center;
        padding: 16px 20px;
        background: #fff;
        border-bottom: 1px solid #e5e7eb;

        .header-left {
            display: flex;
            align-items: center;
            gap: 4px;
            color: #6b7280;
            cursor: pointer;
            font-size: 15px;
            justify-self: start;
            width: fit-content;

            &:hover {
                color: #4b5563;
            }
        }

        .header-title {
            font-size: 20px;
            font-weight: 700;
            color: #1f2937;
            text-align: center;
        }

        .header-right {
            justify-self: end;
            width: 60px;
        }
    }

    /*
     * 练习结果面板（2026-10-26 闭环）
     * ---------------------------------
     * 取代原来那个只有 4 个数字的 ElMessageBox：
     * 给分数、列错词、三个出口，让"练完 → 复盘 → 再练"形成回路。
     */
    .result-panel {
        max-width: 620px;
        margin: 0 auto;
        padding: 28px 26px;
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        display: flex;
        flex-direction: column;
        gap: 18px;
    }

    .result-panel__head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
        padding-bottom: 16px;
        border-bottom: 1px solid #f1f5f9;
    }

    .result-panel__score {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    .result-panel__pct {
        font-size: 40px;
        font-weight: 700;
        line-height: 1;
        color: #111827;

        i {
            font-style: normal;
            font-size: 18px;
            font-weight: 600;
            color: #9ca3af;
            margin-left: 2px;
        }
    }

    .result-panel__label {
        font-size: 12.5px;
        color: #9ca3af;
    }

    .result-panel__nums {
        display: flex;
        gap: 14px;
        font-size: 13px;
        color: #6b7280;

        .is-ok {
            color: #10b981;
        }

        .is-bad {
            color: #ef4444;
        }
    }

    .result-panel__wrong-title {
        margin-bottom: 10px;
        font-size: 12.5px;
        font-weight: 600;
        letter-spacing: .02em;
        color: #9ca3af;
    }

    .wrong-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
        max-height: 280px;
        overflow-y: auto;
    }

    .wrong-item {
        display: grid;
        grid-template-columns: minmax(90px, 140px) 1fr;
        gap: 4px 12px;
        padding: 10px 12px;
        background: #fef2f2;
        border: 1px solid #fee2e2;
        border-radius: 10px;
        font-size: 13px;

        .wrong-item__word {
            font-weight: 600;
            color: #b91c1c;
        }

        .wrong-item__trans {
            color: #6b7280;
        }

        .wrong-item__mine {
            grid-column: 1 / -1;
            font-size: 12px;
            color: #9ca3af;
        }
    }

    .result-panel__allok {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 22px;
        background: #ecfdf5;
        border-radius: 12px;
        color: #047857;
        font-size: 14px;
    }

    .result-panel__actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }

    .result-panel__ai {
        margin: 0;
        padding-top: 14px;
        border-top: 1px dashed #f1f5f9;
        font-size: 13px;
        color: #9ca3af;
    }

    .result-panel__link {
        color: #3b82f6;
        cursor: pointer;

        &:hover {
            text-decoration: underline;
        }
    }

    .book-select-section {
        flex: 1;
        padding: 0;
        max-width: 560px;
        margin: 0 auto;
        width: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        /* 垂直方向也居中，避免内容全挤在页面顶部、下方一大片空白 */
        min-height: calc(100vh - 220px);
        .select-label {
            font-size: 13px;
            font-weight: 600;
            letter-spacing: .02em;
            color: #6b7280;
            margin-bottom: 10px;
        }

        /*
         * 空状态卡片（2026-10-26 新增）
         * 改前未选词库时页面只有一个孤立下拉框，下方空无一物。
         */
        .start-empty {
            margin-top: 28px;
            padding: 44px 24px;
            display: flex;
            flex-direction: column;
            align-items: center;
            text-align: center;
            gap: 6px;
            background: #fff;
            border: 1px dashed #e2e8f0;
            border-radius: 16px;

            .start-empty__icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 56px;
                height: 56px;
                margin-bottom: 6px;
                border-radius: 14px;
                background: #f1f5f9;
                color: #94a3b8;
            }

            .start-empty__title {
                margin: 0;
                font-size: 15px;
                font-weight: 600;
                color: #374151;
            }

            .start-empty__desc {
                max-width: 340px;
                font-size: 13px;
                line-height: 1.7;
                color: #9ca3af;
            }

            .start-empty__btn {
                margin-top: 10px;
            }
        }

        .book-stats {
            display: flex;
            gap: 24px;
            margin-top: 16px;
            padding: 14px 20px;
            background: #fff;
            border-radius: 14px;
            border: 1px solid #e5e7eb;

            .stat-item {
                display: flex;
                /* 2026-10-26：原来 `column + center` —— 一个数字孤零零居中，
                   下面还顶着"总单词"，看起来像张空卡片。改成一行横排更紧凑。 */
                align-items: baseline;
                gap: 8px;

                .stat-value {
                    font-size: 20px;
                    font-weight: 700;
                    line-height: 1;
                    color: #3b82f6;
                }

                .stat-label {
                    font-size: 13px;
                    color: #6b7280;
                }
            }
        }

        .practice-settings {
            margin-top: 24px;
            padding: 20px;
            background: #fff;
            border-radius: 16px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

            /*
             * 2026-10-26 重排
             * -----------------------------------------------------------------
             * 改前：`.setting-label` 是 `display: block`（标签独占一行），
             *       而「练习模式」又被错嵌进「播放顺序」里 —— 那一行是 flex，
             *       于是标签和单选框直接压在一起（截图里能看到字叠字）。
             *
             * 改后：统一两列网格 —— 左列 96px 放标签、右列放控件。
             *       标签不再独占一行，各行左边缘对齐，视觉上是一条竖线。
             */
            .setting-item {
                display: grid;
                grid-template-columns: 96px minmax(0, 1fr);
                align-items: center;
                gap: 16px;
                margin-bottom: 18px;

                &:last-child {
                    margin-bottom: 0;
                }

                .setting-label {
                    font-size: 13.5px;
                    font-weight: 500;
                    color: #1f2937;
                    /* 不再 block：在网格里它天然占左列 */
                    white-space: nowrap;
                }

                /* 单选框之间留出呼吸感，避免挤在一起 */
                :deep(.el-radio) {
                    margin-right: 20px;

                    &:last-child {
                        margin-right: 0;
                    }
                }
            }

            /*
             * 滑块行：`align-items: center` 会让滑块和标签基线错位，
             * 这里改成顶部对齐，并让滑块占满右列。
             */
            .setting-item--slider {
                align-items: start;

                .setting-label {
                    /* 与滑块轨道视觉对齐（滑块本身有内边距） */
                    padding-top: 2px;
                }

                .setting-control {
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                    min-width: 0;
                }

                :deep(.el-slider) {
                    /* 去掉默认左右外边距，让它和上方单选框左边缘对齐 */
                    padding: 0 6px;
                }

                .setting-hint {
                    font-size: 12px;
                    line-height: 1.5;
                    color: #9ca3af;
                }
            }
        }

        .start-section {
            margin-top: 28px;
            text-align: center;

            .el-button {
                width: 200px;
                height: 48px;
                font-size: 16px;
                border-radius: 8px;
            }
        }
    }

    .practice-section {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 24px 20px;
        max-width: 600px;
        margin: 0 auto;
        width: 100%;

        .progress-bar {
            margin-bottom: 32px;

            .progress-text {
                text-align: center;
                font-size: 16px;
                font-weight: 500;
                color: #409eff;
                margin-bottom: 12px;
            }
        }

        .word-card {
            flex: 1;
            background: #fff;
            border-radius: 16px;
            padding: 40px 24px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
            border: 1px solid #e5e7eb;
            display: flex;
            flex-direction: column;

            .word-chinese {
                font-size: 36px;
                font-weight: 700;
                color: #1f2937;
                text-align: center;
                margin-bottom: 12px;
            }

            .word-phonetic {
                font-size: 16px;
                color: #9ca3af;
                text-align: center;
                margin-bottom: 32px;
                font-family: monospace;
            }

            .play-section {
                text-align: center;
                margin-bottom: 40px;

                .play-btn {
                    width: 80px;
                    height: 80px;
                    margin-bottom: 12px;

                    .el-icon {
                        font-size: 32px;
                    }
                }

                .play-hint {
                    display: block;
                    font-size: 14px;
                    color: #6b7280;
                }
            }

            .input-section {
                margin-bottom: 24px;
            }

            .feedback-section {
                .feedback-card {
                    display: flex;
                    align-items: flex-start;
                    gap: 16px;
                    padding: 20px;
                    border-radius: 16px;
                    border: 1px solid transparent;

                    &.correct {
                        background: #f0f9eb;
                        border-color: #b3e19d;
                    }

                    &.wrong {
                        background: #fef0f0;
                        border-color: #fbc4c4;
                    }

                    .feedback-icon {
                        color: #67c23a;

                        .wrong & {
                            color: #f56c6c;
                        }
                    }

                    .feedback-content {
                        flex: 1;

                        .correct-answer,
                        .your-answer,
                        .word-meaning {
                            margin-bottom: 8px;

                            &:last-child {
                                margin-bottom: 0;
                            }

                            .label {
                                font-weight: 500;
                                color: #6b7280;
                            }

                            .value {
                                color: #1f2937;
                                font-weight: 500;
                            }
                        }
                    }
                }
            }
        }

        .action-buttons {
            display: flex;
            gap: 12px;
            justify-content: center;
            margin-top: 24px;
            padding-top: 16px;

            .el-button {
                min-width: 120px;
                border-radius: 8px;
            }
        }
    }
}

@media (max-width: 768px) {
    .listening-page {
        .practice-section {
            .word-card {
                padding: 24px 16px;

                .word-chinese {
                    font-size: 28px;
                }
            }

            .action-buttons {
                flex-wrap: wrap;

                .el-button {
                    flex: 1;
                    min-width: auto;
                }
            }
        }
    }
}
</style>