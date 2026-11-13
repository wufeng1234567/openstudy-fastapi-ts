import { ElMessage } from 'element-plus'

/**
 * 预览/编辑区的交互辅助。
 *
 * 从 QuestionBuilder.vue 抽出：图片预览、公式插入、复制原始 JSON、材料编辑、
 * 选项 JSON 高级编辑、预览数据同步。状态 ref 仍留在 SFC 中，以 options 传入；
 * 返回的 8 个函数保持原签名与名称，模板调用点无需改动。
 */
export function useQuestionBuilderPreviewEdit(options: {
  viewerVisible: any
  viewerSrc: any
  stemEditorRef: any
  mathEditorRef: any
  editingPassage: any
  showOptionsJsonDialog: any
  currentQuestion: any
  rawJsonContent: any
  parsedQuestionsForPreview: any
  editablePreviewData: any
}) {
  const {
    viewerVisible, viewerSrc, stemEditorRef, mathEditorRef, editingPassage,
    showOptionsJsonDialog, currentQuestion, rawJsonContent,
    parsedQuestionsForPreview, editablePreviewData
  } = options

  const openImageViewer = (src: any) => {
    viewerSrc.value = src
    viewerVisible.value = true
  }

  function openMathForStem() {
    mathEditorRef.value?.open('')
  }

  /** 面板确定：插到 Tiptap 光标处（组件内部会 focus 编辑区） */
  function onStemMathInsert(latex: string) {
    if (!latex) return
    stemEditorRef.value?.insertText(latex)
  }

  // 复制原始 JSON
  const copyRawJson = async () => {
    try {
      await navigator.clipboard.writeText(rawJsonContent.value)
      ElMessage.success('JSON 已复制')
    } catch {
      ElMessage.error('复制失败')
    }
  }

  // 编辑材料内容
  const editPassage = () => {
    editingPassage.value = true
  }

  const applyOptionsJson = () => {
    const q = currentQuestion.value
    if (!q) return
    try {
      const parsed = JSON.parse(q.optionsJson)
      if (Array.isArray(parsed)) {
        q.options = parsed.map((item: any) => typeof item === 'string' ? item : item.text || item.value)
        if (q.type === 'single' && q.answer >= q.options.length) q.answer = 0
        if (q.type === 'multiple') q.answer = q.answer.filter((idx: any) => idx < q.options.length)
        showOptionsJsonDialog.value = false
        ElMessage.success('选项已更新')
      } else {
        ElMessage.warning('JSON 必须是一个数组')
      }
    } catch (e) {
      ElMessage.error('JSON 格式错误')
    }
  }

  const onOptionChange = () => {
    const q = currentQuestion.value
    if (q) q.optionsJson = JSON.stringify(q.options)
  }

  // 更新预览数据（当用户编辑时）
  const updatePreviewData = () => {
    // 触发视图更新
    parsedQuestionsForPreview.value = JSON.parse(JSON.stringify(editablePreviewData.value))
  }

  return {
    openImageViewer,
    openMathForStem,
    onStemMathInsert,
    copyRawJson,
    editPassage,
    applyOptionsJson,
    onOptionChange,
    updatePreviewData
  }
}
