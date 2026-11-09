<template>
  <aside class="nap">
    <header class="nap__head">
      <span class="nap__eyebrow">规划建议预览</span>
      <h3>{{ advice?.title || selectedNode?.title || '当前节点' }}</h3>
      <p v-if="advice?.summary" class="nap__summary">{{ advice.summary }}</p>
      <div v-if="advice" class="nap__meta">
        <span>{{ advice.phases?.length || 0 }} 个阶段</span>
        <span>预计共 {{ totalDurationText }}</span>
      </div>
    </header>

    <div v-loading="loading" class="nap__scroll">
      <template v-if="advice">
        <section v-for="phase in advice.phases || []" :key="phase.id" class="nap__phase">
          <div class="nap__phase-head">
            <b>{{ phase.title }}</b>
            <span>约 {{ phase.estimatedMinutes || 0 }} 分钟</span>
          </div>
          <p v-if="phase.goal">{{ phase.goal }}</p>
          <div v-if="phase.nodeIds?.length" class="nap__nodes">
            <span v-for="nodeId in phase.nodeIds" :key="nodeId">{{ nodeTitle(nodeId) }}</span>
          </div>
        </section>
        <section v-if="advice.risks?.length" class="nap__risks">
          <b>需要注意</b>
          <p v-for="item in advice.risks" :key="item">{{ item }}</p>
        </section>
      </template>
      <div v-else-if="!loading" class="nap__empty">暂无预览，点击下方按钮生成完整建议。</div>
    </div>

    <footer class="nap__foot">
      <el-button type="primary" :loading="loading" :disabled="loading" @click="emit('generate')">
        以此生成建议
      </el-button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    advice?: any
    loading?: boolean
    selectedNode?: any
    nodeTitles?: Record<string, string>
  }>(),
  { advice: null, loading: false, selectedNode: null, nodeTitles: () => ({}) }
)

const emit = defineEmits<{ (e: 'generate'): void }>()

const totalMinutes = computed(() =>
  (props.advice?.phases || []).reduce((sum: number, phase: any) => sum + Number(phase.estimatedMinutes || 0), 0)
)
const totalDurationText = computed(() => {
  const minutes = Number(totalMinutes.value || 0)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`
})

function nodeTitle(id: string) {
  const raw = String(id || '')
  const key = raw.replace(/^topic:/, '')
  return props.nodeTitles?.[raw] || props.nodeTitles?.[key] || (raw.startsWith('bank:') ? '题库' : raw)
}
</script>

<style scoped>
.nap { display: flex; height: calc(100vh - 110px); min-height: 420px; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid #e8edf5; border-radius: 12px; background: #fff; }
.nap__head { flex: none; }
.nap__eyebrow { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.nap__head h3 { margin: 5px 0 0; color: #253247; font-size: 16px; line-height: 1.35; }
.nap__summary { display: -webkit-box; overflow: hidden; margin: 7px 0 0; color: #5f6b7d; font-size: 12px; line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.nap__meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.nap__meta span { padding: 3px 8px; border-radius: 99px; background: #f3f6fb; color: #7d8596; font-size: 10.5px; }
.nap__scroll { min-height: 0; flex: 1; overflow-y: auto; overscroll-behavior: contain; padding-right: 3px; scrollbar-width: thin; scrollbar-color: #cfd8e6 transparent; }
.nap__scroll::-webkit-scrollbar { width: 6px; }
.nap__scroll::-webkit-scrollbar-thumb { border-radius: 99px; background: #cfd8e6; }
.nap__phase { padding: 10px 11px; border: 1px solid #e8edf5; border-radius: 8px; background: #fbfcff; }
.nap__phase + .nap__phase { margin-top: 8px; }
.nap__phase-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.nap__phase-head b { color: #253247; font-size: 12.5px; }
.nap__phase-head span { flex: none; color: #2f5fce; font-size: 10.5px; }
.nap__phase p { margin: 5px 0 0; color: #5f6b7d; font-size: 11.5px; line-height: 1.55; }
.nap__nodes { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 7px; }
.nap__nodes span { padding: 3px 7px; border-radius: 5px; background: #eef4ff; color: #2f5fce; font-size: 10.5px; }
.nap__risks { margin-top: 10px; padding: 9px 11px; border: 1px dashed #ecd9b6; border-radius: 8px; background: #fffaf0; }
.nap__risks b { color: #8a6422; font-size: 11.5px; }
.nap__risks p { margin: 5px 0 0; color: #8f7b53; font-size: 11px; line-height: 1.55; }
.nap__empty { padding: 32px 10px; color: #9aa3b2; font-size: 12px; text-align: center; }
.nap__foot { flex: none; padding-top: 7px; border-top: 1px solid #eef1f6; }
.nap__foot .el-button { width: 100%; }
</style>
