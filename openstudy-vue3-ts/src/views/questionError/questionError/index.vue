<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="120px">
      <el-form-item label="用户ID" prop="userId">
        <el-input
          v-model="queryParams.userId"
          placeholder="请输入用户ID"
          clearable
          @keyup.enter="handleQuery"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="题目ID" prop="questionId">
        <el-input
          v-model="queryParams.questionId"
          placeholder="请输入题目ID"
          clearable
          @keyup.enter="handleQuery"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="所属题库ID" prop="bankId">
        <el-input
          v-model="queryParams.bankId"
          placeholder="请输入题库ID"
          clearable
          @keyup.enter="handleQuery"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="错因备注" prop="notes">
        <el-input
          v-model="queryParams.notes"
          placeholder="请输入错因备注"
          clearable
          @keyup.enter="handleQuery"
          style="width: 150px"
        />
      </el-form-item>
      <el-form-item label="累计错误次数" prop="errorCount">
        <el-input-number
          v-model="queryParams.errorCount"
          :min="0"
          placeholder="错误次数"
          controls-position="right"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="掌握状态" prop="isMastered">
        <el-select
          v-model="queryParams.isMastered"
          placeholder="请选择掌握状态"
          clearable
          style="width: 120px"
        >
          <el-option label="未掌握" :value="0" />
          <el-option label="已掌握" :value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="记录状态" prop="status">
        <el-select
          v-model="queryParams.status"
          placeholder="请选择记录状态"
          clearable
          style="width: 120px"
        >
          <el-option label="已删除" :value="0" />
          <el-option label="活跃" :value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="难度评级" prop="difficultyRating">
        <el-rate
          v-model="queryParams.difficultyRating"
          :max="5"
          :colors="['#99A9BF', '#F7BA2A', '#FF9900']"
          :texts="['很简单', '简单', '中等', '困难', '极难']"
          show-text
          style="margin-top: 8px"
        />
      </el-form-item>
      <el-form-item label="首次做错时间" prop="errorTime">
        <el-date-picker
          v-model="queryParams.errorTime"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 240px"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button
          type="primary"
          plain
          icon="Plus"
          @click="handleAdd"
          v-hasPermi="['questionError:questionError:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['questionError:questionError:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['questionError:questionError:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['questionError:questionError:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="questionErrorList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="错题ID" align="center" prop="errorId" width="80" />
      <el-table-column label="用户ID" align="center" prop="userId" width="80" />
      <el-table-column label="题目ID" align="center" prop="questionId" width="80" />
      <el-table-column label="所属题库" align="center" prop="bankId" width="100" />
      
      <el-table-column label="时间信息" align="center" width="280">
        <el-table-column label="首次做错" align="center" prop="errorTime" width="90">
          <template #default="scope">
            <span v-if="scope.row.errorTime">{{ parseTime(scope.row.errorTime, '{y}-{m}-{d}') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近做错" align="center" prop="lastErrorTime" width="90">
          <template #default="scope">
            <span v-if="scope.row.lastErrorTime">{{ parseTime(scope.row.lastErrorTime, '{y}-{m}-{d}') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="最后复习" align="center" prop="lastReviewTime" width="100">
          <template #default="scope">
            <span v-if="scope.row.lastReviewTime">{{ parseTime(scope.row.lastReviewTime, '{y}-{m}-{d}') }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="错题统计" align="center" width="200">
        <el-table-column label="错误次数" align="center" prop="errorCount" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.errorCount > 5 ? 'danger' : scope.row.errorCount > 2 ? 'warning' : 'info'">
              {{ scope.row.errorCount }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复习次数" align="center" prop="reviewCount" width="80">
          <template #default="scope">
            <el-tag type="success">
              {{ scope.row.reviewCount }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="难度评级" align="center" prop="difficultyRating" width="120">
          <template #default="scope">
            <el-rate
              v-model="scope.row.difficultyRating"
              disabled
              :max="5"
              :colors="['#99A9BF', '#F7BA2A', '#FF9900']"
              :texts="['很简单', '简单', '中等', '困难', '极难']"
              show-text
              style="--el-rate-icon-size: 14px"
            />
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="状态信息" align="center" width="200">
        <el-table-column label="掌握状态" align="center" prop="isMastered" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.isMastered === 1 ? 'success' : 'danger'">
              {{ scope.row.isMastered === 1 ? '已掌握' : '未掌握' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="记录状态" align="center" prop="status" width="80">
          <template #default="scope">
            <el-tag :type="scope.row.status === 1 ? 'success' : 'info'">
              {{ scope.row.status === 1 ? '活跃' : '已删除' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="下次复习" align="center" prop="nextReviewTime" width="100">
          <template #default="scope">
            <span v-if="scope.row.nextReviewTime">
              <el-tag 
                :type="getNextReviewStatus(scope.row.nextReviewTime)" 
                size="small"
              >
                {{ parseTime(scope.row.nextReviewTime, '{m}-{d}') }}
              </el-tag>
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="备注标签" align="center" prop="notes" width="200">
        <template #default="scope">
          <div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis;">
            <el-tooltip 
              v-if="scope.row.notes" 
              :content="scope.row.notes" 
              placement="top"
            >
              <span>{{ scope.row.notes.length > 15 ? scope.row.notes.substring(0, 15) + '...' : scope.row.notes }}</span>
            </el-tooltip>
            <span v-else>-</span>
          </div>
          <div v-if="scope.row.tags" style="margin-top: 4px;">
            <el-tag 
              v-for="tag in scope.row.tags.split(',')" 
              :key="tag"
              size="small"
              style="margin-right: 2px;"
            >
              {{ tag }}
            </el-tag>
          </div>
        </template>
      </el-table-column>
      
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="120">
        <template #default="scope">
          <el-tooltip content="编辑" placement="top">
            <el-button 
              link 
              type="primary" 
              icon="Edit" 
              @click="handleUpdate(scope.row)" 
              v-hasPermi="['questionError:questionError:edit']"
            />
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button 
              link 
              type="danger" 
              icon="Delete" 
              @click="handleDelete(scope.row)" 
              v-hasPermi="['questionError:questionError:remove']"
            />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>
    
    <pagination
      v-show="total>0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <!-- 添加或修改用户错题记录对话框 -->
    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="questionErrorRef" :model="form" :rules="rules" label-width="120px">
      <!-- 在模板中修改用户ID验证提示部分 -->
        <el-form-item label="用户ID" prop="userId">
          <el-input 
            v-model="form.userId" 
            placeholder="请输入有效的用户ID"
            @blur="validateUserId"
            @input="clearUserIdError"
          />
          <!-- 用户ID验证结果提示 -->
          <div v-if="userIdError" style="color: #f56c6c; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-warning-outline"></i> {{ userIdError }}
          </div>
          <div v-else-if="userIdValid && userName" style="color: #67c23a; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-circle-check"></i> {{ userName }}
          </div>
          <div v-else-if="userIdValid" style="color: #67c23a; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-circle-check"></i> 用户ID验证通过
          </div>
          <div v-else-if="userIdValidating" style="color: #909399; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-loading"></i> 正在验证用户ID...
          </div>
        </el-form-item>
        
        <el-form-item label="题目ID" prop="questionId">
          <el-input
            v-model="form.questionId"
            placeholder="请输入有效的题目ID"
            @blur="validateQuestionId"
            @input="clearQuestionError"
          />
          <!-- 题目ID验证结果提示 -->
          <div v-if="questionError" style="color: #f56c6c; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-warning-outline"></i> {{ questionError }}
          </div>
          <div v-else-if="questionValid && questionTitle" style="color: #67c23a; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-circle-check"></i> {{ questionTitle }}
          </div>
          <div v-else-if="questionValidating" style="color: #909399; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-loading"></i> 正在验证题目ID...
          </div>
        </el-form-item>
        
        <el-form-item label="所属题库" prop="bankId">
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <!-- 第一行：题库ID输入框 -->
            <div>
              <el-input 
                v-model="form.bankId" 
                placeholder="题库ID将自动填充" 
                disabled
              />
            </div>
            
            <!-- 第二行：题库名称显示 -->
            <div v-if="bankName" style="color: #67c23a; font-size: 14px;">
              <i class="el-icon-notebook-2" style="margin-right: 6px;"></i>
              <span style="font-weight: 500;">题库名称：</span>{{ bankName }}
            </div>
            
            <!-- 加载状态 -->
            <div v-else-if="form.bankId && !bankName" style="color: #606266; font-size: 14px;">
              <i class="el-icon-loading" style="margin-right: 6px;"></i>
              正在加载题库信息...
            </div>
          </div>
        </el-form-item>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="累计错误次数" prop="errorCount">
              <el-input-number 
                v-model="form.errorCount" 
                :min="0" 
                :max="999" 
                placeholder="请输入累计错误次数"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="首次做错时间" prop="errorTime">
              <el-date-picker 
                v-model="form.errorTime"
                type="datetime"
                placeholder="请选择首次做错时间"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="最近做错时间" prop="lastErrorTime">
              <el-date-picker 
                v-model="form.lastErrorTime"
                type="datetime"
                placeholder="请选择最近一次做错时间"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="难度评级" prop="difficultyRating">
              <el-rate
                v-model="form.difficultyRating"
                :max="5"
                :colors="['#99A9BF', '#F7BA2A', '#FF9900']"
                :texts="['很简单', '简单', '中等', '困难', '极难']"
                show-text
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item label="错因备注" prop="notes">
          <el-input 
            v-model="form.notes" 
            type="textarea" 
            :rows="3" 
            placeholder="请输入错因备注，如：知识点掌握不牢固"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        
        <el-form-item label="标签" prop="tags">
          <el-select
            v-model="form.tagsArray"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="请输入或选择标签"
            style="width: 100%"
          >
            <el-option
              v-for="tag in defaultTags"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
        </el-form-item>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="已复习次数" prop="reviewCount">
              <el-input-number 
                v-model="form.reviewCount" 
                :min="0" 
                :max="99" 
                placeholder="已复习次数"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最后复习时间" prop="lastReviewTime">
              <el-date-picker 
                v-model="form.lastReviewTime"
                type="datetime"
                placeholder="请选择最后复习时间"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="下次复习时间" prop="nextReviewTime">
              <el-date-picker 
                v-model="form.nextReviewTime"
                type="datetime"
                placeholder="请选择下次复习时间"
                value-format="YYYY-MM-DD HH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="掌握状态" prop="isMastered">
              <el-radio-group v-model="form.isMastered">
                <el-radio :label="0">未掌握</el-radio>
                <el-radio :label="1">已掌握</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-form-item label="记录状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio :label="1">活跃</el-radio>
            <el-radio :label="0">已删除</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button 
            type="primary" 
            @click="submitForm" 
            :disabled="!userIdValid || !questionValid || submitLoading"
            :loading="submitLoading"
          >
            确 定
          </el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'QuestionError' })
import { listQuestionError, getQuestionError, delQuestionError, addQuestionError, updateQuestionError } from "@/api/questionError/questionError"
import { checkQuestionExists, getQuestionSimpleInfo, checkUserExists, checkQuestionAndUser } from "@/api/questionMain/questionMain"
import { listQuestionBankAll } from "@/api/questionBank/questionBank"
import dayjs from 'dayjs'

const { proxy } = getCurrentInstance()

const questionErrorList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")
const submitLoading = ref(false)
const defaultTags = ref(['易错题', '重点题', '常考题', '难点题', '概念模糊', '计算错误', '审题不清'])

// 用户ID验证相关变量
const userIdValidating = ref(false)
const userIdValid = ref(false)
const userIdError = ref("")
const userName = ref("")

// 题目验证相关变量
const questionValidating = ref(false)
const questionValid = ref(false)
const questionError = ref("")
const questionTitle = ref("")

// 题库相关变量
const bankName = ref("")

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    questionId: null,
    bankId: null,
    errorTime: null,
    lastErrorTime: null,
    errorCount: null,
    notes: null,
    tags: null,
    difficultyRating: null,
    reviewCount: null,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: null,
    status: null,
  },
  rules: {
    userId: [
      { required: true, message: "用户ID不能为空", trigger: "blur" },
      { pattern: /^\d+$/, message: "用户ID必须为数字", trigger: "blur" }
    ],
    questionId: [
      { required: true, message: "题目ID不能为空", trigger: "blur" },
      { pattern: /^\d+$/, message: "题目ID必须为数字", trigger: "blur" }
    ],
    bankId: [
      { required: true, message: "所属题库ID不能为空", trigger: "blur" },
      { pattern: /^\d+$/, message: "题库ID必须为数字", trigger: "blur" }
    ],
    difficultyRating: [
      { type: 'number', min: 1, max: 5, message: '难度评级必须为1-5之间的数字', trigger: 'blur' }
    ],
    errorCount: [
      { type: 'number', min: 0, message: '错误次数不能小于0', trigger: 'blur' }
    ],
    reviewCount: [
      { type: 'number', min: 0, message: '复习次数不能小于0', trigger: 'blur' }
    ]
  }
})

const { queryParams, form, rules } = toRefs(data)

// 计算属性：标签数组与字符串转换
const formTagsArray = computed({
  get() {
    return form.value.tags ? form.value.tags.split(',').filter(tag => tag.trim()) : []
  },
  set(value) {
    form.value.tags = value.filter(tag => tag.trim()).join(',')
  }
})

// ==================== 用户ID验证相关方法 ====================

/** 验证用户ID */
function validateUserId() {
  const userId = form.value.userId
  if (!userId) {
    userIdError.value = "请输入用户ID"
    userIdValid.value = false
    userName.value = ""
    return
  }
  
  if (!/^\d+$/.test(userId)) {
    userIdError.value = "用户ID必须为数字"
    userIdValid.value = false
    userName.value = ""
    return
  }
  
  userIdValidating.value = true
  userIdValid.value = false
  userIdError.value = ""
  userName.value = ""
  
  // 调用后端API验证用户是否存在
  checkUserExists(userId).then(response => {
    if (response.code === 200 && response.data && response.data.exists) {
      userIdValid.value = true
      userIdError.value = ""
      // 如果有用户信息，显示用户名
      if (response.data.userName) {
        userName.value = `用户：${response.data.nickName || response.data.userName}`
      } else {
        userName.value = "用户ID验证通过"
      }
    } else {
      userIdValid.value = false
      userIdError.value = "用户ID不存在，请检查输入"
      userName.value = ""
    }
  }).catch(error => {
    userIdValid.value = false
    userIdError.value = error.msg || "验证失败，请稍后重试"
    userName.value = ""
  }).finally(() => {
    userIdValidating.value = false
  })
}

/** 清除用户ID错误信息 */
function clearUserIdError() {
  userIdError.value = ""
  userIdValid.value = false
  userName.value = ""
}

// ==================== 题目验证相关方法 ====================

/** 验证题目ID是否存在 */
function validateQuestionId() {
  const questionId = form.value.questionId
  if (!questionId || isNaN(questionId)) {
    questionError.value = "请输入有效的题目ID"
    questionValid.value = false
    questionTitle.value = ""
    return
  }
  
  questionValidating.value = true
  questionError.value = ""
  questionValid.value = false
  questionTitle.value = ""
  bankName.value = ""  // 清除之前的题库名称
  
  checkQuestionExists(questionId).then(response => {
    console.log('题目验证响应:', response) // 调试信息
    if (response.code === 200 && response.data) {
      // 检查题目是否存在
      if (response.data.exists === true || response.data.exists === 'true') {
        questionValid.value = true
        questionError.value = ""
        
        // 构建显示信息
        if (response.data.questionText) {
          questionTitle.value = `题目：${response.data.questionText.substring(0, 50)}${response.data.questionText.length > 50 ? '...' : ''} (ID: ${questionId})`
        } else {
          questionTitle.value = `题目ID: ${questionId} 验证成功`
        }
        
        // 自动填充题库信息
        if (response.data.bankId) {
          form.value.bankId = response.data.bankId
          // 加载题库名称
          loadBankName(response.data.bankId)
        }
        
        // 自动填充难度信息
        if (response.data.difficulty) {
          form.value.difficultyRating = response.data.difficulty
        }
      } else {
        questionValid.value = false
        questionError.value = "题目ID不存在，请检查输入"
        questionTitle.value = ""
      }
    } else {
      questionValid.value = false
      questionError.value = "题目ID不存在，请检查输入"
      questionTitle.value = ""
    }
  }).catch(error => {
    console.error('题目验证错误:', error) // 调试信息
    questionValid.value = false
    questionError.value = error.msg || "验证失败，请稍后重试"
    questionTitle.value = ""
  }).finally(() => {
    questionValidating.value = false
  })
}

/** 加载题库名称 */
function loadBankName(bankId) {
  if (!bankId) return
  
  listQuestionBankAll({}).then(response => {
    if (response.code === 200 && response.data) {
      const bank = response.data.find(b => b.id === bankId)
      if (bank) {
        bankName.value = bank.bankName
      } else {
        bankName.value = `题库ID: ${bankId}`
      }
    }
  }).catch(() => {
    bankName.value = `题库ID: ${bankId}`
  })
}

/** 清除题目错误信息 */
function clearQuestionError() {
  questionError.value = ""
  questionValid.value = false
  questionTitle.value = ""
  bankName.value = ""
}

// ==================== 组合验证方法 ====================

/** 同时验证用户和题目 */
function validateUserAndQuestion() {
  const userId = form.value.userId
  const questionId = form.value.questionId
  
  if (!userId || !/^\d+$/.test(userId)) {
    userIdError.value = "请输入有效的用户ID"
    userIdValid.value = false
    return
  }
  
  if (!questionId || isNaN(questionId)) {
    questionError.value = "请输入有效的题目ID"
    questionValid.value = false
    return
  }
  
  userIdValidating.value = true
  questionValidating.value = true
  
  checkQuestionAndUser(questionId, userId).then(response => {
    if (response.code === 200 && response.data) {
      const data = response.data
      
      // 处理用户验证结果
      if (data.userValid === true) {
        userIdValid.value = true
        userIdError.value = ""
        if (data.userName) {
          userName.value = `用户：${data.nickName || data.userName}`
        } else {
          userName.value = "用户验证通过"
        }
      } else {
        userIdValid.value = false
        userIdError.value = data.userError || "用户验证失败"
        userName.value = ""
      }
      
      // 处理题目验证结果
      if (data.questionValid === true) {
        questionValid.value = true
        questionError.value = ""
        if (data.questionText) {
          questionTitle.value = `题目：${data.questionText.substring(0, 50)}${data.questionText.length > 50 ? '...' : ''} (ID: ${questionId})`
        } else {
          questionTitle.value = "题目验证通过"
        }
        
        // 自动填充题库信息
        if (data.bankId) {
          form.value.bankId = data.bankId
          if (data.bankName) {
            bankName.value = data.bankName
          } else {
            loadBankName(data.bankId)
          }
        }
      } else {
        questionValid.value = false
        questionError.value = data.questionError || "题目验证失败"
        questionTitle.value = ""
      }
    } else {
      userIdValid.value = false
      questionValid.value = false
      userIdError.value = "验证失败，请稍后重试"
      questionError.value = "验证失败，请稍后重试"
    }
  }).catch(error => {
    userIdValid.value = false
    questionValid.value = false
    userIdError.value = error.msg || "验证失败，请稍后重试"
    questionError.value = error.msg || "验证失败，请稍后重试"
  }).finally(() => {
    userIdValidating.value = false
    questionValidating.value = false
  })
}

// ==================== 其他方法 ====================

/** 获取下次复习时间状态 */
function getNextReviewStatus(nextReviewTime) {
  if (!nextReviewTime) return 'info'
  
  const now = dayjs()
  const reviewTime = dayjs(nextReviewTime)
  const diffDays = reviewTime.diff(now, 'day')
  
  if (diffDays < 0) return 'danger'  // 已过期
  if (diffDays <= 1) return 'warning' // 即将到期
  return 'success' // 未到期
}

/** 查询用户错题记录列表 */
function getList() {
  loading.value = true
  
  // 处理时间范围查询
  const params = { ...queryParams.value }
  if (params.errorTime && Array.isArray(params.errorTime)) {
    params.beginErrorTime = params.errorTime[0]
    params.endErrorTime = params.errorTime[1]
    delete params.errorTime
  }
  
  listQuestionError(params).then(response => {
    questionErrorList.value = response.rows
    total.value = response.total
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

// 取消按钮
function cancel() {
  open.value = false
  reset()
}

// 表单重置
function reset() {
  form.value = {
    errorId: null,
    userId: null,
    questionId: null,
    bankId: null,
    errorTime: null,
    lastErrorTime: null,
    errorCount: 0,
    notes: null,
    tags: null,
    difficultyRating: 3,
    reviewCount: 0,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: 0,
    status: 1,
    createTime: null,
    updateTime: null
  }
  
  // 重置验证状态
  userIdValidating.value = false
  userIdValid.value = false
  userIdError.value = ""
  userName.value = ""
  
  questionValidating.value = false
  questionValid.value = false
  questionError.value = ""
  questionTitle.value = ""
  bankName.value = ""
  
  proxy.resetForm("questionErrorRef")
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef")
  queryParams.value = {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    questionId: null,
    bankId: null,
    errorTime: null,
    lastErrorTime: null,
    errorCount: null,
    notes: null,
    tags: null,
    difficultyRating: null,
    reviewCount: null,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: null,
    status: null,
  }
  handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.errorId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加错题记录"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _errorId = row.errorId || ids.value
  getQuestionError(_errorId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改错题记录"
    
    // 如果有题目ID，验证并加载题目信息
    if (form.value.questionId) {
      validateQuestionId()
    }
    
    // 如果有题库ID，加载题库名称
    if (form.value.bankId) {
      loadBankName(form.value.bankId)
    }
  })
}

/** 提交前验证 */
function validateBeforeSubmit() {
  if (!form.value.userId || !form.value.questionId) {
    proxy.$modal.msgError('请先填写用户ID和题目ID')
    return
  }
  
  validateUserAndQuestion()
}

/** 提交按钮 */
async function submitForm() {
  try {
    // 验证表单
    await proxy.$refs["questionErrorRef"].validate()
    
    // 验证用户ID
    if (!userIdValid.value) {
      proxy.$modal.msgError('用户ID验证未通过，请检查')
      return
    }
    
    // 验证题目ID
    if (!questionValid.value) {
      proxy.$modal.msgError('题目ID验证未通过，请检查')
      return
    }
    
    submitLoading.value = true
    
    // 准备提交数据
    const submitData = {
      ...form.value,
      errorCount: form.value.errorCount || 0,
      reviewCount: form.value.reviewCount || 0,
      difficultyRating: form.value.difficultyRating || 3,
      isMastered: form.value.isMastered || 0,
      status: form.value.status || 1
    }
    
    if (submitData.errorId != null) {
      await updateQuestionError(submitData)
      proxy.$modal.msgSuccess("修改成功")
    } else {
      await addQuestionError(submitData)
      proxy.$modal.msgSuccess("新增成功")
    }
    
    open.value = false
    getList()
    
  } catch (error) {
    console.error('提交失败:', error)
    if (error.response && error.response.data && error.response.data.msg) {
      proxy.$modal.msgError(error.response.data.msg)
    } else {
      proxy.$modal.msgError('提交失败，请检查数据')
    }
  } finally {
    submitLoading.value = false
  }
}

/** 删除按钮操作 */
function handleDelete(row) {
  const _errorIds = row.errorId || ids.value
  const count = Array.isArray(_errorIds) ? _errorIds.length : 1
  
  proxy.$modal.confirm(`是否确认删除${count}条错题记录？`).then(function() {
    return delQuestionError(_errorIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  const params = { ...queryParams.value }
  if (params.errorTime && Array.isArray(params.errorTime)) {
    params.beginErrorTime = params.errorTime[0]
    params.endErrorTime = params.errorTime[1]
    delete params.errorTime
  }
  proxy.download('questionError/questionError/export', params, `错题记录_${new Date().getTime()}.xlsx`)
}

getList()
</script>

<style scoped>
.el-rate {
  --el-rate-icon-size: 20px;
}

:deep(.el-table .cell) {
  line-height: 1.5;
}

:deep(.el-table .el-tag) {
  margin: 2px;
}

.validation-status {
  margin-top: 5px;
  font-size: 12px;
}

.validation-success {
  color: #67c23a;
}

.validation-error {
  color: #f56c6c;
}

.validation-loading {
  color: #909399;
}
</style>