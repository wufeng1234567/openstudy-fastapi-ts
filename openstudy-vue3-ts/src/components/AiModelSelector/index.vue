<template>
  <el-select :model-value="innerValue" @update:model-value="handleChange" placeholder="自动（跟随默认）" size="small"
    class="ai-model-selector" :style="{ width: width }" :disabled="disabled">
    <!--
      取值约定（重要）：
        · 对外 v-model 仍是 **model 名**（'' = 自动跟随默认），下游逻辑无需改；
        · 但 el-option 的 value 用 **configId**（全局唯一）——因为系统官方与用户自定义
          可能同名（都叫 deepseek-flash），用 model 名作 value 会冲突、无法同时展示两条。
        · 选中后本组件把 configId 映射回 model 名 emit 出去；同时额外 emit `select`
          （完整 config 对象），供需要区分「官方那条 / 我的那条」的调用方使用。
    -->
    <el-option label="自动（跟随默认）" value="" />

    <el-option-group v-if="systemConfigs.length" label="系统提供（官方）">
      <el-option v-for="config in systemConfigs" :key="'sys-' + config.configId"
        :label="config.model" :value="String(config.configId)">
        <span class="opt-main">{{ config.model }}</span>
        <!-- 「仅文本」= 不能传图片（如 deepseek-v4-pro），提前告知，避免用户上传后才发现 -->
        <span v-if="capabilityLabel(config.model)" class="opt-tag">{{ capabilityLabel(config.model) }}</span>
        <span v-if="config.isDefault === 1" class="opt-tag">默认</span>
      </el-option>
    </el-option-group>

    <el-option-group v-if="userConfigs.length" label="我的模型（自定义）">
      <el-option v-for="config in userConfigs" :key="'usr-' + config.configId"
        :label="userOptionLabel(config)" :value="String(config.configId)">
        <span class="opt-main">{{ userOptionLabel(config) }}</span>
        <span v-if="capabilityLabel(config.model)" class="opt-tag">{{ capabilityLabel(config.model) }}</span>
      </el-option>
    </el-option-group>
  </el-select>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { listAiConfig } from '@/api/system/aiConfig'
import { capabilityLabel } from '@/utils/ai-model-capability'

/** 首次进入（无历史记忆）时的默认模型：DS 官方新命名，不再强调 v4flash */
const DEFAULT_MODEL = 'deepseek-flash'

const props = defineProps({
  /** 对外 v-model：**model 名**（'' = 自动跟随默认） */
  modelValue: { type: String, default: '' },
  width: { type: String, default: '220px' },
  disabled: { type: Boolean, default: false },
  /** 场景标识：每个使用点单独记忆（聊天助手 / AI 解析 / 出题等互不影响） */
  scene: { type: String, required: true }
})

const emit = defineEmits(['update:modelValue', 'change', 'select'])

// 分场景历史记忆：localStorage key 按 scene 隔离（存 configId）
const storageKey = `openstudy_ai_model_${props.scene}`

const configList = ref([])
// 内部选中的 configId（'' = 自动）
const selectedId = ref('')

// 两级来源：系统提供（user_id 为空）/ 用户自定义（user_id 有值）
// **两组各自完整展示**：即使同名也各列一条（系统官方一条 + 我的模型一条），
// 靠分组标题 + label 前缀区分；el-option value 用 configId 所以不冲突。
const systemConfigs = computed(() => configList.value.filter(c => c.source !== 'user'))
const userConfigs = computed(() => configList.value.filter(c => c.source === 'user'))

// 用户自定义模型 label 加「我的 ·」前缀，和系统官方一眼区分
const userOptionLabel = (config) => {
  return `我的 · ${config.model}`
}

// el-select 绑定的内部值 = 选中 configId
const innerValue = computed(() => selectedId.value)

const emitFor = (id) => {
  const cfg = id ? configList.value.find(c => String(c.configId) === String(id)) : null
  const modelName = cfg ? cfg.model : ''
  emit('update:modelValue', modelName)
  emit('change', modelName)
  // 额外抛完整 config，供需要 provider / configId 的调用方区分同名
  emit('select', cfg || null)
}

const handleChange = (val) => {
  selectedId.value = val || ''
  localStorage.setItem(storageKey, selectedId.value)
  emitFor(selectedId.value)
}

const applyId = (id) => {
  if (id && String(id) !== selectedId.value) {
    selectedId.value = String(id)
    emitFor(selectedId.value)
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

/** 初始化：优先恢复本场景历史记忆（configId）；否则选系统官方 deepseek-flash，退回第一条 */
const restoreSelection = () => {
  const saved = localStorage.getItem(storageKey)
  if (saved && configList.value.some(c => String(c.configId) === String(saved))) {
    applyId(saved)
    return
  }
  const sys = systemConfigs.value.find(c => c.model === DEFAULT_MODEL)
  if (sys) { applyId(sys.configId); return }
  const usr = userConfigs.value.find(c => c.model === DEFAULT_MODEL)
  if (usr) { applyId(usr.configId); return }
  const first = configList.value[0]
  if (first) applyId(first.configId)
}

onMounted(() => {
  fetchConfigs()
})

// 外部把 v-model 置空（重置为自动）时同步内部态
watch(() => props.modelValue, (v) => {
  if (v === '') {
    selectedId.value = ''
    localStorage.removeItem(storageKey)
  }
})

defineExpose({ refresh: fetchConfigs })
</script>

<style scoped>
.ai-model-selector :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
  background: #fff;
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
