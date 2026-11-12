/**
 * 资料图片 → 题目 / 笔记的插入流程。
 *
 * 从 `workspace/index.vue` 抽出的组合式函数；页面只保留对话框绑定。
 */

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listMyQuestionBank } from '@/api/questionBank/questionBank'
import { getQuestionMain, listQuestionMain, updateQuestionMain } from '@/api/questionMain/questionMain'
import { getNote, listNote, updateNote } from '@/api/notes/note'
import { createContentReference, recordAssetUsage } from '@/api/ai/workspace'

export function useImageInsertion(options: {
  userId: () => string | number | undefined
  onUsageChanged?: () => Promise<void> | void
}) {
  /* 图片插入题目 */
  const questionPickerVisible = ref(false)
  const questionPickerLoading = ref(false)
  const questionPickerImage = ref<any>(null)
  const questionKeyword = ref('')
  const questionBankFilter = ref<number | null>(null)
  const questionBanks = ref<any[]>([])
  const questionRows = ref<any[]>([])
  const questionTotal = ref(0)
  const questionPage = ref(1)
  const QUESTION_PAGE_SIZE = 10
  const questionInsertingId = ref<number | null>(null)

  /* 图片插入笔记 */
  const notePickerVisible = ref(false)
  const notePickerLoading = ref(false)
  const notePickerImage = ref<any>(null)
  const noteKeyword = ref('')
  const noteRows = ref<any[]>([])
  const noteTotal = ref(0)
  const notePage = ref(1)
  const NOTE_PAGE_SIZE = 10
  const noteInsertingId = ref<number | null>(null)

  function openQuestionPicker(img: any) {
    questionPickerImage.value = img
    questionKeyword.value = ''
    questionBankFilter.value = null
    questionPage.value = 1
    questionPickerVisible.value = true
    void loadQuestionBanks()
    loadQuestionPicker(1)
  }

  async function loadQuestionBanks() {
    try {
      const res: any = await listMyQuestionBank()
      questionBanks.value = res.code === 200 && Array.isArray(res.data) ? res.data : []
    } catch {
      questionBanks.value = []
    }
  }

  async function loadQuestionPicker(page = 1) {
    questionPage.value = page
    questionPickerLoading.value = true
    try {
      const params: any = { pageNum: page, pageSize: QUESTION_PAGE_SIZE, status: 0, ownedOnly: true }
      if (questionKeyword.value.trim()) params.keyword = questionKeyword.value.trim()
      if (questionBankFilter.value) params.bankId = questionBankFilter.value
      const res: any = await listQuestionMain(params)
      questionRows.value = res.rows || []
      questionTotal.value = Number(res.total || 0)
    } catch (e: any) {
      ElMessage.error('加载题目失败：' + (e?.message || e))
    } finally {
      questionPickerLoading.value = false
    }
  }

  async function insertImageIntoQuestion(
    row: any,
    field: 'questionAnalysis' | 'questionText' = 'questionAnalysis'
  ) {
    const img = questionPickerImage.value
    if (!img || !row?.id) return
    questionInsertingId.value = row.id
    try {
      const detailRes: any = await getQuestionMain(row.id)
      if (detailRes.code !== 200 || !detailRes.data) {
        ElMessage.error(detailRes.msg || '读取题目失败')
        return
      }
      const q = detailRes.data
      const old = String(q[field] || '')
      const alt = `${img.docName || '资料'}·图${img.seq}`
      const markdown = `![${alt}](${img.rawUrl || img.url})`
      const next = old ? `${old}\n\n${markdown}` : markdown

      const upd: any = await updateQuestionMain({ ...q, [field]: next })
      if (upd.code !== 200) {
        ElMessage.error(upd.msg || '写入题目失败')
        return
      }
      const usage: any = await recordAssetUsage({
        assetKey: img.assetKey,
        assetUrl: img.rawUrl || img.url,
        targetType: 'question',
        targetId: row.id
      })
      if (usage.code === 200) await options.onUsageChanged?.()
      await recordAssetReference(img, 'question', row.id)
      ElMessage.success('已插入题目解析')
    } catch (e: any) {
      ElMessage.error('插入题目失败：' + (e?.message || e))
    } finally {
      questionInsertingId.value = null
    }
  }

  function openNotePicker(img: any) {
    notePickerImage.value = img
    noteKeyword.value = ''
    notePage.value = 1
    notePickerVisible.value = true
    loadNotePicker(1)
  }

  async function loadNotePicker(page = 1) {
    notePage.value = page
    notePickerLoading.value = true
    try {
      const params: any = {
        pageNum: page,
        pageSize: NOTE_PAGE_SIZE,
        userId: options.userId()
      }
      if (noteKeyword.value.trim()) params.title = noteKeyword.value.trim()
      const res: any = await listNote(params)
      noteRows.value = res.rows || []
      noteTotal.value = Number(res.total || 0)
    } catch (e: any) {
      ElMessage.error('加载笔记失败：' + (e?.message || e))
    } finally {
      notePickerLoading.value = false
    }
  }

  async function insertImageIntoNote(row: any) {
    const img = notePickerImage.value
    if (!img || !row?.id) return
    noteInsertingId.value = row.id
    try {
      const detailRes: any = await getNote(row.id)
      if (detailRes.code !== 200 || !detailRes.data) {
        ElMessage.error(detailRes.msg || '读取笔记失败')
        return
      }
      const note = detailRes.data
      const alt = `${img.docName || '资料'}·图${img.seq}`
      const markdown = `![${alt}](${img.rawUrl || img.url})`
      const oldMd = String(note.markdownContent || note.content || '')
      const oldHtml = String(note.content || '')
      const nextMd = oldMd ? `${oldMd}\n\n${markdown}` : markdown
      const nextHtml = oldHtml
        ? `${oldHtml}\n<p><img src="${img.rawUrl || img.url}" alt="${alt}" /></p>`
        : `<p><img src="${img.rawUrl || img.url}" alt="${alt}" /></p>`

      const upd: any = await updateNote({ id: row.id, markdownContent: nextMd, content: nextHtml })
      if (upd.code !== 200) {
        ElMessage.error(upd.msg || '写入笔记失败')
        return
      }
      const usage: any = await recordAssetUsage({
        assetKey: img.assetKey,
        assetUrl: img.rawUrl || img.url,
        targetType: 'note',
        targetId: row.id
      })
      if (usage.code === 200) await options.onUsageChanged?.()
      await recordAssetReference(img, 'note', row.id)
      ElMessage.success('已加入笔记')
    } catch (e: any) {
      ElMessage.error('加入笔记失败：' + (e?.message || e))
    } finally {
      noteInsertingId.value = null
    }
  }

  async function recordAssetReference(img: any, targetType: 'note' | 'question', targetId: number) {
    const key = String(img?.assetKey || '')
    const parts = key.split(':')
    if (parts.length < 2) return
    try {
      if (parts[0] === 'doc') {
        await createContentReference({
          sourceType: 'document_image',
          sourceId: Number(parts[1]),
          sourceSubId: parts[2],
          targetType,
          targetId,
          quote: String(img.sectionTitle || img.caption || '').slice(0, 800)
        })
      } else if (parts[0] === 'chat') {
        await createContentReference({
          sourceType: 'chat_image',
          sourceId: Number(parts[1]),
          targetType,
          targetId,
          quote: String(img.caption || '').slice(0, 800)
        })
      }
    } catch {
      // 引用账本是附加价值：主插入已成功时，不能因为引用失败让用户以为插入失败。
    }
  }

  return {
    questionPickerVisible,
    questionPickerLoading,
    questionPickerImage,
    questionKeyword,
    questionBankFilter,
    questionBanks,
    questionRows,
    questionTotal,
    questionPage,
    questionInsertingId,
    notePickerVisible,
    notePickerLoading,
    notePickerImage,
    noteKeyword,
    noteRows,
    noteTotal,
    notePage,
    noteInsertingId,
    openQuestionPicker,
    loadQuestionBanks,
    loadQuestionPicker,
    insertImageIntoQuestion,
    openNotePicker,
    loadNotePicker,
    insertImageIntoNote
  }
}
