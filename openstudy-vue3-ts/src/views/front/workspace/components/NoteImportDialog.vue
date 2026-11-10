<template>
  <el-dialog
    :model-value="modelValue"
    title="导入笔记"
    width="680px"
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="note-import">
      <div class="note-import__tabs">
        <button type="button" :class="{ 'is-active': tab === 'existing' }" @click="tab = 'existing'">
          从我的笔记导入
        </button>
        <button type="button" :class="{ 'is-active': tab === 'new' }" @click="tab = 'new'">
          新建/上传笔记
        </button>
      </div>

      <template v-if="tab === 'existing'">
        <div class="note-import__bar">
          <el-input v-model="keyword" clearable placeholder="搜索笔记标题…" />
          <el-button size="small" plain :loading="loading" @click="loadNotes">刷新</el-button>
        </div>
        <div v-loading="loading" class="note-import__list">
          <label v-for="note in filteredNotes" :key="note.noteId" class="note-import__item">
            <el-checkbox
              :model-value="selectedIds.includes(Number(note.noteId))"
              :disabled="note.linked || importing"
              @change="toggleNote(Number(note.noteId))"
            />
            <span class="note-import__main">
              <b>{{ note.title || '未命名笔记' }}</b>
              <em>{{ note.summary || '暂无摘要' }}</em>
            </span>
            <el-tag v-if="note.linked" size="small" type="success" effect="plain">已关联</el-tag>
          </label>
          <div v-if="!loading && !filteredNotes.length" class="note-import__empty">
            没有可导入的笔记。可以先在「我的笔记」里写一篇，或使用“新建/上传笔记”。
          </div>
        </div>
      </template>

      <template v-else>
        <div class="note-import__form">
          <label>笔记标题</label>
          <el-input v-model="newTitle" maxlength="120" placeholder="例如：智能体学习笔记" />
          <label>正文</label>
          <el-input v-model="newContent" type="textarea" :rows="9" placeholder="直接粘贴正文，或选择一个 .md / .txt 文件" />
          <div class="note-import__file">
            <input ref="fileInputRef" type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" @change="onFilePicked" />
          </div>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="close">取消</el-button>
      <el-button
        v-if="tab === 'existing'"
        type="primary"
        :loading="importing"
        :disabled="!selectedIds.length"
        @click="importSelected"
      >
        导入选中（{{ selectedIds.length }}）
      </el-button>
      <el-button v-else type="primary" :loading="importing" :disabled="!newTitle.trim() || !newContent.trim()" @click="createAndImport">
        创建并导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listKbNotes, linkKbNote } from '@/api/ai/noteKbLink'
import { addNote } from '@/api/notes/note'
import { addNoteCategory, getAllNoteCategory } from '@/api/noteCategory/noteCategory'

const props = defineProps<{
  modelValue: boolean
  kbId: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'imported'): void
  (e: 'busy', value: boolean): void
}>()

const tab = ref<'existing' | 'new'>('existing')
const keyword = ref('')
const loading = ref(false)
const importing = ref(false)
const notes = ref<any[]>([])
const selectedIds = ref<number[]>([])
const newTitle = ref('')
const newContent = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

const filteredNotes = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return notes.value
  return notes.value.filter((note: any) =>
    `${note.title || ''} ${note.summary || ''}`.toLowerCase().includes(query)
  )
})

watch(() => props.modelValue, (visible) => {
  if (visible) {
    selectedIds.value = []
    keyword.value = ''
    tab.value = 'existing'
    newTitle.value = ''
    newContent.value = ''
    void loadNotes()
  }
})

function close() {
  emit('update:modelValue', false)
}

async function loadNotes() {
  if (!props.kbId) return
  loading.value = true
  try {
    const res: any = await listKbNotes(props.kbId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || '读取笔记失败')
      notes.value = []
      return
    }
    const available = (res.data?.available || []).filter((note: any) => !note.linked)
    notes.value = available
  } catch (error: any) {
    ElMessage.error('读取笔记失败：' + (error?.message || error))
    notes.value = []
  } finally {
    loading.value = false
  }
}

function toggleNote(noteId: number) {
  const index = selectedIds.value.indexOf(noteId)
  if (index >= 0) selectedIds.value.splice(index, 1)
  else selectedIds.value.push(noteId)
}

async function importSelected() {
  if (!selectedIds.value.length || importing.value) return
  importing.value = true
  emit('busy', true)
  try {
    let ok = 0
    for (const noteId of selectedIds.value) {
      const res: any = await linkKbNote(props.kbId, noteId)
      if (res.code === 200) ok += 1
      else ElMessage.error(res.msg || `笔记 ${noteId} 关联失败`)
    }
    if (ok) {
      ElMessage.success(`已关联 ${ok} 篇笔记，知识点抽取会在后台进行`)
      emit('imported')
      close()
    }
  } catch (error: any) {
    ElMessage.error('导入笔记失败：' + (error?.message || error))
  } finally {
    importing.value = false
    emit('busy', false)
  }
}

async function ensureCategoryId(): Promise<number> {
  const res: any = await getAllNoteCategory()
  const categories = res.code === 200 ? (res.data || []) : []
  if (categories.length) return Number(categories[0].id || categories[0].categoryId || 0)
  const created: any = await addNoteCategory({ name: '默认分类' })
  if (created.code !== 200) throw new Error(created.msg || '创建笔记分类失败')
  return Number(created.data?.id || created.data?.categoryId || 0)
}

async function createAndImport() {
  if (!props.kbId || importing.value) return
  importing.value = true
  emit('busy', true)
  try {
    const categoryId = await ensureCategoryId()
    const created: any = await addNote({
      title: newTitle.value.trim(),
      content: newContent.value,
      markdownContent: newContent.value,
      categoryId,
      isPublic: 0,
      status: 'draft'
    })
    if (created.code !== 200) {
      ElMessage.error(created.msg || '创建笔记失败')
      return
    }
    const noteId = Number(created.data?.noteId || created.data?.id || 0)
    if (!noteId) {
      ElMessage.error('创建笔记成功，但没有返回笔记 ID')
      return
    }
    const linked: any = await linkKbNote(props.kbId, noteId)
    if (linked.code !== 200) {
      ElMessage.error(linked.msg || '笔记已创建，但关联资料夹失败')
      return
    }
    ElMessage.success('笔记已创建并关联，知识点抽取会在后台进行')
    emit('imported')
    close()
  } catch (error: any) {
    ElMessage.error('创建笔记失败：' + (error?.message || error))
  } finally {
    importing.value = false
    emit('busy', false)
  }
}

function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    newContent.value = String(reader.result || '')
    if (!newTitle.value.trim()) {
      newTitle.value = file.name.replace(/\.(md|markdown|txt)$/i, '')
    }
  }
  reader.readAsText(file)
  input.value = ''
}
</script>

<style scoped>
.note-import { display: flex; flex-direction: column; gap: 12px; }
.note-import__tabs { display: inline-flex; align-self: flex-start; padding: 2px; border: 1px solid #e6ebf4; border-radius: 8px; background: #f8fafc; }
.note-import__tabs button { padding: 6px 12px; border: 0; border-radius: 6px; color: #7d8596; background: transparent; cursor: pointer; font: inherit; font-size: 12px; }
.note-import__tabs button.is-active { color: #2f5fce; background: #fff; box-shadow: 0 1px 4px rgba(47, 95, 206, .1); font-weight: 600; }
.note-import__bar { display: flex; gap: 8px; align-items: center; }
.note-import__bar .el-input { flex: 1; }
.note-import__list { max-height: 360px; overflow-y: auto; border: 1px solid #edf0f5; border-radius: 9px; padding: 4px; }
.note-import__item { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-radius: 7px; cursor: pointer; }
.note-import__item:hover { background: #f6f9ff; }
.note-import__main { display: flex; min-width: 0; flex: 1; flex-direction: column; gap: 3px; }
.note-import__main b { overflow: hidden; color: #253247; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.note-import__main em { overflow: hidden; color: #9aa1af; font-size: 10px; font-style: normal; text-overflow: ellipsis; white-space: nowrap; }
.note-import__empty { padding: 28px 12px; color: #9aa1af; font-size: 12px; text-align: center; }
.note-import__form { display: flex; flex-direction: column; gap: 9px; }
.note-import__form label { color: #5f6b7d; font-size: 12px; font-weight: 600; }
.note-import__file input { color: #7d8596; font-size: 11px; }
</style>
