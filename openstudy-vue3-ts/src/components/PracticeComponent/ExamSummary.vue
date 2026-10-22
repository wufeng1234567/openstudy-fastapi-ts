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
        <!--
          顶部动作按钮（2026-10-22 定稿）
          ==================================================================
          这里踩过两次坑，改之前先读完：

          坑一：原来只有一个「再考一次」，绑的父组件处理函数里带了一条
                `if (historyRecord.value) → 回历史列表` 的分支，把「再考一次」
                也一起劫持了 —— 用户从考试记录点进详情、再点「再考一次」，
                期望重考，实际被送回列表，看起来就是"点了再考一次跳到考试记录页"。

          坑二：修坑一时把按钮改成**互斥**的（历史回看只给「返回记录」），
                结果历史详情里再也找不到「再考一次」，用户想重考同一场
                只能自己记住配置回去重新设一遍 —— 反而更难用。

          最终口径（用户明确要求「方便用户使用」）：
            · 历史回看要**保留「再考一次」**，让用户把同一套卷子再考一遍；
            · 重考时**沿用它自己的配置**（题型、每题分值、时长、及格分、
              选项乱序、多选判分规则全部照旧），不要用户重新设；
            · 同时保留「返回记录」，让用户能退回列表，不必先离开再重进。

          所以现在是：返回记录（仅历史回看）+ 再考一次（两种来源都有）+ 离开。
          两个动作各有各的按钮，互不覆盖。
        -->
        <button v-if="readonly" class="ghost-btn" type="button" @click="$emit('back-to-history')">
          <el-icon><Back /></el-icon>
          <span>返回记录</span>
        </button>
        <button class="ghost-btn ghost-btn--primary" type="button" @click="$emit('retry')">
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

          <!--
            组合题：先给阅读材料，再逐子题展开
            ============================================================
            原来这里只有一个 `item.stem`，组合题的所有子题都被吞掉了，
            用户只能看到"这题错了"，不知道具体哪一问错、错在哪。
          -->
          <template v-if="isComposite(item.type)">
            <div v-if="item.mainContent" class="wc-main-content">{{ item.mainContent }}</div>

            <div v-if="item.subItems && item.subItems.length" class="wc-subs">
              <div v-for="sub in item.subItems" :key="sub.index" class="wc-sub">
                <div class="wc-sub-head">
                  <span class="wc-sub-index">第 {{ sub.index }} 问</span>
                  <span class="wc-sub-type">{{ typeLabel(sub.type) }}</span>
                </div>
                <div class="wc-sub-stem">{{ sub.question }}</div>

                <!-- 子题的选项也要显示，否则同样不知道选的是哪个 -->
                <ul v-if="sub.options && sub.options.length" class="wc-options">
                  <li v-for="(opt, oi) in sub.options" :key="oi" class="wc-option" :class="optionClass(sub, oi)">
                    <span class="wo-label">{{ optionLabel(oi) }}</span>
                    <span class="wo-text">{{ opt }}</span>
                  </li>
                </ul>

                <div class="wc-answers">
                  <div class="wa-row">
                    <span class="wa-key">你的答案</span>
                    <span class="wa-val bad">{{ describeAnswer(sub.userAnswer, sub.options) }}</span>
                  </div>
                  <div class="wa-row">
                    <span class="wa-key">正确答案</span>
                    <span class="wa-val ok">{{ describeAnswer(sub.correctAnswer, sub.options) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 老记录没有子题明细，退回显示整题答案，至少不空白 -->
            <div v-else class="wc-answers">
              <div class="wa-row">
                <span class="wa-key">你的答案</span>
                <span class="wa-val bad">{{ describeAnswer(item.userAnswer, item.options) }}</span>
              </div>
              <div class="wa-row">
                <span class="wa-key">正确答案</span>
                <span class="wa-val ok">{{ describeAnswer(item.correctAnswer, item.options) }}</span>
              </div>
            </div>
          </template>

          <!-- 普通题型：题干 + 选项 + 答案 -->
          <template v-else>
            <div class="wc-stem">{{ item.stem }}</div>

            <!--
              选项列表（2026-10-22 新增）
              ============================================================
              这是这次修的核心：原来只显示「你的答案 A / 正确答案 C」，
              但 A 和 C 到底是什么，用户完全看不到 —— 错题明细等于没用。
              现在把四个选项全列出来，并用颜色标出：
                · 正确选项 → 绿色
                · 用户选错的选项 → 红色
                · 用户漏选的正确项 → 绿色描边（多选题部分给分时很有用）
            -->
            <ul v-if="item.options && item.options.length" class="wc-options">
              <li v-for="(opt, oi) in item.options" :key="oi" class="wc-option" :class="optionClass(item, oi)">
                <span class="wo-label">{{ optionLabel(oi) }}</span>
                <span class="wo-text">{{ opt }}</span>
                <!--
                  ⚠️ 判断题不打标签（2026-10-22）。
                  它的选项文字本身就是"正确 / 错误"，再挂一个「正确」标签
                  会渲染成「A 正确 正确」，看着像 bug。
                  对错已经由底色+边框表达了，标签对判断题是冗余信息。
                -->
                <template v-if="!isTrueFalse(item)">
                  <span v-if="isCorrectPick(item, oi)" class="wo-tag ok">正确</span>
                  <span v-if="isWrongPick(item, oi) && !isCorrectPick(item, oi)" class="wo-tag bad">误选</span>
                </template>
              </li>
            </ul>

            <div class="wc-answers">
              <div class="wa-row">
                <span class="wa-key">你的答案</span>
                <span class="wa-val bad">{{ describeAnswer(item.userAnswer, item.options) }}</span>
              </div>
              <div class="wa-row">
                <span class="wa-key">正确答案</span>
                <span class="wa-val ok">{{ describeAnswer(item.correctAnswer, item.options) }}</span>
              </div>
            </div>
          </template>

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
  Back,
  Close,
  Refresh
} from '@element-plus/icons-vue'
import type { MockExamItemDetail, MockExamRecord, QuestionType } from '@/types'

const props = defineProps({
  record: { type: Object as () => MockExamRecord, required: true },
  /**
   * 是否是"回看历史记录"（只读）
   *
   * true  → 这一场已经结束了，用户是从考试记录里翻出来看的。
   *         此时不提供"再考一次"（那会让人以为在重考这一场），
   *         只提供"返回记录"回到列表。
   * false → 刚交完卷的结果页，可以再考一次。
   */
  readonly: { type: Boolean, default: false }
})

defineEmits<{
  (e: 'close'): void
  /** 刚考完 → 再考一次 */
  (e: 'retry'): void
  /** 历史回看 → 返回考试记录列表 */
  (e: 'back-to-history'): void
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

/* ==================== 错题明细：选项与答案的渲染 ==================== */

/** 选项字母：0 → A */
function optionLabel(i: number) {
  return String.fromCharCode(65 + i)
}

/** 是否组合题（阅读 / 完形） */
function isComposite(type: string) {
  return type === 'readingComprehension' || type === 'cloze'
}

/**
 * 是否判断题
 *
 * 判断题的选项只有「正确 / 错误」两项，文字本身就是答案语义，
 * 所以不打「正确 / 误选」标签（会变成「A 正确 正确」）。
 * 也兼容选项文字是"对 / 错"、"true / false" 的老数据。
 */
function isTrueFalse(item: any) {
  if (item?.type === 'truefalse') return true
  const opts = item?.options
  if (!Array.isArray(opts) || opts.length !== 2) return false
  const joined = opts.map((o: any) => String(o).trim()).join('|')
  return /^(正确|对|true|True|TRUE)\|(错误|错|false|False|FALSE)$/.test(joined)
}

/**
 * 把答案归一成"一组选项下标"
 *
 * 三种存储形态都要兼容：
 *   · 数字         → 单选 / 判断（下标）
 *   · 数字数组     → 多选
 *   · 数字字符串   → 老数据（后端原始答案 "0" / "1"）
 */
function asIndexSet(ans: any): Set<number> {
  const out = new Set<number>()
  if (ans === null || ans === undefined || ans === '') return out
  const push = (v: any) => {
    if (typeof v === 'number' && Number.isFinite(v)) { out.add(v); return }
    if (typeof v === 'string') {
      const t = v.trim()
      if (!t) return
      // 纯数字字符串
      if (/^\d+$/.test(t)) { out.add(Number(t)); return }
      // 字母（A/B/C…）
      if (/^[A-Za-z]$/.test(t)) { out.add(t.toUpperCase().charCodeAt(0) - 65); return }
    }
  }
  if (Array.isArray(ans)) ans.forEach(push)
  else push(ans)
  return out
}

/** 用户是否选了这个选项 */
function isWrongPick(item: any, oi: number) {
  return asIndexSet(item.userAnswer).has(oi)
}

/** 这个选项是不是正确答案 */
function isCorrectPick(item: any, oi: number) {
  return asIndexSet(item.correctAnswer).has(oi)
}

/**
 * 单个选项的高亮样式
 *
 * 只有"选择类"题才有选项，填空/问答走不到这里。
 *   · 正确答案 → 绿色
 *   · 用户误选（错且不是答案）→ 红色
 *   · 用户漏选的正确答案 → 仍然绿色，但标签会显示"正确"帮他对照
 */
function optionClass(item: any, oi: number) {
  return {
    'is-correct': isCorrectPick(item, oi),
    'is-wrong': isWrongPick(item, oi) && !isCorrectPick(item, oi),
    'is-missed': isCorrectPick(item, oi) && !isWrongPick(item, oi)
  }
}

/**
 * 答案文案：不同题型用不同的说法
 *
 * ⚠️ 不能一律走 `formatAnswer`（2026-10-22）：
 *    · 填空/问答的答案是**字符串内容**，转成字母毫无意义
 *      （当年就吃过这个亏：问答题的答案被渲染成 "A"）；
 *    · 判断题存的是 0/1，应该显示「正确 / 错误」而不是「A / B」；
 *    · 选择题最好同时给出字母和选项原文，方便一眼对照。
 */
function describeAnswer(ans: any, options?: any[]) {
  const empty = ans === null || ans === undefined || ans === '' ||
    (Array.isArray(ans) && ans.length === 0) ||
    (typeof ans === 'string' && ans.trim() === '')

  if (empty) return '未作答'

  // 填空题 / 问答题：直接给文本
  if (typeof ans === 'string' && !/^\d+$/.test(ans.trim()) && !/^[A-Za-z]$/.test(ans.trim())) {
    return ans
  }

  // 判断题：0 = 正确，1 = 错误（后端约定，见 transformQuestionForDisplay）
  if (isTrueFalse({ options })) {
    const idx = Array.from(asIndexSet(ans))[0]
    if (idx === 0) return '正确'
    if (idx === 1) return '错误'
  }

  const set = asIndexSet(ans)
  if (set.size === 0) {
    // 既不是下标也不是字母 → 当作纯文本（例如 "true"/"n-1"）
    return String(ans)
  }

  const letters = Array.from(set).sort((a, b) => a - b).map(optionLabel)
  // 有选项原文时，字母后面附上内容，用户不用来回对照
  if (options && options.length) {
    const texts = Array.from(set).sort((a, b) => a - b)
      .map((i) => (options[i] !== undefined ? String(options[i]) : ''))
      .filter(Boolean)
    if (texts.length) {
      return `${letters.join('、')}（${texts.join('；')}）`
    }
  }
  return letters.join('、')
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

/*
 * 「再考一次」用主色描边强调（2026-10-22）
 *
 * 一排三个按钮里，它是最主要的下一步动作；「返回记录」和「离开」
 * 都是"退出当前视图"。视觉上要给个主次，否则三个长得一模一样，
 * 用户得读一遍文字才知道该点哪个。
 * 只用描边+主色文字，不加实心底色 —— 结果页已经很满，再来一块
 * 实心主色块会抢走得分环的注意力。
 */
.ghost-btn--primary {
  border-color: var(--os-primary, #2563eb);
  color: var(--os-primary, #2563eb);
}

.ghost-btn--primary:hover {
  background: var(--os-primary, #2563eb);
  border-color: var(--os-primary, #2563eb);
  color: #fff;
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

/* ---------- 错题明细：选项列表（2026-10-22 新增） ---------- */
.wc-options {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/*
 * 选项行：默认中性，用左色条 + 底色区分对错。
 * 不用整行大红大绿 —— 一屏四五个选项，全上高饱和色会非常吵，
 * 而这一屏的主要信息是"我错在哪"，只需要把对/错两行提出来。
 */
.wc-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
  background: #fff;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-2, #4b5563);
}

.wc-option.is-correct {
  border-color: #a7f3d0;
  background: #f0fdf4;
  color: #065f46;
}

.wc-option.is-wrong {
  border-color: #fecaca;
  background: #fef2f2;
  color: #991b1b;
}

/* 用户漏选的正确项：绿框但底色更淡，和"他选对的绿"区分开 */
.wc-option.is-missed {
  border-color: #a7f3d0;
  background: #f7fefb;
  color: #065f46;
}

.wo-label {
  flex: none;
  width: 18px;
  font-weight: 600;
}

.wo-text {
  flex: 1;
  word-break: break-word;
}

.wo-tag {
  flex: none;
  align-self: center;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.wo-tag.ok {
  background: #d1fae5;
  color: #047857;
}

.wo-tag.bad {
  background: #fee2e2;
  color: #b91c1c;
}

/* ---------- 错题明细：组合题 ---------- */
.wc-main-content {
  margin-bottom: 12px;
  padding: 11px 13px;
  border-radius: 9px;
  background: #fff;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
  font-size: 12.5px;
  line-height: 1.85;
  color: var(--os-text-2, #4b5563);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
}

.wc-subs {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.wc-sub {
  padding: 11px 13px;
  border-radius: 9px;
  background: #fff;
  border: 1px solid var(--os-border-subtle, #f1f3f5);
}

.wc-sub-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.wc-sub-index {
  font-size: 12px;
  font-weight: 600;
  color: var(--os-text, #111827);
}

.wc-sub-type {
  padding: 1px 7px;
  border-radius: 999px;
  background: var(--os-bg-subtle, #f3f4f6);
  font-size: 11px;
  color: var(--os-text-3, #6b7280);
}

.wc-sub-stem {
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text, #111827);
  margin-bottom: 8px;
  word-break: break-word;
}
</style>
