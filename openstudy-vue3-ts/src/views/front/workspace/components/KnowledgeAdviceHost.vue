<template>
  <ResizableDrawer
    v-model="drawer"
    direction="rtl"
    storage-key="openstudy_advice_drawer_size"
    :default-width="440"
    :min="360"
    :max="760"
    :modal="false"
    :modal-penetrable="true"
    :close-on-click-outside="true"
  >
    <div class="kah__drawer">
      <NodeAdviceHistoryPreview
        v-if="selectedNode && !advice && !isBusy"
        :seed-node-id="selectedNode.id"
        :node-title="selectedNode.title"
        @load="loadHistoryItem"
        @generate="generate()"
      />
      <StudyAdvicePanel
        v-else
        :advice="advice"
        :loading="isBusy"
        :phase="phase"
        :selected-node="selectedNode"
        :node-titles="displayNodeTitles"
        @generate="generate()"
        @adjust="adjust"
        @save="saveCurrent"
        @history="openHistory"
      />
    </div>
  </ResizableDrawer>

  <StudyPlanHistoryDrawer
    v-model="historyOpen"
    :items="history"
    @refresh="loadHistory"
    @load="loadHistoryItem"
    @rename="renameHistory"
    @pin="pinHistory"
    @delete="deleteHistory"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import {
  createStudyPlanHistory,
  deleteStudyPlanHistory,
  generateStudyAdvice,
  getStudyPlanHistory,
  listStudyPlanHistory,
  prepareStudyTrace,
  updateStudyPlanHistory
} from '@/api/ai/studyPlan'
import { readStudyPlanConfig } from '@/utils/studyPlanState'
import NodeAdviceHistoryPreview from './NodeAdviceHistoryPreview.vue'
import StudyAdvicePanel from '@/views/front/myQuestion/myStats/components/StudyAdvicePanel.vue'
import StudyPlanHistoryDrawer from '@/views/front/myQuestion/myStats/components/StudyPlanHistoryDrawer.vue'

const props = withDefaults(
  defineProps<{
    activeKbId?: number | null
    nodeTitles?: Record<string, string>
  }>(),
  { activeKbId: 0, nodeTitles: () => ({}) }
)

const emit = defineEmits<{
  (e: 'busy', value: boolean): void
  (e: 'update', payload: { advice: any; trace: any; visitedPageIds: string[] }): void
  (e: 'focus-page', pageId: number): void
}>()

const advice = ref<any>(null)
const trace = ref<any>(null)
const selectedNode = ref<any>(null)
const phase = ref('idle')
const drawer = ref(false)
const historyOpen = ref(false)
const history = ref<any[]>([])
const snapshotId = ref(0)
const bankIds = ref<number[]>([...(readStudyPlanConfig(props.activeKbId)?.bankIds || [])])
const graphTitles = ref<Record<string, string>>({})
const displayNodeTitles = computed(() => ({ ...(props.nodeTitles || {}), ...graphTitles.value }))
let runSeq = 0

const isBusy = computed(() => ['reading', 'traversing', 'thinking'].includes(phase.value))
watch(isBusy, (value) => emit('busy', value))

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buildParams(instruction = '') {
  return {
    kbId: Number(props.activeKbId || 0),
    bankIds: [...bankIds.value],
    sourceTypes: ['wiki', 'bank', 'document', 'web', 'note', 'image'],
    seedNodeId: selectedNode.value?.id || '',
    goal: 'weakness',
    dailyMinutes: 30,
    horizonDays: 14,
    instruction
  }
}

function syncState() {
  const visited = (trace.value?.visitedNodeIds || [])
    .map((item: any) => String(item).replace(/^topic:/, ''))
    .filter(Boolean)
  emit('update', { advice: advice.value, trace: trace.value, visitedPageIds: visited })
}

async function generateForPage(pageId: number) {
  if (!pageId) {
    drawer.value = true
    return
  }
  return generateForNode({
    id: `topic:${pageId}`,
    title: props.nodeTitles?.[String(pageId)] || '当前主题'
  })
}

async function generateForNode(node: any) {
  const nodeId = String(node?.id || '')
  if (!nodeId) {
    drawer.value = true
    return
  }
  selectedNode.value = { id: nodeId, title: String(node?.title || '当前节点') }
  advice.value = null
  trace.value = null
  phase.value = 'reading'
  drawer.value = true
  await nextTick()
  await generate()
}

function rememberGraphTitles(graph: any) {
  if (!graph?.nodes) return
  const next = { ...graphTitles.value }
  for (const node of graph.nodes) {
    if (node?.id && node?.title) next[String(node.id)] = String(node.title)
  }
  graphTitles.value = next
}

async function playTrace(current: any) {
  const steps = current?.steps || []
  phase.value = 'reading'
  await sleep(350)
  if (!steps.length) {
    phase.value = 'thinking'
    return
  }
  phase.value = 'traversing'
  for (let index = 0; index < steps.length; index++) {
    await sleep(1500)
  }
  phase.value = 'thinking'
}

async function generate(instruction = '', parentId = 0, animateTrace = true) {
  if (isBusy.value) return
  if (!selectedNode.value?.id) {
    drawer.value = true
    ElMessage.info('先点一个图谱节点，再生成规划建议')
    return
  }
  const seq = ++runSeq
  advice.value = null
  trace.value = null
  snapshotId.value = 0
  phase.value = 'reading'
  // 从点击节点开始就打开抽屉展示“生成中”，不要先闪一下历史记录。
  drawer.value = true
  try {
    const params = buildParams(instruction)
    const traceRes: any = await prepareStudyTrace(params)
    if (seq !== runSeq) return
    if (traceRes.code !== 200 || !traceRes.data) throw new Error(traceRes.msg || '轨迹生成失败')
    trace.value = traceRes.data.trace || {}
    if (animateTrace) syncState()
    const advicePromise = generateStudyAdvice({
      ...params,
      traceId: trace.value.traceId || '',
      parentSnapshotId: parentId,
      save: true,
      useLlm: true
    })
    if (animateTrace) {
      await playTrace(trace.value)
      // 轨迹播放完毕后再自动打开抽屉，展示完整建议（或思考骨架）。
      drawer.value = true
    } else {
      phase.value = 'thinking'
      drawer.value = true
    }
    const adviceRes: any = await advicePromise
    if (seq !== runSeq) return
    if (adviceRes.code !== 200 || !adviceRes.data) throw new Error(adviceRes.msg || '建议生成失败')
    advice.value = adviceRes.data.advice || null
    snapshotId.value = Number(adviceRes.data.snapshotId || 0)
    rememberGraphTitles(adviceRes.data.graph)
    phase.value = 'ready'
    await loadHistory()
    if (animateTrace) syncState()
  } catch (e: any) {
    if (seq !== runSeq) return
    phase.value = 'idle'
    ElMessage.error(String(e?.message || '生成建议失败'))
  }
}

function adjust(instruction: string) {
  if (!instruction.trim()) return
  // 调整已有建议不重播图谱连线，直接显示 OpenStudy 思考并生成新建议。
  void generate(instruction, snapshotId.value, false)
}

async function open() {
  drawer.value = true
}

async function saveCurrent() {
  if (!advice.value) return
  const res: any = await createStudyPlanHistory({
    kbId: Number(props.activeKbId || 0),
    title: advice.value.title || '',
    scope: advice.value.scope || {},
    advice: advice.value,
    trace: trace.value || {},
    graph: {},
    parentId: snapshotId.value || 0,
    source: 'page'
  })
  if (res.code === 200) {
    snapshotId.value = Number(res.data?.id || snapshotId.value)
    ElMessage.success('已保存到我的规划')
    await loadHistory()
  }
}

async function openHistory() {
  historyOpen.value = true
  await loadHistory()
}

async function loadHistory() {
  try {
    const res: any = await listStudyPlanHistory(20)
    if (res.code === 200) history.value = res.data?.items || []
  } catch {
    history.value = []
  }
}

async function loadHistoryItem(item: any) {
  const res: any = await getStudyPlanHistory(Number(item.id))
  if (res.code !== 200 || !res.data) {
    ElMessage.error(res.msg || '读取规划失败')
    return
  }
  runSeq++
  // 先清空旧轨迹，确保再次载入历史时 parent 能重新触发连线动画。
  advice.value = null
  trace.value = null
  await nextTick()
  advice.value = res.data.advice || null
  trace.value = res.data.trace || null
  rememberGraphTitles(res.data.graph)
  snapshotId.value = Number(res.data.id || 0)
  phase.value = 'ready'
  drawer.value = true
  historyOpen.value = false
  const seedRaw = String(
    res.data.scope?.seedNodeId ||
    res.data.advice?.scope?.seedNodeId ||
    res.data.trace?.seedNodeId ||
    ''
  )
  const seedPageId = Number(seedRaw.replace(/^topic:/, ''))
  if (seedPageId) {
    selectedNode.value = { id: `topic:${seedPageId}`, title: props.nodeTitles?.[String(seedPageId)] || '' }
    emit('focus-page', seedPageId)
  }
  syncState()
}

async function renameHistory(item: any, title: string) {
  await updateStudyPlanHistory(Number(item.id), { title })
  await loadHistory()
}

async function pinHistory(item: any) {
  await updateStudyPlanHistory(Number(item.id), { pinned: !item.pinned })
  await loadHistory()
}

async function deleteHistory(item: any) {
  await deleteStudyPlanHistory(Number(item.id))
  await loadHistory()
}

function clear() {
  runSeq++
  drawer.value = false
  selectedNode.value = null
  advice.value = null
  trace.value = null
  snapshotId.value = 0
  phase.value = 'idle'
  syncState()
}

onMounted(loadHistory)

defineExpose({ generateForPage, generateForNode, open, clear })
</script>

<style scoped>
.kah__drawer { height: 100%; overflow-y: auto; overscroll-behavior: contain; padding: 10px; box-sizing: border-box; scrollbar-width: thin; scrollbar-color: #cfd8e6 transparent; }
.kah__drawer::-webkit-scrollbar { width: 6px; }
.kah__drawer::-webkit-scrollbar-thumb { border-radius: 99px; background: #cfd8e6; }
</style>
