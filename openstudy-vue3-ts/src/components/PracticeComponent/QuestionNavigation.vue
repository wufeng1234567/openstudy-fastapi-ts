<!-- src/components/PracticeComponent/QuestionNavigation.vue -->
<template>
  <div class="navigation-section">
    <!-- 操作按钮 -->
    <div class="navigation-buttons">
      <el-button size="small" @click="$emit('prev-question')" v-if="showPrev">上一题</el-button>
      <el-button type="primary" size="small" @click="$emit('next-question')"
        v-if="showNext && !((isExamMode || isPracticeMode) && isLastQuestion)">
        下一题
      </el-button>
      <el-button type="warning" size="small"
        @click="isLastBatch && hasSubmittedCurrentBatch ? $emit('close') : $emit('submit-exam')"
        v-if="showSubmitButton && (isExamMode || isPracticeMode) && isLastQuestion" class="submit-btn">
        <el-icon>
          <Finished />
        </el-icon> {{ isLastBatch && hasSubmittedCurrentBatch ? '结束' : '继续提交' }}
      </el-button>
      <el-button size="small" @click="$emit('prev-batch')" v-if="canGoPrevBatch && (isExamMode || isPracticeMode)">
        上一波
      </el-button>
    </div>

    <!-- 功能按钮 -->
    <div class="action-buttons" v-if="moduleType !== 'mock'">
      <!-- 新增：AI 解析按钮 -->
      <el-button size="small" type="warning" plain @click="$emit('ai-analyze')">
        <el-icon>
          <MagicStick />
        </el-icon>
        AI 解析
      </el-button>

      <!-- 收藏组件 -->
      <FavoriteButton v-if="questionId" :type="'question'" :target-id="questionId" size="small" :plain="true"
        collected-button-type="primary" uncollected-button-type="default" />

      <!-- 斩题组件 -->
      <MarkedButton v-if="questionId" :question-id="questionId" size="small" :plain="true" marked-button-type="primary"
        unmarked-button-type="default" :auto-check="true" :show-success-message="true" @change="handleMarkedChange" />

      <el-button size="small" @click="$emit('add-note')">笔记</el-button>
      <el-button size="small" @click="$emit('report')">举报</el-button>
    </div>
  </div>
</template>
<script setup lang="ts">
import FavoriteButton from '@/components/FavoriteButton/FavoriteButton.vue'
import MarkedButton from '@/components/MarkedButton/MarkedButton.vue'
import { MagicStick, Finished } from '@element-plus/icons-vue'
defineProps({
  showPrev: {
    type: Boolean,
    default: true
  },
  showNext: {
    type: Boolean,
    default: true
  },
  questionId: {
    type: [Number, String],
    default: null
  },
  bankId: {
    type: [Number, String],
    default: null
  },
  moduleType: {
    type: String,
    default: ''
  },
  isExamMode: {
    type: Boolean,
    default: false
  },
  isPracticeMode: {
    type: Boolean,
    default: false
  },
  isLastQuestion: {
    type: Boolean,
    default: false
  },
  canGoPrevBatch: {
    type: Boolean,
    default: false
  },
  showSubmitButton: {
    type: Boolean,
    default: true
  },
  isLastBatch: {
    type: Boolean,
    default: false
  },
  hasSubmittedCurrentBatch: {
    type: Boolean,
    default: false
  }
})

defineEmits([
  'prev-question',
  'next-question',
  'mark',
  'add-note',
  'report',
  'ai-analyze',
  'submit-exam',
  'prev-batch',
  'close'
])

// 处理斩题状态变化
const handleMarkedChange = (isMarked: boolean) => {
  console.log(`斩题状态变化: ${isMarked ? '已斩题' : '未斩题'}`)
  // 可以在这里添加额外的处理逻辑
}
</script>