<template>
  <div v-if="hasDiff" class="agent-doc-diff">
    <div class="agent-doc-diff__head">
      <div class="agent-doc-diff__title">
        <OsIcon name="file-text" :size="14" />
        <span class="agent-doc-diff__path" :title="diff.path">{{ diff.path || '文档正文' }}</span>
      </div>
      <div class="agent-doc-diff__actions">
        <div class="agent-doc-diff__stats">
          <span class="is-add">+{{ diff.added || 0 }}</span>
          <span class="is-del">-{{ diff.removed || 0 }}</span>
        </div>
        <button type="button" class="agent-doc-diff__copy" @click="copyDiff">
          {{ copied ? '已复制' : '复制' }}
        </button>
      </div>
    </div>

    <div class="agent-doc-diff__body">
      <div v-if="diff.truncated" class="agent-doc-diff__note">内容较长，仅展示部分修改</div>
      <div
        v-for="(line, index) in visibleHead"
        :key="'head-' + index"
        class="agent-doc-diff__line"
        :class="'is-' + line.kind"
      >
        <span class="agent-doc-diff__no">{{ line.oldLine ?? '' }}</span>
        <span class="agent-doc-diff__no">{{ line.newLine ?? '' }}</span>
        <span class="agent-doc-diff__mark">{{ marker(line.kind) }}</span>
        <span class="agent-doc-diff__text">{{ line.text || ' ' }}</span>
      </div>

      <button v-if="canToggle" type="button" class="agent-doc-diff__toggle" @click="expanded = !expanded">
        {{ expanded ? '收起修改内容' : `展开全部（还有 ${hiddenCount} 行）` }}
      </button>

      <div
        v-for="(line, index) in visibleTail"
        :key="'tail-' + index"
        class="agent-doc-diff__line"
        :class="'is-' + line.kind"
      >
        <span class="agent-doc-diff__no">{{ line.oldLine ?? '' }}</span>
        <span class="agent-doc-diff__no">{{ line.newLine ?? '' }}</span>
        <span class="agent-doc-diff__mark">{{ marker(line.kind) }}</span>
        <span class="agent-doc-diff__text">{{ line.text || ' ' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import OsIcon from '@/components/OsIcon/index.vue'

const MAX_COLLAPSED_LINES = 16
const HEAD_LINES = 8
const TAIL_LINES = 8

const props = defineProps<{
  diff: Record<string, any> | null
}>()

const expanded = ref(false)
const copied = ref(false)

const lines = computed<any[]>(() => (Array.isArray(props.diff?.lines) ? props.diff.lines : []))
const hasDiff = computed(() => lines.value.length > 0)
const canToggle = computed(() => lines.value.length > MAX_COLLAPSED_LINES)

const visibleHead = computed(() => {
  if (expanded.value || lines.value.length <= MAX_COLLAPSED_LINES) return lines.value
  return lines.value.slice(0, HEAD_LINES)
})

const visibleTail = computed(() => {
  if (expanded.value || lines.value.length <= MAX_COLLAPSED_LINES) return []
  return lines.value.slice(-TAIL_LINES)
})

const hiddenCount = computed(() =>
  Math.max(0, lines.value.length - visibleHead.value.length - visibleTail.value.length)
)

async function copyDiff() {
  const text = lines.value
    .map((line) => {
      const prefix = line.kind === 'del' ? '- ' : line.kind === 'add' ? '+ ' : line.kind === 'gap' ? '' : '  '
      return prefix + String(line.text ?? '')
    })
    .join('\n')
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1200)
  } catch {
    // 剪贴板不可用时保持静默，不影响确认操作。
  }
}

function marker(kind: string): string {
  if (kind === 'del') return '-'
  if (kind === 'add') return '+'
  if (kind === 'gap') return '⋯'
  return ' '
}
</script>

<style scoped>
.agent-doc-diff {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}

.agent-doc-diff__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  padding: 0 12px;
  border-bottom: 1px solid #ebeef5;
  background: #f5f7fa;
}

.agent-doc-diff__title {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  color: #303133;
}

.agent-doc-diff__path {
  overflow: hidden;
  color: #606266;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-doc-diff__actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}

.agent-doc-diff__stats {
  display: flex;
  flex: none;
  gap: 8px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
}

.agent-doc-diff__copy {
  padding: 0;
  border: 0;
  background: transparent;
  color: #909399;
  cursor: pointer;
  font-size: 12px;
}

.agent-doc-diff__copy:hover {
  color: #409eff;
}

.agent-doc-diff__stats .is-add {
  color: #237804;
}

.agent-doc-diff__stats .is-del {
  color: #a8071a;
}

.agent-doc-diff__body {
  max-height: 320px;
  padding: 6px 0;
  overflow: auto;
  background: #fafafa;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 12px;
  line-height: 20px;
}

.agent-doc-diff__note {
  padding: 2px 12px 6px;
  color: #909399;
  font-size: 11px;
}

.agent-doc-diff__line {
  display: flex;
  align-items: flex-start;
  min-height: 20px;
  padding-right: 12px;
  white-space: pre;
}

.agent-doc-diff__no {
  flex: none;
  width: 34px;
  padding-right: 8px;
  color: #a8abb2;
  text-align: right;
  user-select: none;
}

.agent-doc-diff__mark {
  flex: none;
  width: 16px;
  color: #909399;
  text-align: center;
  user-select: none;
}

.agent-doc-diff__text {
  min-width: 0;
  color: #303133;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.agent-doc-diff__line.is-del {
  background: #fff1f0;
  box-shadow: inset 3px 0 0 #ff4d4f;
}

.agent-doc-diff__line.is-del .agent-doc-diff__text,
.agent-doc-diff__line.is-del .agent-doc-diff__mark {
  color: #a8071a;
}

.agent-doc-diff__line.is-add {
  background: #f6ffed;
  box-shadow: inset 3px 0 0 #52c41a;
}

.agent-doc-diff__line.is-add .agent-doc-diff__text,
.agent-doc-diff__line.is-add .agent-doc-diff__mark {
  color: #237804;
}

.agent-doc-diff__line.is-gap {
  justify-content: center;
  color: #a8abb2;
  background: #fff;
}

.agent-doc-diff__toggle {
  display: block;
  width: 100%;
  padding: 4px 12px;
  border: 0;
  background: transparent;
  color: #409eff;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.agent-doc-diff__toggle:hover {
  background: #ecf5ff;
}
</style>
