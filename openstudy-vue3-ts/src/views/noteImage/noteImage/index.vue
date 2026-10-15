<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="所属笔记ID" prop="noteId">
        <el-input
          v-model="queryParams.noteId"
          placeholder="请输入所属笔记ID"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="原始文件名" prop="fileName">
        <el-input
          v-model="queryParams.fileName"
          placeholder="请输入原始文件名"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="文件大小" prop="fileSize">
        <el-input
          v-model="queryParams.fileSize"
          placeholder="请输入文件大小"
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
          v-hasPermi="['noteImage:noteImage:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['noteImage:noteImage:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['noteImage:noteImage:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['noteImage:noteImage:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="noteImageList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="图片ID" align="center" prop="id" />
      <el-table-column label="所属笔记ID" align="center" prop="noteId" />
      <el-table-column label="原始文件名" align="center" prop="fileName" />
      <el-table-column label="相对存储路径，如 /upload/notes/img/2025/12/xxx.png" align="center" prop="filePath" />
      <el-table-column label="文件大小" align="center" prop="fileSize" />
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['noteImage:noteImage:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['noteImage:noteImage:remove']">删除</el-button>
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

    <!-- 添加或修改笔记关联的图片资源对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="noteImageRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="所属笔记ID" prop="noteId">
          <el-input v-model="form.noteId" placeholder="请输入所属笔记ID" />
        </el-form-item>
        <el-form-item label="原始文件名" prop="fileName">
          <el-input v-model="form.fileName" placeholder="请输入原始文件名" />
        </el-form-item>
        <el-form-item label="相对存储路径，如 /upload/notes/img/2025/12/xxx.png" prop="filePath">
          <el-input v-model="form.filePath" type="textarea" placeholder="请输入内容" />
        </el-form-item>
        <el-form-item label="文件大小" prop="fileSize">
          <el-input v-model="form.fileSize" placeholder="请输入文件大小" />
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
defineOptions({ name: 'NoteImage' })
import { listNoteImage, getNoteImage, delNoteImage, addNoteImage, updateNoteImage } from "@/api/noteImage/noteImage"

const { proxy } = getCurrentInstance()

const noteImageList = ref([])
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
    noteId: null,
    fileName: null,
    fileSize: null,
  },
  rules: {
    noteId: [
      { required: true, message: "所属笔记ID不能为空", trigger: "blur" }
    ],
    fileName: [
      { required: true, message: "原始文件名不能为空", trigger: "blur" }
    ],
    filePath: [
      { required: true, message: "相对存储路径，如 /upload/notes/img/2025/12/xxx.png不能为空", trigger: "blur" }
    ],
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询笔记关联的图片资源列表 */
function getList() {
  loading.value = true
  listNoteImage(queryParams.value).then(response => {
    noteImageList.value = response.rows
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
    noteId: null,
    fileName: null,
    filePath: null,
    fileSize: null,
    createTime: null
  }
  proxy.resetForm("noteImageRef")
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
  title.value = "添加笔记关联的图片资源"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _id = row.id || ids.value
  getNoteImage(_id).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改笔记关联的图片资源"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["noteImageRef"].validate(valid => {
    if (valid) {
      if (form.value.id != null) {
        updateNoteImage(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addNoteImage(form.value).then(response => {
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
  proxy.$modal.confirm('是否确认删除笔记关联的图片资源编号为"' + _ids + '"的数据项？').then(function() {
    return delNoteImage(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('noteImage/noteImage/export', {
    ...queryParams.value
  }, `noteImage_${new Date().getTime()}.xlsx`)
}

getList()
</script>
