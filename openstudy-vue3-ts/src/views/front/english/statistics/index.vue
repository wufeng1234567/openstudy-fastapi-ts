<template>
  <div class="stat-page" :class="{ 'is-embedded': embedded }">
    <!--
      工具条（2026-10-26 改造）
      ==========================================================================
      原来是整页顶栏（返回按钮 + 「学习统计」大标题 + 右侧 7天/30天 + 刷新）。

      现在这个页面被**嵌进「我的学习 · 学习统计」的第二个 tab** 里，
      大标题和返回按钮会和外层顶栏重复 —— 所以改成一条轻量的工具条，
      只留真正需要操作的两个控件，标题交给外层 tab 去表达。

      `embedded` 为 false 时（直接访问 /front/english/statistics 这种老链接）
      仍保留返回入口，避免用户进来后无路可退。
    -->
    <div class="st-toolbar">
      <button v-if="!embedded" type="button" class="st-back" @click="goBack">
        <OsIcon name="arrow-left" :size="16" />
        <span>英语学习</span>
      </button>
      <span class="st-toolbar__hint">
        数据来自单词听写与阅读练习
      </span>
      <div class="st-toolbar__ops">
        <!-- 窗口切换：7 天 / 30 天 -->
        <div class="st-range">
          <button
            v-for="r in rangeOptions"
            :key="r.days"
            type="button"
            class="st-range__btn"
            :class="{ 'is-active': days === r.days }"
            @click="switchDays(r.days)"
          >
            {{ r.label }}
          </button>
        </div>
        <button type="button" class="st-btn" :disabled="loading" @click="load()">
          <OsIcon name="refresh" :size="14" />
          <span>刷新</span>
        </button>
      </div>
    </div>

    <!-- 骨架 -->
    <div v-if="loading && !loaded" class="st-skeleton">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- 空状态：一次都没练过 -->
    <div v-else-if="!stats.sessions" class="st-empty">
      <div class="st-empty__icon">
        <OsIcon name="chart-column" :size="26" />
      </div>
      <h3 class="st-empty__title">还没有练习记录</h3>
      <p class="st-empty__desc">
        去「单词听写」练一轮，或者做一篇「阅读练习」，这里就会有数据了。
      </p>
      <div class="st-empty__btns">
        <button type="button" class="st-btn is-primary" @click="gotoListening">
          去单词听写
        </button>
        <button type="button" class="st-btn" @click="gotoReading">
          去阅读练习
        </button>
      </div>
    </div>

    <template v-else>
      <!-- 四个核心指标 -->
      <section class="st-kpi">
        <div class="st-kpi__card">
          <span class="st-kpi__label">累计练习</span>
          <strong class="st-kpi__value">{{ stats.sessions }}<i>次</i></strong>
          <span class="st-kpi__sub">{{ stats.total }} 个单词</span>
        </div>
        <div class="st-kpi__card">
          <span class="st-kpi__label">平均正确率</span>
          <strong class="st-kpi__value" :class="accuracyClass(stats.accuracy)">
            {{ stats.accuracy }}<i>%</i>
          </strong>
          <span class="st-kpi__sub">答对 {{ stats.correct }} 个</span>
        </div>
        <div class="st-kpi__card">
          <span class="st-kpi__label">连续练习</span>
          <strong class="st-kpi__value">{{ stats.streak }}<i>天</i></strong>
          <span class="st-kpi__sub">
            {{ stats.streak >= 3 ? '保持住' : stats.streak > 0 ? '再接再厉' : '今天还没练' }}
          </span>
        </div>
        <div class="st-kpi__card">
          <span class="st-kpi__label">薄弱单词</span>
          <strong class="st-kpi__value">{{ stats.topWrong.length }}<i>个</i></strong>
          <span class="st-kpi__sub">
            {{ stats.topWrong.length ? '见下方清单' : '暂无错词' }}
          </span>
        </div>
      </section>

      <!-- 趋势图 -->
      <section class="st-card">
        <div class="st-card__head">
          <h2 class="st-card__title">练习趋势</h2>
          <span class="st-card__hint">
            最近 {{ stats.days }} 天 · 柱高为当天练习单词数
          </span>
        </div>

        <!--
          手写 SVG 柱状图，不用图表库
          ---------------------------------------------------------------
          只为一张柱图引入 echarts（1MB+）或 chart.js（200KB+）不划算，
          而且它俩的默认配色跟我们这套 UI 不搭，还要再覆盖一遍样式。
          这里就是几十行算坐标的事。
        -->
        <div class="st-chart">
          <!-- Y 轴刻度 -->
          <div class="st-chart__yaxis">
            <span v-for="t in yTicks" :key="t">{{ t }}</span>
          </div>
          <div class="st-chart__plot">
            <!-- 网格线 -->
            <div class="st-chart__grid">
              <i v-for="t in yTicks" :key="t" />
            </div>
            <!-- 柱子 -->
            <div class="st-chart__bars" :class="{ 'is-dense': stats.days > 10 }">
              <div
                v-for="(d, i) in stats.trend"
                :key="d.date"
                class="st-bar"
                :class="{ 'is-empty': !d.total, 'is-today': i === stats.trend.length - 1 }"
              >
                <div class="st-bar__col">
                  <div
                    class="st-bar__fill"
                    :style="{ height: barHeight(d.total) }"
                    :title="`${d.date}：${d.total} 个，正确率 ${d.accuracy}%`"
                  />
                </div>
                <!-- X 轴标签：30 天时只显示每隔几天的，避免挤成一团 -->
                <span class="st-bar__label">{{ xLabel(d, i) }}</span>
              </div>
            </div>
          </div>
        </div>
        <!-- 有练习的日子太少时给个提示，避免用户以为图画错了 -->
        <p v-if="activeDays === 0" class="st-chart__note">
          这段时间还没有练习记录
        </p>
      </section>

      <!-- 模式对比 + 薄弱单词：两列 -->
      <section class="st-twocol">
        <!-- 各模式表现 -->
        <div class="st-card">
          <div class="st-card__head">
            <h2 class="st-card__title">各模式表现</h2>
          </div>
          <div v-if="!modeList.length" class="st-blank">暂无数据</div>
          <div v-else class="st-modes">
            <div v-for="m in modeList" :key="m.key" class="st-mode">
              <div class="st-mode__top">
                <span class="st-mode__name">
                  <span class="st-mode__dot" :style="{ background: m.color }" />
                  {{ m.label }}
                </span>
                <span class="st-mode__pct" :class="accuracyClass(m.data.accuracy)">
                  {{ m.data.accuracy }}%
                </span>
              </div>
              <!-- 进度条 -->
              <div class="st-mode__bar">
                <div
                  class="st-mode__bar-fill"
                  :style="{ width: m.data.accuracy + '%', background: m.color }"
                />
              </div>
              <div class="st-mode__meta">
                {{ m.data.sessions }} 次 · {{ m.data.total }} 个 · 对 {{ m.data.correct }} 个
              </div>
            </div>
          </div>
        </div>

        <!-- 薄弱单词 -->
        <div class="st-card">
          <div class="st-card__head">
            <h2 class="st-card__title">最常写错</h2>
            <span class="st-card__hint">取最近 20 次练习</span>
          </div>
          <div v-if="!stats.topWrong.length" class="st-blank">
            还没有错词，继续保持
          </div>
          <ul v-else class="st-wrong">
            <li v-for="(w, i) in stats.topWrong" :key="w.word" class="st-wrong__item">
              <span class="st-wrong__rank">{{ i + 1 }}</span>
              <span class="st-wrong__word">{{ w.word }}</span>
              <span class="st-wrong__count">错 {{ w.count }} 次</span>
              <button
                type="button"
                class="st-wrong__play"
                title="朗读"
                @click="playWord(w.word)"
              >
                <OsIcon name="volume" :size="13" />
              </button>
            </li>
          </ul>
          <!-- 闭环：把错词变成下一次练习 -->
          <button
            v-if="stats.topWrong.length"
            type="button"
            class="st-btn is-primary st-wrong__cta"
            @click="practiceWrongWords"
          >
            用这些错词练一轮
          </button>
        </div>
      </section>

      <!-- 最近记录 -->
      <section class="st-card">
        <div class="st-card__head">
          <h2 class="st-card__title">最近练习</h2>
          <span class="st-card__hint">最多 10 条</span>
        </div>
        <div v-if="!stats.recentLogs.length" class="st-blank">暂无记录</div>
        <div v-else class="st-logs">
          <div v-for="log in stats.recentLogs" :key="log.logId" class="st-log">
            <span class="st-log__mode" :style="{ background: modeColor(log.mode) + '18', color: modeColor(log.mode) }">
              {{ modeLabel(log.mode) }}
            </span>
            <span class="st-log__title">{{ log.title || '未命名' }}</span>
            <span class="st-log__nums">
              {{ log.correct }}/{{ log.total }}
              <i :class="accuracyClass(log.accuracy)">{{ log.accuracy }}%</i>
            </span>
            <span v-if="log.duration" class="st-log__dur">{{ fmtDuration(log.duration) }}</span>
            <span class="st-log__time">{{ log.createTime }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 学习统计（2026-10-26 新增）
 * ============================================================================
 * 用户反馈：「英语练习没有学习统计入口 —— 数据已经存在 english_practice_log 里，
 * 但页面上看不到趋势图，只有练完那一刻的结果面板」。
 *
 * 这个页面把已有数据真正用起来：
 *   ① 四个核心指标（练习次数 / 平均正确率 / 连续天数 / 薄弱词数）
 *   ② 练习趋势柱状图（7 天 / 30 天可切）
 *   ③ 各模式表现对比（听写 / 打字 / 阅读）
 *   ④ 最常写错的词 —— 并且能一键拿去重练（形成闭环）
 *   ⑤ 最近 10 次练习记录
 *
 * 图表是手写 SVG/CSS 柱状图，没有引入图表库 —— 见模板里的注释。
 *
 * ## 2026-10-26 改造：从「独立页面」变成「可嵌入组件」
 *
 * 用户反馈：「两个页面的学习统计有点多余了，想办法融合起来」——
 * 指的是「我的学习 › 学习统计」（题库维度）和「英语学习 › 学习统计」
 * （英语维度）两个同名入口。
 *
 * 现在这一页既可以当独立页面用（`/front/english/statistics`），
 * 也可以被 `<EnglishStatistics embedded />` 嵌进题库统计页的第二个 tab。
 * 差别只在顶栏：嵌入时不渲染「返回」按钮和标题（外层已有），
 * 也不在 `onMounted` 自动加载 —— 由外层在切到该 tab 时调 `refresh()`，
 * 避免用户没看这一屏就先发一次请求。
 */
import { ref, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import { getPracticeStats } from '@/api/words/words'
import { speak } from '@/utils/speech'

const props = withDefaults(
  defineProps<{
    /** 是否作为嵌入组件使用（隐藏返回按钮、不自动加载） */
    embedded?: boolean
    /** 嵌入时的初始窗口天数 */
    initialDays?: number
  }>(),
  { embedded: false, initialDays: 7 }
)

const emit = defineEmits<{
  (e: 'loaded', stats: any): void
}>()

const router = useRouter()

/* ============================ 状态 ============================ */

const loading = ref(false)
const loaded = ref(false)
const days = ref(props.initialDays === 30 ? 30 : 7)

const rangeOptions = [
  { days: 7, label: '7 天' },
  { days: 30, label: '30 天' }
]

/** 统计数据结构（与后端 `/words/practice/stats` 对应） */
const stats = ref<{
  sessions: number
  total: number
  correct: number
  accuracy: number
  days: number
  streak: number
  byMode: Record<string, { sessions: number; total: number; correct: number; accuracy: number }>
  trend: Array<{ date: string; sessions: number; total: number; correct: number; accuracy: number }>
  topWrong: Array<{ word: string; count: number }>
  recentLogs: Array<{
    logId: number
    mode: string
    title: string
    total: number
    correct: number
    accuracy: number
    duration: number
    createTime: string
  }>
}>({
  sessions: 0,
  total: 0,
  correct: 0,
  accuracy: 0,
  days: 7,
  streak: 0,
  byMode: {},
  trend: [],
  topWrong: [],
  recentLogs: []
})

/* ============================ 模式映射 ============================ */

const MODE_META: Record<string, { label: string; color: string }> = {
  dictation: { label: '听写', color: '#3b82f6' },
  input: { label: '打字输入', color: '#8b5cf6' },
  reading: { label: '阅读练习', color: '#10b981' },
  ocr: { label: '拍照识词', color: '#f59e0b' }
}

function modeLabel(mode: string): string {
  return MODE_META[mode]?.label || mode || '练习'
}
function modeColor(mode: string): string {
  return MODE_META[mode]?.color || '#94a3b8'
}

/** 各模式按「练习次数」倒序，只显示有数据的 */
const modeList = computed(() =>
  Object.entries(stats.value.byMode)
    .map(([key, data]) => ({
      key,
      label: modeLabel(key),
      color: modeColor(key),
      data
    }))
    .sort((a, b) => b.data.sessions - a.data.sessions)
)

/* ============================ 图表计算 ============================ */

/**
 * Y 轴刻度
 *
 * 取「最大练习量的 1.25 倍」向上取整到 4 的倍数，再四等分 ——
 * 这样刻度一定是整数，且柱顶不会贴到框线。
 */
const yTicks = computed(() => {
  const max = Math.max(1, ...stats.value.trend.map((d) => d.total))
  const top = Math.ceil((max * 1.25) / 4) * 4
  const step = top / 4
  // 从高到低，跟 CSS 从上往下的渲染顺序一致
  return [top, top - step, top - 2 * step, top - 3 * step, 0].map((n) => Math.round(n))
})

/** 柱子高度百分比 */
function barHeight(total: number): string {
  const top = yTicks.value[0] || 1
  if (!total) return '0%'
  // 最小 4%，让"练了 1 个"也能看见
  return Math.max(4, Math.round((total / top) * 100)) + '%'
}

/** 有练习记录的天数 */
const activeDays = computed(() => stats.value.trend.filter((d) => d.total > 0).length)

/**
 * X 轴标签
 *
 * 7 天：每天都显示 `10-26`
 * 30 天：每 5 天显示一次，最后一天（今天）总是显示 —— 否则挤成一团看不清
 */
function xLabel(d: { date: string }, i: number): string {
  const mmdd = d.date.slice(5) // "2026-10-26" -> "10-26"
  const total = stats.value.trend.length
  if (total <= 10) return mmdd
  if (i === total - 1) return '今天'
  if (i % 5 === 0) return mmdd
  return ''
}

/* ============================ 工具 ============================ */

/** 正确率配色：>=80 绿 / >=60 橙 / 其余红 */
function accuracyClass(pct: number): string {
  if (pct >= 80) return 'is-good'
  if (pct >= 60) return 'is-mid'
  return 'is-bad'
}

/** 秒 → "3分20秒" */
function fmtDuration(sec: number): string {
  if (!sec) return ''
  const m = Math.floor(sec / 60)
  const s = sec % 60
  if (!m) return `${s}秒`
  return s ? `${m}分${s}秒` : `${m}分`
}

function playWord(word: string) {
  try {
    speak(word, { lang: 'en' })
  } catch {
    ElMessage.warning('当前浏览器不支持朗读')
  }
}

/* ============================ 数据加载 ============================ */

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const res: any = await getPracticeStats(days.value)
    const data = res?.data ?? res
    if (data && typeof data === 'object') {
      stats.value = {
        sessions: data.sessions ?? 0,
        total: data.total ?? 0,
        correct: data.correct ?? 0,
        accuracy: data.accuracy ?? 0,
        days: data.days ?? days.value,
        streak: data.streak ?? 0,
        byMode: data.byMode ?? {},
        trend: Array.isArray(data.trend) ? data.trend : [],
        topWrong: Array.isArray(data.topWrong) ? data.topWrong : [],
        recentLogs: Array.isArray(data.recentLogs) ? data.recentLogs : []
      }
      loaded.value = true
      // 通知外层（嵌入模式下用来显示 tab 角标 / 判断空态）
      emit('loaded', stats.value)
    }
  } catch (e: any) {
    console.error('加载学习统计失败:', e)
    ElMessage.error('加载统计失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

/**
 * 对外暴露的刷新入口
 *
 * 嵌入模式下外层在切到本 tab 时才调它 —— 见组件顶部注释。
 */
defineExpose({ refresh: load, reset: () => { loaded.value = false } })

async function switchDays(d: number) {
  if (days.value === d) return
  days.value = d
  await load()
}

/* ============================ 跳转（闭环） ============================ */

function goBack() {
  router.push('/front/english/ocr')
}
function gotoListening() {
  router.push('/front/english/listening')
}
function gotoReading() {
  router.push('/front/english/reading')
}

/**
 * 用错词练一轮
 *
 * 复用听写页已有的 `practiceSeedWords`（sessionStorage 传参）：
 * 把错词塞进去，听写页在 `onMounted` 里读出来直接开练。
 * 这样统计页不是"只读报表"，而是能直接驱动下一轮练习。
 */
function practiceWrongWords() {
  const words = stats.value.topWrong.map((w) => w.word).filter(Boolean)
  if (!words.length) {
    ElMessage.warning('还没有错词')
    return
  }
  try {
    sessionStorage.setItem('practiceSeedWords', JSON.stringify(words))
  } catch {
    /* 隐私模式下 sessionStorage 可能不可用，忽略 */
  }
  router.push('/front/english/listening')
  ElMessage.success(`已带上 ${words.length} 个错词，点「开始听写」即可`)
}

/* ============================ 生命周期 ============================ */

/*
 * 生命周期（2026-10-26 改造）
 *
 * 嵌入模式**不自动加载** —— 外层在用户切到本 tab 时才调 `refresh()`。
 * 理由：统计页要发 1 个请求 + 算 30 根柱子，用户可能只想看题库那部分，
 * 没切过去就先加载是白费。
 */
onMounted(() => {
  if (!props.embedded) load()
})

// 独立页面被 keep-alive 缓存，从练习页回来时要刷新
onActivated(() => {
  if (!props.embedded && loaded.value) load()
})
</script>

<style scoped lang="scss">
.stat-page {
  min-height: 100%;
  padding-bottom: 40px;
  background: #f8fafc;

  /*
   * 嵌入模式（2026-10-26）
   *
   * 被塞进「我的学习 › 学习统计」的 tab 里时，外层已经有白底容器和左右留白，
   * 所以这里去掉自己的背景色和顶部工具条的分隔线，避免出现"框中框"。
   */
  &.is-embedded {
    min-height: auto;
    padding-bottom: 0;
    background: transparent;

    .st-toolbar {
      padding: 0 0 14px;
      border-bottom: 0;
    }

    /* 内容区不再自己限制宽度 —— 外层容器已经限制了 */
    .st-kpi,
    .st-card,
    .st-twocol {
      max-width: none;
      padding-left: 0;
      padding-right: 0;
    }

    .st-kpi {
      padding-top: 0;
    }
  }

  /* ==================== 工具条 ==================== */
  .st-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 28px;
    background: #fff;
    border-bottom: 1px solid #e5e7eb;
    margin-bottom: 4px;

    &__hint {
      flex: 1;
      min-width: 0;
      font-size: 12px;
      color: #9ca3af;
    }

    &__ops {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: none;
    }
  }

  .st-back {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 5px 9px 5px 5px;
    border: 0;
    border-radius: 8px;
    background: transparent;
    color: #6b7280;
    font-size: 14px;
    cursor: pointer;
    flex: none;

    &:hover {
      background: #f1f5f9;
      color: #111827;
    }
  }

  /* 7天/30天 切换 */
  .st-range {
    display: flex;
    padding: 2px;
    border-radius: 9px;
    background: #f1f5f9;
  }

  .st-range__btn {
    padding: 4px 12px;
    border: 0;
    border-radius: 7px;
    background: transparent;
    color: #6b7280;
    font-size: 12.5px;
    cursor: pointer;
    transition: background .16s, color .16s;

    &.is-active {
      background: #fff;
      color: #111827;
      font-weight: 600;
      box-shadow: 0 1px 3px rgba(0, 0, 0, .08);
    }
  }

  /* ==================== 通用按钮 ==================== */
  .st-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 6px 13px;
    border: 1px solid #e5e7eb;
    border-radius: 9px;
    background: #fff;
    color: #374151;
    font-size: 13px;
    cursor: pointer;
    transition: border-color .16s, color .16s, background .16s;

    &:hover:not(:disabled) {
      border-color: #cbd5e1;
      background: #f8fafc;
    }

    &:disabled {
      opacity: .55;
      cursor: not-allowed;
    }

    &.is-primary {
      border-color: #111827;
      background: #111827;
      color: #fff;

      &:hover:not(:disabled) {
        background: #1f2937;
      }
    }
  }

  /* ==================== 内容容器 ==================== */
  .st-kpi,
  .st-card,
  .st-twocol {
    max-width: 1080px;
    margin-left: auto;
    margin-right: auto;
  }

  .st-kpi {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    padding: 20px 28px 0;
  }

  .st-kpi__card {
    padding: 16px 18px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 13px;
  }

  .st-kpi__label {
    display: block;
    font-size: 12px;
    color: #9ca3af;
  }

  .st-kpi__value {
    display: block;
    margin-top: 6px;
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: #111827;

    i {
      margin-left: 2px;
      font-size: 13px;
      font-weight: 500;
      font-style: normal;
      color: #9ca3af;
    }

    &.is-good { color: #10b981; }
    &.is-mid  { color: #f59e0b; }
    &.is-bad  { color: #ef4444; }
  }

  .st-kpi__sub {
    display: block;
    margin-top: 5px;
    font-size: 11.5px;
    color: #b0b7c3;
  }

  /* ==================== 卡片 ==================== */
  .st-card {
    margin-top: 14px;
    padding: 18px 20px;
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 13px;
  }

  .st-card__head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }

  .st-card__title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: #111827;
  }

  .st-card__hint {
    font-size: 11.5px;
    color: #9ca3af;
  }

  .st-blank {
    padding: 20px 0;
    text-align: center;
    font-size: 12.5px;
    color: #b0b7c3;
  }

  /* ==================== 趋势图 ==================== */
  .st-chart {
    display: flex;
    gap: 8px;
    height: 168px;
  }

  .st-chart__yaxis {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    width: 30px;
    flex: none;
    padding-bottom: 20px; /* 让刻度与绘图区对齐（下方留 X 轴标签高度） */
    font-size: 10.5px;
    color: #b0b7c3;
    text-align: right;
  }

  .st-chart__plot {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .st-chart__grid {
    position: absolute;
    inset: 0 0 20px 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;

    i {
      display: block;
      height: 1px;
      background: #f1f5f9;
    }
  }

  .st-chart__bars {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    gap: 6px;

    /* 30 天时柱子太密，缩间距 */
    &.is-dense {
      gap: 2px;
    }
  }

  .st-bar {
    display: flex;
    flex: 1;
    min-width: 0;
    flex-direction: column;
    align-items: center;
    height: 100%;
  }

  .st-bar__col {
    display: flex;
    align-items: flex-end;
    justify-content: center;
    width: 100%;
    flex: 1;
    padding-bottom: 20px; /* 与 grid 对齐 */
  }

  .st-bar__fill {
    width: 100%;
    max-width: 34px;
    border-radius: 4px 4px 0 0;
    background: linear-gradient(180deg, #60a5fa, #3b82f6);
    transition: height .3s ease;
  }

  /* 今天用深色区分 */
  .st-bar.is-today .st-bar__fill {
    background: linear-gradient(180deg, #111827, #374151);
  }

  /* 没练的那天只留一条淡淡的底 */
  .st-bar.is-empty .st-bar__fill {
    background: #f1f5f9;
  }

  .st-bar__label {
    height: 20px;
    font-size: 10px;
    line-height: 20px;
    color: #b0b7c3;
    white-space: nowrap;
  }

  .st-chart__note {
    margin: 10px 0 0;
    font-size: 12px;
    color: #b0b7c3;
    text-align: center;
  }

  /* ==================== 两列 ==================== */
  .st-twocol {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;

    /*
     * ⚠️ 必须把 `.st-card` 的 `margin: auto` 抵消掉。
     *
     * 上面的共享选择器给了 `.st-card { margin-left: auto; margin-right: auto }`
     * 用来水平居中 —— 但在 grid 里，**auto 外边距会吞掉所有剩余空间**，
     * 让 grid item 退化成"内容宽度"，而不是撑满单元格。
     * 实测症状：这两张卡片被压到 140px 左右，右边一大片空白。
     */
    > .st-card {
      max-width: none;
      margin-left: 0;
      margin-right: 0;
    }
  }

  /* ==================== 各模式 ==================== */
  .st-modes {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .st-mode__top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }

  .st-mode__name {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12.5px;
    color: #374151;
  }

  .st-mode__dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }

  .st-mode__pct {
    font-size: 12.5px;
    font-weight: 600;

    &.is-good { color: #10b981; }
    &.is-mid  { color: #f59e0b; }
    &.is-bad  { color: #ef4444; }
  }

  .st-mode__bar {
    height: 6px;
    border-radius: 3px;
    background: #f1f5f9;
    overflow: hidden;
  }

  .st-mode__bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width .3s ease;
  }

  .st-mode__meta {
    margin-top: 5px;
    font-size: 11px;
    color: #b0b7c3;
  }

  /* ==================== 薄弱单词 ==================== */
  .st-wrong {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .st-wrong__item {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 8px;
    border-radius: 8px;
    transition: background .14s;

    &:hover {
      background: #f8fafc;
    }
  }

  .st-wrong__rank {
    width: 17px;
    flex: none;
    font-size: 11px;
    color: #c3cad5;
    text-align: center;
  }

  .st-wrong__word {
    flex: 1;
    min-width: 0;
    font-size: 13px;
    font-weight: 500;
    color: #111827;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .st-wrong__count {
    flex: none;
    font-size: 11.5px;
    color: #ef4444;
  }

  .st-wrong__play {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    flex: none;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: #9ca3af;
    cursor: pointer;

    &:hover {
      background: #f1f5f9;
      color: #3b82f6;
    }
  }

  .st-wrong__cta {
    width: 100%;
    justify-content: center;
    margin-top: 14px;
  }

  /* ==================== 练习记录 ==================== */
  .st-logs {
    display: flex;
    flex-direction: column;
  }

  .st-log {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 9px 4px;
    border-bottom: 1px solid #f1f5f9;
    font-size: 12.5px;

    &:last-child {
      border-bottom: 0;
    }
  }

  .st-log__mode {
    flex: none;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 500;
  }

  .st-log__title {
    flex: 1;
    min-width: 0;
    color: #374151;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .st-log__nums {
    flex: none;
    color: #6b7280;

    i {
      margin-left: 4px;
      font-style: normal;
      font-weight: 600;

      &.is-good { color: #10b981; }
      &.is-mid  { color: #f59e0b; }
      &.is-bad  { color: #ef4444; }
    }
  }

  .st-log__dur {
    flex: none;
    color: #b0b7c3;
  }

  .st-log__time {
    flex: none;
    width: 108px;
    text-align: right;
    color: #b0b7c3;
  }

  /* ==================== 空状态 ==================== */
  .st-skeleton {
    max-width: 1080px;
    margin: 24px auto 0;
    padding: 0 28px;
  }

  .st-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    max-width: 460px;
    margin: 60px auto 0;
    padding: 0 24px;
  }

  .st-empty__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 56px;
    height: 56px;
    margin-bottom: 14px;
    border-radius: 15px;
    background: #f1f5f9;
    color: #94a3b8;
  }

  .st-empty__title {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 600;
    color: #374151;
  }

  .st-empty__desc {
    margin: 0 0 18px;
    font-size: 12.5px;
    line-height: 1.7;
    color: #9ca3af;
  }

  .st-empty__btns {
    display: flex;
    gap: 10px;
  }

  /* ==================== 响应式 ==================== */
  @media (max-width: 900px) {
    .st-kpi {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .st-twocol {
      grid-template-columns: 1fr;
    }
  }
}
</style>
