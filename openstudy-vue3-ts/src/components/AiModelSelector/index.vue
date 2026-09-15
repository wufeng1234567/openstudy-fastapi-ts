<template>
  <el-select :model-value="modelValue" @update:model-value="handleChange" :placeholder="defaultLabel" size="small"
    class="ai-model-selector" :style="{ width: width }" :disabled="disabled">
    <el-option :label="defaultLabel" value="" />
    <el-option v-for="config in configList" :key="config.configId"
      :label="(config.providerName || config.provider) + ' - ' + config.model" :value="config.provider" />
  </el-select>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { listAiConfig } from '@/api/system/aiConfig'

const STORAGE_KEY = 'openstudy_ai_provider'

const props = defineProps({
  modelValue: { type: String, default: '' },
  width: { type: String, default: '200px' },
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'change'])

const configList = ref([])
// 系统默认模型显示名（来自 sys_ai_config 表 is_default=1 的配置）
const defaultLabel = ref('系统默认')

const handleChange = (val) => {
  localStorage.setItem(STORAGE_KEY, val)
  emit('update:modelValue', val)
  emit('change', val)
}

const fetchConfigs = async () => {
  try {
    const res = await listAiConfig()
    if (res.code === 200 && res.rows) {
      configList.value = res.rows.filter(c => c.isEnabled === 1)
      // 找到默认配置，更新"系统默认"显示
      const def = configList.value.find(c => c.isDefault === 1)
      if (def) {
        defaultLabel.value = `系统默认（${def.providerName || def.provider} · ${def.model}）`
      }
    }
  } catch (e) {
    console.error('获取模型配置失败:', e)
  }
}

// 初始化时从 localStorage 恢复选择
const initFromStorage = () => {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved !== null && saved !== props.modelValue) {
    emit('update:modelValue', saved)
    emit('change', saved)
  }
}

onMounted(() => {
  fetchConfigs()
  initFromStorage()
})

defineExpose({ refresh: fetchConfigs })
</script>

<style scoped>
.ai-model-selector :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
  background: #fff;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.ai-model-selector :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #d1d5db;
}

.ai-model-selector :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #b3b3b3;
}
</style>
