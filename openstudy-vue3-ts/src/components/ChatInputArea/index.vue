<!-- components/ChatInputArea/index.vue -->
<!--
  对话输入区（底部组件）

  结构参考 sp3（`apps/springboot3/.../ChatInputArea`），**样式沿用 v2**（配色/圆角/描边与改造前一致），
  并保留 v2 自己的功能优点：
    · 类名与改造前保持一致（`.chat-input-area` / `.input-box` / `.input-header` / `.input-bottom` / `.send-btn`）
      —— 大屏智能体页 `views/front/agent/chat.vue` 里对这几个类的 `:deep()` 覆盖**不用改**就能继续生效。
    · 附件走插槽（`#attachments`），继续由上层用 `ChatAttachmentList` / `ChatFileUploader` 渲染，
      不在这里重造「解析 Word/PDF」那套逻辑。

  与 sp3 的取舍：
    ✅ 搬过来：模式切换卡片（`@` 按钮展开）、textarea 两行起步 + 自动增高、输入/工具行之间的分隔线、放大输入对话框。
       （放大对话入口在 v2 里从**底部工具栏**移到了**输入框右上角角标**，见 `.expand-corner`。）
    ❌ 没搬：模式文字标签（`@` 旁边不挂字 —— 当前模式由抽屉左上角标题实时体现，见 `AiAssistant` 的 `headerTitle`）、
       自带的文件解析预览（v2 用插槽，能力更全）。
    ➕ 自建：「新建会话」按钮（`showNewSession`），放在附件上传右边，由上层决定是否显示。
    ➕ 知识库入口**不在这里**：由上层通过 `#toolbar-extra` 插槽传进来（智能体页传的是
       `KnowledgeBaseDrawer`）。知识库要跟用户/权限绑定、还要管文档，放在这个纯展示组件里
       会把它撑成半个业务组件 —— 现在这样，聊天助手与智能体页可以各自决定要不要给入口。
       （早期这里写着「v2 后端还没有检索能力，先不给入口」，backend 现在有了，
        入口也已经接上，那条注释是过期的。）
-->
<template>
  <div class="chat-input-area">
    <!-- 模式切换卡片：点工具栏的「@」展开（sp3 的交互） -->
    <transition name="mode-card">
      <div v-if="modeCardVisible" class="mode-card-popup">
        <div class="mode-card-title">对话配置</div>
        <div :class="['mode-option', { active: mode === 'agent' }]" @click="chooseMode('agent')">
          <div class="mode-option-name">智能体模式</div>
          <div class="mode-option-desc">可调用工具：建题库、导题、改题、删除；自动开启深度思考</div>
        </div>
        <div :class="['mode-option', { active: mode === 'chat' }]" @click="chooseMode('chat')">
          <div class="mode-option-name">聊天模式</div>
          <div class="mode-option-desc">纯对话、响应更快（不开启深度思考）</div>
        </div>
      </div>
    </transition>

    <div class="input-box">
      <!-- 附件预览：沿用 v2「贴在输入框上方」的排布（对齐 DS 网页端） -->
      <div v-if="$slots.attachments" class="input-header">
        <slot name="attachments"></slot>
      </div>

      <!-- 输入层：两行起步，随内容长高（上限 120px 后滚动）
           「放大输入」入口从底部工具栏**上移到本层右上角**（用户 2026-10-10 裁决）：
           它属低频动作，不该与 @ / 附件 / 新建会话等高频按钮并列占位；
           作为输入框内角标既不挤工具栏，又保留了长文本输入的便利。 -->
      <div class="input-text-layer">
        <textarea ref="textareaRef" v-model="text" class="chat-textarea" rows="2" :placeholder="placeholder"
          :disabled="disabled" @keydown="onKeydown"></textarea>
        <button type="button" class="expand-corner" title="放大输入（写长文本更舒服）"
          @click.stop="expandVisible = true">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 3 21 3 21 9" />
            <polyline points="9 21 3 21 3 15" />
            <line x1="21" y1="3" x2="14" y2="10" />
            <line x1="3" y1="21" x2="10" y2="14" />
          </svg>
        </button>
      </div>

      <!-- 分隔线：把「写什么」和「怎么发」分开 -->
      <div class="input-divider"></div>

      <!-- 工具栏 -->
      <div class="input-bottom">
        <div class="input-bottom-left">
          <!--
            `@` 只作为「模式切换入口」，**不再在旁边挂模式文字标签**：
            当前模式由抽屉左上角的标题实时体现（`OpenStudy-Agent` / `OpenStudy-Chat`，对齐 sp3 的头部做法），
            工具栏这一层保持安静。悬停 `@` 仍能通过 title 看到当前模式。
          -->
          <button v-if="showModeSwitch" class="toolbar-btn at-btn" :disabled="disabled"
            :title="disabled ? '生成中，暂不能切换模式' : `当前：${modeLabel}，点击切换`"
            @click.stop="toggleModeCard">@</button>

          <slot name="toolbar-extra"></slot>

          <!-- 新建会话：紧挨着附件上传（都是「会话级」动作，放一起） -->
          <button v-if="showNewSession" class="toolbar-btn new-session-btn" title="新建会话"
            @click="$emit('new-session')">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 5v14M5 12h14" />
            </svg>
          </button>
        </div>

        <div class="input-bottom-right">
          <slot name="toolbar-right-before"></slot>
          <button v-if="generating" class="send-btn stop-btn" title="停止生成" @click="$emit('toggle-pause')">
            <svg v-if="!paused" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <rect x="6" y="5" width="4" height="14" rx="1" />
              <rect x="14" y="5" width="4" height="14" rx="1" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </button>
          <button v-else class="send-btn" :disabled="!canSend" @click="onSend">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 放大输入：长文本（贴文档 / 大段题干）写起来舒服些 -->
    <el-dialog v-model="expandVisible" title="输入内容" width="620px" append-to-body class="chat-input-expand"
      :close-on-click-modal="false">
      <textarea v-model="text" class="expand-textarea" rows="10" :placeholder="placeholder"
        @keydown.enter.exact.prevent="onSendFromDialog"></textarea>
      <template #footer>
        <el-button @click="expandVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!canSend" @click="onSendFromDialog">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

/** 输入行高上限：超过就内部滚动（与改造前 `.el-textarea__inner` 的 max-height 一致） */
const TEXTAREA_MAX_HEIGHT = 120

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    /** 'agent'=智能体模式（可调工具、开深度思考）；'chat'=纯聊天（关深度思考） */
    mode?: 'agent' | 'chat'
    /** 是否显示模式切换（`@` 按钮 + 模式卡片）。大屏智能体页固定智能体模式，可关掉 */
    showModeSwitch?: boolean
    /** 是否显示「新建会话」按钮（放在附件上传右边，由上层决定要不要） */
    showNewSession?: boolean
    generating?: boolean
    paused?: boolean
    disabled?: boolean
    /** 有附件时即使输入框为空也允许发送（对齐 DS 网页端） */
    hasAttachment?: boolean
  }>(),
  {
    modelValue: '',
    placeholder: '输入消息...（Enter 发送，Ctrl+Enter 换行）',
    mode: 'agent',
    showModeSwitch: true,
    showNewSession: false,
    generating: false,
    paused: false,
    disabled: false,
    hasAttachment: false
  }
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'update:mode', value: 'agent' | 'chat'): void
  (e: 'send', payload: { content: string }): void
  (e: 'toggle-pause'): void
  (e: 'new-session'): void
}>()

const textareaRef = ref<HTMLTextAreaElement | null>(null)
const modeCardVisible = ref(false)
const expandVisible = ref(false)

/** 输入内容（受控：对外仍是 v-model） */
const text = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value)
})

const modeLabel = computed(() => (props.mode === 'agent' ? '智能体' : '聊天'))
const canSend = computed(() => !props.disabled && !props.generating && (!!props.modelValue.trim() || props.hasAttachment))

/** 两行起步 + 自动增高（先置 auto 再读 scrollHeight，才能正确收缩） */
const autoGrow = () => {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, TEXTAREA_MAX_HEIGHT) + 'px'
}

const onKeydown = (e: KeyboardEvent) => {
  // Enter 发送；Shift/Ctrl/⌘ + Enter 换行
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.isComposing) {
    e.preventDefault()
    onSend()
  }
}

const onSend = () => {
  if (!canSend.value) return
  emit('send', { content: props.modelValue.trim() })
  // 与改造前一致：发出后立即清空（清空动作放在这里，因为输入内容由本组件持有）
  emit('update:modelValue', '')
  nextTick(autoGrow)
}

const onSendFromDialog = () => {
  if (!canSend.value) return
  onSend()
  expandVisible.value = false
}

const chooseMode = (mode: 'agent' | 'chat') => {
  if (mode !== props.mode) emit('update:mode', mode)
  modeCardVisible.value = false
}

const toggleModeCard = () => {
  modeCardVisible.value = !modeCardVisible.value
}

/** 点空白处关掉模式卡片（只在卡片开着时挂监听，避免常驻） */
const onDocumentClick = (e: MouseEvent) => {
  const target = e.target as HTMLElement | null
  if (target && target.closest('.mode-card-popup')) return
  if (target && target.closest('.at-btn')) return
  modeCardVisible.value = false
}

watch(modeCardVisible, (open) => {
  if (open) document.addEventListener('click', onDocumentClick)
  else document.removeEventListener('click', onDocumentClick)
})

watch(() => props.modelValue, () => nextTick(autoGrow))

onMounted(() => nextTick(autoGrow))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))
</script>

<style scoped>
/* ========== 容器 ==========
   外层只负责吸底与留白，真正的"卡片"是里面的 `.input-box`（DSH 的 composer 形态） */
.chat-input-area {
  position: relative;
  background-color: transparent;
  padding: 6px 20px 18px;
  border-top: none;
  /*
   * ⚠️ `flex-shrink: 0` 不能删：本组件是消息列表（`.chat-messages`）的**兄弟节点**、
   * 同处一个 flex 列（`.ai-chat-stream`）。默认 `flex-shrink: 1` 时，消息一多它就会被压缩，
   * 输入框跟着变矮甚至被消息区挤没 ——「吸底」要求它在布局上永远不被挤压。
   * 它仍留在正常文档流里（**不要**改成 `position: fixed/absolute`：那要手算偏移，
   * 侧栏折叠 / 窄屏 / 顶栏高度一变就错位；「悬浮」是视觉上的，用背景/圆角/阴影做）。
   */
  flex-shrink: 0;
}

.input-box {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
  box-sizing: border-box;
  background: #fff;
  border: 1px solid var(--os-border);
  border-radius: 20px;
  padding: 12px 14px 8px;
  box-shadow: none;
  /*
   * 只列**状态里真会变**的属性：`:hover` / `:focus-within` 的 border-color。
   * ⚠️ 不要写回 `transition: all`：`all` 会把将来任何人在状态里加的**布局属性**也一起动画化，
   *    那是逐帧重排，正是「点一下卡一下」的来源。
   */
  transition: border-color 0.2s var(--ds-ease-in-out);
  min-height: 0;

  &:hover {
    border-color: var(--os-border-strong);
  }

  /*
   * 聚焦：DSH 的 composer 只把描边压深一点，不画蓝色光圈 ——
   * 输入区本来就大，再来一圈高亮会抢走对话正文的注意力。
   */
  &:focus-within {
    border-color: var(--dsw-static-neutral-bluish-400);
  }
}

/* 输入框上方：待发送附件 */
.input-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

/* ========== 输入层 ========== */
.input-text-layer {
  display: flex;
  min-width: 0;
  /* 放大角标的定位基准 */
  position: relative;
}

/* 放大输入角标：**右上角**、浮于文本框之上、透明底、hover 才显色。
   ⚠️ 位置经过两次修正（2026-10-10）：
     ① 不能放右下角 —— 悬浮助手（`AiAssistant`）的浮动按钮默认就在页面右下角，
        两者会重叠、角标被遮住点不到；
     ② 不能贴 `right: 0` —— textarea 长文本时右侧出现滚动条，会正好压在角标上，
        hover 的背景块与滚动条视觉打架。故 `right` 留出滚动条宽度（约 8px），
        并给 textarea 右侧加 padding，让文字/滚动条都不侵入角标区。 */
.expand-corner {
  position: absolute;
  right: 8px;
  top: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--os-text-4);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.expand-corner:hover {
  background: var(--os-bg-hover);
  color: var(--os-text-2);
}

.chat-textarea {
  width: 100%;
  min-height: 44px;
  max-height: 120px;
  /* 右侧留白：避开右上角的放大角标与滚动条，文字不顶到它们 */
  padding: 4px 30px 4px 2px;
  border: none;
  outline: none;
  background: transparent;
  color: var(--os-text);
  font-size: 14.5px;
  line-height: 1.6;
  font-family: inherit;
  resize: none;
  overflow-y: auto;
  box-sizing: border-box;

  &::placeholder {
    color: var(--os-text-4);
    font-size: 14px;
  }

  &:disabled {
    cursor: not-allowed;
  }
}

/* 分隔线：新 composer 不再用它（工具栏与正文直接留白分层，更接近 DSH） */
.input-divider {
  display: none;
}

/* ========== 工具行 ==========
   DSH 的 composer 底栏是「左：附件等轻量入口 / 右：模型名 + 发送」，一条水平线，无分隔线。 */
.input-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 2px;
  min-height: 34px;
}

.input-bottom-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

/* 右侧工具组：模型名 + 发送键。
   gap 8px —— 与左侧工具组保持一致；之前显得"间距太大"的真正原因是
   模型选择器根节点里那个只承载弹窗的 40px 空壳子（已在 AiModelSelector 里移除占位），
   不是这里的 gap。 */
.input-bottom-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: var(--os-radius-sm);
  background: transparent;
  color: var(--os-text-3);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  /*
   * 只列**状态里真会变**的属性：`:hover` 的 background / color、`:disabled` 的 opacity。
   * ⚠️ 不要写回 `transition: all`（同一个坑：将来往 hover 里加一个 padding/width，就变成静默的逐帧重排）。
   */
  transition: background-color 0.15s ease, color 0.15s ease, opacity 0.15s ease;
  flex-shrink: 0;

  &:hover {
    background: var(--os-bg-hover);
    color: var(--os-text);
  }

  /* 生成中会禁用 `@`（切模式要换消息列表，跑一半切会串台）→ 给个明确的不可点观感 */
  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;

    &:hover {
      background: transparent;
      color: var(--os-text-3);
    }
  }
}

.at-btn {
  font-size: 15px;
}

/* ========== 模式切换卡片 ========== */
.mode-card-popup {
  position: absolute;
  left: 16px;
  bottom: calc(100% + 6px);
  z-index: 20;
  width: 268px;
  padding: 8px;
  background: #fff;
  border: 1px solid var(--os-border-soft);
  border-radius: var(--os-radius);
  box-shadow: var(--os-shadow-2), 0 0 0 0.5px var(--os-border-soft);
}

.mode-card-title {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--os-text-4);
  padding: 4px 8px 6px;
}

.mode-option {
  padding: 8px 10px;
  border-radius: var(--os-radius-sm);
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: var(--os-bg-hover);
  }

  &.active {
    background: var(--os-accent-soft);

    .mode-option-name {
      color: var(--os-accent-strong);
    }
  }
}

.mode-option-name {
  font-size: 13px;
  font-weight: 600;
  color: #1f2d3d;
}

.mode-option-desc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
}

.mode-card-enter-active,
.mode-card-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.mode-card-enter-from,
.mode-card-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

/* ========== 发送 / 停止 ========== */
.send-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  border: none;
  background: var(--os-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  /*
   * 只列**状态里真会变**的属性：`:hover:not(:disabled)` 的 background / color、
   * `:active:not(:disabled)` 的 `transform: scale(0.95)`（scale 属于 transform，写 transform 一个就够）。
   * ⚠️ 不要写回 `transition: all`。
   */
  transition: background-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
  padding: 0;

  &:hover:not(:disabled) {
    background: var(--os-primary-hover);
  }

  &:active:not(:disabled) {
    transform: scale(0.95);
  }

  /*
   * 禁用态（还没输入内容）：**极淡的底 + 淡图标**。
   * 之前用 100 号灰（#ebeef2）铺满一个 32px 方块，在轻量工具行里显得很重，
   * 像"一个可点的灰按钮"。DSH 的做法是让它几乎融进背景，只在可用时才黑起来。
   */
  &:disabled {
    background: var(--dsw-static-neutral-bluish-75);
    color: var(--dsw-static-neutral-bluish-300);
    cursor: not-allowed;
  }
}

.stop-btn {
  background: var(--dsw-static-red-50);
  color: var(--os-danger);

  &:hover {
    background: var(--os-danger);
    color: #fff;
  }
}

/* ========== 放大输入弹窗 ========== */
.expand-textarea {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.6;
  font-family: inherit;
  color: #1f2d3d;
  resize: vertical;
  box-sizing: border-box;
  outline: none;

  &:focus {
    border-color: #b3b3b3;
  }
}
</style>
