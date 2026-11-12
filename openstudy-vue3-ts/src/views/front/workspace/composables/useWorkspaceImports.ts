import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { importDocumentText, importDocumentUrl, searchPublicWeb } from '@/api/ai/rag'
import {
  getKbQuestionBankKnowledge,
  linkKbQuestionBank,
  listKbQuestionBanks,
  unlinkKbQuestionBank
} from '@/api/ai/questionBankLink'
import { listKbNotes, unlinkKbNote } from '@/api/ai/noteKbLink'
import { getQuestionMain } from '@/api/questionMain/questionMain'

/** 资料夹的文本/网页导入、题库关联、笔记关联和题库知识点。 */
export function useWorkspaceImports(options: {
  activeKb: { value: any }
  busy: { value: boolean }
  load: () => Promise<void>
  wikiRefreshKey: { value: number }
}) {
  const router = useRouter()
  const importing = ref(false)
  const textImportVisible = ref(false)
  const textImportContent = ref('')
  const textImportFileName = ref('')
  const webImportVisible = ref(false)
  const webImportQuery = ref('')
  const webImportNote = ref('')
  const webSearching = ref(false)
  const webImporting = ref(false)
  const webResults = ref<Array<Record<string, any>>>([])
  const webImportIsUrl = computed(() => /^https?:\/\/\S+/i.test(webImportQuery.value.trim()))
  const bankImportVisible = ref(false)
  const bankImportLoading = ref(false)
  const bankImporting = ref(false)
  const bankImportKeyword = ref('')
  const bankImportAvailable = ref<any[]>([])
  const linkedBanks = ref<any[]>([])
  const bankImportLoadingId = ref(0)
  const noteImportVisible = ref(false)
  const noteImporting = ref(false)
  const linkedNotes = ref<any[]>([])
  const bankKnowledgeVisible = ref(false)
  const bankKnowledgeLoading = ref(false)
  const bankKnowledgeTitle = ref('')
  const bankKnowledge = ref<any>({ summary: '', entities: [], relations: [], questions: [] })
  const bankKnowledgeBankId = ref(0)
  const questionJumpVisible = ref(false)
  const questionJumpLoading = ref(false)
  const questionJumpData = ref<any>(null)
  const selectedBankEntityName = ref('')
  const selectedBankEntity = computed(() =>
    (bankKnowledge.value.entities || []).find((entity: any) => String(entity.name) === selectedBankEntityName.value)
  )
  const filteredBankKnowledgeQuestions = computed(() => {
    const questions = bankKnowledge.value.questions || []
    if (!selectedBankEntityName.value) return questions.slice(0, 20)
    const ids = new Set((selectedBankEntity.value?.questionIds || []).map(Number))
    return questions.filter((question: any) => ids.has(Number(question.id)))
  })

  function openTextImport() {
    if (options.busy.value) {
      ElMessage.warning('有导入正在进行，等它跑完')
      return
    }
    textImportContent.value = ''
    textImportFileName.value = ''
    textImportVisible.value = true
  }

  function resetTextImport() {
    textImportContent.value = ''
    textImportFileName.value = ''
  }

  async function submitTextImport() {
    const kb = options.activeKb.value
    if (!kb) return
    const content = textImportContent.value.trim()
    if (!content) {
      ElMessage.warning('先粘点内容进来')
      return
    }
    importing.value = true
    try {
      const res: any = await importDocumentText(kb.kbId, content, textImportFileName.value.trim() || '粘贴的文本')
      if (res.code === 200) {
        ElMessage.success('已导入，后台正在分块')
        textImportVisible.value = false
        await options.load()
        setTimeout(() => options.load(), 4000)
      } else {
        ElMessage.error(res.msg || '导入失败')
      }
    } catch (e: any) {
      ElMessage.error('导入失败：' + (e?.message || e))
    } finally {
      importing.value = false
    }
  }

  function openWebImport() {
    if (options.busy.value) {
      ElMessage.warning('有导入正在进行，等它跑完')
      return
    }
    webImportQuery.value = ''
    webImportNote.value = ''
    webResults.value = []
    webImportVisible.value = true
  }

  function resetWebImport() {
    webImportQuery.value = ''
    webImportNote.value = ''
    webResults.value = []
    webSearching.value = false
    webImporting.value = false
  }

  async function submitWebImport() {
    if (webImportIsUrl.value) await importWebUrl(webImportQuery.value.trim())
    else await runWebSearch()
  }

  async function runWebSearch() {
    const query = webImportQuery.value.trim()
    if (!query) {
      ElMessage.warning('先输入关键词')
      return
    }
    if (webSearching.value) return
    webSearching.value = true
    webResults.value = []
    try {
      const res: any = await searchPublicWeb(query, 6)
      if (res.code === 200) {
        webResults.value = Array.isArray(res.data?.results) ? res.data.results : []
        if (!webResults.value.length) ElMessage.warning('没有搜索到公开网页结果，换个关键词试试')
      } else {
        ElMessage.error(res.msg || '网页搜索失败')
      }
    } catch (e: any) {
      ElMessage.error('网页搜索失败：' + (e?.message || e))
    } finally {
      webSearching.value = false
    }
  }

  async function importWebResult(item: Record<string, any>) {
    const url = String(item?.url || '').trim()
    if (url) await importWebUrl(url)
  }

  async function importWebUrl(url: string) {
    const kb = options.activeKb.value
    if (!kb) return
    if (!/^https?:\/\/\S+/i.test(url)) {
      ElMessage.warning('请提供 http:// 或 https:// 开头的公开网页链接')
      return
    }
    if (webImporting.value) return
    webImporting.value = true
    try {
      const res: any = await importDocumentUrl(kb.kbId, url, webImportNote.value.trim() || undefined)
      if (res.code === 200) {
        ElMessage.success(res.msg || '网页已导入，后台正在分块')
        webImportVisible.value = false
        await options.load()
        setTimeout(() => options.load(), 4000)
      } else {
        ElMessage.error(res.msg || '网页导入失败')
      }
    } catch (e: any) {
      ElMessage.error('网页导入失败：' + (e?.message || e))
    } finally {
      webImporting.value = false
    }
  }

  const filteredBankImportBanks = computed(() => {
    const q = bankImportKeyword.value.trim().toLowerCase()
    if (!q) return bankImportAvailable.value
    return bankImportAvailable.value.filter((bank: any) => {
      const text = `${bank.bankName || bank.name || ''} ${bank.subject || ''}`.toLowerCase()
      return text.includes(q)
    })
  })

  async function loadLinkedBanks() {
    const kb = options.activeKb.value
    if (!kb || !Number(kb.kbId)) {
      linkedBanks.value = []
      return
    }
    try {
      const res: any = await listKbQuestionBanks(Number(kb.kbId))
      if (res.code === 200) linkedBanks.value = res.data?.linked || []
    } catch {
      linkedBanks.value = []
    }
  }

  async function loadLinkedNotes() {
    const kb = options.activeKb.value
    if (!kb || !Number(kb.kbId)) {
      linkedNotes.value = []
      return
    }
    try {
      const res: any = await listKbNotes(Number(kb.kbId))
      if (res.code === 200) linkedNotes.value = res.data?.linked || []
    } catch {
      linkedNotes.value = []
    }
  }

  function openNoteImport() {
    if (!options.activeKb.value || !Number(options.activeKb.value.kbId)) return
    noteImportVisible.value = true
  }

  function onNoteImported() {
    noteImporting.value = false
    void loadLinkedNotes()
    options.wikiRefreshKey.value += 1
  }

  async function unlinkLinkedNote(note: any) {
    const kb = options.activeKb.value
    const noteId = Number(note?.noteId || note?.id || 0)
    if (!kb || !noteId) return
    try {
      await ElMessageBox.confirm(`确定取消关联笔记「${note.title || '未命名笔记'}」吗？`, '取消关联', {
        confirmButtonText: '取消关联',
        cancelButtonText: '保留',
        type: 'warning'
      })
    } catch {
      return
    }
    try {
      const res: any = await unlinkKbNote(Number(kb.kbId), noteId)
      if (res.code === 200) {
        ElMessage.success('已取消关联')
        await loadLinkedNotes()
      } else {
        ElMessage.error(res.msg || '取消关联失败')
      }
    } catch (error: any) {
      ElMessage.error('取消关联失败：' + (error?.message || error))
    }
  }

  async function refreshBankImportList() {
    const kb = options.activeKb.value
    if (!kb || !Number(kb.kbId)) return
    bankImportLoading.value = true
    try {
      const res: any = await listKbQuestionBanks(Number(kb.kbId))
      if (res.code === 200) {
        linkedBanks.value = res.data?.linked || []
        bankImportAvailable.value = res.data?.available || []
      } else {
        ElMessage.error(res.msg || '读取题库失败')
      }
    } catch (e: any) {
      ElMessage.error('读取题库失败：' + (e?.message || e))
    } finally {
      bankImportLoading.value = false
    }
  }

  async function openBankImport() {
    if (!options.activeKb.value) return
    bankImportKeyword.value = ''
    bankImportVisible.value = true
    await refreshBankImportList()
  }

  async function importQuestionBank(bank: any) {
    const kb = options.activeKb.value
    const bankId = Number(bank?.bankId || bank?.id || 0)
    if (!kb || !bankId || bank?.linked || bankImporting.value) return
    bankImporting.value = true
    bankImportLoadingId.value = bankId
    try {
      const res: any = await linkKbQuestionBank(Number(kb.kbId), bankId)
      if (res.code === 200) {
        ElMessage.success(`已关联题库「${bank.bankName || bank.name || ''}」，知识图谱会自动提取其中的知识点`)
        await refreshBankImportList()
      } else {
        ElMessage.error(res.msg || '关联题库失败')
      }
    } catch (e: any) {
      ElMessage.error('关联题库失败：' + (e?.message || e))
    } finally {
      bankImporting.value = false
      bankImportLoadingId.value = 0
    }
  }

  function selectBankKnowledgeEntity(name: string) {
    selectedBankEntityName.value = selectedBankEntityName.value === name ? '' : name
  }

  function formatQuestionOptions(value: any) {
    if (!value) return ''
    if (Array.isArray(value)) {
      return value.map((item: any, index: number) => `${String.fromCharCode(65 + index)}. ${item?.label ?? item?.content ?? item}`).join('\n')
    }
    if (typeof value === 'object') {
      return Object.entries(value).map(([key, item]: any) => `${key}. ${item?.label ?? item?.content ?? item}`).join('\n')
    }
    return String(value)
  }

  async function openBankQuestion(question: any) {
    const questionId = Number(question?.id || 0)
    if (!questionId || questionJumpLoading.value) return
    questionJumpData.value = null
    questionJumpVisible.value = true
    questionJumpLoading.value = true
    try {
      const res: any = await getQuestionMain(questionId)
      if (res.code === 200) questionJumpData.value = res.data || null
      else ElMessage.error(res.msg || '题目详情加载失败')
    } catch (e: any) {
      ElMessage.error('题目详情加载失败：' + (e?.message || e))
    } finally {
      questionJumpLoading.value = false
    }
  }

  function goBankPractice() {
    if (bankKnowledgeBankId.value) {
      router.push(`/front/questionPractice/${bankKnowledgeBankId.value}?from=bankKnowledge`)
    }
  }

  async function openBankKnowledge(bank: any) {
    const kb = options.activeKb.value
    const bankId = Number(bank?.bankId || bank?.id || 0)
    if (!kb || !bankId || bankKnowledgeLoading.value) return
    bankKnowledgeTitle.value = String(bank.bankName || bank.name || '题库知识点')
    bankKnowledgeBankId.value = bankId
    bankKnowledge.value = { summary: '', entities: [], relations: [], questions: [] }
    selectedBankEntityName.value = ''
    bankKnowledgeVisible.value = true
    bankKnowledgeLoading.value = true
    try {
      const res: any = await getKbQuestionBankKnowledge(Number(kb.kbId), bankId)
      if (res.code === 200) bankKnowledge.value = res.data || { entities: [], relations: [], questions: [] }
      else ElMessage.error(res.msg || '读取题库知识点失败')
    } catch (e: any) {
      ElMessage.error('读取题库知识点失败：' + (e?.message || e))
    } finally {
      bankKnowledgeLoading.value = false
    }
  }

  async function removeLinkedBank(bank: any) {
    const kb = options.activeKb.value
    const bankId = Number(bank?.bankId || bank?.id || 0)
    if (!kb || !bankId) return
    try {
      const res: any = await unlinkKbQuestionBank(Number(kb.kbId), bankId)
      if (res.code === 200) {
        ElMessage.success('已取消关联')
        await refreshBankImportList()
      }
    } catch (e: any) {
      ElMessage.error('取消关联失败：' + (e?.message || e))
    }
  }

  return {
    importing,
    textImportVisible,
    textImportContent,
    textImportFileName,
    webImportVisible,
    webImportQuery,
    webImportNote,
    webSearching,
    webImporting,
    webResults,
    webImportIsUrl,
    bankImportVisible,
    bankImportLoading,
    bankImporting,
    bankImportKeyword,
    bankImportAvailable,
    linkedBanks,
    bankImportLoadingId,
    noteImportVisible,
    noteImporting,
    linkedNotes,
    bankKnowledgeVisible,
    bankKnowledgeLoading,
    bankKnowledgeTitle,
    bankKnowledge,
    bankKnowledgeBankId,
    questionJumpVisible,
    questionJumpLoading,
    questionJumpData,
    selectedBankEntityName,
    selectedBankEntity,
    filteredBankKnowledgeQuestions,
    filteredBankImportBanks,
    openTextImport,
    resetTextImport,
    submitTextImport,
    openWebImport,
    resetWebImport,
    submitWebImport,
    runWebSearch,
    importWebResult,
    importWebUrl,
    loadLinkedBanks,
    loadLinkedNotes,
    openNoteImport,
    onNoteImported,
    unlinkLinkedNote,
    refreshBankImportList,
    openBankImport,
    importQuestionBank,
    selectBankKnowledgeEntity,
    formatQuestionOptions,
    openBankQuestion,
    goBankPractice,
    openBankKnowledge,
    removeLinkedBank
  }
}
