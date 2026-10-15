<!-- components/KnowledgeBaseDrawer/index.vue -->
<!--
  知识库（嵌在智能体页面里）

  为什么做成「输入栏按钮 + 抽屉」而不是独立页面：
    · 知识库是**给这次提问用的资料**，入口就该在「发消息」的地方 ——
      用户传完资料马上能问，不用跳页面、跳回来、再找会话；
    · 抽屉不占布局，与页面既有的历史会话侧栏（左侧）分工清楚：
      左边是「聊过什么」，右边是「手上有什么资料」。

  ⚠️ 本组件只是**外壳**（入口按钮 + el-drawer）。真正的内容在
     KnowledgeBasePanel 里 —— 悬浮助手的「我的知识库」tab 用的是同一个面板，
     两处功能完全一致，实现只有一份。改功能请改面板，不要改这里。
-->
<template>
  <button class="kb-entry" :title="kbTitle" @click.stop="open">
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
    <span v-if="kbCount" class="kb-entry-badge">{{ kbCount }}</span>
  </button>

  <!-- 可拖拽调宽的通用抽屉容器（公共组件 ResizableDrawer）
       ⚠️ 方向 = **左侧**（ltr）：入口按钮在底部工具栏左侧，按「入口在哪、面板就从哪滑出」的
       一致性原则，与历史会话抽屉同侧（用户 2026-10-10 裁决）。 -->
  <ResizableDrawer
    v-model="visible"
    direction="ltr"
    storage-key="openstudy_kb_drawer_size"
    :default-width="560"
    @open="onOpen"
  >
    <KnowledgeBasePanel ref="panelRef" closable @close="visible = false" />
  </ResizableDrawer>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import KnowledgeBasePanel from '@/components/KnowledgeBasePanel/index.vue'
import ResizableDrawer from '@/components/ResizableDrawer/index.vue'
import { listKnowledgeBases } from '@/api/ai/rag'

const visible = ref(false)
const panelRef = ref<InstanceType<typeof KnowledgeBasePanel> | null>(null)

/** 入口徽标上的数字 */
const kbCount = ref(0)
const kbTitle = ref('知识库 —— 传资料，让智能体检索后回答')

/** 打开抽屉：让面板载入（每次都回到库列表） */
const onOpen = async () => {
  await nextTick()
  await panelRef.value?.activate()
  syncBadge()
}

const open = () => {
  visible.value = true
}

/** 从面板读回库数量，刷新入口徽标 */
const syncBadge = () => {
  const n = panelRef.value?.getKbCount() ?? 0
  kbCount.value = n
  kbTitle.value = n ? `知识库（${n} 个）—— 传资料、让智能体自己检索` : '知识库 —— 传资料，让智能体检索后回答'
}

onMounted(async () => {
  try {
    const res: any = await listKnowledgeBases()
    if (res?.code === 200 && Array.isArray(res.data)) {
      kbCount.value = res.data.length
      kbTitle.value = res.data.length
        ? `知识库（${res.data.length} 个）—— 传资料、让智能体自己检索`
        : '知识库 —— 传资料，让智能体检索后回答'
    }
  } catch (e) {
    console.warn('[kb] 入口徽标取数失败', e)
  }
})

defineExpose({ open })
</script>

<style scoped>
.kb-entry {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  padding: 0;
}

.kb-entry:hover {
  background: #fff;
  border-color: #e5e7eb;
  color: #1f2937;
}

.kb-entry-badge {
  position: absolute;
  top: -3px;
  right: -3px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  background: #4f6ef7;
  color: #fff;
  font-size: 9px;
  line-height: 14px;
  text-align: center;
  font-weight: 600;
}
</style>
