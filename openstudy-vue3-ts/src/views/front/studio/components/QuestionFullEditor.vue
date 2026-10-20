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
              <el-radio v-for="(opt, idx) in question.options" :key="idx" :value="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="question.type === 'multiple'" v-model="question.answer">
              <el-checkbox v-for="(opt, idx) in question.options" :key="idx" :value="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-checkbox>
            </el-checkbox-group>
            <el-radio-group v-else-if="question.type === 'judge'" v-model="question.answer">
              <el-radio :value="true">正确</el-radio>
              <el-radio :value="false">错误</el-radio>
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
                          <el-radio :value="true">正确</el-radio>
                          <el-radio :value="false">错误</el-radio>
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
/*
 * ⚠️ 这段样式曾经**完全没生效**（2026-10-20 修「子题没有滚动条」的真根因）
 *
 * 原写法有两个错误：
 *   ① `.full-editor-dialog { :deep(.el-dialog) { ... } }`
 *      —— class 加在 el-dialog **自己身上**（DOM 是 div.el-dialog.full-editor-dialog），
 *         所以 `:deep(.el-dialog)` 是"自己里面的自己" → 永远匹配 0 个。
 *   ② 改成 `.full-editor-dialog.el-dialog { ... }` 后仍不生效：
 *      scoped 会给整条选择器末尾补 `[data-v-xxx]`，
 *      而 dialog 根元素由 Element Plus 内部渲染、**不带本组件的哈希**。
 *
 * 更隐蔽的一点（有编译产物为证）：嵌套在 SCSS 里的 `:deep()` 在 scoped 转换中
 * 没被正确编译，产物里字面留着 `:deep(...)`，浏览器根本不认。
 *
 * 最终解法：
 *   · dialog 自身尺寸/滚动 → 文件末尾的**非 scoped** 样式块
 *     （选择器 `.full-editor-dialog.el-dialog`，已验证出现在构建产物里）；
 *   · 内部元素样式 → 用 `.full-editor-content` 作锚点（见下）。
 *     它一定带 scoped 哈希、一定是 dialog 的后代，稳妥。
 */
.full-editor-content {
  :deep(.el-dialog__body) {
    flex: 1;
    /*
     * `min-height: 0` 是 flex 子项能滚动的**必要条件**：
     * flex 子项默认 `min-height: auto`（不会小于内容高度），
     * 于是内容多高它就多高，`overflow-y: auto` 形同虚设。
     */
    min-height: 0;
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
          /*
           * ⚠️ 原来是 `overflow: hidden`（2026-10-20 修「子题内容超出看不到」）
           *
           * 用户口径：「子题的完整题目编辑对话框里面 组合题里面 子题没有滚动条
           *   导致内容超出无法看到完整的子题」
           *
           * 根因：`overflow: hidden` 会把超出卡片高度的内容**直接裁掉**，
           * 而且不产生滚动条 —— 用户看不到被裁掉的那部分，也无从滚动。
           * 一张子题卡里有题干编辑器 + 选项列表 + 答案 + 解析，
           * 很容易超过对话框 70vh 给它的份额。
           *
           * 改成 `visible`：让内容自然撑开高度，由外层 `.el-dialog__body`
           * 的 `overflow-y: auto` 统一滚动。
           *
           * 为什么不让卡片自己滚：卡片内已有 Tiptap 编辑器，
           * 编辑器内部本身就会滚动/自适应高度；再套一层滚动容器，
           * 鼠标滚轮会先滚卡片、到边界才滚外层，形成"滚动陷阱"，
           * 手感非常差。**整个对话框一个滚动条**是最稳的解法。
           */
          overflow: visible;

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

<!--
  非 scoped 样式块：专门处理 el-dialog 的尺寸与滚动（2026-10-20）

  ⚠️ 为什么要单独开一个**不带 scoped** 的块：

  1. `class="full-editor-dialog"` 落在 Element Plus 的 dialog 根元素上
     （实测 DOM：`div.el-dialog.full-editor-dialog`）。

  2. `scoped` 会给选择器补 `[data-v-xxxxx]` 属性哈希，
     但那个根元素由 **Element Plus 内部** 渲染，不带本组件的哈希 ——
     无论是 `.full-editor-dialog { :deep(...) }`、`.full-editor-dialog.el-dialog`
     还是 `:deep(.full-editor-dialog.el-dialog)`，实测都匹配不上
     （dialog 高度一直是内容撑开的 1350px、body 的 overflow-y 一直是 visible，
      直接证据是我用 CDP 读 getComputedStyle 拿到的值）。

  3. 与其和 scope 机制较劲，不如**用明确的命名空间避免污染**：
     所有规则都以 `.full-editor-dialog` 开头，它只在这个组件里出现，
     全局写也不会影响别处。这是 Vue 官方也认可的逃生方式。

  这样 `height: 70vh` / `overflow-y: auto` / `min-height: 0` 才真正生效，
  子题超出时对话框内部出现滚动条，用户能看到完整内容。
-->
<style lang="scss">
.full-editor-dialog.el-dialog {
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
  overflow: hidden;

  .el-dialog__header {
    flex-shrink: 0;
    padding: 14px 20px;
    border-bottom: 1px solid #e4e7ed;
    margin-right: 0;
  }

  .el-dialog__body {
    flex: 1;
    /* flex 子项能滚动的必要条件，默认 auto 会让它被内容撑高 */
    min-height: 0;
    overflow-y: auto;
    padding: 16px 20px;
  }

  .el-dialog__footer {
    flex-shrink: 0;
    border-top: 1px solid #e4e7ed;
    padding: 12px 20px;
  }
}
</style>