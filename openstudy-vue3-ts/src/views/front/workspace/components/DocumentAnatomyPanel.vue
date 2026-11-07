<!--
  资料阅读器（原「资料剖析」的核心阅读面板）

  设计目标：
  · 左侧目录是真导航：点击滚动、滚动高亮、可收起、可搜索；
  · 正文限宽，图片收进抽屉；
  · 支持 LLM 清洗后的章节偏移与 chunk 兜底；
  · 选中文字可问 AI / 出题 / 复制，作为学习资料的阅读入口。
-->
<template>
  <div ref="readerRoot" class="reader-panel">
    <div class="reader-toolbar">
      <div class="reader-toolbar__title">
        <span class="reader-toolbar__kicker">资料原文</span>
        <b :title="docName">{{ docName || '未命名资料' }}</b>
      </div>
      <div class="reader-toolbar__tools">
        <el-input v-model="searchInput" class="reader-search" size="small" clearable
          placeholder="搜索正文" @keyup.enter="startSearch">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <span v-if="searchInput.trim() && searchCount" class="reader-search__count">
          {{ searchIndex + 1 }}/{{ searchCount }}
        </span>
        <el-button v-if="searchInput.trim()" size="small" text @click="nextSearch">下一处</el-button>
        <el-button size="small" plain @click="toggleToc">{{ tocCollapsed ? '展开目录' : '收起目录' }}</el-button>
        <el-button size="small" plain @click="openImages">图片 {{ images.length }}</el-button>
        <el-button v-if="showEdit" size="small" text type="primary" @click="emitEdit">编辑</el-button>
        <el-button size="small" plain @click="openRelatedPages">相关主题页</el-button>
        <el-button v-if="showClose" class="reader-close" size="small" text circle
          title="关闭" aria-label="关闭" @click="emit('close')">
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>

    <div class="reader-stats">
      <span><b>{{ stats.contentLength }}</b> 字</span>
      <span><b>{{ sections.length }}</b> 节</span>
      <span><b>{{ images.length }}</b> 张图</span>
      <span v-if="needsAiOutline" class="reader-stats__ai">
        <el-button size="small" text type="primary" :loading="aiBuilding" @click="rebuildOutline">AI 整理目录</el-button>
      </span>
    </div>

    <div v-if="loading" class="reader-loading" v-loading="true"></div>
    <div v-else class="reader-body" :class="{ 'is-toc-collapsed': tocCollapsed }">
      <aside class="reader-toc">
        <div class="reader-toc__head">
          <span>目录</span>
          <button type="button" @click="tocCollapsed = true">‹</button>
        </div>
        <template v-if="!tocCollapsed">
          <el-input v-model="tocQuery" size="small" clearable placeholder="搜索目录" class="reader-toc__search" />
          <div class="reader-toc__list">
            <button v-for="item in filteredSections" :key="item.index" type="button"
              class="reader-toc__item" :class="{ 'is-active': activeSection === item.index }"
              :style="{ paddingLeft: `${12 + Math.max(0, Number(item.level || 1) - 1) * 14}px` }"
              @click="scrollToSection(item.index)">
              <span class="reader-toc__dot"></span>
              <span class="reader-toc__label" :title="item.title">{{ item.title }}</span>
            </button>
            <div v-if="!filteredSections.length" class="reader-toc__empty">没有匹配的章节</div>
          </div>
          <div v-if="needsAiOutline" class="reader-toc__hint">
            当前目录是分段兜底，可点上方「AI 整理目录」按内容重新识别章节。
          </div>
        </template>
      </aside>

      <main ref="readerScroll" class="reader-main" @scroll="onContentScroll" @mouseup="onContentMouseUp">
        <article class="reader-article">
          <section v-for="section in sections" :key="section.index" :ref="(el) => setSectionRef(section.index, el)"
            class="reader-section" :data-section-index="section.index">
            <h2 v-if="Number(section.level || 1) <= 2" class="reader-section__title">{{ section.title }}</h2>
            <h3 v-else class="reader-section__title reader-section__title--sub">{{ section.title }}</h3>
            <template v-for="(seg, segIndex) in sectionSegments(section)" :key="`${section.index}-${segIndex}`">
              <div v-if="seg.type === 'image'" class="reader-image" :data-image-seq="seg.seq"
                :data-raw-start="seg.start" :data-raw-end="seg.end">
                <el-image :src="seg.url" fit="contain" :preview-src-list="[seg.url]" preview-teleported
                  @load="onReaderImageLoad" />
              </div>
              <LatexRenderer v-else :content="seg.text" class="reader-text"
                :data-raw-start="seg.start" :data-raw-end="seg.end" />
            </template>
          </section>
          <div v-if="!sections.length" class="reader-empty">没有可展示的正文，可能还在解析中。</div>
        </article>
      </main>
    </div>

    <el-drawer v-model="imagesVisible" title="资料图片" size="360px" append-to-body class="reader-image-drawer">
      <div class="reader-image-drawer__bar">
        <span>共 {{ images.length }} 张</span>
        <el-checkbox v-model="imageCurrentOnly" size="small">只看当前章节</el-checkbox>
      </div>
      <div class="reader-image-grid">
        <div v-for="img in visibleImages" :key="img.key" class="reader-image-card">
          <el-image :src="img.url" fit="cover" :preview-src-list="[img.url]" preview-teleported @click="scrollToOffset(img.offset)" />
          <div class="reader-image-card__foot">
            <span :title="img.title">{{ img.title }}</span>
            <button type="button" @click="copyImageMarkdown(img)">复制</button>
          </div>
        </div>
        <div v-if="!visibleImages.length" class="reader-empty">当前章节没有图片。</div>
      </div>
    </el-drawer>

    <div v-if="selectionInfo" class="reader-selection" :style="{ left: `${selectionInfo.x}px`, top: `${selectionInfo.y}px` }"
      @mousedown.prevent>
      <button type="button" @click="askSelection('ask')">问 AI 这段</button>
      <button type="button" @click="askSelection('practice')">从这段出题</button>
      <button type="button" @click="askSelection('note')">引用到笔记</button>
      <button type="button" @click="askSelection('prescription')">加入学习处方</button>
      <button type="button" @click="openRelatedPages">相关主题页</button>
      <button type="button" @click="copySelection">复制原文</button>
    </div>

    <el-drawer v-model="relatedVisible" title="相关主题页" size="380px" append-to-body>
      <div v-loading="relatedLoading" class="reader-related">
        <div v-if="!relatedPages.length && !relatedLoading" class="reader-empty">
          没有找到相关主题页，可以先在知识百科里生成。
        </div>
        <div v-for="page in relatedPages" :key="page.pageId" class="reader-related__item">
          <div class="reader-related__title">{{ page.title }}</div>
          <p>{{ page.summary || '暂无摘要' }}</p>
          <span>{{ page.sectionCount || 0 }} 个小节 · {{ page.sourceCount || 0 }} 个来源</span>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Close } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import {
  getDocumentContent,
  getDocumentOutline,
  rebuildDocumentOutline
} from '@/api/ai/rag'
import { listWikiPages } from '@/api/ai/workspace'

defineOptions({ name: 'DocumentAnatomyPanel' })

interface ReaderDoc {
  docId: number
  fileName?: string
  chunkCount?: number
  kbId?: number
}

interface ReaderOptions {
  highlight?: string
  /** 从对话引用跳转时使用：高亮 5 秒后自动消失。 */
  temporaryHighlight?: boolean
  chunkId?: number
  chunkIndex?: number
  chunkCount?: number
  targetText?: string
  offset?: number
  /** 来源片段里【图N】的 N；没有文本命中时用于把图片滚到视野中间并闪一下。 */
  targetImageSeq?: number
  /** 从对话来源打开时默认收起目录，优先展示正文。 */
  collapseToc?: boolean
}

const props = withDefaults(defineProps<{ showEdit?: boolean; showClose?: boolean }>(), {
  showEdit: false,
  showClose: false
})
const emit = defineEmits<{
  (e: 'edit', doc: ReaderDoc): void
  (e: 'close'): void
}>()

const router = useRouter()
const readerRoot = ref<HTMLElement | null>(null)
const readerScroll = ref<HTMLElement | null>(null)
const doc = ref<ReaderDoc | null>(null)
const docName = ref('')
const content = ref('')
const sections = ref<any[]>([])
const imageMap = ref<Record<string, string>>({})
const loading = ref(false)
const aiBuilding = ref(false)
const needsAiOutline = ref(false)
const targetOffset = ref<number | null>(null)
const targetText = ref('')
const targetChunkIndex = ref<number | null>(null)
const targetChunkCount = ref(0)
const targetImageSeq = ref<number | null>(null)
const chunkStarts = ref<any[]>([])
const pendingJumpOffset = ref<number | null>(null)
let lastJumpMark: HTMLElement | null = null
const activeSection = ref(0)
const tocCollapsed = ref(false)
const tocQuery = ref('')
const searchInput = ref('')
const searchIndex = ref(0)
const searchOffsets = ref<number[]>([])
const searchCount = computed(() => searchOffsets.value.length)
const imagesVisible = ref(false)
const imageCurrentOnly = ref(false)
const relatedVisible = ref(false)
const relatedLoading = ref(false)
const relatedPages = ref<any[]>([])
const selectionInfo = ref<{ text: string; x: number; y: number; section: number } | null>(null)
let searchMarkTimer: ReturnType<typeof setTimeout> | null = null
let imageFlashTimer: ReturnType<typeof setTimeout> | null = null
let jumpTimers: ReturnType<typeof setTimeout>[] = []
const sectionEls = new Map<number, HTMLElement>()
const stats = reactive({ contentLength: 0 })

const images = computed(() => {
  const raw = content.value
  return Object.entries(imageMap.value)
    .map(([key, url]) => {
      const marker = `【图${key}】`
      const offset = raw.indexOf(marker)
      const section = sections.value.find((item: any) => offset >= Number(item.start) && offset < Number(item.end))
      return {
        key,
        url: imageUrl(url),
        offset: offset >= 0 ? offset : 0,
        section: section?.index ?? 0,
        title: `图 ${Number(key) + 1}`
      }
    })
    .filter((item) => !!item.url)
})

const visibleImages = computed(() => {
  if (!imageCurrentOnly.value) return images.value
  return images.value.filter((img) => img.section === activeSection.value)
})

const filteredSections = computed(() => {
  const query = tocQuery.value.trim().toLowerCase()
  if (!query) return sections.value
  return sections.value.filter((item: any) => String(item.title || '').toLowerCase().includes(query))
})

function imageUrl(url: string) {
  const value = String(url || '').trim()
  if (!value) return ''
  if (value.startsWith('data:') || value.startsWith('http://') || value.startsWith('https://')) return value
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (value.startsWith('/') ? value : '/' + value)
}

function setSectionRef(index: number, el: any) {
  if (el?.$el) el = el.$el
  if (el instanceof HTMLElement) sectionEls.set(index, el)
}

function sectionBodyInfo(section: any) {
  const rawStart = Number(section.start || 0)
  let text = content.value.slice(rawStart, Number(section.end || 0))
  let start = rawStart
  if (!text) return { text: '', start }
  const firstBreak = text.indexOf('\n')
  if (firstBreak >= 0 && String(section.source || '') !== 'chunk') {
    const first = text.slice(0, firstBreak).replace(/^#+\s*/, '').trim()
    if (first && (first.includes(section.title) || String(section.title).includes(first))) {
      text = text.slice(firstBreak + 1)
      start += firstBreak + 1
    }
  }
  return { text, start }
}

function sectionBody(section: any) {
  return sectionBodyInfo(section).text
}

function sectionSegments(section: any) {
  const body = sectionBodyInfo(section)
  const text = body.text
  if (!text) return []
  const start = body.start
  if (!/【图\d+】/.test(text)) return [{ type: 'text', text, start, end: start + text.length }]
  const result: any[] = []
  const re = /【图(\d+)】/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      result.push({ type: 'text', text: text.slice(last, match.index), start: start + last, end: start + match.index })
    }
    const url = imageMap.value[match[1]] || ''
    if (url) {
      result.push({ type: 'image', url: imageUrl(url), start: start + match.index, end: start + match.index + match[0].length, seq: Number(match[1]) })
    } else {
      result.push({ type: 'text', text: match[0], start: start + match.index, end: start + match.index + match[0].length })
    }
    last = match.index + match[0].length
  }
  if (last < text.length) result.push({ type: 'text', text: text.slice(last), start: start + last, end: start + text.length })
  return result
}

function scrollRootTo(root: HTMLElement, top: number, smooth: boolean) {
  const max = Math.max(0, root.scrollHeight - root.clientHeight)
  const next = Math.max(0, Math.min(max, top))
  if (smooth) {
    root.scrollTo({ top: next, behavior: 'smooth' })
    return
  }
  // CSS 的 `scroll-behavior: smooth` 也会作用于 scrollTop 赋值；跳转索引时要立即到位，
  // 否则 5 秒高亮都过了一半，阅读器还在滚动动画里。
  const previous = root.style.scrollBehavior
  root.style.scrollBehavior = 'auto'
  root.scrollTop = next
  root.style.scrollBehavior = previous
}

function scrollElementToCenter(el: HTMLElement, smooth = true) {
  const root = readerScroll.value
  if (!root) return false
  const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop
    - Math.max(24, (root.clientHeight - Math.max(24, el.offsetHeight)) / 2)
  scrollRootTo(root, top, smooth)
  return true
}

function scrollToSection(index: number, smooth = true): boolean {
  const el = sectionEls.get(Number(index))
  const root = readerScroll.value
  if (!el || !root) return false
  const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 8
  scrollRootTo(root, top, smooth)
  activeSection.value = Number(index)
  persistPosition()
  return true
}

function scrollToOffset(offset: number, smooth = true): boolean {
  const target = Math.max(0, Math.min(content.value.length, Number(offset) || 0))
  const section = sections.value.find((item: any) => target >= Number(item.start) && target < Number(item.end))
  const root = readerScroll.value
  if (root) {
    const blocks = Array.from(root.querySelectorAll<HTMLElement>('[data-raw-start]'))
    const block = blocks.find((item) => {
      const start = Number(item.dataset.rawStart || 0)
      const end = Number(item.dataset.rawEnd || start + 1)
      return target >= start && target < end
    })
    if (block) {
      if (section) activeSection.value = Number(section.index)
      scrollElementToCenter(block, smooth)
      persistPosition()
      return true
    }
  }
  if (!section) return false
  return scrollToSection(section.index, smooth)
}

function scrollToImage(seq: number | null, smooth = true): boolean {
  if (seq == null) return false
  const root = readerScroll.value
  if (!root) return false
  const el = root.querySelector<HTMLElement>(`[data-image-seq="${Number(seq)}"]`)
  if (!el) return false
  const section = sections.value.find((item: any) => {
    const start = Number(el.dataset.rawStart || 0)
    return start >= Number(item.start) && start < Number(item.end)
  })
  if (section) activeSection.value = Number(section.index)
  scrollElementToCenter(el, smooth)
  flashReaderImage(el)
  persistPosition()
  return true
}

function flashReaderImage(el: HTMLElement) {
  if (imageFlashTimer) {
    clearTimeout(imageFlashTimer)
    imageFlashTimer = null
  }
  el.classList.remove('reader-jump-image')
  // 强制重排，重复点击同一张图也能重新触发静态高亮。
  void el.offsetWidth
  el.classList.add('reader-jump-image')
  imageFlashTimer = setTimeout(() => {
    el.classList.remove('reader-jump-image')
    imageFlashTimer = null
  }, 5000)
}

function highlightImageBySeq(seq: number | null) {
  if (seq == null) return
  const root = readerScroll.value
  if (!root) return
  const el = root.querySelector<HTMLElement>(`[data-image-seq="${Number(seq)}"]`)
  if (el) flashReaderImage(el)
}

function onContentScroll() {
  const root = readerScroll.value
  if (!root) return
  const top = root.getBoundingClientRect().top + 90
  let current = 0
  for (const [index, el] of sectionEls.entries()) {
    if (el.getBoundingClientRect().top <= top) current = index
  }
  activeSection.value = current
  persistPosition()
  if (selectionInfo.value) selectionInfo.value = null
}

function persistPosition() {
  if (!doc.value?.docId) return
  try {
    localStorage.setItem(`openstudy.reader.position.${doc.value.docId}`, String(readerScroll.value?.scrollTop || 0))
  } catch {
    // 忽略存储失败
  }
}

function restorePosition() {
  if (!doc.value?.docId) return
  try {
    const position = Number(localStorage.getItem(`openstudy.reader.position.${doc.value.docId}`) || 0)
    if (position > 0 && readerScroll.value) readerScroll.value.scrollTop = position
  } catch {
    // 忽略存储失败
  }
}

function toggleToc() {
  tocCollapsed.value = !tocCollapsed.value
}

function startSearch() {
  const query = searchInput.value.trim()
  searchOffsets.value = []
  searchIndex.value = 0
  if (!query) return
  const lower = content.value.toLowerCase()
  const needle = query.toLowerCase()
  let pos = 0
  while (pos < lower.length) {
    const found = lower.indexOf(needle, pos)
    if (found < 0) break
    searchOffsets.value.push(found)
    pos = found + Math.max(1, needle.length)
    if (searchOffsets.value.length >= 100) break
  }
  if (!searchOffsets.value.length) {
    ElMessage.info('正文中没有找到这个关键词')
    return
  }
  scrollToOffset(searchOffsets.value[0])
  nextTick(() => highlightSearch(query))
}

function nextSearch() {
  if (!searchOffsets.value.length) {
    startSearch()
    return
  }
  searchIndex.value = (searchIndex.value + 1) % searchOffsets.value.length
  scrollToOffset(searchOffsets.value[searchIndex.value])
}

function clearReaderMarks(root: HTMLElement, onlyJump = false) {
  const selector = onlyJump ? 'mark.reader-jump-highlight' : 'mark.reader-search-mark'
  root.querySelectorAll(selector).forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent || ''), mark)
    ;(parent as Element).normalize?.()
  })
}

/** 去掉 Markdown / 图片标记，得到阅读器 DOM 文本能匹配的候选行。 */
function jumpCandidates(query: string): string[] {
  const cleaned = String(query || '')
    .replace(/【图\d+】/g, '\n')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '\n')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*_`~#>]/g, '')
    .replace(/^\s*(?:[-+*]|\d+[.、])\s*/gm, '')
    .replace(/\u00a0/g, ' ')
    .replace(/\r/g, '')
  return Array.from(new Set(
    cleaned.split('\n')
      .map((line) => line.replace(/\s+/g, ' ').trim())
      .filter((line) => line.length >= 2)
  ))
}

function textIndex(root: HTMLElement) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const map: Array<{ node: Text; offset: number }> = []
  let text = ''
  let lastSpace = false
  let node: Node | null
  while ((node = walker.nextNode())) {
    const textNode = node as Text
    const parent = textNode.parentElement
    if (!parent || parent.closest('.katex, .katex-mathml, .katex-html, .reader-search-mark')) continue
    const value = textNode.nodeValue || ''
    for (let i = 0; i < value.length; i += 1) {
      let ch = value[i]
      if (ch === '\u00a0') ch = ' '
      if (/\s/.test(ch)) {
        if (lastSpace) continue
        text += ' '
        map.push({ node: textNode, offset: i })
        lastSpace = true
        continue
      }
      text += ch
      map.push({ node: textNode, offset: i })
      lastSpace = false
    }
  }
  return { text, map }
}

function findTextRange(root: HTMLElement, needle: string): Range | null {
  const target = String(needle || '').replace(/\s+/g, ' ').trim()
  if (target.length < 2) return null
  const { text, map } = textIndex(root)
  const start = text.indexOf(target)
  if (start < 0) return null
  const first = map[start]
  const last = map[start + target.length - 1]
  if (!first || !last) return null
  const range = document.createRange()
  range.setStart(first.node, first.offset)
  range.setEnd(last.node, last.offset + 1)
  return range
}

function wrapRange(range: Range): HTMLElement {
  const mark = document.createElement('mark')
  mark.className = 'reader-search-mark reader-jump-highlight'
  const fragment = range.extractContents()
  mark.appendChild(fragment)
  range.insertNode(mark)
  return mark
}

function scrollMarkToCenter(mark: HTMLElement | null, smooth = true) {
  const root = readerScroll.value
  if (!mark || !root) return
  const rect = mark.getBoundingClientRect()
  const rootRect = root.getBoundingClientRect()
  const top = root.scrollTop + (rect.top - rootRect.top) - (root.clientHeight - rect.height) / 2
  scrollRootTo(root, top, smooth)
}

/** 临时跳转高亮：把整个知识切片里的文本行一起标黄，而不是只标一行。 */
function highlightTemporary(query: string): HTMLElement | null {
  const root = readerScroll.value
  if (!root) return null
  const offset = pendingJumpOffset.value
  const section = offset == null
    ? null
    : sections.value.find((item: any) => offset >= Number(item.start) && offset < Number(item.end))
  const scope = section
    ? (root.querySelector<HTMLElement>(`.reader-section[data-section-index="${section.index}"]`) || root)
    : root
  const candidates = jumpCandidates(query)
  const marks: HTMLElement[] = []
  const seen = new Set<string>()
  for (const candidate of candidates) {
    if (seen.has(candidate)) continue
    const range = findTextRange(scope, candidate)
    if (range) {
      marks.push(wrapRange(range))
      seen.add(candidate)
      continue
    }
    // 整行被 Markdown 拆得过碎时，按分句/长词补标，保证整块切片尽量完整。
    const pieces = candidate.split(/[，。；：、\s]+/).map((item) => item.trim()).filter((item) => item.length >= 3)
      .sort((a, b) => b.length - a.length)
    for (const piece of pieces) {
      if (seen.has(piece)) continue
      const pieceRange = findTextRange(scope, piece)
      if (pieceRange) {
        marks.push(wrapRange(pieceRange))
        seen.add(piece)
        break
      }
    }
  }
  return marks[0] || null
}

function highlightSearch(query: string, temporary = false) {
  const root = readerScroll.value
  if (!root) return null
  if (searchMarkTimer) {
    clearTimeout(searchMarkTimer)
    searchMarkTimer = null
  }
  clearReaderMarks(root)
  if (!query) return null
  if (temporary) {
    return highlightTemporary(query)
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const nodes: Text[] = []
  let node: Node | null
  while ((node = walker.nextNode())) nodes.push(node as Text)
  for (const textNode of nodes) {
    const parent = textNode.parentElement
    if (!parent || parent.closest('.katex, .katex-mathml, .katex-html, .reader-search-mark')) continue
    let current: Text | null = textNode
    while (current?.nodeValue) {
      const found = current.nodeValue.toLowerCase().indexOf(query.toLowerCase())
      if (found < 0) break
      const match = current.splitText(found)
      const after = match.splitText(query.length)
      const mark = document.createElement('mark')
      mark.className = 'reader-search-mark'
      mark.textContent = match.nodeValue
      match.parentNode?.replaceChild(mark, match)
      current = after
    }
  }
  return null
}

function startTemporaryHighlightTimer() {
  const root = readerScroll.value
  if (!root) return
  if (searchMarkTimer) {
    clearTimeout(searchMarkTimer)
    searchMarkTimer = null
  }
  searchMarkTimer = setTimeout(() => {
    clearReaderMarks(root, true)
    searchMarkTimer = null
  }, 5000)
}

function copyImageMarkdown(image: any) {
  const text = `![${docName.value || '资料'}·${image.title}](${image.url})`
  navigator.clipboard?.writeText(text)
    .then(() => ElMessage.success('已复制图片 Markdown'))
    .catch(() => ElMessage.warning('复制失败，请打开图片后手动复制'))
}

function onContentMouseUp() {
  const selection = window.getSelection()
  const text = selection?.toString().trim() || ''
  if (!text || text.length < 2) {
    selectionInfo.value = null
    return
  }
  const range = selection?.rangeCount ? selection.getRangeAt(0) : null
  const root = readerRoot.value
  if (!range || !root) return
  const rect = range.getBoundingClientRect()
  const rootRect = root.getBoundingClientRect()
  const sectionEl = (range.startContainer.parentElement as HTMLElement | null)?.closest('.reader-section') as HTMLElement | null
  selectionInfo.value = {
    text: text.slice(0, 1500),
    x: Math.max(8, Math.min(rootRect.width - 260, rect.left - rootRect.left)),
    y: Math.max(8, rect.top - rootRect.top - 42),
    section: Number(sectionEl?.dataset.sectionIndex || 0)
  }
}

function clearSelection() {
  selectionInfo.value = null
  window.getSelection()?.removeAllRanges()
}

function askSelection(kind: 'ask' | 'practice' | 'note' | 'prescription') {
  if (!selectionInfo.value || !doc.value) return
  const title = sections.value.find((item: any) => item.index === selectionInfo.value?.section)?.title || docName.value
  const quote = selectionInfo.value.text
  const prompt = kind === 'practice'
    ? `请基于《${docName.value}》的「${title}」这段原文出 3 道练习题：\n\n${quote}\n\n请给出答案与解析，并标注来源。`
    : kind === 'note'
      ? `请把《${docName.value}》的「${title}」这段内容整理成一篇学习笔记：\n\n${quote}`
      : kind === 'prescription'
        ? `请把《${docName.value}》的「${title}」这段内容加入我的学习处方，并给出下一步练习建议：\n\n${quote}`
        : `请基于《${docName.value}》的「${title}」回答我的问题，并标注原文来源：\n\n${quote}`
  router.push({ path: '/front/agent/chat', state: { seedQuestion: prompt } })
  ElMessage.success('已把这段内容带入对话，确认后发送')
  clearSelection()
}

function copySelection() {
  if (!selectionInfo.value) return
  navigator.clipboard?.writeText(selectionInfo.value.text)
    .then(() => ElMessage.success('已复制原文'))
    .catch(() => ElMessage.warning('复制失败，请手动选择'))
  clearSelection()
}

function emitEdit() {
  if (doc.value) emit('edit', doc.value)
}

function openImages() {
  imagesVisible.value = true
}

async function openRelatedPages() {
  if (relatedLoading.value) return
  const sectionTitle = selectionInfo.value
    ? sections.value.find((item: any) => item.index === selectionInfo.value?.section)?.title
    : ''
  relatedVisible.value = true
  relatedLoading.value = true
  relatedPages.value = []
  try {
    const res = await listWikiPages({
      kbId: doc.value?.kbId,
      q: sectionTitle || docName.value,
      limit: 8
    })
    relatedPages.value = res.code === 200 ? (res.data?.pages || []) : []
  } catch {
    relatedPages.value = []
  } finally {
    relatedLoading.value = false
  }
}

async function rebuildOutline() {
  if (!doc.value?.docId || aiBuilding.value) return
  aiBuilding.value = true
  try {
    const res = await rebuildDocumentOutline(doc.value.docId)
    if (res.code !== 200) {
      ElMessage.error(res.msg || 'AI 目录整理失败')
      return
    }
    sections.value = res.data?.sections || sections.value
    needsAiOutline.value = sections.value.length <= 1 || sections.value.some((item: any) => item.source !== 'llm')
    activeSection.value = 0
    await nextTick()
    if (readerScroll.value) readerScroll.value.scrollTop = 0
    ElMessage.success(`AI 已整理出 ${sections.value.length} 个章节`)
  } catch (error: any) {
    ElMessage.error('AI 目录整理失败：' + (error?.message || error))
  } finally {
    aiBuilding.value = false
  }
}

function firstMeaningfulLine(text: string): string {
  return String(text || '')
    .split('\n')
    .map((line) => line.trim())
    .find((line) => line.length >= 4 && !line.startsWith('#')) || ''
}

function resolveTargetOffset(): number | null {
  if (targetOffset.value != null) return targetOffset.value
  const chunk = chunkStarts.value.find((item: any) => Number(item.chunkIndex) === Number(targetChunkIndex.value))
  const chunkStart = chunk?.start != null ? Number(chunk.start) : null
  const text = targetText.value
  if (text) {
    if (chunkStart != null) {
      let found = content.value.indexOf(text, chunkStart)
      if (found < 0) {
        const line = firstMeaningfulLine(text)
        if (line) found = content.value.indexOf(line, chunkStart)
      }
      if (found >= 0) return found
    }
    let found = content.value.indexOf(text)
    if (found < 0) {
      const line = firstMeaningfulLine(text)
      if (line) found = content.value.indexOf(line)
    }
    if (found >= 0) return found
  }
  return chunkStart
}

function recenterJumpTargets() {
  if (pendingJumpOffset.value != null) scrollToOffset(pendingJumpOffset.value, false)
  if (lastJumpMark?.isConnected) {
    scrollMarkToCenter(lastJumpMark, false)
  } else if (targetImageSeq.value != null) {
    scrollToImage(targetImageSeq.value, false)
  }
}

/** 图片加载会改变阅读器总高度；在跳转后的前 2.5 秒内按同一个目标反复校正。 */
function scheduleJumpRecenter() {
  jumpTimers.forEach((timer) => clearTimeout(timer))
  jumpTimers = []
  ;[0, 30, 80, 150, 300, 600, 1000, 1600, 2500].forEach((delay) => {
    jumpTimers.push(setTimeout(recenterJumpTargets, delay))
  })
}

function onReaderImageLoad() {
  if (pendingJumpOffset.value != null || lastJumpMark?.isConnected) recenterJumpTargets()
}

async function load(docValue: ReaderDoc, opts: ReaderOptions = {}) {
  doc.value = docValue
  docName.value = docValue.fileName || '未命名资料'
  tocCollapsed.value = opts.collapseToc === true
  loading.value = true
  content.value = ''
  sections.value = []
  imageMap.value = {}
  chunkStarts.value = []
  needsAiOutline.value = false
  targetOffset.value = opts.offset != null ? Number(opts.offset) : null
  targetText.value = String(opts.targetText || '')
  targetChunkIndex.value = opts.chunkIndex ?? null
  targetChunkCount.value = Number(opts.chunkCount || docValue.chunkCount || 0)
  const imageMatch = String(opts.targetText || '').match(/【图(\d+)】/)
  targetImageSeq.value = opts.targetImageSeq != null
    ? Number(opts.targetImageSeq)
    : (imageMatch ? Number(imageMatch[1]) : null)
  pendingJumpOffset.value = null
  lastJumpMark = null
  jumpTimers.forEach((timer) => clearTimeout(timer))
  jumpTimers = []
  stats.contentLength = 0
  activeSection.value = 0
  tocQuery.value = ''
  searchInput.value = ''
  searchOffsets.value = []
  sectionEls.clear()
  try {
    const [contentRes, outlineRes] = await Promise.all([
      getDocumentContent(docValue.docId),
      getDocumentOutline(docValue.docId)
    ])
    if (contentRes.code === 200) {
      const data = contentRes.data || {}
      content.value = data.content || ''
      imageMap.value = data.imageMap || {}
      chunkStarts.value = Array.isArray(data.chunkStarts) ? data.chunkStarts : []
      stats.contentLength = Number(data.contentLength || content.value.length || 0)
    }
    if (outlineRes.code === 200) {
      const data = outlineRes.data || {}
      sections.value = data.sections || []
      needsAiOutline.value = Boolean(data.needsAiOutline)
      if (!sections.value.length) {
        // 兼容旧后端：没有 sections 时用旧树展开成可点击章节。
        sections.value = flattenTree(data.tree)
      }
    }
    // 必须先结束 loading，v-if 的正文容器才会挂载；否则下面 scrollToOffset
    // 找不到 reader-main / sectionEls，定位会静默失败并停在最开头。
    loading.value = false
    await nextTick()
    const resolvedOffset = resolveTargetOffset()
    pendingJumpOffset.value = resolvedOffset
    let located = false
    if (resolvedOffset != null) {
      located = scrollToOffset(resolvedOffset, false)
    }
    if (!located) restorePosition()
    if (opts.highlight && opts.highlight.trim()) {
      await nextTick()
      lastJumpMark = highlightSearch(opts.highlight.trim(), opts.temporaryHighlight === true)
      if (lastJumpMark) {
        await nextTick()
        scrollMarkToCenter(lastJumpMark, true)
        // 从“用户真正看到已居中”开始算 5 秒，而不是从 mark 创建的那一帧开始。
        startTemporaryHighlightTimer()
      }
    }
    if (targetImageSeq.value != null && !lastJumpMark) {
      scrollToImage(targetImageSeq.value, false)
    } else if (targetImageSeq.value != null) {
      highlightImageBySeq(targetImageSeq.value)
    }
    if (pendingJumpOffset.value != null || lastJumpMark) scheduleJumpRecenter()
  } catch (error: any) {
    ElMessage.error('读取资料失败：' + (error?.message || error))
  } finally {
    loading.value = false
  }
}

function flattenTree(tree: any): any[] {
  if (!tree) return []
  const result: any[] = []
  const walk = (node: any, level: number) => {
    if (!node) return
    result.push({ index: result.length, title: String(node.name || '未命名章节'), level, start: 0, end: 0, source: 'rule' })
    for (const child of node.children || []) walk(child, level + 1)
  }
  walk(tree, 1)
  return result
}

onBeforeUnmount(() => {
  persistPosition()
  if (searchMarkTimer) {
    clearTimeout(searchMarkTimer)
    searchMarkTimer = null
  }
  if (imageFlashTimer) {
    clearTimeout(imageFlashTimer)
    imageFlashTimer = null
  }
  jumpTimers.forEach((timer) => clearTimeout(timer))
  jumpTimers = []
})

defineExpose({
  open: (docValue: ReaderDoc, opts?: ReaderOptions) => load(docValue, opts)
})
</script>

<style scoped>
.reader-panel { position: relative; display: flex; flex-direction: column; gap: 10px; min-height: 520px; }
.reader-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 0 2px 10px; border-bottom: 1px solid #edf0f5; }
.reader-toolbar__title { display: flex; min-width: 0; align-items: baseline; gap: 8px; }
.reader-toolbar__kicker { flex: none; color: #4f6bed; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.reader-toolbar__title b { overflow: hidden; color: #1f2937; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.reader-toolbar__tools { display: flex; flex: none; align-items: center; gap: 6px; }
.reader-search { width: 150px; }
.reader-search__count { color: #9aa1af; font-size: 10px; white-space: nowrap; }
.reader-stats { display: flex; gap: 16px; color: #9aa1af; font-size: 10px; }
.reader-stats b { color: #4f6bed; font-size: 12px; }
.reader-stats__ai { margin-left: auto; }
.reader-loading { min-height: 460px; }
.reader-body { display: grid; grid-template-columns: 240px minmax(0, 1fr); gap: 16px; min-height: 540px; }
.reader-body.is-toc-collapsed { grid-template-columns: 34px minmax(0, 1fr); }
.reader-toc { min-width: 0; border: 1px solid #e8edf5; border-radius: 9px; background: #fbfcfe; }
.reader-toc__head { display: flex; align-items: center; justify-content: space-between; padding: 10px 11px; border-bottom: 1px solid #edf0f5; color: #6b7280; font-size: 12px; font-weight: 600; }
.reader-toc__head button { border: 0; color: #9aa1af; background: transparent; cursor: pointer; font-size: 18px; line-height: 1; }
.reader-toc__search { margin: 8px; width: calc(100% - 16px); }
.reader-toc__list { max-height: 470px; padding: 2px 5px 8px; overflow: auto; }
.reader-toc__item { display: flex; width: 100%; align-items: center; gap: 6px; padding-top: 6px; padding-bottom: 6px; border: 0; border-left: 2px solid transparent; color: #697386; background: transparent; cursor: pointer; font-size: 11.5px; line-height: 1.45; text-align: left; }
.reader-toc__item:hover { color: #2f5fce; background: #f3f6fc; }
.reader-toc__item.is-active { border-left-color: #4f6bed; color: #2f5fce; background: #eef2ff; font-weight: 600; }
.reader-toc__dot { width: 3px; height: 3px; flex: none; border-radius: 50%; background: currentColor; opacity: .45; }
.reader-toc__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reader-toc__empty, .reader-toc__hint { padding: 8px 10px; color: #9aa1af; font-size: 10px; line-height: 1.6; }
.reader-toc__hint { margin-top: 4px; border-top: 1px dashed #e8edf5; }
.reader-main { min-width: 0; max-height: 600px; overflow: auto; scroll-behavior: smooth; border: 1px solid #e8edf5; border-radius: 9px; background: #fff; }
.reader-article { max-width: 820px; margin: 0 auto; padding: 28px 46px 60px; }
.reader-section { scroll-margin-top: 14px; }
.reader-section + .reader-section { margin-top: 26px; padding-top: 22px; border-top: 1px solid #f0f2f6; }
.reader-section__title { margin: 0 0 12px; color: #1f2937; font-size: 20px; line-height: 1.35; }
.reader-section__title--sub { font-size: 16px; }
.reader-text { color: #374151; font-size: 14px; line-height: 1.9; }
.reader-text :deep(.latex-content) { font-size: 14px; line-height: 1.9; }
.reader-image { margin: 14px 0; text-align: center; }
.reader-image :deep(.el-image) { max-width: 100%; max-height: 420px; border-radius: 6px; }
.reader-image-drawer__bar { display: flex; align-items: center; justify-content: space-between; padding: 0 2px 10px; color: #9aa1af; font-size: 11px; }
.reader-image-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.reader-image-card { overflow: hidden; border: 1px solid #e8edf5; border-radius: 7px; background: #fbfcfe; }
.reader-image-card :deep(.el-image) { display: block; width: 100%; height: 100px; cursor: pointer; }
.reader-image-card__foot { display: flex; align-items: center; justify-content: space-between; gap: 4px; padding: 5px 7px; color: #9aa1af; font-size: 10px; }
.reader-image-card__foot span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.reader-image-card__foot button { border: 0; color: #4f6bed; background: transparent; cursor: pointer; font-size: 10px; }
.reader-empty { padding: 30px 12px; color: #9aa1af; font-size: 12px; text-align: center; }
.reader-selection { position: absolute; z-index: 20; display: flex; gap: 2px; padding: 3px; border: 1px solid #dce4f2; border-radius: 7px; background: #fff; box-shadow: 0 4px 14px rgba(36, 61, 118, .13); }
.reader-selection button { padding: 4px 7px; border: 0; border-radius: 4px; color: #4b5563; background: transparent; cursor: pointer; font-size: 10px; white-space: nowrap; }
.reader-selection button:hover { color: #2f5fce; background: #eef2ff; }
.reader-related { min-height: 80px; }
.reader-related__item { padding: 10px 0; border-bottom: 1px solid #edf0f5; }
.reader-related__title { color: #1f2937; font-size: 13px; font-weight: 600; }
.reader-related__item p { margin: 5px 0; color: #6b7280; font-size: 11px; line-height: 1.6; }
.reader-related__item span { color: #9aa1af; font-size: 10px; }
.reader-search-mark { padding: 0 2px; border-radius: 2px; background: #fff3c4; color: inherit; }
.reader-search-mark.reader-jump-highlight {
  background: #ffe58f;
  box-shadow: 0 0 0 3px rgba(255, 214, 102, .28);
}
@media (max-width: 900px) { .reader-body { grid-template-columns: 1fr; } .reader-body.is-toc-collapsed { grid-template-columns: 1fr; } .reader-toc { max-height: 220px; } .reader-toc__list { max-height: 160px; } .reader-article { padding: 20px 20px 40px; } .reader-toolbar { align-items: flex-start; flex-direction: column; } .reader-toolbar__tools { flex-wrap: wrap; } }
</style>

<!--
  ⚠️ 不能放进上面的 scoped 块：`<mark>` 是 highlightSearch 运行时 createElement 出来的，
  不会带 Vue 的 `data-v-xxx` 作用域属性。scoped 的 `.reader-search-mark[data-v-xxx]`
  对动态节点不生效，浏览器只能用 `<mark>` 默认的纯黄色，背景/边框也不会按设计显示。
-->
<style>
.reader-search-mark { padding: 0 2px; border-radius: 2px; background: #fff3c4; color: inherit; }
.reader-search-mark.reader-jump-highlight {
  background: #ffe58f;
  box-shadow: 0 0 0 3px rgba(255, 214, 102, .28);
}
.reader-image.reader-jump-image {
  border-radius: 8px;
  box-shadow: 0 0 0 4px rgba(255, 214, 102, .34);
}
</style>
