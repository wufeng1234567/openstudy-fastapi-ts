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
              <div v-if="seg.type === 'image'" class="reader-image">
                <el-image :src="seg.url" fit="contain" :preview-src-list="[seg.url]" preview-teleported />
              </div>
              <LatexRenderer v-else :content="seg.text" class="reader-text" />
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
      <button type="button" @click="copySelection">复制原文</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import {
  getDocumentContent,
  getDocumentOutline,
  rebuildDocumentOutline
} from '@/api/ai/rag'

defineOptions({ name: 'DocumentAnatomyPanel' })

interface ReaderDoc {
  docId: number
  fileName?: string
  chunkCount?: number
}

interface ReaderOptions {
  highlight?: string
  chunkId?: number
  chunkIndex?: number
  chunkCount?: number
  targetText?: string
  offset?: number
}

const props = withDefaults(defineProps<{ showEdit?: boolean }>(), { showEdit: false })
const emit = defineEmits<{
  (e: 'edit', doc: ReaderDoc): void
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
const activeSection = ref(0)
const tocCollapsed = ref(false)
const tocQuery = ref('')
const searchInput = ref('')
const searchIndex = ref(0)
const searchOffsets = ref<number[]>([])
const searchCount = computed(() => searchOffsets.value.length)
const imagesVisible = ref(false)
const imageCurrentOnly = ref(false)
const selectionInfo = ref<{ text: string; x: number; y: number; section: number } | null>(null)
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

function sectionBody(section: any) {
  let text = content.value.slice(Number(section.start || 0), Number(section.end || 0))
  if (!text) return ''
  const firstBreak = text.indexOf('\n')
  if (firstBreak >= 0 && String(section.source || '') !== 'chunk') {
    const first = text.slice(0, firstBreak).replace(/^#+\s*/, '').trim()
    if (first && (first.includes(section.title) || String(section.title).includes(first))) {
      text = text.slice(firstBreak + 1)
    }
  }
  return text
}

function sectionSegments(section: any) {
  const text = sectionBody(section)
  if (!text) return []
  const start = Number(section.start || 0)
  if (!/【图\d+】/.test(text)) return [{ type: 'text', text, start }]
  const result: any[] = []
  const re = /【图(\d+)】/g
  let last = 0
  let match: RegExpExecArray | null
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      result.push({ type: 'text', text: text.slice(last, match.index), start: start + last })
    }
    const url = imageMap.value[match[1]] || ''
    if (url) {
      result.push({ type: 'image', url: imageUrl(url), start: start + match.index })
    } else {
      result.push({ type: 'text', text: match[0], start: start + match.index })
    }
    last = match.index + match[0].length
  }
  if (last < text.length) result.push({ type: 'text', text: text.slice(last), start: start + last })
  return result
}

function scrollToSection(index: number) {
  const el = sectionEls.get(Number(index))
  const root = readerScroll.value
  if (!el || !root) return
  const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top + root.scrollTop - 8
  root.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
  activeSection.value = Number(index)
  persistPosition()
}

function scrollToOffset(offset: number) {
  const target = Math.max(0, Math.min(content.value.length, Number(offset) || 0))
  const section = sections.value.find((item: any) => target >= Number(item.start) && target < Number(item.end))
  if (section) scrollToSection(section.index)
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

function highlightSearch(query: string) {
  const root = readerScroll.value
  if (!root) return
  root.querySelectorAll('mark.reader-search-mark').forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent || ''), mark)
    ;(parent as Element).normalize?.()
  })
  if (!query) return
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

async function load(docValue: ReaderDoc, opts: ReaderOptions = {}) {
  doc.value = docValue
  docName.value = docValue.fileName || '未命名资料'
  loading.value = true
  content.value = ''
  sections.value = []
  imageMap.value = {}
  needsAiOutline.value = false
  targetOffset.value = opts.offset != null ? Number(opts.offset) : null
  targetText.value = String(opts.targetText || '')
  targetChunkIndex.value = opts.chunkIndex ?? null
  targetChunkCount.value = Number(opts.chunkCount || docValue.chunkCount || 0)
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
    await nextTick()
    if (targetOffset.value != null) {
      scrollToOffset(targetOffset.value)
    } else if (targetText.value) {
      const found = content.value.indexOf(targetText.value)
      if (found >= 0) scrollToOffset(found)
      else restorePosition()
    } else {
      restorePosition()
    }
    if (opts.highlight && opts.highlight.trim()) {
      await nextTick()
      highlightSearch(opts.highlight.trim())
    }
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
.reader-search-mark { padding: 0 2px; border-radius: 2px; background: #fff3c4; color: inherit; }
@media (max-width: 900px) { .reader-body { grid-template-columns: 1fr; } .reader-body.is-toc-collapsed { grid-template-columns: 1fr; } .reader-toc { max-height: 220px; } .reader-toc__list { max-height: 160px; } .reader-article { padding: 20px 20px 40px; } .reader-toolbar { align-items: flex-start; flex-direction: column; } .reader-toolbar__tools { flex-wrap: wrap; } }
</style>
