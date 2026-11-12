<template>
    <div class="my-stats">
        <!--
          ==========================================================================
          两个「学习统计」合并（2026-10-26）
          ==========================================================================

          用户反馈：「两个页面的学习统计有点多余了，想办法融合起来」。

          指的是这两个同名入口：
            · 我的学习 › 学习统计  → /front/myQuestion/myStats（题库练习数据）
            · 英语学习 › 学习统计  → /front/english/statistics（英语练习数据）

          它们统计的是**同一个人的学习**，只是数据来自两条不同的练习链路，
          在侧边栏各占一个同名入口，用户会以为是重复功能。

          现在合成这一个页面，用 tab 切换：
            · 题库练习 —— 原有的总览 / 趋势 / 科目分布 / 错题诊断，逻辑一行没动
            · 英语练习 —— 复用 EnglishStatistics 组件（同一个文件既能当独立页，
                          也能当嵌入组件，见该组件顶部注释）

          ⚠️ 英语 tab 必须**懒挂载**（`v-if="tabSeen.english"`）：
             它内含手写柱状图，靠百分比宽度撑开；如果一进页面就渲染但容器
             处于 `display:none` 的隐藏状态，布局计算时宽度为 0，
             切过去后柱子会全部塌成 0 高 —— 这是 CSS 隐藏元素做图表的经典坑。
             懒挂载还顺带省掉一次不必要的请求（用户可能只想看题库那部分）。
        -->
        <div class="stats-tabs">
            <SegmentedTabs v-model="activeTab" :tabs="tabList" @change="onTabChange" />
        </div>

        <!-- ==================== Tab 0：题库练习 ==================== -->
        <div v-show="activeTab === 'bank'" class="tab-pane" v-loading="loading">
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
                        <div class="diag-label">掌握进度 <span class="diag-label-hint">累计错题（含已掌握）</span></div>
                        <div class="diag-big">
                            <span class="diag-num">{{ errorAnalysis.mastered }}</span>
                            <span class="diag-total">/ {{ errorAnalysis.totalErrors }} 题</span>
                        </div>
                        <div class="bar-track">
                            <div class="bar-fill" :style="{ width: `${Math.min(errorAnalysis.masterRate, 100)}%` }"></div>
                        </div>
                        <div class="diag-hint">已掌握 {{ formatRateOf(errorAnalysis.masterRate) }}%；当前仍需消灭 {{ errorAnalysis.activeErrors }} 题</div>
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
                                <span class="error-text" v-html="renderQuestionContent(item.questionText)"></span>
                                <span class="error-count">错 {{ item.errorCount }} 次</span>
                                <el-icon class="error-go"><ArrowRight /></el-icon>
                            </div>
                        </div>
                        <div v-else class="diag-hint empty">暂无错题记录</div>
                    </div>
                </div>
            </section>

            <!-- ============ 学情诊断（2026-10-26 v3 新增） ============ -->
            <!--
              数据来自 `GET /userStats/diagnose`（`study_diagnosis_service.diagnose`）。
              放在"错题诊断"下面：上面那张卡是 SQL 聚合（错了几次、难度分布），
              这张卡是逐题状态（哪道题该复习了、哪道题反复失守），
              两者信息互补，不重复。
            -->
            <DiagnosisPanel @practice="goPractice" @open-question="onOpenDiagnosisItem" />

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

        <!-- ==================== 趋势图下钻：某一天做了什么 ==================== -->
        <el-dialog
            v-model="dayDetailVisible"
            :title="dayDetail ? `${dayDetail.date} 学习明细` : '学习明细'"
            width="680px"
        >
            <div v-loading="dayDetailLoading" class="day-detail">
                <div v-if="dayDetail" class="day-summary">
                    <div><b>{{ dayDetail.practiceCount }}</b><span>次作答</span></div>
                    <div><b class="is-correct">{{ dayDetail.correctCount }}</b><span>答对</span></div>
                    <div><b class="is-error">{{ dayDetail.errorCount }}</b><span>答错</span></div>
                    <div><b>{{ dayDetail.markedCount }}</b><span>斩题</span></div>
                </div>
                <div v-if="dayDetail?.items.length" class="day-list">
                    <div v-for="(item, idx) in dayDetail.items" :key="idx" class="day-item">
                        <span class="day-dot" :class="item.isCorrect ? 'is-correct' : 'is-error'"></span>
                        <div class="day-main">
                            <div class="day-text" v-html="renderQuestionContent(item.questionText)"></div>
                            <div class="day-meta">{{ item.time }} · {{ item.bankName || item.subject || '未分类' }}</div>
                        </div>
                        <span class="day-status" :class="item.isCorrect ? 'is-correct' : 'is-error'">
                            {{ item.isCorrect ? '答对' : '答错' }}
                        </span>
                    </div>
                </div>
                <el-empty v-else-if="!dayDetailLoading" description="这一天没有可展示的作答记录" :image-size="80" />
                <div v-if="dayDetail?.unavailableCount" class="day-unavailable">
                    另有 {{ dayDetail.unavailableCount }} 条记录对应的题目已被删除，无法展示。
                </div>
            </div>
        </el-dialog>

        <!-- ==================== Tab 2：英语练习 ==================== -->
        <!--
          `v-if="tabSeen.english"` 而不是 v-show：见顶部注释里关于
          「隐藏容器里算图表尺寸会塌成 0」的说明。第一次切到这个 tab 后才挂载。
        -->
        <div v-show="activeTab === 'english'" class="tab-pane">
            <EnglishStatistics
                v-if="tabSeen.english"
                ref="englishStatsRef"
                embedded
                @loaded="onEnglishLoaded"
            />
        </div>

        <!-- ==================== Tab 3：学习周报 ==================== -->
        <div v-show="activeTab === 'weekly'" class="tab-pane">
            <WeeklyReportPanel v-if="tabSeen.weekly" ref="weeklyReportRef" @open-plan="openKnowledgeAdvice" />
        </div>

        <!-- ==================== 历史入口：旧考前计划（只读归档，不在 tabs 展示） ==================== -->
        <div v-show="activeTab === 'legacyExam'" class="tab-pane">
            <LegacyExamPlanPanel v-if="tabSeen.legacyExam" ref="legacyExamRef" @open-plan="openKnowledgeAdvice" />
        </div>

    </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'MyStats' })
import { ref, computed, reactive, watch, onMounted, onActivated, onUnmounted, nextTick } from 'vue'
import useTopbarStore from '@/store/modules/topbar'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { TrendCharts, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import SegmentedTabs from '@/components/SegmentedTabs/index.vue'
import EnglishStatistics from '@/views/front/english/statistics/index.vue'
import WeeklyReportPanel from './components/WeeklyReportPanel.vue'
import LegacyExamPlanPanel from './components/LegacyExamPlanPanel.vue'
// 学情诊断面板（2026-10-26 v3）：把后端逐题诊断画成页内图表，而不是下载 PDF
import DiagnosisPanel from './components/DiagnosisPanel.vue'

import {
    getOverview,
    getBySubject,
    getTrend,
    getErrorAnalysis,
    getGrowth,
    getDayDetail
} from '@/api/userStats/userStats'
import type {
    OverviewStats,
    SubjectStat,
    TrendItem,
    ErrorAnalysis,
    GrowthRecord,
    DayDetailResult
} from '@/api/userStats/userStats'
import { renderQuestionContent } from '@/utils/latex'

const router = useRouter()

/* ============================================================================
 * Tab 切换（2026-10-26）
 *
 * 两个 tab 的数据源完全独立：
 *   bank    —— /userStats/*（题库练习）
 *   english —— /words/practice/stats（英语练习）
 *
 * 所以切换时不需要互相同步，只要保证英语那边**第一次切过去才加载**。
 * ========================================================================== */
type StatsTab = 'bank' | 'english' | 'weekly' | 'legacyExam'

const activeTab = ref<StatsTab>('bank')

/** 各 tab 是否已挂载过（图表/重组件懒挂载的关键） */
const tabSeen = reactive({ bank: true, english: false, weekly: false, legacyExam: false })

/** 题库数据是否已经拉过（决定切回 tab 时要不要补拉） */
const bankLoaded = ref(false)

const englishStatsRef = ref<any>(null)
const weeklyReportRef = ref<any>(null)
const legacyExamRef = ref<any>(null)

const tabList = [
    { key: 'bank', label: '题库练习' },
    { key: 'english', label: '英语练习' },
    { key: 'weekly', label: '学习周报' }
]

/*
 * 顶栏副标题跟着 tab 走（2026-10-26）
 *
 * 合并前这句固定是「数据来自你的刷题、错题、斩题与收藏记录」——
 * 那是题库的说明。现在同一页还有英语练习，如果切到英语 tab
 * 副标题还写着"刷题/斩题"，就文不对题了。
 */
function syncTopbarSubtitle() {
    const subtitleMap: Record<StatsTab, string> = {
        bank: '数据来自你的刷题、错题、斩题与收藏记录',
        english: '数据来自你的单词听写与阅读练习',
        weekly: '最近 7 天的真实学习记录，可以保存成图片',
        legacyExam: '旧版考前计划归档，只读查看；规划建议在「我的资料 → 知识图谱」里'
    }
    topbarStore.setCount(subtitleMap[activeTab.value])
}

function onTabChange(key: string) {
    const k = key as StatsTab

    /*
     * 把 tab 同步进 URL（2026-10-26）
     *
     * 好处：刷新页面 / 把链接发给别人 / 浏览器后退，都能回到同一个 tab。
     * 用 `replace` 不用 `push` —— 切 tab 不该在历史里堆一串记录，
     * 否则用户点后退要按好几次才能离开这一页。
     */
    const cur = router.currentRoute.value
    if (cur.query.tab !== k) {
        router.replace({ path: cur.path, query: { ...cur.query, tab: k } })
    }
    syncTopbarSubtitle()

    if (k === 'english') {
        // 已经挂载过：回来时刷新一次，避免看到过期数据
        tabSeen.english = true
        nextTick(() => englishStatsRef.value?.refresh?.())
        return
    }

    if (k === 'weekly') {
        tabSeen.weekly = true
        nextTick(() => weeklyReportRef.value?.refresh?.())
        return
    }

    /*
     * 切回题库 tab
     *
     * ⚠️ 两个都要做：
     *   ① 如果之前从 `?tab=english` 进来，题库数据**一次都没拉过**（见 onMounted），
     *      这里必须补拉，否则切回来是一片空白；
     *   ② echarts 容器刚从 `display:none` 变可见，之前算的尺寸是错的，
     *      必须 resize，否则图会挤在左上角一小块。
     */
    if (!bankLoaded.value) {
        setTimeout(fetchAll, 50)
    }
    nextTick(() => handleResize())
}

function openKnowledgeAdvice() {
    router.push({ path: '/front/workspace', query: { view: 'wiki' } })
}

function onEnglishLoaded(_stats: any) {
    // 目前只用来占位（未来可以在 tab 上显示练习次数角标）
}

/*
 * 从 URL 的 `?tab=english` 直接落到英语 tab
 *
 * 用于旧链接 `/front/english/statistics` 的重定向（见 router/index.ts），
 * 以及智能体工具返回的 jumpUrl。
 *
 * ⚠️ 光在 `onMounted` 里调不够 —— 本页带 `keepAlive: true`，
 *    用户如果之前已经打开过统计页，再从旧链接进来时组件是**复用**的，
 *    `onMounted` 根本不会触发，于是停在原来的 tab 上（实测就是这样）。
 *    所以除了 onMounted，还要 watch 路由 query 变化。
 */
function applyTabFromQuery() {
    const raw = router.currentRoute.value.query.tab
    // 旧链接 ?tab=exam 落在只读历史归档；导航里不再出现考前计划。
    const t = raw === 'exam' ? 'legacyExam' : raw
    if (t === 'english') {
        activeTab.value = 'english'
        tabSeen.english = true
        nextTick(() => englishStatsRef.value?.refresh?.())
    } else if (t === 'bank') {
        activeTab.value = 'bank'
    } else if (t === 'weekly') {
        activeTab.value = 'weekly'
        tabSeen.weekly = true
        nextTick(() => weeklyReportRef.value?.refresh?.())
    } else if (t === 'plan') {
        // 旧学习计划页已移除：旧链接直接回到知识图谱页（规划建议模式）。
        router.replace({
            path: '/front/workspace',
            query: { view: 'wiki', kbId: router.currentRoute.value.query.kbId || undefined }
        })
        return
    } else if (t === 'legacyExam') {
        activeTab.value = 'legacyExam'
        tabSeen.legacyExam = true
        nextTick(() => legacyExamRef.value?.refresh?.())
    }
    // 副标题跟着一起变，否则会显示题库那句说明
    syncTopbarSubtitle()
}

// 监听 query.tab（覆盖 keep-alive 复用的情况）
watch(
    () => router.currentRoute.value.query.tab,
    (t) => {
        if (t === 'english' || t === 'bank' || t === 'weekly' || t === 'plan' || t === 'exam' || t === 'legacyExam') applyTabFromQuery()
    }
)

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
// 趋势图下钻：某一天的学习明细
const dayDetailVisible = ref(false)
const dayDetailLoading = ref(false)
const dayDetail = ref<DayDetailResult | null>(null)

async function openDayDetail(date: string) {
    if (!date) return
    dayDetailVisible.value = true
    dayDetailLoading.value = true
    dayDetail.value = null
    try {
        const res: any = await getDayDetail(date)
        if (res.code === 200 && res.data) dayDetail.value = res.data
    } catch (e: any) {
        console.warn('[学习统计] 读取当天明细失败', e)
    } finally {
        dayDetailLoading.value = false
    }
}
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
        // 与错题诊断的“累计错题（含已掌握）”区分：这里是当前仍在错题本中的活跃题。
        hint: `当前活跃（不含已掌握）${trendSum.value.errorCount ? ` · 近 7 天答错 ${trendSum.value.errorCount} 次` : ''}`,
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
const {
  trendChartRef,
  subjectChartRef,
  difficultyChartRef,
  subjectLegend,
  disposeCharts,
  initTrendChart,
  initSubjectChart,
  initDifficultyChart,
  handleResize
} = useStatsCharts()

async function fetchAll() {
    loading.value = true
    try {
        // 五个接口相互独立：用 allSettled 保留可用数据，不能因为其中一个 500 让整页空白。
        const settled = await Promise.allSettled([
            getOverview(),
            getBySubject(),
            getTrend(7),
            getErrorAnalysis(),
            getGrowth()
        ])
        const valueAt = (i: number) => {
            const r = settled[i]
            return r.status === 'fulfilled' ? r.value : null
        }
        const overviewRes: any = valueAt(0)
        const subjectRes: any = valueAt(1)
        const trendRes: any = valueAt(2)
        const errorRes: any = valueAt(3)
        const growthRes: any = valueAt(4)
        const failed = settled.filter(r => r.status === 'rejected').length

        if (overviewRes?.code === 200 && overviewRes.data) overview.value = { ...overview.value, ...overviewRes.data }
        if (subjectRes?.code === 200 && subjectRes.data) subjectStats.value = subjectRes.data
        if (trendRes?.code === 200 && trendRes.data) trendData.value = trendRes.data
        if (errorRes?.code === 200 && errorRes.data) errorAnalysis.value = { ...errorAnalysis.value, ...errorRes.data }
        if (growthRes?.code === 200 && growthRes.data) growth.value = { ...growth.value, ...growthRes.data }

        if (failed) {
            ElMessage.warning(`部分学习统计加载失败（${failed}/5），已展示其余可用数据`)
        }

        await nextTick()
        // 零数据不渲染空图表，避免整屏「0」
        if (!isEmpty.value) {
            initTrendChart(trendData.value, openDayDetail)
            void initSubjectChart(subjectStats.value)
            initDifficultyChart(errorAnalysis.value.byDifficulty)
        }
        // 标记题库数据已拉过 —— 切回 tab 时不用重复拉（见 onTabChange）
        bankLoaded.value = true
    } catch (e) {
        console.warn('用户统计接口异常:', e)
        ElMessage.error('学习统计加载失败，请稍后重试')
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

/**
 * 点击「学情诊断」里需要关注的题 → 跳到错题本定位
 *
 * 与 `goWrongQuestion` 走同一个落点，但带上诊断来源标记：
 * 这样错题页可以据此决定"要不要自动展开练习区"
 * （从诊断点进去的意图是"现在就想练这道"，不是"随便看看"）。
 */
const onOpenDiagnosisItem = (item: { questionId: number | string }) => {
    if (!item?.questionId) return
    router.push({
        path: '/front/myQuestion/wrongQuestion',
        query: { questionId: String(item.questionId), from: 'diagnosis' }
    })
}

const topbarStore = useTopbarStore()

onMounted(async () => {
    /*
     * 支持 ?tab=english 直达（旧链接重定向过来的）
     *
     * ⚠️ 必须排在 `syncTopbarSubtitle()` **之前**：
     *    它内部会改 `activeTab`，而副标题要按 activeTab 决定文案。
     *    反过来的话会先渲染一句"数据来自刷题…"再被纠正，肉眼能看到闪一下。
     */
    applyTabFromQuery()

    /*
     * 把原来内容区那行副标题推到顶栏
     * 用户 2026-10-18：内容区不再有标题行，说明文字并到顶栏那一行。
     */
    syncTopbarSubtitle()

    await nextTick()
    window.addEventListener('resize', handleResize)

    /*
     * 只有落在题库 tab 时才拉题库数据
     *
     * 从 `?tab=english` 进来时用户根本不看题库那一屏，
     * 拉 4 个接口 + 画 3 张 echarts 纯属浪费（而且容器还隐藏着画不出来）。
     */
    if (activeTab.value === 'bank') {
        setTimeout(fetchAll, 100)
    }
})

onActivated(() => {
    // 从题目页/其他路由返回时，刷新当前 tab 的实时数据
    if (activeTab.value === 'weekly') weeklyReportRef.value?.refresh?.()
    else if (activeTab.value === 'legacyExam') legacyExamRef.value?.refresh?.()
})

onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    disposeCharts()
    topbarStore.clear()
})
</script>

<style scoped lang="scss" src="./index.style1.scss"></style>
