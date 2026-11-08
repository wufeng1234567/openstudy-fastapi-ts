<template>
  <div class="dsr">
    <div class="dsr__intro">
      <div>
        <div class="dsr__eyebrow">智能报告</div>
        <h3 class="dsr__title">这份资料，可以哪里做得更好</h3>
        <p class="dsr__sub">基于资料体检的真实结果，给出更新目标和改进建议；不排任务，也不要求你打卡。</p>
      </div>
      <div v-if="baseline" class="dsr__score">
        <span>体检基线</span>
        <b>{{ baseline.score ?? '—' }}</b>
        <small>{{ baseline.issueCount ?? 0 }} 项待处理</small>
      </div>
    </div>

    <div class="dsr__bar">
      <el-input v-model="instruction" size="small" clearable maxlength="300" show-word-limit
        placeholder="可选：告诉 AI 你更关心什么，例如「我想把它变成可练习的复习资料」" />
      <el-button type="primary" size="small" :loading="generating" :disabled="!doc" @click="generate">
        {{ generating ? 'AI 正在读资料…' : report ? '重新生成' : '生成智能报告' }}
      </el-button>
    </div>

    <div v-if="error" class="dsr__error">{{ error }}</div>

    <div v-if="generating" class="dsr__loading">
      <div class="dsr__pulse"></div>
      <b>AI 正在读体检结果和章节内容</b>
      <span>它会先看这份资料缺什么，再给出可以做得更好的地方。</span>
    </div>

    <div v-else-if="!report" class="dsr__empty">
      <div class="dsr__empty-mark">◇</div>
      <b>还没有智能报告</b>
      <span>点上方按钮，系统会根据体检结果告诉你：这份资料下一步该补什么、怎么补。</span>
    </div>

    <template v-else>
      <section class="dsr__goal">
        <span>更新目标</span>
        <b>{{ report.updateGoal || '把这份资料整理成可学习、可练习的内容' }}</b>
        <p>{{ report.verdict }}</p>
      </section>

      <div v-if="report.strengths?.length" class="dsr__strengths">
        <span v-for="item in report.strengths" :key="item">{{ item }}</span>
      </div>

      <section class="dsr__block">
        <header>
          <h4>可以做得更好的地方</h4>
          <span>{{ report.improvements?.length || 0 }} 项</span>
        </header>
        <article v-for="(item, index) in report.improvements || []" :key="`${item.priority}-${index}`" class="dsr__item">
          <span class="dsr__priority" :class="`is-${String(item.priority || 'P1').toLowerCase()}`">{{ item.priority || 'P1' }}</span>
          <div class="dsr__item-main">
            <div class="dsr__item-title">
              {{ item.problem || '可优化项' }}
              <em v-if="item.sectionTitle">· {{ item.sectionTitle }}</em>
            </div>
            <p>{{ item.action }}</p>
            <span v-if="item.evidence" class="dsr__evidence">{{ item.evidence }}</span>
          </div>
          <button v-if="Number(item.sectionIndex) >= 0" type="button" class="dsr__locate" @click="locate(item)">看原文</button>
        </article>
        <div v-if="!report.improvements?.length" class="dsr__empty-inline">这份资料暂时没有发现明显的改进项。</div>
      </section>

      <section v-if="report.nextSteps?.length" class="dsr__block">
        <header><h4>建议下一步</h4></header>
        <p v-for="item in report.nextSteps" :key="item" class="dsr__line">{{ item }}</p>
      </section>

      <section v-if="report.risks?.length" class="dsr__block dsr__risks">
        <header><h4>需要注意</h4></header>
        <p v-for="item in report.risks" :key="item" class="dsr__line">{{ item }}</p>
      </section>

      <p class="dsr__degraded" v-if="report.degraded?.llmFallback">当前使用规则模板生成；AI 解读暂不可用，报告中仍只使用体检真实数据。</p>
    </template>

    <div class="dsr__footer">
      <span>智能报告只给建议，不改动原文；需要改资料时再走「开始整理」。</span>
      <el-button text size="small" @click="emit('close')">关闭</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { generateSmartReport } from '@/api/ai/documentClinic'

interface SmartReportDoc {
  docId: number
  fileName?: string
}

const emit = defineEmits<{
  (e: 'locate', doc: SmartReportDoc, section: any): void
  (e: 'close'): void
}>()

const doc = ref<SmartReportDoc | null>(null)
const baseline = ref<any>(null)
const report = ref<any>(null)
const instruction = ref('')
const generating = ref(false)
const error = ref('')

async function open(nextDoc: SmartReportDoc) {
  doc.value = nextDoc
  report.value = null
  baseline.value = null
  instruction.value = ''
  error.value = ''
}

async function generate() {
  if (!doc.value?.docId || generating.value) return
  generating.value = true
  error.value = ''
  try {
    const res: any = await generateSmartReport(Number(doc.value.docId), {
      instruction: instruction.value,
      useLlm: true
    })
    if (res.code !== 200 || !res.data) throw new Error(res.msg || '生成失败')
    report.value = res.data.report || null
    baseline.value = res.data.baseline || null
  } catch (e: any) {
    error.value = String(e?.message || '生成智能报告失败')
    ElMessage.error(error.value)
  } finally {
    generating.value = false
  }
}

function locate(item: any) {
  if (!doc.value) return
  emit('locate', doc.value, {
    start: Number(item.start || 0),
    title: String(item.sectionTitle || ''),
    sectionIndex: Number(item.sectionIndex)
  })
}

defineExpose({ open })
</script>

<style scoped>
.dsr { display: flex; flex-direction: column; gap: 10px; padding: 2px 0 0; }
.dsr__intro { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.dsr__eyebrow { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.dsr__title { margin: 5px 0 4px; color: #253247; font-size: 20px; }
.dsr__sub { margin: 0; color: #7d8596; font-size: 12px; line-height: 1.6; }
.dsr__score { display: flex; min-width: 104px; flex-direction: column; align-items: flex-end; gap: 2px; padding: 10px 12px; border: 1px solid #e8edf5; border-radius: 10px; background: #fbfcff; }
.dsr__score span { color: #8a91a0; font-size: 10px; }
.dsr__score b { color: #2f5fce; font-size: 24px; line-height: 1; }
.dsr__score small { color: #a0a8b6; font-size: 10px; }
.dsr__bar { display: flex; gap: 6px; }
.dsr__bar :deep(.el-input) { flex: 1; }
.dsr__error { padding: 7px 9px; border: 1px solid #f4d7d3; border-radius: 7px; color: #b94a44; background: #fff8f7; font-size: 11px; }
.dsr__loading { display: flex; min-height: 260px; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #8a91a0; text-align: center; }
.dsr__loading b { color: #5f6b7d; font-size: 13px; }
.dsr__loading span { font-size: 11px; }
.dsr__pulse { width: 42px; height: 42px; border: 2px solid #c9d9f8; border-radius: 50%; background: radial-gradient(circle, #eaf1ff 0 38%, transparent 40%); animation: dsr-pulse 1.2s ease-in-out infinite; }
@keyframes dsr-pulse { 50% { transform: scale(.82); opacity: .55; } }
.dsr__empty { display: flex; min-height: 260px; flex-direction: column; align-items: center; justify-content: center; gap: 7px; color: #9aa3b2; text-align: center; }
.dsr__empty-mark { color: #c4d3ed; font-size: 24px; }
.dsr__empty b { color: #5f6b7d; font-size: 13px; }
.dsr__empty span { max-width: 340px; font-size: 11px; line-height: 1.55; }
.dsr__goal { padding: 11px 12px; border: 1px solid #dbe7ff; border-radius: 9px; background: #f7faff; }
.dsr__goal span { color: #2f5fce; font-size: 10px; font-weight: 700; letter-spacing: .06em; }
.dsr__goal b { display: block; margin: 5px 0; color: #253247; font-size: 15px; line-height: 1.5; }
.dsr__goal p { margin: 0; color: #7d8596; font-size: 11px; line-height: 1.55; }
.dsr__strengths { display: flex; flex-wrap: wrap; gap: 5px; }
.dsr__strengths span { padding: 2px 7px; border: 1px solid #d9eee9; border-radius: 99px; color: #2f7e72; background: #f5fcfa; font-size: 10px; }
.dsr__block { padding: 9px 10px; border: 1px solid #edf1f7; border-radius: 9px; background: #fff; }
.dsr__block header { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.dsr__block h4 { margin: 0; color: #253247; font-size: 12px; }
.dsr__block header span { color: #a0a8b6; font-size: 10px; }
.dsr__item { display: flex; align-items: flex-start; gap: 7px; padding: 7px 0; border-top: 1px solid #f3f5f9; }
.dsr__item:first-of-type { border-top: 0; }
.dsr__priority { flex: none; padding: 1px 5px; border-radius: 4px; font-size: 9px; font-weight: 700; }
.dsr__priority.is-p0 { color: #b94a44; background: #fdeceb; }
.dsr__priority.is-p1 { color: #a86a16; background: #fff6e6; }
.dsr__priority.is-p2 { color: #2f6f96; background: #eef7fd; }
.dsr__item-main { min-width: 0; flex: 1; }
.dsr__item-title { color: #4d5d78; font-size: 11px; font-weight: 600; line-height: 1.45; }
.dsr__item-title em { color: #9aa3b2; font-style: normal; font-weight: 400; }
.dsr__item p { margin: 3px 0; color: #7d8596; font-size: 10px; line-height: 1.5; }
.dsr__evidence { color: #a0a8b6; font-size: 10px; }
.dsr__locate { flex: none; padding: 0; border: 0; color: #2f5fce; background: transparent; cursor: pointer; font: inherit; font-size: 10px; }
.dsr__line { margin: 3px 0; color: #7d8596; font-size: 10px; line-height: 1.5; }
.dsr__risks .dsr__line { color: #9a6a20; }
.dsr__empty-inline { color: #a0a8b6; font-size: 10px; }
.dsr__degraded { margin: 0; color: #a0a8b6; font-size: 10px; }
.dsr__footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-top: 6px; border-top: 1px solid #f0f3f8; color: #a0a8b6; font-size: 10px; }
</style>
