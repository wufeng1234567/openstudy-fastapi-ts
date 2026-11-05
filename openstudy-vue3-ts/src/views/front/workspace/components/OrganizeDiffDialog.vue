<template>
  <el-dialog
    v-model="dialogVisible"
    :title="`${recordView ? '整理记录' : '整理手术台'} · ${mode === 'deep' ? '智能整理' : '旧版整理'}`"
    width="1120px"
    top="6vh"
    append-to-body
    destroy-on-close
    class="od-dialog"
  >
    <div class="od-head">
      <div class="od-summary">
        <span class="od-summary__item od-summary__item--change">{{ changedCount }} 处变更</span>
        <span v-if="suggestions.length" class="od-summary__item od-summary__item--suggest">
          {{ suggestions.length }} 条剔除建议
        </span>
        <span v-if="mode === 'deep'" class="od-summary__mode">结构分析</span>
      </div>
      <div v-if="status === 'running' || status === 'starting'" class="od-progress">
        <span class="od-progress__stage">{{ stageLabel }}</span>
        <span class="od-progress__time">已用时 {{ elapsedText }}</span>
        <el-progress :percentage="Math.max(0, Math.min(100, progress))" :show-text="false" />
      </div>
    </div>

    <div v-if="status === 'running' || status === 'starting'" class="od-thinking">
      <div class="od-thinking__dot" />
      <span>{{ mode === 'deep' ? '正在分析文档结构、图片和可整理项…' : '正在生成整理预览…' }}</span>
      <span class="od-thinking__hint">结果会逐步出现在下方</span>
    </div>

    <div v-else-if="status === 'failed'" class="od-empty od-empty--error">
      <p>整理失败</p>
      <span>{{ error || '请稍后重试' }}</span>
    </div>

    <div v-else-if="!visibleChanges.length && !contentStatsChange && !suggestions.length" class="od-empty">
      没有需要整理的内容，当前文档已经是最新状态。
    </div>

    <div v-else class="od-body">
      <div v-if="status === 'ready' && !readonlyRecord" class="od-plan">
        <div class="od-plan__stats">
          <div v-for="stat in planStats" :key="stat.key" class="od-plan__stat">
            <b>{{ stat.count }}</b>
            <span>{{ stat.label }}</span>
          </div>
        </div>
        <div class="od-plan__actions">
          <span class="od-plan__hint">这是一份「手术方案」：先看变更理由，再决定接受哪些。</span>
          <el-button link size="small" @click="selectAllChanges">全选变更</el-button>
          <el-button link size="small" @click="clearAllChanges">全部忽略</el-button>
        </div>
      </div>

      <div v-if="status === 'ready'" class="od-guide">
        <div class="od-guide__title">先看这里：这次整理只生成预览，不会自动改资料</div>
        <div class="od-guide__row">
          <span class="od-guide__badge od-guide__badge--change">变更</span>
          <span>智能整理生成的变更（结构顺序、文档信息、图片关联）。默认不勾选，只有勾选后才会应用。</span>
        </div>
        <div class="od-guide__row">
          <span class="od-guide__badge od-guide__badge--suggest">建议剔除</span>
          <span>需要你确认的项目。默认不勾选：不勾选就保持原样；勾选后点击右下角「应用选中整理」才会剔除。原文仍保留，可回退。</span>
        </div>
      </div>

      <div v-if="visibleChanges.length" class="od-section">
        <div class="od-section__head">
          <span>变更对比 <span class="od-ai-tag">整理建议，需确认</span></span>
          <span class="od-section__hint">默认不勾选；只有勾选的变更才会被应用。红色为删除，绿色为新增。</span>
        </div>

        <div v-for="change in visibleChanges" :key="change.id" class="od-change">
          <div class="od-change__head">
            <el-checkbox
              v-if="!readonlyRecord && change.selectable !== false"
              v-model="selectedChangeMap[change.id]"
              class="od-change__check"
            >
              <span class="od-change__label">{{ change.label }}</span>
            </el-checkbox>
            <span v-else class="od-change__label">{{ change.label }}</span>
            <span v-if="readonlyRecord" class="od-applied-tag">已应用</span>
            <span class="od-change__group">{{ groupLabel(change.group) }}</span>
            <span class="od-ai-tag">AI 生成</span>
            <span v-if="change.confidence != null && change.confidence < 1" class="od-confidence">
              置信度 {{ Math.round(Number(change.confidence) * 100) }}%
            </span>
            <span class="od-change__reason">{{ change.reason }}</span>
          </div>
          <div v-if="isImageChange(change)" class="od-image-diff">
            <div class="od-image-diff__side od-image-diff__side--before">
              <div class="od-diff__side-title">− 整理前</div>
              <el-image
                v-if="change.before?.url"
                class="od-image-diff__thumb"
                :src="assetUrl(change.before.url)"
                :preview-src-list="[assetUrl(change.before.url)]"
                fit="contain"
                preview-teleported
              />
              <div v-else class="od-image-diff__empty">无图片</div>
              <div class="od-image-diff__caption">{{ change.before?.position || change.before?.value }}</div>
            </div>
            <div class="od-image-diff__side od-image-diff__side--after">
              <div class="od-diff__side-title">+ 整理后</div>
              <el-image
                v-if="change.after?.url"
                class="od-image-diff__thumb"
                :src="assetUrl(change.after.url)"
                :preview-src-list="[assetUrl(change.after.url)]"
                fit="contain"
                preview-teleported
              />
              <div v-else class="od-image-diff__empty">无图片</div>
              <div class="od-image-diff__caption">{{ change.after?.position || change.after?.value }}</div>
            </div>
          </div>
          <div v-else class="od-diff">
            <div class="od-diff__side od-diff__side--before">
              <div class="od-diff__side-title">− 整理前</div>
              <div
                v-for="(line, index) in diffFor(change).before"
                :key="`b-${index}`"
                class="od-diff__line"
                :class="lineClass(line)"
              >
                <span class="od-diff__mark">{{ line.type === 'remove' ? '−' : ' ' }}</span>
                <span class="od-diff__text">{{ line.text || ' ' }}</span>
              </div>
              <div v-if="change.field === 'imageLinks'" class="od-diff__side-note">旧版本没有图片关联记录，右侧是新增关联。</div>
            </div>
            <div class="od-diff__side od-diff__side--after">
              <div class="od-diff__side-title">+ 整理后</div>
              <div
                v-for="(line, index) in diffFor(change).after"
                :key="`a-${index}`"
                class="od-diff__line"
                :class="lineClass(line)"
              >
                <span class="od-diff__mark">{{ line.type === 'add' ? '+' : ' ' }}</span>
                <span class="od-diff__text">{{ line.text || ' ' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="suggestions.length" class="od-section od-section--suggest">
        <div class="od-section__head">
          <span>建议剔除</span>
          <span class="od-section__hint">默认不勾选：不勾选 = 保持原样；勾选后 = 剔除这条。原文保留，可回退。</span>
        </div>
        <div
          v-for="suggestion in suggestions"
          :key="suggestion.id"
          class="od-suggest-row"
          :class="{ 'is-selected': selectedSuggestionMap[suggestion.id], 'is-readonly': readonlyRecord }"
        >
          <el-checkbox v-if="!readonlyRecord" v-model="selectedSuggestionMap[suggestion.id]" />
          <span v-else class="od-removed-tag">已剔除</span>
          <el-image
            v-if="suggestionImageUrl(suggestion)"
            class="od-suggest-row__thumb"
            :src="assetUrl(suggestionImageUrl(suggestion))"
            :preview-src-list="[assetUrl(suggestionImageUrl(suggestion))]"
            fit="cover"
            preview-teleported
          >
            <template #error>
              <span class="od-suggest-row__thumb-error">图片未上传</span>
            </template>
          </el-image>
          <span v-else class="od-suggest-row__thumb-spacer"></span>
          <div class="od-suggest-row__body">
            <div class="od-suggest-row__title">
              {{ suggestion.label }}
              <span v-if="suggestionImageUrl(suggestion)" class="od-kind">图片</span>
              <span class="od-risk">{{ suggestion.risk === 'high' ? '高风险，请谨慎' : '待你选择' }}</span>
              <span class="od-select-state" :class="{ 'is-on': selectedSuggestionMap[suggestion.id] }">
                {{ selectedSuggestionMap[suggestion.id] ? '勾选后：应用时会剔除' : '未勾选：保持原样' }}
              </span>
            </div>
            <div class="od-suggest-row__reason">{{ suggestion.reason }}</div>
            <div v-if="readonlyRecord" class="od-removed-note">
              {{ suggestionImageUrl(suggestion) ? '这张图片已从资料展示和检索中剔除。' : '这段文字已从资料展示和检索中剔除。' }}
            </div>
          </div>
          <div class="od-suggest-row__diff">
            <span class="od-suggest-row__removed">− {{ suggestion.before?.value || '保留原文' }}</span>
            <span class="od-suggest-row__added">+ {{ suggestion.after?.value || '建议剔除' }}</span>
          </div>
        </div>
      </div>

      <div v-if="contentStatsChange" class="od-stats-panel">
        <div class="od-stats-panel__head">
          <span>内容统计</span>
          <span>自动统计，不需要确认</span>
        </div>
        <div class="od-stats-panel__rows">
          <div v-for="row in contentStatsRows" :key="row.label" class="od-stats-panel__row">
            <span class="od-stats-panel__label">{{ row.label }}</span>
            <span class="od-stats-panel__before">− {{ row.before }}</span>
            <span class="od-stats-panel__arrow">→</span>
            <span class="od-stats-panel__after">+ {{ row.after }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="od-footer">
        <span v-if="status === 'ready'" class="od-footer__hint">
          变更：已选 {{ selectedVisibleChangeIds.length }} / {{ visibleChanges.length }} 项
          ·
          <template v-if="selectedSuggestionIds.length">
            剔除建议：已选 {{ selectedSuggestionIds.length }} / {{ suggestions.length }} 项
          </template>
          <template v-else>
            剔除建议：未选择，保持原样
          </template>
        </span>
        <span v-if="applied" class="od-footer__applied">已应用</span>
        <div class="od-footer__actions">
          <el-button @click="dialogVisible = false">关闭</el-button>
          <el-button v-if="status !== 'running' && status !== 'starting'" @click="$emit('rerun')">
            再次整理
          </el-button>
          <el-button
            v-if="status === 'ready' && !applied"
            type="primary"
            :disabled="!selectedChangeIds.length && !selectedSuggestionIds.length"
            @click="apply"
          >
            应用选中整理
          </el-button>
          <el-button v-if="applied" @click="$emit('recheck')">
            复检
          </el-button>
          <el-button v-if="applied" type="danger" plain @click="$emit('rollback')">
            回退本次整理
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  mode: 'quick' | 'deep'
  status: string
  stage: string
  progress: number
  elapsed: number
  error?: string
  changes: any[]
  suggestions: any[]
  applied?: boolean
  recordView?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
  (e: 'apply', changeIds: string[], exclusionIds: string[]): void
  (e: 'rollback'): void
  (e: 'rerun'): void
  (e: 'recheck'): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})
const readonlyRecord = computed(() =>
  Boolean(props.recordView && ['applied', 'rolled_back'].includes(props.status))
)

const selectedChangeMap = ref<Record<string, boolean>>({})
const selectedSuggestionMap = ref<Record<string, boolean>>({})

watch(
  () => props.changes,
  (list) => {
    const next: Record<string, boolean> = {}
    // AI 生成的变更默认不勾选；用户只想要剔除垃圾时，不会被图片关联等变更强行影响。
    for (const change of list || []) next[change.id] = false
    selectedChangeMap.value = next
  },
  { immediate: true, deep: true }
)

watch(
  () => props.suggestions,
  (list) => {
    const next: Record<string, boolean> = {}
    for (const suggestion of list || []) next[suggestion.id] = false
    selectedSuggestionMap.value = next
  },
  { immediate: true, deep: true }
)

const visibleChanges = computed(() =>
  (props.changes || []).filter((change: any) => change.field !== 'facets')
)
const contentStatsChange = computed(() =>
  (props.changes || []).find((change: any) => change.field === 'facets')
)
const contentStatsRows = computed(() => {
  const before = new Map<string, string>()
  const after = new Map<string, string>()
  for (const row of contentStatsChange.value?.before?.rows || []) before.set(String(row[0]), String(row[1] ?? ''))
  for (const row of contentStatsChange.value?.after?.rows || []) after.set(String(row[0]), String(row[1] ?? ''))
  return [...new Set([...before.keys(), ...after.keys()])]
    .filter((label) => before.get(label) !== after.get(label))
    .map((label) => ({ label, before: before.get(label) ?? '—', after: after.get(label) ?? '—' }))
})
const changedCount = computed(() => visibleChanges.value.length)

const planStats = computed(() => {
  const groupCount = (group: string) =>
    visibleChanges.value.filter((change: any) => change.group === group).length
  // 内容统计（facets）在 visibleChanges 里被过滤掉，单独按原始 changes 计数。
  const facetsCount = (props.changes || []).filter((change: any) => change.field === 'facets').length
  return [
    { key: 'structure', label: '结构/顺序', count: groupCount('structure') },
    { key: 'image', label: '图片', count: groupCount('image') },
    { key: 'meta', label: '元信息/统计', count: groupCount('meta') + facetsCount },
    { key: 'suggest', label: '建议剔除', count: props.suggestions.length }
  ].filter((item) => item.count > 0)
})

function selectAllChanges() {
  const next: Record<string, boolean> = { ...selectedChangeMap.value }
  for (const change of visibleChanges.value) {
    if (change.selectable !== false) next[change.id] = true
  }
  selectedChangeMap.value = next
}

function clearAllChanges() {
  const next: Record<string, boolean> = { ...selectedChangeMap.value }
  for (const change of visibleChanges.value) next[change.id] = false
  selectedChangeMap.value = next
}
const selectedVisibleChangeIds = computed(() =>
  Object.entries(selectedChangeMap.value)
    .filter(([, selected]) => selected)
    .map(([id]) => id)
    .filter((id) => visibleChanges.value.some((change: any) => change.id === id))
)
// 内容统计是派生数据，自动应用，不进入用户确认区。
const selectedChangeIds = computed(() => {
  const ids = [...selectedVisibleChangeIds.value]
  if (contentStatsChange.value) ids.push(contentStatsChange.value.id)
  return ids
})
const selectedSuggestionIds = computed(() =>
  Object.entries(selectedSuggestionMap.value).filter(([, selected]) => selected).map(([id]) => id)
)

const stageLabel = computed(() => {
  const labels: Record<string, string> = {
    starting: '准备整理',
    blocks: '解析文档块',
    structure: '识别题目与章节结构',
    images: '整理图片关联',
    preview: '生成 Diff',
    done: '整理完成',
    failed: '整理失败',
  }
  return labels[props.stage] || props.stage || '准备整理'
})

const elapsedText = computed(() => `${Math.max(0, Math.round(props.elapsed || 0))}s`)

function groupLabel(group: string): string {
  return ({ meta: '元信息', facets: '内容统计', structure: '结构', image: '图片' } as Record<string, string>)[group] || group
}

function isImageChange(change: any): boolean {
  return change?.kind === 'image' || change?.before?.type === 'image' || change?.after?.type === 'image'
}

function assetUrl(url: string): string {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = String(import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : `/${value}`)
}

/** 兼容建议里的 Markdown 图片引用：能预览时显示缩略图，而不是把 ![](...) 当普通文字。 */
function suggestionImageUrl(suggestion: any): string {
  if (suggestion?.imageUrl) return String(suggestion.imageUrl)
  const value = String(suggestion?.before?.value || suggestion?.after?.value || '')
  const match = /!\[[^\]]*\]\(([^)\s]+)\)/.exec(value)
  return match ? match[1] : ''
}

type DiffLine = { text: string; type: 'remove' | 'add' | 'context' }

function textLines(value: any, side: 'before' | 'after'): DiffLine[] {
  const text = String(value?.value ?? '')
  if (!text) return [{ text: '—', type: side === 'before' ? 'remove' : 'add' }]
  return text.split('\n').map((line) => ({
    text: line,
    type: side === 'before' ? 'remove' : 'add'
  }))
}

function listLines(before: string[], after: string[]): { before: DiffLine[]; after: DiffLine[] } {
  const beforeSet = new Set(before)
  const afterSet = new Set(after)
  return {
    before: before.length
      ? before.map((text) => ({ text, type: (afterSet.has(text) ? 'context' : 'remove') as DiffLine['type'] }))
      : [{ text: '—', type: 'remove' }],
    after: after.length
      ? after.map((text) => ({ text, type: (beforeSet.has(text) ? 'context' : 'add') as DiffLine['type'] }))
      : [{ text: '—', type: 'add' }]
  }
}

function tableLines(before: any, after: any): { before: DiffLine[]; after: DiffLine[] } {
  const beforeRows = new Map<string, string>()
  const afterRows = new Map<string, string>()
  for (const row of before?.rows || []) beforeRows.set(String(row[0]), String(row[1] ?? ''))
  for (const row of after?.rows || []) afterRows.set(String(row[0]), String(row[1] ?? ''))
  const keys = [...new Set([...beforeRows.keys(), ...afterRows.keys()])]
  const beforeLines: DiffLine[] = []
  const afterLines: DiffLine[] = []
  for (const key of keys) {
    const a = beforeRows.get(key)
    const b = afterRows.get(key)
    if (a === b) continue
    beforeLines.push({ text: `${key}: ${a ?? '—'}`, type: 'remove' })
    afterLines.push({ text: `${key}: ${b ?? '—'}`, type: 'add' })
  }
  if (!beforeLines.length) {
    beforeLines.push({ text: '无变化', type: 'context' })
    afterLines.push({ text: '无变化', type: 'context' })
  }
  return { before: beforeLines, after: afterLines }
}

function diffFor(change: any): { before: DiffLine[]; after: DiffLine[] } {
  const before = change.before || {}
  const after = change.after || {}
  if (before.type === 'table' && after.type === 'table') {
    return tableLines(before, after)
  }
  if (before.type === 'list' || after.type === 'list') {
    return listLines(
      Array.isArray(before.value) ? before.value.map(String) : [],
      Array.isArray(after.value) ? after.value.map(String) : []
    )
  }
  return { before: textLines(before, 'before'), after: textLines(after, 'after') }
}

function lineClass(line: DiffLine) {
  return {
    'is-removed': line.type === 'remove',
    'is-added': line.type === 'add',
    'is-context': line.type === 'context'
  }
}

function apply() {
  emit('apply', selectedChangeIds.value, selectedSuggestionIds.value)
}
</script>

<style scoped>
.od-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}

.od-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 12px;
}

.od-plan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 13px;
  margin-bottom: 12px;
  border: 1px solid #dbeafe;
  border-radius: 9px;
  background: linear-gradient(90deg, #f8fbff, #ffffff);
}

.od-plan__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}

.od-plan__stat {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.od-plan__stat b {
  color: #1e3a5f;
  font-size: 19px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.od-plan__stat span {
  color: #6b7280;
  font-size: 10.5px;
}

.od-plan__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.od-plan__hint {
  color: #6b7280;
  font-size: 11.5px;
}

.od-confidence {
  flex: none;
  padding: 1px 5px;
  color: #6b7280;
  background: #f3f4f6;
  border-radius: 3px;
  font-size: 10.5px;
}

.od-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.od-summary__item {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.od-summary__item--change {
  color: #166534;
  background: #dcfce7;
}

.od-summary__item--suggest {
  color: #92400e;
  background: #fef3c7;
}

.od-summary__mode {
  padding: 3px 8px;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 999px;
  font-size: 12px;
}

.od-progress {
  min-width: 230px;
  color: #6b7280;
  font-size: 12px;
}

.od-progress__stage {
  display: block;
  margin-bottom: 4px;
  color: #374151;
  font-weight: 600;
}

.od-progress__time {
  float: right;
  margin-top: -19px;
}

.od-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  color: #2563eb;
  background: #eff6ff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  font-size: 13px;
}

.od-thinking__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #2563eb;
  animation: od-pulse 1s ease-in-out infinite;
}

.od-thinking__hint {
  margin-left: auto;
  color: #6b7280;
  font-size: 12px;
}

@keyframes od-pulse {
  50% { opacity: 0.3; }
}

.od-body {
  max-height: 64vh;
  overflow: auto;
}

.od-guide {
  margin-bottom: 16px;
  padding: 11px 14px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
  color: #4b5563;
  font-size: 12.5px;
  line-height: 1.75;
}

.od-guide__title {
  margin-bottom: 4px;
  color: #1e3a5f;
  font-weight: 700;
}

.od-guide__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.od-guide__badge {
  flex: none;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10.5px;
  font-weight: 600;
}

.od-guide__badge--change {
  color: #166534;
  background: #dcfce7;
}

.od-guide__badge--suggest {
  color: #92400e;
  background: #fef3c7;
}

.od-section + .od-section {
  margin-top: 18px;
}

.od-stats-panel {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
}

.od-stats-panel__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: #374151;
  font-size: 12.5px;
  font-weight: 700;
}

.od-stats-panel__head span + span {
  color: #9ca3af;
  font-size: 11px;
  font-weight: 400;
}

.od-stats-panel__rows {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  margin-top: 8px;
  font-family: "Cascadia Code", "Consolas", "Microsoft YaHei", monospace;
  font-size: 12px;
}

.od-stats-panel__row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.od-stats-panel__label {
  color: #6b7280;
}

.od-stats-panel__before {
  color: #991b1b;
  text-decoration: line-through;
}

.od-stats-panel__arrow {
  color: #d1d5db;
}

.od-stats-panel__after {
  color: #166534;
}

.od-section__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #111827;
  font-size: 13px;
  font-weight: 700;
}

.od-section__hint {
  color: #9ca3af;
  font-size: 11.5px;
  font-weight: 400;
}

.od-change {
  margin-top: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.od-change__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
}

.od-change__check {
  flex: none;
  height: auto;
}

.od-change__check :deep(.el-checkbox__label) {
  padding-left: 7px;
}

.od-change__label {
  color: #111827;
  font-size: 13px;
  font-weight: 700;
}

.od-change__group {
  padding: 1px 5px;
  color: #6b7280;
  background: #eef2f7;
  border-radius: 3px;
  font-size: 10.5px;
}

.od-ai-tag {
  flex: none;
  padding: 1px 5px;
  color: #7c3aed;
  background: #f3e8ff;
  border-radius: 3px;
  font-size: 10.5px;
}

.od-applied-tag,
.od-removed-tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10.5px;
  font-weight: 600;
}

.od-applied-tag {
  color: #166534;
  background: #dcfce7;
}

.od-removed-tag {
  color: #991b1b;
  background: #fee2e2;
}

.od-removed-note {
  margin-top: 3px;
  color: #b91c1c;
  font-size: 11.5px;
}

.od-change__reason {
  margin-left: auto;
  color: #9ca3af;
  font-size: 11.5px;
}

.od-diff {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.od-image-diff {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.od-image-diff__side {
  min-width: 0;
  padding: 9px 12px 12px;
}

.od-image-diff__side--before {
  border-right: 1px solid #e5e7eb;
  background: #fffafa;
}

.od-image-diff__side--after {
  background: #f8fffa;
}

.od-image-diff__thumb,
.od-image-diff__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  max-width: 320px;
  height: 180px;
  margin: 5px 0 7px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
}

.od-image-diff__thumb {
  cursor: zoom-in;
}

.od-image-diff__empty {
  color: #9ca3af;
  font-size: 12px;
}

.od-image-diff__caption {
  color: #6b7280;
  font-size: 12px;
  line-height: 1.6;
}

.od-diff__side {
  min-width: 0;
  padding: 8px 0;
  font-family: "Cascadia Code", "Consolas", "Microsoft YaHei", monospace;
  font-size: 12px;
  line-height: 1.7;
}

.od-diff__side--before {
  border-right: 1px solid #e5e7eb;
  background: #fffafa;
}

.od-diff__side--after {
  background: #f8fffa;
}

.od-diff__side-title {
  padding: 0 10px 5px;
  color: #9ca3af;
  font-family: inherit;
  font-size: 11px;
}

.od-diff__line {
  display: flex;
  gap: 7px;
  min-height: 21px;
  padding: 1px 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

.od-diff__mark {
  flex: none;
  width: 12px;
  color: #9ca3af;
  user-select: none;
}

.od-diff__text {
  min-width: 0;
}

.od-diff__line.is-removed {
  background: #fee2e2;
  color: #991b1b;
}

.od-diff__line.is-added {
  background: #dcfce7;
  color: #166534;
}

.od-diff__line.is-context {
  color: #6b7280;
}

.od-diff__side-note {
  margin: 8px 10px 2px;
  padding-top: 8px;
  border-top: 1px dashed #f3d6d6;
  color: #b0a0a0;
  font-family: "Microsoft YaHei", sans-serif;
  font-size: 11px;
  line-height: 1.5;
}

.od-empty {
  padding: 50px 20px;
  color: #9ca3af;
  text-align: center;
}

.od-empty--error {
  color: #ef4444;
}

.od-empty--error p {
  margin: 0 0 5px;
  font-weight: 600;
}

.od-empty--error span {
  color: #6b7280;
  font-size: 12px;
}

.od-section--suggest {
  padding: 12px;
  border: 1px solid #fde68a;
  border-radius: 9px;
  background: #fffbeb;
}

.od-suggest-row {
  display: grid;
  grid-template-columns: 22px 68px minmax(0, 1fr) minmax(260px, 0.9fr);
  align-items: center;
  gap: 10px;
  padding: 10px 6px;
  border-top: 1px solid #fef3c7;
  font-size: 12.5px;
}

.od-suggest-row__thumb,
.od-suggest-row__thumb-spacer {
  width: 68px;
  height: 54px;
  border-radius: 5px;
}

.od-suggest-row__thumb {
  border: 1px solid #fde68a;
  background: #fff;
  cursor: zoom-in;
}

.od-suggest-row__thumb-error {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 4px;
  color: #9ca3af;
  font-size: 10px;
  line-height: 1.35;
  text-align: center;
  background: #f8fafc;
}

.od-suggest-row__thumb-spacer {
  display: block;
}

.od-suggest-row:first-of-type {
  border-top: 0;
}

.od-suggest-row.is-selected {
  background: #fff7d6;
}

.od-suggest-row.is-readonly {
  grid-template-columns: 58px 68px minmax(0, 1fr) minmax(260px, 0.9fr);
}

.od-suggest-row__title {
  color: #374151;
  font-weight: 600;
}

.od-kind {
  margin-left: 6px;
  padding: 1px 5px;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 3px;
  font-size: 10.5px;
  font-weight: 400;
}

.od-risk {
  margin-left: 6px;
  color: #b45309;
  font-size: 10.5px;
  font-weight: 400;
}

.od-select-state {
  margin-left: 8px;
  color: #9ca3af;
  font-size: 10.5px;
  font-weight: 400;
}

.od-select-state.is-on {
  color: #b45309;
}

.od-suggest-row__reason {
  margin-top: 2px;
  color: #6b7280;
  font-size: 11.5px;
}

.od-suggest-row__diff {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-family: "Cascadia Code", "Consolas", "Microsoft YaHei", monospace;
  font-size: 11.5px;
}

.od-suggest-row__removed {
  padding: 2px 5px;
  color: #991b1b;
  background: #fee2e2;
  border-radius: 2px;
  white-space: pre-wrap;
  word-break: break-word;
}

.od-suggest-row__added {
  padding: 2px 5px;
  color: #166534;
  background: #dcfce7;
  border-radius: 2px;
}

.od-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.od-footer__hint {
  color: #6b7280;
  font-size: 12px;
}

.od-footer__applied {
  color: #16a34a;
  font-size: 12px;
  font-weight: 600;
}

.od-footer__actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 900px) {
  .od-diff {
    grid-template-columns: 1fr;
  }

  .od-diff__side--before {
    border-right: 0;
    border-bottom: 1px solid #e5e7eb;
  }

  .od-suggest-row {
    grid-template-columns: 22px 68px minmax(0, 1fr);
  }

  .od-suggest-row__diff {
    grid-column: 3;
  }
}
</style>
