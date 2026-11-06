<!--
  资料阅读器弹窗外壳。
  内容与“资料诊疗室”里的原文阅读共用 DocumentAnatomyPanel，避免两套实现分叉。
-->
<template>
  <el-dialog v-model="visible" :title="`资料原文 · ${docName}`" width="min(1180px, 94vw)" top="3vh"
    append-to-body destroy-on-close class="kbp-reader-dialog">
    <DocumentAnatomyPanel ref="panelRef" :show-edit="props.showEdit" @edit="onEdit" />
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import DocumentAnatomyPanel from './DocumentAnatomyPanel.vue'

defineOptions({ name: 'DocumentAnatomyDialog' })

interface AnatomyDoc {
  docId: number
  fileName?: string
  chunkCount?: number
}

interface AnatomyOptions {
  highlight?: string
  chunkId?: number
  chunkIndex?: number
  chunkCount?: number
  targetText?: string
  offset?: number
}

const props = withDefaults(defineProps<{ showEdit?: boolean }>(), { showEdit: false })
const emit = defineEmits<{
  (e: 'edit', doc: AnatomyDoc): void
}>()

const visible = ref(false)
const docName = ref('')
const panelRef = ref<InstanceType<typeof DocumentAnatomyPanel> | null>(null)

function onEdit(doc: AnatomyDoc) {
  emit('edit', doc)
}

async function open(doc: AnatomyDoc, opts: AnatomyOptions = {}) {
  docName.value = doc.fileName || '未命名资料'
  visible.value = true
  await nextTick()
  panelRef.value?.open(doc, opts)
}

defineExpose({ open })
</script>
