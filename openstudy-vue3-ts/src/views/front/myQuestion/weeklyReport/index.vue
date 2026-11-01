<template>
  <div class="weekly-page">
    <div class="weekly-toolbar">
      <el-button text class="back-btn" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        学习统计
      </el-button>
      <div class="weekly-toolbar-right">
        <el-button size="small" :loading="exporting" @click="downloadImage">
          <el-icon><Download /></el-icon>
          保存为图片
        </el-button>
      </div>
    </div>

    <div v-if="loading" class="weekly-loading" v-loading="true"></div>

    <div v-else-if="!data || !data.hasData" class="weekly-empty">
      <div class="weekly-empty-mark">周</div>
      <h3>这周的周报还没生成</h3>
      <p>先去做几道题，系统会用真实作答记录生成你的成长记录。</p>
      <el-button type="primary" @click="goPractice">去题库练习</el-button>
    </div>

    <div v-else ref="reportRef" class="report">
      <header class="report-head">
        <div>
          <div class="report-title-row">
            <h2>学习周报</h2>
            <span class="report-range">{{ data.range.label }}</span>
            <span v-if="!data.range.isCurrent" class="report-range-tag">最近一次学习</span>
          </div>
        </div>
        <span class="report-generated">生成于 {{ data.generatedAt.slice(0, 10) }}</span>
      </header>

      <p class="report-headline">{{ data.headline }}</p>
      <p v-if="!data.range.isCurrent" class="report-note">
        你最近两周没有新的练习记录，这一页展示的是 {{ data.range.start }} 之后那 7 天的复盘。
      </p>

      <div class="report-stats">
        <div class="report-stat">
          <span class="report-stat-label">完成题量</span>
          <div class="report-stat-value">{{ data.stats.practiceCount }} <i>道</i></div>
          <span class="report-stat-sub">
            <template v-if="data.stats.deltaPractice === null">上一周期 {{ data.stats.prevPracticeCount }} 道</template>
            <template v-else>{{ data.stats.deltaPractice >= 0 ? '↑' : '↓' }} {{ Math.abs(data.stats.deltaPractice) }}% 较上期</template>
          </span>
        </div>
        <div class="report-stat">
          <span class="report-stat-label">正确率</span>
          <div class="report-stat-value">{{ data.stats.accuracy }}<i>%</i></div>
          <span class="report-stat-sub">
            <template v-if="data.stats.deltaAccuracy === null">样本还不够比较</template>
            <template v-else>{{ data.stats.deltaAccuracy >= 0 ? '↑' : '↓' }} {{ Math.abs(data.stats.deltaAccuracy) }} 个百分点</template>
          </span>
        </div>
        <div class="report-stat">
          <span class="report-stat-label">有学习的天数</span>
          <div class="report-stat-value">{{ data.stats.activeDays }} <i>天</i></div>
          <span class="report-stat-sub">最长连续 {{ data.stats.longestStreak }} 天</span>
        </div>
        <div class="report-stat">
          <span class="report-stat-label">主动斩题</span>
          <div class="report-stat-value">{{ data.stats.markedCount }} <i>道</i></div>
          <span class="report-stat-sub">标记「已经会了」</span>
        </div>
      </div>

      <section class="report-section">
        <div class="report-section-head">
          <h3>每日节奏</h3>
          <span>每天完成了多少道题</span>
        </div>
        <div class="report-bars">
          <div v-for="day in data.daily" :key="day.date" class="report-bar-col">
            <div class="report-bar-track">
              <div
                class="report-bar-fill"
                :class="{ 'is-peak': day.practiceCount === maxDaily }"
                :style="{ height: `${barHeight(day.practiceCount)}%` }"
              >
                <span v-if="day.practiceCount" class="report-bar-value">{{ day.practiceCount }}</span>
              </div>
            </div>
            <span class="report-bar-day">{{ day.weekday }}</span>
            <span class="report-bar-date">{{ day.date.slice(5) }}</span>
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
              <span class="highlight-index">{{ String(i + 1).padStart(2, '0') }}</span>
              <div>
                <div class="highlight-title">{{ h.title }}</div>
                <div class="highlight-detail">{{ h.detail }}</div>
              </div>
            </div>
          </div>
          <div v-else class="report-empty">这一周比较安静，下一周留一点记录给未来的自己。</div>
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
          <div v-else class="report-empty">本周没有可归属到科目的练习记录。</div>
        </section>
      </div>

      <section class="report-section">
        <div class="report-section-head">
          <h3>下周，先做这几件事</h3>
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
          <div v-if="!data.nextWeek.length" class="report-empty">下周保持现在的节奏就好。</div>
        </div>
      </section>

      <footer class="report-foot">
        <span>OpenStudy · 学习周报</span>
        <span>{{ data.range.start }} - {{ data.range.end }}</span>
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
      backgroundColor: '#ffffff',
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
  max-width: 980px;
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
  gap: 10px;
}

.weekly-toolbar-hint {
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.back-btn {
  height: 30px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.weekly-loading {
  height: 480px;
  border-radius: var(--os-radius, 12px);
  background: #fff;
}

.weekly-empty {
  padding: 64px 24px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
  text-align: center;
}

.weekly-empty-mark {
  display: inline-grid;
  width: 44px;
  height: 44px;
  margin-bottom: 14px;
  place-items: center;
  border-radius: var(--os-radius-sm, 8px);
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 16px;
  font-weight: 600;
}

.weekly-empty h3 {
  margin: 0 0 6px;
  color: var(--os-text, #0f1115);
  font-size: 16px;
  font-weight: 600;
}

.weekly-empty p {
  margin: 0 auto 18px;
  max-width: 400px;
  color: var(--os-text-3, #81858c);
  font-size: 12px;
  line-height: 1.7;
}

.report {
  padding: 22px 26px 18px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius, 12px);
  background: #fff;
}

.report-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
}

.report-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.report-title-row h2 {
  margin: 0;
  color: var(--os-text, #0f1115);
  font-size: 16px;
  font-weight: 600;
}

.report-range {
  color: var(--os-text-3, #81858c);
  font-size: 12px;
}

.report-range-tag {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.report-sub {
  margin: 5px 0 0;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.report-generated {
  flex: none;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.report-headline {
  margin: 16px 0 4px;
  color: var(--os-text, #0f1115);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.5;
}

.report-note {
  margin: 0 0 6px;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.report-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 16px;
}

.report-stat {
  padding: 12px 14px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius-sm, 8px);
  background: #f9fafb;
}

.report-stat-label {
  display: block;
  color: var(--os-text-3, #81858c);
  font-size: 11px;
}

.report-stat-value {
  margin-top: 4px;
  color: var(--os-text, #0f1115);
  font-size: 23px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.report-stat-value i {
  margin-left: 2px;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
  font-style: normal;
  font-weight: 400;
}

.report-stat-sub {
  display: block;
  margin-top: 3px;
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.report-section {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
}

.report-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}

.report-section-head h3 {
  margin: 0;
  color: var(--os-text, #0f1115);
  font-size: 13px;
  font-weight: 600;
}

.report-section-head span {
  color: var(--os-text-4, #adb2b8);
  font-size: 10px;
}

.report-bars {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 6px;
  align-items: end;
  height: 116px;
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
  position: absolute;
  bottom: 100%;
  left: 50%;
  margin-bottom: 3px;
  transform: translateX(-50%);
  color: var(--os-text-3, #81858c);
  font-size: 9px;
  white-space: nowrap;
}

.report-bar-track {
  display: flex;
  width: 100%;
  height: 72px;
  align-items: flex-end;
  justify-content: center;
}

.report-bar-fill {
  position: relative;
  width: 18px;
  max-width: 60%;
  border-radius: 3px 3px 1px 1px;
  background: #cbd5e1;
  transition: height 0.4s ease;
}

.report-bar-fill.is-peak {
  background: var(--os-accent, #4176e6);
}

.report-bar-day {
  color: var(--os-text-3, #81858c);
  font-size: 10px;
}

.report-bar-date {
  color: var(--os-text-4, #adb2b8);
  font-size: 9px;
}

.report-columns {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 24px;
}

.highlight-list,
.next-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.highlight-item {
  display: flex;
  gap: 9px;
  padding: 9px 10px;
  border-radius: var(--os-radius-sm, 8px);
  background: #f9fafb;
}

.highlight-index {
  flex: none;
  color: var(--os-text-4, #adb2b8);
  font-size: 10px;
  font-weight: 600;
}

.highlight-title,
.next-title {
  color: var(--os-text, #0f1115);
  font-size: 12px;
  font-weight: 500;
}

.highlight-detail,
.next-detail {
  margin-top: 2px;
  color: var(--os-text-3, #81858c);
  font-size: 11px;
  line-height: 1.55;
}

.report-empty {
  padding: 12px 0;
  color: var(--os-text-4, #adb2b8);
  font-size: 11px;
}

.subject-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.subject-row-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.subject-name {
  color: var(--os-text-2, #353638);
  font-size: 12px;
}

.subject-value {
  color: var(--os-text, #0f1115);
  font-size: 12px;
  font-weight: 600;
}

.subject-track {
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: #f1f3f5;
}

.subject-fill {
  height: 100%;
  border-radius: inherit;
  background: var(--os-accent, #4176e6);
}

.subject-meta {
  margin-top: 3px;
  color: var(--os-text-4, #adb2b8);
  font-size: 9px;
}

.next-item {
  display: flex;
  gap: 10px;
  padding: 9px 11px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  border-radius: var(--os-radius-sm, 8px);
}

.next-index {
  display: grid;
  width: 18px;
  height: 18px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: var(--os-bg-subtle, #f5f6f7);
  color: var(--os-text-3, #81858c);
  font-size: 9px;
  font-weight: 600;
}

.report-foot {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
  padding-top: 12px;
  border-top: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.04));
  color: var(--os-text-4, #adb2b8);
  font-size: 10px;
}

@media (max-width: 720px) {
  .report {
    padding: 18px 16px 14px;
  }
  .report-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .report-columns {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>

