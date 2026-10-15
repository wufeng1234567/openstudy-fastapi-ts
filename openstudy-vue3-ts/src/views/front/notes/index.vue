<template>
  <div class="notes-container">
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
import { onMounted, onActivated, watch } from 'vue'

const route = useRoute()
const router = useRouter()
const cacheStore = useFrontPageCacheStore()

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
