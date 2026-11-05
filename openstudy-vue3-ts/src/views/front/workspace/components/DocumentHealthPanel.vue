<!--
  资料体检报告
  ----------------------------------------------------------------------------
  设计目的：把「这份资料值不值得整理、整理完能变成什么」在一屏内讲清楚。

  它不是后台统计面板，而是智能整理的前置诊断：
    · 四维评分：结构 / 图文 / 知识覆盖 / 可学习化；
    · 问题清单：每条带 P0/P1/P2 和修复动作；
    · 章节覆盖热力：绿=讲解+练习，黄=有讲解缺练习，红=内容过薄；
    · 底部「开始整理」直接进入整理手术台。

  所有数字来自后端规则计算，不调用模型；重开同一份资料分数不变。
-->
<template>
  <div class="dh-panel">
    <div v-loading="loading" class="dh-body">
      <div v-if="error" class="dh-empty dh-empty--error">
        <p>体检失败</p>
        <span>{{ error }}</span>
        <el-button size="small" @click="load">重新体检</el-button>
      </div>

      <template v-else-if="report">
        <!-- 顶部总览：总分 + 结论 + 四维指标 -->
        <div class="dh-hero">
          <div class="dh-score" :class="`is-${report.grade?.tone || 'blue'}`">
            <div class="dh-score__ring" :style="{ '--score': `${report.score}%` }">
              <div class="dh-score__inner">
                <b>{{ report.score }}</b>
                <span>综合分</span>
              </div>
            </div>
            <div class="dh-score__label">{{ report.grade?.label || '待评估' }}</div>
          </div>

          <div class="dh-hero__main">
            <div class="dh-hero__title">
              先看诊断，再决定怎么整理
            </div>
            <div class="dh-hero__summary">
              {{ summaryText }}
            </div>
            <div class="dh-hero__chips">
              <span class="dh-chip dh-chip--ink">{{ report.stats?.sectionCount || 0 }} 个章节</span>
              <span class="dh-chip dh-chip--ink">{{ report.stats?.wordCount || 0 }} 字</span>
              <span class="dh-chip dh-chip--ink">{{ report.stats?.imageCount || 0 }} 张图</span>
              <span class="dh-chip dh-chip--ink">{{ report.stats?.questionCount || 0 }} 道题</span>
              <span class="dh-chip dh-chip--warn">{{ issueCount }} 项待处理</span>
            </div>
          </div>
        </div>

        <div class="dh-metrics">
          <div v-for="metric in report.metrics" :key="metric.key" class="dh-metric">
            <div class="dh-metric__head">
              <span class="dh-metric__label">{{ metric.label }}</span>
              <span class="dh-metric__score" :class="scoreTone(metric.score)">{{ metric.score }}</span>
            </div>
            <div class="dh-metric__bar">
              <span :style="{ width: `${metric.score}%` }" :class="scoreTone(metric.score)"></span>
            </div>
            <div class="dh-metric__detail">{{ metric.detail }}</div>
            <ul v-if="metric.evidence?.length" class="dh-metric__evidence">
              <li v-for="(line, idx) in metric.evidence.slice(0, 3)" :key="idx">{{ line }}</li>
            </ul>
          </div>
        </div>

        <div class="dh-grid">
          <!-- 左：问题清单 -->
          <section class="dh-panel dh-panel--issues">
            <div class="dh-panel__head">
              <span>问题清单</span>
              <span class="dh-panel__hint">按严重度排序 · 每条都可追到证据</span>
            </div>
            <div v-if="report.issues?.length" class="dh-issues">
              <div v-for="issue in report.issues" :key="issue.id" class="dh-issue">
                <span class="dh-sev" :class="`is-${issue.severity.toLowerCase()}`">{{ issue.severity }}</span>
                <div class="dh-issue__main">
                  <div class="dh-issue__title">
                    {{ issue.title }}
                    <span v-if="issue.count > 1" class="dh-issue__count">×{{ issue.count }}</span>
                  </div>
                  <div class="dh-issue__detail">{{ issue.detail }}</div>
                </div>
                <button type="button" class="dh-issue__action" @click="handleIssue(issue)">
                  {{ issue.fixAction === 'organize' ? '去整理' : issue.fixAction === 'questions' ? '去出题' : '看章节' }}
                </button>
              </div>
            </div>
            <div v-else class="dh-empty dh-empty--good">
              没有发现需要处理的问题。这份资料的结构、图文和可学习化程度都不错。
            </div>
          </section>

          <!-- 右：章节覆盖热力图 -->
          <section class="dh-panel dh-panel--heat">
            <div class="dh-panel__head">
              <span>章节覆盖热力图</span>
              <span class="dh-panel__hint">绿：讲解+练习 · 黄：有讲解缺练习 · 红：内容过薄</span>
            </div>
            <div class="dh-heat-search">
              <el-input v-model="sectionKeyword" size="small" clearable placeholder="搜索章节，例如「牛顿」" />
              <span class="dh-heat-search__count">{{ visibleSections.length }} / {{ report.sections?.length || 0 }}</span>
            </div>
            <div class="dh-heatbar" :title="heatTitle">
              <span
                v-for="section in visibleSections"
                :key="`bar-${section.index}`"
                class="dh-heatbar__seg"
                :class="`is-${section.coverage}`"
                :style="{ flexGrow: Math.max(1, section.chars) }"
              ></span>
            </div>
            <div v-if="!visibleSections.length" class="dh-empty">
              没有匹配的章节，换个关键词试试。
            </div>
            <div v-else class="dh-sections">
              <button
                v-for="section in visibleSections"
                :key="section.index"
                type="button"
                class="dh-section"
                @click="emitLocate(section)"
              >
                <span class="dh-section__dot" :class="`is-${section.coverage}`"></span>
                <span class="dh-section__main">
                  <span class="dh-section__title">{{ section.title }}</span>
                  <span class="dh-section__meta">
                    {{ section.chars }} 字
                    <template v-if="section.questions"> · {{ section.questions }} 题</template>
                    <template v-if="section.images"> · {{ section.images }} 图</template>
                    <template v-if="section.formulas"> · {{ section.formulas }} 公式</template>
                    <em :class="`is-${section.coverage}`">{{ section.coverageLabel }}</em>
                  </span>
                  <span v-if="section.excerpt" class="dh-section__excerpt">{{ section.excerpt }}</span>
                </span>
              </button>
            </div>
          </section>
        </div>
      </template>
    </div>

    <div class="dh-footer">
      <span class="dh-footer__hint">体检只做诊断，不会改动原文；整理会先生成可逐项确认的方案。</span>
      <div class="dh-footer__actions">
        <el-button @click="closePanel">关闭</el-button>
        <el-button :loading="loading" @click="load">重新体检</el-button>
        <el-button type="primary" :disabled="!report" @click="startOrganize">
          开始整理
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getDocumentHealth } from '@/api/ai/workspace'

defineOptions({ name: 'DocumentHealthPanel' })

interface HealthDoc {
  docId: number
  fileName?: string
}

const emit = defineEmits<{
  (e: 'organize', doc: HealthDoc): void
  (e: 'locate', doc: HealthDoc, section: any): void
  (e: 'ask', doc: HealthDoc, issue: any): void
  (e: 'close'): void
}>()

const visible = ref(false)
const currentDoc = ref<HealthDoc | null>(null)
const loading = ref(false)
const error = ref('')
const report = ref<any>(null)
const sectionKeyword = ref('')
let loadSeq = 0

const issueCount = computed(() => (report.value?.issues || []).length)

const visibleSections = computed(() => {
  const keyword = sectionKeyword.value.trim().toLowerCase()
  const sections = report.value?.sections || []
  if (!keyword) return sections
  return sections.filter((s: any) =>
    `${s.title || ''} ${s.excerpt || ''}`.toLowerCase().includes(keyword)
  )
})

const summaryText = computed(() => {
  const r = report.value
  if (!r) return ''
  const issue = (r.issues || [])[0]
  if (!issue) return '结构、图文与学习化程度都达到可用水平，可以直接生成学习资产。'
  return `最优先处理：${issue.title}。${issue.detail}`
})

const heatTitle = computed(() =>
  (visibleSections.value || [])
    .map((s: any) => `${s.title}：${s.coverageLabel}`)
    .join('\n')
)

function scoreTone(score: number): string {
  if (score >= 85) return 'is-green'
  if (score >= 70) return 'is-blue'
  if (score >= 55) return 'is-orange'
  return 'is-red'
}

async function load() {
  if (!currentDoc.value?.docId) return
  const seq = ++loadSeq
  loading.value = true
  error.value = ''
  report.value = null
  sectionKeyword.value = ''
  try {
    const res: any = await getDocumentHealth(currentDoc.value.docId)
    if (seq !== loadSeq) return
    if (res.code !== 200) throw new Error(res.msg || '体检接口返回异常')
    report.value = res.data
  } catch (e: any) {
    if (seq === loadSeq) error.value = e?.message || String(e)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function handleIssue(issue: any) {
  if (!currentDoc.value) return
  if (issue.fixAction === 'organize') {
    visible.value = false
    emit('organize', currentDoc.value)
    return
  }
  if (issue.fixAction === 'questions') {
    emit('ask', currentDoc.value, issue)
    return
  }
  const first = (report.value?.sections || []).find((s: any) => s.coverage === 'thin')
    || report.value?.sections?.[0]
  if (first) emit('locate', currentDoc.value, first)
}

function emitLocate(section: any) {
  if (currentDoc.value) emit('locate', currentDoc.value, section)
}

function startOrganize() {
  if (!currentDoc.value) return
  emit('organize', currentDoc.value)
}

function closePanel() {
  emit('close')
}

function open(docValue: HealthDoc) {
  currentDoc.value = docValue
  visible.value = true
  load()
}

defineExpose({ open, load })
</script>

<style scoped>
.dh-dialog :deep(.el-dialog__body) {
  padding-top: 4px;
  padding-bottom: 8px;
}

.dh-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-right: 28px;
}

.dh-head__eyebrow {
  margin-bottom: 3px;
  color: #2563eb;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.dh-head__title {
  color: var(--os-text-1, #111827);
  font-size: 18px;
  font-weight: 700;
}

.dh-head__meta {
  color: var(--os-text-3, #9ca3af);
  font-size: 11.5px;
}

.dh-body {
  min-height: 460px;
  max-height: 72vh;
  overflow: auto;
  padding: 4px 2px;
}

.dh-hero {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 18px 20px;
  margin-bottom: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background:
    radial-gradient(circle at 100% 0%, rgba(37, 99, 235, 0.08), transparent 38%),
    #fbfcff;
}

.dh-score {
  flex: none;
  text-align: center;
}

.dh-score__ring {
  display: grid;
  width: 108px;
  height: 108px;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--ring, #2563eb) var(--score), #e5e7eb 0);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}

.dh-score__inner {
  display: flex;
  width: 82px;
  height: 82px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #fff;
}

.dh-score__inner b {
  color: #111827;
  font-size: 30px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.dh-score__inner span {
  margin-top: 5px;
  color: #9ca3af;
  font-size: 10.5px;
}

.dh-score__label {
  margin-top: 7px;
  color: #374151;
  font-size: 12px;
  font-weight: 600;
}

.dh-score.is-green .dh-score__ring { --ring: #16a34a; }
.dh-score.is-blue .dh-score__ring { --ring: #2563eb; }
.dh-score.is-orange .dh-score__ring { --ring: #d97706; }
.dh-score.is-red .dh-score__ring { --ring: #dc2626; }

.dh-hero__main {
  min-width: 0;
}

.dh-hero__title {
  margin-bottom: 6px;
  color: #111827;
  font-size: 16px;
  font-weight: 700;
}

.dh-hero__summary {
  color: #4b5563;
  font-size: 13px;
  line-height: 1.7;
}

.dh-hero__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}

.dh-chip {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.dh-chip--ink {
  color: #374151;
  background: #f3f4f6;
}

.dh-chip--warn {
  color: #92400e;
  background: #fef3c7;
}

.dh-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.dh-metric {
  min-width: 0;
  padding: 12px 13px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
}

.dh-metric__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.dh-metric__label {
  color: #374151;
  font-size: 12.5px;
  font-weight: 700;
}

.dh-metric__score {
  font-size: 22px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.dh-metric__score.is-green { color: #16a34a; }
.dh-metric__score.is-blue { color: #2563eb; }
.dh-metric__score.is-orange { color: #d97706; }
.dh-metric__score.is-red { color: #dc2626; }

.dh-metric__bar {
  height: 5px;
  margin: 8px 0 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #f1f5f9;
}

.dh-metric__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.dh-metric__bar .is-green { background: #16a34a; }
.dh-metric__bar .is-blue { background: #2563eb; }
.dh-metric__bar .is-orange { background: #d97706; }
.dh-metric__bar .is-red { background: #dc2626; }

.dh-metric__detail {
  color: #4b5563;
  font-size: 11.5px;
  line-height: 1.55;
}

.dh-metric__evidence {
  margin: 6px 0 0;
  padding-left: 15px;
  color: #9ca3af;
  font-size: 10.5px;
  line-height: 1.6;
}

.dh-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 12px;
}

.dh-panel {
  min-width: 0;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
}

.dh-panel__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 13px;
  border-bottom: 1px solid #f0f2f5;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
}

.dh-panel__hint {
  color: #9ca3af;
  font-size: 10.5px;
  font-weight: 400;
}

.dh-issues {
  max-height: 350px;
  overflow: auto;
}

.dh-issue {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px 12px;
  border-top: 1px solid #f5f6f8;
}

.dh-issue:first-child {
  border-top: 0;
}

.dh-sev {
  flex: none;
  margin-top: 1px;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 10px;
  font-weight: 700;
}

.dh-sev.is-p0 { color: #991b1b; background: #fee2e2; }
.dh-sev.is-p1 { color: #9a3412; background: #ffedd5; }
.dh-sev.is-p2 { color: #1e40af; background: #dbeafe; }

.dh-issue__main {
  min-width: 0;
}

.dh-issue__title {
  color: #1f2937;
  font-size: 12.5px;
  font-weight: 600;
}

.dh-issue__count {
  margin-left: 5px;
  color: #9ca3af;
  font-size: 10.5px;
  font-weight: 400;
}

.dh-issue__detail {
  margin-top: 2px;
  color: #6b7280;
  font-size: 11px;
  line-height: 1.6;
  word-break: break-word;
}

.dh-issue__action {
  flex: none;
  margin-left: auto;
  padding: 3px 7px;
  border: 1px solid #dbeafe;
  border-radius: 5px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 11px;
  cursor: pointer;
}

.dh-issue__action:hover {
  border-color: #2563eb;
}

.dh-heat-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px 0;
}

.dh-heat-search :deep(.el-input) {
  width: 190px;
}

.dh-heat-search__count {
  color: #9ca3af;
  font-size: 10.5px;
}

.dh-heatbar {
  display: flex;
  gap: 2px;
  height: 18px;
  margin: 11px 13px 8px;
  overflow: hidden;
  border-radius: 5px;
  background: #f1f5f9;
}

.dh-heatbar__seg {
  flex-basis: 0;
  min-width: 4px;
  border-radius: 2px;
}

.dh-heatbar__seg.is-good,
.dh-section__dot.is-good { background: #16a34a; }
.dh-heatbar__seg.is-partial,
.dh-section__dot.is-partial { background: #f59e0b; }
.dh-heatbar__seg.is-thin,
.dh-section__dot.is-thin { background: #ef4444; }

.dh-sections {
  max-height: 312px;
  overflow: auto;
  padding-bottom: 6px;
}

.dh-section {
  display: flex;
  width: 100%;
  gap: 8px;
  padding: 7px 12px;
  border: 0;
  border-top: 1px solid #f7f8fa;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.dh-section:hover {
  background: #f8fafc;
}

.dh-section__dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
}

.dh-section__main {
  min-width: 0;
}

.dh-section__title {
  display: block;
  overflow: hidden;
  color: #1f2937;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dh-section__meta {
  display: block;
  margin-top: 2px;
  color: #9ca3af;
  font-size: 10.5px;
}

.dh-section__meta em {
  margin-left: 6px;
  font-style: normal;
  font-weight: 600;
}

.dh-section__meta em.is-good { color: #15803d; }
.dh-section__meta em.is-partial { color: #b45309; }
.dh-section__meta em.is-thin { color: #b91c1c; }

.dh-section__excerpt {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #b0b7c3;
  font-size: 10.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dh-empty {
  padding: 34px 18px;
  color: #9ca3af;
  font-size: 12.5px;
  text-align: center;
}

.dh-empty--error {
  color: #ef4444;
}

.dh-empty--error p {
  margin: 0 0 4px;
  font-weight: 600;
}

.dh-empty--error span {
  display: block;
  margin-bottom: 10px;
  color: #6b7280;
}

.dh-empty--good {
  color: #15803d;
  background: #f0fdf4;
}

.dh-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dh-footer__hint {
  color: #9ca3af;
  font-size: 11px;
}

.dh-footer__actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 980px) {
  .dh-metrics,
  .dh-grid {
    grid-template-columns: 1fr;
  }

  .dh-hero {
    align-items: flex-start;
  }
}
</style>
