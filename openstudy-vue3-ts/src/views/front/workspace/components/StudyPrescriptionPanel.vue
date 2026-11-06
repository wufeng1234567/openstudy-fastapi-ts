<!--
  学习处方
  ============================================================================
  资料体检负责「看出问题」，原文阅读负责「看清内容」，学习处方负责「接下来怎么学」。

  它不是再生成一份复习卡 / 讲义文件，而是把资料排成按天执行的计划：
    · 用户先选目标、周期和每天可用时间；
    · LLM 根据体检结果和章节情况排出每天的任务；
    · 每个任务都带原文定位，可以勾完成；
    · 错题/薄弱点可以继续回到原文，计划支持复诊对比。
-->
<template>
  <div class="rp-panel">
    <div v-loading="loading" class="rp-body">
      <div class="rp-intro">
        <div>
          <div class="rp-eyebrow">学习处方</div>
          <h3 class="rp-title">把这份资料，排成你每天能执行的学习计划</h3>
          <p class="rp-sub">
            它不会只给你一份文件：而是告诉你今天读哪一节、做几道题、什么时候复习，做完还能复诊。
          </p>
        </div>
        <div v-if="baseline" class="rp-baseline">
          <span>体检基线</span>
          <b>{{ baseline.score ?? '—' }}</b>
          <small>{{ baseline.issueCount ?? 0 }} 项待处理</small>
        </div>
      </div>

      <div class="rp-setup">
        <div class="rp-field">
          <label>学习目标</label>
          <div class="rp-seg">
            <button v-for="item in goals" :key="item.key" type="button"
              :class="{ 'is-active': goal === item.key }" @click="goal = item.key">
              {{ item.label }}
            </button>
          </div>
        </div>
        <div class="rp-field">
          <label>计划周期</label>
          <div class="rp-seg">
            <button v-for="n in [7, 14, 30]" :key="n" type="button"
              :class="{ 'is-active': days === n }" @click="days = n">{{ n }} 天</button>
          </div>
        </div>
        <div class="rp-field">
          <label>每天可用</label>
          <div class="rp-seg">
            <button v-for="n in [20, 30, 45]" :key="n" type="button"
              :class="{ 'is-active': dailyMinutes === n }" @click="dailyMinutes = n">{{ n }} 分钟</button>
          </div>
        </div>
        <div class="rp-field rp-field--wide">
          <label>额外要求（可选）</label>
          <el-input v-model="instruction" maxlength="800" show-word-limit clearable
            placeholder="例如：先补第 2 章；考前只看高频考点；每天最多做 5 道题。" />
        </div>
        <el-button type="primary" :loading="generating" :disabled="generating" @click="generate">
          {{ generating ? 'AI 正在排计划…' : '生成学习处方' }}
        </el-button>
        <el-button v-if="plan" :disabled="generating" @click="resetPlan">重新生成</el-button>
      </div>

      <div v-if="error" class="rp-error">{{ error }}</div>

      <div v-if="generating" class="rp-empty rp-empty--loading">
        <div class="rp-pulse"></div>
        <b>AI 正在根据体检结果排学习顺序</b>
        <span>它会先看每个章节的内容量、练习情况和薄弱点，再排成每天能完成的任务。</span>
      </div>

      <div v-else-if="!plan" class="rp-empty">
        <div class="rp-empty__icon">＋</div>
        <b>还没有学习处方</b>
        <span>选好目标和时间，AI 会把这份资料排成按天执行的学习任务。</span>
      </div>

      <template v-else>
        <div class="rp-plan-head">
          <div>
            <h4>{{ plan.title }}</h4>
            <p>{{ plan.summary }}</p>
          </div>
          <div class="rp-plan-head__right">
            <div class="rp-progress">
              <div class="rp-progress__top">
                <span>计划进度</span>
                <b>{{ doneCount }} / {{ totalTasks }}</b>
              </div>
              <div class="rp-progress__bar"><i :style="{ width: `${progressPercent}%` }"></i></div>
            </div>
            <el-dropdown trigger="click" class="rp-export" @command="exportPrescription">
              <el-button size="small" :loading="exporting">导出处方</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="pdf">导出 PDF</el-dropdown-item>
                  <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
                  <el-dropdown-item command="md">导出 Markdown</el-dropdown-item>
                  <el-dropdown-item command="txt">导出 TXT</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="rp-days">
          <article v-for="day in plan.days" :key="day.day" class="rp-day"
            :class="{ 'is-today': todayDay === day.day, 'is-done': isDayDone(day) }">
            <div class="rp-day__head">
              <span class="rp-day__no">DAY {{ day.day }}</span>
              <b>{{ day.theme }}</b>
              <span class="rp-day__minutes">{{ day.minutes }} 分钟</span>
              <span v-if="isDayDone(day)" class="rp-day__done">已完成</span>
            </div>
            <div class="rp-day__tasks">
              <div v-for="(task, taskIndex) in day.tasks" :key="`${day.day}-${taskIndex}`"
                class="rp-task" :class="{ 'is-done': isTaskDone(day, taskIndex) }">
                <button type="button" class="rp-check" :aria-label="isTaskDone(day, taskIndex) ? '标记未完成' : '标记完成'"
                  @click="toggleTask(day, taskIndex)">
                  {{ isTaskDone(day, taskIndex) ? '✓' : '' }}
                </button>
                <span class="rp-task__type" :class="`is-${task.type}`">{{ taskTypeLabel(task.type) }}</span>
                <div class="rp-task__main">
                  <LatexRenderer class="rp-task__title" :content="task.title" />
                  <LatexRenderer class="rp-task__detail" :content="task.detail" />
                  <div class="rp-task__meta">
                    <span>{{ task.sectionTitle }}</span>
                    <span>·</span>
                    <span>{{ task.minutes }} 分钟</span>
                    <template v-if="task.questionCount">
                      <span>·</span>
                      <span>{{ task.questionCount }} 道题</span>
                    </template>
                  </div>
                </div>
                <div class="rp-task__ops">
                  <button type="button" @click="locateTask(task)">查看原文</button>
                  <button v-if="task.type === 'practice'" type="button" @click="askPractice(task)">去练习</button>
                </div>
              </div>
            </div>
          </article>
        </div>

        <div v-if="plan.checkpoints?.length" class="rp-checkpoints">
          <div class="rp-checkpoints__label">复诊节点</div>
          <span v-for="(item, index) in plan.checkpoints" :key="index">{{ item }}</span>
        </div>

        <div class="rp-footer">
          <span class="rp-footer__hint">任务完成后勾选；复诊会重新读取这份资料的体检结果，和你开处方时的基线对比。</span>
          <div class="rp-footer__actions">
            <el-button :loading="rechecking" @click="recheck">复诊</el-button>
          </div>
        </div>
        <div v-if="recheck" class="rp-recheck">
          <b>复诊结果</b>
          <span>综合分 {{ baseline?.score ?? '—' }} → {{ recheck.score ?? '—' }}</span>
          <span>待处理问题 {{ baseline?.issueCount ?? 0 }} → {{ recheck.issueCount ?? 0 }}</span>
          <span v-if="recheck.grade?.label">当前状态：{{ recheck.grade.label }}</span>
        </div>
      </template>
    </div>

    <div class="rp-footer-bar">
      <span>先诊断，再开方；处方不是文件，是接下来每天的学习动作。</span>
      <el-button text @click="closePanel">关闭</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { saveAs } from 'file-saver'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import {
  exportStudyPrescription,
  generateStudyPrescription,
  getDocumentHealth,
  type StudyPrescriptionParams
} from '@/api/ai/workspace'

defineOptions({ name: 'StudyPrescriptionPanel' })

interface PrescriptionDoc {
  docId: number
  fileName?: string
}

const emit = defineEmits<{
  (e: 'locate', doc: PrescriptionDoc, section: any): void
  (e: 'ask', doc: PrescriptionDoc, issue: any): void
  (e: 'close'): void
}>()

const goals: Array<{ key: StudyPrescriptionParams['goal']; label: string }> = [
  { key: 'foundation', label: '打基础' },
  { key: 'exam', label: '考前冲刺' },
  { key: 'weakness', label: '补薄弱章节' }
]

const loading = ref(false)
const generating = ref(false)
const exporting = ref(false)
const rechecking = ref(false)
const error = ref('')
const currentDoc = ref<PrescriptionDoc | null>(null)
const report = ref<any>(null)
const plan = ref<any>(null)
const baseline = ref<any>(null)
const recheck = ref<any>(null)
const progress = ref<Record<string, boolean>>({})
const goal = ref<StudyPrescriptionParams['goal']>('exam')
const days = ref(7)
const dailyMinutes = ref(30)
const instruction = ref('')
let loadSeq = 0

const storageKey = computed(() =>
  currentDoc.value?.docId ? `os_study_prescription_${currentDoc.value.docId}` : ''
)

const totalTasks = computed(() =>
  (plan.value?.days || []).reduce((sum: number, day: any) => sum + (day.tasks?.length || 0), 0)
)
const doneCount = computed(() =>
  (plan.value?.days || []).reduce(
    (sum: number, day: any) =>
      sum + (day.tasks || []).filter((_: any, index: number) => isTaskDone(day, index)).length,
    0
  )
)
const progressPercent = computed(() =>
  totalTasks.value ? Math.round((doneCount.value / totalTasks.value) * 100) : 0
)

const todayDay = computed(() => {
  const first = (plan.value?.days || []).find((day: any) => !isDayDone(day))
  return first?.day || 0
})

function taskTypeLabel(type: string): string {
  return {
    read: '精读',
    practice: '练习',
    review: '复习',
    recheck: '复测'
  }[type] || '任务'
}

function taskKey(day: any, index: number): string {
  return `${day.day}-${index}`
}

function isTaskDone(day: any, index: number): boolean {
  return !!progress.value[taskKey(day, index)]
}

function isDayDone(day: any): boolean {
  return (day.tasks || []).length > 0 && (day.tasks || []).every((_: any, index: number) => isTaskDone(day, index))
}

function toggleTask(day: any, index: number) {
  const key = taskKey(day, index)
  progress.value = { ...progress.value, [key]: !progress.value[key] }
  saveState()
}

function saveState() {
  if (!storageKey.value || !plan.value) return
  try {
    localStorage.setItem(storageKey.value, JSON.stringify({
      plan: plan.value,
      baseline: baseline.value,
      progress: progress.value
    }))
  } catch {
    /* localStorage 不可用时不影响当前会话 */
  }
}

function loadState() {
  if (!storageKey.value) return false
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (!raw) return false
    const saved = JSON.parse(raw)
    if (!saved?.plan?.days?.length) return false
    plan.value = saved.plan
    baseline.value = saved.baseline || null
    progress.value = saved.progress || {}
    return true
  } catch {
    return false
  }
}

function resetPlan() {
  plan.value = null
  baseline.value = null
  recheck.value = null
  progress.value = {}
  if (storageKey.value) {
    try { localStorage.removeItem(storageKey.value) } catch { /* ignore */ }
  }
}

async function loadHealth() {
  if (!currentDoc.value?.docId) return
  const res: any = await getDocumentHealth(currentDoc.value.docId)
  if (res.code !== 200) throw new Error(res.msg || '读取资料体检失败')
  report.value = res.data
}

async function generate() {
  if (!currentDoc.value?.docId || generating.value) return
  generating.value = true
  error.value = ''
  recheck.value = null
  try {
    const res = await generateStudyPrescription(currentDoc.value.docId, {
      days: days.value,
      dailyMinutes: dailyMinutes.value,
      goal: goal.value,
      sectionIndexes: (report.value?.sections || [])
        .filter((s: any) => s.title !== '开篇')
        .map((s: any) => Number(s.index)),
      instruction: instruction.value
    })
    if (res.code !== 200) throw new Error(res.msg || '生成学习处方失败')
    plan.value = res.data?.plan
    baseline.value = res.data?.baseline || null
    progress.value = {}
    saveState()
    ElMessage.success('学习处方已生成')
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    generating.value = false
  }
}

async function exportPrescription(format: 'pdf' | 'docx' | 'md' | 'txt') {
  const doc = currentDoc.value
  if (!doc?.docId || !plan.value || exporting.value) return
  const ext = format
  exporting.value = true
  try {
    const planForExport = {
      ...plan.value,
      days: (plan.value.days || []).map((day: any) => ({
        ...day,
        tasks: (day.tasks || []).map((task: any, index: number) => ({
          ...task,
          done: isTaskDone(day, index)
        }))
      }))
    }
    const res: any = await exportStudyPrescription(doc.docId, {
      format,
      plan: planForExport,
      meta: {
        docName: doc.fileName || '',
        goal: goal.value,
        goalLabel: goals.find((item) => item.key === goal.value)?.label || goal.value,
        days: days.value,
        dailyMinutes: dailyMinutes.value
      }
    })
    const blob = res instanceof Blob ? res : new Blob([res])
    if (!blob.size) throw new Error('导出文件为空')
    const stem = String(doc.fileName || '资料').replace(/\.[^.]+$/, '') || '资料'
    saveAs(blob, `${stem}-学习处方.${ext}`)
    ElMessage.success('学习处方已导出')
  } catch (e: any) {
    ElMessage.error('导出学习处方失败：' + (e?.message || e))
  } finally {
    exporting.value = false
  }
}

function locateTask(task: any) {
  if (!currentDoc.value) return
  const section = (report.value?.sections || []).find(
    (s: any) => Number(s.index) === Number(task.sectionIndex)
  )
  if (!section) {
    ElMessage.info('这条任务在原文里没有找到对应章节位置，可以到原文阅读里按标题查找。')
    return
  }
  emit('locate', currentDoc.value, section)
}

function askPractice(task: any) {
  if (!currentDoc.value) return
  emit('ask', currentDoc.value, {
    fixAction: 'questions',
    title: task.title,
    sectionTitle: task.sectionTitle
  })
}

async function recheckPrescription() {
  if (!currentDoc.value?.docId || rechecking.value) return
  rechecking.value = true
  try {
    const res: any = await getDocumentHealth(currentDoc.value.docId)
    if (res.code !== 200) throw new Error(res.msg || '复诊失败')
    recheck.value = res.data
    ElMessage.success('复诊完成')
  } catch (e: any) {
    ElMessage.error('复诊失败：' + (e?.message || e))
  } finally {
    rechecking.value = false
  }
}

function closePanel() {
  emit('close')
}

async function open(doc: PrescriptionDoc) {
  const seq = ++loadSeq
  currentDoc.value = doc
  loading.value = true
  error.value = ''
  report.value = null
  plan.value = null
  baseline.value = null
  recheck.value = null
  progress.value = {}
  goal.value = 'exam'
  days.value = 7
  dailyMinutes.value = 30
  instruction.value = ''
  try {
    await loadHealth()
    if (seq === loadSeq) loadState()
  } catch (e: any) {
    if (seq === loadSeq) error.value = e?.message || String(e)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.rp-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.rp-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.rp-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 12px;
}

.rp-eyebrow {
  margin-bottom: 3px;
  color: #2563eb;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.rp-title {
  margin: 0;
  color: #111827;
  font-size: 18px;
  line-height: 1.35;
}

.rp-sub {
  max-width: 700px;
  margin: 5px 0 0;
  color: #6b7280;
  font-size: 11.5px;
  line-height: 1.6;
}

.rp-baseline {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  padding: 7px 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.rp-baseline span,
.rp-baseline small {
  color: #9ca3af;
  font-size: 10px;
}

.rp-baseline b {
  color: #1d4ed8;
  font-size: 19px;
}

.rp-setup {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
  padding: 11px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 9px;
  background: #fff;
}

.rp-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.rp-field--wide {
  flex: 1;
  min-width: 260px;
}

.rp-field label {
  color: #6b7280;
  font-size: 10.5px;
  font-weight: 600;
}

.rp-seg {
  display: flex;
  gap: 3px;
}

.rp-seg button {
  padding: 5px 9px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  color: #6b7280;
  font-size: 10.5px;
  cursor: pointer;
}

.rp-seg button:hover {
  border-color: #93c5fd;
}

.rp-seg button.is-active {
  border-color: #2563eb;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
}

.rp-error {
  margin-bottom: 10px;
  padding: 9px 12px;
  border: 1px solid #fecaca;
  border-radius: 8px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 11.5px;
}

.rp-empty {
  display: flex;
  min-height: 260px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px dashed #dbeafe;
  border-radius: 9px;
  background: #fbfdff;
  color: #6b7280;
  text-align: center;
}

.rp-empty__icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  font-size: 20px;
}

.rp-empty b {
  color: #374151;
  font-size: 13px;
}

.rp-empty span {
  max-width: 460px;
  font-size: 11px;
  line-height: 1.6;
}

.rp-empty--loading {
  border-style: solid;
  background: #f8fbff;
}

.rp-pulse {
  width: 18px;
  height: 18px;
  border: 2px solid #bfdbfe;
  border-top-color: #2563eb;
  border-radius: 50%;
  animation: rp-spin 0.9s linear infinite;
}

@keyframes rp-spin { to { transform: rotate(360deg); } }

.rp-plan-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 10px;
}

.rp-plan-head__right {
  display: flex;
  flex: none;
  align-items: flex-end;
  gap: 10px;
}

.rp-export :deep(.el-button) {
  border-color: #dbe4ff;
  color: #4f6bed;
  background: #f8faff;
}

.rp-plan-head h4 {
  margin: 0;
  color: #111827;
  font-size: 16px;
}

.rp-plan-head p {
  margin: 4px 0 0;
  color: #6b7280;
  font-size: 11.5px;
}

.rp-progress {
  width: 190px;
  flex: none;
}

.rp-progress__top {
  display: flex;
  justify-content: space-between;
  color: #9ca3af;
  font-size: 10px;
}

.rp-progress__top b {
  color: #1d4ed8;
}

.rp-progress__bar {
  height: 5px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #e5e7eb;
}

.rp-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2563eb;
  transition: width 0.2s ease;
}

.rp-days {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.rp-day {
  border: 1px solid #e5e7eb;
  border-radius: 9px;
  background: #fff;
  overflow: hidden;
}

.rp-day.is-today {
  border-color: #bfdbfe;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.05);
}

.rp-day.is-done {
  background: #fbfefc;
}

.rp-day__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #f0f2f5;
  background: #fbfdff;
}

.rp-day__no {
  color: #2563eb;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.rp-day__head b {
  color: #1f2937;
  font-size: 12px;
}

.rp-day__minutes {
  margin-left: auto;
  color: #9ca3af;
  font-size: 10px;
}

.rp-day__done {
  color: #059669;
  font-size: 10px;
}

.rp-task {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  border-top: 1px solid #f6f7f9;
}

.rp-task:first-child {
  border-top: 0;
}

.rp-task.is-done {
  opacity: 0.62;
}

.rp-task.is-done .rp-task__title {
  text-decoration: line-through;
}

.rp-check {
  display: grid;
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 1px;
  place-items: center;
  border: 1.5px solid #cbd5e1;
  border-radius: 50%;
  background: #fff;
  color: #fff;
  font-size: 10px;
  cursor: pointer;
}

.rp-task.is-done .rp-check {
  border-color: #10b981;
  background: #10b981;
}

.rp-task__type {
  flex: none;
  margin-top: 2px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
}

.rp-task__type.is-read { background: #eff6ff; color: #2563eb; }
.rp-task__type.is-practice { background: #fff7ed; color: #c2410c; }
.rp-task__type.is-review { background: #ecfdf5; color: #047857; }
.rp-task__type.is-recheck { background: #f5f3ff; color: #6d28d9; }

.rp-task__main {
  min-width: 0;
  flex: 1;
}

.rp-task__title {
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}

.rp-task__detail {
  margin: 2px 0 0;
  color: #6b7280;
  font-size: 10.5px;
  line-height: 1.55;
}

.rp-task__meta {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 3px;
  color: #9ca3af;
  font-size: 9.5px;
}

.rp-task__ops {
  display: flex;
  flex: none;
  flex-direction: column;
  gap: 4px;
  margin-left: 6px;
}

.rp-task__ops button {
  padding: 2px 6px;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 9.5px;
  cursor: pointer;
}

.rp-task__ops button:hover {
  text-decoration: underline;
}

.rp-checkpoints {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px 10px;
  margin-top: 10px;
  padding: 8px 11px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  color: #6b7280;
  font-size: 10.5px;
}

.rp-checkpoints__label {
  color: #1e3a5f;
  font-weight: 700;
}

.rp-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.rp-footer__hint {
  color: #9ca3af;
  font-size: 10px;
  line-height: 1.5;
}

.rp-recheck {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin-top: 9px;
  padding: 9px 12px;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  background: #f0fdf4;
  color: #047857;
  font-size: 10.5px;
}

.rp-footer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 9px;
  border-top: 1px solid #eef2f7;
  color: #9ca3af;
  font-size: 10px;
}
</style>
