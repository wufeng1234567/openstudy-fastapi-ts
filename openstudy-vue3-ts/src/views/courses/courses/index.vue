<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="课程代码" prop="courseCode">
        <el-input
          v-model="queryParams.courseCode"
          placeholder="请输入课程代码"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="课程名称" prop="courseName">
        <el-input
          v-model="queryParams.courseName"
          placeholder="请输入课程名称"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="学分" prop="credits">
        <el-input
          v-model="queryParams.credits"
          placeholder="请输入学分"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="所属院系" prop="department">
        <el-input
          v-model="queryParams.department"
          placeholder="请输入所属院系"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="授课教师" prop="instructor">
        <el-input
          v-model="queryParams.instructor"
          placeholder="请输入授课教师"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="学期" prop="semester">
        <el-input
          v-model="queryParams.semester"
          placeholder="请输入学期"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="年份" prop="year">
        <el-input
          v-model="queryParams.year"
          placeholder="请输入年份"
          clearable
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="最大学生数" prop="maxStudents">
        <el-input
          v-model="queryParams.maxStudents"
          placeholder="请输入最大学生数"
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
          v-hasPermi="['courses:courses:add']"
        >新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="success"
          plain
          icon="Edit"
          :disabled="single"
          @click="handleUpdate"
          v-hasPermi="['courses:courses:edit']"
        >修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="danger"
          plain
          icon="Delete"
          :disabled="multiple"
          @click="handleDelete"
          v-hasPermi="['courses:courses:remove']"
        >删除</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button
          type="warning"
          plain
          icon="Download"
          @click="handleExport"
          v-hasPermi="['courses:courses:export']"
        >导出</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <el-table v-loading="loading" :data="coursesList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="id" align="center" prop="courseId" />
      <el-table-column label="课程代码" align="center" prop="courseCode" />
      <el-table-column label="课程名称" align="center" prop="courseName" />
      <el-table-column label="课程描述" align="center" prop="description" />
      <el-table-column label="学分" align="center" prop="credits" />
      <el-table-column label="所属院系" align="center" prop="department" />
      <el-table-column label="授课教师" align="center" prop="instructor" />
      <el-table-column label="学期" align="center" prop="semester" />
      <el-table-column label="年份" align="center" prop="year" />
      <el-table-column label="最大学生数" align="center" prop="maxStudents" />
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['courses:courses:edit']">修改</el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['courses:courses:remove']">删除</el-button>
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

    <!-- 添加或修改课程信息对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="coursesRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="课程代码" prop="courseCode">
          <el-input v-model="form.courseCode" placeholder="请输入课程代码" />
        </el-form-item>
        <el-form-item label="课程名称" prop="courseName">
          <el-input v-model="form.courseName" placeholder="请输入课程名称" />
        </el-form-item>
        <el-form-item label="课程描述" prop="description">
          <el-input v-model="form.description" type="textarea" placeholder="请输入内容" />
        </el-form-item>
        <el-form-item label="学分" prop="credits">
          <el-input v-model="form.credits" placeholder="请输入学分" />
        </el-form-item>
        <el-form-item label="所属院系" prop="department">
          <el-input v-model="form.department" placeholder="请输入所属院系" />
        </el-form-item>
        <el-form-item label="授课教师" prop="instructor">
          <el-input v-model="form.instructor" placeholder="请输入授课教师" />
        </el-form-item>
        <el-form-item label="学期" prop="semester">
          <el-input v-model="form.semester" placeholder="请输入学期" />
        </el-form-item>
        <el-form-item label="年份" prop="year">
          <el-input v-model="form.year" placeholder="请输入年份" />
        </el-form-item>
        <el-form-item label="最大学生数" prop="maxStudents">
          <el-input v-model="form.maxStudents" placeholder="请输入最大学生数" />
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
defineOptions({ name: 'Courses' })
import { listCourses, getCourses, delCourses, addCourses, updateCourses } from "@/api/courses/courses"

const { proxy } = getCurrentInstance()

const coursesList = ref([])
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
    courseCode: null,
    courseName: null,
    description: null,
    credits: null,
    department: null,
    instructor: null,
    semester: null,
    year: null,
    maxStudents: null,
  },
  rules: {
    courseCode: [
      { required: true, message: "课程代码不能为空", trigger: "blur" }
    ],
    courseName: [
      { required: true, message: "课程名称不能为空", trigger: "blur" }
    ],
    credits: [
      { required: true, message: "学分不能为空", trigger: "blur" }
    ],
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 查询课程信息列表 */
function getList() {
  loading.value = true
  listCourses(queryParams.value).then(response => {
    coursesList.value = response.rows
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
    courseId: null,
    courseCode: null,
    courseName: null,
    description: null,
    credits: null,
    department: null,
    instructor: null,
    semester: null,
    year: null,
    maxStudents: null,
    createdAt: null
  }
  proxy.resetForm("coursesRef")
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
  ids.value = selection.map(item => item.courseId)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加课程信息"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _courseId = row.courseId || ids.value
  getCourses(_courseId).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改课程信息"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["coursesRef"].validate(valid => {
    if (valid) {
      if (form.value.courseId != null) {
        updateCourses(form.value).then(response => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addCourses(form.value).then(response => {
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
  const _courseIds = row.courseId || ids.value
  proxy.$modal.confirm('是否确认删除课程信息编号为"' + _courseIds + '"的数据项？').then(function() {
    return delCourses(_courseIds)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => {})
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('courses/courses/export', {
    ...queryParams.value
  }, `courses_${new Date().getTime()}.xlsx`)
}

getList()
</script>
