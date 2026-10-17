<template>
  <!-- ⚠️ 必须有**单一根节点**：本组件现在还要内嵌一个 `AiModelManager`（添加模型对话框），
       多根节点会让父级传下来的 `class`/`style`（如 chat.vue 的 `class="settings-expert-model"`）
       **无法透传**（Vue 对多根组件不自动继承属性）。用外层 div 承接，宽度仍由 `width` prop 决定。 -->
  <div class="ai-model-selector-root" :class="{ 'is-borderless': borderless, 'is-auto': width === 'auto' }"
    :style="width === 'auto' ? undefined : { width: width }">
    <el-select :model-value="innerValue" @update:model-value="handleChange" placeholder="自动（跟随默认）" size="small"
      class="ai-model-selector" popper-class="ai-model-selector-popper" style="width: 100%" :disabled="disabled">
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

      <!-- 下拉框底部入口：任何登录用户都能添加自己的模型（后端不限管理员，guest 除外） -->
      <template #footer>
        <div v-if="!disabled" class="add-model-row" @mousedown.stop
          @click.stop="openAddDialog">
          ＋ 添加自定义模型
        </div>
      </template>
    </el-select>

    <AiModelManager ref="mgrRef" dialog-only @saved="onManagerSaved" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { listAiConfig } from '@/api/system/aiConfig'
import { capabilityLabel } from '@/utils/ai-model-capability'
import AiModelManager from '@/components/AiModelManager/index.vue'

/** 首次进入（无历史记忆）时的默认模型：DS 官方新命名，不再强调 v4flash */
const DEFAULT_MODEL = 'deepseek-flash'

const props = defineProps({
  /** 对外 v-model：**model 名**（'' = 自动跟随默认） */
  modelValue: { type: String, default: '' },
  width: { type: String, default: '220px' },
  disabled: { type: Boolean, default: false },
  /**
   * 无边框形态（DSH 的底部输入区就是这个观感）：
   * 去掉 select 的描边/白底，只留文字 + 箭头，hover 才浮出浅底。
   * 用于「模型选择器直接坐在工具行里、与发送按钮同一条线」的场景。
   */
  borderless: { type: Boolean, default: false },
  /** 场景标识：每个使用点单独记忆（聊天助手 / AI 解析 / 出题等互不影响） */
  scene: { type: String, required: true },
  /**
   * 受控模式开关。false = 用于「加载既有值」的表单：
   *   挂载时**不**自动挑默认、**不** emit，只把传入的 model 名映射成 configId 显示；
   *   找不到就留空。外部改 modelValue 时同步映射。默认 true，保持既有调用方行为不变。
   */
  autoDefault: { type: Boolean, default: true }
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
  if (props.autoDefault) localStorage.setItem(storageKey, selectedId.value)
  emitFor(selectedId.value)
}

// 受控模式：把外部传入的 model 名映射成本地 configId（仅用于显示，**不** emit/落记忆）
const mapValueToId = (name) => {
  if (!name) return ''
  const cfg = configList.value.find(c => c.model === name)
  return cfg ? String(cfg.configId) : ''
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
  // 受控模式：只映射外部值，绝不自动挑默认、绝不 emit
  if (!props.autoDefault) {
    selectedId.value = mapValueToId(props.modelValue)
    return
  }
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
    return
  }
  // 受控模式：外部换值（如编辑表单换了一条记录）时同步映射，不 emit
  if (!props.autoDefault) {
    selectedId.value = mapValueToId(v)
  }
})

defineExpose({ refresh: fetchConfigs })

const mgrRef = ref(null)

const openAddDialog = () => {
  mgrRef.value?.openAdd()
}

const onManagerSaved = () => {
  fetchConfigs()
}
</script>

<style scoped>
.ai-model-selector-root {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  vertical-align: middle;

  /*
   * ⚠️ `AiModelManager`（dialog-only）在模板里是一个只承载弹窗的空壳 div。
   *    它的 `el-dialog` 是 teleport 到 body 的，但**根 div 本身仍占 40px 宽**，
   *    于是"模型名 → 发送按钮"之间凭空多出这 40px（用户反馈间距太大）。
   *    这里让它彻底脱离盒模型（不占位、不参与对齐）。
   */
  > .ai-model-manager {
    position: absolute;
    width: 0;
    height: 0;
    overflow: hidden;
    pointer-events: none;
  }
}

/* width="auto"：不写死像素，但**必须给一个能容下模型名的宽度**。
   ⚠️ 这里试过 `width: auto / flex: none`：Element Plus 的 select 内部用绝对定位的
      选中项 + 绝对定位箭头渲染，父级 `width:auto` 会塌缩成一条（只剩箭头，文字没了）。
      所以给一个按内容估算的舒适宽度区间，由 `max-width` 兜住超长模型名。 */
.ai-model-selector-root.is-auto {
  width: fit-content;

  .ai-model-selector {
    /* 132px ≈ "deepseek-flash"（12.5px 字号）+ 右侧箭头与内边距，正好不截断也不留空档 */
    width: 132px !important;
    min-width: 0;
    max-width: 220px;
  }
}

.ai-model-selector {
  flex: 1;
  min-width: 0;
}

.ai-model-selector :deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: 0 0 0 1px #e5e7eb;
  background: #fff;
}

.ai-model-selector :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #b3b3b3;
}

/* ---- 无边框形态：只留文字 + 箭头（DSH 底部输入区的模型选择器） ---- */
.ai-model-selector-root.is-borderless {
  /* 容器宽度必须由内容决定，否则根节点会按 max-width 撑开，
     在"模型名"和右侧发送按钮之间留出一大段空白（用户 2026-10-17 截图反馈）。 */
  width: fit-content;
  max-width: 100%;

  /* EP 2.13 的 select 有两种内层实现（el-input__wrapper / el-select__wrapper），都覆盖 */
  .ai-model-selector :deep(.el-input__wrapper),
  .ai-model-selector :deep(.el-select__wrapper) {
    background: transparent;
    box-shadow: none;
    /* 右侧只留箭头所需的 12px，不再留 18px 的大空档 */
    padding: 0 12px 0 8px;
    border: none;
  }

  .ai-model-selector :deep(.el-input__wrapper:hover),
  .ai-model-selector :deep(.el-select__wrapper:hover) {
    background: var(--os-bg-hover);
    box-shadow: none;
    border-radius: var(--os-radius-sm);
  }

  .ai-model-selector :deep(.el-input__wrapper.is-focus),
  .ai-model-selector :deep(.el-select__wrapper.is-focused) {
    box-shadow: none;
    background: var(--os-bg-hover);
    border-radius: var(--os-radius-sm);
  }

  .ai-model-selector :deep(.el-input__inner),
  .ai-model-selector :deep(.el-select__selected-item) {
    color: var(--os-text-3);
    font-size: 12.5px;
  }

  .ai-model-selector :deep(.el-select__caret),
  .ai-model-selector :deep(.el-select__icon) {
    color: var(--os-text-4);
  }
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

.add-model-row {
  height: 34px;
  line-height: 34px;
  padding: 0 20px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  cursor: pointer;
  border-top: 1px solid var(--el-border-color-light);
  white-space: nowrap;
  text-overflow: ellipsis;
  overflow: hidden;
}

.add-model-row:hover {
  background: var(--el-fill-color-light);
}
</style>

<!-- 下拉浮层被 teleport 到 body，scoped 样式够不到，需用 popper-class 全局覆盖 footer 内边距 -->
<style>
.ai-model-selector-popper .el-select-dropdown__footer {
  padding: 0;
  border-top: none;
}
</style>
