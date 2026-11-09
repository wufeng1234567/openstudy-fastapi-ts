<template>
  <article class="spgc">
    <header class="spgc__head">
      <div>
        <span class="spgc__kicker">规划建议</span>
        <h4>{{ advice?.title || '围绕当前范围的规划建议' }}</h4>
      </div>
      <span class="spgc__meta">{{ advice?.phases?.length || 0 }} 个阶段</span>
    </header>

    <p class="spgc__summary">{{ advice?.summary }}</p>

    <StudyGraphCanvas
      class="spgc__graph"
      compact
      :nodes="graph?.nodes || []"
      :edges="graph?.edges || []"
      :groups="graph?.groups || []"
      :trace="trace"
      :visited-ids="visitedIds"
      phase="ready"
      :selected-id="trace?.seedNodeId || ''"
    />

    <div class="spgc__phases">
      <span v-for="phase in advice?.phases || []" :key="phase.id">
        {{ phase.title }}<em>约 {{ phase.estimatedMinutes || 0 }} 分钟</em>
      </span>
    </div>

    <footer class="spgc__foot">
      <span>建议不是任务，可以在页面继续调整。</span>
      <el-button size="small" type="primary" plain @click="openPage">在页面打开</el-button>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import StudyGraphCanvas from '@/views/front/myQuestion/myStats/components/StudyGraphCanvas.vue'

const props = withDefaults(
  defineProps<{
    advice?: any
    trace?: any
    graph?: any
    jumpUrl?: string
  }>(),
  {
    advice: null,
    trace: null,
    graph: null,
    jumpUrl: ''
  }
)

const router = useRouter()
const visitedIds = computed(() => (props.trace?.visitedNodeIds || []).map(String))

function openPage() {
  const url = props.jumpUrl || '/front/myQuestion/myStats?tab=plan'
  router.push(url)
}
</script>

<style scoped>
.spgc {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
  padding: 10px;
  border: 1px solid #e8edf5;
  border-radius: 10px;
  background: #fff;
}
.spgc__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.spgc__kicker { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.spgc__head h4 { margin: 4px 0 0; color: #253247; font-size: 14px; line-height: 1.4; }
.spgc__meta { flex: none; color: #a0a8b6; font-size: 10px; }
.spgc__summary { margin: 0; color: #7d8596; font-size: 11px; line-height: 1.55; }
.spgc__graph { margin: 2px 0; }
.spgc__phases { display: flex; flex-wrap: wrap; gap: 5px; }
.spgc__phases span { padding: 3px 7px; border: 1px solid #e4ebf6; border-radius: 99px; color: #5d6b82; background: #f8faff; font-size: 10px; }
.spgc__phases em { margin-left: 4px; color: #2f5fce; font-style: normal; font-weight: 600; }
.spgc__foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: #a0a8b6; font-size: 10px; }
</style>
