<!--
  模拟考试结果页（2026-10-22）

  与旧的 `PracticeResult.vue` 的区别：
    · 旧版直接铺开"所有题目 + 解析"，一屏几十道题，用户根本读不完；
    · 新版先给**一眼能看懂的结论**（得分环 + 对错饼图 + 关键指标），
      再让用户按需点进「错题明细」。信息分两层，先结论后证据。

  为什么用环形图而不是实心饼：
    中间那块圆心正好放"得分"，一张图同时承担"分数"与"对错占比"两个信息，
    省掉一次视觉跳转。这也是后面历史列表卡片复用同一套图形的依据。
-->
<template>
  <div class="exam-summary">
    <!-- 顶部：离开 -->
    <header class="summary-head">
      <div class="head-left">
        <span class="exam-badge" :class="record.passed ? 'is-pass' : 'is-fail'">
          {{ record.passed ? '已通过' : '未通过' }}
        </span>
        <h2>考试结果</h2>
        <span class="head-sub">{{ record.bankName }} · {{ formatTime(record.submittedAt) }}</span>
      </div>
      <div class="head-actions">
        <button class="ghost-btn" type="button" @click="$emit('back-to-setup')">
          <el-icon><Refresh /></el-icon>
          <span>再考一次</span>
        </button>
        <button class="ghost-btn" type="button" @click="$emit('close')">
          <el-icon><Close /></el-icon>
          <span>离开</span>
        </button>
      </div>
    </header>

    <!-- 成绩主卡 -->
    <section class="hero">
      <!-- 左：得分环 -->
      <div class="hero-score">
        <div ref="scoreChartRef" class="score-chart"></div>
      </div>

      <!-- 中：关键指标 -->
      <div class="hero-stats">
        <div class="stat">
          <span class="stat-val ok">{{ record.correctCount }}</span>
          <span class="stat-key">答对</span>
        </div>
        <div class="stat">
          <span class="stat-val bad">{{ record.wrongCount }}</span>
          <span class="stat-key">答错</span>
        </div>
        <div class="stat">
          <span class="stat-val">{{ record.totalQuestions }}</span>
          <span class="stat-key">总题数</span>
        </div>
        <div class="stat">
          <span class="stat-val">{{ accuracy }}%</span>
          <span class="stat-key">正确率</span>
        </div>
        <div class="stat">
          <span class="stat-val">{{ formatDuration(record.durationSec) }}</span>
          <span class="stat-key">用时</span>
        </div>
        <div class="stat">
          <span class="stat-val">{{ formatScore(record.gotScore) }} / {{ formatScore(record.fullScore) }}</span>
          <span class="stat-key">得分</span>
        </div>
      </div>

      <!-- 右：对错饼图 -->
      <div class="hero-pie">
        <div ref="pieChartRef" class="pie-chart"></div>
      </div>
    </section>

    <!-- 按题型小结 -->
    <section v-if="typeStats.length" class="panel">
      <div class="panel-head">
        <h3>各题型表现</h3>
        <span class="panel-hint">用来判断薄弱环节在哪一类</span>
      </div>
      <div class="type-stats">
        <div v-for="t in typeStats" :key="t.type" class="type-stat">
          <div class="ts-head">
            <span class="ts-name">{{ t.label }}</span>
            <span class="ts-rate" :class="rateClass(t.rate)">{{ t.rate }}%</span>
          </div>
          <div class="ts-bar">
            <div class="ts-bar-fill" :class="rateClass(t.rate)" :style="{ width: t.rate + '%' }"></div>
          </div>
          <div class="ts-foot">{{ t.correct }} / {{ t.total }} 题正确 · {{ formatScore(t.gotScore) }} 分</div>
        </div>
      </div>
    </section>

    <!-- 错题明细入口 -->
    <section class="panel wrong-panel">
      <div class="panel-head">
        <h3>错题明细</h3>
        <span class="panel-hint">
          <template v-if="record.wrongCount > 0">
            共 {{ record.wrongCount }} 道题答错，点进去逐题看解析
          </template>
          <template v-else>本次考试全部答对，没有错题</template>
        </span>
      </div>

      <div v-if="record.wrongCount > 0" class="wrong-actions">
        <button class="primary-btn" type="button" @click="showDetail = !showDetail">
          <el-icon><component :is="showDetail ? ArrowUp : ArrowDown" /></el-icon>
          <span>{{ showDetail ? '收起错题明细' : '查看错题明细' }}</span>
        </button>
      </div>

      <!-- 内联展开：不跳页，用户看完还能回来看统计 -->
      <div v-if="showDetail && record.wrongCount > 0" class="wrong-list">
        <div v-for="item in wrongItems" :key="item.questionId" class="wrong-card">
          <div class="wc-head">
            <span class="wc-index">第 {{ item.index }} 题</span>
            <span class="wc-type">{{ typeLabel(item.type) }}</span>
            <span class="wc-score">{{ formatScore(item.gotScore) }} / {{ formatScore(item.fullScore) }} 分</span>
          </div>

          <div class="wc-stem" v-html="renderStem(item.stem)"></div>

          <div class="wc-answers">
            <div class="wa-row">
              <span class="wa-key">你的答案</span>
              <span class="wa-val bad">{{ formatAnswer(item.userAnswer) || '未作答' }}</span>
            </div>
            <div class="wa-row">
              <span class="wa-key">正确答案</span>
              <span class="wa-val ok">{{ formatAnswer(item.correctAnswer) }}</span>
            </div>
          </div>

          <div v-if="item.analysis" class="wc-analysis">
            <span class="wca-title">解析</span>
            <div class="wca-body">{{ item.analysis }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import {
  ArrowDown,
  ArrowUp,
  Close,
  Refresh
} from '@element-plus/icons-vue'
import type { MockExamItemDetail, MockExamRecord, QuestionType } from '@/types'

const props = defineProps({
  record: { type: Object as () => MockExamRecord, required: true }
})

defineEmits<{
  (e: 'close'): void
  (e: 'back-to-setup'): void
}>()

const showDetail = ref(false)

const scoreChartRef = ref<HTMLElement | null>(null)
const pieChartRef = ref<HTMLElement | null>(null)
let scoreChart: echarts.ECharts | null = null
let pieChart: echarts.ECharts | null = null

const TYPE_LABELS: Record<string, string> = {
  single: '单选题',
  multiple: '多选题',
  truefalse: '判断题',
  fillblank: '填空题',
  essay: '问答题',
  readingComprehension: '阅读理解',
  cloze: '完形填空',
  unknown: '未知题型'
}

function typeLabel(t: string) {
  return TYPE_LABELS[t] || t
}

const accuracy = computed(() =>
  props.record.totalQuestions > 0
    ? Math.round((props.record.correctCount / props.record.totalQuestions) * 100)
    : 0
)

const wrongItems = computed(() =>
  (props.record.items || []).filter((i) => !i.isCorrect)
)

/** 按题型汇总：正确率 + 得分，用于判断薄弱环节 */
const typeStats = computed(() => {
  const map = new Map<string, { type: string; label: string; total: number; correct: number; gotScore: number }>()
  for (const it of props.record.items || []) {
    const key = String(it.type || 'unknown')
    if (!map.has(key)) {
      map.set(key, { type: key, label: typeLabel(key), total: 0, correct: 0, gotScore: 0 })
    }
    const e = map.get(key)!
    e.total += 1
    if (it.isCorrect) e.correct += 1
    e.gotScore += Number(it.gotScore) || 0
  }
  return [...map.values()]
    .map((e) => ({ ...e, rate: e.total > 0 ? Math.round((e.correct / e.total) * 100) : 0 }))
    .sort((a, b) => a.rate - b.rate) // 薄弱项在前
})

function rateClass(rate: number) {
  if (rate >= 80) return 'good'
  if (rate >= 60) return 'mid'
  return 'bad'
}

function formatScore(n: number) {
  const v = Math.round((Number(n) || 0) * 10) / 10
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

function formatDuration(sec: number) {
  const s = Math.max(0, Math.floor(Number(sec) || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return m > 0 ? `${m}分${r}秒` : `${r}秒`
}

function formatTime(ts: number) {
  try {
    const d = new Date(ts)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return ''
  }
}

/**
 * 答案展示：把索引数组渲染成字母（0 → A）
 *
 * 单选/多选在内部存的是选项下标（见 `useQuestionPractice` 的答案归一），
 * 直接显示数字用户看不懂「0」是哪个选项。
 */
function formatAnswer(ans: any) {
  if (ans === null || ans === undefined || ans === '') return ''
  if (Array.isArray(ans)) {
    return ans
      .map((v) => (typeof v === 'number' ? String.fromCharCode(65 + v) : String(v)))
      .join('、')
  }
  if (typeof ans === 'number') return String.fromCharCode(65 + ans)
  return String(ans)
}

function escapeHtml(s: string) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function renderStem(stem: string) {
  // 题干在入库时已存为纯文本片段，这里只做转义，避免 v-html 注入
  return escapeHtml(String(stem || '')).replace(/\n/g, '<br>')
}

/* ==================== 图表 ==================== */

function renderScoreChart() {
  if (!scoreChartRef.value) return
  if (!scoreChart) scoreChart = echarts.init(scoreChartRef.value)

  const got = Math.max(0, Number(props.record.gotScore) || 0)
  const full = Math.max(0.1, Number(props.record.fullScore) || 0)
  const pct = Math.min(100, Math.round((got / full) * 100))
  const passed = props.record.passed

  scoreChart.setOption({
    series: [
      {
        type: 'pie',
        radius: ['72%', '92%'],
        silent: true,
        label: { show: false },
        labelLine: { show: false },
        data: [
          {
            value: pct,
            itemStyle: {
              color: passed ? '#10b981' : '#ef4444',
              borderRadius: 6
            }
          },
          {
            value: 100 - pct,
            itemStyle: { color: '#f1f3f5' }
          }
        ]
      }
    ],
    // 圆心文字：得分 / 满分
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '40%',
        style: {
          text: formatScore(got),
          fontSize: 34,
          fontWeight: 650,
          fill: passed ? '#059669' : '#dc2626',
          textAlign: 'center'
        }
      },
      {
        type: 'text',
        left: 'center',
        top: '57%',
        style: {
          text: `满分 ${formatScore(full)}`,
          fontSize: 12,
          fill: '#9ca3af',
          textAlign: 'center'
        }
      }
    ]
  })
}

function renderPieChart() {
  if (!pieChartRef.value) return
  if (!pieChart) pieChart = echarts.init(pieChartRef.value)

  const correct = Number(props.record.correctCount) || 0
  const wrong = Number(props.record.wrongCount) || 0

  pieChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: '{b}：{c} 题（{d}%）'
    },
    legend: {
      bottom: 0,
      itemWidth: 9,
      itemHeight: 9,
      icon: 'circle',
      textStyle: { fontSize: 12, color: '#6b7280' }
    },
    series: [
      {
        type: 'pie',
        radius: ['46%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 5, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        labelLine: { show: false },
        data: [
          { value: correct, name: '答对', itemStyle: { color: '#10b981' } },
          { value: wrong, name: '答错', itemStyle: { color: '#ef4444' } }
        ]
      }
    ]
  })
}

function resizeCharts() {
  scoreChart?.resize()
  pieChart?.resize()
}

onMounted(async () => {
  await nextTick()
  renderScoreChart()
  renderPieChart()
  window.addEventListener('resize', resizeCharts)
})

// 记录变化时（历史回看切换考题）重绘
watch(
  () => props.record,
  async () => {
    await nextTick()
    renderScoreChart()
    renderPieChart()
  },
  { deep: false }
)

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  scoreChart?.dispose()
  pieChart?.dispose()
  scoreChart = null
  pieChart = null
})
</script>

<style scoped>
.exam-summary {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px 28px 48px;
  max-width: 1120px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

/* ---------- 顶部 ---------- */
.summary-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.head-left h2 {
  margin: 0;
  font-size: 19px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.exam-badge {
  padding: 3px 11px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.exam-badge.is-pass {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}

.exam-badge.is-fail {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.head-sub {
  font-size: 12.5px;
  color: var(--os-text-4, #9ca3af);
}

.head-actions {
  display: flex;
  gap: 8px;
}

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--os-border, #e5e7eb);
  background: var(--os-bg, #fff);
  color: var(--os-text-2, #4b5563);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.ghost-btn:hover {
  background: var(--os-bg-subtle, #f9fafb);
  border-color: var(--os-border-strong, #d1d5db);
}

/* ---------- 成绩主卡 ---------- */
.hero {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr) 240px;
  gap: 18px;
  align-items: center;
  padding: 22px 24px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 16px;
  background: var(--os-bg, #fff);
}

@media (max-width: 960px) {
  .hero {
    grid-template-columns: 1fr;
    justify-items: center;
  }
}

.score-chart {
  width: 180px;
  height: 180px;
}

.pie-chart {
  width: 240px;
  height: 190px;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 12px 14px;
  border-radius: 11px;
  background: var(--os-bg-subtle, #f9fafb);
  border: 1px solid var(--os-border-subtle, #f1f3f5);
}

.stat-val {
  font-size: 19px;
  font-weight: 650;
  line-height: 1.15;
  color: var(--os-text, #111827);
  font-variant-numeric: tabular-nums;
}

.stat-val.ok {
  color: #059669;
}

.stat-val.bad {
  color: #dc2626;
}

.stat-key {
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 面板 ---------- */
.panel {
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 14px;
  background: var(--os-bg, #fff);
  padding: 18px 20px 20px;
}

.panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.panel-head h3 {
  margin: 0;
  font-size: 14.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.panel-hint {
  font-size: 12px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 题型表现 ---------- */
.type-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.type-stat {
  padding: 13px 15px;
  border-radius: 11px;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
  background: var(--os-bg-subtle, #f9fafb);
}

.ts-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.ts-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--os-text, #111827);
}

.ts-rate {
  font-size: 13px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.ts-rate.good,
.ts-bar-fill.good {
  color: #047857;
}

.ts-rate.mid {
  color: #b45309;
}

.ts-rate.bad {
  color: #b91c1c;
}

.ts-bar {
  height: 5px;
  border-radius: 3px;
  background: #e9ecef;
  overflow: hidden;
}

.ts-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.35s ease;
}

.ts-bar-fill.good {
  background: #10b981;
}

.ts-bar-fill.mid {
  background: #f59e0b;
}

.ts-bar-fill.bad {
  background: #ef4444;
}

.ts-foot {
  margin-top: 7px;
  font-size: 11.5px;
  color: var(--os-text-4, #9ca3af);
}

/* ---------- 错题明细 ---------- */
.wrong-actions {
  display: flex;
}

.primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  border: none;
  border-radius: 10px;
  background: var(--os-primary, #0f1115);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.primary-btn:hover {
  opacity: 0.88;
}

.wrong-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.wrong-card {
  padding: 15px 17px;
  border-radius: 12px;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
  background: var(--os-bg-subtle, #fafbfc);
}

.wc-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
  flex-wrap: wrap;
}

.wc-index {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.wc-type {
  padding: 1px 8px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 11px;
}

.wc-score {
  margin-left: auto;
  font-size: 12px;
  color: #b91c1c;
  font-variant-numeric: tabular-nums;
}

.wc-stem {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--os-text, #111827);
  margin-bottom: 11px;
  word-break: break-word;
}

.wc-answers {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 9px;
  background: #fff;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
}

.wa-row {
  display: flex;
  gap: 10px;
  font-size: 12.5px;
}

.wa-key {
  width: 62px;
  flex: none;
  color: var(--os-text-4, #9ca3af);
}

.wa-val {
  font-weight: 500;
  word-break: break-word;
}

.wa-val.ok {
  color: #047857;
}

.wa-val.bad {
  color: #b91c1c;
}

.wc-analysis {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--os-border, #e5e7eb);
}

.wca-title {
  display: inline-block;
  margin-bottom: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--os-text-3, #6b7280);
}

.wca-body {
  font-size: 12.5px;
  line-height: 1.75;
  color: var(--os-text-2, #4b5563);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
