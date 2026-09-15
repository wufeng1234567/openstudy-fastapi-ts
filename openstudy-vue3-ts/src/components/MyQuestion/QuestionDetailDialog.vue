<!-- src/components/MyQuestion/QuestionDetailDialog.vue -->
<template>
  <el-dialog :model-value="visible" :title="dialogTitle" width="85%" :fullscreen="isFullscreen"
    :close-on-click-modal="false" :close-on-press-escape="true" @close="$emit('close')" class="question-detail-dialog"
    custom-class="question-detail-dialog-custom">
    <!-- 图片预览组件 -->
    <ImageViewer v-model:visible="viewerVisible" :src="viewerSrc" />

    <!-- 题目显示区域 -->
    <div v-if="currentQuestionDetail" class="dialog-content">
      <QuestionDisplay :current-question="currentQuestionDetail" :current-question-index="currentQuestionIndex"
        :total-questions="dialogQuestions.length" :selected-answer="selectedAnswer"
        :sub-fill-blank-answers="subFillBlankAnswers" :sub-essay-answers="subEssayAnswers" :answers="answers"
        @select-option="$emit('select-option', $event)" @update-answer="$emit('update-answer', $event)"
        @select-sub-option="$emit('select-sub-option', $event)"
        @update-sub-fill-blank-answer="$emit('update-sub-fill-blank-answer', $event)"
        @update-sub-essay-answer="$emit('update-sub-essay-answer', $event)"
        @preview-image="openImageViewer" />

      <!-- 底部导航 -->
      <QuestionNavigation :show-prev="currentQuestionIndex > 0"
        :show-next="currentQuestionIndex < dialogQuestions.length - 1" :question-id="currentQuestionDetail?.id"
        @prev-question="$emit('prev-question')" @next-question="$emit('next-question')" @mark="$emit('mark')"
        @add-note="$emit('add-note')" @report="$emit('report')" @ai-analyze="$emit('ai-analyze', currentQuestionDetail)" />
    </div>
    <div v-else class="loading-dialog">
      <el-skeleton :rows="10" animated />
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="$emit('toggle-fullscreen')">
          <el-icon>
            <FullScreen />
          </el-icon>
          {{ isFullscreen ? '退出全屏' : '全屏' }}
        </el-button>
        <el-button @click="$emit('close')">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FullScreen, InfoFilled, Warning, StarFilled, Document, Notebook, Clock, Flag } from '@element-plus/icons-vue'
import QuestionDisplay from '@/components/PracticeComponent/QuestionDisplay.vue'
import QuestionNavigation from '@/components/PracticeComponent/QuestionNavigation.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'

// 图片预览状态
const viewerVisible = ref(false)
const viewerSrc = ref('')

// 打开图片预览
const openImageViewer = (src) => {
  viewerSrc.value = src
  viewerVisible.value = true
}

const props = defineProps({
  visible: Boolean,
  currentQuestionDetail: Object,
  currentQuestionIndex: Number,
  dialogQuestions: Array,
  isFullscreen: Boolean,
  selectedAnswer: [String, Number],
  subFillBlankAnswers: Object,
  subEssayAnswers: Object,
  answers: Array,
  currentFavoriteQuestion: Object,
  questionType: {
    type: String,
    default: 'favorite'
  }
})

const emit = defineEmits([
  'close', 'toggle-fullscreen', 'prev-question', 'next-question',
  'select-option', 'update-answer', 'select-sub-option',
  'update-sub-fill-blank-answer', 'update-sub-essay-answer',
  'mark', 'add-note', 'report', 'ai-analyze'
])

// 使用 ref 来跟踪当前题目类型
const currentQuestionType = ref(props.questionType || 'favorite')

// 监听 questionType 的变化
watch(() => props.questionType, (newType) => {
  if (newType) {
    currentQuestionType.value = newType
  }
})

// 获取对话框标题
const dialogTitle = computed(() => {
  if (!props.currentQuestionDetail) return '题目详情'

  const questionTypeText = getQuestionTypeDisplayText()
  const id = getQuestionId()
  const pageInfo = props.dialogQuestions.length > 1
    ? `(${props.currentQuestionIndex + 1}/${props.dialogQuestions.length})`
    : ''

  return `题目详情 - ${questionTypeText} ${pageInfo}`
})

// 辅助函数
const getQuestionId = () => {
  return props.currentFavoriteQuestion?.questionId ||
    props.currentQuestionDetail?.id ||
    '--'
}

// 获取题型文本
const getQuestionTypeText = (type) => {
  if (type == null) return '未知题型'

  // 处理数字类型
  const numType = typeof type === 'number' ? type : getQuestionTypeNumber(type)

  const typeMap = {
    1: '单选题',
    2: '多选题',
    3: '判断题',
    4: '填空题',
    5: '简答题',
    6: '阅读理解',
    7: '完形填空'
  }
  return typeMap[numType] || '未知题型'
}

// 将字符串题型转换为数字
const getQuestionTypeNumber = (typeStr) => {
  if (!typeStr) return 0

  const typeMap = {
    'single': 1,
    'multiple': 2,
    'judge': 3,
    'truefalse': 3,
    'fill': 4,
    'fillblank': 4,
    'essay': 5,
    'reading': 6,
    'readingComprehension': 6,
    'cloze': 7
  }
  return typeMap[typeStr] || 0
}

// 获取题型显示文本
const getQuestionTypeDisplayText = () => {
  const type = props.currentQuestionDetail?.questionType || props.currentQuestionDetail?.type
  return getQuestionTypeText(type)
}

// 格式化时间（保留供其他可能使用）
const formatTime = (time) => {
  if (!time) return '--'
  try {
    const date = new Date(time)
    if (isNaN(date.getTime())) {
      return time
    }
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    }).replace(/\//g, '-')
  } catch (e) {
    return time
  }
}
</script>

<style scoped>
.question-detail-dialog {
  .dialog-content {
    min-height: 500px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .loading-dialog {
    padding: 20px;
  }

  .dialog-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 16px;
    border-top: 1px solid #e4e7ed;
  }
}
</style>

<style>
.question-detail-dialog-custom .el-dialog__body {
  padding: 24px;
  max-height: 70vh;
  overflow-y: auto;
}

.question-detail-dialog-custom .el-dialog__footer {
  padding: 16px 24px;
}

.question-detail-dialog-custom .el-dialog__header {
  padding: 20px 24px 10px;
  border-bottom: 1px solid #e4e7ed;
}

/* 题目详情框图片尺寸限制 */
.question-detail-dialog .dialog-content img {
  max-width: 400px !important;
  max-height: 300px !important;
  width: auto !important;
  height: auto !important;
  object-fit: contain !important;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.question-detail-dialog .dialog-content img:hover {
  opacity: 0.85;
}
</style>