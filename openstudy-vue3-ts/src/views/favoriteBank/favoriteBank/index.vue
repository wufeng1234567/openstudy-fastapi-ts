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
      <el-form-item label="题库名称" prop="bankName">
        <el-input
          v-model="queryParams.bankName"
          placeholder="请输入题库名称"
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
          style="width: 120px"
        >
          <el-option label="有效" :value="1" />
          <el-option label="失效" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item label="最后学习时间" prop="lastStudyTime">
        <el-date-picker clearable
          v-model="queryParams.lastStudyTime"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="请选择最后学习时间">
        </el-date-picker>
      </el-form-item>
      <el-form-item label="学习次数" prop="studyCount">
        <el-input
          v-model="queryParams.studyCount"
          placeholder="请输入学习次数"
          clearable
          @keyup.enter="handleQuery"
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
          v-hasPermi="['favoriteBank:favoriteBank:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['favoriteBank:favoriteBank:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['favoriteBank:favoriteBank:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['favoriteBank:favoriteBank:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="favoriteBankList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="收藏ID" align="center" prop="favoriteId" />
      <el-table-column label="用户ID" align="center" prop="userId" />
      <el-table-column label="题库ID" align="center" prop="bankId" />
      <el-table-column label="题库名称" align="center" prop="bankName" width="160"/>
      <el-table-column label="收藏备注" align="center" prop="notes" />
      <el-table-column label="标签" align="center" prop="tags" />
      <el-table-column label="排序" align="center" prop="sortOrder" />
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
      <el-table-column label="最后学习时间" align="center" prop="lastStudyTime" width="140">
        <template #default="scope">
          <span>{{ parseTime(scope.row.lastStudyTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="学习次数" align="center" prop="studyCount" />
      <el-table-column label="收藏状态" align="center" prop="favoriteStatus">
        <template #default="scope">
          <el-tag
            :type="scope.row.favoriteStatus === 1 ? 'success' : 'danger'"
            size="small"
          >
            {{ scope.row.favoriteStatus === 1 ? '有效' : '失效' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="140">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['favoriteBank:favoriteBank:edit']">修改</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['favoriteBank:favoriteBank:remove']">删除</el-button>
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

    <!-- 添加或修改用户题库收藏对话框 -->
    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="favoriteBankRef" :model="form" :rules="rules" label-width="120px">
        <el-form-item label="用户ID" prop="userId">
          <el-input v-model="form.userId" placeholder="请输入用户ID" />
        </el-form-item>
        <el-form-item label="题库ID" prop="bankId">
          <el-input
            v-model="form.bankId"
            placeholder="请输入有效的题库ID"
            @blur="validateBankId"
            @input="clearBankError"
          />
          <!-- 验证结果提示 -->
          <div v-if="bankError" style="color: #f56c6c; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-warning-outline"></i> {{ bankError }}
          </div>
          <div v-else-if="bankValid && bankInfo" style="color: #67c23a; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-circle-check"></i> {{ bankInfo }}
          </div>
          <div v-else-if="bankValidating" style="color: #909399; font-size: 12px; margin-top: 5px;">
            <i class="el-icon-loading"></i> 正在验证题库ID...
          </div>
        </el-form-item>
        <el-form-item label="题库名称" prop="bankName">
          <el-input 
            v-model="bankName" 
            placeholder="题库名称将自动填充" 
            disabled
          />
        </el-form-item>
        <el-form-item label="收藏备注" prop="notes">
          <el-input v-model="form.notes" placeholder="请输入收藏备注" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="标签" prop="tags">
          <el-input v-model="form.tags" placeholder="请输入标签，多个用逗号分隔" />
        </el-form-item>
        <el-form-item label="排序" prop="sortOrder">
          <el-input-number
            v-model="form.sortOrder"
            placeholder="请输入排序，数字越小越靠前"
            :min="0"
            controls-position="right"
            style="width: 100%"
          />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="是否标星" prop="isStarred">
              <el-radio-group v-model="form.isStarred">
                <el-radio :label="1">已标星</el-radio>
                <el-radio :label="0">未标星</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="收藏状态" prop="favoriteStatus">
              <el-radio-group v-model="form.favoriteStatus">
                <el-radio :label="1">有效</el-radio>
                <el-radio :label="0">失效</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="最后学习时间" prop="lastStudyTime">
              <el-date-picker clearable
                v-model="form.lastStudyTime"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                placeholder="请选择最后学习时间"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="学习次数" prop="studyCount">
              <el-input-number
                v-model="form.studyCount"
                placeholder="请输入学习次数"
                :min="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <!-- 与「斩题管理」一致：题库ID 校验未通过时不允许提交（历史上会出现"提示不存在却照样入库"） -->
          <el-button type="primary" @click="submitForm" :disabled="!bankValid">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FavoriteBank' })
import { listFavoriteBank, getFavoriteBank, delFavoriteBank, addFavoriteBank, updateFavoriteBank, checkBankExists, listQuestionBankAll } from "@/api/favoriteBank/favoriteBank"


const { proxy } = getCurrentInstance()

const favoriteBankList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")

// 题库验证相关变量
const bankValidating = ref(false)  // 验证加载状态
const bankValid = ref(false)       // 验证是否成功
const bankError = ref("")          // 验证错误信息
const bankInfo = ref("")           // 题库信息（验证成功后显示）
const bankName = ref("")           // 题库名称

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    userId: null,
    bankId: null,
    bankName: null,
    notes: null,
    tags: null,
    isStarred: null,
    lastStudyTime: null,
    studyCount: null,
    favoriteStatus: null,
  },
  rules: {
    userId: [
      { required: true, message: "用户ID不能为空", trigger: "blur" },
      { pattern: /^\d+$/, message: "用户ID必须为数字", trigger: "blur" }
    ],
    bankId: [
      { required: true, message: "题库ID不能为空", trigger: "blur" },
      { pattern: /^\d+$/, message: "题库ID必须为数字", trigger: "blur" }
    ],
    sortOrder: [
      { type: 'number', min: 0, message: '排序不能小于0', trigger: 'blur' }
    ],
    studyCount: [
      { type: 'number', min: 0, message: '学习次数不能小于0', trigger: 'blur' }
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

/** 查询用户题库收藏列表 */
function getList() {
  loading.value = true
  
  // 同时加载收藏列表和题库列表
  Promise.all([
    listFavoriteBank(queryParams.value),
    listQuestionBankAll({})
  ]).then(([favResponse, bankResponse]) => {
    favoriteBankList.value = favResponse.rows
    total.value = favResponse.total
    
    // 题库名称兜底：后端 _format_favorite_bank 已经返回 bankName；
    // 而题库下拉（/questionBank/all）只含「公开 OR 自己的 OR 分享给我的」，
    // 后台管理员查看他人收藏时并不包含对方题库——若直接用下拉结果覆盖，
    // 会把正确的题库名冲成「未知题库」。
    const bankList: any[] = (bankResponse.code === 200 && Array.isArray(bankResponse.data)) ? bankResponse.data : []
    favoriteBankList.value.forEach((item: any) => {
      const bank = item.bankId ? bankList.find((b: any) => b.id === item.bankId) : null
      item.bankName = (bank && bank.bankName) || item.bankName ||
        (item.bankId ? `题库ID: ${item.bankId}` : "无题库")
    })
    
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
    bankId: null,
    notes: null,
    tags: null,
    sortOrder: 0,
    isStarred: 0,
    lastStudyTime: null,
    studyCount: 0,
    favoriteStatus: 1,
    createTime: null,
    updateTime: null
  }
  
  // 重置验证状态
  bankValidating.value = false
  bankValid.value = false
  bankError.value = ""
  bankInfo.value = ""
  bankName.value = ""
  
  proxy.resetForm("favoriteBankRef")
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
  title.value = "添加用户题库收藏"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _favoriteId = row.favoriteId || ids.value
  getFavoriteBank(_favoriteId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改用户题库收藏"
    
    // 题库名称/校验状态：优先用行数据，拿不到就按题库ID重新校验一次
    // （工具栏点「修改」时 row 是事件对象，没有 bankName）
    if (row.bankName) {
      bankName.value = row.bankName
      bankValid.value = true
      bankInfo.value = row.bankName
    } else if (form.value.bankId) {
      validateBankId()
    }
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["favoriteBankRef"].validate(valid => {
    if (valid) {
      if (form.value.favoriteId != null) {
        updateFavoriteBank(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addFavoriteBank(form.value).then(response => {
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
    return delFavoriteBank(_favoriteIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('favoriteBank/favoriteBank/export', {
    ...queryParams.value
  }, `favoriteBank_${new Date().getTime()}.xlsx`)
}

// ==================== 题库验证相关方法 ====================

/** 验证题库ID是否存在 */
function validateBankId() {
  const bankId = form.value.bankId
  if (!bankId || isNaN(bankId)) {
    bankError.value = "请输入有效的题库ID"
    bankValid.value = false
    return
  }
  
  bankValidating.value = true
  bankError.value = ""
  bankValid.value = false
  bankInfo.value = ""
  bankName.value = ""
  
  checkBankExists(bankId).then(response => {
    if (response.code === 200 && (response.data === true || (response.data && response.data.exists === true))) {
      bankValid.value = true
      
      // 构建显示信息
      let infoText = `题库ID: ${bankId}`
      if (response.data.bankName) {
        infoText = response.data.bankName
        bankInfo.value = `${infoText} (ID: ${bankId})`
        bankName.value = response.data.bankName
      } else {
        bankInfo.value = `题库ID: ${bankId} 验证成功`
        bankName.value = `题库ID: ${bankId}`
      }
      bankError.value = ""
    } else {
      bankValid.value = false
      bankError.value = "题库ID不存在，请检查输入"
    }
  }).catch(error => {
    bankValid.value = false
    bankError.value = error.msg || "验证失败，请稍后重试"
  }).finally(() => {
    bankValidating.value = false
  })
}

// 清除题库错误信息（当用户重新输入时）
function clearBankError() {
  bankError.value = ""
  bankValid.value = false
  bankInfo.value = ""
  bankName.value = ""
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