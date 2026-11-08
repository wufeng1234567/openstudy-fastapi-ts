<template>
  <aside class="krp" @pointerdown.stop>
    <header class="krp__head">
      <div class="krp__title-wrap">
        <span class="krp__eyebrow"><OsIcon name="sparkles" :size="13" /> 知航 · 活计划</span>
        <h3>{{ route.targetTitle ? `目标：${route.targetTitle}` : '今日航线' }}</h3>
      </div>
      <button type="button" class="krp__exit" title="退出航线，回到知识图谱" @click="emit('exit')">结束</button>
    </header>

    <div class="krp__strategies" role="group" aria-label="航线规划方式">
      <button
        v-for="item in strategyOptions"
        :key="item.value"
        type="button"
        class="krp__strategy"
        :class="{ 'is-active': strategy === item.value }"
        @click="emit('strategy', item.value)"
      >
        {{ item.label }}
      </button>
    </div>

    <div v-if="offRouteTitle" class="krp__offroute">
      <span>你正在看《{{ offRouteTitle }}》，它不在当前航线上</span>
      <button type="button" @click="emit('set-target', offRoutePageId || 0)">设为目标重算</button>
    </div>

    <p class="krp__basis">{{ basisText }}</p>

    <div class="krp__track">
      <template v-for="(stop, index) in stops" :key="stop.pageId">
        <button
          type="button"
          class="krp__step"
          :class="[`is-${stop.status || 'next'}`, { 'is-active': activeStop && activeStop.pageId === stop.pageId }]"
          :title="`${stop.title} · ${statusText(stop)}`"
          @click="emit('select', stop.pageId)"
        >
          <i>{{ index + 1 }}</i>
          <span>{{ stop.title }}</span>
        </button>
        <em v-if="index < stops.length - 1" class="krp__track-link" :class="{ 'is-past': stop.status === 'done' }"></em>
      </template>
    </div>

    <div v-if="activeStop" class="krp__current">
      <span>{{ activeStop.roleLabel || '当前站' }} · 为什么是这里</span>
      <p>{{ activeStop.reason || '按图谱顺序继续学习' }}</p>
    </div>

    <button type="button" class="krp__plan-link" @click="emit('open-plan')">
      <span>今日任务 {{ plan?.progress?.todayDone || 0 }}/{{ plan?.progress?.todayTotal || 0 }}</span>
      <b>查看完整计划 →</b>
    </button>

    <button type="button" class="krp__go" :disabled="loading" @click="emit('start')">
      <span>{{ activeStop?.task?.label || '继续学习' }}</span>
      <OsIcon name="arrow-right" :size="14" />
    </button>

    <footer class="krp__foot">
      <span>自动记录 · 自动更新</span>
      <button type="button" class="krp__help" @click="emit('guide')">使用说明</button>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'

const props = defineProps<{
  route: any
  plan?: any | null
  stops: any[]
  activeStop: any | null
  strategy: string
  loading?: boolean
  offRouteTitle?: string
  offRoutePageId?: number | null
}>()

const emit = defineEmits<{
  (e: 'strategy', value: string): void
  (e: 'select', pageId: number): void
  (e: 'start'): void
  (e: 'exit'): void
  (e: 'guide'): void
  (e: 'set-target', pageId: number): void
  (e: 'open-plan'): void
}>()

const strategyOptions = [
  { value: 'weakness', label: '补弱' },
  { value: 'foundation', label: '打基础' },
  { value: 'explore', label: '拓展' }
]

const activeStop = computed(() => props.activeStop)
const basisText = computed(() => {
  const route = props.route || {}
  if (route.mode === 'graph') {
    return '依据：前置关系 + 学习状态'
  }
  if (route.degraded?.noPracticeData) return '依据：图谱连接 + 阅读状态'
  return '依据：图谱连接 + 学习状态'
})

function statusText(stop: any) {
  if (stop.status === 'current') return '现在学'
  if (stop.status === 'done') return '已完成'
  if (stop.status === 'review') return '复习'
  if (stop.learning?.level === 'reading') return '已读'
  if (stop.learning?.level === 'practicing') return '练习中'
  if (stop.learning?.level === 'mastered') return '已掌握'
  return '待学习'
}
</script>

<style scoped>
.krp {
  position: absolute;
  z-index: 9;
  top: 12px;
  right: 12px;
  display: flex;
  width: min(200px, calc(100vw - 32px));
  max-height: calc(100vh - 200px);
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 10px 11px;
  border: 1px solid #e4eaf3;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(47, 95, 206, 0.1);
}
.krp__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.krp__title-wrap { min-width: 0; }
.krp__eyebrow { display: inline-flex; align-items: center; gap: 4px; color: #2f5fce; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; }
.krp__head h3 { overflow: hidden; margin: 5px 0 0; color: #253247; font-size: 16px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.krp__exit { flex: none; padding: 2px 4px; border: 0; color: #8a91a0; background: transparent; cursor: pointer; font: inherit; font-size: 11px; line-height: 1.2; }
.krp__exit:hover { color: #2f5fce; background: #f3f7ff; }
.krp__strategies { display: flex; gap: 4px; padding: 3px; border: 1px solid #e8edf5; border-radius: 8px; background: #f7f9fc; }
.krp__strategy { flex: 1; padding: 5px 0; border: 0; border-radius: 6px; color: #7d8596; background: transparent; cursor: pointer; font: inherit; font-size: 11px; }
.krp__strategy.is-active { color: #2f5fce; background: #fff; box-shadow: 0 1px 4px rgba(47, 95, 206, 0.12); font-weight: 600; }
.krp__offroute { display: flex; flex-direction: column; gap: 5px; padding: 8px 9px; border: 1px solid #e0e8f8; border-radius: 8px; background: #f8faff; }
.krp__offroute span { color: #697386; font-size: 11px; line-height: 1.45; }
.krp__offroute button { align-self: flex-start; padding: 0; border: 0; color: #2f5fce; background: transparent; cursor: pointer; font: inherit; font-size: 11px; font-weight: 600; }
.krp__offroute button:hover { text-decoration: underline; }
.krp__lead { margin: 0; color: #8a91a0; font-size: 12px; line-height: 1.55; }
.krp__basis { margin: -3px 0 0; color: #a0a6b2; font-size: 11px; line-height: 1.45; }
.krp__track { display: flex; align-items: flex-start; gap: 0; padding: 3px 0 1px; }
.krp__step { display: flex; min-width: 0; flex: 1; flex-direction: column; align-items: center; gap: 3px; padding: 0; border: 0; background: transparent; color: #7d8596; cursor: pointer; font: inherit; text-align: center; }
.krp__step > i { display: inline-flex; width: 20px; height: 20px; flex: none; align-items: center; justify-content: center; border: 1.5px solid #d7dfec; border-radius: 50%; background: #fff; color: #8b95a7; font-size: 10px; font-style: normal; font-weight: 700; transition: border-color .15s ease, background .15s ease, color .15s ease; }
.krp__step > span { overflow: hidden; width: 100%; color: #7d8596; font-size: 11px; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.krp__step:hover > i { border-color: #9eb8ec; color: #2f5fce; }
.krp__step.is-current > i { border-color: #2f5fce; background: #2f5fce; color: #fff; }
.krp__step.is-current > span { color: #1f3f8f; font-weight: 700; }
.krp__step.is-done > i { border-color: #7fc1ad; background: #2f9e8f; color: #fff; }
.krp__track-link { height: 1px; flex: 1; margin-top: 10px; background: #e6ebf4; }
.krp__track-link.is-past { background: #9ed3c4; }
.krp__current { padding: 6px 8px; border: 1px solid #e4ebfa; border-radius: 8px; background: #f7f9ff; }
.krp__current span { color: #2f5fce; font-size: 11px; font-weight: 700; }
.krp__current p { overflow: hidden; margin: 4px 0 0; color: #697386; font-size: 12px; line-height: 1.55; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
.krp__plan-link { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 6px 8px; border: 1px solid #e4ebfa; border-radius: 7px; color: #697386; background: #fff; cursor: pointer; font: inherit; font-size: 11px; }
.krp__plan-link b { color: #2f5fce; font-weight: 600; white-space: nowrap; }
.krp__plan-link:hover { border-color: #b9cdf3; background: #f8faff; }
.krp__go { display: flex; height: 33px; align-items: center; justify-content: center; gap: 6px; border: 0; border-radius: 7px; background: #2f5fce; color: #fff; cursor: pointer; font: inherit; font-size: 12px; font-weight: 600; }
.krp__go:hover { background: #2853b8; }
.krp__go:disabled { opacity: .55; cursor: not-allowed; }
.krp__foot { display: flex; align-items: center; justify-content: space-between; gap: 6px; color: #a0a8b6; font-size: 11px; white-space: nowrap; }\n.krp__foot > span { overflow: hidden; text-overflow: ellipsis; }
.krp__help { flex: none; padding: 0; border: 0; color: #8a91a0; background: transparent; cursor: pointer; font: inherit; font-size: 11px; white-space: nowrap; }
.krp__help:hover { color: #2f5fce; }
@media (max-width: 1100px) {
  .krp { top: 10px; right: 10px; width: min(190px, calc(100vw - 20px)); max-height: calc(100vh - 190px); gap: 7px; padding: 10px; }
  .krp__stops { max-height: 220px; overflow-y: auto; }
}
@media (max-height: 820px) {
  .krp__lead { display: none; }
  .krp__basis { display: none; }
  .krp__foot { display: none; }
  .krp__stops { max-height: 180px; overflow-y: auto; }
}
@media (max-height: 720px) {
  .krp { gap: 6px; padding: 10px; }
  .krp__lead { display: none; }
  .krp__stops { max-height: 150px; overflow-y: auto; }
  .krp__basis { font-size: 10px; }
}
</style>











