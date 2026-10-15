<template>
  <div class="app-container">
    <!-- 搜索表单 -->
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="68px">
      <el-form-item label="参数名称" prop="configName">
        <el-input
          v-model="queryParams.configName"
          placeholder="请输入参数名称"
          clearable
          style="width: 240px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="参数键名" prop="configKey">
        <el-input
          v-model="queryParams.configKey"
          placeholder="请输入参数键名"
          clearable
          style="width: 240px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="系统内置" prop="configType">
        <el-select v-model="queryParams.configType" placeholder="系统内置" clearable style="width: 240px">
          <el-option label="是" value="Y" />
          <el-option label="否" value="N" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <!-- 操作按钮区 -->
    <el-row :gutter="10" class="mb8">
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <!-- 数据表格 -->
    <el-table
      :data="configList"
      v-loading="loading"
      stripe
    >
      <el-table-column label="参数主键" align="center" prop="configId" width="80" />
      <el-table-column label="参数名称" align="center" prop="configName" :show-overflow-tooltip="true" width="200" />
      <el-table-column label="参数键名" align="center" prop="configKey" :show-overflow-tooltip="true" width="300" />
      <el-table-column label="参数键值" align="center" prop="configValue" width="150">
        <template #default="scope">
          <!-- 验证码开关用 Switch 展示 -->
          <template v-if="scope.row.configKey === 'sys.account.captchaEnabled'">
            <el-switch
              v-model="scope.row.configValue"
              active-value="true"
              inactive-value="false"
              active-text="开启"
              inactive-text="关闭"
              @change="handleCaptchaSwitch(scope.row)"
            />
          </template>
          <template v-else>
            <span>{{ scope.row.configValue }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="系统内置" align="center" prop="configType" width="100">
        <template #default="scope">
          <dict-tag :options="sys_yes_no" :value="scope.row.configType" />
        </template>
      </el-table-column>
      <el-table-column label="备注" align="center" prop="remark" :show-overflow-tooltip="true" />
      <el-table-column label="创建时间" align="center" prop="createTime" width="180" />
      <el-table-column label="操作" align="center" width="200" class-name="small-padding fixed-width">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)">修改</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <pagination
      v-show="total > 0"
      :total="total"
      v-model:page="queryParams.pageNum"
      v-model:limit="queryParams.pageSize"
      @pagination="getList"
    />

    <!-- 添加或修改参数配置对话框 -->
    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="configRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="参数名称" prop="configName">
          <el-input v-model="form.configName" placeholder="请输入参数名称" />
        </el-form-item>
        <el-form-item label="参数键名" prop="configKey">
          <el-input v-model="form.configKey" placeholder="请输入参数键名" />
        </el-form-item>
        <el-form-item label="参数键值" prop="configValue">
          <el-input v-model="form.configValue" placeholder="请输入参数键值" />
        </el-form-item>
        <el-form-item label="系统内置" prop="configType">
          <el-radio-group v-model="form.configType">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注" prop="remark">
          <el-input v-model="form.remark" type="textarea" placeholder="请输入内容" />
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
defineOptions({ name: 'Config' })
import { listConfig, getConfig, updateConfig } from '@/api/system/config'
import { ElMessageBox } from 'element-plus'

const configList = ref([])
const { proxy } = getCurrentInstance()
const { sys_yes_no } = proxy?.useDict('sys_yes_no')
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const total = ref(0)
const title = ref('')

const data = reactive({
  form: {},
  queryParams: {
    pageNum: 1,
    pageSize: 10,
    configName: undefined,
    configKey: undefined,
    configType: undefined,
  },
  rules: {
    configName: [{ required: true, message: '参数名称不能为空', trigger: 'blur' }],
    configKey: [{ required: true, message: '参数键名不能为空', trigger: 'blur' }],
    configValue: [{ required: true, message: '参数键值不能为空', trigger: 'blur' }],
  },
})

const { queryParams, form, rules } = toRefs(data)

function getList() {
  loading.value = true
  listConfig(queryParams.value).then(res => {
    configList.value = res.rows
    total.value = res.total || 0
    loading.value = false
  }).catch(() => {
    loading.value = false
  })
}

function handleQuery() {
  queryParams.value.pageNum = 1
  getList()
}

function resetQuery() {
  proxy.$refs.queryRef?.resetFields()
  handleQuery()
}

function handleAdd() {
  reset()
  open.value = true
  title.value = '添加参数'
}

function handleUpdate(row) {
  reset()
  getConfig(row.configId).then(res => {
    form.value = res.data
    open.value = true
    title.value = '修改参数'
  })
}

/** 验证码开关切换 - 直接保存 */
function handleCaptchaSwitch(row) {
  ElMessageBox.confirm(
    `确认${row.configValue === 'true' ? '开启' : '关闭'}验证码功能？`,
    '提示',
    { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
  ).then(() => {
    updateConfig({
      configId: row.configId,
      configName: row.configName,
      configValue: row.configValue,
    }).then(() => {
      proxy.$modal.msgSuccess(`${row.configValue === 'true' ? '开启' : '关闭'}成功`)
      getList()
    }).catch(() => {
      // 回退状态
      row.configValue = row.configValue === 'true' ? 'false' : 'true'
    })
  }).catch(() => {
    // 取消 - 回退状态
    row.configValue = row.configValue === 'true' ? 'false' : 'true'
  })
}

function submitForm() {
  proxy.$refs.configRef?.validate(valid => {
    if (valid) {
      if (form.value.configId) {
        updateConfig(form.value).then(() => {
          proxy.$modal.msgSuccess('修改成功')
          open.value = false
          getList()
        })
      }
    }
  })
}

function reset() {
  form.value = {
    configId: undefined,
    configName: undefined,
    configKey: undefined,
    configValue: undefined,
    configType: 'Y',
    remark: undefined,
  }
  proxy.$refs.configRef?.resetFields()
}

function cancel() {
  open.value = false
  reset()
}

getList()
</script>
