<template>
  <div class="practice-container" ref="containerRef">
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
      @retry="handleMockRetryFromSummary"
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

      <div v-if="recentSession && moduleType !== 'mock'" class="recent-practice">
        <span>上次练习：<b>{{ recentSession.percentage }} 分</b> · 答对 {{ recentSession.correctCount }} / {{ recentSession.totalCount }}</span>
        <button type="button" class="recent-practice__link" @click="openRecentSession">查看成绩</button>
      </div>

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
              :shuffle-options="effectiveShuffleOptions"
              :need-submit="!isExamMode && needsSubmit(item) && !committedQuestions[index]"
              :committed="!!committedQuestions[index]"
              @select-option="(optIdx) => handleOverviewSelect(index, optIdx)"
              @update-answer="(value) => handleOverviewUpdateAnswer(index, value)"
              @select-sub-option="(subIndex, optIdx) => handleOverviewSelectSubOption(index, subIndex, optIdx)"
              @update-sub-fill-blank-answer="(subIndex, value) => handleOverviewUpdateSubFillBlank(index, subIndex, value)"
              @update-sub-essay-answer="(subIndex, value) => handleOverviewUpdateSubEssay(index, subIndex, value)"
              @commit-answer="handleCommitAnswer(index)"
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
          :module-type="moduleTypeSafe" :draft-state="draftState" :number-base="numberBase"
          :shuffle-options="effectiveShuffleOptions"
          :scrollable="scrollable"
          @scroll-top="handleScrollTop" @scroll-bottom="handleScrollBottom"
          @update:shuffle-options="handleToggleShuffle"
          @go-to-question="scrollToQuestion" @toggle-overview="toggleOverview"
          @reset-practice="resetPractice" @submit-exam="handleSubmitExam" @finish-exam="handleFinishExam" />
      </div>
    </template>

    <!-- 逐题模式（原有布局） -->
    <template v-else>
      <PracticeHeader :mode="moduleTypeSafe" :bank-name="bankName" :formatted-time="formattedRemainingTime"
        :is-warning="isTimeWarning" :is-danger="isTimeDanger" @close="$emit('close')"
        @open-settings="openSettings" />

      <div v-if="recentSession && moduleType !== 'mock'" class="recent-practice">
        <span>上次练习：<b>{{ recentSession.percentage }} 分</b> · 答对 {{ recentSession.correctCount }} / {{ recentSession.totalCount }}</span>
        <button type="button" class="recent-practice__link" @click="openRecentSession">查看成绩</button>
      </div>

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
          :need-submit="!isExamMode && needsSubmit(currentQuestion) && !committedQuestions[currentQuestionIndex]"
          :committed="!!committedQuestions[currentQuestionIndex]"
          @commit-answer="handleCommitAnswer(currentQuestionIndex)"
          @update-answer="handleUpdateAnswer" @select-sub-option="selectSubOption"
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
          :draft-state="draftState" :number-base="numberBase"
          :shuffle-options="effectiveShuffleOptions"
          :scrollable="scrollable"
          @scroll-top="handleScrollTop" @scroll-bottom="handleScrollBottom"
          @update:shuffle-options="handleToggleShuffle"
          @go-to-question="goToQuestion" @reset-practice="resetPractice" @submit-exam="handleSubmitExam"
          @toggle-overview="toggleOverview" @finish-exam="handleFinishExam" />
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
      滚动入口已从「右下角悬浮球」搬到**答题卡内部**（2026-10-22）
      ==================================================================
      用户明确否掉了两版浮层方案：
        ① 浮球 + 悬浮助手叠在右下角 → 两个浮层挤在一起，还压住答题卡；
        ② 方案A 用 `avoidSelector` 动态测量把二者错开
           → 「不行这样做 没有解决不美观的问题 回滚换别的方案」。
      结论不是"再摆一次位置"，而是**练习页不要常驻浮层**：
      滚动能力收进答题卡这一列（见 `AnswerCard` 的 `.scroll-anchors`），
      右下角留白。所以这里不再渲染 `<ScrollButton>`。

      ⚠️ 不要因为"看着空"又把 ScrollButton 加回来 ——
         那会立刻重现用户抱怨的拥挤感，且与答题卡右缘重叠。
      滚动宿主的探测复用 `@/utils/scrollHost`（与 ScrollButton 同一套判据，
      落在真正在滚的外壳 `.os-content` 上，不写死容器）。
    -->

    <ImageViewer v-model:visible="viewerVisible" :src="viewerSrc" />
  </div>
</template>

<script setup lang="ts">
import {
	ref, reactive, computed, watch, getCurrentInstance, nextTick,
	onMounted, onUnmounted, onActivated, onDeactivated
} from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import PracticeHeader from './PracticeHeader.vue'
import QuestionDisplay from './QuestionDisplay.vue'
import AnswerCard from './AnswerCard.vue'
import QuestionNavigation from './QuestionNavigation.vue'
import PracticeSettings from './PracticeSettings.vue'
import MarkedButton from '@/components/MarkedButton/MarkedButton.vue'
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
/*
 * 滚动宿主探测（2026-10-22）
 *
 * 练习页原来在右下角渲染 `<ScrollButton>` 浮球。用户指出「浮球 + 悬浮助手 +
 * 右侧答题卡」三样东西挤在一起、不简洁，错开摆放也救不回来。
 * 现在滚动入口收进答题卡内部（静态的「回到顶部 / 跳到底部」两个文本按钮），
 * 浮球不再出现。判据复用同一个 util，保证"到底在滚谁"始终只有一份答案。
 */
import { usePracticeScrollHost } from './usePracticeScrollHost'
import { usePracticeExamTimer } from './usePracticeExamTimer'
import { usePracticeDraft } from './usePracticeDraft'
import { usePracticeAnswerFlow } from './usePracticeAnswerFlow'
import { usePracticeMockSession } from './usePracticeMockSession'
import { usePracticeMockResult } from './usePracticeMockResult'
import { usePracticeMockHistory } from './usePracticeMockHistory'
import { usePracticeRecentSession } from './usePracticeRecentSession'
import { usePracticeQuestionMeta } from './usePracticeQuestionMeta'
import { usePracticeSettings } from './usePracticeSettings'
import { usePracticeOverview } from './usePracticeOverview'
import { usePracticeMockSetup } from './usePracticeMockSetup'
import { usePracticeAnalysis } from './usePracticeAnalysis'
import { usePracticeRouteWatches } from './usePracticeRouteWatches'
import { usePracticeLifecycle } from './usePracticeLifecycle'
import { usePracticeSubmission } from './usePracticeSubmission'
import { usePracticeStream } from './usePracticeStream'
import { usePracticeInput } from './usePracticeInput'
import { usePracticeSubmitAction } from './usePracticeSubmitAction'
import { usePracticeViewWatchers } from './usePracticeViewWatchers'
import { usePracticeWatchers } from './usePracticeWatchers'
import { usePracticeMockState } from './usePracticeMockState'
// 「只刷错题」空态要用线性图标（全站统一走 OsIcon，不用 Element Plus 实心图标）
import OsIcon from '@/components/OsIcon/index.vue'
import ImageViewer from './ImageViewer.vue'
import { useQuestionPractice } from '@/composables/useQuestionPractice'
import usePracticeSettingsStore from '@/store/modules/practiceSettings'
import useUserStore from '@/store/modules/user'
import {
} from '@/utils/practiceDraft'
import AiAnalysisDialog from '@/components/AiAnalysisDialog/index.vue'
// 模拟考试的三个新界面（2026-10-22）
import MockExamSetup from './MockExamSetup.vue'
import ExamSummary from './ExamSummary.vue'
import MockExamHistory from './MockExamHistory.vue'
import type { MockExamConfig, MockExamRecord } from '@/types'
// 模拟考试组卷要拉全量题目（见 loadMockAvailability / handleMockStart）
import { submitPracticeSession, listPracticeSessions, getPracticeSession } from '@/api/questionMain/questionMain'
/*
 * 模拟考试的判分（2026-10-28 从本文件搬出去）
 *
 * ⚠️ 搬走的唯一目的：**让它能被单测直接 import**。
 *    `judgeMockItem` 原来是本文件 `<script setup>` 里的局部函数，测试拿不到它，
 *    只能在浏览器里点一遍 UI 才能验 —— 慢且脆；或者在测试里抄一份公式，
 *    那验的是副本，改了实现测试照样绿（假测试）。
 *    判分算错是用户当场就能发现的错，必须有参数化的纯函数级测试兜住。
 *    实现与注释都在 `utils/mockExamJudge.ts`（逐字搬移 + F7 的漏选公式修正）。
 */
// 服务端判分后不再在前端使用 judgeMockItem；保留该工具供独立单测，
// PracticeComponent 只负责渲染服务端返回的逐题结果。
/*
 * 模拟考试「进行中会话」的持久化（2026-10-22）
 *
 * 用户 bug：考试中刷新页面 → 卷子消失、回到配置页。
 * 详见 `utils/mockExamSession.ts` 顶部的根因分析。
 */
import {
} from '@/utils/mockExamSession'

// 调试日志工具
import {
  debugEnterModule,
  debugLeaveModule,
  debugWatchTrigger,
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
const {
  mockPhase,
  isMockFlow,
  showMockSetupUI,
  showMockSummaryUI,
  activeMockConfig,
  effectiveShuffleOptions,
  mockAvailable,
  currentExamRecord,
  historyRecord,
  examStartAt,
  showExamResult,
  totalScore,
  showAnalysisDialog,
  viewerVisible,
  viewerSrc,
  hasSubmittedCurrentBatch,
  isFirstLoaded,
  examTimeLimit
} = usePracticeMockState({ moduleTypeSafe, moduleSettings })

const {
  containerRef,
  scrollable,
  ensureScrollHost,
  syncScrollState,
  bindPracticeScrollHost,
  unbindPracticeScrollHost,
  scheduleScrollHostBinding,
  handleScrollTop,
  handleScrollBottom
} = usePracticeScrollHost()

const {
  remainingTime,
  formattedRemainingTime,
  isTimeWarning,
  isTimeDanger,
  startExamTimer,
  stopExamTimer,
  clearExamStorage,
  bindVisibility,
  unbindVisibility
} = usePracticeExamTimer({
  getModuleType: () => props.moduleType,
  getBankId: () => props.bankId,
  examTimeLimit,
  showExamResult,
  onTimeUp: () => handleSubmitExam({ skipConfirm: true })
})


let hasBeenDeactivated = false

const highlightedIndex = ref(0)
const markedQuestions = ref<number[]>([])
const questionStreamRef = ref<HTMLElement | null>(null)



const { proxy } = getCurrentInstance() as any

const { recentSession, loadRecentSession, openRecentSession } = usePracticeRecentSession({
  getBankId: () => props.bankId,
  getModuleTypeSafe: () => moduleTypeSafe.value,
  proxy
})

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
  fetchQuestions,
  resetAndFetchQuestions,
  // 随机题单：练完一轮/提交后清掉，下一轮重新随机
  clearRandomPlan,
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
  markQuestion,
  addNote,
  reportQuestion,
  favoritedQuestions,
  markedQuestions: backendMarkedSet,
  errorQuestions,
  practiceSessionId,
  applyServerGrade,
  ensurePracticeSession,
  updateOnlyWrong,
  updateQuestionCount,
  // 模拟考试组卷要用：把整份卷子灌进题目流（见 handleMockStart 的注释）
  processQuestions,
  updateQuestionOffset,
  loadBatchWithoutReset,
  updateQuestionCountAndSlice,
  saveCurrentAnswerState,
  clearAnswerStateCache
} = useQuestionPractice(props, { proxy }, {
  questionCount: moduleSettings.value.questionCount,
  onlyWrong: moduleSettings.value.onlyWrong
})

const { typeLabelMap, questionGroups, answeredCount, remainingCount } = usePracticeQuestionMeta({
  questions,
  answers,
  totalQuestions
})

const { showSettings, settingsSnapshot, handleSettingsSave, openSettings } = usePracticeSettings({
  moduleSettings,
  resetAndFetchQuestions,
  updateQuestionCountAndSlice
})

const {
  overviewMode,
  forceOverview,
  isOverviewActive,
  isEmptyState,
  handleEmptyRestart,
  handleEmptyTurnOffOnlyWrong
} = usePracticeOverview({
  moduleSettings,
  store,
  getModuleType: () => props.moduleType,
  noWrongQuestionsReason,
  questions,
  resetPractice,
  clearAnswerStateCache,
  resetAndFetchQuestions
})

const { markedQuestionsSet, toggleOverview, scrollToQuestion, onStreamScroll, handleMarkedChange, handlePrevBatch } = usePracticeStream({
  questions,
  markedQuestions,
  backendMarkedSet,
  highlightedIndex,
  questionStreamRef,
  isOverviewActive,
  forceOverview,
  overviewMode,
  hasSubmittedCurrentBatch,
  showExamResult,
  totalScore,
  moduleSettings,
  questionOffset,
  store,
  getModuleType: () => props.moduleType,
  loadBatchWithoutReset,
  goToQuestion
})

const {
  committedQuestions,
  isInstantJudgeType,
  needsSubmit,
  handleCommitAnswer,
  handleOverviewSelect,
  handleOverviewUpdateAnswer,
  handleOverviewSelectSubOption,
  handleOverviewUpdateSubFillBlank,
  handleOverviewUpdateSubEssay,
  jumpToNextBatch
} = usePracticeAnswerFlow({
  currentQuestion,
  currentQuestionIndex,
  questions,
  answers,
  selectedAnswer,
  isExamMode,
  isOverviewActive,
  moduleSettings,
  questionOffset,
  hasSubmittedCurrentBatch,
  showExamResult,
  totalScore,
  selectOption,
  selectSubOption,
  updateSubFillBlankAnswer,
  updateSubEssayAnswer,
  handleAnswerSubmission,
  loadBatchWithoutReset,
  startExamTimer,
  isMock: () => props.moduleType === 'mock',
  goToQuestion
})

/* ==================== 「已确认答案」标记的生命周期 ==================== */

/**
 * 这批题目换了 → 清空确认标记（2026-10-22）
 *
 * `committedQuestions` 的 key 是**波内下标**，它只在"同一批题目"内部有意义。
 * 但这些标记在以下路径上都可能残留：
 *   · 换波（`jumpToNextBatch` / `handlePrevBatch`）；
 *   · 重新练习（`handleEmptyRestart` → `resetAndFetchQuestions`）；
 *   · 改设置后重拉、切题库、切模块。
 *
 * 不清空的后果很具体：新一批题目的第 1 题会继承上一批第 1 题的"已确认"，
 * 于是多选/填空题一出现就是"已判分 + 解析展开"的样子，
 * 而且「确认答案」按钮**不显示** → 用户完全没法作答。
 *
 * 为什么用 watch 题目流、而不是在每个调用点手动清：
 *   重拉题目的入口有 5+ 处（上面列的那些），逐个加必然漏。
 *   这里盯住 `questions` 的**身份变化**（用首题 id 判断，不是长度），
 *   一次性覆盖全部路径。`jumpToNextBatch` 里那次显式清空可以保留 ——
 *   watch 是异步的，而换波后紧接着就会渲染，早清一步更稳。
 */
/* ============================================================================
 * 模拟考试：组卷 / 判分 / 生成记录（2026-10-22）
 * ============================================================================
 * 这一块整体是「新增的一段独立逻辑」，只在 moduleType === 'mock' 时启用，
 * 不影响其他三个刷题入口的任何行为。
 */

/** 题型归一：后端数字题型 → 前端字符串（与 useQuestionPractice 的映射保持一致） */
/**
 * 拉一份全量题目并按题型统计可选题量
 *
 * 配置页要显示「/ 262 道」这样的上限提示，必须先把题库拿到手。
 * ⚠️ 这里直接调接口而不是复用 `allQuestionsData`：后者可能只装了"某一波"的切片，
 *    也可能因为「只刷错题」被过滤过 —— 用它算上限会给出错误的可选范围。
 */
const { loadMockAvailability, handleMockStart } = usePracticeMockSetup({
  mockAvailable,
  activeMockConfig,
  examStartAt,
  mockPhase,
  practiceSessionId,
  store,
  proxy,
  getBankId: () => props.bankId,
  updateQuestionOffset,
  updateQuestionCount,
  processQuestions,
  startExamTimer,
  setMockSessionEndAt: (value) => { mockSessionEndAt = value }
})

/**
 * 从总结页点「再考一次」
 *
 * @param preset 要沿用的配置。不传就按"本场快照 / store 当前配置"兜底。
 *
 * 两种来源的区别（2026-10-22 用户明确要求「方便用户使用」）：
 *
 *   · 刚交完卷 → 沿用这一场的配置 `activeMockConfig`，天然一致。
 *   · 从考试记录回看 → 沿用那条记录的 `config` 快照。**不能**读 store 里
 *     当前的配置：用户可能后来改过（那次考的是 5 道单选×2 分，现在设置里
 *     是 20 道×2 分），直接拿 store 就会"重考"出一张完全不同的卷子，
 *     与按钮叫「再考一次」的承诺不符。
 *
 * ⚠️ 无论哪种来源，都要把这份配置**写回 store**：
 *   配置页是从 `store.getMockExamConfig()` 读的。不写回的话，用户重考完
 *   再回配置页，看到的是改之前的旧配置 —— 与刚才实际考的卷子对不上。
 */
const {
  handleMockAgain,
  handleOpenHistoryRecord,
  handleMockRetryFromSummary,
  handleMockBackToHistory,
  handleToggleShuffle
} = usePracticeMockHistory({
  activeMockConfig,
  currentExamRecord,
  historyRecord,
  showExamResult,
  totalScore,
  mockPhase,
  store,
  proxy,
  moduleTypeSafe,
  getModuleType: () => props.moduleType,
  handleMockStart
})

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

/* ==================== 模拟考试会话的持久化与恢复 ==================== */

/** 当前会话的结束时间戳（恢复 / 开考时确定，保存快照时复用） */
let mockSessionEndAt = 0

/*
 * ⚠️ `userStore` / `currentUserId` 必须在这之前定义
 *
 * 它们在下面「页面暂存」一节里也用到，但 `persistMockSession` /
 * `restoreMockSession` 出现得更早（会话恢复要在进模块的 watch 里就执行）。
 * 若仍写在后面，运行时一进 mock 模块就踩 TDZ：
 *   ReferenceError: Cannot access 'currentUserId' before initialization
 */
const userStore = useUserStore()

/** 取当前用户 id（登录态可能晚于组件挂载就绪，所以用函数而不是取值） */
const currentUserId = () => {
  const id = (userStore as any).id
  return id === undefined || id === null || id === '' ? null : id
}

const { persistMockSession, restoreMockSession } = usePracticeMockSession({
  isMockFlow,
  mockPhase,
  activeMockConfig,
  questions,
  answers,
  subFillBlankAnswers,
  subEssayAnswers,
  currentQuestion,
  currentQuestionIndex,
  questionOffset,
  practiceSessionId,
  examStartAt,
  getUserId: currentUserId,
  getBankId: () => props.bankId,
  getMockSessionEndAt: () => mockSessionEndAt,
  setMockSessionEndAt: (value) => { mockSessionEndAt = value },
  updateQuestionOffset,
  updateQuestionCount,
  processQuestions,
  startExamTimer
})

usePracticeViewWatchers({
  questions,
  committedQuestions,
  isOverviewActive,
  currentQuestionIndex,
  moduleTypeSafe,
  getModuleType: () => props.moduleType,
  getBankId: () => props.bankId,
  historyRecord,
  currentExamRecord,
  showExamResult,
  totalScore,
  mockPhase,
  ensureScrollHost,
  syncScrollState,
  restoreMockSession,
  loadMockAvailability
})



const { handleMockSubmit } = usePracticeMockResult({
  activeMockConfig,
  practiceSessionId,
  examStartAt,
  questions,
  answers,
  currentExamRecord,
  totalScore,
  showExamResult,
  mockPhase,
  getBankId: () => props.bankId,
  getBankName: () => props.bankName,
  store,
  proxy,
  getUserId: currentUserId,
  stopExamTimer,
  clearExamStorage,
  setMockSessionEndAt: (value) => { mockSessionEndAt = value },
  showAllAnalysis
})

/**
 * 把「当前进行中的考试」写进 localStorage
 *
 * ⚠️ 只在 `mockPhase === 'running'` 时写。配置页 / 结果页 / 历史页都不该有会话：
 *   · 配置页还没开考，没有"进行中的考试"；
 *   · 结果页的考试已经结束（记录进了历史），留着会话会让下次进来错误地恢复。
 */
/**
 * 考试进行中，作答变化 → 落一次会话
 *
 * ⚠️ 用 watch 而不是在每个作答入口手动调：
 *   作答入口有选项 / 子选项 / 填空 / 简答 / 组合题 5 类，
 *   逐个加必然漏（历史上已经漏过好几次）。这里盯住"答案整体变了"这一个信号。
 *
 * 不做节流的理由：考试时作答频率远低于练习（一次点击就是一次作答），
 * 而丢一次作答的代价很高（刷新后这题答案没了）。写入的是几百字节的 JSON，
 * 每点一下写一次的代价可以忽略。
 */
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
 *
 * ⚠️ `userStore` / `currentUserId` 已提前到上面「模拟考试会话」一节定义
 *    （`persistMockSession` 需要它们，且那段代码出现得更早）。不要在这里重复声明。
 */

/**
 * 自动保存状态
 *
 * ⚠️ 界面上已经**不再显示任何"自动保存成功"的提示**（2026-10-22 用户：
 *    「这个不用说明」）。保存是默认行为，没有意外时的提示全是噪音。
 *    这个 ref 现在只有一个消费方：`AnswerCard` 据此判断是否要渲染
 *    **失败**警示（写盘失败 = 真实的数据丢失风险，必须告知）。
 *
 * 演进记录（避免有人再加回提示）：
 *    ① 最初「进度已自动保存」+「暂存」按钮；
 *    ② 删掉按钮，只留「进度自动保存」；
 *    ③ 连这句也去掉 —— 只剩失败态。
 *
 * ⚠️ 手动「暂存」按钮同样已删除。确认过：`draftSaver.schedule()` 在每次作答 /
 *    判分 / 换题 / 换波后都会静默写盘（600ms 节流），离开页面时还会 `flush()`
 *    立刻落一次 —— 手动按钮调用的 `flush()` 与自动保存是同一个动作，纯属多余入口。
 */
const {
  draftState,
  draftSavedAt,
  buildDraftSnapshot,
  draftSaver,
  draftRestored,
  resetDraftRestored,
  restoreDraftIfAny
} = usePracticeDraft({
  getUserId: currentUserId,
  getBankId: () => props.bankId,
  getModuleType: () => props.moduleType,
  getQuestions: () => questions.value,
  getAnswers: () => answers.value,
  getSubFillBlank: () => subFillBlankAnswers.value,
  getSubEssay: () => subEssayAnswers.value,
  getCurrentQuestion: () => currentQuestion.value,
  getQuestionOffset: () => questionOffset.value,
  getQuestionCount: () => moduleSettings.value.questionCount || 10,
  getHasSubmittedCurrentBatch: () => hasSubmittedCurrentBatch.value,
  getCorrectCount: () => correctCount.value,
  getWrongCount: () => wrongCount.value,
  getModuleTypeSafe: () => moduleTypeSafe.value,
  getAllQuestionsData: () => allQuestionsData.value,
  isPracticeMode: () => isPracticeMode.value,
  loadBatchWithoutReset,
  goToQuestion,
  setQuestionOffset: (value) => { questionOffset.value = value }
})

usePracticeWatchers({
  answers,
  subFillBlankAnswers,
  subEssayAnswers,
  currentQuestionIndex,
  questionOffset,
  hasSubmittedCurrentBatch,
  questions,
  mockPhase,
  showExamResult,
  draftRestored,
  moduleTypeSafe,
  moduleSettings,
  isResetting,
  isOverviewActive,
  questionStreamRef,
  highlightedIndex,
  persistMockSession,
  draftSaver,
  restoreDraftIfAny,
  updateQuestionCountAndSlice,
  updateOnlyWrong,
  fetchQuestions
})

const { handleSubmitExam, handleFinishExam } = usePracticeSubmission({
  isMockFlow,
  activeMockConfig,
  practiceSessionId,
  questions,
  answers,
  totalQuestions,
  answeredCount,
  totalScore,
  showExamResult,
  hasSubmittedCurrentBatch,
  forceOverview,
  proxy,
  emit,
  ensurePracticeSession,
  handleMockSubmit,
  applyServerGrade,
  showAllAnalysis,
  loadRecentSession,
  clearExamStorage,
  stopExamTimer,
  clearAnswerStateCache
})

const { handleSubmit } = usePracticeSubmitAction({
  totalQuestions,
  answeredCount,
  hasSubmittedCurrentBatch,
  forceOverview,
  getModuleType: () => props.moduleType,
  clearRandomPlan,
  handleSubmitExam
})

usePracticeLifecycle({
  getModuleType: () => props.moduleType,
  getBankId: () => props.bankId,
  isFirstLoaded,
  showExamResult,
  setTimeUpDialogShowing: (value) => { isTimeUpDialogShowing = value },
  fetchQuestions,
  restoreDraftIfAny,
  loadRecentSession,
  startExamTimer,
  stopExamTimer,
  draftSaver,
  saveCurrentAnswerState,
  bindVisibility,
  unbindVisibility,
  bindPracticeScrollHost,
  scheduleScrollHostBinding,
  unbindPracticeScrollHost,
  debugEnterModule,
  debugLeaveModule
})

usePracticeRouteWatches({
  getModuleType: () => props.moduleType,
  getBankId: () => props.bankId,
  showExamResult,
  hasSubmittedCurrentBatch,
  remainingTime,
  saveCurrentAnswerState,
  resetAndFetchQuestions,
  resetDraftRestored,
  startExamTimer,
  stopExamTimer,
  clearExamStorage,
  debugWatchTrigger,
  debugLeaveModule,
  debugEnterModule
})

/*
 * 手动暂存入口已删除（2026-10-22）
 * ============================================================================
 * 原 `handleManualSaveDraft` 与 `draftButtonText` 一并移除。
 * 理由见上面 `draftState` 的注释：自动保存本来就在跑，
 * 手动按钮做的 `flush()` 与它是同一个动作，对用户是纯多余的心智负担。
 *
 * 真正的"离开前保证落盘"逻辑仍在 `onUnmounted` 里 `draftSaver.flush()`，
 * 那条不能删 —— 它防的是"节流窗口内用户直接关标签页"这种真实丢数据场景。
 */

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
function openImageViewer(src: string) {
  viewerSrc.value = src
  viewerVisible.value = true
}

const {
  analysisCache,
  currentAnalysisContent,
  isAnalysisGenerating,
  analysisTargetQuestion,
  openAiAnalysis,
  openAiAnalysisForQuestion,
  getQuestionTypeName,
  formatOptionsForAnalysis,
  getAnalysisQuestionText,
  updateAnalysisCache,
  setAnalysisGenerating,
  handleAnalysisClose
} = usePracticeAnalysis({ currentQuestion, showAnalysisDialog })

const { handleUpdateAnswer, handleSelectOption } = usePracticeInput({
  selectedAnswer,
  currentQuestionIndex,
  answers,
  questions,
  currentQuestion,
  totalQuestions,
  isExamMode,
  committedQuestions,
  isInstantJudgeType,
  handleAnswerSubmission,
  selectOption,
  moduleSettings,
  nextQuestion
})

/**
 * 填空 / 简答输入（逐题模式）
 *
 * ⚠️ 除了更新 `selectedAnswer`，**必须同步写进 `answers`**（2026-10-22）。
 *
 * 原来模板里是内联的 `value => selectedAnswer = value`，只改临时值：
 *   · 「确认答案」读的是 `answers[qIndex]` → 读到 `undefined` → 永远提示"请先作答"；
 *   · 自动保存快照也读 `answers` → 用户写的字从来没被存下来；
 *   · 点「下一题」时虽然会被 `handleAnswerSubmission` 补写，
 *     但如果用户一直停在这题、中途刷新，内容就丢了。
 *
 * 写 `answers` 而不是只在确认时写，还有一个原因：`buildDraftSnapshot`
 * 会据此判断"这题答过没有"，进而决定要不要写进暂存。
 */
defineExpose({})
</script>

<style scoped src="./PracticeComponent.style1.css"></style>

<style src="@/assets/styles/PracticeComponent.css"></style>
