<template>
  <div class="app-container">
    <!-- 搜索区域 -->
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="80px">
      <el-form-item label="敏感词" prop="word">
        <el-input v-model="queryParams.word" placeholder="请输入敏感词" clearable @keyup.enter="handleQuery" />
      </el-form-item>
      <el-form-item label="分类" prop="category">
        <el-select v-model="queryParams.category" placeholder="请选择分类" clearable style="width: 200px">
          <el-option label="涉政" value="涉政" />
          <el-option label="色情" value="色情" />
          <el-option label="暴恐" value="暴恐" />
          <el-option label="辱骂" value="辱骂" />
          <el-option label="广告" value="广告" />
          <el-option label="其他" value="其他" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="请选择状态" clearable style="width: 120px">
          <el-option label="启用" :value="1" />
          <el-option label="禁用" :value="0" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 按钮区域 -->
    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['sensitiveWord:sensitiveWord:add']">
          新增
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success" plain icon="Edit" :disabled="single" @click="handleUpdate"
          v-hasPermi="['sensitiveWord:sensitiveWord:edit']">
          修改
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger" plain icon="Delete" :disabled="multiple" @click="handleDelete"
          v-hasPermi="['sensitiveWord:sensitiveWord:remove']">
          删除
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="info" plain icon="MagicStick" @click="handleAiGenerate"
          v-hasPermi="['sensitiveWord:sensitiveWord:add']">
          AI生成
        </el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="warning" plain icon="Download" @click="handleExport"
          v-hasPermi="['sensitiveWord:sensitiveWord:export']">
          导出
        </el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>
    </el-row>

    <!-- 表格区域 -->
    <el-table v-loading="loading" :data="sensitiveWordList" @selection-change="handleSelectionChange">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="ID" align="center" prop="id" width="80" />
      <el-table-column label="敏感词" align="center" prop="word" />
      <el-table-column label="分类" align="center" prop="category" width="100" />
      <el-table-column label="状态" align="center" prop="status" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.status === 1 ? 'success' : 'danger'">
            {{ scope.row.status === 1 ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="备注" align="center" prop="remark" show-overflow-tooltip />
      <el-table-column label="创建时间" align="center" prop="createTime" width="160" />
      <el-table-column label="操作" align="center" width="150" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)"
            v-hasPermi="['sensitiveWord:sensitiveWord:edit']">
            修改
          </el-button>
          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)"
            v-hasPermi="['sensitiveWord:sensitiveWord:remove']">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <pagination v-show="total > 0" :total="total" v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize" @pagination="getList" />

    <!-- 新增/修改对话框 -->
    <el-dialog :title="title" v-model="open" width="500px" append-to-body>
      <el-form ref="sensitiveWordRef" :model="form" :rules="rules" label-width="80px">
        <el-row>
          <el-col :span="24">
            <el-form-item label="敏感词" prop="word">
              <el-input v-model="form.word" placeholder="请输入敏感词" maxlength="50" show-word-limit />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="分类" prop="category">
              <el-select v-model="form.category" placeholder="请选择分类" clearable style="width: 100%">
                <el-option label="涉政" value="涉政" />
                <el-option label="色情" value="色情" />
                <el-option label="暴恐" value="暴恐" />
                <el-option label="辱骂" value="辱骂" />
                <el-option label="广告" value="广告" />
                <el-option label="其他" value="其他" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="状态" prop="status">
              <el-radio-group v-model="form.status">
                <el-radio :label="1">启用</el-radio>
                <el-radio :label="0">禁用</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="备注" prop="remark">
              <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注" maxlength="255"
                show-word-limit />
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

    <!-- AI生成敏感词对话框 -->
    <el-dialog :title="aiDialogTitle" v-model="aiDialogOpen" width="480px" append-to-body>
      <el-form ref="aiFormRef" :model="aiForm" :rules="aiRules" label-width="80px">
        <el-form-item label="主题" prop="topic">
          <el-input v-model="aiForm.topic" placeholder="如：涉政、色情、广告、辱骂" maxlength="30" />
          <div class="form-tip">输入主题词，AI会生成相关的敏感词变体</div>
        </el-form-item>
        <el-form-item label="分类" prop="category">
          <el-select v-model="aiForm.category" placeholder="请选择分类" clearable style="width: 100%">
            <el-option label="涉政" value="涉政" />
            <el-option label="色情" value="色情" />
            <el-option label="暴恐" value="暴恐" />
            <el-option label="辱骂" value="辱骂" />
            <el-option label="广告" value="广告" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>
        <el-form-item label="生成数量" prop="count">
          <el-slider v-model="aiForm.count" :min="5" :max="50" :step="5" show-stops show-input />
          <div class="form-tip">建议20-30个，过多可能质量下降</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="aiDialogOpen = false">取消</el-button>
        <el-button type="primary" @click="submitAiGenerate" :loading="aiGenerating">
          <el-icon v-if="!aiGenerating">
            <MagicStick />
          </el-icon>
          开始生成
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'SensitiveWord' })
import { ref, reactive, toRefs, getCurrentInstance, nextTick } from 'vue'
import { listSensitiveWord, getSensitiveWord, delSensitiveWord, addSensitiveWord, updateSensitiveWord, aiGenerateWords } from "@/api/sensitiveWord/sensitiveWord"
import { MagicStick } from '@element-plus/icons-vue'

const { proxy } = getCurrentInstance()

const sensitiveWordList = ref([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref([])
const single = ref(true)
const multiple = ref(true)
const total = ref(0)
const title = ref("")

// AI生成相关
const aiDialogOpen = ref(false)
const aiDialogTitle = ref("AI 生成敏感词")
const aiGenerating = ref(false)
const aiFormRef = ref(null)
const aiForm = reactive({
  topic: '',
  category: '',
  count: 20
})

const aiRules = {
  topic: [{ required: true, message: '请输入主题', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }]
}

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    word: undefined,
    category: undefined,
    status: undefined,
  },
  rules: {
    word: [
      { required: true, message: "敏感词不能为空", trigger: "blur" }
    ],
    category: [
      { required: true, message: "请选择分类", trigger: "change" }
    ],
    status: [
      { required: true, message: "请选择状态", trigger: "change" }
    ],
  }
})

const { queryParams, form, rules } = toRefs(data)

/** 打开AI生成对话框 */
function handleAiGenerate() {
  aiForm.topic = ''
  aiForm.category = ''
  aiForm.count = 20
  aiDialogOpen.value = true
  nextTick(() => {
    document.querySelector('.el-dialog input')?.focus()
  })
}

/** 提交AI生成 */
function submitAiGenerate() {
  aiFormRef.value?.validate(async (valid) => {
    if (!valid) return
    aiGenerating.value = true
    try {
      const res = await aiGenerateWords(aiForm)
      proxy.$modal.msgSuccess(res.msg || `成功生成敏感词`)
      aiDialogOpen.value = false
      getList()
    } catch (error) {
      proxy.$modal.msgError(error.message || '生成失败')
    } finally {
      aiGenerating.value = false
    }
  })
}

/** 查询敏感词管理列表 */
function getList() {
  loading.value = true
  listSensitiveWord(queryParams.value).then(response => {
    sensitiveWordList.value = response.rows
    total.value = response.total
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

/** 取消按钮 */
function cancel() {
  open.value = false
  reset()
}

/** 表单重置 */
function reset() {
  form.value = {
    id: null,
    word: null,
    category: null,
    status: 1,
    remark: null
  }
  proxy.resetForm("sensitiveWordRef")
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

/** 多选框选中数据 */
function handleSelectionChange(selection) {
  ids.value = selection.map(item => item.id)
  single.value = selection.length != 1
  multiple.value = !selection.length
}

/** 新增按钮操作 */
function handleAdd() {
  reset()
  open.value = true
  title.value = "添加敏感词"
}

/** 修改按钮操作 */
function handleUpdate(row) {
  reset()
  const _id = row.id || ids.value[0]
  getSensitiveWord(_id).then(response => {
    form.value = response.data
    open.value = true
    title.value = "修改敏感词"
  })
}

/** 提交按钮 */
function submitForm() {
  proxy.$refs["sensitiveWordRef"].validate(valid => {
    if (valid) {
      if (form.value.id != null) {
        updateSensitiveWord(form.value).then(() => {
          proxy.$modal.msgSuccess("修改成功")
          open.value = false
          getList()
        })
      } else {
        addSensitiveWord(form.value).then(() => {
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
  proxy.$modal.confirm('是否确认删除所选敏感词？').then(function () {
    return delSensitiveWord(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess("删除成功")
  }).catch(() => { })
}

/** 导出按钮操作 */
function handleExport() {
  proxy.download('sensitiveWord/sensitiveWord/export', {
    ...queryParams.value
  }, `sensitiveWord_${new Date().getTime()}.xlsx`)
}

getList()
</script>

<style scoped>
.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>