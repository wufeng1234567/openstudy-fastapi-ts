<template>
    <div class="listening-page">
        <!--
          顶部导航栏
          ⚠️ 2026-10-26：中间的「听力练习」标题已上移到全局顶栏
             （`英语学习 · 单词听写` + 灰色副标题），这里删掉以免重复。
             顺带把页面名统一为「单词听写」——侧边菜单和顶栏都是这个名字，
             原来这里写「听力练习」会造成同一功能两个叫法。
        -->
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title"></div>
            <div class="header-right"></div>
        </div>

        <!-- 词库选择（未开始时显示） -->
        <div class="book-select-section" v-if="!isPracticing">
            <div class="select-label">选择词库</div>
            <el-select v-model="selectedBookId" placeholder="请选择词库" size="large" style="width: 100%"
                @change="onBookChange">
                <el-option v-for="book in bookOptions" :key="book.bookId" :label="book.bookName" :value="book.bookId" />
            </el-select>

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

            <!-- 练习设置 -->
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
                    <div class="setting-item">
                        <span class="setting-label">练习模式</span>
                        <el-radio-group v-model="practiceMode">
                            <el-radio value="input">输入模式</el-radio>
                            <el-radio value="dictation">听写模式</el-radio>
                        </el-radio-group>
                    </div>
                </div>
                <div class="setting-item">
                    <span class="setting-label">播放次数</span>
                    <el-radio-group v-model="repeatCount">
                        <el-radio :value="1">1次</el-radio>
                        <el-radio :value="2">2次</el-radio>
                        <el-radio :value="3">3次</el-radio>
                    </el-radio-group>
                </div>
                <div class="setting-item" v-if="practiceMode === 'dictation'">
                    <span class="setting-label">播放间隔</span>
                    <el-slider v-model="playInterval" :min="1" :max="5" :step="0.5" show-stops
                        :format-tooltip="(val) => val + '秒'" style="width: 200px" />
                    <span class="setting-label">自动下一题间隔</span>
                    <el-slider v-model="autoNextInterval" :min="1" :max="10" :step="0.5" show-stops
                        :format-tooltip="(val) => val + '秒'" style="width: 200px" />
                    <span class="setting-hint">播放完成后等待此时间自动进入下一题</span>
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

        <!-- 练习界面 -->
        <div class="practice-section" v-else>
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
    CircleCheck, CircleClose
} from '@element-plus/icons-vue'
import { listFrontWordBooks } from '@/api/wordBooks/wordBooks'
import { listAllWords } from '@/api/words/words'
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
const showPracticeResult = () => {
    stopSpeaking()

    const total = practiceResults.value.length
    const correct = practiceResults.value.filter(r => r.isCorrect).length
    const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0

    ElMessageBox.alert(
        `
        <div style="text-align: center;">
            <h3>练习完成！</h3>
            <p>总题数：${total}</p>
            <p>正确：${correct}</p>
            <p>错误：${total - correct}</p>
            <p>正确率：${accuracy}%</p>
        </div>
        `,
        '练习结果',
        {
            dangerouslyUseHTMLString: true,
            confirmButtonText: '返回',
            callback: () => {
                isPracticing.value = false
                // 刷新单词列表
                if (selectedBookId.value) {
                    onBookChange(selectedBookId.value)
                }
            }
        }
    )
}

// 结束练习
const stopPractice = () => {
    ElMessageBox.confirm('确定要结束本次练习吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
    }).then(() => {
        stopSpeaking()
        clearAutoNextTimer()  // ✅ 清除定时器

        // 如果已经做了一些题，显示结果
        if (practiceResults.value.length > 0) {
            const total = practiceResults.value.length
            const correct = practiceResults.value.filter(r => r.isCorrect).length

            ElMessageBox.alert(
                `
                <div style="text-align: center;">
                    <h3>练习已结束</h3>
                    <p>已完成：${total} 题</p>
                    <p>正确：${correct}</p>
                    <p>错误：${total - correct}</p>
                </div>
                `,
                '练习结果',
                {
                    dangerouslyUseHTMLString: true,
                    confirmButtonText: '确定'
                }
            )
        }

        isPracticing.value = false
        clearAutoNextTimer()  // ✅ 再次确保清除
        if (selectedBookId.value) {
            onBookChange(selectedBookId.value)
        }
    }).catch(() => { })
}

// 监听页面离开
watch(() => isPracticing.value, (val) => {
    if (!val) {
        stopSpeaking()
        clearAutoNextTimer()  // ✅ 清除定时器
    }
})
// 返回
// ⚠️ 2026-10-26：「英语学习」的入口首页已下线，返回目标改成「我的词库」
//    （听写之前通常先去词库确认有哪些词书）。
const goBack = () => {
    if (isPracticing.value) {
        stopPractice()
    } else {
        cacheStore.setLastVisited('english', 'vocabulary')
        router.push('/front/english/vocabulary')
    }
}

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
    min-height: 100vh;
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

    .book-select-section {
        flex: 1;
        padding: 24px 20px;
        max-width: 500px;
        margin: 0 auto;
        width: 100%;

        .select-label {
            font-size: 14px;
            font-weight: 500;
            color: #1f2937;
            margin-bottom: 12px;
        }

        .book-stats {
            display: flex;
            gap: 24px;
            margin-top: 20px;
            padding: 16px;
            background: #fff;
            border-radius: 16px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);

            .stat-item {
                display: flex;
                flex-direction: column;
                align-items: center;

                .stat-value {
                    font-size: 24px;
                    font-weight: 700;
                    color: #409eff;
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

            .setting-item {
                margin-bottom: 20px;

                &:last-child {
                    margin-bottom: 0;
                }

                .setting-label {
                    display: block;
                    font-size: 14px;
                    font-weight: 500;
                    color: #1f2937;
                    margin-bottom: 12px;
                }
            }
        }

        .start-section {
            margin-top: 32px;
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