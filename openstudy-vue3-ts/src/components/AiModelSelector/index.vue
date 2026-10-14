<template>
  <el-select :model-value="modelValue" @update:model-value="handleChange" placeholder="自动（跟随默认）" size="small"
    class="ai-model-selector" :style="{ width: width }" :disabled="disabled">
    <!--
      「自动」选项：value = 空串，语义 = **跟随系统默认模型**（后端 `build_agent_llm` 在
      model 为空时用默认模型）。加它是为了：
        ① 空值不再显示成占位符「请选择」——那会让用户以为「没配置好 / 坏了」；
        ② 用户主动选过某个模型后，还能**切回自动**（没有这个选项就切不回去）。
      这就是默认态：首次进入若 `restoreSelection` 未能拿到模型列表，也会落到「自动」而非「请选择」。
    -->
    <el-option label="自动（跟随默认）" value="" />

    <el-option-group v-if="systemConfigs.length" label="系统提供">
      <el-option v-for="config in systemConfigs" :key="'sys-' + config.configId"
        :label="config.model" :value="config.model">
        <span class="opt-main">{{ config.model }}</span>
        <!-- 「仅文本」= 不能传图片（如 deepseek-v4-pro），提前告知，避免用户上传后才发现 -->
        <span v-if="capabilityLabel(config.model)" class="opt-tag">{{ capabilityLabel(config.model) }}</span>
        <span v-if="config.isDefault === 1" class="opt-tag">默认</span>
      </el-option>
    </el-option-group>

    <el-option-group v-if="userConfigs.length" label="用户自定义">
      <el-option v-for="config in userConfigs" :key="'usr-' + config.configId"
        :label="optionLabel(config)" :value="config.model">
        <span class="opt-main">{{ optionLabel(config) }}</span>
        <span v-if="capabilityLabel(config.model)" class="opt-tag">{{ capabilityLabel(config.model) }}</span>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { listAiConfig } from '@/api/system/aiConfig'
import { capabilityLabel } from '@/utils/ai-model-capability'

/** 首次进入（无历史记忆）时的默认模型：DS 官方新命名，不再强调 v4flash */
const DEFAULT_MODEL = 'deepseek-flash'

const props = defineProps({
  modelValue: { type: String, default: '' },
  width: { type: String, default: '220px' },
  disabled: { type: Boolean, default: false },
  /** 场景标识：每个使用点单独记忆（聊天助手 / AI 解析 / 出题等互不影响） */
  scene: { type: String, required: true }
})

const emit = defineEmits(['update:modelValue', 'change'])

// 分场景历史记忆：localStorage key 按 scene 隔离
const storageKey = `openstudy_ai_model_${props.scene}`

const configList = ref([])

// 两级来源：系统提供（user_id 为空）/ 用户自定义（user_id 有值）
// ⚠️ el-option 的 value 用 model 名，同名会重复。原逻辑「用户同名则隐藏系统行」的副作用是
//    「系统官方模型被用户自定义顶掉、从下拉里消失」——这不是我们要的。
//    改为：**系统提供组始终完整展示**（官方模型永远可见），用户自定义组只补充
//    「系统里没有的 model」；同名时以系统（官方）行展示。
const systemConfigs = computed(() => configList.value.filter(c => c.source !== 'user'))
const userConfigs = computed(() => {
  const systemModels = new Set(systemConfigs.value.map(c => c.model))
  // 用户自定义里与系统同名的，不再重复展示（选了同名 model 会优先解析到系统/凭据行）
  return configList.value.filter(c => c.source === 'user' && !systemModels.has(c.model))
})

const optionLabel = (config) => {
  return `${config.providerName || config.provider} · ${config.model}`
}

const handleChange = (val) => {
  // 用户主动选择才写入历史记忆（首次默认选中不落盘）
  localStorage.setItem(storageKey, val)
  emit('update:modelValue', val)
  emit('change', val)
}

const applyValue = (val) => {
  if (val && val !== props.modelValue) {
    emit('update:modelValue', val)
    emit('change', val)
  }
}

const fetchConfigs = async () => {
  try {
    // scope='available'：系统提供的官方模型 + 我自己在「我的模型」里添加的模型。
    // 不能取 all —— 那会连带列出别人的自定义模型。
    const res = await listAiConfig('available')
    if (res.code === 200 && res.rows) {
      configList.value = res.rows.filter(c => c.isEnabled === 1)
    }
  } catch (e) {
    console.error('获取模型配置失败:', e)
  }
  restoreSelection()
}

/** 初始化：优先恢复本场景的历史记忆；没有记忆（首次进入）默认选中 deepseek-flash */
const restoreSelection = () => {
  const allModels = [
    ...userConfigs.value.map(c => c.model),
    ...systemConfigs.value.map(c => c.model)
  ]
  const saved = localStorage.getItem(storageKey)
  if (saved && allModels.includes(saved)) {
    applyValue(saved)
    return
  }
  if (allModels.includes(DEFAULT_MODEL)) {
    applyValue(DEFAULT_MODEL)
    return
  }
  // 兜底：没有 deepseek-flash 时选第一个可用模型
  if (allModels.length > 0) applyValue(allModels[0])
}

onMounted(() => {
  fetchConfigs()
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

.opt-main {
  float: left;
}

.opt-tag {
  float: right;
  color: #9ca3af;
  font-size: 12px;
  margin-left: 12px;
}
</style>
