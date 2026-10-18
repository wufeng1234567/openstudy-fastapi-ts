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
              <!--
                题号必须**跨波顺延**（用户 2026-10-18：「点击下一波后还是 1 到 20，
                应该要顺延」）。
                原来写的是 `index + 1`，而 `questions` 是分波切片，每波下标都从 0 起 ——
                所以第二波又从"第 1 题"开始。改成 `numberBase + index + 1`。
              -->
              <span class="question-number" v-if="overviewMode">第 {{ numberBase + index + 1 }} 题</span>
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

          <!--
            浏览模式底部操作区（用户 2026-10-18 的分波规则）
            ================================================
            规则（逐题模式与浏览模式一致）：
              · 第一波            → 只显示「继续下一波」（不显示"回到上一波"）
              · 中间波            → 「回到上一波」+「继续下一波」
              · 最后一波          → 「回到上一波」+「提交」（不再显示"继续下一波"）
            说明：这里用 `canGoNextBatch` 而不是判断 `hasSubmittedCurrentBatch` ——
                  "有没有提交这一波"是状态，跟"是不是最后一波"是两件正交的事，
                  混在一起会导致最后一波提交后按钮突然消失。
          -->
          <div v-if="(moduleType === 'mock' || isExamMode || isPracticeMode) && !showExamResult"
            class="overview-submit-area">
            <el-button v-if="canGoPrevBatch" @click="handlePrevBatch">回到上一波</el-button>
            <el-button v-if="canGoNextBatch" type="primary" @click="handleContinuePractice">
              继续下一波
            </el-button>
            <el-button v-else type="primary" @click="handleSubmit">提交</el-button>
          </div>

          <div v-if="showExamResult" class="overview-submit-area">
            <el-button type="primary" @click="handleFinishExam">结束</el-button>
          </div>
        </div>

        <AnswerCard class="answer-card overview-card" :questions="questions" :question-groups="questionGroups"
          :marked-questions="markedQuestionsSet" :favorited-questions="favoritedQuestions" :error-questions="errorQuestions"
          :is-overview-mode="true" :current-highlight-index="highlightedIndex"
          :stats="{ correctCount, wrongCount, accuracy }" :is-exam-mode="isExamMode" :is-practice-mode="isPracticeMode"
          :is-last-question="isLastQuestion" :show-exam-result="showExamResult" :total-score="totalScore"
          :answered-count="answeredCount" :total-count="totalQuestions" :remaining-count="remainingCount"
          :module-type="moduleType" :draft-state="draftState" :draft-button-text="draftButtonText" :number-base="numberBase"
          @go-to-question="scrollToQuestion" @toggle-overview="toggleOverview"
          @reset-practice="resetPractice" @submit-exam="handleSubmitExam" @finish-exam="handleFinishExam"
          @save-draft="handleManualSaveDraft" />
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
          :total-questions="totalQuestions" :number-offset="numberBase" :selected-answer="selectedAnswer"
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
          :draft-state="draftState" :draft-button-text="draftButtonText" :number-base="numberBase"
          @go-to-question="goToQuestion" @reset-practice="resetPractice" @submit-exam="handleSubmitExam"
          @toggle-overview="toggleOverview" @finish-exam="handleFinishExam"
          @save-draft="handleManualSaveDraft" />
      </div>



      <QuestionNavigation :show-prev="currentQuestionIndex > 0" :show-next="currentQuestionIndex < totalQuestions - 1"
        :question-id="currentQuestion?.id" :bank-id="bankId" :module-type="moduleType" :is-exam-mode="isExamMode"
        :is-practice-mode="isPracticeMode" :is-last-question="isLastQuestion" :can-go-prev-batch="canGoPrevBatch"
        :is-last-batch="isLastBatch" :has-submitted-current-batch="hasSubmittedCurrentBatch"
        :show-submit-button="(isExamMode || isPracticeMode) && moduleType !== 'mock'" @prev-question="prevQuestion"
        @next-question="nextQuestion" @mark="markQuestion" @add-note="addNote" @report="reportQuestion"
        @ai-analyze="openAiAnalysis" @submit-exam="handleSubmit" @prev-batch="handlePrevBatch"
        @next-batch="jumpToNextBatch"
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
import { ElMessage, ElMessageBox } from 'element-plus'
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
import useUserStore from '@/store/modules/user'
import {
  createDraftSaver,
  loadDraft,
  clearDraft,
  type DraftSaveState
} from '@/utils/practiceDraft'
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

/**
 * 本波第一题在整个题库里的**序号偏移**
 * ------------------------------------------------------------------
 * 题号要跨波顺延（用户 2026-10-18：「点下一波还是 1 到 20，应该要顺延」）。
 *
 * `questions` 是 `allQuestionsData` 的切片（`[questionOffset, +count)`），
 * 所以波内下标 `i` 对应的全局序号是 `questionOffset + i + 1`。
 *
 * ⚠️ 直接等于 `questionOffset`，不要再加判断分支：
 *    第一波 offset=0 → 1 开始；第二波 offset=20 → 21 开始。所有展示处共用它，
 *    避免"卡片顺延了、答题卡没顺延"这种不一致。
 */
const numberBase = computed(() => Number(questionOffset.value) || 0)
/**
 * 是否已经是**最后一波**
 *
 * 语义：这一波之后没有更多题了。
 * 例：100 题、每波 20 题、当前第 5 波（offset=80）→ 80+20=100 ≤ 100 → 是最后一波。
 *
 * ⚠️ 用 `<=` 而不是 `<`：正好整除时（100/20）最后一波的末尾 offset+total 恰好 == 总题数，
 *    必须是"最后一波"；用 `<` 会把它判成"还有下一波"，于是最后一波还显示"继续下一波"、
 *    点进去是空波。之前这里是 `<=`，保持正确，勿改回。
 */
const isLastBatch = computed(() => allQuestionsData.value.length <= questionOffset.value + totalQuestions.value)

/**
 * 是否还能「继续下一波」
 *
 * 用户 2026-10-18 的分波规则：
 *   · 最后一波结尾 → **不显示**「继续下一波」，只显示「回到上一波」+「提交」；
 *   · 其余情况（含第一波）→ 显示「继续下一波」。
 */
const canGoNextBatch = computed(() => !isLastBatch.value)

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
    fetchQuestions().then(() => {
      // 题目就绪后再尝试恢复暂存（顺序很重要：没有题目就没法按 id 对齐答案）
      try {
        restoreDraftIfAny()
      } catch (e) {
        console.warn('[practice] 恢复暂存失败', e)
      }
    })
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

  /*
   * 离开页面时**立即**落一次暂存（不走节流）。
   * 用户可能直接关标签/点走，节流窗口内那次还悬着 —— 这里同步 flush 保证不丢。
   */
  try {
    draftSaver.flush()
  } catch {
    /* 暂存失败不该影响离开页面 */
  }
  draftSaver.cancel()

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

/**
 * 「继续下一波」—— 只做一件事：切到下一波
 * ============================================================================
 * 用户 2026-10-18：「感觉太麻烦了，给我直接简化掉，简化更好的」。
 *
 * 旧实现（约 70 行）串了三层弹窗：
 *   未答题 → 「是否继续提交」→ 「是否继续刷下一波」→ 再决定 jumpToNextBatch 还是
 *   handleSubmitExam；而 handleSubmitExam 会把 showExamResult 置为 true，
 *   底部按钮随即变成「结束」—— 于是第一波也会显示「结束」（用户报的 bug）。
 *
 * 现在这条链彻底删掉。语义回到最直白的：
 *   · 「继续下一波」= 往前走一波，别的什么都不做；
 *   · 「提交」= 进结算（由 handleSubmit 负责，那里有一次未答提醒）；
 *   · 「回到上一波」= handlePrevBatch。
 * 三个按钮各自只对应一个动作，不再互相触发弹窗。
 */
const handleContinuePractice = () => {
  // 结算态下不该走到这里（那时按钮是「结束」），兜底先收起结果页
  if (showExamResult.value) {
    showExamResult.value = false
    totalScore.value = 0
  }
  jumpToNextBatch()
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

/**
 * 点「提交」→ 进入结算页
 * ============================================================================
 * 用户 2026-10-18 的需求：
 *   「用户做完当前题库后点击"提交"，进入结算页面。结算页面以当前浏览模式
 *     （瀑布流题目模式）作为主窗口展示；右侧答题卡标记错题并可跳转；
 *     所有题目解析自动展开。」
 *
 * 改前的行为（已废弃）：提交时先弹「是否继续刷下一波」的确认框，
 * 分波导航靠弹窗完成 —— 既打断阅读，也和"页内按钮"的分波规则冲突
 * （浏览模式底部已经有「继续下一波 / 提交」按钮了，不该再问一遍）。
 *
 * 现在的行为：
 *   · 只做一次「有未答题」的提醒（这是有价值的防误提交），确认后直接进结算；
 *   · 结算 = 切到瀑布流（overviewMode）+ showExamResult + 全部解析展开；
 *   · 刷题模式下解析本来就在答完时更新，这里再 `showAllAnalysis()` 保证全覆盖。
 *
 * ⚠️ 逐题模式提交后也会切到瀑布流结算 —— 这是"结算页以浏览模式展示"的落点，
 *    不是把用户的练习模式永久改掉（`handleFinishExam` / 重新练习会复位）。
 */
const handleSubmit = () => {
  const unanswered = totalQuestions.value - answeredCount.value

  const enterSettlement = () => {
    hasSubmittedCurrentBatch.value = true

    /*
     * 结算页固定用瀑布流展示。
     * `overviewMode` 是用户设置项，这里**临时**打开用于展示结算；
     * 不改 `moduleSettings.isOverviewMode`（那是持久化的偏好），
     * 否则用户下次进来会莫名其妙变成浏览模式。
     */
    if (!overviewMode.value) {
      overviewMode.value = true
    }

    // 进入结算：判分 + 全部解析展开（见 handleSubmitExam 的实现）
    handleSubmitExam()

    // 滚动到第一题，让用户从头核对（瀑布流里错题跳转由答题卡负责）
    nextTick(() => {
      setTimeout(() => {
        const firstCard = document.querySelector('.overview-question-card')
        if (firstCard) firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 120)
    })
  }

  // 模拟考试（mock）：沿用原来的"确认交卷"语义
  if (props.moduleType === 'mock') {
    let msg = '确定要交卷吗？'
    if (unanswered > 0) msg = `您还有 ${unanswered} 题未作答，确定要交卷吗？`
    ElMessageBox.confirm(msg, '确认提交', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
      .then(enterSettlement)
      .catch(() => {
        /* 用户取消：什么都不做，留在当前题 */
      })
    return
  }

  // 练习模式 / 考试模式：有未答题时提醒一次，确认后进结算
  if (unanswered > 0) {
    ElMessageBox.confirm(`您还有 ${unanswered} 题未作答，是否提交并查看解析？`, '提示', {
      confirmButtonText: '提交并查看解析',
      cancelButtonText: '继续答题',
      type: 'warning'
    })
      .then(enterSettlement)
      .catch(() => {
        /* 继续答题 */
      })
    return
  }

  enterSettlement()
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

/* ===================== 页面暂存（练习进度） =====================
 *
 * 与 keep-alive 的分工见 `utils/practiceDraft.ts` 顶部说明：
 *   keep-alive 保的是"组件实例 + 滚动位置"（刷新即丢），
 *   暂存保的是"答题数据"（落 localStorage，关掉浏览器也在）。
 *
 * 这里只做三件事：
 *   ① 从暂存恢复（进题库时，若该题库/模块有未完成进度）；
 *   ② 作答/换题/换波后**静默**写一次（节流，用户无感）；
 *   ③ 给答题卡面板提供手动「暂存」入口与状态文案。
 */
const userStore = useUserStore()

/** 手动暂存的状态（驱动答题卡上的按钮文案） */
const draftState = ref<DraftSaveState>('idle')
/** 上次成功暂存的时间（用于显示"已暂存 12:03"这类文案） */
const draftSavedAt = ref<number>(0)

/** 取当前用户 id（登录态可能晚于组件挂载就绪，所以用函数而不是取值） */
const currentUserId = () => {
  const id = (userStore as any).id
  return id === undefined || id === null || id === '' ? null : id
}

/**
 * 把"每题 id → 作答"的关联写进暂存
 *
 * 为什么用 questionId 而不是数组下标：随机练习 / 重新进入时题目顺序会变，
 * 用下标恢复会把答案按错位置贴上去（张冠李戴）。
 */
function buildDraftSnapshot() {
  const ids: Array<number | string> = []
  const answersById: Record<string, any> = {}
  const judgedById: Record<string, boolean> = {}
  const correctById: Record<string, boolean> = {}
  const fillById: Record<string, Record<string, any>> = {}
  const essayById: Record<string, Record<string, any>> = {}

  const list = questions.value || []
  list.forEach((q: any, idx: number) => {
    if (!q) return
    const qid = q.id ?? q.questionId ?? idx
    ids.push(qid)
    const ans = answers.value?.[idx]

    /*
     * 「这一题到底答过没有」的判据
     * ------------------------------------------------------------------
     * ⚠️ 别只判 `!== null && !== ''`（2026-10-18 踩到）：
     *    组合题（readingComprehension / cloze）在 `answers` 里存的是**对象**
     *    （`resetAnswers` 会给它们初始化成 `{}`）。空对象 `{}` 既不是 null 也不是 ''，
     *    于是被当成"答过"，暂存里就会塞进一堆没作答的组合题 id ——
     *    恢复时它们会覆盖成"已作答"的错误状态。
     */
    const hasAnswer =
      ans === null || ans === undefined
        ? false
        : typeof ans === 'object'
          ? Array.isArray(ans)
            ? ans.length > 0
            : Object.keys(ans).length > 0 // 组合题：有子答案才算答过
          : ans !== ''

    if (hasAnswer) {
      answersById[String(qid)] = ans
    }
    if (q.answered) judgedById[String(qid)] = true
    if (q.correct === true || q.correct === false) correctById[String(qid)] = !!q.correct
  })

  // 组合题子题答案：`subFillBlankAnswers` 的 key 是 `${qid}_${subIndex}` 这类拼接
  Object.keys(subFillBlankAnswers.value || {}).forEach((k) => {
    const [qid, sub] = String(k).split('_')
    if (!qid || sub === undefined) return
    const v = (subFillBlankAnswers.value as any)[k]
    if (v === null || v === undefined || v === '') return
    ;(fillById[qid] ||= {})[sub] = v
  })
  Object.keys(subEssayAnswers.value || {}).forEach((k) => {
    const [qid, sub] = String(k).split('_')
    if (!qid || sub === undefined) return
    const v = (subEssayAnswers.value as any)[k]
    if (v === null || v === undefined || v === '') return
    ;(essayById[qid] ||= {})[sub] = v
  })

  const cur = currentQuestion.value
  const curId = cur ? cur.id ?? cur.questionId ?? null : null

  return {
    bankId: props.bankId,
    moduleType: props.moduleType,
    questionIds: ids,
    answers: answersById,
    judged: judgedById,
    correct: correctById,
    subFillBlank: fillById,
    subEssay: essayById,
    currentQuestionId: curId,
    batchIndex: Math.floor((questionOffset.value || 0) / Math.max(1, moduleSettings.value.questionCount || 10)),
    batchSize: moduleSettings.value.questionCount || 10,
    submittedBatches: hasSubmittedCurrentBatch.value ? [(questionOffset.value || 0)] : [],
    stats: {
      correct: correctCount.value || 0,
      wrong: wrongCount.value || 0,
      elapsedMs: 0
    }
  }
}

const draftSaver = createDraftSaver({
  getUserId: currentUserId,
  getBankId: () => props.bankId,
  getModuleType: () => props.moduleType,
  buildSnapshot: buildDraftSnapshot as any,
  onStateChange: (s, at) => {
    draftState.value = s
    if (s === 'saved' && at) draftSavedAt.value = at
    // 失败要明确告知（配额满 / 隐私模式），否则用户以为存上了
    if (s === 'failed') {
      ElMessage.warning('暂存失败：浏览器存储不可用或空间不足')
    }
  }
})

/** 手动暂存（答题卡面板的「暂存」按钮） */
const handleManualSaveDraft = () => {
  const ok = draftSaver.flush()
  if (ok) ElMessage.success('已暂存当前练习进度')
  // 失败提示已在 onStateChange 里统一处理，这里不重复弹
}

/** 答题卡上显示的暂存按钮文案 */
const draftButtonText = computed(() => {
  switch (draftState.value) {
    case 'saving':
      return '保存中…'
    case 'saved':
      return '已暂存'
    case 'failed':
      return '暂存失败'
    default:
      return '暂存'
  }
})

/**
 * 进题库时恢复上次进度
 *
 * 匹配规则：按 **questionId** 对齐（不是数组下标）——
 * 随机练习/重新进入时题目顺序可能变，按下标贴答案会张冠李戴。
 *
 * 恢复内容：作答、是否已判、对错、组合题子题答案、当前题、当前波次。
 * 不恢复：计时器、弹窗、临时 UI 状态（那些属于 keep-alive 的范畴）。
 *
 * 只在"这个题库这个模块确有暂存"时执行，且**不覆盖**用户当场刚输入的内容：
 * 只有在答案还是空的时候才回填。
 */
/** 是否已经从暂存恢复过（避免重复提示 / 重复覆盖） */
let draftRestoredOnce = false

function restoreDraftIfAny(retry = 0) {
  if (draftRestoredOnce) return
  const draft = loadDraft(currentUserId(), props.bankId, props.moduleType)
  if (!draft) {
    draftRestoredOnce = true
    return
  }

  /*
   * 先回到"当时那一波"，再对齐答案
   * ------------------------------------------------------------------
   * ⚠️ 顺序非常重要（2026-10-18 实测踩到）：
   *    `questions` 是 `allQuestionsData` 的**切片**（[questionOffset, +count)），
   *    不是全量。若用户上次做到第 3 波，而这次进来停在第 1 波，
   *    切片里的题目完全不同 → 按 questionId 一条也对不上 → 看起来"没恢复"。
   *    所以必须先把 questionOffset 拨回暂存里记录的批位置。
   */
  const batchSize = Math.max(1, Number(draft.batchSize) || moduleSettings.value.questionCount || 10)
  const wantOffset = Math.max(0, Number(draft.batchIndex || 0) * batchSize)
  if (wantOffset !== (questionOffset.value || 0) && allQuestionsData.value.length > wantOffset) {
    questionOffset.value = wantOffset
    loadBatchWithoutReset()
  }

  const list = questions.value || []
  if (!list.length) {
    /*
     * 题目还没到（`fetchQuestions()` 是异步的，且可能有别的入口先触发了加载）。
     * 这里轮询等待，而不是"一次拿不到就放弃" —— 放弃会让用户看到空白的作答题，
     * 以为进度丢了（2026-10-18 实测踩到）。
     * 最多等约 3 秒（20 × 150ms），之后安静退出。
     */
    if (retry < 20) {
      setTimeout(() => restoreDraftIfAny(retry + 1), 150)
    }
    return
  }

  // 建 id → 下标 的索引（用字符串比较，避免 number/string 类型差异）
  const idxById = new Map<string, number>()
  list.forEach((q: any, i: number) => {
    const qid = q?.id ?? q?.questionId ?? i
    idxById.set(String(qid), i)
  })

  let restoredCount = 0

  Object.keys(draft.answers || {}).forEach((qid) => {
    const i = idxById.get(String(qid))
    if (i === undefined) return
    const val = draft.answers[qid]
    // 用户已经当场答过的不要覆盖（例如恢复前手快点了选项）
    const cur = answers.value?.[i]
    if (cur !== null && cur !== undefined && cur !== '') return
    answers.value[i] = val
    restoredCount += 1
  })

  // 已判状态与对错（刷题模式下答完即判，恢复后解析应该还在）
  Object.keys(draft.judged || {}).forEach((qid) => {
    const i = idxById.get(String(qid))
    if (i === undefined) return
    const q = list[i]
    if (!q) return
    q.answered = true
    if (draft.correct && typeof draft.correct[qid] === 'boolean') {
      q.correct = draft.correct[qid]
    }
    // 刷题模式：恢复出来的题要能直接看到解析
    if (isPracticeMode.value) q.showAnalysis = true
  })

  // 组合题子题答案
  Object.keys(draft.subFillBlank || {}).forEach((qid) => {
    const subs = draft.subFillBlank[qid] || {}
    Object.keys(subs).forEach((sub) => {
      const k = `${qid}_${sub}`
      if (!(k in (subFillBlankAnswers.value || {}))) {
        ;(subFillBlankAnswers.value as any)[k] = subs[sub]
      }
    })
  })
  Object.keys(draft.subEssay || {}).forEach((qid) => {
    const subs = draft.subEssay[qid] || {}
    Object.keys(subs).forEach((sub) => {
      const k = `${qid}_${sub}`
      if (!(k in (subEssayAnswers.value || {}))) {
        ;(subEssayAnswers.value as any)[k] = subs[sub]
      }
    })
  })

  // 定位到上次那一题（按 id）
  if (draft.currentQuestionId !== undefined && draft.currentQuestionId !== null) {
    const i = idxById.get(String(draft.currentQuestionId))
    if (i !== undefined) goToQuestion(i)
  }

  if (restoredCount > 0) {
    draftRestoredOnce = true
    // 明确告诉用户"这是恢复的"，而不是让他以为自己已经答过
    ElMessage.success(`已恢复上次练习进度（${restoredCount} 题）`)
    draftState.value = 'saved'
    draftSavedAt.value = draft.savedAt
  } else {
    draftRestoredOnce = true
  }
}

/**
 * 静默暂存：作答 / 判分 / 换题 / 换波 后自动写一次
 * 为什么 watch 这么多个源而不是"只在作答时存"：
 *   · `answers` 变了 → 用户选了选项（最核心）；
 *   · `currentQuestionIndex` 变了 → 换题，要记住"我看到第几题"；
 *   · `questionOffset` 变了 → 换波，要记住"我做到第几波"；
 *   · `subFillBlankAnswers` / `subEssayAnswers` → 组合题子题；
 *   · `hasSubmittedCurrentBatch` → 本波是否提交（考试模式恢复时要知道）。
 * 全部走 `schedule()`（节流），所以连着敲字也只会在停顿后写一次。
 */
watch(
  () => [
    JSON.stringify(answers.value),
    currentQuestionIndex.value,
    questionOffset.value,
    hasSubmittedCurrentBatch.value,
    JSON.stringify(subFillBlankAnswers.value),
    JSON.stringify(subEssayAnswers.value)
  ],
  () => {
    // 结算/成绩页不写（那是结果态，不是「进行中的练习」）
    if (showExamResult.value) return
    // 恢复还没完成时不要写：否则会用"空答案"把暂存覆盖掉（最致命的一种数据丢失）
    if (!draftRestoredOnce) return
    draftSaver.schedule()
  }
)

/**
 * 兜底：题目首次就绪时尝试恢复
 *
 * 为什么不只依赖 onMounted 里那次：提交流程里 `fetchQuestions()` 有多条触发路径
 * （切换模块、设置变更、重新练习），onMounted 里的 `.then` 不一定是「题目第一次可用」
 * 的那一刻。这里盯住 `questions.length` 从 0 变正数，任何路径都能覆盖到。
 */
watch(
  () => questions.value.length,
  (n, old) => {
    if (n > 0 && (!old || old === 0)) {
      restoreDraftIfAny()
    }
  }
)

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
