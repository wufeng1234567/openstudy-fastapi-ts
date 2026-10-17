<template>
  <div class="reading-comprehension">
    <!-- 添加安全检查 -->
    <div v-if="currentQuestion && currentQuestion.subQuestions && currentQuestion.subQuestions.length">
      <div v-for="(q, idx) in currentQuestion.subQuestions" :key="idx" class="sub-question">
        <!-- 子题目题型提示 -->
        <div class="sub-question-type-hint" :class="getSubQuestionTypeClass(q.type)">
          <span class="sub-type-icon">
            <el-icon v-if="q.type === 'single'"><Select /></el-icon>
            <el-icon v-else-if="q.type === 'multiple'">
              <CircleCheck />
            </el-icon>
            <el-icon v-else-if="q.type === 'truefalse'">
              <Check />
            </el-icon>
            <el-icon v-else-if="q.type === 'fillblank'">
              <EditPen />
            </el-icon>
            <el-icon v-else-if="q.type === 'essay'">
              <Document />
            </el-icon>
          </span>
          <span class="sub-type-text">{{ getSubQuestionTypeText(q.type) }}</span>
          <!-- 多选题提示 -->
          <span class="sub-multi-hint" v-if="q.type === 'multiple'">（可多选）</span>
          <!-- 判断题提示 -->
          <span class="sub-truefalse-hint" v-if="q.type === 'truefalse'">（判断对错）</span>
        </div>

        <div class="sub-question-title"><span class="sub-question-idx">{{ idx + 1 }}.</span> <LatexRenderer :content="q.question" raw-html /></div>

        <!-- 单选题、多选题 -->
        <div v-if="q.type && ['single', 'multiple'].includes(q.type) && q.options && q.options.length > 0" class="sub-options">
          <div v-for="(option, oIdx) in q.options" :key="oIdx" class="option-item" :class="{
            'user-selected': isSubUserSelected(idx, oIdx),
            'correct-answer': isSubCorrectOption(idx, oIdx)
          }" @click="$emit('select-sub-option', idx, oIdx)">
            <span class="option-letter">{{ getOptionLabel(oIdx) }}.</span>
            <LatexRenderer class="option-text" :content="option" />
          </div>
          <!-- 子题标准答案和解析 -->
          <div v-if="currentQuestion?.showAnalysis && (q.correctAnswer !== undefined || q.analysis)"
            class="sub-answer-analysis">
            <div v-if="q.correctAnswer && q.type !== 'essay'" class="standard-answer">
              <strong>标准答案：</strong><LatexRenderer class="standard-answer-value" :content="formatAnswer(q.correctAnswer, q.type)" />
            </div>
            <div v-if="q.analysis" class="sub-analysis-box">
              <div class="sub-analysis-header">
                <el-icon>
                  <Lightning />
                </el-icon>
                <span>题目解析</span>
              </div>
              <LatexRenderer class="analysis-content" :content="q.analysis" raw-html />
            </div>
          </div>
        </div>

        <!-- 判断题 -->
        <div v-else-if="q.type === 'truefalse'" class="sub-truefalse">
          <div class="truefalse-buttons">
            <div class="truefalse-btn" :class="{
              'user-selected': isSubUserSelected(idx, 0),
              'correct-answer': isSubCorrectOption(idx, 0)
            }" @click="$emit('select-sub-option', idx, 0)">
              <span class="truefalse-icon"><OsIcon name="check" :size="14" /></span>
              <span class="truefalse-text">正确</span>
            </div>
            <div class="truefalse-btn" :class="{
              'user-selected': isSubUserSelected(idx, 1),
              'correct-answer': isSubCorrectOption(idx, 1)
            }" @click="$emit('select-sub-option', idx, 1)">
              <span class="truefalse-icon"><OsIcon name="close" :size="14" /></span>
              <span class="truefalse-text">错误</span>
            </div>
          </div>
          <!-- 子题标准答案和解析 -->
          <div v-if="currentQuestion?.showAnalysis && (q.correctAnswer !== undefined || q.analysis)"
            class="sub-answer-analysis">
            <div v-if="q.correctAnswer !== undefined" class="standard-answer">
              <strong>标准答案：</strong><LatexRenderer class="standard-answer-value" :content="formatAnswer(q.correctAnswer, q.type)" />
            </div>
            <div v-if="q.analysis" class="sub-analysis-box">
              <div class="sub-analysis-header">
                <el-icon>
                  <Lightning />
                </el-icon>
                <span>题目解析</span>
              </div>
              <LatexRenderer class="analysis-content" :content="q.analysis" raw-html />
            </div>
          </div>
        </div>

        <!-- 填空题 -->
        <div v-else-if="q.type === 'fillblank'" class="sub-fillblank">
          <el-input v-model="localFillBlankAnswers[idx]" @blur="handleFillBlankBlur(idx)" placeholder="请输入答案"
            size="small" clearable />
          <!-- 子题标准答案和解析 -->
          <div v-if="currentQuestion?.showAnalysis && (q.correctAnswer !== undefined || q.analysis)"
            class="sub-answer-analysis">
            <div v-if="q.correctAnswer !== undefined && q.correctAnswer !== null" class="standard-answer">
              <strong>标准答案：</strong><LatexRenderer class="standard-answer-value" :content="formatAnswer(q.correctAnswer, q.type)" />
            </div>
            <div v-if="q.analysis" class="sub-analysis-box">
              <div class="sub-analysis-header">
                <el-icon>
                  <Lightning />
                </el-icon>
                <span>题目解析</span>
              </div>
              <LatexRenderer class="analysis-content" :content="q.analysis" raw-html />
            </div>
          </div>
        </div>

        <!-- 简答题 -->
        <div v-else-if="q.type === 'essay'" class="sub-essay">
          <el-input v-model="localEssayAnswers[idx]" @blur="handleEssayBlur(idx)" type="textarea" :rows="4"
            placeholder="请输入您的答案" clearable />
        </div>
      </div>
    </div>

    <!-- 没有子题目的情况 -->
    <div v-else class="no-sub-questions">
      <el-empty description="暂无题目内容" :image-size="100">
        <template #image>
          <el-icon>
            <Document />
          </el-icon>
        </template>
      </el-empty>
    </div>

    <!-- 组合题的解析 -->
    <div v-if="currentQuestion?.type === 'cloze' && currentQuestion?.showAnalysis && currentQuestion?.analysis"
      class="analysis-box">
      <el-divider />
      <div class="analysis-title"><OsIcon name="lightbulb" :size="14" /> 解析</div>
      <LatexRenderer class="analysis-content" :content="currentQuestion.analysis" raw-html />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PropType } from 'vue'
import {
  Select,
  CircleCheck,
  Check,
  EditPen,
  Document,
  Lightning
} from '@element-plus/icons-vue'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import OsIcon from '@/components/OsIcon/index.vue'

interface SubQuestion {
  question?: string
  type?: string
  options?: any[]
  analysis?: string
  correctAnswer?: any
  answered?: boolean
  correct?: boolean
  [key: string]: any
}

interface CurrentQuestion {
  subQuestions?: SubQuestion[]
  showAnalysis?: boolean
  type?: string
  analysis?: string
  [key: string]: any
}

const props = defineProps({
  currentQuestion: {
    type: Object as PropType<CurrentQuestion>,
    default: () => ({})
  },
  subFillBlankAnswers: {
    type: Object as PropType<Record<number, any>>,
    default: () => ({})
  },
  subEssayAnswers: {
    type: Object as PropType<Record<number, any>>,
    default: () => ({})
  },
  currentQuestionIndex: {
    type: Number,
    default: 0
  },
  answers: {
    type: Array as PropType<any[]>,
    default: () => []
  }
})

const emit = defineEmits([
  'select-sub-option',
  'update-sub-fill-blank-answer',
  'update-sub-essay-answer'
])

const localFillBlankAnswers = ref<Record<number, any>>({})
const localEssayAnswers = ref<Record<number, any>>({})

watch(() => props.subFillBlankAnswers, (newVal) => {
  localFillBlankAnswers.value = { ...newVal }
}, { immediate: true, deep: true })

watch(() => props.subEssayAnswers, (newVal) => {
  localEssayAnswers.value = { ...newVal }
}, { immediate: true, deep: true })

function handleFillBlankBlur(idx: number) {
  const value = localFillBlankAnswers.value[idx] || ''
  emit('update-sub-fill-blank-answer', idx, value)
}

function handleEssayBlur(idx: number) {
  const value = localEssayAnswers.value[idx] || ''
  emit('update-sub-essay-answer', idx, value)
}

// 获取子题目题型文本
function getSubQuestionTypeText(type: string | undefined) {
  const typeMap: Record<string, string> = {
    single: '单选题',
    multiple: '多选题',
    truefalse: '判断题',
    fillblank: '填空题',
    essay: '简答题'
  }
  return (type && typeMap[type]) || '未知题型'
}

// 获取子题目题型对应的 CSS 类
function getSubQuestionTypeClass(type: string | undefined) {
  const classMap: Record<string, string> = {
    single: 'sub-type-single',
    multiple: 'sub-type-multiple',
    truefalse: 'sub-type-truefalse',
    fillblank: 'sub-type-fillblank',
    essay: 'sub-type-essay'
  }
  return (type && classMap[type]) || ''
}

function getOptionLabel(index: number) {
  return String.fromCharCode(65 + index)
}

// ✅ 修复：安全的获取填空题值的方法
function getSubFillBlankValue(subIndex: number) {
  if (!props.subFillBlankAnswers || typeof props.subFillBlankAnswers !== 'object') {
    return ''
  }
  return props.subFillBlankAnswers[subIndex] || ''
}

// ✅ 修复：安全的获取简答题值的方法
function getSubEssayValue(subIndex: number) {
  if (!props.subEssayAnswers || typeof props.subEssayAnswers !== 'object') {
    return ''
  }
  return props.subEssayAnswers[subIndex] || ''
}

// 计算当前子题的答案
const currentSubAnswers = computed<Record<number, any>>(() => {
  if (!props.answers || !Array.isArray(props.answers)) {
    return {}
  }
  return props.answers[props.currentQuestionIndex] || {}
})

function isSubUserSelected(subIndex: number, optionIndex: number) {
  const subAnswers = currentSubAnswers.value
  const currentQ = props.currentQuestion

  if (!currentQ || !currentQ.subQuestions || !subAnswers) return false

  const subQ = currentQ.subQuestions[subIndex]
  if (!subQ) return false

  if (subQ.type === 'multiple') {
    return Array.isArray(subAnswers[subIndex]) && subAnswers[subIndex].includes(optionIndex)
  }

  return subAnswers[subIndex] === optionIndex
}

function isSubCorrectOption(subIndex: number, optionIndex: number) {
  const currentQ = props.currentQuestion
  if (!currentQ || !currentQ.showAnalysis || !currentQ.subQuestions) return false

  const subQ = currentQ.subQuestions[subIndex]
  if (!subQ) return false

  // 处理多选题
  if (subQ.type === 'multiple') {
    return Array.isArray(subQ.correctAnswer) && subQ.correctAnswer.includes(optionIndex)
  }

  // 处理单选题和其他题型
  return optionIndex === subQ.correctAnswer
}

function formatAnswer(answer: any, type: string | undefined) {
  if (answer === undefined || answer === null) return ''

  if (type === 'multiple') {
    if (Array.isArray(answer)) {
      return answer.map((a: any) => {
        if (typeof a === 'number') {
          return String.fromCharCode(65 + a)
        }
        return a
      }).join(', ')
    }
    return String(answer)
  } else if (type === 'single') {
    if (typeof answer === 'number') {
      return String.fromCharCode(65 + answer)
    }
    return String(answer)
  } else if (type === 'truefalse') {
    return answer === 0 ? '正确' : '错误'
  } else if (type === 'fillblank') {
    // ✅ 专门处理填空题：直接显示答案文本
    return String(answer)
  }

  return String(answer)
}
</script>

<style scoped>
.reading-comprehension {
  margin: 20px 0;
}

.sub-question {
  margin-bottom: 25px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
}

/* 子题目题型提示样式 */
.sub-question-type-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  margin-bottom: 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  width: fit-content;
}

.sub-type-icon {
  display: flex;
  align-items: center;
  font-size: 14px;
}

.sub-type-text {
  font-weight: 600;
}

.sub-multi-hint {
  color: #f56c6c;
  font-size: 11px;
  font-weight: 500;
}

.sub-truefalse-hint {
  color: #e6a23c;
  font-size: 11px;
  font-weight: 500;
}

/* 不同子题目题型的背景色 */
.sub-type-single {
  background-color: rgba(230, 247, 255, 0.8);
  border-left: 3px solid #409eff;
  color: #1890ff;
}

.sub-type-multiple {
  background-color: rgba(240, 249, 255, 0.8);
  border-left: 3px solid #36cfc9;
  color: #08979c;
}

.sub-type-truefalse {
  background-color: rgba(255, 247, 230, 0.8);
  border-left: 3px solid #faad14;
  color: #d48806;
}

.sub-type-fillblank {
  background-color: rgba(246, 255, 237, 0.8);
  border-left: 3px solid #73d13d;
  color: #389e0d;
}

.sub-type-essay {
  background-color: rgba(249, 240, 255, 0.8);
  border-left: 3px solid #9254de;
  color: #722ed1;
}

.sub-question-title {
  font-weight: bold;
  margin-bottom: 12px;
  font-size: 14px;
  color: #1f2937;
  line-height: 1.5;

  .sub-question-idx {
    font-weight: bold;
  }

  :deep(img) {
    max-width: 100%;
    max-height: 400px;
    object-fit: contain;
    height: auto;
    border-radius: 8px;
    margin: 8px 0;
  }

  :deep(p) {
    margin: 0 0 4px;
  }

  :deep(p:last-child) {
    margin-bottom: 0;
  }
}

/* 子题目选项样式 */
.sub-options {
  margin: 10px 0;
}

.sub-options .option-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 6px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: white;
}

.sub-options .option-item:hover {
  background-color: #f3f4f6;
}

.sub-options .option-item.user-selected {
  background-color: #f3f4f6;
  color: #1f2937;
  border-color: #d1d5db;
}

.sub-options .option-item.correct-answer {
  border: 2px solid #67c23a;
  background-color: #f0f9eb;
  color: #1f2937;
}

.sub-options .option-letter {
  font-weight: bold;
  margin-right: 8px;
  font-size: 13px;
}

.sub-options .option-text {
  flex: 1;
  font-size: 13px;
}

/* 子题目填空题样式 */
.sub-fillblank {
  margin: 10px 0;
}

/* 子题目简答题样式 */
.sub-essay {
  margin: 10px 0;
}

/* 判断题按钮样式 */
.sub-truefalse {
  margin: 10px 0;
}

.truefalse-buttons {
  display: flex;
  gap: 12px;
}

.truefalse-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  background: #fff;
  color: #6b7280;
  font-weight: 500;
}

.truefalse-btn:hover {
  transform: translateY(-2px);
  border-color: #d1d5db;
  color: #4b5563;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.truefalse-btn.user-selected {
  background: #fff7e6;
  border-color: #faad14;
  color: #d48806;
}

.truefalse-btn.correct-answer {
  background: #f0f9eb;
  border: 2px solid #67c23a;
  color: #67c23a;
}

.truefalse-icon {
  font-size: 16px;
  font-weight: bold;
}

.truefalse-text {
  font-size: 14px;
}

.standard-answer {
  margin-top: 10px;
  padding: 8px;
  background-color: #f0f9eb;
  border-radius: 8px;
  font-size: 13px;
  color: #1f2937;
}

.standard-answer-value {
  display: inline;
}

.no-sub-questions {
  padding: 40px;
  text-align: center;
  color: #9ca3af;
}

.analysis-box {
  margin-top: 20px;
  padding: 12px;
  background-color: #f8f9fa;
  border-left: 4px solid #d1d5db;
  border-radius: 8px;
}

.analysis-title {
  font-weight: bold;
  color: #1f2937;
  margin-bottom: 6px;
  font-size: 14px;
}

.analysis-content {
  font-size: 13px;
  line-height: 1.5;
  color: #6b7280;
}

/* 子题目答案和解析容器 */
.sub-answer-analysis {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

/* 子题目解析框 */
.sub-analysis-box {
  margin-top: 10px;
  padding: 10px;
  background: #fefce8;
  border-radius: 6px;
  border: 1px solid #e5e0c0;
}

.sub-analysis-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-weight: bold;
  color: #7a6238;
  font-size: 13px;
}

.sub-analysis-header .el-icon {
  color: #947a4a;
  font-size: 16px;
}
</style>