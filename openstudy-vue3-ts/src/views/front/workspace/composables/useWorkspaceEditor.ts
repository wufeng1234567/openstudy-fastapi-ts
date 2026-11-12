import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { saveAs } from 'file-saver'
import { getDocumentContent, exportDocument } from '@/api/ai/rag'
import { blobValidate } from '@/utils/legacy'
import { createTurndownService, htmlToEditorMarkdown, markdownToEditorHtml } from '../utils/editorMarkdown'

/** 资料正文编辑器：状态、打开、导出与微课跳转。 */
export function useWorkspaceEditor(options: { anatomyImageUrl: (url: string) => string }) {
  const router = useRouter()
  const editorVisible = ref(false)
  const editorLoading = ref(false)
  const editorSaving = ref(false)
  const editorDoc = ref<any>(null)
  const editorContent = ref('')
  const editorHtml = ref('')
  const editorImageMap = ref<Record<string, string>>({})
  const editorPreview = ref(false)
  const versionsVisible = ref(false)
  const turndownService = createTurndownService()
  const editorMarkdown = computed(() => htmlToEditorMarkdown(turndownService, editorHtml.value))

  async function openEditor(doc: any) {
    if (!doc?.docId) return
    editorDoc.value = doc
    editorPreview.value = false
    editorContent.value = ''
    editorHtml.value = ''
    editorImageMap.value = {}
    editorVisible.value = true
    editorLoading.value = true
    try {
      const res: any = await getDocumentContent(doc.docId)
      if (res.code !== 200) {
        ElMessage.error(res.msg || '读取正文失败')
        editorVisible.value = false
        return
      }
      editorContent.value = res.data?.content || ''
      editorImageMap.value = res.data?.imageMap || {}
      editorHtml.value = markdownToEditorHtml(editorContent.value, editorImageMap.value, options.anatomyImageUrl)
    } catch (e: any) {
      editorVisible.value = false
      ElMessage.error('读取正文失败：' + (e?.message || e))
    } finally {
      editorLoading.value = false
    }
  }

  async function exportDoc(doc: any, format: 'markdown' | 'docx', content?: string) {
    if (!doc?.docId) return
    try {
      const blob: any = await exportDocument(doc.docId, format, content)
      if (!(blob instanceof Blob) || blob.size === 0 || !blobValidate(blob)) {
        let msg = '导出失败'
        try {
          const parsed = JSON.parse(await blob.text())
          msg = parsed?.msg || parsed?.message || msg
        } catch { /* 非 JSON 错误体 */ }
        ElMessage.error(msg)
        return
      }
      const stem = String(doc.fileName || '资料').replace(/\.[^.]+$/, '')
      saveAs(new Blob([blob]), `${stem}.${format === 'docx' ? 'docx' : 'md'}`)
      ElMessage.success(`正在导出${format === 'docx' ? ' Word' : ' Markdown'}`)
    } catch (e: any) {
      ElMessage.error('导出失败：' + (e?.message || e))
    }
  }

  function exportCurrent(format: 'markdown' | 'docx') {
    if (editorDoc.value) exportDoc(editorDoc.value, format, editorMarkdown.value)
  }

  function openMicroCourse(doc: any) {
    router.push({ path: '/front/microCourse', query: { docId: String(doc.docId) } })
  }

  return {
    editorVisible,
    editorLoading,
    editorSaving,
    editorDoc,
    editorContent,
    editorHtml,
    editorImageMap,
    editorPreview,
    versionsVisible,
    editorMarkdown,
    openEditor,
    exportDoc,
    exportCurrent,
    openMicroCourse
  }
}

