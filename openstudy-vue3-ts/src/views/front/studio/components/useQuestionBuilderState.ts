import { ref, computed } from 'vue'

/**
 * QuestionBuilder.vue 的本地响应式状态。
 *
 * 从 SFC 抽出的纯状态声明（ref / 一个派生 computed），不含任何业务逻辑、
 * 事件监听或生命周期。SFC 通过解构把这些名字重新暴露给模板与其它 composable，
 * 因此所有调用点与模板绑定保持不变。
 *
 * 注意：`watch(questions, ..., { immediate: true })` 仍留在 SFC —— 它属于
 * 「题目列表变化自动选中第一题」的事件时序，不在本模块职责内。
 */
export function useQuestionBuilderState() {
  // 视图模式：'raw' 显示原始JSON文本，'pretty' 显示美化卡片
  const viewMode = ref('pretty')
  const parsedQuestionsForPreview = ref<any>(null)
  const rawJsonContent = ref('') // 原始 JSON 内容

  // 题目列表
  const questions = ref<any[]>([])
  const currentId = ref(null)

  // 可编辑预览数据（深拷贝，用于用户编辑）
  const editablePreviewData = ref<any>(null)

  // 编辑状态
  const editingPassage = ref(false)

  // 搜索与分页
  const searchKeyword = ref('')
  const currentPage = ref(1)
  const pageSize = ref(10)

  // 选项 JSON 高级编辑对话框
  const showOptionsJsonDialog = ref(false)

  // 全屏编辑弹窗
  const fullEditorVisible = ref(false)

  // 图片预览
  const viewerVisible = ref(false)
  const viewerSrc = ref('')

  /* ===== 公式编辑（2026-10-27）=====
     Tiptap 是富文本，公式以 `$...$` 源码形式存进 HTML（导出/练习时由统一管线渲染）。
     点「ƒx」→ 符号面板（鼠标操作）→ 确定后插到 Tiptap 光标处。 */
  const stemEditorRef = ref<any>(null)
  const mathEditorRef = ref<any>(null)

  const currentQuestion = computed(() => questions.value.find((q) => q?.id === currentId.value))
  const selectedSubType = ref('single')
  const aiDialogVisible = ref(false)
  const aiFormRef = ref(null)

  return {
    viewMode,
    parsedQuestionsForPreview,
    rawJsonContent,
    questions,
    currentId,
    editablePreviewData,
    editingPassage,
    searchKeyword,
    currentPage,
    pageSize,
    showOptionsJsonDialog,
    fullEditorVisible,
    viewerVisible,
    viewerSrc,
    stemEditorRef,
    mathEditorRef,
    currentQuestion,
    selectedSubType,
    aiDialogVisible,
    aiFormRef
  }
}
