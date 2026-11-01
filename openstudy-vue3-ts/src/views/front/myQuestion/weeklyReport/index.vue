<template>
  <div class="weekly-page">
    <div class="weekly-toolbar">
      <el-button text class="back-btn" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        学习统计
      </el-button>
      <div class="weekly-toolbar-right">
        <span class="weekly-toolbar-hint">所有数字来自真实作答记录</span>
        <el-button type="primary" plain :loading="exporting" @click="downloadImage">
          <el-icon><Download /></el-icon>
          保存为图片
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="weekly-loading" v-loading="true"></div>

    <div v-else-if="!data || !data.hasData" class="weekly-empty">
      <div class="weekly-empty-mark">周</div>
      <h3>这周的周报还没生成</h3>
      <p>先去做几道题，系统会用真实作答记录生成你的成长故事。</p>
      <el-button type="primary" @click="goPractice">去题库练习</el-button>
    </div>

    <div v-else ref="reportRef" class="weekly-card">
      <div class="report-glow"></div>

      <header class="report-head">
        <div>
          <div class="report-brand">OPENSTUDY · 学习周报</div>
          <div class="report-range">
            {{ data.range.label }}
            <span v-if="!data.range.isCurrent" class="report-range-tag">最近一次学习</span>
          </div>
        </div>
        <div class="report-mark">W</div>
      </header>

      <h1 class="report-headline">{{ data.headline }}</h1>
      <p v-if="!data.range.isCurrent" class="report-note">
        你最近两周没有新的练习记录，这一页展示的是 {{ data.range.start }} 之后那 7 天的复盘。
      </p>

      <div class="report-stats">
        <div class="report-stat is-hero">
          <span class="report-stat-num">{{ data.stats.practiceCount }}</span>
          <span class="report-stat-label">道题</span>
          <span class="report-stat-sub" :class="{ 'is-down': (data.stats.deltaPractice ?? 0) < 0 }">
            <template v-if="data.stats.deltaPractice === null">
              上一周期 {{ data.stats.prevPracticeCount }} 道
            </template>
            <template v-else>
              {{ data.stats.deltaPractice >= 0 ? '↑' : '↓' }} {{ Math.abs(data.stats.deltaPractice) }}% 较上期
            </template>
          </span>
        </div>
        <div class="report-stat">
          <span class="report-stat-num">{{ data.stats.accuracy }}<i>%</i></span>
          <span class="report-stat-label">正确率</span>
          <span class="report-stat-sub" :class="{ 'is-down': (data.stats.deltaAccuracy ?? 0) < 0 }">
            <template v-if="data.stats.deltaAccuracy === null">样本还不够比较</template>
            <template v-else>
              {{ data.stats.deltaAccuracy >= 0 ? '↑' : '↓' }} {{ Math.abs(data.stats.deltaAccuracy) }} 个百分点
            </template>
          </span>
        </div>
        <div class="report-stat">
          <span class="report-stat-num">{{ data.stats.activeDays }}<i>天</i></span>
          <span class="report-stat-label">有学习</span>
          <span class="report-stat-sub">最长连续 {{ data.stats.longestStreak }} 天</span>
        </div>
        <div class="report-stat">
          <span class="report-stat-num">{{ data.stats.markedCount }}<i>道</i></span>
          <span class="report-stat-label">主动斩题</span>
          <span class="report-stat-sub">标记「已经会了」</span>
        </div>
      </div>

      <section class="report-section">
        <div class="report-section-head">
          <h3>每日节奏</h3>
          <span>每一天的作答量</span>
        </div>
        <div class="report-bars">
          <div v-for="day in data.daily" :key="day.date" class="report-bar-col">
            <span class="report-bar-value">{{ day.practiceCount || '' }}</span>
            <div class="report-bar-track">
              <div
                class="report-bar-fill"
                :class="{ 'is-peak': day.practiceCount === maxDaily }"
                :style="{ height: `${barHeight(day.practiceCount)}%` }"
              ></div>
            </div>
            <span class="report-bar-day">{{ day.weekday }}</span>
            <span class="report-bar-date">{{ day.date.slice(8) }}</span>
          </div>
        </div>
      </section>

      <div class="report-columns">
        <section class="report-section report-highlights">
          <div class="report-section-head">
            <h3>这周发生了什么</h3>
            <span>只记录真实发生的事</span>
          </div>
          <div v-if="data.highlights.length" class="highlight-list">
            <div v-for="(h, i) in data.highlights" :key="i" class="highlight-item">
              <span class="highlight-index">0{{ i + 1 }}</span>
              <div>
                <div class="highlight-title">{{ h.title }}</div>
                <div class="highlight-detail">{{ h.detail }}</div>
              </div>
            </div>
          </div>
          <div v-else class="highlight-empty">这一周比较安静，下一周留一点记录给未来的自己。</div>
        </section>

        <section class="report-section report-subjects">
          <div class="report-section-head">
            <h3>学科体检</h3>
            <span>按本周正确率</span>
          </div>
          <div v-if="data.subjects.length" class="subject-list">
            <div v-for="subject in data.subjects" :key="subject.subject" class="subject-row">
              <div class="subject-row-head">
                <span class="subject-name">{{ subject.subject }}</span>
                <span class="subject-value">{{ subject.accuracy }}%</span>
              </div>
              <div class="subject-track">
                <div class="subject-fill" :style="{ width: `${Math.max(subject.accuracy, 2)}%` }"></div>
              </div>
              <div class="subject-meta">{{ subject.attempts }} 次作答</div>
            </div>
          </div>
          <div v-else class="highlight-empty">本周没有可归属到科目的练习记录。</div>
        </section>
      </div>

      <section class="report-section report-next">
        <div class="report-section-head">
          <h3>下周，先做这三件事</h3>
          <span>按优先级排好</span>
        </div>
        <div class="next-list">
          <div v-for="(n, i) in data.nextWeek" :key="i" class="next-item">
            <span class="next-index">{{ i + 1 }}</span>
            <div>
              <div class="next-title">{{ n.title }}</div>
              <div class="next-detail">{{ n.detail }}</div>
            </div>
          </div>
          <div v-if="!data.nextWeek.length" class="highlight-empty">下周保持现在的节奏就好。</div>
        </div>
      </section>

      <footer class="report-foot">
        <span>OpenStudy · 把「学过」变成「学会」</span>
        <span class="report-foot-date">生成于 {{ data.generatedAt.slice(0, 10) }}</span>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Download } from '@element-plus/icons-vue'
import html2canvas from 'html2canvas'
import { ElMessage } from 'element-plus'
import { getWeeklyReport, type WeeklyReportResult } from '@/api/userStats/userStats'

defineOptions({ name: 'WeeklyReport' })

const router = useRouter()
const loading = ref(true)
const exporting = ref(false)
const data = ref<WeeklyReportResult | null>(null)
const reportRef = ref<HTMLElement | null>(null)

const maxDaily = computed(() => Math.max(1, ...(data.value?.daily || []).map((d) => d.practiceCount)))

function barHeight(value: number) {
  if (!value) return 2
  return Math.max(6, Math.round((value / maxDaily.value) * 100))
}

const goBack = () => router.push('/front/myQuestion/myStats')
const goPractice = () => router.push('/front/questionPractice')

async function load() {
  loading.value = true
  try {
    const res: any = await getWeeklyReport()
    if (res.code === 200) data.value = res.data
  } catch (e: any) {
    console.warn('[学习周报] 加载失败', e)
  } finally {
    loading.value = false
  }
}

async function downloadImage() {
  if (!reportRef.value) return
  exporting.value = true
  try {
    const canvas = await html2canvas(reportRef.value, {
      backgroundColor: '#f6f7fb',
      scale: 2,
      useCORS: true,
      logging: false,
    })
    const link = document.createElement('a')
    link.download = `OpenStudy学习周报_${data.value?.range.label || ''}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    ElMessage.success('周报已保存')
  } catch (e: any) {
    ElMessage.error('保存失败，请重试')
    console.warn('[学习周报] 导出失败', e)
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.weekly-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 16px 48px;
}

.weekly-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.weekly-toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.weekly-toolbar-hint {
  color: #9ca3af;
  font-size: 11px;
}

.back-btn {
  color: #64748b;
  font-size: 13px;
}

.weekly-loading {
  height: 520px;
  border-radius: 20px;
  background: #fff;
}

.weekly-empty {
  padding: 72px 24px;
  border: 1px solid #eef2f7;
  border-radius: 20px;
  background: #fff;
  text-align: center;
}

.weekly-empty-mark {
  display: inline-grid;
  width: 56px;
  height: 56px;
  margin-bottom: 14px;
  place-items: center;
  border-radius: 16px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 22px;
  font-weight: 700;
}

.weekly-empty h3 {
  margin: 0 0 8px;
  color: #1f2937;
  font-size: 18px;
}

.weekly-empty p {
  margin: 0 auto 20px;
  max-width: 420px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.7;
}

.weekly-card {
  position: relative;
  overflow: hidden;
  padding: 34px 38px 26px;
  border: 1px solid #e8edf5;
  border-radius: 22px;
  background:
    radial-gradient(circle at 100% 0%, rgba(59, 130, 246, 0.09), transparent 32%),
    linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  box-shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
}

.report-glow {
  position: absolute;
  top: -90px;
  right: -70px;
  width: 240px;
  height: 240px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.22), transparent 65%);
  pointer-events: none;
}

.report-head {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.report-brand {
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.report-range {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.report-range-tag {
  margin-left: 8px;
  padding: 1px 7px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 10px;
}

.report-mark {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 14px;
  background: #111827;
  color: #fff;
  font-size: 17px;
  font-weight: 800;
}

.report-headline {
  max-width: 640px;
  margin: 22px 0 8px;
  color: #0f172a;
  font-size: 27px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.35;
}

.report-note {
  margin: 0 0 6px;
  color: #94a3b8;
  font-size: 11px;
}

.report-stats {
  display: grid;
  grid-template-columns: 1.25fr 1fr 1fr 1fr;
  gap: 10px;
  margin-top: 22px;
}

.report-stat {
  display: flex;
  flex-direction: column;
  padding: 14px 16px;
  border: 1px solid #eef2f7;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
}

.report-stat.is-hero {
  background: linear-gradient(135deg, #111827, #1e3a8a);
  border-color: transparent;
}

.report-stat-num {
  color: #111827;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1;
}

.report-stat-num i {
  margin-left: 2px;
  color: #94a3b8;
  font-size: 12px;
  font-style: normal;
  font-weight: 500;
}

.report-stat.is-hero .report-stat-num {
  color: #fff;
}

.report-stat-label {
  margin-top: 7px;
  color: #64748b;
  font-size: 11px;
}

.report-stat.is-hero .report-stat-label {
  color: rgba(255, 255, 255, 0.75);
}

.report-stat-sub {
  margin-top: 8px;
  color: #059669;
  font-size: 10px;
}

.report-stat.is-hero .report-stat-sub {
  color: #93c5fd;
}

.report-stat-sub.is-down {
  color: #dc2626;
}

.report-section {
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid #eef2f7;
}

.report-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.report-section-head h3 {
  margin: 0;
  color: #1f2937;
  font-size: 14px;
  font-weight: 700;
}

.report-section-head span {
  color: #94a3b8;
  font-size: 10px;
}

.report-bars {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
  align-items: end;
  height: 128px;
}

.report-bar-col {
  display: flex;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 3px;
}

.report-bar-value {
  min-height: 12px;
  color: #64748b;
  font-size: 9px;
}

.report-bar-track {
  display: flex;
  width: 100%;
  height: 82px;
  align-items: flex-end;
  justify-content: center;
}

.report-bar-fill {
  width: 24px;
  max-width: 70%;
  border-radius: 5px 5px 2px 2px;
  background: #bfdbfe;
  transition: height 0.5s ease;
}

.report-bar-fill.is-peak {
  background: linear-gradient(180deg, #3b82f6, #2563eb);
}

.report-bar-day {
  color: #64748b;
  font-size: 10px;
}

.report-bar-date {
  color: #cbd5e1;
  font-size: 9px;
}

.report-columns {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 26px;
}

.highlight-list,
.next-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.highlight-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f8fafc;
}

.highlight-index {
  flex: none;
  color: #2563eb;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
}

.highlight-title,
.next-title {
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
}

.highlight-detail,
.next-detail {
  margin-top: 3px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.55;
}

.highlight-empty {
  padding: 14px 0;
  color: #94a3b8;
  font-size: 11px;
}

.subject-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.subject-row-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.subject-name {
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}

.subject-value {
  color: #1f2937;
  font-size: 12px;
  font-weight: 700;
}

.subject-track {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #eef2f7;
}

.subject-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #2563eb);
}

.subject-meta {
  margin-top: 4px;
  color: #94a3b8;
  font-size: 9px;
}

.report-next {
  margin-top: 22px;
}

.next-item {
  display: flex;
  gap: 12px;
  padding: 11px 14px;
  border: 1px solid #eef2f7;
  border-radius: 10px;
  background: #fff;
}

.next-index {
  display: grid;
  width: 20px;
  height: 20px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  font-size: 10px;
  font-weight: 700;
}

.report-foot {
  display: flex;
  justify-content: space-between;
  margin-top: 26px;
  padding-top: 14px;
  border-top: 1px dashed #e2e8f0;
  color: #94a3b8;
  font-size: 10px;
}

.report-foot-date {
  color: #cbd5e1;
}

@media (max-width: 720px) {
  .weekly-card {
    padding: 24px 20px 20px;
  }
  .report-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .report-columns {
    grid-template-columns: 1fr;
    gap: 0;
  }
  .report-headline {
    font-size: 22px;
  }
}
</style>
