<template>
  <div class="chat-answer-body">
    <div v-for="(block, index) in blocks" :key="index" class="chat-answer-block">
      <div class="chat-answer-block__html" v-html="renderAgentMarkdown(block.content)"></div>
      <ChatSourceList v-if="block.references.length" :references="block.references" :show-label="false" />
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
  return blocks.flatMap(splitListItems)
}

/** 把连续列表拆成「每项一段」，让来源 chip 跟到对应条目后面，而不是堆在回答末尾。 */
function splitListItems(block: string): string[] {
  if (/^\s*```/.test(block)) return [block]
  const lines = block.split('\n')
  const hasList = lines.some((line) => /^\s*(?:[-*+]|\d+[.)])\s+/.test(line))
  if (!hasList) return [block]
  const items: string[] = []
  let prefix: string[] = []
  for (const line of lines) {
    const isItem = /^\s*(?:[-*+]|\d+[.)])\s+/.test(line)
    if (isItem) {
      if (prefix.length) {
        items.push(prefix.join('\n'))
        prefix = []
      }
      items.push(line)
    } else if (items.length && line.trim()) {
      items[items.length - 1] += `\n${line}`
    } else {
      prefix.push(line)
    }
  }
  if (prefix.length) items.push(prefix.join('\n'))
  return items
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
  const scored = props.references.map((ref: any) => {
    const haystack = `${ref.docName || ''} ${ref.wikiPageTitle || ''} ${ref.source || ''} ${ref.content || ''}`.toLowerCase()
    let score = 0
    for (const term of termsOf(block)) {
      if (term.length < 2) continue
      if (haystack.includes(term)) score += term.length >= 4 ? 2 : 1
    }
    for (const name of [ref.docName, ref.wikiPageTitle].filter(Boolean)) {
      if (text.includes(String(name).toLowerCase())) score += 8
    }
    return { ref, score }
  }).sort((a, b) => b.score - a.score)

  // 每个段落只挂一个最相关的来源，避免一条回答刷出几十个 chip、把正文挤满。
  const best = scored[0]
  return best && best.score > 0 ? [best.ref] : []
}

function isHeadingBlock(content: string): boolean {
  return /^#{1,6}\s+/.test(content.trim()) || /^\d+[.、]\s*[^\n]{2,24}$/.test(content.trim())
}

const blocks = computed<Block[]>(() =>
  splitBlocks(props.content).map((content) => ({
    content,
    references: isHeadingBlock(content) ? [] : pickReferences(content)
  }))
)
</script>

<style scoped>
.chat-answer-body { min-width: 0; }
.chat-answer-block { display: block; }
.chat-answer-block + .chat-answer-block { margin-top: 6px; }
.chat-answer-block__html { display: inline; min-width: 0; }
.chat-answer-block__html :deep(p) { display: inline; margin: 0; }
.chat-answer-block__html :deep(ul), .chat-answer-block__html :deep(ol) { display: inline; margin: 0; padding-left: 1.1em; }
.chat-answer-block__html :deep(li) { display: inline; margin: 0; }
.chat-answer-block__html :deep(h1), .chat-answer-block__html :deep(h2), .chat-answer-block__html :deep(h3),
.chat-answer-block__html :deep(h4), .chat-answer-block__html :deep(h5), .chat-answer-block__html :deep(h6) { margin: 6px 0 2px; }
.chat-answer-block__html :deep(pre) { margin: 5px 0; }
</style>
