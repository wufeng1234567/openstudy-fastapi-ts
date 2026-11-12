<template>
  <div v-if="organizeTask.active" class="kbp-reprocess kbp-reprocess--organize">
    <div class="kbp-reprocess__head">
      <span class="kbp-reprocess__spinner"></span>
      <b>正在整理「{{ organizeTask.fileName }}」</b>
      <span class="kbp-reprocess__stage">{{ organizeTask.statusText }}</span>
      <button type="button" class="kbp-reprocess__open" @click="emit('open-organize')">查看进度</button>
      <span class="kbp-reprocess__elapsed">{{ Math.round(organizeTask.percent) }}%</span>
    </div>
    <div class="kbp-reprocess__bar">
      <span :style="{ width: `${organizeTask.percent}%` }"></span>
    </div>
    <div class="kbp-reprocess__hint">整理在后台进行，可以先浏览其他资料；关闭预览不会中断任务。</div>
  </div>

  <div v-if="reprocessTask.active" class="kbp-reprocess">
    <div class="kbp-reprocess__head">
      <span class="kbp-reprocess__spinner"></span>
      <b>正在重新整理「{{ reprocessTask.fileName }}」</b>
      <span class="kbp-reprocess__stage">{{ reprocessTask.statusText }}</span>
      <span class="kbp-reprocess__elapsed">已用时 {{ reprocessElapsed }}s</span>
    </div>
    <div class="kbp-reprocess__bar">
      <span :style="{ width: `${reprocessTask.percent}%` }"></span>
    </div>
    <div class="kbp-reprocess__hint">
      解析、切分和向量化在后台进行，预计需要几十秒；期间可以先浏览其他资料，完成后自动刷新。
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  organizeTask: { active: boolean; fileName: string; statusText: string; percent: number }
  reprocessTask: { active: boolean; fileName: string; statusText: string; percent: number }
  reprocessElapsed: number
}>()

const emit = defineEmits<{ (e: 'open-organize'): void }>()
</script>
