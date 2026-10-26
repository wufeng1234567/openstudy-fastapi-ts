<!--
  ============================================================================
  学情诊断面板（2026-10-26 v3 新增）
  ============================================================================

  ## 为什么要有这个组件

  后端 `study_diagnosis_service.diagnose()` 一直在算很好的数据：每道题的掌握
  状态（七档）、学科正确率、复习紧迫度、学习节奏。但它**只挂在 AI 工具链上**，
  用户要跟 AI 说一句话才能看到，而且默认产物是一份 PDF 下载。

  数据在，但用户看不到 —— 这是最可惜的一种浪费。所以这里把它画成**页内图表**：

    ① 掌握度分布（环形）  —— 一眼看出"我现在整体处于什么状态"
    ② 学科正确率（横向条）—— 哪个科目在拖后腿
    ③ 学习节奏（折线）    —— 是持续在学还是突击
    ④ 需要关注的题（列表）—— 点进去就能练

  ## 设计取舍

  · **不引新依赖**：用项目已有的 `echarts`（`myStats` 页面本来就在用）
  · **不下载 PDF**：所有信息页内呈现。PDF 导出是另一条路（题库导出），
    这个面板的目的恰恰是"不用下载也能看到"
  · **空状态要说人话**：没有数据时不画空图，直接给一句引导
  · **颜色有意义**：红色=反复错、橙色=该复习、绿色=已掌握、灰色=新题，
    与后端档位一一对应，不做花哨配色
-->
<template>
    <section class="panel diag-panel">
        <div class="panel-head">
            <h3 class="panel-title">学情诊断</h3>
            <span class="panel-sub">逐题掌握度 · 复习节奏 · 学科短板</span>
            <!-- ============ 导出复习卷（2026-10-26 v3） ============
                 诊断结果此前只能"看"，看完就没了。
                 这个按钮把它变成一份可打印的 Word：
                   卷首 分档表 + 学科表 ｜ 正文 题目 ｜ 卷尾 7 天计划表 ｜ 附页 答案
                 只在有数据时出现（无数据时生成出来是空卷，没意义）。 -->
            <el-button v-if="data?.hasData" class="dp-export" size="small" type="primary" plain
                :loading="exporting" @click="exportReviewSheet">
                <el-icon v-if="!exporting"><Download /></el-icon>
                生成复习卷
            </el-button>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="diag-loading">
            <el-icon class="is-loading" :size="18"><Loading /></el-icon>
            <span>正在分析你的作答记录…</span>
        </div>

        <!-- 无数据 -->
        <div v-else-if="!data || !data.hasData" class="diag-empty">
            <p>{{ data?.headline || '还没有作答记录 —— 先去题库里练几道，这里就会有诊断结果了' }}</p>
            <el-button v-if="data?.suggestions?.length" text type="primary" @click="emit('practice')">
                {{ data.suggestions[0] }}
            </el-button>
        </div>

        <template v-else>
            <!-- ============ 结论句（后端算好的，不是模板拼的） ============ -->
            <div class="diag-headline">
                <el-icon class="headline-icon"><InfoFilled /></el-icon>
                <span>{{ data.headline }}</span>
            </div>

            <!-- ============ 四个关键数字 ============ -->
            <div class="diag-kpis">
                <div class="kpi">
                    <div class="kpi-num">{{ data.summary.questionsSeen }}</div>
                    <div class="kpi-label">做过的题</div>
                </div>
                <div class="kpi">
                    <div class="kpi-num">{{ formatPct(data.summary.overallAccuracy) }}</div>
                    <div class="kpi-label">总正确率 (%)</div>
                </div>
                <div class="kpi" :class="{ warn: data.summary.needsAttention > 0 }">
                    <div class="kpi-num">{{ data.summary.needsAttention }}</div>
                    <div class="kpi-label">需要关注</div>
                </div>
                <div class="kpi" :class="{ warn: data.summary.overdueCount > 0 }">
                    <div class="kpi-num">{{ data.summary.overdueCount }}</div>
                    <div class="kpi-label">欠复习</div>
                </div>
            </div>

            <!-- ============ 图表区 ============ -->
            <div class="diag-charts">
                <div class="chart-box">
                    <div class="chart-caption">掌握度分布</div>
                    <div ref="levelChartRef" class="chart chart-level"></div>
                </div>
                <div class="chart-box">
                    <div class="chart-caption">学科正确率</div>
                    <div v-if="hasSubject" ref="subjectChartRef" class="chart chart-subject"></div>
                    <div v-else class="chart-hint">还没有足够数据</div>
                </div>
            </div>

            <div class="chart-box wide">
                <div class="chart-caption">
                    最近 {{ data.activity.windowDays }} 天学习节奏
                    <span class="caption-note">
                        活跃 {{ data.activity.activeDays }} 天 · 共 {{ data.activity.totalPractice }} 次
                        <template v-if="data.activity.looksLikeBurst"> · 偏突击式</template>
                    </span>
                </div>
                <div ref="activityChartRef" class="chart chart-activity"></div>
            </div>

            <!-- ============ 需要关注的题 ============ -->
            <div v-if="attentionItems.length" class="attention">
                <div class="attention-head">
                    现在最该练的 {{ attentionItems.length }} 道
                    <span class="attention-note">按「该先处理谁」排序</span>
                </div>
                <div class="attention-list">
                    <div v-for="item in attentionItems" :key="item.questionId" class="attention-item"
                        role="button" tabindex="0" @click="emit('openQuestion', item)"
                        @keyup.enter="emit('openQuestion', item)">
                        <span class="lv-tag" :style="{ background: levelColor(item.level) }">
                            {{ item.levelText }}
                        </span>
                        <span class="q-text">{{ item.questionText }}</span>
                        <span class="q-meta">
                            {{ item.attempts }} 次 · 对 {{ item.correctCount }} 次
                            <template v-if="item.overdueDays > 0"> · 欠复习 {{ item.overdueDays }} 天</template>
                        </span>
                        <el-icon class="q-go"><ArrowRight /></el-icon>
                    </div>
                </div>
            </div>

            <!-- ============ 建议 ============ -->
            <ul v-if="data.suggestions.length" class="diag-suggestions">
                <li v-for="(s, i) in data.suggestions" :key="i">{{ s }}</li>
            </ul>
        </template>
    </section>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { Loading, InfoFilled, ArrowRight, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
// 与项目其他地方保持一致：整体引入 `echarts`（myStats 主页面也是这么写的）。
// 不用 `echarts/core` 按需引入 —— 混用两套容易在打包后出现 "series type not exists"。
import * as echarts from 'echarts'
import {
    getDiagnose,
    buildReviewSheet,
    type DiagnosisResult,
    type DiagnosisItem,
    type MasteryLevel,
} from '@/api/userStats/userStats'

defineOptions({ name: 'DiagnosisPanel' })

const emit = defineEmits<{
    (e: 'practice'): void
    (e: 'openQuestion', item: DiagnosisItem): void
}>()

const loading = ref(true)
const data = ref<DiagnosisResult | null>(null)

/**
 * 复习卷导出状态（2026-10-26 v3）
 *
 * 单独一个 ref 而不是复用 `loading`：
 * 导出的 loading 只该转那个按钮，不能把整个面板变成骨架屏 ——
 * 用户点了"生成复习卷"却看不见自己的诊断结果，会以为页面刷没了。
 */
const exporting = ref(false)

/**
 * 生成并下载复习卷
 *
 * 后端返回的是 .docx 二进制流（不是 URL），所以这里走 blob 下载 ——
 * 与题库导出保持同一套做法，避免"先存服务器再取"的一次多余往返。
 */
async function exportReviewSheet() {
    if (exporting.value) return
    exporting.value = true
    try {
        // 题量按诊断出的需关注题目数自适应，但不低于 10、不超过 40：
        //   · < 10 道不成一份复习卷
        //   · > 40 道用户一次做不完，反而失去"按优先级"的意义
        const attention = data.value?.summary?.needsAttention || 0
        const limit = Math.min(40, Math.max(10, attention))

        const blob = await buildReviewSheet(limit)

        // 文件名带日期：用户可能一天生成多次，也可能隔天再生成，不覆盖
        const d = new Date()
        const stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `薄弱点复习卷_${stamp}.docx`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        // 立刻 revoke 会让部分浏览器下载失败，延后释放
        setTimeout(() => URL.revokeObjectURL(url), 4000)

        ElMessage.success('复习卷已生成，请查看下载文件')
    } catch (e: any) {
        // 后端在"没有练习记录"时返回 code=400 + 人话 msg，
        // 这里要把它透出来，而不是显示一个笼统的"导出失败"
        const msg =
            e?.response?.data?.msg ||
            e?.msg ||
            e?.message ||
            '生成失败，请稍后再试'
        ElMessage.warning(msg)
    } finally {
        exporting.value = false
    }
}

const levelChartRef = ref<HTMLDivElement>()
const subjectChartRef = ref<HTMLDivElement>()
const activityChartRef = ref<HTMLDivElement>()

let levelChart: echarts.ECharts | null = null
let subjectChart: echarts.ECharts | null = null
let activityChart: echarts.ECharts | null = null

/**
 * 档位配色
 *
 * 语义：红=反复错（最该管）、橙=该复习、黄=快到期、蓝=正常、绿=已掌握、灰=新题。
 * 与后端 `byLevel` 的键一一对应，不做映射表之外的发挥。
 */
const LEVEL_COLORS: Record<string, string> = {
    repeated_failure: '#e5534b',
    lapsing: '#e8833a',
    overdue: '#e8a33a',
    due_soon: '#d9c04a',
    on_track: '#4c8fd6',
    mastered: '#3fa06a',
    fresh: '#9aa4b2',
}

function levelColor(level: string): string {
    return LEVEL_COLORS[level] || '#9aa4b2'
}

function formatPct(v: number | null | undefined): string {
    if (v === null || v === undefined || Number.isNaN(v)) return '0'
    return Number(v).toFixed(1).replace(/\.0$/, '')
}

const hasSubject = computed(() => (data.value?.bySubject?.length || 0) > 0)

/**
 * 需要关注的题：优先取前四档（反复失守 / 记忆衰减 / 欠复习 / 快到期）
 *
 * 不直接用 `items` 全部：`items` 里还有 mastered / fresh，
 * 把它们混进"最该练"的列表会让建议失去指向性。
 */
const ATTENTION_LEVELS = new Set<MasteryLevel>(['repeated_failure', 'lapsing', 'overdue', 'due_soon'])

const attentionItems = computed<DiagnosisItem[]>(() => {
    const items = data.value?.items || []
    return items.filter((it) => ATTENTION_LEVELS.has(it.level)).slice(0, 8)
})

function renderLevelChart() {
    if (!levelChartRef.value || !data.value) return
    const byLevel = data.value.byLevel || {}
    const rows = Object.entries(byLevel)
        .filter(([, v]) => v.count > 0)
        .map(([key, v]) => ({
            name: v.text,
            value: v.count,
            itemStyle: { color: levelColor(key) },
        }))
    if (!rows.length) return

    if (!levelChart) levelChart = echarts.init(levelChartRef.value)
    levelChart.setOption(
        {
            tooltip: { trigger: 'item', formatter: '{b}：{c} 题（{d}%）' },
            legend: {
                type: 'scroll',
                bottom: 0,
                itemWidth: 9,
                itemHeight: 9,
                textStyle: { fontSize: 11, color: '#5a6472' },
            },
            series: [
                {
                    type: 'pie',
                    radius: ['46%', '68%'],
                    center: ['50%', '42%'],
                    avoidLabelOverlap: true,
                    label: { show: false },
                    labelLine: { show: false },
                    data: rows,
                },
            ],
        },
        true,
    )
}

function renderSubjectChart() {
    if (!subjectChartRef.value || !data.value) return
    const rows = (data.value.bySubject || []).slice(0, 8)
    if (!rows.length) return

    if (!subjectChart) subjectChart = echarts.init(subjectChartRef.value)
    // 横向条：科目名放左侧，长度=正确率（0~100）
    const names = rows.map((r) => r.subject || '未分类')
    const values = rows.map((r) => Number(r.accuracy) || 0)

    subjectChart.setOption(
        {
            grid: { left: 68, right: 40, top: 8, bottom: 8 },
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'shadow' },
                formatter: (params: any) => {
                    const p = Array.isArray(params) ? params[0] : params
                    const row = rows[p.dataIndex]
                    return `${row.subject}<br/>正确率 ${formatPct(row.accuracy)}%<br/>做过 ${row.questions} 题 / ${row.attempts} 次`
                },
            },
            xAxis: { type: 'value', max: 100, axisLabel: { fontSize: 10, color: '#8b95a3' }, splitLine: { lineStyle: { color: '#f0f2f5' } } },
            yAxis: {
                type: 'category',
                data: names,
                axisLabel: { fontSize: 11, color: '#5a6472' },
                axisTick: { show: false },
                axisLine: { show: false },
            },
            series: [
                {
                    type: 'bar',
                    data: values.map((v) => ({
                        value: v,
                        // 正确率低于 60% 标红，提醒这是短板
                        itemStyle: { color: v < 60 ? '#e5534b' : '#4c8fd6', borderRadius: [0, 4, 4, 0] },
                    })),
                    barMaxWidth: 16,
                    label: {
                        show: true,
                        position: 'right',
                        formatter: '{c}%',
                        fontSize: 10,
                        color: '#5a6472',
                    },
                },
            ],
        },
        true,
    )
}

function renderActivityChart() {
    if (!activityChartRef.value || !data.value) return
    const daily = data.value.activity?.daily || []
    if (!daily.length) return

    if (!activityChart) activityChart = echarts.init(activityChartRef.value)
    activityChart.setOption(
        {
            grid: { left: 40, right: 16, top: 16, bottom: 28 },
            tooltip: { trigger: 'axis' },
            xAxis: {
                type: 'category',
                data: daily.map((d) => String(d.date).slice(5)), // MM-DD
                axisLabel: { fontSize: 10, color: '#8b95a3' },
                axisTick: { show: false },
                axisLine: { lineStyle: { color: '#e6e9ee' } },
            },
            yAxis: {
                type: 'value',
                minInterval: 1,
                axisLabel: { fontSize: 10, color: '#8b95a3' },
                splitLine: { lineStyle: { color: '#f0f2f5' } },
            },
            series: [
                {
                    name: '练习次数',
                    type: 'line',
                    smooth: true,
                    symbolSize: 5,
                    data: daily.map((d) => d.practiceCount),
                    areaStyle: { color: 'rgba(76,143,214,0.12)' },
                    lineStyle: { color: '#4c8fd6', width: 2 },
                    itemStyle: { color: '#4c8fd6' },
                },
                {
                    name: '答对',
                    type: 'line',
                    smooth: true,
                    symbolSize: 4,
                    data: daily.map((d) => d.correctCount),
                    lineStyle: { color: '#3fa06a', width: 1.5, type: 'dashed' },
                    itemStyle: { color: '#3fa06a' },
                },
            ],
        },
        true,
    )
}

function renderAll() {
    nextTick(() => {
        renderLevelChart()
        renderSubjectChart()
        renderActivityChart()
    })
}

function disposeAll() {
    levelChart?.dispose()
    subjectChart?.dispose()
    activityChart?.dispose()
    levelChart = subjectChart = activityChart = null
}

function handleResize() {
    levelChart?.resize()
    subjectChart?.resize()
    activityChart?.resize()
}

async function load() {
    loading.value = true
    try {
        const res = await getDiagnose(40)
        data.value = (res as any)?.data ?? null
    } catch {
        // 诊断失败不该让整个统计页报错 —— 静默降级为"无数据"
        data.value = null
    } finally {
        loading.value = false
        renderAll()
    }
}

watch(data, () => renderAll())

onMounted(() => {
    load()
    window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    disposeAll()
})

defineExpose({ reload: load })
</script>

<style scoped>
.diag-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.diag-loading,
.diag-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 36px 16px;
    color: var(--el-text-color-secondary);
    font-size: 13px;
}

.diag-empty p {
    margin: 0;
    text-align: center;
    line-height: 1.7;
}

/* 结论句 */
.diag-headline {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 11px 14px;
    background: linear-gradient(90deg, #f2f7ff, #f8fbff);
    border-left: 3px solid var(--el-color-primary);
    border-radius: 6px;
    font-size: 13.5px;
    color: #2f3946;
    line-height: 1.6;
}

.headline-icon {
    flex: 0 0 auto;
    margin-top: 2px;
    color: var(--el-color-primary);
}

/* KPI */
.diag-kpis {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
}

.kpi {
    padding: 12px 14px;
    background: #fafbfc;
    border: 1px solid #eef0f3;
    border-radius: 8px;
}

.kpi.warn {
    background: #fff8f2;
    border-color: #fbe0c8;
}

.kpi-num {
    font-size: 22px;
    font-weight: 600;
    color: #2f3946;
    line-height: 1.2;
}

.kpi-num i {
    font-size: 12px;
    font-style: normal;
    margin-left: 1px;
    color: #8b95a3;
}

.kpi-label {
    margin-top: 3px;
    font-size: 12px;
    color: #8b95a3;
}

/* 图表 */
.diag-charts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}

.chart-box {
    min-width: 0;
}

.chart-box.wide {
    width: 100%;
}

.chart-caption {
    font-size: 12.5px;
    font-weight: 500;
    color: #5a6472;
    margin-bottom: 6px;
}

.caption-note {
    font-weight: 400;
    color: #9aa4b2;
    margin-left: 6px;
}

.chart {
    width: 100%;
}

.chart-level {
    height: 208px;
}

.chart-subject {
    height: 208px;
}

.chart-activity {
    height: 168px;
}

.chart-hint {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 208px;
    color: #9aa4b2;
    font-size: 12.5px;
}

/* 需要关注的题 */
.attention-head {
    font-size: 12.5px;
    font-weight: 500;
    color: #5a6472;
    margin-bottom: 8px;
}

.attention-note {
    font-weight: 400;
    color: #9aa4b2;
    margin-left: 6px;
}

.attention-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.attention-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 12px;
    background: #fafbfc;
    border: 1px solid #eef0f3;
    border-radius: 7px;
    cursor: pointer;
    transition: all 0.16s;
}

.attention-item:hover {
    background: #f2f7ff;
    border-color: #d6e6fb;
}

.lv-tag {
    flex: 0 0 auto;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    color: #fff;
    white-space: nowrap;
}

.q-text {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 13px;
    color: #2f3946;
}

.q-meta {
    flex: 0 0 auto;
    font-size: 11.5px;
    color: #8b95a3;
}

.q-go {
    flex: 0 0 auto;
    color: #b6bfcc;
    font-size: 13px;
}

/* 建议 */
.diag-suggestions {
    margin: 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.diag-suggestions li {
    font-size: 12.5px;
    color: #5a6472;
    line-height: 1.65;
}

@media (max-width: 900px) {
    .diag-kpis {
        grid-template-columns: repeat(2, 1fr);
    }

    .diag-charts {
        grid-template-columns: 1fr;
    }
}
</style>
