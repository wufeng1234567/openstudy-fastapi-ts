<!--
  笔记管理（分组壳）
  ============================================================================
  用户 2026-10-18：「给我的笔记同样的修改 —— 笔记管理，其中包含用户自己的笔记
  以及收藏的笔记」。

  与「题库管理」「题目管理」同一套做法：
    · 一个页面 + 顶部分组切换（我的笔记 / 收藏的笔记）
    · 不再在侧栏放两个入口

  ## 为什么复用原页面组件而不是重写

  `myNotes`（745 行）与 `myFavoriteNote`（282 行）是两套完全独立的实现：
  前者用 `PageHeader` + `CommonFilterSidebar` + 分页，有筛选/搜索/删除全部/写笔记；
  后者是手写的卡片列表 + 简单分页。业务逻辑一行没重叠。

  所以这里只做「壳」：两个原页面 `v-show` 常驻，切分组瞬时。
  `myNotes` 传 `embedded` 让它不渲染自己的标题（外层有分组切换）；
  `myFavoriteNote` 本来就没有标题，不用改。

  ## 计数

  `myNotes` 自己用 `PageHeader` 显示「N 篇笔记」，这里额外把条数推到顶栏，
  与「题库管理」「题目管理」保持一致（顶栏一行：`我的学习 · 笔记管理  N 篇笔记`）。
-->
<template>
  <div class="note-manage-page">
    <!-- 分组切换 -->
    <div class="tab-switch">
      <button v-for="t in tabs" :key="t.key" type="button" :class="['tab-btn', { active: activeTab === t.key }]"
        @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- 我的笔记 -->
    <div v-show="activeTab === 'own'" class="tab-panel">
      <MyNotes ref="ownRef" embedded @total-change="onTotalChange('own', $event)" />
    </div>

    <!-- 收藏的笔记 -->
    <div v-show="activeTab === 'favorite'" class="tab-panel">
      <MyFavoriteNote ref="favRef" @total-change="onTotalChange('favorite', $event)" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontNoteManage' })

import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MyNotes from '../myNotes/index.vue'
import MyFavoriteNote from '../myFavoriteNote/index.vue'
import useTopbarStore from '@/store/modules/topbar'

type TabKey = 'own' | 'favorite'

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'own', label: '我的笔记' },
  { key: 'favorite', label: '收藏的笔记' }
]

const route = useRoute()

/**
 * 初始分组：支持 `?tab=favorite`
 *
 * 旧路由 `/front/myQuestion/favoriteNote` 会重定向到
 * `noteManage?tab=favorite`，所以进页面时要认这个参数。
 */
const initTab = (): TabKey => (String(route.query.tab || '') === 'favorite' ? 'favorite' : 'own')
const activeTab = ref<TabKey>(initTab())

/* 侧栏在同一页内切 ?tab= 时跟上 */
watch(
  () => route.query.tab,
  (t) => {
    activeTab.value = String(t || '') === 'favorite' ? 'favorite' : 'own'
  }
)

/* ---------- 顶栏计数 ---------- */
const ownRef = ref<any>(null)
const favRef = ref<any>(null)
const topbarStore = useTopbarStore()

const counts = ref<Record<TabKey, number>>({ own: 0, favorite: 0 })

function onTotalChange(key: TabKey, n: number) {
  counts.value[key] = Number(n) || 0
}

watch(
  [activeTab, () => counts.value.own, () => counts.value.favorite],
  () => {
    const n = counts.value[activeTab.value] || 0
    topbarStore.setCount(n ? `${n} 篇笔记` : '')
  },
  { immediate: true }
)

onBeforeUnmount(() => topbarStore.clear())
</script>

<style scoped lang="scss">
.note-manage-page {
  padding: 0;
}

/* 分组切换：与「题库管理」「题目管理」完全一致（下划线 + 无边框按钮） */
.tab-switch {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--os-border-soft, rgba(0, 0, 0, 0.06));
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px 10px;
  border: 0;
  background: transparent;
  font-size: 13.5px;
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

.tab-panel {
  min-height: 0;
}
</style>
