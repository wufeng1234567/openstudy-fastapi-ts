<!--
  我的智能体 · 管理弹窗
  ============================================================================
  从 `chat.vue` 抽出来的独立组件（用户 2026-10-18 要求把设置做成全局对象）。
  逻辑与原实现一致，只做两件事：
    ① 数据自己拉（不再依赖对话页的 myAgents / toolOptions）；
    ② 变更后 `emit('changed')`，让上层刷新自己的列表。

  ⚠️ 不写死 Emoji / 不使用 Element Plus 实心图标（与全站线条风格一致）。
-->
<template>
  <el-dialog v-model="visible" title="我的智能体" width="600px" append-to-body>
    <div class="agent-mgr-list">
      <div v-if="!agents.length" class="agent-mgr-empty">
        还没有自定义智能体。点击下方「新建智能体」创建你自己的 AI 助手（可设人设、限定工具、绑定模型）。
      </div>
      <div v-for="a in agents" :key="a.agentId" class="agent-mgr-item">
        <div class="agent-mgr-main">
          <div class="agent-mgr-name">{{ a.name }}</div>
          <div class="agent-mgr-desc">{{ a.description || '（无简介）' }}</div>
          <div class="agent-mgr-tools">
            工具：{{ (a.tools && a.tools.length) ? a.tools.map((t) => toolLabelMap[t] || t).join('、') : '全部' }}
            <span v-if="a.model"> ｜ 模型：{{ a.model }}</span>
          </div>
        </div>
        <div class="agent-mgr-ops">
          <el-button text size="small" @click="openEdit(a)">编辑</el-button>
          <el-button text size="small" type="danger" @click="remove(a)">删除</el-button>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="openCreate">新建智能体</el-button>
      <el-button type="primary" @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 新建 / 编辑 表单 -->
  <el-dialog v-model="formVisible" :title="editingId == null ? '新建智能体' : '编辑智能体'" width="560px" append-to-body>
    <div v-if="editingId == null" class="agent-form-tip">
      <OsIcon name="lightbulb" :size="14" />
      也可以直接在输入框里说「帮我建一个数学老师智能体」，由「智能体专家」按对话帮你创建。
    </div>
    <el-form label-width="90px" label-position="right">
      <el-form-item label="名称" required>
        <el-input v-model="form.name" maxlength="64" show-word-limit placeholder="如：数学老师" />
      </el-form-item>
      <el-form-item label="简介">
        <el-input v-model="form.description" maxlength="255" placeholder="一句话说明它的用途" />
      </el-form-item>
      <el-form-item label="人设提示词">
        <el-input v-model="form.personaPrompt" type="textarea" :rows="4" maxlength="4000" show-word-limit
          placeholder="用英文描述这个智能体的角色与行为（会作为系统指令）。留空则仅按工具集工作。" />
      </el-form-item>
      <el-form-item label="可用工具">
        <el-select v-model="form.tools" multiple clearable placeholder="留空 = 不限（全部工具）" style="width: 100%">
          <el-option v-for="t in toolOptions" :key="t.name" :label="t.label || t.name" :value="t.name" />
        </el-select>
      </el-form-item>
      <el-form-item label="绑定模型">
        <AiModelSelector v-model="form.model" scene="agent-form" width="100%" :auto-default="false" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="formVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import OsIcon from '@/components/OsIcon/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import {
  listAgentConfigs,
  createAgentConfig,
  updateAgentConfig,
  deleteAgentConfig,
  type AgentConfig,
  type AgentConfigInput
} from '@/api/ai/agent'
import { fetchAgentToolsForUi } from '@/api/ai/agentDsFree'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  /** 列表变更（新建 / 编辑 / 删除后），上层可刷新自己的下拉 */
  (e: 'changed'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

/* ---------- 列表 ---------- */
const agents = ref<AgentConfig[]>([])
const loading = ref(false)

async function loadList() {
  loading.value = true
  try {
    const list = await listAgentConfigs()
    agents.value = (list as any) || []
  } catch {
    agents.value = []
  } finally {
    loading.value = false
  }
}

/* ---------- 工具清单（表单里的多选） ---------- */
const toolOptions = ref<Array<{ name: string; label?: string; disabled?: number }>>([])
let _toolInFlight: Promise<void> | null = null

async function loadToolOptions() {
  if (_toolInFlight) return _toolInFlight
  _toolInFlight = (async () => {
    try {
      /*
       * 工具清单走 `fetchAgentToolsForUi()`（与对话页同一入口）。
       * 它返回的是**全量**清单（含被禁用的条目，各自带 disabled: 1），
       * 正好适合表单里的多选：用户能看到所有可选工具。
       */
      const payload: any = await fetchAgentToolsForUi()
      const raw = Array.isArray(payload?.tools) ? payload.tools : []
      toolOptions.value = raw.map((t: any) => ({
        name: t.name || t.function?.name || '',
        label: t.label || t.title || t.function?.name || t.name || '',
        disabled: t.disabled ?? 0
      }))
    } catch {
      toolOptions.value = []
    } finally {
      _toolInFlight = null
    }
  })()
  return _toolInFlight
}

/** 工具名 → 中文名（列表里展示用） */
const toolLabelMap = computed(() => {
  const m: Record<string, string> = {}
  toolOptions.value.forEach((t) => {
    if (t?.name) m[t.name] = t.label || t.name
  })
  return m
})

/* ---------- 表单 ---------- */
const formVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const form = reactive<AgentConfigInput>({
  name: '',
  description: '',
  greeting: '',
  personaPrompt: '',
  tools: [],
  model: ''
})

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', description: '', greeting: '', personaPrompt: '', tools: [], model: '' })
  formVisible.value = true
}

function openEdit(a: AgentConfig) {
  editingId.value = a.agentId
  Object.assign(form, {
    name: a.name,
    description: a.description || '',
    greeting: a.greeting || '',
    personaPrompt: a.personaPrompt || '',
    tools: [...(a.tools || [])],
    model: a.model || ''
  })
  formVisible.value = true
}

async function save() {
  if (!form.name || !form.name.trim()) {
    ElMessage.warning('请填写智能体名称')
    return
  }
  saving.value = true
  try {
    const body: AgentConfigInput = {
      name: form.name.trim(),
      description: form.description || '',
      greeting: form.greeting || '',
      personaPrompt: form.personaPrompt || '',
      tools: form.tools || [],
      model: form.model || ''
    }
    if (editingId.value == null) {
      await createAgentConfig(body)
      ElMessage.success('智能体已创建')
    } else {
      await updateAgentConfig(editingId.value, body)
      ElMessage.success('智能体已更新')
    }
    formVisible.value = false
    await loadList()
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function remove(a: AgentConfig) {
  try {
    await ElMessageBox.confirm(`确定删除智能体「${a.name}」吗？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAgentConfig(a.agentId)
    ElMessage.success('已删除')
    await loadList()
    emit('changed')
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

/* ---------- 打开时加载 ---------- */
watch(visible, (v) => {
  if (v) {
    loadList()
    loadToolOptions()
  }
})
</script>

<style scoped lang="scss">
.agent-mgr-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 52vh;
  overflow-y: auto;
}

.agent-mgr-empty {
  padding: 24px 8px;
  text-align: center;
  font-size: 13px;
  line-height: 1.7;
  color: var(--os-text-4, #9ca3af);
}

.agent-mgr-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  border-radius: var(--os-radius-sm, 8px);
}

.agent-mgr-main {
  flex: 1;
  min-width: 0;
}

.agent-mgr-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
}

.agent-mgr-desc {
  margin-top: 3px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--os-text-3, #6b7280);
}

.agent-mgr-tools {
  margin-top: 5px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--os-text-4, #9ca3af);
}

.agent-mgr-ops {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}

.agent-form-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 12px;
  padding: 8px 10px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--os-text-3, #6b7280);
  background: var(--os-bg-hover, rgba(0, 0, 0, 0.03));
  border-radius: var(--os-radius-sm, 6px);
}
</style>
