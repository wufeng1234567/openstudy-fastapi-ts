import { computed } from 'vue'
import { useRouter } from 'vue-router'

const BANK_ACTIONS = new Set(['create', 'batch_import', 'import', 'update', 'open'])
const BANK_TOOLS = new Set(['bank_manage', 'question_manage'])
const NOTE_ACTIONS = new Set(['create', 'update'])
const LINK_WRITE_ACTIONS = new Set([
  'create_book',
  'rename_book',
  'add_word',
  'batch_add_words',
  'create',
  'batch_import',
  'open',
  'from_text',
  'from_attachment',
  'update_document',
  'restore_document_version',
  'start'
])
const LINK_UI: Record<string, { badge: string; buttonText: string; icon: string }> = {
  english_wordbook: { badge: '词库已更新', buttonText: '去看看', icon: 'book' },
  bank_manage: { badge: '题库入口', buttonText: '去刷题', icon: 'book-open' },
  question_manage: { badge: '题目已就绪', buttonText: '去刷题', icon: 'pen-line' },
  knowledge_ingest: { badge: '资料已入库', buttonText: '查看处理进度', icon: 'folder' },
  english_practice: { badge: '练习已就绪', buttonText: '开始听力练习', icon: 'book-open' }
}

function pickBankPayload(d: any): any | null {
  if (!d || typeof d !== 'object') return null
  const nested = d.bank
  if (nested && typeof nested === 'object') {
    const nid = nested.bankId ?? nested.bank_id ?? nested.id
    if (nid) return nested
  }
  const did = d.bankId ?? d.bank_id ?? d.id
  if (did) return d
  return null
}

/** 题库 / 笔记 / 通用 jumpUrl 三类跳转卡片。 */
export function useAgentToolJumps(options: { props: any; unwrap: (raw: any) => any }) {
  const router = useRouter()

  const bankJump = computed(() => {
    if (options.props.status !== 'ok') return null
    if (options.props.tool && !BANK_TOOLS.has(options.props.tool)) return null
    const d = options.unwrap(options.props.data)
    if (!d || typeof d !== 'object') return null
    const payload = pickBankPayload(d)
    if (!payload) return null
    const bankId = Number(payload.bankId ?? payload.bank_id ?? payload.id ?? 0)
    if (!bankId) return null
    const action = String(d.action || options.props.action || '').toLowerCase()
    if (action && !BANK_ACTIONS.has(action)) return null
    const bankName = String(payload.bankName || payload.bank_name || payload.name || '题库')
    const total = Number(payload.bankTotal ?? payload.totalQuestions ?? payload.total_questions ?? d.imported ?? 0)
    if (action === 'create' && total <= 0) return null
    const metaParts: string[] = []
    if (total > 0) metaParts.push(`共 ${total} 题`)
    if (d.imported) metaParts.push(`本次导入 ${d.imported} 题`)
    const subject = payload.subject || d.subject
    if (subject) metaParts.push(String(subject))
    return {
      bankId,
      bankName,
      meta: metaParts.join(' · '),
      isNew: action === 'create',
      isOpen: action === 'open',
      total
    }
  })

  const noteJump = computed(() => {
    if (options.props.tool !== 'note_manage') return null
    if (options.props.status !== 'ok') return null
    const d = options.unwrap(options.props.data)
    if (!d || typeof d !== 'object') return null
    const action = String(d.action || '').toLowerCase()
    if (action && !NOTE_ACTIONS.has(action)) return null
    const note = d.note && typeof d.note === 'object' ? d.note : d
    const noteId = Number(note.noteId ?? note.note_id ?? 0)
    if (!noteId) return null
    const title = String(note.title || '笔记')
    const metaParts: string[] = []
    if (note.visibility) metaParts.push(String(note.visibility))
    const tags = String(note.tags || '').trim()
    if (tags) metaParts.push(tags.replace(/,/g, ' · '))
    return { noteId, title, meta: metaParts.join(' · '), isNew: action === 'create' }
  })

  const linkJump = computed(() => {
    if (options.props.status !== 'ok') return null
    const d = options.unwrap(options.props.data)
    if (!d || typeof d !== 'object') return null
    const raw = d.jumpUrl
    if (typeof raw !== 'string' || !raw.trim()) return null
    const action = String(d.action || options.props.action || '').toLowerCase()
    if (action && !LINK_WRITE_ACTIONS.has(action)) return null
    if (options.props.tool === 'bank_manage' && action === 'create') {
      const payload = pickBankPayload(d)
      const total = Number(payload?.bankTotal ?? payload?.totalQuestions ?? payload?.total_questions ?? 0)
      if (total <= 0) return null
    }
    if (bankJump.value || noteJump.value) return null
    const ui = LINK_UI[String(options.props.tool || '')] || {
      badge: '已保存',
      buttonText: '去看看',
      icon: 'arrow-right'
    }
    const badge = action === 'update_document'
      ? '资料已更新'
      : action === 'restore_document_version'
        ? '版本已恢复'
        : ui.badge
    const nested = d.book && typeof d.book === 'object' ? d.book : null
    const name = String(
      d.fileName || d.bookName || nested?.bookName || d.noteTitle || d.title || ''
    )
    const isPractice = action === 'start'
    const practiceMeta = (() => {
      if (!isPractice) return ''
      const parts: string[] = []
      const total = Number(d.count || 0)
      if (total) parts.push(`${total} 个词`)
      const modeText = d.mode === 'input' ? '打字输入' : d.mode === 'listen' ? '纯听力' : '自动听写'
      parts.push(modeText)
      if (d.scope === 'due') parts.push('按记忆曲线排的')
      else if (d.scope === 'wrong') parts.push('易错词')
      return parts.join(' · ')
    })()
    const meta = isPractice
      ? practiceMeta
      : typeof d.message === 'string'
        ? d.message
        : d.addedCount
          ? `本次加入 ${d.addedCount} 个`
          : ''
    return { url: raw.trim(), badge, buttonText: ui.buttonText, icon: ui.icon, name, meta }
  })

  function goToBank() {
    const b = bankJump.value
    if (b) router.push(`/front/questionPractice/${b.bankId}`)
  }

  function goToNote() {
    const n = noteJump.value
    if (n) router.push(`/front/notes/detail/${n.noteId}`)
  }

  function goToLink() {
    const j = linkJump.value
    if (j) router.push(j.url)
  }

  return { bankJump, noteJump, linkJump, goToBank, goToNote, goToLink }
}
