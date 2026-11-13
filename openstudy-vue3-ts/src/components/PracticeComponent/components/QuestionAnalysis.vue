<template>
  <!-- 普通题型的解析（不含组合题） -->
  <div
    v-if="currentQuestion?.showAnalysis && currentQuestion?.analysis && !['readingComprehension', 'cloze'].includes(currentQuestion?.type)"
    class="analysis-box">
    <el-divider />
    <div class="analysis-title"><OsIcon name="lightbulb" :size="14" /> 解析</div>
    <LatexRenderer class="analysis-content" :content="currentQuestion.analysis" raw-html />
  </div>

  <!-- 填空/简答：显示标准答案 -->
  <div v-if="currentQuestion?.showAnalysis && ['fillblank', 'essay'].includes(currentQuestion?.type)"
    class="standard-answer">
    <strong>标准答案：</strong><LatexRenderer class="standard-answer-value" :content="String(currentQuestion.correctAnswer ?? '')" />
  </div>

  <!-- cloze类型的主文章解析 -->
  <div v-if="currentQuestion?.showAnalysis && currentQuestion?.type === 'cloze' && currentQuestion?.analysis"
    class="analysis-box">
    <el-divider />
    <div class="analysis-title"><OsIcon name="lightbulb" :size="14" /> 解析</div>
    <LatexRenderer class="analysis-content" :content="currentQuestion.analysis" raw-html />
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import type { TransformedQuestion } from '@/types'

defineProps({
  currentQuestion: {
    type: Object as PropType<TransformedQuestion | null>,
    default: null
  },
  subFillBlankAnswers: {
    type: Object as PropType<Record<number | string, any>>,
    default: () => ({})
  },
  subEssayAnswers: {
    type: Object as PropType<Record<number | string, any>>,
    default: () => ({})
  }
})
</script>

<style scoped>
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
</style>
