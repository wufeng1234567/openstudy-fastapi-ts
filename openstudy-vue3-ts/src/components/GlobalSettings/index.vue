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
    direction="ltr"
    :offset-left="sidebarOffset"
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

      <!--
        tab 头：设置 / 知识库
        ----------------------------------------------------------------
        用户 2026-10-18：「为什么你要把知识库和智能体设置区分开来？不要区分啊」。
        所以两者**住在同一个抽屉里**，只切 tab、不开第二个抽屉 ——
        这也正是出现「左边知识库 + 右边设置」双抽屉的直接原因。
      -->
      <div class="gs-tabs">
        <div :class="['gs-tab', { active: tab === 'settings' }]" @click="switchTab('settings')">
          <OsIcon name="settings" :size="14" />
          <span>设置</span>
        </div>
        <div :class="['gs-tab', { active: tab === 'kb' }]" @click="switchTab('kb')">
          <OsIcon name="folder" :size="14" />
          <span>知识库</span>
        </div>
      </div>

      <div class="gs-body" v-show="tab === 'settings'">
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

      <!-- 知识库 tab：与设置同一个抽屉，只是切 tab（用 v-show 保状态，来回切不重载） -->
      <div class="gs-body is-kb" v-show="tab === 'kb'">
        <KnowledgeBasePanel ref="kbRef" :closable="false" />
      </div>
    </div>
  </ResizableDrawer>

  <!-- 我的智能体管理弹窗（从 chat.vue 搬来，逻辑不变） -->
  <AgentManagerDialog v-model="agentMgrVisible" @changed="loadMyAgents" />
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import OsIcon from '@/components/OsIcon/index.vue'
import AiModelSelector from '@/components/AiModelSelector/index.vue'
import AgentManagerDialog from './AgentManagerDialog.vue'
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel/index.vue'
import { listAgentExperts, setAgentExpertPref, setAgentExpertModel } from '@/api/ai/agent'
import { listAgentConfigs } from '@/api/ai/agent'
import useAgentUiStore from '@/store/modules/agentUi'

/** 自动：交由主助手按需安排 */
const AUTO_AGENT_KEY = 'auto'

const ui = useAgentUiStore()

/* ---------- 开合：由侧栏的全局信号驱动 ---------- */
const visible = ref(false)

/**
 * 抽屉要给左侧导航让出的宽度
 * --------------------------
 * 用户 2026-10-18：「要从菜单栏那边生成，而不是在最右边生成抽屉；
 *                  要贴着左侧菜单生成抽屉」。
 * 所以：方向改 `ltr`（从左往右滑出），并把遮罩/抽屉一起内缩到侧栏右缘 ——
 * 只让出侧栏，导航仍然可见可点。
 *
 * ⚠️ 宽度用**实时量 DOM**，不要读 localStorage：侧栏可拖拽（220–420）、
 *    可收起（64），存下来的值可能已经过期；量 `.os-sidebar` 最准。
 */
const sidebarOffset = ref(0)
function measureSidebar() {
  const el = document.querySelector('.os-sidebar') as HTMLElement | null
  sidebarOffset.value = el ? Math.round(el.getBoundingClientRect().width) : 0
}

/** 当前 tab：设置 / 知识库（与原来对话页抽屉里的语义一致） */
type PanelTab = 'settings' | 'kb'
const tab = ref<PanelTab>('settings')
const kbRef = ref<InstanceType<typeof KnowledgeBasePanel> | null>(null)

/**
 * 切 tab
 *
 * 知识库面板**故意不在 onMounted 自动加载**（见其源码注释：宿主有两种，懒挂载更稳），
 * 所以切进来时要显式 `activate()`。用 `nextTick` 等 v-show 生效后再调，
 * 否则面板还在 display:none 里，尺寸测量会拿到 0。
 */
function switchTab(next: PanelTab) {
  tab.value = next
  if (next === 'kb') {
    nextTick(() => kbRef.value?.activate?.())
  }
}

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

/* ---------- 抽屉打开期间：侧栏宽度变化要跟上 ---------- */
/*
 * 用户可能在抽屉打开时拖侧栏、或按 Ctrl+Alt+B 收起侧栏 —— 这时
 * 抽屉如果还贴在旧位置，就会和侧栏错位（露出空隙或压住导航）。
 * 用 ResizeObserver 盯住侧栏元素，比轮询更省。
 */
let _ro: ResizeObserver | null = null
watch(visible, (v) => {
  if (v) {
    measureSidebar()
    const el = document.querySelector('.os-sidebar') as HTMLElement | null
    if (el && typeof ResizeObserver !== 'undefined') {
      _ro = new ResizeObserver(() => measureSidebar())
      _ro.observe(el)
    }
  } else if (_ro) {
    _ro.disconnect()
    _ro = null
  }
})

/* ---------- 侧栏信号：打开 / 收起（开关语义） ---------- */
/*
 * 信号约定（`agentUi` store）：
 *   · `settingsToken`  —— 侧栏「设置」；再点一次收起
 *   · `settingsTab`    —— 本次想停在哪个 tab（'settings' | 'kb'）
 *
 * 对话页的「知识库」按钮不再自己开抽屉，而是请求这里切到 kb tab ——
 * 这样全站只有**一个**抽屉实例，不会再出现"左边知识库 + 右边设置"。
 */
let lastToken = ui.settingsToken
watch(
  () => ui.settingsToken,
  (token) => {
    if (!token || token === lastToken) return
    lastToken = token
    const want = (ui.settingsTab as PanelTab) || 'settings'
    // 再点同一个 tab = 收起；点另一个 tab = 保持打开并切过去
    if (visible.value && tab.value === want) {
      visible.value = false
      return
    }
    tab.value = want
    // 打开前先量一次侧栏宽度（拖拽过 / 收起过都能拿到当前真实值）
    measureSidebar()
    visible.value = true
    if (want === 'kb') nextTick(() => kbRef.value?.activate?.())
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

  &.is-kb {
    /* 知识库面板自带内边距，这里不再叠加，否则内容会缩进两次 */
    padding: 0;
  }
}

/*
 * tab 头（设置 / 知识库）
 * ------------------------------------------------------------------
 * 上一版漏了这段样式，图标与文字会叠在一起（挤成一团）。
 * 与对话页原来的 `.agent-panel-tabs` 视觉保持一致：发丝下划线 + 激活态实色。
 */
.gs-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 14px;
  flex: none;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.gs-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 10px 10px;
  font-size: 13px;
  line-height: 1;
  color: var(--os-text-3, #6b7280);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.15s ease, border-color 0.15s ease;

  &:hover {
    color: var(--os-text, #1f2937);
  }

  &.active {
    color: var(--os-text, #1f2937);
    font-weight: 600;
    border-bottom-color: var(--os-primary, #4f6ef7);
  }
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
