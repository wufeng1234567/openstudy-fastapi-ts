<template>
  <div class="perf-monitor" :class="{ 'is-low': fps > 0 && fps < 45 }">
    <button type="button" class="perf-pill" title="点击展开性能监视器" @click="expanded = !expanded">
      <span class="perf-dot"></span>
      <b>{{ fps || '—' }}</b>
      <span>FPS</span>
    </button>
    <div v-if="expanded" class="perf-panel">
      <div class="perf-panel__head">
        <b>性能监视器</b>
        <span>{{ lastAction || 'idle' }}</span>
      </div>
      <div class="perf-metrics">
        <span>FPS <b>{{ fps }}</b></span>
        <span>帧耗时 <b>{{ frameMs }}ms</b></span>
        <span>最低 <b>{{ minFps }}</b></span>
      </div>
      <div class="perf-bar"><i :style="{ width: `${Math.min(100, fps)}%` }"></i></div>
      <div class="perf-panel__meta">
        <span>长任务 {{ longTasks }}</span>
        <span>节点 {{ nodeCount }}</span>
        <span>边 {{ edgeCount }}</span>
      </div>
      <div class="perf-panel__foot">
        <span>{{ reportStatus }}</span>
        <span>每 10s 上报</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { reportPerformance } from '@/api/ai/workspace'

const props = withDefaults(defineProps<{
  page?: string
  kbId?: number | null
  nodeCount?: number
  edgeCount?: number
}>(), {
  page: 'knowledge-graph',
  kbId: 0,
  nodeCount: 0,
  edgeCount: 0
})

const expanded = ref(false)
const fps = ref(0)
const frameMs = ref('0.0')
const minFps = ref(999)
const longTasks = ref(0)
const lastAction = ref('')
const reportStatus = ref('等待上报')
const sessionId = `perf-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
const samples: Array<{ t: number; fps: number; frameMs: number; longTasks: number }> = []

let raf = 0
let lastSampleAt = 0
let frames = 0
let lastReportAt = 0
let lastLongTasks = 0
let observer: PerformanceObserver | null = null

function onAction(event: Event) {
  const detail = (event as CustomEvent<any>).detail || {}
  const action = String(detail.action || detail.name || '').trim()
  if (action) lastAction.value = action
}

function observeLongTasks() {
  const PerformanceObserverCtor = (window as any).PerformanceObserver
  if (!PerformanceObserverCtor) return
  try {
    observer = new PerformanceObserverCtor((list: any) => {
      // 浏览器可能传 PerformanceObserverEntryList，而不是数组；统一取 entries。
      const entries = Array.isArray(list)
        ? list
        : typeof list?.getEntries === 'function'
          ? list.getEntries()
          : []
      for (const entry of entries) {
        if (Number(entry.duration || 0) >= 50) longTasks.value += 1
      }
    })
    observer.observe({ entryTypes: ['longtask'] })
  } catch {
    observer = null
  }
}

function tick(now: number) {
  frames += 1
  if (now - lastSampleAt >= 1000) {
    const elapsed = Math.max(1, now - lastSampleAt)
    const currentFps = Math.round((frames * 1000) / elapsed)
    fps.value = currentFps
    frameMs.value = (elapsed / Math.max(1, frames)).toFixed(1)
    minFps.value = Math.min(minFps.value, currentFps)
    samples.push({ t: Date.now(), fps: currentFps, frameMs: Number((elapsed / Math.max(1, frames)).toFixed(1)), longTasks: longTasks.value - lastLongTasks })
    if (samples.length > 30) samples.shift()
    lastLongTasks = longTasks.value
    frames = 0
    lastSampleAt = now
    if (now - lastReportAt >= 10000) void report()
  }
  raf = requestAnimationFrame(tick)
}

async function report() {
  lastReportAt = performance.now()
  const snapshot = {
    sessionId,
    page: props.page,
    kbId: Number(props.kbId || 0),
    nodeCount: Number(props.nodeCount || 0),
    edgeCount: Number(props.edgeCount || 0),
    fps: fps.value,
    avgFrameMs: Number(frameMs.value),
    minFps: minFps.value === 999 ? fps.value : minFps.value,
    longTasks: longTasks.value,
    action: lastAction.value,
    samples: samples.slice(-10)
  }
  try {
    const res = await reportPerformance(snapshot)
    reportStatus.value = res.code === 200 ? '已写入后台日志' : '上报失败'
    minFps.value = fps.value || 999
  } catch {
    reportStatus.value = '上报失败（不影响使用）'
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') void report()
}

onMounted(() => {
  lastSampleAt = performance.now()
  lastReportAt = lastSampleAt
  observeLongTasks()
  window.addEventListener('openstudy:performance', onAction)
  document.addEventListener('visibilitychange', onVisibilityChange)
  raf = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  observer?.disconnect()
  window.removeEventListener('openstudy:performance', onAction)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.perf-monitor { position: absolute; z-index: 12; top: 58px; left: 16px; display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
.perf-pill { display: inline-flex; align-items: center; gap: 5px; height: 25px; padding: 0 8px; border: 1px solid rgba(15, 23, 42, 0.1); border-radius: 7px; color: #66758b; background: rgba(255, 255, 255, 0.9); box-shadow: 0 4px 12px rgba(29, 43, 70, 0.08); cursor: pointer; font: inherit; font-size: 10px; }
.perf-pill b { color: #2f9e8f; font-size: 12px; font-variant-numeric: tabular-nums; }
.perf-monitor.is-low .perf-pill b { color: #d38a42; }
.perf-dot { width: 6px; height: 6px; border-radius: 50%; background: #2f9e8f; }
.perf-monitor.is-low .perf-dot { background: #d38a42; }
.perf-panel { width: 210px; padding: 10px; border: 1px solid rgba(15, 23, 42, 0.1); border-radius: 9px; background: rgba(255, 255, 255, 0.96); box-shadow: 0 8px 24px rgba(29, 43, 70, 0.12); backdrop-filter: blur(8px); }
.perf-panel__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: #253247; font-size: 11px; }
.perf-panel__head span { color: #9aa1af; font-size: 9px; }
.perf-metrics { display: flex; justify-content: space-between; margin-top: 8px; color: #8a94a6; font-size: 9.5px; }
.perf-metrics b { color: #253247; font-size: 10.5px; font-variant-numeric: tabular-nums; }
.perf-bar { height: 4px; margin-top: 7px; overflow: hidden; border-radius: 99px; background: #eef1f6; }
.perf-bar i { display: block; height: 100%; border-radius: inherit; background: #2f9e8f; transition: width .25s ease; }
.perf-monitor.is-low .perf-bar i { background: #d38a42; }
.perf-panel__meta, .perf-panel__foot { display: flex; justify-content: space-between; gap: 6px; margin-top: 7px; color: #9aa1af; font-size: 9px; }
.perf-panel__foot { padding-top: 6px; border-top: 1px solid #eef1f6; }
</style>
