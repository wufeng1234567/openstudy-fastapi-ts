import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadToWorkspace } from '@/api/ai/workspace'
import { uploadDocument, deleteDocument, getDocumentStatusBatch } from '@/api/ai/rag'
import {
  ensureMarkdownImageFiles,
  missingMarkdownImageFiles,
  pickMissingImagesFromDirectory
} from '@/utils/markdownUpload'
import { delay } from '../utils/helpers'

/** 文档上传、批量删除和上传后的后台状态轮询。 */
export function useWorkspaceUpload(options: {
  activeKb: { value: any }
  fileInputRef: { value: HTMLInputElement | null }
  busy: { value: boolean }
  dragOver: { value: boolean }
  uploading: { value: boolean }
  uploadTip: { value: string }
  selectedDocIds: { value: number[] }
  load: () => Promise<void>
  openTextImport: () => void
  openWebImport: () => void
  openBankImport: () => void
  openNoteImport: () => void
  onGraphChanged?: () => void
}) {
  function onPick() {
    options.fileInputRef.value?.click()
  }

  function onUploadCommand(command: string) {
    if (options.busy.value) return
    if (command === 'file') onPick()
    else if (command === 'text') options.openTextImport()
    else if (command === 'url') options.openWebImport()
    else if (command === 'bank') options.openBankImport()
    else if (command === 'note') options.openNoteImport()
  }

  async function onFilesPicked(e: Event) {
    const input = e.target as HTMLInputElement
    const files = Array.from(input.files || [])
    input.value = ''
    if (files.length) await uploadFiles(files)
  }

  function onDrop(e: DragEvent) {
    options.dragOver.value = false
    if (options.busy.value || !options.activeKb.value) return
    const list = e.dataTransfer?.files
    if (list?.length) uploadFiles(Array.from(list))
  }

  async function uploadFiles(list: File[]) {
    const kb = options.activeKb.value
    if (!kb) return
    if (!list.length || options.busy.value) return

    let uploadList = [...list]
    const missingGroups = await missingMarkdownImageFiles(uploadList)
    if (missingGroups.length) {
      const names = [...new Set(missingGroups.flatMap((item) => item.missing))]
      if ((window as any).showDirectoryPicker) {
        try {
          const extra = await pickMissingImagesFromDirectory(names)
          if (extra.length) uploadList = [...uploadList, ...extra]
        } catch {
          // 用户取消目录授权，继续走下面的明确提示。
        }
      }
    }
    if (!(await ensureMarkdownImageFiles(uploadList))) return
    if (uploadList.length > 20) {
      ElMessage.warning('一次最多上传 20 个文件，请分批上传')
      return
    }
    const totalBytes = uploadList.reduce((sum, file) => sum + Number(file.size || 0), 0)
    if (totalBytes > 5 * 1024 * 1024) {
      ElMessage.warning(
        `本次选择 ${(totalBytes / 1024 / 1024).toFixed(1)}MB，单次上传总大小不能超过 5MB，请减少文件数量或压缩后再上传`
      )
      return
    }
    options.uploading.value = true
    let ok = 0
    let fail = 0
    const uploadedDocIds: number[] = []
    try {
      options.uploadTip.value = uploadList.length > 1 ? `正在上传 ${uploadList.length} 个文件…` : `正在上传 ${uploadList[0].name}…`
      const res: any = kb.isDefault
        ? await uploadToWorkspace(uploadList)
        : await uploadDocument(kb.kbId, uploadList)
      let images: any[] = []
      if (res.code === 200) {
        const documents = Array.isArray(res.data?.documents)
          ? res.data.documents
          : (res.data?.docId ? [res.data] : [])
        images = Array.isArray(res.data?.images)
          ? res.data.images
          : (res.data?.assetKey ? [res.data] : [])
        const failed = Array.isArray(res.data?.failed) ? res.data.failed : []
        ok = documents.length + images.length
        fail = failed.length
        for (const item of failed) {
          ElMessage.error(`${item.fileName || '文件'}：${item.error || '上传失败'}`)
        }
        for (const item of documents) {
          const uploadedId = Number(item.docId || 0)
          if (uploadedId) uploadedDocIds.push(uploadedId)
        }
        if (!ok && res.msg) ElMessage.error(res.msg)
        const ocrCount = documents.filter((item: any) => item.ocrApplied).length
        if (ocrCount) ElMessage.success(`${ocrCount} 张手写图片已完成 OCR 校对`)
        const versioned = documents.filter((item: any) => item.versioned)
        for (const item of versioned) {
          ElMessage.success(`「${item.fileName}」已更新为第 ${item.version} 版，旧版本可在编辑器「历史版本」中恢复`)
        }
        const unchanged = documents.filter((item: any) => item.unchanged)
        if (unchanged.length) ElMessage.info('同名资料内容未变化，未重复创建版本')
      } else {
        fail = uploadList.length
        ElMessage.error(res.msg || '上传失败')
      }
      if (ok) {
        const imageCount = images.length
        const documentCount = ok - imageCount
        if (documentCount) {
          ElMessage.success(`已上传 ${documentCount} 份资料${fail ? `，${fail} 份失败` : ''}，正在后台解析并建立索引`)
        }
        if (imageCount) {
          ElMessage.success(`已上传 ${imageCount} 张独立图片，正在生成图片名称和描述`)
        }
        options.uploadTip.value = '上传完成：资料正在解析、提取图片/公式并建立索引；独立图片已加入画廊并生成名称/描述。'
        await options.load()
        options.onGraphChanged?.()
        if (uploadedDocIds.length) pollUploadedDocuments(uploadedDocIds)
      } else {
        options.uploadTip.value = ''
      }
    } catch (err: any) {
      ElMessage.error('上传失败：' + (err?.message || err))
    } finally {
      options.uploading.value = false
    }
  }

  function toggleDocSelected(docId: number) {
    const id = Number(docId)
    if (!id) return
    const idx = options.selectedDocIds.value.indexOf(id)
    if (idx >= 0) options.selectedDocIds.value.splice(idx, 1)
    else options.selectedDocIds.value.push(id)
  }

  async function removeSelectedDocs() {
    const ids = [...options.selectedDocIds.value]
    if (!ids.length) return
    try {
      await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 份资料吗？删除后不可恢复。`, '批量删除资料', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }
    let ok = 0
    let fail = 0
    for (const id of ids) {
      try {
        const res: any = await deleteDocument(id)
        if (res.code === 200) ok += 1
        else fail += 1
      } catch {
        fail += 1
      }
    }
    options.selectedDocIds.value = []
    await options.load()
    if (ok) ElMessage.success(`已删除 ${ok} 份资料${fail ? `，${fail} 份失败` : ''}`)
    else ElMessage.error('批量删除失败，请稍后重试')
  }

  async function removeDoc(doc: any) {
    try {
      await ElMessageBox.confirm(`确定删除「${doc.fileName}」吗？`, '删除资料', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      })
    } catch {
      return
    }
    try {
      const res: any = await deleteDocument(doc.docId)
      if (res.code === 200) {
        ElMessage.success('已删除')
        await options.load()
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (e: any) {
      ElMessage.error('删除失败：' + (e?.message || e))
    }
  }

  async function pollUploadedDocuments(docIds: number[]) {
    const pending = new Set(docIds.map(Number).filter(Boolean))
    let failed = 0
    try {
      for (let i = 0; i < 90 && pending.size; i++) {
        await delay(1200)
        try {
          const res: any = await getDocumentStatusBatch([...pending])
          if (res.code === 200 && Array.isArray(res.data)) {
            for (const item of res.data) {
              const docId = Number(item.docId)
              const status = Number(item.status || 0)
              if (status === 4) {
                failed++
                pending.delete(docId)
              } else if (status === 5) {
                pending.delete(docId)
              }
            }
          }
        } catch {
          // 单轮失败不打断，下一轮继续。
        }
        if (pending.size) await options.load()
      }
    } finally {
      await options.load()
      options.uploadTip.value = ''
      // 文档解析完成后内容 hash / 分块才稳定，再触发一次图谱增量同步。
      options.onGraphChanged?.()
      if (failed) ElMessage.error(`${failed} 份资料解析失败，可在文档行点击「更多 → 重新解析」`)
    }
  }

  return {
    onPick,
    onUploadCommand,
    onFilesPicked,
    onDrop,
    toggleDocSelected,
    removeSelectedDocs,
    removeDoc
  }
}

