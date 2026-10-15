<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">
      <el-form-item label="所属用户ID" prop="userId">
        <el-input
          v-model="queryParams.userId"
          placeholder="请输入所属用户ID"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="分类名称" prop="name">
        <el-input
          v-model="queryParams.name"
          placeholder="请输入分类名称"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="排序序号" prop="orderNum">
        <el-input
          v-model="queryParams.orderNum"
          placeholder="请输入排序序号"
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
          v-hasPermi="['noteCategory:noteCategory:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['noteCategory:noteCategory:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['noteCategory:noteCategory:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['noteCategory:noteCategory:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="noteCategoryList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="分类ID，主键" align="center" prop="id" />
      <el-table-column label="所属用户ID，关联 sys_user.id" align="center" prop="userId" />
      <el-table-column label="分类名称，如“个人笔记”、“工作文档”，由用户自定义" align="center" prop="name" />
      <el-table-column label="排序序号，用于前端拖拽调整分类顺序" align="center" prop="orderNum" />
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['noteCategory:noteCategory:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['noteCategory:noteCategory:remove']">删除</el-button>
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

    <!-- 添加或修改笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="noteCategoryRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="所属用户ID，关联 sys_user.id" prop="userId">
          <el-input v-model="form.userId" placeholder="请输入所属用户ID，关联 sys_user.id" />
        </el-form-item>
        <el-form-item label="分类名称，如“个人笔记”、“工作文档”，由用户自定义" prop="name">
          <el-input v-model="form.name" placeholder="请输入分类名称，如“个人笔记”、“工作文档”，由用户自定义" />
        </el-form-item>
        <el-form-item label="排序序号，用于前端拖拽调整分类顺序" prop="orderNum">
          <el-input v-model="form.orderNum" placeholder="请输入排序序号，用于前端拖拽调整分类顺序" />
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
defineOptions({ name: 'NoteCategory' })
import { listNoteCategory, getNoteCategory, delNoteCategory, addNoteCategory, updateNoteCategory } from "@/api/noteCategory/noteCategory"

const { proxy } = getCurrentInstance()

const noteCategoryList = ref([])
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
    userId: null,
    name: null,
    orderNum: null,
  },
  rules: {
    userId: [
      { required: true, message: "所属用户ID，关联 sys_user.id不能为空", trigger: "blur" }
    ],
    name: [
      { required: true, message: "分类名称，如“个人笔记”、“工作文档”，由用户自定义不能为空", trigger: "blur" }
    ],
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记列表 */
function getList() {
  loading.value = true
  listNoteCategory(queryParams.value).then(response => {
    noteCategoryList.value = response.rows
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
    userId: null,
    name: null,
    orderNum: null,
    createTime: null
  }
  proxy.resetForm("noteCategoryRef")
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
  title.value = "添加笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _id = row.id || ids.value
  getNoteCategory(_id).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["noteCategoryRef"].validate(valid => {
    if (valid) {
      if (form.value.id != null) {
        updateNoteCategory(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addNoteCategory(form.value).then(response => {
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
  proxy.$modal.confirm('是否确认删除笔记分类，支持用户自定义单层分类，每个分类下可包含多篇笔记编号为"' + _ids + '"的数据项？').then(function() {
    return delNoteCategory(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('noteCategory/noteCategory/export', {
    ...queryParams.value
  }, `noteCategory_${new Date().getTime()}.xlsx`)
}

getList()
</script>
