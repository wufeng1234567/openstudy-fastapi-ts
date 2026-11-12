import { watch } from 'vue'

/** AI 出题弹窗打开、快捷键和上下文预加载。 */
export function useQuestionBuilderAiDialog(options: {
  aiDialogVisible: any
  aiGenerating: any
  aiForm: any
  createDefaultAiForm: () => any
  handleAiGenerate: () => void
  materialItems: any
  materialParsing: any
  rawJsonContent: any
  parsedQuestionsForPreview: any
  editablePreviewData: any
  pendingImportData: any
  loadPromptHistory: () => void
  loadBankContextInfo: () => void
  loadUserAiConfigs: () => void
  kbList: any
  loadKnowledgeBases: (opts?: any) => void
}) {
  const {
    aiDialogVisible, aiGenerating, aiForm, createDefaultAiForm, handleAiGenerate,
    materialItems, materialParsing, rawJsonContent, parsedQuestionsForPreview,
    editablePreviewData, pendingImportData, loadPromptHistory, loadBankContextInfo,
    loadUserAiConfigs, kbList, loadKnowledgeBases
  } = options

// ==================== 键盘快捷键 ====================
const handleKeydown = (e) => {
  if (!aiDialogVisible.value) return

  // Ctrl+Enter 开始生成
  if (e.ctrlKey && e.key === 'Enter' && !aiGenerating.value) {
    e.preventDefault()
    handleAiGenerate()
  }
}

// 监听对话框状态，添加/移除键盘事件
watch(aiDialogVisible, (val) => {
  if (val) {
    window.addEventListener('keydown', handleKeydown)
  } else {
    window.removeEventListener('keydown', handleKeydown)
  }
})

// 修改打开弹窗的方法，加载上下文
const openAiDialog = () => {
  /*
   * ⚠️⚠️ 这里必须与 `aiForm` 的初始声明保持**同一份字段集**（2026-10-20 踩过）。
   *
   * 这是「整体替换」而不是"逐个字段赋值"，所以任何在声明里加了、
   * 但这里漏掉的字段，都会在**每次打开弹窗时被静默抹掉**。
   *
   * 我当时只改了上面的声明（加了 kbIds / customRequirement），
   * 没同步这里，结果：
   *   · 改后的代码静态检查全过（字段确实在文件里）；
   *   · 但运行时 `Object.keys(aiForm)` 永远是 7 个旧字段；
   *   · 素材面板的 `v-if="aiForm.questionType === 'custom'"` 能进，
   *     可 `v-model="aiForm.kbIds"` 绑到一个不存在的属性上 ——
   *     表现就是"选中素材出题后，面板不出现/不工作"。
   * 排查花了一小时，因为"源码有、运行时没有"这个现象很容易被误判成
   * dev server 缓存问题（我一开始也确实这么怀疑）。
   *
   * 教训：**这类"初始化字面量"在文件里出现几次，就必须改几次。**
   * 如果以后字段继续增加，考虑抽成一个 `createDefaultAiForm()` 工厂函数，
   * 从根上消除这份重复。
   */
  /*
   * ⚠️ 用工厂函数，不要手写字面量（2026-10-20 踩过）：
   *   这里是「整体替换」`aiForm.value`，任何在 `createDefaultAiForm()` 里
   *   加了、这里却漏掉的字段，都会在每次打开弹窗时被静默抹掉 ——
   *   表现为"源码有、运行时没有"，极难排查。详见该工厂函数的注释。
   */
  aiForm.value = {
    ...createDefaultAiForm(),
    // 只有这里的 model 带记忆（上一次用的模型），其余走默认值
    model: localStorage.getItem('openstudy_ai_model_question-builder') || ''
  }
  /*
   * 每次打开弹窗都清空素材。
   *
   * 为什么**图片也一起清**：
   *   图片是压缩后的 data URL，体积可观（几百 KB 一张）。
   *   跨会话保留它们会白白占内存，而且用户很可能已经忘了上次挂过什么图
   *   —— 拿旧图出新题是比"要重传一次"更糟的体验。
   */
  materialItems.value = []
  materialParsing.value = false
  rawJsonContent.value = ''
  parsedQuestionsForPreview.value = null
  editablePreviewData.value = null
  pendingImportData.value = null
  aiGenerating.value = false
  aiDialogVisible.value = true
  loadPromptHistory()

  // 加载题库上下文
  loadBankContextInfo()
  loadUserAiConfigs()
  /*
   * 预加载知识库列表（2026-10-20 修「第一次进入获取不到，必须点刷新」）
   *
   * 根因：`loadKnowledgeBases` 上一轮重构后**一次都没有被自动调用** ——
   *   我把它从 `onAiTypeChange` 里删掉了（当时改成"展开素材面板才需要"），
   *   结果只剩模板上那个「刷新」按钮会调它。
   *   用户第一次打开弹窗、展开素材、点开下拉 → 列表是空的，必须手动点一次刷新。
   *   这属于"功能能用但要多点一下"的隐性缺陷，比直接报错更烦人。
   *
   * 为什么在**打开弹窗时**就加载、而不是等展开素材面板：
   *   · 一次请求很轻（就是个列表），没必要为省这点流量牺牲首屏体验；
   *   · 素材面板可以随时展开，等展开再请求会让用户先看到一个空下拉；
   *   · 与 `loadUserAiConfigs()`（模型列表）同一时机，语义一致：
   *     "打开弹窗就把可选项准备好"。
   *
   * 失败不阻断：`loadKnowledgeBases` 内部已 catch 并提示"可改用上传文档"。
   */
  if (kbList.value.length === 0) {
    // silent: 弹窗刚打开就弹"加载失败"很吵，且用户此刻未必想用知识库
    loadKnowledgeBases({ silent: true })
  }
}



  return { handleKeydown, openAiDialog }
}
