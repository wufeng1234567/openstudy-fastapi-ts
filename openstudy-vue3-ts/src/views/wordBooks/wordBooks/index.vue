<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="单词本名称" prop="name">
        <el-input
          v-model="queryParams.name"
          placeholder="请输入单词本名称"
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
          v-hasPermi="['wordBooks:wordBooks:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['wordBooks:wordBooks:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['wordBooks:wordBooks:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['wordBooks:wordBooks:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="wordBooksList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="主键ID" align="center" prop="id" />
      <el-table-column label="单词本名称" align="center" prop="name" />
      <el-table-column label="单词本描述" align="center" prop="description" />
      <el-table-column label="创建时间" align="center" prop="createdTime" width="180">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createdTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" align="center" prop="updatedTime" width="180">
        <template #default="scope">
          <span>{{ parseTime(scope.row.updatedTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否为默认单词本" align="center" prop="isDefault" />
      <el-table-column label="逻辑删除标识: 0-未删除, 1-已删除" align="center" prop="isDeleted" />
      <el-table-column label="删除时间" align="center" prop="deletedTime" width="180">
        <template #default="scope">
          <span>{{ parseTime(scope.row.deletedTime, '{y}-{m}-{d}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['wordBooks:wordBooks:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['wordBooks:wordBooks:remove']">删除</el-button>
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

    <!-- 添加或修改单词本对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="wordBooksRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="单词本名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入单词本名称" />
        </el-form-item>
        <el-form-item label="单词本描述" prop="description">
          <el-input v-model="form.description" type="textarea" placeholder="请输入内容" />
        </el-form-item>
        <el-form-item label="创建时间" prop="createdTime">
          <el-date-picker clearable
            v-model="form.createdTime"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择创建时间">
          </el-date-picker>
        </el-form-item>
        <el-form-item label="更新时间" prop="updatedTime">
          <el-date-picker clearable
            v-model="form.updatedTime"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择更新时间">
          </el-date-picker>
        </el-form-item>
        <el-form-item label="是否为默认单词本" prop="isDefault">
          <el-input v-model="form.isDefault" placeholder="请输入是否为默认单词本" />
        </el-form-item>
        <el-form-item label="逻辑删除标识: 0-未删除, 1-已删除" prop="isDeleted">
          <el-input v-model="form.isDeleted" placeholder="请输入逻辑删除标识: 0-未删除, 1-已删除" />
        </el-form-item>
        <el-form-item label="删除时间" prop="deletedTime">
          <el-date-picker clearable
            v-model="form.deletedTime"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="请选择删除时间">
          </el-date-picker>
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
defineOptions({ name: 'WordBooks' })
import { listWordBooks, getWordBooks, delWordBooks, addWordBooks, updateWordBooks } from "@/api/wordBooks/wordBooks"

const { proxy } = getCurrentInstance()

const wordBooksList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    name: null,
    description: null,
  },
  rules: {
    name: [
      { required: true, message: "单词本名称不能为空", trigger: "blur" }
    ],
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询单词本列表 */
function getList() {
  loading.value = true
  listWordBooks(queryParams.value).then(response => {
    wordBooksList.value = response.rows
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
    id: null,
    name: null,
    description: null,
    createdTime: null,
    updatedTime: null,
    isDefault: null,
    isDeleted: null,
    deletedTime: null
  }
  proxy.resetForm("wordBooksRef")
}

/** 搜索按钮操作 */
function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

/** 重置按钮操作 */
function resetQuery() {
  proxy.resetForm("queryRef")
  handleQuery()
}

// 多选框选中数据
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.id)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加单词本"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _id = row.id || ids.value
  getWordBooks(_id).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改单词本"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["wordBooksRef"].validate(valid => {
    if (valid) {
      if (form.value.id != null) {
        updateWordBooks(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addWordBooks(form.value).then(response => {
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
  const _ids = row.id || ids.value
  proxy.$modal.confirm('是否确认删除单词本编号为"' + _ids + '"的数据项？').then(function() {
    return delWordBooks(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('wordBooks/wordBooks/export', {
    ...queryParams.value
  }, `wordBooks_${new Date().getTime()}.xlsx`)
}

getList()
</script>
