import { computed, ref } from 'vue'

/** AI 出题表单的默认值、深度思考状态、模型选择和校验规则。 */
export function useQuestionBuilderAiForm() {
  const deepThink = ref(localStorage.getItem('openstudy_ai_thinking') === '1')
  const createDefaultAiForm = () => ({
    questionType: 'single',
    knowledgePoint: '',
    count: 3,
    model: '',
    compositeRequirement: '',
    wordCount: 200,
    subCount: 5,
    kbIds: [],
    customRequirement: ''
  })
  const aiForm = ref(createDefaultAiForm())
  const selectedConfigId = ref(null)
  const onModelSelect = (cfg: any) => {
    selectedConfigId.value = cfg?.configId ?? null
  }

  const aiRules = computed(() => {
    if (aiForm.value.questionType === 'composite') {
      return {
        questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
        compositeRequirement: [
          { required: true, message: '请输入文章主题或出题要求', trigger: 'blur' },
          { max: 200, message: '不能超过200个字符', trigger: 'blur' }
        ]
      }
    }
    if (aiForm.value.questionType === 'custom') {
      return {
        questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
        customRequirement: [
          { required: true, message: '请描述你要出什么题', trigger: 'blur' },
          { max: 500, message: '不能超过500个字符', trigger: 'blur' }
        ]
      }
    }
    return {
      questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
      knowledgePoint: [
        { required: true, message: '请输入知识点', trigger: 'blur' },
        { max: 200, message: '不能超过200个字符', trigger: 'blur' }
      ],
      count: [{ required: true, message: '请选择数量', trigger: 'change' }]
    }
  })

  return { aiForm, deepThink, selectedConfigId, onModelSelect, aiRules, createDefaultAiForm }
}
