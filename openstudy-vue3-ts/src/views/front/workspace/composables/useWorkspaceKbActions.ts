import { ElMessage, ElMessageBox } from 'element-plus'
import { createKnowledgeBase, deleteKnowledgeBase, updateKnowledgeBase } from '@/api/ai/rag'
import { setDocumentSearchable } from '@/api/ai/workspace'

/** 资料夹菜单、分享、重命名、删除、屏蔽和文档可检索开关。 */
export function useWorkspaceKbActions(options: {
  activeKbId: { value: number | null }
  creating: { value: boolean }
  kbMenu: { visible: boolean; x: number; y: number; kb: any }
  shareKbId: { value: number | null }
  shareDialogVisible: { value: boolean }
  docShareDialogVisible: { value: boolean }
  shareDoc: { value: any }
  load: (keepActive?: boolean) => Promise<void>
}) {
  function openShare(kb: any) {
    closeKbMenu()
    options.shareKbId.value = Number(kb?.kbId) || null
    options.shareDialogVisible.value = true
  }

  function openKbMenu(event: MouseEvent, kb: any) {
    const target = event.currentTarget as HTMLElement
    const rect = target.getBoundingClientRect()
    const menuWidth = 188
    const menuHeight = kb?.isDefault ? 150 : 188
    const x = Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8)
    const y = Math.min(rect.bottom + 4, window.innerHeight - menuHeight - 8)
    options.kbMenu.kb = kb
    options.kbMenu.x = Math.max(8, x)
    options.kbMenu.y = Math.max(8, y)
    options.kbMenu.visible = true
  }

  function closeKbMenu() {
    options.kbMenu.visible = false
    options.kbMenu.kb = null
  }

  function openDocShare(doc: any) {
    options.shareDoc.value = { docId: Number(doc.docId), fileName: String(doc.fileName || '未命名文档') }
    options.docShareDialogVisible.value = true
  }

  function handleKbCommand(command: string, kb: any) {
    if (!kb) return
    closeKbMenu()
    if (command === 'rename') return promptRename(kb)
    if (command === 'share') return openShare(kb)
    if (command === 'toggle-disabled') return toggleDisabled(kb)
    if (command === 'delete' && !kb.isDefault) return removeKb(kb)
  }

  async function promptCreate() {
    try {
      const r: any = await ElMessageBox.prompt('给资料夹起个名字', '新建资料夹', {
        confirmButtonText: '创建',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：概率论、数据结构期末',
        inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
      })
      options.creating.value = true
      const res: any = await createKnowledgeBase({ name: r.value.trim() })
      if (res.code === 200) {
        ElMessage.success('资料夹已创建')
        await options.load()
        if (res.data?.kbId) options.activeKbId.value = res.data.kbId
      } else {
        ElMessage.error(res.msg || '创建失败')
      }
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.error('创建失败：' + (e?.message || e))
    } finally {
      options.creating.value = false
    }
  }

  async function promptRename(kb: any) {
    try {
      const r: any = await ElMessageBox.prompt('改成什么名字？', '重命名资料夹', {
        confirmButtonText: '保存',
        cancelButtonText: '取消',
        inputValue: kb.name,
        inputValidator: (v: string) => (v && v.trim() ? true : '名字不能为空')
      })
      const res: any = await updateKnowledgeBase(kb.kbId, { name: r.value.trim() })
      if (res.code === 200) {
        ElMessage.success('已重命名')
        await options.load()
      } else {
        ElMessage.error(res.msg || '重命名失败')
      }
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.error('重命名失败：' + (e?.message || e))
    }
  }

  async function removeKb(kb: any) {
    try {
      await ElMessageBox.confirm(
        `确定删除「${kb.name}」吗？里面的 ${kb.docCount} 份资料会一起删掉，不能恢复。`,
        '删除资料夹',
        { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    try {
      const res: any = await deleteKnowledgeBase(kb.kbId)
      if (res.code === 200) {
        ElMessage.success('已删除')
        if (options.activeKbId.value === kb.kbId) options.activeKbId.value = null
        await options.load(false)
      } else {
        ElMessage.error(res.msg || '删除失败')
      }
    } catch (e: any) {
      ElMessage.error('删除失败：' + (e?.message || e))
    }
  }

  async function toggleDisabled(kb: any) {
    const next = kb.disabled === 1 ? 0 : 1
    try {
      const res: any = await updateKnowledgeBase(kb.kbId, { disabled: next })
      if (res.code === 200) {
        ElMessage.success(next === 1 ? '已屏蔽，智能体不会再检索它' : '已恢复检索')
        await options.load()
      } else {
        ElMessage.error(res.msg || '操作失败')
      }
    } catch (e: any) {
      if (e?.__repeatSubmit) return
      ElMessage.error('操作失败：' + (e?.message || e))
    }
  }

  async function toggleDocSearchable(doc: any) {
    const next = doc.disabled !== 1
    try {
      const res: any = await setDocumentSearchable(doc.docId, next)
      if (res.code === 200) {
        ElMessage.success(next ? '已恢复这份资料的检索' : '已屏蔽这份资料，智能体不会检索它')
        await options.load()
      } else {
        ElMessage.error(res.msg || '操作失败')
      }
    } catch (e: any) {
      if (e?.__repeatSubmit) return
      ElMessage.error('操作失败：' + (e?.message || e))
    }
  }

  return {
    openShare,
    openKbMenu,
    closeKbMenu,
    openDocShare,
    handleKbCommand,
    promptCreate,
    promptRename,
    removeKb,
    toggleDisabled,
    toggleDocSearchable
  }
}
