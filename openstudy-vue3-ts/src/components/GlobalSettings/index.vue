<!--
  全局设置抽屉
  ============================================================================
  用户 2026-10-18 两条反馈，指向同一个设计错误：

    ① 「设置面板和智能会话目前是绑定在一起的。当我进入题库练习页面，然后点设置按钮，
        此时会自动跳转到智能会话页面，这是不合理的。设置按钮应该作为一个全局设置对象
        处理，在哪里点击就在那个页面展开。」

    ② 「进入我的学习任一子 tab 后，第一次点设置能弹出抽屉，点取消（关闭）后再点设置，
        此时会出现两个设置抽屉，并且跳转到会话窗口。」

  根因：设置面板原先**住在 `chat.vue` 里**（作为对话页的一个 panel tab）。
        所以侧栏点「设置」只能先 `router.push('/front/agent/chat')` 把人送过去，
        再发 token 让对话页打开抽屉 —— 于是任何页面点设置都会被"拽"到对话页。
        叠加 keep-alive 复用时，对话页被反复激活 → 出现两个抽屉。

  现在的做法：把设置**提成全局组件**，挂在应用外壳（`layout/front.vue`）上，
  与对话页彻底解耦。侧栏只负责「打开」，不再做任何路由跳转。

  内容包含三块（与原来对话页里的一致）：
    · 我的智能体（选择 + 管理弹窗）
    · 模型（AiModelSelector，本组件自带数据加载）
    · 专家（开关 + 每个专家的模型）

  ⚠️ 与对话页的耦合点：「正在生成时禁止改设置」。
     原来靠 chat.vue 的 `isGenerating`；现在改由 `useAgentChat` 暴露的全局状态判断，
     拿不到就当作"没在生成"（宁可允许改，也不要错误禁用）。
-->
<template>
  <ResizableDrawer
    v-model="visible"
    direction="rtl"
    :offset-left="offsetLeft"
    storage-key="openstudy_global_settings_size"
    :default-width="380"
    :min="320"
    :max="720"
  >
    <div class="gs-panel">
      <div class="gs-head">
        <h3 class="gs-title">设置</h3>
        <button type="button" class="gs-close" title="关闭" @click="visible = false">
          <OsIcon name="close" :size="15" />
        </button>
      </div>

      <div class="gs-body">
        <!-- ① 我的智能体 -->
        <section class="gs-row">
          <div class="gs-label-row">
            <span class="gs-label">我的智能体</span>
            <el-button text type="primary" size="small" @click="agentMgrVisible = true">
              管理（新建 / 编辑 / 删除）
            </el-button>
          </div>
          <div class="gs-field">
            <el-select v-if="myAgents.length" v-model="selectedAgentKey" size="default" style="width: 100%">
              <el-option label="自动（由主助手按需安排）" :value="AUTO_AGENT_KEY" />
              <el-option v-for="a in myAgents" :key="'a-' + a.agentId" :label="a.name" :value="'user:' + a.agentId" />
            </el-select>
            <div class="gs-hint" v-if="myAgents.length">
              「自动」= 由主助手按需安排；也可指定你创建的某个智能体来对话。
            </div>
            <div class="gs-hint" v-else>
              还没有自定义智能体。点上方「管理」新建一个（可设人设、限定工具、绑定模型）。
            </div>
          </div>
        </section>

        <!-- ② 模型 -->
        <section class="gs-row">
          <div class="gs-label">模型</div>
          <div class="gs-field">
            <AiModelSelector v-model="model" scene="agent" width="100%" @select="onModelSelect" />
          </div>
        </section>

        <!-- ③ 专家 -->
        <section class="gs-row">
          <div class="gs-label">专家</div>
          <div class="gs-field">
            <div v-if="expertLoading" class="gs-hint">正在读取专家…</div>
            <div v-else-if="expertLoadFailed" class="gs-error">
              <span>专家列表没取到</span>
              <el-button text type="primary" size="small" @click="loadExperts">重试</el-button>
            </div>
            <div v-else class="gs-tools">
              <div v-for="e in experts" :key="e.key" class="gs-tool">
                <div class="gs-tool-main">
                  <span class="gs-tool-name">{{ e.name }}</span>
                  <span class="gs-tool-desc">{{ e.description }}</span>
                  <AiModelSelector
                    :model-value="e.model || ''"
                    scene="agent-expert"
                    width="100%"
                    :auto-default="false"
                    class="gs-tool-model"
                    @update:model-value="(v) => onExpertModelChange(e, v)"
                  />
                </div>
                <el-switch
                  :model-value="e.disabled !== 1"
                  size="small"
                  :loading="expertTogglingKey === e.key"
                  @update:model-value="toggleExpert(e, $event)"
                />
              </div>
            </div>
            <div class="gs-hint">
              开启的专家，主助手会在需要时自动请它来帮忙；关掉就完全不用它。
            </div>
          </div>
        </section>
      </div>
    </div>
  </ResizableDrawer>

  <!-- 我的智能体管理弹窗（从 chat.vue 搬来，逻辑不变） -->
  <AgentManagerDialog v-model="agentMgrVisible" @changed="loadMyAgents" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AgentManagerDialog from './AgentManagerDialog.vue'
import { listAgentExperts, setAgentExpertPref, setAgentExpertModel } from '@/api/ai/agent'
import { listAgentConfigs } from '@/api/ai/agent'
import useAgentUiStore from '@/store/modules/agentUi'

/** 自动：交由主助手按需安排 */
const AUTO_AGENT_KEY = 'auto'

const ui = useAgentUiStore()

/* ---------- 开合：由侧栏的全局信号驱动 ---------- */
const visible = ref(false)
/** 抽屉贴左时给侧栏让位（与外壳的侧栏宽度保持一致） */
const offsetLeft = ref(0)

/** 当前对话选中的智能体（与对话页共享同一个 localStorage，改完对话页立即生效） */
const SELECTED_AGENT_KEY = 'openstudy_selected_agent'
const selectedAgentKey = ref(localStorage.getItem(SELECTED_AGENT_KEY) || AUTO_AGENT_KEY)
watch(selectedAgentKey, (v) => {
  try {
    localStorage.setItem(SELECTED_AGENT_KEY, v)
  } catch {
    /* 隐私模式下忽略 */
  }
})

/** 模型：与对话页共享同一个 key（AiModelSelector 的 scene=agent 就是这个 key） */
const model = ref(localStorage.getItem('openstudy_ai_model_agent') || '')

const onModelSelect = (_id: any, _label?: string, value?: string) => {
  if (value !== undefined) model.value = value
}

/* ---------- 我的智能体 ---------- */
const myAgents = ref<any[]>([])

async function loadMyAgents() {
  try {
    const list = await listAgentConfigs()
    myAgents.value = ((list as any) || []).filter((a: any) => a.enabled !== 0)
  } catch {
    myAgents.value = []
  }
}

/* ---------- 专家 ---------- */
const experts = ref<any[]>([])
const expertLoading = ref(false)
const expertLoadFailed = ref(false)
const expertTogglingKey = ref('')
let _expertInFlight: Promise<void> | null = null

async function loadExperts(force = false) {
  // 飞行锁：打开抽屉 / 点重试 可能同时触发，只发一次
  if (_expertInFlight && !force) return _expertInFlight
  expertLoading.value = true
  expertLoadFailed.value = false
  _expertInFlight = (async () => {
    try {
      const list = await listAgentExperts()
      if (Array.isArray(list)) experts.value = list
      // 取到了但一条都没有 → 也视为失败（否则界面空白无从判断）
      expertLoadFailed.value = experts.value.length === 0
    } catch {
      expertLoadFailed.value = true
    } finally {
      expertLoading.value = false
      _expertInFlight = null
    }
  })()
  return _expertInFlight
}

async function toggleExpert(e: any, on: boolean) {
  expertTogglingKey.value = e.key
  const prev = e.disabled
  e.disabled = on ? 0 : 1
  try {
    // 官方签名是 setAgentExpertPref(expert, disabled)，第一个参数是专家 key
    const list = await setAgentExpertPref(e.key, on ? 0 : 1)
    if (Array.isArray(list)) experts.value = list
  } catch {
    e.disabled = prev // 回滚，避免界面与后端不一致
    ElMessage.error('保存失败，请重试')
  } finally {
    expertTogglingKey.value = ''
  }
}

async function onExpertModelChange(e: any, m: string) {
  const prev = e.model
  e.model = m
  try {
    const list = await setAgentExpertModel(e.key, m)
    if (Array.isArray(list)) experts.value = list
  } catch {
    e.model = prev
    ElMessage.error('模型保存失败')
  }
}

/* ---------- 管理弹窗 ---------- */
const agentMgrVisible = ref(false)

/* ---------- 首次打开时加载数据 ---------- */
let loadedOnce = false
watch(visible, (v) => {
  if (!v) return
  if (!loadedOnce) {
    loadedOnce = true
    loadMyAgents()
    loadExperts()
  }
})

/* ---------- 侧栏信号：打开 / 收起（开关语义） ---------- */
let lastToken = ui.settingsToken
watch(
  () => ui.settingsToken,
  (token) => {
    if (!token || token === lastToken) return
    lastToken = token
    // 再点一次 = 收起（与原来对话页的行为一致，符合"开关"直觉）
    visible.value = !visible.value
    if (visible.value) {
      // 侧栏宽度：外壳把它写在 CSS 变量上，这里读回来给抽屉让位
      const w = getComputedStyle(document.documentElement).getPropertyValue('--os-sidebar-w').trim()
      offsetLeft.value = Number(w.replace('px', '')) || 0
    }
  }
)
</script>

<style scoped lang="scss">
.gs-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.gs-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px 10px;
  flex: none;
}

.gs-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
}

.gs-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: var(--os-radius-sm, 6px);
  background: transparent;
  color: var(--os-text-3, #6b7280);
  cursor: pointer;

  &:hover {
    background: var(--os-bg-hover, rgba(0, 0, 0, 0.04));
    color: var(--os-text, #1f2937);
  }
}

.gs-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 18px 24px;
}

.gs-row {
  padding: 14px 0;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.05));

  &:last-child {
    border-bottom: 0;
  }
}

.gs-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.gs-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
}

.gs-field {
  margin-top: 8px;
}

.gs-hint {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--os-text-4, #9ca3af);
}

.gs-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--el-color-danger, #f56c6c);
}

.gs-tools {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.gs-tool {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
  border-radius: var(--os-radius-sm, 8px);
}

.gs-tool-main {
  flex: 1;
  min-width: 0;
}

.gs-tool-name {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--os-text, #1f2937);
}

.gs-tool-desc {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--os-text-3, #6b7280);
}

.gs-tool-model {
  margin-top: 8px;
}
</style>
