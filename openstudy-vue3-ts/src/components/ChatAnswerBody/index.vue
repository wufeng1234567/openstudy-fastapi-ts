<template>
  <div class="chat-answer-body">
    <div v-for="(block, index) in blocks" :key="index"
      class="chat-answer-block" :class="{ 'chat-answer-block--plain': !block.section }">
      <div class="chat-answer-block__html" v-html="renderAgentMarkdown(withWebLinks(block.content))"></div>
      <ChatSourceList v-if="block.references.length" :references="block.references" :show-label="false"
        @open-document="$emit('open-document', $event)" />
    </div>
    <!-- 网页搜索的索引必须始终可见：不依赖正文段落是否命中关键词。 -->
    <ChatSourceList v-if="webReferences.length" :references="webReferences" show-label
      @open-document="$emit('open-document', $event)" />
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

type Block = { content: string; references: any[]; section: boolean }

const webReferences = computed(() =>
  (props.references || []).filter(
    (ref: any) => ref?.sourceType === 'web' && /^https?:\/\//i.test(String(ref?.url || ''))
  )
)

/**
 * 模型有时只写 `W3` / `W3、W5`，不写完整 Markdown 链接。这里用真实
 * 搜索结果把它补成可点击的 `[W3](url)`；没有对应 url 的编号保持原样，
 * 绝不编造链接。
 */
function withWebLinks(content: string) {
  let text = String(content || '')
  if (!webReferences.value.length || !text) return text
  const byIndex = new Map<number, string>()
  webReferences.value.forEach((ref: any, position: number) => {
    const index = Number(ref.index || position + 1)
    if (index > 0 && ref.url) byIndex.set(index, String(ref.url))
  })
  if (!byIndex.size) return text
  // 先遮住模型已经写好的 Markdown 链接，避免把链接标签里的 W3 二次替换。
  const links: string[] = []
  text = text.replace(/\[[^\]]*\]\([^)]*\)/g, (whole) => {
    const token = `\u0000MDLINK${links.length}\u0000`
    links.push(whole)
    return token
  })
  text = text.replace(/\bW(\d+)\b/g, (whole: string, number: string) => {
    const url = byIndex.get(Number(number))
    return url ? `[W${number}](${url})` : whole
  })
  return text.replace(/\u0000MDLINK(\d+)\u0000/g, (_whole, index: string) => links[Number(index)] || '')
}
type Group = { content: string; section: boolean }

function trimBlock(value: string) {
  return value.replace(/^\s+|\s+$/g, '')
}

/** 顶层大点标题：一、 / 二、 / 2. / 2、 / ## 标题。 */
function isTopHeadingLine(line: string): boolean {
  const text = line.trim()
  if (!text) return false
  if (/^#{1,6}\s+/.test(text) || /^[一二三四五六七八九十百]+[、.]/.test(text)) return true
  // 数字编号只有短标题才算大点；“1. **模型复杂度过高**——……” 是列表项。
  if (!/^\d+[.、](?!\d)\s*\S/.test(text)) return false
  return text.length <= 40 && !text.includes('**') && !/[—，。；：]/.test(text)
}

/**
 * 按「大点」切组：一个大点标题下面的 2.1/2.2/2.3 及所有列表都算同一段，
 * 只在整段结尾挂一个来源索引；没有标题的回答才按空行分普通段落。
 */
function buildGroups(content: string): Group[] {
  const text = String(content || '')
  if (!text.trim()) return []
  const groups: Group[] = []
  let current: string[] = []
  let currentSection = false
  let inFence = false
  const flush = () => {
    const value = trimBlock(current.join('\n'))
    if (value) groups.push({ content: value, section: currentSection })
    current = []
    currentSection = false
  }
  for (const line of text.split('\n')) {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      current.push(line)
      continue
    }
    if (!inFence && isTopHeadingLine(line)) {
      flush()
      current = [line]
      currentSection = true
      continue
    }
    // 进入大点后，空行和其后的 2.1/2.2/2.3 都留在同一个段落里。
    if (!currentSection && !inFence && !line.trim()) {
      flush()
      continue
    }
    current.push(line)
  }
  flush()
  return groups
}

const COMMON_TERMS = new Set([
  '资料', '内容', '知识', '知识点', '章节', '部分', '方法', '问题', '进行', '可以',
  '需要', '对应', '包括', '其中', '使用', '通过', '以及', '这个', '一个', '我们',
  '学习', '路径', '分析', '数据', '处理', '优化', '输出', '生成', '结果'
])

// 代码/模型训练文档里极常见的英文词：命中它们不能证明“这段正文在讲同一个知识点”。
const CODE_TERMS = new Set([
  'loss', 'model', 'models', 'acc', 'accuracy', 'compile', 'optimizer', 'adam',
  'keras', 'tensorflow', 'predict', 'prediction', 'print', 'import', 'true',
  'false', 'train', 'test', 'data', 'image', 'images', 'label', 'labels'
])

function termsOf(text: string): string[] {
  return Array.from(new Set(
    String(text || '')
      .toLowerCase()
      .match(/[\u4e00-\u9fff]{2,}|[a-z0-9_]{2,}/g) || []
  )).filter((term) => !COMMON_TERMS.has(term))
}

/** 从一个可能跨章节的 chunk 里，截出和当前回答段落字符串最接近的片段。 */
function bestSnippet(content: string, block: string): string {
  const text = String(content || '').replace(/\r\n/g, '\n').trim()
  const terms = termsOf(block)
  if (!text || !terms.length) return text.slice(0, 600)
  const lines = text.split('\n')
  let best = { score: -1, start: 0, end: Math.min(lines.length, 3) }
  for (let i = 0; i < lines.length; i += 1) {
    for (let size = 1; size <= 4 && i + size <= lines.length; size += 1) {
      const segment = lines.slice(i, i + size).join('\n').toLowerCase()
      let score = 0
      for (const term of terms) {
        if (segment.includes(term)) score += term.length >= 4 ? 3 : 1
      }
      if (score > best.score) best = { score, start: i, end: i + size }
    }
  }
  if (best.score <= 0) return text.slice(0, 600)
  // 前后各带一行，保留上下文但不把整个跨章节 chunk 都塞进浮层。
  const start = Math.max(0, best.start - 1)
  const end = Math.min(lines.length, best.end + 1)
  return lines.slice(start, end).join('\n').trim().slice(0, 900)
}

/** 清洗一行原文，得到可以拿去 DOM 文本节点里匹配的高亮种子。 */
function cleanHighlightLine(line: string): string {
  return String(line || '')
    .replace(/【图\d+】/g, ' ')
    .replace(/^\s*(?:#{1,6}|>|[-+*]|\d+[.、])\s*/, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`~]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * 从 snippet 中挑“最适合做高亮锚点”的一行：
 * 先按当前回答段落的命中词打分，分数相同取更长的一行；
 * 都命不中时退化为最长的一行。绝不把 `【图N】` 或 Markdown 标记带进查询串。
 */
function highlightLineOf(snippet: string, block: string): string {
  const terms = termsOf(block)
  const lines = String(snippet || '')
    .split('\n')
    .map(cleanHighlightLine)
    .filter((line) => line.length >= 2)
  if (!lines.length) return ''
  let best = ''
  let bestScore = -1
  for (const line of lines) {
    let score = 0
    for (const term of terms) {
      if (line.includes(term)) score += term.length >= 4 ? 2 : 1
    }
    if (score > bestScore || (score === bestScore && line.length > best.length)) {
      best = line
      bestScore = score
    }
  }
  return best || lines.sort((a, b) => b.length - a.length)[0] || ''
}

function imageSeqOf(snippet: string): number | null {
  const match = String(snippet || '').match(/【图(\d+)】/)
  return match ? Number(match[1]) : null
}

function pickReferences(block: string, references: any[] = props.references): any[] {
  // 网页来源统一走底部「参考来源 N 个网页」汇总；不要在正文段落里再贴一遍 chip。
  const docReferences = (references || []).filter((ref: any) => ref?.sourceType !== 'web')
  if (!docReferences.length) return []
  const text = block.toLowerCase()
  const docCounts = new Map<string, number>()
  for (const ref of docReferences) {
    const key = String(ref.docId || ref.wikiPageId || ref.docName || ref.wikiPageTitle || '')
    docCounts.set(key, (docCounts.get(key) || 0) + 1)
  }
  const scored = docReferences.map((ref: any) => {
    const haystack = `${ref.docName || ''} ${ref.wikiPageTitle || ''} ${ref.source || ''} ${ref.content || ''}`.toLowerCase()
    let directScore = 0
    const matchedTerms: string[] = []
    for (const term of termsOf(block)) {
      if (term.length < 2 || CODE_TERMS.has(term)) continue
      if (haystack.includes(term)) {
        matchedTerms.push(term)
        directScore += term.length >= 4 ? 2 : 1
      }
    }
    for (const name of [ref.docName, ref.wikiPageTitle].filter(Boolean)) {
      const normalized = String(name).toLowerCase()
      if (text.includes(normalized)) directScore += 8
    }
    // 只用当前段落自己的直接命中分数，绝不把回答末尾提到的知识百科
    // 反向加权到前面的所有段落（那会把真正命中的文档压掉）。
    let score = directScore
    const docKey = String(ref.docId || ref.wikiPageId || ref.docName || ref.wikiPageTitle || '')
    score += Math.min(3, docCounts.get(docKey) || 0)
    // 只命中一个「折线图」或代码词 `loss` 不算内容匹配；至少一个 4 字词，
    // 或两个 3 字词，才允许给这一段挂来源。
    const strongMatch = matchedTerms.some((term) => term.length >= 4)
      || matchedTerms.filter((term) => term.length >= 3).length >= 2
    return { ref, score, directScore, strongMatch }
  }).sort((a, b) => b.score - a.score)

  // 每个段落只挂一个最相关的来源；没有直接内容命中就不硬贴来源。
  const best = scored[0]
  if (!best || best.directScore <= 0 || !best.strongMatch) return []
  const snippet = bestSnippet(best.ref.content, block)
  return [{
    ...best.ref,
    // 完整 chunk 保留给定位；snippet 只用于 hover 浮层和阅读器打开参数。
    content: best.ref.content,
    snippet,
    highlightText: highlightLineOf(snippet, block),
    imageSeq: imageSeqOf(snippet) ?? (best.ref.imageSeq ?? null)
  }]
}

function isFollowUpBlock(content: string): boolean {
  const text = content.replace(/^[-*+]\s*/, '').trim()
  if (!text) return false
  if (/需要的话|我可以接着帮你|接下来你可以|你想用哪一种|需要我|要不要我|如果你需要|如需/.test(text)) return true
  // 结尾的行动建议 / 短问句不是知识点，不挂文档索引。
  if (/^(按这份资料|画一张|把它整理|或打开|做成教学|生成一|出一套)/.test(text) && text.length <= 120) return true
  return /[?？]$/.test(text) && text.length <= 100
}

function isPreambleBlock(content: string): boolean {
  return /^(我先|我先在|我先查|我查|我看|让我|好的|收到|已核对|已经核对)/.test(content.trim())
}

function isHeadingOnlyBlock(content: string): boolean {
  const text = content.trim()
  if (text.includes('\n') || !isTopHeadingLine(text)) return false
  // "1. **模型复杂度过高**……" 是列表项，不是章节标题；真正的标题应当短、
  // 不含加粗标记/句号式解释。
  return text.length <= 32 && !text.includes('**') && !/[：:，。；]/.test(text)
}

const blocks = computed<Block[]>(() =>
  buildGroups(props.content).map((group) => ({
    content: group.content,
    section: group.section,
    references:
      isFollowUpBlock(group.content) || isPreambleBlock(group.content) || isHeadingOnlyBlock(group.content)
        ? []
        : pickReferences(group.content, props.references)
  }))
)
</script>

<style scoped>
.chat-answer-body { min-width: 0; }
.chat-answer-block { display: block; }
.chat-answer-block + .chat-answer-block { margin-top: 10px; }
.chat-answer-block__html { display: block; min-width: 0; }
.chat-answer-block__html :deep(p) { margin: 0 0 5px; }
.chat-answer-block__html :deep(p:last-child) { margin-bottom: 0; }
.chat-answer-block__html :deep(ul), .chat-answer-block__html :deep(ol) { margin: 3px 0 0; padding-left: 1.4em; }
.chat-answer-block__html :deep(li) { margin: 2px 0; }
.chat-answer-block__html :deep(h1), .chat-answer-block__html :deep(h2), .chat-answer-block__html :deep(h3),
.chat-answer-block__html :deep(h4), .chat-answer-block__html :deep(h5), .chat-answer-block__html :deep(h6) { margin: 6px 0 3px; }
.chat-answer-block__html :deep(pre) { margin: 5px 0; }
.chat-answer-block--plain .chat-answer-block__html :deep(p) { display: inline; margin: 0; }
.chat-answer-block--plain { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px; }
</style>
