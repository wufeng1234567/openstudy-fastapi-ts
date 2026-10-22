<template>
  <div class="practice-container">
    <!--
      加载动画
      ==================================================================
      ⚠️ 必须放在下面那条 v-if 链**之前**，且自身是一条独立的短链。
         绝不能插在 v-if / v-else-if 兄弟之间 —— Vue 要求 v-else-if 紧跟
         上一个分支，中间夹一个元素会直接编译报错。
    -->
    <div v-if="loading && !showMockSetupUI && !showMockSummaryUI" class="loading-overlay">
      <div class="loading-spinner">
        <div class="loading-ring"></div>
        <div class="loading-text">正在加载题目...</div>
      </div>
    </div>

    <!--
      主界面：一条链管到底（2026-10-22 重构）
      ==================================================================
      这里是**唯一**一条渲染链，从上到下依次是：

          模拟考试（配置 / 历史 / 总结）
          → 空态
          → 整体浏览
          → 逐题（考卷）

      ⚠️⚠️ 踩过的严重 bug，改之前先读完：
        原来「模拟考试三态」是独立的一条 v-if 链，刷题 UI 是另一条，
        两条链之间隔着加载动画等兄弟节点 —— 于是它们**互不排斥**：
        用户在配置页设置题目时，配置页**下面还完整渲染着一份考卷**（含答题卡）。

        当时试过在刷题链里加一个 `v-else-if` 占位去"挡住"考卷，但那条链是从
        `isEmptyState` 起步的，占位分支排在它后面 —— 永远轮不到，等于没挡。

        正确做法就是现在这样：把模拟考试三态作为**同一条链的前三个分支**。
        Vue 的 v-if 链天生只有一个分支能渲染，互斥由结构保证，
        不需要任何"占位挡住"的技巧，也不可能再出现叠加。

      下方分支顺序也有讲究（都是修过的 bug，别随意调整）：
        · 空态必须排在浏览/逐题**之前** —— 否则"没有题"时会被考卷分支吃掉，
          用户看到的是空白而不是解释（见 2026-10-21 那段注释）。
        · 浏览模式排在逐题之前 —— 它是 `isOverviewActive` 为真时的展示形态。
    -->
    <MockExamSetup
      v-if="isMockFlow && mockPhase === 'setup'"
      :bank-id="bankId"
      :bank-name="bankName"
      :available="mockAvailable"
      @cancel="$emit('close')"
      @open-history="mockPhase = 'history'"
      @start="handleMockStart" />

    <MockExamHistory
      v-else-if="isMockFlow && mockPhase === 'history'"
      :bank-id="bankId"
      :bank-name="bankName"
      @cancel="mockPhase = 'setup'"
      @open-record="handleOpenHistoryRecord" />

    <ExamSummary
      v-else-if="isMockFlow && mockPhase === 'summary' && currentExamRecord"
      :record="currentExamRecord"
      :readonly="!!historyRecord"
      @close="$emit('close')"
      @retry="handleMockAgain"
      @back-to-history="handleMockBackToHistory" />

    <!--
      「没有题可练」空态 —— 独立于「逐题 / 整体浏览」两种展示
      ==================================================================
      ⚠️⚠️ 这块**必须**放在两个展示分支**之外**（2026-10-21 修的 bug）。

      踩坑经过（这就是「修好的 bug 又回复了」的机制）：
        · 上一轮把空态写在了 `v-else`（逐题模式）分支内部，
          而 `overviewMode` 为 true 时走的是另一个 `<template>` —— 空态**根本不存在**；
        · 更糟的是 `overviewMode` 是 computed，setter 会**立刻写进 localStorage**
          持久化。而 `handleSubmit` 的结算逻辑里有 `overviewMode.value = true`
          （注释写着"临时的、不改持久化偏好"，但实际 setter 一赋值就落盘了）。
          于是：用户点过一次「提交」→ 整体浏览被永久打开 → 之后进顺序练习+仅错题
          → 走浏览分支 → 空白页，逐题分支里的空态永远显示不出来。
          用户看到的现象就是「已经修好的 bug 又回来了」。

      所以：空态不挂在任何一个展示分支下面，而是**两个分支的共同前置**。
      这样不管 `overviewMode` 是 true 还是 false，只要没有题，就一定看到这块 UI。
    -->
    <template v-else-if="isEmptyState">
      <PracticeHeader :mode="moduleTypeSafe" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="openSettings" />

      <!-- 错题状态条：空态时仍要说明「你当前在错题模式」，否则用户不明白为什么没题 -->
      <div class="only-wrong-bar" v-if="moduleSettings.onlyWrong">
        <span class="only-wrong-bar__chip">
          <OsIcon name="alert" :size="13" class="only-wrong-bar__icon" />
          仅错题
        </span>
        <span class="only-wrong-bar__text">正在只练你答错过的题</span>
        <button type="button" class="only-wrong-bar__action" @click="openSettings">
          调整
        </button>
      </div>

      <div class="practice-empty">
        <OsIcon :name="noQuestionsKind === 'finished' ? 'check' : 'inbox'" :size="30" class="practice-empty__icon" />
        <p class="practice-empty__title">{{ noWrongQuestionsReason }}</p>
        <!--
          ⚠️ 两种「没有题」必须给**不同的解释和动作**（2026-10-21）
          用 `noQuestionsKind` 区分：
            · noWrong  → 解释错题本怎么用，动作是「关闭只刷错题」
            · finished → 说明刷完了，动作是「重新练习」
          否则会给刷完的用户显示「先去别的模式练几道」，完全答非所问。
        -->
        <p class="practice-empty__desc">
          <template v-if="noQuestionsKind === 'finished'">
            这一轮已经全部作答完毕。可以重新练一遍，或者返回题库换个模式。
          </template>
          <template v-else>
            错题本会自动记录你答错的题。先去别的模式练几道，答错的题就会出现在这里。
          </template>
        </p>
        <div class="practice-empty__actions">
          <el-button v-if="noQuestionsKind === 'finished'" size="small" type="primary" plain
            @click="handleEmptyRestart">
            重新练习
          </el-button>
          <el-button v-else size="small" type="primary" plain @click="handleEmptyTurnOffOnlyWrong">
            关闭「只刷错题」
          </el-button>
          <el-button size="small" @click="$emit('close')">返回题库</el-button>
        </div>
      </div>
    </template>

    <!-- 整体浏览模式 -->
    <template v-else-if="isOverviewActive">
      <PracticeHeader :mode="moduleTypeSafe" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="openSettings" />

      <!--
        ⚠️ 状态条在**浏览模式和逐题模式都要有**（2026-10-20）：
        原来只有逐题模式那一支有，用户一点「整体浏览」就看不到自己还在错题模式里，
        切回来才发现题目少了一半 —— 状态必须在两种展示下都可读。
      -->
      <div class="only-wrong-bar" v-if="moduleSettings.onlyWrong">
        <span class="only-wrong-bar__chip">
          <OsIcon name="alert" :size="13" class="only-wrong-bar__icon" />
          仅错题
        </span>
        <span class="only-wrong-bar__text">正在只练你答错过的题</span>
        <button type="button" class="only-wrong-bar__action" @click="openSettings">
          调整
        </button>
      </div>

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
              <span class="question-number" v-if="isOverviewActive">第 {{ numberBase + index + 1 }} 题</span>
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
              :shuffle-options="effectiveShuffleOptions"
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
          :module-type="moduleTypeSafe" :draft-state="draftState" :draft-button-text="draftButtonText" :number-base="numberBase"
          :shuffle-options="effectiveShuffleOptions"
          @update:shuffle-options="handleToggleShuffle"
          @go-to-question="scrollToQuestion" @toggle-overview="toggleOverview"
          @reset-practice="resetPractice" @submit-exam="handleSubmitExam" @finish-exam="handleFinishExam"
          @save-draft="handleManualSaveDraft" />
      </div>
    </template>

    <!-- 逐题模式（原有布局） -->
    <template v-else>
      <PracticeHeader :mode="moduleTypeSafe" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="openSettings" />

      <!--
        「只刷错题」状态条
        ==================================================================
        2026-10-20 重做视觉（用户：「只练错题这个提示太难看了」）。

        旧版是满宽容的**告警样式**：`#fef3c7` 黄底 + `#fcd34d` 黄框 + 深棕文字，
        和「题目区」抢同一层注意力，但它的信息量远低于题目 ——
        用户每次低头看题都被一条黄色横幅晃一下，属于"用告警的视觉说状态"。

        新版按**状态标签**来做（与全站 `.os-chip` 一致的调性）：
          · 不再是横贯整行的色块，而是贴着标题行下方的一枚小胶囊；
          · 中性底 + 发丝描边，只有图标用主色 —— 表示"这是一个模式说明"，不是警告；
          · 右侧给出**可操作**的出口（调整），而不是让用户自己去右上角找齿轮。

        语义边界（重要）：这条只表示「当前处于错题模式」这个**状态**。
        「这个库里没有错题」是另一件事，由下面 `.practice-empty` 负责 ——
        两者不会同时出现，所以文案不要合并。
      -->
      <div class="only-wrong-bar" v-if="moduleSettings.onlyWrong">
        <span class="only-wrong-bar__chip">
          <OsIcon name="alert" :size="13" class="only-wrong-bar__icon" />
          仅错题
        </span>
        <span class="only-wrong-bar__text">正在只练你答错过的题</span>
        <button type="button" class="only-wrong-bar__action" @click="openSettings">
          调整
        </button>
      </div>

      <!--
        ⚠️ 空态已经提到上面、两个展示分支的共同前置里了（见 `isEmptyState`）。
           那段历史注释保留在 `isEmptyState` 定义处，别在这里再造一块重复的空态 ——
           两份就会同时渲染，用户看到两遍文案。
      -->
      <div class="main-content">
        <QuestionDisplay :current-question="currentQuestion" :current-question-index="currentQuestionIndex"
          :total-questions="totalQuestions" :number-offset="numberBase" :selected-answer="selectedAnswer"
          :sub-fill-blank-answers="subFillBlankAnswers" :sub-essay-answers="subEssayAnswers" :answers="answers"
          :show-analysis-immediately="showAnalysisImmediately" @select-option="handleSelectOption"
          :shuffle-options="effectiveShuffleOptions"
          @update-answer="value => selectedAnswer = value" @select-sub-option="selectSubOption"
          @update-sub-fill-blank-answer="updateSubFillBlankAnswer" @update-sub-essay-answer="updateSubEssayAnswer"
          @preview-image="openImageViewer" />

        <AnswerCard :questions="questions" :current-question-index="currentQuestionIndex" :stats="{
          correctCount,
          wrongCount,
          accuracy
        }" :is-exam-mode="isExamMode" :is-practice-mode="isPracticeMode" :is-last-question="isLastQuestion"
          :show-exam-result="showExamResult" :total-score="totalScore" :answered-count="answeredCount"
          :total-count="totalQuestions" :remaining-count="remainingCount" :module-type="moduleTypeSafe"
          :marked-questions="markedQuestionsSet" :favorited-questions="favoritedQuestions" :error-questions="errorQuestions"
          :draft-state="draftState" :draft-button-text="draftButtonText" :number-base="numberBase"
          :shuffle-options="effectiveShuffleOptions"
          @update:shuffle-options="handleToggleShuffle"
          @go-to-question="goToQuestion" @reset-practice="resetPractice" @submit-exam="handleSubmitExam"
          @toggle-overview="toggleOverview" @finish-exam="handleFinishExam"
          @save-draft="handleManualSaveDraft" />
      </div>



      <QuestionNavigation v-if="!(noWrongQuestionsReason && questions.length === 0)"
        :show-prev="currentQuestionIndex > 0" :show-next="currentQuestionIndex < totalQuestions - 1"
        :question-id="currentQuestion?.id" :bank-id="bankId" :module-type="moduleTypeSafe" :is-exam-mode="isExamMode"
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
import { ref, reactive, computed, watch, getCurrentInstance, nextTick, onMounted, onUnmounted } from 'vue'
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
// 「只刷错题」空态要用线性图标（全站统一走 OsIcon，不用 Element Plus 实心图标）
import OsIcon from '@/components/OsIcon/index.vue'
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
// 模拟考试的三个新界面（2026-10-22）
import MockExamSetup from './MockExamSetup.vue'
import ExamSummary from './ExamSummary.vue'
import MockExamHistory from './MockExamHistory.vue'
import type { MockExamConfig, MockExamRecord, MockExamItemDetail } from '@/types'
// 模拟考试组卷要拉全量题目（见 loadMockAvailability / handleMockStart）
import { listQuestionMainAll } from '@/api/questionMain/questionMain'

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
  /*
   * 练习模块类型
   *
   * ⚠️ 允许 null（`type: [String, Object]` 不写 `required`）：
   *    页面刚挂载时路由参数可能还没解析出来，父级会先传 `null`。
   *    原来声明成 `type: String, required: true`，于是控制台每次进练习页都刷
   *    `Invalid prop: type check failed for prop "moduleType"`（2026-10-18 实测）。
   *    组件内部用 `moduleTypeSafe` 归一化成 `'sequential'` 兜底，再往下传。
   */
  moduleType: {
    type: String,
    default: 'sequential',
    validator: (val: any) => !val || ['sequential', 'random', 'custom', 'mock'].includes(val)
  }
})

const emit = defineEmits(['close'])

/**
 * 归一化后的模块类型（永不为 null）
 *
 * 路由参数未就绪时父级会传 `null`；子组件（PracticeHeader / AnswerCard /
 * QuestionNavigation）的 prop 都声明成 `type: String`，传 `null` 会刷类型警告。
 * 统一用这个值往下传，组件内部逻辑也用它，避免"有时是 null 有时是字符串"。
 */
const moduleTypeSafe = computed(() => (props.moduleType || 'sequential') as string)

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

/* ============================================================================
 * 模拟考试的三个阶段（2026-10-22）
 * ============================================================================
 *   setup   → 考试配置页（选题型、题数、分值、时长、及格分）
 *   running → 正在作答（原来的刷题界面）
 *   summary → 交卷后的结果页（得分环 + 对错饼图 + 错题明细）
 *   history → 历史记录列表（从配置页进）
 *
 * 为什么用状态机而不是"再加几个布尔"：
 *   这三态互斥，且任何一态显示时其他两态必须完全让位（不能让"配置页"和"考卷"
 *   同时挂在 DOM 上 —— 那会导致计时器在配置页就开始跑）。
 *   三个独立布尔迟早会出现两个同时为真。
 */
type MockPhase = 'setup' | 'running' | 'summary' | 'history'
const mockPhase = ref<MockPhase>('setup')

/** 是否处于模拟考试流程（决定模板走哪一套 UI） */
const isMockFlow = computed(() => moduleTypeSafe.value === 'mock')
/** 是否应显示考试配置/历史/总结，而不是考卷 */
const showMockSetupUI = computed(
  () => isMockFlow.value && (mockPhase.value === 'setup' || mockPhase.value === 'history')
)
const showMockSummaryUI = computed(() => isMockFlow.value && mockPhase.value === 'summary')

/**
 * 本次考试的配置（开考时从 store 载入并冻结）
 *
 * ⚠️ 必须**冻结快照**：考试进行中用户可能去设置页改配置，
 *    若判分时再读 store，就会出现"按新配置判旧卷子"的错乱。
 */
const activeMockConfig = ref<MockExamConfig | null>(null)

/**
 * 选项是否打乱（下发给 `QuestionDisplay` / `AnswerCard`）
 *
 * 两种模式的「乱序」来源不同，不能混用一个值：
 *   · 模拟考试：由**本次考试的配置**决定（用户开考时在配置页勾的），
 *     且它在开考瞬间就冻结了 —— 考试中途改全局设置不该影响进行中的卷子。
 *   · 其余三个入口：读全局设置，用户在答题卡面板里随时可开关、实时生效。
 *
 * ⚠️ 必须定义在 `activeMockConfig` **之后**：computed 的 getter 虽然延迟执行，
 *    但声明顺序错了在首次渲染时就会踩到 TDZ（Cannot access before initialization）。
 */
const effectiveShuffleOptions = computed(() => {
  if (isMockFlow.value) return !!activeMockConfig.value?.shuffleOptions
  return !!moduleSettings.value.shuffleOptions
})

/** 各题型的可选题量（配置页显示"最多能抽几道"用） */
const mockAvailable = ref<Record<string, number>>({})

/** 交卷后的结果（总结页与历史页共用） */
const currentExamRecord = ref<MockExamRecord | null>(null)

/** 从历史记录打开的那一条（与 currentExamRecord 分开：历史是只读回看） */
const historyRecord = ref<MockExamRecord | null>(null)

/** 考试开始时间（算用时） */
const examStartAt = ref<number>(0)


/**
 * 「打开设置弹窗那一刻」的设置快照
 *
 * ⚠️ 存在的唯一原因：`PracticeSettings.handleSave()` 是**先写 store 再 emit**，
 * 父组件收到 `save` 事件时 `moduleSettings` 已经是新值，没法据此判断"用户改了什么"。
 * 所以在打开弹窗时把旧值记下来，保存时跟这份快照比。
 *
 * 详见 `openSettings()` 与 `handleSettingsSave()` 的注释 —— 这两个函数是配套的，
 * 改动其一时必须同步另一个，否则「只刷错题」会再次变成"开关点了没反应"。
 */
const settingsSnapshot = reactive({
  onlyWrong: false,
  questionCount: 10 as number | string,
  isOverviewMode: false
})

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
    // skipConfirm：时间已到，用户没有选择权，不再弹第二次确认
    handleSubmitExam({ skipConfirm: true })
  }).catch(() => {
    console.log(`[EXAM] 弹窗被关闭，提交试卷`)
    isTimeUpDialogShowing = false
    handleSubmitExam({ skipConfirm: true })
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

/**
 * 切换题库时**必须重置**（2026-10-22）
 *
 * ⚠️ 这是真实 bug 的修复，不是预防性加固：
 *   路由是 `/front/questionPractice/:bankId/:moduleType`，刷题页外层套了
 *   裸 `<keep-alive>`（`views/questionPractice/questionPractice/index.vue`），
 *   所以「从题库 A 换到题库 B」时 —— **只变路由参数，组件实例被复用**。
 *
 *   于是三处逻辑全部失效：
 *     · `onMounted` 不再执行（`isFirstLoaded` 已是 true，没人再调 `fetchQuestions`）；
 *     · `watch(moduleType)` 不触发（多数情况下 A/B 用的是同一个 mode）；
 *     · 即使有谁调了 `fetchQuestions()`，它内部第一道判断是
 *       `if (questions.value.length > 0) return` —— 此刻 `questions` 里装的
 *       正是**题库 A 的题**，于是直接返回，什么都不拉。
 *
 *   用户看到的结果：点题库 B，标题/URL 都变成 B 了，题目还是 A 的。
 *
 * 为什么不能只靠 `:key` 强制重建组件：
 *   那会连带丢掉 keep-alive 的意义（返回题库列表再进来时进度全没），
 *   而「同一题库再次进入保留进度」是刻意设计（见 `restoreAnswerState` /
 *   `practiceDraft` 的注释）。所以这里做**精准重置**：换题库才重置，
 *   同题库来回切仍然走缓存。
 */
watch(() => props.bankId, (newId, oldId) => {
  // 首次挂载时 oldId 为 undefined，交给 onMounted 处理，不要重复拉
  if (oldId === undefined || oldId === null) return
  if (!newId || Number(newId) <= 0) return
  // 同值不处理（数字/字符串混用时会误判，统一 Number 比较）
  if (Number(newId) === Number(oldId)) return

  debugWatchTrigger('bankId', String(newId), String(newId), String(oldId))

  // 1) 计时器与考试态属于「上一个题库」，必须停掉，否则 B 题库会显示 A 的倒计时
  stopExamTimer()
  remainingTime.value = 0
  clearExamStorage()
  showExamResult.value = false
  hasSubmittedCurrentBatch.value = false

  /*
   * 2) 「已从暂存恢复过」的闸门要重新打开。
   *    `restoreDraftIfAny()` 里有 `if (draftRestoredOnce) return`，它是按组件
   *    实例（不是按题库）记的 —— 不重置的话，B 题库的暂存永远恢复不出来。
   */
  draftRestoredOnce = false

  // 3) 重置题目与作答，再去拉 B 题库的数据。
  //    ⚠️ 必须把 oldId 传进去：此刻 `props.bankId` 已经是新题库，
  //    `resetAndFetchQuestions` 内部会先 `saveCurrentAnswerState`，
  //    不带 oldId 就会把旧题库的题存进新题库的缓存 key（见该函数的注释）。
  resetAndFetchQuestions(props.moduleType, oldId)
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

/**
 * 「临时」打开整体浏览（结算用），**不写进持久化偏好**
 * ============================================================================
 * ⚠️⚠️ 这是「修好的 bug 又回复了」的真正根源（2026-10-21）。
 *
 * 原来的结算代码写的是：
 *     if (!overviewMode.value) { overviewMode.value = true }
 * 注释还写着"这里**临时**打开，不改 `moduleSettings.isOverviewMode`"。
 * 但 `overviewMode` 是 **computed，且带 setter**：
 *     set: (val) => store.saveModuleSettings(props.moduleType, { isOverviewMode: val })
 * 一赋值就直接落 localStorage 了 —— 注释的意图和代码的实际行为完全不同。
 *
 * 后果（用户可见）：
 *   点过一次「提交」→ `isOverviewMode` 被永久置 true →
 *   下次（以及以后每次）进这个模块都直接是整体浏览视图 →
 *   而空态当时只写在"逐题模式"那条分支里 → **空白页**。
 *   于是"我这边验证过空态是好的"，用户那边永远是空白 —— 因为他的
 *   localStorage 里已经被上一次结算写成了 `isOverviewMode: true`。
 *
 * 正确做法：用一个**独立的本地区状态** `forceOverview` 叠加在用户偏好之上。
 *   · 结算时置 `forceOverview = true`（只影响本次会话的渲染，不落盘）；
 *   · `isOverviewActive` = 用户偏好 OR 本次强制；
 *   · 模板用 `isOverviewActive` 判断走哪个分支，用户的偏好设置保持原样。
 */
const forceOverview = ref(false)
const isOverviewActive = computed(() => moduleSettings.value.isOverviewMode || forceOverview.value)

/**
 * 「当前没有题可练」——空态的总开关
 * ============================================================================
 * ⚠️⚠️ 这个 computed 存在的唯一原因，就是**让空态不再依赖 `overviewMode`**
 * （2026-10-21 修的 bug，用户口径：「刚刚给你修复好的 bug 又回复了
 *   顺序模式下的只刷错题 没有兜底 ui」）。
 *
 * 上一轮把空态写在逐题分支（`v-else`）内部，而模板结构是：
 *     <template v-if="overviewMode"> …整体浏览… </template>   ← 没有空态
 *     <template v-else>            …逐题…     </template>   ← 空态在这里
 * 于是只要 `overviewMode` 为 true，空态就是**不存在的代码路径**。
 *
 * 而 `overviewMode` 极易被打开（两个入口，都不是用户主动选的）：
 *   ① 结算里 `overviewMode.value = true` 一赋值就**持久化**（见上面
 *      `forceOverview` 的注释 —— 这条是真正的元凶，已修）；
 *   ② 用户自己在答题卡上点「整体浏览」也会持久化（这个是用户选择，合理）。
 * 所以"我这边明明修好了、空态也能看到"，到用户那里就是空白页。
 *
 * 判据用 `questions.length === 0` 而不是 `totalQuestions`：
 * 后者是 computed，在 `allQuestionsData` 也被清空时行为不稳定；
 * `questions` 是模板直接渲染的源，长度 0 = 一定渲染不出题目。
 * 再与 `noWrongQuestionsReason` 相与，保证只有**明确的"没有题"**才显示空态：
 * 加载中（loading 遮罩盖住）、第一次进入尚未取到数据等瞬时状态都不会误判成空态。
 */
const isEmptyState = computed(
  () => !!noWrongQuestionsReason.value && questions.value.length === 0
)

/**
 * 空态里的「重新练习」/「关闭只刷错题」——必须**真的能离开空态**
 * ============================================================================
 * ⚠️ 为什么不能直接绑 `resetPractice` / `openSettings`（2026-10-21）：
 *
 * `resetPractice()`（composable 里）只做三件事：清随机题单、清乱序缓存、
 * `questionOffset = 0` + `resetAnswers()`。
 * 它**不看 `noWrongQuestionsReason`，也不重新取题**。所以：
 *   · 在「本轮刷完」空态里点它 → 空态还在（因为它没去重新拉题），
 *     用户的感觉就是"按钮点了没反应"。这正是必须重拉的原因 ——
 *     "刷完"是 `offset` 推到了数组末尾，原地重置 offset 并不会让
 *     `questions` 重新有内容（`processQuestions` 才是那条路径）。
 *   · 在「没有错题」空态里点「关闭只刷错题」更糟：`openSettings()` 只是
 *     **打开设置弹窗**，用户看到的是一个弹窗，而不是"关掉后立刻有题练"。
 *     按钮写的是「关闭『只刷错题』」，行为却是"打开设置"，名不副实。
 *
 * 所以这两个入口都走 `resetAndFetchQuestions()`：
 *   它会「同步最新设置（含 onlyWrong）→ 清空全部题目状态 → 重新从接口拉取」，
 *   正好是"离开空态、回到正常刷题"需要的全部动作。
 *   「关闭只刷错题」还要先**把设置真的关掉**（写 store），再重拉 ——
 *   只重拉不改设置的话，拉回来还是那个空错题集，等于什么都没做。
 */
const handleEmptyRestart = () => {
  /*
   * 三步，缺一步都会让用户觉得"按钮没反应"或"重练了还是旧卷子"：
   *   ① `resetPractice()` —— 清随机题单 + 清乱序缓存 + offset 归零 + 清答案
   *      + 清空态标记。少了它，随机模式重练出来的还是同一份题单，
   *      只是答案被清空了；
   *   ② `clearAnswerStateCache()` —— 丢掉这个模块的答题状态缓存。
   *      少了它，`resetAndFetchQuestions` 会走 `restoreAnswerState()` 直接把
   *      **上一次的题目和作答**恢复回来，用户看到的是自己刚做完的那份卷子；
   *   ③ `resetAndFetchQuestions()` —— 真正重拉题目。
   * 另外撤掉结算留下的临时整体浏览态：用户点「重新练习」是想逐题重做，
   * 不该因为上一次结算而停在瀑布流。
   */
  resetPractice()
  clearAnswerStateCache(props.moduleType)
  forceOverview.value = false
  resetAndFetchQuestions()
}

const handleEmptyTurnOffOnlyWrong = () => {
  // ① 真的把「只刷错题」关掉并落盘（store action 内部会 saveToStorage）
  store.saveModuleSettings(props.moduleType, { onlyWrong: false })
  // ② 再整体重拉：resetAndFetchQuestions 会重新读设置 → onlyWrong=false
  resetAndFetchQuestions()
  // ③ 给一句明确反馈，否则用户不知道刚才那一下按钮做了什么
  ElMessage.success('已关闭「只刷错题」，正在加载全部题目')
}
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
  /*
   * 用户主动点「整体浏览 / 逐题模式」= 明确的偏好选择，**要持久化**。
   *
   * 与结算里的 `forceOverview` 区分开：
   *   · 这里    → 写 store（用户的长期偏好，下次进来还该是这个视图）；
   *   · 结算时  → 只置 `forceOverview`（一次性，不改偏好）。
   * 两条路径以前共用一个 computed setter，于是"临时展示"也被持久化了。
   */
  if (isOverviewActive.value) {
    store.saveModuleSettings(props.moduleType, { overviewScrollIndex: highlightedIndex.value })
  }
  const next = !isOverviewActive.value
  // 用户手动切换后，结算留下的临时态就该让位给用户的真实选择
  forceOverview.value = false
  overviewMode.value = next
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
    if (isOverviewActive.value) {
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
    if (isOverviewActive.value) {
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
 * 设置弹窗保存后的生效逻辑
 *
 * ⚠️⚠️ 这里连踩两个坑，改之前先读完（2026-10-20）：
 *
 * **坑一：原来只处理「题数变化」，完全没管「只刷错题」。**
 *   用户口径：「顺序模式下 设置只练错题 没有这个提示」——
 *   实际提示条出现了，但**题目还是全库的**（1/10 而不是 1/5 道错题）。
 *   表现上就是"开关没生效"。
 *
 * **坑二：不能用 `moduleSettings.value` 判断"值变没变"。**
 *   `PracticeSettings.handleSave()` 的执行顺序是
 *       ① `store.saveModuleSettings(...)`   ← 先把新值写进 store
 *       ② `emit('save', ...)`               ← 才通知父组件
 *   于是本函数拿到的 `moduleSettings.value.onlyWrong` **已经是新值**，
 *   `onlyWrongChanged` 恒为 false → 重载逻辑永远不执行。
 *   （我第一版就是这么写的，探针显示"保存后题量没变"，排查了一轮才发现。）
 *
 * 正解：由**打开设置弹窗的那一刻**把旧值记下来，保存回来时跟这份快照比。
 * `settingsSnapshot` 在 `openSettings()` 里写入，是这一判断的唯一可靠来源。
 *
 * 修法：`onlyWrong` 变化时走 `resetAndFetchQuestions()` —— 那个函数正是为此存在：
 * 清空 questions/allQuestionsData、同步最新设置（含 onlyWrong）、再从接口重拉。
 * 不能复用 `updateOnlyWrong()` + `fetchQuestions()`：后者开头有
 *   `if (questions.value.length > 0) return`
 * 题已在内存里就直接提前返回，永远不会重新拉取。
 */
const handleSettingsSave = (data: { moduleType: string; settings: any }) => {
  const { settings } = data
  // 与「打开弹窗时」的快照对比，而不是与已被 store 更新的当前值对比（见上面坑二）
  const prevOnlyWrong = !!settingsSnapshot.onlyWrong
  const prevCount = settingsSnapshot.questionCount
  const onlyWrongChanged = !!settings.onlyWrong !== prevOnlyWrong
  const countChanged = settings.questionCount !== prevCount

  if (onlyWrongChanged) {
    // 错题集和全库是两个不同的题目集合，必须整体重拉（不能只切片）
    resetAndFetchQuestions()
    return
  }
  if (countChanged) {
    updateQuestionCountAndSlice(settings.questionCount)
  }
}

/**
 * 打开设置弹窗
 *
 * ⚠️ 必须在这里**快照**当前设置：`PracticeSettings.handleSave` 会先写 store 再 emit，
 * 父组件收到事件时读到的已经是新值，无法据此判断"变了什么"。
 * 详见 `handleSettingsSave` 的注释。
 */
const openSettings = () => {
  const s = moduleSettings.value
  settingsSnapshot.onlyWrong = !!s.onlyWrong
  settingsSnapshot.questionCount = s.questionCount
  settingsSnapshot.isOverviewMode = !!s.isOverviewMode
  showSettings.value = true
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
     * 「提交」= 这一轮练习结束 → 丢掉随机题单，下一轮重新随机
     *
     * ⚠️ 为什么在这里清（2026-10-20）：
     *   随机练习现在是「一次随机、题单固定」（用户 2026-10-20 的方案）。
     *   题单固定的前提是"这一轮还没做完"。用户点了提交/交卷，说明这一轮结束了，
     *   下次再进就该拿到**新的**随机题单，而不是重做刚才那一套。
     *
     *   只对随机模式有意义；其它模式没有题单，调用了也只是删掉一个不存在的键，
     *   所以不做模式判断 —— 少一个分支，少一处漏判断的机会。
     *
     * ⚠️ 不要在这里清"上一轮做过哪些题"（`os_recent_practice_*`）：
     *   那是下一轮"新题优先"的依据。`clearRandomPlan()` 只清题单，正合适。
     */
    clearRandomPlan()

    /*
     * 结算页固定用瀑布流展示 —— 但**绝不能写进用户偏好**
     *
     * ⚠️⚠️ 这里原来写的是 `overviewMode.value = true`，注释还宣称"临时打开、
     *   不改 `moduleSettings.isOverviewMode`"。事实是 `overviewMode` 是带 setter
     *   的 computed，setter 直接 `saveModuleSettings(...)` 落 localStorage ——
     *   注释的意图和代码行为完全相反，这就是「空态修好了又消失」的元凶：
     *   用户点一次「提交」→ 偏好被永久改成浏览模式 → 以后每次进都走浏览分支
     *   （那条分支上没有空态）→ 空白页。
     *
     * 正确做法：只置**本地区**的 `forceOverview`，渲染时由 `isOverviewActive`
     * 与用户偏好取或。用户的 `isOverviewMode` 一个字节都不动。
     */
    forceOverview.value = true

    /*
     * 进入结算：判分 + 全部解析展开
     *
     * ⚠️ `skipConfirm: true`（2026-10-20）：
     *   这里是**练习态**的「提交」，`handleSubmit` 已经做过一次
     *   "有未答题"的确认（那是练习态的防误提交），这里再弹一次考试式的
     *   "交卷后不能修改"就重复了，而且语义也不对（练习本来就能重练）。
     *   考试态的确认由 `AnswerCard` 的「交卷」按钮走 —> handleSubmitExam() 自己弹。
     */
    handleSubmitExam({ skipConfirm: true })

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
  // 「只刷错题」但当前题库没有可练错题时的说明（空串 = 正常）
  noWrongQuestionsReason,
  // 「没有题可练」的类型：noWrong（没错题）/ finished（本轮刷完）—— 决定空态文案与动作
  noQuestionsKind,
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
  // 随机题单：练完一轮/提交后清掉，下一轮重新随机
  clearRandomPlan,
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
  // 模拟考试组卷要用：把整份卷子灌进题目流（见 handleMockStart 的注释）
  processQuestions,
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

/* ============================================================================
 * 模拟考试：组卷 / 判分 / 生成记录（2026-10-22）
 * ============================================================================
 * 这一块整体是「新增的一段独立逻辑」，只在 moduleType === 'mock' 时启用，
 * 不影响其他三个刷题入口的任何行为。
 */

/** 题型归一：后端数字题型 → 前端字符串（与 useQuestionPractice 的映射保持一致） */
function normalizeType(raw: any): string {
  switch (Number(raw)) {
    case 1: return 'single'
    case 2: return 'multiple'
    case 3: return 'truefalse'
    case 4: return 'fillblank'
    case 5: return 'essay'
    case 6: return 'readingComprehension'
    case 7: return 'cloze'
    default: return String(raw || 'unknown')
  }
}

/**
 * 拉一份全量题目并按题型统计可选题量
 *
 * 配置页要显示「/ 262 道」这样的上限提示，必须先把题库拿到手。
 * ⚠️ 这里直接调接口而不是复用 `allQuestionsData`：后者可能只装了"某一波"的切片，
 *    也可能因为「只刷错题」被过滤过 —— 用它算上限会给出错误的可选范围。
 */
async function loadMockAvailability(): Promise<void> {
  try {
    const res: any = await listQuestionMainAll({ bankId: props.bankId, status: '0' })
    const data: any[] = Array.isArray(res?.data) ? res.data
      : Array.isArray(res?.result) ? res.result : []
    const counter: Record<string, number> = {}
    for (const q of data) {
      const t = normalizeType(q.questionType ?? q.question_type)
      counter[t] = (counter[t] || 0) + 1
    }
    mockAvailable.value = counter
    /*
     * 顺手把最新配置里"超出题库实际题量"的题数收回来。
     * 不收的话：用户上次设了单选 70 道，换到一个只有 10 道单选的题库，
     * 点开始会组出一份 10 道的卷子但界面写着 70 —— 直接对不上。
     */
    const cfg = store.getMockExamConfig()
    let changed = false
    for (const row of cfg.typeRows) {
      const cap = counter[row.type] || 0
      if (row.count > cap) { row.count = cap; changed = true }
    }
    if (changed) store.saveMockExamConfig(cfg)
  } catch (e) {
    console.warn('[mock] 读取题库题量失败', e)
    mockAvailable.value = {}
  }
}

/**
 * 按配置组卷
 *
 * 规则：
 *   · 每个题型独立随机抽 `count` 道（题库不够就抽多少算多少，不报错）；
 *   · 抽完后整体打乱：真实考试不会把同一题型排在一起，混排更像"一份卷子"；
 *   · 每道题挂上 `_mockScore`（该题满分）与 `_mockType`，供判分使用。
 *
 * ⚠️ 分值写在题目对象上（`_mockScore`）而不是另开一张表：
 *    题目对象本来就贯穿"渲染 → 作答 → 判分"整条链路，挂在它身上最不容易丢。
 *    下划线前缀与 `guard.params_payload` 的"内部字段"约定一致，不会被误当业务字段。
 */
function buildMockPaper(cfg: MockExamConfig, pool: any[]): any[] {
  const byType = new Map<string, any[]>()
  for (const q of pool) {
    const t = normalizeType(q.questionType ?? q.question_type)
    if (!byType.has(t)) byType.set(t, [])
    byType.get(t)!.push(q)
  }

  const picked: any[] = []
  for (const row of cfg.typeRows) {
    const list = byType.get(row.type) || []
    if (!list.length || row.count <= 0) continue
    const shuffled = [...list]
    // Fisher-Yates：比 sort(() => Math.random() - 0.5) 分布更均匀
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    for (const q of shuffled.slice(0, row.count)) {
      picked.push({ ...q, _mockScore: Number(row.score) || 0, _mockType: row.type })
    }
  }

  // 整体混排
  for (let i = picked.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[picked[i], picked[j]] = [picked[j], picked[i]]
  }
  return picked
}

/** 取某题的标准答案（与原判分逻辑同口径，但只读不依赖 answers 数组位置） */
function correctAnswerOf(q: any): any {
  return q.correctAnswer ?? q.answer
}

/**
 * 判定一道题对错，并返回实得分
 *
 * 与原 `correctCount` 计算的差别只在多选题：
 *   · 原逻辑：必须完全一致才算对（0/1）；
 *   · 这里额外支持 `partial`（漏选按比例得分），且**错选一律 0 分** ——
 *     这是绝大多数真实考试的规则，也是用户截图里那个选项的语义。
 */
function judgeMockItem(q: any, userAnswer: any, cfg: MockExamConfig): { isCorrect: boolean; gotScore: number } {
  const full = Number(q._mockScore) || 0
  const type = String(q._mockType || q.type || 'unknown')
  const correct = correctAnswerOf(q)

  const empty = userAnswer === null || userAnswer === undefined ||
    (Array.isArray(userAnswer) && userAnswer.length === 0) ||
    (typeof userAnswer === 'string' && userAnswer.trim() === '')
  if (empty) return { isCorrect: false, gotScore: 0 }

  if (type === 'multiple') {
    const user = (Array.isArray(userAnswer) ? userAnswer : [userAnswer]).map(String).sort()
    const std = (Array.isArray(correct) ? correct : String(correct).split(/[,，]/)).map(String).sort()
    const exact = user.length === std.length && user.every((v, i) => v === std[i])
    if (exact) return { isCorrect: true, gotScore: full }

    const noWrongPick = user.every((v) => std.includes(v))
    if (cfg.multipleMode === 'partial' && noWrongPick && user.length > 0) {
      // 漏选：按已选对的比例给分（比例可配），封顶不超过满分
      const ratio = Math.min(1, Math.max(0, Number(cfg.partialRatio) || 0)) * user.length
      const got = Math.min(full, Math.round(full * ratio * 10) / 10)
      return { isCorrect: false, gotScore: got }
    }
    return { isCorrect: false, gotScore: 0 }
  }

  if (type === 'fillblank' || type === 'essay') {
    const ok = String(userAnswer).trim().toLowerCase() === String(correct ?? '').trim().toLowerCase()
    return { isCorrect: ok, gotScore: ok ? full : 0 }
  }

  // 单选 / 判断：严格相等
  const ok = String(userAnswer) === String(correct)
  return { isCorrect: ok, gotScore: ok ? full : 0 }
}

/** 从题目里取一段纯文本题干（列表展示用） */
function plainStem(q: any): string {
  const raw = String(q?.content ?? q?.questionText ?? q?.question ?? q?.mainContent ?? '')
  return raw
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 160)
}

/** 点击「开始考试」 */
async function handleMockStart(cfg: MockExamConfig) {
  activeMockConfig.value = JSON.parse(JSON.stringify(cfg))
  examStartAt.value = Date.now()

  // 重新按配置组卷（不能复用配置页那次统计的结果，用户可能刚改过）
  try {
    const res: any = await listQuestionMainAll({ bankId: props.bankId, status: '0' })
    const pool: any[] = Array.isArray(res?.data) ? res.data
      : Array.isArray(res?.result) ? res.result : []
    if (!pool.length) {
      proxy.$modal.msgWarning('这个题库还没有题目，无法开始考试')
      mockPhase.value = 'setup'
      return
    }
    const paper = buildMockPaper(cfg, pool)
    if (!paper.length) {
      proxy.$modal.msgWarning('按当前配置没有抽到题目，请调整题型题数')
      mockPhase.value = 'setup'
      return
    }
    /*
     * 把整份卷子一次性塞进 allQuestionsData，并让 questionOffset 归零。
     *
     * 为什么不走分波（questionCount 切片）：
     *   模拟考试的"题数"是由配置决定的整卷，不该再被"每波 10 题"这个刷题偏好切片，
     *   否则用户设了 40 题却只做到 10 题就必须点"继续下一波"，不像考试。
     *   这里直接用 `processQuestions` 处理全量，再把切片宽度放到整卷长度。
     *
     * ⚠️ 偏移量必须一起归零：`questionOffset` 是**按全库题数**记的分波进度，
     *    用户在别的模式刷到第 3 波再回来考试时它还是 20 —— 于是卷子从第 21 条
     *    开始取，前 20 条直接没了（表现为"交卷只有几道题"）。
     */
    const prevOffset = questionOffset.value
    updateQuestionOffset(0)
    updateQuestionCount(paper.length)
    processQuestions(paper).then(() => {
      // 卷子处理完把偏移量还回去，不影响用户在其它模式的分波进度
      updateQuestionOffset(prevOffset)
    })
  } catch (e) {
    console.error('[mock] 组卷失败', e)
    proxy.$modal.msgError('组卷失败，请重试')
    mockPhase.value = 'setup'
    return
  }

  mockPhase.value = 'running'
  // 进入考卷后再启动计时（配置页不该消耗考试时间）
  await nextTick()
  startExamTimer()
}

/** 交卷：判分 + 生成记录 + 切到总结页 */
function handleMockSubmit() {
  const cfg = activeMockConfig.value
  if (!cfg) return

  const items: MockExamItemDetail[] = []
  let gotScore = 0
  let correct = 0
  let wrong = 0

  questions.value.forEach((q: any, i: number) => {
    const userAnswer = answers.value[i]
    const { isCorrect, gotScore: gs } = judgeMockItem(q, userAnswer, cfg)
    gotScore += gs
    if (isCorrect) correct += 1
    else wrong += 1
    items.push({
      questionId: q.id,
      index: i + 1,
      type: (q._mockType || q.type || 'unknown') as any,
      stem: plainStem(q),
      userAnswer,
      correctAnswer: correctAnswerOf(q),
      isCorrect,
      gotScore: gs,
      fullScore: Number(q._mockScore) || 0,
      analysis: String(q.analysis ?? '') || undefined
    })
  })

  const fullScore = items.reduce((s, it) => s + (Number(it.fullScore) || 0), 0)
  const durationSec = examStartAt.value
    ? Math.max(0, Math.round((Date.now() - examStartAt.value) / 1000))
    : 0

  const record: MockExamRecord = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    bankId: props.bankId,
    bankName: props.bankName,
    submittedAt: Date.now(),
    config: JSON.parse(JSON.stringify(cfg)),
    totalQuestions: items.length,
    correctCount: correct,
    wrongCount: wrong,
    gotScore: Math.round(gotScore * 10) / 10,
    fullScore,
    /*
     * ⚠️ `fullScore <= 0` 时**一律判不及格**（2026-10-22 修的 bug）。
     *
     * 旧写法直接比 `gotScore >= passScore`。一旦满分因为配置读错而算成 0，
     * 而及格分也是 0，就成了"一题没做对也显示通过"—— 这是最不能出现的那种错。
     * 满分拿不到说明这张卷子本身有问题，不应该给出"通过"的结论。
     */
    passed: fullScore > 0 && gotScore >= (Number(cfg.passScore) || 0),
    durationSec,
    items
  }

  currentExamRecord.value = record
  store.addMockExamRecord(record)

  // 收尾：停计时、清考试存储、展开解析
  stopExamTimer()
  clearExamStorage()
  showAllAnalysis()
  totalScore.value = Math.round(record.gotScore)
  showExamResult.value = true
  mockPhase.value = 'summary'
}

/** 从总结页「再考一次」 */
function handleMockAgain() {
  currentExamRecord.value = null
  /*
   * ⚠️ `historyRecord` 必须一起清（2026-10-22）。
   *
   * 它是"当前看的是不是历史回看"的标记。如果重考时不清，
   * 下一场交卷后总结页会因为 `readonly = !!historyRecord` 仍为真，
   * 而把按钮显示成「返回记录」—— 用户刚考完却找不到"再考一次"。
   */
  historyRecord.value = null
  showExamResult.value = false
  totalScore.value = 0
  mockPhase.value = 'setup'
  loadMockAvailability()
}

/** 从历史记录打开一条 */
function handleOpenHistoryRecord(r: MockExamRecord) {
  historyRecord.value = r
  currentExamRecord.value = r
  mockPhase.value = 'summary'
}

/** 历史回看时点「返回记录」→ 回考试记录列表 */
function handleMockBackToHistory() {
  historyRecord.value = null
  currentExamRecord.value = null
  mockPhase.value = 'history'
}

/**
 * 实时切换「选项乱序」（2026-10-22）
 *
 * 需求口径：这三个入口的答题卡上，用户点开关就要**当场打乱/还原选项**，
 * 而不是"改了设置、下次进来才生效"。
 *
 * ⚠️ 关键取舍：切换后**要不要清空已选答案**？
 *    不清 —— 用户可能答了几题才发现想打乱。清掉等于把进度删了，这是最不能接受的。
 *    但打乱后选项下标变了，原来选"第 2 个"现在指向别的选项文案 ——
 *    这会让"用户以为自己选的 A 变成了 B"。
 *
 *    处理办法：`useQuestionPractice.displayOptions` 打乱时用的是**稳定的随机种子**
 *    （见那里的注释），同一道题在同一会话内重复打乱得到同一个顺序；
 *    且答案按**选项内容**而非下标存储于 `answers`（单选/多选存的是原始下标，
 *    经 `selectOption` 归一）。因此切换开关**只影响显示顺序**，不改变已选内容的语义。
 *
 *    这里只做三件事：写 store、清乱序缓存（让下次进入重新打乱）、提示用户。
 */
function handleToggleShuffle(val: boolean) {
  if (moduleTypeSafe.value === 'mock') return
  /*
   * 只写 store —— 打乱由 `QuestionDisplay` 的 `displayOptions` 负责。
   *
   * `moduleSettings` 是 `store.getModuleSettings()` 的 computed，
   * 写进 store 后它会重算，`shuffle-options` prop 随之变化，
   * `QuestionDisplay` 里的 computed 立刻重新洗牌或还原 —— 实时生效，无需刷新。
   */
  store.saveModuleSettings(props.moduleType, { shuffleOptions: val })
  proxy.$modal.msgSuccess(val ? '已打乱选项顺序' : '已恢复选项原始顺序')
}

/*
 * ⚠️ 这里原本有个 `handleMockSummaryBack`，逻辑是
 *     「historyRecord 有值就回历史列表，否则重新开考」。
 *   它被「再考一次」按钮调用，于是从历史详情进来的用户点「再考一次」
 *   会被送回考试记录列表 —— 文案说重考，行为是回列表，严重不符预期。
 *
 *   现在拆成两个语义明确的事件（见 ExamSummary 的 readonly prop）：
 *     · retry           → handleMockAgain（真的重新开考）
 *     · back-to-history → handleMockBackToHistory（回列表）
 *   不要再合并回一个函数，那样又会把两个动作搅在一起。
 */

// 进入 mock 模块时的初始化：拉题量、复位阶段
watch(
  () => [props.moduleType, props.bankId],
  async () => {
    if (moduleTypeSafe.value !== 'mock') return
    historyRecord.value = null
    currentExamRecord.value = null
    showExamResult.value = false
    totalScore.value = 0
    mockPhase.value = 'setup'
    await loadMockAvailability()
  },
  { immediate: true }
)


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
/**
 * 手动暂存（答题卡底部按钮）
 *
 * ⚠️ 考试态直接拒绝（2026-10-20）：
 *   界面上考试态已经不显示暂存按钮了（见 `AnswerCard` 的 `v-if="isExamMode"` 分支），
 *   但这里仍然防守一次 —— 原因是"按钮不显示"靠的是模板条件，
 *   任何人以后新增一个入口（快捷键 / 右键菜单 / 别的组件调它）都会绕过那个条件，
 *   而"考试中途可存"是**产品语义上的错误**，不该只靠 UI 拦。
 *
 *   注意：这不代表考试过程的答案不保护。`draftSaver` 的自动写盘照常工作，
 *   刷新回来答案还在 —— 那是技术兜底，不是给用户的"暂存"功能。两者不是一回事。
 */
const handleManualSaveDraft = () => {
  if (isExamMode.value) return
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

  /*
   * 关于 `draft.questionIds` 和"恢复题目顺序"
   * =================================================================
   * 上一版（同一天早些时候）我在这里做过「按快照重排 allQuestionsData」，
   * 用来修"刷新题号变、题目不变"。**现已移除**，原因：
   *
   *   那是治标。病根是「随机顺序每次刷新都会重算」，所以只能事后用快照把顺序掰回去，
   *   两个数据源（题单快照 vs 重新洗牌）互相拉扯，迟早还会出别的问题。
   *
   *   用户给的方案是治本：「随机只随机一次，没练完就一直用这份」——
   *   顺序本身持久化了（见 `useQuestionPractice.buildRandomPlan` / `loadRandomPlan`），
   *   刷新后重新加载拿到的**就是同一份题单**，顺序天然一致，
   *   于是下面按 `currentQuestionId` 定位也天然正确，不需要任何重排补丁。
   *
   *   `questionIds` 仍然保留在草稿结构里：它记录"这份题单当时包含哪些题"，
   *   在有多个题库入口或将来做"跨设备继续"时是有意义的元数据。
   *   只是现在**不再需要**靠它来纠正顺序了。
   */

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

  /*
   * 定位到上次那一题（按 id，不按数组下标）
   *
   * ⚠️ 随机模式也**要跳**（2026-10-20 最终结论，推翻了我当天早些时候的判断）：
   *   当时我以为"随机模式不跳、回到第一题"更像随机，但这会让用户
   *   **看不出进度被恢复了** —— 明明做到第 5 题，刷新后回到第 1 题，
   *   还要自己往下翻，体验比"跳回上次那题"差。
   *
   *   现在顺序是持久化的（随机题单存 localStorage），题号与题目的对应关系
   *   刷新后不变，所以按 id 跳回去**不会**出现"题号变、题目不变"——
   *   那个老 bug 的根因（每次刷新重排）已经没了。
   *   既然顺序稳定，"上次那一题"就是一个确定的、唯一的位置，跳过去是对的。
   */
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

/**
 * 交卷（判分 + 出成绩）
 * ============================================================================
 * ⚠️ 不能直接判分，必须先确认（2026-10-20 加的）：
 *
 *   改前是「点一下交卷 → 立刻判分出成绩」，中间没有任何阻挡。
 *   这在模拟考试里是个**不可逆**的操作：倒计时还在跑、手里可能还有没答的题，
 *   误点一下就再也回不去了（`showExamResult` 一旦为 true，
 *   答题状态就被结算态覆盖）。
 *
 *   所以分成两条路径：
 *     · **时间到**（`handleTimeUp` 调它）→ 直接判分，不问 ——
 *       考试时间已经用尽，用户没有选择权，问一遍是多余的骚扰；
 *     · **用户主动交卷** → 先确认，并把"还有几道没答"明确告诉他，
 *       让他有机会返回补答。这是考试产品最基本的防误触。
 *
 *   确认框的文案尽量"可决策"：说清楚未答数量和后果（交卷后不能修改），
 *   而不是干巴巴一句"确定交卷吗"。
 */
const handleSubmitExam = (options: { skipConfirm?: boolean } = {}) => {
  const doSubmit = () => {
    /*
     * 模拟考试走独立的判分与结果页（2026-10-22）。
     *
     * 分歧点：原来的 `Math.round(correct/total*100)` 是"按题数算百分比"，
     * 而模拟考试的分值是按题型配置的（单选 2 分、多选 4 分……），
     * 还可能有多选漏选按比例给分 —— 用"题数百分比"当分数是错的。
     * 所以 mock 交给 `handleMockSubmit`，其余模块保持原逻辑不变。
     */
    if (isMockFlow.value && activeMockConfig.value) {
      handleMockSubmit()
      return
    }
    showAllAnalysis()
    const score = Math.round((correctCount.value / totalQuestions.value) * 100)
    totalScore.value = score
    showExamResult.value = true
    // 清除考试计时器存储
    clearExamStorage()
    stopExamTimer()
  }

  // 时间到 → 直接判分（用户没有选择权，见上面的注释）
  if (options.skipConfirm) {
    doSubmit()
    return
  }

  /*
   * 主动交卷 → 确认。
   *
   * 用 `totalQuestions - answeredCount` 算未答数量：
   * 这两个都是"当前这一波/整场"的口径，和答题卡上显示的数字一致，
   * 不会出现"提示说 3 道没答、答题卡显示 2 道"这种自相矛盾。
   */
  const unanswered = Math.max(0, totalQuestions.value - answeredCount.value)
  const tip = unanswered > 0
    ? `还有 ${unanswered} 道题没有作答。\n交卷后不能修改答案，确定现在交卷吗？`
    : '所有题目都已作答。\n交卷后不能修改答案，确定交卷吗？'

  ElMessageBox.confirm(tip, '确认交卷', {
    confirmButtonText: '确认交卷',
    cancelButtonText: '继续答题',
    type: unanswered > 0 ? 'warning' : 'info',
    // 交卷是重要动作，先别让用户误关（点空白处不关闭）
    closeOnClickModal: false
  })
    .then(() => doSubmit())
    .catch(() => {
      // 用户选择继续答题 → 什么都不做，保持当前进度
    })
}

// 结束考试：清空模拟考试缓存并关闭
const handleFinishExam = () => {
  console.log(`[EXAM] handleFinishExam 被调用`)
  // 重置考试结果状态
  showExamResult.value = false
  totalScore.value = 0
  hasSubmittedCurrentBatch.value = false
  /*
   * 结算结束 → 撤掉那一层"临时整体浏览"（2026-10-21）。
   *
   * `forceOverview` 是结算为了展示瀑布流临时打开的（见它的定义处）。
   * 不复位的话，即使 `moduleSettings.isOverviewMode` 一直是 false，
   * `isOverviewActive` 也会恒为 true —— 用户「结束」完再进这个模块，
   * 或切到别的题继续练，看到的仍是瀑布流，他的偏好被这层临时态盖住了。
   * 这里只动本地态，不碰 store。
   */
  forceOverview.value = false
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

watch(isOverviewActive, (val) => {
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
/*
 * 「只刷错题」状态条（2026-10-20 重做视觉）
 *
 * 设计意图（为什么不再是黄色横幅）：
 *   旧版满宽 `#fef3c7` 黄底 + `#fcd34d` 边框，是**告警**的视觉语言。
 *   但「当前在错题模式」是一个**正常状态**，不是需要警觉的异常 ——
 *   用户每次看题都被一条黄条晃一下，注意力成本完全不划算。
 *
 * 新版三要素，克制且可操作：
 *   · chip   中性底 + 主色图标 = 「筛选已生效」，与全站 `.os-chip` 同一调性
 *   · text   次级灰字，说明"在做什么"，读者扫一眼就够
 *   · action 右侧文字按钮，把"想退出/调整"的出口放在原地，而不是让用户找齿轮
 *
 * 三个元素同一行、纵向居中、间隔用 gap 控制，整体只占一行高度，
 * 不再像旧版那样撑出一条独立色块。
 */
.only-wrong-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 24px 6px;
  min-height: 24px;
  /*
   * 宽度只到「内容需要的程度」，不撑满整行。
   *
   * ⚠️ 这里必须限定宽度：如果容器满宽，右侧的「调整」会被推（或靠 auto 甩）到页面
   * 最右边，离 chip 一千多像素远，看起来像两个不相干的元素
   * （第一版就是这样：截图里「调整」孤零零挂在右缘，还贴着答题卡）。
   *
   * 现在：容器 `max-content` 收缩 + `__action` 不用 margin auto ——
   * 三者始终是一个贴在一起的小组。
   */
  width: max-content;
  max-width: 100%;
}

.only-wrong-bar__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  /* 发丝描边 + 极浅中性底：靠形状区分，不靠高饱和色块 */
  border: 1px solid var(--os-border);
  background: var(--os-bg-subtle);
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  color: var(--os-text);
  white-space: nowrap;
}

.only-wrong-bar__icon {
  /* 图标是这条里唯一带颜色的元素 —— 一眼定位"这里有筛选" */
  color: var(--os-accent);
}

.only-wrong-bar__text {
  font-size: 12px;
  line-height: 1;
  color: var(--os-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.only-wrong-bar__action {
  appearance: none;
  border: 0;
  background: none;
  padding: 0 2px;
  /* 不用 margin-left:auto —— 那会把它推到容器最右（见 .only-wrong-bar 的注释） */
  font-size: 12px;
  line-height: 1;
  color: var(--os-text-3);
  cursor: pointer;
  transition: color var(--ds-duration-base, 0.15s) ease;
}

.only-wrong-bar__action:hover {
  color: var(--os-accent);
}

/*
 * 「只刷错题」但没有可练错题的空态
 *
 * 与 `.only-wrong-hint`（黄色提示条）分工不同：
 *   提示条 = 「当前是错题模式」这个**状态**；
 *   空态   = 「这个模式下没有可练的题」这个**结果 + 下一步**。
 * 两者可以同时出现，所以空态自己要有足够的垂直空间，不跟提示条挤在一起。
 *
 * 配色用中性灰（`--os-text-*`），不用红色 —— 这不是错误。
 *
 * ⚠️ 为什么用 `min-height` 而不是 `flex: 1`（2026-10-21 实测）：
 *   `.practice-container` 是 `flex-direction: column`，但它的高度**由内容决定**
 *   （不是 100% / 100vh）—— 父级 `.os-content` 是普通滚动容器，不是
 *   `is-flush` 的 flex 列。实测 `.practice-container` 只有 357px 高，
 *   而可视区有 1948px。于是 `flex: 1` 完全撑不开，空态贴在最上面，
 *   下面留一大片白 —— 看起来像"没渲染完"。
 *
 * 高度用 `calc(100vh - 240px)` 而不是固定值/百分比：
 *   · `%` 需要父级有确定高度，而父级高度正是"内容决定"，永远算不出来；
 *   · 固定 px 在小窗口上会把整块撑出滚动条，在大屏上还是偏上。
 *   240px ≈ 顶栏(52) + 练习头(约 90) + 错题状态条(约 30) + 上下留白，
 *   实测这个余量正好让内容在可视区里居中、且不产生多余滚动。
 * 外面套一层 `max(320px, …)`：窗口很矮时（比如 600px 高的笔记本分屏）
 *   保证仍能看到图标+文案+按钮，不会被压成一条。
 */
.practice-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: max(320px, calc(100vh - 240px));
  padding: 48px 24px;
  text-align: center;
}

.practice-empty__icon {
  color: var(--os-text-4, #9ca3af);
}

.practice-empty__title {
  margin: 2px 0 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--os-text, #111827);
}

.practice-empty__desc {
  margin: 0;
  max-width: 420px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-3, #6b7280);
}

.practice-empty__actions {
  display: flex;
  gap: 10px;
  margin-top: 6px;
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
