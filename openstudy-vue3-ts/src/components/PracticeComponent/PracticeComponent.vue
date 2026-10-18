<template>
  <div class="practice-container">
    <!-- 加载动画 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner">
        <div class="loading-ring"></div>
        <div class="loading-text">正在加载题目...</div>
      </div>
    </div>

    <!-- 整体浏览模式 -->
    <template v-if="overviewMode">
      <PracticeHeader :mode="moduleType" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="showSettings = true" />

      <div class="main-content overview-content">
        <div class="overview-question-stream" ref="questionStreamRef" @scroll.passive="onStreamScroll">
          <div v-for="(item, index) in questions" :key="index" class="overview-question-card">
            <div class="overview-card-header">
              <span class="question-number" v-if="overviewMode">第 {{ index + 1 }} 题</span>
              <div v-else class="header-spacer"></div>
              <MarkedButton :question-id="item.id" :bank-id="bankId" size="small" @change="handleMarkedChange(index)" />
              <FavoriteButton type="question" :target-id="item.id" size="small" />
              <el-button v-if="moduleType !== 'mock'" size="small" type="warning" plain
                @click="openAiAnalysisForQuestion(item)">
                <el-icon>
                  <MagicStick />
                </el-icon>
                AI 解析
              </el-button>
            </div>
            <QuestionDisplay :current-question="item" :current-question-index="index" :total-questions="totalQuestions"
              :selected-answer="answers[index]" :sub-fill-blank-answers="subFillBlankAnswers"
              :sub-essay-answers="subEssayAnswers" :answers="answers"
              :show-analysis-immediately="showAnalysisImmediately" :show-question-index="false"
              :overview-mode="true"
              :overview-need-submit="!isExamMode && needsOverviewSubmit(item) && !overviewCommitted[index]"
              :overview-committed="!!overviewCommitted[index]"
              @select-option="(optIdx) => handleOverviewSelect(index, optIdx)"
              @update-answer="(value) => handleOverviewUpdateAnswer(index, value)"
              @select-sub-option="(subIndex, optIdx) => handleOverviewSelectSubOption(index, subIndex, optIdx)"
              @update-sub-fill-blank-answer="(subIndex, value) => handleOverviewUpdateSubFillBlank(index, subIndex, value)"
              @update-sub-essay-answer="(subIndex, value) => handleOverviewUpdateSubEssay(index, subIndex, value)"
              @commit-answer="handleOverviewCommitAnswer(index)"
              @preview-image="openImageViewer" />
          </div>

          <div v-if="moduleType === 'mock' && (isExamMode || isPracticeMode) && !showExamResult"
            class="overview-submit-area">
            <el-button v-if="canGoPrevBatch" @click="handlePrevBatch">上一波</el-button>
            <el-button @click="handleSubmit">提交</el-button>
          </div>

          <div v-if="moduleType === 'mock' && showExamResult" class="overview-submit-area">
            <el-button type="primary" @click="handleFinishExam">结束考试</el-button>
          </div>

          <div v-if="moduleType !== 'mock' && (isExamMode || isPracticeMode)" class="overview-submit-area">
            <template v-if="!hasSubmittedCurrentBatch">
              <el-button v-if="isLastBatch" type="primary" @click="handleContinuePractice">继续刷题</el-button>
              <el-button v-else type="primary" @click="handleContinuePractice">继续刷下一波</el-button>
            </template>
            <template v-else>
              <el-button v-if="canGoPrevBatch" @click="handlePrevBatch">回到上一波</el-button>
              <el-button v-if="isLastBatch" type="primary" @click="$emit('close')">结束</el-button>
              <el-button v-else type="primary" @click="handleContinuePractice">继续刷下一波</el-button>
            </template>
          </div>
        </div>

        <AnswerCard class="answer-card overview-card" :questions="questions" :question-groups="questionGroups"
          :marked-questions="markedQuestionsSet" :favorited-questions="favoritedQuestions" :error-questions="errorQuestions"
          :is-overview-mode="true" :current-highlight-index="highlightedIndex"
          :stats="{ correctCount, wrongCount, accuracy }" :is-exam-mode="isExamMode" :is-practice-mode="isPracticeMode"
          :is-last-question="isLastQuestion" :show-exam-result="showExamResult" :total-score="totalScore"
          :answered-count="answeredCount" :total-count="totalQuestions" :remaining-count="remainingCount"
          :module-type="moduleType" @go-to-question="scrollToQuestion" @toggle-overview="toggleOverview"
          @reset-practice="resetPractice" @submit-exam="handleSubmitExam" @finish-exam="handleFinishExam" />
      </div>
    </template>

    <!-- 逐题模式（原有布局） -->
    <template v-else>
      <PracticeHeader :mode="moduleType" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="showSettings = true" />

      <div class="only-wrong-hint" v-if="moduleSettings.onlyWrong">
        <el-icon>
          <InfoFilled />
        </el-icon>
        <span>当前为错题练习模式，仅展示错题</span>
      </div>

      <div class="main-content">
        <QuestionDisplay :current-question="currentQuestion" :current-question-index="currentQuestionIndex"
          :total-questions="totalQuestions" :selected-answer="selectedAnswer"
          :sub-fill-blank-answers="subFillBlankAnswers" :sub-essay-answers="subEssayAnswers" :answers="answers"
          :show-analysis-immediately="showAnalysisImmediately" @select-option="handleSelectOption"
          @update-answer="value => selectedAnswer = value" @select-sub-option="selectSubOption"
          @update-sub-fill-blank-answer="updateSubFillBlankAnswer" @update-sub-essay-answer="updateSubEssayAnswer"
          @preview-image="openImageViewer" />

        <AnswerCard :questions="questions" :current-question-index="currentQuestionIndex" :stats="{
          correctCount,
          wrongCount,
          accuracy
        }" :is-exam-mode="isExamMode" :is-practice-mode="isPracticeMode" :is-last-question="isLastQuestion"
          :show-exam-result="showExamResult" :total-score="totalScore" :answered-count="answeredCount"
          :total-count="totalQuestions" :remaining-count="remainingCount" :module-type="moduleType"
          :marked-questions="markedQuestionsSet" :favorited-questions="favoritedQuestions" :error-questions="errorQuestions"
          @go-to-question="goToQuestion" @reset-practice="resetPractice" @submit-exam="handleSubmitExam"
          @toggle-overview="toggleOverview" @finish-exam="handleFinishExam" />
      </div>



      <QuestionNavigation :show-prev="currentQuestionIndex > 0" :show-next="currentQuestionIndex < totalQuestions - 1"
        :question-id="currentQuestion?.id" :bank-id="bankId" :module-type="moduleType" :is-exam-mode="isExamMode"
        :is-practice-mode="isPracticeMode" :is-last-question="isLastQuestion" :can-go-prev-batch="canGoPrevBatch"
        :is-last-batch="isLastBatch" :has-submitted-current-batch="hasSubmittedCurrentBatch"
        :show-submit-button="(isExamMode || isPracticeMode) && moduleType !== 'mock'" @prev-question="prevQuestion"
        @next-question="nextQuestion" @mark="markQuestion" @add-note="addNote" @report="reportQuestion"
        @ai-analyze="openAiAnalysis" @submit-exam="handleSubmit" @prev-batch="handlePrevBatch"
        @close="$emit('close')" />
    </template>

    <!-- AI 解析弹窗 -->
    <AiAnalysisDialog v-if="showAnalysisDialog"
      :question="getAnalysisQuestionText(analysisTargetQuestion)"
      :question-id="analysisTargetQuestion?.id" :question-type="getQuestionTypeName(analysisTargetQuestion?.type)"
      :options="formatOptionsForAnalysis(analysisTargetQuestion)"
      :correct-answer="analysisTargetQuestion?.correctAnswer" :cached-content="currentAnalysisContent"
      :sub-questions="analysisTargetQuestion?.subQuestions || []"
      :is-generating="isAnalysisGenerating" @close="handleAnalysisClose"
      @update-cache="(content) => updateAnalysisCache(analysisTargetQuestion?.id, content)"
      @generating="setAnalysisGenerating" />

    <!-- 刷题设置弹窗 -->
    <PracticeSettings v-model="showSettings" :default-module="moduleType" @save="handleSettingsSave" />

    <!--
      滚动按钮（回到顶部 / 跳到底部）

      ⚠️ **不要传 scroll-container**（用户 2026-10-18 bug4）。
         实测这页真正在滚的是**外壳内容区 `.os-content`**（sh 4938 / ch 948），
         而 `.overview-question-stream` 自己 `scrollHeight === clientHeight`（不滚），
         `document.documentElement` 也不滚（整页高度 = 视口）。
         写死任何一个都会踩空。
      所以交给 ScrollButton 自己从挂载点向上找"内容确实溢出"的可滚动祖先，
      这样不管是单题模式、浏览模式，还是将来换外壳，都能自动对上。
    -->
    <ScrollButton :bottom="24" :right="24" />

    <ImageViewer v-model:visible="viewerVisible" :src="viewerSrc" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, getCurrentInstance, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { InfoFilled, RefreshRight, MagicStick } from '@element-plus/icons-vue'
import PracticeHeader from './PracticeHeader.vue'
import QuestionDisplay from './QuestionDisplay.vue'
import AnswerCard from './AnswerCard.vue'
import QuestionNavigation from './QuestionNavigation.vue'
import PracticeSettings from './PracticeSettings.vue'
import MarkedButton from '@/components/MarkedButton/MarkedButton.vue'
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
import ScrollButton from '@/components/ScrollButton/ScrollButton.vue'
import ImageViewer from './ImageViewer.vue'
import { useQuestionPractice } from '@/composables/useQuestionPractice'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import AiAnalysisDialog from '@/components/AiAnalysisDialog/index.vue'

// 调试日志工具
import {
  debugEnterModule,
  debugLeaveModule,
  debugWatchTrigger,
  debugStateSnapshot
} from '@/utils/practiceDebug'

const props = defineProps({
  bankId: { type: Number, required: true },
  bankName: { type: String, default: '题库' },
  moduleType: {
    type: String,
    required: true,
    validator: (val: any) => ['sequential', 'random', 'custom', 'mock'].includes(val)
  }
})

const emit = defineEmits(['close'])

const store = usePracticeSettingsStore()

const moduleSettings = computed(() => {
  return store.getModuleSettings(props.moduleType)
})

const isExamMode = computed(() => moduleSettings.value.practiceMode === 'exam')
const isPracticeMode = computed(() => moduleSettings.value.practiceMode === 'practice')
const showAnalysisImmediately = computed(() => !isExamMode.value || showExamResult.value)
const canGoPrevBatch = computed(() => questionOffset.value > 0 && (isExamMode.value || isPracticeMode.value))
const isLastQuestion = computed(() => currentQuestionIndex.value === totalQuestions.value - 1)
const isLastBatch = computed(() => allQuestionsData.value.length <= questionOffset.value + totalQuestions.value)

const showSettings = ref(false)
const showExamResult = ref(false)
const totalScore = ref(0)
const showAnalysisDialog = ref(false)
const viewerVisible = ref(false)
const viewerSrc = ref('')
const hasSubmittedCurrentBatch = ref(false)
const isFirstLoaded = ref(false)

const examTimeLimit = computed(() => moduleSettings.value.examTimeLimit || 60)
const remainingTime = ref(0)
const examTimer = ref<ReturnType<typeof setInterval> | null>(null)
const EXAM_END_TIME_KEY = 'openstudy_exam_end_time'
const EXAM_BANK_ID_KEY = 'openstudy_exam_bank_id'

// 全局标志，防止多个弹窗
let isTimeUpDialogShowing = false

const formattedRemainingTime = computed(() => {
  const minutes = Math.floor(remainingTime.value / 60)
  const seconds = remainingTime.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})

const isTimeWarning = computed(() => remainingTime.value > 0 && remainingTime.value <= 300)
const isTimeDanger = computed(() => remainingTime.value > 0 && remainingTime.value <= 60)

function startExamTimer() {
  if (props.moduleType !== 'mock') return
  // 如果已经显示考试结果，不启动计时器
  if (showExamResult.value) {
    console.log(`[EXAM] 跳过启动计时器（已显示考试结果）`)
    return
  }

  // 先停止现有定时器，防止重复启动
  stopExamTimer()

  // 检查是否有保存的考试结束时间（同一个题库）
  const savedEndTime = localStorage.getItem(EXAM_END_TIME_KEY)
  const savedBankId = localStorage.getItem(EXAM_BANK_ID_KEY)
  const now = Date.now()

  if (savedEndTime && savedBankId === String(props.bankId)) {
    const endTime = parseInt(savedEndTime)
    if (now < endTime) {
      // 还有剩余时间，继续倒计时
      remainingTime.value = Math.ceil((endTime - now) / 1000)
      console.log(`[EXAM] 恢复考试计时器, 剩余: ${remainingTime.value}秒`)
    } else {
      // 时间已到，静默清除存储，不弹窗（用户离开期间时间已过）
      console.log(`[EXAM] 离开期间时间已过，静默清除`)
      remainingTime.value = 0
      clearExamStorage()
      // 不调用 handleTimeUp，让用户重新开始
      return
    }
  } else {
    // 新的考试，设置结束时间
    const totalSeconds = examTimeLimit.value * 60
    const endTime = now + totalSeconds * 1000
    localStorage.setItem(EXAM_END_TIME_KEY, String(endTime))
    localStorage.setItem(EXAM_BANK_ID_KEY, String(props.bankId))
    remainingTime.value = totalSeconds
    console.log(`[EXAM] 启动考试计时器, 总时间: ${totalSeconds}秒`)
  }

  // 启动定时器更新显示
  examTimer.value = setInterval(() => {
    const currentTime = Date.now()
    const endTime = parseInt(localStorage.getItem(EXAM_END_TIME_KEY) || '')

    if (!endTime || currentTime >= endTime) {
      // 停止定时器
      stopExamTimer()
      clearExamStorage()
      remainingTime.value = 0

      // 只有在页面可见且没有弹窗显示时才弹窗提示
      if (!document.hidden && !isTimeUpDialogShowing) {
        handleTimeUp()
      }
    } else {
      remainingTime.value = Math.ceil((endTime - currentTime) / 1000)
    }
  }, 1000)
}

function stopExamTimer() {
  if (examTimer.value) {
    console.log(`[EXAM] 停止计时器`)
    clearInterval(examTimer.value)
    examTimer.value = null
  }
}

function clearExamStorage() {
  localStorage.removeItem(EXAM_END_TIME_KEY)
  localStorage.removeItem(EXAM_BANK_ID_KEY)
}

function handleTimeUp() {
  // 如果已经显示弹窗或已显示考试结果，不再重复处理
  if (isTimeUpDialogShowing || showExamResult.value) {
    console.log(`[EXAM] 跳过 handleTimeUp（弹窗已显示或已显示结果）`)
    return
  }

  isTimeUpDialogShowing = true
  console.log(`[EXAM] handleTimeUp 被调用`)

  ElMessageBox.alert('考试时间已到，系统将自动提交试卷！', '时间到', {
    confirmButtonText: '确定',
    type: 'warning',
    showClose: false,
    closeOnClickModal: false,
    closeOnPressEscape: false
  }).then(() => {
    console.log(`[EXAM] 用户点击确定，提交试卷`)
    isTimeUpDialogShowing = false
    handleSubmitExam()
  }).catch(() => {
    console.log(`[EXAM] 弹窗被关闭，提交试卷`)
    isTimeUpDialogShowing = false
    handleSubmitExam()
  })
}

// 页面可见性变化处理
function handleVisibilityChange() {
  if (document.hidden) {
    // 页面隐藏，停止定时器（但不清除结束时间）
    console.log(`[EXAM] 页面隐藏，暂停定时器`)
    stopExamTimer()
  } else {
    // 页面显示，恢复定时器（复用 startExamTimer 逻辑）
    if (props.moduleType === 'mock' && !showExamResult.value) {
      console.log(`[EXAM] 页面显示，恢复定时器`)
      startExamTimer()
    }
  }
}

watch(() => props.moduleType, (newType, oldType) => {
  // 调试日志
  debugWatchTrigger('moduleType', newType, newType, oldType)

  // 当 moduleType 从有效值变为 undefined（路由过渡）时，保存旧模块状态
  if (newType === undefined && oldType && oldType !== 'null') {
    // 路由过渡，保存旧模块状态
    saveCurrentAnswerState(oldType)
    return
  }

  if (newType === 'mock' && !showExamResult.value) {
    startExamTimer()
  } else {
    stopExamTimer()
    remainingTime.value = 0
    clearExamStorage()
  }

  // 只在模式切换时重置（新值有效，且不是首次加载）
  // oldType 为 undefined 表示路由切换过渡，也需要触发重置
  if (newType && newType !== oldType && oldType !== null) {
    debugLeaveModule(oldType || 'unknown', props.bankId)
    debugEnterModule(newType, props.bankId)
    // 传入旧的 moduleType，用于保存旧模块的答题状态
    resetAndFetchQuestions(oldType)
  }
})

watch(showExamResult, (val) => {
  console.log(`[EXAM] showExamResult 变化: ${val}, moduleType: ${props.moduleType}`)
  if (val) {
    stopExamTimer()
    isTimeUpDialogShowing = false
  } else if (props.moduleType === 'mock') {
    isTimeUpDialogShowing = false
    startExamTimer()
  }
})

onMounted(() => {
  // 调试日志
  debugEnterModule(props.moduleType, props.bankId)

  if (!isFirstLoaded.value && props.bankId && props.bankId > 0) {
    isFirstLoaded.value = true
    fetchQuestions()
  }
  if (props.moduleType === 'mock' && !showExamResult.value) {
    startExamTimer()
  }

  // 添加页面可见性变化监听
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onUnmounted(() => {
  // 调试日志
  debugLeaveModule(props.moduleType, props.bankId)

  // 保存答题状态
  saveCurrentAnswerState()

  stopExamTimer()

  // 移除页面可见性变化监听
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

const overviewMode = computed({
  get: () => moduleSettings.value.isOverviewMode || false,
  set: (val) => store.saveModuleSettings(props.moduleType, { isOverviewMode: val })
})
const highlightedIndex = ref(0)
const markedQuestions = ref<number[]>([])
const markedQuestionsSet = computed(() => {
  const set = new Set<number>()
  // 后端斩题状态（ID-based）
  backendMarkedSet.value.forEach(id => set.add(Number(id)))
  // 本地 UI 标记（index-based → 转换为 ID）
  markedQuestions.value.forEach(idx => {
    const q = questions.value[idx]
    if (q && q.id != null) set.add(Number(q.id))
  })
  return set
})
let scrollDebounceTimer: ReturnType<typeof setTimeout> | null = null
let scrollLock = false
const questionStreamRef = ref<HTMLElement | null>(null)

const typeLabelMap: Record<string, string> = {
  single: '单选题', multiple: '多选题', truefalse: '判断题',
  fillblank: '填空题', essay: '问答题', readingComprehension: '组合题', cloze: '完形填空'
}

const questionGroups = computed(() => {
  const groupMap: Record<string, any> = {}
  const qs = questions.value

  qs.forEach((q, i) => {
    const label = typeLabelMap[q.type] || '其他'
    if (!groupMap[label]) {
      groupMap[label] = {
        typeLabel: label,
        typeName: q.type,
        startIndex: i,
        endIndex: i,
        items: []
      }
    }
    groupMap[label].endIndex = i
    groupMap[label].items.push({ ...q, index: i })
  })

  return Object.values(groupMap)
})

const answeredCount = computed(() => answers.value.filter(a => a !== null).length)
const remainingCount = computed(() => totalQuestions.value - answeredCount.value)

const toggleOverview = () => {
  if (overviewMode.value) {
    store.saveModuleSettings(props.moduleType, { overviewScrollIndex: highlightedIndex.value })
  }
  overviewMode.value = !overviewMode.value
}

const scrollToQuestion = (index: number) => {
  if (!questionStreamRef.value) return
  scrollLock = true
  highlightedIndex.value = index
  const children = questionStreamRef.value.children
  if (children && children[index]) {
    ;(children[index] as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  setTimeout(() => { scrollLock = false }, 600)
}

const onStreamScroll = () => {
  if (scrollLock) return
  if (scrollDebounceTimer) clearTimeout(scrollDebounceTimer)
  scrollDebounceTimer = setTimeout(() => {
    if (!questionStreamRef.value) return
    const scrollTop = questionStreamRef.value.scrollTop
    if (scrollTop !== undefined) {
      const idx = Math.round(scrollTop / 120)
      if (idx >= 0 && idx < questions.value.length) {
        highlightedIndex.value = idx
      }
    }
  }, 200)
}

const handleMarkedChange = (index: number) => {
  const q = questions.value[index]
  const qid = q && q.id != null ? Number(q.id) : null
  const set = new Set(markedQuestions.value)
  if (set.has(index)) {
    set.delete(index)
    if (qid != null) backendMarkedSet.value.delete(qid)
  } else {
    set.add(index)
    if (qid != null) backendMarkedSet.value.add(qid)
  }
  markedQuestions.value = [...set]
  store.saveModuleSettings(props.moduleType, { markedQuestions: markedQuestions.value })
}

/*
 * ==================== 整体浏览模式：作答 → 判题 ====================
 *
 * 用户 2026-10-18 报的 bug2：
 *   浏览模式下**单选**点一下就出答案（这是设计初衷），
 *   但**多选 / 填空 / 简答**也被同样对待：
 *     · 多选：刚点第一个选项就判了（必然错），没法选第二个；
 *     · 填空：输入第一个字符就提交了，后面全被"判错"；
 *     · 简答：同样，写一个字就判。
 *
 * 修法：按题型分流。
 *   · `single` / `truefalse` → 选完**立即判**（保留初衷，不用多点一次）；
 *   · `multiple` / `fillblank` / `essay` / 组合题子题 → 只记录答案，
 *     等用户在题目下方点「提交答案」才判（见 `handleOverviewCommitAnswer`）。
 *
 * 为什么用"是否即时判"的判定函数、而不是在模板里散写条件：
 *   同一套判断在 4 个入口（选项 / 子选项 / 填空 / 简答）都要用，
 *   QuestionDisplay 也要用它决定显示"提交答案"按钮还是直接出解析。
 */

/** 这类题型"选一个就能定论"，可以即时判；其余需要用户确认后再判 */
function isInstantJudgeType(type: string | undefined) {
  return type === 'single' || type === 'truefalse'
}

/** 该题（在浏览模式下）是否已经提交过答案 */
const overviewCommitted = ref<Record<number, boolean>>({})

/** 浏览模式下：这道题要不要显示「提交答案」按钮 */
function needsOverviewSubmit(q: any): boolean {
  if (!q) return false
  if (isInstantJudgeType(q.type)) return false
  // 组合题：只有存在子题时才需要（子题逐题提交）
  if (q.type === 'composite') {
    return Array.isArray(q.subQuestions) && q.subQuestions.length > 0
  }
  return true
}

/**
 * 浏览模式下用户点「提交答案」→ 真正判题
 *
 * 同时把 `overviewCommitted[qIndex]` 置真：QuestionDisplay 据此把
 * 「提交答案」换成解析（它已经通过 `showAnalysisImmediately` 拿到结果）。
 */
function handleOverviewCommitAnswer(qIndex: number) {
  if (currentQuestionIndex.value !== qIndex) {
    currentQuestionIndex.value = qIndex
  }
  const q = questions.value[qIndex]
  // 空答案（没选 / 没填）不判，避免用户点一下就判错
  const val = answers.value[qIndex]
  const empty = val === null || val === undefined || val === '' || (Array.isArray(val) && val.length === 0)
  if (empty) {
    ElMessage.warning(q?.type === 'essay' ? '请先写下你的答案' : '请先作答再提交')
    return
  }
  overviewCommitted.value[qIndex] = true
  handleAnswerSubmission(qIndex)
}

const handleOverviewSelect = (qIndex: number, optIdx: number) => {
  if (currentQuestionIndex.value !== qIndex) {
    if (currentQuestion.value && !['readingComprehension', 'cloze'].includes(currentQuestion.value.type) && selectedAnswer.value !== null && answers.value[currentQuestionIndex.value] === null) {
      handleAnswerSubmission(currentQuestionIndex.value)
    }
    currentQuestionIndex.value = qIndex
  }
  selectedAnswer.value = answers.value[qIndex] ?? (questions.value[qIndex]?.type === 'multiple' ? [] : null)
  selectOption(optIdx)
  answers.value[qIndex] = selectedAnswer.value
  if (questions.value[qIndex]) {
    questions.value[qIndex].answered = true
  }
  // 单选/判断：即时判（原行为）；多选：等用户点「提交答案」
  if (!isExamMode.value && isInstantJudgeType(questions.value[qIndex]?.type)) {
    handleAnswerSubmission(qIndex)
  }
}

const handleOverviewUpdateAnswer = (qIndex: number, value: any) => {
  if (currentQuestionIndex.value !== qIndex) {
    currentQuestionIndex.value = qIndex
  }
  selectedAnswer.value = value
  answers.value[qIndex] = value
  if (questions.value[qIndex]) {
    questions.value[qIndex].answered = true
  }
  // 填空/简答是"边写边改"，**不能**每次输入都判题（原来这里会立刻判错）。
  // 只有单选/判断这类"一下就定"的题型才即时判。
  if (!isExamMode.value && isInstantJudgeType(questions.value[qIndex]?.type)) {
    handleAnswerSubmission(qIndex)
  }
}

const handleOverviewSelectSubOption = (qIndex: number, subIndex: number, optIdx: number) => {
  if (currentQuestionIndex.value !== qIndex) {
    currentQuestionIndex.value = qIndex
  }
  selectSubOption(subIndex, optIdx)
  answers.value = [...answers.value]
}

const handleOverviewUpdateSubFillBlank = (qIndex: number, subIndex: number, value: any) => {
  if (currentQuestionIndex.value !== qIndex) {
    currentQuestionIndex.value = qIndex
  }
  updateSubFillBlankAnswer(subIndex, value)
  // 组合题子题（填空）：同样不即时判，等用户点「提交答案」
}

const handleOverviewUpdateSubEssay = (qIndex: number, subIndex: number, value: any) => {
  if (currentQuestionIndex.value !== qIndex) {
    currentQuestionIndex.value = qIndex
  }
  updateSubEssayAnswer(subIndex, value)
  // 组合题子题（简答）：不即时判
}

const jumpToNextBatch = () => {
  hasSubmittedCurrentBatch.value = false
  showExamResult.value = false
  totalScore.value = 0
  const count = moduleSettings.value.questionCount || 10
  questionOffset.value = questionOffset.value + count
  loadBatchWithoutReset()
  if (props.moduleType === 'mock') {
    startExamTimer()
  }
  setTimeout(() => {
    if (overviewMode.value) {
      const firstCard = document.querySelector('.overview-question-card')
      if (firstCard) {
        firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } else {
      goToQuestion(0)
    }
  }, 150)
}

const handleContinuePractice = () => {
  if (showExamResult.value) {
    ElMessageBox.confirm('是否留在当前页面继续查看解析？', '查看解析', {
      confirmButtonText: '留在本页',
      cancelButtonText: '继续刷题',
      type: 'info'
    }).then(() => {
      showExamResult.value = true
    }).catch(() => {
      showExamResult.value = false
      totalScore.value = 0
      const count = moduleSettings.value.questionCount || 10
      questionOffset.value = questionOffset.value + count
      loadBatchWithoutReset()
      setTimeout(() => {
        if (overviewMode.value) {
          const firstCard = document.querySelector('.overview-question-card')
          if (firstCard) {
            firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }
        } else {
          goToQuestion(0)
        }
      }, 150)
    })
    return
  }

  const unanswered = totalQuestions.value - answeredCount.value
  const hasMoreQuestions = allQuestionsData.value.length > questionOffset.value + totalQuestions.value
  if (unanswered > 0) {
    ElMessageBox.confirm(`您还有 ${unanswered} 题未作答，是否继续提交并查看解析？`, '提示', {
      confirmButtonText: '继续提交',
      cancelButtonText: '继续答题',
      type: 'warning'
    }).then(() => {
      hasSubmittedCurrentBatch.value = true
      if (isLastBatch.value) {
        handleSubmitExam()
      } else if (hasMoreQuestions) {
        ElMessageBox.confirm('恭喜完成！是否继续刷下一波题目？', '继续刷题', {
          confirmButtonText: '继续刷下一波',
          cancelButtonText: '查看结果',
          type: 'success'
        }).then(() => {
          jumpToNextBatch()
        }).catch(() => {
          handleSubmitExam()
        })
      } else {
        handleSubmitExam()
      }
    }).catch(() => {
      hasSubmittedCurrentBatch.value = true
    })
  } else {
    handleSubmitExam()
    hasSubmittedCurrentBatch.value = true
    if (isLastBatch.value) {
      // Last batch, just show results
    } else if (hasMoreQuestions) {
      ElMessageBox.confirm('恭喜完成！是否继续刷下一波题目？', '继续刷题', {
        confirmButtonText: '继续刷下一波',
        cancelButtonText: '查看结果',
        type: 'success'
      }).then(() => {
        jumpToNextBatch()
      }).catch(() => {
        handleSubmitExam()
      })
    }
  }
}

const handlePrevBatch = () => {
  hasSubmittedCurrentBatch.value = false
  showExamResult.value = false
  totalScore.value = 0
  const count = moduleSettings.value.questionCount || 10
  const newOffset = questionOffset.value - count
  questionOffset.value = Math.max(0, newOffset)
  loadBatchWithoutReset()
  setTimeout(() => {
    if (overviewMode.value) {
      const firstCard = document.querySelector('.overview-question-card')
      if (firstCard) {
        firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    } else {
      goToQuestion(0)
    }
  }, 150)
}

const handleSettingsSave = (data: { moduleType: string; settings: any }) => {
  const { settings } = data
  if (settings.questionCount !== moduleSettings.value.questionCount) {
    updateQuestionCountAndSlice(settings.questionCount)
  }
}

const handleSubmit = () => {
  if (props.moduleType === 'mock') {
    const unanswered = totalQuestions.value - answeredCount.value
    let msg = `确定要交卷吗？`
    if (unanswered > 0) {
      msg = `您还有 ${unanswered} 题未作答，确定要交卷吗？`
    }
    ElMessageBox.confirm(msg, '确认提交', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      handleSubmitExam()
    }).catch(() => { })
    return
  }

  const unanswered = totalQuestions.value - answeredCount.value
  const hasMoreQuestions = allQuestionsData.value.length > questionOffset.value + totalQuestions.value

  if (unanswered > 0) {
    ElMessageBox.confirm(`您还有 ${unanswered} 题未作答，是否继续提交并查看解析？`, '提示', {
      confirmButtonText: '继续提交',
      cancelButtonText: '继续刷题',
      type: 'warning'
    }).then(() => {
      handleSubmitExam()
      hasSubmittedCurrentBatch.value = true
      if (hasMoreQuestions) {
        ElMessageBox.confirm('恭喜完成！是否继续刷下一波题目？', '继续刷题', {
          confirmButtonText: '继续刷下一波',
          cancelButtonText: '查看结果',
          type: 'success'
        }).then(() => {
          jumpToNextBatch()
        }).catch(() => {
          handleSubmitExam()
          hasSubmittedCurrentBatch.value = true
        })
      }
    }).catch(() => {
      handleSubmitExam()
      hasSubmittedCurrentBatch.value = true
    })
  } else {
    handleSubmitExam()
    hasSubmittedCurrentBatch.value = true
    if (hasMoreQuestions) {
      if (isExamMode.value) {
        ElMessageBox.confirm('恭喜完成！是否继续刷下一波题目？', '继续刷题', {
          confirmButtonText: '继续刷下一波',
          cancelButtonText: '查看结果',
          type: 'success'
        }).then(() => {
          jumpToNextBatch()
        }).catch(() => {
          handleSubmitExam()
          hasSubmittedCurrentBatch.value = true
        })
      } else {
        ElMessageBox.confirm('恭喜完成！是否继续刷下一波题目？', '继续刷题', {
          confirmButtonText: '继续刷下一波',
          cancelButtonText: '查看结果',
          type: 'success'
        }).then(() => {
          jumpToNextBatch()
        }).catch(() => {
          handleSubmitExam()
          hasSubmittedCurrentBatch.value = true
        })
      }
    }
  }
}

const { proxy } = getCurrentInstance() as any

const {
  questions,
  currentQuestionIndex,
  selectedAnswer,
  answers,
  loading,
  subFillBlankAnswers,
  subEssayAnswers,
  questionOffset,
  allQuestionsData,
  isResetting,
  currentQuestion,
  totalQuestions,
  correctCount,
  wrongCount,
  accuracy,
  displayOptions,
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
  collectQuestion,
  markQuestion,
  addNote,
  reportQuestion,
  favoritedQuestions,
  markedQuestions: backendMarkedSet,
  errorQuestions,
  updateOnlyWrong,
  updateQuestionCount,
  updateQuestionOffset,
  applyQuestionLimits,
  loadBatchWithoutReset,
  updateQuestionCountAndSlice,
  saveCurrentAnswerState,
  clearAnswerStateCache
} = useQuestionPractice(props, { proxy }, {
  questionCount: moduleSettings.value.questionCount,
  onlyWrong: moduleSettings.value.onlyWrong
})

const handleSubmitExam = () => {
  showAllAnalysis()
  const score = Math.round((correctCount.value / totalQuestions.value) * 100)
  totalScore.value = score
  showExamResult.value = true
  // 清除考试计时器存储
  clearExamStorage()
  stopExamTimer()
}

// 结束考试：清空模拟考试缓存并关闭
const handleFinishExam = () => {
  console.log(`[EXAM] handleFinishExam 被调用`)
  // 重置考试结果状态
  showExamResult.value = false
  totalScore.value = 0
  hasSubmittedCurrentBatch.value = false
  // 清空模拟考试的答题状态缓存
  clearAnswerStateCache('mock')
  console.log(`[EXAM] 缓存已清空，准备关闭页面`)
  // 关闭页面
  emit('close')
}

watch(() => moduleSettings.value.questionCount, (val) => {
  // 如果正在重置中，跳过（防止二次触发）
  if (isResetting.value) return
  updateQuestionCountAndSlice(val)
})

watch(() => moduleSettings.value.onlyWrong, (val) => {
  // 如果正在重置中，跳过（防止二次触发）
  if (isResetting.value) return
  updateOnlyWrong(val)
  fetchQuestions()
})

watch(overviewMode, (val) => {
  if (val) {
    const savedIndex = moduleSettings.value.overviewScrollIndex || 0
    if (savedIndex > 0 && questionStreamRef.value) {
      setTimeout(() => {
        if (!questionStreamRef.value) return
        const children = questionStreamRef.value.children
        if (children && children[savedIndex]) {
          ;(children[savedIndex] as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
        highlightedIndex.value = savedIndex
      }, 100)
    }
  }
})

function openImageViewer(src: string) {
  viewerSrc.value = src
  viewerVisible.value = true
}

function openAiAnalysis() {
  const questionId = currentQuestion.value?.id
  if (!questionId) return
  analysisTargetQuestion.value = currentQuestion.value
  if (analysisCache.value.has(questionId)) {
    currentAnalysisContent.value = analysisCache.value.get(questionId) as string
  } else {
    currentAnalysisContent.value = ''
  }
  showAnalysisDialog.value = true
}

function openAiAnalysisForQuestion(question: any) {
  const questionId = question?.id
  if (!questionId) return
  analysisTargetQuestion.value = question
  if (analysisCache.value.has(questionId)) {
    currentAnalysisContent.value = analysisCache.value.get(questionId) as string
  } else {
    currentAnalysisContent.value = ''
  }
  showAnalysisDialog.value = true
}

function getQuestionTypeName(type: string) {
  const typeMap: Record<string, string> = {
    single: '单选题', multiple: '多选题', truefalse: '判断题',
    fillblank: '填空题', essay: '简答题', readingComprehension: '组合题', cloze: '组合题'
  }
  return typeMap[type] || type
}

function formatOptionsForAnalysis(question: any) {
  if (!question || !question.options) return ''
  if (Array.isArray(question.options)) return JSON.stringify(question.options)
  return question.options
}

// 获取用于 AI 解析的题目文本
function getAnalysisQuestionText(question: any) {
  if (!question) return ''

  // 对于组合题（阅读理解、完形填空），需要包含主内容
  if (question.type === 'readingComprehension' || question.type === 'cloze') {
    const parts: string[] = []
    if (question.mainTitle) parts.push(question.mainTitle)
    if (question.mainContent) parts.push(question.mainContent)
    if (parts.length > 0) return parts.join('\n\n')
  }

  // 普通题目：优先使用 question 字段，其次尝试 questionText
  return question.question || question.questionText || question.title || ''
}

const analysisCache = ref(new Map<any, string>())
const currentAnalysisContent = ref('')
const isAnalysisGenerating = ref(false)
const analysisTargetQuestion = ref<any>(null)

function updateAnalysisCache(questionId: any, content: string) {
  analysisCache.value.set(questionId, content)
}

function setAnalysisGenerating(generating: boolean) {
  isAnalysisGenerating.value = generating
}

function handleAnalysisClose() {
  showAnalysisDialog.value = false
  isAnalysisGenerating.value = false
}

function handleSelectOption(index: number) {
  selectOption(index)

  if (isExamMode.value) return
  if (!moduleSettings.value.autoNextOnCorrect) return

  const q = currentQuestion.value
  if (!q) return

  if (q.type === 'single' || q.type === 'truefalse') {
    if (selectedAnswer.value === q.correctAnswer && currentQuestionIndex.value < totalQuestions.value - 1) {
      nextQuestion()
    }
  } else if (q.type === 'multiple') {
    const selected = Array.isArray(selectedAnswer.value) ? selectedAnswer.value : []
    const correct = Array.isArray(q.correctAnswer) ? q.correctAnswer : []
    if (selected.length === correct.length && selected.every(v => correct.includes(v))) {
      if (currentQuestionIndex.value < totalQuestions.value - 1) {
        nextQuestion()
      }
    }
  }
}

defineExpose({})
</script>

<style scoped>
.only-wrong-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin: 0 24px;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  font-size: 13px;
  color: #92400e;
}

.continue-practice-area {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 20px 0;
  position: sticky;
  bottom: 20px;
  background: white;
  z-index: 10;
}

.continue-practice-area .el-button {
  border-radius: 8px;
  font-weight: 500;
  padding: 12px 40px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.overview-submit-area {
  display: flex;
  justify-content: center;
  gap: 12px;
  padding: 20px 0;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.95);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.loading-ring {
  width: 56px;
  height: 56px;
  border: 4px solid #e5e7eb;
  border-top-color: #6b9ac9;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.loading-text {
  font-size: 15px;
  color: #6b7280;
  letter-spacing: 1px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

<style src="@/assets/styles/PracticeComponent.css"></style>