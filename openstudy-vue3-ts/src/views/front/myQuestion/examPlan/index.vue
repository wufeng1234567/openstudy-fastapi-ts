<template>
  <div class="exam-page">
    <div class="exam-topbar">
      <el-button text class="back-btn" @click="goStats">
        <el-icon><ArrowLeft /></el-icon>
        学习统计
      </el-button>
      <span class="exam-topbar-hint">按你的真实薄弱点倒排，不是模板</span>
    </div>

    <div class="exam-layout">
      <aside class="exam-form">
        <div class="exam-form-title">
          <span class="exam-form-mark">EXAM</span>
          <h2>你的考试，<br />倒着排。</h2>
          <p>告诉系统哪天考、每天能学多久，剩下的交给它。</p>
        </div>

        <div class="form-item">
          <label>考试名称</label>
          <el-input v-model="form.examName" placeholder="如：专升本英语 / 期末考试" maxlength="30" />
        </div>

        <div class="form-item">
          <label>考试日期</label>
          <el-date-picker
            v-model="form.examDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择考试当天"
            :disabled-date="disablePast"
            style="width: 100%"
          />
        </div>

        <div class="form-item">
          <label>科目</label>
          <el-select v-model="form.subject" clearable placeholder="全部科目（推荐）" style="width: 100%">
            <el-option v-for="s in subjects" :key="s" :label="s" :value="s" />
          </el-select>
        </div>

        <div class="form-item">
          <label>每天可学 <b>{{ form.dailyMinutes }} 分钟</b></label>
          <el-slider v-model="form.dailyMinutes" :min="20" :max="180" :step="10" :show-tooltip="false" />
        </div>

        <el-button type="primary" class="generate-btn" :loading="loading" @click="generate">
          生成倒计时路线图
        </el-button>
        <p class="form-note">系统会读取你的逐题诊断结果，题不够时会自动收缩任务，不凑数。</p>
      </aside>

      <main class="exam-main">
        <div v-if="!plan" class="exam-intro">
          <div class="intro-eyebrow">BEFORE YOU START</div>
          <h1>别再从「明天开始」开始。</h1>
          <p>输入考试日期，系统把剩下的日子拆成三个阶段，每天告诉你先做哪几道题。</p>
          <div class="intro-phases">
            <div class="intro-phase is-red">
              <span>01</span>
              <h3>补地基</h3>
              <p>反复失守的题，先补前置概念，而不是继续刷。</p>
            </div>
            <div class="intro-phase is-amber">
              <span>02</span>
              <h3>还债 + 巩固</h3>
              <p>把过了复习窗口的题补上，再用同科目题确认迁移。</p>
            </div>
            <div class="intro-phase is-blue">
              <span>03</span>
              <h3>全真模拟</h3>
              <p>按考试节奏做整套，练取舍，不再开新题。</p>
            </div>
          </div>
        </div>

        <div v-else-if="!plan.hasData" class="exam-empty">
          <div class="exam-empty-mark">!</div>
          <h3>路线图还缺依据</h3>
          <p>{{ plan.message || '先做几道题，系统才能按你的薄弱点排计划。' }}</p>
          <el-button type="primary" @click="goPractice">去题库练习</el-button>
        </div>

        <template v-else>
          <section class="exam-summary">
            <div class="countdown">
              <span class="countdown-num">{{ plan.exam.daysLeft }}</span>
              <span class="countdown-label">天后考试</span>
            </div>
            <div class="summary-main">
              <h2>{{ plan.exam.name }}</h2>
              <p>{{ plan.exam.date }} · 每天 {{ plan.exam.dailyMinutes }} 分钟 · {{ plan.exam.subject || '全部科目' }}</p>
            </div>
            <div class="summary-stats">
              <div><b>{{ plan.overview?.overallAccuracy }}%</b><span>当前正确率</span></div>
              <div><b>{{ plan.overview?.needsAttention }}</b><span>需要关注</span></div>
              <div><b>{{ plan.overview?.overdueCount }}</b><span>欠复习</span></div>
            </div>
          </section>

          <section class="phase-track">
            <div v-for="(phase, index) in plan.phases" :key="phase.key" class="phase-card" :style="{ '--phase-color': phase.color }">
              <div class="phase-head">
                <span class="phase-index">0{{ index + 1 }}</span>
                <span class="phase-days">{{ phase.days }} 天</span>
              </div>
              <h3>{{ phase.title }}</h3>
              <p>{{ phase.goal }}</p>
              <div class="phase-range">{{ phase.start.slice(5) }} → {{ phase.end.slice(5) }}</div>
            </div>
          </section>

          <section class="plan-days">
            <div class="plan-days-head">
              <h3>每天做什么</h3>
              <span>{{ plan.days.length }} 天 · 点击题目直接开练</span>
            </div>
            <div v-for="day in plan.days" :key="day.date" class="day-row" :class="`is-${day.phase}`">
              <div class="day-date">
                <b>{{ day.date.slice(5) }}</b>
                <span>{{ weekday(day.date) }}</span>
              </div>
              <div class="day-body">
                <div class="day-theme">
                  {{ day.theme }}
                  <span class="day-minutes">{{ day.minutes }} 分钟</span>
                </div>
                <div
                  v-for="(task, ti) in day.tasks"
                  :key="ti"
                  class="task-row"
                  :class="{ 'is-clickable': task.questionId > 0 }"
                  role="button"
                  :tabindex="task.questionId > 0 ? 0 : -1"
                  @click="openTask(task)"
                  @keyup.enter="openTask(task)"
                >
                  <span class="task-type">{{ taskTypeLabel(task.type) }}</span>
                  <div class="task-body">
                    <div class="task-title" v-html="renderQuestionContent(task.title)"></div>
                    <div class="task-detail">{{ task.detail }}</div>
                  </div>
                  <span class="task-minutes">{{ task.minutes }}′</span>
                </div>
              </div>
            </div>
          </section>

          <section class="exam-advice">
            <h3>使用建议</h3>
            <div v-for="(advice, i) in plan.advice" :key="i" class="advice-row">
              <span>{{ i + 1 }}</span>
              <p>{{ advice }}</p>
            </div>
          </section>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { getExamPlan, getLearningLoop, type ExamPlanResult, type ExamPlanTask } from '@/api/userStats/userStats'
import { renderQuestionContent } from '@/utils/latex'

defineOptions({ name: 'ExamPlan' })

const router = useRouter()
const loading = ref(false)
const plan = ref<ExamPlanResult | null>(null)
const subjects = ref<string[]>([])

function defaultExamDate() {
  const d = new Date(Date.now() + 30 * 24 * 3600 * 1000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const form = reactive({
  examName: '期末考试',
  examDate: defaultExamDate(),
  subject: '',
  dailyMinutes: 40,
})

function disablePast(date: Date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}

const weekday = (value: string) => '日一二三四五六'[new Date(`${value}T00:00:00`).getDay()]

function taskTypeLabel(type: string) {
  const map: Record<string, string> = {
    question: '题目',
    concept: '概念',
    paper: '模拟',
    practice: '练习',
    review: '回看',
    rest: '休息',
  }
  return map[type] || '任务'
}

async function loadSubjects() {
  try {
    const res: any = await getLearningLoop()
    if (res.code === 200) {
      subjects.value = (res.data?.healthMap || []).map((n: any) => n.subject).filter(Boolean)
    }
  } catch (e) {
    // 科目下拉只是辅助，失败不影响主流程
  }
}

async function generate() {
  if (!form.examDate) {
    ElMessage.warning('先选一个考试日期')
    return
  }
  loading.value = true
  try {
    const res: any = await getExamPlan({
      examName: form.examName || '我的考试',
      examDate: form.examDate,
      subject: form.subject,
      dailyMinutes: form.dailyMinutes,
    })
    if (res.code === 200) {
      plan.value = res.data
    } else {
      ElMessage.error(res.msg || '生成失败')
    }
  } catch (e: any) {
    ElMessage.error('生成路线图失败，请重试')
    console.warn('[考前路线图] 生成失败', e)
  } finally {
    loading.value = false
  }
}

function openTask(task: ExamPlanTask) {
  if (!task?.questionId) return
  router.push({
    path: '/front/myQuestion/wrongQuestion',
    query: { questionId: String(task.questionId), from: 'examPlan' },
  })
}

const goStats = () => router.push('/front/myQuestion/myStats')
const goPractice = () => router.push('/front/questionPractice')

onMounted(loadSubjects)
</script>

<style scoped>
.exam-page {
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 20px 60px;
}

.exam-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.back-btn {
  color: #64748b;
  font-size: 13px;
}

.exam-topbar-hint {
  color: #9ca3af;
  font-size: 11px;
}

.exam-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}

.exam-form {
  position: sticky;
  top: 16px;
  padding: 24px 22px;
  border: 1px solid #e8edf5;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 10px 36px rgba(15, 23, 42, 0.05);
}

.exam-form-mark {
  color: #2563eb;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.exam-form-title h2 {
  margin: 10px 0 8px;
  color: #0f172a;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.3;
}

.exam-form-title p {
  margin: 0 0 20px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.65;
}

.form-item {
  margin-bottom: 16px;
}

.form-item label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
}

.form-item label b {
  color: #2563eb;
  font-size: 11px;
}

.generate-btn {
  width: 100%;
  height: 40px;
  margin-top: 6px;
  border-radius: 10px;
}

.form-note {
  margin: 12px 0 0;
  color: #b0b7c3;
  font-size: 10px;
  line-height: 1.6;
}

.exam-main {
  min-width: 0;
}

.exam-intro {
  padding: 48px 44px;
  border: 1px solid #e8edf5;
  border-radius: 20px;
  background:
    radial-gradient(circle at 92% 0%, rgba(59, 130, 246, 0.1), transparent 34%),
    #fff;
}

.intro-eyebrow {
  color: #2563eb;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.18em;
}

.exam-intro h1 {
  margin: 12px 0 10px;
  color: #0f172a;
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.04em;
}

.exam-intro > p {
  max-width: 520px;
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.75;
}

.intro-phases {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 30px;
}

.intro-phase {
  padding: 16px;
  border-radius: 12px;
  background: #f8fafc;
}

.intro-phase span {
  color: #94a3b8;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.intro-phase h3 {
  margin: 8px 0 6px;
  color: #1f2937;
  font-size: 13px;
}

.intro-phase p {
  margin: 0;
  color: #64748b;
  font-size: 10px;
  line-height: 1.6;
}

.intro-phase.is-red { border-top: 3px solid #dc2626; }
.intro-phase.is-amber { border-top: 3px solid #d97706; }
.intro-phase.is-blue { border-top: 3px solid #2563eb; }

.exam-empty {
  padding: 60px 30px;
  border: 1px solid #e8edf5;
  border-radius: 20px;
  background: #fff;
  text-align: center;
}

.exam-empty-mark {
  display: inline-grid;
  width: 48px;
  height: 48px;
  margin-bottom: 14px;
  place-items: center;
  border-radius: 14px;
  background: #fff7e6;
  color: #d97706;
  font-size: 20px;
  font-weight: 800;
}

.exam-empty h3 {
  margin: 0 0 8px;
  color: #1f2937;
  font-size: 17px;
}

.exam-empty p {
  margin: 0 auto 18px;
  max-width: 440px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.7;
}

.exam-summary {
  display: flex;
  align-items: center;
  gap: 22px;
  padding: 24px 26px;
  border-radius: 18px;
  background:
    radial-gradient(circle at 92% 12%, rgba(96, 165, 250, 0.3), transparent 30%),
    linear-gradient(135deg, #111827, #1e3a5f 65%, #1d4ed8);
  color: #fff;
}

.countdown {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 106px;
  padding-right: 22px;
  border-right: 1px solid rgba(255, 255, 255, 0.18);
}

.countdown-num {
  font-size: 44px;
  font-weight: 800;
  letter-spacing: -0.05em;
  line-height: 1;
}

.countdown-label {
  margin-top: 5px;
  color: #93c5fd;
  font-size: 11px;
}

.summary-main {
  min-width: 0;
  flex: 1;
}

.summary-main h2 {
  margin: 0 0 6px;
  color: #fff;
  font-size: 22px;
  font-weight: 700;
}

.summary-main p {
  margin: 0;
  color: rgba(255, 255, 255, 0.68);
  font-size: 11px;
}

.summary-stats {
  display: flex;
  gap: 20px;
}

.summary-stats div {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.summary-stats b {
  font-size: 20px;
  font-weight: 700;
}

.summary-stats span {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 10px;
}

.phase-track {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 14px;
}

.phase-card {
  padding: 16px;
  border: 1px solid #eef2f7;
  border-top: 3px solid var(--phase-color);
  border-radius: 12px;
  background: #fff;
}

.phase-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.phase-index {
  color: var(--phase-color);
  font-size: 10px;
  font-weight: 800;
}

.phase-days {
  color: #94a3b8;
  font-size: 10px;
}

.phase-card h3 {
  margin: 9px 0 5px;
  color: #1f2937;
  font-size: 14px;
}

.phase-card p {
  margin: 0;
  color: #64748b;
  font-size: 10px;
  line-height: 1.55;
}

.phase-range {
  margin-top: 10px;
  color: #94a3b8;
  font-size: 9px;
}

.plan-days {
  margin-top: 20px;
  padding: 18px;
  border: 1px solid #eef2f7;
  border-radius: 16px;
  background: #fff;
}

.plan-days-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.plan-days-head h3 {
  margin: 0;
  color: #1f2937;
  font-size: 14px;
}

.plan-days-head span {
  color: #94a3b8;
  font-size: 10px;
}

.day-row {
  display: flex;
  gap: 14px;
  padding: 12px 0;
  border-top: 1px solid #f1f5f9;
}

.day-date {
  display: flex;
  width: 52px;
  flex: none;
  flex-direction: column;
  align-items: flex-start;
}

.day-date b {
  color: #1f2937;
  font-size: 13px;
  font-weight: 700;
}

.day-date span {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 10px;
}

.day-body {
  min-width: 0;
  flex: 1;
}

.day-theme {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
  color: #334155;
  font-size: 11px;
  font-weight: 600;
}

.day-minutes {
  color: #94a3b8;
  font-size: 9px;
  font-weight: 400;
}

.task-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 9px;
  border-radius: 8px;
  background: #fbfcfe;
  transition: background 0.15s;
}

.task-row + .task-row {
  margin-top: 5px;
}

.task-row.is-clickable {
  cursor: pointer;
}

.task-row.is-clickable:hover {
  background: #eff6ff;
}

.task-row.is-clickable:hover .task-title {
  color: #2563eb;
}

.task-type {
  flex: none;
  margin-top: 1px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 9px;
}

.task-body {
  min-width: 0;
  flex: 1;
}

.task-title {
  display: -webkit-box;
  overflow: hidden;
  color: #334155;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.5;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.task-title :deep(.katex) {
  font-size: 1em;
}

.task-detail {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 9px;
  line-height: 1.5;
}

.task-minutes {
  flex: none;
  color: #94a3b8;
  font-size: 9px;
}

.exam-advice {
  margin-top: 18px;
  padding: 18px 20px;
  border: 1px dashed #dbeafe;
  border-radius: 14px;
  background: #f8fbff;
}

.exam-advice h3 {
  margin: 0 0 10px;
  color: #1e40af;
  font-size: 12px;
}

.advice-row {
  display: flex;
  gap: 8px;
  color: #475569;
  font-size: 10px;
  line-height: 1.6;
}

.advice-row + .advice-row {
  margin-top: 5px;
}

.advice-row span {
  display: grid;
  width: 16px;
  height: 16px;
  flex: none;
  place-items: center;
  border-radius: 50%;
  background: #dbeafe;
  color: #2563eb;
  font-size: 8px;
  font-weight: 700;
}

.advice-row p {
  margin: 0;
}

@media (max-width: 980px) {
  .exam-layout {
    grid-template-columns: 1fr;
  }
  .exam-form {
    position: static;
  }
  .intro-phases,
  .phase-track {
    grid-template-columns: 1fr;
  }
  .exam-summary {
    flex-wrap: wrap;
  }
}
</style>
