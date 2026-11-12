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
const { recentSession, loadRecentSession, openRecentSession } = usePracticeRecentSession({
  getBankId: () => props.bankId,
  getModuleTypeSafe: () => moduleTypeSafe.value,
  proxy
})

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

/* ==================== 滚动状态（答题卡内的「回到顶部 / 跳到底部」） ==================== */

/**
 * 为什么把滚动状态放在 `PracticeComponent` 而不是 `AnswerCard` 里
 * ----------------------------------------------------------------------------
 * 因为**真正在滚的不是答题卡**：实测练习页滚的是外壳 `.os-content`
 * （scrollHeight 4938 / clientHeight 948），而 `.overview-question-stream`
 * 与答题卡自身都不滚。子组件若"从自己往上找"，第一个可滚祖先就是错的。
 *
 * 所以：探测 + 监听 + 执行滚动都留在本组件（它持有页面根节点 `containerRef`），
 * `AnswerCard` 只接收布尔值、只 emit 意图 —— 纯展示，不做 DOM 查询。
 */

/** 页面根节点，作为"向上找滚动宿主"的起点 */
const {
  containerRef,
  scrollable,
  bindPracticeScrollHost,
  unbindPracticeScrollHost,
  scheduleScrollHostBinding,
  handleScrollTop,
  handleScrollBottom
} = usePracticeScrollHost()

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


const examTimeLimit = computed(() => moduleSettings.value.examTimeLimit || 60)
let hasBeenDeactivated = false

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
  resetDraftRestored()

  // 3) 重置题目与作答，再去拉 B 题库的数据。
  //    ⚠️ 必须把 oldId 传进去：此刻 `props.bankId` 已经是新题库，
  //    `resetAndFetchQuestions` 内部会先 `saveCurrentAnswerState`，
  //    不带 oldId 就会把旧题库的题存进新题库的缓存 key（见该函数的注释）。
  resetAndFetchQuestions(props.moduleType, oldId)
})

watch(showExamResult, (val) => {
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
  // 服务端成绩回看：刷新/换设备后仍能看到上一次已交卷成绩
  loadRecentSession()

  // 添加页面可见性变化监听（幂等，见 bindVisibility 的注释）
  bindVisibility()

  /*
   * 绑定滚动宿主（答题卡里的「回到顶部 / 跳到底部」依赖它）
   *
   * 三次尝试的原因见 `bindPracticeScrollHost` 的注释：
   * 首次挂载时外壳内容区可能还没撑开，那时只能退回 window（不滚），
   * 等布局稳定再解析一次才能真正落到 `.os-content` 上。
   * 定时器存进 `scrollHostRetryTimers`，卸载时统一清掉。
   */
  scheduleScrollHostBinding()
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

  // 移除页面可见性变化监听（幂等，见 bindVisibility 的注释）
  unbindVisibility()

  // 解绑滚动宿主（含重试定时器）
  unbindPracticeScrollHost(true)
})

/*
 * ⚠️⚠️ 路由离场（**keep-alive**）的收尾与恢复（2026-10-28 修，审核发现 F1）
 * ============================================================================
 * 刷题页被两层 keep-alive 包着：
 *   · `views/questionPractice/questionPractice/index.vue` 里是裸 `<keep-alive>`；
 *   · `layout/front.vue` 里是 `<keep-alive :include="cachedViews">`，而
 *     `FrontQuestionPractice` 被显式注册进了 `cachedViews`。
 *
 * 于是「离开刷题页」**只会 deactivate，不会 unmount** —— 上面的 `onUnmounted`
 * 一次都不会跑。修之前，模拟考试的倒计时（`setInterval`）会带着整场考试
 * 继续在后台跑：走到 0 之后 `handleTimeUp()` 判断 `!document.hidden`
 * （用户此时在别的页面，document 当然可见）→ 在**无关的页面上**弹出
 * 「考试时间已到，系统将自动提交试卷！」→ 用户点确定就静默交卷并写进历史。
 * `visibilitychange` 监听同样一直挂着，从不解绑。
 *
 * 所以这里补一对 deactivated / activated，与 `onUnmounted` 同口径收尾：
 *   · 离场：停计时 + 摘监听 + 落一次暂存 + 解绑滚动宿主；
 *   · 回场：重新绑监听 / 滚动宿主，模拟考试进行中则续跑倒计时。
 *
 * 倒计时**不需要**重新计时：`startExamTimer()` 读的是 localStorage 里的
 * **绝对结束时间**（`openstudy_exam_end_time`），天然满足两个场景：
 *   · 离场期间没超时 → 按剩余时间续跑（考试是绝对deadline，离场不该"暂停"）；
 *   · 离场期间已超时 → `startExamTimer` 内部静默清存储并把 `remainingTime`
 *     归 0，**不弹窗、不自动交卷**（用户没在看这场考试，不该被远程交卷）。
 */
onDeactivated(() => {
  debugLeaveModule(props.moduleType, props.bankId)

  // 离开页面时立即落一次暂存（不走节流），与 onUnmounted 同口径
  try {
    draftSaver.flush()
  } catch {
    /* 暂存失败不该影响离开页面 */
  }
  draftSaver.cancel()

  stopExamTimer()

  unbindVisibility()

  unbindPracticeScrollHost(true)

  hasBeenDeactivated = true
})

onActivated(() => {
  /*
   * ⚠️ KeepAlive 下 `onActivated` 在**首次挂载时也会触发**（紧随 `onMounted`），
   *    不能在这里无条件再起一次倒计时 —— 那会和 `onMounted` 里的那次重复。
   *    只有"真的离场过再回来"才需要续跑。
   */
  const isReentry = hasBeenDeactivated
  hasBeenDeactivated = false

  debugEnterModule(props.moduleType, props.bankId)

  bindVisibility()

  bindPracticeScrollHost()

  // 离场后回场 + 模拟考试进行中 → 续跑
  // （绝对结束时间还在就按剩余时间走；已过则 startExamTimer 内部静默清掉）
  if (isReentry && props.moduleType === 'mock' && !showExamResult.value) {
    startExamTimer()
  }
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

const { typeLabelMap, questionGroups, answeredCount, remainingCount } = usePracticeQuestionMeta({
  questions,
  answers,
  totalQuestions
})

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
 * ==================== 作答 → 判题（两种模式共用） ====================
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
 *     等用户在题目下方点「确认答案」才判（见 `handleCommitAnswer`）。
 *
 * ⚠️ 这段判据**两种模式共用**（2026-10-22 修正）：
 *    上一版只有浏览模式接了这套逻辑，逐题模式既没有确认按钮、
 *    点选项也不判分（判分要等点「下一题」），属于功能缺失。
 *    现在 `needsSubmit` / `committedQuestions` / `handleCommitAnswer`
 *    同时服务逐题与浏览两条模板分支。
 *
 * 为什么用"是否即时判"的判定函数、而不是在模板里散写条件：
 *   同一套判断在 4 个入口（选项 / 子选项 / 填空 / 简答）都要用，
 *   QuestionDisplay 也要用它决定显示"确认答案"按钮还是直接出解析。
 */

/** 这类题型"选一个就能定论"，可以即时判；其余需要用户确认后再判 */
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
watch(
  () => questions.value.map((q: any) => q?.id).join(','),
  () => {
    committedQuestions.value = {}
  }
)

/* ==================== 滚动锚点：跟随展示内容变化重算 ==================== */

/**
 * 什么时候需要重新同步滚动状态
 * ----------------------------------------------------------------------------
 * 用户明确指出练习页有**两种模式**，两者的可滚量完全不同：
 *   · 逐题模式（一题一屏）→ 通常不溢出，锚点整行不出现；
 *   · 整体浏览（瀑布流）  → 几乎总是溢出，锚点必须有。
 *
 * ⚠️ 这里只调 `ensureScrollHost()`（幂等）+ `syncScrollState()`，
 *    **不**再拆监听：两种模式只替换页面内部的 DOM，真正在滚的外壳
 *    `.os-content` 是同一个元素。上一版每次都 `detach` 再靠 rAF 重绑，
 *    结果 rAF 被节流时监听永久丢失、状态卡死（详见 `onPracticeScroll` 的注释）。
 *
 * `questions.length` 也纳入：切题库 / 换波 / 换题量都会改变内容高度。
 * 用 `flush: 'post'` 是必须的：DOM 还没打完补丁时量出来的高度是旧的。
 */
watch(
  [() => isOverviewActive.value, () => questions.value.length],
  () => {
    ensureScrollHost()
    syncScrollState()
  },
  { flush: 'post' }
)

/**
 * 切题时也要重算
 *
 * 逐题模式下换一道题，内容高度可能从"不溢出"变成"溢出"（长题干 / 组合题），
 * 这时锚点才应该出现。不做这一步，用户必须切一下模式或滚一下才会更新。
 */
watch(
  () => currentQuestionIndex.value,
  () => {
    syncScrollState()
  },
  { flush: 'post' }
)

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

// 进入 mock 模块时的初始化：拉题量、复位阶段（或恢复进行中的考试）
watch(
  () => [props.moduleType, props.bankId],
  async () => {
    if (moduleTypeSafe.value !== 'mock') return
    historyRecord.value = null
    currentExamRecord.value = null
    showExamResult.value = false
    totalScore.value = 0

    /*
     * ⚠️ 这里**不能无条件** `mockPhase.value = 'setup'`（2026-10-22 修的 bug）
     *
     * 原来这一行是本 bug 的第一根因：用户考试中刷新页面，
     * 组件重建 → watch 立即执行 → 阶段被打回 setup → 看到的是配置页，
     * 而卷子、答案、配置全都只存在组件内存里，已经随刷新一起没了。
     *
     * 现在先尝试恢复"进行中的考试会话"：
     *   · 有且未过期 → 恢复卷子并直接进考试（`restoreMockSession` 内部处理计时的接续）；
     *   · 没有 / 已过期 → 才回到配置页。
     * 注意 `loadMockAvailability()` 两种情况都要跑：配置页要用它显示各题型可用题数。
     */
    const restored = await restoreMockSession()
    if (!restored) {
      mockPhase.value = 'setup'
    }
    await loadMockAvailability()
  },
  { immediate: true }
)

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
watch(
  [() => JSON.stringify(answers.value), () => JSON.stringify(subFillBlankAnswers.value), () => JSON.stringify(subEssayAnswers.value)],
  () => {
    if (mockPhase.value !== 'running') return
    persistMockSession()
  }
)

/** 换题也落一次：记住"我刚才在做哪道"，刷新后回到这题 */
watch(currentQuestionIndex, () => {
  if (mockPhase.value !== 'running') return
  persistMockSession()
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
    if (!draftRestored.value) return
    /*
     * 模拟考试的进度由 `persistMockSession` 负责，**不写练习草稿**（2026-10-22）。
     * 两套机制各存各的：草稿按"波次"切片，考试是整卷，混写会互相破坏
     * （详见 `restoreDraftIfAny` 顶部那段说明）。
     */
    if (moduleTypeSafe.value === 'mock') return
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
  const doSubmit = async () => {
    /*
     * 模拟考试走独立的判分与结果页（2026-10-22）。
     *
     * 分歧点：原来的 `Math.round(correct/total*100)` 是"按题数算百分比"，
     * 而模拟考试的分值是按题型配置的（单选 2 分、多选 4 分……），
     * 还可能有多选漏选按比例给分 —— 用"题数百分比"当分数是错的。
     * 所以 mock 交给 `handleMockSubmit`，其余模块保持原逻辑不变。
     */
    if (isMockFlow.value && activeMockConfig.value) {
      await handleMockSubmit()
      return
    }
    try {
      if (!practiceSessionId.value) await ensurePracticeSession()
      if (!practiceSessionId.value) {
        proxy.$modal.msgError('练习会话不存在，无法交卷，请刷新后重试')
        return
      }
      // 考试模式不做逐题上报：交卷时把本地答案按题目 id 一并交给服务端
      const localAnswers = Object.fromEntries(
        questions.value.map((q: any, i: number) => [String(q.id), answers.value[i]])
      )
      const res: any = await submitPracticeSession(practiceSessionId.value, undefined, localAnswers)
      if (res?.code !== 200) {
        proxy.$modal.msgError(res?.msg || '交卷失败，请重试')
        return
      }
      // 用服务端返回的逐题判分刷新本地题目对象，结算页/答题卡都读同一份结果
      const items: any[] = Array.isArray(res.data?.items) ? res.data.items : []
      const byId = new Map<string, any>(questions.value.map((q: any) => [String(q.id), q]))
      items.forEach((item: any) => {
        const q = byId.get(String(item.questionId))
        if (q) applyServerGrade(q, item)
      })
      totalScore.value = Math.round(Number(res.data?.percentage ?? 0))
      showAllAnalysis()
      showExamResult.value = true
      loadRecentSession()
      clearExamStorage()
      stopExamTimer()
      if (Number(res.data?.pendingCount || 0) > 0) {
        proxy.$modal.msgInfo(`本次有 ${res.data.pendingCount} 道简答题待自评，不计入自动正确率`)
      }
    } catch (e: any) {
      console.error('[practice] 交卷失败', e)
      proxy.$modal.msgError('交卷失败，请检查网络后重试')
    }
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
function handleUpdateAnswer(value: any) {
  selectedAnswer.value = value
  const qIndex = currentQuestionIndex.value
  if (qIndex >= 0 && qIndex < answers.value.length) {
    answers.value[qIndex] = value
  }
  /*
   * 注意：这里**不判分**。填空/简答是"边写边改"，
   * 每敲一个字就比对会立刻判错（历史 bug），必须等用户点「确认答案」。
   */
  /*
   * 但**已确认过的**要撤销确认：「确认答案」重新出现，
   * 解析复位。否则用户改完答案后解析还停在旧结果、
   * 按钮也不会再出现，等于永远没法重新比对（实测发现的死角）。
   */
  if (!isExamMode.value && committedQuestions.value[qIndex]) {
    committedQuestions.value[qIndex] = false
    const q = questions.value[qIndex]
    if (q) {
      q.showAnalysis = false
      q.answered = false
      q.correct = false
    }
  }
}

function handleSelectOption(index: number) {
  selectOption(index)

  /*
   * 把刚选的值同步进 `answers`（2026-10-22）
   * ==================================================================
   * ⚠️ 这是"静默自动保存"能成立的前提，之前漏了这一句。
   *
   * `selectOption()` 只改 `selectedAnswer`（当前题的临时选择），
   * 真正写进 `answers[qIndex]` 的是 `handleAnswerSubmission()` —— 而它只在
   * 「下一题 / 上一题 / 跳题」时才被调用。于是存在一个真实的数据丢失窗口：
   *
   *     用户点 A  →  selectedAnswer = 0，answers[0] 仍是 null
   *               →  自动保存快照读 answers → 存进去的是 {}
   *               →  用户直接刷新 / 关掉页面  →  刚才那一下白选了
   *
   * 实测复现过：点「A. 堆」后 `answers` 仍是 `[null, null, ...]`，
   * localStorage 里 `answers: {}`，刷新后选中态也没有了。
   *
   * 所以这里立即同步一次。副作用是良性的：
   *   · 单选题下它就是"我选了但还没判"的中间态，与界面表现一致；
   *   · 判分逻辑仍然由后面的 `handleAnswerSubmission` 负责，这里不判；
   *   · 考试模式下同样需要 —— 考试中途刷新本就该保住已选答案。
   */
  const qIndex = currentQuestionIndex.value
  if (qIndex >= 0 && qIndex < answers.value.length) {
    answers.value[qIndex] = selectedAnswer.value
  }

  if (isExamMode.value) return

  /*
   * 单选 / 判断：**点一次就出答案**（2026-10-22 用户明确要求）
   * ==================================================================
   * 原来这里只同步 `answers`，判分要等用户点「下一题」才发生 ——
   * 表现就是"点了选项什么都没发生，看不到对错，也没有解析"，
   * 而浏览模式下同样的点击会立刻出答案。两种模式行为不一致，属于遗漏。
   *
   * 现在与浏览模式完全对齐：
   *   · 单选 / 判断 → 选完立即判（`isInstantJudgeType`）；
   *   · 多选 / 填空 / 简答 / 组合 → 不判，等用户点「确认答案」
   *     （见 `handleCommitAnswer`，按钮由 `needsSubmit` 控制显示）。
   * 同时记 `committedQuestions`，让 QuestionDisplay 收起确认按钮、展示解析。
   */
  if (isInstantJudgeType(currentQuestion.value?.type)) {
    committedQuestions.value[qIndex] = true
    handleAnswerSubmission(qIndex)
  } else if (committedQuestions.value[qIndex]) {
    /*
     * 已确认过的多选/填空/简答，用户又改了答案 → **撤销"已确认"**
     * ==================================================================
     * 不撤销的话会出现一个死角（实测发现）：
     *   多选题确认后显示解析 → 用户发现选错了，再点一个选项 →
     *   答案变了，但解析还停在旧结果上，而且「确认答案」按钮**不会再出现**
     *   （因为 `committed` 仍为 true）→ 用户永远没法重新比对。
     *
     * 撤销后按钮重新出现，状态回到"已作答但未确认"，
     * 与"刚选完还没确认"完全一致 —— 心智模型统一。
     * `showAnalysis` 也一并复位，否则解析区会继续显示上一次的判定。
     */
    committedQuestions.value[qIndex] = false
    const q = questions.value[qIndex]
    if (q) {
      q.showAnalysis = false
      q.answered = false
      q.correct = false
    }
  }

  /*
   * ⚠️ 自动跳下一题的逻辑必须留在下面 `autoNextOnCorrect` 的闸门之后，
   *    不要因为上面新增的同步而提前 return（会破坏"答对自动翻页"）。
   */
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

<style scoped src="./PracticeComponent.style1.css"></style>

<style src="@/assets/styles/PracticeComponent.css"></style>
