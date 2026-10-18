<template>
    <div class="my-stats" v-loading="loading">
        <!--
          标题行已整块移除
          ==========================================================================
          用户 2026-10-18：「学习统计那边『我的学习 · 学习统计』+『数据来自你的刷题、
          错题、斩题与收藏记录』这一行去掉，跟前面几个模块一样，把后面的副标题
          改到第一行的『我的学习 · 学习统计』就行」。

          所以顶栏（`layout/front.vue`）现在显示：
            `我的学习 · 学习统计  数据来自你的刷题、错题、斩题与收藏记录`
          内容区直接从内容开始，不再占一行。
        -->

        <!-- ============ 零数据：给出引导而不是一片空图 ============ -->
        <div v-if="!loading && isEmpty" class="onboarding">
            <div class="onboarding-mark" aria-hidden="true">
                <el-icon :size="26">
                    <TrendCharts />
                </el-icon>
            </div>
            <h3 class="onboarding-title">还没有学习记录</h3>
            <p class="onboarding-text">
                去「题库练习」刷几道题吧。之后这里会记录你的正确率、错题分布、斩题进度和学习趋势。
            </p>
            <el-button type="primary" @click="goPractice">去题库练习</el-button>
        </div>

        <template v-else>
            <!-- ============ 学习总览 ============ -->
            <section class="panel overview-panel">
                <div class="panel-head">
                    <h3 class="panel-title">学习总览</h3>
                    <span class="panel-sub">累计数据</span>
                </div>

                <div class="overview-body">
                    <div class="rate-block">
                        <div class="rate-ring-wrap">
                            <svg class="rate-ring" viewBox="0 0 80 80" role="img" aria-label="答题正确率">
                                <circle class="ring-track" cx="40" cy="40" r="34" />
                                <circle class="ring-value" cx="40" cy="40" r="34" :stroke="rateColor"
                                    :stroke-dasharray="`${ringDash} ${ringLength}`" />
                            </svg>
                            <span class="rate-number" :style="{ color: rateColor }">{{ formatRate }}%</span>
                        </div>
                        <div class="rate-text">
                            <div class="rate-title">答题正确率</div>
                            <div class="rate-sub">
                                共作答 {{ overview.totalPracticeCount }} 次 · 错 {{ overview.totalPracticeCount - correctCount }} 次
                            </div>
                        </div>
                    </div>

                    <div class="mini-metrics">
                        <div class="mini" v-for="m in miniMetrics" :key="m.label">
                            <div class="mini-label">
                                <span class="dot" :style="{ background: m.color }"></span>
                                {{ m.label }}
                            </div>
                            <div class="mini-value">{{ m.value }}</div>
                            <div class="mini-hint">{{ m.hint }}</div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- ============ 趋势 + 科目分布 ============ -->
            <section class="chart-row">
                <div class="panel">
                    <div class="panel-head">
                        <h3 class="panel-title">学习趋势</h3>
                        <span class="panel-sub">最近 7 天 · 练习总量 / 答对 / 答错 / 斩题</span>
                    </div>
                    <div ref="trendChartRef" class="chart chart-main"></div>
                </div>
                <div class="panel">
                    <div class="panel-head">
                        <h3 class="panel-title">科目分布</h3>
                        <span class="panel-sub">按收藏题库</span>
                    </div>
                    <div class="subject-body">
                        <div v-if="subjectLegend.length" ref="subjectChartRef" class="chart chart-subject"></div>
                        <div v-else class="subject-empty">还没有收藏题库</div>
                        <ul v-if="subjectLegend.length" class="subject-legend">
                            <li v-for="s in subjectLegend" :key="s.name">
                                <i :style="{ background: s.color }"></i>
                                <span class="subj-name">{{ s.name }}</span>
                                <span class="subj-count">{{ s.value }}</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </section>

            <!-- ============ 错题诊断（合并原来两张卡） ============ -->
            <section class="panel">
                <div class="panel-head">
                    <h3 class="panel-title">错题诊断</h3>
                    <span class="panel-sub">掌握进度 / 难度分布 / 高频错题</span>
                </div>

                <div class="diag-grid">
                    <div class="diag-col">
                        <div class="diag-label">掌握进度</div>
                        <div class="diag-big">
                            <span class="diag-num">{{ errorAnalysis.mastered }}</span>
                            <span class="diag-total">/ {{ errorAnalysis.totalErrors }} 题</span>
                        </div>
                        <div class="bar-track">
                            <div class="bar-fill" :style="{ width: `${Math.min(errorAnalysis.masterRate, 100)}%` }"></div>
                        </div>
                        <div class="diag-hint">已掌握 {{ formatRateOf(errorAnalysis.masterRate) }}%</div>
                    </div>

                    <div class="diag-col">
                        <div class="diag-label">按难度</div>
                        <div ref="difficultyChartRef" class="chart chart-mini"></div>
                    </div>

                    <div class="diag-col">
                        <div class="diag-label">
                            易错 TOP 5
                            <span class="diag-label-hint">点击可定位到错题</span>
                        </div>
                        <div v-if="errorAnalysis.topErrors.length" class="error-list">
                            <div v-for="(item, idx) in errorAnalysis.topErrors" :key="item.questionId"
                                class="error-item" role="button" tabindex="0"
                                @click="goWrongQuestion(item)" @keyup.enter="goWrongQuestion(item)">
                                <span class="error-rank">{{ idx + 1 }}</span>
                                <span class="error-text">{{ item.questionText }}</span>
                                <span class="error-count">错 {{ item.errorCount }} 次</span>
                                <el-icon class="error-go"><ArrowRight /></el-icon>
                            </div>
                        </div>
                        <div v-else class="diag-hint empty">暂无错题记录</div>
                    </div>
                </div>
            </section>

            <!-- ============ 我的积累 + 里程碑（原来底部重复的成长记录） ============ -->
            <section class="panel accum-panel">
                <div class="accum-left">
                    <span class="accum-title">我的积累</span>
                    <span class="chip" v-for="c in accumChips" :key="c.label">
                        {{ c.label }} <b>{{ c.value }}</b>
                    </span>
                </div>
                <div class="accum-right" v-if="nextMilestone">
                    <span class="accum-hint">
                        下一个里程碑：{{ nextMilestone.title }}（{{ nextMilestone.current }} / {{ nextMilestone.count }}）
                    </span>
                    <div class="bar-track slim">
                        <div class="bar-fill amber"
                            :style="{ width: `${Math.min(nextMilestone.current / nextMilestone.count * 100, 100)}%` }"></div>
                    </div>
                </div>
                <div class="accum-right" v-else>
                    <span class="accum-hint">全部里程碑已达成</span>
                </div>
            </section>
        </template>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MyStats' })
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import useTopbarStore from '@/store/modules/topbar'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { TrendCharts, ArrowRight } from '@element-plus/icons-vue'
import {
    getOverview,
    getBySubject,
    getTrend,
    getErrorAnalysis,
    getGrowth
} from '@/api/userStats/userStats'
import type {
    OverviewStats,
    SubjectStat,
    TrendItem,
    ErrorAnalysis,
    GrowthRecord
} from '@/api/userStats/userStats'

const router = useRouter()
const loading = ref(true)

// 总览数据
const overview = ref<OverviewStats>({
    totalQuestions: 0,
    totalBanks: 0,
    totalErrors: 0,
    totalMarked: 0,
    totalMastered: 0,
    totalFavoriteNotes: 0,
    totalPracticeCount: 0,
    correctRate: 0,
    bankStudyCount: 0
})

// 科目统计
const subjectStats = ref<SubjectStat[]>([])
// 趋势数据
const trendData = ref<TrendItem[]>([])
// 错题分析
const errorAnalysis = ref<ErrorAnalysis>({
    totalErrors: 0,
    activeErrors: 0,
    mastered: 0,
    masterRate: 0,
    byDifficulty: [],
    topErrors: []
})
// 成长记录
const growth = ref<GrowthRecord>({
    joinDate: '',
    studyDays: 0,
    consecutiveDays: 0,
    totalBanks: 0,
    totalQuestions: 0,
    totalNotes: 0,
    milestones: []
})

/** 全部指标为 0 —— 新用户，走引导态（不渲染空图表） */
const isEmpty = computed(() => {
    const o = overview.value
    return !o.totalPracticeCount && !o.totalErrors && !o.totalMarked
        && !o.totalBanks && !o.totalQuestions && !o.totalFavoriteNotes
})

/** 正确次数 = 总作答 - 错误次数（后端只给正确率与总次数） */
const correctCount = computed(() => {
    const total = overview.value.totalPracticeCount || 0
    return Math.round(total * (overview.value.correctRate || 0) / 100)
})

const formatRate = computed(() => Number(overview.value.correctRate || 0).toFixed(1).replace(/\.0$/, ''))
const formatRateOf = (v: number) => Number(v || 0).toFixed(1).replace(/\.0$/, '')

/** 正确率配色：越低越需要提醒 */
const rateColor = computed(() => {
    const r = overview.value.correctRate || 0
    if (!overview.value.totalPracticeCount) return '#c0c4cc'
    if (r >= 80) return '#67c23a'
    if (r >= 60) return '#409eff'
    if (r >= 40) return '#e6a23c'
    return '#f56c6c'
})

const ringLength = 2 * Math.PI * 34
const ringDash = computed(() => {
    const r = Math.min(Math.max(overview.value.correctRate || 0, 0), 100)
    return (r / 100) * ringLength
})

/** 近 7 天各项新增，用于给小指标一句「趋势」 */
const trendSum = computed(() => {
    const s = { errorCount: 0, correctCount: 0, markedCount: 0, practiceCount: 0 }
    trendData.value.forEach(d => {
        s.errorCount += d.errorCount || 0
        s.correctCount += d.correctCount || 0
        s.markedCount += d.markedCount || 0
        s.practiceCount += d.practiceCount || 0
    })
    return s
})

const miniMetrics = computed(() => [
    {
        label: '待消灭错题',
        value: overview.value.totalErrors,
        // errorCount 现在统计的是「答错次数」（含重复做错），语义比原来的「新增错题数」更准
        hint: trendSum.value.errorCount ? `近 7 天答错 ${trendSum.value.errorCount} 次` : '近 7 天无答错',
        color: '#f56c6c'
    },
    {
        label: '已斩题',
        value: overview.value.totalMarked,
        hint: trendSum.value.markedCount ? `近 7 天 +${trendSum.value.markedCount}` : '近 7 天无新增',
        color: '#e6a23c'
    },
    {
        label: '已掌握错题',
        value: overview.value.totalMastered,
        hint: `掌握率 ${formatRateOf(errorAnalysis.value.masterRate)}%`,
        color: '#67c23a'
    }
])

const accumChips = computed(() => [
    { label: '收藏题库', value: growth.value.totalBanks || 0 },
    { label: '收藏题目', value: growth.value.totalQuestions || 0 },
    { label: '笔记', value: growth.value.totalNotes || 0 },
    { label: '连续学习', value: `${growth.value.consecutiveDays || 0} 天` },
    { label: '学习天数', value: `${growth.value.studyDays || 0} 天` }
])

/**
 * 里程碑取「第一个未达成的」，并换算当前进度
 * type -> 当前值来源：bank=收藏题库 / marked=斩题 / mastered=已掌握错题
 */
const nextMilestone = computed(() => {
    const list = growth.value.milestones || []
    const next = list.find(m => !m.achieved)
    if (!next) return null
    const currentMap: Record<string, number> = {
        bank: growth.value.totalBanks || 0,
        marked: overview.value.totalMarked || 0,
        mastered: overview.value.totalMastered || 0
    }
    return { ...next, current: currentMap[next.type] ?? 0 }
})

// 图表引用
const trendChartRef = ref<HTMLElement | null>(null)
const subjectChartRef = ref<HTMLElement | null>(null)
const difficultyChartRef = ref<HTMLElement | null>(null)

let trendChart: echarts.ECharts | null = null
let subjectChart: echarts.ECharts | null = null
let difficultyChart: echarts.ECharts | null = null

const difficultyMap: Record<number, string> = { 1: '简单', 2: '中等', 3: '困难' }

function disposeCharts() {
    trendChart?.dispose(); trendChart = null
    subjectChart?.dispose(); subjectChart = null
    difficultyChart?.dispose(); difficultyChart = null
}

/** 趋势折线：练习总量 / 答对 / 答错 / 斩题（全部来自答题流水，不再是收藏记录数） */
function initTrendChart(data: TrendItem[]) {
    if (!trendChartRef.value) return
    trendChart?.dispose()
    trendChart = echarts.init(trendChartRef.value)
    const line = (name: string, color: string, values: number[], withArea = false) => ({
        name,
        type: 'line' as const,
        smooth: true,
        symbolSize: 6,
        data: values,
        lineStyle: { color, width: 2 },
        itemStyle: { color },
        // 只给「练习总量」铺面积，四条线都铺会糊成一片
        areaStyle: withArea
            ? {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: hexToRgba(color, 0.22) },
                    { offset: 1, color: hexToRgba(color, 0.02) }
                ])
            }
            : undefined
    })
    trendChart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['练习总量', '答对次数', '答错次数', '斩题'], bottom: 0, itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12 } },
        grid: { left: 4, right: 12, bottom: 34, top: 12, containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: data.map(d => (d.date || '').slice(5)),
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            splitLine: { lineStyle: { color: '#f3f4f6' } },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        series: [
            line('练习总量', '#409eff', data.map(d => d.practiceCount), true),
            line('答对次数', '#67c23a', data.map(d => d.correctCount)),
            line('答错次数', '#f56c6c', data.map(d => d.errorCount)),
            line('斩题', '#e6a23c', data.map(d => d.markedCount))
        ]
    })
}

/** 科目分布色板（圆环与图例共用，保证颜色一一对应） */
const SUBJECT_PALETTE = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b8afb']

/** 科目分布图例：自己渲染成下方列表，不用 echarts 图例 */
const subjectLegend = ref<{ name: string; value: number; color: string }[]>([])

/** 科目分布环形图 —— 圆环居中，图例放到圆环下方自动换行
 *
 * 原先用 echarts 自带 legend（`orient: vertical` + `right: 0`），而圆环固定在左侧 34% 处，
 * 且 radius 是按 min(宽,高)/2 算的（高度恒为 232，宽度却随卡片伸缩）——
 * 卡片一窄圆环就相对变"胖"，右缘直接顶到图例色点上，两者挤在一起。
 * 现在横纵不再争空间：圆环独占一行，图例在下面 flex-wrap。
 */
async function initSubjectChart(data: SubjectStat[]) {
    // 只保留真正有题库的科目：bankCount=0 会在饼图里生成 0 值扇区，图例也是噪音
    const list = (data || []).filter(s => (s.bankCount || 0) > 0)

    subjectLegend.value = list.map((s, i) => ({
        name: s.subject || '未分类',
        value: s.bankCount || 0,
        color: SUBJECT_PALETTE[i % SUBJECT_PALETTE.length]
    }))

    subjectChart?.dispose()
    subjectChart = null

    // 一个题库都没收藏时只显示空状态，连空圆环都不画
    if (!list.length) return
    await nextTick()  // 等 v-if 把图表容器渲染出来
    if (!subjectChartRef.value) return

    subjectChart = echarts.init(subjectChartRef.value)
    subjectChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} 个题库 ({d}%)' },
        legend: { show: false },
        color: SUBJECT_PALETTE,
        series: [{
            type: 'pie',
            radius: ['58%', '80%'],
            center: ['50%', '50%'],
            avoidLabelOverlap: true,
            itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
            label: { show: false },
            emphasis: { scale: true, scaleSize: 4, label: { show: false } },
            data: list.map(s => ({ value: s.bankCount, name: s.subject || '未分类' }))
        }]
    })
}

/** 难度分布柱状图 */
function initDifficultyChart(data: ErrorAnalysis['byDifficulty']) {
    if (!difficultyChartRef.value) return
    difficultyChart?.dispose()
    difficultyChart = echarts.init(difficultyChartRef.value)

    const sorted = [...(data || [])].sort((a, b) => a.difficulty - b.difficulty)
    const categories = sorted.map(d => difficultyMap[d.difficulty] || `难度${d.difficulty}`)
    const counts = sorted.map(d => d.count)
    const colorMap: Record<number, string> = { 1: '#67c23a', 2: '#e6a23c', 3: '#f56c6c' }

    difficultyChart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: 4, right: 8, bottom: 4, top: 16, containLabel: true },
        xAxis: {
            type: 'category',
            data: categories.length ? categories : ['暂无数据'],
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisTick: { show: false },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            splitLine: { lineStyle: { color: '#f3f4f6' } },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        series: [{
            type: 'bar',
            barWidth: '42%',
            data: counts.length
                ? sorted.map(d => ({ value: d.count, itemStyle: { color: colorMap[d.difficulty] || '#909399' } }))
                : [{ value: 0, itemStyle: { color: '#e5e7eb' } }],
            itemStyle: { borderRadius: [4, 4, 0, 0] }
        }]
    })
}

/** #409eff -> rgba(64,158,255,alpha) */
function hexToRgba(hex: string, alpha: number) {
    const h = hex.replace('#', '')
    const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

function handleResize() {
    trendChart?.resize()
    subjectChart?.resize()
    difficultyChart?.resize()
}

async function fetchAll() {
    loading.value = true
    try {
        const [overviewRes, subjectRes, trendRes, errorRes, growthRes] = await Promise.all([
            getOverview(),
            getBySubject(),
            getTrend(7),
            getErrorAnalysis(),
            getGrowth()
        ])

        if (overviewRes.code === 200 && overviewRes.data) overview.value = { ...overview.value, ...overviewRes.data }
        if (subjectRes.code === 200 && subjectRes.data) subjectStats.value = subjectRes.data
        if (trendRes.code === 200 && trendRes.data) trendData.value = trendRes.data
        if (errorRes.code === 200 && errorRes.data) errorAnalysis.value = { ...errorAnalysis.value, ...errorRes.data }
        if (growthRes.code === 200 && growthRes.data) growth.value = { ...growth.value, ...growthRes.data }

        await nextTick()
        // 零数据不渲染空图表，避免整屏「0」
        if (!isEmpty.value) {
            initTrendChart(trendData.value)
            void initSubjectChart(subjectStats.value)
            initDifficultyChart(errorAnalysis.value.byDifficulty)
        }
    } catch (e) {
        console.warn('用户统计接口异常:', e)
    } finally {
        loading.value = false
    }
}

const goPractice = () => router.push('/front/questionPractice')

/** 点击易错题 → 跳到「我的错题」并自动定位、打开该题卡片 */
const goWrongQuestion = (item: { questionId: number | string }) => {
    if (!item?.questionId) return
    router.push({
        path: '/front/myQuestion/wrongQuestion',
        query: { questionId: String(item.questionId), from: 'stats' }
    })
}

const topbarStore = useTopbarStore()

onMounted(async () => {
    /*
     * 把原来内容区那行副标题推到顶栏
     * 用户 2026-10-18：内容区不再有标题行，说明文字并到顶栏那一行。
     */
    topbarStore.setCount('数据来自你的刷题、错题、斩题与收藏记录')
    await nextTick()
    window.addEventListener('resize', handleResize)
    setTimeout(fetchAll, 100)
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    disposeCharts()
    topbarStore.clear()
})
</script>

<style scoped lang="scss">
.my-stats {
    padding: 0 16px;

    .page-header {
        display: flex;
        align-items: baseline;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 18px;
    }

    .page-title {
        /* 与「我的学习」下其它子页统一：16px / 600（原来 22px/700 明显过重） */
        font-size: 16px;
        font-weight: 600;
        letter-spacing: -0.01em;
        color: var(--os-text, #1f2937);
        margin: 0;
    }

    .title-sep {
        margin: 0 6px;
        color: var(--os-text-4, #9ca3af);
        font-weight: 400;
    }

    .page-sub {
        font-size: 13px;
        color: #9ca3af;
    }

    /* 通用面板 */
    .panel {
        background: #fff;
        border-radius: 12px;
        border: 1px solid #f3f4f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        padding: 18px;
        margin-bottom: 16px;
    }

    .panel-head {
        display: flex;
        align-items: baseline;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }

    .panel-title {
        font-size: 16px;
        font-weight: 600;
        color: #1f2937;
        margin: 0;
    }

    .panel-sub {
        font-size: 12px;
        color: #9ca3af;
    }

    /* ===== 零数据引导 ===== */
    .onboarding {
        background: #fff;
        border-radius: 12px;
        border: 1px solid #f3f4f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        padding: 56px 24px;
        text-align: center;

        .onboarding-mark {
            width: 56px;
            height: 56px;
            border-radius: 50%;
            background: #eff6ff;
            color: #409eff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 16px;
        }

        .onboarding-title {
            font-size: 17px;
            font-weight: 600;
            color: #1f2937;
            margin: 0 0 8px;
        }

        .onboarding-text {
            font-size: 13px;
            color: #6b7280;
            line-height: 1.7;
            margin: 0 auto 20px;
            max-width: 460px;
        }
    }

    /* ===== 学习总览 ===== */
    .overview-body {
        display: grid;
        grid-template-columns: minmax(0, 260px) minmax(0, 1fr);
        gap: 24px;
        align-items: center;

        @media (max-width: 768px) {
            grid-template-columns: 1fr;
            gap: 18px;
        }
    }

    .rate-block {
        display: flex;
        align-items: center;
        gap: 16px;
        padding-right: 24px;
        border-right: 1px solid #f3f4f6;

        @media (max-width: 768px) {
            border-right: none;
            padding-right: 0;
        }
    }

    .rate-ring-wrap {
        position: relative;
        width: 92px;
        height: 92px;
        flex-shrink: 0;
    }

    .rate-ring {
        width: 92px;
        height: 92px;
        transform: rotate(-90deg);

        .ring-track {
            fill: none;
            stroke: #f3f4f6;
            stroke-width: 8;
        }

        .ring-value {
            fill: none;
            stroke-width: 8;
            stroke-linecap: round;
            transition: stroke-dasharray 0.6s ease;
        }
    }

    .rate-number {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        font-weight: 700;
    }

    .rate-title {
        font-size: 14px;
        font-weight: 600;
        color: #1f2937;
    }

    .rate-sub {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 6px;
        line-height: 1.6;
    }

    .mini-metrics {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;

        @media (max-width: 560px) {
            grid-template-columns: 1fr;
        }
    }

    .mini {
        background: #f9fafb;
        border-radius: 10px;
        padding: 14px 16px;
    }

    .mini-label {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #6b7280;

        .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            flex-shrink: 0;
        }
    }

    .mini-value {
        font-size: 26px;
        font-weight: 700;
        color: #1f2937;
        line-height: 1.25;
        margin-top: 6px;
    }

    .mini-hint {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 2px;
    }

    /* ===== 图表区：趋势 2 : 科目 1 ===== */
    .chart-row {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
        gap: 16px;

        .panel {
            margin-bottom: 16px;
        }

        @media (max-width: 992px) {
            grid-template-columns: 1fr;
        }
    }

    .chart {
        width: 100%;
    }

    .chart-main {
        height: 232px;
    }

    .chart-mini {
        height: 150px;
    }

    /* ===== 科目分布：圆环独占一行，图例在下方自动换行（不再与圆环抢横向空间） ===== */
    .subject-body {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 6px;
        min-height: 232px;
    }

    .chart-subject {
        height: 176px;
    }

    .subject-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 12px;
        max-height: 80px;
        overflow-y: auto;
        margin: 0;
        padding: 0;
        list-style: none;

        li {
            display: flex;
            align-items: center;
            gap: 5px;
            min-width: 0;
            font-size: 12px;
            line-height: 18px;
            color: #6b7280;
        }

        i {
            flex: none;
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }

        .subj-name {
            max-width: 84px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .subj-count {
            flex: none;
            color: #9ca3af;
        }
    }

    .subject-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        color: #9ca3af;
    }

    /* ===== 错题诊断 ===== */
    .diag-grid {
        display: grid;
        grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr);
        gap: 24px;

        @media (max-width: 992px) {
            grid-template-columns: 1fr;
            gap: 18px;
        }
    }

    .diag-col {
        min-width: 0;
    }

    .diag-label {
        font-size: 12px;
        color: #6b7280;
        margin-bottom: 10px;

        .diag-label-hint {
            margin-left: 6px;
            font-size: 11px;
            color: #c0c4cc;
        }
    }

    .diag-big {
        display: flex;
        align-items: baseline;
        gap: 4px;
        margin-bottom: 10px;

        .diag-num {
            font-size: 24px;
            font-weight: 700;
            color: #1f2937;
        }

        .diag-total {
            font-size: 12px;
            color: #9ca3af;
        }
    }

    .diag-hint {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 8px;

        &.empty {
            padding: 24px 0;
            text-align: center;
            color: #c0c4cc;
        }
    }

    .bar-track {
        height: 8px;
        border-radius: 4px;
        background: #f3f4f6;
        overflow: hidden;

        &.slim {
            height: 4px;
            margin-top: 8px;
        }
    }

    .bar-fill {
        height: 100%;
        border-radius: 4px;
        background: #67c23a;
        transition: width 0.6s ease;

        &.amber {
            background: #e6a23c;
        }
    }

    .error-list {
        .error-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 8px;
            margin: 0 -8px;
            border-radius: 6px;
            border-bottom: 1px solid #f6f7f9;
            cursor: pointer;
            transition: background 0.2s ease;

            &:hover {
                background: #f5f9ff;

                .error-go {
                    color: #409eff;
                    transform: translateX(2px);
                }
            }

            &:focus-visible {
                outline: 2px solid #409eff;
                outline-offset: 2px;
            }

            &:last-child {
                border-bottom: none;
            }
        }

        .error-go {
            color: #c0c4cc;
            font-size: 13px;
            flex-shrink: 0;
            transition: color 0.2s ease, transform 0.2s ease;
        }

        .error-rank {
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #fef0f0;
            color: #f56c6c;
            font-size: 12px;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .error-text {
            flex: 1;
            min-width: 0;
            font-size: 13px;
            color: #374151;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .error-count {
            font-size: 12px;
            color: #f56c6c;
            flex-shrink: 0;
        }
    }

    /* ===== 我的积累 ===== */
    .accum-panel {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
        flex-wrap: wrap;
    }

    .accum-left {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
    }

    .accum-title {
        font-size: 14px;
        font-weight: 600;
        color: #1f2937;
        margin-right: 4px;
    }

    .chip {
        font-size: 12px;
        color: #6b7280;
        background: #f9fafb;
        border-radius: 999px;
        padding: 5px 12px;

        b {
            font-weight: 600;
            color: #1f2937;
            margin-left: 2px;
        }
    }

    .accum-right {
        min-width: 220px;
        flex: 1;
        max-width: 340px;
    }

    .accum-hint {
        font-size: 12px;
        color: #9ca3af;
    }
}
</style>
