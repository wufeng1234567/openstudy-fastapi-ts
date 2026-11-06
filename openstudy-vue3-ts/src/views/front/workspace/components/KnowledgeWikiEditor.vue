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
      <div v-for="(section, index) in draft.sections" :key="index" class="kw-editor__section">
        <div class="kw-editor__section-top">
          <el-input v-model="section.heading" maxlength="60" placeholder="小节标题" />
          <el-button size="small" text type="danger" :disabled="draft.sections.length <= 1"
            @click="removeSection(index)">删除</el-button>
        </div>
        <el-input v-model="section.body" type="textarea" :rows="4" maxlength="1600" show-word-limit
          placeholder="只写主题页内容；引用来源仍以原始资料为准" />
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
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { updateWikiPage } from '@/api/ai/workspace'

const props = defineProps<{
  modelValue: boolean
  page: any
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
</style>
