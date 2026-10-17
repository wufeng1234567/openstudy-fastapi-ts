<template>
  <el-dialog v-model="visible" title="完整题目编辑" width="65%" top="5vh" :close-on-click-modal="false"
    class="full-editor-dialog" :show-close="true" @close="handleClose">
    <div class="full-editor-content">
      <el-form label-position="top" size="default">
        <el-form-item label="题型">
          <el-select v-model="question.type" @change="onTypeChange" style="width: 100%">
            <el-option label="单选题" value="single" />
            <el-option label="多选题" value="multiple" />
            <el-option label="判断题" value="judge" />
            <el-option label="填空题" value="fill" />
            <el-option label="简答题" value="essay" />
            <el-option label="组合题（含子题）" value="composite" />
          </el-select>
        </el-form-item>

        <el-form-item label="题干">
          <div class="full-tiptap-wrapper">
            <TiptapEditor v-model="question.title" placeholder="请输入题目内容，支持图片上传" @preview-image="openImageViewer" />
          </div>
        </el-form-item>

        <template v-if="['single', 'multiple', 'judge'].includes(question.type)">
          <el-form-item v-if="question.type !== 'judge'" label="选项列表">
            <div class="options-visual-editor">
              <div v-for="(opt, idx) in question.options" :key="idx" class="option-item">
                <span class="option-letter">{{ String.fromCharCode(65 + idx) }}.</span>
                <el-input v-model="question.options[idx]" placeholder="请输入选项内容" size="small" style="flex: 1" />
                <el-button type="danger" text size="small" @click="removeOption(idx)"
                  :disabled="question.options.length <= 2">
                  <el-icon>
                    <Delete />
                  </el-icon>
                </el-button>
              </div>
              <el-button v-if="question.options.length < 6" type="primary" text size="small" @click="addOption">
                <el-icon>
                  <Plus />
                </el-icon> 添加选项 (最多6个)
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="正确答案">
            <el-radio-group v-if="question.type === 'single'" v-model="question.answer">
              <el-radio v-for="(opt, idx) in question.options" :key="idx" :label="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="question.type === 'multiple'" v-model="question.answer">
              <el-checkbox v-for="(opt, idx) in question.options" :key="idx" :label="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-checkbox>
            </el-checkbox-group>
            <el-radio-group v-else-if="question.type === 'judge'" v-model="question.answer">
              <el-radio :label="true">正确</el-radio>
              <el-radio :label="false">错误</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>

        <template v-if="question.type === 'fill' || question.type === 'essay'">
          <el-form-item label="正确答案">
            <el-input v-model="question.answer" placeholder="请输入正确答案" />
          </el-form-item>
        </template>

        <template v-if="question.type === 'composite'">
          <el-form-item label="材料/文章内容">
            <div class="full-tiptap-wrapper composite-tiptap">
              <TiptapEditor v-model="question.content" placeholder="请输入文章或材料内容。可使用 ___1___、___2___ 等占位符" @preview-image="openImageViewer" />
            </div>
          </el-form-item>

          <el-form-item label="子题管理">
            <div class="sub-questions-container">
              <div class="sub-toolbar">
                <el-select v-model="selectedSubType" placeholder="选择题型" size="small" style="width: 120px" clearable>
                  <el-option label="单选题" value="single" />
                  <el-option label="多选题" value="multiple" />
                  <el-option label="判断题" value="judge" />
                  <el-option label="填空题" value="fill" />
                  <el-option label="简答题" value="essay" />
                </el-select>
                <el-button type="primary" size="small" @click="addSubQuestion">添加子题</el-button>
              </div>
              <div class="sub-list">
                <div v-for="(sub, idx) in question.subQuestions" :key="sub.id" class="sub-question-card">
                  <div class="card-header">
                    <div class="header-left">
                      <span class="sub-index">子题 {{ idx + 1 }}</span>
                      <el-select v-model="sub.type" size="small" style="width: 100px">
                        <el-option label="单选" value="single" />
                        <el-option label="多选" value="multiple" />
                        <el-option label="判断" value="judge" />
                        <el-option label="填空" value="fill" />
                        <el-option label="简答" value="essay" />
                      </el-select>
                    </div>
                    <div class="header-right">
                      <el-input-number v-model="sub.score" :min="1" :max="100" size="small" style="width: 90px" />
                      <el-button type="danger" text size="small" @click="removeSubQuestion(idx)">
                        <el-icon>
                          <Delete />
                        </el-icon>
                      </el-button>
                    </div>
                  </div>
                  <div class="card-body">
                    <div class="field-item field-full">
                      <label class="field-label">题干</label>
                      <div class="sub-tiptap-wrapper">
                        <TiptapEditor v-model="sub.question" placeholder="子题题干，支持图片上传" @preview-image="openImageViewer" />
                      </div>
                    </div>
                    <template v-if="['single', 'multiple'].includes(sub.type)">
                      <div class="field-item">
                        <label class="field-label">选项</label>
                        <div class="options-inline">
                          <div v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx" class="option-row">
                            <span class="option-letter">{{ String.fromCharCode(65 + optIdx) }}.</span>
                            <el-input v-model="sub.options[optIdx]" placeholder="选项内容" size="small" style="flex: 1" />
                            <el-button type="danger" text size="small" @click="removeSubOption(sub, optIdx)"
                              :disabled="(sub.options || []).length <= 2">
                              <el-icon>
                                <Delete />
                              </el-icon>
                            </el-button>
                          </div>
                          <el-button type="primary" text size="small" @click="addSubOption(sub)"
                            :disabled="(sub.options || []).length >= 6">
                            <el-icon>
                              <Plus />
                            </el-icon> 添加选项
                          </el-button>
                        </div>
                      </div>
                    </template>
                    <div class="field-item">
                      <label class="field-label">正确答案</label>
                      <template v-if="sub.type === 'single'">
                        <el-select v-model="sub.answer" size="small" style="width: 100%">
                          <el-option v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx"
                            :label="`${String.fromCharCode(65 + optIdx)}. ${opt}`" :value="optIdx" />
                        </el-select>
                      </template>
                      <template v-else-if="sub.type === 'multiple'">
                        <el-select v-model="sub.answer" multiple size="small" style="width: 100%">
                          <el-option v-for="(opt, optIdx) in (sub.options || [])" :key="optIdx"
                            :label="`${String.fromCharCode(65 + optIdx)}. ${opt}`" :value="optIdx" />
                        </el-select>
                      </template>
                      <template v-else-if="sub.type === 'judge'">
                        <el-radio-group v-model="sub.answer" size="small">
                          <el-radio :label="true">正确</el-radio>
                          <el-radio :label="false">错误</el-radio>
                        </el-radio-group>
                      </template>
                      <template v-else>
                        <el-input v-model="sub.answer" placeholder="请输入正确答案" size="small" />
                      </template>
                    </div>
                    <div class="field-item">
                      <label class="field-label">解析</label>
                      <el-input v-model="sub.analysis" type="textarea" :rows="1" placeholder="答案解析（选填）" size="small" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </el-form-item>
        </template>

        <el-form-item label="答案解析">
          <el-input v-model="question.analysis" type="textarea" :rows="1" placeholder="请输入答案解析" />
        </el-form-item>

        <el-form-item label="分值">
          <el-input-number v-model="question.score" :min="1" :max="100" size="small" />
        </el-form-item>
      </el-form>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </div>
    </template>
  </el-dialog>

  <ImageViewer v-model:visible="viewerVisible" :src="viewerSrc" />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import TiptapEditor from '@/components/TiptapEditor/index.vue'
import ImageViewer from '@/components/PracticeComponent/ImageViewer.vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  questionData: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update:modelValue', 'save'])

const visible = ref(props.modelValue)
const question = ref({})
const selectedSubType = ref('single')

const viewerVisible = ref(false)
const viewerSrc = ref('')

const openImageViewer = (src) => {
  viewerSrc.value = src
  viewerVisible.value = true
}

watch(() => props.modelValue, (val) => {
  visible.value = val
  if (val && props.questionData) {
    question.value = JSON.parse(JSON.stringify(props.questionData))
  }
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

const handleClose = () => {
  visible.value = false
}

const handleSave = () => {
  emit('save', question.value)
  visible.value = false
  ElMessage.success('题目已保存')
}

const addOption = () => {
  if (!question.value.options) question.value.options = []
  if (question.value.options.length >= 6) {
    ElMessage.warning('最多支持6个选项（A-F）')
    return
  }
  question.value.options.push('')
}

const removeOption = (index) => {
  if (question.value.options.length <= 2) {
    ElMessage.warning('至少保留2个选项')
    return
  }
  question.value.options.splice(index, 1)
  if (question.value.type === 'single') {
    if (question.value.answer === index) question.value.answer = 0
    else if (question.value.answer > index) question.value.answer -= 1
  } else if (question.value.type === 'multiple') {
    question.value.answer = question.value.answer
      .filter(idx => idx !== index)
      .map(idx => idx > index ? idx - 1 : idx)
  }
}

const addSubQuestion = () => {
  if (!question.value.subQuestions) question.value.subQuestions = []
  const newSub = {
    id: Date.now() + Math.random(),
    type: selectedSubType.value || 'single',
    question: '',
    answer: selectedSubType.value === 'single' ? 0 :
      selectedSubType.value === 'multiple' ? [] :
        selectedSubType.value === 'judge' ? false : '',
    score: 2,
    analysis: '',
    options: ['选项A', '选项B']
  }
  question.value.subQuestions.push(newSub)
}

const addSubOption = (sub) => {
  if (Array.isArray(sub.options) && sub.options.length < 6) {
    sub.options.push(`选项${String.fromCharCode(65 + sub.options.length)}`)
  }
}

const removeSubOption = (sub, index) => {
  if (Array.isArray(sub.options) && sub.options.length > 2) {
    sub.options.splice(index, 1)
  }
}

const removeSubQuestion = (index) => {
  question.value.subQuestions.splice(index, 1)
}

const onTypeChange = () => {
  if (question.value.type === 'composite') {
    if (!question.value.subQuestions) question.value.subQuestions = []
    if (question.value.content === undefined) question.value.content = ''
  } else if (question.value.type === 'single' || question.value.type === 'multiple') {
    if (!question.value.options) {
      question.value.options = ['选项A', '选项B']
    }
    if (question.value.type === 'single' && typeof question.value.answer !== 'number') question.value.answer = 0
    if (question.value.type === 'multiple' && !Array.isArray(question.value.answer)) question.value.answer = []
  } else if (question.value.type === 'judge') {
    if (typeof question.value.answer !== 'boolean') question.value.answer = false
  } else {
    if (typeof question.value.answer !== 'string') question.value.answer = ''
  }
}
</script>

<style scoped lang="scss">
.full-editor-dialog {
  :deep(.el-dialog) {
    position: fixed;
    top: 5vh;
    left: 50%;
    transform: translateX(-50%);
    border-radius: var(--os-radius);
    display: flex;
    flex-direction: column;
    height: 70vh;
    max-height: 70vh;
    max-width: 65%;
  }

  :deep(.el-dialog__body) {
    flex: 1;
    overflow-y: auto;
    padding: 16px 20px;
  }

  :deep(.el-dialog__footer) {
    border-top: 1px solid #e4e7ed;
    padding: 12px 20px;
    flex-shrink: 0;
  }

  :deep(.el-dialog__header) {
    flex-shrink: 0;
    padding: 14px 20px;
    border-bottom: 1px solid #e4e7ed;
    margin-right: 0;
  }

  .full-editor-content {
    padding: 4px;

    .el-form-item {
      margin-bottom: 14px;
    }

    .options-visual-editor {
      .option-item {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;

        .option-letter {
          width: 24px;
          font-weight: bold;
          color: var(--os-accent);
        }
      }
    }

    .sub-questions-container {
      border: 1px solid var(--os-border);
      border-radius: var(--os-radius);
      padding: 12px;
      background: var(--dsw-static-neutral-bluish-50);

      .sub-toolbar {
        display: flex;
        gap: 12px;
        margin-bottom: 12px;
        align-items: center;
        flex-wrap: wrap;

        :deep(.el-select) {
          .el-input__wrapper {
            border-radius: 8px;
          }
        }
      }

      .sub-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 12px;

        .sub-question-card {
          background: #fff;
          border-radius: var(--os-radius);
          border: 1px solid var(--os-border);
          box-shadow: none;
          transition: background-color var(--ds-duration-fast) var(--ds-ease-in-out), border-color var(--ds-duration-fast) var(--ds-ease-in-out), color var(--ds-duration-fast) var(--ds-ease-in-out);
          overflow: hidden;

          &:hover {
            box-shadow: none;
            border-color: var(--os-border-strong);
          }

          .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 14px;
            background: linear-gradient(to right, #f8f9fa, #fff);
            border-bottom: 1px solid var(--os-bg-hover);

            .header-left {
              display: flex;
              align-items: center;
              gap: 12px;

              .sub-index {
                font-weight: 600;
                color: var(--os-text);
                font-size: 14px;
              }
            }

            .header-right {
              display: flex;
              align-items: center;
              gap: 8px;
            }
          }

          .card-body {
            padding: 12px 14px;

            .field-item {
              margin-bottom: 10px;

              &.field-full {
                width: 100%;
              }

              .field-label {
                display: block;
                font-size: 12px;
                color: var(--os-text-3);
                font-weight: 500;
                margin-bottom: 4px;
              }
            }

            .options-inline {
              .option-row {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 6px;

                &:last-child {
                  margin-bottom: 0;
                }

                .option-letter {
                  width: 20px;
                  font-weight: 600;
                  color: var(--os-accent);
                  font-size: 13px;
                }
              }
            }
          }
        }
      }
    }
  }

  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }

  .full-tiptap-wrapper {
    width: 100%;
    :deep(.tiptap-editor) {
      min-height: 120px;
      border-radius: 8px;
    }
    :deep(.editor-content) {
      padding: 10px 14px;
      min-height: 80px;
    }
  }

  .composite-tiptap {
    :deep(.tiptap-editor) {
      min-height: 180px;
    }
  }

  .sub-tiptap-wrapper {
    margin-bottom: 8px;
    :deep(.tiptap-editor) {
      min-height: 80px;
      border-radius: 8px;
      border-color: var(--os-border);
    }
    :deep(.editor-toolbar) {
      padding: 4px 6px;
      .toolbar-btn {
        width: 26px;
        height: 26px;
      }
    }
    :deep(.editor-content) {
      padding: 8px 12px;
      min-height: 50px;
      font-size: 14px;
    }
  }
}
</style>
