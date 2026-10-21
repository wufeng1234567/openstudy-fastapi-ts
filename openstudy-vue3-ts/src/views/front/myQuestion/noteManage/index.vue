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
    <!-- 分组切换（与「题库管理 / 题目管理」共用一个组件） -->
    <SegmentedTabs v-model="activeTab" :tabs="tabItems" />

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

import { computed, onActivated, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MyNotes from '../myNotes/index.vue'
import MyFavoriteNote from '../myFavoriteNote/index.vue'
import SegmentedTabs from '@/components/SegmentedTabs/index.vue'
import useTopbarStore from '@/store/modules/topbar'

type TabKey = 'own' | 'favorite'

const TAB_DEFS: Array<{ key: TabKey; label: string }> = [
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
    /*
     * ⚠️ 必须确认「当前确实停在本页」。
     * 本页是 keep-alive 的，用户切到「题目管理」后本组件仍然存活；
     * 而「题目管理」用的也是 `?tab=` —— 不加路径判断，
     * 这里会被别人的 `?tab=favorite` 唤醒，把 activeTab 翻成「收藏的笔记」，
     * 并把「1 篇笔记」推到顶栏（实测：进题目管理看到「我的学习 · 题目管理  1 篇笔记」）。
     */
    if (!route.path.startsWith('/front/myQuestion/noteManage')) return
    activeTab.value = String(t || '') === 'favorite' ? 'favorite' : 'own'
  }
)

/* ---------- 顶栏计数 ---------- */
const ownRef = ref<any>(null)
const favRef = ref<any>(null)
const topbarStore = useTopbarStore()

const counts = ref<Record<TabKey, number>>({ own: 0, favorite: 0 })

/** 分组切换条的入参：标签 + 角标计数（数据没回来前不显示 0） */
const tabItems = computed(() =>
  TAB_DEFS.map((t) => ({ ...t, count: counts.value[t.key] || undefined }))
)

function onTotalChange(key: TabKey, n: number) {
  counts.value[key] = Number(n) || 0
}

watch(
  [activeTab, () => counts.value.own, () => counts.value.favorite],
  () => {
    // keep-alive 下本页可能已不在前台：不要往顶栏推别人的计数
    if (!route.path.startsWith('/front/myQuestion/noteManage')) return
    const n = counts.value[activeTab.value] || 0
    topbarStore.setCount(n ? `${n} 篇笔记` : '')
  },
  { immediate: true }
)

// 回到本页时重新推一次（离开期间顶栏被清空过）
onActivated(() => {
  const n = counts.value[activeTab.value] || 0
  topbarStore.setCount(n ? `${n} 篇笔记` : '')
})

onBeforeUnmount(() => topbarStore.clear())
</script>

<style scoped lang="scss">
.note-manage-page {
  padding: 0;
}
/* 分组切换条已抽到 `SegmentedTabs`（三个管理页共用一份样式），这里不再重复定义 */

.tab-panel {
  min-height: 0;
}
</style>
