<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="90px">
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
      <el-form-item label="所属题库" prop="bankId">
        <el-input
          v-model="queryParams.bankId"
          placeholder="请输入题库ID"
          clearable
          @keyup.enter="handleQuery"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="斩题类型" prop="markedType">
        <el-select
          v-model="queryParams.markedType"
          placeholder="请选择斩题类型"
          clearable
          style="width: 120px"
        >
          <el-option label="错题" :value="1" />
          <el-option label="难题" :value="2" />
          <el-option label="重点" :value="3" />
          <el-option label="易错" :value="4" />
          <el-option label="技巧" :value="5" />
        </el-select>
      </el-form-item>
      <el-form-item label="难度等级" prop="difficultyLevel">
        <el-select
          v-model="queryParams.difficultyLevel"
          placeholder="请选择难度等级"
          clearable
          style="width: 120px"
        >
          <el-option label="简单" :value="1" />
          <el-option label="中等" :value="2" />
          <el-option label="困难" :value="3" />
          <el-option label="极难" :value="4" />
        </el-select>
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
      <el-form-item label="斩题时间" prop="createTime">
        <el-date-picker
          v-model="queryParams.createTime"
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
          v-hasPermi="['questionMarked:questionMarked:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['questionMarked:questionMarked:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['questionMarked:questionMarked:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['questionMarked:questionMarked:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="questionMarkedList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="斩题ID" align="center" prop="markedId" width="80" />
      <el-table-column label="用户ID" align="center" prop="userId" width="80" />
      <el-table-column label="题目ID" align="center" prop="questionId" width="80" />
      <el-table-column label="所属题库" align="center" prop="bankId" width="100" />
      
      <el-table-column label="斩题信息" align="center" width="300">
        <el-table-column label="斩题类型" align="center" prop="markedType" width="100">
          <template #default="scope">
            <el-tag 
              :type="getMarkedTypeTagType(scope.row.markedType)"
              size="small"
            >
              {{ getMarkedTypeText(scope.row.markedType) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="难度等级" align="center" prop="difficultyLevel" width="100">
          <template #default="scope">
            <el-tag 
              :type="getDifficultyTagType(scope.row.difficultyLevel)"
              size="small"
            >
              {{ getDifficultyText(scope.row.difficultyLevel) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="错误次数" align="center" prop="errorTimesBeforeMark" width="100">
          <template #default="scope">
            <el-tag 
              :type="scope.row.errorTimesBeforeMark > 5 ? 'danger' : scope.row.errorTimesBeforeMark > 2 ? 'warning' : 'info'"
              size="small"
            >
              {{ scope.row.errorTimesBeforeMark || 0 }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="掌握进度" align="center" width="200">
        <el-table-column label="掌握状态" align="center" prop="isMastered" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.isMastered == 1 ? 'success' : 'warning'" size="small">
              {{ scope.row.isMastered == 1 ? '已掌握' : '未掌握' }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="复习次数" align="center" prop="reviewCount" width="100">
          <template #default="scope">
            <el-tag type="success" size="small">
              {{ scope.row.reviewCount || 0 }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="时间信息" align="center" width="280">
        <el-table-column label="斩题时间" align="center" prop="createTime" width="140">
          <template #default="scope">
            <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}') }}</span>
          </template>
        </el-table-column>
        
        <el-table-column label="最后复习" align="center" prop="lastReviewTime" width="140">
          <template #default="scope">
            <span v-if="scope.row.lastReviewTime">{{ parseTime(scope.row.lastReviewTime, '{y}-{m}-{d}') }}</span>
            <span v-else class="text-gray">-</span>
          </template>
        </el-table-column>
      </el-table-column>
      
      <el-table-column label="备注标签" align="center" prop="notes" width="200">
        <template #default="scope">
          <div style="max-width: 180px; overflow: hidden; text-overflow: ellipsis;">
            <el-tooltip 
              v-if="scope.row.notes" 
              :content="scope.row.notes" 
              placement="top"
            >
              <span>{{ scope.row.notes.length > 15 ? scope.row.notes.substring(0, 15) + '...' : scope.row.notes }}</span>
            </el-tooltip>
            <span v-else class="text-gray">无</span>
          </div>
          <div v-if="scope.row.tags" style="margin-top: 4px;">
            <el-tag 
              v-for="tag in getTagsArray(scope.row.tags)" 
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
          <el-tooltip content="修改" placement="top">
            <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['questionMarked:questionMarked:edit']"></el-button>
          </el-tooltip>
          <el-tooltip content="删除" placement="top">
            <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['questionMarked:questionMarked:remove']"></el-button>
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

    <!-- 添加或修改用户斩题对话框 -->
    <el-dialog :title="title" v-model="open" width="700px" append-to-body>
      <el-form ref="questionMarkedRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
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
          </el-col>
          <el-col :span="12">
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
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
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
          </el-col>
          <el-col :span="12">
            <el-form-item label="斩题类型" prop="markedType">
              <el-select v-model="form.markedType" placeholder="请选择斩题类型" style="width: 100%">
                <el-option label="错题" :value="1" />
                <el-option label="难题" :value="2" />
                <el-option label="重点" :value="3" />
                <el-option label="易错" :value="4" />
                <el-option label="技巧" :value="5" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="难度等级" prop="difficultyLevel">
              <el-select v-model="form.difficultyLevel" placeholder="请选择难度等级" style="width: 100%">
                <el-option label="简单" :value="1" />
                <el-option label="中等" :value="2" />
                <el-option label="困难" :value="3" />
                <el-option label="极难" :value="4" />
              </el-select>
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
        
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="错误次数" prop="errorTimesBeforeMark">
              <el-input-number 
                v-model="form.errorTimesBeforeMark" 
                :min="0" 
                :max="999" 
                placeholder="斩题前错误次数"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="复习次数" prop="reviewCount">
              <el-input-number 
                v-model="form.reviewCount" 
                :min="0" 
                :max="999" 
                placeholder="已复习次数"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        
        <el-row :gutter="20">
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
        </el-row>
        
        <el-form-item label="斩题备注" prop="notes">
          <el-input
            v-model="form.notes"
            type="textarea"
            :rows="3"
            placeholder="请输入斩题备注，如解题思路、技巧总结等"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
        
        <el-form-item label="标签" prop="tags">
          <el-select
            v-model="formTagsArray"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="请输入或选择标签"
            style="width: 100%"
          >
            <el-option
              v-for="tag in commonTags"
              :key="tag"
              :label="tag"
              :value="tag"
            />
          </el-select>
          <div class="tag-hint">如：难题,重点,易错,技巧</div>
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
defineOptions({ name: 'QuestionMarked' })
import { listQuestionMarked, getQuestionMarked, delQuestionMarked, addQuestionMarked, updateQuestionMarked } from "@/api/questionMarked/questionMarked"
import { checkQuestionExists, getQuestionSimpleInfo, checkUserExists, checkQuestionAndUser } from "@/api/questionMain/questionMain"
import { listQuestionBankAll } from "@/api/questionBank/questionBank"
import dayjs from 'dayjs'

const { proxy } = getCurrentInstance()

const questionMarkedList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")
const submitLoading = ref(false)

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

const commonTags = ref(['难题', '重点', '易错', '技巧', '高频', '基础', '进阶', '综合', '经典', '压轴'])

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    questionId: null,
    bankId: null,
    notes: null,
    tags: null,
    markedType: null,
    difficultyLevel: null,
    errorTimesBeforeMark: null,
    correctTimesBeforeMark: null,
    reviewCount: null,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: null,
    masteryDate: null,
    markedStatus: null,
    createTime: null,
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
    markedType: [
      { required: true, message: "斩题类型不能为空", trigger: "change" }
    ],
    difficultyLevel: [
      { required: true, message: "难度等级不能为空", trigger: "change" }
    ],
    isMastered: [
      { required: true, message: "掌握状态不能为空", trigger: "change" }
    ],
    errorTimesBeforeMark: [
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
        
        // 自动填充难度信息（仅在未设置时兜底：编辑既有记录时不要用题目难度
        // 覆盖用户已保存的斩题难度，否则「修改」对话框一开一存难度就被改掉）
        if (response.data.difficulty && !form.value.difficultyLevel) {
          // 将题目难度转换为斩题难度等级
          const difficultyMap = {
            1: 1, // 简单
            2: 2, // 中等
            3: 3, // 困难
            4: 4  // 极难
          }
          form.value.difficultyLevel = difficultyMap[response.data.difficulty] || 2
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
        
        // 自动填充难度信息
        if (data.difficulty) {
          const difficultyMap = {
            1: 1,
            2: 2,
            3: 3,
            4: 4
          }
          form.value.difficultyLevel = difficultyMap[data.difficulty] || 2
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

/** 查询用户斩题（重点攻克题目）列表 */
function getList() {
  loading.value = true
  
  // 处理时间范围查询
  const params = { ...queryParams.value }
  if (params.createTime && Array.isArray(params.createTime)) {
    params.beginCreateTime = params.createTime[0]
    params.endCreateTime = params.createTime[1]
    delete params.createTime
  }
  
  listQuestionMarked(params).then(response => {
    questionMarkedList.value = response.rows
    total.value = response.total
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
    markedId: null,
    userId: null,
    questionId: null,
    bankId: null,
    notes: null,
    tags: null,
    markedType: null,
    difficultyLevel: null,
    errorTimesBeforeMark: 0,
    correctTimesBeforeMark: 0,
    reviewCount: 0,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: 0,
    masteryDate: null,
    markedStatus: 1,
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
  
  proxy.resetForm("questionMarkedRef")
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
    notes: null,
    tags: null,
    markedType: null,
    difficultyLevel: null,
    errorTimesBeforeMark: null,
    correctTimesBeforeMark: null,
    reviewCount: null,
    lastReviewTime: null,
    nextReviewTime: null,
    isMastered: null,
    masteryDate: null,
    markedStatus: null,
    createTime: null,
  }
  handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.markedId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加用户斩题"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _markedId = row.markedId || ids.value
  getQuestionMarked(_markedId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改用户斩题"
    
    // 如果有题目ID，验证并加载题目信息
    if (form.value.questionId) {
      validateQuestionId()
    }
    
    // 如果有题库ID，加载题库名称
    if (form.value.bankId) {
      loadBankName(form.value.bankId)
    }
    
    // 如果有用户ID，验证用户
    if (form.value.userId) {
      validateUserId()
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
    await proxy.$refs["questionMarkedRef"].validate()
    
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
      errorTimesBeforeMark: form.value.errorTimesBeforeMark || 0,
      correctTimesBeforeMark: form.value.correctTimesBeforeMark || 0,
      reviewCount: form.value.reviewCount || 0,
      difficultyLevel: form.value.difficultyLevel || 2,
      isMastered: form.value.isMastered || 0,
      markedStatus: form.value.markedStatus || 1
    }
    
    if (submitData.markedId != null) {
      await updateQuestionMarked(submitData)
      proxy.$modal.msgSuccess("修改成功")
    } else {
      await addQuestionMarked(submitData)
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
  const _markedIds = row.markedId || ids.value
  const count = Array.isArray(_markedIds) ? _markedIds.length : 1
  
  proxy.$modal.confirm(`是否确认删除${count}条斩题记录？`).then(function() {
    return delQuestionMarked(_markedIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  // 处理时间范围查询参数
  const exportParams = { ...queryParams.value }
  if (exportParams.createTime && Array.isArray(exportParams.createTime)) {
    exportParams.beginCreateTime = exportParams.createTime[0]
    exportParams.endCreateTime = exportParams.createTime[1]
    delete exportParams.createTime
  }
  
  proxy.download('questionMarked/questionMarked/export', exportParams, `斩题记录_${new Date().getTime()}.xlsx`)
}

// 工具函数
function getTagsArray(tags) {
  if (!tags) return []
  return tags.split(',').filter(tag => tag.trim())
}

// 状态显示函数
function getMarkedTypeText(value) {
  const map = {
    1: '错题',
    2: '难题',
    3: '重点',
    4: '易错',
    5: '技巧'
  }
  return map[value] || '未知'
}

function getMarkedTypeTagType(value) {
  const map = {
    1: 'danger',    // 错题 - 红色
    2: 'warning',   // 难题 - 橙色
    3: 'primary',   // 重点 - 蓝色
    4: 'info',      // 易错 - 青色
    5: 'success'    // 技巧 - 绿色
  }
  return map[value] || ''
}

function getDifficultyText(value) {
  const map = {
    1: '简单',
    2: '中等',
    3: '困难',
    4: '极难'
  }
  return map[value] || '未知'
}

function getDifficultyTagType(value) {
  const map = {
    1: 'success',   // 简单 - 绿色
    2: 'primary',   // 中等 - 蓝色
    3: 'warning',   // 困难 - 橙色
    4: 'danger'     // 极难 - 红色
  }
  return map[value] || ''
}

/** 下次复习时间状态 */
function getNextReviewStatus(nextReviewTime) {
  if (!nextReviewTime) return 'info'
  
  const now = dayjs()
  const reviewTime = dayjs(nextReviewTime)
  const diffDays = reviewTime.diff(now, 'day')
  
  if (diffDays < 0) return 'danger'  // 已过期
  if (diffDays <= 1) return 'warning' // 即将到期
  return 'success' // 未到期
}

// 初始化
onMounted(() => {
  getList()
})
</script>

<style scoped>
.app-container {
  padding: 20px;
}

.text-gray {
  color: #909399;
  font-style: italic;
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

.tag-item {
  margin: 1px;
}

.notes-text {
  color: #606266;
  font-size: 12px;
}

.tag-hint {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.el-table .cell {
  white-space: nowrap;
}

.el-table .cell .el-tag {
  margin: 1px;
}

/* 确保表格列宽合适 */
.el-table--small .el-table__cell {
  padding: 4px 0;
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

:deep(.el-table .cell) {
  line-height: 1.5;
}

:deep(.el-table .el-tag) {
  margin: 2px;
}
</style>