import { ElMessageBox } from 'element-plus'

/**
 * 一键恢复与 AI 出题弹窗的交互动作。
 *
 * 从 QuestionBuilder.vue 抽出：恢复确认、题型切换重置、关闭弹窗重置。
 * 依赖以 ref 形式从 options 传入，返回的三个函数仍以原名暴露给模板。
 */
export function useQuestionBuilderDialogActions(options: {
  props: any
  emit: any
  aiForm: any
  rawJsonContent: any
  parsedQuestionsForPreview: any
  editablePreviewData: any
  pendingImportData: any
  aiGenerating: any
  viewMode: any
  aiDialogVisible: any
}) {
  const {
    props, emit, aiForm, rawJsonContent, parsedQuestionsForPreview,
    editablePreviewData, pendingImportData, aiGenerating, viewMode, aiDialogVisible
  } = options

  // 一键恢复：先弹确认框，用户确认后才通知父组件执行恢复
  // 有当前题库时恢复该题库的原始数据（bankId 动态跟随用户切换的题库）；无题库时恢复初始状态
  const handleRestore = async () => {
    const hasBank = !!props.bankId
    const message = hasBank
      ? '将丢弃当前未保存的修改，恢复至该题库的原始数据，是否继续？'
      : '当前尚未绑定题库，将清空所有未保存的题目并恢复初始状态，是否继续？'
    try {
      await ElMessageBox.confirm(message, '一键恢复确认', {
        confirmButtonText: '确认恢复',
        cancelButtonText: '取消',
        type: 'warning'
      })
      emit('reset')
    } catch {
      // 用户取消，不做任何操作
    }
  }

  const onAiTypeChange = () => {
    /*
     * 切换题型时**不清空参考素材**（知识库 kbIds / 已解析文档 materialDocs）。
     *
     * 2026-10-20 用户明确要求「知识库和文档应该是一个全局共用 无论是哪种题型
     * 都可以用到」—— 既然是全局附加项，它就不属于某一个题型，
     * 切题型把它清掉在语义上是矛盾的（用户从单选切到判断，
     * 难道"我刚才上传的讲义"就不算数了？）。
     *
     * 清空的是**题型专属的输入**：知识点 / 组合题要求。
     * 那是"这一次要生成的内容"，换了题型确实该重填。
     */
    if (aiForm.value.questionType === 'composite') {
      aiForm.value.compositeRequirement = ''
      aiForm.value.wordCount = 200
      aiForm.value.subCount = 5
    } else if (aiForm.value.questionType === 'custom') {
      // 自定义出题：需求描述由用户自己写，这里只清掉固定题型的知识点
      aiForm.value.knowledgePoint = ''
    } else {
      aiForm.value.knowledgePoint = ''
      aiForm.value.count = 3
    }
    // 清空预览数据
    rawJsonContent.value = ''
    parsedQuestionsForPreview.value = null
    editablePreviewData.value = null
  }

  const onAiDialogClose = () => {
    // 清空所有数据
    rawJsonContent.value = ''
    parsedQuestionsForPreview.value = null
    editablePreviewData.value = null
    pendingImportData.value = null
    aiGenerating.value = false
    viewMode.value = 'pretty'
    aiDialogVisible.value = false
  }

  return { handleRestore, onAiTypeChange, onAiDialogClose }
}
