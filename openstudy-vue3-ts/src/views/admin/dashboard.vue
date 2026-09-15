<template>
    <div class="admin-dashboard">
        <!-- 页头 -->
        <div class="page-header">
            <h2 class="page-title">数据概览</h2>
            <span class="page-sub">全站用户 / 题库 / 题目 / 笔记的累计统计</span>
        </div>

        <!-- ============ 统计卡片 ============ -->
        <div class="stat-cards">
            <div class="panel stat-panel" v-for="card in statCards" :key="card.label">
                <div class="stat-icon" :style="{ background: card.gradient }">
                    <el-icon :size="26">
                        <component :is="card.icon" />
                    </el-icon>
                </div>
                <div class="stat-content">
                    <div class="stat-value">{{ card.value }}</div>
                    <div class="stat-label">{{ card.label }}</div>
                </div>
            </div>
        </div>

        <!-- ============ 分类统计 + 最近活动 ============ -->
        <div class="grid-row">
            <div class="panel">
                <div class="panel-head">
                    <h3 class="panel-title">题库分类统计</h3>
                    <span class="panel-sub">按科目</span>
                </div>
                <div class="category-body">
                    <div v-if="categoryLegend.length" ref="categoryChartRef" class="chart chart-pie"></div>
                    <div v-else class="chart-empty">暂无题库数据</div>
                    <ul v-if="categoryLegend.length" class="pie-legend">
                        <li v-for="c in categoryLegend" :key="c.name">
                            <i :style="{ background: c.color }"></i>
                            <span class="legend-name">{{ c.name }}</span>
                            <span class="legend-count">{{ c.value }}</span>
                        </li>
                    </ul>
                </div>
            </div>

            <div class="panel">
                <div class="panel-head">
                    <h3 class="panel-title">最近活动</h3>
                    <span class="panel-sub">题库 / 题目 / 笔记动态</span>
                </div>
                <div v-if="recentActivities.length" class="activity-list">
                    <div v-for="(item, index) in recentActivities" :key="index" class="activity-item">
                        <div class="activity-icon" :class="item.type">
                            <el-icon :size="16">
                                <component :is="item.icon" />
                            </el-icon>
                        </div>
                        <div class="activity-content">
                            <div class="activity-text">{{ item.text }}</div>
                            <div class="activity-time">{{ item.time }}</div>
                        </div>
                    </div>
                </div>
                <div v-else class="chart-empty">暂无活动记录</div>
            </div>
        </div>

        <!-- ============ 用户增长 + 系统信息 ============ -->
        <div class="grid-row">
            <div class="panel">
                <div class="panel-head">
                    <h3 class="panel-title">用户增长趋势</h3>
                    <span class="panel-sub">最近 7 天新增注册</span>
                </div>
                <div v-if="!growthEmpty" ref="userGrowthChartRef" class="chart chart-main"></div>
                <div v-else class="growth-empty">
                    <div class="growth-empty-mark">
                        <el-icon :size="22">
                            <User />
                        </el-icon>
                    </div>
                    <span>近 7 天没有新增用户注册</span>
                </div>
            </div>

            <div class="panel">
                <div class="panel-head">
                    <h3 class="panel-title">系统信息</h3>
                    <span class="panel-sub">运行环境</span>
                </div>
                <div class="system-info">
                    <div class="info-item">
                        <span class="info-label">系统名称</span>
                        <span class="info-value">OpenStudy 学习平台</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">后端框架</span>
                        <span class="info-value">FastAPI 0.115.6 (Python)</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">前端框架</span>
                        <span class="info-value">Vue3 + Element Plus</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">数据库</span>
                        <span class="info-value">MySQL</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">当前时间</span>
                        <span class="info-value">{{ currentTime }}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'AdminDashboard' })
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { User, Collection, EditPen, Notebook, Document } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { getDashboardStats, getDashboardRecent } from '@/api/dashboard'

// ---------------- 统计卡片 ----------------
const rawStats = ref({
    userCount: 0,
    questionBankCount: 0,
    questionCount: 0,
    noteCount: 0
})

const statCards = computed(() => [
    {
        label: '用户总数',
        value: rawStats.value.userCount,
        icon: User,
        gradient: 'linear-gradient(135deg, #6366f1, #8b8cf9)'
    },
    {
        label: '题库总数',
        value: rawStats.value.questionBankCount,
        icon: Collection,
        gradient: 'linear-gradient(135deg, #059669, #34d399)'
    },
    {
        label: '题目总数',
        value: rawStats.value.questionCount,
        icon: EditPen,
        gradient: 'linear-gradient(135deg, #d97706, #fbbf24)'
    },
    {
        label: '笔记总数',
        value: rawStats.value.noteCount,
        icon: Notebook,
        gradient: 'linear-gradient(135deg, #3b82f6, #60a5fa)'
    }
])

// ---------------- 最近活动 ----------------
const recentActivities = ref<{ type: string; icon: any; text: string; time: string }[]>([])

const ACTIVITY_ICON: Record<string, any> = {
    bank: Collection,
    question: EditPen,
    note: Notebook,
    user: User
}

/** 后端 recent 返回 {type,id,title,subject?,createTime}，这里拼成可读文案 */
function normalizeActivity(item: any) {
    const type = item.type || 'bank'
    const title = (item.title || '').trim()
    const textMap: Record<string, string> = {
        bank: `创建了题库《${title || '未命名题库'}》`,
        question: `新增题目「${title.slice(0, 30) || '未命名题目'}」`,
        note: `发布了笔记《${title || '未命名笔记'}》`
    }
    return {
        type,
        icon: ACTIVITY_ICON[type] || Document,
        text: textMap[type] || title,
        time: formatTime(item.createTime || item.time)
    }
}

/** ISO 时间 -> MM-DD HH:mm */
function formatTime(iso: string) {
    if (!iso) return ''
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ---------------- 当前时间 ----------------
const currentTime = ref('')
let timeTimer: ReturnType<typeof setInterval> | null = null

function updateTime() {
    const now = new Date()
    const pad = (n: number) => String(n).padStart(2, '0')
    currentTime.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

// ---------------- 图表 ----------------
const categoryChartRef = ref<HTMLElement | null>(null)
const userGrowthChartRef = ref<HTMLElement | null>(null)
let categoryChart: echarts.ECharts | null = null
let userGrowthChart: echarts.ECharts | null = null

/** 与学习统计页「科目分布」共用的色板，视觉统一 */
const SUBJECT_PALETTE = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9b8afb']

/** 饼图图例：自己渲染成下方 flex-wrap 列表，与圆环不再抢横向空间 */
const categoryLegend = ref<{ name: string; value: number; color: string }[]>([])

/** 近 7 天无新增用户时不渲染假折线，改走空态 */
const growthEmpty = ref(false)

function initCategoryChart(data: { value: number; name: string }[]) {
    if (!categoryChartRef.value) return
    categoryChart?.dispose()
    categoryChart = echarts.init(categoryChartRef.value)
    categoryChart.setOption({
        tooltip: { trigger: 'item', formatter: '{b}: {c} 个题库 ({d}%)' },
        legend: { show: false },
        color: SUBJECT_PALETTE,
        series: [{
            type: 'pie',
            radius: ['56%', '78%'],
            center: ['50%', '50%'],
            avoidLabelOverlap: true,
            itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
            label: { show: false },
            emphasis: { scale: true, scaleSize: 4, label: { show: false } },
            data
        }]
    })
}

/** 后端只返回「有新增」的日期，这里补齐近 7 天（缺的填 0），X 轴才连续 */
function fillLast7Days(data: { date: string; count: number }[]) {
    const countMap = new Map<string, number>()
    for (const d of data || []) {
        const key = normalizeDateKey(d.date)
        if (key) countMap.set(key, Number(d.count) || 0)
    }
    const dates: string[] = []
    const counts: number[] = []
    const pad = (n: number) => String(n).padStart(2, '0')
    for (let i = 6; i >= 0; i--) {
        const d = new Date(Date.now() - i * 86400000)
        const key = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
        dates.push(key.slice(5))
        counts.push(countMap.get(key) || 0)
    }
    return { dates, counts }
}

/** 兼容 "2026-09-12" / "09-12" 两种 key */
function normalizeDateKey(date: string) {
    if (!date) return ''
    return date.length >= 10 ? date.slice(0, 10) : `2026-${date}`
}

function initUserGrowthChart(dates: string[], counts: number[]) {
    if (!userGrowthChartRef.value) return
    userGrowthChart?.dispose()
    userGrowthChart = echarts.init(userGrowthChartRef.value)
    userGrowthChart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['新增用户'], bottom: 0, itemWidth: 12, itemHeight: 12, textStyle: { fontSize: 12 } },
        grid: { left: 4, right: 12, bottom: 34, top: 12, containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: dates,
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            splitLine: { lineStyle: { color: '#f3f4f6' } },
            axisLabel: { color: '#9ca3af', fontSize: 11 }
        },
        series: [{
            name: '新增用户',
            type: 'line',
            smooth: true,
            symbolSize: 6,
            data: counts,
            lineStyle: { color: '#409eff', width: 2 },
            itemStyle: { color: '#409eff' },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(64, 158, 255, 0.22)' },
                    { offset: 1, color: 'rgba(64, 158, 255, 0.02)' }
                ])
            }
        }]
    })
}

function handleResize() {
    categoryChart?.resize()
    userGrowthChart?.resize()
}

// ---------------- 数据获取 ----------------
async function fetchStats() {
    try {
        const res = await getDashboardStats()
        if (res.code === 200 && res.data) {
            rawStats.value = {
                userCount: res.data.userCount || 0,
                questionBankCount: res.data.bankCount ?? res.data.questionBankCount ?? 0,
                questionCount: res.data.questionCount || 0,
                noteCount: res.data.noteCount || 0
            }

            // 分类统计：过滤 0 值科目（0 值扇区与图例都是噪音）
            const categoryData = (res.data.categoryStats || [])
                .map((item: any) => ({
                    value: Number(item.value ?? item.count ?? 0),
                    name: item.name ?? item.subject ?? '未分类'
                }))
                .filter((c: any) => c.value > 0)
            categoryLegend.value = categoryData.map((c: any, i: number) => ({
                ...c,
                color: SUBJECT_PALETTE[i % SUBJECT_PALETTE.length]
            }))
            await nextTick()
            if (categoryLegend.value.length && categoryChartRef.value) {
                initCategoryChart(categoryData)
            }

            // 用户增长：补齐近 7 天；全为 0 时走空态，不渲染贴地的假折线
            const growth = fillLast7Days(res.data.userGrowth || [])
            const hasNewUser = growth.counts.some(c => c > 0)
            growthEmpty.value = !hasNewUser
            await nextTick()
            if (hasNewUser && userGrowthChartRef.value) {
                initUserGrowthChart(growth.dates, growth.counts)
            }
        }
    } catch (e) {
        console.warn('Dashboard stats 接口异常:', e)
    }
}

async function fetchRecent() {
    try {
        const res = await getDashboardRecent()
        if (res.code === 200 && Array.isArray(res.data)) {
            recentActivities.value = res.data.map(normalizeActivity)
        }
    } catch (e) {
        console.warn('Dashboard recent 接口异常:', e)
    }
}

onMounted(async () => {
    await nextTick()
    updateTime()
    timeTimer = setInterval(updateTime, 1000)
    window.addEventListener('resize', handleResize)
    fetchStats()
    fetchRecent()
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (timeTimer) {
        clearInterval(timeTimer)
    }
    categoryChart?.dispose()
    userGrowthChart?.dispose()
})
</script>

<style scoped lang="scss">
.admin-dashboard {
    padding: 20px;
    background: #f7f8fa;
    min-height: calc(100vh - 84px);

    /* ===== 页头：与「学习统计」页一致 ===== */
    .page-header {
        display: flex;
        align-items: baseline;
        gap: 10px;
        margin-bottom: 16px;
    }

    .page-title {
        font-size: 22px;
        font-weight: 700;
        color: #1f2937;
        margin: 0;
    }

    .page-sub {
        font-size: 13px;
        color: #9ca3af;
    }

    /* ===== 通用面板：与「学习统计」页 panel 同款 ===== */
    .panel {
        background: #fff;
        border-radius: 12px;
        border: 1px solid #f3f4f6;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        padding: 18px;
        margin-bottom: 16px;
        min-width: 0;
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

    /* ===== 统计卡片 ===== */
    .stat-cards {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 16px;
        margin-bottom: 0;

        @media (max-width: 992px) {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        @media (max-width: 560px) {
            grid-template-columns: 1fr;
        }

        .stat-panel {
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 16px;
        }

        .stat-icon {
            width: 56px;
            height: 56px;
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;

            .el-icon {
                font-size: 26px;
                color: white;
            }
        }

        .stat-content {
            flex: 1;
            min-width: 0;

            .stat-value {
                font-size: 28px;
                font-weight: 700;
                color: #1f2937;
                line-height: 1.2;
            }

            .stat-label {
                font-size: 13px;
                color: #6b7280;
                margin-top: 4px;
            }
        }
    }

    /* ===== 两行图表：2 : 1（同「学习趋势 : 科目分布」布局） ===== */
    .grid-row {
        display: grid;
        grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
        gap: 16px;

        @media (max-width: 992px) {
            grid-template-columns: 1fr;
        }
    }

    .chart {
        width: 100%;
    }

    .chart-main {
        height: 260px;
    }

    .chart-pie {
        height: 196px;
    }

    .chart-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 196px;
        font-size: 13px;
        color: #9ca3af;
    }

    /* ===== 分类饼图：圆环独占一行 + 图例在下方 flex-wrap（与「科目分布」同方案，不再挤压） ===== */
    .category-body {
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 6px;
    }

    .pie-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 4px 14px;
        max-height: 88px;
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

        .legend-name {
            max-width: 110px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .legend-count {
            flex: none;
            color: #9ca3af;
        }
    }

    /* ===== 最近活动 ===== */
    .activity-list {
        max-height: 300px;
        overflow-y: auto;

        .activity-item {
            display: flex;
            align-items: flex-start;
            padding: 11px 0;
            border-bottom: 1px solid #f3f4f6;

            &:last-child {
                border-bottom: none;
            }

            .activity-icon {
                width: 34px;
                height: 34px;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 12px;
                flex-shrink: 0;

                .el-icon {
                    color: white;
                }

                &.bank {
                    background: #059669;
                }

                &.question {
                    background: #d97706;
                }

                &.note {
                    background: #3b82f6;
                }

                &.user {
                    background: #6b7280;
                }
            }

            .activity-content {
                flex: 1;
                min-width: 0;

                .activity-text {
                    font-size: 14px;
                    color: #374151;
                    line-height: 1.5;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    display: -webkit-box;
                    -webkit-line-clamp: 2;
                    -webkit-box-orient: vertical;
                }

                .activity-time {
                    font-size: 12px;
                    color: #9ca3af;
                    margin-top: 4px;
                }
            }
        }
    }

    /* ===== 用户增长空态 ===== */
    .growth-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 10px;
        min-height: 260px;
        font-size: 13px;
        color: #9ca3af;

        .growth-empty-mark {
            width: 52px;
            height: 52px;
            border-radius: 50%;
            background: #eff6ff;
            color: #409eff;
            display: flex;
            align-items: center;
            justify-content: center;
        }
    }

    /* ===== 系统信息 ===== */
    .system-info {
        .info-item {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 12px 0;
            border-bottom: 1px solid #f3f4f6;

            &:last-child {
                border-bottom: none;
            }

            .info-label {
                font-size: 13px;
                color: #6b7280;
                flex-shrink: 0;
            }

            .info-value {
                font-size: 13px;
                color: #1f2937;
                font-weight: 500;
                text-align: right;
                word-break: break-all;
            }
        }
    }
}

@media (max-width: 768px) {
    .admin-dashboard {
        padding: 12px;
    }
}
</style>
