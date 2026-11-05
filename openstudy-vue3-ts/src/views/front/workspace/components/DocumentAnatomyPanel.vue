<!--
  单份资料的「资料刨析」查看器
  ----------------------------------------------------------------------------
  从 workspace/index.vue 抽出的共享组件：我的资料页、设置面板的「我的资料」
  tab、以及资料夹面板里的「资料刨析」入口都复用这一份页面，避免两套结构树/
  正文/图片资产的展示逻辑逐渐分叉。

  入口行为：
    · `open(doc, opts)`：加载正文、章节树、图片资产并打开弹窗；
    · 可选 `showEdit`：显示「编辑」按钮，点击后向调用方抛 `edit` 事件；
    · `highlight` / `targetText` / `chunkIndex`：语义检索命中后定位并标黄。
-->
<template>
  <div class="kbp-anatomy-shell">
    <div class="kbp-anatomy-panel">
      <div ref="mainBodyRef" v-loading="loading" class="kbp-anatomy">
      <div class="kbp-anatomy__stats">
        <span><b>{{ stats.contentLength }}</b> 字</span>
        <span><b>{{ stats.imageCount }}</b> 张图</span>
        <span><b>{{ stats.headingCount }}</b> 个标题</span>
        <span><b>{{ stats.chunkCount }}</b> 个分块</span>
        <el-button v-if="props.showEdit && doc" text type="primary" size="small" class="kbp-anatomy__edit"
          @click="emitEdit">编辑</el-button>
      </div>

      <div class="kbp-anatomy__grid">
        <section class="kbp-anatomy__outline">
          <h4>资料结构</h4>
          <div v-if="questionGroups.length" class="kbp-anatomy__question-groups">
            <div class="kbp-anatomy__question-groups-label">按题型整理</div>
            <div v-for="group in questionGroups" :key="group.name" class="kbp-anatomy__question-group"
              @click="jumpToQuestionGroup(group)">
              <span>{{ group.name }}</span>
              <b>{{ group.count }} 题</b>
            </div>
          </div>
          <div v-if="outlineItems.length" class="kbp-anatomy__outline-list">
            <div v-for="(item, idx) in outlineItems" :key="idx" class="kbp-anatomy__outline-item"
              :style="{ paddingLeft: `${12 + item.level * 14}px` }">
              {{ item.name }}
            </div>
          </div>
          <div v-else-if="!questionGroups.length" class="kbp-anatomy__empty">
            {{ outlineReason || '这份资料没有可提取的章节结构。' }}
          </div>
        </section>

        <section class="kbp-anatomy__content">
          <h4 class="kbp-anatomy__content-head">
            <span>正文与图片</span>
            <button type="button" class="kbp-anatomy__fullscreen" title="全屏查看正文与图片"
              @click="openFullscreen">全屏观看</button>
          </h4>
          <div v-if="segments.length" class="kbp-anatomy__content-inner">
            <template v-for="(seg, si) in segments" :key="si">
              <div v-if="seg.type === 'image'" class="kbp-anatomy__segment"
                :data-raw-start="seg.start" :data-raw-end="seg.end">
                <el-image :src="seg.url" fit="contain" class="kbp-anatomy__inline-image"
                  :preview-src-list="[seg.url]" preview-teleported @load="onImageLoad" />
              </div>
              <div v-else class="kbp-anatomy__segment" :data-raw-start="seg.start" :data-raw-end="seg.end">
                <LatexRenderer :content="seg.text" class="kbp-anatomy__rendered" />
              </div>
            </template>
          </div>
          <div v-else class="kbp-anatomy__empty">没有可展示的正文，可能还在解析中。</div>
        </section>

        <section class="kbp-anatomy__assets">
          <h4>图片资产 <span>{{ images.length }}</span></h4>
          <div v-if="images.length" class="kbp-anatomy__image-grid">
            <div v-for="(img, idx) in images" :key="img.key" class="kbp-anatomy__image-card">
              <el-image :src="img.url" fit="cover" :preview-src-list="[img.url]" preview-teleported />
              <span>图 {{ idx + 1 }}</span>
              <button type="button" class="kbp-anatomy__copy" @click="copyImageMarkdown(img.url, idx + 1)">
                复制
              </button>
            </div>
          </div>
          <div v-else class="kbp-anatomy__empty">这份资料里没有提取到图片。</div>
        </section>
      </div>
    </div>
    </div>

  <el-dialog v-model="fullscreenVisible" :title="`资料正文 · ${docName}`" fullscreen append-to-body
    class="kbp-anatomy-fullscreen-dialog">
    <div ref="fullscreenBodyRef" class="kbp-anatomy-fullscreen__body">
      <template v-if="segments.length">
        <template v-for="(seg, si) in segments" :key="`full-${si}`">
          <div v-if="seg.type === 'image'" class="kbp-anatomy__segment"
            :data-raw-start="seg.start" :data-raw-end="seg.end">
            <el-image :src="seg.url" fit="contain" class="kbp-anatomy__inline-image"
              :preview-src-list="[seg.url]" preview-teleported />
          </div>
          <div v-else class="kbp-anatomy__segment" :data-raw-start="seg.start" :data-raw-end="seg.end">
            <LatexRenderer :content="seg.text" class="kbp-anatomy__rendered" />
          </div>
        </template>
      </template>
      <div v-else class="kbp-anatomy__empty">没有可展示的正文，可能还在解析中。</div>
    </div>
  </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import LatexRenderer from '@/components/LatexRenderer/LatexRenderer.vue'
import { getDocumentContent, getDocumentOutline } from '@/api/ai/rag'

defineOptions({ name: 'DocumentAnatomyPanel' })

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
  /** 原文精确字符偏移（体检章节定位用），优先级高于 targetText */
  offset?: number
}

const props = withDefaults(
  defineProps<{
    showEdit?: boolean
  }>(),
  { showEdit: false }
)

const emit = defineEmits<{
  (e: 'edit', doc: AnatomyDoc): void
}>()

const visible = ref(false)
const fullscreenVisible = ref(false)
const loading = ref(false)
const mainBodyRef = ref<HTMLElement | null>(null)
const fullscreenBodyRef = ref<HTMLElement | null>(null)
const doc = ref<AnatomyDoc | null>(null)
const docName = ref('')
const content = ref('')
const highlight = ref('')
const targetChunkId = ref<number | null>(null)
const targetChunkIndex = ref<number | null>(null)
const targetChunkCount = ref(0)
const targetText = ref('')
const scrollTargetOffset = ref<number | null>(null)
const excludedRanges = ref<any[]>([])
const imageMap = ref<Record<string, string>>({})
const tree = ref<any>(null)
const outlineReason = ref('')
const stats = reactive({
  contentLength: 0,
  imageCount: 0,
  headingCount: 0,
  chunkCount: 0
})

function imageUrl(url: string): string {
  const v = String(url || '').trim()
  if (!v) return ''
  if (v.startsWith('data:') || v.startsWith('http://') || v.startsWith('https://')) return v
  const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
  return base + (v.startsWith('/') ? v : '/' + v)
}

async function copyImageMarkdown(url: string, seq: number) {
  if (!url) return
  const alt = `${docName.value || '资料'}·图${seq}`
  const text = `![${alt}](${url})`
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const input = document.createElement('textarea')
      input.value = text
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
    }
    ElMessage.success('已复制图片 Markdown')
  } catch {
    ElMessage.warning('复制失败，请打开图片后手动复制')
  }
}

const images = computed(() =>
  Object.entries(imageMap.value)
    .map(([key, url]) => ({ key, url: imageUrl(url) }))
    .filter((x) => !!x.url)
)

const outlineItems = computed(() => {
  const out: Array<{ name: string; level: number }> = []
  const walk = (node: any, level: number) => {
    if (!node || out.length >= 80) return
    out.push({ name: String(node.name || '未命名'), level })
    for (const child of node.children || []) walk(child, level + 1)
  }
  if (tree.value) walk(tree.value, 0)
  return out
})

const questionGroups = computed(() => {
  const text = content.value
  if (!text) return []
  const re = /^\s*(\d+)[.、]\s*[［\[]?(单选题|多选题|填空题|简答题|判断题|选择题|计算题|论述题)[\]\]]?/gm
  const groups = new Map<string, { name: string; count: number; first: number }>()
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const name = m[2]
    const no = Number(m[1])
    const item = groups.get(name)
    if (item) item.count += 1
    else groups.set(name, { name, count: 1, first: no })
  }
  return [...groups.values()]
})

function contentElement(root: HTMLElement | null): HTMLElement | null {
  if (!root) return null
  return (root.querySelector('.kbp-anatomy__content-inner') as HTMLElement | null) || root
}

function scrollToOffset(offset: number): boolean {
  const el = contentElement(mainBodyRef.value)
  if (!el) return false
  const blocks = [...el.querySelectorAll<HTMLElement>('[data-raw-start]')]
  if (!blocks.length) return false
  const targetOffset = Math.max(0, Math.min(content.value.length, Number(offset) || 0))
  scrollTargetOffset.value = targetOffset
  let target = blocks.find((block) => {
    const start = Number(block.dataset.rawStart || 0)
    const end = Number(block.dataset.rawEnd || start)
    return targetOffset >= start && targetOffset < end
  })
  if (!target) target = blocks[blocks.length - 1]
  const top = target.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop
  el.scrollTop = Math.max(0, top - el.clientHeight * 0.18)
  return true
}

function onImageLoad() {
  const offset = scrollTargetOffset.value
  if (offset == null) return
  nextTick(() => scrollToOffset(offset))
}

function jumpToQuestionGroup(group: { first: number }) {
  const match = new RegExp(`^\\s*${Number(group.first)}[.、]`, 'm').exec(content.value)
  if (!match) return
  scrollToOffset(match.index)
}

function isExcluded(start: number, end: number): boolean {
  return excludedRanges.value.some((range: any) => {
    const rs = Number(range?.start)
    const re = Number(range?.end)
    return Number.isFinite(rs) && Number.isFinite(re) && rs < end && re > start
  })
}

function blankExcludedText(text: string, start: number, end: number): string {
  if (!excludedRanges.value.length) return text
  let out = text
  for (const range of excludedRanges.value) {
    const rs = Number(range?.start)
    const re = Number(range?.end)
    if (!Number.isFinite(rs) || !Number.isFinite(re) || re <= start || rs >= end) continue
    const from = Math.max(0, rs - start)
    const to = Math.min(out.length, re - start)
    if (to > from) out = out.slice(0, from) + ' '.repeat(to - from) + out.slice(to)
  }
  return out
}

const segments = computed(() => {
  const text = content.value
  if (!text) return []
  if (!/【图\d+】/.test(text)) {
    return [{ type: 'text', text: blankExcludedText(text, 0, text.length), start: 0, end: text.length }]
  }
  const segs: any[] = []
  const re = /【图(\d+)】/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      segs.push({
        type: 'text',
        text: blankExcludedText(text.slice(last, m.index), last, m.index),
        start: last,
        end: m.index
      })
    }
    if (isExcluded(m.index, m.index + m[0].length)) {
      last = m.index + m[0].length
      continue
    }
    const url = imageMap.value[m[1]] || ''
    if (url) {
      segs.push({ type: 'image', url: imageUrl(url), start: m.index, end: m.index + m[0].length })
    } else {
      segs.push({ type: 'text', text: m[0], start: m.index, end: m.index + m[0].length })
    }
    last = m.index + m[0].length
  }
  if (last < text.length) {
    segs.push({
      type: 'text',
      text: blankExcludedText(text.slice(last), last, text.length),
      start: last,
      end: text.length
    })
  }
  return segs
})

function clearMarks(root: HTMLElement) {
  root.querySelectorAll('mark.kbp-search-mark').forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent || ''), mark)
    ;(parent as Element).normalize?.()
  })
}

function applyHighlight() {
  const roots = [mainBodyRef.value, fullscreenBodyRef.value].filter(Boolean) as HTMLElement[]
  roots.forEach(clearMarks)
  const phrase = highlight.value.trim()
  if (!phrase) return
  const needle = phrase.toLowerCase()
  for (const root of roots) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    const nodes: Node[] = []
    let node: Node | null
    while ((node = walker.nextNode())) nodes.push(node)
    for (const textNode of nodes) {
      const parent = textNode.parentElement
      if (!parent || parent.closest('.katex, .katex-mathml, .katex-html, .latex-error, .kbp-search-mark')) continue
      let current: Text | null = textNode as Text
      while (current && current.nodeValue) {
        const idx = current.nodeValue.toLowerCase().indexOf(needle)
        if (idx < 0) break
        const matchNode = current.splitText(idx)
        const afterNode = matchNode.splitText(needle.length)
        const mark = document.createElement('mark')
        mark.className = 'kbp-search-mark'
        mark.textContent = matchNode.nodeValue
        matchNode.parentNode?.replaceChild(mark, matchNode)
        current = afterNode
      }
    }
  }

  const rawTarget = targetText.value.trim()
  const target = rawTarget.replace(/【图\d+】/g, '').trim()
  const source = content.value || ''
  let targetOffset: number | null = null
  if (source) {
    let idx = rawTarget ? source.indexOf(rawTarget) : -1
    if (idx < 0 && target) idx = source.indexOf(target)
    if (idx < 0 && target) idx = source.indexOf(target.slice(0, Math.min(80, target.length)))
    if (idx < 0 && target) idx = source.indexOf(target.slice(0, 30))
    if (idx >= 0) targetOffset = idx
  }

  if (targetOffset != null && scrollToOffset(targetOffset)) return
  const totalChunks = targetChunkCount.value || stats.chunkCount
  if (targetOffset == null && targetChunkIndex.value != null && totalChunks > 0 && source) {
    const estimated = source.length * ((Number(targetChunkIndex.value) + 0.5) / totalChunks)
    if (scrollToOffset(estimated)) return
  }
  const first = mainBodyRef.value?.querySelector('mark.kbp-search-mark') as HTMLElement | null
  first?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

async function openFullscreen() {
  fullscreenVisible.value = true
  await nextTick()
  applyHighlight()
}

function emitEdit() {
  if (doc.value) emit('edit', doc.value)
}

async function load(docValue: AnatomyDoc, opts: AnatomyOptions = {}) {
  visible.value = true
  loading.value = true
  fullscreenVisible.value = false
  doc.value = docValue
  docName.value = docValue.fileName || '未命名资料'
  highlight.value = String(opts.highlight || '')
  targetChunkId.value = opts.chunkId ?? null
  targetChunkIndex.value = opts.chunkIndex ?? null
  targetChunkCount.value = Number(opts.chunkCount || docValue.chunkCount || 0)
  targetText.value = String(opts.targetText || '')
  scrollTargetOffset.value = opts.offset != null ? Number(opts.offset) : null
  content.value = ''
  excludedRanges.value = []
  imageMap.value = {}
  tree.value = null
  outlineReason.value = ''
  stats.contentLength = 0
  stats.imageCount = 0
  stats.headingCount = 0
  stats.chunkCount = Number(opts.chunkCount || docValue.chunkCount || 0)

  try {
    const [contentRes, outlineRes] = await Promise.all([
      getDocumentContent(docValue.docId),
      getDocumentOutline(docValue.docId)
    ])
    if (contentRes.code === 200) {
      const data = contentRes.data || {}
      content.value = data.content || ''
      excludedRanges.value = data.excludedRanges || []
      imageMap.value = data.imageMap || {}
      stats.contentLength = Number(data.contentLength || content.value.length || 0)
      stats.imageCount = Object.keys(imageMap.value).length
    }
    if (outlineRes.code === 200) {
      const data = outlineRes.data || {}
      if (data.hasOutline && data.tree) {
        tree.value = data.tree
        stats.headingCount = Number(data.totalHeadings || data.count || 0)
      } else {
        outlineReason.value = data.reason || '这份资料没有可提取的章节结构。'
      }
    }
  } catch (e: any) {
    ElMessage.error('读取资料刨析失败：' + (e?.message || e))
  } finally {
    loading.value = false
    await nextTick()
    // 体检章节用精确偏移定位；此时内容已渲染，直接滚到对应位置。
    if (scrollTargetOffset.value != null) scrollToOffset(scrollTargetOffset.value)
    applyHighlight()
  }
}

defineExpose({
  open: (docValue: AnatomyDoc, opts?: AnatomyOptions) => load(docValue, opts)
})
</script>

<style scoped>
.kbp-anatomy__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-right: 28px;
  font-size: 16px;
  font-weight: 600;
  color: var(--os-text-1, #111827);
}

.kbp-anatomy__edit {
  margin-left: auto;
}

.kbp-anatomy {
  min-height: 420px;
}

.kbp-anatomy__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 8px;
  background: var(--os-surface-2, #f8fafc);
  color: var(--os-text-3, #6b7280);
  font-size: 12px;
}

.kbp-anatomy__stats b {
  color: var(--os-text-1, #111827);
  font-size: 15px;
}

.kbp-anatomy__grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(320px, 1.4fr) minmax(220px, 0.7fr);
  gap: 14px;
  min-height: 480px;
}

.kbp-anatomy__outline,
.kbp-anatomy__content,
.kbp-anatomy__assets {
  min-width: 0;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.kbp-anatomy__outline h4,
.kbp-anatomy__content h4,
.kbp-anatomy__assets h4 {
  margin: 0;
  padding: 10px 12px;
  border-bottom: 1px solid var(--os-border, #e5e7eb);
  font-size: 13px;
  color: var(--os-text-1, #111827);
}

.kbp-anatomy__assets h4 span {
  color: var(--os-text-3, #9ca3af);
  font-weight: 400;
}

.kbp-anatomy__outline-list {
  max-height: 540px;
  padding: 8px 0;
  overflow: auto;
}

.kbp-anatomy__question-groups {
  padding: 10px 12px;
  border-bottom: 1px solid var(--os-border, #e5e7eb);
  background: #f8fafc;
}

.kbp-anatomy__question-groups-label {
  margin-bottom: 6px;
  color: var(--os-text-3, #6b7280);
  font-size: 11px;
}

.kbp-anatomy__question-group {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 7px;
  border-radius: 4px;
  color: var(--os-text-2, #4b5563);
  font-size: 12.5px;
  cursor: pointer;
}

.kbp-anatomy__question-group:hover {
  background: #eff6ff;
  color: var(--os-primary, #2563eb);
}

.kbp-anatomy__question-group b {
  color: var(--os-primary, #2563eb);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.kbp-anatomy__outline-item {
  padding-top: 5px;
  padding-bottom: 5px;
  padding-right: 10px;
  border-left: 2px solid transparent;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--os-text-2, #4b5563);
  word-break: break-word;
}

.kbp-anatomy__outline-item:hover {
  border-left-color: var(--os-primary, #2563eb);
  background: var(--os-surface-2, #f8fafc);
}

.kbp-anatomy__content-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.kbp-anatomy__fullscreen {
  padding: 2px 7px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 4px;
  background: #fff;
  color: var(--os-primary, #2563eb);
  cursor: pointer;
  font-size: 11px;
}

.kbp-anatomy__fullscreen:hover {
  border-color: var(--os-primary, #2563eb);
  background: #eff6ff;
}

.kbp-anatomy-fullscreen__body {
  height: calc(100vh - 116px);
  padding: 24px max(24px, calc((100vw - 980px) / 2));
  overflow: auto;
  background: #fff;
  font-size: 15px;
  line-height: 1.8;
}

.kbp-anatomy-fullscreen__body .kbp-anatomy__inline-image {
  max-height: 75vh;
}

.kbp-anatomy-fullscreen__body .kbp-anatomy__rendered {
  font-size: 15px;
}

.kbp-anatomy__content-inner {
  max-height: 540px;
  padding: 12px;
  overflow: auto;
}

.kbp-anatomy__rendered {
  margin-bottom: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-2, #4b5563);
}

.kbp-anatomy__rendered :deep(.latex-content) {
  font-size: inherit;
}

.kbp-anatomy__content-inner :deep(mark.kbp-search-mark),
.kbp-anatomy-fullscreen__body :deep(mark.kbp-search-mark) {
  padding: 0 2px;
  border-radius: 2px;
  background: #fff3c4;
  color: inherit;
}

.kbp-anatomy__inline-image {
  display: block;
  max-width: 100%;
  max-height: 320px;
  margin: 8px auto 12px;
  border-radius: 6px;
}

.kbp-anatomy__image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 8px;
  max-height: 540px;
  padding: 12px;
  overflow: auto;
}

.kbp-anatomy__image-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 4px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 6px;
}

.kbp-anatomy__image-card .el-image {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 4px;
  background: #f3f4f6;
}

.kbp-anatomy__image-card span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: var(--os-text-3, #6b7280);
}

.kbp-anatomy__copy {
  padding: 3px 6px;
  border: 1px solid var(--os-border, #e5e7eb);
  border-radius: 4px;
  background: #fff;
  color: var(--os-text-3, #6b7280);
  font-size: 11px;
  cursor: pointer;
}

.kbp-anatomy__copy:hover {
  border-color: var(--os-primary, #2563eb);
  color: var(--os-primary, #2563eb);
}

.kbp-anatomy__empty {
  padding: 18px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #9ca3af);
}

@media (max-width: 900px) {
  .kbp-anatomy__grid {
    grid-template-columns: 1fr;
  }

  .kbp-anatomy__content-inner,
  .kbp-anatomy__image-grid {
    max-height: 40vh;
  }
}
</style>
