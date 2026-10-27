<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="所属题库" prop="bankId">
        <el-select v-model="queryParams.bankId" placeholder="请选择题库" clearable filterable style="width: 200px">
                <el-option v-for="bank in bankOptions" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
        </el-select>
      </el-form-item>
      <el-form-item label="题型" prop="questionType">
        <el-select v-model="queryParams.questionType" placeholder="请选择题型" clearable style="width: 120px">
          <el-option v-for="d in typeDict" :key="d.value" :label="d.label" :value="editorTypeToNum(d.value)" />
        </el-select>
      </el-form-item>
      <el-form-item label="难度" prop="difficulty">
        <el-select v-model="queryParams.difficulty" placeholder="请选择难度" clearable style="width: 120px">
          <el-option v-for="d in difficultyDict" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="请选择状态" clearable style="width: 100px">
          <el-option v-for="d in common_status" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="题干" prop="keyword">
        <el-input v-model="queryParams.keyword" placeholder="题干关键词" clearable style="width: 180px" @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="创建时间" prop="createTime">
        <el-date-picker clearable v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
          range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" style="width: 240px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['questionMain:questionMain:add']">新增题目</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success" plain icon="Edit" :disabled="single" @click="handleEditCurrent" v-hasPermi="['questionMain:questionMain:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger" plain icon="Delete" :disabled="multiple" @click="handleDelete" v-hasPermi="['questionMain:questionMain:remove']">删除</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="questionMainList" @selection-change="handleSelectionChange" row-key="id">
      <el-table-column type="selection" width="50" align="center" />
      <el-table-column label="ID" align="center" prop="id" width="70" />
      <el-table-column label="题型" align="center" prop="questionType" width="80">
        <template #default="scope">
          <el-tag :type="getTypeTagType(scope.row.questionType)" size="small">
            {{ getTypeName(scope.row.questionType) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="题干" align="center" prop="questionText" show-overflow-tooltip min-width="200" />
      <el-table-column label="难度" align="center" prop="difficulty" width="70">
        <template #default="scope">
          <span :style="{ color: difficultyColor(scope.row.difficulty) }">
            {{ difficultyLabel(scope.row.difficulty) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="分值" align="center" prop="score" width="70" />
      <el-table-column label="所属题库" align="center" min-width="140">
        <template #default="scope">
          {{ getBankName(scope.row.bankId) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" prop="status" width="70">
        <template #default="scope">
          <dict-tag :options="common_status" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" align="center" prop="createTime" width="170">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="180">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleEdit(scope.row)" v-hasPermi="['questionMain:questionMain:edit']">编辑</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['questionMain:questionMain:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="750px" top="3vh" append-to-body
      :close-on-click-modal="false" class="question-editor-dialog" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" size="default">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="题型" prop="questionType">
              <div style="display:flex; gap:4px; width:100%">
                <el-select v-model="form.questionType" @change="onTypeChange" style="flex:1">
                  <el-option v-for="d in typeDict" :key="d.value" :label="d.label" :value="d.value" />
                </el-select>
                <el-button :icon="Setting" @click="typeManagerVisible = true" />
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="难度" prop="difficulty">
              <el-select v-model="form.difficulty" style="width: 100%">
                <el-option v-for="d in difficultyDict" :key="d.value" :label="d.label" :value="Number(d.value)" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="分值" prop="score">
              <el-input-number v-model="form.score" :min="1" :max="100" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属题库" prop="bankId">
              <div style="display:flex; gap:4px; width:100%">
                <el-select v-model="form.bankId" placeholder="请选择题库" filterable style="flex:1">
          <el-option v-for="bank in bankOptions" :key="bank.bankId" :label="bank.bankName" :value="bank.bankId" />
                </el-select>
                <el-button :icon="Setting" @click="bankManagerVisible = true" />
              </div>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="状态" prop="status">
              <el-radio-group v-model="form.status">
                <el-radio v-for="d in common_status" :key="d.value" :value="d.value">{{ d.label }}</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="排序" prop="sortOrder">
              <el-input-number v-model="form.sortOrder" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 题干：带公式按钮（2026-10-27）
             数学题的题干含 LaTeX，纯文本框只能看源码、没法编辑公式。
             MathInput 在旁边挂「ƒx」按钮，点开是符号面板。 -->
        <el-form-item label="题干" prop="questionText">
          <MathInput v-model="form.questionText" :rows="3" placeholder="请输入题目内容" />
        </el-form-item>

        <template v-if="isChoiceType">
          <el-form-item label="选项">
            <div class="options-visual-editor">
              <div v-for="(opt, idx) in form.options" :key="idx" class="option-row">
                <span class="option-letter">{{ String.fromCharCode(65 + idx) }}.</span>
                <MathInput v-model="form.options[idx]" type="text" placeholder="请输入选项内容" class="opt-math-input" />
                <el-button type="danger" text size="small" @click="removeOption(idx)" :disabled="form.options.length <= 2">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </div>
              <el-button v-if="form.options.length < 6" type="primary" text size="small" @click="addOption">
                <el-icon><Plus /></el-icon> 添加选项
              </el-button>
            </div>
          </el-form-item>

          <el-form-item label="正确答案">
            <el-radio-group v-if="form.questionType === '1'" v-model="form.answer" class="answer-radio-group">
              <el-radio v-for="(opt, idx) in form.options" :key="idx" :value="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="form.questionType === '2'" v-model="form.answer" class="answer-checkbox-group">
              <el-checkbox v-for="(opt, idx) in form.options" :key="idx" :value="idx">
                {{ String.fromCharCode(65 + idx) }}. {{ opt }}
              </el-checkbox>
            </el-checkbox-group>
            <el-radio-group v-else-if="form.questionType === '3'" v-model="form.answer">
              <el-radio :value="true">正确</el-radio>
              <el-radio :value="false">错误</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>

        <template v-if="form.questionType === '4' || form.questionType === '5'">
          <el-form-item label="正确答案" prop="answer">
            <MathInput v-model="form.answer" type="text" placeholder="请输入正确答案" />
          </el-form-item>
        </template>

        <template v-if="form.questionType === '6'">
          <el-form-item label="材料/文章内容">
            <el-input v-model="form.content" type="textarea" :rows="4" placeholder="输入文章或材料内容" />
          </el-form-item>

          <el-form-item label="子题管理">
            <div class="sub-questions-container">
              <div class="sub-toolbar">
                <el-select v-model="newSubType" placeholder="选择题型" size="small" style="width: 120px" clearable>
                  <el-option v-for="d in subTypeDict" :key="d.value" :label="d.label" :value="d.value" />
                </el-select>
                <el-button type="primary" size="small" @click="addSubQuestion">添加子题</el-button>
              </div>
              <div v-if="form.subQuestions.length === 0" class="empty-sub">暂无子题，请点击"添加子题"</div>
              <div v-for="(sub, idx) in form.subQuestions" :key="sub._tempId" class="sub-question-card">
                <div class="sub-header">
                  <span class="sub-index">子题 {{ idx + 1 }}</span>
                  <el-select v-model="sub.questionType" size="small" style="width: 100px" @change="(val:any)=>onSubTypeChange(sub, val)">
                    <el-option v-for="d in subTypeDict" :key="d.value" :label="d.label" :value="d.value" />
                  </el-select>
                  <span class="sub-score-label">分值</span>
                  <el-input-number v-model="sub.score" :min="1" :max="100" size="small" style="width: 80px" controls-position="right" />
                  <el-button type="danger" text size="small" @click="removeSubQuestion(idx)">
                    <el-icon><Delete /></el-icon>
                  </el-button>
                </div>
                <div class="sub-body">
                  <MathInput v-model="sub.questionText" :rows="2" placeholder="子题题干" size="small" />
                  <template v-if="sub.questionType === '1' || sub.questionType === '2'">
                    <div class="sub-options-area">
                      <span class="sub-field-label">选项：</span>
                      <div v-for="(opt, oi) in sub.options" :key="oi" class="sub-option-row">
                        <span class="option-letter-sm">{{ String.fromCharCode(65 + oi) }}.</span>
                        <el-input v-model="sub.options[oi]" placeholder="选项内容" size="small" style="flex:1" />
                        <el-button type="danger" text size="small" @click="removeSubOption(sub, oi)" :disabled="sub.options.length <= 2">
                          <el-icon><Close /></el-icon>
                        </el-button>
                      </div>
                      <el-button type="primary" text size="small" @click="addSubOption(sub)" :disabled="sub.options.length >= 6">
                        <el-icon><Plus /></el-icon> 添加选项
                      </el-button>
                    </div>
                  </template>
                  <div class="sub-answer-area">
                    <span class="sub-field-label">答案：</span>
                    <template v-if="sub.questionType === '1'">
                      <el-select v-model="sub.answer" size="small" style="width: 100%">
                        <el-option v-for="(opt, oi) in sub.options" :key="oi" :label="String.fromCharCode(65 + oi) + '. ' + opt" :value="oi" />
                      </el-select>
                    </template>
                    <template v-else-if="sub.questionType === '2'">
                      <el-select v-model="sub.answer" multiple size="small" style="width: 100%">
                        <el-option v-for="(opt, oi) in sub.options" :key="oi" :label="String.fromCharCode(65 + oi) + '. ' + opt" :value="oi" />
                      </el-select>
                    </template>
                    <template v-else-if="sub.questionType === '3'">
                      <el-radio-group v-model="sub.answer" size="small">
                        <el-radio :value="true">正确</el-radio>
                        <el-radio :value="false">错误</el-radio>
                      </el-radio-group>
                    </template>
                    <template v-else>
                      <MathInput v-model="sub.answer" type="text" placeholder="答案" size="small" />
                    </template>
                  </div>
                  <div class="sub-analysis-area">
                    <span class="sub-field-label">解析：</span>
                    <el-input v-model="sub.analysis" type="textarea" :rows="1" placeholder="解析（选填）" size="small" />
                  </div>
                </div>
              </div>
            </div>
          </el-form-item>
        </template>

        <el-form-item label="答案解析">
          <MathInput v-model="form.analysis" :rows="2" placeholder="请输入答案解析（选填）" />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取 消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitting">确 定</el-button>
        </div>
      </template>
    </el-dialog>
  <el-dialog v-model="bankManagerVisible" title="题库管理" width="700px" append-to-body :close-on-click-modal="false" destroy-on-close @open="loadBankList">
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" size="small" @click="openBankForm()">新增题库</el-button>
      </el-col>
    </el-row>
    <el-table :data="bankList" v-loading="bankLoading" size="small" max-height="350">
      <el-table-column label="ID" prop="bankId" width="60" />
      <el-table-column label="题库名称" prop="bankName" min-width="150" />
      <el-table-column label="科目" prop="subject" width="100" />
      <el-table-column label="状态" width="70">
        <template #default="scope">
          <dict-tag :options="common_status" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button link type="primary" size="small" @click="openBankForm(scope.row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="deleteBank(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>

  <el-dialog v-model="bankFormVisible" :title="bankFormTitle" width="450px" append-to-body :close-on-click-modal="false" destroy-on-close>
    <el-form ref="bankFormRef" :model="bankForm" label-width="80px" size="small">
      <el-form-item label="题库名称" prop="bankName" :rules="[{ required: true, message: '请输入题库名称', trigger: 'blur' }]">
        <el-input v-model="bankForm.bankName" placeholder="请输入题库名称" />
      </el-form-item>
      <el-form-item label="科目" prop="subject">
        <el-input v-model="bankForm.subject" placeholder="请输入科目" />
      </el-form-item>
      <el-form-item label="描述" prop="description">
        <el-input v-model="bankForm.description" type="textarea" :rows="2" placeholder="题库描述（选填）" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-radio-group v-model="bankForm.status">
          <el-radio v-for="d in common_status" :key="d.value" :value="d.value">{{ d.label }}</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="small" @click="bankFormVisible = false">取消</el-button>
      <el-button size="small" type="primary" @click="saveBank" :loading="bankSaving">确定</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="typeManagerVisible" title="题型管理" width="500px" append-to-body :close-on-click-modal="false" destroy-on-close>
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" size="small" @click="openTypeForm()">新增题型</el-button>
      </el-col>
    </el-row>
    <el-table :data="typeDict" size="small" max-height="350">
      <el-table-column label="标识" prop="value" width="120" />
      <el-table-column label="名称" prop="label" min-width="150" />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button link type="primary" size="small" @click="openTypeForm(scope.row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="deleteType(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>

  <el-dialog v-model="typeFormVisible" :title="typeFormTitle" width="400px" append-to-body :close-on-click-modal="false" destroy-on-close>
    <el-form ref="typeFormRef" :model="typeForm" label-width="60px" size="small">
      <el-form-item label="标识" prop="value" :rules="[{ required: true, message: '请输入标识', trigger: 'blur' }]">
        <el-input v-model="typeForm.value" placeholder="如 single / multiple" />
      </el-form-item>
      <el-form-item label="名称" prop="label" :rules="[{ required: true, message: '请输入名称', trigger: 'blur' }]">
        <el-input v-model="typeForm.label" placeholder="如 单选题" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button size="small" @click="typeFormVisible = false">取消</el-button>
      <el-button size="small" type="primary" @click="saveType" :loading="typeSaving">确定</el-button>
    </template>
  </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'QuestionMain' })

import { listQuestionMain, getQuestionMain, delQuestionMain, addQuestionMain, updateQuestionMain } from '@/api/questionMain/questionMain'
import { listQuestionBankAll, addQuestionBank, updateQuestionBank, delQuestionBank } from '@/api/questionBank/questionBank'
import { addData as addDictData, updateData as updateDictData, delData as delDictData } from '@/api/system/dict/data'
import { getDicts } from '@/api/system/dict/data'
import useDictStore from '@/store/modules/dict'
import { parseTime } from '@/utils/ruoyi'
import { Delete, Plus, Close, Setting } from '@element-plus/icons-vue'
// 公式输入（2026-10-27）：数学题的题干/选项/答案/解析都含 LaTeX，
// 纯文本框只能显示源码。MathInput 挂「ƒx」按钮，点开是符号面板。
import MathInput from '@/components/MathInput/index.vue'

const { proxy } = getCurrentInstance()
const { common_status } = proxy.useDict('common_status')
const { question_type } = proxy.useDict('question_type')
const { difficulty_level } = proxy.useDict('difficulty_level')

// 题型字典（带兜底数据，防止接口失败导致下拉框为空）
const typeDict = computed(() => {
  const dict = question_type?.value || []
  if (dict.length > 0) return dict
  // 兜底数据
  return [
    { label: '单选题', value: '1', elTagType: 'primary', elTagClass: '1' },
    { label: '多选题', value: '2', elTagType: 'success', elTagClass: '2' },
    { label: '判断题', value: '3', elTagType: 'warning', elTagClass: '3' },
    { label: '填空题', value: '4', elTagType: 'info', elTagClass: '4' },
    { label: '简答题', value: '5', elTagType: 'danger', elTagClass: '5' },
    { label: '组合题', value: '6', elTagType: '', elTagClass: '6' },
  ]
})
const difficultyDict = computed(() => {
  const dict = difficulty_level?.value || []
  if (dict.length > 0) return dict
  return [
    { label: '简单', value: '1', elTagType: 'success', elTagClass: '' },
    { label: '中等', value: '2', elTagType: 'primary', elTagClass: '' },
    { label: '困难', value: '3', elTagType: 'warning', elTagClass: '' },
    { label: '极难', value: '4', elTagType: 'danger', elTagClass: '' },
  ]
})

const questionMainList = ref<any[]>([])
const bankOptions = ref<any[]>([])
const dialogVisible = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref<number[]>([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const dialogTitle = ref('')
const submitting = ref(false)
const newSubType = ref('1')
let tempIdCounter = 0

const dateRange = ref<string[]>([])

const bankManagerVisible = ref(false)
const bankList = ref<any[]>([])
const bankLoading = ref(false)
const bankFormVisible = ref(false)
const bankFormTitle = ref('')
const bankSaving = ref(false)
const bankForm = reactive({ bankName: '', subject: '', description: '', status: '0', id: null as number | null })
const bankFormRef = ref<any>(null)

const typeManagerVisible = ref(false)
const typeFormVisible = ref(false)
const typeFormTitle = ref('')
const typeSaving = ref(false)
const typeForm = reactive({ value: '', label: '', _editIndex: -1, _dictCode: null as number | null })

const subTypeDict = computed(() => typeDict.value.filter((d: any) => d.value !== '6'))

const data = reactive({
  form: {} as any,
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    bankId: null,
    questionType: null,
    difficulty: null,
    status: null,
    keyword: null
  },
  rules: {
    bankId: [{ required: true, message: '请选择题库', trigger: 'change' }],
    questionType: [{ required: true, message: '请选择题型', trigger: 'change' }],
    questionText: [{ required: true, message: '请输入题干', trigger: 'blur' }]
  }
})

const { queryParams, form, rules } = toRefs(data)

const isChoiceType = computed(() =>
  ['1', '2', '3'].includes(form.value.questionType)
)

function getTypeName(type: string | number): string {
  if (!type && type !== 0) return ''
  const found = typeDict.value.find((d: any) => d.value === String(type))
  return found?.label || String(type)
}

function getTypeTagType(type: string | number): string {
  if (!type && type !== 0) return ''
  const found = typeDict.value.find((d: any) => d.value === String(type))
  return found?.elTagType || ''
}

function difficultyColor(level: number): string {
  const colors: Record<number, string> = { 1: '#67c23a', 2: '#409eff', 3: '#e6a23c', 4: '#f56c6c' }
  return colors[level] || '#909399'
}

function difficultyLabel(level: number): string {
  const map: Record<number, string> = { 1: '简单', 2: '中等', 3: '困难', 4: '极难' }
  return map[level] || String(level)
}

function getBankName(bankId: number): string {
  const bank = bankOptions.value.find((b: any) => b.bankId === bankId)
  return bank?.bankName || String(bankId)
}

function loadBankOptions() {
  listQuestionBankAll({ pageNum: 1, pageSize: 999 }).then((res: any) => {
    bankOptions.value = res.data || res.rows || []
  })
}

function getList() {
  loading.value = true
  const params = { ...queryParams.value }
  if (dateRange.value && dateRange.value.length > 0) {
    params.beginTime = dateRange.value[0]
    params.endTime = dateRange.value[1]
  } else {
    params.beginTime = null
    params.endTime = null
  }
  listQuestionMain(params).then((response: any) => {
    questionMainList.value = response.rows || []
    total.value = response.total || 0
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

function reset() {
  form.value = {
    id: null,
    bankId: null,
    questionType: '1',
    difficulty: 1,
    score: 5,
    questionText: '',
    content: '',
    answer: null,
    analysis: '',
    sortOrder: 0,
    status: '0',
    options: ['选项A', '选项B'],
    subQuestions: []
  }
  proxy.resetForm('formRef')
}

function cancel() {
  dialogVisible.value = false
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  dateRange.value = []
  proxy.resetForm('queryRef')
  handleQuery()
}

function handleSelectionChange(selection: any[]) {
  ids.value = selection.map((item: any) => item.id)
  single.value = selection.length !== 1
  multiple.value = selection.length === 0
}

function handleAdd() {
  reset()
  dialogVisible.value = true
  dialogTitle.value = '新增题目'
}

function handleEdit(row: any) {
  reset()
  const id = row.id || ids.value[0]
  getQuestionMain(id).then((response: any) => {
    const data = response.data
    if (!data) return
    form.value = convertApiToEditor(data)
    dialogVisible.value = true
    dialogTitle.value = '编辑题目'
  })
}

function handleEditCurrent() {
  if (ids.value.length === 1) {
    const row =   questionMainList.value.find((r: any) => r.id === ids.value[0])
    if (row) handleEdit(row)
  }
}

function convertApiToEditor(data: any): any {
  const type = data.questionType
  const isNumType = typeof type === 'number'
  const editorType = isNumType ? String(type) : type
  const mappedType = numToEditorType(editorType)

  const result: any = {
    id: data.id,
    bankId: data.bankId,
    questionType: mappedType,
    difficulty: data.difficulty || 1,
    score: data.score || 5,
    questionText: data.questionText || data.questionContent || '',
    content: data.content || '',
    analysis: data.questionAnalysis || data.analysis || '',
    sortOrder: data.sortOrder || 0,
    status: data.status ?? '0',
    options: ['选项A', '选项B'],
    answer: null,
    subQuestions: []
  }

  if (mappedType === '1' || mappedType === '2') {
    let opts = data.options
    if (Array.isArray(opts)) {
      result.options = opts.map((o: any) => {
        if (typeof o === 'string') return o
        if (typeof o === 'object' && o.content) return o.content
        if (typeof o === 'object' && o.label) return o.content || o.label
        return String(o)
      })
    }
    result.answer = data.answer
    if (typeof result.answer === 'string') {
      if (mappedType === '1') result.answer = /^\d+$/.test(result.answer) ? Number(result.answer) : 0
      if (mappedType === '2') {
        try { result.answer = JSON.parse(result.answer) } catch { result.answer = [] }
      }
    }
  }

  if (mappedType === '3') {
    result.answer = data.answer === true || data.answer === 'true' || data.answer === 1
  }

  if (mappedType === '4' || mappedType === '5') {
    result.answer = data.answer || ''
  }

  if (mappedType === '6') {
    result.content = data.content || ''
    const subs = data.questionSubList || data.subQuestions || []
    result.subQuestions = subs.map((s: any) => {
      const subType = numToEditorType(s.questionType || s.subType || '1')
      const sub: any = {
        _tempId: ++tempIdCounter,
        questionType: subType,
        questionText: s.questionText || s.content || '',
        answer: s.answer,
        analysis: s.analysis || '',
        score: s.score || 2,
        options: ['选项A', '选项B']
      }
      if (subType === '1' || subType === '2') {
        opts = s.options
        if (Array.isArray(opts)) {
          sub.options = opts.map((o: any) => typeof o === 'string' ? o : o.content || String(o))
        }
        if (typeof sub.answer === 'string') {
          if (subType === '1') sub.answer = /^\d+$/.test(sub.answer) ? Number(sub.answer) : 0
          if (subType === '2') {
            try { sub.answer = JSON.parse(sub.answer) } catch { sub.answer = [] }
          }
        }
      }
      if (subType === '3') {
        sub.answer = s.answer === true || s.answer === 'true' || s.answer === 1
      }
      if (subType === '4' || subType === '5') {
        sub.answer = s.answer || ''
      }
      return sub
    })
  }

  return result
}

function convertEditorToApi(editor: any): any {
  const apiType = editorTypeToNum(editor.questionType)
  const result: any = {
    bankId: editor.bankId,
    questionType: apiType,
    questionText: editor.questionText,
    content: editor.content || '',
    difficulty: editor.difficulty || 1,
    score: editor.score || 5,
    questionAnalysis: editor.analysis || '',
    sortOrder: editor.sortOrder || 0,
    status: editor.status ?? '0'
  }

  if (editor.id) result.id = editor.id

  if (editor.questionType === '1' || editor.questionType === '2') {
    result.options = editor.options || []
    result.answer = editor.answer
    if (editor.questionType === '2' && Array.isArray(result.answer)) {
      result.answer = JSON.stringify(result.answer)
    }
    if (editor.questionType === '1' && typeof result.answer === 'number') {
      result.answer = String(result.answer)
    }
  }

  if (editor.questionType === '3') {
    result.answer = editor.answer === true ? 'true' : 'false'
  }

  if (editor.questionType === '4' || editor.questionType === '5') {
    result.answer = editor.answer || ''
  }

  if (editor.questionType === '6') {
    result.questionSubList = (editor.subQuestions || []).map((s: any) => {
      const subApiType = editorTypeToNum(s.questionType)
      const sub: any = {
        questionText: s.questionText || '',
        questionType: subApiType,
        answer: s.answer,
        analysis: s.analysis || '',
        score: s.score || 2,
        sortOrder: s.sortOrder || 0,
        options: s.options || []
      }
      if (s.questionType === '1') {
        sub.answer = typeof s.answer === 'number' ? String(s.answer) : s.answer
      }
      if (s.questionType === '2' && Array.isArray(s.answer)) {
        sub.answer = JSON.stringify(s.answer)
      }
      if (s.questionType === '3') {
        sub.answer = s.answer === true ? 'true' : 'false'
      }
      if (s.questionId || s.id) sub.id = s.questionId || s.id
      return sub
    })
  }

  return result
}

function numToEditorType(val: string | number): string {
  const found = typeDict.value.find((d: any) => d.value === String(val))
  return found?.value || '1'
}

function editorTypeToNum(type: string): number {
  const found = typeDict.value.find((d: any) => d.value === type)
  return found ? Number(found.elTagClass) : 1
}

function onTypeChange() {
  const t = form.value.questionType
  if (t === '1' || t === '2') {
    if (!form.value.options || form.value.options.length < 2) {
      form.value.options = ['选项A', '选项B']
    }
    form.value.answer = t === '1' ? 0 : []
  } else if (t === '3') {
    form.value.options = ['正确', '错误']
    form.value.answer = true
  } else if (t === '4' || t === '5') {
    form.value.options = []
    form.value.answer = ''
  } else if (t === '6') {
    form.value.options = []
    form.value.answer = null
    if (!form.value.subQuestions) form.value.subQuestions = []
    form.value.content = form.value.content || ''
  }
}

function addOption() {
  if (!form.value.options) form.value.options = ['选项A', '选项B']
  if (form.value.options.length >= 6) return
  form.value.options.push('选项' + String.fromCharCode(65 + form.value.options.length))
}

function removeOption(index: number) {
  if (form.value.options.length <= 2) return
  form.value.options.splice(index, 1)
  if (form.value.questionType === '1') {
    if (form.value.answer === index) form.value.answer = 0
    else if (form.value.answer > index) form.value.answer -= 1
  } else if (form.value.questionType === '2') {
    form.value.answer = form.value.answer
      .filter((idx: number) => idx !== index)
      .map((idx: number) => idx > index ? idx - 1 : idx)
  }
}

function addSubQuestion() {
  if (!form.value.subQuestions) form.value.subQuestions = []
  const type = newSubType.value || '1'
  const sub: any = {
    _tempId: ++tempIdCounter,
    questionType: type,
    questionText: '',
    answer: type === '1' ? 0 : type === '2' ? [] : type === '3' ? true : '',
    options: ['选项A', '选项B'],
    analysis: '',
    score: 2,
    sortOrder: form.value.subQuestions.length
  }
  form.value.subQuestions.push(sub)
}

function removeSubQuestion(index: number) {
  form.value.subQuestions.splice(index, 1)
}

function onSubTypeChange(sub: any, val: string) {
  if (val === '1' || val === '2') {
    if (!sub.options || sub.options.length < 2) sub.options = ['选项A', '选项B']
    sub.answer = val === '1' ? 0 : []
  } else if (val === '3') {
    sub.options = ['正确', '错误']
    sub.answer = true
  } else {
    sub.options = []
    sub.answer = ''
  }
}

function addSubOption(sub: any) {
  if (!sub.options) sub.options = ['选项A', '选项B']
  if (sub.options.length >= 6) return
  sub.options.push('选项' + String.fromCharCode(65 + sub.options.length))
}

function removeSubOption(sub: any, index: number) {
  if (!sub.options || sub.options.length <= 2) return
  sub.options.splice(index, 1)
}

function loadBankList() {
  bankLoading.value = true
  listQuestionBankAll({ pageNum: 1, pageSize: 999 }).then((res: any) => {
    bankList.value = res.data || res.rows || []
  }).finally(() => { bankLoading.value = false })
}

function openBankForm(row?: any) {
  if (row) {
    bankFormTitle.value = '编辑题库'
    bankForm.bankName = row.bankName || ''
    bankForm.subject = row.subject || ''
    bankForm.description = row.description || ''
    bankForm.status = row.status ?? '0'
    bankForm.id = row.bankId
  } else {
    bankFormTitle.value = '新增题库'
    bankForm.bankName = ''
    bankForm.subject = ''
    bankForm.description = ''
    bankForm.status = '0'
    bankForm.id = null
  }
  bankFormVisible.value = true
}

function saveBank() {
  bankFormRef.value?.validate((valid: boolean) => {
    if (!valid) return
    bankSaving.value = true
    const payload: any = {
      bankName: bankForm.bankName,
      subject: bankForm.subject,
      description: bankForm.description,
      status: bankForm.status
    }
    if (bankForm.id) payload.bankId = bankForm.id
    const api = bankForm.id ? updateQuestionBank : addQuestionBank
    api(payload).then(() => {
      proxy.$modal.msgSuccess(bankForm.id ? '修改成功' : '新增成功')
      bankFormVisible.value = false
      loadBankList()
      loadBankOptions()
    }).finally(() => { bankSaving.value = false })
  })
}

function deleteBank(row: any) {
  proxy.$modal.confirm('是否确认删除题库"' + row.bankName + '"？').then(() => {
    delQuestionBank(row.bankId).then(() => {
      proxy.$modal.msgSuccess('删除成功')
      loadBankList()
      loadBankOptions()
    })
  }).catch(() => {})
}

function refreshTypeDict() {
  getDicts('question_type').then((resp: any) => {
    const items = (resp.data || []).map((p: any, i: number) => ({
      label: p.dictLabel,
      value: p.dictValue,
      elTagType: p.listClass,
      elTagClass: p.cssClass,
      dictCode: i + 1
    }))
    useDictStore().setDict('question_type', items)
    question_type.value = items
  })
}

function openTypeForm(row?: any) {
  if (row) {
    typeFormTitle.value = '编辑题型'
    typeForm.value = row.value
    typeForm.label = row.label
    typeForm._dictCode = row.dictCode || typeDict.value.indexOf(row) + 1
  } else {
    typeFormTitle.value = '新增题型'
    typeForm.value = ''
    typeForm.label = ''
    typeForm._dictCode = null
  }
  typeFormVisible.value = true
}

function saveType() {
  typeSaving.value = true
  if (typeForm._dictCode) {
    const existing = typeDict.value.find((d: any) => d.dictCode === typeForm._dictCode) || typeDict.value[typeForm._dictCode - 1]
    const cssClass = existing?.elTagClass || String(typeDict.value.length + 1)
    updateDictData({ dictCode: typeForm._dictCode, dictType: 'question_type', dictValue: typeForm.value, dictLabel: typeForm.label, listClass: 'primary', cssClass }).then(() => {
      refreshTypeDict()
      typeFormVisible.value = false
      proxy.$modal.msgSuccess('题型已更新')
    }).finally(() => { typeSaving.value = false })
  } else {
    const maxNum = typeDict.value.reduce((max: number, d: any) => Math.max(max, Number(d.elTagClass) || 0), 0)
    addDictData({ dictType: 'question_type', dictValue: typeForm.value, dictLabel: typeForm.label, listClass: 'primary', cssClass: String(maxNum + 1) }).then(() => {
      refreshTypeDict()
      typeFormVisible.value = false
      proxy.$modal.msgSuccess('题型已新增')
    }).finally(() => { typeSaving.value = false })
  }
}

function deleteType(row: any) {
  proxy.$modal.confirm('是否确认删除题型"' + row.label + '"？该操作会级联删除该类型下所有题目！').then(() => {
    const idx = typeDict.value.indexOf(row)
    if (idx >= 0) {
      delDictData(idx + 1, { dictType: 'question_type' }).then(() => {
        refreshTypeDict()
        proxy.$modal.msgSuccess('题型已删除')
      })
    }
  }).catch(() => {})
}

function submitForm() {
  proxy.$refs['formRef'].validate((valid: boolean) => {
    if (!valid) return
    submitting.value = true
    const payload = convertEditorToApi(form.value)
    const api = payload.id ? updateQuestionMain : addQuestionMain
    api(payload).then(() => {
      proxy.$modal.msgSuccess(payload.id ? '修改成功' : '新增成功')
      dialogVisible.value = false
      getList()
    }).catch((err: any) => {
      console.error('保存失败:', err)
      proxy.$modal.msgError(err?.msg || '保存失败')
    }).finally(() => {
      submitting.value = false
    })
  })
}

function handleDelete(row: any) {
  const _ids = row.id || ids.value
  proxy.$modal.confirm('是否确认删除题目编号为"' + _ids + '"的数据项？').then(() => {
    return delQuestionMain(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess('删除成功')
  }).catch(() => {})
}

loadBankOptions()
getList()
</script>

<style scoped>
.options-visual-editor {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
  width: 100%;
}

.option-row {
  display: flex;
  /* 选项里现在装 MathInput（标签行 + 输入框 + 预览行），用 center 会让字母浮在中间 */
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

/* MathInput 吃掉剩余宽度，别和删除按钮挤在一起 */
.opt-math-input {
  flex: 1;
  min-width: 0;
}

.option-row:last-child {
  margin-bottom: 0;
}

.option-letter {
  width: 24px;
  font-weight: 700;
  color: #409eff;
  flex-shrink: 0;
}

.option-letter-sm {
  width: 20px;
  font-weight: 600;
  color: #409eff;
  font-size: 13px;
  flex-shrink: 0;
}

.answer-radio-group,
.answer-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-questions-container {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
  width: 100%;
}

.sub-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  align-items: center;
}

.sub-question-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 10px;
  overflow: hidden;
}

.sub-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.sub-index {
  font-weight: 600;
  color: #1f2937;
  font-size: 14px;
}

.sub-score-label {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
}

.sub-body {
  padding: 10px 12px;
}

.sub-field-label {
  display: block;
  font-size: 12px;
  color: #909399;
  font-weight: 500;
  margin-bottom: 4px;
}

.sub-options-area,
.sub-answer-area,
.sub-analysis-area {
  margin-top: 8px;
}

.sub-option-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.empty-sub {
  text-align: center;
  color: #909399;
  padding: 20px 0;
}
</style>
