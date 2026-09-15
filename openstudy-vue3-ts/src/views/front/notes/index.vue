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
      const queryStr = route.fullPath.includes('?') ? route.fullPath.substring(route.fullPath.indexOf('?')) : ''
      cacheStore.setLastVisited('notes', subPath + queryStr)
    }
  }
}
</script>
