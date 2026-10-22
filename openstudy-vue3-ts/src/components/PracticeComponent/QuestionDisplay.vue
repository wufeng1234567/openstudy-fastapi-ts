<!-- src/components/PracticeComponent/QuestionDisplay.vue -->
<template>
  <div class="question-area" @click="handleContentClick">

    <!-- 题型提示区域 -->
    <div class="question-type-hint" :class="getQuestionTypeClass(currentQuestion?.type)">
      <span class="type-icon">
        <el-icon v-if="currentQuestion?.type === 'single'"><Select /></el-icon>
        <el-icon v-else-if="currentQuestion?.type === 'multiple'">
          <CircleCheck />
        </el-icon>
        <el-icon v-else-if="currentQuestion?.type === 'truefalse'">
          <Check />
        </el-icon>
        <el-icon v-else-if="currentQuestion?.type === 'fillblank'">
          <EditPen />
        </el-icon>
        <el-icon v-else-if="currentQuestion?.type === 'essay'">
          <Document />
        </el-icon>
        <el-icon v-else-if="currentQuestion?.type === 'readingComprehension' || currentQuestion?.type === 'cloze'">
          <DocumentCopy />
        </el-icon>
      </span>
      <span class="type-text">{{ getQuestionTypeText(currentQuestion?.type) }}</span>
      <!-- 多选题提示 -->
      <span class="multi-hint" v-if="currentQuestion?.type === 'multiple'">（可多选）</span>
      <!-- 判断题提示 -->
      <span class="truefalse-hint" v-if="currentQuestion?.type === 'truefalse'">（判断对错）</span>
    </div>

    <!-- 题库和难度标签 -->
    <div v-if="currentQuestion && (currentQuestion.bankName || currentQuestion.difficulty)" class="question-meta-tags">
      <el-tag v-if="currentQuestion.bankName" size="small" class="bank-tag">
        <el-icon>
          <Collection />
        </el-icon>
        {{ currentQuestion.bankName }}
      </el-tag>
      <el-tag v-if="currentQuestion.difficulty" size="small"
        :class="['difficulty-tag', `difficulty-${currentQuestion.difficulty}`]">
        {{ getDifficultyText(currentQuestion.difficulty) }}
      </el-tag>
    </div>

    <!-- 题目标题 -->
    <div class="question-header">
      <!-- 显示主干内容（组合题） -->
      <div v-if="currentQuestion?.hasMainContent && currentQuestion?.mainContent" class="main-content-box"
        style="margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 4px">
        <h4>{{ currentQuestion.mainTitle }}</h4>
        <LatexRenderer :content="formatMainContent(currentQuestion.mainContent)" raw-html />
      </div>
      <!--
        题号跨波顺延（用户 2026-10-18）：
        `currentQuestionIndex` 是**波内**下标（每波从 0 起），
        全局序号 = `numberOffset + index + 1`。第一波 offset=0 → 1 起；第二波 → 21 起。
      -->
      <span class="question-index" v-if="showQuestionIndex !== false">{{ numberOffset + (currentQuestionIndex ?? 0) + 1 }}/{{ totalQuestions }}</span>

      <!-- 只有 currentQuestion 存在才显示题目内容 -->
      <template v-if="currentQuestion">
        <!-- 移除这里的 question-type span，移动到上面的提示区域 -->
        <LatexRenderer class="question-title"
          v-if="currentQuestion.type !== 'cloze' && currentQuestion.type !== 'readingComprehension'"
          :content="currentQuestion.question" raw-html />
      </template>

      <!-- 如果还没加载出来，显示"加载中" -->
      <span v-else>加载中...</span>
    </div>

    <!-- 题目内容区（根据题型动态渲染） -->
    <div class="question-body" v-if="currentQuestion">
      <!-- 单选题、多选题、判断题 -->
      <!--
        选项乱序（2026-10-22）：`displayOptions` 每项带 `_origin`（原始下标）。
        · 选中态/正确答案用 `_origin` 判断（answers 里存的是原始下标）；
        · 点击时也把 `_origin` 发出去，保证记录下来的仍是原始下标。
        这样"显示顺序变了"与"答案指向哪个选项"是两件互不干扰的事。
      -->
      <div v-if="['single', 'multiple', 'truefalse'].includes(currentQuestion.type)" class="options">
        <div v-for="(option, index) in displayOptions" :key="option._origin" class="option-item" :class="{
          'user-selected': isUserSelected(option._origin),
          'correct-answer': isCorrectOption(option._origin)
        }" @click="$emit('select-option', option._origin)">
          <span class="option-letter">{{ getOptionLabel(index) }}.</span>
          <LatexRenderer class="option-text" :content="option.text" />
        </div>
      </div>

      <!-- 填空题 -->
      <div v-else-if="currentQuestion.type === 'fillblank'" class="input-area">
        <el-input :model-value="selectedAnswer" @update:model-value="(value: any) => $emit('update-answer', value)"
          placeholder="请输入答案" size="small" clearable />
      </div>

      <!-- 简答题 -->
      <div v-else-if="currentQuestion.type === 'essay'" class="input-area">
        <el-input :model-value="selectedAnswer" @update:model-value="(value: any) => $emit('update-answer', value)"
          type="textarea" :rows="4" placeholder="请输入您的答案" clearable />
      </div>

      <!-- 组合题（原阅读理解 & 完形填空） -->
      <ReadingComprehensionDisplay v-else-if="['readingComprehension', 'cloze'].includes(currentQuestion.type)"
        :current-question="currentQuestion" :current-question-index="currentQuestionIndex" :answers="answers"
        :sub-fill-blank-answers="subFillBlankAnswers" :sub-essay-answers="subEssayAnswers"
        @select-sub-option="(subIndex, optionIndex) => $emit('select-sub-option', subIndex, optionIndex)"
        @update-sub-fill-blank-answer="(subIndex, value) => $emit('update-sub-fill-blank-answer', subIndex, value)"
        @update-sub-essay-answer="(subIndex, value) => $emit('update-sub-essay-answer', subIndex, value)" />

      <!-- 其他题型（预留） -->
      <div v-else>
        <p>暂不支持该题型</p>
      </div>
    </div>

    <!--
      浏览模式下的「提交答案」（用户 2026-10-18 bug2）
      ================================================
      背景：浏览模式原本是"选完立刻判"，单选/判断这样很顺，
      但多选/填空/简答被同样对待 → 多选点第一个选项就判错、填空题输第一个字就判错。

      现在按题型分流（判定逻辑在 PracticeComponent 的 `isInstantJudgeType`）：
        · 单选 / 判断 → 仍然点完即判，**不显示**这个按钮；
        · 多选 / 填空 / 简答 / 组合题 → 先记录答案，用户点「提交答案」才判分。
      提交过（overviewCommitted）就不再显示按钮，改为展示解析。
    -->
    <div v-if="overviewNeedSubmit" class="overview-commit-row">
      <el-button type="primary" size="small" @click="$emit('commit-answer')">
        提交答案
      </el-button>
      <span class="commit-hint">提交后才会判分并显示解析</span>
    </div>

    <!-- ✅ 修复：完整的解析区域（排除组合题） -->
    <div class="question-analysis" v-if="currentQuestion && currentQuestion.showAnalysis && showAnalysisImmediately && !['readingComprehension', 'cloze'].includes(currentQuestion.type)">
      <el-divider content-position="left">
        <div style="display: flex; align-items: center; gap: 8px;">
          <el-icon>
            <InfoFilled />
          </el-icon>
          <span>答案解析</span>
        </div>
      </el-divider>

      <div class="analysis-content">
        <!-- 显示正确答案 -->
        <div class="correct-answer-section">
          <div class="answer-header">
            <span class="answer-title">正确答案：</span>
            <LatexRenderer class="answer-value" :content="getCorrectAnswerText()" />
          </div>

          <!-- 如果用户回答了，显示用户答案 -->
          <div class="user-answer-section" v-if="showUserAnswer()">
            <span class="user-answer-title">您的答案：</span>
            <LatexRenderer class="user-answer-value" :content="getUserAnswerText()" />
          </div>
        </div>

        <!-- 解析内容 -->
        <div class="explanation-section" v-if="currentQuestion.analysis">
          <div class="explanation-header">
            <el-icon>
              <Lightning />
            </el-icon>
            <span class="explanation-title">题目解析</span>
          </div>
          <LatexRenderer class="explanation-content" :content="currentQuestion.analysis" raw-html />
        </div>

        <!-- 没有解析时的提示 -->
        <div class="no-analysis" v-else>
          <el-empty description="暂无解析内容" :image-size="60">
            <template #image>
              <el-icon>
                <Search />
              </el-icon>
            </template>
          </el-empty>
        </div>
      </div>
    </div>

    <!-- 单独处理组合题的解析 -->
    <div class="reading-analysis"
      v-if="currentQuestion && ['readingComprehension', 'cloze'].includes(currentQuestion.type) && currentQuestion.showAnalysis && showAnalysisImmediately">
      <QuestionAnalysis :current-question="currentQuestion" :answers="answers"
        :current-question-index="currentQuestionIndex" :sub-fill-blank-answers="subFillBlankAnswers"
        :sub-essay-answers="subEssayAnswers" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import type { PropType } from 'vue'
import {
  Select,
  CircleCheck,
  Check,
  EditPen,
  Document,
  DocumentCopy,
  InfoFilled,
  Lightning,
  Search,
  Collection
} from '@element-plus/icons-vue'
import ReadingComprehensionDisplay from './ReadingComprehensionDisplay.vue'
import QuestionAnalysis from './QuestionAnalysis.vue'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import type { TransformedQuestion } from '@/types'

const props = defineProps({
  currentQuestion: {
    type: Object as PropType<TransformedQuestion | null>,
    default: null
  },
  currentQuestionIndex: { type: Number, default: 0 },
  totalQuestions: { type: Number, default: 0 },
  /**
   * 题号偏移（= 本波第一题之前的题目数）
   *
   * 分波刷题时 `questions` 只是切片，波内下标每波都从 0 起；
   * 显示"第几题"必须加上这个偏移才能跨波顺延（用户 2026-10-18）。
   */
  numberOffset: { type: Number, default: 0 },
  /*
   * ⚠️ 必须允许 Object：组合题（cloze / readingComprehension）的作答是一个
   *    `{ 子题序号: 选项 }` 的对象，不是标量也不是数组。
   *    原来只声明 [String, Number, Array]，于是每渲染一道组合题就报
   *    `Invalid prop: type check failed for prop "selectedAnswer"` —— 
   *    控制台满屏红字（2026-10-18 实测，用户看到大量报错会认为系统不稳定）。
   */
  selectedAnswer: {
    type: [String, Number, Array, Object] as PropType<
      string | number | (string | number)[] | Record<string | number, any> | null
    >,
    default: null
  },
  subFillBlankAnswers: {
    type: Object as PropType<Record<number | string, any>>,
    default: () => ({})
  },
  subEssayAnswers: {
    type: Object as PropType<Record<number | string, any>>,
    default: () => ({})
  },
  answers: {
    type: Array as PropType<any[]>,
    default: () => []
  },
  showAnalysisImmediately: {
    type: Boolean,
    default: true
  },
  /**
   * 是否打乱选项显示顺序（2026-10-22）
   *
   * 传 `false` / 不传时行为与改造前完全一致（原样返回 options），
   * 所以对不关心这个开关的调用方（如题目详情弹窗）没有任何影响。
   */
  shuffleOptions: {
    type: Boolean,
    default: false
  },
  showQuestionIndex: {
    type: Boolean,
    default: true
  },
  /* ---- 整体浏览模式：多选/填空/简答需要「提交答案」才判分（见模板里的说明） ---- */
  /** 是否处于整体浏览模式（单题模式不显示提交按钮） */
  overviewMode: {
    type: Boolean,
    default: false
  },
  /** 本题当前是否**需要**显示「提交答案」按钮 */
  overviewNeedSubmit: {
    type: Boolean,
    default: false
  },
  /** 本题是否**已经提交过**（提交后不再显示按钮，改为展示解析） */
  overviewCommitted: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'select-option',
  'update-answer',
  'select-sub-option',
  'update-sub-fill-blank-answer',
  'update-sub-essay-answer',
  'commit-answer',
  'preview-image'
])

// 获取题型文本
function getQuestionTypeText(type: string | undefined) {
  if (!type) return '未知题型'
  const typeMap: Record<string, string> = {
    single: '单选题',
    multiple: '多选题',
    truefalse: '判断题',
    fillblank: '填空题',
    essay: '简答题',
    readingComprehension: '组合题',
    cloze: '组合题'
  }
  return typeMap[type] || '未知题型'
}

// 获取题型对应的 CSS 类
function getQuestionTypeClass(type: string | undefined) {
  if (!type) return ''
  const classMap: Record<string, string> = {
    single: 'type-single',
    multiple: 'type-multiple',
    truefalse: 'type-truefalse',
    fillblank: 'type-fillblank',
    essay: 'type-essay',
    readingComprehension: 'type-composite',
    cloze: 'type-composite'
  }
  return classMap[type] || ''
}

// 获取难度文本
function getDifficultyText(difficulty: number | string) {
  const difficultyMap: Record<string, string> = {
    1: '简单',
    2: '中等',
    3: '困难',
    4: '极难'
  }
  return difficultyMap[difficulty] || '中等'
}

// 格式化主干内容
function formatMainContent(content: string) {
  if (!content) return ''
  return content.replace(/___(\d+)___/g, '<strong style="color: #409eff; text-decoration: underline;">[$1]</strong>')
}

function getOptionLabel(index: number) {
  return String.fromCharCode(65 + index)
}

/*
 * 选项乱序（2026-10-22）
 * ==========================================================================
 * ⚠️ 这是本组件**自己的** `displayOptions`，与 `useQuestionPractice` 里同名 computed
 *    不是同一个东西。父组件通过 `shuffle-options` 把开关传进来，这里做真正的重排。
 *
 * 两个必须处理对的地方：
 *
 * ① 洗牌结果必须**按题记忆**。computed 会因答案变化等依赖重算，
 *    每次重算都重新洗 → 选项跳来跳去，根本没法答题。
 *
 * ② **下标必须映射回原始下标**。
 *    `selectedAnswer` / `correctAnswer` 里存的都是**原始下标**（0=A、1=B…）。
 *    打乱后，屏幕上第 0 个位置可能是原始第 2 个选项。所以：
 *      · 渲染时用 `_origin` 判断"这个选项是不是用户选的 / 是不是正确答案"；
 *      · 点击时把 `_origin` 发出去，让 `answers` 里记录的仍是原始下标。
 *    这样打乱只影响**显示顺序**，判分、暂存、历史记录全都不受影响。
 */
const optionOrderCache = new Map<string, number[]>()

function shuffleCacheKey(): string {
  const q = props.currentQuestion
  return `${q?.id ?? q?.questionId ?? ''}`
}

function fisherYates(n: number): number[] {
  const arr = Array.from({ length: n }, (_, i) => i)
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

/** 渲染用的选项列表：每项带 `_origin`（原始下标） */
const displayOptions = computed<Array<{ text: any; _origin: number }>>(() => {
  const q: any = props.currentQuestion
  const opts = q?.options
  if (!Array.isArray(opts) || opts.length === 0) return []

  const plain = opts.map((o: any, i: number) => ({
    // 选项既可能是纯字符串，也可能是 { label/text } 对象
    text: typeof o === 'object' && o !== null ? o : o,
    _origin: i
  }))

  if (!props.shuffleOptions) {
    optionOrderCache.delete(shuffleCacheKey())
    return plain
  }

  const key = shuffleCacheKey()
  let order = optionOrderCache.get(key)
  if (!order || order.length !== plain.length) {
    order = fisherYates(plain.length)
    optionOrderCache.set(key, order)
  }
  return order.map((origin) => plain[origin])
})

/** 打开新题时清掉旧题的记忆，避免缓存无限增长 */
watch(
  () => props.currentQuestion?.id ?? props.currentQuestion?.questionId,
  () => {
    if (optionOrderCache.size > 200) optionOrderCache.clear()
  }
)

function isUserSelected(index: number) {
  const type = props.currentQuestion?.type
  if (type === 'multiple') {
    return Array.isArray(props.selectedAnswer) && props.selectedAnswer.includes(index)
  }
  return props.selectedAnswer === index
}

// ✅ 修复：改进的 isCorrectOption 函数
function isCorrectOption(index: number) {
  if (!props.currentQuestion?.showAnalysis) return false
  if (!props.showAnalysisImmediately) return false

  const ca = props.currentQuestion?.correctAnswer
  const type = props.currentQuestion?.type

  if (type === 'multiple') {
    if (Array.isArray(ca)) {
      return ca.includes(index)
    } else {
      return false
    }
  }

  return ca === index
}

// ✅ 新增：获取正确答案文本
function getCorrectAnswerText() {
  const q = props.currentQuestion
  if (!q) return ''

  const ca = q.correctAnswer

  if (q.type === 'single' || q.type === 'truefalse') {
    if (typeof ca === 'number') {
      return getOptionLabel(ca) + '. ' + (q.options?.[ca] || ca)
    }
    return ca
  } else if (q.type === 'multiple') {
    if (Array.isArray(ca)) {
      return (ca as any[]).map((index: number) => getOptionLabel(index) + '. ' + (q.options?.[index] || index)).join('；')
    }
    return ca
  } else if (q.type === 'fillblank' || q.type === 'essay') {
    return ca || '暂无标准答案'
  }

  return ca
}

// ✅ 新增：获取用户答案文本
function getUserAnswerText() {
  const q = props.currentQuestion
  if (!q) return ''

  const userAnswer = props.selectedAnswer

  if (q.type === 'single' || q.type === 'truefalse') {
    if (typeof userAnswer === 'number') {
      return getOptionLabel(userAnswer) + '. ' + (q.options?.[userAnswer] || userAnswer)
    }
    return userAnswer
  } else if (q.type === 'multiple') {
    if (Array.isArray(userAnswer)) {
      return (userAnswer as any[]).map((index: number) => getOptionLabel(index) + '. ' + (q.options?.[index] || index)).join('；')
    }
    return userAnswer
  } else if (q.type === 'fillblank' || q.type === 'essay') {
    return userAnswer || '未作答'
  }

  return userAnswer
}

// ✅ 新增：判断是否显示用户答案
function showUserAnswer() {
  const q = props.currentQuestion
  if (!q) return false

  const userAnswer = props.selectedAnswer

  if (q.type === 'single' || q.type === 'truefalse') {
    return userAnswer !== null && userAnswer !== undefined
  } else if (q.type === 'multiple') {
    return Array.isArray(userAnswer) && userAnswer.length > 0
  } else if (q.type === 'fillblank' || q.type === 'essay') {
    return userAnswer && typeof userAnswer === 'string' && userAnswer.trim() !== ''
  }

  return false
}

function handleContentClick(e: MouseEvent) {
  const img = (e.target as HTMLElement).closest('img')
  if (img && img.src) {
    emit('preview-image', img.src)
  }
}
</script>

<style scoped>
/* 题型提示样式 */
.question-type-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
}

.type-icon {
  display: flex;
  align-items: center;
  font-size: 16px;
}

.type-text {
  font-weight: 600;
}

.multi-hint {
  color: #f56c6c;
  font-size: 13px;
  font-weight: 500;
}

.truefalse-hint {
  color: #e6a23c;
  font-size: 13px;
  font-weight: 500;
}

/* 不同题型的背景色 */
.type-single {
  background-color: rgba(230, 247, 255, 0.8);
  border-left: 4px solid #409eff;
  color: #1890ff;
}

.type-multiple {
  background-color: rgba(240, 249, 255, 0.8);
  border-left: 4px solid #36cfc9;
  color: #08979c;
}

.type-truefalse {
  background-color: rgba(255, 247, 230, 0.8);
  border-left: 4px solid #faad14;
  color: #d48806;
}

.type-fillblank {
  background-color: rgba(246, 255, 237, 0.8);
  border-left: 4px solid #73d13d;
  color: #389e0d;
}

.type-essay {
  background-color: rgba(249, 240, 255, 0.8);
  border-left: 4px solid #9254de;
  color: #722ed1;
}

/* ✅ 组合题主题型样式 - 使用橙色/金色系，不与任何题型重复 */
.type-composite {
  background-color: rgba(255, 247, 230, 0.85);
  border-left: 4px solid #fa8c16;
  color: #d46b00;
}

/* 题库和难度标签 */
.question-meta-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.question-meta-tags .bank-tag {
  background: #ecf5ff;
  border-color: #d9ecff;
  color: #409eff;
  border-radius: 4px;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.question-meta-tags .difficulty-tag {
  border-radius: 4px;
  font-size: 12px;
  border-width: 1px;
  border-style: solid;
}

.question-meta-tags .difficulty-tag.difficulty-1 {
  background: #f0f9eb;
  border-color: #e1f3d8;
  color: #67c23a;
}

.question-meta-tags .difficulty-tag.difficulty-2 {
  background: #ecf5ff;
  border-color: #d9ecff;
  color: #409eff;
}

.question-meta-tags .difficulty-tag.difficulty-3 {
  background: #fdf6ec;
  border-color: #faecd8;
  color: #e6a23c;
}

.question-meta-tags .difficulty-tag.difficulty-4 {
  background: #fef0f0;
  border-color: #fde2e2;
  color: #f56c6c;
}

/* 原样式调整 */
.question-header {
  margin-bottom: 20px;
}

.question-index {
  font-weight: bold;
  color: #6b7280;
  margin-right: 10px;
}

.question-type {
  display: none;
}

.question-title {
  font-size: 16px;
  line-height: 1.6;
  margin-top: 8px;
  display: block;

  :deep(img) {
    max-width: 100%;
    max-height: 400px;
    object-fit: contain;
    height: auto;
    border-radius: 8px;
    margin: 8px 0;
  }

  :deep(p) {
    margin: 0 0 8px;
  }

  :deep(p:last-child) {
    margin-bottom: 0;
  }
}

/* 选项区域样式 */
.options {
  margin: 20px 0;
}

.option-item {
  display: flex;
  align-items: center;
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.option-item:hover {
  background-color: #f3f4f6;
}

.option-item.user-selected {
  background-color: #f3f4f6;
  color: #1f2937;
  border-color: #d1d5db;
}

.option-item.correct-answer {
  border: 2px solid #67c23a;
  background-color: #f0f9eb;
  color: #1f2937;
}

.option-letter {
  font-weight: bold;
  margin-right: 8px;
}

.option-text {
  flex: 1;
}

/* 输入区域样式 */
.input-area {
  margin: 20px 0;
}

/* 主干内容框样式 */
.main-content-box {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e5e7eb;

  :deep(img) {
    max-width: 100%;
    max-height: 400px;
    object-fit: contain;
    height: auto;
    border-radius: 8px;
    margin: 8px 0;
  }
}

.question-analysis {
  margin-top: 30px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  border-left: 4px solid #d1d5db;
}

.analysis-content {
  padding: 15px;
  background: white;
  border-radius: 6px;
}

.correct-answer-section {
  margin-bottom: 20px;
  padding: 15px;
  background: #f0f9eb;
  border-radius: 6px;
  border: 1px solid #e1f3d8;
}

.answer-header {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.answer-title {
  font-weight: bold;
  color: #1f2937;
  font-size: 15px;
  min-width: 80px;
}

.answer-value {
  font-size: 15px;
  color: #1f2937;
  font-weight: 600;
  flex: 1;
}

.user-answer-section {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
}

.user-answer-title {
  font-weight: bold;
  color: #6b7280;
  font-size: 14px;
  min-width: 80px;
}

.user-answer-value {
  font-size: 14px;
  color: #6b7280;
  font-weight: 500;
  flex: 1;
}

.explanation-section {
  padding: 15px;
  background: #fefce8;
  border-radius: 6px;
  border: 1px solid #e5e0c0;
}

.explanation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.explanation-header .el-icon {
  color: #947a4a;
  font-size: 18px;
}

.explanation-title {
  font-weight: bold;
  color: #7a6238;
  font-size: 15px;
}

.explanation-content {
  font-size: 14px;
  line-height: 1.6;
  color: #6b7280;
}

.no-analysis {
  text-align: center;
  padding: 30px 0;
}

.reading-analysis {
  margin-top: 30px;
}

/* 浏览模式的「提交答案」行：与题面留一点空隙，左边按钮、右边灰字提示 */
.overview-commit-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));

  .commit-hint {
    font-size: 12px;
    line-height: 1.5;
    color: var(--os-text-4, #9ca3af);
  }
}
</style>