<!-- src/components/Dictation/DictationPractice.vue -->
<template>
  <div class="dictation-content-wrapper">
    <el-row :gutter="20">
      <el-col :span="10">
        <el-card class="config-card">
          <template #header>
            <div class="card-header">
              <span><i-ep-setting class="icon-margin" />练习设置</span>
            </div>
          </template>
          <el-form :model="dictationForm" ref="dictationFormRef" label-width="100px" class="dictation-config-form">
            <el-form-item label="选择单词本" prop="wordBookId">
              <el-select v-model="dictationForm.wordBookId" placeholder="请选择单词本" @change="onWordBookChange"
                style="width: 100%;">
                <el-option v-for="item in wordBookOptions" :key="item.id" :label="item.name" :value="item.id" />
              </el-select>
            </el-form-item>

            <el-form-item label="播放模式" prop="mode">
              <el-radio-group v-model="dictationForm.mode">
                <el-radio label="sequence"><i-ep-sort class="icon-margin" />顺序播放</el-radio>
                <el-radio label="random"><i-ep-refresh class="icon-margin" />随机播放</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="播放间隔" prop="interval">
              <el-slider v-model="dictationForm.interval" :min="1" :max="30" show-input :show-input-controls="false"
                input-size="small" />
              <span class="interval-unit">秒</span>
            </el-form-item>

            <el-form-item label="单词重复" prop="repeatCount">
              <el-input-number v-model="dictationForm.repeatCount" :min="1" :max="10" size="small" />
              <span class="interval-unit">遍</span>
            </el-form-item>

            <el-form-item label="重复间隔" prop="repeatInterval">
              <el-slider v-model="dictationForm.repeatInterval" :min="0.5" :max="5" :step="0.5" show-input
                :show-input-controls="false" input-size="small" />
              <span class="interval-unit">秒</span>
            </el-form-item>

            <el-form-item label="循环播放" prop="loopPlay">
              <el-switch v-model="dictationForm.loopPlay" />
            </el-form-item>

            <el-form-item label="播放内容" prop="playType">
              <el-radio-group v-model="dictationForm.playType">
                <el-radio label="english"><i-ep-chat-line-round class="icon-margin" />播放英文</el-radio>
                <el-radio label="chinese"><i-ep-message class="icon-margin" />播放中文</el-radio>
              </el-radio-group>
            </el-form-item>

            <!-- 统一按钮区域 -->
            <!-- 替换原来的按钮区域 -->
            <el-form-item>
              <div class="action-buttons">
                <el-button type="primary" icon="VideoPlay" @click="startDictation" size="large">
                  开始练习
                </el-button>
                <el-button :type="isPlayingDictation ? 'warning' : 'info'"
                  :icon="isPlayingDictation ? 'VideoPause' : 'RefreshLeft'" @click="toggleDictation" size="large">
                  {{ isPlayingDictation ? '暂停练习' : '恢复播放' }}
                </el-button>
                <el-button v-if="dictationForm.wordBookId" type="primary" plain icon="View" @click="showWordList = true"
                  size="large">
                  单词本内容
                </el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card class="statistic-card mt15">
          <template #header>
            <div class="card-header">
              <span><i-ep-data-analysis class="icon-margin" />练习统计</span>
            </div>
          </template>
          <div class="statistics-content">
            <el-row :gutter="15">
              <el-col :span="12">
                <div class="statistic-item">
                  <div class="statistic-value">{{ totalWords }}</div>
                  <div class="statistic-label">总单词数</div>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="statistic-item">
                  <div class="statistic-value">{{ currentProgress }}</div>
                  <div class="statistic-label">已完成</div>
                </div>
              </el-col>
            </el-row>
            <el-progress :percentage="(currentProgress / Math.max(totalWords, 1)) * 100" :show-text="false"
              class="mt10" />
          </div>
        </el-card>
      </el-col>

      <el-col :span="14">
        <!-- 主要内容保持不变 -->
        <el-card class="exercise-card">
          <template #header>
            <div class="card-header">
              <span><i-ep-headset class="icon-margin" />听力练习区</span>
            </div>
          </template>
          <div class="dictation-content">
            <div class="current-word-display">
              <transition name="fade" mode="out-in">
                <div :key="currentWord" class="current-word">{{ currentWord || '准备就绪' }}</div>
              </transition>
              <div class="progress-info">
                第 {{ currentProgress }} / {{ totalWords }} 个单词
              </div>
            </div>

            <div class="answer-section">
              <el-input v-model="userAnswer" placeholder="请输入听到的单词或中文意思" size="large" @keyup.enter="submitAnswer"
                class="answer-input" />
              <el-button type="primary" @click="submitAnswer" size="large" class="submit-btn">提交答案</el-button>
            </div>

            <div class="control-buttons mt20">
              <el-button icon="CaretRight" circle size="large" @click="playCurrentWord" title="播放当前单词" />
              <el-button icon="ArrowRight" circle size="large" @click="nextWord" title="下一个单词" />
              <el-button icon="RefreshLeft" circle size="large" @click="prevWord" title="上一个单词" />
            </div>
          </div>
        </el-card>

        <el-card class="result-card mt15">
          <template #header>
            <div class="card-header">
              <span><i-ep-document-checked class="icon-margin" />答题记录</span>
            </div>
          </template>
          <div class="result-content">
            <el-empty description="暂无答题记录" v-if="!practiceResults.length" />
            <div v-else class="result-list">
              <div v-for="(result, index) in practiceResults" :key="index" class="result-item"
                :class="{ 'correct': result.correct, 'incorrect': !result.correct }">
                <div class="result-question">{{ result.question }}</div>
                <div class="result-answer">你的答案: {{ result.userAnswer }}</div>
                <div class="result-correct" v-if="!result.correct">正确答案: {{ result.correctAnswer }}</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 在单词列表抽屉中添加分页组件 -->
    <el-drawer v-model="showWordList" title="单词本内容" direction="rtl" size="50%" :before-close="handleWordListClose">
      <div class="word-list-container">
        <el-button type="primary" plain icon="Refresh" @click="loadWordBookWords" class="refresh-btn">
          刷新单词列表
        </el-button>

        <!-- 修改单词列表抽屉中的表格部分 -->
        <!-- ⚠️ 2026-10-23 修：prop 原来是 `english` / `chinese`，
             但后端 `/words/words/list` 返回的字段是 `word` / `translation`，
             所以这两列一直是空白。 -->
        <el-table :data="wordBookWords" height="calc(100vh - 250px)" class="word-list-table mt15">
          <el-table-column label="英文单词" prop="word" min-width="150">
            <template #default="scope">
              <span class="word-english">{{ scope.row.word }}</span>
            </template>
          </el-table-column>
          <el-table-column label="中文意思" prop="translation" min-width="200">
            <template #default="scope">
              <span class="word-chinese">{{ scope.row.translation }}</span>
            </template>
          </el-table-column>
          <el-table-column label="音标" prop="phonetic" min-width="120">
            <template #default="scope">
              <span class="word-phonetic">{{ scope.row.phonetic || '-' }}</span>
            </template>
          </el-table-column>
          <!-- 添加播放按钮列 -->
          <!-- 在抽屉表格的播放按钮中添加禁用条件 -->
          <el-table-column label="操作" width="100" align="center">
            <template #default="scope">
              <el-button type="primary" icon="Headset" circle size="small" @click="playWord(scope.row.word)"
                :disabled="isPlayingDictation" title="播放单词发音" />
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加分页组件 -->
        <pagination v-show="wordBookWordsTotal > 0" :total="wordBookWordsTotal"
          v-model:page="wordBookWordsQuery.pageNum" v-model:limit="wordBookWordsQuery.pageSize"
          @pagination="loadWordBookWords" class="pagination-container" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { listWords, listAllWords } from "@/api/words/words"
import { speak, stopSpeak, speakReasonText } from '@/utils/speech'

const props = defineProps({
  wordBookOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['startDictation', 'stopDictation'])

// 听力练习相关数据
const currentWord = ref("")
const currentProgress = ref(0)
const totalWords = ref(0)
const userAnswer = ref("")
const practiceResults = ref([])
const wordBookWords = ref([]) // 单词本中的单词列表
const showWordList = ref(false) // 控制单词列表抽屉显示

// 语音播放相关
// ⚠️ 2026-10-23：`speechSynthesis` / `utterance` 两个本地句柄已不再需要，
//    播放统一走 @/utils/speech。这里只保留状态位。
const isPlaying = ref(false)
const isPlayingDictation = ref(false) // 是否正在播放听写练习
const currentWordIndex = ref(0) // 当前播放的单词索引
let playTimer = null // 自动播放定时器
let repeatCount = ref(0) // 当前单词已重复播放次数

const playedWordsCount = ref(0) // 已播放的单词数量（用于非循环随机播放模式）
// 添加一个数组用于跟踪已播放的单词索引
const playedWordIndices = ref([]) // 已播放的单词索引列表

const dictationForm = reactive({
  wordBookId: null,
  mode: 'sequence',
  interval: 5,
  repeatCount: 2, // 单词重复播放次数
  repeatInterval: 1, // 重复播放间隔（秒）
  loopPlay: false, // 是否循环播放
  playType: 'english'
})

// 单词本单词分页相关数据
// ⚠️ 键名必须是 `bookId`（后端认的参数名）。原来是 `wordBookId`，
//    后端读不到就当没传，返回的是「我所有词书」的单词。
const wordBookWordsQuery = reactive({
  pageNum: 1,
  pageSize: 10,
  bookId: null
})
const wordBookWordsTotal = ref(0)


const dictationFormRef = ref(null)

const fullWordBookWords = ref([]) // 用于存储完整的单词本单词列表


// 在 onWordBookChange 函数中重置分页参数和播放状态
function onWordBookChange() {
  console.log('单词本切换，选中的单词本ID:', dictationForm.wordBookId);
  // 停止当前播放
  stopDictation()
  
  // 重置分页参数
  wordBookWordsQuery.pageNum = 1
  wordBookWordsQuery.pageSize = 10
  
  // 当选择单词本变化时的处理
  loadWordBookWords()
}

// 修改 loadWordBookWords 函数
function loadWordBookWords() {
  if (!dictationForm.wordBookId) {
    console.log('没有选中单词本，返回');
    return
  }
  
  console.log('加载单词本数据，查询参数:', {...wordBookWordsQuery, bookId: dictationForm.wordBookId});

  // 设置查询参数
  // ⚠️ 2026-10-23 修：后端参数名是 `bookId`（不是 wordBookId）。
  //    传 wordBookId 会被 FastAPI 静默忽略 → 返回「我所有词书」的单词，
  //    听写会练到别的词书里去。
  wordBookWordsQuery.bookId = dictationForm.wordBookId

  // 加载分页数据用于表格显示
  listWords(wordBookWordsQuery).then(response => {
    console.log('分页数据加载完成，数据:', response);
    wordBookWords.value = response.rows
    wordBookWordsTotal.value = response.total
    
    // 更新当前显示的总单词数
    totalWords.value = response.total
    console.log('更新totalWords为分页数据总数:', response.total);
    
    // 重置进度
    currentProgress.value = 0
    if (response.rows.length > 0 && !isPlayingDictation.value) {
      currentWordIndex.value = 0
      updateCurrentWordDisplay()
    }
  })

  // 同时加载完整的单词列表用于播放（仅在单词本改变时加载）
  if (arguments.length === 0) { // 只有在非分页调用时才加载完整列表
    // ⚠️ 2026-10-23 修：原来写 `pageSize: 1000`，但后端 `le=200` 是硬上限，
    //    超了会被 FastAPI 直接 HTTP 422（整本词书加载失败）。
    //    现在改用 listAllWords：内部按 200 翻页把整本词书取完，词书再大也不截断。
    const fullListQuery = {
      bookId: dictationForm.wordBookId
    };
    console.log('加载完整单词列表，查询参数:', fullListQuery);
    
    listAllWords(fullListQuery).then(response => {
      console.log('完整单词列表加载完成，数据:', response);
      fullWordBookWords.value = response.rows
      // 更新总单词数为当前单词本的实际单词数
      totalWords.value = response.rows.length
      console.log('更新totalWords为完整列表长度:', response.rows.length);
      
      // 重置播放相关状态
      resetPlayState()
    })
  }
}


// 添加重置播放状态的函数
function resetPlayState() {
  console.log('重置播放状态，当前完整单词列表长度:', fullWordBookWords.value.length);
  // 停止当前播放
  stopDictation()
  stopAutoPlay()
  stopSpeech()
  
  // 重置播放相关变量
  currentWordIndex.value = 0
  repeatCount.value = 0
  playedWordsCount.value = 0
  playedWordIndices.value = []
  currentWord.value = ""
  currentProgress.value = 0
  
  // 确保总单词数正确
  totalWords.value = fullWordBookWords.value.length
  console.log('在resetPlayState中更新totalWords为:', fullWordBookWords.value.length);
  
  // 更新显示
  if (fullWordBookWords.value.length > 0) {
    updateCurrentWordDisplay()
  }
}
// 修改 updateCurrentWordDisplay 函数，使用完整单词列表进行播放
function updateCurrentWordDisplay() {
  console.log('更新当前单词显示，完整单词列表长度:', fullWordBookWords.value.length, 
              '当前索引:', currentWordIndex.value);
  // 使用完整单词列表而不是分页列表
  if (fullWordBookWords.value.length > 0 && currentWordIndex.value < fullWordBookWords.value.length) {
    const word = fullWordBookWords.value[currentWordIndex.value]
    // ⚠️ 2026-10-23 修：字段是 `word` / `translation`（不是 english / chinese），
    //    原来取到 undefined → 屏幕上的当前单词永远是空的。
    currentWord.value = dictationForm.playType === 'english' ? word.word : word.translation
    console.log('当前显示单词:', currentWord.value);

    // 正确更新进度显示
    if (dictationForm.mode === 'random') {
      // 随机播放模式
      if (dictationForm.loopPlay) {
        // 循环播放时显示当前索引位置
        currentProgress.value = currentWordIndex.value + 1
      } else {
        // 非循环播放时显示已播放的单词数量
        currentProgress.value = playedWordIndices.value.length
      }
    } else {
      // 顺序播放模式
      if (dictationForm.loopPlay) {
        // 循环播放时显示当前索引位置
        currentProgress.value = currentWordIndex.value + 1
      } else {
        // 非循环播放时显示已播放的单词数量
        currentProgress.value = playedWordsCount.value
      }
    }
    console.log('更新进度显示，currentProgress:', currentProgress.value, 'totalWords:', totalWords.value);
  }
}

// 修改 startDictation 函数
function startDictation() {
  if (fullWordBookWords.value.length === 0) {
    console.log("请先选择包含单词的单词本")
    return
  }

  // 开始听写练习前先停止可能的其他播放
  stopDictation()

  // 开始听写练习
  isPlayingDictation.value = true

  // 重置索引和计数器
  currentWordIndex.value = 0
  repeatCount.value = 0
  playedWordsCount.value = 0
  playedWordIndices.value = []

  // 根据播放模式设置初始索引
  if (dictationForm.mode === 'random') {
    currentWordIndex.value = Math.floor(Math.random() * fullWordBookWords.value.length)
    playedWordIndices.value.push(currentWordIndex.value)
    playedWordsCount.value = 1
  } else {
    playedWordsCount.value = 1
  }

  updateCurrentWordDisplay()
  playCurrentWordWithRepeat()

  // 开始自动播放
  startAutoPlay()
}

// 停止听力练习
function stopDictation() {
  isPlayingDictation.value = false
  stopAutoPlay()
  stopSpeech()
  // 不重置索引和计数器，保持当前状态
}

// 添加恢复播放函数
function resumeDictation() {
  if (fullWordBookWords.value.length === 0) {
    console.log("请先选择包含单词的单词本")
    return
  }

  if (!isPlayingDictation.value) {
    isPlayingDictation.value = true
    // 恢复自动播放
    startAutoPlay()
    // 播放当前单词
    playCurrentWord()
  }
}

// 开始自动播放
function startAutoPlay() {
  stopAutoPlay() // 先清除之前的定时器

  playTimer = setInterval(() => {
    if (!isPlaying.value) { // 只有在当前单词播放完毕后才播放下一个
      nextDictationWord()
    }
  }, dictationForm.interval * 1000)
}

// 停止自动播放
function stopAutoPlay() {
  if (playTimer) {
    clearInterval(playTimer)
    playTimer = null
  }
}

// 修改 nextDictationWord 函数中相关部分
function nextDictationWord() {
  if (fullWordBookWords.value.length === 0) return

  // 检查是否需要循环播放
  if (dictationForm.loopPlay) {
    // 循环播放模式
    if (dictationForm.mode === 'sequence') {
      // 顺序播放
      currentWordIndex.value = (currentWordIndex.value + 1) % fullWordBookWords.value.length
    } else {
      // 随机播放 - 循环模式下可以重复播放
      let newIndex
      do {
        newIndex = Math.floor(Math.random() * fullWordBookWords.value.length)
      } while (newIndex === currentWordIndex.value && fullWordBookWords.value.length > 1)
      currentWordIndex.value = newIndex
    }
  } else {
    // 非循环播放模式
    if (dictationForm.mode === 'sequence') {
      // 顺序播放
      if (currentWordIndex.value < fullWordBookWords.value.length - 1) {
        currentWordIndex.value++
        playedWordsCount.value = currentWordIndex.value + 1
      } else {
        // 已经播放完所有单词，停止播放
        stopDictation()
        return
      }
    } else {
      // 随机播放 - 非循环模式下不能重复播放
      if (playedWordIndices.value.length < fullWordBookWords.value.length) {
        // 还有未播放的单词
        let newIndex
        let attempts = 0
        do {
          newIndex = Math.floor(Math.random() * fullWordBookWords.value.length)
          attempts++
          // 防止无限循环
          if (attempts > fullWordBookWords.value.length * 2) {
            // 找到第一个未播放的单词
            for (let i = 0; i < fullWordBookWords.value.length; i++) {
              if (!playedWordIndices.value.includes(i)) {
                newIndex = i
                break
              }
            }
            break
          }
        } while (playedWordIndices.value.includes(newIndex))

        currentWordIndex.value = newIndex
        playedWordIndices.value.push(newIndex) // 记录已播放的单词索引
        // playedWordsCount.value 在随机模式下通过 playedWordIndices.length 计算
      } else {
        // 已经播放完所有单词，停止播放
        stopDictation()
        return
      }
    }
  }

  updateCurrentWordDisplay()
  playCurrentWordWithRepeat()
}


// 修改所有使用 wordBookWords.value 进行播放的相关函数
// 修改 playCurrentWordWithRepeat 函数
function playCurrentWordWithRepeat() {
  if (fullWordBookWords.value.length === 0) return

  const word = fullWordBookWords.value[currentWordIndex.value]
  let textToSpeak = ""

  // ⚠️ 2026-10-23 修：字段是 `word` / `translation`（不是 english / chinese）
  if (dictationForm.playType === 'english') {
    textToSpeak = word.word
  } else {
    textToSpeak = word.translation
  }

  if (textToSpeak) {
    // 如果还没达到重复次数，继续重复播放
    if (repeatCount.value < dictationForm.repeatCount - 1) {
      speakWord(textToSpeak, () => {
        // 播放完成后，增加重复计数，并在间隔后再次播放
        repeatCount.value++
        setTimeout(() => {
          playCurrentWordWithRepeat()
        }, dictationForm.repeatInterval * 1000)
      })
    } else {
      // 达到重复次数，正常播放一次
      speakWord(textToSpeak, () => {
        // 重置重复计数
        repeatCount.value = 0
      })
    }
  }
}

// 修改 playCurrentWord 函数
function playCurrentWord() {
  if (fullWordBookWords.value.length === 0) return

  const word = fullWordBookWords.value[currentWordIndex.value]
  let textToSpeak = ""

  // ⚠️ 2026-10-23 修：后端字段是 `word` / `translation`，不是 `english` / `chinese`。
  //    原来取到的是 undefined → `if (textToSpeak)` 判断失败 → **点了完全没反应**。
  if (dictationForm.playType === 'english') {
    textToSpeak = word.word
  } else {
    textToSpeak = word.translation
  }

  if (textToSpeak) {
    speakWord(textToSpeak)
  }
}
// 添加抽屉列表播放单词方法
// ⚠️ 2026-10-23 改：同样收归到 @/utils/speech。
function playWord(englishWord) {
  if (!englishWord) return
  // 处理英语缩写
  const processedText = String(englishWord)
    .replace(/\bsth\b/g, "something")
    .replace(/\bsb\b/g, "somebody")
    .replace(/\bkb\b/g, "kilobyte")
    .replace(/\bmb\b/g, "megabyte")
    .replace(/\bg\b/g, "gram")
    .replace(/\bkg\b/g, "kilogram");

  isPlaying.value = true;
  speak(processedText, { lang: 'en-US', rate: 0.8 })
    .then((res) => {
      isPlaying.value = false;
      if (!res.ok && res.reason !== 'interrupted' && res.reason !== 'canceled') {
        ElMessage.warning(speakReasonText(res.reason, 'en-US'));
      }
    })
    .catch(() => {
      isPlaying.value = false;
    });
}

// 使用Web Speech API播放文字
// ⚠️ 2026-10-23 改：原来自己 new SpeechSynthesisUtterance + speak，
//    踩了「cancel 后立刻 speak 被 Chrome 丢弃」「onerror 被吞」两个坑。
//    现在交给 @/utils/speech（统一处理语音包选择、看门狗、错误提示）。
function speakWord(text, onEndCallback) {
  // 预处理文本，替换常见缩写
  let processedText = text;
  if (dictationForm.playType === 'english') {
    // 处理英语缩写
    processedText = text
      .replace(/\bsth\b/g, "something")
      .replace(/\bsb\b/g, "somebody")
      .replace(/\bkb\b/g, "kilobyte")
      .replace(/\bmb\b/g, "megabyte")
      .replace(/\bg\b/g, "gram")
      .replace(/\bkg\b/g, "kilogram");
  }

  const lang = dictationForm.playType === 'english' ? 'en-US' : 'zh-CN';

  isPlaying.value = true;
  speak(processedText, { lang, rate: 0.8 })
    .then((res) => {
      isPlaying.value = false;
      if (!res.ok) {
        if (res.reason !== 'interrupted' && res.reason !== 'canceled') {
          ElMessage.warning(speakReasonText(res.reason, lang));
        }
        return;
      }
      if (onEndCallback) {
        onEndCallback();
      }
    })
    .catch(() => {
      isPlaying.value = false;
    });
}
// 添加切换播放状态的方法
function toggleDictation() {
  if (isPlayingDictation.value) {
    // 当前正在播放，执行暂停
    stopDictation()
  } else {
    // 当前未播放，执行恢复播放
    resumeDictation()
  }
}
// 停止语音播放
// ⚠️ 2026-10-23 改：原来只在 `isPlaying` 为 true 时才 cancel()，
//    Chrome 卡在 pending 状态时永远停不下来。现在无条件停。
function stopSpeech() {
  stopSpeak()
  isPlaying.value = false
}

// 手动播放下一个单词（用于练习区按钮）
// 修改 nextWord 函数
function nextWord() {
  if (fullWordBookWords.value.length === 0) return

  currentWordIndex.value = (currentWordIndex.value + 1) % fullWordBookWords.value.length
  updateCurrentWordDisplay()
  playCurrentWord()
}

// 手动播放上一个单词（用于练习区按钮）
// 修改 prevWord 函数
function prevWord() {
  if (fullWordBookWords.value.length === 0) return

  currentWordIndex.value = (currentWordIndex.value - 1 + fullWordBookWords.value.length) % fullWordBookWords.value.length
  updateCurrentWordDisplay()
  playCurrentWord()
}

function submitAnswer() {
  // 提交答案
  console.log("答案已提交")
}

// 处理单词列表抽屉关闭
function handleWordListClose(done) {
  showWordList.value = false
  done()
}

// 组件卸载前清理
onBeforeUnmount(() => {
  stopAutoPlay()
  stopSpeech()
})

// 暴露方法给父组件
defineExpose({
  loadWordBookWords
})
</script>

<style scoped lang="scss">
.dictation-content-wrapper {

  .config-card,
  .exercise-card,
  .statistic-card,
  .result-card {
    border-radius: 8px;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);

    :deep(.el-card__header) {
      background-color: #f8f9fa;
      padding: 12px 20px;
      border-bottom: 1px solid #ebeef5;
    }
  }

  .card-header {
    font-weight: 500;
    color: #303133;
    display: flex;
    align-items: center;
  }

  .icon-margin {
    margin-right: 8px;
  }

  .dictation-config-form {
    :deep(.el-form-item) {
      margin-bottom: 20px;
    }

    :deep(.el-form-item__label) {
      font-weight: 500;
    }

    /* 统一按钮样式 */
    .action-buttons {
      display: flex;
      gap: 12px;
      justify-content: center;
      flex-wrap: wrap;

      :deep(.el-button) {
        flex: 1;
        min-width: 90px;
        max-width: 100px;
      }
    }
  }

  .interval-unit {
    margin-left: 10px;
    color: #606266;
  }

  .dictation-content {
    text-align: center;
    padding: 20px;
  }

  .current-word-display {
    margin-bottom: 30px;

    .current-word {
      font-size: 24px;
      font-weight: 500;
      color: #303133;
      min-height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .progress-info {
      margin-top: 10px;
      color: #909399;
      font-size: 14px;
    }
  }

  .fade-enter-active,
  .fade-leave-active {
    transition: opacity 0.3s;
  }

  .fade-enter-from,
  .fade-leave-to {
    opacity: 0;
  }

  .answer-section {
    max-width: 500px;
    margin: 0 auto;

    .answer-input {
      margin-bottom: 15px;
    }

    .submit-btn {
      width: 100%;
    }
  }

  .control-buttons {
    display: flex;
    justify-content: center;
    gap: 20px;

    :deep(.el-button) {
      padding: 12px;
    }
  }

  .statistics-content {
    .statistic-item {
      text-align: center;
      padding: 10px;

      .statistic-value {
        font-size: 24px;
        font-weight: 600;
        color: #409eff;
      }

      .statistic-label {
        font-size: 14px;
        color: #909399;
        margin-top: 5px;
      }
    }
  }

  .result-content {
    .result-list {
      max-height: 200px;
      overflow-y: auto;
    }

    .result-item {
      padding: 10px;
      border-bottom: 1px solid #ebeef5;
      font-size: 14px;

      &:last-child {
        border-bottom: none;
      }

      &.correct {
        background-color: #f0f9eb;
        border-left: 3px solid #67c23a;
      }

      &.incorrect {
        background-color: #fef0f0;
        border-left: 3px solid #f56c6c;
      }

      .result-question {
        font-weight: 500;
        margin-bottom: 5px;
      }

      .result-answer,
      .result-correct {
        color: #606266;
        margin-bottom: 3px;
      }
    }
  }

  .word-list-container {
    padding: 20px;

    .refresh-btn {
      margin-bottom: 15px;
    }

    .word-list-table {
      .word-english {
        font-weight: 500;
        color: #303133;
      }

      .word-chinese {
        color: #606266;
      }

      .word-phonetic {
        color: #909399;
        font-style: italic;
      }
    }
  }
}
</style>