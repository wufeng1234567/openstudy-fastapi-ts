<template>
  <div class="answer-card">
    <div class="card-header">
      <!-- 左列：标题 -->
      <div class="header-left">
        <h4>答题卡</h4>
      </div>

      <!-- 中列：模式标签 + 切换图标 -->
      <div class="header-center">
        <div class="mode-group">
          <el-tag size="small" :type="isOverviewMode ? 'primary' : 'info'" effect="plain" round>
            {{ isOverviewMode ? '整体浏览' : '逐题模式' }}
          </el-tag>
          <el-tooltip :content="isOverviewMode ? '切换为逐题模式' : '切换为整体浏览'" placement="top">
            <el-button :icon="isOverviewMode ? List : Grid" circle size="small" @click="$emit('toggle-overview')" />
          </el-tooltip>
        </div>
      </div>

      <!--
        右列：暂存 + 重新练习
        ----------------------------------------
        「暂存」是**手动**入口（用户 2026-10-18 要求）：
        正常刷题时进度会静默自动保存，这个按钮用于"我就是想立刻存一下"，
        并按 `draft-state` 显示 保存中 / 已暂存 / 暂存失败。
      -->
      <div class="header-right">
        <el-button text size="small" :loading="draftState === 'saving'" @click="$emit('save-draft')">
          <span :class="['draft-label', 'is-' + draftState]">{{ draftButtonText }}</span>
        </el-button>
        <el-button text size="small" @click="$emit('reset-practice')">重新练习</el-button>
      </div>
    </div>

    <!-- 正常模式：题号网格（原样保留） -->
    <template v-if="!isOverviewMode">
      <div class="question-grid">
        <div v-for="(item, index) in questions" :key="index" class="grid-item" :class="{
          answered: item.answered,
          correct: !isExamMode && item.correct && item.answered,
          wrong: !isExamMode && !item.correct && item.answered,
          current: index === currentQuestionIndex
        }" @click="$emit('go-to-question', index)">
          {{ index + 1 }}
        </div>
      </div>

      <div class="stats">
        <!-- 刷题模式：显示进度 -->
        <template v-if="isPracticeMode">
          <div class="progress-text">已刷：{{ answeredCount }} / {{ totalCount }} 题</div>
          <div class="progress-hint" v-if="remainingCount > 0">剩余 {{ remainingCount }} 题待练习</div>
        </template>

        <!-- 考试模式：显示总分 -->
        <template v-else-if="isExamMode && showExamResult">
          <div class="total-score">总分：{{ totalScore }} 分</div>
          <el-button v-if="moduleType === 'mock'" type="primary" size="small" @click="$emit('finish-exam')">
            结束考试
          </el-button>
        </template>

        <!-- 模拟考试提交后（非考试模式）：显示结束按钮 -->
        <template v-else-if="moduleType === 'mock' && showExamResult">
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
          <el-button type="primary" size="small" @click="$emit('finish-exam')">
            结束考试
          </el-button>
        </template>

        <!-- 考试模式：交卷按钮（非最后一题时显示） -->
        <template v-else-if="isExamMode && !isLastQuestion">
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
          <el-button size="small" @click="$emit('submit-exam')">交卷</el-button>
        </template>

        <!-- 默认统计（预览模式等） -->
        <template v-else>
          <div>答对：<span class="correct">{{ stats.correctCount }}</span>题</div>
          <div>答错：<span class="wrong">{{ stats.wrongCount }}</span>题</div>
          <div>正确率：<span class="rate">{{ stats.accuracy }}%</span></div>
        </template>
      </div>
    </template>

    <!-- 整体浏览模式：分组展示 -->
    <template v-else>
      <div class="overview-card-body">
        <div v-for="group in questionGroups" :key="group.typeName" class="group-section">
          <div class="group-title">{{ group.typeLabel }}（共 {{ group.items.length }} 题）</div>
          <div class="group-grid">
            <div v-for="q in group.items" :key="q.index" :ref="el => setGridItemRef(el, q.index)"
              class="grid-item overview-grid-item" :class="getOverviewItemClass(q.index)"
              @click="$emit('go-to-question', q.index)">
              {{ q.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { PropType } from 'vue'
import { Grid, List } from '@element-plus/icons-vue'

interface QuestionItem {
  id?: number | string
  type?: string
  answered?: boolean
  correct?: boolean
  [key: string]: any
}

interface QuestionGroup {
  typeLabel: string
  typeName: string
  startIndex: number
  endIndex: number
  items: Array<QuestionItem & { index: number }>
}

interface Stats {
  correctCount: number
  wrongCount: number
  accuracy: number
  [key: string]: any
}

const props = defineProps({
  questions: { type: Array as PropType<QuestionItem[]>, default: () => [] },
  currentQuestionIndex: { type: Number, default: 0 },
  stats: { type: Object as PropType<Stats>, default: () => ({ correctCount: 0, wrongCount: 0, accuracy: 0 }) },
  isExamMode: { type: Boolean, default: false },
  isPracticeMode: { type: Boolean, default: false },
  isLastQuestion: { type: Boolean, default: false },
  questionGroups: { type: Array as PropType<QuestionGroup[]>, default: () => [] },
  markedQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  favoritedQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  errorQuestions: { type: Set as PropType<Set<number>>, default: () => new Set<number>() },
  isOverviewMode: { type: Boolean, default: false },
  currentHighlightIndex: { type: Number, default: 0 },
  showExamResult: { type: Boolean, default: false },
  totalScore: { type: Number, default: 0 },
  answeredCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  remainingCount: { type: Number, default: 0 },
  moduleType: { type: String, default: '' },
  /** 暂存状态：驱动「暂存」按钮的文案与 loading（见 PracticeComponent 的 draftState） */
  draftState: { type: String, default: 'idle' },
  /** 暂存按钮文案（由父组件按状态生成，避免子组件重复一套文案） */
  draftButtonText: { type: String, default: '暂存' }
})

const emit = defineEmits([
  'go-to-question',
  'reset-practice',
  'submit-exam',
  'toggle-overview',
  'finish-exam',
  /** 手动暂存当前练习进度 */
  'save-draft'
])

const isMounted = ref(false)
const gridItemRefs = ref<Record<number, HTMLElement>>({})

onMounted(() => {
  isMounted.value = true
})

const setGridItemRef = (el: any, index: number) => {
  if (el) {
    gridItemRefs.value[index] = el
  }
}

// 状态判断辅助函数（基于题目 ID）
const getOverviewItemClass = (index: number) => {
  const q = props.questions[index]
  const isHighlighted = index === props.currentHighlightIndex
  const isCorrect = !props.isExamMode && q && q.correct && q.answered
  const isWrong = !props.isExamMode && !isCorrect && q && q.answered

  if (isHighlighted) return 'current'
  if (isCorrect) return 'correct'
  if (isWrong) return 'wrong'
  if (q && q.answered) return 'answered'
  return ''
}
</script>

<style scoped>
.answer-card {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid #e5e7eb;
  position: sticky;
  top: 20px;
  height: fit-content;
}

.card-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  margin-bottom: 8px;
}

.header-left h4 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-center {
  display: flex;
  justify-content: center;
}

.mode-group {
  display: flex;
  align-items: center;
  gap: 4px;
  /* 标签和图标紧贴 */
}

.header-right {
  display: flex;
  margin-right: -10px;
  justify-content: flex-end;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-left h4 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.question-grid {
  display: grid;
  grid-template-columns: repeat(5, 36px);
  gap: 6px 2px;
  margin-bottom: 20px;
  justify-content: center;
}

.grid-item {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.grid-item.answered {
  background-color: #e8f0fe;
  border-color: #c5d9f5;
  color: #1a56db;
}

.grid-item.correct {
  background-color: #f0f9eb;
  color: #67c23a;
}

.grid-item.wrong {
  background-color: #fef2f2;
  color: #b45353;
}

.grid-item.current {
  background-color: #f3f4f6;
  border-color: #d1d5db;
  font-weight: bold;
}

.stats {
  margin-bottom: 20px;
}

.stats div {
  margin-bottom: 5px;
  font-size: 14px;
  color: #6b7280;
}

.correct {
  color: #67c23a;
}

.wrong {
  color: #b45353;
}

.rate {
  font-weight: bold;
  color: #1f2937;
}

.progress-text {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 4px;
}

.progress-hint {
  font-size: 13px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.total-score {
  font-size: 20px;
  font-weight: bold;
  color: #1f2937;
  margin-bottom: 8px;
}

/* 整体浏览模式样式 */
.overview-card-body {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
  scrollbar-gutter: stable;
  margin-right: -10px;
}

.group-section {
  margin-bottom: 12px;
}

.group-title {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 6px;
  padding-left: 2px;
}

.group-grid {
  display: grid;
  grid-template-columns: repeat(5, 36px);
  gap: 6px 2px;
  max-width: calc(100% - 24px);
}

.overview-grid-item {
  width: 36px;
  height: 36px;
  border-radius: 6px;
  font-size: 14px;
  border: 1px solid #e5e7eb;
  background: #fff;
  color: #6b7280;
  transition: all 0.2s ease;
}

.overview-grid-item:hover {
  border-color: #d1d5db;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
}

.overview-grid-item.answered {
  background: #e8f0fe;
  border-color: #c5d9f5;
  color: #1a56db;
}

.overview-grid-item.current {
  background-color: #f3f4f6;
  border-color: #d1d5db;
  font-weight: bold;
}

.overview-grid-item.correct {
  background-color: #f0f9eb;
  color: #67c23a;
}

.overview-grid-item.wrong {
  background-color: #fef2f2;
  color: #b45353;
}
</style>