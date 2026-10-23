<template>
    <div class="listening-page">
        <!-- 顶部导航栏 -->
        <div class="page-header">
            <div class="header-left" @click="goBack">
                <el-icon>
                    <ArrowLeft />
                </el-icon>
                <span>返回</span>
            </div>
            <div class="header-title">听力练习</div>
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
                <div class="word-chinese">{{ currentWord?.chinese || '' }}</div>
                <div class="word-phonetic" v-if="currentWord?.phonetic">{{ currentWord.phonetic }}</div>

                <!-- 播放按钮 -->
                <div class="play-section">
                    <el-button type="primary" circle size="large"
                        @click="practiceMode === 'dictation' ? startDictationRound() : playCurrentWord()"
                        :loading="isPlaying" class="play-btn" :disabled="isWaitingAutoNext">
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
                                <span class="value">{{ currentWord.english }}</span>
                            </div>
                            <div class="your-answer" v-if="!isCorrect">
                                <span class="label">你的答案：</span>
                                <span class="value">{{ userAnswer }}</span>
                            </div>
                            <div class="word-meaning">
                                <span class="label">释义：</span>
                                <span class="value">{{ currentWord.chinese }}</span>
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
import { listWords } from '@/api/words/words'
import useUserStore from '@/store/modules/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'

const router = useRouter()
const userStore = useUserStore()
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
// 使用浏览器内置的 SpeechSynthesis API，无需后端接口或第三方服务
// MDN 文档：https://developer.mozilla.org/zh-CN/docs/Web/API/SpeechSynthesis
// 兼容性：Chrome、Edge、Safari、Firefox 均支持
let speechSynthesis = window.speechSynthesis
let currentUtterance = null  // 当前正在播放的语音实例，用于中途停止

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
        const userId = userStore.id
        const response = await listFrontWordBooks({
            pageNum: 1,
            pageSize: 100,
            userId
        })
        if (response.code === 200) {
            bookOptions.value = response.rows || []
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
        const response = await listWords({
            pageNum: 1,
            pageSize: 1000,
            bookId: bookId
        })
        if (response.code === 200) {
            wordList.value = response.rows || []
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

    for (let i = 0; i < repeatCount.value; i++) {
        currentPlayCount.value = i + 1
        await speakChinesePromise(chinese)
        if (i < repeatCount.value - 1) {
            await sleep(playInterval.value * 1000)
        }
    }

    isPlaying.value = false
    currentPlayCount.value = 0

    // 播放完成后，等待自动下一题
    startAutoNextCountdown()
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
 * 使用 Web Speech API 的 SpeechSynthesisUtterance 对象
 * @param text 要朗读的中文文本
 * @returns Promise 朗读结束时 resolve
 *
 * 参数说明：
 * - lang: 'zh-CN'  中文语音
 * - rate: 0.9      语速（0.1~10，默认1，0.9稍慢更清晰）
 * - pitch: 1       音高（0~2，默认1）
 * - volume: 1      音量（0~1，默认1）
 */
const speakChinesePromise = (text) => {
    return new Promise((resolve) => {
        const utterance = new SpeechSynthesisUtterance(text)
        utterance.lang = 'zh-CN'
        utterance.rate = 0.9
        utterance.pitch = 1
        utterance.volume = 1

        utterance.onend = () => resolve()
        utterance.onerror = () => resolve()

        speechSynthesis.speak(utterance)
    })
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
 */
const playCurrentWord = async () => {
    if (!currentWord.value) return

    // 停止当前播放
    stopSpeaking()

    const chinese = currentWord.value.chinese
    if (!chinese) {
        ElMessage.warning('该单词没有中文释义')
        return
    }

    isPlaying.value = true

    // 根据设置播放多次
    for (let i = 0; i < repeatCount.value; i++) {
        if (i > 0) {
            await sleep(playInterval.value * 1000)
        }
        speakChinese(chinese)
        // 等待播放完成
        await waitForSpeechEnd()
    }

    isPlaying.value = false
}

/**
 * 播放中文语音（内部方法）
 * 创建 SpeechSynthesisUtterance 对象并调用 speechSynthesis.speak()
 * 浏览器会使用系统内置的中文语音引擎朗读文本
 */
const speakChinese = (text) => {
    return new Promise((resolve) => {
        const utterance = new SpeechSynthesisUtterance(text)
        utterance.lang = 'zh-CN'
        utterance.rate = 0.9
        utterance.pitch = 1
        utterance.volume = 1

        utterance.onend = () => resolve()
        utterance.onerror = () => resolve()

        currentUtterance = utterance
        speechSynthesis.speak(utterance)
    })
}

/**
 * 等待语音播放结束
 * 轮询 speechSynthesis.speaking 状态，每 100ms 检查一次
 * 当 speaking 变为 false 时 resolve
 */
const waitForSpeechEnd = () => {
    return new Promise((resolve) => {
        const checkInterval = setInterval(() => {
            if (!speechSynthesis.speaking) {
                clearInterval(checkInterval)
                resolve()
            }
        }, 100)
    })
}

/**
 * 停止当前语音播放
 * 调用 speechSynthesis.cancel() 会立即停止所有排队中的语音
 */
const stopSpeaking = () => {
    if (speechSynthesis.speaking) {
        speechSynthesis.cancel()
    }
    currentUtterance = null
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

    const correctEnglish = currentWord.value.english.toLowerCase().trim()
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
const goBack = () => {
    if (isPracticing.value) {
        stopPractice()
    } else {
        cacheStore.setLastVisited('english', 'home')
        router.push('/front/english/home')
    }
}

// 组件卸载时停止播放
onMounted(() => {
    loadBookOptions()
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