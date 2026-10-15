<template>
  <div class="app-container">
    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="80px">
      <el-form-item label="模型名称" prop="modelName">
        <el-input
          v-model="queryParams.modelName"
          placeholder="请输入模型名称"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="供应商" prop="provider">
        <el-input
          v-model="queryParams.provider"
          placeholder="请输入供应商"
          clearable
          style="width: 200px"
          @keyup.enter="handleQuery"
        />
      </el-form-item>
      <el-form-item label="状态" prop="status">
        <el-select v-model="queryParams.status" placeholder="配置状态" clearable style="width: 120px">
          <el-option v-for="dict in sys_normal_disable" :key="dict.value" :label="dict.label" :value="dict.value" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>
        <el-button icon="Refresh" @click="resetQuery">重置</el-button>
      </el-form-item>
    </el-form>

    <el-row :gutter="10" class="mb8">
      <el-col :span="1.5">
        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="['system:aiConfig:add']">新增</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="success" plain icon="Edit" :disabled="single" @click="handleUpdate" v-hasPermi="['system:aiConfig:edit']">修改</el-button>
      </el-col>
      <el-col :span="1.5">
        <el-button type="danger" plain icon="Delete" :disabled="multiple" @click="handleDelete" v-hasPermi="['system:aiConfig:remove']">删除</el-button>
      </el-col>
      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList" />
    </el-row>

    <el-table v-loading="loading" :data="aiConfigList" @selection-change="handleSelectionChange" row-key="modelId">
      <el-table-column type="selection" width="55" align="center" />
      <el-table-column label="配置ID" align="center" prop="modelId" width="80" />
      <el-table-column label="模型名称" align="center" prop="modelName" min-width="140" />
      <el-table-column label="供应商" align="center" prop="provider" width="120" />
      <el-table-column label="API地址" align="center" prop="apiUrl" show-overflow-tooltip min-width="180" />
      <el-table-column label="API密钥" align="center" prop="apiKey" width="140">
        <template #default="scope">
          <span>{{ maskApiKey(scope.row.apiKey) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="是否默认" align="center" prop="isDefault" width="90">
        <template #default="scope">
          <el-tag :type="scope.row.isDefault ? 'danger' : 'info'" effect="plain">
            {{ scope.row.isDefault ? '默认' : '' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" align="center" prop="status" width="80">
        <template #default="scope">
          <dict-tag :options="sys_normal_disable" :value="scope.row.status" />
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center" class-name="small-padding fixed-width" width="240">
        <template #default="scope">
          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="['system:aiConfig:edit']">修改</el-button>
          <el-button
            v-if="!scope.row.isDefault"
            link type="warning" icon="Star"
            @click="handleSetDefault(scope.row)"
            v-hasPermi="['system:aiConfig:edit']"
          >设为默认</el-button>
          <el-button link type="success" icon="Connection" @click="handleTestConnection(scope.row)" v-hasPermi="['system:aiConfig:edit']">测试</el-button>
          <el-button link type="danger" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="['system:aiConfig:remove']">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog :title="title" v-model="open" width="600px" append-to-body>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="模型名称" prop="modelName">
          <el-input v-model="form.modelName" placeholder="例如：gpt-4o、deepseek-chat" />
        </el-form-item>
        <el-form-item label="供应商" prop="provider">
          <el-select v-model="form.provider" placeholder="请选择供应商" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="文心一言" value="wenxin" />
            <el-option label="通义千问" value="qwen" />
            <el-option label="Claude" value="claude" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="API地址" prop="apiUrl">
          <el-input v-model="form.apiUrl" placeholder="例如：https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API密钥" prop="apiKey">
          <el-input v-model="form.apiKey" placeholder="请输入API密钥" type="password" show-password />
        </el-form-item>
        <el-form-item label="系统默认" prop="isDefault">
          <el-switch v-model="form.isDefault" :active-value="1" :inactive-value="0"
            :disabled="form.isDefault === 1 && form.modelId != null" />
          <span class="form-tip-text">{{ form.isDefault === 1 && form.modelId != null ? '当前即系统默认模型，将其它模型设为默认后自动替换' : '开启后该模型将作为全站默认模型，原默认模型自动取消' }}</span>
        </el-form-item>
        <el-form-item label="状态" prop="status">
          <el-radio-group v-model="form.status">
            <el-radio value="0">正常</el-radio>
            <el-radio value="1">停用</el-radio>
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
defineOptions({ name: 'AiConfig' })

import {
  listAiConfig,
  getAiConfig,
  addAiConfig,
  updateAiConfig,
  deleteAiConfig,
  setDefaultConfig,
  testAiConnection
} from '@/api/system/aiConfig'

const { proxy } = getCurrentInstance()
const { sys_normal_disable } = proxy.useDict('sys_normal_disable')

const aiConfigList = ref<any[]>([])
const open = ref(false)
const loading = ref(true)
const showSearch = ref(true)
const ids = ref<number[]>([])
const single = ref(true)
const multiple = ref(true)
const title = ref('')

const data = reactive({
  form: {} as any,
  queryParams: {
    modelName: null,
    provider: null,
    status: null
  },
  rules: {
    modelName: [
      { required: true, message: '模型名称不能为空', trigger: 'blur' }
    ],
    provider: [
      { required: true, message: '供应商不能为空', trigger: 'change' }
    ]
  }
})

const { queryParams, form, rules } = toRefs(data)

function maskApiKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '****'
  return key.substring(0, 4) + '****' + key.substring(key.length - 4)
}

function getList() {
  loading.value = true
  listAiConfig().then((response: any) => {
    let list = response.data || response.rows || []
    if (queryParams.value.modelName) {
      list = list.filter((item: any) => item.modelName?.includes(queryParams.value.modelName))
    }
    if (queryParams.value.provider) {
      list = list.filter((item: any) => item.provider?.includes(queryParams.value.provider))
    }
    if (queryParams.value.status) {
      list = list.filter((item: any) => item.status === queryParams.value.status)
    }
    aiConfigList.value = list
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
    modelId: null,
    modelName: null,
    provider: null,
    apiUrl: null,
    apiKey: null,
    isDefault: 0,
    status: '0'
  }
  proxy.resetForm('formRef')
}

function handleQuery() {
  getList()
}

function resetQuery() {
  proxy.resetForm('queryRef')
  handleQuery()
}

function handleSelectionChange(selection: any[]) {
  ids.value = selection.map((item: any) => item.modelId)
  single.value = selection.length !== 1
  multiple.value = selection.length === 0
}

function handleAdd() {
  reset()
  open.value = true
  title.value = '新增AI模型配置'
}

function handleUpdate(row: any) {
  reset()
  const modelId = row.modelId || ids.value[0]
  getAiConfig(modelId).then((response: any) => {
    form.value = response.data
    open.value = true
    title.value = '修改AI模型配置'
  })
}

function submitForm() {
  proxy.$refs['formRef'].validate((valid: boolean) => {
    if (valid) {
      if (form.value.modelId != null) {
        updateAiConfig(form.value).then((response: any) => {
          if (response.code !== 200) {
            proxy.$modal.msgError(response.msg || '修改失败')
            return
          }
          proxy.$modal.msgSuccess('修改成功')
          open.value = false
          getList()
        })
      } else {
        addAiConfig(form.value).then((response: any) => {
          if (response.code !== 200) {
            proxy.$modal.msgError(response.msg || '新增失败')
            return
          }
          proxy.$modal.msgSuccess('新增成功')
          open.value = false
          getList()
        })
      }
    }
  })
}

function handleDelete(row: any) {
  const _ids = row.modelId || ids.value
  proxy.$modal.confirm('是否确认删除AI配置编号为"' + _ids + '"的数据项？').then(() => {
    return deleteAiConfig(_ids)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess('删除成功')
  }).catch(() => {})
}

function handleSetDefault(row: any) {
  proxy.$modal.confirm('确认将"' + row.modelName + '"设为默认模型？').then(() => {
    return setDefaultConfig(row.modelId)
  }).then(() => {
    getList()
    proxy.$modal.msgSuccess('设置成功')
  }).catch(() => {})
}

function handleTestConnection(row: any) {
  proxy.$modal.loading('正在测试连接...')
  testAiConnection({ modelId: row.modelId, apiUrl: row.apiUrl, apiKey: row.apiKey })
    .then((response: any) => {
      proxy.$modal.closeLoading()
      if (response.code === 200) {
        proxy.$modal.msgSuccess('连接成功！' + (response.data || ''))
      } else {
        proxy.$modal.msgError('连接失败：' + (response.msg || '未知错误'))
      }
    })
    .catch(() => {
      proxy.$modal.closeLoading()
      proxy.$modal.msgError('连接测试失败，请检查网络或配置')
    })
}

getList()
</script>

<style scoped>
.form-tip-text {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}
</style>
