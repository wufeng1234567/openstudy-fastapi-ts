<template>
  <aside ref="exportRoot" class="sap" :class="{ 'is-exporting': exporting }">
    <header class="sap__head">
      <div>
        <span class="sap__eyebrow">规划建议</span>
        <h3>{{ advice?.title || '先选一个起点，再生成建议' }}</h3>
      </div>
      <div class="sap__head-actions">
        <el-dropdown v-if="advice" trigger="click" @command="exportAdvice">
          <el-button size="small" text>导出</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="image">导出图片（PNG）</el-dropdown-item>
              <el-dropdown-item command="text">导出文本（TXT）</el-dropdown-item>
              <el-dropdown-item command="pdf">导出 PDF</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-if="advice" size="small" plain @click="emit('save')">保存</el-button>
        <el-button size="small" text @click="emit('history')">历史</el-button>
      </div>
    </header>

    <div v-if="loading" class="sap__skeleton">
      <i></i><i></i><i></i><i></i>
      <span>{{ phase === 'thinking' ? 'OpenStudy 正在思考…' : '正在生成建议…' }}</span>
    </div>

    <template v-else-if="advice">
      <p class="sap__summary">{{ advice.summary }}</p>

      <div class="sap__meta">
        <span>{{ advice.phases?.length || 0 }} 个阶段</span>
        <span>预计共 {{ totalDurationText }}</span>
        <span v-if="advice.scope?.nodeIds?.length">{{ advice.scope.nodeIds.length }} 个节点</span>
      </div>

      <section v-for="phase in advice.phases || []" :key="phase.id" class="sap__phase">
        <div class="sap__phase-head">
          <b>{{ phase.title }}</b>
          <span>约 {{ phase.estimatedMinutes || 0 }} 分钟</span>
        </div>
        <p class="sap__phase-goal">{{ phase.goal }}</p>
        <div class="sap__nodes">
          <span v-for="nodeId in phase.nodeIds || []" :key="nodeId" class="sap__node-chip">
            {{ nodeTitle(nodeId) }}
          </span>
        </div>
        <p v-if="phase.reason" class="sap__reason">{{ phase.reason }}</p>
      </section>

      <section v-if="advice.alternatives?.length" class="sap__block">
        <h4>另一种选择</h4>
        <div v-for="item in advice.alternatives" :key="item.title" class="sap__alt">
          <b>{{ item.title }}</b>
          <p>{{ item.summary }}</p>
          <span v-if="item.tradeoff">{{ item.tradeoff }}</span>
        </div>
      </section>

      <section v-if="advice.risks?.length" class="sap__block sap__risks">
        <h4>需要注意</h4>
        <p v-for="item in advice.risks" :key="item">{{ item }}</p>
      </section>

      <section class="sap__adjust">
        <h4>继续调整</h4>
        <div class="sap__chips">
          <button type="button" @click="emit('adjust', '更基础一点，先补前置概念')">更基础</button>
          <button type="button" @click="emit('adjust', '时间减半，只保留最关键的节点')">时间减半</button>
          <button type="button" @click="emit('adjust', '加入题库，用真实薄弱题验证')">加入题库</button>
        </div>
        <div class="sap__custom">
          <el-input v-model="custom" size="small" clearable placeholder="用一句话调整，例如：每天只能 20 分钟" @keyup.enter="submitCustom" />
          <el-button size="small" type="primary" plain :disabled="!custom.trim()" @click="submitCustom">调整</el-button>
        </div>
      </section>

      <p class="sap__foot">这是建议，不是任务；不勾选、不打卡，随时可以继续改。</p>
    </template>

    <div v-else class="sap__empty">
      <div class="sap__empty-mark">◇</div>
      <b>{{ selectedNode?.title ? `已选择「${selectedNode.title}」` : '还没有生成建议' }}</b>
      <p>{{ selectedNode?.title ? '点下方按钮，让系统沿着真实图谱关系读一遍。' : '点图谱节点，或直接点「生成建议」。' }}</p>
      <el-button size="small" type="primary" @click="emit('generate')">
        {{ selectedNode?.title ? '以此生成建议' : '生成建议' }}
      </el-button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import html2canvas from 'html2canvas'
import { saveAs } from 'file-saver'
import { exportStudyAdvice } from '@/api/ai/studyPlan'

const props = withDefaults(
  defineProps<{
    advice?: any
    loading?: boolean
    phase?: string
    selectedNode?: any
    nodeTitles?: Record<string, string>
  }>(),
  {
    advice: null,
    loading: false,
    phase: 'idle',
    selectedNode: null,
    nodeTitles: () => ({})
  }
)

const emit = defineEmits<{
  (e: 'adjust', instruction: string): void
  (e: 'save'): void
  (e: 'history'): void
  (e: 'generate'): void
}>()

const custom = ref('')
const exportRoot = ref<HTMLElement | null>(null)
const exporting = ref(false)

function fileStem() {
  const raw = String(props.advice?.title || '规划建议').replace(/[\\/:*?"<>|]+/g, '-').trim()
  return raw || '规划建议'
}

function buildText() {
  const advice = props.advice || {}
  const lines: string[] = [
    `# ${advice.title || '规划建议'}`,
    '',
    String(advice.summary || ''),
    '',
    '## 阶段建议'
  ]
  for (const phase of advice.phases || []) {
    lines.push(`### ${phase.title || '阶段'}（约 ${Number(phase.estimatedMinutes || 0)} 分钟）`)
    if (phase.goal) lines.push(`目标：${phase.goal}`)
    const nodes = (phase.nodeIds || []).map((id: string) => nodeTitle(id)).filter(Boolean)
    if (nodes.length) lines.push(`涉及节点：${nodes.join('、')}`)
    if (phase.reason) lines.push(`依据：${phase.reason}`)
    lines.push('')
  }
  if (advice.alternatives?.length) {
    lines.push('## 另一种选择')
    for (const item of advice.alternatives) {
      lines.push(`- ${item.title || '替代路径'}：${item.summary || ''}`)
      if (item.tradeoff) lines.push(`  取舍：${item.tradeoff}`)
    }
    lines.push('')
  }
  if (advice.risks?.length) {
    lines.push('## 需要注意')
    for (const item of advice.risks) lines.push(`- ${item}`)
    lines.push('')
  }
  lines.push('> 这是规划建议，不是任务清单；可以在 OpenStudy 中继续调整。')
  return lines.join('\n')
}

async function exportAdvice(command: string) {
  if (!props.advice) return
  if (command === 'text') {
    const blob = new Blob([buildText()], { type: 'text/plain;charset=utf-8' })
    saveAs(blob, `${fileStem()}.txt`)
    ElMessage.success('规划建议文本（TXT）已导出')
    return
  }
  if (command === 'pdf') {
    exporting.value = true
    try {
      const res: any = await exportStudyAdvice('pdf', props.advice)
      const blob = res instanceof Blob ? res : new Blob([res], { type: 'application/pdf' })
      if (!blob.size) throw new Error('导出文件为空')
      saveAs(blob, `${fileStem()}.pdf`)
      ElMessage.success('规划建议 PDF 已导出')
    } catch (error: any) {
      ElMessage.error(String(error?.message || '导出 PDF 失败'))
    } finally {
      exporting.value = false
    }
    return
  }
  if (command !== 'image') return
  if (!exportRoot.value) return
  exporting.value = true
  try {
    await nextTick()
    await new Promise((resolve) => setTimeout(resolve, 80))
    const canvas = await html2canvas(exportRoot.value, {
      backgroundColor: '#ffffff',
      scale: 2,
      useCORS: true,
      logging: false
    })
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('图片生成失败')
    saveAs(blob, `${fileStem()}.png`)
    ElMessage.success('规划建议图片已导出')
  } catch (error: any) {
    ElMessage.error(String(error?.message || '导出图片失败'))
  } finally {
    exporting.value = false
  }
}

const totalMinutes = computed(() =>
  (props.advice?.phases || []).reduce((sum: number, phase: any) => sum + Number(phase.estimatedMinutes || 0), 0)
)
const totalDurationText = computed(() => {
  const minutes = Number(totalMinutes.value || 0)
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`
})

function nodeTitle(id: string) {
  const raw = String(id || '')
  const pageId = raw.replace(/^topic:/, '')
  const fallback = raw.startsWith('bank:') ? '题库' : raw
  return props.nodeTitles?.[raw] || props.nodeTitles?.[pageId] || fallback
}

function submitCustom() {
  const text = custom.value.trim()
  if (!text) return
  emit('adjust', text)
  custom.value = ''
}
</script>

<style scoped>
.sap {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e8edf5;
  border-radius: 12px;
  background: #fff;
}
.sap__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.sap__eyebrow {
  color: #2f5fce;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.sap__head h3 {
  margin: 5px 0 0;
  color: #253247;
  font-size: 16px;
  line-height: 1.35;
}
.sap__head-actions { display: flex; flex: none; gap: 2px; }
.sap.is-exporting .sap__head-actions,
.sap.is-exporting .sap__adjust,
.sap.is-exporting .sap__foot { display: none; }
.sap__summary {
  margin: 0;
  color: #5f6b7d;
  font-size: 12px;
  line-height: 1.65;
}
.sap__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.sap__meta span {
  padding: 2px 7px;
  border: 1px solid #e4ebf6;
  border-radius: 99px;
  color: #697386;
  background: #f8faff;
  font-size: 10px;
}
.sap__phase {
  padding: 9px 10px;
  border: 1px solid #edf1f7;
  border-radius: 9px;
  background: #fbfcff;
}
.sap__phase-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.sap__phase-head b { color: #253247; font-size: 12px; }
.sap__phase-head span { color: #2f5fce; font-size: 10px; font-weight: 700; }
.sap__phase-goal { margin: 4px 0 6px; color: #7d8596; font-size: 11px; line-height: 1.5; }
.sap__nodes { display: flex; flex-wrap: wrap; gap: 4px; }
.sap__node-chip {
  padding: 2px 6px;
  border-radius: 5px;
  color: #4d5d78;
  background: #edf3ff;
  font-size: 10px;
}
.sap__reason { margin: 6px 0 0; color: #9aa3b2; font-size: 10px; line-height: 1.5; }
.sap__block h4 { margin: 0 0 5px; color: #253247; font-size: 11px; }
.sap__alt { padding: 7px 8px; border: 1px dashed #dce5f3; border-radius: 7px; background: #fff; }
.sap__alt + .sap__alt { margin-top: 5px; }
.sap__alt b { color: #4d5d78; font-size: 11px; }
.sap__alt p { margin: 3px 0; color: #7d8596; font-size: 10px; line-height: 1.45; }
.sap__alt span { color: #a0a8b6; font-size: 10px; }
.sap__risks p { margin: 3px 0; color: #9a6a20; font-size: 10px; line-height: 1.45; }
.sap__adjust {
  padding-top: 8px;
  border-top: 1px solid #f0f3f8;
}
.sap__adjust h4 { margin: 0 0 6px; color: #253247; font-size: 11px; }
.sap__chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.sap__chips button {
  padding: 3px 7px;
  border: 1px solid #dce5f3;
  border-radius: 6px;
  color: #5d6b82;
  background: #fff;
  cursor: pointer;
  font: inherit;
  font-size: 10px;
}
.sap__chips button:hover { color: #2f5fce; border-color: #b9cdf1; background: #f7faff; }
.sap__custom { display: flex; gap: 5px; }
.sap__foot { margin: 2px 0 0; color: #a0a8b6; font-size: 10px; line-height: 1.5; }
.sap__empty {
  display: flex;
  min-height: 260px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #9aa3b2;
  text-align: center;
}
.sap__empty-mark { color: #c4d3ed; font-size: 24px; }
.sap__empty b { color: #5f6b7d; font-size: 13px; }
.sap__empty p { max-width: 240px; margin: 0 0 6px; font-size: 11px; line-height: 1.55; }
.sap__skeleton {
  display: flex;
  min-height: 260px;
  flex-direction: column;
  gap: 9px;
  padding: 10px 0;
}
.sap__skeleton i {
  display: block;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, #f0f4fb 25%, #f8faff 50%, #f0f4fb 75%);
  background-size: 200% 100%;
  animation: sap-shimmer 1.2s infinite;
}
.sap__skeleton i:nth-child(2) { width: 82%; }
.sap__skeleton i:nth-child(3) { width: 64%; }
.sap__skeleton i:nth-child(4) { width: 90%; }
.sap__skeleton span { margin-top: 8px; color: #8a91a0; font-size: 11px; text-align: center; }
@keyframes sap-shimmer { to { background-position: -200% 0; } }
</style>
