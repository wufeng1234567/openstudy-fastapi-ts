<template>
  <el-dialog v-model="visible" title="编辑知识主题页" width="820px" top="5vh" append-to-body
    destroy-on-close class="kw-editor-dialog" @closed="emit('update:modelValue', false)">
    <div v-if="draft" class="kw-editor">
      <div class="kw-editor__hint">
        保存后生成新版本；AI 后续更新会保留历史版本，可在主题页里恢复。
        正文里的 [[主题页标题|原词]] 会显示为可跳转的绿色链接；也可以在主题页详情的「页面链接」里手动添加或移除。
      </div>
      <label class="kw-editor__label">标题</label>
      <el-input v-model="draft.title" maxlength="255" show-word-limit />

      <label class="kw-editor__label">摘要</label>
      <el-input v-model="draft.summary" type="textarea" :rows="3" maxlength="500" show-word-limit
        placeholder="一句话说明这个主题" />

      <div class="kw-editor__section-head">
        <span>正文小节</span>
        <el-button size="small" plain @click="addSection">添加小节</el-button>
      </div>
      <div v-for="(section, index) in draft.sections" :key="index" class="kw-editor__section"
        @keyup.capture="onSectionKeyup(index, $event)" @input.capture="onSectionInput(index, $event)"
        @click.capture="onSectionClick(index, $event)">
        <div class="kw-editor__section-top">
          <el-input v-model="section.heading" maxlength="60" placeholder="小节标题" />
          <el-button size="small" text type="danger" :disabled="draft.sections.length <= 1"
            @click="removeSection(index)">删除</el-button>
        </div>
        <el-input v-model="section.body" type="textarea" :rows="4" maxlength="1600" show-word-limit
          placeholder="只写主题页内容；输入 @ 引用其他知识百科"
          @input="onSectionInput(index, $event)" @keyup="onSectionKeyup(index, $event)" @click="onSectionClick(index, $event)" />
        <div class="kw-editor__mention-hint">输入 <b>@</b> 搜索并引用其他知识实体</div>
        <div v-if="section.sourceChunkIds?.length" class="kw-editor__source">
          本节引用 {{ section.sourceChunkIds.length }} 个资料片段
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存并生成新版本</el-button>
    </template>
  </el-dialog>

  <Teleport to="body">
    <div v-if="mentionVisible" ref="mentionPopoverRef" class="kw-mention-popover"
      :style="{ left: `${mentionPosition.x}px`, top: `${mentionPosition.y}px` }">
      <el-input v-model="mentionQuery" size="small" clearable placeholder="搜索知识实体…"
        class="kw-mention-search" @keydown.stop="onMentionKeydown" />
      <div ref="mentionListRef" class="kw-mention-list" @scroll="onMentionScroll">
        <div class="kw-mention-spacer" :style="{ height: `${mentionOptions.length * MENTION_ROW_HEIGHT}px` }">
          <button v-for="(item, index) in mentionWindow" :key="item.pageId" type="button"
            class="kw-mention-item" :class="{ 'is-active': mentionStartIndex + index === mentionActiveIndex }"
            :style="{ top: `${(mentionStartIndex + index) * MENTION_ROW_HEIGHT}px` }"
            @mousedown.prevent="insertMention(item)">
            <span class="kw-mention-item__dot" :style="{ background: pageTypeMeta(item.pageType).color }"></span>
            <span class="kw-mention-item__title">{{ item.title }}</span>
            <em>{{ pageTypeMeta(item.pageType).label }}</em>
          </button>
        </div>
        <div v-if="!mentionOptions.length" class="kw-mention-empty">没有匹配的知识实体</div>
      </div>
      <div class="kw-mention-foot">
        <span>{{ mentionOptions.length }} 个实体</span>
        <span>↑↓ 选择 · Enter 插入 · Esc 关闭</span>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { updateWikiPage } from '@/api/ai/workspace'

const props = defineProps<{
  modelValue: boolean
  page: any
  pages?: any[]
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'saved', page: any): void
}>()

const saving = ref(false)
const draft = ref<any>(null)
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
})

watch(
  () => [props.modelValue, props.page],
  () => {
    if (!props.modelValue || !props.page) return
    draft.value = {
      title: props.page.title || '',
      summary: props.page.summary || '',
      sections: (props.page.sections || []).map((section: any) => ({
        heading: section.heading || '',
        body: section.body || '',
        sourceChunkIds: [...(section.sourceChunkIds || [])]
      }))
    }
  },
  { immediate: true, deep: true }
)

const MENTION_ROW_HEIGHT = 38
const mentionVisible = ref(false)
const mentionQuery = ref('')
const mentionPosition = reactive({ x: 12, y: 12 })
const mentionPopoverRef = ref<HTMLElement | null>(null)
const mentionListRef = ref<HTMLElement | null>(null)
const mentionTextarea = ref<HTMLTextAreaElement | null>(null)
const mentionAnchorIndex = ref(0)
const mentionSectionIndex = ref(-1)
const mentionScrollTop = ref(0)
const mentionActiveIndex = ref(0)

const PAGE_TYPE_META: Record<string, { label: string; color: string }> = {
  summary: { label: '摘要', color: '#3B7CFF' },
  entity: { label: '实体', color: '#2F9E8F' },
  concept: { label: '概念', color: '#F08A24' },
  synthesis: { label: '综合', color: '#2D8CF0' },
  comparison: { label: '对比', color: '#D95757' }
}

function pageTypeMeta(type?: string) {
  const key = !type || type === 'topic' ? 'concept' : type
  return PAGE_TYPE_META[key] || PAGE_TYPE_META.concept
}

const mentionOptions = computed(() => {
  const currentId = Number(props.page?.pageId || 0)
  const query = mentionQuery.value.trim().toLowerCase()
  return (props.pages || [])
    .filter((item: any) => Number(item.pageId) !== currentId)
    .filter((item: any) => {
      if (!query) return true
      const haystack = `${item.title || ''} ${item.summary || ''} ${(item.aliases || []).join(' ')}`.toLowerCase()
      return haystack.includes(query)
    })
})

const mentionStartIndex = computed(() =>
  Math.max(0, Math.floor(mentionScrollTop.value / MENTION_ROW_HEIGHT))
)
const mentionWindow = computed(() =>
  mentionOptions.value.slice(mentionStartIndex.value, mentionStartIndex.value + 10)
)

function closeMention() {
  mentionVisible.value = false
  mentionTextarea.value = null
  mentionSectionIndex.value = -1
}

function syncMentionFromTextarea(index: number, textarea: HTMLTextAreaElement) {
  const cursor = textarea.selectionStart ?? 0
  const before = textarea.value.slice(0, cursor)
  const match = before.match(/@([^\s@]*)$/)
  if (!match) {
    closeMention()
    return
  }
  mentionTextarea.value = textarea
  mentionSectionIndex.value = index
  mentionAnchorIndex.value = cursor - match[0].length
  mentionQuery.value = match[1]
  mentionScrollTop.value = 0
  mentionActiveIndex.value = 0
  const rect = textarea.getBoundingClientRect()
  const width = 340
  const height = 350
  mentionPosition.x = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + 8))
  mentionPosition.y = rect.bottom + height > window.innerHeight
    ? Math.max(12, rect.top - height - 8)
    : rect.bottom + 8
  mentionVisible.value = true
}

function onSectionClick(index: number, event: MouseEvent) {
  const textarea = event.target as HTMLTextAreaElement
  if (textarea?.tagName === 'TEXTAREA') syncMentionFromTextarea(index, textarea)
}

function onSectionInput(index: number, value: any) {
  const textarea = document.activeElement as HTMLTextAreaElement | null
  if (!textarea || textarea.tagName !== 'TEXTAREA') return
  // Element Plus 的 input 事件传的是 value；v-model 已经同步，直接按当前光标计算。
  if (typeof value === 'string' && textarea.value !== value) return
  syncMentionFromTextarea(index, textarea)
}

function onSectionKeyup(index: number, event: KeyboardEvent) {
  const textarea = event.target as HTMLTextAreaElement
  if (!textarea || textarea.tagName !== 'TEXTAREA') return
  if (event.key === 'Escape') {
    closeMention()
    return
  }
  syncMentionFromTextarea(index, textarea)
}

function onMentionScroll(event: Event) {
  const target = event.target as HTMLElement
  mentionScrollTop.value = target.scrollTop
}

function onMentionKeydown(event: KeyboardEvent) {
  if (!mentionVisible.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    closeMention()
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const delta = event.key === 'ArrowDown' ? 1 : -1
    mentionActiveIndex.value = Math.max(0, Math.min(mentionOptions.value.length - 1, mentionActiveIndex.value + delta))
    const active = mentionActiveIndex.value
    if (mentionListRef.value) {
      if (active < mentionStartIndex.value) mentionListRef.value.scrollTop = active * MENTION_ROW_HEIGHT
      else if (active >= mentionStartIndex.value + 10) mentionListRef.value.scrollTop = (active - 9) * MENTION_ROW_HEIGHT
    }
    return
  }
  if (event.key === 'Enter') {
    event.preventDefault()
    const item = mentionOptions.value[mentionActiveIndex.value]
    if (item) insertMention(item)
  }
}

async function insertMention(item: any) {
  const textarea = mentionTextarea.value
  if (!textarea || !item) return
  const value = textarea.value
  const start = mentionAnchorIndex.value
  const end = textarea.selectionStart ?? start
  const token = `[[page:${item.pageId}|${item.title}]]`
  const next = value.slice(0, start) + token + value.slice(end)
  const section = draft.value?.sections?.[mentionSectionIndex.value]
  if (section) section.body = next
  closeMention()
  await nextTick()
  const pos = start + token.length
  textarea.focus()
  textarea.setSelectionRange(pos, pos)
}

function onMentionOutside(event: PointerEvent) {
  if (!mentionVisible.value) return
  const target = event.target as Node
  if (mentionPopoverRef.value?.contains(target) || mentionTextarea.value?.contains(target)) return
  closeMention()
}

watch(mentionQuery, () => {
  mentionScrollTop.value = 0
  mentionActiveIndex.value = 0
})

onMounted(() => document.addEventListener('pointerdown', onMentionOutside, true))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onMentionOutside, true))

function addSection() {
  if (!draft.value) return
  draft.value.sections.push({ heading: '', body: '', sourceChunkIds: [] })
}

function removeSection(index: number) {
  if (!draft.value || draft.value.sections.length <= 1) return
  draft.value.sections.splice(index, 1)
}

async function save() {
  if (!draft.value || !props.page?.pageId) return
  if (!draft.value.title.trim()) {
    ElMessage.warning('标题不能为空')
    return
  }
  const sections = draft.value.sections
    .map((section: any) => ({
      heading: String(section.heading || '').trim(),
      body: String(section.body || '').trim(),
      sourceChunkIds: section.sourceChunkIds || []
    }))
    .filter((section: any) => section.heading && section.body)
  if (!sections.length) {
    ElMessage.warning('至少保留一个完整的小节')
    return
  }
  saving.value = true
  try {
    const res = await updateWikiPage(props.page.pageId, {
      title: draft.value.title.trim(),
      summary: draft.value.summary.trim(),
      sections,
      changeType: 'manual',
      baseVersion: Number(props.page.version || 1)
    })
    if (res.code !== 200) {
      ElMessage.error(res.msg || '保存失败')
      return
    }
    ElMessage.success('主题页已保存')
    emit('saved', res.data)
    visible.value = false
  } catch (error: any) {
    ElMessage.error('保存失败：' + (error?.message || error))
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.kw-editor { display: flex; flex-direction: column; gap: 10px; max-height: 68vh; overflow-y: auto; padding-right: 4px; }
.kw-editor__hint { padding: 8px 10px; border-radius: 8px; color: #7d8596; background: #f6f8fc; font-size: 11px; line-height: 1.6; }
.kw-editor__label { margin-top: 4px; color: #4b5563; font-size: 12px; font-weight: 600; }
.kw-editor__section-head { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; color: #4b5563; font-size: 12px; font-weight: 600; }
.kw-editor__section { margin-top: 8px; padding: 10px; border: 1px solid #e8edf5; border-radius: 9px; background: #fbfcfe; }
.kw-editor__section-top { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kw-editor__source { margin-top: 5px; color: #9aa1af; font-size: 10px; }
.kw-editor__mention-hint { margin-top: 3px; color: #a0a6b2; font-size: 10px; }
.kw-editor__mention-hint b { color: #2f5fce; font-weight: 600; }
.kw-mention-popover { position: fixed; z-index: 4000; width: 340px; padding: 9px; border: 1px solid #e4eaf3; border-radius: 11px; background: #fff; box-shadow: 0 14px 36px rgba(28, 45, 75, .16); }
.kw-mention-search :deep(.el-input__wrapper) { border-radius: 7px; box-shadow: 0 0 0 1px #e7ecf5 inset; }
.kw-mention-list { position: relative; height: 260px; margin-top: 7px; overflow-y: auto; overscroll-behavior: contain; }
.kw-mention-spacer { position: relative; width: 100%; }
.kw-mention-item { position: absolute; left: 0; right: 0; display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 8px; border: 0; border-radius: 7px; color: #4b5563; background: transparent; cursor: pointer; font: inherit; font-size: 11px; text-align: left; }
.kw-mention-item:hover, .kw-mention-item.is-active { background: #f3f7ff; }
.kw-mention-item__dot { width: 8px; height: 8px; flex: none; border-radius: 50%; }
.kw-mention-item__title { overflow: hidden; flex: 1; text-overflow: ellipsis; white-space: nowrap; }
.kw-mention-item em { flex: none; color: #a0a6b2; font-size: 9px; font-style: normal; }
.kw-mention-empty { padding: 20px 8px; color: #a0a6b2; font-size: 11px; text-align: center; }
.kw-mention-foot { display: flex; justify-content: space-between; gap: 8px; padding: 6px 2px 1px; color: #a0a6b2; font-size: 9px; }
</style>
