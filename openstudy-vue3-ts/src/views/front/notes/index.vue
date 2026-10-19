<template>
  <div class="notes-container" :class="{ 'is-editor': isEditorPage }">
    <router-view v-slot="{ Component, route }">
      <template v-if="route.name === 'FrontNotesList'">
        <keep-alive>
          <component :is="Component" :key="route.fullPath" />
        </keep-alive>
      </template>
      <template v-else>
        <component :is="Component" :key="route.fullPath" />
      </template>
    </router-view>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: 'FrontNotes' })
import { useRoute, useRouter } from 'vue-router'
import { useFrontPageCacheStore } from '@/store/modules/frontPageCache'
import { computed, onMounted, onActivated, watch } from 'vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

/**
 * 「写笔记」页自己管滚动，需要一条完整的高度链
 * ==========================================
 * 用户 2026-10-19：「草稿页面没有滚动条 / 笔记编辑页面没有滚动条，整个页面无法滚动」。
 *
 * 根因：外层 `layout/front.vue` 把编辑页当成满高页面（`.os-content.is-flush`：
 * `overflow:hidden` + flex 列），**高度只给到这一层**：
 *
 *     .os-content.is-flush   908px  overflow:hidden   ← 高度在这里被卡住
 *     └ .notes-container    2399px  overflow:visible  ← 被内容撑高，没人约束
 *       └ .notes-editor-container  2399px             ← height:100% 拿到的是撑高后的值
 *         └ .editor-main     2327px  overflow:auto    ← 自己等于内容高，滚不动（可滚动量 0）
 *
 * 编辑页内部 `.editor-main` 早就写了 `overflow-y:auto`，但它的高度来自
 * `.notes-container` 的 `height:100%`；而 `.notes-container` 是普通 block、
 * 高度由内容撑开（2399px），于是「滚动容器」比内容还高 → 永远没有可滚动量，
 * 滚动条自然不出现。
 *
 * 修法：编辑页把 `.notes-container` 接进 flex 高度链（`display:flex` + `min-height:0`），
 * 让它严格等于父级给的高度，而不是被内容撑开。列表页保持原样（它靠外壳滚动）。
 */
const isEditorPage = computed(() => route.path === '/front/notes/editor')

onMounted(() => {
  if (route.path === '/front/notes') {
    const lastVisited = cacheStore.getLastVisited('notes', 'list')
    router.replace(`/front/notes/${lastVisited}`)
  } else {
    updateCachedPath()
  }
})

onActivated(() => {
  if (!route.path.startsWith('/front/notes')) return
  if (route.path === '/front/notes') {
    const lastVisited = cacheStore.getLastVisited('notes', 'list')
    router.push(`/front/notes/${lastVisited}`)
  } else {
    updateCachedPath()
  }
})

watch(() => route.path, () => {
  if (route.path !== '/front/notes') {
    updateCachedPath()
  }
})

function updateCachedPath() {
  const path = route.path
  if (path.startsWith('/front/notes/')) {
    const subPath = path.replace('/front/notes/', '')
    if (subPath) {
      // ⚠️ focusComment 是「一次性」跳转意图（私信 / 通知里点某条回复 → 跳到笔记并定位它）。
      //    它一旦进了 lastVisitedMap 就会被持久化到 localStorage，之后每次点顶部「学习分享」
      //    都原样重放那条 URL → 已经关掉的「查看对话」对话框又自己弹出来。
      //    位置记忆只记位置、不记命令；`editor?id=` 这种确实要记住的参数不受影响。
      const raw = route.fullPath.includes('?') ? route.fullPath.slice(route.fullPath.indexOf('?')) : ''
      const params = new URLSearchParams(raw)
      params.delete('focusComment')
      const queryStr = params.toString()
      cacheStore.setLastVisited('notes', subPath + (queryStr ? '?' + queryStr : ''))
    }
  }
}
</script>

<style lang="scss">
/*
 * 编辑页的高度链（修「写笔记页面无法滚动」，见 script 里的说明）
 * ------------------------------------------------------------------
 * 只对编辑页生效：列表页/详情页仍然让 `.os-content` 自己滚，行为不变。
 *
 * `.os-content.is-flush` 是 `display:flex` 列容器，这里让 `.notes-container`
 * 成为它的 flex item 且 `min-height:0` —— 这样它的高度**等于**父级剩余高度，
 * 而不是被内容撑开；再让 `.notes-editor-container` 的 `height:100%` 拿到这个确定值，
 * 一路传到 `.editor-main` 的 `overflow-y:auto`，滚动条才会真正出现。
 */
.notes-container.is-editor {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  /* 内容超出由内部的 .editor-main 滚，这一层不要自己滚（否则会出现双滚动条） */
  overflow: hidden;

  > * {
    flex: 1;
    min-height: 0;
  }
}
</style>
