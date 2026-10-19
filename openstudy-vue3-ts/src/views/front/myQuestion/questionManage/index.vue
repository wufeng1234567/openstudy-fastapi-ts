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

  ## 顶栏计数（2026-10-19 修 bug）

  用户反馈：「第一次点击题目管理，默认进入题目收藏，但上方标题没有题目数，
  必须点一下别的 tab 才出现」。

  原因是之前只在 `watch([activeTab, refs])` 里读一次 `getTotal()`，
  而**首次进入时**：三个子页还在挂载 / 首屏请求还没回来，
  `requestAnimationFrame` 里读到的 `total` 还是 0，之后数据到位也没有再触发。

  现在改成「**子页面自己上报**」：三个子页面各自 `watch` 自己的 total 并 emit，
  壳只负责记录 + 把当前分组的数字推给顶栏。
  这样无论数据什么时候回来（首次 / 刷新 / 删除后），顶栏都会跟着更新。
-->
<template>
  <div class="question-manage-page">
    <!-- 分组切换（与「题库管理 / 笔记管理」共用一个组件，视觉只有一份定义） -->
    <SegmentedTabs v-model="activeTab" :tabs="tabItems" />

    <!-- 三个分组常驻（v-show：切换瞬时，不重新拉数据） -->
    <div v-show="activeTab === 'favorite'" class="tab-panel">
      <MyFavoriteQuestion ref="favRef" embedded @total-change="onTotalChange('favorite', $event)" />
    </div>
    <div v-show="activeTab === 'wrong'" class="tab-panel">
      <MyMistakes ref="wrongRef" embedded @total-change="onTotalChange('wrong', $event)" />
    </div>
    <div v-show="activeTab === 'marked'" class="tab-panel">
      <MyMarked ref="markedRef" embedded @total-change="onTotalChange('marked', $event)" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontQuestionManage' })

import { computed, onActivated, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import MyFavoriteQuestion from '../myFavoriteQuestion/index.vue'
import MyMistakes from '../myMistakes/index.vue'
import MyMarked from '../myMarked/index.vue'
import SegmentedTabs from '@/components/SegmentedTabs/index.vue'
import useTopbarStore from '@/store/modules/topbar'

type TabKey = 'favorite' | 'wrong' | 'marked'

const TAB_DEFS: Array<{ key: TabKey; label: string }> = [
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
    /*
     * ⚠️ 必须确认「当前确实停在本页」。
     * 本页是 keep-alive 的，用户切到「笔记管理」后本组件仍然存活；
     * 「笔记管理」用的也是 `?tab=` —— 不加路径判断，
     * 这里会被别人的 `?tab=own` 唤醒，把 activeTab 误翻成「题目收藏」，
     * 还会把「6 道题」推到顶栏（同一个 bug 的反向版本）。
     */
    if (!route.path.startsWith('/front/myQuestion/questions')) return
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
 * 各分组的上报状态
 * ----------------------------------------------------------------------------
 * 子页面（题目收藏 / 我的错题 / 我的斩题）在数据变化时 emit `total-change`，
 * payload 是 `{ total, loading }`。三个页面都是 `v-show` 常驻，
 * 所以三份数据会各自上报，切分组立刻有数。
 *
 * `ready` 是关键：加载中收到的数字只是中间值（可能先 0 后 N），
 * 不能直接显示，否则顶栏会「闪两下」（用户 2026-10-19 反馈）。
 */
interface CountState {
  total: number
  /** 该分组是否已经完成过一次加载（拿到确定的条数） */
  ready: boolean
}

const states = ref<Record<TabKey, CountState>>({
  favorite: { total: 0, ready: false },
  wrong: { total: 0, ready: false },
  marked: { total: 0, ready: false }
})

/** 分组切换条的入参：标签 + 角标计数（只显示已就绪的分组） */
const tabItems = computed(() =>
  TAB_DEFS.map((t) => ({
    ...t,
    count: states.value[t.key].ready ? states.value[t.key].total || undefined : undefined
  }))
)

function onTotalChange(key: TabKey, payload: { total: number; loading: boolean }) {
  const prev = states.value[key]
  // 加载中：只记录数字，不认作"已就绪"
  if (payload.loading) {
    states.value = { ...states.value, [key]: { total: payload.total, ready: prev.ready } }
    return
  }
  states.value = { ...states.value, [key]: { total: payload.total, ready: true } }
}

/* 分组切换或任一状态变化 → 刷新顶栏 */
watch(
  [activeTab, () => states.value.favorite, () => states.value.wrong, () => states.value.marked],
  () => {
    // keep-alive 下本页可能已不在前台：不要往顶栏推别人的计数
    if (!route.path.startsWith('/front/myQuestion/questions')) return
    const st = states.value[activeTab.value]
    /*
     * 只有**已就绪**才写顶栏。
     * 未就绪 = 数据还在路上，这时写 ""（或写中间值）都会让文字跳一下；
     * 干脆什么都不做，等 ready 后再精确写一次（`topbar` store 本身也做了同值不写）。
     */
    if (!st.ready) return
    topbarStore.setCount(`${st.total} 道题`)
  },
  { immediate: true }
)

// 回到本页时重新推一次（离开期间顶栏被清空过）
onActivated(() => {
  const st = states.value[activeTab.value]
  topbarStore.setCount(st.ready ? `${st.total} 道题` : '')
})

onBeforeUnmount(() => topbarStore.clear())
</script>

<style scoped lang="scss">
.question-manage-page {
  padding: 0;
}

/* 分组切换条已抽到 `SegmentedTabs`（三个管理页共用一份样式），这里不再重复定义 */

.tab-panel {
  min-height: 0;
}
</style>
