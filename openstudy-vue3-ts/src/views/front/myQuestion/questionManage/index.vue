<!--
  题目管理（分组壳）
  ============================================================================
  用户 2026-10-18：「才用这个思路：三个 MyQuestion 实例用 v-show 常驻
  （切分组瞬时切换），各自传各自的 apiConfig —— 只需要一个带分组切换的壳」。

  ## 为什么是「壳 + 三个原页面」而不是「重写三个 apiConfig」

  这三个页面（题目收藏 / 我的错题 / 我的斩题）各自有 270+ 行：
  除了 `apiConfig` 的五个钩子（listApi / deleteApi / updateApi / detailApi /
  transformQuestion），还有 userId 兜底、状态过滤、字段补齐、
  `focusQuestionId` 定位等差异。把它们搬进一个新组件 =
  把三套业务逻辑硬塞一处，风险远大于收益。

  所以这里**直接复用原页面组件**（`myFavoriteQuestion` / `myMistakes` / `myMarked`），
  用 `embedded` 让它们不渲染自己的标题 —— 业务逻辑一行没动。

  ## 为什么用 v-show 而不是 v-if

  · `v-if`：每次切分组都要重新挂载 + 重新拉列表，有可见空白期；
  · `v-show`：首屏三份都加载好，之后切换是瞬时的（用户明确要求这个方案）。

  代价是首屏三个请求并发。这三个列表本来就是高频互相切换的，
  用一次首屏换掉之后的每次等待，划算。

  ## 计数

  各分组的条数由子页面自己的 `PageHeader` 显示；顶栏的「N 道题」这里不接管
  （三个页面各自管理自己的 total，硬抽出来反而要改它们的内部实现）。
-->
<template>
  <div class="question-manage-page">
    <!-- 分组切换 -->
    <div class="tab-switch">
      <button v-for="t in tabs" :key="t.key" type="button" :class="['tab-btn', { active: activeTab === t.key }]"
        @click="activeTab = t.key">
        {{ t.label }}
      </button>
    </div>

    <!-- 三个分组常驻（v-show：切换瞬时，不重新拉数据） -->
    <div v-show="activeTab === 'favorite'" class="tab-panel">
      <MyFavoriteQuestion ref="favRef" embedded />
    </div>
    <div v-show="activeTab === 'wrong'" class="tab-panel">
      <MyMistakes ref="wrongRef" embedded />
    </div>
    <div v-show="activeTab === 'marked'" class="tab-panel">
      <MyMarked ref="markedRef" embedded />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontQuestionManage' })

import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MyFavoriteQuestion from '../myFavoriteQuestion/index.vue'
import MyMistakes from '../myMistakes/index.vue'
import MyMarked from '../myMarked/index.vue'
import useTopbarStore from '@/store/modules/topbar'

type TabKey = 'favorite' | 'wrong' | 'marked'

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: 'favorite', label: '题目收藏' },
  { key: 'wrong', label: '我的错题' },
  { key: 'marked', label: '我的斩题' }
]

const route = useRoute()

/**
 * 初始分组：支持 `?tab=wrong` / `?tab=marked`
 *
 * 侧栏的「我的错题」「我的斩题」入口现在都指向本页（用 query 区分），
 * 不认这个参数的话，从「我的错题」点进来会落在「题目收藏」分组。
 */
const initTab = (): TabKey => {
  const t = String(route.query.tab || '')
  return t === 'wrong' || t === 'marked' ? t : 'favorite'
}
const activeTab = ref<TabKey>(initTab())

/*
 * 侧栏在同一个页面内切 `?tab=` 时（如已在本页、点另一个入口），
 * `activeTab` 的初始化只跑一次，需要监听 query 跟上。
 */
watch(
  () => route.query.tab,
  (t) => {
    const k = String(t || '')
    if (k === 'wrong' || k === 'marked' || k === 'favorite') activeTab.value = k as TabKey
  }
)

/* ---------- 顶栏计数 ---------- */
const favRef = ref<any>(null)
const wrongRef = ref<any>(null)
const markedRef = ref<any>(null)
const topbarStore = useTopbarStore()

/**
 * 把当前分组的总数推到顶栏
 *
 * 子页面的 `MyQuestion` 通过 `getTotal()` 暴露条数（刚加的）。
 * 分组切换 / 数据刷新后都读一次；元素还没挂好时静默跳过，
 * 等下一次 watch 触发。
 */
function syncTopbarCount() {
  const map: Record<TabKey, any> = {
    favorite: favRef.value,
    wrong: wrongRef.value,
    marked: markedRef.value
  }
  const el = map[activeTab.value]
  // 子页面 → MyQuestion 的层级：先取页面实例里的 myQuestionRef，再取 getTotal
  const inner = el?.myQuestionRef ?? el?.$refs?.myQuestionRef
  const n = Number(inner?.getTotal?.() ?? 0)
  const unit = '道题'
  topbarStore.setCount(n ? `${n} ${unit}` : '')
}

watch([activeTab, favRef, wrongRef, markedRef], () => {
  // 等子页面的数据渲染完再读
  requestAnimationFrame(syncTopbarCount)
}, { immediate: true })

onBeforeUnmount(() => topbarStore.clear())

</script>

<style scoped lang="scss">
.question-manage-page {
  padding: 0;
}

/*
 * 分组切换：与「题库管理」完全一致的形态
 * （下划线 + 无边框按钮；不用 el-tabs，避免外壳里再套一层描边）
 */
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
