import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

/** 题目编辑动作：全屏编辑、删除、选项/小问增删、题型切换和拖拽。 */
export function useQuestionBuilderEdit(options: {
  questions: any
  currentId: any
  currentQuestion: any
  fullEditorVisible: any
  selectedSubType: any
  setTypeFilter: (type: any) => void
  parsedQuestionsForPreview: any
}) {
  const { questions, currentId, currentQuestion, fullEditorVisible, selectedSubType, setTypeFilter, parsedQuestionsForPreview } = options

const openFullEditor = () => {
  if (!currentQuestion.value) {
    ElMessage.warning('请先选择一道题目')
    return
  }
  fullEditorVisible.value = true
}

const handleFullEditorSave = (updatedQuestion) => {
  const index = questions.value.findIndex(q => q.id === currentId.value)
  if (index !== -1) {
    questions.value[index] = { ...questions.value[index], ...updatedQuestion }
    currentId.value = updatedQuestion.id || currentId.value
  }
  ElMessage.success('题目已更新')
}

const removeQuestion = async (id) => {
  const index = questions.value.findIndex(q => q.id === id)
  if (index === -1) return
  const q = questions.value[index]
  try {
    await ElMessageBox.confirm(
      `确定从当前题库移除「${q.title || '这道题'}」吗？保存后才会同步删除。`,
      '删除题目',
      { confirmButtonText: '确定移除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  questions.value.splice(index, 1)
  if (currentId.value === id) currentId.value = questions.value[0]?.id || null
}

const onTypeChange = () => {
  const q = currentQuestion.value
  if (!q) return
  if (q.type === 'composite') {
    if (!q.subQuestions) q.subQuestions = []
    if (q.content === undefined) q.content = ''
  } else if (q.type === 'single' || q.type === 'multiple') {
    if (!q.options) {
      q.options = ['选项A', '选项B']
      q.optionsJson = JSON.stringify(q.options)
    }
    if (q.type === 'single' && typeof q.answer !== 'number') q.answer = 0
    if (q.type === 'multiple' && !Array.isArray(q.answer)) q.answer = []
  } else if (q.type === 'judge') {
    if (typeof q.answer !== 'boolean') q.answer = false
  } else {
    if (typeof q.answer !== 'string') q.answer = ''
  }
}

const addOption = () => {
  const q = currentQuestion.value
  if (!q) return
  if (!q.options) q.options = []
  if (q.options.length >= 6) {
    ElMessage.warning('最多支持6个选项（A-F）')
    return
  }
  q.options.push('')
  syncOptionsJson(q)
}

const removeOption = (index) => {
  const q = currentQuestion.value
  if (!q) return
  if (q.options.length <= 2) {
    ElMessage.warning('至少保留2个选项')
    return
  }
  q.options.splice(index, 1)
  if (q.type === 'single') {
    if (q.answer === index) q.answer = 0
    else if (q.answer > index) q.answer -= 1
  } else if (q.type === 'multiple') {
    q.answer = q.answer.filter(idx => idx !== index).map(idx => idx > index ? idx - 1 : idx)
  }
  syncOptionsJson(q)
}

// 判断是否为组合题预览
const isCompositePreview = computed(() => {
  const data = parsedQuestionsForPreview.value
  return data && !Array.isArray(data) && data.passage && data.questions
})

// 获取子题题型标签类型（Element Plus Tag 的 type）
// 判断子题选项是否正确（用于组合题子题预览）
// 格式化子题答案显示（用于组合题子题预览）
const syncOptionsJson = (q) => { q.optionsJson = JSON.stringify(q.options) }

const addSubQuestionBySelectedType = () => {
  if (!selectedSubType.value) {
    ElMessage.warning('请先选择题型')
    return
  }
  const newSub = createEmptySub(selectedSubType.value)
  currentQuestion.value.subQuestions.push(newSub)
}

const createEmptySub = (type) => {
  const base = {
    id: Date.now() + Math.random(),
    type,
    question: '',
    answer: type === 'single' ? 0 : type === 'multiple' ? [] : type === 'judge' ? false : '',
    score: 2,
    sortOrder: currentQuestion.value.subQuestions.length,
    analysis: ''
  }
  if (type === 'single' || type === 'multiple') {
    base.options = ['选项A', '选项B']
    base.optionsJson = JSON.stringify(base.options)
  }
  return base
}

const removeSubQuestion = (index) => { currentQuestion.value.subQuestions.splice(index, 1) }

const onSubTypeChange = (sub) => {
  if (sub.type === 'single') {
    sub.answer = 0
    if (!sub.options) sub.options = ['选项A', '选项B']
    if (!sub.optionsJson) sub.optionsJson = JSON.stringify(sub.options)
  } else if (sub.type === 'multiple') {
    sub.answer = []
    if (!sub.options) sub.options = ['选项A', '选项B']
    if (!sub.optionsJson) sub.optionsJson = JSON.stringify(sub.options)
  } else if (sub.type === 'judge') {
    sub.answer = false
    sub.options = []
    sub.optionsJson = ''
  } else {
    sub.answer = ''
    sub.options = []
    sub.optionsJson = ''
  }
}

const parseSubOptions = (sub) => {
  if (!sub.optionsJson) return
  try {
    const parsed = JSON.parse(sub.optionsJson)
    if (Array.isArray(parsed)) sub.options = parsed.map(item => typeof item === 'string' ? item : item.text || item.value)
  } catch (e) {
    ElMessage.warning('子题选项格式错误')
  }
}

// 题型点击/拖拽判断
let typeMouseDownPos = null
let typeMouseDownTime = 0
let isTypeDragging = false

const onTypeMouseDown = (e, element) => {
  typeMouseDownPos = { x: e.clientX, y: e.clientY }
  typeMouseDownTime = Date.now()
  isTypeDragging = false
}

const onTypeMouseUp = (e, element) => {
  if (isTypeDragging) return  // 已经触发了拖拽，忽略

  const pos = typeMouseDownPos
  if (!pos) return

  // 计算移动距离
  const dx = Math.abs(e.clientX - pos.x)
  const dy = Math.abs(e.clientY - pos.y)
  const elapsed = Date.now() - typeMouseDownTime

  // 如果移动距离小于 5px 且时间小于 300ms，认为是点击
  if (dx < 5 && dy < 5 && elapsed < 300) {
    setTypeFilter(element.type)
  }

  typeMouseDownPos = null
}

let lastDraggedType = null
const onTypeDragStart = (evt, typeItem) => {
  lastDraggedType = typeItem.type
  isTypeDragging = true  // 标记正在拖拽
}
const onSubDragAdd = () => {
  if (lastDraggedType) {
    const newSub = createEmptySub(lastDraggedType)
    currentQuestion.value.subQuestions.push(newSub)
    lastDraggedType = null
  }
}
const onSubDragEnd = () => { }
const onDragEnd = () => { }



  return {
    openFullEditor,
    handleFullEditorSave,
    removeQuestion,
    onTypeChange,
    addOption,
    removeOption,
    isCompositePreview,
    addSubQuestionBySelectedType,
    removeSubQuestion,
    onSubTypeChange,
    parseSubOptions,
    onTypeMouseDown,
    onTypeMouseUp,
    onTypeDragStart,
    onSubDragAdd,
    onSubDragEnd,
    onDragEnd
  }
}
