<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="用户ID" prop="userId">
        <el-input
          v-model="queryParams.userId"
          placeholder="请输入用户ID"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="题目ID" prop="questionId">
        <el-input
          v-model="queryParams.questionId"
          placeholder="请输入题目ID"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="收藏备注" prop="notes">
        <el-input
          v-model="queryParams.notes"
          placeholder="请输入收藏备注"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="标签" prop="tags">
        <el-input
          v-model="queryParams.tags"
          placeholder="请输入标签"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="难度评级" prop="difficultyRating">
        <el-select
          v-model="queryParams.difficultyRating"
          placeholder="请选择难度评级"
          clearable
          style="width: 120px"
        >
          <el-option label="1星" :value="1" />
          <el-option label="2星" :value="2" />
          <el-option label="3星" :value="3" />
          <el-option label="4星" :value="4" />
          <el-option label="5星" :value="5" />
        </el-select>
      </el-form-item>
      <el-form-item label="错误次数" prop="errorTimes">
        <el-input-number
          v-model="queryParams.errorTimes"
          placeholder="错误次数"
          :min="0"
          controls-position="right"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="正确次数" prop="correctTimes">
        <el-input-number
          v-model="queryParams.correctTimes"
          placeholder="正确次数"
          :min="0"
          controls-position="right"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="最后复习时间" prop="lastReviewTime">
        <el-date-picker clearable
          v-model="queryParams.lastReviewTime"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="请选择最后复习时间">
        </el-date-picker>
      </el-form-item>
      <el-form-item label="下次复习时间" prop="nextReviewTime">
        <el-date-picker clearable
          v-model="queryParams.nextReviewTime"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="请选择下次复习时间">
        </el-date-picker>
      </el-form-item>
      <el-form-item label="复习次数" prop="reviewCount">
        <el-input-number
          v-model="queryParams.reviewCount"
          placeholder="复习次数"
          :min="0"
          controls-position="right"
          style="width: 120px"
        />
      </el-form-item>
      <el-form-item label="是否标星" prop="isStarred">
        <el-select
          v-model="queryParams.isStarred"
          placeholder="请选择标星状态"
          clearable
          style="width: 120px"
        >
          <el-option label="已标星" :value="1" />
          <el-option label="未标星" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item label="收藏状态" prop="favoriteStatus">
        <el-select
          v-model="queryParams.favoriteStatus"
          placeholder="请选择收藏状态"
          clearable
          style="width: 140px"
        >
          <el-option label="正常收藏" :value="1" />
          <el-option label="已掌握" :value="2" />
          <el-option label="待复习" :value="3" />
          <el-option label="取消收藏" :value="0" />
        </el-select>
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
          v-hasPermi="['favoriteQuestion:favoriteQuestion:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['favoriteQuestion:favoriteQuestion:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['favoriteQuestion:favoriteQuestion:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['favoriteQuestion:favoriteQuestion:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="favoriteQuestionList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="收藏ID" align="center" prop="favoriteId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <el-table-column label="题目ID" align="center" prop="questionId" />
      <el-table-column label="所属题库" align="center" prop="bankName" width="160"/>
      <el-table-column label="收藏备注" align="center" prop="notes" />
      <el-table-column label="难度评级" align="center" prop="difficultyRating" width="160">
        <template #default="scope">
          <el-rate
            v-model="scope.row.difficultyRating"
            disabled
            :max="5"
            :colors="['#99A9BF', '#F7BA2A', '#FF9900']"
            style="display: inline-block"
          />
          <span style="margin-left: 8px; font-size: 12px">{{ scope.row.difficultyRating }}星</span>
        </template>
      </el-table-column>
      <el-table-column label="错误次数" align="center" prop="errorTimes" />
      <el-table-column label="正确次数" align="center" prop="correctTimes" />
      <el-table-column label="最后复习时间" align="center" prop="lastReviewTime" width="120">
        <template #default="scope">
          <span>{{ parseTime(scope.row.lastReviewTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="下次复习时间" align="center" prop="nextReviewTime" width="120">
        <template #default="scope">
          <span>{{ parseTime(scope.row.nextReviewTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="复习次数" align="center" prop="reviewCount" />
      <el-table-column label="是否标星" align="center" prop="isStarred">
        <template #default="scope">
          <el-tag
            :type="scope.row.isStarred === 1 ? 'warning' : 'info'"
            size="small"
          >
            {{ scope.row.isStarred === 1 ? '已标星' : '未标星' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="收藏状态" align="center" prop="favoriteStatus">
        <template #default="scope">
          <el-tag
            :type="getStatusTagType(scope.row.favoriteStatus)"
            size="small"
          >
            {{ getStatusText(scope.row.favoriteStatus) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="180">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['favoriteQuestion:favoriteQuestion:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['favoriteQuestion:favoriteQuestion:remove']">删除</el-button>
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

    <!-- 添加或修改用户题目收藏（支持复习功能）对话框 -->
    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="favoriteQuestionRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="用户ID" prop="userId">
          <el-input v-model="form.userId" placeholder="请输入用户ID" />
        </el-form-item>
       <el-form-item label="题目ID" prop="questionId">
          <el-input
            v-model="form.questionId"
            placeholder="请输入有效的题目ID"
            @blur="validateQuestionId"
            @input="clearQuestionError"
          >
           
          </el-input>
          <!-- 验证结果提示 -->
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
        <div v-if="bankName" style="color: #67c23a; font-size: 14px; ">
          <i class="el-icon-notebook-2" style="margin-right: 6px;"></i>
          <span style="font-weight: 500;">题库名称：</span>{{ bankName }}
        </div>
        
        <!-- 加载状态 -->
        <div v-else-if="form.bankId && !bankName" style="color: #606266; font-size: 14px;  ">
          <i class="el-icon-loading" style="margin-right: 6px;"></i>
          正在加载题库名称...
        </div>
      </div>
      </el-form-item>
        <el-form-item label="收藏备注" prop="notes">
          <el-input v-model="form.notes" placeholder="请输入收藏备注" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-input v-model="form.tags" placeholder="请输入标签，多个用逗号分隔" />
        </el-form-item>
        <el-form-item label="难度评级" prop="difficultyRating">
          <el-rate
            v-model="form.difficultyRating"
            :max="5"
            :colors="['#99A9BF', '#F7BA2A', '#FF9900']"
          />
          <span style="margin-left: 8px; color: #666">{{ form.difficultyRating || 0 }}星</span>
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="错误次数" prop="errorTimes">
              <el-input-number
                v-model="form.errorTimes"
                :min="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="正确次数" prop="correctTimes">
              <el-input-number
                v-model="form.correctTimes"
                :min="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="最后复习时间" prop="lastReviewTime">
              <el-date-picker clearable
                v-model="form.lastReviewTime"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="请选择最后复习时间"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="下次复习时间" prop="nextReviewTime">
              <el-date-picker clearable
                v-model="form.nextReviewTime"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="请选择下次复习时间"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="复习次数" prop="reviewCount">
          <el-input-number
            v-model="form.reviewCount"
            :min="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="是否标星" prop="isStarred">
          <el-radio-group v-model="form.isStarred">
            <el-radio :label="1">已标星</el-radio>
            <el-radio :label="0">未标星</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="收藏状态" prop="favoriteStatus">
          <el-radio-group v-model="form.favoriteStatus">
            <el-radio :label="1">正常收藏</el-radio>
            <el-radio :label="2">已掌握</el-radio>
            <el-radio :label="3">待复习</el-radio>
            <el-radio :label="0">取消收藏</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <!-- 与「斩题管理」一致：题目ID 校验未通过时不允许提交（历史上会出现"提示不存在却照样入库"） -->
          <el-button type="primary" @click="submitForm" :disabled="!questionValid">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FavoriteQuestion' })
import { listFavoriteQuestion, getFavoriteQuestion, delFavoriteQuestion, addFavoriteQuestion, updateFavoriteQuestion,checkQuestionExists } from "@/api/favoriteQuestion/favoriteQuestion"
import { listQuestionBankAll } from "@/api/questionBank/questionBank"  // 添加这行导入

const { proxy } = getCurrentInstance()

const favoriteQuestionList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")

// 题目验证相关变量（添加到现有的变量后面）
const questionValidating = ref(false)  // 验证加载状态
const questionValid = ref(false)       // 验证是否成功
const questionError = ref("")          // 验证错误信息
const questionTitle = ref("")          // 题目标题（验证成功后显示）

// 题库相关变量
const bankName = ref("")
const bankLoading = ref(false)

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
    difficultyRating: null,
    errorTimes: null,
    correctTimes: null,
    lastReviewTime: null,
    nextReviewTime: null,
    reviewCount: null,
    isStarred: null,
    favoriteStatus: null,
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
    errorTimes: [
      { type: 'number', min: 0, message: '错误次数不能小于0', trigger: 'blur' }
    ],
    correctTimes: [
      { type: 'number', min: 0, message: '正确次数不能小于0', trigger: 'blur' }
    ],
    reviewCount: [
      { type: 'number', min: 0, message: '复习次数不能小于0', trigger: 'blur' }
    ],
    isStarred: [
      { required: true, message: "请选择标星状态", trigger: "change" }
    ],
    favoriteStatus: [
      { required: true, message: "请选择收藏状态", trigger: "change" }
    ]
  }
})

const { queryParams, form, rules } = toRefs(data)

// 获取状态标签类型
function getStatusTagType(status) {
  const map = {
    0: 'info',    // 取消收藏
    1: 'success', // 正常收藏
    2: 'primary', // 已掌握
    3: 'warning'  // 待复习
  }
  return map[status] || 'info'
}

// 获取状态文本
function getStatusText(status) {
  const map = {
    0: '取消收藏',
    1: '正常收藏',
    2: '已掌握',
    3: '待复习'
  }
  return map[status] || '未知'
}

/** 查询用户题目收藏（支持复习功能）列表 */
function getList() {
  loading.value = true
  
  // 同时加载收藏列表和题库列表
  Promise.all([
    listFavoriteQuestion(queryParams.value),
    listQuestionBankAll({})
  ]).then(([favResponse, bankResponse]) => {
    favoriteQuestionList.value = favResponse.rows
    total.value = favResponse.total
    
    // 题库名称兜底：后端 _format_favorite_question 已经返回 bankName；
    // 题库下拉（/questionBank/all）只含「公开 OR 自己的 OR 分享给我的」，
    // 后台管理员查看他人收藏时并不包含对方题库——直接用下拉覆盖会冲成「未知题库」。
    const bankList: any[] = (bankResponse.code === 200 && Array.isArray(bankResponse.data)) ? bankResponse.data : []
    favoriteQuestionList.value.forEach((item: any) => {
      const bank = item.bankId ? bankList.find((b: any) => b.id === item.bankId) : null
      item.bankName = (bank && bank.bankName) || item.bankName ||
        (item.bankId ? `题库ID: ${item.bankId}` : "无题库")
    })
    
    console.log('处理后的列表数据:', favoriteQuestionList.value)
    loading.value = false
  }).catch(error => {
    console.error('加载数据失败:', error)
    loading.value = false
    proxy.$modal.msgError("加载列表失败")
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
    favoriteId: null,
    userId: null,
    questionId: null,
    bankId: null,
    notes: null,
    tags: null,
    difficultyRating: 3,
    errorTimes: 0,
    correctTimes: 0,
    lastReviewTime: null,
    nextReviewTime: null,
    reviewCount: 0,
    isStarred: 0,
    favoriteStatus: 1,
    createTime: null,
    updateTime: null
  }
  
  // 重置验证状态
  questionValidating.value = false
  questionValid.value = false
  questionError.value = ""
  questionTitle.value = ""
  bankName.value = ""  // 重置题库名称
  
  proxy.resetForm("favoriteQuestionRef")
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef")
  queryParams.value.pageNum = 1
  getList()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.favoriteId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加用户题目收藏"
}



/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _favoriteId = row.favoriteId || ids.value
  getFavoriteQuestion(_favoriteId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改用户题目收藏"
    
    
    // 题库名称/校验状态：优先用行数据，拿不到就按题目ID重新校验一次
    // （工具栏点「修改」时 row 是事件对象，没有 bankName）
    if (row.bankName) {
      bankName.value = row.bankName
    }
    if (form.value.questionId) {
      validateQuestionId()
    }
  })
}


/** 提交按钮 */
function submitForm() {
  proxy.$refs["favoriteQuestionRef"].validate(valid => {
    if (valid) {
      if (form.value.favoriteId != null) {
        updateFavoriteQuestion(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addFavoriteQuestion(form.value).then(response => {
          proxy.$modal.msgSuccess("新增成功")
          open.value = false
          getList()
        })
      }
    }
  })
}
/** 删除按钮操作 */
function handleDelete(row) {
  const _favoriteIds = row.favoriteId || ids.value
  const count = Array.isArray(_favoriteIds) ? _favoriteIds.length : 1
  
  proxy.$modal.confirm(`是否确认删除${count}条收藏记录？`).then(function() {
    return delFavoriteQuestion(_favoriteIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('favoriteQuestion/favoriteQuestion/export', {
    ...queryParams.value
  }, `favoriteQuestion_${new Date().getTime()}.xlsx`)
}


// ==================== 题目验证相关方法 ====================

/** 验证题目ID是否存在 */
function validateQuestionId() {
  const questionId = form.value.questionId
  if (!questionId || isNaN(questionId)) {
    questionError.value = "请输入有效的题目ID"
    questionValid.value = false
    return
  }
  
  questionValidating.value = true
  questionError.value = ""
  questionValid.value = false
  questionTitle.value = ""
  bankName.value = ""  // 清除之前的题库名称
  
  checkQuestionExists(questionId).then(response => {
    if (response.code === 200 && (response.data === true || (response.data && response.data.exists === true))) {
      questionValid.value = true
      
      // 构建显示信息
      let infoText = `题目ID: ${questionId}`
      if (response.data.title && response.data.title !== `题目ID: ${questionId}`) {
        // 如果有真实的题目标题
        infoText = response.data.title
        questionTitle.value = `${infoText} (ID: ${questionId})`
      } else {
        // 如果没有题目标题，只显示ID
        questionTitle.value = `题目ID: ${questionId} 验证成功`
      }
      questionError.value = ""
      
     // 自动填充题库信息
    if (response.data.bankId) {
      form.value.bankId = response.data.bankId
      
      // 显示题库名称
      if (response.data.bankName) {
        bankName.value = response.data.bankName
      } else if (response.data.bankId) {
        // 如果后端没有返回题库名称，我们可以暂时不显示
        // 等列表加载时会自动填充
        bankName.value = `题库ID: ${response.data.bankId}`
      }
    }
      
      // 自动填充难度信息
      if (response.data.difficulty) {
        form.value.difficultyRating = response.data.difficulty
      }
    } else {
      questionValid.value = false
      questionError.value = "题目ID不存在，请检查输入"
    }
  }).catch(error => {
    questionValid.value = false
    questionError.value = error.msg || "验证失败，请稍后重试"
  }).finally(() => {
    questionValidating.value = false
  })
}

// 清除题目错误信息（当用户重新输入时）
function clearQuestionError() {
  questionError.value = ""
  questionValid.value = false
  questionTitle.value = ""
}

getList()
</script>

<style scoped>
:deep(.el-tag) {
  cursor: default;
}

:deep(.el-table .cell) {
  white-space: nowrap;
}

:deep(.el-rate) {
  display: inline-flex;
  align-items: center;
}

:deep(.el-input-group__append) {
  background-color: transparent;
  border-left: none;
  padding: 0;
}

:deep(.el-button--link) {
  padding: 0 10px;
  height: 32px;
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