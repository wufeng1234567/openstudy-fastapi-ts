<template>
  <div class="chat-sources" :class="{ 'chat-sources--compact': showLabel === false }" @mouseleave="scheduleClose">
    <span v-if="showLabel !== false" class="chat-sources__label">参考文档</span>
    <button v-for="group in groups" :key="group.key" type="button" class="chat-source-chip"
      :class="{ 'is-active': float.visible && float.groupKey === group.key }"
      :title="group.chunks.some((chunk: any) => chunk.docId) ? '点击查看文档原文' : group.docName"
      @mouseenter="showGroup(group, $event)" @focus="showGroup(group, $event)" @mouseleave="scheduleClose"
      @click.stop="onChipClick(group, $event)">
      <el-icon class="chat-source-chip__icon"><Document /></el-icon>
      <span class="chat-source-chip__name">{{ group.docName }}</span>
      <span v-if="group.chunks.length > 1" class="chat-source-chip__count">{{ group.chunks.length }}</span>
    </button>

    <Teleport to="body">
      <div v-if="float.visible" class="chat-source-float" :style="{ top: `${float.top}px`, left: `${float.left}px` }"
        @mouseenter="cancelClose" @mouseleave="scheduleClose">
        <div class="chat-source-float__head">
          <el-icon><Document /></el-icon>
          <span>{{ float.docName }}</span>
          <em v-if="float.chunks.length > 1">{{ float.chunks.length }} 个片段</em>
        </div>
        <div class="chat-source-float__body">
          <div v-for="(chunk, index) in float.chunks" :key="chunkKey(chunk, index)" class="chat-source-chunk">
            <div class="chat-source-chunk__meta">
              <span>{{ chunkLabel(chunk, index) }}</span>
              <span v-if="chunk.source" class="chat-source-chunk__source">{{ chunk.source }}</span>
            </div>
            <p>{{ cleanContent(chunk.content) || '这个片段暂无可读内容。' }}</p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Document } from '@element-plus/icons-vue'

const props = defineProps<{ references: any[]; showLabel?: boolean }>()
const emit = defineEmits<{ (e: 'open-document', item: any): void }>()

type SourceGroup = { key: string; docName: string; chunks: any[] }
const float = ref<{ visible: boolean; groupKey: string; docName: string; chunks: any[]; top: number; left: number }>({
  visible: false,
  groupKey: '',
  docName: '',
  chunks: [],
  top: 0,
  left: 0
})
let closeTimer: ReturnType<typeof setTimeout> | null = null

const groups = computed<SourceGroup[]>(() => {
  const map = new Map<string, SourceGroup>()
  for (const ref of props.references || []) {
    const docName = String(ref?.docName || ref?.wikiPageTitle || ref?.source || '未命名文档')
    const key = String(ref?.docId || ref?.wikiPageId || docName)
    if (!map.has(key)) map.set(key, { key, docName, chunks: [] })
    map.get(key)!.chunks.push(ref)
  }
  return Array.from(map.values())
})

function cleanContent(content: string) {
  return String(content || '')
    .replace(/^\s*([-*_])\1{2,}\s*$/gm, '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/(\*\*|__|`)/g, '')
    .replace(/\n{2,}/g, '\n')
    .trim()
}

function chunkLabel(chunk: any, index: number) {
  const number = Number.isFinite(Number(chunk?.chunkIndex)) ? Number(chunk.chunkIndex) + 1 : index + 1
  return chunk?.sourceType === 'wiki' ? (chunk?.wikiPageTitle || `主题页 ${number}`) : `第 ${number} 段`
}

function chunkKey(chunk: any, index: number) {
  return String(chunk?.chunkId ?? `${chunk?.docId || ''}-${chunk?.chunkIndex ?? index}-${index}`)
}

function onChipClick(group: SourceGroup, event: Event) {
  const documentChunk = group.chunks.find((chunk: any) => chunk.docId)
  if (documentChunk) {
    emit('open-document', { ...documentChunk, docName: group.docName })
    return
  }
  showGroup(group, event)
}

function showGroup(group: SourceGroup, event: Event) {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
  const el = event.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const width = 340
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12))
  const top = Math.min(rect.bottom + 8, window.innerHeight - 280)
  float.value = { visible: true, groupKey: group.key, docName: group.docName, chunks: group.chunks, top, left }
}

function cancelClose() {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = null }
}

function scheduleClose() {
  cancelClose()
  closeTimer = setTimeout(() => { float.value.visible = false }, 160)
}

onBeforeUnmount(cancelClose)
</script>

<style scoped>
.chat-sources { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.chat-sources--compact { display: inline-flex; margin-top: 2px; vertical-align: baseline; }
.chat-sources--compact .chat-source-chip { padding: 1px 5px; font-size: 9px; }
.chat-sources__label { margin-right: 1px; color: #a0a7b4; font-size: 10px; }
.chat-source-chip { display: inline-flex; max-width: 240px; align-items: center; gap: 4px; padding: 2px 7px; border: 1px solid #e6eaf1; border-radius: 999px; color: #7a8494; background: #f7f9fc; cursor: pointer; font: inherit; font-size: 10px; line-height: 1.5; transition: background .15s ease, border-color .15s ease, color .15s ease; }
.chat-source-chip:hover, .chat-source-chip.is-active { border-color: #cddaf4; color: #3f5f9d; background: #f0f5ff; }
.chat-source-chip__icon { flex: none; font-size: 12px; }
.chat-source-chip__name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-source-chip__count { display: inline-flex; min-width: 14px; height: 14px; align-items: center; justify-content: center; border-radius: 50%; color: #6f86b8; background: #e5edfd; font-size: 9px; }
.chat-source-float { position: fixed; z-index: 10000; width: 340px; max-width: calc(100vw - 24px); max-height: 360px; overflow-y: auto; padding: 10px 12px 12px; border: 1px solid #e1e6ef; border-radius: 9px; color: #38465c; background: #fff; box-shadow: 0 6px 24px rgba(31, 47, 75, .14); font-size: 12px; line-height: 1.65; animation: source-float-in .15s ease-out both; }
.chat-source-float__head { display: flex; align-items: center; gap: 6px; padding-bottom: 8px; margin-bottom: 7px; border-bottom: 1px solid #edf0f5; color: #34425a; font-size: 12px; font-weight: 600; }
.chat-source-float__head .el-icon { color: #7d8ba3; }
.chat-source-float__head em { margin-left: auto; color: #a0a7b4; font-size: 10px; font-style: normal; font-weight: 400; }
.chat-source-chunk + .chat-source-chunk { margin-top: 9px; padding-top: 9px; border-top: 1px dashed #edf0f5; }
.chat-source-chunk__meta { display: flex; gap: 7px; margin-bottom: 2px; color: #7d8ba3; font-size: 10px; }
.chat-source-chunk__source { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-source-chunk p { display: -webkit-box; overflow: hidden; margin: 0; color: #5f6b7d; -webkit-box-orient: vertical; -webkit-line-clamp: 7; line-clamp: 7; white-space: pre-line; overflow-wrap: anywhere; }
@keyframes source-float-in { from { opacity: 0; transform: translateY(-3px); } }
</style>
