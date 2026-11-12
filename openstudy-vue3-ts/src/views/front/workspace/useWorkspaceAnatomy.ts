import { computed, nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

/** 单文档刨析（Document Anatomy）的状态、位置锚点和图文分段。 */
export function useWorkspaceAnatomy() {
  const anatomyVisible = ref(false)
  const anatomyLoading = ref(false)
  const anatomyFullscreen = ref(false)
  const anatomyDocName = ref('')
  const anatomyContent = ref('')
  const anatomyHighlight = ref('')
  const anatomyTargetChunkId = ref<number | null>(null)
  const anatomyTargetChunkIndex = ref<number | null>(null)
  const anatomyTargetChunkCount = ref(0)
  const anatomyTargetText = ref('')
  const anatomyScrollTargetOffset = ref<number | null>(null)
  const anatomyExcludedRanges = ref<any[]>([])
  const anatomyImageMap = ref<Record<string, string>>({})
  const anatomyTree = ref<any>(null)
  const anatomyOutlineReason = ref('')
  const anatomyStats = reactive({
    contentLength: 0,
    imageCount: 0,
    headingCount: 0,
    chunkCount: 0
  })

  function anatomyImageUrl(url: string): string {
    const v = String(url || '').trim()
    if (!v) return ''
    if (v.startsWith('data:') || v.startsWith('http://') || v.startsWith('https://')) return v
    const base = (import.meta.env.VITE_APP_BASE_API || '').replace(/\/$/, '')
    return base + (v.startsWith('/') ? v : '/' + v)
  }

  async function copyImageMarkdown(url: string, docName: string, seq: number) {
    if (!url) return
    const alt = `${docName || '资料'}·图${seq}`
    const text = `![${alt}](${url})`
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
      else {
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

  const anatomyImages = computed(() =>
    Object.entries(anatomyImageMap.value)
      .map(([key, url]) => ({ key, url: anatomyImageUrl(url) }))
      .filter((x) => !!x.url)
  )

  const anatomyOutlineItems = computed(() => {
    const out: Array<{ name: string; level: number }> = []
    const walk = (node: any, level: number) => {
      if (!node || out.length >= 80) return
      out.push({ name: String(node.name || '未命名'), level })
      for (const child of node.children || []) walk(child, level + 1)
    }
    if (anatomyTree.value) walk(anatomyTree.value, 0)
    return out
  })

  const anatomyQuestionGroups = computed(() => {
    const text = anatomyContent.value
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

  function scrollAnatomyToOffset(offset: number): boolean {
    const content = document.querySelector('.kbp-anatomy__content-inner') as HTMLElement | null
    if (!content) return false
    const blocks = [...content.querySelectorAll<HTMLElement>('[data-raw-start]')]
    if (!blocks.length) return false
    const targetOffset = Math.max(0, Math.min(anatomyContent.value.length, Number(offset) || 0))
    anatomyScrollTargetOffset.value = targetOffset
    let target = blocks.find((block) => {
      const start = Number(block.dataset.rawStart || 0)
      const end = Number(block.dataset.rawEnd || start)
      return targetOffset >= start && targetOffset < end
    })
    if (!target) target = blocks[blocks.length - 1]
    const top = target.getBoundingClientRect().top - content.getBoundingClientRect().top + content.scrollTop
    content.scrollTop = Math.max(0, top - content.clientHeight * 0.18)
    return true
  }

  function onAnatomyImageLoad() {
    const offset = anatomyScrollTargetOffset.value
    if (offset == null) return
    nextTick(() => scrollAnatomyToOffset(offset))
  }

  function jumpToQuestionGroup(group: { first: number }) {
    const match = new RegExp(`^\\s*${Number(group.first)}[.、]`, 'm').exec(anatomyContent.value)
    if (!match) return
    scrollAnatomyToOffset(match.index)
  }

  function isAnatomyExcluded(start: number, end: number): boolean {
    return anatomyExcludedRanges.value.some((range: any) => {
      const rs = Number(range?.start)
      const re = Number(range?.end)
      return Number.isFinite(rs) && Number.isFinite(re) && rs < end && re > start
    })
  }

  function blankExcludedText(text: string, start: number, end: number): string {
    if (!anatomyExcludedRanges.value.length) return text
    let out = text
    for (const range of anatomyExcludedRanges.value) {
      const rs = Number(range?.start)
      const re = Number(range?.end)
      if (!Number.isFinite(rs) || !Number.isFinite(re) || re <= start || rs >= end) continue
      const from = Math.max(0, rs - start)
      const to = Math.min(out.length, re - start)
      if (to > from) out = out.slice(0, from) + ' '.repeat(to - from) + out.slice(to)
    }
    return out
  }

  const anatomySegments = computed(() => {
    const text = anatomyContent.value
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
        segs.push({ type: 'text', text: blankExcludedText(text.slice(last, m.index), last, m.index), start: last, end: m.index })
      }
      if (isAnatomyExcluded(m.index, m.index + m[0].length)) {
        last = m.index + m[0].length
        continue
      }
      const url = anatomyImageMap.value[m[1]] || ''
      if (url) segs.push({ type: 'image', url: anatomyImageUrl(url), start: m.index, end: m.index + m[0].length })
      else segs.push({ type: 'text', text: m[0], start: m.index, end: m.index + m[0].length })
      last = m.index + m[0].length
    }
    if (last < text.length) {
      segs.push({ type: 'text', text: blankExcludedText(text.slice(last), last, text.length), start: last, end: text.length })
    }
    return segs
  })

  return {
    anatomyVisible,
    anatomyLoading,
    anatomyFullscreen,
    anatomyDocName,
    anatomyContent,
    anatomyHighlight,
    anatomyTargetChunkId,
    anatomyTargetChunkIndex,
    anatomyTargetChunkCount,
    anatomyTargetText,
    anatomyScrollTargetOffset,
    anatomyExcludedRanges,
    anatomyImageMap,
    anatomyTree,
    anatomyOutlineReason,
    anatomyStats,
    anatomyImageUrl,
    copyImageMarkdown,
    anatomyImages,
    anatomyOutlineItems,
    anatomyQuestionGroups,
    scrollAnatomyToOffset,
    onAnatomyImageLoad,
    jumpToQuestionGroup,
    isAnatomyExcluded,
    blankExcludedText,
    anatomySegments
  }
}
