<template>
  <div class="app-container rag-config">
    <!-- ============ 顶部：当前状态 ============ -->
    <el-card shadow="never" class="status-card">
      <div class="status-row">
        <div class="status-main">
          <span class="status-label">当前向量化方式</span>
          <el-tag :type="statusTagType" size="large" effect="dark" class="status-tag">
            {{ backendLabel }}
          </el-tag>
          <span class="status-summary">{{ status.summary }}</span>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="load">重新检测</el-button>
      </div>

      <!-- 环境不满足时的引导 -->
      <el-alert
        v-if="showGuide"
        :title="guideTitle"
        type="warning"
        :closable="false"
        show-icon
        class="guide-alert"
      >
        <div class="guide-body">{{ guideText }}</div>
        <div class="guide-actions">
          <el-button type="primary" size="small" @click="switchToCloud">
            改用云端（硅基流动）
          </el-button>
          <el-button size="small" @click="showInstallHelp = true">
            我想装本地模型
          </el-button>
        </div>
      </el-alert>
    </el-card>

    <!-- ============ 选择后端 ============ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>向量化后端</span>
          <span class="card-hint">切换后立即生效，无需重启服务</span>
        </div>
      </template>

      <el-radio-group v-model="form.backend" class="backend-group" @change="onBackendChange">
        <el-radio-button value="local" :disabled="!status.local.available && form.backend !== 'local'">
          <div class="backend-item">
            <div class="backend-title">
              本地模型
              <el-tag v-if="status.local.available" type="success" size="small" effect="plain">可用</el-tag>
              <el-tag v-else type="info" size="small" effect="plain">未就绪</el-tag>
            </div>
            <div class="backend-desc">文档不出内网，不消耗云端额度；需本机下载约 2.2GB 模型</div>
          </div>
        </el-radio-button>

        <el-radio-button value="siliconflow">
          <div class="backend-item">
            <div class="backend-title">
              云端（硅基流动）
              <el-tag v-if="status.cloud.available" type="success" size="small" effect="plain">可用</el-tag>
              <el-tag v-else type="danger" size="small" effect="plain">缺 Key</el-tag>
            </div>
            <div class="backend-desc">开箱即用、无需本地模型；需联网并配置 API Key</div>
          </div>
        </el-radio-button>

        <el-radio-button value="auto">
          <div class="backend-item">
            <div class="backend-title">自动</div>
            <div class="backend-desc">优先本地，本地不可用时自动回退云端</div>
          </div>
        </el-radio-button>
      </el-radio-group>
    </el-card>

    <!-- ============ 本地环境检测 ============ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>本地环境检测</span>
          <el-tag :type="status.local.available ? 'success' : 'warning'" size="small" effect="plain">
            {{ status.local.available ? '全部就绪' : '缺少依赖或模型' }}
          </el-tag>
        </div>
      </template>

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="Python 依赖">
          <el-tag :type="status.local.depsInstalled ? 'success' : 'danger'" size="small">
            {{ status.local.depsInstalled ? '已安装 sentence-transformers' : '未安装' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型文件">
          <el-tag :type="status.local.modelCached ? 'success' : 'danger'" size="small">
            {{ status.local.modelCached ? '已下载' : '未下载' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="模型名称">{{ status.local.modelName }}</el-descriptions-item>
        <el-descriptions-item label="预计占用">{{ status.local.estimatedSizeMB }} MB</el-descriptions-item>
        <el-descriptions-item label="模型位置" :span="2">
          <span class="mono">{{ status.local.modelPath || status.local.modelDir || '（默认目录）' }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="!status.local.available"
        :title="status.local.reason"
        type="info"
        :closable="false"
        show-icon
        class="reason-alert"
      >
        <div class="reason-text">{{ status.local.suggestion }}</div>
      </el-alert>
    </el-card>

    <!-- ============ 云端 API Key ============ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>云端 API Key</span>
          <el-tag v-if="status.cloud.keyConfigured" type="success" size="small" effect="plain">
            已配置
          </el-tag>
          <el-tag v-else type="warning" size="small" effect="plain">未配置</el-tag>
        </div>
      </template>

      <el-form :model="form" label-width="180px" class="param-form">
        <el-form-item label="硅基流动 API Key">
          <div class="key-row">
            <el-input
              v-model="form.cloudApiKey"
              :type="showKey ? 'text' : 'password'"
              :placeholder="keyPlaceholder"
              clearable
              class="key-input"
            />
            <el-button text @click="showKey = !showKey">
              {{ showKey ? '隐藏' : '显示' }}
            </el-button>
            <el-button v-if="status.cloud.keyConfigured" text type="danger" @click="clearKey">
              清除
            </el-button>
          </div>
          <div class="field-tip key-tip">
            在
            <a href="https://cloud.siliconflow.cn/account/ak" target="_blank" rel="noopener">
              siliconflow.cn
            </a>
            控制台创建，形如 <code>sk-xxxxxxxx</code>。保存后立即生效，无需重启。
            <br />
            <span v-if="status.cloud.keySource === 'env'" class="source-note">
              当前 Key 来自 .env 配置；在这里填写会覆盖它。
            </span>
            <span v-else-if="status.cloud.keyConfigured" class="source-note">
              当前 Key：{{ status.cloud.keyMasked }}（已隐藏，不会回传原文）
            </span>
          </div>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ============ 检索参数 ============ -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>检索参数</span>
          <span class="card-hint">影响「从资料里找多准、找多少」</span>
        </div>
      </template>

      <el-form :model="form" label-width="180px" class="param-form">
        <el-form-item label="分块大小">
          <el-input-number v-model="form.chunkSize" :min="100" :max="4000" :step="50" />
          <span class="field-tip">每段切多少字。太小会切断语义，太大会稀释检索精度</span>
        </el-form-item>

        <el-form-item label="分块重叠">
          <el-input-number v-model="form.chunkOverlap" :min="0" :max="1000" :step="10" />
          <span class="field-tip">相邻两段重叠的字数，避免一句话被切成两半</span>
        </el-form-item>

        <el-form-item label="检索返回条数">
          <el-slider v-model="form.topK" :min="1" :max="20" show-input class="slider" />
          <span class="field-tip">每次检索带回多少段原文给模型参考</span>
        </el-form-item>

        <el-form-item label="混合检索 RRF 常数">
          <el-input-number v-model="form.rrfK" :min="1" :max="200" :step="5" />
          <span class="field-tip">两路检索结果的融合平滑度，默认 60（论文建议值）</span>
        </el-form-item>

        <el-form-item label="本地失败自动回落云端">
          <el-switch v-model="form.autoFallback" />
          <span class="field-tip">开启后本地模型出错会自动改用云端，不会让检索直接失败</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ============ 保存 ============ -->
    <div class="actions">
      <el-button type="primary" :loading="saving" @click="save">保存配置</el-button>
      <el-button @click="load">重置</el-button>
    </div>

    <!-- 本地安装帮助 -->
    <el-dialog v-model="showInstallHelp" title="如何启用本地向量化" width="620px">
      <div class="help-body">
        <p>本地模式会把文档转成向量存在你自己的数据库里，<strong>内容不会发到任何云端</strong>。</p>
        <p>需要两步：</p>
        <ol>
          <li>
            安装依赖（在 <code>openstudy-fastapi</code> 目录下）：
            <pre>pip install -r requirements-local-embedding.txt</pre>
          </li>
          <li>
            重启后端，首次上传文档时会自动从魔搭下载 <code>BAAI/bge-m3</code>（约 2.2GB）。
          </li>
        </ol>
        <p class="help-note">
          如果机器内存小于 8GB 或磁盘紧张，建议直接用云端模式，效果一样且不占本地资源。
        </p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { getRagConfig, updateRagConfig } from '@/api/ai/ragConfig'

const loading = ref(false)
const saving = ref(false)
const showInstallHelp = ref(false)
const showKey = ref(false)

const status = reactive<any>({
  config: {},
  current: 'auto',
  effective: 'unavailable',
  summary: '',
  local: { available: false, depsInstalled: false, modelCached: false, modelName: '', modelPath: '', modelDir: '', estimatedSizeMB: 0, reason: '', suggestion: '' },
  cloud: { available: false, keyConfigured: false, keyMasked: '', keySource: '', model: '', reason: '', suggestion: '' }
})

const form = reactive({
  backend: 'auto',
  model: '',
  chunkSize: 500,
  chunkOverlap: 50,
  topK: 5,
  rrfK: 60,
  cloudModel: '',
  autoFallback: true,
  // 用户新填的 Key。空 = 不改；__CLEAR__ = 清空
  cloudApiKey: ''
})

/** Key 输入框的占位文案：已配置时提示「留空即不修改」 */
const keyPlaceholder = computed(() =>
  status.cloud.keyConfigured
    ? `已配置（${status.cloud.keyMasked}），留空表示不修改`
    : '粘贴 sk- 开头的硅基流动 API Key'
)

/** 清空 Key（需要用户在保存时确认，这里只置标记） */
function clearKey() {
  form.cloudApiKey = '__CLEAR__'
  ElMessage.info('已标记为清除，点「保存配置」后生效')
}


const backendLabel = computed(() => {
  const map: Record<string, string> = {
    local: '本地模型',
    siliconflow: '云端（硅基流动）',
    auto: '自动',
    unavailable: '不可用'
  }
  return map[status.effective] || status.effective
})

const statusTagType = computed(() => {
  if (status.effective === 'local') return 'success'
  if (status.effective === 'siliconflow') return 'primary'
  if (status.effective === 'auto') return 'info'
  return 'danger'
})

const showGuide = computed(() => {
  // 选了本地但没装 / 选了云端但没 Key / 都没有
  if (form.backend === 'local' && !status.local.available) return true
  if (form.backend === 'siliconflow' && !status.cloud.available) return true
  return !status.local.available && !status.cloud.available
})

const guideTitle = computed(() => {
  if (form.backend === 'local' && !status.local.available) return '本机还没有可用的本地向量化模型'
  if (form.backend === 'siliconflow' && !status.cloud.available) return '云端向量化缺少 API Key'
  return '当前两条链路都不可用'
})

const guideText = computed(() => {
  if (form.backend === 'local' && !status.local.available) return status.local.suggestion
  if (form.backend === 'siliconflow' && !status.cloud.available) return status.cloud.suggestion
  return '本地未安装模型，云端也没配 Key。建议先切换到云端模式（只需一个 API Key，无需下载模型）。'
})

async function load() {
  loading.value = true
  try {
    const res: any = await getRagConfig()
    if (res.code === 200) {
      Object.assign(status, res.data)
      const c = res.data.config || {}
      form.backend = c['rag.embedding.backend'] ?? 'auto'
      form.model = c['rag.embedding.model'] ?? ''
      form.chunkSize = Number(c['rag.embedding.chunkSize'] ?? 500)
      form.chunkOverlap = Number(c['rag.embedding.chunkOverlap'] ?? 50)
      form.topK = Number(c['rag.embedding.topK'] ?? 5)
      form.rrfK = Number(c['rag.embedding.rrfK'] ?? 60)
      form.cloudModel = c['rag.embedding.cloudModel'] ?? ''
      form.autoFallback = String(c['rag.embedding.autoFallback'] ?? 'true') === 'true'
      // Key 永远不回显原文：清空输入框，已配置状态由 status.cloud 展示
      form.cloudApiKey = ''
    } else {
      ElMessage.error(res.msg || '读取失败')
    }
  } catch (e: any) {
    ElMessage.error('读取 RAG 配置失败：' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function onBackendChange(val: string) {
  if (val === 'siliconflow' && !status.cloud.available) {
    ElMessage.warning(status.cloud.reason || '云端未配置 API Key，请在下方填写')
  }
}

/** 一键切云端：如果还没 Key，先把焦点引导到 Key 输入框 */
async function switchToCloud() {
  form.backend = 'siliconflow'
  if (!status.cloud.keyConfigured) {
    ElMessage.warning('请先在「云端 API Key」处填写 Key，再保存')
    // 滚到 Key 区域
    document.querySelector('.key-input')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    return
  }
  await save()
}

async function save() {
  saving.value = true
  try {
    const payload: Record<string, any> = {
      backend: form.backend,
      model: form.model || undefined,
      chunkSize: form.chunkSize,
      chunkOverlap: form.chunkOverlap,
      topK: form.topK,
      rrfK: form.rrfK,
      cloudModel: form.cloudModel || undefined,
      autoFallback: form.autoFallback
    }
    // 只有用户真的输入了才传（空 = 不改；__CLEAR__ = 清空）
    if (form.cloudApiKey) {
      payload.cloudApiKey = form.cloudApiKey
    }
    const res: any = await updateRagConfig(payload)
    if (res.code === 200) {
      Object.assign(status, res.data)
      form.cloudApiKey = ''
      ElMessage.success('配置已保存并生效')
      if (res.data?.needReindex && res.data?.reindexHint) {
        ElMessage.warning({ message: res.data.reindexHint, duration: 8000, showClose: true })
      }
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped lang="scss">
.rag-config {
  padding: 16px 20px 40px;
}

.status-card,
.section-card {
  margin-bottom: 16px;
  border-radius: 10px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.status-main {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.status-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.status-tag {
  font-weight: 600;
}

.status-summary {
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.guide-alert {
  margin-top: 14px;
}

.guide-body {
  font-size: 13px;
  line-height: 1.7;
  margin-bottom: 10px;
}

.guide-actions {
  display: flex;
  gap: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.card-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.backend-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

/* 让选中态更明显：主色描边 + 浅色底，文字保持深色可读 */
.backend-group :deep(.el-radio-button__inner) {
  border-left: 1px solid var(--el-border-color);
  border-radius: 8px !important;
  padding: 14px 16px;
  min-width: 250px;
  transition: all 0.15s;
}

.backend-group :deep(.el-radio-button__inner:hover) {
  border-color: var(--el-color-primary);
}

.backend-group :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: var(--el-color-primary-light-9) !important;
  border: 1.5px solid var(--el-color-primary) !important;
  box-shadow: none !important;
  color: var(--el-text-color-primary) !important;
}

.backend-item {
  padding: 0;
  text-align: left;
  max-width: 230px;
}

.backend-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.backend-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  white-space: normal;
}

.reason-alert {
  margin-top: 14px;
}

.reason-text {
  font-size: 12px;
  line-height: 1.6;
}

.param-form {
  max-width: 760px;
}

/* 云端 Key 输入行 */
.key-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  max-width: 560px;
}

.key-input {
  flex: 1;
}

.key-tip {
  display: block;
  margin-left: 0;
  margin-top: 6px;
  line-height: 1.7;
}

.key-tip a {
  color: var(--el-color-primary);
  text-decoration: none;
}

.key-tip code {
  background: var(--el-fill-color-light);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
}

.source-note {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}

.field-tip {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.slider {
  max-width: 380px;
  margin-right: 12px;
}

.mono {
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  word-break: break-all;
}

.actions {
  display: flex;
  gap: 10px;
  padding-left: 4px;
}

.help-body {
  font-size: 13px;
  line-height: 1.8;
}

.help-body pre {
  background: var(--el-fill-color-light);
  padding: 10px 12px;
  border-radius: 6px;
  margin: 6px 0;
  font-size: 12px;
  overflow-x: auto;
}

.help-note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
