<template>
  <section class="spp">
    <header class="spp__hero">
      <div class="spp__hero-copy">
        <span class="spp__kicker">学习计划</span>
        <h1>{{ plan?.route?.targetTitle ? `目标：${plan.route.targetTitle}` : '今天先学这些' }}</h1>
        <p>{{ plan?.route?.headline || '系统会按你的知识图谱和题库，安排今天能做完的事。' }}</p>
        <div v-if="plan" class="spp__chips">
          <span><b>{{ plan.progress?.doneTasks || 0 }}</b> / {{ plan.progress?.totalTasks || 0 }} 已完成</span>
          <span v-if="todayMinutes"><b>{{ todayMinutes }}</b> 分钟今天</span>
          <span v-if="selectedBanks.length">已纳入 {{ selectedBanks.length }} 个题库</span>
          <span v-if="plan.degraded?.noQuestionSource" class="is-warn">题库暂无资料锚点，不硬连知识页</span>
        </div>
      </div>
      <div class="spp__actions">
        <el-select v-model="kbId" size="small" class="spp__kb" @change="onKbChange">
          <el-option label="不选资料夹 · 只按题库" :value="0" />
          <el-option v-for="kb in kbs" :key="kb.kbId" :label="kb.name" :value="Number(kb.kbId)" />
        </el-select>
        <el-button size="small" plain @click="askAi">问 AI</el-button>
        <el-button size="small" type="primary" @click="openAdjust">{{ plan ? '调整计划' : '生成计划' }}</el-button>
      </div>
    </header>

    <div v-if="plan" class="spp__flow" aria-label="学习闭环">
      <span class="is-done"><i>1</i>知识图谱</span>
      <em>→</em>
      <span class="is-done"><i>2</i>学习计划</span>
      <em>→</em>
      <span :class="{ 'is-done': todayTasks.length }"><i>3</i>今天做什么</span>
      <em>→</em>
      <span :class="{ 'is-done': plan.progress?.doneTasks > 0 }"><i>4</i>做完自动回流</span>
    </div>

    <div v-if="loading" class="spp__loading">
      <el-icon class="is-loading" :size="18"><Loading /></el-icon>
      <span>正在读取你的知识图谱和学习记录…</span>
    </div>

    <template v-else-if="plan">
      <div class="spp__stats">
        <div class="spp__stat">
          <span>知识页</span>
          <b>{{ graph.stats?.pageCount || 0 }}</b>
          <em>已读 {{ readPageCount }}</em>
        </div>
        <div class="spp__stat">
          <span>题库</span>
          <b>{{ graph.stats?.bankCount || 0 }}</b>
          <em>{{ graph.stats?.weakQuestionCount || 0 }} 道薄弱题</em>
        </div>
        <div class="spp__stat">
          <span>计划进度</span>
          <b>{{ plan.progress?.percent || 0 }}%</b>
          <em>{{ plan.progress?.doneMinutes || 0 }} / {{ plan.progress?.plannedMinutes || 0 }} 分钟</em>
        </div>
        <div class="spp__stat">
          <span>今天</span>
          <b>{{ todayTasks.length }}</b>
          <em>{{ todayTasks.length ? `${todayMinutes} 分钟` : '没有安排' }}</em>
        </div>
      </div>

      <div class="spp__main">
        <section class="spp__map-card">
          <header class="spp__section-head">
            <div>
              <h2>知识图谱</h2>
              <p>点知识页看学习状态，点题库看真实薄弱题；计划只使用真实节点。</p>
            </div>
            <span class="spp__section-meta">{{ graph.stats?.pageCount || 0 }} 页 · {{ graph.stats?.bankCount || 0 }} 题库</span>
          </header>
          <StudyMapGraph :nodes="graph.nodes" :edges="graph.edges" :route-page-ids="routePageIds" @select="onGraphSelect" />
          <p v-if="graph.degraded?.noQuestionSource" class="spp__hint">
            当前题库还没有可反查的资料锚点，题库节点独立展示，不会硬连到知识页。
          </p>
        </section>

        <section class="spp__today-card">
          <header class="spp__section-head">
            <div>
              <h2>今天</h2>
              <p>{{ todayLabel }} · 只做真实安排，不把明天冒充成今天。</p>
            </div>
            <span class="spp__section-meta">{{ todayTasks.length }} 项</span>
          </header>
          <div v-if="todayTasks.length" class="spp__today-list">
            <button v-for="task in todayTasks" :key="task.id" type="button" class="spp__task"
              :class="{ 'is-done': task.status === 'done' }" @click="openTask(task)">
              <span class="spp__task-state">{{ task.status === 'done' ? '✓' : task.status === 'current' ? '▶' : '○' }}</span>
              <span class="spp__task-body">
                <b>{{ task.title }}</b>
                <em>{{ task.reason }}</em>
              </span>
              <span class="spp__task-min">{{ task.minutes }}′</span>
            </button>
          </div>
          <div v-else class="spp__today-empty">
            <b>今天没有安排</b>
            <span v-if="nextDay">下一段从 {{ dayLabel(nextDay.date) }} 开始：{{ nextDay.tasks?.[0]?.title || '继续学习' }}</span>
            <span v-else>完成一次阅读或练习后，计划会自动更新。</span>
          </div>
          <button v-if="primaryTask" type="button" class="spp__primary" @click="openTask(primaryTask)">
            开始今天第一项 <span>· {{ primaryTask.minutes }}′</span>
          </button>
        </section>
      </div>

      <section class="spp__timeline">
        <header class="spp__section-head">
          <div>
            <h2>完整安排</h2>
            <p>未完成任务会保留；过去没做的任务会标为“待补”，不会消失。</p>
          </div>
          <span class="spp__section-meta">{{ plan.days?.length || 0 }} 天 · {{ plan.window?.start }} → {{ plan.window?.end }}</span>
        </header>
        <div v-for="day in plan.days || []" :key="day.date" class="spp__day" :class="{ 'is-today': day.date === todayStr }">
          <div class="spp__date">
            <b>{{ dayLabel(day.date) }}</b>
            <span>{{ day.minutes }} 分钟</span>
            <em v-if="day.overloaded">任务较多</em>
          </div>
          <div class="spp__day-tasks">
            <button v-for="task in day.tasks || []" :key="task.id" type="button" class="spp__task spp__task--compact"
              :class="{ 'is-done': task.status === 'done' }" @click="openTask(task)">
              <span class="spp__task-state">{{ task.status === 'done' ? '✓' : task.status === 'current' ? '▶' : '○' }}</span>
              <span class="spp__task-body">
                <b>{{ task.title }}</b>
                <em>{{ task.reason }}</em>
              </span>
              <span class="spp__task-min">{{ task.minutes }}′</span>
            </button>
          </div>
        </div>
        <div v-if="!plan.days?.length" class="spp__today-empty">
          <b>暂时没有可执行任务</b>
          <span>先读一个知识页，或在题库里做几道题，计划会随真实记录长出来。</span>
        </div>
      </section>

      <footer class="spp__foot">
        <span>完成状态来自真实答题/阅读记录，不需要手动勾选。</span>
        <span v-if="plan.planId">计划 {{ plan.planId }} · 实时重算，不保存完成态</span>
      </footer>
    </template>

    <div v-else class="spp__empty">
      <div class="spp__empty-mark">◇</div>
      <h2>还没有可以执行的学习计划</h2>
      <p>系统会读取你的知识图谱和题库。先选一个资料夹，或者直接从题库开始。</p>
      <el-button type="primary" @click="openAdjust">生成学习计划</el-button>
    </div>

    <el-dialog v-model="adjusting" title="调整学习计划" width="460px" append-to-body>
      <div class="spp__form">
        <label>
          <span>考试日期 <em>可选；填了就按考试倒排</em></span>
          <el-date-picker v-model="form.examDate" type="date" value-format="YYYY-MM-DD" placeholder="不设考试日期"
            :disabled-date="disablePast" style="width: 100%" />
        </label>
        <label>
          <span>每天可学 <b>{{ form.dailyMinutes }} 分钟</b></span>
          <el-slider v-model="form.dailyMinutes" :min="10" :max="240" :step="10" :show-tooltip="false" />
        </label>
        <label>
          <span>计划天数 <em>无考试日期时生效</em></span>
          <el-input-number v-model="form.horizonDays" :min="1" :max="30" style="width: 100%" />
        </label>
        <label>
          <span>每周休息日</span>
          <el-select v-model="form.restDays" multiple collapse-tags placeholder="不设休息日" style="width: 100%">
            <el-option v-for="day in weekdays" :key="day.value" :label="day.label" :value="day.value" />
          </el-select>
        </label>
        <label>
          <span>题库范围 <em>不选则只按知识图谱；选了会加入真实题库薄弱题</em></span>
          <el-select v-model="form.bankIds" multiple collapse-tags placeholder="不加入题库" style="width: 100%">
            <el-option v-for="bank in graph.banks || []" :key="bank.bankId" :value="Number(bank.bankId)"
              :label="`${bank.title} · ${bank.questionCount} 题`" />
          </el-select>
        </label>
      </div>
      <template #footer>
        <el-button @click="adjusting = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="applyAdjust">重新安排</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="bankDrawer" size="440px" :with-header="false" append-to-body>
      <div v-if="activeBank" class="spp__bank-detail">
        <div class="spp__drawer-kicker">题库</div>
        <h2>{{ activeBank.title }}</h2>
        <p>{{ activeBank.subject || '未分类' }} · {{ activeBank.questionCount }} 题 · 已练 {{ activeBank.practicedQuestionCount }} 题</p>
        <div class="spp__bank-stats">
          <span><b>{{ activeBank.weakCount }}</b> 道薄弱题</span>
          <span><b>{{ activeBank.accuracy }}%</b> 正确率</span>
          <span><b>{{ activeBank.mappedQuestionCount }}</b> 道有知识页锚点</span>
        </div>
        <div class="spp__drawer-actions">
          <el-button type="primary" @click="goPractice(activeBank.bankId)">去练这个题库</el-button>
          <el-button plain @click="toggleBankInPlan(activeBank)">
            {{ selectedBankIds.has(Number(activeBank.bankId)) ? '从学习计划移除' : '纳入学习计划' }}
          </el-button>
        </div>
        <section class="spp__weak-block">
          <header><h3>优先处理</h3><span>来自真实诊断</span></header>
          <button v-for="question in activeBank.weakQuestions || []" :key="question.questionId" type="button" class="spp__weak"
            @click="goPractice(activeBank.bankId)">
            <span class="spp__weak-level">{{ question.levelText || '需关注' }}</span>
            <span class="spp__weak-text">{{ question.questionText }}</span>
            <span class="spp__weak-meta">{{ question.accuracy }}% · {{ question.attempts }} 次</span>
          </button>
          <div v-if="!activeBank.weakQuestions?.length" class="spp__hint">这个题库暂时没有诊断出的薄弱题。</div>
        </section>
        <p class="spp__hint">
          {{ activeBank.mappedQuestionCount > 0
            ? '这个题库有真实资料锚点，相关题目可回到知识页。'
            : '这个题库没有可反查的知识页锚点，只能按题库直接安排，不会伪造归属。' }}
        </p>
      </div>
    </el-drawer>

    <el-drawer v-model="pageDrawer" size="520px" :with-header="false" append-to-body>
      <div v-if="pageLoading" class="spp__loading"><el-icon class="is-loading" :size="18"><Loading /></el-icon><span>正在打开知识页…</span></div>
      <div v-else-if="pageDetail" class="spp__page-detail">
        <div class="spp__drawer-kicker">知识页</div>
        <h2>{{ pageDetail.title }}</h2>
        <p>{{ pageDetail.summary }}</p>
        <div class="spp__bank-stats">
          <span><b>{{ pageDetail.learning?.viewCount || 0 }}</b> 次阅读</span>
          <span><b>{{ pageDetail.learning?.practiceCount || 0 }}</b> 题练习</span>
          <span><b>{{ pageDetail.learning?.accuracy || 0 }}%</b> 正确率</span>
        </div>
        <el-button type="primary" @click="goWorkspace(pageDetail.pageId)">打开完整主题页</el-button>
        <p class="spp__hint">阅读记录会自动回写；读完关掉这里，今天的任务会重新计算。</p>
      </div>
    </el-drawer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { listKnowledgeBases } from '@/api/ai/rag'
import { getStudyGraph, getStudyPlan, getWikiPage, recordWikiPageView } from '@/api/ai/workspace'
import { readLegacyExamConfig, readStudyPlanConfig, saveStudyPlanConfig, startOfTodayMs } from '@/utils/studyPlanState'
import useUserStore from '@/store/modules/user'
import StudyMapGraph from './StudyMapGraph.vue'

defineOptions({ name: 'StudyPlanPanel' })

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const kbs = ref<any[]>([])
const kbId = ref(0)
const graph = ref<any>({ nodes: [], edges: [], banks: [], stats: {}, degraded: {} })
const plan = ref<any>(null)
const loading = ref(true)
const generating = ref(false)
const adjusting = ref(false)
const bankDrawer = ref(false)
const activeBank = ref<any>(null)
const pageDrawer = ref(false)
const pageLoading = ref(false)
const pageDetail = ref<any>(null)
const pageViewed = ref(false)

const todayStr = new Date().toLocaleDateString('sv-SE')
const form = reactive({
  examDate: '',
  dailyMinutes: 40,
  horizonDays: 7,
  restDays: [] as number[],
  bankIds: [] as number[]
})

const weekdays = [
  { value: 1, label: '周一' },
  { value: 2, label: '周二' },
  { value: 3, label: '周三' },
  { value: 4, label: '周四' },
  { value: 5, label: '周五' },
  { value: 6, label: '周六' },
  { value: 7, label: '周日' }
]

const selectedBankIds = computed(() => new Set((plan.value?.intent?.bankIds || []).map(Number)))
const selectedBanks = computed(() =>
  (graph.value.banks || []).filter((bank: any) => selectedBankIds.value.has(Number(bank.bankId)))
)
const routePageIds = computed(() =>
  (plan.value?.route?.stops || []).map((stop: any) => Number(stop.pageId)).filter(Boolean)
)
const readPageCount = computed(() =>
  (graph.value.nodes || []).filter((node: any) => node.kind === 'page' && Number(node.learning?.viewCount || 0) > 0).length
)
const todayTasks = computed(() => {
  const day = (plan.value?.days || []).find((item: any) => String(item.date || '').slice(0, 10) === todayStr)
  return day?.tasks || []
})
const todayMinutes = computed(() =>
  todayTasks.value.reduce((sum: number, task: any) => sum + Number(task.minutes || 0), 0)
)
const todayLabel = computed(() => `${todayStr.slice(5)} · 周${'日一二三四五六'[new Date(`${todayStr}T00:00:00`).getDay()]}`)
const nextDay = computed(() =>
  (plan.value?.days || []).find((day: any) => String(day.date || '') > todayStr) || null
)
const primaryTask = computed(() => {
  const tasks = todayTasks.value
  return tasks.find((task: any) => task.status === 'current')
    || tasks.find((task: any) => task.status !== 'done')
    || null
})

function dayLabel(value: string) {
  const date = new Date(`${String(value || '').slice(0, 10)}T00:00:00`)
  if (Number.isNaN(date.getTime())) return value
  const base = new Date(`${todayStr}T00:00:00`)
  const diff = Math.round((date.getTime() - base.getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '明天'
  return `${value.slice(5)} · 周${'日一二三四五六'[date.getDay()]}`
}

function disablePast(date: Date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return date.getTime() < today.getTime()
}

function applyConfig(config: ReturnType<typeof readStudyPlanConfig>) {
  if (!config) return
  kbId.value = Number(config.kbId || 0)
  form.examDate = config.examDate && config.examDate >= todayStr ? config.examDate : ''
  form.dailyMinutes = Number(config.dailyMinutes || 40)
  form.horizonDays = Number(config.horizonDays || 7)
  form.restDays = [...(config.restDays || [])]
  form.bankIds = [...(config.bankIds || [])]
}

async function loadKbs() {
  try {
    const res: any = await listKnowledgeBases()
    kbs.value = res.code === 200 && Array.isArray(res.data) ? res.data.filter((item: any) => Number(item.disabled || 0) !== 1) : []
  } catch {
    kbs.value = []
  }
  const queryKb = Number(route.query.kbId || 0)
  const activeKb = Number(localStorage.getItem('openstudy.workspace.activeKbId') || 0)
  // 有明确 URL 参数时以 URL 为准；否则沿用上次学习计划选的资料夹。
  const saved = queryKb ? readStudyPlanConfig(queryKb) : readStudyPlanConfig()
  if (saved) {
    applyConfig(saved)
  } else {
    const legacy = readLegacyExamConfig(userStore.id)
    if (legacy) {
      form.examDate = legacy.examDate && legacy.examDate >= todayStr ? legacy.examDate : ''
      form.dailyMinutes = legacy.dailyMinutes || 40
      form.restDays = legacy.restDays || []
      // 旧题库不自动混入新计划：它可能属于另一个科目；用户在题库详情里手动纳入。
    }
    const fallback = queryKb
      || (kbs.value.some((kb: any) => Number(kb.kbId) === activeKb) ? activeKb : 0)
      || Number(kbs.value[0]?.kbId || 0)
    kbId.value = fallback
  }
  if (!kbs.value.some((kb: any) => Number(kb.kbId) === kbId.value)) {
    kbId.value = Number(kbs.value[0]?.kbId || 0)
  }
}

async function loadGraph() {
  try {
    const res: any = await getStudyGraph(kbId.value || 0, { bankLimit: 8 })
    if (res.code === 200 && res.data) graph.value = res.data
  } catch {
    graph.value = { nodes: [], edges: [], banks: [], stats: {}, degraded: {} }
  }
}

function saveConfig(planData: any) {
  saveStudyPlanConfig({
    kbId: Number(kbId.value || 0),
    goal: form.examDate ? 'exam' : 'weakness',
    examDate: form.examDate,
    horizonDays: form.horizonDays,
    dailyMinutes: form.dailyMinutes,
    restDays: form.restDays,
    bankIds: form.bankIds,
    sinceMs: Number(planData?.window?.sinceMs || startOfTodayMs()),
    planId: String(planData?.planId || '')
  })
}

async function generatePlan(resetSince = false) {
  if (generating.value) return
  generating.value = true
  try {
    const sinceMs = resetSince
      ? startOfTodayMs()
      : Number(plan.value?.window?.sinceMs || startOfTodayMs())
    const res: any = await getStudyPlan(kbId.value || 0, {
      goal: form.examDate ? 'exam' : 'weakness',
      examDate: form.examDate || undefined,
      horizonDays: form.horizonDays,
      dailyMinutes: form.dailyMinutes,
      restDays: form.restDays,
      bankIds: form.bankIds,
      sinceMs
    })
    if (res.code === 200 && res.data) {
      plan.value = res.data
      saveConfig(res.data)
      await loadGraph()
      return true
    }
    ElMessage.error(res.msg || '学习计划生成失败')
    return false
  } catch (error: any) {
    console.error('[学习计划] 生成失败', error)
    ElMessage.error('学习计划生成失败，请稍后重试')
    return false
  } finally {
    generating.value = false
  }
}

async function refreshPlan() {
  if (!plan.value) {
    await loadAll()
    return
  }
  await generatePlan(false)
}

async function loadAll() {
  loading.value = true
  try {
    await loadKbs()
    await loadGraph()
    const saved = readStudyPlanConfig(kbId.value)
    if (saved) {
      applyConfig(saved)
      await generatePlan(false)
    } else {
      await generatePlan(true)
    }
  } finally {
    loading.value = false
  }
}

async function onKbChange() {
  plan.value = null
  // 题库属于另一门课时，用户可在题库节点里重新纳入，不带着旧库跨资料夹。
  form.bankIds = []
  await loadGraph()
  await generatePlan(true)
}

function openAdjust() {
  if (plan.value?.intent) {
    form.examDate = plan.value.intent.examDate || ''
    form.dailyMinutes = Number(plan.value.window?.dailyMinutes || form.dailyMinutes)
    form.horizonDays = Number(plan.value.window?.horizonDays || form.horizonDays)
    form.restDays = [...(plan.value.window?.restDays || [])]
    form.bankIds = [...(plan.value.intent?.bankIds || [])]
  }
  adjusting.value = true
}

async function applyAdjust() {
  if (form.examDate && form.examDate < todayStr) {
    ElMessage.warning('考试日期不能早于今天，已按不设考试处理')
    form.examDate = ''
  }
  adjusting.value = false
  await generatePlan(true)
}

function onGraphSelect(node: any) {
  if (node?.kind === 'bank') {
    activeBank.value = node
    bankDrawer.value = true
    return
  }
  if (node?.pageId) void openPage(node.pageId)
}

async function openPage(pageId: number) {
  pageDrawer.value = true
  pageLoading.value = true
  pageDetail.value = null
  pageViewed.value = false
  try {
    const res: any = await getWikiPage(pageId)
    if (res.code !== 200 || !res.data) {
      ElMessage.error(res.msg || '知识页加载失败')
      pageDrawer.value = false
      return
    }
    pageDetail.value = res.data
    // 真实阅读记录；不依赖前端勾选。
    await recordWikiPageView(pageId)
    pageViewed.value = true
  } catch {
    pageDrawer.value = false
  } finally {
    pageLoading.value = false
  }
}

function openTask(task: any) {
  const target = task?.target || {}
  if (target.kind === 'question' || target.kind === 'bank') {
    if (target.bankId) {
      goPractice(target.bankId)
      return
    }
  }
  if (target.pageId) {
    void openPage(Number(target.pageId))
    return
  }
  if (target.questionId) {
    router.push({ path: '/front/myQuestion/wrongQuestion', query: { questionId: String(target.questionId), from: 'plan' } })
  }
}

function goPractice(bankId: number) {
  router.push({ path: `/front/questionPractice/${bankId}/practice/sequential` })
}

function goWorkspace(pageId: number) {
  router.push({ path: '/front/workspace', query: { view: 'wiki', kbId: kbId.value || undefined, pageId } })
}

function toggleBankInPlan(bank: any) {
  const bid = Number(bank.bankId)
  if (!bid) return
  if (form.bankIds.includes(bid)) {
    form.bankIds = form.bankIds.filter((id) => id !== bid)
  } else {
    form.bankIds = [...form.bankIds, bid]
  }
  bankDrawer.value = false
  void generatePlan(true)
}

function askAi() {
  const kb = kbId.value || 0
  const prompt = [
    `请查看我的学习计划：kbId=${kb}${plan.value?.planId ? `，planId=${plan.value.planId}` : ''}。`,
    '请先用 study_graph 查看我的知识图谱和题库（重点看真实薄弱题和题→知识页锚点），',
    '再用 study_plan 读取同一份学习计划，解释为什么这样安排，并告诉我今天最该先做什么。',
    '不要编造不存在的知识点、题目或完成状态。'
  ].join('')
  window.dispatchEvent(new CustomEvent('openstudy:ask-assistant', { detail: { prompt } }))
}

watch(pageDrawer, (visible) => {
  if (!visible && pageViewed.value) {
    pageViewed.value = false
    // 阅读记录已写入，重新拉计划即可看到今天的任务自动推进。
    void generatePlan(false)
  }
})

watch(
  () => route.query.kbId,
  (value) => {
    const next = Number(value || 0)
    if (next && next !== kbId.value) {
      kbId.value = next
      plan.value = null
      void loadAll()
    }
  }
)

onMounted(loadAll)

defineExpose({ refresh: refreshPlan })
</script>

<style scoped>
.spp { display: flex; flex-direction: column; gap: 16px; padding-bottom: 12px; }
.spp__hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 4px 2px 2px; }
.spp__hero-copy { min-width: 0; }
.spp__kicker { color: #2f5fce; font-size: 11px; font-weight: 700; letter-spacing: .1em; }
.spp__hero h1 { margin: 7px 0 5px; color: #1f2937; font-size: 23px; line-height: 1.3; }
.spp__hero p { margin: 0; color: #7d8596; font-size: 12px; line-height: 1.6; }
.spp__chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
.spp__chips span { padding: 3px 8px; border: 1px solid #e4ebf6; border-radius: 99px; color: #697386; background: #f8faff; font-size: 10px; }
.spp__chips span b { color: #2f5fce; }
.spp__chips span.is-warn { color: #b26b13; border-color: #f4dfbc; background: #fff9ee; }
.spp__actions { display: flex; flex: none; align-items: center; gap: 7px; }
.spp__kb { width: 180px; }
.spp__flow { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; padding: 7px 10px; border: 1px solid #e8eef8; border-radius: 9px; background: #fbfcff; color: #9aa3b2; font-size: 10px; }
.spp__flow span { display: inline-flex; align-items: center; gap: 4px; }
.spp__flow span i { display: grid; width: 16px; height: 16px; place-items: center; border: 1px solid #dbe4f2; border-radius: 50%; color: #9aa3b2; background: #fff; font-size: 9px; font-style: normal; }
.spp__flow span.is-done { color: #2f5fce; }
.spp__flow span.is-done i { border-color: #c9d9f8; color: #2f5fce; background: #eef4ff; }
.spp__flow em { color: #c4ccd8; font-style: normal; }
.spp__loading { display: flex; min-height: 160px; align-items: center; justify-content: center; gap: 8px; color: #8a91a0; font-size: 12px; }
.spp__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.spp__stat { display: flex; min-height: 78px; flex-direction: column; justify-content: center; gap: 3px; padding: 10px 14px; border: 1px solid #e8edf5; border-radius: 10px; background: #fff; }
.spp__stat span { color: #8a91a0; font-size: 10px; }
.spp__stat b { color: #253247; font-size: 22px; line-height: 1.1; }
.spp__stat em { color: #a0a8b6; font-size: 10px; font-style: normal; }
.spp__main { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(280px, .9fr); gap: 12px; align-items: stretch; }
.spp__map-card, .spp__today-card, .spp__timeline { min-width: 0; padding: 14px; border: 1px solid #e8edf5; border-radius: 12px; background: #fff; }
.spp__section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.spp__section-head h2 { margin: 0; color: #253247; font-size: 14px; }
.spp__section-head p { margin: 4px 0 0; color: #9aa3b2; font-size: 10px; line-height: 1.5; }
.spp__section-meta { flex: none; color: #a0a8b6; font-size: 10px; }
.spp__hint { margin: 8px 0 0; color: #9aa3b2; font-size: 10px; line-height: 1.55; }
.spp__today-card { display: flex; flex-direction: column; }
.spp__today-list { display: flex; flex-direction: column; gap: 7px; }
.spp__task { display: flex; width: 100%; align-items: flex-start; gap: 9px; padding: 10px 9px; border: 1px solid #edf1f7; border-radius: 9px; background: #fff; color: inherit; cursor: pointer; font: inherit; text-align: left; }
.spp__task:hover { border-color: #cfdcf5; background: #f9fbff; }
.spp__task.is-done { opacity: .62; }
.spp__task-state { flex: none; width: 15px; color: #b1b9c6; font-size: 12px; line-height: 1.45; }
.spp__task.is-done .spp__task-state { color: #2f9e8f; }
.spp__task-body { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }
.spp__task-body b { overflow: hidden; color: #38465c; font-size: 12px; font-weight: 600; line-height: 1.45; text-overflow: ellipsis; white-space: nowrap; }
.spp__task-body em { display: -webkit-box; overflow: hidden; color: #9aa3b2; font-size: 10px; font-style: normal; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.spp__task-min { flex: none; color: #a4acb9; font-size: 10px; line-height: 1.5; }
.spp__today-empty { display: flex; min-height: 120px; flex-direction: column; align-items: center; justify-content: center; gap: 5px; border-radius: 9px; background: #f8fafc; color: #9aa3b2; text-align: center; font-size: 11px; line-height: 1.55; }
.spp__today-empty b { color: #5f6b7d; font-size: 12px; }
.spp__primary { display: flex; height: 38px; align-items: center; justify-content: center; gap: 4px; margin-top: auto; border: 0; border-radius: 8px; color: #fff; background: #2f5fce; cursor: pointer; font: inherit; font-size: 12px; font-weight: 600; }
.spp__primary:hover { background: #2853b8; }
.spp__primary span { font-weight: 400; opacity: .8; }
.spp__timeline { margin-top: 0; }
.spp__day { display: grid; grid-template-columns: 86px minmax(0, 1fr); gap: 12px; padding: 10px 0; border-top: 1px solid #f0f3f8; }
.spp__day.is-today { margin: 0 -8px; padding: 10px 8px; border-radius: 8px; background: #f7faff; }
.spp__date { display: flex; flex-direction: column; gap: 3px; }
.spp__date b { color: #38465c; font-size: 12px; }
.spp__date span { color: #a0a8b6; font-size: 10px; }
.spp__date em { width: fit-content; padding: 1px 5px; border-radius: 4px; color: #b26b13; background: #fff3df; font-size: 9px; font-style: normal; }
.spp__day-tasks { display: flex; flex-direction: column; gap: 5px; }
.spp__task--compact { padding: 7px 8px; }
.spp__foot { display: flex; justify-content: space-between; gap: 10px; padding: 0 2px; color: #a0a8b6; font-size: 10px; line-height: 1.5; }
.spp__empty { display: flex; min-height: 260px; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border: 1px solid #e8edf5; border-radius: 12px; background: #fff; text-align: center; }
.spp__empty-mark { display: grid; width: 44px; height: 44px; place-items: center; border-radius: 12px; color: #2f5fce; background: #f2f6ff; font-size: 24px; }
.spp__empty h2 { margin: 0; color: #38465c; font-size: 16px; }
.spp__empty p { max-width: 420px; margin: 0 0 6px; color: #9aa3b2; font-size: 11px; line-height: 1.6; }
.spp__form { display: flex; flex-direction: column; gap: 14px; }
.spp__form label { display: flex; flex-direction: column; gap: 7px; color: #5f6b7d; font-size: 12px; }
.spp__form label > span { display: flex; justify-content: space-between; gap: 8px; }
.spp__form label em { color: #a0a8b6; font-size: 10px; font-style: normal; font-weight: 400; }
.spp__form label b { color: #2f5fce; font-size: 11px; }
.spp__bank-detail, .spp__page-detail { display: flex; flex-direction: column; gap: 10px; padding: 4px 4px 20px; }
.spp__drawer-kicker { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .1em; }
.spp__bank-detail h2, .spp__page-detail h2 { margin: 0; color: #253247; font-size: 20px; line-height: 1.35; }
.spp__bank-detail p, .spp__page-detail p { margin: 0; color: #8a91a0; font-size: 11px; line-height: 1.6; }
.spp__bank-stats { display: flex; flex-wrap: wrap; gap: 8px; }
.spp__bank-stats span { padding: 6px 9px; border: 1px solid #e8edf5; border-radius: 7px; color: #697386; background: #f8fafc; font-size: 10px; }
.spp__bank-stats b { color: #2f5fce; font-size: 12px; }
.spp__drawer-actions { display: flex; gap: 7px; }
.spp__weak-block { margin-top: 8px; border-top: 1px solid #eef2f7; padding-top: 12px; }
.spp__weak-block header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 7px; }
.spp__weak-block h3 { margin: 0; color: #38465c; font-size: 13px; }
.spp__weak-block header span { color: #a0a8b6; font-size: 10px; }
.spp__weak { display: flex; width: 100%; align-items: flex-start; gap: 7px; padding: 8px 0; border: 0; border-bottom: 1px solid #f4f6fa; background: transparent; color: inherit; cursor: pointer; font: inherit; text-align: left; }
.spp__weak:hover .spp__weak-text { color: #2f5fce; }
.spp__weak-level { flex: none; padding: 1px 4px; border-radius: 4px; color: #b26b13; background: #fff3df; font-size: 9px; }
.spp__weak-text { display: -webkit-box; overflow: hidden; flex: 1; color: #5f6b7d; font-size: 11px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.spp__weak-meta { flex: none; color: #a0a8b6; font-size: 9px; }
@media (max-width: 980px) {
  .spp__hero { flex-direction: column; }
  .spp__actions { width: 100%; flex-wrap: wrap; }
  .spp__kb { flex: 1; min-width: 180px; }
  .spp__main { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .spp__stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .spp__day { grid-template-columns: 70px minmax(0, 1fr); }
  .spp__foot { flex-direction: column; }
}
</style>
