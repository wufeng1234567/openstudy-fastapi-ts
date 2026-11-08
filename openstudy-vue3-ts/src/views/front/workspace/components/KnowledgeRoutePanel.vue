<template>
  <aside class="krp">
    <div class="krp__head">
      <span class="krp__eyebrow">学习建议</span>
      <button type="button" class="krp__exit" title="关闭" @click="emit('exit')">×</button>
    </div>
    <p class="krp__text">学习建议已经移到「学习计划」工作台，那里可以沿着真实图谱关系生成、调整和保存建议。</p>
    <button type="button" class="krp__link" @click="emit('open-plan')">打开学习计划 →</button>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  route?: any
  stops?: any[]
  activeStop?: any | null
  loading?: boolean
  offRouteTitle?: string
  offRoutePageId?: number | null
}>()

const emit = defineEmits<{
  (e: 'select', pageId: number): void
  (e: 'start'): void
  (e: 'exit'): void
  (e: 'guide'): void
  (e: 'set-target', pageId: number): void
  (e: 'open-plan'): void
}>()
</script>

<style scoped>
.krp {
  position: absolute;
  z-index: 9;
  top: 12px;
  right: 12px;
  display: flex;
  width: min(220px, calc(100vw - 32px));
  flex-direction: column;
  gap: 7px;
  padding: 10px 11px;
  border: 1px solid #e4eaf3;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(47, 95, 206, 0.1);
}
.krp__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.krp__eyebrow { color: #2f5fce; font-size: 11px; font-weight: 700; letter-spacing: .06em; }
.krp__exit { padding: 0 2px; border: 0; color: #9aa3b2; background: transparent; cursor: pointer; font: inherit; font-size: 14px; line-height: 1; }
.krp__exit:hover { color: #2f5fce; }
.krp__text { margin: 0; color: #7d8596; font-size: 11px; line-height: 1.55; }
.krp__link { align-self: flex-start; padding: 0; border: 0; color: #2f5fce; background: transparent; cursor: pointer; font: inherit; font-size: 11px; font-weight: 600; }
.krp__link:hover { text-decoration: underline; }
</style>
