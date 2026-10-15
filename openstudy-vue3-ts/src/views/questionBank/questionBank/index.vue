<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="题库名称" prop="bankName">
        <el-input v-model="queryParams.bankName" placeholder="请输入题库名称" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="分类" prop="subject">
        <el-input v-model="queryParams.subject" placeholder="请输入分类" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="请选择状态" clearable style="width: 120px">
          <el-option v-for="dict in common_status" :key="dict.value" :label="dict.label" :value="dict.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="创建者" prop="userId">
        <el-input v-model="queryParams.userId" placeholder="请输入创建者ID" clearable @keyup.enter="handleQuery" />
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
        <el-button type="primary" plain icon="Plus" @click="handleAdd"
          v-hasPermi="['questionBank:questionBank:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success" plain icon="Edit" :disabled="single" @click="handleUpdate"
          v-hasPermi="['questionBank:questionBank:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger" plain icon="Delete" :disabled="multiple" @click="handleDelete"
          v-hasPermi="['questionBank:questionBank:remove']">删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport"
          v-hasPermi="['questionBank:questionBank:export']">导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="questionBankList" @selection-change="handleSelectionChange" row-key="bankId">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="题库ID" align="center" prop="bankId" width="80" />
      <el-table-column label="题库名称" align="center" prop="bankName" min-width="140" show-overflow-tooltip />
      <el-table-column label="分类" align="center" prop="subject" width="100" />
      <el-table-column label="题目数量" align="center" prop="totalQuestions" width="90" />
      <el-table-column label="封面图" align="center" prop="coverImage" width="80">
        <template #default="scope">
          <image-preview :src="scope.row.coverImage" :width="40" :height="40" v-if="scope.row.coverImage" />
        </template>
      </el-table-column>
      <el-table-column label="创建者ID" align="center" prop="userId" width="100" />
      <el-table-column label="状态" align="center" prop="status" width="80">
        <template #default="scope">
          <dict-tag :options="common_status" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="创建时间" align="center" prop="createTime" width="170">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="130">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)"
            v-hasPermi="['questionBank:questionBank:edit']">修改</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)"
            v-hasPermi="['questionBank:questionBank:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize" @pagination="getList" />

    <el-dialog :title="title" v-model="open" width="550px" append-to-body>
      <el-form ref="questionBankRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="题库名称" prop="bankName">
          <el-input v-model="form.bankName" placeholder="请输入题库名称" />
        </el-form-item>
        <el-form-item label="分类" prop="subject">
          <el-input v-model="form.subject" placeholder="请输入分类" />
        </el-form-item>
        <el-form-item label="题库描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入题库描述" />
        </el-form-item>
        <el-form-item label="封面图" prop="coverImage">
          <image-upload v-model="form.coverImage" />
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio v-for="dict in common_status" :key="dict.value" :value="dict.value">
              {{ dict.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="submitForm">确 定</el-button>
          <el-button @click="cancel">取 消</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'QuestionBank' })

import { listQuestionBank, getQuestionBank, delQuestionBank, addQuestionBank, updateQuestionBank } from '@/api/questionBank/questionBank'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()
const { common_status } = proxy.useDict('common_status')

const questionBankList = ref<any[]>([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref<number[]>([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref('')

const dateRange = ref<string[]>([])

const data = reactive({
  form: {} as any,
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    bankName: null,
    subject: null as string | null,
    status: null,
    userId: null as number | null,
    beginTime: null as string | null,
    endTime: null as string | null,
    params: {} as any
  },
  rules: {
    bankName: [
      { required: true, message: '题库名称不能为空', trigger: 'blur' }
    ]
  }
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  if (dateRange.value && dateRange.value.length > 0) {
    queryParams.value.beginTime = dateRange.value[0]
    queryParams.value.endTime = dateRange.value[1]
  } else {
    queryParams.value.beginTime = null
    queryParams.value.endTime = null
  }
  listQuestionBank(queryParams.value).then((response: any) => {
    questionBankList.value = response.rows || []
    total.value = response.total || 0
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

function cancel() {
  open.value = false
  reset()
}

function reset() {
  form.value = {
    bankId: null,
    bankName: null,
    subject: null,
    description: null,
    coverImage: null,
    status: '0',
    userId: null
  }
  proxy.resetForm('questionBankRef')
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  dateRange.value = []
  proxy.resetForm('queryRef')
  queryParams.value.beginTime = null
  queryParams.value.endTime = null
  handleQuery()
}

function handleSelectionChange(selection: any[]) {
  ids.value = selection.map((item: any) => item.bankId)
  single.value = selection.length !== 1
  multiple.value = selection.length === 0
}

function handleAdd() {
  reset()
  open.value = true
  title.value = '添加题库'
}

function handleUpdate(row: any) {
  reset()
  const _id = row.bankId || ids.value[0]
  getQuestionBank(_id).then((response: any) => {
    form.value = response.data
    open.value = true
    title.value = '修改题库'
  })
}

function submitForm() {
  proxy.$refs['questionBankRef'].validate((valid: boolean) => {
    if (valid) {
      if (form.value.bankId != null) {
        updateQuestionBank(form.value).then(() => {
          proxy.$modal.msgSuccess('修改成功')
          open.value = false
          getList()
        })
      } else {
        addQuestionBank(form.value).then(() => {
          proxy.$modal.msgSuccess('新增成功')
          open.value = false
          getList()
        })
      }
    }
  })
}

function handleDelete(row: any) {
  const _ids = row.bankId || ids.value
  proxy.$modal.confirm('是否确认删除题库编号为"' + _ids + '"的数据项？').then(() => {
    return delQuestionBank(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess('删除成功')
  }).catch(() => {})
}

function handleExport() {
  proxy.download('questionBank/questionBank/export', {
    ...queryParams.value
  }, `questionBank_${new Date().getTime()}.xlsx`)
}

getList()
</script>
