<!-- src/components/PracticeComponent/QuestionNavigation.vue -->
<template>
  <div class="navigation-section">
    <!--
      操作按钮（用户 2026-10-18 的分波规则，与浏览模式保持一致）
      ==========================================================
      · 中间题      → 上一题 / 下一题
      · 这一波最后一题 → 隐藏「下一题」，换成波次按钮：
          - 第一波            → 「继续下一波」
          - 中间波            → 「回到上一波」+「继续下一波」
          - 最后一波          → 「回到上一波」+「提交」
      为什么在这里拦「下一题」：最后一题再点"下一题"会跑出本波范围，
      而波外根本没有已加载的题目（会造成空白/错位）。
    -->
    <div class="navigation-buttons">
      <el-button size="small" @click="$emit('prev-question')" v-if="showPrev && !isLastQuestion">上一题</el-button>

      <!-- 非本波最后一题：常规翻页 -->
      <el-button type="primary" size="small" @click="$emit('next-question')" v-if="showNext && !isLastQuestion">
        下一题
      </el-button>

      <!-- 本波最后一题：波次切换 / 提交 -->
      <template v-if="isLastQuestion && (isExamMode || isPracticeMode)">
        <el-button size="small" @click="$emit('prev-batch')" v-if="canGoPrevBatch">
          回到上一波
        </el-button>
        <el-button type="primary" size="small" @click="onNextBatch" v-if="!isLastBatch">
          继续下一波
        </el-button>
        <el-button type="warning" size="small" @click="$emit('submit-exam')" v-else class="submit-btn">
          <el-icon>
            <Finished />
          </el-icon> 提交
        </el-button>
      </template>
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

const emit = defineEmits([
  'prev-question',
  'next-question',
  'mark',
  'add-note',
  'report',
  'ai-analyze',
  'submit-exam',
  'prev-batch',
  /** 逐题模式：本波最后一题点「继续下一波」（用户 2026-10-18 新增） */
  'next-batch',
  'close'
])

/**
 * 点「继续下一波」
 *
 * 这里不做"这一波做没做完"的校验 —— 与浏览模式的行为保持一致：
 * 用户已经站在本波最后一题、按钮也显示出来了，就让他走。
 * （未答题的提醒由「提交」那一侧负责，不该在切波时二次打扰。）
 */
const onNextBatch = () => {
  emit('next-batch')
}

// 处理斩题状态变化
const handleMarkedChange = (isMarked: boolean) => {
  console.log(`斩题状态变化: ${isMarked ? '已斩题' : '未斩题'}`)
  // 可以在这里添加额外的处理逻辑
}
</script>