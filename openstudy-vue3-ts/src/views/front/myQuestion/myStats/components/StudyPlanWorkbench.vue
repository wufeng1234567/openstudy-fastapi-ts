<template>
  <section class="spw">
    <header class="spw__hero">
      <div class="spw__hero-copy">
        <span class="spw__kicker">学习计划</span>
        <h1>{{ advice?.title || '先看懂图谱，再决定学什么' }}</h1>
        <p>选一个主题、资料或题库，系统会沿着真实关系读一遍，再给你一份可以反复修改的建议。</p>
      </div>
      <div class="spw__actions">
        <el-select v-model="kbId" size="small" class="spw__kb" @change="onKbChange">
          <el-option label="全部资料夹" :value="0" />
          <el-option v-for="kb in kbs" :key="kb.kbId" :label="kb.name" :value="Number(kb.kbId)" />
        </el-select>
        <el-select v-model="goal" size="small" class="spw__goal" @change="onScopeChange">
          <el-option label="补弱" value="weakness" />
          <el-option label="打基础" value="foundation" />
          <el-option label="拓展" value="explore" />
        </el-select>
        <el-input-number v-model="dailyMinutes" size="small" :min="10" :max="180" :step="10" controls-position="right" class="spw__minutes" @change="onScopeChange" />
        <el-popover placement="bottom-end" :width="300" trigger="click">
          <template #reference>
            <el-button size="small" plain>范围</el-button>
          </template>
          <div class="spw__scope">
            <div class="spw__scope-title">图谱来源</div>
            <el-checkbox-group v-model="sourceTypes" size="small" @change="onScopeChange">
              <el-checkbox label="wiki">知识百科</el-checkbox>
              <el-checkbox label="bank">题库</el-checkbox>
              <el-checkbox label="document">资料</el-checkbox>
              <el-checkbox label="web">网页</el-checkbox>
              <el-checkbox label="note">笔记</el-checkbox>
              <el-checkbox label="image">图片</el-checkbox>
            </el-checkbox-group>
            <div class="spw__scope-title">题库范围</div>
            <el-select v-model="bankIds" multiple collapse-tags size="small" placeholder="不限定题库" style="width: 100%" @change="onScopeChange">
              <el-option v-for="bank in bankOptions" :key="bank.ref.bankId" :label="bank.title" :value="Number(bank.ref.bankId)" />
            </el-select>
            <div class="spw__scope-title">计划跨度</div>
            <el-input-number v-model="horizonDays" size="small" :min="3" :max="30" controls-position="right" style="width: 100%" @change="onScopeChange" />
          </div>
        </el-popover>
        <el-button size="small" type="primary" :loading="isBusy" @click="generate()">生成建议</el-button>
      </div>
    </header>

    <div class="spw__stats">
      <div><span>知识主题</span><b>{{ graph.stats?.topicCount || 0 }}</b></div>
      <div><span>题库</span><b>{{ graph.stats?.bankCount || 0 }}</b></div>
      <div><span>资料 / 网页</span><b>{{ (graph.stats?.documentCount || 0) + (graph.stats?.webCount || 0) }}</b></div>
      <div><span>薄弱题</span><b>{{ graph.stats?.weakQuestionCount || 0 }}</b></div>
    </div>

    <div class="spw__main">
      <StudyGraphCanvas
        :nodes="graph.nodes"
        :edges="graph.edges"
        :trace="trace"
        :active-step="activeStep"
        :phase="phase"
        :selected-id="selectedNode?.id || ''"
        :visited-ids="visitedIds"
        @select="onSelectNode"
      />
      <StudyAdvicePanel
        :advice="advice"
        :loading="isBusy"
        :phase="phase"
        :selected-node="selectedNode"
        :node-titles="nodeTitles"
        @generate="generate()"
        @adjust="adjust"
        @save="saveCurrent"
        @history="openHistory"
      />
    </div>

    <div v-if="error" class="spw__error">{{ error }}</div>

    <section class="spw__recent">
      <header>
        <div>
          <h2>我的规划</h2>
          <p>每次生成都会留一份快照；可以查看、重命名、置顶或删除。</p>
        </div>
        <el-button size="small" text @click="openHistory">全部规划 →</el-button>
      </header>
      <div v-if="history.length" class="spw__recent-list">
        <button v-for="item in history.slice(0, 3)" :key="item.id" type="button" class="spw__recent-item" @click="loadHistoryItem(item)">
          <b>{{ item.title || '未命名规划' }}</b>
          <span>{{ item.createTime?.slice(5, 16) || '' }} · {{ item.phaseCount || 0 }} 个阶段</span>
        </button>
      </div>
      <div v-else class="spw__recent-empty">还没有保存的规划。生成建议后会自动保存。</div>
    </section>

    <StudyPlanHistoryDrawer
      v-model="historyOpen"
      :items="history"
      @refresh="loadHistory"
      @load="loadHistoryItem"
      @rename="renameHistory"
      @pin="pinHistory"
      @delete="deleteHistory"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listKnowledgeBases } from '@/api/ai/rag'
import {
  createStudyPlanHistory,
  deleteStudyPlanHistory,
  generateStudyAdvice,
  getStudyMap,
  getStudyPlanHistory,
  listStudyPlanHistory,
  prepareStudyTrace,
  updateStudyPlanHistory
} from '@/api/ai/studyPlan'
import { readStudyPlanConfig, saveStudyPlanConfig, startOfTodayMs } from '@/utils/studyPlanState'
import StudyGraphCanvas from './StudyGraphCanvas.vue'
import StudyAdvicePanel from './StudyAdvicePanel.vue'
import StudyPlanHistoryDrawer from './StudyPlanHistoryDrawer.vue'

defineOptions({ name: 'StudyPlanWorkbench' })

const route = useRoute()
const kbs = ref<any[]>([])
const kbId = ref(0)
const goal = ref('weakness')
const dailyMinutes = ref(30)
const horizonDays = ref(14)
const sourceTypes = ref<string[]>(['wiki', 'bank'])
const bankIds = ref<number[]>([])
const seedNodeId = ref('')
const graph = ref<any>({ nodes: [], edges: [], stats: {}, sourceStats: [], degraded: {} })
const trace = ref<any>(null)
const advice = ref<any>(null)
const selectedNode = ref<any>(null)
const phase = ref('idle')
const activeStep = ref(-1)
const visitedIds = ref<string[]>([])
const error = ref('')
const snapshotId = ref(0)
const history = ref<any[]>([])
const historyOpen = ref(false)
const loadingGraph = ref(false)
let runSeq = 0
let graphSeq = 0

const isBusy = computed(() => ['reading', 'traversing', 'thinking'].includes(phase.value))
const bankOptions = computed(() => (graph.value.nodes || []).filter((node: any) => node.kind === 'bank'))
const nodeTitles = computed(() => {
  const map: Record<string, string> = {}
  for (const node of graph.value.nodes || []) map[String(node.id)] = String(node.title || node.id)
  return map
})

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buildParams(instruction = '') {
  return {
    kbId: Number(kbId.value || 0),
    bankIds: [...bankIds.value],
    sourceTypes: [...sourceTypes.value],
    seedNodeId: seedNodeId.value || '',
    goal: goal.value,
    dailyMinutes: Number(dailyMinutes.value || 30),
    horizonDays: Number(horizonDays.value || 14),
    instruction
  }
}

function rememberConfig() {
  saveStudyPlanConfig({
    kbId: Number(kbId.value || 0),
    goal: goal.value as any,
    examDate: '',
    horizonDays: Number(horizonDays.value || 14),
    dailyMinutes: Number(dailyMinutes.value || 30),
    restDays: [],
    bankIds: [...bankIds.value],
    sinceMs: startOfTodayMs(),
    sourceTypes: [...sourceTypes.value],
    seedNodeId: seedNodeId.value,
    adviceId: snapshotId.value || undefined
  })
}

async function loadKbs() {
  try {
    const res: any = await listKnowledgeBases()
    kbs.value = res.code === 200 && Array.isArray(res.data) ? res.data.filter((item: any) => Number(item.disabled || 0) !== 1) : []
  } catch {
    kbs.value = []
  }
  const saved = readStudyPlanConfig()
  if (saved) {
    kbId.value = Number(saved.kbId || 0)
    goal.value = saved.goal || 'weakness'
    dailyMinutes.value = Number(saved.dailyMinutes || 30)
    horizonDays.value = Number(saved.horizonDays || 14)
    bankIds.value = [...(saved.bankIds || [])]
    sourceTypes.value = saved.sourceTypes?.length ? [...saved.sourceTypes] : ['wiki', 'bank']
    seedNodeId.value = saved.seedNodeId || ''
  } else {
    const queryKb = Number(route.query.kbId || 0)
    const activeKb = Number(localStorage.getItem('openstudy.workspace.activeKbId') || 0)
    const fallback = queryKb || (kbs.value.some((kb: any) => Number(kb.kbId) === activeKb) ? activeKb : 0) || Number(kbs.value[0]?.kbId || 0)
    kbId.value = fallback
  }
  if (!kbs.value.some((kb: any) => Number(kb.kbId) === Number(kbId.value))) {
    kbId.value = Number(kbs.value[0]?.kbId || 0)
  }
}

async function loadGraph() {
  const seq = ++graphSeq
  loadingGraph.value = true
  try {
    const res: any = await getStudyMap({
      kbId: Number(kbId.value || 0),
      bankIds: bankIds.value,
      sourceTypes: sourceTypes.value,
      seedNodeId: seedNodeId.value,
      depth: 2,
      limit: 80
    })
    if (seq !== graphSeq) return
    if (res.code === 200 && res.data) {
      graph.value = res.data
      if (selectedNode.value?.id) {
        selectedNode.value = (res.data.nodes || []).find((n: any) => String(n.id) === String(selectedNode.value.id)) || null
      }
      rememberConfig()
    }
  } catch {
    if (seq === graphSeq) graph.value = { nodes: [], edges: [], stats: {}, sourceStats: [], degraded: {} }
  } finally {
    if (seq === graphSeq) loadingGraph.value = false
  }
}

async function loadHistory() {
  try {
    const res: any = await listStudyPlanHistory(20)
    if (res.code === 200) history.value = res.data?.items || []
  } catch {
    history.value = []
  }
}

function onKbChange() {
  runSeq++
  advice.value = null
  snapshotId.value = 0
  selectedNode.value = null
  seedNodeId.value = ''
  bankIds.value = []
  phase.value = 'idle'
  void loadGraph()
}

function onScopeChange() {
  runSeq++
  advice.value = null
  snapshotId.value = 0
  phase.value = 'idle'
  void loadGraph()
}

async function onSelectNode(node: any) {
  if (!node?.id) {
    selectedNode.value = null
    seedNodeId.value = ''
    await loadGraph()
    return
  }
  selectedNode.value = node
  seedNodeId.value = String(node.id)
  await loadGraph()
}

async function playTrace(current: any) {
  const steps = current?.steps || []
  phase.value = 'reading'
  activeStep.value = -1
  visitedIds.value = []
  await sleep(380)
  if (!steps.length) {
    phase.value = 'thinking'
    await sleep(420)
    return
  }
  phase.value = 'traversing'
  const visited: string[] = []
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index]
    activeStep.value = index
    if (step.from && !visited.includes(step.from)) visited.push(step.from)
    if (step.to && !visited.includes(step.to)) visited.push(step.to)
    visitedIds.value = [...visited]
    await sleep(Number(step.durationMs || 520))
  }
  phase.value = 'thinking'
  await sleep(420)
}

async function generate(instruction = '', parentId = 0) {
  if (isBusy.value) return
  const seq = ++runSeq
  error.value = ''
  advice.value = null
  trace.value = null
  snapshotId.value = 0
  phase.value = 'reading'
  try {
    const params = buildParams(instruction)
    const traceRes: any = await prepareStudyTrace(params)
    if (seq !== runSeq) return
    if (traceRes.code !== 200 || !traceRes.data) throw new Error(traceRes.msg || '轨迹生成失败')
    const currentTrace = traceRes.data.trace || {}
    trace.value = currentTrace
    if (traceRes.data.graph) graph.value = traceRes.data.graph
    if (currentTrace.seedNodeId) {
      seedNodeId.value = String(currentTrace.seedNodeId)
      selectedNode.value = (graph.value.nodes || []).find((n: any) => String(n.id) === String(currentTrace.seedNodeId)) || null
    }
    const advicePromise = generateStudyAdvice({
      ...params,
      traceId: currentTrace.traceId || '',
      parentSnapshotId: parentId,
      save: true,
      useLlm: true
    })
    await playTrace(currentTrace)
    const adviceRes: any = await advicePromise
    if (seq !== runSeq) return
    if (adviceRes.code !== 200 || !adviceRes.data) throw new Error(adviceRes.msg || '建议生成失败')
    advice.value = adviceRes.data.advice || null
    snapshotId.value = Number(adviceRes.data.snapshotId || 0)
    if (adviceRes.data.graph) graph.value = adviceRes.data.graph
    phase.value = 'ready'
    rememberConfig()
    await loadHistory()
  } catch (e: any) {
    if (seq !== runSeq) return
    console.error('[学习计划] 生成失败', e)
    phase.value = 'idle'
    error.value = String(e?.message || '生成失败，请稍后重试')
    ElMessage.error(error.value)
  }
}

function adjust(instruction: string) {
  if (!instruction.trim()) return
  void generate(instruction, snapshotId.value)
}

async function saveCurrent() {
  if (!advice.value) return
  try {
    const res: any = await createStudyPlanHistory({
      kbId: Number(kbId.value || 0),
      title: advice.value.title || '',
      scope: advice.value.scope || {},
      advice: advice.value,
      trace: trace.value || {},
      graph: graph.value || {},
      parentId: snapshotId.value || 0,
      source: 'page'
    })
    if (res.code === 200) {
      snapshotId.value = Number(res.data?.id || snapshotId.value)
      ElMessage.success('已保存到我的规划')
      await loadHistory()
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch {
    ElMessage.error('保存失败')
  }
}

async function openHistory() {
  historyOpen.value = true
  await loadHistory()
}

async function loadHistoryItem(item: any) {
  try {
    const res: any = await getStudyPlanHistory(Number(item.id))
    if (res.code !== 200 || !res.data) {
      ElMessage.error(res.msg || '读取规划失败')
      return
    }
    const data = res.data
    advice.value = data.advice || null
    trace.value = data.trace || null
    graph.value = data.graph || graph.value
    snapshotId.value = Number(data.id || 0)
    seedNodeId.value = String(data.scope?.seedNodeId || data.advice?.scope?.seedNodeId || '')
    selectedNode.value = (graph.value.nodes || []).find((n: any) => String(n.id) === seedNodeId.value) || null
    phase.value = 'ready'
    activeStep.value = -1
    visitedIds.value = (data.trace?.visitedNodeIds || []).map(String)
    historyOpen.value = false
  } catch {
    ElMessage.error('读取规划失败')
  }
}

async function renameHistory(item: any, title: string) {
  const res: any = await updateStudyPlanHistory(Number(item.id), { title })
  if (res.code === 200) {
    ElMessage.success('已重命名')
    await loadHistory()
  } else {
    ElMessage.error(res.msg || '重命名失败')
  }
}

async function pinHistory(item: any) {
  const res: any = await updateStudyPlanHistory(Number(item.id), { pinned: !item.pinned })
  if (res.code === 200) await loadHistory()
  else ElMessage.error(res.msg || '操作失败')
}

async function deleteHistory(item: any) {
  const res: any = await deleteStudyPlanHistory(Number(item.id))
  if (res.code === 200) {
    ElMessage.success('已删除')
    await loadHistory()
  } else {
    ElMessage.error(res.msg || '删除失败')
  }
}

onMounted(async () => {
  await loadKbs()
  await loadGraph()
  await loadHistory()
  const adviceId = Number(route.query.adviceId || 0)
  if (adviceId) {
    await loadHistoryItem({ id: adviceId })
  }
})

defineExpose({ refresh: loadGraph })
</script>

<style scoped>
.spw { display: flex; flex-direction: column; gap: 12px; padding-bottom: 12px; }
.spw__hero { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 2px 2px 0; }
.spw__hero-copy { min-width: 0; }
.spw__kicker { color: #2f5fce; font-size: 11px; font-weight: 700; letter-spacing: .1em; }
.spw__hero h1 { margin: 6px 0 5px; color: #253247; font-size: 22px; line-height: 1.3; }
.spw__hero p { margin: 0; color: #7d8596; font-size: 12px; line-height: 1.6; }
.spw__actions { display: flex; flex: none; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.spw__kb { width: 150px; }
.spw__goal { width: 86px; }
.spw__minutes { width: 92px; }
.spw__stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.spw__stats div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 8px 12px; border: 1px solid #e8edf5; border-radius: 9px; background: #fff; }
.spw__stats span { color: #8a91a0; font-size: 10px; }
.spw__stats b { color: #253247; font-size: 18px; }
.spw__main { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(300px, .9fr); gap: 10px; align-items: stretch; }
.spw__error { padding: 8px 10px; border: 1px solid #f4d7d3; border-radius: 7px; color: #b94a44; background: #fff8f7; font-size: 11px; }
.spw__recent { padding: 10px 12px; border: 1px solid #e8edf5; border-radius: 10px; background: #fff; }
.spw__recent header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.spw__recent h2 { margin: 0; color: #253247; font-size: 13px; }
.spw__recent p { margin: 4px 0 0; color: #9aa3b2; font-size: 10px; }
.spw__recent-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin-top: 8px; }
.spw__recent-item { display: flex; min-width: 0; flex-direction: column; gap: 3px; padding: 7px 8px; border: 1px solid #edf1f7; border-radius: 7px; background: #fbfcff; color: inherit; cursor: pointer; text-align: left; }
.spw__recent-item:hover { border-color: #cfdcf5; }
.spw__recent-item b { overflow: hidden; color: #4d5d78; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.spw__recent-item span { color: #a0a8b6; font-size: 10px; }
.spw__recent-empty { margin-top: 8px; color: #a0a8b6; font-size: 10px; }
.spw__scope { display: flex; flex-direction: column; gap: 7px; }
.spw__scope-title { margin-top: 3px; color: #8a91a0; font-size: 10px; font-weight: 600; }
.spw__scope :deep(.el-checkbox) { margin-right: 8px; }
@media (max-width: 980px) {
  .spw__hero { flex-direction: column; }
  .spw__actions { justify-content: flex-start; }
  .spw__main { grid-template-columns: 1fr; }
  .spw__recent-list { grid-template-columns: 1fr; }
}
</style>
