<template>
  <div class="chat-answer-body">
    <div v-for="(block, index) in blocks" :key="index" class="chat-answer-block">
      <div class="chat-answer-block__html" v-html="renderAgentMarkdown(block.content)"></div>
      <ChatSourceList v-if="block.references.length" :references="block.references" :show-label="false"
        @open-document="$emit('open-document', $event)" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderAgentMarkdown } from '@/utils/markdown'
import ChatSourceList from '@/components/ChatSourceList/index.vue'

const props = defineProps<{
  content: string
  references: any[]
}>()
const emit = defineEmits<{ (e: 'open-document', item: any): void }>()

type Block = { content: string; references: any[] }

function trimBlock(value: string) {
  return value.replace(/^\s+|\s+$/g, '')
}

function splitBlocks(content: string): string[] {
  const text = String(content || '')
  if (!text.trim()) return []
  const blocks: string[] = []
  let current: string[] = []
  let inFence = false
  const flush = () => {
    const value = trimBlock(current.join('\n'))
    if (value) blocks.push(value)
    current = []
  }
  for (const line of text.split('\n')) {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      current.push(line)
      continue
    }
    if (!inFence && !line.trim()) {
      flush()
      continue
    }
    current.push(line)
  }
  flush()
  return blocks
}

function termsOf(text: string): string[] {
  return Array.from(new Set(
    String(text || '')
      .toLowerCase()
      .match(/[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}/g) || []
  ))
}

function pickReferences(block: string): any[] {
  if (!props.references?.length) return []
  const text = block.toLowerCase()
  const answerText = String(props.content || '').toLowerCase()
  const docCounts = new Map<string, number>()
  for (const ref of props.references) {
    const key = String(ref.docId || ref.wikiPageId || ref.docName || ref.wikiPageTitle || '')
    docCounts.set(key, (docCounts.get(key) || 0) + 1)
  }
  const scored = props.references.map((ref: any) => {
    const haystack = `${ref.docName || ''} ${ref.wikiPageTitle || ''} ${ref.source || ''} ${ref.content || ''}`.toLowerCase()
    let directScore = 0
    for (const term of termsOf(block)) {
      if (term.length < 2) continue
      if (haystack.includes(term)) directScore += term.length >= 4 ? 2 : 1
    }
    for (const name of [ref.docName, ref.wikiPageTitle].filter(Boolean)) {
      const normalized = String(name).toLowerCase()
      if (text.includes(normalized)) directScore += 8
    }
    // 回答里提到某份资料时，只在「本段确实命中该资料内容」的前提下加权，
    // 避免把同一份文档的 chip 无差别贴到每一句话后面。
    let score = directScore
    for (const name of [ref.docName, ref.wikiPageTitle].filter(Boolean)) {
      if (answerText.includes(String(name).toLowerCase())) score += 18
    }
    const docKey = String(ref.docId || ref.wikiPageId || ref.docName || ref.wikiPageTitle || '')
    score += Math.min(3, docCounts.get(docKey) || 0)
    return { ref, score, directScore }
  }).sort((a, b) => b.score - a.score)

  // 每个段落只挂一个最相关的来源；没有直接内容命中就不硬贴来源。
  const best = scored[0]
  return best && best.directScore > 0 ? [best.ref] : []
}

function isHeadingBlock(content: string): boolean {
  return /^#{1,6}\s+/.test(content.trim()) || /^([一二三四五六七八九十百]+[、.]|\d+[.、])\s*[^\n]{2,24}$/.test(content.trim())
}

function isFollowUpBlock(content: string): boolean {
  const text = content.replace(/^[-*+]\s*/, '').trim()
  if (!text) return false
  if (/需要的话|我可以接着帮你|接下来你可以|你想用哪一种|需要我|要不要我|如果你需要|如需/.test(text)) return true
  // 结尾的短问句/行动建议不是知识点，不挂文档索引。
  return /[?？]$/.test(text) && text.length <= 100
}

const blocks = computed<Block[]>(() => {
  let followUpMode = false
  return splitBlocks(props.content).map((content) => {
    if (isFollowUpBlock(content)) followUpMode = true
    return {
      content,
      references: followUpMode || isHeadingBlock(content) ? [] : pickReferences(content)
    }
  })
})
</script>

<style scoped>
.chat-answer-body { min-width: 0; }
.chat-answer-block { display: block; }
.chat-answer-block + .chat-answer-block { margin-top: 6px; }
.chat-answer-block__html { display: inline; min-width: 0; }
.chat-answer-block__html :deep(p) { display: inline; margin: 0; }
.chat-answer-block__html :deep(ul), .chat-answer-block__html :deep(ol) { margin: 0; padding-left: 1.3em; }
.chat-answer-block__html :deep(li) { margin: 0; }
.chat-answer-block__html :deep(h1), .chat-answer-block__html :deep(h2), .chat-answer-block__html :deep(h3),
.chat-answer-block__html :deep(h4), .chat-answer-block__html :deep(h5), .chat-answer-block__html :deep(h6) { margin: 6px 0 2px; }
.chat-answer-block__html :deep(pre) { margin: 5px 0; }
</style>
