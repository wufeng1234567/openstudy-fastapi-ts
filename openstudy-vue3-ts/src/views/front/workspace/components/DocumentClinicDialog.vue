<!--
  学习材料诊疗室（统一工作台）
  ============================================================================
  背景：资料体检、资料装配、资料解剖原本是文档行里的三个独立入口，三个弹窗、
  三套标题，用户要先理解“这是三个功能”才能用。对同一份资料来说，它们其实是
  同一条工作流的三步：

      先体检（哪里有问题） → 再刨析（里面有什么） → 最后装配（能变成什么）

  所以这里把它们收成一个入口「资料诊疗室」和一套工作台：
    · 一个按钮进入，左侧三步导航，右侧只显示当前步骤；
    · 三步共用同一份文档上下文，不用反复关窗、重新找文件；
    · “资料解剖 / 资料刨析”统一改为“原文阅读”，与体检、学习处方并列；
    · 每个面板仍复用原来的真实数据与操作，不伪造分数和产物。

  组件边界：
    · DocumentHealthPanel   —— 体检报告（只读规则计算）
    · DocumentAnatomyPanel  —— 结构 / 正文 / 图片资产
    · StudyPrescriptionPanel —— 按天执行、可勾完成、可复诊的学习计划
-->
<template>
  <el-dialog
    v-model="visible"
    width="min(1280px, 94vw)"
    top="3vh"
    append-to-body
    destroy-on-close
    class="clinic-dialog"
    @closed="reset"
  >
    <template #header>
      <div class="clinic-head">
        <div class="clinic-head__main">
          <div class="clinic-head__eyebrow">学习材料诊疗室</div>
          <div class="clinic-head__title">资料诊疗室</div>
          <div class="clinic-head__doc" :title="docName">{{ docName }}</div>
        </div>
        <div class="clinic-head__meta">先体检，再读原文，最后开一份学习处方</div>
      </div>
    </template>

    <div class="clinic-tabs" role="tablist" aria-label="资料诊疗步骤">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="clinic-tab"
        :class="{ 'is-active': activeTab === tab.key }"
        role="tab"
        :aria-selected="activeTab === tab.key"
        @click="switchTab(tab.key)"
      >
        <span class="clinic-tab__no">{{ tab.no }}</span>
        <span class="clinic-tab__copy">
          <b>{{ tab.label }}</b>
          <small>{{ tab.desc }}</small>
        </span>
      </button>
    </div>

    <div class="clinic-body">
      <section class="clinic-content">
        <DocumentHealthPanel
          v-show="activeTab === 'health'"
          ref="healthRef"
          @organize="handleOrganize"
          @locate="handleLocate"
          @ask="handleAsk"
          @close="close"
        />
        <DocumentAnatomyPanel
          v-show="activeTab === 'anatomy'"
          ref="anatomyRef"
          :show-edit="showEdit"
          @edit="handleEdit"
        />
        <StudyPrescriptionPanel
          v-show="activeTab === 'prescription'"
          ref="prescriptionRef"
          @locate="handleLocate"
          @ask="handleAsk"
          @close="close"
        />
      </section>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import DocumentHealthPanel from './DocumentHealthPanel.vue'
import DocumentAnatomyPanel from './DocumentAnatomyPanel.vue'
import StudyPrescriptionPanel from './StudyPrescriptionPanel.vue'

defineOptions({ name: 'DocumentClinicDialog' })

interface ClinicDoc {
  docId: number
  fileName?: string
  chunkCount?: number
  kbId?: number
}

type ClinicTab = 'health' | 'anatomy' | 'prescription'

const props = withDefaults(
  defineProps<{
    showEdit?: boolean
  }>(),
  { showEdit: false }
)

const emit = defineEmits<{
  (e: 'organize', doc: ClinicDoc): void
  (e: 'locate', doc: ClinicDoc, section: any): void
  (e: 'ask', doc: ClinicDoc, issue: any): void
  (e: 'edit', doc: ClinicDoc): void
}>()

const visible = ref(false)
const currentDoc = ref<ClinicDoc | null>(null)
const activeTab = ref<ClinicTab>('health')
const healthRef = ref<any>(null)
const anatomyRef = ref<any>(null)
const prescriptionRef = ref<any>(null)
const openedTabs = ref<Set<ClinicTab>>(new Set())

const tabs: Array<{ key: ClinicTab; no: string; label: string; desc: string }> = [
  { key: 'health', no: '01', label: '资料体检', desc: '先看问题，再决定怎么整理' },
  { key: 'anatomy', no: '02', label: '原文阅读', desc: '按章节阅读、搜索与定位原文' },
  { key: 'prescription', no: '03', label: '学习处方', desc: '按天执行，学完还能复诊' }
]

const docName = computed(() => currentDoc.value?.fileName || '未命名资料')

function panelRef(tab: ClinicTab) {
  if (tab === 'health') return healthRef.value
  if (tab === 'anatomy') return anatomyRef.value
  return prescriptionRef.value
}

async function ensureTab(tab: ClinicTab, opts?: any) {
  if (!currentDoc.value) return
  await nextTick()
  if (!openedTabs.value.has(tab)) {
    const panel = panelRef(tab)
    if (tab === 'health') panel?.open(currentDoc.value)
    else if (tab === 'anatomy') panel?.open(currentDoc.value, opts)
    else panel?.open(currentDoc.value)
    openedTabs.value.add(tab)
  } else if (tab === 'anatomy' && opts) {
    // 从体检章节跳过来：复用同一个面板，但重新定位到指定字符偏移。
    panelRef(tab)?.open(currentDoc.value, opts)
  }
}

async function open(doc: ClinicDoc, tab: ClinicTab = 'health', opts?: any) {
  currentDoc.value = doc
  activeTab.value = tab
  openedTabs.value = new Set()
  visible.value = true
  await ensureTab(tab, opts)
}

async function switchTab(tab: ClinicTab) {
  activeTab.value = tab
  await ensureTab(tab)
}

function close() {
  visible.value = false
}

function reset() {
  currentDoc.value = null
  activeTab.value = 'health'
  openedTabs.value = new Set()
}

function handleOrganize(doc: ClinicDoc) {
  visible.value = false
  emit('organize', doc)
}

function handleLocate(doc: ClinicDoc, section: any) {
  activeTab.value = 'anatomy'
  nextTick(() => {
    anatomyRef.value?.open(doc, {
      offset: Number(section?.start || 0),
      targetText: String(section?.title || '')
    })
    openedTabs.value.add('anatomy')
  })
}

function handleAsk(doc: ClinicDoc, issue: any) {
  emit('ask', doc, issue)
}

function handleEdit(doc: ClinicDoc) {
  emit('edit', doc)
}

defineExpose({ open, close })
</script>

<style scoped>
.clinic-dialog :deep(.el-dialog__body) {
  padding: 0;
}

.clinic-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-right: 28px;
}

.clinic-head__eyebrow {
  margin-bottom: 3px;
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.clinic-head__title {
  color: #111827;
  font-size: 19px;
  font-weight: 700;
}

.clinic-head__doc {
  overflow: hidden;
  max-width: 760px;
  margin-top: 4px;
  color: #4b5563;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clinic-head__meta {
  flex: none;
  color: #9ca3af;
  font-size: 12px;
}

.clinic-tabs {
  display: flex;
  gap: 8px;
  padding: 12px 22px;
  border-top: 1px solid #eef2f7;
  border-bottom: 1px solid #eef2f7;
  background: #fbfdff;
}

.clinic-tab {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: #f6f8fc;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.clinic-tab:hover {
  border-color: #dbeafe;
  background: #f2f7ff;
}

.clinic-tab.is-active {
  border-color: #bfdbfe;
  background: #eff6ff;
  box-shadow: inset 0 -2px 0 #2563eb;
}

.clinic-tab__no {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  font-size: 10px;
  font-weight: 700;
}

.clinic-tab.is-active .clinic-tab__no {
  background: #2563eb;
  color: #fff;
}

.clinic-tab__copy {
  min-width: 0;
}

.clinic-tab__copy b {
  display: block;
  color: #374151;
  font-size: 13.5px;
}

.clinic-tab__copy small {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #9ca3af;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.clinic-tab.is-active .clinic-tab__copy b {
  color: #1d4ed8;
}

.clinic-body {
  height: calc(88vh - 188px);
  min-height: 520px;
  overflow: hidden;
}

.clinic-content {
  height: 100%;
  min-width: 0;
  padding: 16px 22px 14px;
  overflow: hidden;
}

.clinic-content :deep(.dh-panel),
.clinic-content :deep(.sp-panel),
.clinic-content :deep(.kbp-anatomy-shell),
.clinic-content :deep(.kbp-anatomy-panel) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.clinic-content :deep(.dh-body),
.clinic-content :deep(.sp-body),
.clinic-content :deep(.kbp-anatomy) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.clinic-content :deep(.dh-body) {
  max-height: none;
}
</style>
