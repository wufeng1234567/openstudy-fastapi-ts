<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="90px">
      <el-form-item label="笔记ID" prop="noteId">
        <el-input
          v-model="queryParams.noteId"
          placeholder="请输入笔记ID"
          clearable
          style="width: 140px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="用户名称" prop="userName">
        <el-input
          v-model="queryParams.userName"
          placeholder="请输入用户名称"
          clearable
          style="width: 140px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="评论内容" prop="content">
        <el-input
          v-model="queryParams.content"
          placeholder="请输入评论内容"
          clearable
          style="width: 180px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="评论状态" clearable style="width: 120px">
          <el-option label="正常" value="0" />
          <el-option label="隐藏" value="1" />
        </el-select>
      </el-form-item>
      <el-form-item label="评论时间" prop="createTime">
        <el-date-picker
          v-model="dateRange"
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
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['system:comment:remove']"
        >删除</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table
      v-loading="loading"
      :data="commentList"
      @selection-change="handleSelectionChange"
      row-key="commentId"
    >
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="评论ID" align="center" prop="commentId" width="80" />
      <el-table-column label="笔记标题" align="center" prop="noteTitle" show-overflow-tooltip min-width="140" />
      <el-table-column label="用户名称" align="center" prop="userName" width="120" />
      <el-table-column label="评论内容" align="center" prop="content" show-overflow-tooltip min-width="220" />
      <el-table-column label="状态" align="center" prop="status" width="80">
        <template #default="scope">
          <el-tag :type="scope.row.status === '0' ? 'success' : 'warning'" disable-transitions>
            {{ scope.row.status === '0' ? '正常' : '隐藏' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="评论时间" align="center" prop="createTime" width="170">
        <template #default="scope">
          <span>{{ parseTime(scope.row.createTime, '{y}-{m}-{d} {h}:{i}:{s}') }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="180">
        <template #default="scope">
          <el-button link type="primary" icon="View" @click="handleView(scope.row)">查看</el-button>
          <el-button
            v-if="scope.row.status === '0'"
            link type="warning" icon="Hide"
            @click="handleToggleStatus(scope.row, '1')"
            v-hasPermi="['system:comment:edit']"
          >隐藏</el-button>
          <el-button
            v-if="scope.row.status === '1'"
            link type="success" icon="View"
            @click="handleToggleStatus(scope.row, '0')"
            v-hasPermi="['system:comment:edit']"
          >显示</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['system:comment:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <el-dialog :title="title" v-model="open" width="700px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="评论ID" prop="commentId">
              <el-input v-model="form.commentId" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="笔记标题" prop="noteTitle">
              <el-input v-model="form.noteTitle" disabled />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="用户名称" prop="userName">
              <el-input v-model="form.userName" disabled />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="回复对象" prop="replyUserName">
              <el-input v-model="form.replyUserName" disabled placeholder="无（非回复）" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="评论内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="4" disabled />
        </el-form-item>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-select v-model="form.status" placeholder="评论状态" style="width: 100%">
                <el-option label="正常" value="0" />
                <el-option label="隐藏" value="1" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="评论时间" prop="createTime">
              <el-input v-model="form.createTime" disabled />
            </el-form-item>
          </el-col>
        </el-row>
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
defineOptions({ name: 'Comment' })

import { listComment, getComment, updateComment, delComment } from '@/api/system/comment'
import { parseTime } from '@/utils/ruoyi'

const { proxy } = getCurrentInstance()

const commentList = ref<any[]>([])
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
    noteId: null,
    userName: null,
    content: null,
    status: null,
    params: {} as any
  },
  rules: {}
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  queryParams.value.params = {}
  if (dateRange.value && dateRange.value.length > 0) {
    queryParams.value.params.beginTime = dateRange.value[0]
    queryParams.value.params.endTime = dateRange.value[1]
  }
  listComment(queryParams.value).then((response: any) => {
    commentList.value = response.rows
    total.value = response.total
    loading.value = false
  })
}

function cancel() {
  open.value = false
  reset()
}

function reset() {
  form.value = {
    commentId: null,
    noteId: null,
    noteTitle: null,
    userId: null,
    userName: null,
    content: null,
    replyUserName: null,
    status: '0',
    createTime: null
  }
  proxy.resetForm('formRef')
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  dateRange.value = []
  proxy.resetForm('queryRef')
  queryParams.value.params = {}
  handleQuery()
}

function handleSelectionChange(selection: any[]) {
  ids.value = selection.map((item: any) => item.commentId)
  single.value = selection.length !== 1
  multiple.value = selection.length === 0
}

function handleView(row: any) {
  reset()
  const commentId = row.commentId
  getComment(commentId).then((response: any) => {
    form.value = response.data
    open.value = true
    title.value = '查看评论'
  })
}

function handleToggleStatus(row: any, status: string) {
  const statusText = status === '0' ? '显示' : '隐藏'
  proxy.$modal.confirm('确认' + statusText + '该评论？').then(() => {
    return updateComment({ commentId: row.commentId, status: status })
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess(statusText + '成功')
  }).catch(() => {})
}

function submitForm() {
  proxy.$refs['formRef'].validate((valid: boolean) => {
    if (valid) {
      updateComment(form.value).then((response: any) => {
        proxy.$modal.msgSuccess('修改成功')
        open.value = false
        getList()
      })
    }
  })
}

function handleDelete(row: any) {
  const _ids = row.commentId || ids.value
  proxy.$modal.confirm('是否确认删除评论编号为"' + _ids + '"的数据项？').then(() => {
    return delComment(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess('删除成功')
  }).catch(() => {})
}

getList()
</script>
