import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { searchWorkspace } from '@/api/ai/workspace'

/** 「试试 AI 怎么找」的检索状态、高亮和命中片段。 */
export function useWorkspaceTrySearch(options: {
  activeKb: { value: any }
  showAnatomy: (doc: any, opts?: any) => void
}) {
  const tryQuery = ref('')
  const tryPanelRef = ref<HTMLElement | null>(null)
  const trying = ref(false)
  const tried = ref(false)
  const tryHits = ref<any[]>([])
  const tryPage = ref(1)
  const TRY_PAGE_SIZE = 10
  const tryPageHits = computed(() => {
    const start = (tryPage.value - 1) * TRY_PAGE_SIZE
    return tryHits.value.slice(start, start + TRY_PAGE_SIZE)
  })
  const tryReason = ref('')
  const lowConfidence = ref(false)
  const trySearchedQuery = ref('')

  function clearTryResults() {
    tryHits.value = []
    tryPage.value = 1
    tried.value = false
    tryReason.value = ''
    lowConfidence.value = false
    trySearchedQuery.value = ''
  }

  function onTryInput() {
    if (!tryQuery.value.trim()) clearTryResults()
  }

  async function doTry() {
    const q = tryQuery.value.trim()
    if (!q) {
      ElMessage.warning('先输入一句描述')
      return
    }
    const kb = options.activeKb.value
    if (!kb) return
    trying.value = true
    tried.value = false
    tryReason.value = ''
    tryHits.value = []
    tryPage.value = 1
    lowConfidence.value = false
    trySearchedQuery.value = q
    try {
      const res: any = await searchWorkspace(q, 50, [kb.kbId])
      if (res.code === 200) {
        tryHits.value = res.data.hits || []
        tryReason.value = res.data.reason || ''
        lowConfidence.value = !!res.data.lowConfidence
        tried.value = true
      } else {
        ElMessage.error(res.msg || '查找失败')
      }
    } catch (e: any) {
      ElMessage.error('查找失败：' + (e?.message || e))
    } finally {
      trying.value = false
    }
  }

  function openHit(hit: any) {
    const doc = options.activeKb.value?.files.find((f: any) => Number(f.docId) === Number(hit.docId))
    options.showAnatomy(
      {
        ...(doc || {}),
        docId: hit.docId,
        fileName: hit.docName || hit.fileName || doc?.fileName || '未命名资料'
      },
      {
        highlight: trySearchedQuery.value,
        chunkIndex: hit.chunkIndex,
        chunkId: hit.chunkId,
        chunkCount: Number(doc?.chunkCount || 0),
        targetText: String(hit.content || '')
      }
    )
  }

  function highlight(content: string): string {
    const escaped = String(content || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const terms = trySearchedQuery.value.trim().split(/\s+/).filter((t) => t.length > 0)
    if (!terms.length) return escaped
    terms.sort((a, b) => b.length - a.length)
    const pattern = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
    try {
      return escaped.replace(new RegExp(`(${pattern})`, 'gi'), '<mark>$1</mark>')
    } catch {
      return escaped
    }
  }

  function highlightQuery(content: string, query: string): string {
    const escaped = String(content || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const term = String(query || '').trim()
    if (!term) return escaped
    const pattern = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    try {
      return escaped.replace(new RegExp(`(${pattern})`, 'gi'), '<mark>$1</mark>')
    } catch {
      return escaped
    }
  }

  function cleanMathForSnippet(input: string): string {
    return String(input || '')
      .replace(/\$([^$]+)\$/g, (_, body) => body
        .replace(/\\overline\{([^{}]+)\}/g, '$1')
        .replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '($1)/($2)')
        .replace(/\\[a-zA-Z]+\{([^{}]*)\}/g, '$1')
        .replace(/\\[a-zA-Z]+/g, '')
        .replace(/[{}]/g, ''))
      .replace(/【图\d+】/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  function buildHitSnippet(content: string): string {
    const text = cleanMathForSnippet(content)
    const q = trySearchedQuery.value.trim()
    if (!text || !q) return text.slice(0, 180)
    const lower = text.toLowerCase()
    let pos = lower.indexOf(q.toLowerCase())
    if (pos < 0) {
      const first = q.split(/\s+/).find((t) => t.length > 0) || ''
      pos = first ? lower.indexOf(first.toLowerCase()) : -1
    }
    if (pos < 0) return text.slice(0, 180)
    const start = Math.max(0, pos - 46)
    const end = Math.min(text.length, pos + q.length + 110)
    return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`
  }

  function docTagType(status: number) {
    if (status === 5) return 'success'
    if (status === 4) return 'danger'
    if (status === 2) return 'warning'
    return 'info'
  }

  return {
    tryQuery,
    tryPanelRef,
    trying,
    tried,
    tryHits,
    tryPage,
    tryPageHits,
    tryReason,
    lowConfidence,
    trySearchedQuery,
    clearTryResults,
    onTryInput,
    doTry,
    openHit,
    highlight,
    highlightQuery,
    cleanMathForSnippet,
    buildHitSnippet,
    docTagType
  }
}
