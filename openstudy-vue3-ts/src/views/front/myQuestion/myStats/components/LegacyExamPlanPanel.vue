<template>
  <section class="legacy-exam">
    <div class="legacy-exam__banner">
      <div>
        <b>历史计划（旧版）</b>
        <span>这里只展示你以前生成的考前计划；新的学习计划在「学习计划」tab，不再新建计划或复制题库。</span>
      </div>
      <el-button size="small" type="primary" plain @click="emit('open-plan')">打开学习计划</el-button>
    </div>
    <ExamPlanPanel ref="innerRef" readonly />
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ExamPlanPanel from './ExamPlanPanel.vue'

defineOptions({ name: 'LegacyExamPlanPanel' })

const emit = defineEmits<{
  (e: 'open-plan'): void
}>()

const innerRef = ref<any>(null)

defineExpose({
  refresh: () => innerRef.value?.refreshProgress?.()
})
</script>

<style scoped>
.legacy-exam { display: flex; flex-direction: column; gap: 12px; }
.legacy-exam__banner { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 11px 14px; border: 1px solid #f0dfbd; border-radius: 10px; background: #fffaf0; }
.legacy-exam__banner > div { display: flex; min-width: 0; flex-direction: column; gap: 3px; }
.legacy-exam__banner b { color: #8a5c13; font-size: 12px; }
.legacy-exam__banner span { color: #9a855f; font-size: 10px; line-height: 1.5; }
.legacy-exam :deep(.exam-form) { display: none; }
.legacy-exam :deep(.exam-layout) { grid-template-columns: minmax(0, 1fr); }
</style>
