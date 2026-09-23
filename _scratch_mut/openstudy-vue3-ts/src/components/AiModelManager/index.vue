<template>
  <div class="ai-model-manager">
    <div class="model-header">
      <div class="header-text">
        <h3>AI模型配置</h3>
        <p class="header-tip">这里只显示你自己添加的模型；系统提供的官方模型由管理员统一维护。</p>
      </div>
      <el-button class="btn-add" @click="handleAdd">
        <el-icon>
          <Plus />
        </el-icon>
        添加模型
      </el-button>
    </div>

    <el-empty v-if="!loading && configList.length === 0" description="暂无自定义模型配置" />

    <div v-else class="model-list">
      <el-table :data="configList" v-loading="loading" style="width: 100%">
        <el-table-column prop="providerName" label="服务商" width="120" />
        <el-table-column prop="model" label="模型" min-width="150">
          <template #default="{ row }">
            <span>{{ row.model }}</span>
            <el-tag v-if="row.isDefault === 1" type="success" size="small" style="margin-left: 8px">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="baseUrl" label="API地址" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.baseUrl || getDefaultBaseUrl(row.provider) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="apiKey" label="API Key" min-width="150">
          <template #default="{ row }">
            <span>{{ maskApiKey(row.apiKey) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="isEnabled" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.isEnabled === 1 ? 'success' : 'info'" size="small">
              {{ row.isEnabled === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button class="btn-action" @click="handleEdit(row)">编辑</el-button>
            <el-button class="btn-action btn-default" v-if="row.isDefault !== 1"
              @click="handleSetDefault(row)">设为默认</el-button>
            <el-button class="btn-action btn-danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="服务商" prop="provider">
          <el-select v-model="form.provider" placeholder="请选择服务商" style="width: 100%">
          <el-option-group label="官方 API">
            <el-option label="DeepSeek（官方 API）" value="deepseek" />
          </el-option-group>
            <el-option-group label="其它 / 自定义">
              <el-option label="智谱AI (GLM)" value="zhipuai" />
              <el-option label="硅基流动" value="siliconflow" />
              <el-option label="OpenAI" value="openai" />
            </el-option-group>
          </el-select>
        </el-form-item>

        <el-form-item label="模型名称" prop="model">
          <el-input v-model="form.model" placeholder="如：deepseek-flash、deepseek-v4-pro" />
          <div class="form-tip">
            DeepSeek 官方当前提供 deepseek-flash / deepseek-v4-pro
          </div>
        </el-form-item>

        <el-form-item label="API Key" prop="apiKey">
          <el-input v-model="form.apiKey" type="password" placeholder="请输入API Key" show-password />
        </el-form-item>

        <el-form-item label="API地址" prop="baseUrl">
          <el-input v-model="form.baseUrl" placeholder="留空使用默认地址" />
          <div class="form-tip" v-if="!form.baseUrl">
            默认地址：{{ defaultBaseUrl }}<br />
          </div>
          <div class="form-tip">
            留空使用下方默认地址<br />
            智谱默认：https://open.bigmodel.cn/api/paas/v4<br />
            DeepSeek默认：https://api.deepseek.com<br />
            硅基流动默认：https://api.siliconflow.cn/v1<br />
            OpenAI默认：https://api.openai.com/v1
          </div>
        </el-form-item>

        <template v-if="form.provider === 'deepseek'">
          <el-divider content-position="left">DeepSeek 高级配置</el-divider>

          <el-form-item label="思考模式">
            <el-select v-model="form.thinkingMode" placeholder="选择思考模式" style="width: 100%">
              <el-option label="自动（默认）" value="auto" />
              <el-option label="启用思考" value="enabled" />
              <el-option label="禁用思考" value="disabled" />
            </el-select>
            <div class="form-tip">启用后模型会输出思考过程（reasoning_content）</div>
          </el-form-item>

          <el-form-item label="推理强度" v-if="form.thinkingMode !== 'disabled'">
            <el-select v-model="form.reasoningEffort" placeholder="选择推理强度" style="width: 100%">
              <el-option label="低（low）" value="low" />
              <el-option label="中（medium）" value="medium" />
              <el-option label="高（high）" value="high" />
              <el-option label="最大（max）" value="max" />
            </el-select>
            <div class="form-tip">控制思考预算，复杂问题建议使用 high 或 max</div>
          </el-form-item>

          <el-form-item label="上下文长度">
            <el-select v-model="form.contextLength" placeholder="选择上下文长度" style="width: 100%">
              <el-option label="32K tokens" value="32k" />
              <el-option label="128K tokens" value="128k" />
              <el-option label="1M tokens（仅 Pro）" value="1m" />
            </el-select>
            <div class="form-tip">根据模型支持的上下文窗口选择</div>
          </el-form-item>
        </template>

        <template v-if="form.provider === 'siliconflow'">
          <el-divider content-position="left">硅基流动 高级配置</el-divider>

          <el-form-item label="思考模式">
            <el-select v-model="form.thinkingMode" placeholder="选择思考模式" style="width: 100%">
              <el-option label="启用思考" value="enabled" />
              <el-option label="禁用思考" value="disabled" />
            </el-select>
            <div class="form-tip">禁用思考模式可提升响应速度</div>
          </el-form-item>
        </template>

        <el-form-item label="设为默认">
          <el-switch v-model="form.isDefault" :active-value="1" :inactive-value="0" />
        </el-form-item>

        <el-form-item label="状态">
          <el-radio-group v-model="form.isEnabled">
            <el-radio :label="1">启用</el-radio>
            <el-radio :label="0">停用</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="可选备注信息" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button class="btn-cancel" @click="dialogVisible = false">取消</el-button>
        <el-button class="btn-action btn-test" @click="handleTestConnection" :loading="testing">
          测试连接
        </el-button>
        <el-button class="btn-primary" @click="handleSave" :loading="saving">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import {
  listAiConfig,
  addAiConfig,
  updateAiConfig,
  deleteAiConfig,
  setDefaultConfig,
  testAiConnection
} from '@/api/system/aiConfig'

const props = defineProps({
  userId: {
    type: Number,
    default: null
  }
})

const loading = ref(false)
const configList = ref([])
const dialogVisible = ref(false)
const dialogTitle = ref('')
const testing = ref(false)
const saving = ref(false)
const formRef = ref(null)
const isEdit = ref(false)

const form = reactive({
  configId: null,
  provider: 'zhipuai',
  providerName: '',
  model: '',
  apiKey: '',
  baseUrl: '',
  isDefault: 0,
  isEnabled: 1,
  remark: '',
  thinkingMode: 'auto',
  reasoningEffort: 'high',
  contextLength: '32k',
  // ds-free（官网 Web 反代）专用
  webPhone: '',
  webPassword: '',
  webAreaCode: '+86'
})

const rules = {
  provider: [{ required: true, message: '请选择服务商', trigger: 'change' }],
  model: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  apiKey: [
    {
      validator: (rule, value, callback) => {
        if (!value) return callback(new Error('请输入API Key'))
        callback()
      },
      trigger: 'blur'
    }
  ]
}

const providerNames = {
  zhipuai: '智谱AI',
  deepseek: 'DeepSeek',
  siliconflow: '硅基流动',
  openai: 'OpenAI'
}

const defaultBaseUrls = {
  zhipuai: 'https://open.bigmodel.cn/api/paas/v4',
  deepseek: 'https://api.deepseek.com',
  siliconflow: 'https://api.siliconflow.cn/v1',
  openai: 'https://api.openai.com/v1'
}

const defaultBaseUrl = computed(() => defaultBaseUrls[form.provider] || '')

watch(() => form.provider, (newProvider) => {
  form.providerName = providerNames[newProvider] || newProvider
  if (!isEdit.value) {
    form.thinkingMode = 'auto'
    form.reasoningEffort = 'high'
    form.contextLength = '32k'
  }
}, { immediate: true })

function maskApiKey(key) {
  if (!key) return ''
  if (key.length <= 8) return '****'
  return key.substring(0, 6) + '****' + key.substring(key.length - 4)
}

function getDefaultBaseUrl(provider) {
  return defaultBaseUrls[provider] || ''
}

async function fetchConfigList() {
  loading.value = true
  try {
    // scope='mine'：只列「我自己添加的模型」。
    // 系统提供的官方模型（user_id 为空）由管理员在「系统管理 → AI 模型配置」维护，
    // 不该出现在普通用户的个人中心里（否则人人可编辑/删除官方配置）。
    const res = await listAiConfig('mine')
    if (res.code === 200 && res.rows) {
      configList.value = res.rows
    }
  } catch (error) {
    console.error('获取模型配置失败:', error)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    configId: null,
    provider: 'zhipuai',
    providerName: '',
    model: '',
    apiKey: '',
    baseUrl: '',
    isDefault: 0,
    isEnabled: 1,
    remark: '',
    thinkingMode: 'auto',
    reasoningEffort: 'high',
    contextLength: '32k',
    webPhone: '',
    webPassword: '',
    webAreaCode: '+86'
  })
}

function handleAdd() {
  resetForm()
  dialogTitle.value = '添加模型配置'
  isEdit.value = false
  dialogVisible.value = true
}

function handleEdit(row) {
  Object.assign(form, {
    configId: row.configId,
    provider: row.provider,
    providerName: row.providerName || providerNames[row.provider] || '',
    model: row.model,
    apiKey: row.apiKey,
    baseUrl: row.baseUrl || '',
    isDefault: row.isDefault,
    isEnabled: row.isEnabled,
    remark: row.remark || '',
    thinkingMode: row.thinkingMode || 'auto',
    reasoningEffort: row.reasoningEffort || 'high',
    contextLength: row.contextLength || '32k'
  })
  dialogTitle.value = '编辑模型配置'
  isEdit.value = true
  dialogVisible.value = true
}

async function handleSave() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  saving.value = true
  try {
    if (isEdit.value) {
      const res = await updateAiConfig(form)
      if (res.code === 200) {
        ElMessage.success('保存成功')
        dialogVisible.value = false
        fetchConfigList()
      } else {
        ElMessage.error(res.msg || '保存失败')
      }
    } else {
      const res = await addAiConfig(form)
      if (res.code === 200) {
        ElMessage.success('添加成功')
        dialogVisible.value = false
        fetchConfigList()
      } else {
        ElMessage.error(res.msg || '添加失败')
      }
    }
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTestConnection() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  testing.value = true
  try {
    const res = await testAiConnection(form)
    if (res.code === 200) {
      ElMessage.success(res.msg || '连接成功')
    } else {
      ElMessage.error(res.msg || '连接失败')
    }
  } catch (error) {
    console.error('测试连接失败:', error)
    ElMessage.error('测试连接失败')
  } finally {
    testing.value = false
  }
}

async function handleSetDefault(row) {
  try {
    const res = await setDefaultConfig(row.configId)
    if (res.code === 200) {
      ElMessage.success('已设为默认模型')
      fetchConfigList()
    } else {
      ElMessage.error(res.msg || '设置失败')
    }
  } catch (error) {
    console.error('设置默认失败:', error)
    ElMessage.error('设置失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除模型配置"${row.model}"吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const res = await deleteAiConfig(row.configId)
    if (res.code === 200) {
      ElMessage.success('删除成功')
      fetchConfigList()
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
    }
  }
}

onMounted(() => {
  fetchConfigList()
})

defineExpose({
  refresh: fetchConfigList
})
</script>

<style scoped>
.ai-model-manager {
  padding: 20px;
}

.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.model-header .header-text {
  min-width: 0;
}

.model-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.model-header .header-tip {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #9ca3af;
}

.btn-add {
  border-radius: 8px;
  font-weight: 500;
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
}

.btn-add:hover {
  border-color: #b3b3b3;
  color: #4b5563;
  transform: translateY(-1px);
}

.btn-action {
  border-radius: 6px;
  font-weight: 500;
  padding: 4px 10px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
  font-size: 13px;
}

.btn-action:hover {
  border-color: #b3b3b3;
  color: #4b5563;
  transform: translateY(-1px);
}

.btn-action.btn-default {
  color: #059669;
  border-color: #a7d7d0;
  background: #f0fdf9;
}

.btn-action.btn-default:hover {
  background: #ecfdf5;
  border-color: #059669;
}

.btn-action.btn-danger {
  color: #dc2626;
  border-color: #fecaca;
  background: #fef2f2;
}

.btn-action.btn-danger:hover {
  background: #fef2f2;
  border-color: #dc2626;
}

.btn-cancel {
  border-radius: 8px;
  font-weight: 500;
  padding: 8px 16px;
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #6b7280;
}

.btn-cancel:hover {
  border-color: #b3b3b3;
  color: #4b5563;
}

.btn-action.btn-test {
  color: #d97706;
  border-color: #fcd34d;
  background: #fffbeb;
}

.btn-action.btn-test:hover {
  background: #fefce8;
  border-color: #d97706;
}

.btn-primary {
  border-radius: 8px;
  font-weight: 500;
  padding: 8px 16px;
  background: #1f2937;
  border: 1px solid #1f2937;
  color: #fff;
}

.btn-primary:hover {
  background: #374151;
  border-color: #374151;
  transform: translateY(-1px);
}

.form-tip {
  margin-top: 6px;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.5;
}
</style>
